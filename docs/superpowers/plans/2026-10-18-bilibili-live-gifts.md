# Bilibili Live Gifts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前播放器的颜文字右侧添加送礼入口，以真实 GIF、房间分类、数量选项和电池余额支持普通礼物及背包赠送，并在成功送出后移出鼠标时关闭浮窗。

**Architecture:** 礼物 API、账号状态、媒体与浮窗分别放进四个新模块，`DanmakuComposer` 负责入口及生命周期。账号级协调器限制同一账号只有一次赠送在途，并让各格子的余额和库存同步失效；所有请求捕获房间和凭据，UI 通过带版本的状态快照接收结果。沿用现有表情、Cookie 和后台线程模式，不重构播放器。

**Tech Stack:** 现有 Python 3.13 环境、PySide6、requests、标准库 unittest；不增加外部依赖。

**Spec:** [2026-10-18-bilibili-live-gifts-design.md](../specs/2026-10-18-bilibili-live-gifts-design.md)，用户已于 2026-10-18 批准。

## Global Constraints

- 在 `codex/bilibili-live-gifts` 开发，分支已从 `codex/bilibili-danmaku-send2` 的 `41c5b5a` 创建；现有未跟踪 `.codegraph/` 不加入提交。
- 工具栏顺序为输入框、颜文字、礼物、发送；礼物按钮为 28×28 逻辑像素。
- 不新增登录体系、数据库、平台插件或外部依赖，沿用当前 Python、PySide6、requests 和账号凭据。
- 首版支持普通电池礼物及当前账号、房间允许赠送的背包礼物；大航海、装扮、红包等独立购买流程保留展示和提示，禁用普通赠送。
- 原始金额使用整数；100 个原始单位为 1 电池，不把 `bp` 等余额相加。只有一个数量选项时点击即送，多数量或自定义数量使用数量窗的“赠送”按钮。
- 赠送成功后，鼠标还在礼物浮窗内时保持打开；鼠标移到浮窗外时默认关闭。
- 请求不自动重试，不跨 v1/v2 或付费/背包接口重发；背包库存不足不得改为购买。
- 每个完成的改动必须有对应 commit，并更新相关测试、通过验证。下面每个任务都包含自己的测试周期与提交。
- 自动测试不用真实 Cookie、不保存真实配置、不执行真实扣费赠送；只读服务验证与真实送礼验证分别报告。

## Review Focus

1. 同一种背包礼物存在多个到期批次，必须使用选中批次的 `bag_id`，不能合并或扣到另一批；由任务 1、2 测试。
2. 余额/背包读取响应在一次成功赠送之前发出、之后才返回，不能恢复旧余额或库存；由任务 2 的账号版本测试覆盖。
3. 用户点击后、准备账号/主播信息期间切换房间，尚未提交的 POST 必须取消；由任务 2 覆盖。
4. 已送过一次、第二次仍在途时移出窗口，不能提前隐藏或把失败误作成功；由任务 4 覆盖。
5. 原生视频窗口、全屏、高 DPI 与数量窗间的缝隙可能吞掉鼠标事件，需验证可点击、不误关及退出时无残留线程；由任务 5 覆盖。

---

## File Structure and Shared Contracts

| 文件 | 职责 |
| --- | --- |
| 新建 `ddm/gift_api.py` | 不操作控件的规范化、只读 API、身份准备及单次赠送 HTTP 请求 |
| 新建 `ddm/gift_controller.py` | Qt 后台请求、房间/账号版本、账号级赠送锁与失效广播 |
| 新建 `ddm/gift_media.py` | 保留 GIF 原始字节的缓存、后台加载和 `QMovie` 生命周期 |
| 新建 `ddm/gift_popup.py` | 礼盒按钮、主浮窗、礼物卡片、数量窗及成功后关闭逻辑 |
| 修改 `ddm/danmaku_send.py` | `DanmakuComposer` 插入礼物按钮及联动，保留现有表情接口 |
| 修改 `ddm/app.py` | 主窗隐藏后的退出等待追加礼物请求等待 |
| 新建 `dev/gift_fixtures.py` | 人造且脱敏的真实形状响应，不包含任何个人数据 |
| 新建 `dev/selfcheck_gift_api.py`、`dev/selfcheck_gift_controller.py` | 读取、编码、失败分类、竞争与异步隔离回归 |
| 新建 `dev/selfcheck_gift_media.py`、`dev/selfcheck_gift_popup.py` | GIF 生命周期及真实 Qt 两级浮窗回归 |
| 修改 `dev/selfcheck_danmaku_composer.py` | 按钮顺序、窗口互斥、换房、主题及窄格集成回归 |
| 修改 `README.md`、`docs/README.md`、`docs/repository-map.md` | 功能说明、文档入口和已跟踪文件清单 |

