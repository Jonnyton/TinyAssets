# Discovery profile publication — proposed integration, not active

September 9,2026. The exact metadata home is already present:
`storage/outbound_connections.py` has `connection_capabilities`, keyed by
connection_id and capability_kind, storing a validated descriptor_json document.
Today its sole kind is realtime_voice. `api/provider_capability.py` and the
existing write_graph connection/configure_provider_capability branch publish it.
ProviderDefinition identity needs no extension. The primitive checker reports
no handler-map match for that operation, but direct source inspection confirms
the explicit universe_server branch; do not propose a duplicate action.

## Proposed bounded extension (pre-build review required)

Add model_discovery as another typed descriptor in the existing table, not a
second connection registry. Use a separate ModelDiscoveryCapability value type;
do not overload realtime voice's session_url or change its existing projection.
Closed fields: protocol, catalogue_url, optional benchmark_url. Initially the
protocol adapter is openrouter_user_models_v1 (the documented authenticated
user-filtered response), with the existing artificial-analysis benchmark decoder.
Opaque model releases remain remote data. This adapter name is not a core routing
brand list. Unknown wire protocols must be reported unsupported, not interpreted
as one of the known schemas or activated from remote executable instructions.

All configured URLs are canonical bounded HTTPS destinations. Publishing the
descriptor checks the existing active connection, GET scope and allowlist for
each destination in the same write transaction. It adds no endpoint, scope or
credential permission. Removing metadata leaves the underlying connection and
all serving assignments unchanged. Realtime_voice behavior remains unchanged.

Extend the existing configure_provider_capability operation only for this kind
with a definition_id reference. Its handler derives principal and universe from
authenticated request context, requires the same explicit owner/admin ACL used
by connect_compute, loads the verified definition from that universe, and derives
the actual grant/connection from it. Do not accept a caller-supplied connection,
grant or owner identity. Revalidate live grant/resource ownership and universe
scope at publication. This new kind must not depend on a currently functioning
serving LLM or a ready serving assignment: unpowered users need to configure it.
The existing realtime voice shape and current-serving resolution stay intact.
Inaccessible resources receive the existing uniform not_found envelope.

## Discovery evidence and execution boundary

read_http_discovery_document is implemented as internal transport only. It checks
server-derived context, current grant/resource, GET permission and exact URLs,
then uses the existing credential-blind resolver/broker. It reads one JSON
document, closes its proxy, rejects partial/redirect/malformed/oversized responses
and follows no response links. There is no external caller or profile activation.

The integration must load the current typed profile, read only its configured
destinations and compare profile plus current authority after the reads, before
publishing a snapshot. Initially fetch fresh rather than adding another durable
cache store. Carry source URLs, fetch time and a digest of the profile/current
connection authority into the snapshot; recheck at actual model authorization.
Never mark arbitrary same-schema JSON as verified account-filtered availability:
the protocol's account-filtered endpoint semantics must be established separately
from shape decoding. A global catalogue or caller-supplied owner_filtered flag
cannot substitute for that evidence. The precise compatible-endpoint verification
is a review question, not a solved claim in the transport implementation.

Benchmark as_of controls score freshness; a new HTTP fetch does not freshen old
scores. Missing benchmark coverage leaves models visible but unranked. Missing
or unsupported price components never become zero. Decoder output cannot assert
executor tool support, independent account capacity, assignment membership or
spending permission. The HTTP executor remains text-only until its real tool loop
is implemented; do not advertise HTTP full-agent readiness from catalogue tools.

## Acceptance before activation

- Existing realtime capability tests pass unchanged; owner/universe isolation and
  unpowered access use authenticated handler tests, including malformed/copied
  definitions, revoked grants and connection ownership changes.
- Idempotent configure/read/remove uses the existing table and leaves identity,
  grants, endpoints and assignment generation unchanged. Missing GET authority
  refuses publication, including optional benchmark URLs.
- Profile mutation or authority revocation during discovery prevents publication
  of a fresh snapshot. A schema-compatible global catalogue cannot claim filtered
  availability. Concurrent refresh is single-flight; async ingress offloads the
  blocking broker operation without spawning duplicate calls on cancellation.
- Fresh unknown model ids become selectable only through the separate per-attempt
  model validator and approved cost/capability limits. Prove actual execution,
  UI and rendered app behavior later; these unit fixtures are not that proof.
