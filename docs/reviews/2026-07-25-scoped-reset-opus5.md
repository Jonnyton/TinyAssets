# Scoped reset opposite-provider review

Date: 2026-07-25

Reviewer: Claude Opus 5 (read-only), with a read-only Codex second opinion

Reviewed range: `6cde7ef0..f613b23d`

Verdict: **REJECT**

This is the durable branch artifact for the review originally returned at:

`C:/Users/Jonathan/AppData/Local/Temp/claude/C--Users-Jonathan-Projects-TinyAssets/036bd960-6d91-4662-8f8a-0b21163ead22/scratchpad/verdict-scoped-reset.md`

The temporary source is not required to understand or reproduce the findings.

## Findings

1. **Blocker — cross-home data loss.** The reviewed plan bound the home action
   only to a path string. Replacing Alice's directory at that path with Bob's
   directory left the plan ID unchanged; apply completed and deleted Bob's
   file.
2. **Blocker — unclassified in-home stores were destroyed.** Files such as
   `future_queue.sqlite3`, JSONL/Parquet stores, and extensionless stores were
   silently skipped by inspection and then removed with the home.
3. **Blocker — legacy API writer fencing failed open.**
   `fantasy_daemon.api.configure()` released its live barrier before acquiring
   the replacement. Failed acquisition left the old root serving unfenced.
4. **Major — root and run-history schema growth was skipped.** A future root
   `.sqlite3` store and an unknown `.runs.db` table did not block reset.
5. **Major — founder-home predicate widening survived the mutation proof.**
   Widening `founder_home` selection to universe-only left the then-current
   64-test suite green.
6. **Minor — plan was not filesystem-mutation-free.** Read-only SQLite opens
   created `.tinyassets.db-wal` and `.tinyassets.db-shm`.
7. **Process — the prior approval claim had no durable evidence.**
   `LANE_REPORT.md` said an independent reviewer approved, but the branch
   contained no named, dated review artifact.

## Required adaptation

- Bind a reviewed home to the roster principal, its filesystem object identity,
  and an entry/content digest; revalidate under the exclusive barrier before
  rename.
- Default-deny unclassified home/root stores and unknown root-run tables.
- Acquire the legacy replacement writer barrier before swapping and releasing.
- Pin the `founder_home` selector in the mutation proof.
- Make plan reads side-effect-free.
- Preserve this rejection durably and do not claim a post-fix approval unless a
  reviewer actually provides one.

## Fold status

The branch subsequently added reviewer reproductions for all technical
findings before the implementation fixes. The fold evidence and post-fix
commands remain in the intentionally uncommitted `LANE_REPORT.md`. This
artifact records the original verdict; it does not convert REJECT into an
independent post-fix approval.
