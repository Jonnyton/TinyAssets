---
title: Post-Redeploy Wiki Migration Playbook
date: 2026-04-26
audience: claude-code lead — execute after cloud daemon redeploy lands BUG-028 alias-resolution
status: active — single ordered playbook
---

# Post-Redeploy Wiki Migration Playbook

When the cloud daemon redeploy lands the BUG-028 alias-resolution fix
(`tinyassets/universe_server.py:12644-12658`), every wiki write that has been
deferred against a canonical `BUG-NNN-...` uppercase-slug path becomes safe.

Pre-redeploy, those writes hit `_sanitize_slug` lowercasing and either
duplicate the page (creating a stale lowercase sibling) or land in
`drafts/bugs/`. Post-redeploy, the alias-resolution branch detects the
existing uppercase variant and updates it in-place.

This playbook is the ordered sequence of every such deferred write. Run
top-to-bottom. Do **not** start until §0 gates are green.

Companion: `docs/ops/post-redeploy-validation-runbook.md` covers deploy
fingerprint + canary + fix-validation. This file is the wiki-write subset
of §5.5 expanded into per-page operations.

---

## §0 — Pre-flight gates (must be green before any write below)

1. **Deploy fingerprint confirmed.** `docs/ops/post-redeploy-validation-runbook.md` §1 GREEN — image tag matches latest origin/main, container `Up`, MCP `/health` 200.
2. **Wiki write canary GREEN.** Run:
   ```bash
   python scripts/wiki_canary.py --url https://tinyassets.io/mcp --verbose
   ```
   Expect exit 0 + `wiki write OK` + `wiki read roundtrip OK`.
3. **Alias-resolution smoke test.** One read against an uppercase canonical path that previously had a duplicate (BUG-003 or BUG-023) — confirm `wiki action=read page=...` resolves to the right body and the live `_wiki_write` log emits `BUG-028 slug-case alias` warning when an uppercase variant exists. If no warning fires on a known-duplicate page, the alias logic isn't live in the deployed image — STOP and re-check §0.1.

If §0 is not green, abort. Do not run any write below.

---

## §1 — Migration writes (ordered)

Each row: target page (canonical uppercase path), write-action shape, expected before/after. The `before` column captures the live page state observed in the 2026-04-26T18:45Z navigator wiki sweep; if a `before` row already shows the desired state, skip the write.

### §1.1 — BUG-034 status comment (navigator-queued 2026-04-26)

| Field | Value |
|---|---|
| Page | `pages/bugs/BUG-034-all-extensions-actions-return-no-approval-received-while-goa.md` |
| Action | `wiki action=write category=bugs filename=BUG-034-all-extensions-actions-return-no-approval-received-while-goa content=<full-body-with-status-comment-appended>` |
| Before | Body present; `## Related` section has `_none yet_`. No triage note. |
| After | `## Related` section appends triage note: `Triaged 2026-04-26: ChatGPT connector approval-prompt failure, not TinyAssets server. Workaround: 'goals action=get goal_id=<id>' inlines bound branches with full graph + node_defs + state_schema. See [[chatbot-builder-behaviors]] §"When MCP actions return 'No approval received'".` |
| Verify | `wiki action=read page="pages/bugs/BUG-034-..."` returns body with the new triage note in Related; response is `status=updated` (in-place), not `status=drafted`. |

### §1.2 — BUG-003 status update (conditional_edges shipped, partial)

| Field | Value |
|---|---|
| Page | `pages/bugs/BUG-003-build-branch-and-patch-branch-do-not-expose-conditional-edge.md` |
| Action | `wiki action=write category=bugs filename=BUG-003-... content=<body-with-status-fixed-partial-and-related-update>` |
| Before | Frontmatter `status: open`. No resolution note. Confirmed via builder-notes: `conditional_edges` accepted in `build_branch` (shape `{from, key_field, conditions}`), Mermaid renders dashed lines. END-routing edge case still open as BUG-019. |
| After | Frontmatter `status: fixed (partial — END-routing edge case open as BUG-019)`. Append `## Resolution` section: `2026-04-22 (per [[builder-notes-agent-teams]]): conditional_edges accepted in build_branch with shape {from, key_field, conditions: {outcome_str: target_node_id}}. Mermaid renders dashed lines. END-routing edge case (KeyError '__end__') split out to [[BUG-019]] — still open.` |
| Verify | Read returns `status: fixed (partial — END-routing edge case open as BUG-019)` in frontmatter. |

