# Design — Spec Out Existing Platform

## Context

The platform was built before OpenSpec adoption. `openspec/specs/` contains 8
forward-vision specs (boundary-layer, data-commons, demand-side,
hardware-creation, paid-market-price-index-and-forwards, paid-market-training,
pooled-training-ownership, token-architecture) describing the *future*
platform; nothing specs the as-built one. Four in-flight changes
(`universe-creation`, `universe-personification`,
`collapse-live-mcp-surface-to-5-handles`, `brain-okf-canonical-store`) carry
delta specs for capabilities whose code is partly or fully landed. Baseline
truth source: `tinyassets/` on `origin/main` (the `workflow/` rename is
complete; `packaging/claude-plugin/.../runtime/tinyassets/` is a parity-guarded
byte mirror, never a second truth).

## Goals / Non-Goals

**Goals:**
- One as-built main spec per landed capability, grounded in actual code
  (file:line-verified during drafting), including as-built limitations.
- A named sync target for every in-flight change's deltas.
- Documentation-only, with one review-mandated exception: the Codex adapt
  verdict required the pre-existing red canary drift to land with the
  baseline rather than stay a red dependency, so `git diff` touches
  `openspec/**`, `AGENTS.md`, `STATUS.md`, plus the
  `scripts/mcp_public_canary.py` docstring/help/success-suffix and the
  `tests/test_mcp_public_canary.py` fixture (adds `converse`; no runtime
  behavior change — `CANONICAL_HANDLES` already enforced it).

**Non-Goals:**
- No new requirements, no behavior changes, no code edits.
- No speccing of the marketing website (`WebSite/`), desktop tray, or
  packaging/distribution surfaces (install surfaces, not behavioral
  capabilities; the plugin mirror is a build artifact).
- No rewriting of the 8 forward-vision specs — they stay as the future layer.

## Decisions

1. **Specs describe reality, including warts.** Known defects stay in the
   spec as as-built behavior with an explicit limitation note (shallow
   right-biased `_dict_merge`; graph-run `source_code` executing in-process
   via `exec()` behind the approval-hash gate, with `NodeSandbox` built but
   unwired; flat unencrypted JSON credential vault). Alternative — speccing
   the intended behavior — rejected: that recreates the aspiration/reality
   drift specs exist to kill. Fixes arrive as future MODIFIED deltas.
2. **As-built handle truth is 5 core + `converse` + `get_status`.** The
   canary's `CANONICAL_HANDLES` includes `converse`; "five handles" naming
   (AGENTS.md Hard Rule #12, canary docstring) is stale and is corrected to
   defer to the `live-mcp-connector-surface` spec.
3. **Baseline capability names win; in-flight deltas sync into them.**
   Mapping recorded here so archive-time sync lands in one file per domain:
   `collapse-live-mcp-surface-to-5-handles` → `live-mcp-connector-surface`;
   `universe-personification` → `universe-personification-and-relay`;
   `universe-creation` and `brain-okf-canonical-store` →
   `universe-lifecycle-and-soul` (splitting into a separate capability at
   sync time is fine if the delta grows past lifecycle scope). In-flight
   change artifacts are not edited by this change.
4. **Delta-then-sync, not direct main-spec writes.** Specs are drafted as
   `## ADDED Requirements` deltas inside this change and synced to
   `openspec/specs/` in the same branch — dogfooding the lifecycle the
   AGENTS.md convention now mandates.
5. **Fan-out drafting with per-capability verification.** One drafting agent
   per capability, each required to re-verify the mapper's file:line claims
   against code before writing; then a cross-family (Codex) accuracy review
   over the full spec set before the PR leaves draft-authoring.

## Risks / Trade-offs

- [Spec claims drift from code the day they land] → Every requirement was
  code-verified at draft time on `origin/main`; future changes must ship
  MODIFIED deltas (AGENTS.md gate: landed-but-unsynced deltas = failing gate).
- [Speccing warts could be read as endorsing them] → Limitation notes name
  the defect and point at the owning STATUS/wiki item where one exists
  (e.g. L4 reducer law row).
- [14 specs is a large review surface] → Cross-family Codex review gates
  accuracy; specs are per-capability files so review and future edits stay
  scoped.
- [In-flight changes may finish with different shapes than the baseline
  assumes] → The mapping in Decision 3 is a convention, not a lock; sync
  reconciles against whatever actually lands.

## Migration Plan

Docs-only: land via draft PR review → merge. No deploy, no rollback concerns.
On merge, the four in-flight changes inherit the Decision-3 sync targets.

## Open Questions

- Whether `demand-side` (forward-vision) should absorb the as-built
  `shared-goals-and-convergence` spec when bounties land, or stay layered
  above it — defer to the change that builds bounties.
