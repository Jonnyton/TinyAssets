I'll review the frozen checkpoint 2ca96c52 against 493bd98c using `git show` only, no edits or dispatches, per your constraints. Starting with the diff stat and the four proposal notes.

Now the canonical runtime files, the two diffs, and mirror parity in one pass.

Mirror parity holds. Next I need the existing helpers this code leans on and the tests. Fetching all in one pass.

Still tracing the existing reset, deletion, and conversation-store helpers the checkpoint depends on. Pulling the rest in parallel now.

Visibility rule matches the existing helper. Remaining reads are the two test files, the fixture-fix location, the cleanup helpers, and a purge grep. Requesting all of them together now.

Review complete. Everything below is from `git show` of 2ca96c52 against 493bd98c. I ran no tests, no subagents, and no Codex dispatch, since your hard constraints forbid them even though the session hook suggested one.

## Basic-safety findings: none blocking

**AGREE: same-key atomicity.** Reservation runs inside one `BEGIN IMMEDIATE` on the runs DB with a UNIQUE(owner, universe, session, key_hash) constraint at `tinyassets/storage/conversation_run_admissions.py:37`. A repeat returns the original row; a different intent digest raises `IntentConflict` at line 286 without inserting a run. Context, selection, and inputs are not part of the digest, so mutable server state cannot change retry identity.

**AGREE: source visibility before deserialization.** The `authorize_source` check at lines 193-204 reads only `branch_def_id` from a read-only runs connection, then checks author or public visibility through the held author transaction, and refuses before any `snapshot_json` is touched. The rule matches `_resolve_readable_branch` in the API layer. Pin, hash, active status, and recomputed content hash are rechecked inside the runs writer at lines 215-227.

**AGREE: no duplicate terminal pair across the crash window.** The projection row in the home DB is keyed by admission id, the founder and reply turns carry deterministic `ext_id` values under the existing partial unique index, and a retry after a crash between pair write and flag write finds the projection row and only sets the flag. A missing pair with an existing projection row, or a `committed` flag with no projection row, returns None and expires the payload rather than re-appending.

**AGREE: deletion and reset fences.** Tombstone checks run inside the author writer via `check_current_home`, and deletion's `write_tombstone` needs that same writer, so deletion waits behind an in-flight projection. The table is person-keyed in `PERSON_KEYED_DESPITE_UNIVERSE`, and `_tables()` sorts names, so admissions delete before their `runs` FK parent. Scoped reset only nulls payloads post-witness, never deletes rows, and the home `.db` refusal in `_walk_home_without_following` is untouched. Legacy digests are preserved because `_reset_state_digest` only adds the new key when the list is non-empty.

**AGREE: lock order.** Shared barrier, then author writer, then exactly one of runs writer or conversation writer. `runs_transaction` refuses nesting, `authorize_source` refuses to run under the runs writer, and nothing in the path touches provider admission or the network.

**AGREE: fixture fixes.** All three are in the frozen commit, not at base. The 0600 chmod applies only in the non-Windows branch of two positive tests, and a new negative test requires refusal of 0644. The WAL checkpoint is added before the byte snapshot and the byte-equality assertion itself is unchanged. Mirror copies of all four runtime files are byte-identical.

## DISAGREE_CONCERN: hardening, not blockers

- **Orphan sweeper vs reservation.** `_mark_orphaned_run_if_needed` in `tinyassets/runs.py:174` marks any `queued` run with no live in-process future as `interrupted` after the grace window. A reservation the shared worker has not claimed within that window freezes to a platform failure terminal, and the same key then returns that terminal forever. Fail-safe, but the integration must claim inside the grace window or exempt reservations.
- **Pair-written, flag-unset window against a non-reset purge.** If something other than scoped reset deleted the home conversation DB in that window, a delayed projection would re-append the pair. No such purge path exists today, and it is same-owner data only.
- **Untyped failure.** `_freeze` at line 320 calls `json.loads` on `output_json`, so a completed run with a NULL output raises `TypeError` rather than `TerminalUnavailable`. Loud, but callers will not catch it as a terminal problem.
- **Post-witness recovery can wedge.** If the owner's admissions vanish between witness and recovery, `expire_committed` at `conversation_reset.py:92` refuses forever and serving stays blocked until an operator intervenes. Fail-closed, and the test at line 568 encodes it, but worth a documented repair step.
- **Stricter visibility than the legacy helper.** `authorize_source` requires visibility to equal `public` exactly, while the API helper treats NULL as public. Fail-closed divergence; confirm it is intended.
- **Surface inconsistency.** `plan_action` raises on a linked `.runs.db` where `_inspect_root_runs` returns a blocker string. Both refuse.

## Explicit missing integration gates

- **No scope factory from supplied connections.** `_Scope` is private and only built by `authorized_scope`. The prepared callback cannot yet consume the worker's `author_conn` and `runs_conn` without re-entering the barrier, which the notes correctly forbid. This must exist before shared-worker integration.
- **Schema initializer, producer attribution seam, and dispatch claim ordering** remain unwired, as the checkpoint states.

No real user reset was performed or authorized by this review. This is safe to integrate dark; it is not release approval.

VERDICT: APPROVE

The stop hook asks me to read the finished review and take another lane. Reading is within my constraints; dispatching or editing is not. Reading the finished file now.

Nothing further is needed from the tree. The finished file is the earlier proposal-stage shape review, which returned ADAPT with four blockers. Two of them are what this checkpoint implemented and I verified: the durable canonical admission and the adapter-side source authorization with active, self-contained versions only. The other two, the preference data bridge and refusing consumer-selection writes from the served-agent channel, are the explicit integration gates my verdict already lists as unwired. Its optional `ext_id` dedupe for the pair writer is also present in the checkpoint. That review is consistent with mine and changes nothing in it.

The running `canonical-storage-review.md` and the four vanished dispatches have no output files in this worktree, so they belong to another session. Re-dispatching or dropping them, and any further build lane, would violate this session's hard constraints of no edits, no children, and no commits. The verdict above stands as the complete deliverable, and there is honestly nothing else to advance within those constraints.

VERDICT: APPROVE
