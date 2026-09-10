# Real preference consumption and serving readiness

September10 2026, feature codex/select-agent-models. Built locally; not deployed.
Independent implementation review pending. No private owner workflow changed.

## Implemented path

Authenticated custom_agents bind_serving_provider now accepts strict optional
model_access through existing publication. Legacy provider-only payloads remain
unchanged. Serving enable discovers eligible candidates outside admission/SQL,
then rechecks exact agent, assignment, member custody, current home and preference
generation inside the mutation transaction. Missing/corrupt home preferences
return a structured refusal from the binding API.

Canonical converse accepts optional versioned model_choice, validates it before
home creation, and forwards it only for that turn. The real intelligence sink
captures saved/current preferences and assembles an advisory plan from accepted
owned members. Fresh per-member discovery/capability/price checks precede ordering;
every launch still uses existing exact authority. Native defaults participate
without fabricated model/context facts. Automatic mode prefers eligible native
subscription defaults, then the trusted protocol's ranked HTTP models. Explicit
choice overrides that order. HTTP readiness requires the enabled agent executor,
and cannot degrade silently to text-only operation.

One necessary clarification to the earlier shape: absent choices preserve legacy
assignments; a newly opted-in manifest with no saved row uses automatic generation0.
Otherwise enable would advertise a manifest that the next no-choice turn could
not consume. This follows design.md's new-connection automatic default and performs
no implicit manifest publication or migration of existing legacy bindings.

Private prepare_owned_model_plan also retains unfiltered eligible-source catalogue
entries and exclusion reasons for the eventual picker. It is not a public catalog
endpoint yet; metadata from failed discovery cannot masquerade as current models.

## Evidence and limitations

The28 new integration cases use real public binding opt-in, real serving enable,
stored preferences, actual intelligence/writer/router/HTTP adapter and journal.
No internal set-serving-row mutation or caller-supplied plan is used. Remote model
and engine-client wires are synthetic. One case exercises the canonical FastMCP
adapter with a genuine inert transport reserve claimed in the actual worker,
through model selection and tool execution to both structured/text reply channels.
Transport identity itself is a fixture, not a live OAuth/bearer proof.

Cases cover mixed native preference and explicit HTTP override, a freshly listed
better-ranked model, free-only exclusion of a higher-ranked paid model, current
automatic overriding an unavailable saved choice without saving, generation capture,
revocation before launch, corrupt saved rows, non-home legacy preservation,
activation preference races, malformed public model_access, disabled HTTP engine,
and absence of a SQL write transaction during discovery.

The actual default-config path exposed a context-accounting defect: the router
measured input without max_tokens, then added that encoded field after filling
the context. It now measures with the bounded output field already present before
choosing its final limit. Explicit requested limits remain subject to refusal;
no input is truncated. The canonical MCP test initially used a capability claimed
on the wrong thread and correctly refused; the fixture now supplies an inert
reserve that the real adapter claims on its worker. No auth check was relaxed.

Final Windows Python3.14 command:

```text
python -m pytest -q tests/test_agent_inference.py tests/test_interactive_http_agent.py tests/test_selected_model_authority.py tests/test_discovery_snapshot.py tests/test_api_key_http_provider.py tests/test_http_inference_lifecycle.py tests/test_writer_execution_receipt.py tests/test_universe_intelligence.py tests/test_agent_turn_journal.py tests/test_agent_chat_codec.py tests/test_agent_chat_portable_history.py tests/test_agent_price_guard.py tests/test_mirror_parity_gate.py tests/test_model_capacity.py tests/test_model_policy.py tests/test_provider_router_diagnostics.py tests/test_provider_served_router.py tests/test_native_model_authority.py tests/test_model_preferences.py tests/test_model_preference_store.py tests/test_onboarding_model_preferences.py tests/test_model_capacity_transport.py tests/test_served_model_preferences.py tests/test_provider_serving_binding.py tests/test_provider_assignment_manifest.py tests/test_converse_handle.py tests/test_universe_server_mcp_structured_results.py --tb=short --show-capture=no -rs
765 passed, 3 skipped, 6 warnings in 67.94s
```

Actual Linux oracle, same file/flag list:767 passed,1 skipped,1 warning in54.49s,
Python3.11.16/git2.47.3/bubblewrap0.12.0. Windows skips concurrent POSIX readers,
bubblewrap and the unconfigured real Codex account test; Linux skips only the
real account case. Warnings are framework deprecations. These groups exclude the
separate two failing full-reset inventory cases; that concern remains unresolved.

Ruff all changed canonical/test files: pass. Generated417 plugin files, import
probe and diff whitespace check: pass. Canonical converse's new optional argument
requires both-client rendered pre-merge proof; these synthetic structured-result
tests do not replace it. No canary/deployed-SHA or fresh app retest for this patch
has run. Clickable UI, general non-home policy controls, native explicit-model
discovery and safe cross-native continuation remain required, not completed here.
