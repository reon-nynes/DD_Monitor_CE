# Generic Tile Extensions and bili_live Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

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

- [x] **Step 1 — Write failing tests.** `test_existing_new_and_initially_empty_tiles_receive_one_control` asserts one factory call per provider/tile after repeated wiring and an initial room callback. `test_every_assignment_is_delivered_as_a_copy` covers None, same-ID metadata, replacement, swap and restoration; mutation of the received dictionary must leave `tile.room` unchanged. `test_failed_load_rolls_back_controls` and `test_provider_exceptions_do_not_block_others` assert partial widgets are removed and a second provider still updates. `test_remove_and_unload_shutdown_once` asserts a shutdown counter of one after removal followed by unload.
- [x] **Step 2 — Run** `.\.venv\Scripts\python.exe dev/selfcheck_plugin_controls.py`; expect failure for the missing public contracts, not missing Qt/VLC dependencies.
- [x] **Step 3 — Implement** registration and tile attachment. Use a host-owned wrapper for each plugin widget: width overflow hides the wrapper while unsupported-room hiding remains the widget's own state. Existing tiles attach after `plugins.load()`; later tiles attach from `_wire_tile`. Call room delivery inside `Tile.set_room` for all branches, including its empty-room return. Keep initial-construction guards and fullscreen reparenting safe. Roll back only the failing provider's resources, isolate callbacks and disconnect on disposal.

  Add width tests `test_no_extension_layout_is_preserved`, `test_priority_overflow_recovers_on_widening`, `test_compact_controls_fit_200_360_900`. A demo expanding control with minimum width 90/preferred 240 must fit at 200 without a hidden fullscreen or volume button; lower-priority overflow controls reappear at 900. Start from send2's compact layout thresholds, replacing composer-specific decisions with aggregate extension width. Status and compact labels yield first; existing narrow-tile recording behavior is retained. Public controls never call private tile methods.
- [x] **Step 4 — Verify** the new check plus `dev/selfcheck_plugins.py`, `dev/selfcheck_tile_bottom_order.py`, `dev/selfcheck_duplicate_tile_controls.py`, `dev/selfcheck_tile_fullscreen.py`, `dev/selfcheck_danmaku_room_switches.py` and documentation/file checks. Update affected baseline expectations only where the approved extension slot changes them.
- [x] **Step 5 — Commit in host:** `feat(plugins): add managed per-tile control extensions`.

## Task 2: Shared Credential Snapshots and Generic Fullscreen Interaction

**Files:** Create host `ddm/plugin_credentials.py`, `dev/selfcheck_plugin_credentials.py`; modify `ddm/plugins.py`, `ddm/widgets.py`, `ddm/app.py`, `ddm/bili.py`, `ddm/fullscreen_cursor.py`, `dev/selfcheck_fullscreen_cursor.py`, `docs/plugins.md`, inventory.

**Interfaces:** Produces credential contracts/events and `Tile.plugin_interaction_active`. The Bilibili host adapter reads the existing atomic cookie snapshot; identity keys are `SESSDATA`/`bili_jct`; only ancillary `buvid3` is writable. Add an atomic `bili.remember_buvid3(value: str) -> str` that fills an absent device cookie while preserving an identity already obtained by the host/login.

- [x] **Step 1 — Write failing tests.** A fake `demo` provider proves snapshots are detached, unsupported providers return None, repr/events contain no secrets, stale updates return False and forbidden keys raise ValueError. `test_device_refresh_keeps_account_generation` asserts a persisted buvid3 update emits ancillary-update fields while the generation stays equal; a new SESSDATA or csrf changes it. `test_old_device_update_after_login_is_rejected` and `test_existing_login_device_is_preserved` cover the races. Real host account-flow tests assert restored credentials are immediately available, both login methods reach notification through `_on_login`, and logout empties authentication before controls receive the event.
- [x] **Step 2 — Run** the new credential check and extended fullscreen check; confirm failures identify missing behavior.
- [x] **Step 3 — Implement** host adapters before plugin load and notify synchronously from login/logout. Save accepted ancillary changes through the existing host save path; do not write plugin settings. Maintain thread-safe cookie access and avoid advancing the account generation for buvid3-only changes. Add a demo focused editor/popup control to fullscreen tests; query `plugin_interaction_active()` before both outside-tile hiding and idle-video hiding. A hidden/disabled control must return inactive; a throwing query must not block other providers. Preserve all existing cursor/modal/native-window logic.
- [x] **Step 4 — Verify** new credentials/controls checks, cookie tests, account-dialog checks, fullscreen cursor/controls/native-focus checks and documentation checks. Use existing QR/web tests or small direct callback doubles; do not launch real login or read account files.
- [x] **Step 5 — Commit in host:** `feat(plugins): expose credential snapshots and interaction state`.

## Task 3: Port Sending, Emoticons and Plugin Lifecycle

**Files:** Create plugin `plugins/bili_live/{plugin.json,plugin.py,README.md,session.py,workers.py,bili_api.py,composer.py,emoticons.py}`, `tests/bili_live_support.py`, `tests/check_bili_live_send.py`, `tests/check_bili_live_composer.py`, `tests/check_bili_live_emoticons.py`; modify plugin root README and `tests/check_packages.py`, `tests/check_release_upgrade.py`.

**Interfaces:** `BiliSession(context, parent=None)` exposes `snapshot() -> CredentialSnapshot | None`, signal `changed(object)` and GUI slot `publish_device(generation: int, value: str)`. Plugin `on_event` routes account/ancillary events to it. `DanmakuComposer(session, parent=None)` preserves send2's public UI methods and adds `interaction_active() -> bool`. A `BiliControl` facade implements task 1, initially minimum width 90/preferred 240/priority 100.

`workers.Request(context, operation, *, cookies: dict, account_generation: int, require_device: bool = False)` runs `operation(local_cookies)` and emits `completed(object, object)`, `failed(object, object)` with the exception, and `deviceReady(int, str)`. `start_worker(worker, priority=QThread.InheritPriority) -> None`, `wait_for_requests() -> None` and cancellation cover all plugin workers; worker lifetime is independent of receiver widgets. `bili_api` produces `api_result(response) -> dict`, `prepare_cookies(cookies: dict) -> dict`, `resolve_room(room_id: str, *, cookies: dict) -> tuple[str, int]`, `send_danmaku(room_id, message, *, dm_type=0, cookies: dict) -> dict`, `get_emoticons(room_id, *, cookies: dict) -> list[dict]`. Room resolution returns real room ID and anchor UID.

