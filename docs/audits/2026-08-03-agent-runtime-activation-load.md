# Custom-agent activation cross-process load evidence

Freshness: 2026-08-03 PDT, Windows, Python 3.14, branch
`feature/agent-runtime-activation-load-20260803` based on merged activation
PR #2230 (`1a799ae8`).

## Classification

This is shaped local SQLite evidence, not dark-cloud deployment, live-provider,
connector, or production health evidence. It exercises the real landed
manifest, grant, and automation-activation owners with fresh service instances
in spawned processes. It does not close OpenSpec task 5.1.

## Activation scenario and result

`python -m pytest tests/load/test_agent_runtime_activation_load.py -q -s`

- 64 requests across eight spawned processes converged on one active record,
  epoch 1, and exactly one filesystem-visible server lease mint.
- Replacing the entire process pool and sending 64 more requests returned the
  byte-equivalent activation identity without advancing the epoch or minting a
  lease.
- After revoking the required universe-scoped capability, another fresh pool
  returned 64 typed `grants_not_current` denials. The original activation row
  remained unchanged and no additional lease was minted.
- SQLite `PRAGMA integrity_check` returned `ok`.
- Refreshed wall times: initial 0.869s, restart 0.667s, revoked 0.715s.

## Combined evidence

`python -m pytest tests/load/test_agent_runtime_activation_load.py tests/load/test_agent_runtime_cloud_load.py -q -s`

Result: 4 passed in 27.06s. The existing provider/restart load proof again
showed one receipt/claim/reservation/continuation identity, one provider-call
marker, typed concurrent losers, exact terminal replay, and intact storage.

The broader agent-runtime and invocation-authority regression family passed
189 tests in 18.19s. Changed-test Ruff, strict OpenSpec, and diff checks passed.

## Independent review

Independent Claude Sonnet review approved exact evidence head `e0b00149` after
reproducing the focused test four consecutive times, confirming eight distinct
PIDs in each of two non-overlapping process pools, rerunning the combined load
suite, and tracing the real grant and activation transactions. It found no
correctness, authority, race, or claim-boundary defect.

The review identified two integration findings, both folded before
publication: this subtask is numbered `5.1c` to avoid collision with the
existing dark-deploy `5.1b`, and the spawned-process file is listed in
`.github/heavy-test-files.txt` beside its provider-load sibling. This preserves
the short required-test gate while retaining the test in scheduled full-suite
coverage; hosted CI on the publication PR remains required evidence.

## Remaining gate

Task 5.1 still requires dark deployment health, live substrate/environment
evidence, unchanged seven-handle/public-route proof at the deployed head, and
the complete change-level review/foldback. No cloud or customer-surface claim
is made here.
