# Loop substrate roadmap — post-PR-#176 sequence

**Author:** Cowork session, 2026-05-02 ~19:35 UTC.
**Source:** Live dev-partner conversation with ChatGPT (gpt-5) at https://chatgpt.com/c/69f64b8d-fa04-83e8-b4d3-bb6e95b16475 — chatbot was framed as senior-dev partner on the loop project, did 11+ tool calls inspecting live state, gave a fully prioritized plan with concrete schemas + code.
**For:** Codex assistant pickup. Replaces / supersedes the watcher MVP idea in `COWORK_HANDOFF_2026-05-02-user-sim-plan/branch-export-import-spec.md` § "Tier-1 #6" because Codex's PR #176 closed the in-process call-site, making the external watcher unnecessary.

## TL;DR — the 6-step sequence (chatbot's preferred ordering)

Given PR #176 just landed (in-process trigger), in this order:

1. **Verify `file_bug` returns or records `run_id`.** I checked PR #176's diff — it does NOT surface `triggered_run_id`. Step 2 picks this up.
2. **Add trigger receipt / outbox.** Per-bug-id traceable record so silent enqueue failures don't masquerade as success.
3. **Add BUG-011 lease fields + heartbeat write path.** Phase A — write-only, no behavior change.
4. **Shadow watchdog.** Phase B — log what it would reclaim, don't actually reclaim yet.
5. **Scoped active reclaim** for `fd5c66b1d87d` (start narrow on change_loop_v1, then expand).
6. **Then BUG-045 child invocation.** `invoke_autoresearch_lab` → `await` → child output attachment.

**Chatbot's correction from earlier:** after PR #176, the next fastest path is NOT only BUG-011. It is **trigger observability + BUG-011 together**. Without trigger receipts, we can think the bridge works while silently dropping runs. Without lease/reclaim, we can start runs but lose them. Both are needed before BUG-045 gives us reliable autonomy.

---

## Step 1 — Verify `file_bug` surfaces `run_id` (5 min check)

**State of PR #176 verified via GitHub API:**

PR #176 changed exactly 3 files:
- `workflow/api/wiki.py` (+42 / -0)
- `packaging/claude-plugin/plugins/workflow-universe-server/runtime/workflow/api/wiki.py` (+42 / -0)
- `tests/test_bug_investigation_wiring.py` (+19 / -13)

**No `run_id` token in the patch text.** The trigger fires but the spawned `run_id` is not returned to the caller or written to the bug page frontmatter. So Step 2 is genuinely needed.

**Verify path:** once the live daemon picks up PR #176's image, file a fresh test bug via direct MCP and look at the response payload. If `triggered_run_id` is absent, file Step 2 immediately.

---

## Step 2 — Trigger receipt / outbox (chatbot's recommended shape)

Replaces the weaker idea of a single `last_trigger_attempted_at` field. Per-bug-id traceable.

### Where it lives

`_wiki_file_bug` in `workflow/api/wiki.py`. When the bug page is written, also create a trigger record (separate row in a new `bug_trigger_attempts` table or appended to existing run-events table — Codex picks the storage shape).

### Trigger record fields

```
bug_id                       BUG-NNN
bug_page                     pages/bugs/bug-nnn-...md
trigger_attempt_id           uuid
goal_id                      c4f481e65b13
branch_def_id                fd5c66b1d87d
status                       pending | queued | failed
attempted_at                 ISO timestamp
run_id                       <run_id when status=queued, NULL otherwise>
```

### Surface the same in the file_bug response

The bug page frontmatter (or the `file_bug` JSON response payload) should include:

```yaml
triggered_branch_def_id: fd5c66b1d87d
triggered_goal_id: c4f481e65b13
triggered_run_id: <run_id>
trigger_status: queued
triggered_at: <timestamp>
```

That gives the join key for evidence records, watchdog recovery, and later child-invocation proof.

---

## Step 3 — BUG-011 lease fields + heartbeat (Phase A: write-only)

### Add columns to runs table (or equivalent)

```
worker_owner_id            string, nullable
worker_generation          int, default 0
heartbeat_at               timestamp, nullable
lease_expires_at           timestamp, nullable
last_progress_at           timestamp, nullable
attempt_count              int, default 0
max_attempts               int, default 3
recovery_reason            string, nullable
```

### Feature flags

```
WF_RUN_LEASES_ENABLED=true       # write columns
WF_RUN_RECLAIM_ENABLED=false     # don't reclaim yet
```

### Heartbeat call site

After every node commit:

```python
record_node_output(...)
mark_node_ran(...)
last_progress_at = now
heartbeat(...)        # writes worker_owner_id, heartbeat_at, lease_expires_at = now + LEASE_TTL
```

