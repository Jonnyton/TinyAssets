# Startup ordering integration evidence

September21,2026. Candidate based on deployed89b47e00, not deployed yet.
Necessary dependency discovered by closeout PR3906 required CI35650830517:
HTTP TestClient startup raised database-is-locked before any SSE assertion.

Opus built commits405687df (red/shape),8bf585d2 (ordering),8b078519 (concern).
Terminal peer89612 exit0/741s. Codex independently reviewed and corrected the
integration tests: isolate only the unrelated perpetual maintenance thread,
exercise HTTP/SSE/stdio assigned-worker ordering and initialization refusal,
verify barrier cleanup, and use managed temporary roots. Causal wording now
distinguishes controlled SQLite locking from unidentified historical contention.
No production retries, flags, schema, permissions or workflow edits.

## Regression evidence

- Frozen pre-fix405687df, Linux oracle48695:3failed/1passed in2.26s. Command:
  `python scripts/linux_oracle.py -- -q tests/test_startup_db_order.py --tb=short`.
  Actual HTTP lock, HTTP order and stdio worker order fail; locked-DB control passes.
- Integrated candidate, Windows Python3.14:13passed in6.03s. Command:
  `python -m pytest -q tests/test_startup_db_order.py tests/test_mcp_sse_keepalive.py --tb=short`.
- Integrated candidate, Linux oracle6931 exit0:15passed in6.55s, no skips,
  Python3.11.15/git2.47.3/bwrap0.12.0. Same two files plus
  `tests/test_workspace_run_wiring.py::test_http_application_lifespan_stops_workspace_sweepers`
  and `tests/test_refresh_session_seal.py::test_the_daemon_arms_the_seal_as_the_first_thing_main_does`.
- Those existing SSE tests passed at both frozen base and original closeout
  (3 each); existing cleanup/seal selectors passed2 at unchanged base.
- Ruff passes for changed code/tests after formatting; plugin build stages496
  files with import probe-ok. No quarantine or CI-gate changes.

## Release boundary

Integrate this necessary startup dependency into PR3906's closeout branch,
return the PR to draft before changing its head, then obtain a fresh exact-head
cross-family review. Prior e4dc801f review remains valid only for that old head.
Required CI, verified deployed SHA/public canary, and rendered app retest still
gate release completion. No replay of users' private workflows by the operator.

Rollback: if startup/health fails after deployment, restore the previous known
good image using the canonical deployment rollback path; no schema or stored
data has changed. Revert only the startup-order correction through a reviewed
patch if source rollback is needed, retaining the prior provider tool-wait fix.
Do not work around a failure by weakening gates or reusing old approvals.
