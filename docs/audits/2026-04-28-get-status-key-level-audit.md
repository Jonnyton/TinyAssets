---
audit: get_status key-level audit per minimal-primitives
date: 2026-04-28
author: navigator
scope: tinyassets/api/status.py:get_status() response shape — every top-level + nested key
lens: project_minimal_primitives_principle, project_community_build_over_platform_build
companion:
  - docs/audits/2026-04-28-commons-first-tool-surface-audit.md (parent — §6 listed this as opt-in follow-up)
  - PLAN.md "Scoping Rules" §1 minimal-primitives (cross-provider source)
  - tinyassets/api/status.py (canonical implementation)
  - tinyassets/api/universe.py:_action_get_recent_events (primitive that obviates 3 evidence sub-keys)
status: findings ready; awaits lead dispatch decision
---

# `get_status` key-level audit

## TL;DR

The `get_status` response shape ships **14 top-level keys + 5 evidence sub-keys = 19 chatbot-readable fields**, originally estimated as "~30 keys" (loose estimate, audit confirms 19). Applying minimal-primitives + community-build-over-platform tests:

| Verdict | Count | Keys |
|---|---|---|
| **PRIMITIVE — keep** | 11 | schema_version, active_host, tier_routing_policy, evidence_caveats, caveats, storage_utilization, per_provider_cooldown_remaining, sandbox_status, missing_data_files, universe_id, universe_exists, evidence.policy_hash, evidence.last_completed_request_llm_used |
| **CONVENIENCE — retire candidate** | 5 | actionable_next_steps, session_boundary, evidence.activity_log_tail, evidence.activity_log_line_count, evidence.last_n_calls |
| **MARGINAL — flag for lead** | 0 | — |

**Total retire candidates: 5 of 19 keys (~26%).** All 5 are convenience-rollups composable from existing primitives (`get_recent_events`, `caveats`, `account_user` env). Removing them shrinks the response by ~25-40% bytes (depending on activity.log size) and removes 5 reasons the chatbot might confuse a `get_status` field for the canonical observability surface.

**Recommendation:** dispatch a single dev task post-#18 SHIP that retires the 5 convenience keys + adds 1 cross-reference caveat ("for activity tail / recent calls, call `get_recent_events`"). ~30-45 min dev work. No new primitives. No external surface contract change beyond the deprecation.

---

## 1. Methodology

For each key in the `get_status` response (`tinyassets/api/status.py:340-361`), apply the minimal-primitives test from PLAN.md §"Scoping Rules" §1:

1. **Is this fundamentally NEW capability, or convenience over existing capability?**
2. **Could you build THIS from a smaller combination of existing primitives?** If yes, document the composition pattern instead.
3. **Would a competent chatbot reliably compose this from primitives in <5 reasoning steps?** If yes → community-build, no platform ship. If no (composition is fragile, requires nondeterministic reasoning, or hits a structural gap) → keep as primitive.

For each retire candidate, name the primitive it duplicates and the composition steps the chatbot would use post-retire.

---

## 2. Key inventory

**Top-level keys (14):** schema_version, active_host, tier_routing_policy, evidence (wrapper), evidence_caveats, caveats, actionable_next_steps, session_boundary, storage_utilization, per_provider_cooldown_remaining, sandbox_status, missing_data_files, universe_id, universe_exists.

**evidence sub-keys (5):** last_completed_request_llm_used, activity_log_tail, activity_log_line_count, last_n_calls, policy_hash.

**Total: 19 chatbot-readable fields.**

---

## 3. Per-key disposition

### 3.1 PRIMITIVES — keep (11 keys)

