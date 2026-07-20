# Spec Out Existing Platform

## Why

Host directive 2026-07-19: the project is spec-driven development from here on,
and what is already built must be specced. The platform predates OpenSpec
adoption — `openspec/specs/` holds only forward-vision specs (future platform),
while the entire as-built platform (MCP surface, graph engine, auth, daemon,
wiki, market, …) has no requirement-level spec at all. Every future OpenSpec
change needs a truthful baseline to write deltas against.

## What Changes

- Backfill as-built capability specs for the landed platform — documentation
  only, **zero runtime behavior change**.
- Each spec records what the code actually does today (grounded in
  `tinyassets/` on `origin/main`), including known as-built limitations
  (e.g. shallow `_dict_merge`, in-process `exec()` node execution, flat
  unencrypted credential vault) — specs describe reality, not aspiration.
- Establish the reconciliation convention for the 4 in-flight changes: when
  they complete, their delta specs sync into the matching baseline capability
  (see design.md mapping) instead of creating parallel spec files.
- Existing forward-vision specs in `openspec/specs/` are untouched.

## Capabilities

### New Capabilities

- `live-mcp-connector-surface`: the public MCP entry point — canonical handle
  set (read_graph/write_graph/run_graph/read_page/write_page/converse +
  get_status) as thin routers, MCP prompts, legacy fat-tool deprecation,
  Cloudflare Worker front door, public canaries.
- `graph-execution-substrate`: BranchDefinition/NodeDefinition model, graph
  compiler (reducers, conditional edges), runs engine (SqliteSaver
  checkpointing, failure taxonomy, resume), node evaluation sandboxing.
- `universe-lifecycle-and-soul`: ULID universe identity, creation + OKF soul
  bundle seeding, governed `soul.edit` writes, confirm-gated reset.
- `universe-personification-and-relay`: first-party personified universe
  intelligence, chatbot-as-relay, consent-gated embodiment, sandboxed
  `converse` engine turn, fail-closed learning.
- `identity-auth-and-access-control`: WorkOS OAuth 2.1 resource server,
  anonymous-read/authed-write posture, pre-dispatch 401 write challenge,
  founder home auto-birth, two-axis authorization (visibility + ACL).
- `credential-vault`: per-universe typed credential store (as-built: flat
  0600-permission JSON), daemon-side resolvers, provider auth env overlay.
- `provider-routing`: role-based fallback chains terminating at local model,
  subscription-only default, pinning, quarantine, per-node policy, judge
  ensemble.
- `daemon-runtime-and-dispatch`: stateless dispatcher, file-locked lease
  claims, supervisor + healthcheck, singleton lock, persistent scheduler,
  idle-cycle single-flight, work-target registry.
- `wiki-commons`: shared markdown knowledge/coordination commons — draft →
  promote gate, typed filings (BUG/FEAT/DESIGN/PR), sha-guarded patch,
  trigger receipts, seed (not closed) category taxonomy.
- `knowledge-retrieval-and-memory`: hybrid RAG (SQLite KG, HippoRAG, RAPTOR,
  LanceDB singleton), hierarchical memory scopes, unified notes, bounded
  daemon learning-wiki.
- `shared-goals-and-convergence`: shared goal primitives, branch binding,
  canonical marking, run-canonical + leaderboard, selector branches,
  subscriptions.
- `community-patch-loop`: wiki-bug → investigation branch-task → Patch Packet
  write-back; auto-ship dry-run validator; flag-gated PR creation; ledger.
- `evaluation-outcomes-and-attribution`: NL-only run judging, node
  auto-promotion/flagging, KEEP rubric + conformance packs, outcome gates +
  attestation, append-only contribution ledger, attribution edges, selector
  leaderboard.
- `paid-market-economy`: pure market-microstructure library, escrow money
  path (flag-gated off), MicroToken conservation, node bids + write-once
  settlement, treasury take/split.

### Modified Capabilities

<!-- none — the 8 forward-vision specs are untouched; this change only adds -->

## Impact

- `openspec/changes/spec-out-existing-platform/specs/**` (delta specs), synced
  to `openspec/specs/<capability>/spec.md` (14 new main specs).
- No code, no tests, no runtime surfaces change.
- Future changes gain a baseline: deltas against these capabilities instead of
  unspecced prose; in-flight changes get a named sync target.
