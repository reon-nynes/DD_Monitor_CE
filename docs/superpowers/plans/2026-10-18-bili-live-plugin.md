# Generic Tile Extensions and bili_live Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide stable host extension hooks and deliver the send2 composer, emoticons and approved Bilibili live-gifting behavior as an installable `bili_live` plugin.

**Architecture:** The application owns tile attachment/layout, credential storage and fullscreen interaction; the plugin owns all sending/gifting requests, UI and workers. Register providers once and attach controls through the host's tile lifecycle. Captured credentials, cancellation tokens and account/data generations prevent stale work from affecting a new context.

**Tech Stack:** Existing Python 3.13, PySide6, requests and standard-library unittest; existing ZIP tooling. No new runtime dependency.

**Spec:** [Approved cross-repository design](../specs/2026-10-18-bili-live-plugin-design.md), approved 2026-10-18. The sending source is host commit `7c034e2700449cb2c67c05a80776577826c39933`; original gift specification/plan are available through `git show codex/bilibili-live-gifts:docs/superpowers/specs/2026-10-18-bilibili-live-gifts-design.md` and its adjacent `plans/2026-10-18-bilibili-live-gifts.md`.

## Global Constraints

- Host root `D:\Dev\DD_Monitor_CE`, branch `codex/plugin-tile-extensions`, based on cookie-persistence `7011541`; plugin root `D:\Dev\DD_Monitor_Plugins`, branch `codex/bili-live`, based on `7f909be`.
- Keep Bilibili playback, receiving, login and storage in the host. Do not merge the complete send2/gifts branches or create a second login.
- Composer order is input, emoticon button, gift button, send. Emoticon and gift buttons are 28 by 28 logical pixels. Verify tile widths 900, 360 and 200; preserve useful typing space and existing player controls.
- Use raw integers for price and wallet arithmetic; 100 raw units display as one battery. Preserve separate bag IDs and never replace a bag operation with a paid purchase.
- Exactly one gift submission may be in flight for an account across all tiles. Do not retry POSTs automatically, switch endpoint versions on failure, or fall back between paid/bag operations.
- Preserve the spec's complete mouse-out-after-success rules. Account/room changes, hiding/removal and explicit dismissal close windows without resubmitting or reopening on delayed completion.
- Retain restart-based plugin enable/disable/removal and the legacy sender interface. Do not introduce composer/gift imports or private UI patching into the host.
- Every completed change includes relevant new/updated tests, passing verification and its own repository's Git commit. Preserve the untracked `.codegraph/`; do not push, merge, create a PR or publish a release.
- Tests use fake credentials, temporary config/cache roots and `DDM_NO_SAVE=1`. Real gift submissions need an explicit room/gift/count instruction. Report simulated, native-window and real-service evidence separately.

## Review Focus

1. A provider registered while every tile is empty must appear after a later room assignment; factory-once and room-copy tests belong to task 1.
2. A low-priority control hidden by width overflow must reappear on widening without overriding the plugin's own unsupported-room hiding; wrapper/visibility tests belong to task 1.
3. Device-cookie publication racing a new login must not replace that login's identity or invalidate the request that obtained the device cookie; generation/persistence tests belong to task 2 and plugin tests in task 3.
4. Removing a view or switching accounts while a gift POST is already in flight must not release its reservation early or apply a stale wallet read; barrier tests belong to task 5.
5. A second send after a success, movement across the quantity-popup gap, and a hidden view's delayed completion must obey the original closing behavior; real Qt interaction tests belong to task 7 and packaged integration in task 8.

---

## File Structure and Shared Interfaces

Host additions: `ddm/plugin_controls.py` implements managed Qt attachments; `ddm/plugin_credentials.py` implements provider-neutral snapshots/adapters. `ddm/plugins.py` exposes/re-exports the public contracts. Integrate through `ddm/widgets.py`, `ddm/app.py`, `ddm/fullscreen_cursor.py` and the existing Bilibili cookie store. Avoid restructuring those large modules.

