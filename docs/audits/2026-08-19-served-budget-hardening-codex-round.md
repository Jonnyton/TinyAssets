# Served-budget hardening — Codex cross-family round (2026-08-19)

Branch `durable-agent-push` / PR #2434. Cross-family adversarial review by Codex
(read-only) of the served-budget decouple + Slack app-ingress serving fix.

## Round 1 verdict: REJECT

Codex reviewed commit `cb18cf97` and found merge-blocking defects. Summary of the
five findings and how each was addressed in the follow-up hardening commit.

1. **Critical — per-turn token bound is not hard-enforced.** The router lowers
   `ModelConfig.max_tokens` but neither `claude -p` nor `codex exec` is passed a
   token limit, and Claude reports no usage, so settlement is a best-effort byte
   estimate. Removing settled-usage accounting permits repeated real overruns
   until upstream metering intervenes.
   → **Resolved by honesty, not a false hard cap.** This is architectural (Hard
   Rule 3: CLI subprocess writer, no SDK). The reserve path now documents
   explicitly that `max_tokens` is not a hard cap and the real spend bound is the
   user's own metered subscription; the ledger is best-effort accounting +
   runaway detection. No fabricated boundary.

2. **Critical — Claude serving violated the OpenSpec design.** The blanket
   `claude-code` hold was replaced by a computed check that trivially passed
   because `_SERVING_ROLES == ("writer",)`; `design.md` §"Claude requester-local
   readiness" forbids silently bypassing role-completeness merely because
   converse asks only for writer.
   → **Resolved.** claude-code serving is now HELD BY DEFAULT and requires BOTH
   an explicit host opt-in (`TINYASSETS_ALLOW_CLAUDE_SERVING`, off by default)
   AND the computed role-coverage proof. The default matches the spec; any
   relaxation is an explicit host deployment decision. Formal OpenSpec sync of
   the host exception is owed and pending founder ratification.

3. **Required — guard was both a routine brick and a restart-resettable runaway
   guard.** The cumulative count bricked at ~2500 conversations yet reset on
   restart and depended on audit-row retention.
   → **Resolved.** The invocation runaway guard is now a true ROLLING WINDOW
   (`_RUNAWAY_WINDOW_S`, counts only rows created in the window): it bounds
   runaway but ages out, so it never permanently bricks. Retention pruning is
   decoupled — `_prune_settled_history` never evicts a row still inside the
   window, so the guard is independent of retention.

4. **Required — stale recovery was load-bearing but boot-only.** Non-unavailable
   failures become `indeterminate` (in-flight under the new budget) and never
   settle during a healthy long-lived process; one orphaned near-full reservation
   could brick serving until reboot.
   → **Resolved.** Added a `created_at` timestamp + `reconcile_served_budget_leases`
   that settles unsettled holds older than `_UNSETTLED_LEASE_S`, wired as a
   periodic daemon thread (every 5 min) so serving self-heals mid-run without a
   restart. Live in-flight turns (within the lease) are never charged early.

5. **Required — `release_served_provider_budget` erased the invocation count.**
   Deleting the `reserved` row released both the token hold AND the runaway-guard
   history, and `ProviderUnavailableError` is only a heuristic.
   → **Resolved.** Release now SETTLES the row as zero-spend `succeeded` instead
   of deleting it: the launch still counts toward the rolling window, the token
   hold is released, and rolling-window aging keeps a burst of failed launches
   from bricking.

App-ingress: Codex found no cross-owner credential confusion in the change
itself (resolution stays constrained to the routed universe + capability
principal + one serving binding, revalidated at provider authorization). It noted
two adjacent pre-existing items — persona/ACL not revalidated at the converse
sink (revocation race) and "exactly one" searching only the newest 100 bindings —
tracked separately, out of this change's scope.

## Follow-ups still owed (multi-tenant gate)
- Persona/ACL revalidation at the converse sink; SQL-level binding cardinality.
- Formal OpenSpec sync of the claude-serving host exception (founder ratify).
- Real rolling-window cumulative TOKEN budget (vs the current best-effort byte
  accounting) is inherently limited by the CLI-subprocess architecture.
