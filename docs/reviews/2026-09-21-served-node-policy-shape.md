# Served node policy edit: independent shape review

2026-09-21UTC, Claude Fable3265,185seconds, read-only source review of root
proposalacabb442. VERDICT: APPROVE; no blocking disagreement. Existing create/
add_node accepts policy, canonical update already validates/replaces/null-clears
atomically, owned author gate and run admission provider checks remain. Immutable
published snapshots and captured run definitions are not rewritten by patch.

Implementation adaptations required: retain malformed preferred_provider case
as canonical validation refusal rather than dropping coverage; correct sanitizer
comment to distinguish routing preference from authority; guidance must explain
editing does not bind a provider; delegate string/dict/null grammar entirely
to canonical coercer (no second served type grammar). Existing patch CAS absence
is unchanged, not a new release blocker. No broad field parity/default setter.

Evidence inspected: engine_mcp_server served sanitizer/patch route/connect_compute
guidance; api/branches staging/coercer/author gate; branches policy validation;
foreground_run_provider snapshot and admission; branch_versions write-once
snapshots; test_engine_mcp_write_graph_patch refusal test. Root retained full
peer result in local output; this artifact records the build-gating conclusion.
