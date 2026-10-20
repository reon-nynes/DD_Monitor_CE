# Refresh the optional Bilibili plugin on current main

Date: 2026-10-19. Status: approved by the user on 2026-10-19; builder check found nothing important left. See the [implementation plan](../plans/2026-10-19-bili-plugin-main-refresh.md).

## Intent and confirmed boundaries

Recover the separation between the application and the optional Bilibili interaction plugin after upstream main integrated PR #12 and a locally adapted implementation of its sending feature. Keep current main's unrelated improvements. Reimplement the generic host extensions on a clean branch, then adapt the existing `codex/bili-live` plugin to that host.

The user confirmed:

- Without the plugin, the host continues to persist necessary Bilibili cookies, but cannot send danmaku or gifts. Existing login, playback and incoming danmaku continue to work.
- Adopt main's centered input with a maximum width.
- Preserve the existing bili_live plugin's other behavior. In particular, do not adopt main's newer emoticon sorting or picker implementation, and do not redesign gifts, popups or native drag following.
- Remove unnecessary documentation commits from the rebuilt host feature history.
- Each completed change needs related tests, passing validation and a Git commit. Consult the existing implementations first.

## Verified starting points

| Work | Repository and revision |
| --- | --- |
| Current upstream main | `D:\Dev\DD_Monitor_CE`, `c3743fde8d48f539c625fea26602b16352dbed7b` |
| Existing host extension work | `codex/plugin-tile-extensions`, `02bc173768f6fe420dd5ecc9fb4076d70a714c14` |
| Cookie persistence reference | `codex/bilibili-cookie-persistence`, `7011541ad537a41cbf264edb7f544bcdcf54c24e` |
| Original sending reference | `codex/bilibili-danmaku-send2`, `7c034e2700449cb2c67c05a80776577826c39933` |
| Existing plugin | `D:\Dev\DD_Monitor_Plugins`, `codex/bili-live`, `f6c4fd92ce7f0333d99c1d9ecf73b0ec187f3118` |

Fetching both the fork and public upstream confirmed that their main refs resolve to the same host commit. Refresh upstream again before starting implementation; if it advances, audit the additional changes rather than assuming the recorded revision is still latest.

The PR #12 integration merge is `c384b74`. Its first-parent diff changes only four files because the host already contained an adapted sending implementation. A mechanical revert of that merge would leave the feature present. The required result is a focused removal of the complete built-in interaction implementation and its later host wiring, with PR #12 recorded as provenance.

Main has since added libmpv playback, codec selection, resize work, repository policy and a classified check runner. Its plugin API adds `StreamCodecUnavailable` and `Platform.play_url_for_codec`. It does not yet contain the existing branch's tile-control or credential-snapshot API. All newer platform and playback interfaces must survive this work.

The host checkout has pre-existing untracked `.codegraph/` and `plugins_user/bili_live/`. The plugin repository has pre-existing untracked `.codegraph/`. Preserve them and do not stage them. The installed plugin copy is not the source of truth; source changes belong in the separate plugin repository.

## Branch and commit arrangement

Author's choice: create `function/plugin-tile-extensions` from freshly verified upstream main. The `function/` prefix follows the policy in current main's AGENTS.md and CONTRIBUTING.md. Keep main and the original host feature branch available without rebasing or resetting their existing history.

Use separate implementation commits on the new host branch:

1. Remove built-in Bilibili sending and its host coupling while preserving cookie persistence and current main's receiving/playback behavior. Include removal regressions and update affected existing checks.
2. Add the adapted generic tile-control, credential and interaction interfaces, with centered bounded allocation and compatibility regressions. Additional fixes may be separate commits when they form independently testable changes.

Update the existing `codex/bili-live` plugin branch with the minimum compatibility changes and corresponding tests. Do not rewrite its existing behavior or history.