- [x] **Step 1 — Port failing tests** from send2's `selfcheck_danmaku_send.py`, `selfcheck_danmaku_composer.py` and `selfcheck_emoticon_tabs.py`, changing only package loading and credential injection initially. Retain actual local HTTP form/cookie/CSRF checks, dm_type=1, locked emotes, no retry and code=0 failure messages; draft revisions, IME/ShortcutOverride, per-tile isolation, tab covers, lazy image batches and popup clipping. Add `test_older_host_rejected_before_registration` and `test_device_publication_is_gui_only_and_generation_checked`.
- [x] **Step 2 — Run** each plugin check with `D:\Dev\DD_Monitor_CE\.venv\Scripts\python.exe <check> --host D:\Dev\DD_Monitor_CE`; expect missing plugin modules/interfaces.
- [x] **Step 3 — Extract** the existing source through `git show` without switching host branches. Keep the UI behavior; split emoticon-specific widgets out of the composer. Move sending/endpoints into plugin `bili_api`; use captured cookies rather than host global/private bili functions. Share on-demand device lookup safely between workers and publish its result through the host snapshot generation. On account/room changes cancel unsubmitted work and ignore stale results. Register through public hooks only. Feature-check the public methods before registration and report a clear compatible-host message. The manifest starts at ID `bili_live`, display name `B站直播互动`, version `1.0`.

  On closing, stop scheduling/close views; on unload, shut down controls and wait for bounded workers without terminating threads. Ensure a headless package manager can register without a QApplication or real host window. Generalize package/release-upgrade source-plugin counts from manifests; retain the exact five existing playback platforms and assert bili_live adds none. Build an initial ZIP only after staging tracked files.
- [x] **Step 4 — Verify** all three ported checks and existing plugin package/release-upgrade tests against the real modified host. Existing three plugins must continue loading, and a ZIP install must not execute plugin code before load.
- [x] **Step 5 — Commit in plugin repo:** `feat(bili-live): extract danmaku composer and emoticons`.

## Task 4: Gift Models, Catalog, Wallet and Bag Reads

**Files:** Create plugin `plugins/bili_live/gift_api.py`, `tests/bili_live_fixtures.py`, `tests/check_bili_live_gift_api.py`; extend shared test support.

**Interfaces:** Immutable `GiftItem(key, source, gift_id, name, price, gif_url, image_url, counts, max_count, allow_custom, disabled_reason, bag_id=0, stock=0, expires_at=0)`, `GiftTab(key, title, items)`, `GiftCatalog(tabs, configs, max_send_count)`, `GiftTarget(room_id, uid, ruid)`, `GiftResult(gift_key, quantity, payload)`; `GiftSendError(ValueError)` carries `uncertain: bool`. `source` is gold/bag/unsupported; amounts/counts/IDs are integers. Produce `normalize_catalog(data: dict, room_id: str) -> GiftCatalog`, `normalize_bag(data: dict, catalog: GiftCatalog | None, room_id: str, *, now: int) -> GiftTab`, `format_battery(raw: int) -> str`, `get_catalog(room_id, *, cookies: dict) -> GiftCatalog`, `get_wallet(*, cookies: dict) -> int`, `get_bag(room_id, catalog: GiftCatalog | None, *, cookies: dict) -> GiftTab`.

- [x] **Step 1 — Write failing fixture/read tests.** Assert room-reference-only lists, stable position order, room overrides, permission/interactive-pay disabling, valid deduplicated counts/custom maxima, image fallback and malformed-response errors. Assert `format_battery(5200) == "52"`, `format_battery(105) == "1.05"`, missing gold raises while gold=0 returns zero, and null bag list/config produce an empty tuple. Preserve distinct bag batches 701/702; expired/wrong-room/unknown-rule stock is not sendable. Bag-provided metadata must support valid inventory with `catalog=None`, so a failed ordinary catalog does not block independently readable bag gifts; unknown rules still disable sending. GET mocks assert captured cookies and a 10-second timeout.
- [x] **Step 2 — Run** `tests/check_bili_live_gift_api.py --host ...`; expect missing normalizers/read methods.
- [x] **Step 3 — Implement** using the previously inspected `roomGiftList`, `myWallet`, `gift/bag_list` shapes. Resolve only room list/tab references, merging base and room config by ID. Use integer money and per-batch identity; do not synthesize purchasable gifts from unreferenced global config. Keep independent read errors. Read the maintained public sendGold/sendBag implementation now and record exact selected versions/fields in the plugin README's developer notes; compare the known v1/v2 bag difference without making a real POST. Pin one endpoint version per operation before task 5 writes its request assertions.
- [x] **Step 4 — Verify** the complete gift API check plus the sending API check; no live login/config/network is required for automated cases.
- [x] **Step 5 — Commit in plugin repo:** `feat(bili-live): read gift catalog wallet and bag`.

## Task 5: Gift Submission and Shared Account Coordination

**Files:** Extend plugin `gift_api.py`, its tests and fixtures; create `plugins/bili_live/gift_controller.py`, `tests/check_bili_live_gift_controller.py`.

**Interfaces:** API `prepare_target(room_id: str, *, cookies: dict) -> GiftTarget` resolves sender from the captured session and anchor/real room via task 3; `send_gift(target, item, quantity, *, cookies: dict, wallet: int | None, still_current: Callable[[], bool]) -> GiftResult`. `GiftCoordinator(parent=None)` owns reservations and monotonically increasing account-data revisions. `GiftController(session, coordinator, parent=None)` produces immutable `.state: GiftPanelState`, signals `stateChanged(object)`, `sent(object)`, `failed(str, bool)`; methods `set_context(room_id: str, snapshot: CredentialSnapshot)`, `load(force=False)`, `send(gift_key: str, quantity: int)`, `shutdown()`. State fields are `tabs`, `wallet: int | None`, `catalog_error`, `wallet_error`, `bag_error`, `loading: frozenset[str]`, `sending: bool`, `feedback: str`.

- [x] **Step 1 — Write failing tests.** A local HTTP server must observe exactly one correctly encoded form POST with sender UID 123, anchor UID 456, real room 90001, raw unit price, csrf/csrf_token, Origin/Referer, no redirects and the task-4-pinned endpoint. Bag selection 702 must never send 701 or fall back to gold. Invalid quantities, credentials, permissions, expiry, special flows and insufficient known funds cause zero POSTs. Timeout, disconnect and bad success JSON cause one attempt and uncertain=True; explicit rejection is uncertain=False.

  Barrier tests `test_one_send_across_two_controllers`, `test_room_change_during_target_preparation_never_posts`, `test_old_wallet_and_bag_reads_after_success_are_ignored`, `test_destroyed_view_does_not_release_inflight_reservation`, `test_account_change_does_not_apply_old_result` and `test_success_then_refresh_failure_stays_success` pin coordination. A busy reservation is held until the actual worker completes, even after view shutdown or auth change; the single active Bilibili account never gets a duplicate in-flight request.
- [x] **Step 2 — Run** gift API/controller checks; confirm each new contract fails for missing send/coordinator behavior.
- [x] **Step 3 — Implement** final validation immediately before the single POST, following source-confirmed fields. Use cancellation tokens for GUI-context changes; workers never query host GUI state. Explicit rejection and uncertain post-submission errors are distinct. Success and uncertainty advance shared data revision and invalidate wallet/bag across tiles; already-issued older reads are discarded. Hidden panels reload on next open; visible panels refresh. Never persist balances or permissions and never destroy running workers with a popup.
- [x] **Step 4 — Verify** the two gift checks, sending API/composer checks and lifecycle cases with bounded barriers rather than timing-dependent sleeps.
- [x] **Step 5 — Commit in plugin repo:** `feat(bili-live): coordinate gift submissions across tiles`.

## Task 6: Gift GIFs and Bounded Media Loading

