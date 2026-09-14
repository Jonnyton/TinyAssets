# Independent launch-accounting implementation review

September 9, 2026. Claude, exact clean head d38d150a0f921d7516407ad77173eaf9825fbc1c. Terminal exit 0 after 186 seconds. Scope: launch accounting, not candidate traversal or completed model selection.

Review complete. Everything I needed is in hand.

**Verified at exact head d38d150a** on a clean worktree. `tests/test_served_launch_accounting.py` ran with cache writing disabled: 4 passed. Canonical and runtime-mirror copies of both source files are byte-identical at head. The broader pass counts in the proof doc were not re-run here, per the constraint.

**AGREE — server-issued identity and locking.** `seal_provider_request_launch_allowance` (`tinyassets/auth/middleware.py:322`) validates through `_active_provider_request`, which checks exact type, issuer pid, claimed state, identity token, and that the weakref resolves to the very same object, all under the registry lock. It then re-checks record, state, and identity token under the lock before mutating. That is the same discipline `consume_provider_request_invocation` already uses. Revoked or forged capabilities raise PermissionError, covered by `test_seal_requires_a_live_server_issued_request`.

**AGREE — no late seal or inflation.** A different value against a sealed record is refused, sealing after any unsealed launch is refused, and an idempotent re-seal returns the sealed value without touching `invocations` (`middleware.py:344-352`). Consumption prefers the sealed value over the caller's proposed limit (`middleware.py:374-377`). Both seal and consume serialize on one lock, so the concurrent-seal and concurrent-consume tests are meaningful, not lucky.

**AGREE — consumption sits after budget and slot admission.** In `_call_routed`, the order is now reserve budget, acquire the provider slot, run `before_provider_launch`, consume the invocation, set `provider_started = True`, then `provider.complete` (`tinyassets/providers/router.py:921-966`). There is no await between the consume and the started flag, so no cancellation window there.

**AGREE — reserved budget is cleaned up on every pre-launch failure path.**
- Budget refusal: reserve raises before assignment, so there is nothing to release.
- Slot refusal: the `_ProviderBusy` branch releases, unchanged.
- Pre-launch hook refusal and invocation refusal: the BaseException branch releases because `provider_started` is false (`router.py:1001-1004`).
- The outer classifier still re-raises `ProviderAuthorityHeldError` without cooldown or fallback, so the refusal reaches the caller as before.
The parametrized test asserts zero invocations, zero provider calls, and a zero-spend released row for the slot and pre-launch cases.

**AGREE — post-launch settlement is unchanged.** Once started, only `ProviderUnavailableError` releases; every other error, including cancellation, abandons the reservation conservatively, and carrier settlement is untouched. Cancellation during slot acquire now releases instead of abandons, which is correct because nothing launched.

**AGREE — legacy and background nonregression.** `_SERVED_REQUEST_MAX_INVOCATIONS` stays at 2 (`tinyassets/provider_assignment.py:29`) and an unsealed record falls through to the caller's limit. Background authorities carry no request capability, so the consume is skipped exactly as before. The seal function is not referenced anywhere outside middleware, tests, and docs.

**DISAGREE_CONCERN — exhausted requests now spend runaway-window slots.** Previously a third legacy call failed at the consume before any reservation existed. Now it reserves a row, takes a provider slot, runs the pre-launch hook, and only then fails. The released row is settled as zero-spend 'succeeded' (`provider_assignment.py:790-796`) and the runaway guard counts all rows in its window (`provider_assignment.py:561-563`). So a caller that keeps calling the router after exhaustion within one request charges the binding's rolling runaway window once per refused call. The proof doc names this consequence and the shape review accepted reserve-first ordering. It is bounded by request lifetime and the window ages out, so it is not a pre-live blocker, but it is the one real behavioral cost of the reorder.

**Minor notes, not blockers.**
- The pre-launch hook refusal now releases rather than abandons the reservation. That is correct and the test asserts it, but it is a behavior change beyond the strict title.
- Seal rejects int subclasses with an exact type check while consume accepts them. Cosmetic inconsistency.
- The six-launch test uses one recording provider and one carrier. The proof doc says so plainly. It proves accounting, not candidate traversal, which matches the declared scope.

**VERDICT: APPROVE**