**Lease TTL:** 5–10 minutes. Stale-terminal cutoff should be much longer than one hour and **attempt-based**, not "one hour of silence → terminal" (that's the BUG-011 pattern that bit `4da58d59ff4c4e18`).

### Exit criteria for Phase A

Every new `change_loop_v1` run has populated lease metadata visible via `get_run`. Legacy execution still owns terminal state. Nothing breaks.

---

## Step 4 — Shadow watchdog (Phase B: log only)

### Stale sweeper (logging only, no actual reclaim)

```python
for run in running_runs_where(lease_expires_at < now):
    if attempt_count < max_attempts:
        log("would_requeue: run_id=%s attempt=%s", run.id, run.attempt_count + 1)
    else:
        log("would_terminate: run_id=%s reason=worker_lease_expired_attempts_exhausted",
            run.id)
```

### On daemon startup (logging only)

```python
log("would_requeue_orphans: %s",
    [r.id for r in running_runs_where(worker_owner_id_belongs_to_dead_process_or_lease_expired)])
```

### Exit criteria for Phase B

Run the watchdog for ~24h in shadow mode. Compare its log output against the actual stuck-run cases observed in production. If the watchdog would have correctly identified all of them with no false positives, ship Phase C.

---

## Step 5 — Scoped active reclaim (Phase C: turn it on for change_loop_v1 only)

### Active reclaim SQL

```sql
UPDATE runs
SET worker_owner_id = :worker_id,
    worker_generation = worker_generation + 1,
    lease_expires_at = :new_expiry,
    recovery_reason = 'worker_lease_expired_requeued',
    status = 'queued'
WHERE id = :run_id
  AND status = 'queued'
  AND (worker_owner_id IS NULL OR lease_expires_at < now());
```

### Resumption rule

**Do not resume mid-node.** Resume from the next uncompleted node boundary. Mid-node resume requires per-node idempotence which we don't have yet.

### Feature flag

```
WF_RUN_RECLAIM_ENABLED=true     # only after Phase B shadow ran clean for 24h
```

### What "done" looks like

A live run should no longer say:

```yaml
resumable: false
resumable_reason: v1 terminal-on-restart
```

It should say:

```yaml
resumable: true
reclaimable: true
last_checkpoint_node: attachment_receipt_gate
next_pending_nodes: [invoke_autoresearch_lab]
attempt_count: 1
```

And if the worker dies, `get_run` should show:

```yaml
status: queued
recovery_reason: worker_lease_expired_requeued
```

or after another worker picks it up:

```yaml
status: running
worker_owner_id: worker-abc
recovered_from_worker: worker-old
```

### Exit criteria for Phase C

A `change_loop_v1` run that has its worker killed mid-execution gets reclaimed by another worker within `lease_ttl + sweep_interval` and completes successfully. Demonstrated end-to-end via a deliberate kill test, not just inferred from logs.

---

## Step 6 — BUG-045 child invocation (after run survival is solid)

Per chatbot: don't attempt this before Steps 3–5 complete. **A child invocation path that starts but gets orphaned is worse than no child invocation at all** — it adds complexity without trustworthy evidence.

Once runs survive worker churn, prove the path:

```
change_loop_v1.invoke_autoresearch_lab → await_autoresearch_lab → attach child outputs
```

Then tighten success criteria — parent-only completion becomes insufficient; require child packet attachment.

The chatbot did not produce a full BUG-045 implementation spec in this conversation. That should be the next topic on the next dev-partner chat.

---

## Bonus — observability tripwire (alongside Step 2)

A periodic canary that files a marked-test bug and asserts the loop fires within N seconds:

```yaml
component: workflow.file_bug_trigger_canary
severity: cosmetic
title: CANARY file_bug trigger bridge YYYY-MM-DD HH:MM UTC
```

Within N seconds of filing, assert:

- BUG page exists
- `trigger_attempt_id` exists for that bug
- `run_id` exists in the trigger record
- `get_run(run_id)` returns `queued` / `running` / `completed`
- `branch_def_id == fd5c66b1d87d`

If any fail → page / alert / file evidence.

**Cleanup pattern:** make canaries hidden / `category=test` if possible, or tag them so the loop ignores them. Avoid daily noisy canary bugs forever unless there is a cleanup/ignore path.

This canary is a **second layer**, not the primary tripwire. Trigger-receipt records (Step 2) are the primary durable source of truth — the canary is dashboard telemetry on top of it.

---

## What we DID NOT cover in this dev-partner chat (next topics)

- **Goal taxonomy cleanup** (chatbot's earlier finding #4): `change_loop_v1` is canonical for `bug_investigation` (`c4f481e65b13`), but the broader "Route a patch request through investigation, PR, release, and live observation" goal `4ff5862cc26d` has no canonical branch. May be intentional but should be cleaned before autonomous branch selection depends on it.
- **BUG-045 implementation detail.** Sequenced after Steps 3–5 per chatbot, but the actual code path needs its own dev-partner pass.
- **Daemon worldbuild_stuck noise on `echoes-of-the-cosmos`.** Orthogonal to loop work but blocks 24/7 confidence claims. Probably wants its own audit + fix.
- **Branch-content drift detection.** Already covered separately in `branch-export-import-spec.md` — the export primitive becomes the drift signal vs the wiki/git snapshot.

---

## Provenance notes

- Conversation captured at https://chatgpt.com/c/69f64b8d-fa04-83e8-b4d3-bb6e95b16475 — the chat is on Jonathan's ChatGPT Pro account in Developer Mode with the Workflow DEV connector enabled.
- Chatbot was driven in dev-partner mode (per host directive 2026-05-02 retiring the persona-narrative framing) with senior-dev framing in the opening turn.
- The ui-test skill rules that authorize this self-initiated work are PR #175 ("do not self-initiate" retired) and PR #181 ("Mission's primary question answered → stop" retired). Both pushed by this Cowork session.
- Cross-family rule applied: Cowork (Anthropic family) drives ChatGPT (OpenAI family) for cross-perspective coverage.