Plugin additions live in `plugins/bili_live/`: `plugin.py` entry/lifecycle, `session.py` shared host credential binding, `workers.py` request lifetime, `bili_api.py` sending/common Bilibili HTTP helpers, `composer.py` and `emoticons.py` extracted UI, `gift_api.py`, `gift_controller.py`, `gift_media.py`, and `gift_popup.py`. Tests live in the plugin repository, alongside a shared `tests/bili_live_support.py` that accepts `--host` and loads the real plugin package under the host loader's module name.

Public host contracts to implement:

- `TileControlContext(parent, room: dict, invalidate_layout: Callable[[], None])`: Qt parent and detached current room. Context room is refreshed on every assignment.
- `TileControl(widget, *, minimum_width: int = 0, preferred_width: int = 240)`: methods `set_room(room: dict) -> None`, `interaction_active() -> bool`, `shutdown() -> None`; widget controls its own supported-room visibility.
- `PluginContext.register_tile_control(control_id: str, factory: Callable[[TileControlContext], TileControl], *, priority: int = 0) -> None`. Higher priority appears first; equal priorities retain registration order. Manager host entry points: `attach_tile(tile)`, `detach_tile(tile)`.
- `CredentialSnapshot(platform: str, generation: int, values: dict[str, str])`: frozen record with detached values; exclude credentials from repr/logs. Unavailable platform returns `None`.
- Manager host-only registration: `register_credentials(platform, read, *, update=None, identity_keys=(), writable_fields=())`; `notify_credentials(platform) -> None` samples the provider and advances generation only when identity keys change.
- `PluginContext.credentials(platform: str) -> CredentialSnapshot | None`; `update_credentials(platform: str, changes: dict[str, str], *, expected_generation: int) -> bool`. Reject stale generations; raise a clear ValueError for unsupported keys/provider updates. GUI-thread-only public calls; captured values are safe for workers.
- `EVENT_ACCOUNT_CHANGED = "account.changed"` with platform/generation; `EVENT_CREDENTIALS_UPDATED = "account.credentials_updated"` with platform/generation/field names. Neither event includes secret values.
- `Tile.plugin_interaction_active() -> bool`: isolated aggregate query of applicable, visible and enabled registered controls.

## Task 1: Generic Tile Attachment, Layout and Cleanup

**Files:** Create host `ddm/plugin_controls.py`, `dev/selfcheck_plugin_controls.py`; modify `ddm/plugins.py`, `ddm/widgets.py`, `ddm/app.py`, `docs/plugins.md`, `docs/repository-map.md`.

**Interfaces:** Produces the tile contracts above. `plugin_controls.TileControls` owns per-tile wrapper widgets, provider attachments, room delivery, width allocation and idempotent shutdown. The host manager tracks tiles weakly and defers provider activation until successful `on_load`; headless managers with no tiles can register without constructing widgets.

- [ ] **Step 1 — Write failing tests.** `test_existing_new_and_initially_empty_tiles_receive_one_control` asserts one factory call per provider/tile after repeated wiring and an initial room callback. `test_every_assignment_is_delivered_as_a_copy` covers None, same-ID metadata, replacement, swap and restoration; mutation of the received dictionary must leave `tile.room` unchanged. `test_failed_load_rolls_back_controls` and `test_provider_exceptions_do_not_block_others` assert partial widgets are removed and a second provider still updates. `test_remove_and_unload_shutdown_once` asserts a shutdown counter of one after removal followed by unload.
- [ ] **Step 2 — Run** `.\.venv\Scripts\python.exe dev/selfcheck_plugin_controls.py`; expect failure for the missing public contracts, not missing Qt/VLC dependencies.
- [ ] **Step 3 — Implement** registration and tile attachment. Use a host-owned wrapper for each plugin widget: width overflow hides the wrapper while unsupported-room hiding remains the widget's own state. Existing tiles attach after `plugins.load()`; later tiles attach from `_wire_tile`. Call room delivery inside `Tile.set_room` for all branches, including its empty-room return. Keep initial-construction guards and fullscreen reparenting safe. Roll back only the failing provider's resources, isolate callbacks and disconnect on disposal.

  Add width tests `test_no_extension_layout_is_preserved`, `test_priority_overflow_recovers_on_widening`, `test_compact_controls_fit_200_360_900`. A demo expanding control with minimum width 90/preferred 240 must fit at 200 without a hidden fullscreen or volume button; lower-priority overflow controls reappear at 900. Start from send2's compact layout thresholds, replacing composer-specific decisions with aggregate extension width. Status and compact labels yield first; existing narrow-tile recording behavior is retained. Public controls never call private tile methods.