任务 1 定义以下不可变数据类型，后续任务直接使用，禁止重复一套字典键：

- `GiftItem`：`key: str`、`source: str`（`gold`/`bag`/`unsupported`）、`gift_id: int`、`name: str`、`price: int`、`gif_url: str`、`image_url: str`、`counts: tuple[int, ...]`、`max_count: int`、`allow_custom: bool`、`disabled_reason: str`、`bag_id: int = 0`、`stock: int = 0`、`expires_at: int = 0`。
- `GiftTab`：`key: str`、`title: str`、`items: tuple[GiftItem, ...]`。
- `GiftCatalog`：`tabs: tuple[GiftTab, ...]`、`configs: dict[int, dict]`、`max_send_count: int`。`configs` 保留基础/房间合并后的元数据，仅 `tabs` 中引用的条目可付费送出。
- `GiftTarget`：`room_id: str`、`uid: int`、`ruid: int`。
- `GiftResult`：`gift_key: str`、`quantity: int`、`payload: dict`。
- `GiftSendError(ValueError)`：`uncertain: bool`，区分服务端明确拒绝与提交后结果未知。

普通礼物 `key` 包含分类和礼物 ID，背包 `key` 包含真实 `bag_id`。`disabled_reason` 非空即禁止赠送。无明确普通支付语义的特殊项和银瓜子直购项归为 `unsupported`，不新增未批准的银瓜子兑换/支付功能。

测试从 `dev/gift_fixtures.py` 使用 `room_payload()`、`bag_payload()`、`single_item()`、`multi_item()`；函数每次返回全新的对象。固定 fixture 使用房间 90001、发送者 UID 123、主播 UID 456、原始单价 5200，数量配置 `(1, 10, 100, 520)`；背包有同礼物的两个批次 701、702，各有独立库存和有效期。

## Task 1: Room Catalog, Wallet and Bag Reads

**Files:** Create `ddm/gift_api.py`, `dev/gift_fixtures.py`, `dev/selfcheck_gift_api.py`; update `docs/repository-map.md` for the two new dev files.

**Interfaces:**
- Consumes: `bili._cookies()`, `bili.ensure_buvid3()`, `bili.HEADERS`, `bili._danmaku_result(response)`; follow `bili.get_emoticons` for request conventions.
- Produces: data types above; `normalize_catalog(data: dict, room_id: str) -> GiftCatalog`; `normalize_bag(data: dict, catalog: GiftCatalog, room_id: str, *, now: int) -> GiftTab`; `format_battery(raw: int) -> str`.
- Produces: `get_catalog(room_id: str, *, cookies: dict) -> GiftCatalog`; `get_wallet(*, cookies: dict) -> int`; `get_bag(room_id: str, catalog: GiftCatalog, *, cookies: dict) -> GiftTab`. HTTP timeout is 10 seconds; reads receive captured cookies rather than looking up changing globals halfway through.

- [ ] **Step 1: Write the failing normalization/read tests.** Add `test_room_references_override_and_stable_order`, `test_count_limits_permissions_and_special_pay`, `test_wallet_units_and_unknown_value`, `test_null_bag_and_separate_batches`, `test_read_urls_captured_cookies_and_rejections`. Include these exact outcomes:

