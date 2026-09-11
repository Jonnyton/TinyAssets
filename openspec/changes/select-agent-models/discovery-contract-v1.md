# Connection-authored discovery contracts — pre-build review

September 11, 2026. Proposed correction to the closed discovery seam, not
implemented, approved, deployed or a claim of universal CLI compatibility.

## Intent and existing homes

An owner can describe an unfamiliar connected source's catalogue, prices,
ranking, capacity and supported request ceilings as bounded data. A newly
discovered model on that source can enter the existing picker and actual
authorized agent route without adding provider-named Python callbacks.
Do not solve the channel ratchet by renaming functions, exemptions or baselines.

Reuse `write_graph(target=connection, operation=configure_provider_capability)`
and `connection_capabilities.descriptor_json` with kind `model_discovery`.
The primitive checker currently misses this explicit dispatch; source confirms
it in `universe_server.py` and `api/provider_capability.py`. No new MCP handle,
connection registry, credential path, provider-definition field or SQL column.
This nevertheless changes a public/storage contract and needs pre-build review.

Existing descriptor `{protocol, catalogue_url, benchmark_url?}` keeps its exact
validation and interpretation. Its protocol name resolves a bundled immutable
data contract through the same compiler used for new descriptors. No rewrite
of old rows or definition IDs. Generic decoding must differential-test the old
model/benchmark/cost/capacity results before replacing the old implementation.
The old functions remain only as compatibility callers where actually needed;
do not retain a second working decoder or move brand branches into another file.

## Versioned document and bounded interpreter

New closed outer document: `{schema_version: 1, catalogue_url, benchmark_url?,
contract}`. It has no `protocol` field. Mixing versions/legacy fields refuses.
The contract has these closed groups:

| Group | Declared data |
|---|---|
| transport | Existing inference wire-protocol ID and catalogue auth scheme; exact catalogue/benchmark path and query already present in the granted URLs. |
| catalogue | Rows pointer, model ID pointer, optional canonical join-key pointer, optional default-ID pointer, tools declaration, input/output modality pointers and positive context-length pointers. |
| completeness | Optional total-count and next-page pointers. A present count must equal row count; a present next page must be empty. No automatic pagination or response URLs. |
| prices | Price-object pointer; closed mapping of source field to unit-bearing component and exact decimal scale; required fields; bounded override-list pointer; recognized non-price condition keys. |
| benchmark | Optional rows/source/ID/score/time pointers, exact source ID and score scales; one comparable source, no source-name inference. |
| inference | Required body-key set, excluded model-ID literal prefixes/suffixes, price-cap output paths and exact scales, required constant request fields, and charge-component relationships. |
| capacity | Finite HTTP status-to-scope/reason mapping plus optional standard Retry-After interpretation. |
| usage | Optional exact total-cost pointer and scale; absent/invalid cost remains unknown. |

Selectors are JSON Pointer paths only: object keys and nonnegative array indices,
at most 16 segments/512 characters; no wildcards, expressions, templates, regex,
callbacks, imports, transforms that execute code, response-driven URLs or loops
other than bounded catalogue/override lists. Document <=64 KiB, <=128 extraction
fields, <=64 price components, <=32 capacity cases. Wire response retains current
transport size/deadline limits, plus <=10,000 model rows and <=128 overrides per
row. Exceeding a limit refuses the snapshot instead of publishing a prefix.
Unknown fields/version/operators refuse at publication and readback.

Exact scalar operations are finite: required/optional lookup, positive integer,
trimmed opaque identifier, string set, list-membership or boolean tools evidence,
minimum known positive contexts, and nonnegative decimal scaling. Amounts use
the existing exact integer-micro units. Scales are integer powers of ten within
the current bounded Decimal range; no floats, rounding, underflow-to-zero or
invented prices. Existing legacy JSON numeric benchmark/usage behavior must be
preserved by the legacy contract; new contracts specify accepted scalar encoding.
Optional unknown capabilities remain unknown, never a successful default.

## Price closure and inference ceilings

Every key encountered in a declared price object or override must be mapped or
an explicitly recognized non-price condition. Unknown keys make pricing
ineligible, including additional zero-looking charges. A malformed base or
override invalidates that component; valid overrides take the maximum, never
the current cheaper time/tier. Required fields absent at base remain unknown.
New contracts cannot declare a source unmetered; local/subscription unmetered
evidence continues to come from the installed executor/owned binding.

Inference operates on the already validated installed codec body. Cap mappings
inject only explicit approved price ceilings, using exact output units. Constant
fields are literal JSON scalars/objects with bounded depth/size. Output paths
must be pairwise nonoverlapping and must not overwrite model, messages, tools,
tool_choice, credentials, headers, endpoints, temperature or token limits.
No remote catalogue entry may supply these fields. Conflicting existing body
fields refuse rather than merge. Supported model indirection restrictions are
literal contract data; aliases cannot bypass a known restriction.

The existing `Interaction` structure stays the sole charge/capability policy:
required, excluded, ceiling, output-modality and bounded-extra components are
validated references to declared unit-bearing components. Missing caps or an
unrepresentable/unenforceable ceiling means ineligible, not "try and see".
Catalogue price <= permitted price is necessary but is not a spending grant.
Free-only remains exact zero ceilings; unknown usage never becomes zero usage.

## Availability and semantic trust — explicitly separate from authority

No schema can independently prove a remote service's privacy or charging
promise. The legacy adapter already trusts the owner-chosen host to implement
its pinned credential-filtered contract; a compatible JSON body alone proves
neither that promise nor account identity. Do not turn a caller's
`account_filtered=true` into trusted evidence.