| Key | Why primitive |
|---|---|
| `schema_version` | Structural versioning. Required for chatbot to reason about response-shape evolution across upgrades. Irreducible — chatbot cannot derive schema version from any other primitive. |
| `active_host` (host_id, served_llm_type, llm_endpoint_bound) | Identity primitive. Cannot be derived from elsewhere — `host_id` is env-resolved, `served_llm_type` is dispatcher config, `llm_endpoint_bound` is provider-priority chain. Three orthogonal facts in one struct. |
| `tier_routing_policy` (7 sub-fields: served_llm_type, accept_external_requests, accept_goal_pool, accept_paid_bids, allow_opportunistic, paid_market_flag_on, tier_status_map) | Config snapshot — chatbot reads it to narrate dispatcher posture. No alternate primitive surfaces this; reading dispatcher config files directly is below the chatbot's tool surface. |
| `evidence_caveats` | Per-field self-auditing-tools annotation. Different shape from global `caveats` — keyed by which evidence field is degenerate. Composition pattern would re-derive these from the field values, but doing so reliably requires reproducing internal state thresholds — fragile composition, costs primitive bytes to do right. Keep. |
| `caveats` | Global self-auditing-tools per `docs/design-notes/2026-04-19-self-auditing-tools.md`. Trust-critical: chatbot uses these to compose trustworthy narratives. Cannot be derived from response fields alone (some caveats reflect internal observability — e.g. "activity.log read failed (I/O error)"). Keep. |
| `storage_utilization` | BUG-023/032 observability primitive. Per-subsystem byte counts + pressure level. Cannot be composed by chatbot — requires `inspect_storage_utilization()` privileged stat calls. Keep. |
| `per_provider_cooldown_remaining` | BUG-029 observability primitive. Per-provider quota cooldown seconds. Requires shared-router quota internal state — not chatbot-composable. Keep. |
| `sandbox_status` (bwrap_available, reason) | bwrap probe primitive. Cached process-wide. Chatbot can't probe bwrap availability — local subprocess-only. Keep. |
| `missing_data_files` | BUG-027 startup file probe primitive. Operator-visible signal of cloud-image data gaps. Chatbot can't probe filesystem — primitive. Keep. |
| `universe_id` | Request echo. Trivially primitive — clarifies which universe the response is about. Keep. |
| `universe_exists` | Boolean derived from `udir.is_dir()` — chatbot can't check filesystem. Primitive. Keep. |
| `evidence.policy_hash` | Deterministic sha256 of policy payload. Chatbot uses across-call comparison to detect config drift. Could compose by hashing `active_host + tier_routing_policy` itself, BUT the canonical hash function (sorted-JSON + separators) is platform-defined — re-deriving in chatbot costs hallucination risk on the hash format. Cheap to ship; keep as convenience-with-stable-contract. **Marginal but defensible — kept.** |
| `evidence.last_completed_request_llm_used` | Heuristic scan of activity.log for `llm=`/`provider=`/`model=` tokens. **Marginally composable** via `get_recent_events` + chatbot regex, but the heuristic varies (legacy formats) and chatbot reproducing it consistently is fragile. Audit borderline — keep for now; revisit if `last_n_calls` retires (below) and chatbot starts composing this from `get_recent_events` reliably. **Marginal but defensible — kept.** |

### 3.2 RETIRE CANDIDATES — convenience over `get_recent_events` (3 keys)

The platform ships `get_recent_events(universe_id, tag, limit)` at `tinyassets/api/universe.py:2673` as the canonical activity-log inspection primitive. It returns structured `events` + `source` + `caveats` per the self-auditing-tools pattern. **Three evidence sub-keys in `get_status` duplicate this primitive's surface:**

| Key | Why retire | Chatbot composition (post-retire) |
|---|---|---|
| `evidence.activity_log_tail` (last 20 lines as raw strings) | Strict subset of `get_recent_events(limit=20)` events surface. Raw-string form is *less structured* than the primitive's parsed form — it's an inferior duplicate. | `get_recent_events(limit=20)` — returns parsed `events[]` with `ts/tag/message/raw` per entry. Chatbot reads `.raw` fields if string form is needed. |
| `evidence.activity_log_line_count` | Total line count of activity.log. Convenience rollup — chatbot can compute `len(events)` from `get_recent_events(limit=500)` if total ≤500, or just use the count directly when needed. Even simpler: this field's only legitimate use is "is the log growing?" which is better served by storage_utilization. | `get_recent_events(limit=500)` then `len(response['events'])`; OR check `storage_utilization.per_subsystem.activity_log.bytes` for size monitoring. |
| `evidence.last_n_calls` (parsed last 10 entries newest-first) | Strict subset of `get_recent_events(limit=10)` events, same parsed shape. **Direct duplicate of the primitive.** Reverse-order is the only differentiation, which chatbot reverses trivially. | `get_recent_events(limit=10)` — returns events newest-first by default per the primitive's reverse-order semantics. Identical shape. |

