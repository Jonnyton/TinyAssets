# Repair-friendly model collection: local proof

September10 2026, Windows and actual Docker Linux. Implements the collection
portion of model-picker-surface.md adaptations4/5/6, not the public API or UI.

- Fixed typed discovery reasons distinguish revoked sources, missing GET/profile/
  endpoint access, incompatible protocols and expired observations. Existing
  ProviderUnavailableError handling remains compatible; remote exception text,
  credentials, grant ids and URLs are not public reason strings.
- Native host/role holds and absent executors are distinguishable. HTTP price
  component/contract incompatibility preserves discovered model facts without
  admitting those models into execution. Connection-level reasons appear on
  each affected model row, not merely on an unrelated missing-default record.
- prepare_owned_model_plan allow_empty is an internal display option. Default
  runtime/serving preparation still refuses a plan with no candidate. Complete
  owner/home/agent/assignment mismatch holds the display. Final source-specific
  revocation/expiry demotes only that source; independent native choices survive.
  Preferences are rechecked for display; no settings, assignments or workflow edits.
- Shared existing filtering/ranking remains in use; the display code does not
  authorize a launch. Public owner scope, registered-unaccepted/native inventory,
  catalogue response and enabled picker controls are still required.

Nine new collector tests use actual binding opt-in and owned discovery fixtures;
four additional discovery tests exercise typed causes at their source. The
two-contract test changes a collected interaction to faithfully exercise the
contract rejection seam; it does not claim another live network protocol exists.
Expiry uses the real final freshness check with an advanced fixture clock.

Final Windows Python3.14:

```text
python -m pytest -q tests/test_agent_inference.py tests/test_interactive_http_agent.py tests/test_selected_model_authority.py tests/test_discovery_snapshot.py tests/test_api_key_http_provider.py tests/test_http_inference_lifecycle.py tests/test_writer_execution_receipt.py tests/test_universe_intelligence.py tests/test_agent_turn_journal.py tests/test_agent_chat_codec.py tests/test_agent_chat_portable_history.py tests/test_agent_price_guard.py tests/test_mirror_parity_gate.py tests/test_model_capacity.py tests/test_model_policy.py tests/test_provider_router_diagnostics.py tests/test_provider_served_router.py tests/test_native_model_authority.py tests/test_model_preferences.py tests/test_model_preference_store.py tests/test_onboarding_model_preferences.py tests/test_model_capacity_transport.py tests/test_served_model_preferences.py tests/test_provider_serving_binding.py tests/test_provider_assignment_manifest.py tests/test_converse_handle.py tests/test_universe_server_mcp_structured_results.py tests/test_model_options.py tests/test_model_options_composition.py tests/test_compute_connection.py tests/test_discovery_http.py tests/test_model_catalogue_collection.py --tb=short --show-capture=no -rs
875 passed, 3 skipped, 6 warnings in 67.62s
```

The identical32-file group through scripts/linux_oracle.py, actual Docker
Python3.11.16/git2.47.3/bwrap0.12.0:877passed,1skipped,1warning in65.08s.
Windows POSIX reader/bwrap skips are covered on Linux. Both skip the unconfigured
real Codex account integration. Framework deprecations only. The two previously
known failing reset-inventory cases remain outside this focused group, unresolved.

Ruff changed canonical/test files passed,418 plugin mirrors/import probe passed,
mirror parity included in final runs, git diff --check passed. No deployed/live
claim. Independent exact implementation review remains required before landing.
