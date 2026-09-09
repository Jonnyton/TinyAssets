## 1. Visible status behavior

- [x] 1.1 Separate accessible conversation and Voice status regions so Voice renders never overwrite canonical progress.
- [x] 1.2 Make Voice stop/failure and later turn settlement report the observed pending-reply outcome without claiming cancellation.

## 2. Voice state context

- [x] 2.1 Add optional default-false `voice_active` input to founder-only `converse` without changing its authority checks.
- [x] 2.2 Relay bounded invocation-time Voice context to the writer while preserving canonical message storage and learning input.
- [x] 2.3 Have every shared-app conversation invocation pass Voice state derived from the actual client state.

## 3. Verification and delivery

- [x] 3.1 Add transition, schema, prompt-boundary, persistence, and packaged-runtime regression coverage; run focused tests, lint, strict OpenSpec, and invariants.
- [x] 3.2 Complete the initial opposite-family review, address its finding, sync specifications, and archive this change for release.
