---
severity: P1
title: Cross-process provider polling can exhaust nested admission reserve
filed: 2026-09-30
summary: In-process blocking slot transfer does not cover a resident CLI polling a queued child through engine-MCP; a finite reserve cannot guarantee completion of that chain.
---

Remaining gap from PR #4136's nested-provider review. The former broad concern
is replaced by this explicit process-boundary finding; the draft remains on hold.
The separate account-limits concern is unchanged.

The limit-2 reproduction held an outer slot and an agent-child slot, then
timed out waiting for the grandchild after a test-only 150 ms. Exclusive
in-process ownership now lets the blocking grandchild use the child's slot.
Router, compiler worker, sibling accounting, cancellation, and return paths
have regression tests in `tests/test_provider_slot_transfer.py`.

That does **not** establish completion of the live CLI topology. The router
holds admission for `provider.complete`; CLI tools cross engine-MCP/HTTP, and
`universe_server.run_graph` queues work and returns. It does not synchronously
suspend its caller. Background workers deliberately clear inherited slot
ownership. A model can nevertheless keep its provider invocation alive while
polling that child's status, and deeper children can exhaust the reserve.

The process-local handle is never serialized. The reserve is retained for
children without a transferable parent; it buys first-layer headroom, not an
arbitrary-depth progress guarantee. A blocked CLI also retains resident memory,
so simply letting its subprocess child bypass admission would weaken the host
memory floor.

Cross-family Claude review: DISAGREE_EVIDENCE on calling the live deadlock
resolved; accepted. Its observation that current production child launches
have no held same-process parent is also accepted: transfer supports that
contract, but tests with an injected nested provider are not live CLI proof.
The review agreed on exclusive ownership, return, process checks and thread
propagation. Caller timeouts inside a loan intentionally drain the borrower
before resuming the parent, so a wedged borrower can still prevent return.

Handoff: design and prove a process-aware suspension/resumption protocol, or
a durable continuation that retires the parent's provider before the child
needs admission. Preserve WAIT and the resident-process memory ceiling; do
not restore a refusal deadline or add a recursion cap. No deployment or
live-user completion claim is justified by the in-process fix.
