# Generic tile extensions and the bili_live plugin

Date: 2026-10-18. Status: approved by the user on 2026-10-18. Product implementation has not started. See the [coordinated implementation plan](../plans/2026-10-18-bili-live-plugin.md).

## Intent and confirmed scope

Keep the Bilibili interaction features outside the main application while preserving the experience of `codex/bilibili-danmaku-send2`. Implement the already approved live-gifting behavior in the same plugin. Users continue to log in through the application's existing account interface and interact directly below each Bilibili video.

The user requested two new development branches:

| Repository | New branch | Starting point |
| --- | --- | --- |
| `D:\Dev\DD_Monitor_CE` | `codex/plugin-tile-extensions` | `codex/bilibili-cookie-persistence`, commit `7011541ad537a41cbf264edb7f544bcdcf54c24e` |
| `D:\Dev\DD_Monitor_Plugins` | `codex/bili-live` | cloned repository `main`, commit `7f909becce3329647c9cdf7e46f876572a193908` |

The branch names are the author's choice. Both branches have been created. Existing branches and the pre-existing untracked `.codegraph/` directory remain available.

Behavioral sources inspected locally:

- Sending: `codex/bilibili-danmaku-send2` at `7c034e2700449cb2c67c05a80776577826c39933`, including its composer, API functions and self-checks.
- Gifting: `codex/bilibili-live-gifts` at `8fe7178`, containing the approved `docs/superpowers/specs/2026-10-18-bilibili-live-gifts-design.md` and its implementation plan. That branch contains a design and plan, not implemented gifting code.
- Existing plugin packaging and UI integration: `domestic_live`, `global_live`, and especially `match_sync` in the plugin repository.

This document carries the sending and gifting requirements into the plugin architecture. The original gifting plan's application-module paths and instruction not to create a plugin are superseded by the user's current request. Its user-visible behavior remains the target.

## Ownership

| Main application | bili_live plugin |
| --- | --- |
| Account login, logout, credential persistence and existing playback/receiving | Text danmaku sending and emoticon APIs |
| Stable per-tile control attachment, room updates, layout and cleanup | Composer, drafts, feedback and emoticon popup |
| Generic credential snapshots and account-change notifications | Gift catalog, wallet, bag, validation and send APIs |
| Generic interaction handling for fullscreen controls | Gift coordination, animated media, main popup and quantity popup |
| Plugin loader and existing install/enable/restart workflow | Plugin manifest, documentation, automated tests and installable ZIP |

The host must run normally without this plugin. Disabling or removing it takes effect through the existing restart workflow: its composer, emoticon and gift UI disappear, while Bilibili playback, receiving, account login and other plugins keep working. Live hot reload is outside scope.

Do not merge the complete send2 or gifts branches into the host. The cookie-persistence base already supplies the receiving and persistence fixes needed here. Other unrelated send2 fixes are carried separately only if a regression demonstrates that this work requires them, with their own tests and commits.

## Host extension contract

The public API must describe tile controls and credentials without importing a Bilibili composer or gift module. Exact Python names below are proposed API names; the implementation plan may refine them without changing these guarantees.

### Per-tile controls

`PluginContext.register_tile_control(control_id, factory, *, priority=0)` registers a provider owned by that plugin. IDs are unique within the owner; separate plugins may reuse an ID. Registration order, with explicit priority, provides deterministic ordering.

The factory receives a small tile-control context containing the Qt parent, a detached current-room dictionary and an `invalidate_layout()` callback. It returns a control with a QWidget plus `set_room(room)`, `interaction_active()` and `shutdown()` hooks. It declares minimum/preferred width through the control contract rather than patching the tile's layout methods. A plugin can hide its widget for unsupported rooms and request a new layout when visibility or width requirements change.

Required host behavior:

- Attach exactly once to every existing tile after the plugin has loaded successfully, including empty tiles; attach to every subsequently created tile. A factory is not skipped permanently because the tile initially has no supported room.
- Deliver the initial room and every later `Tile.set_room` assignment, including empty rooms, room swaps, restoration and assignments made outside playback-start paths. Supply a copy of the room dictionary; plugins must not modify host state through it.
- Retain the same control instance while a tile is reused or reparented for fullscreen. Changing the room updates context; it must not attach duplicate controls or signal handlers.
- Put controls in the bottom bar's flexible area between the existing status/volume area and the danmaku-viewing/recording/fullscreen controls. Reproduce send2's compact behavior for one composer, extending the width budget to include the gift button.
- Keep the current no-extension layout when no control is applicable. With extensions, compact labels and lower-priority status information yield space before the input becomes unusable; volume access, recording and fullscreen remain reachable as in send2. Multiple providers share the available area deterministically; the host can hide the lowest-priority extension first when their declared minimum widths cannot fit. The first supported composer must remain usable at the tested 200-pixel tile width.
- Isolate exceptions in construction, room updates and interaction queries. Roll back this provider's partially attached controls if registration/loading fails. A failing provider must not stop another provider or the player's controls.
- On tile removal or plugin shutdown, call `shutdown()` once, remove the widget and disconnect host-owned connections. Callbacks from removed controls cannot access a replacement tile. Plugin-wide workers remain the plugin's responsibility.

