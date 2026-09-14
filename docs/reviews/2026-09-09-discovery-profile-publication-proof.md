# Discovery profile publication — local implementation, not deployed selection

September 9,2026,21:56 UTC. The independent discovery review approved internal
transport/decoders at4e21c3d5 and returned three profile-shape ADAPT corrections.
Those corrections were incorporated into discovery-profile.md before this code.

The existing connection_capabilities table now supports typed model_discovery
metadata. One capability-spec table owns kind, validator, value type, HTTP verb
and URL fields across configure/read. Voice behavior and storage layout remain
unchanged. Metadata adds no endpoint, credential, inference grant or preference.

The existing configure_provider_capability operation accepts definition_id only
for model_discovery. It requires authenticated admin plus exact ownership, loads
the content-address-verified universe-local definition, reuses compute grant
validation and fences expected grant identity under the metadata transaction.
It never asks for a serving assignment or functioning model. Removal is explicit
connection-wide metadata removal, leaving grants and definitions intact. Revoked
connections/grants cannot configure; retained metadata is not current authority.

The protocol-boundary contract fixes the user-filtered catalogue path and the
single documented output_modalities=all query. This query is a documented
refinement of the review's no-query proposal: a query-free request only lists
text-output models. The owner asked to see all available choices. No arbitrary
query/global catalogue substitution is admitted; GET query permission must
already exist. Optional benchmark URL uses its fixed path without query.
The owner chooses the allowed host; no model-release names are in this contract.
Bearer authentication is required for this protocol's account-filtered semantics.

Verification, Windows Python3.14 and supplemental Ubuntu Python3.11.15:

`python -m pytest -q tests/test_model_discovery_capability.py
tests/test_connection_capabilities.py tests/test_provider_capability_api.py
tests/test_realtime_voice.py tests/test_discovery_http.py tests/test_catalog_decoders.py
tests/test_model_policy.py tests/test_api_key_http_provider.py tests/test_mirror_parity_gate.py`

- Windows:279 passed,12.75s, no skips.
- Ubuntu via external-temp output/receiver-linux-proof.sh:279 passed,33.44s,
  no skips, one existing LangChain warning. Not a Docker-oracle claim.
- Forty new profile cases cover typed/idempotent read-write-remove, connection
  sharing, no definition/grant mutation, forbidden fields/global/partial URLs,
  optional benchmark boundaries, GET/auth/owner authority, expected-grant fencing,
  revocation between API read/write, unpowered API operation, tampered/copied
  definition refusal, and routing through the existing write_graph operation.
- Existing realtime voice tests passed unchanged. Ruff check/format, diff checks,
  401-file plugin mirror build and import probe passed.

No new MCP handle/signature/decorator shape; operation documentation now explains
both metadata kinds and explicitly does not claim selection or full-agent
readiness. Independent implementation review and CI are required before landing.
This is not live account discovery: profile-bound refresh/snapshot provenance,
current per-attempt model/cost authority, HTTP tools, policy storage/routing and
visible controls remain unfinished. Live price-component coverage remains open.
No operator workflow, grant, approval or provider selection was changed.
