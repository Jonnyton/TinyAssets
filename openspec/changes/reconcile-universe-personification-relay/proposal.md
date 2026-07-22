## Why

The change `universe-personification` (proposed 2026-06-24, Codex-ADAPT 2026-06-25, PR
#1372 merged 2026-06-25) states as its load-bearing invariant that a chatbot bound by the
founder's OAuth **embodies** the persona and speaks in first person, **never relays**.

**That invariant was reversed by host directive on 2026-07-02 and is contradicted by
shipped production behavior.** Three independent sources agree, verified against
`origin/main` on 2026-07-22:

1. **Host directive** — `STATUS.md` `[filed:2026-07-02] RESHAPE`: universe intelligence
   becomes the single first-party personified agent and sole action-taker; the chatbot MCP
   demotes to onboard + relay. It names the reversal explicitly ("REVERSES
   `universe-personification` 'chatbot embodies, never relays' (live-falsified)") and
   instructs "Do NOT build more chatbot-embodiment."
2. **Design note** —
   `docs/design-notes/2026-07-02-universe-intelligence-relay-architecture.md` §3 documents
   *why* it was falsified: a behavioral contract delivered in a tool result is structurally
   indistinguishable from prompt injection, and careful hosts correctly refuse it. Embodiment
   moved to a first-party model (persona in the universe intelligence's own system prompt).
3. **Shipped code** — `tinyassets/universe_server.py:208` now instructs the exact opposite:
   *"You do NOT speak as the universe: … RELAY their message via `converse` and RENDER its
   own first-person reply verbatim — you are the connector, not the universe."* The landed
   as-built capability `openspec/specs/universe-personification-and-relay/spec.md` (baselined
   2026-07-19) codifies the relay model.

The change nonetheless still carries **11 unchecked tasks** written against the reversed
invariant. Since 2026-07-19 OpenSpec is this project's spec standard and agents are directed
to work from `openspec/changes/*/tasks.md` — so an agent following the process *correctly*
would build precisely what the host said not to build. This is the
`stale-backlog-rows-misdirect` failure mode (2026-07-21: 5 of 5 dispatched rows had false
premises) reproduced inside the system that replaced the backlog.

The most dangerous single row is task 4.1 — `sync-specs` into
`openspec/specs/universe-personification/spec.md`. Running it would write the embodiment
model into `openspec/specs/` alongside the as-built relay capability, making the reversed
model read as current spec truth.

## What Changes

- **Classify all 11 unchecked tasks** (reversed / survives / already landed / unclear), each
  with a one-line reason verified against `origin/main` — recorded in
  `design.md` §"Task-by-task reconciliation".
- **Retire `universe-personification`** by archiving it with a `SUPERSEDED` banner on every
  artifact and a per-task classification written into its `tasks.md`, so the design thinking
  is preserved and readable but no longer appears in `openspec list` as claimable work.
  Nothing is deleted.
- **Carry the surviving intent forward** as ADDED requirements on the landed
  `universe-personification-and-relay` capability — the four items that are still correct
  under relay and are **not** yet built:
  - authorization-before-voice, generalized past the current founder-only `converse` gate;
  - visitor actor binding + identity-tier gating (T0/T1/T2);
  - the anti-collision write path (reject profile-shaped / persona-dossier writes);
  - persona as a forkable `[composable]` default, reworded for first-party custody.
- **Record what already landed** so it is not rebuilt: the anti-collision *instructions*
  guard, honest fallback, and grounded first-person assembly all shipped inside `converse`.
- **Leave one host decision open** — the *ratified* narrative spec
  `docs/specs/2026-06-10-tiny-first-principles-spec.md:128` still states the reversed
  "never relays" invariant. It is out of this change's write-set and amending a ratified spec
  is a host call. See `design.md` §"Host decision required".

## Capabilities

### Modified Capabilities
- `universe-personification-and-relay`: adds the four surviving-but-unbuilt requirements
  rescued from the retired change. No landed behavior is modified or removed — the relay
  model, `converse` sandbox, learning path, and founder-only gate all stand as specced.

### Removed Capabilities
- `universe-personification` (the *proposed* capability, never synced to `openspec/specs/`):
  retired. Its correct content already lives in the as-built
  `universe-personification-and-relay` capability; its reversed content must not ship.

## Impact

- **Spec-only. No runtime code changes.** The relay behavior already shipped and is not
  touched here.
- **`openspec/changes/universe-personification/**`** → archived to
  `openspec/changes/archive/2026-07-22-universe-personification/` with banners + classification.
- **`openspec/specs/universe-personification-and-relay/spec.md`** — gains four requirements
  on `sync-specs`, after host approval. Not synced in this draft.
- **Out of write-set, flagged not applied:** `docs/specs/2026-06-10-tiny-first-principles-spec.md`
  §9 (host decision); `STATUS.md` and `AGENTS.md` (contended by #1506/#1507/#1501).
- **Gates:** opposite-provider review dispatched to Codex 2026-07-22 (verdict recorded in
  `design.md`). Draft PR — a spec reversal is a host-visible decision and must not merge
  unreviewed.