- [ ] **Step 4 — Verify** the new check plus `dev/selfcheck_plugins.py`, `dev/selfcheck_tile_bottom_order.py`, `dev/selfcheck_duplicate_tile_controls.py`, `dev/selfcheck_tile_fullscreen.py`, `dev/selfcheck_danmaku_room_switches.py` and documentation/file checks. Update affected baseline expectations only where the approved extension slot changes them.
- [ ] **Step 5 — Commit in host:** `feat(plugins): add managed per-tile control extensions`.

## Task 2: Shared Credential Snapshots and Generic Fullscreen Interaction

**Files:** Create host `ddm/plugin_credentials.py`, `dev/selfcheck_plugin_credentials.py`; modify `ddm/plugins.py`, `ddm/widgets.py`, `ddm/app.py`, `ddm/bili.py`, `ddm/fullscreen_cursor.py`, `dev/selfcheck_fullscreen_cursor.py`, `docs/plugins.md`, inventory.

**Interfaces:** Produces credential contracts/events and `Tile.plugin_interaction_active`. The Bilibili host adapter reads the existing atomic cookie snapshot; identity keys are `SESSDATA`/`bili_jct`; only ancillary `buvid3` is writable. Add an atomic `bili.remember_buvid3(value: str) -> str` that fills an absent device cookie while preserving an identity already obtained by the host/login.

- [ ] **Step 1 — Write failing tests.** A fake `demo` provider proves snapshots are detached, unsupported providers return None, repr/events contain no secrets, stale updates return False and forbidden keys raise ValueError. `test_device_refresh_keeps_account_generation` asserts a persisted buvid3 update emits ancillary-update fields while the generation stays equal; a new SESSDATA or csrf changes it. `test_old_device_update_after_login_is_rejected` and `test_existing_login_device_is_preserved` cover the races. Real host account-flow tests assert restored credentials are immediately available, both login methods reach notification through `_on_login`, and logout empties authentication before controls receive the event.
- [ ] **Step 2 — Run** the new credential check and extended fullscreen check; confirm failures identify missing behavior.
- [ ] **Step 3 — Implement** host adapters before plugin load and notify synchronously from login/logout. Save accepted ancillary changes through the existing host save path; do not write plugin settings. Maintain thread-safe cookie access and avoid advancing the account generation for buvid3-only changes. Add a demo focused editor/popup control to fullscreen tests; query `plugin_interaction_active()` before both outside-tile hiding and idle-video hiding. A hidden/disabled control must return inactive; a throwing query must not block other providers. Preserve all existing cursor/modal/native-window logic.
- [ ] **Step 4 — Verify** new credentials/controls checks, cookie tests, account-dialog checks, fullscreen cursor/controls/native-focus checks and documentation checks. Use existing QR/web tests or small direct callback doubles; do not launch real login or read account files.
- [ ] **Step 5 — Commit in host:** `feat(plugins): expose credential snapshots and interaction state`.

## Task 3: Port Sending, Emoticons and Plugin Lifecycle

**Files:** Create plugin `plugins/bili_live/{plugin.json,plugin.py,README.md,session.py,workers.py,bili_api.py,composer.py,emoticons.py}`, `tests/bili_live_support.py`, `tests/check_bili_live_send.py`, `tests/check_bili_live_composer.py`, `tests/check_bili_live_emoticons.py`; modify plugin root README and `tests/check_packages.py`, `tests/check_release_upgrade.py`.