```python
self.assertEqual(format_battery(5200), "52")
self.assertEqual(format_battery(105), "1.05")
self.assertEqual(normalize_bag({"list": None, "gift_config": None}, catalog, "90001", now=100).items, ())
self.assertEqual([item.bag_id for item in bag.items], [701, 702])
```

  Check that an unreferenced config never becomes a card; room config overrides base; duplicate or invalid counts are removed, custom limits are enforced, `interactive_pay` and `special.is_use=0` are disabled, expired/wrong-room inventory cannot send, and 0 differs from missing gold. Check main/tab item sorting and absent GIF static fallback separately.
- [ ] **Step 2: Run the test and confirm failure.** Run `.\.venv\Scripts\python.exe dev\selfcheck_gift_api.py`; expected missing `ddm.gift_api` or missing interface assertions, not an unrelated import error.
- [ ] **Step 3: Implement the declared data/read interfaces.** Merge configs by gift ID with room override, resolve only room references, and parse `gold` as a nonnegative integer without float math. Normalize both `list=null` and `[]` to an empty bag. Use the three already investigated GET endpoints from the spec. Malformed responses show an explicit error; they cannot silently become balance 0 or usable inventory. Preserve server bag order and individual batch identity; use bag-specific metadata before falling back to catalog metadata.
- [ ] **Step 4: Verify the tests pass.** Run the complete `dev/selfcheck_gift_api.py`; expected all tests pass without external network or real configuration access.
- [ ] **Step 5: Commit.** Stage only task files plus the updated inventory and commit as `feat: read room gifts wallet and gift bag`.

## Task 2: Single-Submission Sending and Shared Account State

**Files:** Modify `ddm/gift_api.py`; create `ddm/gift_controller.py`, `dev/selfcheck_gift_controller.py`; extend `dev/selfcheck_gift_api.py` and the inventory.

**Interfaces:**
- Consumes: task 1 types and read functions; existing `bili.send_danmaku` and `dev/selfcheck_danmaku_send.py` as references for encoding, cookies and local HTTP verification.
- Produces in `gift_api`: `prepare_target(room_id: str, *, cookies: dict) -> GiftTarget`; `send_gift(target: GiftTarget, item: GiftItem, quantity: int, *, cookies: dict, wallet: int | None, still_current: Callable[[], bool]) -> GiftResult`.
- Produces in `gift_controller`: `GiftPanelState` with `tabs: tuple[GiftTab, ...]`, `wallet: int | None`, `catalog_error: str`, `wallet_error: str`, `bag_error: str`, `loading: frozenset[str]`, `sending: bool`, `feedback: str`.
- Produces: `GiftController(parent: QObject | None = None)`, signals `stateChanged(object)`, `sent(object)`, `failed(str, bool)`, `deviceCookieReady()`; methods `set_context(room_id: str, cookies: dict) -> None`, `load(*, force: bool = False) -> None`, `send(gift_key: str, quantity: int) -> None`, `shutdown() -> None`; `.state: GiftPanelState` exposes current immutable state.
- Produces: `start_worker(worker: QThread, priority=QThread.InheritPriority) -> None`, `wait_for_requests() -> None`, with registry lifetime independent of the popup. Task 3 uses the same registry for media threads.

- [ ] **Step 1: Pin the sending contract from sources, without a real POST.** Start with the inspected 17.4.2 `sendGold`/`sendBag` source in the spec; inspect current public source for the documented v2 bag variant. Fix one selected version per operation in the code and a test assertion, and record why. Default to source-confirmed v1 ordinary gifting; select the bag version only after checking its exact fields. Never discover a version by retrying an uncertain POST. `prepare_target` reads sender UID using the captured cookies and resolves room/anchor through `room_init`; do not use the global `my_uid()` cache across snapshots.
- [ ] **Step 2: Write failing sending/controller tests.** Name and assert: `test_form_uses_sender_anchor_real_room_and_csrf` (123/456/90001, exact single form POST and no redirects); `test_bag_uses_selected_batch_without_paid_fallback` (bag 702, never 701); `test_timeout_disconnect_and_bad_success_json_never_retry` (`post.call_count == 1`, uncertain true); `test_invalid_quantity_funds_credentials_or_special_never_post` (`post.assert_not_called()`). Use a local HTTP server for actual form encoding, matching the existing danmaku tests.

  Controller tests use threading barriers: `test_one_send_per_account_across_controllers` asserts one POST while a second controller submits; `test_context_change_before_post_cancels` changes room during identity preparation and asserts zero POSTs; `test_old_read_after_success_cannot_restore_state` releases an old wallet/bag response after invalidation and asserts it is ignored. Also cover independent read failures, old account callbacks, duplicate clicks, successful send followed by refresh failure, deleted receivers and thread completion.
