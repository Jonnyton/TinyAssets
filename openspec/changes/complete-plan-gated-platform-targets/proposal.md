## Why

The 2026-07-22 full-coverage audit found three full-platform target groups with
no complete active OpenSpec owner, all three blocked on the same four unresolved
PLAN positions: canonical store, private-data placement, public tool surface,
and privacy-policy ownership. Blind transcription of the 2026-04-18 architecture
would have silently chosen a side on each.

All four positions landed on `origin/main` 2026-07-25 through the brain-OKF
PLAN foldback (#1761):

- **1A — canonical store is per-domain.** Postgres is canonical for catalog,
  ledger, inbox, and market. The OKF bundle is canonical for the commons. A
  user's brain organization is theirs to design; OKF is the default, not a
  mandate.
- **1B — private-data custody is OPEN RESEARCH**, deliberately. Four modes are
  under study (host machine, private universe brain, vault, platform-held) and
  **neither** the never-store nor the platform-store position may be treated as
  settled.
- **1C — minimal irreducible primitives.** A new top-level primitive ships only
  on a recorded *irreducibility finding*. Everything else lands as actions and
  parameters under the existing canonical handles, or as commons patterns.
- **1D — enforcement-only privacy.** Privacy *guidance* and taxonomies are
  seeded, remixable commons content; the platform owns enforcement boundaries
  only.

Three of these are decisions this change can now apply. The fourth (1B) is
settled *as an open question*, which is itself directive: portability, deletion,
and succession must be written custody-agnostic rather than waiting for the
research to close.

## What Changes

- Add a target-only `collaborative-catalog-and-editing` capability: a
  Postgres-canonical catalog that *references* rather than duplicates
  OKF-canonical commons knowledge (1A), compare-and-swap versioned writes,
  immutable revisions with revert-as-new-revision, the enforced wiki-open vs
  fork-and-PR content-class split, derived one-way GitHub export with
  no-privilege round-trip import, and visibility enforced at the catalog
  projection.
- Add a target-only `node-discovery-and-remix` capability: a single-call
  composite signal contract, ranking delegated to a user-buildable selector
  Branch reusing the shipped DESIGN-008 contract, visibility-filtered candidates
  and derived signal blocks, commons-equal ranking with no platform-origin
  boost, atomic remix-from-N over the shipped multi-parent attribution edge, and
  propose-then-ratify convergence with supersede-not-delete.
- Add a target-only `realtime-collaboration-presence` capability: presence as an
  advisory expiring signal that is never an authority boundary, versioned-row
  broadcast (not CRDT), visibility parity across presence and streams,
  degradable-by-design realtime, and subscription-bounded fan-out.
- Add a target-only `data-portability-and-deletion` capability, written
  **custody-agnostic** per 1B: per-item custody-mode labelling with inline bytes
  or a resolvable retrieval descriptor, export conformance in every custody mode,
  graceful deferral when a host-resident holder is offline, cross-principal
  privacy enforcement, deletion as direct erasure *plus* a verifiable obligation
  to every non-platform holder with unconfirmed items reported as unconfirmed,
  wiki-orphan survival of commons contributions, and identity detachment as
  resolution-time suppression over append-only ledgers.
- Add a target-only `platform-succession-and-feedback` capability: a machine-
  checkable successor roster over the SPOF inventory, succession that transfers
  operator authority **without** granting access to user content in any custody
  mode, phase-split executable bus-factor gates, staleness-detectable runbook,
  typed authenticated commons feedback filings, and external-tracker mirroring as
  a receipted outbound effect that is never the canonical queue.
- Record an explicit irreducibility call for every standalone RPC the 2026-04-18
  architecture named across §§15, 16, 21, 22, and 23. **Result: zero new
  top-level primitives and zero new advertised MCP handles.** Every behavior
  lands as an action or parameter under the seven canonical handles, or as
  seeded remixable commons content.
- Keep every requirement active and unsynced. Nothing here is built.

## Capabilities

### New Capabilities

- `collaborative-catalog-and-editing`
- `node-discovery-and-remix`
- `realtime-collaboration-presence`
- `data-portability-and-deletion`
- `platform-succession-and-feedback`

### Modified Capabilities

- None. Every delta is ADDED into a new capability. Where a target surface sits
  adjacent to shipped behavior — `shared-goals-and-convergence` exact-identifier
  common-node discovery, `wiki-commons` hash-guarded page deletion,
  `evaluation-outcomes-and-attribution` append-only attribution edges,
  `knowledge-retrieval-and-memory` OKF bundle export — this change specifies the
  target as *additive* and names the boundary in `design.md`. If an implementing
  lane finds it must change one of those shipped contracts, that lane authors the
  MODIFIED delta at that time; this change does not pre-emptively rewrite
  as-built truth.

## Impact

Implementation will affect the catalog/control plane, discovery and remix
surfaces, realtime transport, account lifecycle, operator succession process, and
the feedback intake path, plus their storage migrations, visibility enforcement,
concurrency proofs, and rendered-chatbot acceptance. It has hard read
dependencies on `identity-auth-and-access-control` (the permission actor and the
two orthogonal access axes), `wiki-commons` (typed filings, CAS patch/supersede,
scoped discovery), `evaluation-outcomes-and-attribution` (append-only attribution
and contribution ledgers), `shared-goals-and-convergence` (the user-buildable
selector contract), and `outbound-boundary-layer` (external mirroring as a
receipted effect).

This change is **target-only**. No requirement in it may be synced into
`openspec/specs/` and the change may not be archived until the corresponding
implementation and its named acceptance evidence land. `openspec archive` syncs
delta specs as a side effect; archiving this change early would write five
unbuilt capabilities into canonical as-built truth.
