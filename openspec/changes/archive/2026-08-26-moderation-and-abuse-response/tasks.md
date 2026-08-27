## 0. Split Record And Ownership

This change was split out of `complete-independent-full-platform-targets` on
2026-07-25 to discharge that change's task 6.3. The delta spec moved with
`git mv` (requirement text unchanged); the implementation tasks below moved
verbatim with their premise-verification notes.

**The capability is target-only.** Every task in section 2 describes intended
behavior that is not on `origin/main`. A task may be checked only by landed code
plus its named acceptance evidence — never by annotation, delegation, or a note.

- [x] 0.1 Record the split: `specs/moderation-and-abuse-response/spec.md` and the
  section-2 tasks now live here; `complete-independent-full-platform-targets`
  retains `packaged-tray-installation`, `node-authoring-and-autoresearch`, and
  `real-world-handoffs-and-outcomes` (split lane, 2026-07-25).
- [x] 0.2 Verify the split is collision-free: `gh pr view 1662/1667 --json files`
  (2026-07-25) shows neither draft PR touches
  `openspec/changes/complete-independent-full-platform-targets/` or this change
  directory, so moving the spec and tasks races nothing. Both PRs are OPEN drafts.
- [x] 0.3 Assign the ownership task 6.3 required, concretely:
  - **Implementation** — the moderation PR lane. `models.py`, `policy.py`,
    `service.py`, `__init__.py`, `tests/test_moderation_authority.py`, and
    `tests/test_moderation_service.py` are owned by draft PRs #1662/#1667 (or
    their successors). The unowned remainder (`store.py`, the next numbered
    storage migration, the `tinyassets/api/` routing, and
    `tests/test_moderation_concurrency.py`) is claimable by any provider that
    declares those files in a `STATUS.md` Work row first.
  - **Acceptance** — task 2.5's §14 proof, plus the AGENTS.md rendered-chatbot
    proof and a `scripts/mcp_public_canary.py --assert-handles` run for any
    user-visible surface change.
  - **Sync** — task 3.1 below, in the same lane that lands the last
    implementation task.
  - **Archive** — task 3.2 below, in that same lane.
- [ ] 0.4 Re-verify the section-1 fence before writing any fenced file: the fence
  is only valid while #1662/#1667 are open. If both are closed unmerged, check
  with `gh pr view` and `git log --diff-filter=A -- tinyassets/moderation/`,
  then update section 1 and claim the files in `STATUS.md`.
  - _recurring obligation_ — this stays unchecked; it re-runs at each write.

## 1. In-Flight Fence

**Do not write `tinyassets/moderation/` outside the named lane.** Verified
2026-07-25 by `gh pr view --json files`:

| File | Owner |
|------|-------|
| `tinyassets/moderation/__init__.py` | draft PR #1662 |
| `tinyassets/moderation/models.py` | draft PR #1662 |
| `tinyassets/moderation/policy.py` | draft PR #1662 |
| `tests/test_moderation_authority.py` | draft PR #1662 |
| `tinyassets/moderation/service.py` | draft PR #1667 |
| `tests/test_moderation_service.py` | draft PR #1667 |
| `tinyassets/moderation/store.py` | unowned |
| next numbered storage migration | unowned |
| moderation routing in `tinyassets/api/` | unowned |
| `tests/test_moderation_concurrency.py` | unowned |

Neither PR is merged, and neither claims the full service surface described in
task 2.2 — landing them does not complete this capability.

## 2. Moderation And Abuse Response

- [ ] 2.1 Add moderation persistence and invariants in `tinyassets/moderation/models.py`, `tinyassets/moderation/store.py`, and the next numbered storage migration.
  - _in-flight external (PR #1662)_ — `models.py` and `__init__.py` are on the #1662 branch. `store.py` and the storage migration are still unowned by any open PR. Migration numbering: `009_market_ledger.sql` is the highest on `origin/main`; 010-012 are taken by parallel lanes (012 = `012_authoring_sessions.sql`), so take the next free number at implementation time and do not renumber to close gaps.
- [ ] 2.2 Implement flag, queue, decision, appeal, recusal, moderator-eligibility, and audit services in `tinyassets/moderation/service.py` and `tinyassets/moderation/policy.py`.
  - _in-flight external (PR #1662, #1667)_ — `policy.py` on #1662, `service.py` on #1667. Neither is merged; neither claims the full service surface above.
- [ ] 2.3 Route moderation actions through existing canonical API handles in `tinyassets/api/` without adding an advertised MCP handle; add web-surface adapters only after the same service boundary exists.
  - _unbuilt-target_ — no open PR touches `tinyassets/api/` for moderation. Unowned. The advertised set to preserve is the canonical seven asserted by `CANONICAL_HANDLES` in `scripts/mcp_public_canary.py` and owned by `openspec/specs/live-mcp-connector-surface/spec.md`.
- [ ] 2.4 Add `tests/test_moderation_service.py`, `tests/test_moderation_authority.py`, and `tests/test_moderation_concurrency.py`, including distinct-flagger races, two-reviewer deletion, appeal independence, rate limits, and fail-closed authorization.
  - _in-flight external (PR #1662, #1667)_ — `test_moderation_authority.py` on #1662, `test_moderation_service.py` on #1667. `test_moderation_concurrency.py` is unowned; none of the three exists on `origin/main`.
- [ ] 2.5 Run §14 moderation proof with concurrent flag/decision/appeal traffic, queue-latency and write-contention bounds, anomaly-volume failure injection, and no lost or duplicated terminal decision.
  - _unbuilt-target_ — gated on 2.1-2.4.

## 3. Foldback

- [ ] 3.1 Sync `specs/moderation-and-abuse-response/spec.md` into
  `openspec/specs/moderation-and-abuse-response/` only when sections 2.1-2.5 are
  complete with their acceptance evidence.
  - _blocked on implementation_ — zero of the five tasks has landed code on
    `origin/main`. Syncing now would write target-only requirements into
    as-built truth.
- [ ] 3.2 Archive this change in the implementation landing lane and retire its
  `STATUS.md` row. Note that `openspec archive` also syncs deltas, so 3.1 and 3.2
  land together.
- [ ] 3.3 Notify the dependent lane: `complete-independent-full-platform-targets`
  task 5.5 (handoff/outcome disputes) reads `tinyassets/moderation/service.py`
  from this change. Confirm its `Depends` edge still names this change when the
  service module lands or is renamed.