**Files:** Create plugin `plugins/bili_live/gift_media.py`, `tests/check_bili_live_gift_media.py`; extend fixtures.

**Interfaces:** `GiftMediaLoader(cache_dir, parent=None)` signals `loaded(int, str, str)` and `failed(int, str)`; methods `request(urls: tuple[str, ...], generation: int)`, `cancel()`, `shutdown()`. `GiftImageLabel(parent=None)` has `set_file(path: str)`, `set_playing(playing: bool)`, `.movie: QMovie | None`. Use task 3's worker registry; media requests carry no account cookies.

- [x] **Step 1 — Write failing tests.** A tiny two-frame fixture gives `movie.frameCount() == 2`; visible playback resumes and hiding pauses. Assert static fallback/name usability after a failed GIF, no stale generation application, no more than two simultaneous downloads, cache reuse without another GET and incomplete-download files never being published as valid media.
- [x] **Step 2 — Run** `tests/check_bili_live_gift_media.py --host ...`; expect missing media contracts.
- [x] **Step 3 — Implement** raw-byte URL-hash caching under `cache/bili_live/gifts`, atomic complete writes, HTTP(S)-only input and 10-second requests. Create/use QMovie on the GUI thread. Request current visible-page rows, stop scheduling on hiding/category change, and retain readable card content when both images fail. Keep test cache paths temporary.
- [x] **Step 4 — Verify** media, controller and emoticon checks. A media cancellation must not strand a worker or cause authenticated cookies to reach a CDN.
- [x] **Step 5 — Commit in plugin repo:** `feat(bili-live): load and animate visible gift images`.

## Task 7: Gift Panel, Quantity Panel and Closing Rules

**Files:** Create plugin `plugins/bili_live/gift_popup.py`, `tests/check_bili_live_gift_popup.py`.

**Interfaces:** `GiftButton(parent=None)`; `GiftPopup(parent=None)` signals `sendRequested(str, int)`, `refreshRequested()`, methods `open_at(button)`, `set_state(state: GiftPanelState)`, `mark_sent(result: GiftResult)`, `shutdown()`, `interaction_active() -> bool`; `.quantity_popup` exposes the current secondary view for integration/testing. Internal `GiftCard` and `GiftQuantityPopup` emit gift key/count; they never contain credentials or submit HTTP directly.

- [x] **Step 1 — Write failing Qt tests.** Single ordinary count `(1,)`/no custom emits exactly one `(key, 1)` on click. Other counts/custom open on hover and original-card click without emitting; selecting 10 and clicking send emits exactly once. Invalid/noninteger/over-limit/over-budget counts disable send. Test category order, bag stock/expiry, independent loading/errors, unknown balance, unsupported items, 400x340/five-column starting layout, adaptive scrolling, clipping and readable fallback.

  Assert actual visibility after cursor/event delivery for browsing-outside-stays-open, success-inside-stays-open then outside closes both, response-arrives-outside-closes, quantity-gap-crossing-stays-open, second-send-inflight-defers-close, failure-before-first-success-does-not-arm, hidden-completion-never-reopens and reopen-resets-latch. Test Esc/outside click/button toggle and narrow/high-DPI screen bounds separately.
- [x] **Step 2 — Run** `tests/check_bili_live_gift_popup.py --host ...`; expect missing interaction behavior.
- [x] **Step 3 — Implement** both views with existing theme tokens and accessible names. Use the union of main/quantity bounds and a 150 ms transition allowance. Arm pointer-close only after `mark_sent`; suppress it while sending and re-evaluate on completion. Explicit dismissal remains available during a request. Hidden views pause media and cannot reopen from callbacks; do not put wallet/auth coordination inside popup widgets.
- [x] **Step 4 — Verify** popup/media/controller checks in real Qt. Use event-loop settling with bounded deadlines; prove user-visible states, not just private flags.
- [x] **Step 5 — Commit in plugin repo:** `feat(bili-live): add gift and quantity popups`.

## Task 8: Integrate Gifts, Package and Verify the Real Host

**Files:** Modify plugin composer/entry/session/README; create `tests/check_bili_live_integration.py`, extend composer/package/release-upgrade tests. Update plugin root README and `tests/website.test.mjs` where it assumes source and published plugins are the same set. Update host `docs/plugins.md` only for finalized public API examples/compatibility, and inventory if new host checks were added.

**Interfaces:** Composer `.gift_button`, `.gift_popup`, `.gift_controller`, `open_gifts(_checked=False)`. One plugin-scoped coordinator is passed to all controls. Existing composer `.popup` remains the emoticon view. Registration/shutdown uses tasks 1–3; no gifts-specific host API is added.

- [x] **Step 1 — Write failing integration tests.** Assert row order `edit < emote < gift < send`, 28x28 buttons, mutual popup exclusion, lazily created authenticated gift state, draft preservation after gifts, credential/room reset of both views and hidden non-Bilibili entry. At widths 900/360/200, assert usable input (at least 24 logical pixels at 200), volume/fullscreen reachability, recording accessibility as in send2 and no overlap. Add account-wide actions in two tiles, hide/remove in flight, theme changes and exit with gift/media workers.

  Install the actual ZIP through `PluginManager.install_zip` into a temporary directory and construct a real patched-offline MainWindow. Verify existing/new/empty tiles, room swaps, fullscreen reparenting, shared login event and device persistence. Restart with bili_live disabled/removed and assert its UI is gone while playback/receiving/other plugins remain available. Test headless package loading and older-host failure separately.
- [x] **Step 2 — Run** integration and extended composer checks, confirming failures are missing gift integration rather than installed local plugin interference.
- [x] **Step 3 — Wire** lazy controller/popups, credential snapshots, room/hide/shutdown handling and shared coordinator. Start with gift-aware compact send-button threshold 176 pixels, retaining the control's 90-pixel minimum and adjusting only from measured test geometry. Use the finalized public hook for focus/IME/popups. Document real behavior, unsupported gifts and compatible host hooks.

  Generalize package/release-upgrade counts from manifests, assert all four plugins load and the original five playback platforms remain. Website data describes already published v1.0 ZIPs and is older than current source manifests; do not fabricate a bili_live download/checksum or rewrite existing published links to nonexistent assets. Its tests should validate catalog entries against their actual versioned package manifests/checksums, require unique IDs and permit the published subset of source plugins. Remove fixed-three assumptions; build source packages and site assets separately. New bili_live is delivered locally as `dist/bili_live-1.0.zip`, not publicly released.
- [x] **Step 4 — Verify** package integrity/source consistency, release-upgrade and integration checks for all plugins. Run existing plugin regression scripts with `--host` as applicable, then website checks/build only if that test file/site code changed; establish and report any genuine pre-existing published-artifact failure rather than hiding it. Verify `git diff --check` and changed Python compilation.
- [x] **Step 5 — Commit in plugin repo:** `feat(bili-live): integrate gifts and verify packaged host behavior`; commit any finalized host docs/test adjustment separately with its own checks.

## Task 9: Final Regression, Native Checks and Independent Review

**Files:** Update this plan's completed checkboxes and record verification in plugin `plugins/bili_live/README.md` developer notes; add focused regression tests and fix files only for actual review findings. Update host docs inventory for any new tracked support/report file.

