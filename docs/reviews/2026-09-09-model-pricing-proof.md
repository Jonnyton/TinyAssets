# Pricing applicability verification

September9,2026 UTC. Working tree over558b94a3; local only, no activation.

Claude shape40794: ADAPT271s. Corrected conditional override treatment and
output-modality gating as recorded in pricing-applicability.md. Implementation
review14602 completed ADAPT421s, independently reproduced268 tests. Its required
automatic cache-write correction is applied; full verdict/disposition is in
model-pricing-review.md. Corrected head is not independently reapproved.

Before review corrections, Windows Python3.14:494 passed,3 skipped in27.87s. Actual Linux oracle Python3.11.16,
Git2.47.3,bubblewrap0.12.0:496 passed,1 skipped in20.99s. Command group:

`python -m pytest -q tests/test_model_price_applicability.py tests/test_selected_model_authority.py tests/test_config.py tests/test_open_serving_bind.py tests/test_provider_serving_binding.py tests/test_provider_served_router.py tests/test_served_authority_shared_chain.py tests/test_served_launch_accounting.py tests/test_serving_manifest_publication.py tests/test_provider_assignment_manifest.py tests/test_model_discovery_capability.py tests/test_discovery_snapshot.py tests/test_discovery_http.py tests/test_catalog_decoders.py tests/test_model_policy.py tests/test_api_key_http_provider.py tests/test_mirror_parity_gate.py --tb=short -rs`

Same arguments passed to scripts/linux_oracle.py through the existing native
Ubuntu Docker route and process-local translated GIT_DIR/GIT_WORK_TREE documented
in linux-oracle-wsl-proof.md. Oracle93062 exit0. Windows83917 exit0. Windows
additionally skips shared-read file locking/POSIX sandbox; sole Linux skip is
optional real-Codex credential fixture.403 runtime mirror/import, Ruff and
git diff --check pass. No inference secrets or live account used in these tests.

Forty-two added cases distinguish omitted/malformed/unknown fees, paid extras,
cache/reasoning bounds, output media, conditional maximums, exact wire strings,
unsupported server indirections and actual message shape. Five exercise real
selected router/HTTP encoding with synthetic network and request launch counts.

Read-only public all-output catalogue schema simulation at23:49–23:50 UTC:
583 rows decode;19 free text-shape candidates,153 capability holds,379
not-confirmed-free,30 unknown-price and2 missing-price holds. This uses a
synthetic observation scope, NOT account-filtered eligibility. No remote
inference or provider preference change. Previously every row was excluded by
the mandatory four-price shape. Live account-filtered execution remains required.

Current sources rechecked:
[pricing schema](https://github.com/OpenRouterTeam/typescript-sdk/blob/main/src/models/publicpricing.ts),
[conditional overrides](https://github.com/OpenRouterTeam/typescript-sdk/blob/main/src/models/pricingoverride.ts),
[wire ceilings](https://github.com/OpenRouterTeam/typescript-sdk/blob/main/src/models/providerpreferences.ts),
[reasoning](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens),
[cache behavior](https://openrouter.ai/docs/guides/best-practices/prompt-caching).
No provider SDK added to execution. Full agent-tool requests must define their
own enforced pricing shape; this text-only contract is not that tool loop.

Additional author check while review14602 was running: a legacy Interaction
without ceiling_components still ignores a newly decoded known web_search fee.
Reproducer uses tests.test_catalog_decoders.row/decode/order with
pricing.web_search='0.001'; returns1 candidate. The selected dispatch uses the
new protocol contract and is protected, but generic advisory callers must not
silently claim eligibility for undeclared extras. Corrected after the frozen
review completed, with a regression. Cache-write cap-fit adds a second case.
Final focused171pass/0skip; Windows combined496pass/3skip in30.11s (16237 exit0).
Final Docker rerun36703 exit0:498pass/1skip in19.18s. The same optional real-Codex
fixture is the only skip. The two final cases bring added coverage to44.