This is a dedicated control-registration facility, not a generic arbitrary UI patching framework. `bili_live` must not replace private tile methods or attach through `context.window.wall`.

### Account snapshots and notifications

Expose a platform-keyed credential service through `PluginContext`, backed by host-owned adapters. A snapshot contains the platform key, an opaque account generation and a detached credential mapping. Bilibili's adapter provides `SESSDATA`, `bili_jct` and `buvid3` from the cookie-persistence branch. A fake non-Bilibili adapter in tests demonstrates that the public interface is platform-neutral; implementing every existing platform's credential adapter is not required for this feature.

- `context.credentials(platform)` returns the current snapshot, or a documented empty/unavailable result. It never returns a live mutable cookie jar or the application's state dictionary.
- An `account.changed` event contains the platform and account generation, without credentials. Login, logout and replacement of authentication credentials advance the generation. Initial controls receive an initial snapshot without relying on a startup event having already occurred.
- The Bilibili adapter is wired into both existing QR/web login paths through the normal application account flow, logout and startup restoration. It does not create a second login or ask users to copy cookies.
- A narrow `context.update_credentials(platform, changes, expected_generation=...)` operation lets an adapter accept ancillary credentials discovered in a worker. Adapters explicitly allow fields; Bilibili permits `buvid3`, while authentication fields continue to be controlled by login. Unknown/unsupported updates fail clearly. Updates from an old account generation are rejected.
- Publishing a device cookie persists it using the existing host save path and does not change account generation or invalidate the successful request that discovered it. Host notifications distinguish an ancillary refresh from an account change.
- Credential lookup/publication occurs on the GUI thread. Workers receive captured copies and cancellation tokens; they do not call GUI objects or reread changing global authentication halfway through a request.

The plugin owns Bilibili sending/gifting HTTP endpoints and any on-demand device-identity request. It publishes a discovered device cookie back through the conditional update operation. The host owns storage; the plugin must not write credentials into plugin settings, logs or its own account file. Credential encryption migration is outside scope.

### Fullscreen interaction

The host keeps controls visible when any visible extension reports active interaction, including an editor with focus, IME composition or its open popup/quantity editor. The query applies both while the pointer is over video and when it is outside the tile/on another monitor. Existing modal/popup/button protections still apply. Hiding or disabling a control must release the interaction state, so it cannot keep bars visible indefinitely.

The fullscreen implementation calls this generic query; it contains no `tile.composer`, gift or Bilibili references. Application shortcuts must not activate while an extension consumes typing or IME input.

## Plugin structure and compatibility

Create `plugins/bili_live/` in the plugin repository, with `plugin.json`, `plugin.py`, README and separate modules for the sending API, composer/emoticons, gift API, gift coordination, gift media and gift popups. This follows match_sync's existing multi-file packaging convention. Use Python, PySide6, requests and the standard library already present in the host; add no external dependency.

The plugin's `on_load` checks for the required public extension methods before registering anything and reports a clear compatible-host requirement on an older application. The manifest and README document that requirement; do not rely only on the displayed app version or an unenforced manifest field. Existing plugins continue to load through the current API.

The plugin registers one tile-control provider. It does not register a replacement Bilibili playback platform. The unused legacy single `DanmakuSender` registration remains compatible; the new plugin-owned composer does not require the host to call a Bilibili sender.

Reuse host theme/image utilities where they are appropriate, while keeping Bilibili HTTP logic in the plugin. Store only media in a plugin-specific directory under the existing ignored cache directory. Balance, permissions, gift selections and cookies are not persistent plugin cache data.

On `app.closing`, stop scheduling work and invalidate live views. On `on_unload`, close controls/popups, release GIF resources and wait for the plugin's bounded workers. Worker ownership outlives transient widgets, so closing a popup or deleting a tile cannot destroy a running QThread. Shutdown must not introduce a composer-specific wait/import into the host. Plugin callbacks and cleanup are idempotent.

