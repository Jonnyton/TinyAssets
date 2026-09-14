# Work carrier provenance checkpoint

September 14, 2026, local working tree based on a03afe6c. Five read-only
accessors expose existing sealed record facts for the planned workflow journal
observer. No carrier minting, lifetime, seal, settlement, router permission,
workflow definition or budget rule changed.

Verified around 18:16–18:17 UTC:

```
python -m pytest -q tests/test_provider_work_authority.py tests/test_work_model_selection.py tests/test_agent_workflow_fences.py --tb=short --show-capture=no --disable-warnings -rs
```

- Windows: 115 passed, zero skips, 9.68s.
- Linux: 115 passed, zero skips, 6.67s. WSL Ubuntu invoked
  `python3 scripts/linux_oracle.py --` with the same pytest arguments and explicit
  worktree Git paths. Oracle Python 3.11.16, git 2.47.3, bubblewrap 0.12.0.
- Ruff and diff whitespace checks pass; plugin mirror rebuilt 440 files and its
  import probe passes.

Real store-minted legacy carriers retain exactly one launch after repeated
provenance reads, reject assignment, and remain consumed after later reads.
Two real foreground HTTP compiler/router cases with synthetic wire assert that
manifest records expose the actual selected member binding tuple, not the null
aggregate binding, and that each receipt/reservation matches the persisted row.
These are supporting tests, not live-user execution proof. Final approved Fable
release review remains unused. Workflow adapter, observer and allowance are open.