- [ ] **Step 3: Run both test files and confirm the new assertions fail.** Run the task 1 API test and controller test separately; expected missing send/controller behavior.
- [ ] **Step 4: Implement the declared send/controller interfaces.** Validate positive integers, legal presets/custom quantities, server limits, permissions, expiry, selected inventory and funds immediately before POST. Recheck `still_current()` after all preparatory reads. Use captured Cookie/CSRF and `Origin`/room `Referer`; 10-second timeout, `allow_redirects=False`, no retry adapter. Explicit rejections become `GiftSendError(uncertain=False)`; transport or unparseable post-submission outcomes become uncertain errors. Treat nonempty failure messages even in `code=0` as failures, following the existing result parser pattern.

  In the GUI thread maintain account identity `(SESSDATA, bili_jct)`, one in-flight reservation and a monotonically increasing shared data revision. Claim before starting work, release on all completion/cancellation paths. Success or uncertain submission invalidates wallet and bag revisions for all controllers; open consumers refresh, hidden ones reload next open. Already-issued reads from old revisions are discarded. Controllers own no UI windows; snapshots include independent catalog/wallet/bag loading and errors. Closing a view does not destroy running workers or reopen it on completion.
- [ ] **Step 5: Verify all API/controller tests pass and commit.** Run both files, require no failures, then commit task files and inventory as `feat: send live gifts with account scoped coordination`.

## Task 3: Animated Gift Media with Bounded Background Loading

**Files:** Create `ddm/gift_media.py`, `dev/selfcheck_gift_media.py`; update inventory.

**Interfaces:**
- Consumes: `gift_controller.start_worker`; `ddm.images` cache-path and image-worker conventions; `ddm.widgets.LoadingIndicator` as the existing `QMovie` lifecycle reference.
- Produces: `GiftMediaLoader(parent: QObject | None = None)`, signal `loaded(int, str, str)` for generation, URL and cached raw-file path; `failed(int, str)`; methods `request(urls: tuple[str, ...], generation: int) -> None`, `cancel() -> None`.
- Produces: `GiftImageLabel(parent: QWidget | None = None)`, methods `set_file(path: str) -> None`, `set_playing(playing: bool) -> None`; `.movie: QMovie | None` for animation state. Main-thread construction owns the `QMovie`; network workers never create widgets.

- [ ] **Step 1: Write failing media tests.** `test_raw_gif_keeps_multiple_frames` uses a tiny two-frame GIF fixture and asserts `movie.frameCount() == 2`; `test_hide_pauses_and_show_resumes` checks Qt movie state; `test_static_fallback_and_failed_url_keep_label_usable` checks fallback and retained name/price in the consumer; `test_cancelled_generation_does_not_apply` checks callback version; `test_at_most_two_downloads_and_cache_reuse` counts in-flight GETs and repeat reads. Use a temporary cache under `work/`, not the user's cache.
- [ ] **Step 2: Run `.\.venv\Scripts\python.exe dev\selfcheck_gift_media.py` and confirm missing media behavior.**
- [ ] **Step 3: Implement the interfaces.** Preserve unconverted response bytes in `cache/gifts/` under a hash of the URL; restrict input URLs to HTTP(S), use 10-second timeouts, and publish a path only after a complete successful write. Support at most two concurrent downloads; cancellation stops scheduling new work. `QMovie` and its backing file remain valid while visible. Hidden/removed cards pause or release movies; invalid GIF tries the item's static fallback without losing readable text. Queue only the current page's visible cards, with scroll-driven scheduling for additional visible rows.
- [ ] **Step 4: Run the complete media test file; expected all pass.**
- [ ] **Step 5: Commit as `feat: cache and animate visible gift images`.**

## Task 4: Main Gift Popup, Quantity Popup and Pointer Closing

