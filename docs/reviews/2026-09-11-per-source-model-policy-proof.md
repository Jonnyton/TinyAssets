# Cross-source routing keeps each source's pricing rules

September11 2026 UTC, local feature tree against11fab59e; not deployed.
SourceModelPolicy captures each accepted source's Interaction and exact caps.
The advisory kernel validates complete/unique source coverage and checks each
model under its own requirements, retaining one shared ranking/explicit order
and existing capacity identity. Old single-policy callers keep their behavior.

Actual owned-plan collection no longer rejects differing Interaction shapes or
constructs a union of maximum caps. HTTP admission remains source-specific;
native/default priority and per-attempt serving authority remain unchanged.
Picker projection uses the same plan order. Display demotion removes both the
failed catalogue and its captured rules. No new API payload, storage column,
permission, workflow, live account or request is introduced.

Updated real-ledger collection fixture now requires both independently eligible
different-shape sources instead of the old refusal; its synthetic alternate
contract is not a newly installed remote provider. New test_model_source_policies
covers distinct prices/ranking, native defaults, explicit order/empty fallbacks,
account/model exhaustion, no cap/evidence borrowing and malformed rule coverage.

Command: python -m pytest -q followed by tests/test_model_source_policies.py,
tests/test_model_catalogue_collection.py, tests/test_model_options.py,
tests/test_model_options_composition.py, tests/test_model_options_api.py,
tests/test_served_model_preferences.py, tests/test_model_policy.py,
tests/test_model_capacity.py, tests/test_model_capacity_transport.py,
tests/test_interactive_http_agent.py, tests/test_selected_model_authority.py,
then --tb=short --show-capture=no -rs.
Windows252passed63.00s; actual Linux oracle via Ubuntu WSL252passed36.34s,
zero skips. Linux Python3.11.16/git2.47.3/bubblewrap0.12.0. Ruff clean;
runtime mirrors rebuilt. Independent exact-head review required.

Full custom source-contract publication/consumer, enforced accounting and
unfamiliar-source actual execution remain unfinished. Four neutrality loci
remain. No whole-release or live app acceptance claim; no push/deployment.
