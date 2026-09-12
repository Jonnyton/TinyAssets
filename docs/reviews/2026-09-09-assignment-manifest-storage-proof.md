# Assignment manifest storage — inactive implementation slice

September 9, 2026, feature working tree following d38d150a. Provider-keyed
candidate records bind model access and cost constraints to a root assignment.
Preference order is not authority membership. Version-one digests and existing
assignments retain their prior encoding; version-two roots require intact member
digests and an explicit matching root anchor. Root and children read from one
SQLite snapshot and publish in the caller's transaction.

This is data storage only. The shared serving validator explicitly refuses
manifest-backed assignments until candidate publication and per-attempt model
validation are implemented. No production caller creates these assignments.
The temporary refusal is not the finished user capability or acceptance contract.

Verification on September 9, 2026:

- Windows Python 3.14: `python -m pytest -q tests/test_provider_assignment_manifest.py tests/test_open_serving_bind.py tests/test_served_authority_shared_chain.py tests/test_provider_served_router.py tests/test_served_launch_accounting.py tests/test_provider_request_capability.py tests/test_mirror_parity_gate.py -rs`: 115 passed, 3 skipped, 14.11s. Skips require POSIX shared readers, bubblewrap, or optional real-Codex fixtures.
- Supplemental Ubuntu Python 3.11.15: same seven files through the existing `output/receiver-linux-proof.sh` in a fresh external temporary environment: 117 passed, 1 skipped, 29.43s. The optional real-Codex fixture is absent. This is WSL evidence, not the Docker oracle.
- Focused manifest suite: 26 passed. Covers v1 compatibility/migration, scope/cost changes, order independence, corruption and missing membership, cross-universe copies, transaction rollback, root anchor mismatch, invalid model access, and refusal to activate incomplete v2 authority.
- Ruff over the touched canonical source and test files passed; `python packaging/claude-plugin/build_plugin.py` rebuilt 398 runtime files and passed its import probe; `git diff --check` passed.

Independent implementation review, publication/replay equality, candidate-aware
execution validation, dynamic discovery, actual model routing, full HTTP tool
continuation, visible controls and live user acceptance remain unfinished.
