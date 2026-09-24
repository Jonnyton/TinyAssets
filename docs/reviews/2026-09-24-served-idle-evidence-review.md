# Served failure evidence: bounded independent review

September24,2026 UTC. Claude builder1818 completed349s/exit0; narrow formatter
preserves admitted tool_phase, finite nonnegative last_progress_age_ms and
side_effect_state in existing server failure logs. Raw telemetry is never
copied. No owner-response, timeout, retry, authority, storage or workflow change.

Codex lead independently reviewed all runtime/tests at9dc674e4 on da0dd350,
measured100pass0skip6.15s with:
`python -m pytest -q tests/test_a_failed_turn_says_what_actually_happened.py
tests/test_provider_tool_wait_evidence.py --basetemp <unique external Temp>`.
Windows Python3.14; scoped Ruff/mirror499-file import/whitespace pass. No
filesystem/sandbox behavior changed. Linux CI remains required.

Independent Opus95400 wrote APPROVE9dc674e4 with44focused passes4.59s.
Lead read the complete report; this records the written verdict, not yet a
successful wrapper exit. Its comment-only observation is corrected: age is
sampled after termination/drain, not proof of provider silence or loop stall.
The synthetic blocked-reader probe proves one possible race, not incident cause.
Final amendment only changes this wording, its mirror and as-built spec/receipt.

Nonblocking: side-effect vocabulary has other definitions; this allowlist
fails closed on unknown states. Pre-existing broader diagnostic serialization
is not hardened by this patch. No secrets-safety claim outside these three new
tokens. No further review round needed for unchanged executable code.

Acceptance: required checks, protected deployed SHA, public handles and original
ordinary app continuity, then inspect next genuine failure's safe timing fields
if one occurs. Never manufacture a live failure or replay side effects to
produce a log. Overall idle-reliability issue remains open until cause/fix/proof.
Rollback: normal cloud image rollback; no schema/data migration or local fallback.
