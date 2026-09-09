# Accepted connection publication

September 9, 2026. Extends the existing bind_serving_provider transaction with
optional complete model_access membership. No public app/MCP caller supplies it
yet. It is not a fallback order, saved preference or model-execution permission.
The per-attempt model-validation gate still refuses manifest-backed execution.

The same pending/ready protocol now publishes all accepted connection bindings
against one root assignment digest. Provider definitions and credential schemes
are unchanged. The root remains a structural anchor, not first preference.
Replaying equivalent members/model sets is order independent; changed membership,
model scope or cost bounds advances authority generation. Replay validates every
member's current binding, live custody and token/cost/invocation ceilings.
The private shared member checker validates independent members without requiring
the root anchor's live credential; it does not authorize a model or launch.

Pending commits contain the complete candidate manifest. Ready publication
revalidates custody and the exact pending root, issues all bindings and updates
the agent in one transaction. A failed later member rolls back earlier bindings
and leaves a deny-all failed/pending root. Recovery compares the current root to
the pending attempt before writing, so it cannot overwrite another transition.
Invalid input caught before publication preserves the previous assignment.

Verification on the September 9 working tree following8a5ac19e:

- Windows Python3.14: `python -m pytest -q tests/test_serving_manifest_publication.py tests/test_provider_assignment_manifest.py tests/test_open_serving_bind.py tests/test_served_authority_shared_chain.py tests/test_provider_served_router.py tests/test_served_launch_accounting.py tests/test_provider_request_capability.py tests/test_mirror_parity_gate.py -rs`:145 passed,3 skipped,17.54s. Skips need POSIX shared readers, bubblewrap and optional real-Codex credentials.
- Supplemental Ubuntu Python3.11.15: the same eight files through the existing external-temp `output/receiver-linux-proof.sh`:147 passed,1 skipped,37.78s. Optional real-Codex fixture absent; one pre-existing LangChain deprecation warning. This is WSL evidence, not a Docker-oracle claim.
- New publication suite has30 cases: multiple HTTP connections, subscription+HTTP,
  root anchoring, unchanged definitions, reorder replay, scope/model/cost/member
  changes, all member ceilings, independent fallback custody after anchor
  revocation, rotated/revoked grants, non-ready roots, owner/universe mismatch,
  rollback, between-phase revocation, stale recovery, invalid input, absent
  subscription custody and v1/v2 transitions. Shared legacy differential tests
  remain in the combined group.
- Ruff check and format passed; `python packaging/claude-plugin/build_plugin.py`
  rebuilt398 runtime files and passed the import probe; diff check passed.

Independent exact-head review is next. This slice is local and unactivated.
Candidate-aware model validation, discovery, request-local policy, actual ordered
fallback, HTTP tool continuation and UI remain required before user acceptance.