**Net retire: 3 evidence sub-keys, 100% obviated by `get_recent_events`.**

### 3.3 RETIRE CANDIDATES — convenience composable from caveats (1 key)

| Key | Why retire | Chatbot composition (post-retire) |
|---|---|---|
| `actionable_next_steps` | Built by inspecting `caveats` and emitting one matching string per caveat condition (`served_llm_type` unset → "Set served_llm_type"; `endpoint_hint` unset → "Bind an LLM provider"; etc.). The caveats themselves already explain the issue; the next-step strings are a redundant projection. **Trivially composable** by chatbot — read the caveats, propose actions in user-vocabulary. <5 reasoning steps. Per `project_community_build_over_platform_build` rule 2: this is exactly the chatbot's job. | Read `caveats` array; for each caveat that names a missing config / unbound provider / nonexistent universe, propose the corresponding action in user-vocabulary. Chatbot does this reliably without canned strings. |

The strongest argument FOR keeping this would be "consistency across chatbot replies — the same caveat always yields the same next-step phrasing." But that's exactly the wrong optimization per `project_chatbot_assumes_workflow_ux` (chatbot picks vocabulary appropriate to the user, not platform-canned strings).

### 3.4 RETIRE CANDIDATES — convenience composable from `get_recent_events` + env (1 key)

| Key | Why retire | Chatbot composition (post-retire) |
|---|---|---|
| `session_boundary` (prior_session_context_available, account_user, last_session_ts, note) | Scans activity.log for the most-recent entry matching `account_user` (env `UNIVERSE_SERVER_USER`). 4 fields packaging "did this user have a prior session in this universe?". Composable: chatbot calls `get_recent_events(limit=200)`, filters by author/user token, takes most recent. <5 steps. The `account_user` echo is also retire-eligible — `get_status.active_host.host_id` covers operator identity, and `UNIVERSE_SERVER_USER` is in the chatbot's env-readable surface via the existing `get_status` evidence chain. The "note" string is a self-auditing-tools annotation that belongs on `get_recent_events` (already there: it has its own `caveats`). | `get_recent_events(limit=200)` — chatbot scans events for entries matching the operator identity; returns most-recent timestamp or "no prior session" if none. Reusable composition pattern. |

This one is borderline. The case FOR keeping: the per-account scan logic is non-trivial (regex extraction of timestamp from `[YYYY-MM-DD...]` prefix), and chatbot reproducing the regex consistently is moderately fragile. **My read:** the regex is simple enough (one capture group), the composition is <5 steps, and the per-user-session question is exactly the kind of context-specific signal `project_community_build_over_platform_build` says the chatbot should compose per-conversation rather than the platform precomputing for everyone. **Retire.**

---

## 4. Composition-patterns wiki page update

Per `pages/plans/composition-patterns.md` (F4 promoted live 2026-04-27T22:45Z), the retired keys' composition patterns deserve documentation. Recommend adding 2 new patterns (or updating existing) post-retire:

- **Pattern: "What did the daemon do recently?"** → `get_recent_events(limit=N)` (replaces former `get_status.evidence.activity_log_tail` / `last_n_calls` reflex).
- **Pattern: "Did this user have a prior session?"** → `get_recent_events(limit=200)` + filter by author/user (replaces former `get_status.session_boundary`).
- **Pattern: "What should the operator do next?"** → read `get_status.caveats`, propose user-vocabulary actions (replaces former `actionable_next_steps`).

These are 3 small additions, ~15 lines each, navigator-authored, post-retire-SHIP.

---

## 5. Net effect

**Pre-retire response shape (19 chatbot-readable fields):**
```
schema_version, active_host{3}, tier_routing_policy{7}, evidence{5},
evidence_caveats, caveats, actionable_next_steps, session_boundary{4},
storage_utilization{...}, per_provider_cooldown_remaining{...},
sandbox_status{2}, missing_data_files, universe_id, universe_exists
```

