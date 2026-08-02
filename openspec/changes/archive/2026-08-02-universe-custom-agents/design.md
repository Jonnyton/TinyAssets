## Context

TinyAssets already has three adjacent primitives: public branch definitions,
universe-scoped private state, and daemon identities/runtime instances. What it
lacks is the compositional artifact between them: a user-authored description
of an agent whose parts can be remixed independently and then bound privately
to one universe.

The public/private boundary is the central constraint. Agent definitions must
be useful as a global commons and portable between installations, while
credentials, provider accounts, channel endpoints, conversations, authority,
and runtime state must remain universe-scoped. The live MCP surface must also
remain exactly seven handles.

For v1, binding metadata uses the same custody mode already selected for its
universe's control plane. It contains references and configuration, not private
content, credentials, conversations, or effect payloads. This scoped choice
does not settle PLAN.md's open private-data custody question for other data.

This change intersects active security work. Arbitrary user code cannot run on
managed cloud before the Engine OS sandbox exists, and Slack/other outbound
effects cannot run before the outbound boundary layer provides consent,
credential isolation, and effect receipts. The core model may describe those
components and bindings now, but it cannot execute around those gates.

## Goals / Non-Goals

**Goals:**

- Make a custom agent a first-class, portable, public artifact with no
  platform-prescribed archetype.
- Allow every component to be replaced, extended, or credited to one or more
  parent definitions.
- Keep universe-specific configuration and all operational authority private.
- Make publication, remix, binding, inspection, and interchange available
  through targets on the existing graph handles.
- Give writes transactional retry safety and binding updates lost-update
  protection.
- Reuse branch, evaluator, skill, adapter, provider-policy, and resource
  references instead of cloning those systems.

**Non-Goals:**

- Execute arbitrary user code in managed cloud.
- Send or receive live Slack/other external-app traffic.
- Copy provider credentials or app secrets into an agent record.
- Replace the daemon runtime, branch execution substrate, provider router, or
  boundary-layer adapter system.
- Define a preferred OpenClaw, Hermes, coding-agent, or TinyAssets archetype.

## Decisions

### 1. Definition, binding, and runtime are distinct

An `AgentDefinition` is public, immutable, and remixable. An `AgentBinding` is
private to a universe and gives a definition a local role, goals, authority
references, resource references, provider policy, channel addresses, and
configuration. A daemon runtime instance is the eventual executor of a
binding.

This follows the existing branch-definition/runtime split and makes the
public/private boundary inspectable. Extending `author_definitions` directly
was rejected because that table combines legacy soul identity and runtime
metadata and only supports one parent.

### 2. Definitions use a small extensible component envelope

A definition has `schema_version=1`, name, description, tags, and a `components`
object. Component keys are user-chosen stable slugs; each component value is a
JSON object with a required `kind` and arbitrary JSON-compatible configuration.
The platform does not reserve a mandatory component taxonomy. Common presets
can choose names such as `identity`, `reasoning`, `memory`, `tools`,
`workflows`, `evaluation`, and `channels`, while power users can add their own.

The envelope is bounded to 64 components and 256 KiB of canonical JSON.
Component keys match `^[a-z][a-z0-9_-]{0,63}$`. Objects containing
secret-bearing field names such as `password`, `api_key`, `access_token`,
`refresh_token`, `client_secret`, `private_key`, or `credential` are rejected
recursively. References such as `resource_binding_id`, `provider_policy_id`,
and `adapter_ref` are allowed because they name governed records rather than
contain secret material.

A rigid platform-owned component enum was rejected because it would put an
artificial ceiling on expert configurations. Unbounded opaque blobs were
rejected because they are not safely inspectable or portable.

### 3. Publication is immutable; evolution creates a successor

Each publish/remix/import mints `agent_<ULID>`, records the authenticated
author, computes a SHA-256 fingerprint over the normalized portable content,
and never updates that row. User edits therefore publish a successor, normally
with lineage to the earlier definition. Optional idempotency keys are unique
per author and return the already-created result on retry.