**Interfaces:** Consumes all previous public APIs and the built ZIP. No additional framework interface is introduced.

- [x] **Step 1 — Run final scoped checks** in separate processes: all new plugin checks, `check_packages.py`, `check_release_upgrade.py`, existing host plugin/cookie/room-switch/fullscreen/bottom-order/native-control/repository checks, and any additional test whose runtime module actually changed. Require nonzero exits to stop delivery. Do not broaden/repeat passing suites unless a later change warrants it.
- [x] **Step 2 — Perform visible/native Qt verification** over a real VLC surface with simulated local gift outcomes: dark/light, 900/360/200 widths, fullscreen and `QT_SCALE_FACTOR=1.5`. Check native hit targets, GIF playback/pause, main-to-quantity pointer path, focus/IME behavior and exit. Save only synthetic test-window captures under ignored `work/` if needed. Report any native behavior that cannot be verified here explicitly.
- [x] **Step 3 — Perform permitted real-service read checks** only if usable credentials are already available through the app; do not request/login automatically or output wallet/cookies/inventory. Otherwise record that these checks were not run. No real gift/text send is implied by a read check.
- [x] **Step 4 — Get one independent whole-change review** across both branches against the approved spec, concentrating on cleanup, account switching, pre-POST cancellation, duplicate submission, stale data and compact native UI. Correct material findings with a failing focused test, passing verification and a corresponding commit in the affected repo. With native execution, dispatch only this final review; with subagent-driven execution, also retain the per-task review gates.
- [x] **Step 5 — Commit evidence/progress/docs** in their respective repos after the relevant documentation checks pass. Deliver branch/commit IDs, local ZIP location, checks passed and precise remaining live/native validation limits. Do not create empty commits for tests-only runs.

## Verification Commands and Environment

Use host `.venv\Scripts\python.exe` for both repositories. Plugin checks accept `--host D:\Dev\DD_Monitor_CE` and set host import/CWD before loading VLC. Run them from the plugin root using the absolute host Python path. Tests must isolate plugin directories from real `plugins_user` and block unrelated background network tasks.

