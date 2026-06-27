---
status: active
---

# Canary → patch_request Seam — Design Spec (v2)

**Date:** 2026-04-25
**Author:** navigator
**Status:** Design spec — v2 consolidation. Folds in cross-doc seam findings from this session's pair-reads + audits. Preserves v1 (`2026-04-25-canary-to-patch-request-spec.md`) for diff lineage.
**Predecessor:** v1 (~210 lines, 8 sections).
**v2 changes:**
1. **§3 Layer 3 NEW: composition rule with surgical rollback** — when #57 emits successful `caused_regression`, canary skip-or-tag to prevent double-counting (per #65 §2 cross-doc seam).
2. **§5 NEW: closure status taxonomy refinement** — adds `closed_watching` status distinct from `fixed` (closes v1 §7 Q4 collision).
3. **§3 Layer 1 sharpening: durable throttle-state location** (closes v1 §7 Q1 — `.tinyassets/canary_state/` instead of `.agents/canary_state/`).
4. **§4 minor: severity escalation memory** — canary re-reads open bug's current severity before file-or-cosign decision (closes v1 §7 Q2).
5. **§9 NEW: composition with #55 external-PR bridge** — `code_committed` from PR vs. canary `caused_regression` are orthogonal but share the surgical-rollback signal source.
6. **§3 Layer 4 NEW: tag namespace formalization** — `source:`, `canary:`, `failure_class:` namespaces ratified (closes v1 §7 Q3).
**Roadmap reference:** Phase C item 14 — Phase E item 23 cross-doc seam captured.

---

## 1. Trigger surfaces (UNCHANGED from v1)

Same five canaries with the same exit-code → kind/failure_class mapping. No changes to v1 §1.

---

## 2. patch_request frontmatter shape

UNCHANGED from v1 §2 except: `tags` namespace is now formalized — see §3 Layer 4 below. `source:canary, canary:<name>, failure_class:<class>` is the canonical shape.

**Wire-shape addition (NEW in v2):** the canary helper consults `_check_existing_rollback(failure_class, version_id_window)` BEFORE filing per §3 Layer 3.

---

## 3. Throttling, dedup, AND rollback-composition

Four layers now (was two in v1 — v2 adds Layer 3 and Layer 4).

### Layer 1 — canary-side throttle file (UPDATED location)

Each canary maintains a small JSON state file. **v2 location:** `.tinyassets/canary_state/<canary_name>.json` (was `.agents/canary_state/...` in v1).

**Why the move:** `.agents/` is for cross-session activity logs and team coordination; `.tinyassets/` is the persistent state root (alongside `.tinyassets/wiki`, `.tinyassets/runs.db`). Throttle state belongs in persistent-state, not session-coordination. Survives daemon restart cleanly; no daemon-restart-recovery complexity.

**Throttle rule** (UNCHANGED from v1): one new patch_request per `(canary_name, failure_class)` pair per 6 hours unless severity escalates from P1/P2 → P0. Within window, repeated failures invoke `cosign_bug` against existing `bug_id`.

### Layer 2 — server-side dedup (UNCHANGED)

`_wiki_file_bug` Jaccard similarity ≥ 0.5. v2 adds: when canary receives `similar_found` response, the cosign call ALSO records the rollback-composition status from §3 Layer 3 (i.e., a cosign can carry the `rolled-back-already` tag).

### Layer 3 — composition with surgical rollback (NEW in v2)

Per pair-read #65 §2 — surgical rollback (#57) and canary→file_bug (this spec) BOTH consume the same canary outputs. They are complementary (forward-pipeline vs. safety-net), but should not double-count.

**Composition rule:**

