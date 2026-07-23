---
title: Memory-scope Stage 2c flip-readiness checklist
date: 2026-04-27
author: dev-2
status: pre-flip checklist (not yet dispatched — depends on 30d clean watch ending ≥2026-05-16)
load-bearing-question: What besides setting `TINYASSETS_TIERED_SCOPE=on` is required to flip Stage 2c safely, and what does rollback look like if it regresses?
relates-to:
  - docs/design-notes/2026-04-15-memory-scope-tiered.md (canonical tiered-scope spec)
  - docs/exec-plans/completed/2026-04-16-memory-scope-stage-2b.md (2b ship plan; 2c is the §9 deferred set)
  - tinyassets/retrieval/router.py (flag reader + assertion implementation)
  - tinyassets/memory/scoping.py (MemoryScope + NodeScope shape)
  - tinyassets/api/runs.py:1118 (`get_memory_scope_status` self-audit tool)
audience: dev (executor), navigator (observer), lead (gate)
---

> **Liveness verified:2026-07-22 — ACTIVE: STATUS.md still carries the `Memory-scope Stage 2c flag` row (`monitoring`). Triage: `docs/audits/2026-07-22-exec-plan-liveness-triage.md`.**

# Memory-scope Stage 2c flip-readiness checklist

## 0. Status + 30d watch math

- **Stage 2b.3 landed:** commit `e25bd3b` (`Memory-scope Stage 2b.3: four-tier assertion + flag + ACL fixture`) on **2026-04-16 21:09 -0700**.
- **30d clean window starts:** 2026-04-16.
- **30d clean window ends (earliest flip date):** **2026-05-16**.
- STATUS Work row currently classifies state as `monitoring` with `30d clean` as the gate. Today (2026-04-27) is day 11 of the watch. **20 days remaining.**

## 1. What flipping the flag actually changes

Per `docs/design-notes/2026-04-15-memory-scope-tiered.md` §6 + `tinyassets/retrieval/router.py:359-491`:

| Surface | Flag OFF (today) | Flag ON (post-flip) |
|---|---|---|
| `tiered_scope_enabled()` | `False` | `True` |
| `assert_scope_match(row, scope)` | Drops row only if `universe_id` mismatch (Stage 1 hard invariant). | Drops row if ANY pinned tier mismatches: `universe_id` (always), `goal_id`, `branch_id`, `user_id`. |
| `_drop_cross_universe_rows(result, scope)` | Filters by `universe_id` only; logs warn-mode mismatches. | Filters by all 4 tiers (when caller pinned); logs continue (warn → still warn at Stage 2c per design §6 "warn-and-drop becomes hard-fail"). |
| `get_memory_scope_status` MCP tool | Returns `tiered_scope_enabled: false`, `active_enforcement_tiers: ["universe_id"]`, includes caveat about goal/branch/user not enforced. | Returns `tiered_scope_enabled: true`, `active_enforcement_tiers: ["universe_id", "goal_id", "branch_id", "user_id"]`, drops the off-flag caveat. |
| Caller-pinned-but-row-untagged | Row passes through (legacy/universe-public rows). | **Same** — row passes through (NULL/empty sub-tier values explicitly allow legacy rows). |
| Private-universe `universe_acl` Layer-1 reject | ACL functions exist (`grant_universe_access`, `universe_access_permission`, `universe_is_private`) but read paths do NOT call them. | **No automatic change** — design §6 line 278 says "Private universes actually reject cross-universe reads" but the wiring of the ACL into read paths was deferred. **Verify before flip:** does flipping the flag wire the ACL reject, or does it require additional code? See §4 below. |
| `assert_scope_match` warn-vs-hard-fail | warn-and-drop. | **Per design note: hard-fail.** Per current router code: still warn-and-drop (the function returns False, caller drops; no exception raised). **Mismatch with design §6 line 278.** See §4 below. |

## 2. Tests that must pass with flag on

Pre-flip dev ritual: run these test files with `TINYASSETS_TIERED_SCOPE=on` set in env. All currently green per file inspection.

- `tests/test_memory_scope_stage_2b3.py` — already has `monkeypatch.setenv("TINYASSETS_TIERED_SCOPE", "on")` cases for: 4-tier assertion, mismatch drop, NULL passthrough, ACL fixture. Covers the core flip semantics. **Required green.**
- `tests/test_memory_scope_stage_2b.py` — write-site threading tests; flag-agnostic by design (writes always tag regardless of flag). **Required green** (regression check that 2b.2 behavior unchanged).
- `tests/test_memory_scope_stage_2a.py` — schema/ACL foundation. **Required green.**
- Full retrieval test suite (`tests/test_retrieval*.py`, `tests/test_router*.py` if any retrieval-router-flavored) — flag should not regress existing retrieval behavior. **Required green.**
- `tests/test_self_auditing_tools.py` — exercises `get_memory_scope_status`; tool should reflect flag-on state correctly post-flip. **Required green.**
- Full `pytest` suite — Stage 2b's "regression: full suite green with `TINYASSETS_TIERED_SCOPE=0`" criterion (exec plan §7) gets a sibling: full suite green with `TINYASSETS_TIERED_SCOPE=1`. **Required green.**