Set `DDM_NO_SAVE=1`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONIOENCODING=utf-8`, and `QT_QPA_PLATFORM=offscreen` for normal checks. Temporary files belong under an authorized writable task directory; the current visualization temp root is known to work. Set `PYTHON_VLC_LIB_PATH=D:\Dev\DD_Monitor_CE\libvlc.dll` where host initialization requires it. Native checks use the Windows Qt platform in a separate process; never change global display scaling.

Run `git diff --check` in each repo and compile changed Python sources using `compile(source, filename, 'exec')` to avoid writing tracked cache files. Stage new plugin files before `tools/build_plugins.py`; ZIP building intentionally ignores untracked files. Keep output in the ignored plugin `dist/` directory.

The sandbox mounts host `.git` read-only and does not grant write/traversal access to the second repository by default. Use standard per-command escalation for the explicitly requested branch/commit/plugin edits as needed. If an existing repository-map test's child PowerShell script receives `AuthorizationManager check failed`, rerun that exact validation with standard escalation; do not weaken script security or the test.

## Plan Self-Review and Handoff

Coverage: task 1 owns the tile lifecycle/layout contract; task 2 owns credentials and generic interaction; task 3 preserves all sending/emoticon behavior; tasks 4–7 implement every approved gift requirement; task 8 verifies the installed ZIP and no-plugin behavior; task 9 owns final native/live evidence and independent review. The five review-focus cases have explicit tests. Cross-task type/method/signal names above are consistent; public API names are now fixed for implementation.

Status: implemented natively in this session and reviewed once across both branches. All five Important findings were fixed with failing-then-passing regressions in plugin commit `34f568c`; no second independent review was requested. Checked steps mean their work/verification was performed, not that live endpoints or unavailable historical release assets were proved. The evidence and exceptions below are part of delivery.


## Completion evidence (2026-10-18)

Both repositories remain on their requested local feature branches. No push, PR, merge or release was performed. The pre-existing untracked `.codegraph/` is preserved. The branch heads also include the documentation commits carrying this record.

| Repository / branch | Implementation commits |
| --- | --- |
| Host `codex/plugin-tile-extensions`, cookie-persistence base `7011541` | `2c8ca44` managed tile controls; `60bf336` credential snapshots and generic interaction |
| Plugin `codex/bili-live`, base `7f909be` | `772a6b1` composer/emoticons; `a37b2b8` gift reads; `3f5b258` coordination; `3f8d899` media; `ee04132` popups; `6a14970` integration; `b88509b` native checks; `34f568c` review fixes |

Task 1's original scratch ledger completion range accidentally preceded its commit; the correct implementation commit is `2c8ca44`. Subsequent task records and the table above identify the committed work.

The installable local artifact is `D:\Dev\DD_Monitor_Plugins\dist\bili_live-1.0.zip`. ZIP CRC integrity and byte equality against every tracked file under `plugins/bili_live/` were checked. The final documentation rebuild includes the updated plugin README. All changed Python sources compile in memory (12 host files and 24 plugin-repository files), without writing tracked bytecode, and both repositories pass `git diff --check`.

### Regression and native evidence

| Verification | Result |
| --- | --- |
| Sending / composer / emoticons / lifecycle | 13 / 16 / 17 / 3 tests passed |
| Gift API / controller / media / popup | 14 / 8 / 4 / 10 tests passed |
| Actual ZIP installed into real offline-patched MainWindow | 6 tests passed; normal Windows Qt and `QT_SCALE_FACTOR=1.5` runs exit 0 |
| Total new plugin unit and integration tests | 91 passed after review fixes |
| Package integrity and historical release-upgrade | Passed; all four plugins load, original five playback platforms retained |
| Existing platform regressions | `check_douyu.py`, `check_douyu_follows.py`, `check_douyu_playback_auth.py`, `check_douyin_accounts.py`, `check_platform_logo.py` passed |
| Generic host controls / credentials / cookies | 8 / 7 / 9 tests passed; existing plugin/account/room-switch checks also passed |
| Host layout / fullscreen / native focus and hit targets | Bottom order, duplicate controls, tile fullscreen, cursor, fullscreen controls, native focus and native hit checks passed on Windows Qt |
| Native real VLC surface with simulated gift data | Dark/light; 900/360/200 widths; editor width at least 24 logical pixels; native gift-button hit targets; GIF play/pause; quantity gap; focus/IME; cleanup passed |
| Additional high-DPI run | `QT_SCALE_FACTOR=1.5`; effective device pixel ratio 2.25 on this display; native checks and 6 installed-ZIP integration tests passed |
| Host repository documentation/file checks | 5 / 3 tests passed |
| Website | Locked dependencies installed, audit zero vulnerabilities, build passed; page/link/asset tests 2 passed, published-artifact tests 2 failed as detailed below |

Native evidence comes from automated Windows Qt windows over a real local VLC surface, not human visual acceptance. Some VLC MPEG4 teardown warnings remain even on exit-0 runs. Offscreen integration ran all 6 assertions successfully but one post-fix process exited `3221225477` during teardown; Windows Qt reruns exited 0 at both scaling settings. Earlier offscreen/Windows fullscreen runs also intermittently crashed during teardown after assertions; the final required Windows checks exited 0. This report does not convert assertion success alone into a successful process result.

### One independent review and author fix pass

The fresh-context reviewer inspected host `7011541..60bf336` and plugin `7f909be..b88509b`, the approved spec/plan and all prior rulings. Verdict: **With fixes**, five Important findings, zero Critical, no deferred minors. All five were accepted as Important by user-visible impact and addressed in the one native fix pass; the reviewer did not re-review the fixes.

| Finding | Regression observed failing before the fix, passing afterward |
| --- | --- |
| Old-account completion strands new-account wallet/bag reads | `test_old_account_completion_preserves_new_account_reads`; controller revision now changes only for its current account context |
| Hidden invalidated panel reopens without refetching bag | `test_hidden_panel_reopens_with_refreshed_bag`; successful empty bags and invalidated placeholders have distinct validity |
| Failed GIF fallback cancels other visible images | `test_failed_gif_fallback_preserves_other_visible_images`; fallback appends to the current generation's queue |
| Explicit server counts filtered away become a fabricated single paid send | `test_explicit_unavailable_counts_never_create_single_send`; unsupported counts disable sending; approved custom counts and a bag stock of one remain supported |
| Malformed special-flow types become ordinary paid gifts | `test_unknown_flow_types_never_post`; 18 malformed-field cases disable sending before POST |

Review Focus 1 (initially empty tiles), 2 (overflow versus plugin hiding), 3 (device publication/login race) and 5 (popup closing) passed inspection. Focus 4's reservation lifetime was correct, but its account/read timing exposed the first two findings above. Each fix has an observed RED→GREEN regression, followed by all 91 relevant plugin tests, package/existing-platform checks and native/high-DPI verification.

### Remaining validation limits and existing failures

- Public unauthenticated `roomGiftList` for room 6 was read successfully and confirmed the nested schema. No usable real account was available through the app, so authenticated wallet/bag reads were not run. No real text or gift was submitted. Fixed v1 `sendGold`/`sendBag` forms were checked against maintained PyPI `bilibili-api-python==17.4.2` source and local HTTP tests; actual service/account compatibility remains unverified.
- Website tests `published catalog is a unique subset of source IDs with actual release manifests` and `published package checksums match the actual versioned release ZIP files` fail because original v1.0 archives are absent from `dist/published/`. The catalog's domestic ZIP URL returns HTTP 404 and `gh release view v1.0` reports release not found. Published links/checksums were preserved; current source ZIPs are not substitutes for those original archives.
- Existing `check_match_sync_performance.py` passes its multistream stage at about 59 fps, then fails in host `dev/selfcheck_match_sync_comparison.py:130`: `AttributeError: 'Decoder' object has no attribute 'analysis_size'`. The host comparison script, plugin `match_sync` source and wrapper are unchanged from the feature bases; this is an existing fixture/source mismatch, not suppressed by this work.
- Therefore the implemented feature's scoped regressions are green, but the broader repositories cannot be described as wholly green. No real gift should be used merely to discover endpoint compatibility; a live send needs its own explicit room/gift/count instruction.

### Rulings carried from execution and review

The following is the exhaustive decision record, in execution order, including each decision's cost if wrong:

- Task 1: Ruling: compact volume width is 26 below 260px when extensions are present — the actual base VolumeButton is 40px and cannot fit a 90px control at 200px otherwise — cost if wrong: compact channel markings may need painter adjustment during native verification.
- Task 2: Ruling: isolate deferred startup in selfcheck_fullscreen_cursor — its offline startup was releasing the manually installed VLC player and causing an access violation before cursor assertions — cost if wrong: startup sequencing itself is covered by other checks rather than this fixture.
- Task 2: Ruling: wait for revealed bar geometry before cursor hover assertions and give native-focus fixture the settings adapter it consumes — both failures precede extension behavior — cost if wrong: fixture corrections could mask an unrelated startup/animation regression; separate existing fullscreen checks remain required.
- Task 3: Ruling: move built-in Tile.composer/MainWindow source tests to installed-package integration in Task 8 — public extensions deliberately eliminate that private host property — cost if wrong: those host flows remain pending until Task 8.
- Task 3: Ruling: README match_sync version follows its actual 1.1 source manifest (pre-existing README said 1.2); historical domestic 1.1 fixture uses existing release commit 0ee6568 because v1.1 tag is absent locally and remotely — preserves real historical upgrade coverage — cost if wrong: release-fixture provenance needs correction, not reduced assertions.
- Task 3: Ruling: send_danmaku accepts an optional still_current callback checked immediately before POST — room resolution may finish after room/account cancellation — cost if wrong: API extension maintenance; existing callers retain default behavior.
- Task 4: Ruling: pin v1 sendGold and sendBag from current PyPI 17.4.2 source; old GitHub source paths are unavailable and the source confirms no v2 dependency — no automatic endpoint fallback — cost if wrong: live service may require an explicit later contract update; real sends remain unverified.
- Task 8: Ruling: installed-host tests grow the real tile pool via 2x2 layout and reuse empty tiles — add_room on a full 1x1 pool intentionally retires an extra empty tile — cost if wrong: add-room paths have separate existing host regression coverage.
- Task 8: Ruling: separate published ZIPs under dist/published from current source packages and validate actual manifests/checksums — prevents older website v1.0 catalog being equated to new manifests — cost if wrong: CI must provide original release artifacts.
- Final: Ruling: real authenticated wallet/bag and real gift/text success remain unverified — no usable app account was available and no real send was authorized; synthetic/native evidence does not prove service compatibility — cost if wrong: live endpoint/account-specific failures may require a later explicit compatibility fix.
- Final: Ruling: original website v1.0 ZIP identity/checksums remain externally unverified — the original release is absent (HTTP404/release not found); retain published data and the two failing checks rather than fabricate artifacts — cost if wrong: website validation stays blocked until authentic release archives are available.
- Final: Ruling: hot reload, other platform credential adapters and recharge/subscription/SC/special flow execution remain outside this feature — approved scope retains restart behavior and disables unsupported gifts — cost if wrong: those workflows need separate implementation rather than silently acting as ordinary gifts.

Deferred minors: none. The reviewer noted compressed formatting but did not raise a separate style/refactor finding. This plan record and Git history preserve the execution evidence after removing only this plan's ignored scratch workspace.

## Follow-up: seven UI fixes (2026-10-18)

The user requested tighter status/input spacing, faster and consistently positioned
pickers, unified rounded window/button behavior, click-driven quantities, inline
gift-send progress, and fixes for three Qt warning classes. Implementation remains
on the same two local feature branches.

| Repository / branch | Follow-up implementation commits |
| --- | --- |
| Host `codex/plugin-tile-extensions` | `040dc6b` status width follows its actual text, keeping the input beside short status labels |
| Plugin `codex/bili-live` | `178daf5` shared anchored pickers, parallel media, quantity interactions, inline send feedback and worker cleanup; `ca412ad` event-filter safety during Qt destruction and Python cyclic GC |

### Delivered behavior

- Both pickers use the same rounded, frameless tool-window base and shared card/tab
  styles. They center above their anchor, flip/clamp when necessary, follow owner
  movement, and pass outside presses through to the original target. Native title
  bar dragging preserves visible pickers and quantities.
- Emoticon loading uses up to four independent image requests; the shared HTTP
  limit and gift loader also permit four. Existing caches are reused, gift static
  thumbnails precede GIFs, and repeated image paths do not restart animations.
- Gifts are the default tab even when bag data arrives first. Empty idle status
  is hidden. Quantity options open on a gift click, not hover; the panel is 168px
  wide, puts 1 in the input when allowed, and omits a duplicate 1 button. A second
  click on the same gift sends one when permitted; moving to another gift closes
  quantities, with a short grace period across the gap to the quantity panel.
- Sending progress and failure messages follow the battery balance; success clears
  progress and refreshes balance. Long failures wrap without expanding off screen.
- Empty media paths no longer reach QMovie file opening; tool windows have valid
  top-level owners; workers are joined before retirement. Deferred media callbacks
  are cancelled and host-owned pickers deleted on tile shutdown. Application event
  filters check native target validity and Python state before processing events.

### Follow-up verification

| Check | Result |
| --- | --- |
| Send / composer / emoticons / lifecycle | 13 / 16 / 18 / 5 passed |
| Gift API / controller / media / popup / picker UX | 14 / 8 / 4 / 10 / 14 passed |
| Rebuilt ZIP installed into actual offline-patched Windows MainWindow | 6 passed; exit 0 |
| Total bili_live unit and installed integration tests | 108 passed |
| Windows real-VLC checks on rebuilt ZIP | Dark/light, 900/360/200 widths, native hit targets, GIFs, quantity gap, focus/IME; effective DPR 1.5 and 2.25, both exit 0 |
| High-DPI picker UX | 14 passed; exit 0 |
| Host plugin controls | 9 passed; includes observed RED→GREEN short-status spacing regression |
| Additional host checks during this follow-up | Credentials 7, cookies 9, bottom-bar order, fullscreen native focus, repository files 3 and repository map 5 passed |
| Packages / upgrade / original platform checks | Package CRC and source byte equality, historical upgrade and five original platform regression scripts passed |
| Changed Python sources, compiled in memory | Host 12 and plugin repository 26 passed |
| Patch whitespace | Both repositories pass `git diff --check` |

The final full unit run was also checked for callback exceptions and the three
reported warning strings instead of relying solely on unittest's exit code.
Installed integration captures and asserts absence of empty-file-name,
non-top-level-window and QThreadStorage warnings. A finalization run initially
printed a deleted EmoticonPopup callback despite passing assertions; it was not
accepted as clean. Two new tests reproduced direct parent destruction and Python
GC teardown errors, then passed after `ca412ad`. A separate 40-iteration stress
probe for each of direct, deferred, owner and GC deletion found no callback errors.

### Independent incremental review and fixes

One fresh-context read-only reviewer examined this follow-up across both branches.
Verdict: **With fixes**, zero Critical, three Important. The author accepted and
fixed all three with observed failing-then-passing regressions:

1. Explicitly delete pickers owned by MainWindow when their composer shuts down.
2. Default quantities to one despite service counts ordered as 10, 1, 99, while
   respecting services that forbid one and permit only listed counts.
3. Constrain/wrap long inline failures and reanchor the popup after layout changes.

The reviewer did not re-review the fixes; the author ran the final tests above.
No deferred minors. The additional Qt/GC finalization fix was author-diagnosed
and regression-tested after that review. Native theme inspection also caught
undersized quantity buttons; their usable height now has a regression test.

### Follow-up rulings and limits

- Ruling: preserve service quantity restrictions when the user requests a default
  of one — use one whenever allowed, otherwise the first permitted count, and never
  fabricate an unauthorized single send — cost if wrong: some gifts intentionally
  cannot use the requested one-click path.
- Ruling: retain `[关闭]` as an ordinary existing close-timing log — it is not a Qt
  warning and does not identify a failure — cost if wrong: timing-log preferences
  need a separate logging change.
- Ruling: judge loading improvements by bounded concurrent progress and cache reuse,
  not by a synthetic CDN speed claim — real authenticated service and network
  latency remain unverified — cost if wrong: a real CDN/account bottleneck may need
  further measurement. No real text/gift send was used for verification.
- Ruling: keep original historical published artifacts intact — website tests still
  have two existing failures for absent original v1.0 release ZIPs; page/link/asset
  checks pass — cost if wrong: complete website validation awaits authentic archives.
- The review set aside authenticated wallet/bag/live sends, actual CDN timing,
  mixed-monitor DPI and native VLC behavior. Primary checks cover native VLC and
  two fixed scaling settings; authenticated actions, actual CDN timing and moving
  between monitors remain unverified. Some VLC MPEG4 `get_buffer` diagnostics still
  occur at successful teardown; the three targeted Qt warning classes did not recur
  in tested flows. The earlier existing match_sync `analysis_size` failure was not
  rerun during this follow-up and is not claimed fixed.

Final installable artifact: `D:\Dev\DD_Monitor_Plugins\dist\bili_live-1.0.zip`.
SHA256: `184bc737168ad3d313538761eb2ccc4d27e665cb7c3b6a0ec48d020e0a383649`.
The artifact includes the final README and source files. Both branches are retained
locally; no push, merge or release, and the pre-existing `.codegraph/` is untouched.

## Follow-up: gift success, fan-club light signs, native following and exit

The user clarified that dragging smoothness means moving the main window while
its small pickers follow, rather than tile dragging. Plugin commit `db68825` fixes
the following with observed failing-then-passing regressions:

- `code=0, message="ok"` was misclassified as a failed gift send. Accept its
  case variants as success, keep nonzero codes/contradictory errors rejected,
  and refresh the wallet without success feedback. The controller regression
  exercises the real response parser using a synthetic HTTP response.
- The public roomGiftList response marks known ordinary fan-club light signs
  (IDs 31164/34001) with special_type=3 and the default_gift/send_gift route.
  The prior blanket special_type filter disabled them. Permit this exact known
  exception while retaining permissions, room/payment and unknown-flow checks.
  Current public room 6 was read without authentication; no real gift was sent.
- A quantity popup repositioned on every Move/Resize throughout the application,
  including unrelated windows. Restrict this to its gift picker, ignore unrelated
  base-filter event types early, and avoid native handle queries on ordinary
  events. The regression observes zero unrelated-window updates and at most one
  quantity update per owner move. Native tests cover 24 consecutive owner moves
  in each theme, accepting fractional-DPR physical-pixel rounding. These checks
  establish behavior and reduced repeated work, not a measured drag frame rate.

The host's production entry called os._exit while QApplication was still alive.
A native minimal-label reproduction identified the QThreadStorage warning's
thread address as the GUI thread; explicit QApplication disposal removes the
warning before the retained direct process exit. Application disposal requires
complete worker cleanup: a six-second owned request exceeded the existing
2.5-second wait and reproduced a fatal QThread destruction; an event-loop worker
also reproduced a shutdown hang until quit was requested. The final close path
requests interruption/quit and joins all remaining owned QThreads, including
native thread-local teardown, before disposing QApplication. The window remains
hidden during this cleanup. `[关闭]` remains an ordinary timing log.

| Final incremental check | Result |
| --- | --- |
| Send / composer / emoticons / lifecycle | 13 / 16 / 18 / 5 passed |
| Gift API / controller / media / popup / picker UX | 17 / 9 / 4 / 10 / 15 passed |
| Rebuilt actual ZIP installed into offline Windows MainWindow | 6 passed at effective DPR 1.5 and again at 2.25; both processes exit 0 |
| Unique bili_live unit and installed integration checks | 113 passed |
| Native Qt + real local VLC | Dark/light, 900/360/200 widths, continuous owner/gift/quantity following, native hit targets, GIFs, gap, focus/IME; effective DPR 1.5 and 2.25, exit 0 |
| High-DPI picker UX | 15 passed, exit 0 |
| Full host close-release selfcheck | Pass; real production exit subprocesses cover label, MainWindow/VLC, six-second request and event-loop worker; no QThreadStorage warning |
| Host plugin control regressions | 9 passed; deliberate fault-isolation exceptions are expected test output |
| Final packages | CRC/source byte consistency, install without execution, host loading and five platform registrations pass |
| Syntax / whitespace | Two changed host and seven changed plugin Python sources compile in memory; both patches pass git diff --check |

The reported QWindowsWindow::setGeometry warning is **not confirmed fixed**.
Native probes of main-window resizing/restoring/maximizing and settings dialogs
with actual settings, a real MainWindow owner, animated page switching and
post-save value collection did not reproduce it. The user has an optional pending
question about the exact triggering operation. Do not apply a guessed minimum-size
or orientation workaround. Fixed-scale coverage does not establish cross-monitor
DPI behavior. VLC teardown can still print existing MPEG4 get_buffer diagnostics.

The previous independent reviews remain recorded above; these later diagnostics
and fixes used author regressions and did not dispatch another review. Previously
documented historical-website/match_sync limitations remain unchanged and are not
claimed fixed or rerun here. No real danmaku/gifts, push, merge or release.

Final replacement artifact: `D:\Dev\DD_Monitor_Plugins\dist\bili_live-1.0.zip`.
SHA256: `0761b65b58f7ebcfe3aee28e35595fca29d7ce543132d58790e4b0c4f6cc6d24`.
The user's installed, untracked `plugins_user/bili_live/` copy was preserved;
the new source/ZIP needs to be installed and the host restarted to run these fixes.

## Follow-up: geometry warning without a known trigger

The user answered that the triggering operation is unknown. The size warning
remains unreproduced and is not claimed fixed. Add targeted evidence capture for
its next occurrence: the Qt log handler records a bounded Python calling stack
only for QWindowsWindow::setGeometry messages, without querying GUI objects from
Qt's potentially non-GUI message-handler thread. Give MainWindow and SettingsDialog
stable object names so their native warning identifies the originating window.
No minimum-size, layout, warning suppression or plugin behavior changes.

The extended selfcheck_qt_log first failed because no geometry calling path was
recorded, then passed after the change. It exercises real qWarning delivery and
native names of real MainWindow/SettingsDialog windows, checks the triggering
Python function appears in the log, preserves existing fatal logging, and verifies
ordinary warnings do not receive stacks. It passes offscreen and in Windows Qt
at effective DPR 1.5 and 2.25. selfcheck_general_settings passes, changed Python
sources compile, and git diff --check passes.

Expanded validation found an existing selfcheck_settings_status failure at its
shared-room identity assertion (line 227). Re-executing the committed HEAD app
and dialogs reproduced the same failure. A temporary explicit shared-data fixture
allowed the script to progress to a second stale assertion about the global
settings key set; that experimental fixture change was removed. The status test
was not weakened or counted as passing, and these unrelated baseline issues are
outside this diagnostic change. No new independent review was dispatched.

## Follow-up: gift list scroll, guard payment flows and transient picker positions

Plugin commit `7304850d9ca1e5953c8d64eb3e7c5e736e441873` on
`codex/bili-live` addresses the user's next three reports. Host runtime code did
not require changes; this host branch records the paired delivery only.

Disabling a focused gift card walks Qt's focus chain through later cards and
makes QScrollArea reveal each card, scrolling from 0 to 1227 in the failing
offscreen reproduction (1231 in native Windows). Native testing also established
that QApplication's active focus can belong to the host while the tool window
remembers a gift card. Use the gift window's remembered focus and move it to the
scroll container before disabling cards. Preserve the selected grid when only
the wallet or a different tab's contents change. The regression uses 80 cards,
actual clicking/focus and the send/refresh states without issuing a real send.

The user confirmed the captain gift tooltip was "暂不支持此购买流程" in all
rooms they tried. This was a plugin limitation: the initial implementation only
supported sendGold/sendBag and rejected all interactive_pay routes. Public,
unauthenticated roomGiftList reads for 21452505 and 22637261 confirmed captain,
admiral and governor gifts use guard_gift/interactive_pay; guard attire uses
guard_attire/interactive_pay (special_type=15). The cached official frontend
app.3f7250563d6495ab0c32.js modules 17202/99591 establish the
`/xlive/revenue/v2/interactive_pay/send` fields and three guard agreement URLs.
Implement these two direct routes with the original gift_scene JSON, receiver,
anchor, room, quantity, price, CSRF and getIpInfo address. Guard opening gifts
confirm amount/agreements before submission; cancel on state/context changes
during the dialog. No retry, alternate endpoint or paid fallback is attempted.
Retain server permissions and quantity/stock restrictions. Descriptive rules on
ordinary paid gifts no longer count as unknown bag-use restrictions. Unsupported
scenes such as guard_blind_box stay visible with their specific disabled reason.

Each ancestor Move/Resize during a bottom-row layout previously moved the native
picker immediately, exposing intermediate anchor positions. An actual Move-event
observer reproduced two positions from one layout transaction for both picker
types. Coalesce descendant layout positioning through an owned zero-delay timer;
owner-window Move still places synchronously for dragging. Hide/shutdown cancels
pending placement. The integration suite also sweeps the native pointer between
four real MainWindow tiles and the open gift/emoticon pickers. This establishes
the identified cause and covered paths, not every intermittent physical pointer
trajectory or a measured frame-rate improvement.

| Final follow-up validation | Result |
| --- | --- |
| Send / composer / emoticons / lifecycle | 13 / 16 / 18 / 5 passed |
| Gift API / controller / media / popup / picker UX | 23 / 9 / 4 / 13 / 18 passed |
| Actual rebuilt ZIP installed into offline Windows MainWindow | 7 passed at effective DPR 1.5 and 2.25 |
| Unique bili_live unit and installation checks | 126 passed |
| Native Qt + actual local VLC | Dark/light, 900/360/200 widths, continuous owner/picker following, hit targets, GIFs, gap, focus/IME; both DPR settings exit 0 |
| Native gift popup / picker UX | 13 / 18 passed at each DPR; includes real agreement dialog clicks, focused-card scroll and cancelled placement on teardown |
| Final packages | CRC, source-byte consistency, install without execution, host loading and five platform registrations pass |
| Syntax / whitespace | All changed plugin Python files compile in memory; git diff --check passes |

The expanded timer regression also corrected test cleanup: shutdown already
schedules picker deletion, so tearDown must not call deleteLater again after
processing events. The installed restart fixture no longer unloads the old
closed owner after replacing its temporary module namespace. The unrelated
window in the movement test is placed away from the picker so it cannot trigger
the independent mouse-leave policy merely by covering it.

Final artifact: `D:\Dev\DD_Monitor_Plugins\dist\bili_live-1.0.zip`.
SHA256: `33c09e367fd8406d113ea9da7b5eec4ffe8de8d5ccb6aa01b818bebb2423f446`.
No real gifts/danmaku were sent. The new payment forms follow public/official
evidence and synthetic request tests; authenticated online charging remains
unverified. The prior setGeometry warning is still not claimed fixed; native VLC
can still print MPEG4 teardown diagnostics. Earlier unrelated repository-wide
validation limitations remain as recorded above. No additional independent
review, push, merge or release. Preserve `.codegraph/` and the user's installed
untracked `plugins_user/bili_live/`; source loading needs a restart, installed
loading needs the replacement ZIP and a restart.

## Follow-up: retain retrieved emoticons during refresh and use inline spinners

Plugin commit `28a246e56842b3bd0b381d86acc2885d1bb3c587` implements the user's
explicit refresh behavior. Emoticon refresh preserves the retrieved package tabs,
loaded icons, selection and scroll while awaiting the response. The same-context
permission snapshot remains valid so existing emoticons can still be selected;
failure retains them. An unchanged result reuses the existing grid. Room/account
changes explicitly clear the old content and permissions; the existing request
and image generation checks continue to reject stale responses.

Both pickers share a 16-pixel vector spinner directly left of refresh. It has a
reserved layout slot, animates only while loading and visible, pauses while the
picker is hidden and resumes on reopen if the request is still pending. Refresh
is disabled during reads. Gift loading no longer adds a separate text row;
actual read errors retain their error messages. Preserve the hidden emoticon
status label's layout stretch so the spinner cannot spread away from refresh.

Three added regressions were observed failing before the implementation, then
passing: retain 80 retrieved emoticons/icons and scroll across pending/error/same
results; select during a blocked refresh but clear on room change; inspect the
rendered spinner animation, adjacency, stopped hidden timer and resumed loading
for both picker types. A tighter adjacency assertion reproduced a 91-pixel gap
when the status label was hidden; retaining its layout stretch fixes that too.

129 unique plugin unit/installed integration checks pass (13 send, 17 composer,
19 emoticons, 5 lifecycle, 23 gift API, 9 controller, 4 media, 13 gift popup,
19 picker UX, 7 installed integration). Native Windows integration and picker UX
pass at effective DPR 1.5 and 2.25 after the final header layout change. The
same-turn native VLC checks and emoticon suite also pass at both scales before
that header-spacing adjustment. Python syntax, patch whitespace, ZIP CRC/source
byte consistency and host package loading pass. Host runtime code is unchanged.

Final replacement ZIP: `D:\Dev\DD_Monitor_Plugins\dist\bili_live-1.0.zip`.
SHA256: `0ab81e5bd1bfa2c111da766cf92b1d2179c4781c54874c23f655686584d9a22a`.
No real gift/danmaku sends, extra independent review, push, merge or release.
Preserve the installed untracked plugin and `.codegraph/`. Prior geometry-warning,
VLC teardown diagnostics and unrelated full-repository validation limits remain
as recorded. Direct source loading needs a restart; installed loading needs this
ZIP and restart.

## Follow-up: retain battery balance and protect quantity-popup travel

Plugin commit `ef39743b7ef21bcfabcad7e7e911c7b507df6a08` implements the latest
balance and quantity-popup feedback on `codex/bili-live`. Host runtime code is
unchanged; `codex/plugin-tile-extensions` records delivery here.

The old send invalidation explicitly replaced the displayed wallet with None.
The account-wide coordinator now retains the submitted cost and broadcasts a
debit only after confirmed success. Controllers retain the displayed balance,
subtract price times quantity for paid gifts, then replace it with an independent
authoritative wallet response. Bag gifts do not debit batteries; rejected sends
do not debit either. All same-account tiles apply the change, including when the
originating tile has been destroyed. Consecutive successes accumulate and
revision/read identity checks reject older pre-send or prior-send responses.

Display retention is separate from permission to purchase and read freshness.
An uncertain outcome retains the number without assuming a debit, but disables
paid sends until a fresh wallet response arrives. A hidden invalidated panel
fetches the wallet when reopened even though its displayed number is retained.
Manual refresh also retains the number. A failed reconciliation retains the
estimate and reports the read error without reclassifying a confirmed gift as
failed. Success adds no success text; existing inline refresh indicators remain.

The quantity popup sits six pixels from its card while grid rows are only three
pixels apart. The travel gap therefore overlaps the preceding gift row, whose
Enter handler and pointer polling both used to dismiss the popup. Both now use
the same narrow bridge between the card and popup. It covers above/below
placement while preserving immediate dismissal on another gift outside that
bridge, second-click one-gift sending and existing owner-window following.

Regression evidence: six controller assertions reproduced the old cleared
balance; a second-row pointer traversal reproduced premature closure at the
overlapping row. The fixes pass these reproductions. Added/extended checks
cover blocked authoritative reads, exact quantity cost, two rooms on one account,
destroyed sender, accumulated sends, old refresh rejection, bag gifts, rejected
and uncertain sends, retained-display purchase blocking, reopening stale state,
both popup directions, neighbor dismissal and one emitted quantity submission.
The installed ZIP integration also checks the actual label first shows the
deducted amount and then the authoritative amount, with no success text.

| Current validation | Result |
| --- | --- |
| Send / composer / emoticons / lifecycle | 13 / 17 / 19 / 5 passed |
| Gift API / controller / media / popup / picker UX | 23 / 15 / 4 / 14 / 21 passed |
| Unique unit and actual ZIP installation checks | 138 passed, including 7 installed integration checks |
| Windows Qt integration / gift popup / picker UX | 7 / 14 / 21 passed at effective DPR 1.5 and 2.25 |
| Native Qt + actual local VLC | Dark/light, 900/360/200 widths, owner following, hit targets, GIFs, gap, focus/IME; both scales exit 0 |
| Final package integrity | ZIP CRC, source-byte consistency, install without execution and host loading pass |
| Syntax / whitespace | Six changed Python files compile in memory; git diff --check passes |
| Host repository documentation checks | File checks 3 and repository-map checks 5 passed |

The final ZIP was rebuilt after the README validation record; native runs used
the same runtime bytes before that documentation-only packaging change.
Replacement artifact: `D:\Dev\DD_Monitor_Plugins\dist\bili_live-1.0.zip`.
SHA256: `ad8d81e6a735aaa97db2ee718ae1af5b3ddc0d878dd4052351e386d613eb588f`.
No real gifts/danmaku were sent. Native VLC still printed the previously recorded
MPEG4 teardown diagnostics; earlier geometry-warning and unrelated full-repo
validation limitations remain. No additional independent review, push, merge or
release. Preserve `.codegraph/` and the installed untracked
`plugins_user/bili_live/`. Source loading needs restart; installed loading needs
the replacement ZIP and restart.
