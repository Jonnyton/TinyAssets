# Scoped model discovery transport — internal foundation, not live selection

September 9,2026,21:38 UTC. providers/discovery_http.py reads one configured
catalogue/benchmark JSON document through the existing exact scoped proxy. It
requires server-derived owner/universe context matching the verified definition,
live grant and connection, GET permission and the current endpoint allowlist.
The existing resolver and broker remain authoritative at dispatch; no direct
credential read, SDK, secret header, redirect or automatic retry was added.

One bounded request closes its proxy on success/failure. Only HTTP200 plus a
bounded JSON object is accepted:206/redirects, duplicate JSON fields, non-finite
constants, malformed/oversized bodies and malformed status envelopes fail loudly.
Errors do not include upstream response bodies, private details or URLs. Full
channel grants retain their already-approved host boundary, not a new global one.

Tests use a real ConnectionLedger, exact resolver and CredentialBlindBroker with
a synthetic network/credential fixture. They exercise context mismatches, revoked
authority, changes before resolution and immediately before dispatch, narrowed
endpoint scope, cleanup, status/error behavior and an unknown model appearing
across refresh without mutating connection/definition state or following links.
The fake network applies the existing endpoint validator; it is not live SSRF or
real-account evidence. New internal transport has no public caller yet.

Verification commands and environment:

- Windows Python3.14: `python -m pytest -q tests/test_discovery_http.py`:
  63 passed,1.51s.
- Windows Python3.14: same command with tests/test_catalog_decoders.py,
  tests/test_model_policy.py, tests/test_api_key_http_provider.py and
  tests/test_mirror_parity_gate.py:188 passed,4.42s, no skips.
- Supplemental Ubuntu Python3.11.15: same five files through the existing
  external-temp output/receiver-linux-proof.sh:188 passed,19.88s, no skips;
  one pre-existing LangChain warning. This is not a Docker-oracle claim.
  The first non-login invocation could not find uv; the login-shell invocation
  succeeded. Reusing the prior ephemeral environment later failed, so final
  evidence comes from the complete fresh-script run, not an empty command result.
- Ruff check/format and git diff --check passed. Canonical plugin build mirrored
  400 runtime files and the import probe passed.

The proposed metadata home is the existing connection_capabilities table, not
ProviderDefinition identity. Exact proposed API/storage extension and remaining
account-filtered evidence/cancellation gates are in discovery-profile.md in the
active change. That publication is not implemented; no grant, serving assignment,
owner choice, app workflow or production state was changed by these tests.
Independent discovery review is required before landing or integration activation.
