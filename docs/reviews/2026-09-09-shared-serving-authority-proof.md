# Shared serving-authority validator

September 9, 2026. Feature worktree `codex/select-agent-models`, based on b3bb8956.
Implementation only: not merged, deployed, or a claim of working fallback routing.

Execution now calls the existing readiness validator for assignment, binding and
live credential custody. Carrier/source/role checks, exact agent revision,
admission fencing, credential snapshots, cleanup and provider-body errors stay
at the execution boundary. Dispatch passes its explicit storage root; existing
readiness callers keep their canonical universe-parent lookup. No schema, public
API, candidate authority, budget limit, model activation or preference changes.

The pre-refactor function is retained as an executable test baseline. Twenty-three
new checks cover HTTP and subscription allow/deny equivalence, non-ready states,
tampered digests, revoked carriers/grants, rotated HTTP credentials, disabled
agents, provider errors, snapshot cleanup and actual shared-validator delegation.

Verification on the working tree:

- Windows / Python 3.14: `python -m pytest -q tests/test_served_authority_shared_chain.py tests/test_open_serving_bind.py tests/test_provider_served_router.py tests/test_mirror_parity_gate.py -rs`: 70 passed, 3 skipped. Skips: POSIX shared-reader concurrency, bubblewrap, optional real-Codex fixture.
- WSL Ubuntu / Python 3.11.15: same four files, `python -m pytest -p no:cacheprovider -q ... --tb=short`: 72 passed, 1 skipped. Optional real-Codex integration was not supplied. Supplemental environment created with `output/receiver-linux-proof.sh`; not a Docker-oracle claim.
- `python -m ruff check tinyassets/provider_assignment.py tinyassets/provider_serving_binding.py tests/served_authority_baseline.py tests/test_served_authority_shared_chain.py`: passed.
- `python packaging/claude-plugin/build_plugin.py`: 397 runtime files, import probe passed.
- `git diff --check`: passed.

Independent review and production verification remain required before landing.
