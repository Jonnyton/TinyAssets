# Work-owned agent journal checkpoint — September 14, 2026

Local working tree based on e02d4b1e21bf9fd4a706284a27e9773f0f521805.
This is storage-format proof, not workflow execution or deployment proof.

Work records use explicit version 3 and immutable root/round receipt lineage.
HTTP version 1 and native version 2 canonical bytes remain unchanged. Invalid
versions, kinds, unknown fields, and mismatched root/round receipts refuse on
write and read. Completed tool results remain recorded and uncertain effects
still block reset. No stored row is migrated or rewritten.

On September 14 around 18:10–18:13 UTC, both environments ran:

```
python -m pytest -q tests/test_agent_work_journal.py tests/test_agent_turn_journal.py tests/test_agent_native_journal.py tests/test_agent_turn_coordinator.py tests/test_interactive_http_agent.py tests/test_mixed_agent_execution.py tests/test_agent_workflow_fences.py --tb=short --show-capture=no --disable-warnings -rs
```

- Windows: 258 passed, zero skips, 31.43s.
- Linux oracle: 258 passed, zero skips, 35.71s. Invoked via WSL Ubuntu,
  `python3 scripts/linux_oracle.py --` with the same pytest arguments; working
  tree copied into the repository oracle (Python 3.11.16, git 2.47.3,
  bubblewrap 0.12.0). Explicit GIT_DIR/GIT_WORK_TREE mapped the Windows worktree.
- Ruff, `git diff --check`, and `openspec validate select-agent-models --strict`
  passed. Plugin build refreshed 440 mirrored files and passed its import probe.

The first expanded Windows run exposed five incorrect test assertions querying
a table that should not exist after invalid root input. Corrected the assertions
to verify rejection before schema creation; production validation was unchanged.

The new 37 cases use real SQLite journals and synthetic records; they do not
claim inference permission. The existing mixed and differential cases retain
chat behavior and pinned workflow refusals. Work authority adapter, finite round
allowance, replay prevention, final Fable review and live proof remain pending.