**Interfaces:** `BiliSession(context, parent=None)` exposes `snapshot() -> CredentialSnapshot | None`, signal `changed(object)` and GUI slot `publish_device(generation: int, value: str)`. Plugin `on_event` routes account/ancillary events to it. `DanmakuComposer(session, parent=None)` preserves send2's public UI methods and adds `interaction_active() -> bool`. A `BiliControl` facade implements task 1, initially minimum width 90/preferred 240/priority 100.

`workers.Request(context, operation, *, cookies: dict, account_generation: int, require_device: bool = False)` runs `operation(local_cookies)` and emits `completed(object, object)`, `failed(object, object)` with the exception, and `deviceReady(int, str)`. `start_worker(worker, priority=QThread.InheritPriority) -> None`, `wait_for_requests() -> None` and cancellation cover all plugin workers; worker lifetime is independent of receiver widgets. `bili_api` produces `api_result(response) -> dict`, `prepare_cookies(cookies: dict) -> dict`, `resolve_room(room_id: str, *, cookies: dict) -> tuple[str, int]`, `send_danmaku(room_id, message, *, dm_type=0, cookies: dict) -> dict`, `get_emoticons(room_id, *, cookies: dict) -> list[dict]`. Room resolution returns real room ID and anchor UID.

- [ ] **Step 1 — Port failing tests** from send2's `selfcheck_danmaku_send.py`, `selfcheck_danmaku_composer.py` and `selfcheck_emoticon_tabs.py`, changing only package loading and credential injection initially. Retain actual local HTTP form/cookie/CSRF checks, dm_type=1, locked emotes, no retry and code=0 failure messages; draft revisions, IME/ShortcutOverride, per-tile isolation, tab covers, lazy image batches and popup clipping. Add `test_older_host_rejected_before_registration` and `test_device_publication_is_gui_only_and_generation_checked`.
- [ ] **Step 2 — Run** each plugin check with `D:\Dev\DD_Monitor_CE\.venv\Scripts\python.exe <check> --host D:\Dev\DD_Monitor_CE`; expect missing plugin modules/interfaces.
- [ ] **Step 3 — Extract** the existing source through `git show` without switching host branches. Keep the UI behavior; split emoticon-specific widgets out of the composer. Move sending/endpoints into plugin `bili_api`; use captured cookies rather than host global/private bili functions. Share on-demand device lookup safely between workers and publish its result through the host snapshot generation. On account/room changes cancel unsubmitted work and ignore stale results. Register through public hooks only. Feature-check the public methods before registration and report a clear compatible-host message. The manifest starts at ID `bili_live`, display name `B站直播互动`, version `1.0`.

  On closing, stop scheduling/close views; on unload, shut down controls and wait for bounded workers without terminating threads. Ensure a headless package manager can register without a QApplication or real host window. Generalize package/release-upgrade source-plugin counts from manifests; retain the exact five existing playback platforms and assert bili_live adds none. Build an initial ZIP only after staging tracked files.
- [ ] **Step 4 — Verify** all three ported checks and existing plugin package/release-upgrade tests against the real modified host. Existing three plugins must continue loading, and a ZIP install must not execute plugin code before load.
- [ ] **Step 5 — Commit in plugin repo:** `feat(bili-live): extract danmaku composer and emoticons`.

## Task 4: Gift Models, Catalog, Wallet and Bag Reads

**Files:** Create plugin `plugins/bili_live/gift_api.py`, `tests/bili_live_fixtures.py`, `tests/check_bili_live_gift_api.py`; extend shared test support.

**Interfaces:** Immutable `GiftItem(key, source, gift_id, name, price, gif_url, image_url, counts, max_count, allow_custom, disabled_reason, bag_id=0, stock=0, expires_at=0)`, `GiftTab(key, title, items)`, `GiftCatalog(tabs, configs, max_send_count)`, `GiftTarget(room_id, uid, ruid)`, `GiftResult(gift_key, quantity, payload)`; `GiftSendError(ValueError)` carries `uncertain: bool`. `source` is gold/bag/unsupported; amounts/counts/IDs are integers. Produce `normalize_catalog(data: dict, room_id: str) -> GiftCatalog`, `normalize_bag(data: dict, catalog: GiftCatalog | None, room_id: str, *, now: int) -> GiftTab`, `format_battery(raw: int) -> str`, `get_catalog(room_id, *, cookies: dict) -> GiftCatalog`, `get_wallet(*, cookies: dict) -> int`, `get_bag(room_id, catalog: GiftCatalog | None, *, cookies: dict) -> GiftTab`.

