## Proposal

- [x] Inspect repository principles, current related specs, and delivery WIP.
- [x] Define the experience composition contract and acceptance scenarios.

## Before implementation

- [x] Settle the renderer isolation contract, the bundle store and its byte bounds
      against the existing handlers (design.md, "Implementation slice").
- [ ] Record cross-family shape review and resolve its findings.

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

- [ ] Rendered real-browser proof through `ui-test`; harness evidence is not it.
- [ ] Sync verified behavior into canonical specs and archive when it lands.
- [ ] Deferred and not claimed: device capability negotiation, notification
      routing, voice handoff, multi-file/binary bundles, per-universe file store.
