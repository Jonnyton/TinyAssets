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

## Repair acceptance

Freshness: 2026-08-02 on Windows/Python 3.14, repair heads `655f9331` and
`578bcb4b`. Same-provider independent review was explicitly approved by the
host after the normal opposite-provider path was unavailable.

The four rejection findings are cleared:

1. Admission authority is backed by an immutable, server-HMAC-sealed witness
   written atomically with the binding, command, root, and event. A
   self-consistent raw-row forgery cannot validate or mint a carrier.
   Independent scoped review: approve.
2. Draft capture and admission bind to a middleware-minted request nonce;
   reuse by the same owner in a later request fails without writes.
   Independent scoped review: approve.
3. Expired pre-launch work renews the same claim/reservation/continuation under
   generation fences, while launch-started uncertainty remains held. The
   8-way recovery race converges on one generation-2 identity and one provider
   call. Independent scoped review: approve.
4. Useful-progress health validates the continuation against the canonical
   command/event and complete provider binding, receipt, claim, reservation,
   typed-input, subject, lease, and budget lineage. The final exact-head review
   of `578bcb4b` approved after rerunning 9/9 health tests.

Fresh local evidence at `578bcb4b`: 58 directly affected tests and 517 related
authority/runtime/Branch tests passed; targeted Ruff check/format passed;
strict OpenSpec validation passed; plugin build/import probe passed; all 325
canonical/plugin Python mirrors were byte-identical; `git diff --check` passed.
Two earlier combined review invocations timed out and are recorded only as
errors, never as approval evidence. The four bounded scoped reviews are the
acceptance evidence.