- [ ] **Step 1 — Write failing fixture/read tests.** Assert room-reference-only lists, stable position order, room overrides, permission/interactive-pay disabling, valid deduplicated counts/custom maxima, image fallback and malformed-response errors. Assert `format_battery(5200) == "52"`, `format_battery(105) == "1.05"`, missing gold raises while gold=0 returns zero, and null bag list/config produce an empty tuple. Preserve distinct bag batches 701/702; expired/wrong-room/unknown-rule stock is not sendable. Bag-provided metadata must support valid inventory with `catalog=None`, so a failed ordinary catalog does not block independently readable bag gifts; unknown rules still disable sending. GET mocks assert captured cookies and a 10-second timeout.
- [ ] **Step 2 — Run** `tests/check_bili_live_gift_api.py --host ...`; expect missing normalizers/read methods.
- [ ] **Step 3 — Implement** using the previously inspected `roomGiftList`, `myWallet`, `gift/bag_list` shapes. Resolve only room list/tab references, merging base and room config by ID. Use integer money and per-batch identity; do not synthesize purchasable gifts from unreferenced global config. Keep independent read errors. Read the maintained public sendGold/sendBag implementation now and record exact selected versions/fields in the plugin README's developer notes; compare the known v1/v2 bag difference without making a real POST. Pin one endpoint version per operation before task 5 writes its request assertions.
- [ ] **Step 4 — Verify** the complete gift API check plus the sending API check; no live login/config/network is required for automated cases.
- [ ] **Step 5 — Commit in plugin repo:** `feat(bili-live): read gift catalog wallet and bag`.

## Task 5: Gift Submission and Shared Account Coordination

**Files:** Extend plugin `gift_api.py`, its tests and fixtures; create `plugins/bili_live/gift_controller.py`, `tests/check_bili_live_gift_controller.py`.

**Interfaces:** API `prepare_target(room_id: str, *, cookies: dict) -> GiftTarget` resolves sender from the captured session and anchor/real room via task 3; `send_gift(target, item, quantity, *, cookies: dict, wallet: int | None, still_current: Callable[[], bool]) -> GiftResult`. `GiftCoordinator(parent=None)` owns reservations and monotonically increasing account-data revisions. `GiftController(session, coordinator, parent=None)` produces immutable `.state: GiftPanelState`, signals `stateChanged(object)`, `sent(object)`, `failed(str, bool)`; methods `set_context(room_id: str, snapshot: CredentialSnapshot)`, `load(force=False)`, `send(gift_key: str, quantity: int)`, `shutdown()`. State fields are `tabs`, `wallet: int | None`, `catalog_error`, `wallet_error`, `bag_error`, `loading: frozenset[str]`, `sending: bool`, `feedback: str`.

- [ ] **Step 1 — Write failing tests.** A local HTTP server must observe exactly one correctly encoded form POST with sender UID 123, anchor UID 456, real room 90001, raw unit price, csrf/csrf_token, Origin/Referer, no redirects and the task-4-pinned endpoint. Bag selection 702 must never send 701 or fall back to gold. Invalid quantities, credentials, permissions, expiry, special flows and insufficient known funds cause zero POSTs. Timeout, disconnect and bad success JSON cause one attempt and uncertain=True; explicit rejection is uncertain=False.

  Barrier tests `test_one_send_across_two_controllers`, `test_room_change_during_target_preparation_never_posts`, `test_old_wallet_and_bag_reads_after_success_are_ignored`, `test_destroyed_view_does_not_release_inflight_reservation`, `test_account_change_does_not_apply_old_result` and `test_success_then_refresh_failure_stays_success` pin coordination. A busy reservation is held until the actual worker completes, even after view shutdown or auth change; the single active Bilibili account never gets a duplicate in-flight request.