### §1.3 — BUG-003 lowercase-duplicate cleanup (host action — filesystem rm)

| Field | Value |
|---|---|
| Page | `pages/bugs/bug-003-build-branch-and-patch-branch-do-not-expose-conditional-edge.md` |
| Action | **NOT a wiki write — host shell action.** `ssh root@<droplet> "rm /data/wiki/pages/bugs/bug-003-build-branch-and-patch-branch-do-not-expose-conditional-edge.md"` |
| Before | Lowercase duplicate present (created 2026-04-26 during pre-fix failed write attempt). Body: stale, content matches §1.2 target. |
| After | Lowercase variant deleted. Only canonical uppercase page remains (now updated per §1.2). |
| Verify | `wiki action=list category=bugs` returns the BUG-003 entry once, with the canonical uppercase path. No `bug-003-...` lowercase entry. |

### §1.4 — BUG-007 status update (input_keys warning event live)

| Field | Value |
|---|---|
| Page | `pages/bugs/BUG-007-input-keys-is-not-enforced-as-context-isolation-prompt-templ.md` |
| Action | `wiki action=write category=bugs filename=BUG-007-input-keys-is-not-enforced-as-context-isolation-prompt-templ content=<body-with-status-fixed-partial>` |
| Before | Frontmatter `status: open`. No resolution note. Builder-notes confirms `input_keys_leak` warning event at step 1000000 + opt-in `strict_input_isolation: bool` flag on node_def for hard-reject. |
| After | Frontmatter `status: fixed (partial — warning + opt-in strict mode; default still permissive)`. Append `## Resolution` section: `2026-04-22 (per [[builder-notes-agent-teams]]): input_keys leak now emits 'input_keys_leak' warning event at step 1000000. Opt-in 'strict_input_isolation: bool' on node_def enables hard-reject enforcement. Default remains permissive — flip to strict by default deferred pending downstream behavior review.` |
| Verify | Read returns `status: fixed (partial)` in frontmatter. |

### §1.5 — BUG-014 Part A status update (literal-brace escape live)

| Field | Value |
|---|---|
| Page | `pages/bugs/BUG-014-compiler-rejects-double-brace-literal-escapes-in-prompt-temp.md` |
| Action | `wiki action=write category=bugs filename=BUG-014-compiler-rejects-double-brace-literal-escapes-in-prompt-temp content=<body-with-status-fixed-partial-A>` |
| Before | Frontmatter `status: open`. Builder-notes confirms backslash-escape `\{x\}` renders literal `{x}`; Jinja `{{x}}` still substitutes. Part B (build-time missing-key validation) NOT live. |
| After | Frontmatter `status: fixed (Part A only — backslash-escape live; Part B build-time validation still open)`. Append `## Resolution` section: `2026-04-22 (per [[builder-notes-agent-teams]]): backslash-escape '\{x\}' renders literal '{x}'. Confirmed live in agent_team_3node_v4 lead prompt. Jinja '{{x}}' still substitutes (preserved). Part B (build-time missing-key validation) still not implemented — would need separate task.` |
| Verify | Read returns `status: fixed (Part A only — ...)` in frontmatter. |

### §1.6 — BUG-015 status update (multi-output_keys typed JSON)

| Field | Value |
|---|---|
| Page | `pages/bugs/BUG-015-multi-output-keys-node-silently-drops-all-but-first-key-into.md` |
| Action | `wiki action=write category=bugs filename=BUG-015-multi-output-keys-node-silently-drops-all-but-first-key-into content=<body-with-status-fixed>` |
| Before | Frontmatter `status: open`. Builder-notes confirms engine auto-injects RESPONSE FORMAT section listing all declared output_keys with types; LLM returns single JSON; typed JSON lands correctly in state. |
| After | Frontmatter `status: fixed`. Append `## Resolution` section: `2026-04-22 (per [[builder-notes-agent-teams]]): engine auto-injects RESPONSE FORMAT section listing all declared output_keys with types, instructs LLM to return single JSON. Typed JSON lands correctly in state. Strictly better than the single-JSON-envelope workaround previously documented in [[structured-json-node-outputs]].` |
| Verify | Read returns `status: fixed` in frontmatter. |

