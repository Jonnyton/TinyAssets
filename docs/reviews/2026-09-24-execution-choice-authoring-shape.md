# Execution-choice persistence/authoring pre-build review

2026-09-24 UTC. Independent Codex root review of Claude Opus13215's design,
diagnostic22tests and relevant real storage/build/patch/serialization paths.
AGREE with additive nullable columns, existing authorized operations, explicit
clearing, immutable versions and no new provider authority. PLAN unchanged.

DISAGREE_EVIDENCE: daemon_server.save_branch_definition uses INSERT OR REPLACE;
old code omitting new columns erases values, contrary to the proposed rollback
claim. Corrected design requires forward repair or preserving a cloud backup
and blocking incompatible definition writes on rollback. No schema rollback.

DISAGREE_EVIDENCE: api.branches `_spec_get` ignores explicit null; the proposed
reuse would pick nested values or parent defaults instead of clearing. Resolve
key presence with top-level precedence separately for these two fields and test
null-over-value and null-over-parent. Existing topology behavior stays unchanged.

Representability: SQLite signed64-bit integer bounds must be validated before
binding. A larger budget is refused with a clear storage error, not converted to
float and not mistaken for a provider concurrency limit. Keep ordinary positive
budgets uncapped by platform resource constants.

VERDICT: APPROVE shape with these corrections, before runtime implementation.
Root is the independent opposite-family reviewer, not a second Claude reviewing
its own work. No Codex subprocess was dispatched. Implementation, required CI,
deployed proof and ordinary app-agent acceptance remain open. The prior authoring
designer's report mistook its own running dispatch for a separate review; that
statement is false and is superseded by this actual review.
