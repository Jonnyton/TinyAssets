## Proposal

- [x] Inspect repository principles, current related specs, and delivery WIP.
- [x] Define the experience composition contract and acceptance scenarios.

## Before implementation

- [x] Settle the renderer isolation contract, the bundle store and its byte bounds
      against the existing handlers (design.md, "Implementation slice").
- [x] Record cross-family shape review and resolve its findings (Codex
      gpt-6-astra, 2026-09-26, ADAPT: 3xP1 + 2xP2, all fixed; design.md).

## Implementation slice: executable UI bundles

- [x] Serve a fixed, content-free bootstrap document from `/mcp/app/ui-frame`
      under a header CSP granting `sandbox allow-scripts` and denying its network.
- [x] Add `frame-src 'self'` to the app CSP and keep `script-src` nonce-only.
- [x] Read and bound the `tinyassets.app-ui.v1` component; unsupported is named,
      never guessed, and never sanitized.
- [x] Host the bundle in the isolated frame and hand it a bridge client.
- [x] Implement the parent-side bridge: frozen allowlist, frame-source check,
      viewer-pinned home, picked-field replies.
- [x] Add the on-the-fly switcher and persist the selection in the existing
      `app_experience` binding configuration with read-back and CAS.
- [x] Carry a bundle through the existing publish/remix path so a remix installs
      into the remixer's own binding.
- [x] Prove isolation, allowlist, cross-user refusal and remix identity in tests;
      mutation-check the isolation boundary and the allowlist.

## Remaining before this is user-ready

- [ ] **First run through the app has no way to create the app experience.**
      Installing a bundle needs an `app_experience` binding, and a binding needs
      *some* existing definition — `_require_definition`
      (`tinyassets/custom_agents.py`) checks existence only, not authorship, so a
      universe's own agent CAN bind against any public definition and keep the
      bundle in the private configuration. But the app's own path cannot: App
      design's Apply requires inspecting a supported *public layout* design first,
      so a user with no layout installed sees `install` refuse with "Install an app
      experience first". The agent route works today; the app route needs either a
      "create my app experience" action or a content-free shell definition to bind
      against. A shell publishes a public row, so it is public surface and belongs
      in its own change, not folded in after a review round.
- [ ] Rendered real-browser proof through `ui-test`; harness evidence is not it.
- [ ] Sync verified behavior into canonical specs and archive when it lands.
- [ ] Deferred and not claimed: device capability negotiation, notification
      routing, voice handoff, multi-file/binary bundles, per-universe file store.