Immutable records make forks reproducible and prevent a public source from
changing underneath its downstream remixes. Mutable "latest" definitions were
rejected for that reason.

### 4. Component lineage is server-validated and multi-parent

A remix supplies the complete child component plus zero or more source records
for that component. Every source names an existing public parent definition
and component key. Credit shares are finite numbers in `[0,1]`, and the shares
for one child component cannot exceed `1.0`; any residual belongs to the child
author.

The server writes the child definition and all lineage rows in one transaction.
Because parents must already exist and definitions are immutable, a child
cannot become its own ancestor. The service still computes lineage depth and
rejects a chain beyond 50 generations, matching the existing attribution
bound. A dedicated `agent_component_lineage` ledger is used rather than
coercing component edges into the branch/node-only attribution schema.

### 5. Bindings are private, revisioned, and reference governed resources

An `AgentBinding` stores the target universe, definition ID, private display
name, role, goals, component configuration, authority/resource/provider
references, and channel-address references. It never stores raw credentials,
message history, or effect payloads. Reads and writes require current
read/write universe authority respectively; unauthorized reads return the same
not-found envelope as an absent binding.

Binding updates use a caller-supplied `expected_revision` compare-and-swap and
increment the revision atomically. This prevents two chatbot/app sessions from
silently overwriting each other. A binding update may point to a successor
definition, enabling controlled rollout without mutating public history.

### 6. Portable export is the public definition; import is verified publication

Reading one public definition returns a canonical `portable_definition`
containing its schema, content fingerprint, components, and lineage
declarations but no server-local binding data. Import verifies the fingerprint
when supplied, validates all content again, and publishes a new local
definition. Locally resolvable lineage becomes verified ledger edges;
unresolvable external origin descriptors remain informational and confer no
attribution credit.

### 7. Existing MCP handles gain targets, not another handle

`read_graph` gains `agents`, `agent`, `agent_bindings`, and `agent_binding`.
`write_graph` gains `agent` and `agent_binding`, with an `operation` and
`payload_json`. Public definitions can be listed/read anonymously. Binding
reads are universe-authorized. All writes remain behind the existing
`write_graph` OAuth challenge and then enforce actor/universe authorization in
the domain API.

The router delegates to `tinyassets.api.custom_agents`; it contains no storage
logic. Adding a dedicated `agents` MCP handle was rejected because agent
composition is reducible to graph artifact reads/writes and would violate the
seven-handle contract.

## Risks / Trade-offs

- **[Extensible JSON can contain unknown semantics]** → Persist and remix it,
  but execute only component kinds supported by governed runtime adapters.
- **[Secret-name filtering cannot detect every disguised secret]** → Make
  references the only supported credential path, reject common secret fields,
  keep definitions public by contract, and add security-focused tests.
- **[Public immutable records accumulate]** → Use bounded list reads and
  content fingerprints now; retention/index policy can be added from measured
  load without changing the artifact contract.
- **[A binding may reference a dependency not installed on one host]** →
  Preserve portability and report unresolved references explicitly at
  activation time; do not silently drop them.
- **[Channel intent may look executable before the boundary layer lands]** →
  Return `configured`, not `connected`, and expose no send/run operation in
  this change.

## Migration Plan

1. Add idempotent SQLite tables and indexes. Existing data is untouched.
2. Ship the domain/API code and local tests with no live runtime activation.
3. Add the graph-handle targets while preserving the exact seven advertised
   tools.
4. Run focused tests, full relevant regression tests, the handle drift guard,
   and an independent security/diff review.
5. After deployment, run the public canary and a rendered chatbot acceptance
   conversation before treating the public surface as accepted.

Rollback removes the router targets and code while leaving the additive tables
intact. Their rows are inert and can be retained for a forward fix; no
destructive rollback migration is required.

## Open Questions

- Which common presets should TinyAssets publish first? This is commons
  curation, not a schema decision.
- When the boundary layer lands, should a single binding expose several
  channel identities or use one child binding per identity?
- Which external-origin identifier becomes the cross-installation verification
  standard? Until then, only locally resolvable lineage earns verified credit.
