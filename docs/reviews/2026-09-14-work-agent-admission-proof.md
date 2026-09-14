# Agent work allowance and between-step fence

September 14, 2026, local feature tree based on d89378e3. This implements the
R5 adaptation in remaining-model-execution.md and the foreground part of the
reviewed R3 between-step fence. It does not enable the workflow coordinator.

The existing immutable agent-turn opt-in uses the accepted finite binding/work
ceiling, shared across every round under the same receipt. Static node/retry cost
must still fit; prompt-only workflows retain their previous invocation count.
No token/cost ceiling, workflow field, private workflow or background queue cap
changes. Both legacy and manifest foreground receipts are exercised through the
real admission path. The fixture's ordinary HTTP policy has three retry slots;
its agent variant uses the already accepted binding ceiling instead.

The private foreground between-step check validates the exact store-minted,
process-bound sealed carrier; current immutable run and opt-in; current owner;
unchanged live receipt/claim and expiry; original reservation and selected member;
current custody/assignment; and the legacy child binding where applicable.
It reserves nothing and does not rearm an inference. Missing/revoked authority,
run cancellation, altered subject, changed owner and tampered seal refuse.
The adapter still needs to invoke this check before rounds and tools.

Verification on September 14 around 18:29–18:32 UTC:

```
python -m pytest -q tests/test_work_agent_authority.py tests/test_work_agent_allowance.py tests/test_run_provider_session.py tests/test_work_model_selection.py tests/test_agent_workflow_fences.py tests/test_provider_work_authority.py --tb=short --show-capture=no --disable-warnings -rs
```

- Windows: 193 passed, zero skips, 27.67s.
- Linux oracle: 193 passed, zero skips, 23.83s. WSL Ubuntu invoked
  `python3 scripts/linux_oracle.py --` with the same arguments and explicit
  worktree Git paths (Python 3.11.16, git 2.47.3, bubblewrap 0.12.0).
- Windows provider-neutrality ratchet plus the two new files: 57 passed,
  zero skips, 17.53s.
- Ruff, strict OpenSpec validation, diff whitespace checks and 440-file plugin
  mirror/import probe pass. Only import sorting changed after the Linux launch;
  no executable behavior changed.

An initial manifest test accidentally used the legacy fixture (no accepted model
access), correctly producing a legacy receipt. The fixture now explicitly seeds
discovered model access; no production validation was weakened. Initial Ruff
line-length/import-order findings were corrected.

The new authority tests use real stores/router but intentionally replace persona
setup and remote provider responses. They are authority tests, not actual tool
execution or native-account proof. Workflow adapter/observer, background twin,
whole-node replay suppression, final approved Fable review, deploy and rendered
app acceptance remain open. Existing router/tool refusals are unchanged.