- [ ] **Step 2 — Run** gift API/controller checks; confirm each new contract fails for missing send/coordinator behavior.
- [ ] **Step 3 — Implement** final validation immediately before the single POST, following source-confirmed fields. Use cancellation tokens for GUI-context changes; workers never query host GUI state. Explicit rejection and uncertain post-submission errors are distinct. Success and uncertainty advance shared data revision and invalidate wallet/bag across tiles; already-issued older reads are discarded. Hidden panels reload on next open; visible panels refresh. Never persist balances or permissions and never destroy running workers with a popup.
- [ ] **Step 4 — Verify** the two gift checks, sending API/composer checks and lifecycle cases with bounded barriers rather than timing-dependent sleeps.
- [ ] **Step 5 — Commit in plugin repo:** `feat(bili-live): coordinate gift submissions across tiles`.

## Task 6: Gift GIFs and Bounded Media Loading

**Files:** Create plugin `plugins/bili_live/gift_media.py`, `tests/check_bili_live_gift_media.py`; extend fixtures.

**Interfaces:** `GiftMediaLoader(cache_dir, parent=None)` signals `loaded(int, str, str)` and `failed(int, str)`; methods `request(urls: tuple[str, ...], generation: int)`, `cancel()`, `shutdown()`. `GiftImageLabel(parent=None)` has `set_file(path: str)`, `set_playing(playing: bool)`, `.movie: QMovie | None`. Use task 3's worker registry; media requests carry no account cookies.

- [ ] **Step 1 — Write failing tests.** A tiny two-frame fixture gives `movie.frameCount() == 2`; visible playback resumes and hiding pauses. Assert static fallback/name usability after a failed GIF, no stale generation application, no more than two simultaneous downloads, cache reuse without another GET and incomplete-download files never being published as valid media.
- [ ] **Step 2 — Run** `tests/check_bili_live_gift_media.py --host ...`; expect missing media contracts.
- [ ] **Step 3 — Implement** raw-byte URL-hash caching under `cache/bili_live/gifts`, atomic complete writes, HTTP(S)-only input and 10-second requests. Create/use QMovie on the GUI thread. Request current visible-page rows, stop scheduling on hiding/category change, and retain readable card content when both images fail. Keep test cache paths temporary.
- [ ] **Step 4 — Verify** media, controller and emoticon checks. A media cancellation must not strand a worker or cause authenticated cookies to reach a CDN.
- [ ] **Step 5 — Commit in plugin repo:** `feat(bili-live): load and animate visible gift images`.

## Task 7: Gift Panel, Quantity Panel and Closing Rules

**Files:** Create plugin `plugins/bili_live/gift_popup.py`, `tests/check_bili_live_gift_popup.py`.

**Interfaces:** `GiftButton(parent=None)`; `GiftPopup(parent=None)` signals `sendRequested(str, int)`, `refreshRequested()`, methods `open_at(button)`, `set_state(state: GiftPanelState)`, `mark_sent(result: GiftResult)`, `shutdown()`, `interaction_active() -> bool`; `.quantity_popup` exposes the current secondary view for integration/testing. Internal `GiftCard` and `GiftQuantityPopup` emit gift key/count; they never contain credentials or submit HTTP directly.

- [ ] **Step 1 — Write failing Qt tests.** Single ordinary count `(1,)`/no custom emits exactly one `(key, 1)` on click. Other counts/custom open on hover and original-card click without emitting; selecting 10 and clicking send emits exactly once. Invalid/noninteger/over-limit/over-budget counts disable send. Test category order, bag stock/expiry, independent loading/errors, unknown balance, unsupported items, 400x340/five-column starting layout, adaptive scrolling, clipping and readable fallback.

  Assert actual visibility after cursor/event delivery for browsing-outside-stays-open, success-inside-stays-open then outside closes both, response-arrives-outside-closes, quantity-gap-crossing-stays-open, second-send-inflight-defers-close, failure-before-first-success-does-not-arm, hidden-completion-never-reopens and reopen-resets-latch. Test Esc/outside click/button toggle and narrow/high-DPI screen bounds separately.
