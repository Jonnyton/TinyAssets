# Selected HTTP model execution — local integration, not app activation

September9,2026,22:46 UTC. Extends the reviewed connection-manifest shape and
discovery profile. No new public action, owner approval, private workflow edit,
provider SDK, model-release catalogue or connection identity mutation.

The real router now accepts a request-local ModelRef only under a server-issued
request carrier. It validates owner/agent revision, ready root/anchor, exact member
binding and live custody before catalogue IO and again afterward. Agent changes
during IO fail; source/profile/age and agent state are rechecked after slot
admission. ModelConfig cannot supply selection authority. The exact authorized
selection overrides it, or is cleared for legacy calls.

HTTP selection requires a fresh account-filtered profile, exact permitted model,
text capabilities, known context, complete permitted pricing and an executor
protocol that enforces those price components. OpenRouter max_price wire values
never round the accepted ceiling upward. The request does not merge plugins,
extra model arrays, provider overrides or other unbounded fields. Protocol evidence:
[OpenRouter provider selection](https://openrouter.ai/docs/guides/routing/provider-selection),
rechecked September9; max_price documents prompt/completion USD per million and
request/image USD. This is documentation plus synthetic wire proof, not a live
account charge guarantee or complete real catalogue price-component coverage.

An unspecified output budget is bounded by available model context; explicit
oversized requests fail without truncation. Reservation recognizes the exact
selected child rather than demanding the anchor binding. Its cost estimate is at
least the selected request's price-cap upper bound, using full model context for
input rather than a tokenizer guess, while retaining the legacy accounting floor.
Unknown actual cost remains unknown in ProviderResponse and conservatively
estimated in the existing ledger. Ready config projections include every accepted
binding; later explicit allowlists, including empty ones, still narrow selection.

42 new cases in tests/test_selected_model_authority.py include actual router and
HTTP encoder with synthetic proxy, new model without rebinding, config injection,
revoked request/grant/profile, stale/backwards clock, agent changes, missing/paid/
unknown pricing, context limits, tools hold, independent child after anchor
revocation, per-child settled budget and price-cap accounting. Test fixture uses
the existing server-only serving CAS: public v2 readiness remains held. It does
not establish the final app ingress or activation flow.

Verification on the working tree, September9 Windows Python3.14 and supplemental
Ubuntu Python3.11.15:

`python -m pytest -q tests/test_selected_model_authority.py tests/test_config.py
tests/test_open_serving_bind.py tests/test_provider_serving_binding.py
tests/test_provider_served_router.py tests/test_served_authority_shared_chain.py
tests/test_served_launch_accounting.py tests/test_serving_manifest_publication.py
tests/test_provider_assignment_manifest.py tests/test_model_discovery_capability.py
tests/test_discovery_snapshot.py tests/test_discovery_http.py
tests/test_catalog_decoders.py tests/test_model_policy.py
tests/test_api_key_http_provider.py tests/test_mirror_parity_gate.py --tb=short`

- Windows:442 passed,3 skipped,26.96s. Skips: shared-read overlap unsupported by
  Windows exclusive locks, POSIX bubblewrap, optional real-Codex fixture.
- Supplemental Ubuntu:444 passed,1 skipped,84.80s; one existing LangChain warning.
  Only the optional real-Codex fixture remains skipped. Uses the external-temp
  receiver-linux-proof.sh, not the required Docker oracle.
- Ruff and diff checks passed; rebuilt403 runtime mirrors and import probe passed.
- Required oracle initially refused: no running Docker Linux engine. Docker
  Desktop start --detach succeeded at22:46 UTC; actual readiness/oracle still to
  verify. Starting the test engine is not production deployment.

Independent execution/refresh review APPROVED exact83b19b49 after349s and
reproduced42 tests. Full verdict/disposition: selected-model-execution-review.md.
Docker readiness did not recover: fresh22:46:34 host logs report a startup crash
at dockerInference. The readiness query was cancelled and exact newly started
processes stopped; no data reset/deletion. The required Docker oracle is still
unavailable, not replaced by the supplemental Ubuntu result. No app
consumer, default/fallback policy persistence, CLI/local dynamic selection, HTTP
agent-tool continuation or picker is complete. Blocking discovery/HTTP broker IO
must be integrated off the event loop without moving thread-owned admission
locks between threads or trusting caller catalogue objects. Full-agent HTTP
requests are explicitly refused, and unselected v2 execution retains its hold.
This is not acceptance of a text-only substitute for the requested full agent.
