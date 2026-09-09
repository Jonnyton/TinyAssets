# Next implementation contract: shared capacity follows real execution

This is the next boundary within the existing full resource-policy goal, not a
new completion criterion or a claim of implemented capacity. The shipped
workspace-start and engine-share removals remain intact. The five-gap app retest
remains an independent required acceptance gate in `goal-completion-contract.md`.

## Evidence and decision

`docs/reviews/2026-09-08-provider-capacity-next-boundary.md` records two independent
Claude design rounds and two local executable findings: independent processes
can each take a limit=1 slot, and real provider-adapter cancellation can return
its slot while a synthetic descendant still answers. Therefore the next code
must replace both process-local exclusion and early lifetime release. Merely
making `_live` cross-process would preserve a known false-capacity result.

The existing slot call sites are class-neutral, but their resource description
is not: they bracket CLI processes and remote/local-server HTTP calls alike.
Capacity must describe the actual local resource held. It cannot promise remote
server-side job cancellation, measure provider tokens as process seconds, or
grant additional upstream spending authority.

## Implementation requirements

1. **One shared exclusion domain.** Resolve the trusted daemon state root through
   `storage.data_dir`, shared by the daemon and its engine children. Never derive
   a namespace from the working directory, provider name, graph ID or user input.
   Verify forwarding at persistent HTTP and stdio engine entry points. Explicitly
   separate independent deployment roots from a claim of machine-wide capacity;
   whole-host protection cannot be inferred from one directory namespace.

2. **Stable slot identity and count-based admission.** Serialize acquisition under
   a short-held kernel mutex, count all occupied slot identities including indices
   above a lowered limit, and hold one available slot only when that count fits
   the existing effective limit. Never unlink a reusable lock identity. Preserve
   the existing nested reserve, async cancellation-safe waiting and actionable
   busy refusal. Lock I/O failure is not evidence that capacity is free.

3. **Execution owns release.** An acquired permit must stay held until the local
   execution owner confirms that its admitted process tree has ended. Caller
   cancellation, a cancelled await, parent death and a bounded reap timeout do
   not establish that fact. Passing descriptors to the first CLI is not a
   substitute: arbitrary descendants can close or omit them. The cleanup owner
   must be independent of provider protocol/version and must never be writable
   by a workflow or widen that workflow's filesystem/credential authority.

4. **Use real OS containment where available, prove each backend.** The existing
   Linux bubblewrap lifetime/namespace path is a candidate to reuse, not a proof
   for currently plain launches. Windows requires an execution-tree owner such
   as a kill-on-close Job Object, including race-free attachment before user code
   can spawn descendants. Resolve supported macOS/non-bubblewrap launch behavior
   before a blanket release claim. A new process supervisor is not automatically
   justified: first show why existing execution owners cannot carry the permit.
   Do not ship platform-specific expected failures as completed lifecycle support.

5. **Separate resource identity from provider identity.** Attach the capacity
   lifetime to the actual launch or connection/dispatch operation. A future
   provider using the same execution method must receive the same treatment
   without a new vendor-name branch. Existing caller authority and invocation /
   token / cost reservations remain independently enforced. Do not simply
   exempt HTTP providers from the current guard without bounding their real
   dispatch resource and checking settlement coverage.

6. **Evidence remains truthful.** Shared live occupancy must read the same
   exclusion authority that admission uses. Historical local duration, admitted,
   refused and peak samples remain explicitly process-local unless a justified
   existing store provides wider truth. No new usage ledger, schema, pricing,
   quota number or data-custody decision is authorized by this design.

## Finite implementation proof

| Case | Required observation |
|---|---|
| Two real processes, one shared capacity root, limit 1 | One holder; second waits/refuses; receipt/stat reads do not allocate. |
| Parent cancellation and parent death | A real child and grandchild either still hold capacity or are observed exited before it returns. |
| Descendant closes inherited descriptors / changes session | The execution owner still accounts for or ends it; no early free-slot report. |
| Nested work and saturated outer work | Existing progress reserve works across process boundaries without authorizing an unbound call. |
| Limit lowered with high-index holders | All old holders count while draining; no low-index oversubscription. |
| Concurrent acquisitions / status / release / lock failure | One authority; no inode splitting, orphan waiter, or failure-as-free result. |
| Different providers, same execution method | Identical capacity treatment; no vendor/model-specific admission branch. |
| Production execution entry points | Real router calls and engine children use the shared boundary; a primitive-only test is insufficient. |

Use bounded harmless local fixtures for lifecycle tests, plus Linux CI/oracle
with actual containment and unchanged baseline comparisons. Required independent
shape/exact-head review and authenticated deployment gates still apply. Final
rendered app acceptance is additional evidence, not replaced by these tests.

## Next action and authority boundary

Implement and test the reusable execution-lifetime owner together with the
shared permit, rather than landing the counter first with a declared orphan gap.
The remaining design question is the concrete portable OS backend, not a user
choice of semaphore or a request for new quota numbers. If that implementation
actually requires a new storage authority, OS privilege, public surface or PLAN
change, identify that exact conflict before implementation. Do not infer such
permission from this internal design. The retained-space overhead decision in
`consolidation-decision.md` remains undecided and is not changed here.
