# Agent envelope separation — reviewed locally, not deployed

September11,2026UTC. Runtime e2b67fcac0650b2351c9744612d0df84a0a93b10 against
cbe36655213b27b69218f7a04e8846dd068a8d3a independently APPROVE105s. Canonical
message/history validation no longer knows HTTP paths, choice envelopes or usage
field locations. The installed immutable AgentWireShape owns those mappings;
the actual AgentCodec factory uses it directly. Historical imports remain thin
wrappers outside the engine path. No new owner-authorable wire schema, authority,
spending permission, unknown-CLI support or arbitrary inner-message translator.

Alternative installed-envelope tests change path, six top-level request names
and nested response selectors while preserving canonical validation and exact
tool results. Frozen three-function oracle matches base by independent AST
comparison. Failure/unknown states, single choice/error refusal, old-source
reasoning stripping and optional model/token receipts preserve behavior.

Independent available-family fallback under the primary checkout's
docs/reviews/2026-09-11-review-provider-limit.md, not cross-family approval.
Reviewer reproduced197cases0.93s on Windows with bytecode disabled and
python -m pytest -p no:cacheprovider -q tests/test_agent_wire_shape.py. All five
plugin mirrors byte-identical. One nonblocking blank line at oracle EOF removed
after review; no runtime changed. Brief/output are primary
output/agent-envelope-review-brief.md and output/agent-envelope-review.md.
Command: python scripts/peer_agent.py codex --out output/agent-envelope-review.md
--prompt-file output/agent-envelope-review-brief.md
--cwd C:/Users/Jonathan/.codex/worktrees/select-agent-models/TinyAssets --timeout 600.
Terminal exit0, no recursive peers or renewed monthly-limit probes.

Author WindowsPython3.14:781passed21.71s; actual LinuxPython3.11.16/git2.47.3/
bwrap0.12.0:781passed16.90s, zero skips. Command:

    python -m pytest -q tests/test_agent_wire_shape.py tests/test_agent_chat_codec.py tests/test_agent_protocol_capability.py tests/test_protocol_encoders.py tests/test_interactive_http_agent.py tests/test_agent_inference.py tests/test_custom_source_execution.py tests/test_bundled_source_contract.py tests/test_selected_model_authority.py tests/test_discovery_execution_shapes.py --tb=short --show-capture=no -rs

Linux uses wsl -d Ubuntu --cd /mnt/c/Users/Jonathan/.codex/worktrees/select-agent-models/TinyAssets
bash -lc with GIT_DIR=/mnt/c/Users/Jonathan/Projects/TinyAssets/.git/worktrees/TinyAssets6,
GIT_WORK_TREE=/mnt/c/Users/Jonathan/.codex/worktrees/select-agent-models/TinyAssets,
then python3 scripts/linux_oracle.py -- and the same pytest arguments.
Plugin build completed before oracle archived the working tree. Ruff and mirror
checks pass; python packaging/claude-plugin/build_plugin.py stages427files and
passes its import probe.

Initial three-file codec/protocol check was1failed117passed; replaying both base
codec/protocol modules from git show cbe36655 in a fresh interpreter reproduced
the exact same failure. Prior source migration changed the legacy incomplete-cap
error wording. One line restores original wording, as still asserted by the
existing test and frozen discovery oracle. No rejection/price guard relaxed.

Standalone check_channel_agnostic.py passes after substantive decoupling. Its
separate equality test initially failed because three counts decreased. The
documented --update regenerates the baseline DOWN only: compute_connection
claude2->1, protocol_encoders anthropic12->11 and openai9->8. No increased count,
new exemption, known-failure suppression or skipped test. Existing total comment
was also stale; current682across54files. Fifteen ratchet tests pass6.82s Windows.

Local wheel built with python -m pip wheel . --no-deps --wheel-dir an external
unique temp directory, using isolated build dependencies, not a global install.
tinyassets-0.1.0-py3-none-any.whl SHA256
125bd90bb1061480a2f8f01a5687d788d6ed52c2c062d0208001fb1679456b62 includes both
agent_wire_shape.json and source_contract_presets.json. A separate pip --target
installation in that temp directory imported its own modules and loaded both
assets, including four legacy ceiling units. First diagnostic used nonexistent
key ceilings and failed; corrected actual key caps passes. CI artifacts not proved.

Not whole-PR approval, deployment or rendered user acceptance. Public source
authoring help, native explicit/all-universe controls, persisted receipts and
unpowered automatic setup remain open. PR3832 at08:51UTC still draft/open,
remote bd93e239, auto-merge null. No private workflow or app account changed.

Release follow-up08:56UTC:353f1eee pushed to the same draft PR; packaging CI
34581378904 passes and slow-tests in34581378851 passes, required-tests still
running. Invariants34581378823/preview34581379070 find the same stale generated
app checksum from the earlier picker change. Canonical render_marks changes only
that checksum; all52generated assets unchanged. All six pre-commit invariants
now pass. Normal npm ci resolves the initial missing-yaml local test dependency;
npm test passes233with4platform skips,0failures. No package/lockfile edits.
Two earlier frozen-oracle EOF blank lines removed; full bd93-to-working diff
whitespace check clean. Ratchet Linux15passed5.23s,0skips. PR scope gate correctly
needs fresh exact whole-PR authority review; old bd93 approval is not reused.
