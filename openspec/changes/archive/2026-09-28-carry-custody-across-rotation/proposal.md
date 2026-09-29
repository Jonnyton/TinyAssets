## Why

A platform refresh of a deposited sign-in (same owner, same account, new tokens) renews the accepted source today. Renewal republishes everything: the agent binding revision, the assignment generation, every member's work binding, and the custody generation and reference digest. Every receipt already in flight names the old values, so it refuses its next launch. The founder's always-on background agent wakes about once a minute, so the 12-hour refresh cycle would strand a live run each time. A background attempt voided between nodes is not retried; it is stranded (`docs/concerns/2026-09-28-a-renewal-voids-other-running-receipts.md`).

Lead decision (2026-09-28): a renewal of the SAME owner's SAME accepted source must not void receipts in flight. A different account or owner still must.

## What Changes

- The custody reference names the owner's consent, not the bytes. It is `(reference_id, owner, universe, service, generation)` at schema version 2. The byte pin (`record_digest`) stays on the custody row and is still verified at every custody read and every launch snapshot.
- A rotation that the platform performed or adopted, and that keeps the credential's account identity, updates only the custody row's byte pin, by compare-and-swap. The generation, the reference digest and every pin downstream (bindings, assignment, manifest, receipts, carriers) stay unchanged. Nothing is republished and nothing in flight is voided.
- An owner deposit, a change of account identity, or any row still at schema version 1 renews exactly as today. Existing rows move to version 2 at their next renewal.