New custom contracts therefore require explicit acceptance of their exact
normalized descriptor through the existing authenticated owner/admin action:
first preview validation returns its digest and scope/cost-enforcement summary,
then commit must supply that digest. Extend only new-version publication with
`preview: true` (no write) or `expected_descriptor_digest` (commit). The summary
states that the connected source, not TinyAssets, asserts its availability,
privacy and ceiling semantics. It names the exact endpoints and notes that the
contract is shared by all definitions using this owned connection. The agent
can compose it; the UI must not auto-accept it from remote catalogue content.
Existing legacy calls keep their shape and do not gain a mandatory preview.

This acceptance is configuration consent, NOT a credential, inference/spend
grant, nor independent validation of the provider's promises. No account IDs,
executor-tools flag or source-kind priority may come from the contract.
Subscription/local priority remains server-derived. Actual inference still
requires an accepted assignment/model, current grant/custody and price ceilings.

Replace the internal ambiguous `owner_filtered` truth projection with an
explicit availability basis for the policy boundary: `credential_filtered`,
`owner_accepted_contract`, or `unverified`. Legacy adapters retain their old
credential-filtered meaning. A custom source is eligible only after authenticated
transport to the exact accepted endpoint, the compiled structural checks and
all existing admission rules; its UI basis is "source contract accepted", never
"verified account availability". Unverified sources stay display-only. This is
an intentional reviewed distinction, not silently relabelling a declaration as
proof. No broader privacy guarantee is claimed than the owner's chosen source.

Acceptance is bound to normalized bytes including version, URLs and the whole
contract. Validate the submitted descriptor again under the metadata write's
existing BEGIN IMMEDIATE grant/resource fence; compare its expected digest.
No stored approval flag is accepted from a caller. The stored new-version row
exists only after this path; readers compute its digest from the validated
document. An unsupported contract never publishes a ready snapshot. Deletion,
revocation and owner/connection changes retain their current fail-closed rules.

## Ranking, capacity and freshness

Benchmarks join exact declared IDs; no model-name heuristics. Scores retain
source and scale identity, and source-supplied aware timestamp controls age.
Transport time cannot freshen old scores. Duplicate/ambiguous IDs are unranked;
future, missing, malformed or stale times are not fresh. Scores with a different
source/schema/scale identity are incomparable, even if source labels match.
Keep the existing stable ranked/unranked ordering and subscription/local
preference, allowing explicit user selection regardless of unknown ranking.

Capacity status mappings may emit only the existing bounded reason vocabulary
and scopes `model`, `account`, `unknown`. They do not create an authenticated
account identity. Current unknown/shared-capacity conservative fallback rules
remain; no rotating credentials or infinite retries. Usage decoding never
supplies an actual answering model; that remains the installed response codec's
receipt. Capabilities are local executor facts combined with advertised model
support, not remote permission to activate a missing tool loop.

## Integration and compatibility

- `ModelDiscoveryCapability` carries and round-trips the full validated optional
  versioned contract, preserving legacy descriptor serialization exactly.
- Publication/readback use one compiler. Snapshot context includes the entire
  descriptor and current authority, not just the old protocol string. Current
  context is checked after fetch and immediately before every actual attempt.
- Replace protocol-name lookups in discovery, selected-model constraints and
  HTTP usage/capacity with the captured compiled contract. No process-global
  mutable profile registration or caller injection of executable objects.
- Installed wire protocol still must match the definition and supply an agent
  codec. This descriptor does not teach arbitrary CLI syntax or invent support
  for an unknown inference wire format. Those remain separate provider-agnostic
  capability work, not a reason to report the whole feature complete.
- No migration of saved choice/order, journals, definition IDs or existing
  candidate digests. Snapshot-only availability/comparability fields are not
  added to the existing persisted ModelAccess document. Unsupported versions
  hold on rollback; old binaries must not reinterpret them as legacy profiles.
- Bundled legacy service metadata becomes declarative data only after the shared
  compiler can consume a user-supplied unfamiliar contract. This is substantive
  extensibility, not moving strings solely to satisfy the ratchet.

## Required tests and rollout evidence

1. Strict publication/readback, preview no-write, exact digest commit, owner/admin
   and grant fences, same-connection sharing, invalid contract no overwrite,
   legacy byte/behavior compatibility, unpowered configuration.
2. Frozen old decoder/constraint/usage/capacity differential tests over existing
   fixtures and malformed inputs; new fields never hide unknown charges.
3. A distinctly shaped unfamiliar catalogue and source name, with a new opaque
   model ID, goes through public configure -> discovery -> picker -> saved/current
   policy -> actual writer/router/HTTP tool loop. No preset registration or source
   code edit. Synthetic wires are supporting evidence, not live acceptance.
4. Stale/incomplete/unknown data, incompatible codec, missing or unenforceable caps,
   altered contract or revoked grant cannot yield an inference call. Price/cap
   field conflicts and descriptor-origin URLs never escape existing permissions.
5. Windows/Linux focused groups, plugin parity, unchanged neutrality ratchet and
   exact-head independent release review/CI before deployment. Authenticated SHA
   and canary after deploy; ordinary rendered app/connector conversation is final
   proof. Do not operator-edit workflows or approve a new account/grant for it.

Pre-build reviewer must challenge the availability-consent distinction, bounded
contract expressiveness, exact ceiling safety and compatibility. Approval of this
document is not proof that arbitrary providers work or that the picker is live.