Reapply the needed host code and tests selectively. Do not merge the old extension branch wholesale. Omit its progress logs, old design/plan files, documentation-only verification records and obsolete diagnostics. Keep useful public API documentation, the check index and other repository-required references current within implementation commits.

Keep this design and the subsequent implementation plan on the existing host branch as planning records; do not carry those planning commits onto the clean implementation branch. This keeps the deliverable history focused while retaining the requested design approval record.

## Host ownership and removal

The host owns Bilibili login, cookie storage, playback, incoming danmaku, existing account and receiving lifecycle fixes, and platform-neutral plugin services. Preserve the cookie-persistence behavior represented by `7011541`, adapting it to current main rather than restoring old files wholesale. Retain `SESSDATA`, `bili_jct` and `buvid3` across restart through the existing configuration and login paths. Logout must clear authentication as before.

Remove the built-in `ddm/danmaku_send.py` implementation, Bilibili sending/emoticon-fetch endpoints in host `ddm/bili.py`, concrete composer construction and room updates in Tile, host-owned emoticon order, composer-specific signal connections, login synchronization, fullscreen references and shutdown waits. Replace only the integration points needed by generic extensions. Keep the existing legacy generic DanmakuSender registration API compatible; it must not create built-in Bilibili interaction capability.

Preserve current main's playback backend, codec selection/fallback, recording, volume menu, input shortcuts outside plugin editors, receiving renderers and receiving startup/room isolation. Retain ancillary-cookie discovery used by incoming danmaku. Remove or adapt sending-specific host tests and obsolete runner entries; retain useful unrelated assertions from mixed tests. Add explicit coverage that the host starts, logs in/restores fake cookies, switches rooms, enters/exits fullscreen and shuts down without any sending module or installed plugin.

Core removal does not port main's emoticon sorting or migrate its old host-owned order into the plugin. Any old configuration keys can be ignored through normal configuration compatibility; this task does not need a new settings migration API.

## Generic extension contract

Adapt the existing `TileControl`, `TileControlContext`, `TileControls` and credential-store implementations to current main. Preserve the public methods already consumed by bili_live where practical:

- `PluginContext.register_tile_control(control_id, factory, priority=...)` owns deterministic providers and attaches controls to existing and new tiles, including empty ones.
- A control owns a widget and declares its minimum/preferred width. It receives detached room dictionaries on initial assignment and every later room change, exposes generic interaction state, and shuts down exactly once when detached.
- Factory/load failures are isolated and partially registered providers are rolled back. One failed provider cannot break another provider or ordinary player controls. Removed controls' callbacks cannot act on replacement tiles.
- Fullscreen reuse retains a tile's control instance. Generic interaction protects editing, IME composition and open popups from player shortcuts or automatic hiding, including when the pointer leaves the tile.
- `credentials(platform)` returns a detached immutable snapshot with account generation. Account identity changes emit platform/generation events without credentials.
- `update_credentials(platform, changes, expected_generation=...)` accepts only adapter-allowed ancillary fields. Bilibili allows `buvid3`, persists it through the host save path and rejects updates captured under an old login. It cannot replace authentication credentials.
- Credential access/publication is on the GUI thread; plugin workers use captured copies. Cover a fake second platform so public services remain platform-neutral.

Preserve main's newer Platform API and old plugin registration/loading behavior. Do not add Bilibili classes, endpoints, gift state or composer knowledge to these generic services. Exclude unrelated historical diagnostics and shutdown changes unless a reproduced current-main integration failure requires them; any required fix needs its own regression and commit.

## Centered, bounded allocation

The only intended plugin presentation change is its placement and width within the tile bottom bar. Apply main's centering rule to the generic extension region, leaving the plugin's internal input/emoticon/gift/send arrangement intact.

Author's choice: for the single bili_live control, use main's cap `min(520, max(300, int(tile_width * 0.45)))` logical pixels for the complete control region. Shrink to the available space between existing controls. Center against the entire bottom bar when space permits; clamp to the free interval otherwise. The gift button consumes space inside that region rather than widening it beyond the cap.

