# Bilibili Plugin Main Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove built-in Bilibili interaction from current main, restore generic plugin extensions and run the existing bili_live plugin with centered bounded controls.

**Architecture:** Start a clean host branch at upstream main and selectively remove sending while retaining cookie storage and receiving. Adapt the existing provider/credential services to current Tile, MainWindow and fullscreen code; a centered extension container replaces concrete composer coupling. Keep plugin business logic unchanged and update compatibility, packaging and real-host tests.

**Tech Stack:** Existing Python, PySide6, requests and libmpv host; unittest/selfcheck runner; existing plugin ZIP tooling.

**Spec:** [Approved design](../specs/2026-10-19-bili-plugin-main-refresh-design.md).

## Global Constraints

- Without the plugin, persist necessary Bilibili cookies but provide no danmaku/gift sending.
- Preserve existing bili_live behavior except for centered bounded placement; do not port main's picker/sorting.
- Use `function/plugin-tile-extensions` from upstream main, verified at `c3743fd`; update existing plugin `codex/bili-live` at `f6c4fd9`.
- Preserve untracked `.codegraph/` and installed `plugins_user/bili_live/`; stage exact paths.
- Cap the entire extension region at `min(520, max(300, int(tile_width * 0.45)))`; hide controls whose minimum cannot fit alongside host actions.
- Keep planning commits on the old host branch; keep useful API docs and check indexes in implementation commits.
- Every completed implementation change has regression coverage, passing applicable checks and a commit; no push/merge/release.
- Use isolated fake accounts/config/cache, `DDM_NO_SAVE=1`, no actual sends or payments.

## Review Focus

- A late callback from a removed provider must not touch a reused tile (Task 2 invalidation/shutdown test).
- Switching between unsupported and supported rooms must invalidate cached layout visibility (Task 2 room and layout test).
- Late device-cookie publication after login replacement must be rejected without overwriting auth (Task 2 credential generation test).
- A native picker must follow the new libmpv host without depending on VLC fields (Task 3 real-ZIP/native tests).
- A narrow tile or long recording status must retain host actions without overlap or focus churn (Task 2 geometry/hover tests).

## File responsibilities

Host runtime: `ddm/bili.py` owns existing cookie/playback/receiving APIs; `ddm/widgets.py` owns Tile and bar layout; `ddm/app.py` owns login, persistence and lifecycle; `ddm/fullscreen_cursor.py` consumes generic interaction. Adapt `ddm/plugins.py` and restore focused `ddm/plugin_controls.py` and `ddm/plugin_credentials.py` from the old feature branch.

Host tests: create `dev/selfcheck_bili_plugin_boundary.py`, adapt mixed composer-dependent selfchecks, restore `dev/selfcheck_plugin_controls.py` and `dev/selfcheck_plugin_credentials.py` with current-main/layout cases. Update `dev/checks/suites.json`, `dev/checks/README.md`, public `docs/plugins.md` and repository inventories required by main.

Plugin: keep `plugins/bili_live/` runtime except for needed declarations/capability compatibility. Update `tests/bili_live_support.py`, composer/installed integration/native checks and short README compatibility information. Package using the existing tracked-source tooling.

### Task 1: Remove built-in interaction and preserve cookies

**Interfaces:** Consume current main's login/cookie APIs and `Tile.set_room(room)`. Produce a normal host with `set_login_cookies`, `_cookies`, `ensure_buvid3` unchanged, and no `ddm.danmaku_send`, `bili.send_danmaku`, `bili.get_emoticons` or concrete Tile composer.

- [ ] Write `BiliPluginBoundaryTests` with fake state asserting no sender module/API/widget, all three restored cookies survive a config round trip, room/fullscreen lifecycle works and normal close succeeds with plugins disabled. Assert codec APIs remain available.
- [ ] Run the boundary test before removal and confirm the built-in capability assertions fail.
- [ ] Create `function/plugin-tile-extensions` from refreshed upstream/main after planning commit. Keep the existing checkout and local files; no reset or whole-tree replacement.
- [ ] Remove `ddm/danmaku_send.py`, sending-only API functions and concrete composer/order wiring from app/widgets/fullscreen. Preserve generic legacy sender registration and all cookie/receiving APIs. Keep main's bottom bar control sizing and layout without its composer/spacer section.
- [ ] Delete tests dedicated solely to the removed built-in sender/picker; adapt mixed checks using their original non-sending assertions. Remove runner/index/doc references to deleted files and add the boundary test as isolated offline coverage.
- [ ] Run boundary, cookie, receiving/startup, room-switch, tile-bottom, fullscreen, theme and repository tests; diagnose failures against main where needed. Run both complete repository/offline suites before the commit and inspect their logs.
- [ ] Stage exact changed files, run `git diff --cached --check`, commit `refactor: move Bilibili interaction out of the core app`.

### Task 2: Adapt the generic services and centered bar

**Interfaces:** Preserve `TileControl(widget, minimum_width=0, preferred_width=240)`, `TileControlContext(parent, room, invalidate_layout)`, `PluginContext.register_tile_control(control_id, factory, priority=0)`, `credentials(platform)` and `update_credentials(platform, changes, expected_generation=...)`. CredentialSnapshot exposes `platform`, `generation`, immutable `values`. Events remain `account.changed` and `account.credentials_updated`.

