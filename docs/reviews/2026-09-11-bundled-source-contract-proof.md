# Shared legacy source interpreters — local proof, not deployed

September11 2026UTC. Runtime52f56a94f6c0af3d6ba8010620a98ac3220c3685
againstfe81526e. Initial independent APPROVE140s confirmed shared shape and no
pricing/trust leak but found a nonblocking exact-byte claim mismatch. Correction
9963d04b015d2c53ea28d87d03a73eabdc921309 against52f56a94 preserves prior caller-cap
ordering. Exact correction APPROVE59s, terminal exit0, no required changes;
no push or rollout.

Installed legacy behavior is now JSON data compiled by the shared CatalogueShape,
BenchmarkShape, RequestCeilings, CapacityShape and UsageShape. Discovery no longer
dispatches provider-specific request/capacity/usage callbacks. Existing public
protocol IDs, descriptor bytes, endpoints, provenance, all14 pricing fields,
4ceiling components, Interaction exclusions/derived bounds/output mapping and
reservation arithmetic remain unchanged. Compatibility function names only
delegate to the common interpreters. No user workflow/connection is rewritten.

Installed compatibility inputs preserve prior text scalar/container and numeric
usage semantics. They are not public source-descriptor flags. Owner SourceContract
still requires its closed three-unit/quantity/strict-wire contract and rejects
legacy/account_filtered/compatibility_default fields. No new trust/spend/model
grant or arbitrary-wire/CLI support is claimed by this internal migration.

287 differential cases compare the frozenfe81526e implementations with compiled
data: exact request bytes and model exclusions, all14 prices and eligibility,
capacity/retry scopes, original numeric usage edge cases, full Interaction and
benchmark/transport facts, alternate installed shape through the same machinery,
and refused owner attempts to enable compatibility/trust.24 permutations now
compare unsorted JSON bytes; initial sorted JSON assertions only proved semantic
equivalence and masked cap-key ordering drift. Shared legacy ceiling injection now
uses caller-cap order while custom strict sources retain descriptor order. The frozen oracle's
imports were regrouped; function bodies remain the pre-migration specification.

Author WindowsPython3.14:870 passed34.04s, zero skips. Actual LinuxPython3.11.16,
git2.47.3,bwrap0.12.0:870 passed26.05s, zero skips. Same15-file group:

```text
python -m pytest -q tests/test_bundled_source_contract.py tests/test_custom_source_execution.py tests/test_selected_model_authority.py tests/test_interactive_http_agent.py tests/test_agent_inference.py tests/test_agent_protocol_capability.py tests/test_discovery_execution_shapes.py tests/test_discovery_contract.py tests/test_discovery_contract_compatibility.py tests/test_discovery_snapshot.py tests/test_catalog_decoders.py tests/test_model_options_composition.py tests/test_custom_discovery_publication.py tests/test_model_discovery_capability.py tests/test_protocol_encoders.py --tb=short --show-capture=no -rs
```

Actual Linux runs scripts/linux_oracle.py with the same pytest arguments under
WSL Ubuntu, GIT_DIR=/mnt/c/Users/Jonathan/Projects/TinyAssets/.git/worktrees/TinyAssets6,
GIT_WORK_TREE=/mnt/c/Users/Jonathan/.codex/worktrees/select-agent-models/TinyAssets.
Ruff and whitespace pass. Plugin425-file build/import passes; seven canonical
mirror pairs including JSON pass. Separate import with the plugin runtime first
on sys.path resolves its own discovery_presets.py and four price components.
All three desktop specs use collect_all(tinyassets); CI artifact proof remains.
Local wheel build was not run because hatchling is absent; no package installed.

Initial reviewer independently ran263cases1.01s and verified frozen oracle bodies
against the base by AST. Correction reviewer independently ran287cases1.12s:
PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -q
tests/test_bundled_source_contract.py. Both reviews read-only, available-family
fallback under the documented terminal monthly limit, not cross-family evidence.
Primary outputs: output/bundled-source-contract-review.md and
output/bundled-source-order-review.md. This is bounded exact-commit approval,
not whole-PR or CI/artifact or live acceptance proof.

Fresh check_channel_agnostic.py still fails two earlier loci: agent_chat_codec.py
and protocol_encoders.py. Two discovery loci disappeared through shared execution,
not renamed callbacks, moved provider code, baseline changes or exceptions.
Authoring/schema help, remaining wire-shape work, native/all-universe controls and
live acceptance remain. The last verified remote PR3832 is still draftbd93; this
commit has not been pushed. Remote PR reverified08:32UTC: draft/open, bd93e239,
auto-merge null. App reload still reports the original checklist
passed and the separate approved CI-log302 blocker. No retest prompt or PR takeover.
