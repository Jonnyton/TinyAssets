---
severity: P1
title: Cross-process provider polling needs durable continuation
filed: 2026-09-30
summary: Provider admission still refuses after its production deadline when resident parents exhaust nested capacity; retire waiting parent processes and resume durable continuations before allowing indefinite admission.
---

Follow-up to PR #4136. Provider admission retains origin/main's configurable
20-second wait deadline and retryable ProviderBusy refusal. A nested chain
across processes can still exhaust the reserve and be refused after that
deadline. This PR adds neither a new indefinite hang nor a new admission refusal
policy. Same-process exclusive slot transfer remains implemented and tested.

The router holds admission around provider.complete. The Claude provider spawns
the CLI before reading its stream and tears it down only on stream exit.
Engine-MCP run_graph queues a child and returns a receipt; a model may keep its
parent CLI alive while polling the child. Background workers deliberately clear
inherited ownership. Process-local transfer handles cannot cross this boundary,
and a finite nested reserve gives headroom, not arbitrary-depth progress.

Evidence retained from the real-process probe: three Python child processes
blocked on stdin, each retaining a 16 MiB allocation. With limit 2, two counted
slots held two resident children and the grandchild could not enter. Returning
only the waiting parent's counter admitted the third: **2 slots, 3 resident
processes**. All children were reaped and the counter returned to zero. This
proves counter-only suspension violates the resident-process bound; it is not
an end-to-end live CLI regression or proof that cross-process waiting is fixed.

The lead selected durable continuation as a separate change: retire the waiting
parent CLI/provider process, persist its continuation, and resume it through
Claude/Codex session resume or an equivalent when its child finishes. Waiting
must hold neither resident provider memory nor a provider slot. Only after that
lifecycle is implemented and proven can provider admission wait forever.
FIFO fairness or returning a counter while keeping the CLI resident is not a fix.

The prior cross-family review's DISAGREE_EVIDENCE on calling live polling resolved
remains accepted. Same-process ownership, exclusive lending, thread propagation,
and return have regression coverage in tests/test_provider_slot_transfer.py.
A wedged in-process borrower still delays its parent's unwind until it settles.
No deployment or live-user completion is claimed here.
