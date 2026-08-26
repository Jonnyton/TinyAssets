# Concerns

One file per unresolved concern. **This directory replaced the `STATUS.md` Concerns section on
2026-08-25**, when the board was retired in the harness reset.

## Why files, not GitHub issues

Codex's review of the reset plan (`docs/audits/2026-08-25-harness-reset-codex-review.md`) argued
this and was right: GitHub issues are externally mutable, network-dependent, and **absent from a
clone**. A security finding that only exists in a web UI is not evidence a fresh checkout can act
on. A tracked file is. Link an issue from a concern file when one exists — but the file is canonical.

## Conventions

- **Filename:** `YYYY-MM-DD-short-slug.md`, dated by when the concern was **filed**.
- **Header:** `**Filed:**` / `**Verified:**` / `**Re-verified:**` / `**Severity:**` (P0/P1/P2, or
  omitted when severity is not the point).
- **Source (verbatim)** — the original text, unedited. Never paraphrase a security finding forward;
  paraphrase drifts, and the drift is what let `#1489` end up pointing at an unrelated merged PR.
- **Re-verification** — when a premise is re-checked, record the date and what changed. Line numbers
  and paths rot; the premise usually doesn't. Correct the citation, keep the finding.
- Resolve a concern by **deleting the file**. Git holds the history.

## Open concerns, migrated 2026-08-25

| Severity | Concern | Filed |
|---|---|---|
| **P0** | [Public-site privacy, deps, and CI secret exposure](2026-07-27-public-site-privacy-deps-ci.md) — a same-repo PR can request 19 secrets | 2026-07-27 |
| **P0** | [Graph/provider false attestation](2026-07-02-graph-provider-false-attestation.md) — router fallback neutralizes isolation refusals | 2026-07-02 |
| **P1** | [`write_brain` persistent prompt-injection](2026-08-24-write-brain-prompt-injection.md) — attacker content re-injected into system role every turn | 2026-08-24 |
| **P1** | [Founder-taught canon defaults public](2026-08-06-founder-canon-defaults-public.md) — Codex reproduced | 2026-08-06 |
| **P1** | [No live failure proof](2026-07-23-no-live-failure-proof.md) — escalation and caps are CI-only | 2026-07-23 |
| **P1** | [Served-agent BUILD verb parity](2026-08-23-served-surface-build-verb-parity.md) — partial; the rest is authority-sensitive | 2026-08-23 |
| **P2** | [`_current_actor` env fallback](2026-06-30-current-actor-env-fallback.md) — bypasses `permissions.py` | 2026-06-30 |
| — | [Cloud automation rollback refused >24h](2026-08-05-cloud-automation-rollback-refused.md) — tested, not fixed | 2026-08-05 |
| — | [Provider fallback-chain privacy](2026-04-17-provider-fallback-chain-privacy.md) — gemini/groq/grok still in the chains | 2026-04-17 |
| **P2** | [`deployed_sha` proves the receipt, not the running binary](2026-08-26-deployed-sha-proves-receipt-only.md) — a rollback with an intact receipt reads as shipped | 2026-08-26 |

Predating the migration: [synthesis skip echoes](2026-04-16-synthesis-skip-echoes.md),
[`test_record_and_get_stats` flake](2026-04-26-test_record_and_get_stats_flake.md),
[cloud-agent command duplication](2026-08-02-cloud-agent-command-duplication.md).

## Not migrated, and why

Triage found three of twelve board rows did not survive contact with the code. Recorded here so
nobody re-derives them.

**Resolved — `EPOCH2_QUEUE_CONSUMER_READY` (P1, filed 2026-08-03).** The row read: *"3 tests still
assert the closed gate — now the ONLY blockers of main's `full-tests` tripwire."* Inverted.
`tinyassets/branch_tasks_v2.py:113` is `EPOCH2_QUEUE_CONSUMER_READY = True`, and the tests now
assert `is True` and pass (`tests/test_cloud_worker.py:601`,
`tests/test_cloud_automation_continuation.py:1814`; 5 passed, 2026-08-25). Nothing to migrate.

**Expired by design — two watches filed 2026-08-25.** Plug-and-play prod verification (waiting on a
founder X deposit; the first organic post is the proof) and prod disk at 78.6% (already guarded by a
`disk_watch` GitHub issue at 80% and hourly `disk_autoprune` at 85%). Both name their own automated
guard or closing event. A watch whose guard already exists does not need a second home.

## A caution the migration earned

The board's row for the LAN/CSRF finding cited **`#1489`**. PR #1489 is *"feat(command-center):
recover the Agent Village"*, merged — unrelated. Two other concerns cited paths that no longer exist
(`engine_helpers.py:192`, `router.py:89-92`); both premises held at their new locations. Verify a
citation against the code before acting on it, and re-stamp it when you do.
