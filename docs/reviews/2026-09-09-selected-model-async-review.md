# Selected-model async integration — independent review

September9,2026,23:16 UTC. Claude read-only review83041 terminated with exit0
after311s. Exact runtime head9e19a7b86ea2bfeec7e91587c1d12e78bbc0af96;
51 focused cases independently reproduced. No blocking findings. No app
activation or complete-selector acceptance implied.

Optional diagnostic/export nits are deferred; they do not change authority or
execution and do not justify a repeat review round. The pre-existing shared
admission's same-thread limitation remains a separate integration constraint.
The container oracle is now being attempted through an existing Ubuntu Docker
engine; the earlier Desktop failure remains unrepaired but no reset is needed.
Live public pricing-shape mismatch is independently recorded in the main goal
concern; it is outside this async-only diff and remains an activation gate.

## Verbatim reviewer result

Verification is complete and the focused test file passed. Writing up the structured review now.

**Scope reviewed:** diff 439bd4c2..9e19a7b8 at head 9e19a7b8, four canonical source files, the two test files, and the proof document. Tree confirmed clean. Runtime mirrors ignored. No subagents, edits, or commits.

**Test run (cache disabled, bytecode writes disabled):**

```
python -m pytest -q -p no:cacheprovider tests/test_selected_model_authority.py --tb=short -rs
51 passed in 4.77s
```

The full suite and the 16-file group were not run.

## AGREE

- **Helper extraction preserves legacy gates.** `_served_request_agent` in `tinyassets/provider_assignment.py` keeps the universe/binding-id precheck, the exact two-tuple accepted-source set, the converse/writer restriction, and the status/owner/revision triple. The only change is that a missing binding and a stale binding now share one message. Both were already wrapped into the same held error.
- **Async preflight validates a current accepted member.** `_selected_chain` runs `_current_selected_member_authority` under a short shared admission plus a read transaction. That resolver requires a manifest-digested ready assignment, the agent's provider_ref match, member presence, binding validation, and live grant custody. An unaccepted ModelRef or a non-ModelRef fails before any GET, and the new test asserts the reader saw no requests.
- **SQL and thread-owned admission are released before the worker.** The store context and the shared admission both exit before the await in `authorize_served_provider_call_async`. The refresh runs via to_thread and takes no assignment admission, since discovery_snapshot has no reference to it. Admission enter and exit both happen on the loop thread, which matches the thread-identity ownership in `ProviderAssignmentAdmission.shared`.
- **Final validator rechecks everything.** The private `_authorize_served_provider_call` re-runs the request carrier check, re-derives the agent, re-resolves the chain and compares it to the preflight chain, calls the freshness recheck, re-reads the binding, then resolves the chain a third time inside BEGIN and compares again. The carrier validator is a pure read of the registry record, so calling it twice has no side effect.
- **Callers supply only ModelRef.** The router passes the context ModelRef. The prepared tuple travels only through a private kwarg on a private function that the public sync wrapper never forwards. The prepared selected-model facts are trusted only after chain equality and freshness pass, so this is not a new token or provenance scheme.
- **Router behaviour retained.** The async branch only replaces the selected-call fence. The config selection is still overwritten from the authority at router.py line 625, and the slot-bound prelaunch recheck via the before-launch hook is untouched.
- **Cancellation is safe.** A cancel during discovery raises CancelledError, which is a BaseException and bypasses the wrapping except clause. Admission is not held at that point. The shielded per-loop task keeps running, the second caller reuses it, and the done callback clears the map. A cancel during the routed call is thrown into both generators at their yield points, so the sync cleanup and admission exit still run.
- **Legacy sync path preserved.** The public sync entrypoint keeps its signature and its in-fence discovery IO. The differential baseline in tests is untouched.
- **Freshness now includes the catalogue GET.** Moving the observed_at stamp before the read makes the post-read window check and the launch-time recheck both stricter. The new test discriminates the old and new order.

## DISAGREE_EVIDENCE

None.

## DISAGREE_CONCERN (optional hardening, not blocking)

- **Preflight admission failure is mislabelled.** The shared acquisition in the async preflight sits inside the broad except clause, so a non-reentrant RuntimeError becomes the "Connect your provider" held error. The sync path and the final fence surface it as RuntimeError. Consider acquiring the shared fence outside the try, or re-raising RuntimeError. This only affects diagnostics of an already-existing same-thread reentrancy state.
- **Export nit.** The async entrypoint is not listed in the module's public export list. The router imports it by name, so this is cosmetic.

## Explicitly unfinished gates (not claims of this patch)

Full HTTP agent tools, inference offloading, safe continuation, policy persistence, the model picker, native CLI, local dynamic selection, public activation, and the Docker oracle. The same-thread non-reentrancy of shared admission and synchronous HTTP inference are pre-existing and unchanged.

VERDICT: APPROVE


