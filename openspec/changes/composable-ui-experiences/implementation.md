# Implementation slice: editable inert experience preview

Date: 2026-09-14. [Follow-up proposal approval](https://github.com/Jonnyton/TinyAssets/pull/3842#issuecomment-5672004948) names reviewed head `5e8a5d0120566b4c49b56e6a81388e35bb1a818d`.
The first implementation review approved the inert slice at
`c3a7d2a137dbd876dd716bd7fc59db1596b43920`, with rendered evidence still requested.
The posted proposal and implementation reviews are retained in [review-evidence.md](review-evidence.md).

## Built

Open `examples/experiences/preview.html` in a browser. Edit the native composition,
switch desktop board/phone list, inspect a fixture action, and restore the example.
The recovery controls stay outside the rendered composition. Both layouts consume
the same fixture data and symbolic action binding. Source remains editable; unknown
component kinds survive inspection and are shown as unsupported. User text reaches
textContent, never executable HTML. The fixture's CSP denies network connections.

`tinyassets/onboarding/experience.js` is a dependency-free interpreter for these
declarative views and a prepared-intent helper. This file belongs beside the app
surface; it is not automatically loaded into the authenticated app. The preview
does not implement a governed renderer for arbitrary executable source, native
import staging, private storage, or authenticated user bindings.

Only `run_branch` is understood by the initial **preview** action adapter.
Other operation names are preserved in source and explicitly refused when prepared.
This is adapter capability, not a permanent platform action taxonomy.
A prepared intent freezes the exact source, action input, private target reference
and revision. Revalidation refuses changed source, changed input and retargeting.
It returns no execution authority and dispatches nothing. When attached to a live
handler, that handler must independently derive the caller/universe and check the
current target and authority. Client-side comparison is not a security boundary.

Conversation delivery has no fabricated action identity. The recovery helper always
disables automatic retry, directing conversation ambiguity to canonical history
and typed-action ambiguity to its outcome. Existing app `sendTurn`/MCP conversation
transport remains a separate integration seam; this new helper does not assert
that an ambiguous relayed message failed to execute.

## Evidence

Run `node --test tests/test_experience_preview.cjs`.
Cases cover source preservation, immutable prepared intents, changed revision and
target rejection, changed inputs, private-content refusal, unsupported conversation
operations, safe recovery and desktop/phone interpretation using literal text sinks.

The DOM double verifies interpreter behavior; it is explicitly **not** a rendered
browser or phone acceptance result. The HTML file is the manual interaction
fixture. No browser automation or live connector trace was available in this build
workspace. Required rendered acceptance, ordinary user binding, real action-handler
integration, per-store cursors and S-1 retained-data adoption remain open.

The Linux workspace lacks pytest, Ruff, the OpenSpec CLI and full runtime
dependencies. Node tests, JavaScript syntax checks and staged diff checks are local
evidence. CI remains pending; the retained review applies to its named head.
The plugin mirror is regenerated using the documented minimal-environment
`--skip-probe` option; its import probe remains pending.

## Android and Play evidence boundary

The inspected source records `mobile/android-release.json` as package
`io.tinyassets.app`, version code 4 / version 1.0.3, min SDK 24 and target/compile
SDK 36. `docs/ops/google-play-launch.md` §1b calls this a **candidate**, and its
dated 2026-09-03 account evidence says release 2 (1.0.1) was active on the private
internal track. These are repository records, not a fresh Play Console read.
`docs/audits/2026-09-08-android-play-v4-claude-review.md` records approval and APK
build evidence for the notification/version delta. None proves this new experience
on an Android device, actual phone push, earbud routing, voice capture, handoff or
production-store availability. Each retains its own device/delivery acceptance.

## Implementation review follow-up (2026-09-14 UTC)

Recovery now requires explicit `kind: "action"` and a nonblank string action ID
before recommending action-outcome inspection. Missing/unknown kinds, missing or
malformed IDs and conversations go to canonical history; automatic retry remains
disabled. Malformed fixtures receive a value-free validation error before the
previous rendered view is replaced. Regression tests cover these boundaries.

The preview's credential-shaped-text regex is still narrower than native Python
validation. This is an inert preview, not a shared import authorization or secret
scrubbing boundary. Before integrating a shared import path, route validation
through the native contract and use common cross-language conformance vectors;
do not claim parity from the preview heuristic.

### Browser evidence blocked

Fresh workspace probe `e65d65b63a764186` found no `chromium`,
`chromium-browser`, `google-chrome` or `firefox` on PATH, and no resolvable
Node `playwright`, `puppeteer` or `@playwright/test` package. This session exposes
no browser-control tool; workspace dependency provisioning is unavailable.
No screenshot, console capture or phone render is claimed.

To close the review ask, capture `examples/experiences/preview.html` in a real
browser at 1280x900 and 390x844. Record the browser version, exact tested commit,
URL/scheme and console errors. Check initial board rendering, switch to Phone list,
edit the composition and preview it, inspect an inert action, and restore the
example. Capture both widths and the action status. In particular, test the
advertised `file://` opening path with its CSP unchanged; if the relative script
is blocked, fix that loading path and repeat rather than claiming a successful
HTTP render also proves direct-file loading. Preserve the captures with this change.
These checks prove the local example only, not native-device or live-user adoption.
