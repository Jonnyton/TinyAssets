# Assignment projection consumes resolved records

September 11, 2026; local Windows worktree `codex/select-agent-models`,
parent a3715f2209a27452b012812ed586153844b40727. Not deployed.

The manifest publisher now passes its resolved `AssignmentCandidate` tuple to
the non-authorizing config writer. The writer derives only binding identity,
generation and digests, checks root consistency and unique membership, and
preserves unrelated YAML. It no longer maintains a second provider-brand list
for manifest members. The legacy single-source contract remains unchanged.
These typed records are not credentials or authority; admission still reads
current SQLite binding/custody state. This adds no public provider registration
or arbitrary CLI support, and does not change the stored config shape.

Verification command: `python -m pytest -q` with
`tests/test_assignment_projection_contract.py`, `tests/test_config.py`,
`tests/test_provider_assignment_admission.py`,
`tests/test_provider_assignment_manifest.py`,
`tests/test_serving_manifest_publication.py`,
`tests/test_status_says_what_is_true.py`, followed by
`--tb=short --show-capture=no -rs`.

- Windows: 119 passed in 10.81s, zero skips.
- Actual Linux via `python3 scripts/linux_oracle.py --` with the same pytest
  arguments in Ubuntu WSL: 119 passed in 5.84s, zero skips. Python 3.11.16,
  git 2.47.3, bubblewrap 0.12.0; working-tree snapshot, not an old image checkout.
- New tests cover unfamiliar member identifiers, exact nonsecret output,
  malformed/duplicate/mismatched members, refusal without overwriting config,
  unreadable YAML, legacy behavior and config unable to create authoritative
  assignments or a serving binding. Existing real SQLite publication and
  admission tests remain in the group.
- `python -m ruff check` on both canonical files and the new test: clean.
- `python packaging/claude-plugin/build_plugin.py`: 419 files, import probe OK.
- `python scripts/check_channel_agnostic.py`: still fails at four loci:
  agent_chat_codec/openai, discovery_protocols/openai and openrouter,
  protocol_encoders/openai. The two config regressions are removed. No baseline
  change, exemption or suppression; this is not release readiness.

Independent exact-commit review is required before landing. The remaining
public discovery contract, native choices and live model-picker acceptance
remain open in the owning change.