- [ ] **Step 2 — Run** `tests/check_bili_live_gift_popup.py --host ...`; expect missing interaction behavior.
- [ ] **Step 3 — Implement** both views with existing theme tokens and accessible names. Use the union of main/quantity bounds and a 150 ms transition allowance. Arm pointer-close only after `mark_sent`; suppress it while sending and re-evaluate on completion. Explicit dismissal remains available during a request. Hidden views pause media and cannot reopen from callbacks; do not put wallet/auth coordination inside popup widgets.
- [ ] **Step 4 — Verify** popup/media/controller checks in real Qt. Use event-loop settling with bounded deadlines; prove user-visible states, not just private flags.
- [ ] **Step 5 — Commit in plugin repo:** `feat(bili-live): add gift and quantity popups`.

## Task 8: Integrate Gifts, Package and Verify the Real Host

**Files:** Modify plugin composer/entry/session/README; create `tests/check_bili_live_integration.py`, extend composer/package/release-upgrade tests. Update plugin root README and `tests/website.test.mjs` where it assumes source and published plugins are the same set. Update host `docs/plugins.md` only for finalized public API examples/compatibility, and inventory if new host checks were added.

**Interfaces:** Composer `.gift_button`, `.gift_popup`, `.gift_controller`, `open_gifts(_checked=False)`. One plugin-scoped coordinator is passed to all controls. Existing composer `.popup` remains the emoticon view. Registration/shutdown uses tasks 1–3; no gifts-specific host API is added.

- [ ] **Step 1 — Write failing integration tests.** Assert row order `edit < emote < gift < send`, 28x28 buttons, mutual popup exclusion, lazily created authenticated gift state, draft preservation after gifts, credential/room reset of both views and hidden non-Bilibili entry. At widths 900/360/200, assert usable input (at least 24 logical pixels at 200), volume/fullscreen reachability, recording accessibility as in send2 and no overlap. Add account-wide actions in two tiles, hide/remove in flight, theme changes and exit with gift/media workers.

  Install the actual ZIP through `PluginManager.install_zip` into a temporary directory and construct a real patched-offline MainWindow. Verify existing/new/empty tiles, room swaps, fullscreen reparenting, shared login event and device persistence. Restart with bili_live disabled/removed and assert its UI is gone while playback/receiving/other plugins remain available. Test headless package loading and older-host failure separately.
- [ ] **Step 2 — Run** integration and extended composer checks, confirming failures are missing gift integration rather than installed local plugin interference.
- [ ] **Step 3 — Wire** lazy controller/popups, credential snapshots, room/hide/shutdown handling and shared coordinator. Start with gift-aware compact send-button threshold 176 pixels, retaining the control's 90-pixel minimum and adjusting only from measured test geometry. Use the finalized public hook for focus/IME/popups. Document real behavior, unsupported gifts and compatible host hooks.

  Generalize package/release-upgrade counts from manifests, assert all four plugins load and the original five playback platforms remain. Website data describes already published v1.0 ZIPs and is older than current source manifests; do not fabricate a bili_live download/checksum or rewrite existing published links to nonexistent assets. Its tests should validate catalog entries against their actual versioned package manifests/checksums, require unique IDs and permit the published subset of source plugins. Remove fixed-three assumptions; build source packages and site assets separately. New bili_live is delivered locally as `dist/bili_live-1.0.zip`, not publicly released.
- [ ] **Step 4 — Verify** package integrity/source consistency, release-upgrade and integration checks for all plugins. Run existing plugin regression scripts with `--host` as applicable, then website checks/build only if that test file/site code changed; establish and report any genuine pre-existing published-artifact failure rather than hiding it. Verify `git diff --check` and changed Python compilation.
- [ ] **Step 5 — Commit in plugin repo:** `feat(bili-live): integrate gifts and verify packaged host behavior`; commit any finalized host docs/test adjustment separately with its own checks.

## Task 9: Final Regression, Native Checks and Independent Review

