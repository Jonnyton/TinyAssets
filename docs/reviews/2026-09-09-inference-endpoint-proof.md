# Preserve inference endpoints alongside discovery reads

September 9, 2026. Found while implementing connection-scoped model discovery.
The HTTP executor selected a connection's custom path only if it had exactly
one path of any method. Adding a GET catalogue/account endpoint made it fall
back to the protocol default and discard the already-granted custom POST path.
This affects arbitrary compatible endpoints, not just a named vendor.

The selector now considers only POST-capable endpoints. Multiple POST paths or
templates retain the existing protocol-default behavior; the broker still
authorizes the exact host/path/method. No grant, credential, model or workflow
is changed. No discovery or routing capability is enabled by this fix alone.

Evidence on the September 9 working tree:

- Before correction, `python -m pytest -q tests/test_api_key_http_provider.py -k 'discovery_reads or non_inference_endpoint'`: 5 failed, reproducing two discarded custom paths and three non-POST path selections.
- After correction, Windows Python 3.14: `python -m pytest -q tests/test_api_key_http_provider.py tests/test_mirror_parity_gate.py`: 49 passed, no skips.
- Supplemental WSL Ubuntu Python 3.11.15, same two files with `-p no:cacheprovider -q --tb=short`: 49 passed, no skips. Environment created by `output/receiver-linux-proof.sh`; not a Docker-oracle claim.
- `python -m ruff check tinyassets/providers/api_key_http_provider.py tests/test_api_key_http_provider.py`: passed.
- `python packaging/claude-plugin/build_plugin.py`: 397 mirrored files, import probe passed.
- `git diff --check`: passed.

Tests use real SQLite connections/grants and an injected HTTP proxy to inspect
the outbound wire request. They are not live-provider or broker-network proof.
Independent review, required CI and deployment verification remain outstanding.

Rollback: revert the isolated runtime/test commit through normal CI and deployment
if inference error rates or endpoint regressions appear; no storage migration or
user configuration rollback is needed. Do not rewrite connection grants to mask
an endpoint-selection regression.