Preserve current main's native control sizes, compact volume popup, recording access and fullscreen access. Below the plugin's declared usable minimum, hide its region rather than cover host controls. Keep no-plugin layout equivalent to current main with its built-in composer absent. Do not revive the older requirement to force a plugin input into a 200-pixel tile by hiding existing host actions.

For multiple providers, use one centered bounded extension group. Order by priority then registration order, reserve declared minima for providers that fit, and distribute spare width deterministically toward their preferred widths. Hide providers that cannot fit without overlap. The precise public field names and the allocation implementation are builder choices; there must be no Bilibili-specific layout branch. Layout invalidation must account for provider changes and visibility so main's layout signature cache cannot reuse stale geometry. Repeated hover must preserve focus and settled popup anchors.

## Plugin adaptation

Work from the committed plugin source at `f6c4fd9`, preserving its sending, gifting, retained content/balances, inline loading, quantities, popup closing, animations, native HWND following and worker lifecycle. Do not transplant main's composer or picker. Do not add emoticon sorting, new gift flows or another login path.

Change only the host API capability checks, control registration/width declarations, credential binding or runtime assumptions that the adapted host requires. In particular, tests that assume VLC must be updated to verify the real current libmpv host and current native video surface. A compatibility change needed to preserve existing behavior is in scope; unrelated refactoring is not.

Update the short compatibility instructions and package from Git-tracked source as `dist/bili_live-1.0.zip` using the existing tooling. Test installation of that actual ZIP into a temporary plugin directory; do not replace the user's installed untracked plugin during development. The final delivery identifies the new host branch, plugin commit and matching ZIP.

## Validation and completion

Use isolated state, fake credentials, temporary plugin/config/cache roots and `DDM_NO_SAVE=1`. Do not read real account configuration or send real danmaku or gifts.

Host coverage includes no-plugin startup/shutdown and feature absence; cookie restoration/login/logout; receiving room isolation/startup cancellation; plugin loader/platform compatibility; tile creation/reassignment/removal and failure rollback; credential snapshots/generations/conditional persistence; allocation with one/multiple providers; fullscreen focus/IME; hover stability and ordinary host controls.

Update the new main check runner and classification index for tests added, removed or changed. Run the full `repository` and `offline` suites, relevant existing native checks and syntax/patch validation. Run native libmpv regressions at the available Windows scale and an additional high-DPI setting. Exercise 900, 360 and 200 logical-pixel tiles and a large/fullscreen tile that reaches the 520-pixel cap. Assert center/clamping and cap numerically, and test that narrow tiles preserve recording, volume and fullscreen access.

Run all bili_live source tests, actual-ZIP integration against the new host, relevant native popup/focus/follow tests at both scales, and plugin packaging/regression checks for existing plugins. Preserve the popup and gift behavior through these checks rather than rewriting it. Verify plugin disabled/removed plus restart restores the ordinary host while cookies, playback and receiving remain available.

Investigate any encountered failure; compare with the recorded baseline before attributing it to this work. Fix task-caused failures. Report any independently reproduced pre-existing failure and its actual impact rather than claiming all checks passed. Historical VLC warnings, website artifact failures and teardown outcomes are evidence to recheck, not assumptions about current main. No actual online send/payment compatibility claim follows from simulated requests.

Deliver tested commits, the clean branch/base relationship, the plugin commit and ZIP, validation results and any remaining untracked files. No push, upstream merge or release is requested.

## Builder discretion

The branch arrangement, generic centered-group policy, cap applying to the complete plugin control, narrow-tile fallback and omission of historical diagnostics/planning commits are the author's proposed implementation choices, not additional user requirements. The builder may settle exact symbols, signal signatures, cache invalidation details, test grouping and commit count while preserving the confirmed feature boundary and unchanged plugin behavior.
