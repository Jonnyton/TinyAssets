# One connector, two uses, no patch

**Founder, 2026-09-24** (PR #3949, Hard Rule 3 and PLAN Providers): any LLM or
platform connects through vendor-neutral connectors the user's agent
configures, and a new vendor never needs a patch. There is one modular
connector system for compute and platforms. An LLM is just another universe
connection, and the connection-request notification is the setup UX.

This is Slice 1 of the vendor-neutral migration plan.

## The problem

A platform API and a model endpoint are both "an HTTPS endpoint, a key, and
an allowlist". The platform already has that primitive: the
`ConnectionLedger` connection, its grant, the credential-blind broker, and
the `connect_http` request rail. But an LLM could not use it in one step.
Today the owner (or their agent) has to:

- deposit the key with `connect_http`;
- register a compute definition with `connect_compute`;
- configure a priced `model_discovery` catalogue, which demands prices even
  for a free or flat-rate source;
- bind serving;
- confirm model access.

A source with no catalogue endpoint could not serve with tools at all. The
two wire encoders were code keyed by company names (`openai_chat`,
`anthropic_messages`). A platform that needs a version header on every call
made every workflow node retype it.

## What changes

1. **`connect` request action.** It takes the `connect_http` fields, plus
   `uses` (`call` and/or `model{wire, models, billing}`) and
   `constant_headers`. One owner answer deposits the key and creates the
   connection and grant. It records the uses, registers the model source,
   and serves the universe on the model when nothing powers the universe
   yet. The access is explicit and limited to the listed models, with
   free-only caps.
2. **`write_graph target=connection operation=configure`** edits the same
   non-secret fields on a connection the owner already holds. It is served
   to the app agent and to the public connector. It never touches the
   secret, endpoints or serving.
3. **Bundled wire dialects.** The two encoders become data documents
   (`providers/dialects/chat_messages.json`, `content_blocks.json`),
   resolved by structural name. The old names stay as read aliases, so
   stored rows resolve unchanged.
4. **Static model lists and `free`/`flat` billing.** A declared list feeds
   selection, reservation and execution through the existing snapshot
   shape, and needs no catalogue fetch. `metered` still goes through a
   priced `model_discovery` source contract.
5. **Constant headers applied by the broker**, after the node's headers and
   before auth, so they cannot replace the credential.

## Tier and review

**Tier 2.** The answer path deposits a secret into the vault, reusing
`connect_http` unchanged, and the broker, which is the credential-custody
component, now applies connection metadata. Both are credential custody. A
cross-family (Codex) review is owed before landing.

## Out of scope (later slices)

- Refreshable OAuth2 (slice 2).
- The command runner (slice 3).
- Moving CLI-subscription users (slice 4).
- The generic pool and fallback (slice 5).
- The first-power rail using `connect` (slice 6).
- Deleting vendor code (slice 7).
- Stored-value renames (slice 8).
- Removing a model use or header set through `configure`.
- A `block_tools` tool dialect for `content_blocks`.