### §1.7 — BUG-016 status update (typed output writeback)

| Field | Value |
|---|---|
| Page | `pages/bugs/BUG-016-typed-non-str-output-keys-from-prompt-template-nodes-are-not.md` |
| Action | `wiki action=write category=bugs filename=BUG-016-typed-non-str-output-keys-from-prompt-template-nodes-are-not content=<body-with-status-fixed>` |
| Before | Frontmatter `status: open`. Builder-notes confirms int/bool/str all write to state correctly. Probes: `a590c3a51cb0` (multi-str), `47aaade0839d` (typed). |
| After | Frontmatter `status: fixed`. Append `## Resolution` section: `2026-04-22 (per [[builder-notes-agent-teams]]): int/bool/str output_keys all write to state correctly via the typed-JSON RESPONSE FORMAT path (same fix as [[BUG-015]]). Verified via probe runs a590c3a51cb0 (multi-str) and 47aaade0839d (typed).` |
| Verify | Read returns `status: fixed` in frontmatter. |

### §1.8 — BUG-018 status update (related_wiki_pages on describe_branch live)

| Field | Value |
|---|---|
| Page | `pages/bugs/BUG-018-no-maintainer-notes-field-on-nodes-builder-to-builder-notes-.md` |
| Action | `wiki action=write category=bugs filename=BUG-018-no-maintainer-notes-field-on-nodes-builder-to-builder-notes content=<body-with-status-superseded>` |
| Before | Frontmatter `status: open (superseded by feature plan)`. Builder-notes confirms `related_wiki_pages` on `describe_branch` is live — returns up to 20 related pages with `matched_via` transparency. The page itself is discoverable via `describe_branch`. |
| After | Frontmatter `status: closed (superseded by feature-describe-branch-related-wiki-pages)`. Append `## Resolution` section: `2026-04-22 (per [[builder-notes-agent-teams]]): superseded by [[feature-describe-branch-related-wiki-pages]] — describe_branch + get_branch now return up to 20 related wiki pages with 'matched_via' transparency. Builder-to-builder notes are surfaced via this related-pages mechanism rather than a per-node maintainer_notes field. This page itself is discoverable via describe_branch on any agent_team_* branch.` |
| Verify | Read returns `status: closed (superseded ...)` in frontmatter. |

### §1.9 — Tier-1 investigation page closing paragraph

| Field | Value |
|---|---|
| Page | `pages/plans/tier-1-investigation-routing-resolver.md` |
| Action | `wiki action=write category=plans filename=tier-1-investigation-routing-resolver content=<body-with-resolution-section-appended>` |
| Before | Page already has Related footer + budget closer. No paragraph stating investigation outcome. |
| After | Append a `## Resolution status (2026-04-26)` section before the Related footer. Content: `Investigation completed in two phases. Phase 1 ([[BUG-003]]): conditional_edges accepted in build_branch with shape {from, key_field, conditions}. Phase 2 ([[BUG-021]]): recursion_limit exposed via run_branch with explicit budget. END-routing edge case ([[BUG-019]]) and conditional-edges-to-no-op-router-falls-through ([[BUG-022]]) remain open and tracked separately. Net: in-graph iteration is production-ready for sequential gate→work patterns; routing-to-END requires the BUG-019 fix before iterative-loop branches can terminate cleanly.` |
| Verify | Read returns the new section between the existing budget closer and Related footer. |

### §1.10 — BUG-002 status check (NOT pre-confirmed resolved)