1. Before filing OR cosigning, the canary helper queries the local rollback registry (per #57 §5's `runs action=get_rollback_history` MCP read action — see §3.1 below).
2. If a successful `caused_regression` event was emitted within the last 6 hours that attributed to a `branch_version_id` in the canary's surface AND the failure_class is consistent with what was rolled back:
   - **Action: cosign with `rolled-back-already` tag** (NOT skip filing entirely). The cosign records that this canary observed the regression too — useful for navigator triage and for confirming the rollback addressed the root cause.
   - **Severity treatment:** the cosign weight is half (gives the rollback's `caused_regression` the dominant attribution; canary's cosign is corroboration).
3. If NO recent rollback was emitted (canary RED is a fresh signal):
   - **Action: file or cosign normally** per Layers 1+2.
4. If a rollback was emitted BUT the failure_class differs (e.g., rollback was for wiki-write-fail, canary is now reporting endpoint-unreachable) — that's a NEW failure mode emerging post-rollback:
   - **Action: file fresh patch_request with `post-rollback-emergence` tag.** Severity escalates +1 (P2→P1, P1→P0) — emergent failure post-rollback warrants attention.

**Implementation detail:** the canary helper reads `runs action=get_rollback_history since_days=1` once per canary tick; caches result for 60s to avoid hammering the MCP surface. Rollback history is small (rollback events are rare), so the call is cheap.

### §3.1 — Rollback registry lookup

The canary helper exposes a small read function:

```python
def _check_existing_rollback(
    failure_class: str,
    component: str,
    since_seconds: int = 21600,  # 6h
) -> dict | None:
    """Return the most recent rollback record matching this canary's surface,
    or None if no rollback in window."""
    # Calls runs action=get_rollback_history; filters by component +
    # failure_class match against rollback's caused_regression events.
```

Returns `None` if no match → file normally. Returns a dict with `rolled_back_at + branch_version_id + rolled_back_reason` if matched → apply Layer 3 rule.

### Layer 4 — Tag namespace ratification (NEW in v2 — closes v1 §7 Q3)

Tag-key namespaces are pinned as project convention:

| Namespace | Format | Example |
|---|---|---|
| `source:` | `source:<source_name>` | `source:canary`, `source:github_pr`, `source:user_chat` |
| `canary:` | `canary:<canary_name>` | `canary:mcp_public_canary` |
| `failure_class:` | `failure_class:<class>` | `failure_class:endpoint_unreachable` |
| `severity_escalation:` | `severity_escalation:from-PN-to-PN` | `severity_escalation:from-P2-to-P0` |
| `rolled-back-already:` | `rolled-back-already:<branch_version_id>` | `rolled-back-already:def_id@abc12345` |
| `post-rollback-emergence:` | `post-rollback-emergence:<branch_version_id>` | `post-rollback-emergence:def_id@abc12345` |
| `repo:` | `repo:<owner/name>` (per #55) | `repo:host/workflow` |
| `pr_url:` | `pr_url:<url>` (per #55) | `pr_url:https://github.com/...` |
| `github_handle:` | `github_handle:<login>` (per #55) | `github_handle:userA` |

**Convention:** every tag is `<namespace>:<value>` with at most one colon at the namespace boundary. Values may contain `:` (e.g., a URL) but the namespace is the prefix up to the first `:`. Tag-namespaces are referentially integrity-checked at filing time — unknown namespaces are rejected with a clear error.

**Why ratify now:** chat-bot tooling that scans tags (per #55, future #59 chatbot-side preview) needs a stable namespace to query against. Free-form tags grow inconsistent fast; a small ratified set is forward-compatible.

---

## 4. Severity mapping + escalation memory

Severity table UNCHANGED from v1 §4 (11 rows; P0 / P1 / P2 / suppressed).

**v2 NEW: severity escalation memory** (closes v1 §7 Q2):

When the canary helper is about to file-or-cosign, it re-reads the open bug's current severity from the wiki page metadata (cheap MCP read). If the human-edited severity has changed (e.g., a navigator escalated P2 → P0 mid-window), the canary's local state is updated to match.

**Behavior matrix:**

| Local severity | Wiki severity | Action |
|---|---|---|
| P2 | P2 | Throttle-window cosign (Layer 1) |
| P2 | P1 | Update local state to P1; cosign |
| P2 | P0 | Update local state to P0; **cosign** (NOT file new — wiki severity is authoritative) |
| P0 (escalation) | P0 | Throttle-window cosign |
| P0 (escalation) | P2 | Wiki severity won (human de-escalated); update local; cosign |
| (any) | (closed) | File fresh per Layer 1 idempotency rule |

**Implementation:** one MCP read per canary tick when throttle would re-cosign. Sub-millisecond (wiki page reads are file-cached). Worth the round-trip; eliminates stale-state race.

---

## 5. Closure path (REFINED)

v1's three close conditions remain. **v2 NEW: `closed_watching` status taxonomy refinement** (closes v1 §7 Q4).

**Status states for canary-filed bugs:**

| Status | Meaning | Transition triggers |
|---|---|---|
| `open` | Active failure being investigated | Default at file time |
| `closed_watching` | Canary green for ≥ 30 min; under post-fix watch window | Auto-close routine |
| `closed_resolved` | Canary green for ≥ 7 days OR explicit human closure | Auto-promotion from `closed_watching` after 7d clean OR manual close |
| `reopened` | Canary green during watch window then RED again | Auto-reopen on re-fire |
| `superseded` | A merge from coding team supersedes this bug | Manual or PR-merge-trigger |

**Why `closed_watching` distinct from `closed_resolved`:**
- v1 §7 Q4: a `fixed` bug that's still under watch-window can re-fire; the UX of "fixed → reopened" is jarring. `closed_watching` makes the watch-window state explicit.
- Downstream readers (chatbot dedup, navigator triage UI, contribution ledger filters) can distinguish "actually fixed" from "thinks-it's-fixed-but-watching."
- The 7-day window from auto-close (30min green) → `closed_resolved` matches AGENTS.md "post-fix clean-use evidence" timing.

**Idempotency:** auto-close is idempotent across statuses — a canary re-firing during `closed_watching` reopens; re-firing during `closed_resolved` files fresh.

---

## 6. Wiring — UNCHANGED from v1 §6

Per-canary thin-module wiring. `scripts/canary_patch_request.py` shared helper. v2 helper additions:
- `_check_existing_rollback(...)` per §3.1 above.
- `_re_read_wiki_severity(bug_id)` per §4 escalation memory.
- `_advance_status(bug_id, new_status)` for §5 status taxonomy.

**Endpoint preference UNCHANGED:** canaries call local daemon endpoint (`http://127.0.0.1:8001/mcp`); fallback to log-only if local also unreachable.

---

## 7. Open questions (v2 status)

| v1 Q | Status |
|---|---|
| Q1 throttle-state-file persistence under restart | **CLOSED** — moved to `.tinyassets/canary_state/` (persistent state root). |
| Q2 severity escalation memory | **CLOSED** — §4 v2 NEW behavior matrix. |
| Q3 tag namespace formalization | **CLOSED** — §3 Layer 4 ratification. |
| Q4 auto-close vs watch-window collision | **CLOSED** — §5 `closed_watching` distinct from `closed_resolved`. |
| Q5 canary-the-canary | STILL OPEN — synthetic-failure injection canary. v3+ infrastructure. |

**v2 NEW open questions:**

1. **Cross-canary correlation.** When PROBE-001 (public MCP) AND PROBE-002 (Layer-2 deeper init) both fire RED simultaneously, are they the same failure or two different ones? Today: both file (or cosign on dedup). **Open Q:** should there be cross-canary correlation primitive that recognizes "these N canaries went RED at the same time on the same surface — file ONE bug with all N as evidence"? Recommend defer to v3+; let dedup handle it for now.

2. **Rollback-already cosign weight reduction.** §3 Layer 3 says cosign weight is "half" when `rolled-back-already`. **Open Q:** is half the right calibration, or should it be configurable? Recommend: pin half for v2; revisit if observed pain.

3. **`closed_watching → closed_resolved` 7-day auto-promotion timer.** Who fires the timer — a scheduled job, on-canary-tick check, or both? Recommend: on-canary-tick (no separate scheduler complexity). Each canary green-tick during `closed_watching` checks: "is this bug ≥ 7d in `closed_watching`? → promote to `closed_resolved`." Implementation-time concern.

---

## 8. Composition with #55 external-PR bridge (NEW in v2)

External-PR bridge (#55) and canary→file_bug (this spec) both source patch_requests but at different abstraction layers. Cross-doc seam:

- **#55 emits `code_committed` events on PR merge** (per #58 §1.3).
- **This spec emits `caused_regression` events on canary RED in watch-window** (via #57 surgical rollback path).
- **Both can fire on the same surface.** A PR merges, canary goes RED in the merge's watch-window → rollback emits `caused_regression` → canary helper checks rollback registry per §3 Layer 3 → cosigns the rollback's bug with `rolled-back-already`.

**Symmetric composition:** the same canary RED that triggered the rollback ALSO triggers the cosign. Audit trail records: PR-from-#55 author got `code_committed`; rollback's caused_regression deducted from that author proportionally; canary's cosign confirmed the regression observation. Three records, one root cause.

**Recommendation:** when surgical rollback impl lands, include integration test exercising this full chain end-to-end. Test name: `test_pr_merged_canary_red_rollback_canary_cosign_chain`. Filing as [PENDING #55+#57+canary-spec-integration-test].

---

## 9. References

- v1: `docs/design-notes/2026-04-25-canary-to-patch-request-spec.md` (preserved for diff lineage).
- Pair-read source: `docs/audits/2026-04-25-pair-57-surgical-rollback-convergence.md` §2 (cross-doc seam discovery).
- Composition substrate:
  - `docs/design-notes/2026-04-25-surgical-rollback-proposal.md` (#57 — `runs action=get_rollback_history` consumer in §3.1).
  - `docs/design-notes/2026-04-25-external-pr-bridge-proposal.md` (#55 — `code_committed` source in §8).
  - `docs/design-notes/2026-04-25-attribution-layer-specs.md` (caused_regression weight calibration).
- Tag namespace cross-reference: tag conventions across spec sources (#55 §3, #57 §5 metadata, #59 scope_token namespacing).
- Existing canary scripts (unchanged): `scripts/{mcp_public_canary,uptime_canary,uptime_canary_layer2,wiki_canary,mcp_tool_canary,revert_loop_canary}.py`.
- Memory load-bearing: `project_wiki_is_uptime_surface`, `project_always_up_auto_heal`, `project_file_bug_dedup_at_filing`, `feedback_uptime_top_priority`.
- v2 vision Phase C/E phasing: `docs/design-notes/2026-04-25-self-evolving-platform-vision-v2.md` §6.