Update the plugin repository README, packaging tests and any release/website catalog code that assumes there are exactly three plugins. Produce an importable `bili_live-<version>.zip` containing one `bili_live/` directory and the repository's required license/notice files. ZIP construction continues to use Git-tracked files. Publishing a release or pushing branches is outside this request.

## Sending and emoticon behavior to preserve

- The inline composer belongs to its tile. Preserve independent drafts, Enter sending, IME-safe composition, protection against player shortcuts and the compact send-button behavior from send2. A room change clears the old room's draft; sending a gift does not clear a text draft.
- Bilibili numeric rooms show the composer; empty and other-platform rooms do not. Existing login is reused. Missing SESSDATA prompts login; missing `bili_jct` explains that re-login is necessary.
- Small emoji insert their text. Supported large emoticon packages send the permitted `emoticon_unique` using `dm_type=1`; locked emotes remain disabled with their reason.
- Preserve package tabs, cover icons with readable fallbacks, lazy construction, background image loading, caching and popup screen clipping. Hidden popups stop scheduling work.
- All requests run in workers with explicit timeouts and captured room/account context. Account changes invalidate permission caches and stale completions; room changes and edits made while a send is pending cannot cause a delayed response to clear a new draft.
- Do not automatically retry a send after a timeout or ambiguous response. Preserve readable server-error feedback, including unsuccessful payloads with `code=0` and a failure message.

## Gifting behavior to implement

This section preserves the prior approved gift design; the feature itself still needs implementation.

### Entry, catalog and animated media

- Composer order is input, emoticon button, gift button, send. Emoticon and gift buttons are 28 by 28 logical pixels; opening their popups is mutually exclusive.
- The gift panel uses the current room and shared login. Anchor above the gift button, fall below when necessary and clip both main and quantity windows to available screen geometry. Follow the existing dark/light theme and remain usable with fullscreen, high DPI and native VLC video.
- Begin around 400 by 340 logical pixels with five columns, reducing columns and scrolling on smaller screens. Show actual GIFs, names and prices; static images are the fallback. One broken image cannot break the list. Play only visible GIFs and pause/release them when hidden or changing categories. Preserve animation bytes and use Qt QMovie rather than converting GIFs into a static pixmap.
- Show remaining battery at the top, refresh/status controls, server-provided room categories and a bag tab. Use room-referenced gift lists and stable server position ordering, merging room overrides over global gift metadata. Unreferenced global gifts are not offered for sending.
- Catalog, wallet and bag have independent loading/error states. Unknown balance is distinct from zero. Wallet failure blocks paid sending while still permitting valid bag operations; it does not prevent catalog browsing.
- Display bag stock and expiry, retaining separate `bag_id` batches. Expired, restricted, unavailable or unknown special flows show why sending is disabled.

### Quantities and submissions

- Respect `count_map`, `diy_count_map`, gift and room limits; remove invalid/duplicate quantities. A gift with only the ordinary single-send option and no custom quantity sends one on click, without an extra confirmation dialog. Multiple options/custom quantities open a quantity popup on hover; clicking the gift card focuses that popup without spending. Select quantity and click its send button to submit.
- Custom counts must be allowed by the server, positive integers and within all limits. Bag custom counts are also limited to the selected batch's stock; stock of one supports one-click sending. Do not combine batches or replace an insufficient bag operation with a paid purchase.
- Use raw integers for price and wallet arithmetic; 100 raw units display as one battery. Preserve fractional battery display and do not add unrelated balances.
- Ordinary battery gifts and eligible free/bag gifts are supported. Special purchase/interactive flows, subscriptions, recharge, SC, sending to linked guests, blind-box result animations and fullscreen effects remain outside scope. Show unsupported entries and their explanations rather than treating them as ordinary purchases.
- Exactly one gift submission may be in flight for an account across all tiles. This does not block text sending or playback. Revalidate credentials, room, permissions, quantity, funds and stock before POST; cancel a prepared operation if its room/account changed before submission.
- After success, show success and invalidate/refetch wallet and bag across all tile panels. Reads issued before that invalidation cannot restore old balances/stock. A failed post-success refresh reports that refresh failure without rewriting the send as a failure.
- Do not retry POSTs automatically, switch endpoint versions on failure, or fall back between paid/bag operations. Timeout, disconnect and unparseable post-submission responses report an unconfirmed result and invalidate possibly stale account data.