| Field | Value |
|---|---|
| Page | `pages/bugs/BUG-002-list-branches-node-count-does-not-match-describe-branch-actu.md` |
| Action | **DO NOT WRITE BLINDLY.** Builder-notes-agent-teams.md does NOT mention BUG-002 (`list_branches` node-count mismatch). STATUS line 41 includes it in the migration list, but the resolution evidence is missing from the wiki. |
| Before | Frontmatter `status: open`. No resolution evidence in builder-notes. |
| After | **Verify first**: search code for `list_branches` node-count handler; confirm whether the count derives from the same source as `describe_branch`. If yes (fix shipped silently), update status to `fixed` with a code-pointer resolution note. If no, leave open and remove from STATUS line 41 migration scope. |
| Verify | Either status updated with evidence, or row removed from the STATUS migration scope with a note "BUG-002 not pre-confirmed; needs separate triage." |

### §1.11 — BUG-020 status — NO CHANGE (deliberately excluded)

| Field | Value |
|---|---|
| Page | `pages/bugs/BUG-020-no-long-poll-synchronous-wait-mode-chatbot-tool-budget-exhau.md` |
| Action | **NO WRITE.** STATUS line 41 lists BUG-020, but builder-notes-agent-teams.md confirms only a behavioral workaround ("never `stream_run` in iterative session; single `get_run` after delay"), not a fix. The underlying primitive gap is unaddressed. |
| Reason | Closing this issue would mark a still-broken primitive as fixed. Skip until either (a) a real long-poll mode ships, or (b) host explicitly downgrades the issue to "deferred pending Layer-3" with a status note that reflects that. |

---

## §2 — Post-migration verification

After §1.1–§1.10 complete (skipping §1.11):

1. **List re-check.** `python scripts/mcp_probe.py --url https://tinyassets.io/mcp wiki` — expect:
   - 44 promoted pages (no new/lost pages from migration writes; in-place updates only).
   - Zero entries with lowercase `bug-NNN-...` paths (BUG-003 lowercase variant deleted in §1.3; BUG-023 already lowercase by historical accident — leave as-is unless host requests cleanup).
2. **Cursor refresh.** Update `.claude/agent-memory/navigator/wiki_sweep_cursor.md`:
   - Bump `last_sweep` timestamp.
   - For each updated page, refresh the `updated` column to today's date.
   - Delete the "Pending wiki writes (gated by cloud redeploy)" section — it's been drained.
   - Move the "Deploy-lag note (2026-04-26)" section to a new "Historical resolved" subsection at the bottom.
3. **STATUS trim.** Delete the Work-table row "Wiki status migration (#32) — ... | post-deploy" once §1 is complete. (Per `feedback_status_md_host_managed`, do NOT auto-trim Concerns; only Work rows.)
4. **STATUS Concern update.** The 2026-04-26 BUG-034 triage Concern row can be deleted (the triage write is done) — but only after §1.1 confirms.

---

## §3 — If a write fails mid-playbook

- **Write returns `status=drafted` instead of `status=updated`** → alias-resolution didn't fire. Inspect the response: if it includes a `BUG-028 slug-case alias` warning in the `note` field, the resolution worked but landed at a different path (rare, indicates uppercase variant doesn't exist for this BUG-NNN). If no warning, the deployed image predates the BUG-028 fix — abort §1, re-check §0 gates, escalate to host.
- **Write returns `error: Failed to write`** → filesystem permission issue on the droplet. Host action required: check `/data/wiki/pages/bugs/` ownership + mode.
- **Read after write returns the OLD body** → cache layer between MCP and disk. Wait 30s, re-read. If still stale, restart the daemon (`docs/ops/cloud-daemon-restart.md`) and re-verify.

In all cases: do NOT mark a row complete in this playbook until the §1.x `Verify` line passes.

---

## §4 — Why this playbook exists

Cloud-daemon-redeploy unblocks ~10 deferred wiki writes that have been sitting in three different surfaces (cursor "Pending wiki writes" section, STATUS Work row "Wiki status migration #32", individual session messages). Without a single ordered playbook, the lead would cross-reference all three at execution time and likely miss the per-write before/after detail or the §1.10/§1.11 caveats. Source: lead session-planning 2026-04-26.

Companion docs:
- `docs/ops/post-redeploy-validation-runbook.md` — deploy fingerprint + canary + fix validation; this playbook implements its §5.5 row.
- `docs/ops/cloud-daemon-restart.md` — restart-only ops if §3 hits a cache layer.
