# Sealed request launch accounting

September 9, 2026. Implements the reviewed request-registry seam in
`connection-model-authority.md`; no candidate manifest, discovery, model switch
or new public API is activated. Legacy callers retain their two-launch limit.

The trusted future planner can seal one positive finite allowance on the existing
request registry. Repeating the same seal is idempotent, a different value is
refused, and an unsealed request cannot be sealed after a launch. Consumption
enforces the sealed value rather than a later caller's proposed larger limit.
The existing registry lock and process-bound, server-issued request identity
remain authoritative; no new token or credential scheme.

Router consumption now follows budget and slot admission, immediately before
provider.complete. Pre-launch refusal releases any created reservation. Provider
errors after launch retain existing conservative settlement. Zero-spend released
rows still count toward the existing rolling runaway guard; this patch changes
request launch count, not every resource-accounting convention.

Verification on the September 9 feature working tree:

- Windows Python 3.14: request capability + launch accounting + served router + mirror parity, 60 passed / 3 skipped (POSIX shared-reader concurrency, bubblewrap, optional real-Codex integration).
- Supplemental Ubuntu Python 3.11.15: same four files, 62 passed / 1 skipped (optional real-Codex fixture), 23.24s. Existing `output/receiver-linux-proof.sh` built a fresh environment; no Docker-oracle claim.
- Windows source-placement guards: `python -m pytest -q tests/test_provider_admission.py -k 'every_provider_dispatch or busy_refusal'`: 2 passed.
- Exact baseline regression: load ProviderRouter._call_routed from `git show 336adc95:tinyassets/providers/router.py` into the current module in memory, then run `tests/test_served_launch_accounting.py -k pre_launch_refusal`: all 3 fail with invocation count 1 rather than 0. Files are unchanged by this diagnostic. Restoring normal import in a fresh process gives all 4 launch-accounting tests passing.
- Ruff, mirror rebuild/import probe and diff checks passed.
- Additional post-Linux assertion checks zero-spend reservation settlement after slot/pre-launch refusals; Windows launch-accounting tests re-run below. The runtime is unchanged from the Linux run.

Tests prove finite launch accounting, not traversal of three distinct providers:
the six-launch case uses one recording provider and the same request carrier.
Real ordered candidate routing and safe tool continuation are still unfinished.
Exact-head Claude implementation review APPROVED d38d150a on September 9, 2026,
reproducing all four launch-accounting tests. See the adjacent review artifact.
The reviewer retained the documented rolling-window cost as a nonblocking concern.
Production verification remains outstanding; this slice is not activated routing.