**Post-retire response shape (14 chatbot-readable fields):**
```
schema_version, active_host{3}, tier_routing_policy{7}, evidence{2:
  last_completed_request_llm_used, policy_hash},
evidence_caveats, caveats, storage_utilization{...},
per_provider_cooldown_remaining{...}, sandbox_status{2},
missing_data_files, universe_id, universe_exists
```

**Bytes saved per call:** ~25-40% depending on activity.log size (the 3 activity-log evidence keys carry the largest payload). For a daemon with a 1000-line activity log, this is 5-15 KB per call.

**Chatbot tool-list cognition cost:** -5 keys to learn / not confuse with `get_recent_events`. Reduces the "which surface gives me activity history" hallucination class.

**Test-surface impact:** `tests/test_get_status_primitive.py` exists per the file-grep. Retire would touch 5 assertions there (one per retired key). New test pinning the deprecation: assert keys NOT in response.

---

## 6. Dispatch shape

**Title:** `get_status` key-level slim — retire 5 convenience keys per minimal-primitives.

**Files:**
- `tinyassets/api/status.py` — delete activity-tail block (L107-145), session_boundary block (L264-303), actionable_next_steps construction (L196-215), and remove the 3 evidence sub-keys + 2 top-level keys from `response` dict (L340-361).
- `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/api/status.py` — plugin mirror, same edits.
- `tests/test_get_status_primitive.py` — adjust assertions for retired keys; add deprecation pin.
- `pages/plans/composition-patterns.md` (wiki, navigator-authored post-SHIP) — add the 3 composition patterns.

**Depends:** Task #18 (universe_server.py decomp Step 7/10 in flight; `tinyassets/api/status.py` is in dev's lock-set per STATUS Work-table row).

**Effort:** ~30-45 min dev for code changes + ~15 min navigator for wiki composition patterns post-SHIP.

**Verify:**
- `tests/test_get_status_primitive.py` passes with adjusted assertions.
- `tests/test_get_recent_events.py` still green (the primitive that absorbs the load).
- `python scripts/mcp_probe.py status` returns the slimmed shape.
- Manual sanity: response byte size shrinks ~25-40% on a populated universe.

**Anti-coordination guard:** This task touches `tinyassets/api/status.py` which is in dev's #18 lock-set. **Cannot dispatch until #18 SHIPs.** Block via `Depends: #18 SHIP`.

---

## 7. What's NOT in this audit

- **`get_status` deprecation warnings or schema_version bump.** The retire is a content-shrink, not a schema break. Chatbots reading retired keys will get `KeyError`-style absence. If a deprecation period is desired (chatbot reads still work but log a warning), that's a policy call beyond minimal-primitives — flag if lead disagrees.
- **`tier_routing_policy` 7 sub-fields field-level audit.** All 7 are config-snapshot fields with no chatbot-composable alternative. Marked PRIMITIVE wholesale; per-field audit would not surface retire candidates.
- **`storage_utilization` per-subsystem audit.** Sub-fields are byte counts per subsystem path. All primitive (chatbot can't stat filesystem). No retire candidates.
- **`get_status` vs `universe action=inspect` overlap.** Different scope (host identity + routing vs universe content). Out of scope for this audit.

---

## 8. Cross-references

- PLAN.md "Scoping Rules" §1 minimal-primitives — the rule under which this audit runs.
- PLAN.md "Scoping Rules" §2 community-build-over-platform-build — the rule that 4 of 5 retire candidates fail.
- `docs/audits/2026-04-28-commons-first-tool-surface-audit.md` §6 — parent audit listing this as opt-in follow-up.
- `pages/plans/composition-patterns.md` — wiki composition catalog (F4); post-SHIP additions go here.
- `tinyassets/api/universe.py:_action_get_recent_events` — the primitive that absorbs 3 of the 5 retired keys.
- `tinyassets/api/status.py:get_status` — canonical implementation under audit.
- `tests/test_get_status_primitive.py` — test surface to adjust.
- `tests/test_get_recent_events.py` — primitive that absorbs the load.
