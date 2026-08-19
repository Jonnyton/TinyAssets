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

## Round 2 (re-review of the hardening) — REJECT again, five more findings

The follow-up Codex re-review (of the pinned hardening commit) confirmed findings
1 and 5 resolved, but rejected again. Each remaining point and its final fix:

- **Lease vs provider-timeout race (Critical).** A fixed lease is unsafe because
  the served timeout is UNBOUNDED — Codex reproduced `UNBOUNDED_SERVED_TIMEOUT=
  3600`. An interim bump to 1800s was still a fixed guess. → FINAL FIX: a
  **per-call `lease_deadline`** stored on each reservation (`created_at +
  call_timeout + _LEASE_MARGIN_S`); the reconciler settles only rows past their
  OWN deadline, so a live call under any timeout is never reclaimed early. The
  router passes `call_timeout_s=cfg.timeout`.
- **Reconcile was boot/thread-only + slow orphan reclaim + streamable-http only.**
  → Added an **opportunistic reconcile inside `reserve_served_provider_budget`**:
  every served call first settles its own binding's past-deadline holds, so
  serving self-heals on EVERY transport (sse/stdio included) on the next call,
  not only via the periodic thread.
- **Finalizer after reconciliation raised a hard error.** A call that outran its
  lease is settled by the reconciler; its late finalize hit `rowcount != 1`. →
  `finalize` now DETECTS an already-settled row and returns gracefully (logs, no
  re-charge); only a genuinely missing row raises.
- **NULL `created_at` not fail-safe.** Migrated/old-binary rows were NULL and
  ESCAPED the runaway window. → Migration backfills existing NULLs to 0
  (ancient, excluded); the guard now treats any stray NULL as IN-window
  (over-count, never under-count), so a runaway cannot slip through an upgrade.
- **Claude hold only at binding creation (Critical).** Serving authorization
  loads PERSISTED bindings; a grandfathered claude binding kept serving after the
  flag was cleared (Codex reproduced `response:served`). → Added a fail-closed
  **serve-time re-check in `reserve_served_provider_budget`**, making the opt-in
  a true kill switch for existing bindings too.

## Founder decision / deferred (NOT resolvable in code)
- **claude-serving spec legitimacy (Critical 2b).** The OpenSpec design
  (`byo-llm-connect-flow/design.md`) explicitly forbids relaxing the
  role-completeness hold "merely because converse currently asks only for
  writer," which is exactly the writer-only scope this opt-in relies on. The
  held-by-default + serve-time-gated form is a strict improvement over main's
  current always-on bypass, but full compliance requires a **founder-ratified
  OpenSpec change** (or holding claude-serving). Surfaced to the founder.
- **Global retention growth (multi-tenant).** In-window rows are retained per
  binding generation; generations/universes are not globally capped. Fine for a
  single founder; the multi-tenant rolling ledger owes a table-wide bound.
- Persona/ACL revalidation at the converse sink; SQL-level binding cardinality.
- Hard per-turn token enforcement is impossible with the CLI-subprocess writer
  (Hard Rule 3); the real bound is the user's own metered subscription.
