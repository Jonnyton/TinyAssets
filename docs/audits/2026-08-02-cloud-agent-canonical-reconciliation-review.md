# Cloud agent canonical reconciliation review

Freshness: 2026-08-02, exact reviewed head `9201bb4a4915b8d7b403e605c03ae6075b470dbd`, independent Codex `gpt-5.6-sol` review.

## Verdict: reject

1. Self-consistent raw command/root/event rows referencing a legitimate active provider binding could mint a receipt, claim, reservation, and valid provider carrier. `authorizing_grant_generation` was unconditional and the admission witness was an unkeyed reproducible digest. Required: a real canonical admission-witness record with server seal, identity, generation, and transactional revalidation on every authority transition.
2. A live provider-binding draft was scoped only to service instance and owner. Ending one request and starting another for the same owner still admitted the old draft. Required: an unforgeable request-boundary nonce invalidated on middleware teardown.
3. Restart 301 seconds after a pre-launch reservation dead-ended because the expired claim remained `STALE` and could not be taken over. Required: fenced claim renewal/takeover or conclusive pre-launch cancellation, including concurrent recovery proof.
4. Useful-progress health trusted a continuation after checking only command and invocation linkage. Required: exact provider binding, receipt, claim, and reservation lineage validation before recognizing continuation progress.

Confirmed positives: canonical #2155/#2160 command/root/event shapes were preserved; duplicate classes/tables were removed; admission wrote provider binding, command, root, and admitted event under one `BEGIN IMMEDIATE`; canonical/plugin mirrors matched; the then-focused 123 tests passed.

## Repair gate

The rejection is not cleared by implementation alone. The repair must reproduce all four failures as tests, pass the broader authority/runtime suite, and receive a new exact-head independent verdict.