- [ ] Restore the old branch's controls/credentials regression files without restoring old product files wholesale. Add tests for one generic provider at widths 900/360/200/1600, center/cap/clamping, two providers by priority, narrow fallback preserving player controls, status/recording changes, unsupported-room return and repeated-hover focus stability. Assert `StreamCodecUnavailable` and `Platform.play_url_for_codec` still work.
- [ ] Run the restored tests and confirm missing-interface/layout failures.
- [ ] Restore/adapt the focused control and credential service modules and plugin manager/context registrations. Give each tile one extension container immediately after the status label, with provider wrappers inside it, so one generic centered group can be allocated and positioned independently of player controls.
- [ ] Add `TileControls` allocation returning the fitted group width; reserve provider minima in priority/order, distribute spare space toward preferred widths, and let the group use spare capped width for a single expanding control. Dispose each provider once and invalidate stale callbacks on removal. Isolate failed factory/room/interaction hooks and failed plugin load rollback.
- [ ] Update Tile room delivery, drop/shutdown, layout invalidation/signature and `plugin_interaction_active()`. Reuse main's fixed-control/free-interval calculation for centered/clamped placement; compute the group cap with the exact spec formula and preserve no-provider layout.
- [ ] Adapt MainWindow tile attachment and credentials registration, login/logout notifications, allowed ancillary-cookie publication and persistence. Use `bili.set_device_cookie(value)` as a narrow host adapter if needed, rather than writing auth fields. Replace fullscreen concrete editor checks with generic active-interaction protection before outside-pointer hiding.
- [ ] Run controls/credentials plus cookie/account, room/fullscreen, plugin loader and both repository/offline suites. Update API docs and check catalog/index for every new selfcheck. Test failure rollback and detached callbacks explicitly.
- [ ] Stage exact paths and commit `feat(plugins): restore generic tile controls on current main` after passing checks.

### Task 3: Adapt and verify the existing plugin

**Interfaces:** Consume Task 2's unchanged public control/credential methods. Produce the existing `codex/bili-live` source, a matching tracked-source `dist/bili_live-1.0.zip`, and tests accepting a `--host D:\Dev\DD_Monitor_CE` argument.

- [ ] Compare old plugin registration/session assumptions with Task 2's API. Add installed integration tests asserting centered capped controls, no duplicated built-in composer, hidden narrow input with retained host actions, and independent drafts/room/account transitions. Replace VLC-specific native setup/assertions with real libmpv state and surface assertions; retain existing popup/IME/native follow checks.
- [ ] Run changed tests before compatibility edits to identify actual failures. Do not alter the picker/gift runtime merely to satisfy an obsolete VLC test.
- [ ] Make minimum declaration/capability/session changes needed for the host. Update README compatibility to describe public capabilities instead of requiring the old host branch. Preserve all other plugin module behavior and native follower implementation.
- [ ] Build the ZIP from tracked sources. Run every `check_bili_live_*.py` with the new host, source tests offscreen and installed/native checks under Windows at default and additional high DPI. Run package integrity/source-byte and existing plugin packaging/regression checks. Capture process exit codes as well as assertions.
- [ ] Run host native libmpv/resize/fullscreen tests and inspect source diffs for accidental playback/API regressions. Check plugin disabled/removed and restarted using temporary install directories, retaining fake cookie restoration.
- [ ] Diagnose any failure against the unchanged current-main/plugin baseline. Fix task-caused failures with regression tests. Document independently reproduced pre-existing failures accurately; do not silently remove or skip their assertions.
- [ ] Stage exact plugin changes and commit `fix(bili_live): support the refreshed generic host interface`. Rebuild if tracked runtime/package documentation changes and rerun package consistency.
- [ ] Request one fresh whole-change reviewer for both repositories, resolve material findings with tests and commits, then report branch/base, host/plugin commits, ZIP, validation evidence and preserved untracked files.

## Verification commands

Host: `.venv/Scripts/python.exe dev/run_checks.py --suite repository`, then `--suite offline`; selected native checks via the classified runner or an isolated direct invocation. Use the existing `.venv` and local libmpv installation.

Plugin: use the host Python to invoke each relevant test with `--host D:\Dev\DD_Monitor_CE`. Read existing packaging entrypoints before building; native tests use `QT_QPA_PLATFORM=windows` and a second run with `QT_SCALE_FACTOR=1.5`. Stop/await test-owned workers before interpreter teardown.

Final: compile changed Python, `git diff --check`, ZIP CRC/source consistency, exact staged-path review and clean tracked status in both repositories. Do not claim a passing process when assertions succeed but teardown crashes.

## Self-review and execution

All approved design sections map to Tasks 1-3, including legacy API compatibility, cookie generations, multi-provider allocation, narrow fallback and unchanged plugin behavior. Public method names match the existing plugin. Each review-focus condition has an explicit regression owner above. Execute natively in the current session, with one independent final reviewer; the user's approval authorizes carrying out this migration.
