# Rate-limit recovery repair — 2026-09-11

A rate-limited scheduler attempt records an empty last_run_id. The context resolver now walks this automation's retained attempt records across rate-limit refusals to recover the preceding run. An initial rate-limit refusal permits a first wake; unknown or missing history still fails closed. Recovered run identity, branch, universe and terminal state retain existing validation.

Validation in the Linux workspace on PR head 4e2c1b0e162ee4f356155dde927dd40641e3e0cd plus this patch: `python3 tests/test_automation_live_context.py -v`: 21 passed; `python3 -m py_compile tinyassets/automation_context.py` and `git diff --check`: passed. Plugin staging copied the updated module, but its import probe lacked uvicorn. pytest and ruff are unavailable. Claude CLI is absent, so independent cross-family review remains outstanding.

Not deployed. PR #3622 required-tests was failing before this repair. Fresh-context integration, preservation of full artifact archives across failed runs, durable work ownership/deduplication and two real scheduler ticks still require verification. The current 20-minute automation still uses literal snapshot inputs; it must only be switched after the runtime is deployed and verified.