**Files:** Update this plan's completed checkboxes and record verification in plugin `plugins/bili_live/README.md` developer notes; add focused regression tests and fix files only for actual review findings. Update host docs inventory for any new tracked support/report file.

**Interfaces:** Consumes all previous public APIs and the built ZIP. No additional framework interface is introduced.

- [ ] **Step 1 — Run final scoped checks** in separate processes: all new plugin checks, `check_packages.py`, `check_release_upgrade.py`, existing host plugin/cookie/room-switch/fullscreen/bottom-order/native-control/repository checks, and any additional test whose runtime module actually changed. Require nonzero exits to stop delivery. Do not broaden/repeat passing suites unless a later change warrants it.
- [ ] **Step 2 — Perform visible/native Qt verification** over a real VLC surface with simulated local gift outcomes: dark/light, 900/360/200 widths, fullscreen and `QT_SCALE_FACTOR=1.5`. Check native hit targets, GIF playback/pause, main-to-quantity pointer path, focus/IME behavior and exit. Save only synthetic test-window captures under ignored `work/` if needed. Report any native behavior that cannot be verified here explicitly.
- [ ] **Step 3 — Perform permitted real-service read checks** only if usable credentials are already available through the app; do not request/login automatically or output wallet/cookies/inventory. Otherwise record that these checks were not run. No real gift/text send is implied by a read check.
- [ ] **Step 4 — Get one independent whole-change review** across both branches against the approved spec, concentrating on cleanup, account switching, pre-POST cancellation, duplicate submission, stale data and compact native UI. Correct material findings with a failing focused test, passing verification and a corresponding commit in the affected repo. With native execution, dispatch only this final review; with subagent-driven execution, also retain the per-task review gates.
- [ ] **Step 5 — Commit evidence/progress/docs** in their respective repos after the relevant documentation checks pass. Deliver branch/commit IDs, local ZIP location, checks passed and precise remaining live/native validation limits. Do not create empty commits for tests-only runs.

## Verification Commands and Environment

Use host `.venv\Scripts\python.exe` for both repositories. Plugin checks accept `--host D:\Dev\DD_Monitor_CE` and set host import/CWD before loading VLC. Run them from the plugin root using the absolute host Python path. Tests must isolate plugin directories from real `plugins_user` and block unrelated background network tasks.

Set `DDM_NO_SAVE=1`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONIOENCODING=utf-8`, and `QT_QPA_PLATFORM=offscreen` for normal checks. Temporary files belong under an authorized writable task directory; the current visualization temp root is known to work. Set `PYTHON_VLC_LIB_PATH=D:\Dev\DD_Monitor_CE\libvlc.dll` where host initialization requires it. Native checks use the Windows Qt platform in a separate process; never change global display scaling.

Run `git diff --check` in each repo and compile changed Python sources using `compile(source, filename, 'exec')` to avoid writing tracked cache files. Stage new plugin files before `tools/build_plugins.py`; ZIP building intentionally ignores untracked files. Keep output in the ignored plugin `dist/` directory.

The sandbox mounts host `.git` read-only and does not grant write/traversal access to the second repository by default. Use standard per-command escalation for the explicitly requested branch/commit/plugin edits as needed. If an existing repository-map test's child PowerShell script receives `AuthorizationManager check failed`, rerun that exact validation with standard escalation; do not weaken script security or the test.

## Plan Self-Review and Handoff

Coverage: task 1 owns the tile lifecycle/layout contract; task 2 owns credentials and generic interaction; task 3 preserves all sending/emoticon behavior; tasks 4–7 implement every approved gift requirement; task 8 verifies the installed ZIP and no-plugin behavior; task 9 owns final native/live evidence and independent review. The five review-focus cases have explicit tests. Cross-task type/method/signal names above are consistent; public API names are now fixed for implementation.

Status: plan written and self-reviewed; product implementation has not started. Request plan review and execution-method choice under writing-plans before beginning task 1. Recommended approach: native execution followed by one independent review, because host/plugin contracts are tightly coupled and the same implementer can carry their context across the port and integration without repeated handoffs.
