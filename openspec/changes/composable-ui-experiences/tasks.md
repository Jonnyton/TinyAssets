## Proposal

- [x] Define the composition contract and its acceptance scenarios against current
      principles and related specs; settle the renderer isolation contract, the
      bundle store and its byte bounds against the existing handlers; record the
      cross-family review with its findings resolved (Codex gpt-6-astra,
      2026-09-26, ADAPT: 3xP1 + 2xP2, all fixed — design.md).

## Implementation slice: executable UI bundles

- [x] Isolate the renderer: a fixed, content-free bootstrap at `/mcp/app/ui-frame`
      under a header CSP granting `sandbox allow-scripts` with no same-origin and
      no network of its own, plus `frame-src 'self'` on the app page with
      `script-src` still nonce-only. Egress CSP cannot express (WebRTC, DNS
      prefetch) is removed from the realm rather than policed.
- [x] Read and bound the `tinyassets.app-ui.v1` component — unsupported is named,
      never guessed, never sanitized, sizes in the bytes the server counts — and
      host it in that frame, delivered verbatim.
- [x] Implement the parent-side bridge: frozen allowlist refusing by name,
      frame-source check, viewer-pinned home, picked-field replies, replies fenced
      to the frame that asked, and the grant ended on any identity or home change.
- [x] Add the on-the-fly switcher and persist it in the existing `app_experience`
      binding configuration through ONE read-back-and-CAS write path shared with
      the layout editor, fed by one binding read.
- [x] Get a bundle into a universe two ways: the existing publish/remix path, so a
      remix installs into the remixer's own binding and runs as the remixer; and a
      first run from nothing, where a binding's definition reference is optional and
      an owner-scoped, idempotent bootstrap creates the private row with nothing
      published and never overwrites what it finds.
- [x] Name the primitive where an agent reaches for it: the `interfaces` handbook
      chapter, in the resident index, paid for out of the capped resident set, with
      its promised calls checked against the bridge's real allowlist.
- [x] Prove it: isolation, allowlist, cross-user refusal, remix identity,
      discoverability and the bootstrap, with the isolation boundary, the bridge
      allowlist and the bootstrap's data-loss guards mutation-scored (39/39 red, 2
      decoys green).

## Remaining

- [ ] Rendered real-browser proof through `ui-test` on both accounts, plus the
      deployed-sha assertion. Harness evidence is neither.
- [ ] Sync verified behavior into canonical specs and archive, same lane as landing.
- [ ] Per-message agent addressing — filed with its scope, including that the fix
      must move the execution-time selection check and not only reservation:
      `docs/concerns/2026-09-26-a-turn-reaches-only-the-one-selected-agent.md`.
- [ ] Deferred and not claimed: device capability negotiation, notification
      routing, voice handoff, multi-file/binary bundles, per-universe file store.
