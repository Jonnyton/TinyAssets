# Interactive HTTP agent composition: local proof

Date: 2026-09-10 05:49 UTC. Environment: select-agent-models worktree on Windows;
actual WSL Docker Linux oracle (Python 3.11.16, git 2.47.3, bubblewrap 0.12.0).
Scope: integrated implementation on top of 73f49e357090c92e18878bd2be0c777f611825e6.

The ordinary writer bridge now invokes the HTTP agent on the capability-claiming
thread. Each inference uses fresh selected-model/tool capability admission,
finite accepted-binding launch allowance, full encoded accounting, and a durable
intent committed after consumption and before network dispatch. Known tool results
are committed before continuation; ambiguous effects or transport outcomes hold.
Native CLI execution is unchanged. OpenRouter cost parsing uses original decimal
tokens and rounds positive sub-micro costs upward rather than silently to zero.

Command (same test arguments on Windows and through scripts/linux_oracle.py):

```text
python -m pytest -q tests/test_agent_inference.py tests/test_interactive_http_agent.py tests/test_selected_model_authority.py tests/test_discovery_snapshot.py tests/test_api_key_http_provider.py tests/test_http_inference_lifecycle.py tests/test_writer_execution_receipt.py tests/test_universe_intelligence.py tests/test_agent_turn_journal.py tests/test_agent_chat_codec.py tests/test_agent_chat_portable_history.py tests/test_agent_price_guard.py tests/test_mirror_parity_gate.py --tb=short -rs
```

- Windows: 409 passed, zero skips, 27.66 seconds.
- Linux oracle: 409 passed, zero skips, 22.45 seconds; image
  `tinyassets-linux-oracle:ce0e83fb15a8`.
- Ruff for changed canonical runtime/tests: all checks passed.
- Plugin generator: 414 mirrored files and import probe passed; mirror-parity is
  included in both test runs above.

Composition tests exercise real authority, router, adapter, journal and engine
client validation with synthetic network seams. They are not live provider calls
or real tool effects. They cover four inferences beyond the former two-launch
limit, failed admission, failed intent/result persistence, owner-home revocation,
absent discovered tool support, tool cancellation/unknown outcomes, and a
statusless post-dispatch response retaining an indeterminate reservation.

Not complete: independent implementation review, typed candidate/account fallback,
saved/current selection consumption, clickable controls, deploy, protected SHA and
canary gates, and rendered ordinary app proof. No public picker activation or
checklist completion is claimed by these local tests.

## Supplemental legacy/authority regression group

Exact runtimeffbc918f, September10 05:55UTC. Command:

```text
python -m pytest -q tests/test_provider_assignment_admission.py tests/test_provider_served_router.py tests/test_provider_assignment_manifest.py tests/test_provider_request_capability.py tests/test_provider_router_diagnostics.py tests/test_agent_runtime_provider_call.py tests/test_provider_auth_router_quarantine.py tests/test_engine_tool_client.py tests/test_provider_router_bug029.py --tb=short -rs
```

Windows173passed/3skipped20.64s; same arguments in the actual Linux oracle image
above175passed/1skipped9.33s. Linux exercises the shared-reader concurrency and
bubblewrap cases skipped on Windows. Both skip the separately configured real
Codex integration (TINYASSETS_REAL_CODEX_TEST_UNIVERSE/SNAPSHOT absent); this is not
evidence that real CLI integration ran. No runtime files changed during review.
