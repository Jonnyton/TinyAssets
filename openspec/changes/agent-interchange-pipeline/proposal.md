## Why

Agent configurations are effectively unbounded, so a platform-maintained
starter catalog would become stale and constrain the very power users the
custom-agent system is meant to serve. TinyAssets instead needs a general,
safe pipeline that can import, inspect, remix, bind, and export arbitrary agent
definitions—including direct blends of public agents made by any users—while
making conversion loss and provenance explicit.

## What Changes

- Define exact native `agent-definition/v1` round-tripping as the canonical
  portability guarantee; private bindings and runtime state never enter it.
- Add private import staging that validates and scrubs source material before
  any explicit publish or universe-binding action.
- Define a versioned `agent-interchange-adapter/v1` contract for foreign
  formats, with structured conversion reports and content-bound receipts.
- Preserve safe unknown content in bounded namespaced extensions, refuse
  silent loss, and exclude suspected credentials or authority-bearing data
  from public definitions, exports, receipts, and logs.
- Make any public definition from any user eligible as a remix parent, with
  one child able to select, replace, remove, or add components across any
  number of creators while retaining verified component lineage.
- Keep adapters and common configurations as ordinary public, remixable,
  evaluable commons artifacts; do not create a starter catalog, format enum,
  privileged publisher, or new MCP handle.

## Capabilities

### New Capabilities

- `agent-interchange`: Canonical native import/export, private foreign-import
  staging, versioned loss-aware adapter reports and receipts, and universal
  cross-user multi-parent remix behavior.

### Modified Capabilities

- `universe-custom-agents`: Separate immutable portable lineage declarations
  from locally verified ledger projections and add stable parent-definition
  and component-content fingerprints so a multi-parent definition round-trips
  unchanged through an empty commons.

## Impact

The change depends on `universe-custom-agents` landing before archive and will
affect the custom-agent domain/API and storage boundary,
canonical `read_graph`/`write_graph` agent target payloads, governed Branch or
Engine OS adapter execution, public definition validation, provenance reads,
focused concurrency/security tests, and rendered connector acceptance. It
introduces no new top-level MCP handle and grants imported definitions or
adapters no ambient credentials, authority, provider access, or runtime
privilege.
