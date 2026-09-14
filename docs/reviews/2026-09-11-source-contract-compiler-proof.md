# Shared source-contract composition — internal, not live

September11 2026 UTC, feature777ff9ba against e0d8c8a2, then correction315a0bba.
SourceContract combines catalogue/price/benchmark, request caps, extension quantity
effects, aggregate reservation, capacity and observed usage in one immutable
description/digest. It adds no source registry entry. One unfamiliar synthetic
source passes through all interpreters and an installed text/agent wire codec;
this is not public connection publication or live inference evidence.

Unknown/missing charge bindings, incompatible extension dimensions, removed base
quantities, unsupported installed validation, modified endpoint shapes and
unsupported price authority refuse. The existing Interaction is derived from
required prices and cap components. Current v1 supports input/output million-token
USD and request USD dimensions only; unsupported extra dimensions are not silently
excluded. Benchmark identity separates source, score schema and scale. Declared
remote semantics do not prove provider behavior or authorize spending.

Optional installed WireProtocol validators preserve all legacy encode/decode
entrypoints. The new shared validator covers text and full-agent bodies. Final
envelope checks exact JSON types/keys before canonical comparison; generated caps,
constant values, protected fields and base content cannot be modified unnoticed.
JSON-only descriptor depth<=16/size<=64KiB; user tool schemas/history do not acquire
that descriptor nesting limit. Present invalid scalar limits refuse in both text
and agent branches.

Initial independent exact777ff9ba review ADAPT117s, terminal exit0, required two
corrections: serialized comparison coerced tuples/integer keys, and agent bodies
returned before shared numeric bounds. Both corrected in315a0bba with13 regression
cases. Initial reviewer ran45cases successfully, then reproduced the two holes;
green tests alone were insufficient. Follow-up exact315a0bba review APPROVE78s,
terminal exit0, no remaining required corrections. Reviewer ran58cases via
python -B -m pytest -q -p no:cacheprovider -o addopts='' tests/test_discovery_contract.py,
plugin autoload disabled, local Windows September11UTC. Reviewed files match
the commit and canonical/plugin bytes match. Broader group not rerun by reviewer.
Available-family fallback under the recorded hard provider limit/quality-gates
policy; not cross-family evidence. Full reviews are in primary output/
source-contract-compiler-review.md and source-contract-correction-review.md.

Author final command: python -m pytest -q tests/test_discovery_contract.py
tests/test_discovery_quantities.py tests/test_discovery_execution_shapes.py
tests/test_discovery_exact_numbers.py tests/test_discovery_catalogue_shapes.py
tests/test_discovery_contract_compatibility.py tests/test_model_capacity.py
tests/test_model_capacity_transport.py tests/test_selected_model_authority.py
tests/test_interactive_http_agent.py tests/test_agent_protocol_capability.py
tests/test_protocol_encoders.py --tb=short --show-capture=no -rs.
703Windows36.29s/703actualLinux19.59s, zero skips. Linux via Ubuntu WSL
scripts/linux_oracle.py, Python3.11.16/git2.47.3/bubblewrap0.12.0.
Ruff on the three canonical changed files,423-file plugin build/import/mirror
and diff checks pass. Prior initial group690/690 is superseded by final703/703.

Next activation: existing connection publisher/preview and semantic provenance,
whole-current-descriptor snapshot capture, same-contract selection/request/budget/
settlement/usage/capacity consumers. Existing request-cap authority remains;
tariff-only sources require their separate explicit money-authority design.
Legacy four-unit/extra-price semantics must remain differential-tested as they
move onto the shared composition; do not remove them or hide a gate regression.
Native explicit choices, all-universe controls, full release and live model-picker
acceptance remain separate open work. No public payload, permissions, workflows,
gate exemptions, push or deployment changed in this slice.