### Popup closing and stale work

- Before the first successful send in an opening session, merely moving outside does not close the browsing panel. After success, keep it open while the pointer is inside the main/quantity window; close both when the pointer leaves. If success arrives after the pointer left, close immediately.
- Main panel, quantity popup and their short transition gap form one interaction area. A short close delay (initially 150 ms) may bridge that gap. Quantity editing, buttons and scrollbars must not trigger accidental closing.
- Suppress pointer-driven closing during an in-flight send, including a second send after a previous success; re-evaluate the pointer on completion. Failure before any success does not arm mouse-out closing. Reopening resets this state.
- Esc, outside click, gift-button toggle, room/account change, tile hiding/removal and shutdown close both windows even when a request is in flight. Closing cannot repeat a submission. A hidden view never reopens because a response arrived.
- Capture account, room, data revision and request identity. Old requests and image callbacks cannot overwrite a new context. Shared account coordination and worker lifetime belong to the plugin, not individual popup widgets.

### Endpoint evidence and remaining verification

The previous investigation identified `roomGiftList`, `myWallet`, `gift/bag_list`, revenue `gift/sendGold` and `gift/sendBag`. Room/wallet/bag read shapes were inspected; actual gift submissions were not performed. Verify exact submission fields against maintained public source before coding the request contract. Select one supported endpoint version per operation; resolve the known bag v1/v2 difference through source evidence, never by retrying an uncertain submission.

Use the captured sender UID, resolved real room ID and anchor UID distinctly. Tests must verify form encoding, CSRF fields, selected bag ID, room Referer/Origin, explicit timeout and disabled redirects. A real paid/free gift must not be sent merely to discover whether the endpoint works. Live gift validation requires a separate explicit room/gift/count instruction; otherwise delivery must identify that gap accurately.

## Validation and delivery

Every implementation change includes relevant new/updated tests, passing validation and a Git commit in its own repository. Keep commits separated by responsibility; no push, PR, merge or release is implied.

Host tests must cover existing/new/empty tiles, every room assignment path, swaps/fullscreen reuse, deterministic multiple-provider layout, provider failure isolation/rollback, removal and shutdown, detached credential snapshots, account events and generations, conditional device-cookie persistence, and generic focus behavior both over video and outside the tile. Use a non-Bilibili test provider to prove the interface has no composer dependency. Run affected existing plugin, cookie, room-switch, layout, fullscreen, account and repository checks.

Plugin tests port the send2 API/composer/emoticon cases to the packaged plugin, retaining local HTTP request checks and real Qt widget interaction. Add gift tests for normalization and server limits, precise money, null bags/separate batches, permissions, HTTP forms, no retry, account-wide concurrency, pre-submit cancellation, stale reads, success/refresh distinction, raw GIFs and bounded loading, quantity interactions, the complete popup-closing rules and shutdown without running-thread destruction.

Integration tests install the actual ZIP into a temporary plugin directory, load it in the modified real host, exercise initial/new tiles and account/room changes, and verify that uninstall/disable plus restart restores the no-plugin UI. Re-run packaging tests for all existing plugins. Check the combined toolbar at 900, 360 and 200 logical pixels, dark/light themes, fullscreen, high DPI and native video hit-testing. A source-only import of individual modules is insufficient evidence of packaging success.

Automated checks use fake credentials and temporary config/cache roots with `DDM_NO_SAVE=1`. No real account values are printed or added to fixtures. Report real-service read checks separately from simulated send tests and from visible native-window checks. A limitation in one category must not be presented as validation in another.

For this design-only commit, update the documentation index/inventory and extend the existing document-link validation to include design/plan documents; run the repository documentation/file checks and `git diff --check`.

## Author's decisions and builder discretion

Author's decisions: retain built-in Bilibili playback/receiving; use one optional plugin for sending and gifting; keep login/storage in the host; prefer a small public control/credential/focus API over private method wrapping; use the existing Python/Qt/request stack; preserve the current restart-based plugin workflow; keep the legacy sender interface compatible; use the branch names above.

The builder can settle exact module/class names, signal signatures, cache bounds, numeric layout budgets, loader scheduling and endpoint parameters from verified source, while meeting the behavior and tests above. Do not introduce a second login, move gift-specific state into the host, redesign the familiar UI or drop gift behavior to make extraction easier.

After approval, write one coordinated implementation plan covering both repositories, then implement the host hooks, port sending/emoticons, implement gifts, and finish with packaged-host integration and an independent review. This document is not evidence that any of those features have been implemented.