**Files:** Create `ddm/gift_popup.py`, `dev/selfcheck_gift_popup.py`; update inventory.

**Interfaces:**
- Consumes: `GiftItem`, `GiftTab`, `GiftPanelState`, `format_battery`, `GiftMediaLoader`, `GiftImageLabel`; reference `EmoticonPopup.open_at`, themed styles, screen clipping and batch construction.
- Produces: `GiftButton(QPushButton)`; `GiftPopup(parent: QWidget | None = None)` with signals `sendRequested(str, int)`, `refreshRequested()`; methods `open_at(button: QWidget) -> None`, `set_state(state: GiftPanelState) -> None`, `mark_sent(result: GiftResult) -> None`, `shutdown() -> None`.
- Produces internal `GiftQuantityPopup` and `GiftCard`; `.quantity_popup` identifies the live child. The popup retains no Cookie and emits gift key plus count only; the controller validates them again.

- [ ] **Step 1: Write failing Qt interaction tests.** `test_single_click_sends_one_without_dialog` asserts exactly `[(key, 1)]`; `test_multi_hover_and_original_click_only_open_quantity` asserts no request until choosing 10 and clicking “赠送”; `test_custom_counts_invalid_or_insufficient_disable_send` covers 0, negatives, nonintegers, over-limit and over-budget. Include locked/special cards, empty bag, independent errors, gift order, clipping, narrow columns and inaccessible GIF fallback.

  Pin closing with `test_browsing_leave_keeps_open`, `test_success_inside_keeps_open_then_leave_closes_both`, `test_success_arrives_when_pointer_outside_closes`, `test_crossing_into_quantity_popup_does_not_close`, `test_second_send_inflight_defers_pointer_close`, `test_failure_before_first_success_keeps_open`, `test_hidden_completion_never_reopens` and `test_reopen_resets_success_latch`. Move the real cursor for Qt tests; assert visible state after event delivery, not only private flags.
- [ ] **Step 2: Run `.\.venv\Scripts\python.exe dev\selfcheck_gift_popup.py`; expected missing popup behavior.**
- [ ] **Step 3: Implement the popup interfaces.** Start at 400×340, five columns, 28×28 button, existing theme tokens and accessible names; clip both windows to screen and reduce columns on narrow screens. Show GIF/name/price and bag stock/expiry. Use the actual Qt mouse area of both windows, allow their connecting gap with a 150 ms close timer, and arm mouse-out closing only after `mark_sent`. Suppress this auto-close while `state.sending`; on completion re-evaluate current cursor position. External click/Esc/button-toggle/context loss closes both, and opening resets the success latch. Visible items alone request media; changing page/hiding cancels unused work.
- [ ] **Step 4: Run popup and media test files; expected all pass.**
- [ ] **Step 5: Commit as `feat: add gift popup and quantity interactions`.**

## Task 5: Composer Integration, Exit Lifecycle and Final Verification

**Files:** Modify `ddm/danmaku_send.py:422` (`DanmakuComposer`), `ddm/app.py:1000` (exit wait), `dev/selfcheck_danmaku_composer.py`, `README.md`, documentation indexes/inventory; extend the gift tests for integration. Keep edits to `ddm/widgets.py` unnecessary unless actual native-window evidence requires a local fix.

**Interfaces:**
- Consumes: tasks 1–4 interfaces. Existing `DanmakuComposer.set_room`, `sync_credentials`, `hideEvent`, `shutdown`, `open_emoticons` are the context/lifecycle hooks; `deviceCookieReady` already reaches the app's persistence callback.
- Produces: `DanmakuComposer.gift_button: GiftButton`, `.gift_popup: GiftPopup | None`, `.gift_controller: GiftController | None`, `open_gifts(_checked: bool = False) -> None`; existing public methods and `.popup` (emoticons) retain behavior.

