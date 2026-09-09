## 1. Contract and relay

- [x] 1.1 Replace the public `converse` `voice_active` parameter with the closed `input_method` turn-provenance field and relay it unchanged.
- [x] 1.2 Replace Voice-session prompt context with a plainly labeled current-turn input-method fact while preserving message, learning, and authority boundaries.

## 2. Shared app

- [x] 2.1 Send `typed` from typed founder input, `spoken` from browser-speech and realtime-Voice turns, and `app_action` from founder-selected controls; remove every app use of `voice_active`.
- [x] 2.2 Preserve input method through queued and retried sends, using `unknown` only for restored records that contain no provenance.

## 3. Verification and delivery

- [x] 3.1 Add focused schema, relay, prompt-context, and browser-harness coverage, including a typed turn while Voice is active and rejection of `voice_active`.
- [x] 3.2 Rebuild the packaged runtime mirror and pass focused tests, lint, invariants, and strict OpenSpec validation.
- [x] 3.3 Obtain independent opposite-family review and resolve blocking findings.
- [x] 3.4 Sync the reviewed delta specs and archive the completed change before landing.
- [ ] 3.5 Merge through a reviewed PR, deploy the exact revision, and verify typed and spoken provenance through the live app.