**Pre-flip command (verifier-owned):**

```bash
# Targeted gate
TINYASSETS_TIERED_SCOPE=on pytest tests/test_memory_scope_stage_2b3.py tests/test_memory_scope_stage_2b.py tests/test_memory_scope_stage_2a.py tests/test_self_auditing_tools.py -v

# Full-suite gate (if targeted is green)
TINYASSETS_TIERED_SCOPE=on pytest -q
```

If full-suite reveals failures: those tests assumed flag-off behavior implicitly. Each one is either (a) a real regression to fix, or (b) needs a `monkeypatch.delenv("TINYASSETS_TIERED_SCOPE", raising=False)` guard. Tag with `# Stage 2c flip discovered:` so the audit trail is clear.

## 3. Callers that branch on flag state

Surfaced via grep `TINYASSETS_TIERED_SCOPE|tiered_scope_enabled` across the canonical tree:

| Site | Behavior gated | Action on flip |
|---|---|---|
| `tinyassets/retrieval/router.py:367` | `tiered_scope_enabled()` reader (canonical). | None — reads new value naturally. |
| `tinyassets/retrieval/router.py:408` | `assert_scope_match` early-out for sub-tiers. | None — naturally activates sub-tier checks. |
| `tinyassets/retrieval/router.py:451` | `_drop_cross_universe_rows` log tag. | None — log tag flips to `tiered_flag=on`. |
| `tinyassets/api/runs.py:1140-1185` | `get_memory_scope_status` self-audit tool — derives `active_enforcement_tiers`, caveats, and next-steps from flag. | None — naturally returns the on-state shape post-flip. **Verify chatbot output:** the "Set TINYASSETS_TIERED_SCOPE=on" next-step suggestion should disappear; chatbot consumers may have memorized "the suggestion to set the flag" — communicate the change. |
| `tinyassets/universe_server.py:535` | Docstring reference only — no runtime branch. | None. |
| `tinyassets/memory/scoping.py:21,244,322` | Docstring references only. | None. |
| `tinyassets/daemon_server.py:3401` | Comment reference. | None. |
| `tinyassets/knowledge/knowledge_graph.py:245` | Docstring reference. | None. |
| `tinyassets/ingestion/indexer.py:59` | Docstring reference. | None. |

**No production code branches on the flag besides the router + self-audit tool.** The flip surface is small and localized.

## 4. Open inconsistencies between design + code (RESOLVE BEFORE FLIP)

Two gaps where current code does NOT match the design's "Stage 2c on" semantics:

### 4.1 ACL hard-reject for private universes is not wired into read paths

**Design (§6 line 278):** "Private universes actually reject cross-universe reads."

**Code today:** ACL functions exist (`tinyassets/daemon_server.py: universe_is_private, universe_access_permission, grant_universe_access, list_universe_acl`) but no read path consults them. Flipping the flag does NOT wire the ACL — it only turns on sub-tier row filtering.

**Decision needed before flip:**
- Option A — flip flag with ACL still un-wired; defer ACL hard-reject to Stage 2d. Honest scope; doc the deferral. **Recommend.**
- Option B — wire ACL reject into the universe-load path before the flip. Adds dev work to the 2c arc. Larger blast radius.

### 4.2 Assertion is warn-and-drop, not hard-fail

**Design (§6 line 278):** "Stage 1 assertion becomes hard-fail instead of warn-and-drop."

**Code today:** `assert_scope_match` returns bool; `_drop_cross_universe_rows` drops without raising. Flipping the flag does NOT change this — it expands the *fields* checked but keeps drop-style behavior.

**Decision needed before flip:**
- Option A — flip flag with assertion still warn-and-drop; defer hard-fail to a later commit gated on "zero scope-mismatch warnings for 30d." **Recommend** — drop-style is forgiving during cutover; hard-fail risks crashing on legacy rows under load.
- Option B — flip flag AND change assertion to hard-fail in same commit. Risk: any unseen legacy row with mistagged scope columns crashes a live retrieval; high blast radius.

**Both 4.1 and 4.2 are calibration choices.** The design described an aspirational end state; the code shipped a flag-only flip. Recommend documenting the gap explicitly in the flip commit message + STATUS.md row, then deciding 2d separately.

## 5. Pre-flip observability checklist

The 30d clean watch is monitoring `retrieval.scope_mismatch` warnings in `activity.log` per `_drop_cross_universe_rows` (router.py:467). Before flipping:

- [ ] Confirm `activity.log` has been retained for the full 30d window (no rotation).
- [ ] Run `grep "retrieval.scope_mismatch" .agents/uptime.log activity.log` (and per-universe activity logs) — confirm zero warnings since 2026-04-16. Per `get_memory_scope_status` MCP tool: `recent_scope_mismatch_warnings` should be empty.
- [ ] If ANY mismatch warning fires during the watch window: do NOT flip. Investigate the mismatch (most likely a singleton-bleed or 2b write-site threading gap per router.py:484-491). Flip only after the gap is closed and a fresh 30d clock starts.
- [ ] Sporemarch + Ashwater (or current canonical fantasy fixtures) test runs: assert zero behavior change with flag-off, then assert zero behavior change with flag-on. Per Stage 2b acceptance criterion §7 line 119.

## 6. Flip procedure

1. Verifier runs §2 test gate: targeted + full suite, both with flag on. Block on green.
2. Resolve §4 inconsistencies (recommend: doc as deferred to 2d, no code change).
3. Land a 1-line commit: change AGENTS.md "Configuration" table default from `off (Stage 1 monitoring; flip to on at Stage 2c per task #19)` to `on (Stage 2c shipped <date>)`. NO router-code change — the flag still defaults to "off" if env var unset (the router reads `os.environ.get("TINYASSETS_TIERED_SCOPE", "off")`); the *deployment surface* (tray, container env, deploy scripts) is what flips.
4. Update tray + container env to set `TINYASSETS_TIERED_SCOPE=on` by default. Surfaces:
   - `deploy/*` env files (per-environment config)
   - `fantasy_daemon/__main__.py` if there's a default-env injection
   - tray-runtime preferences `~/.tinyassets/preferences.json` if relevant
   - GitHub Actions deploy step (rotates env to host)
5. Restart daemon + canary check (`get_memory_scope_status` should return `tiered_scope_enabled: true`).
6. Watch `retrieval.scope_mismatch` rate for 7 days post-flip. If any non-zero rate → §7 rollback.
7. Update STATUS.md Concerns row from `monitoring` to `landed` (or delete row per the "deletion is as important as addition" rule).
8. Move this doc to `docs/exec-plans/landed/`.

## 7. Rollback procedure (if metrics regress)

The flag is the rollback knob. No code revert needed; just flip the env var back.

1. Set `TINYASSETS_TIERED_SCOPE=off` in deployment env.
2. Restart daemon (TinyAssets MCP server). Per `feedback_restart_daemon` memory: tray is the canonical restart path; auto-comes-back in ~2-5s. Verify via `POST /mcp initialize`.
3. Confirm via `get_memory_scope_status` MCP tool: `tiered_scope_enabled` should report `false`.
4. Open a STATUS.md Concerns row documenting the regression observation + rollback timestamp.
5. Investigate the regression cause:
   - Sub-tier row filter dropping rows that should pass? Inspect the dropped row's sub-tier values; usually a write-site that didn't thread MemoryScope correctly (Stage 2b tasking gap).
   - Increased latency from the extra tier checks? Profile `_drop_cross_universe_rows`; the 4-tier loop is per-row Python overhead. If hot, optimize before re-flipping.
   - Any caller crashing on a `False` return when they expected silent passthrough? Audit the caller; warn-mode shouldn't crash callers, but a downstream `assert` could.
6. Restart the 30d clock (or shorter, if the diagnosis surfaces a tight class of fix).

**Rollback is cheap by design.** This is exactly why the flag exists — Stage 2b shipped the scaffolding; 2c is observation-driven.

## 8. Out-of-scope (deferred to Stage 2d)

- ACL hard-reject in read paths (§4.1).
- Assertion hard-fail mode (§4.2).
- Per-tier drop counts in `retrieval_stats_by_tier` field of `get_memory_scope_status` (caveat at runs.py:1158 — "Stage 2b.3 not yet instrumented; per-tier drop counts will appear in Stage 2c"). **Recommend instrumenting in 2c if dev-cycles allow** — it makes future regressions diagnosable. Otherwise defer.
- Narrow-slice retrieval narrowing — ships behind the same flag but is a separate dispatch (retrieval-router work, not assertion work).

## 9. Cross-references

- Canonical spec: `docs/design-notes/2026-04-15-memory-scope-tiered.md`
- Stage 2b ship plan: `docs/exec-plans/completed/2026-04-16-memory-scope-stage-2b.md`
- Code: `tinyassets/retrieval/router.py:359-491`, `tinyassets/memory/scoping.py`
- Self-audit tool: `tinyassets/api/runs.py:1118` (`get_memory_scope_status`)
- AGENTS.md "Configuration — environment variables" table row for `TINYASSETS_TIERED_SCOPE`
- STATUS.md Work row: `Memory-scope Stage 2c flag — 30d clean — monitoring`
- Stage 2b.1/2/3 commits: `5944ca1` (2b.1), `d053468` (2b.2), `e25bd3b` (2b.3)