- [ ] **Step 1: Write failing integration tests.** Add `test_gift_button_order_toggle_and_emoticon_exclusion`; assert the row positions are edit < emote < gift < send, and opening either popup hides the other. Add `test_gifts_context_switch_hides_both_and_ignores_old_response`, `test_gift_success_refresh_preserves_danmaku_draft`, and `test_exit_wait_includes_gift_and_media_workers`. Extend the existing dark/light and 900/360/200-width tile layout test to assert gift size 28×28 and usable input width; verify a non-B站/empty room hides the entry. Test fullscreen and native video hit-testing with the same native-control patterns used by `dev/selfcheck_native_control_hit.py` and `dev/selfcheck_tile_fullscreen.py`.
- [ ] **Step 2: Run composer and relevant gift tests; confirm missing integration assertions fail.**
- [ ] **Step 3: Wire the interfaces.** Lazily create the controller and popup on the first authenticated click; forward refreshed credential snapshots on room/auth updates, and connect `deviceCookieReady` to the composer signal. Open first and then load state in the background. Keep gift status independent from the text-danmaku busy flag/draft, and retain Enter sending. On hide/shutdown close both gift windows and stop media; on app exit wait for bounded gift/media workers after the main window is hidden. Recalculate the send-button visibility threshold so all three compact controls and input fit small tiles.
- [ ] **Step 4: Update user-facing docs and inventory.** Document one-click and multiple-quantity behavior, bag isolation, success-after-leave closing, special-flow limitations and unknown-result messages. Mark this plan's completed steps and update the design/README status only when implementation evidence exists. List every new dev/doc file in `docs/repository-map.md`.
- [ ] **Step 5: Run the final scoped regression set in separate processes, fail on any nonzero exit.** Use the environment setup below, then every new `selfcheck_gift_*.py`, `selfcheck_danmaku_send.py`, `selfcheck_danmaku_composer.py`, `selfcheck_emoticon_tabs.py`, `selfcheck_bili_cookies.py`, `selfcheck_native_control_hit.py`, `selfcheck_tile_fullscreen.py`, `selfcheck_repository_files.py`, `selfcheck_repository_map.py`, plus any tests whose modules were actually changed. Expected: every selected script exits 0; `git diff --check` is clean; compileall succeeds for the changed Python files. Broaden testing only for new failures or additional touched modules.
- [ ] **Step 6: Perform visible and read-only checks.** Use a running Qt window to check real GIFs, hover path, outside click, successful/failed responses simulated locally, dark/light, full screen and high DPI over VLC. Read the real room list/wallet/bag without printing credentials or personal values. Do not invoke real `sendGold`/`sendBag` without an explicit room/gift/count instruction. Record what was verified and what remains untested against the real paid service.
- [ ] **Step 7: Commit as `feat: integrate live gifting into player composer`.** Before final delivery perform one independent whole-branch review and fix any material findings with related tests and commits; no push, PR, merge or release is required by this request.

## Verification Environment

Use source environment `.\.venv\Scripts\python.exe`. Tests set `DDM_NO_SAVE=1` and `QT_QPA_PLATFORM=offscreen` except the explicitly visible native-window pass. The existing `dev/run-checks.cmd` pauses and does not propagate each test's exit status, so invoke the selected scripts individually and inspect every result.

```powershell
$giftCheckTemp = Join-Path (Get-Location).Path 'work\gift-checks-tmp'
New-Item -ItemType Directory -Path $giftCheckTemp -Force | Out-Null
$env:TEMP = $giftCheckTemp
$env:TMP = $giftCheckTemp
$env:DDM_NO_SAVE = '1'
$env:QT_QPA_PLATFORM = 'offscreen'
$env:PYTHON_VLC_LIB_PATH = Join-Path (Get-Location).Path 'libvlc.dll'
$env:PYTHONIOENCODING = 'utf-8'
```

Existing documentation tests launch PowerShell. If the sandbox produces `AuthorizationManager check failed`, request the standard tool escalation for that exact test command; keep test temporary paths within the repository. Do not change security policy or weaken the tests to make this pass.

## Plan Self-Review

Completed before handoff: every spec requirement maps to one of the five tasks; main/quantity close rules map to task 4 and lifecycle to task 5; identities, integer money, versioning, inventory and no-retry map to tasks 1–2; raw GIF/cache scope maps to task 3. Shared type names, signal signatures and integration method names match across tasks. The five Review Focus cases each have a named test above. Product implementation remains pending plan review and execution-method selection.
