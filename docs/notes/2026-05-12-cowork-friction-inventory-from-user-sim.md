---
date: 2026-05-12T07:04Z
author: cowork
audience: codex
status: open
related: PR-080, BUG-067, BUG-069
session: ChatGPT thread 6a02bc31-6a94-83e8-a39e-07898be214ec (persona mark-session, Developer Mode, Memory Off)
---

# Cowork friction inventory from user-sim — 2026-05-12

## Why this note exists

Drove a fresh "Mark" user-sim session (ChatGPT Developer Mode, no shared memory, MCP-only) to try to migrate `.github/workflows/auto-fix-bug.yml` behavior into `change_loop_v1` via MCP primitives. The headline finding (write primitives uniformly fail) is **already covered by PR-080 + BUG-067 + BUG-069** — do not duplicate-file. Today's session added meaningful empirical coverage to that class (build_branch + wiki.file_bug success-path also fail, not just patch_branch), and surfaced **12 distinct friction events**, most of which are SECONDARY to PR-080 and worth tracking separately.

This note exists because today's session could not file the items through MCP (the write path it would have used is itself the bug). Once PR-080 ships and chatbot writes work end-to-end, Codex (or a follow-up Cowork) can file the items below as proper patch_requests.

## Empirical expansion of PR-080's known surface (file inside PR-080 amendment, not as new PR)

PR-080's title is "write-action recovery receipts for chatbot-visible response loss" — originally framed around `patch_branch`. Today's session shows the class is broader:

- **patch_branch** — 3 attempts (large payload, large payload BUG-001-aware, minimal 2-state-field-only); all wedge at "Access granted → Thinking → generation error"; substrate state unchanged each time (verified via 4 follow-up describe_branch calls).
- **build_branch** — 1 attempt with a fresh probe branch (valid 2-node spec_json `probe_start → end_marker → END`, `input_keys`/`output_keys` as native arrays); same failure shape.
- **wiki.file_bug success-path** — accepted validation path on first try (small structured "severity enum" error rendered cleanly); the corrected retry with severity=critical wedged identically. Confirmed via wiki.search + wiki.since (changed_since=2026-05-12T05:30:00Z → 0 results) that the page was NEVER created — not just unrendered.

Hypothesis update: my mid-session "writes succeed silently and only render fails" theory was **wrong**. Substrate-side wedge / non-mutation is real, not a render-only failure. PR-080's framing as a "response receipt" gap is right but the underlying issue is a write-path or post-tool-handler crash, not just response loss.

## Items already covered by existing brain pages — no new filing needed

- Headline write-path failure → **PR-080** + BUG-067 + BUG-069 (covered, just amend with build_branch + wiki coverage)
- BUG-001 (`patch_branch` silent char-iter of string `input_keys`/`output_keys`) → **already open**, chatbot defensively read the page before writes — no new filing
- Reusable-node library fantasy framing (e.g., `make_qa_plan` prompt template references "game jam release / jam brief") → **substrate-fix #12 DomainNeutralVocabulary** already filed; today's session confirms it's still leaking

## New friction items worth filing as patch_requests (once writes work)

Each item below is a genuine new gap not already covered. All would be `kind=patch_request` per project framing convention.

### F1 — `read.page` should accept repo-file paths (or new `read.repo_file` primitive)

- **Observed:** Host told the chatbot "the cheat lives at `.github/workflows/auto-fix-bug.yml`" — a real repo file path. Chatbot had no MCP primitive to fetch it. Fell back through wiki.search → public-GitHub-raw (cache miss) → 3 separate `community.review` scopes to triangulate.
- **Cost:** 4+ tool calls and 3 permission gates to recover context for one named file path the user already pointed at.
- **Proposed fix:** Either extend `wiki.read`/`read.page` to accept a `repo_path` argument that resolves to the file at HEAD, or add `extensions.read_repo_file(path)`. Either lets the user point and the chatbot fetch in one call.
- **Severity:** major (blocks user-buildable-substrate composition when migrating from repo cheats).

### F2 — Tool surface stability per turn

- **Observed:** Chatbot reported (verbatim) "The GitHub connector path that was available at first is no longer exposed in this session" — connector visible at the start of a single response, invisible 10 seconds later within the same turn.
- **Proposed fix:** Substrate should guarantee tool surface stability per chatbot turn — what's in the affordance list at turn start stays callable through end of turn.
- **Severity:** major.

### F3 — Session-level read-consent (collapse community.review re-prompts)

- **Observed:** 5 separate user-consent gates fired in one chatbot turn (wiki action, community.review PRs, community.review issue 808, community.review repo PRs, plus the universe call at start). Each new community scope re-prompts.
- **Proposed fix:** One session-level consent for "read this universe + community" instead of per-scope re-prompts. Keep per-write consent (that's correct gating); collapse per-read consent.
- **Severity:** minor (UX friction, not blocker; reads succeed once consented).

### F4 — `patch_branch.changes_json` schema hint reads singular when schema needs list-of-ops

- **Observed:** `extensions.search_nodes` returns a help string "include the same `node_ref` inside a `spec_json` / `changes_json` node entry on build_branch / patch_branch" — singular phrasing. Chatbot's first natural guess was an object form; substrate guarded correctly with "changes_json must be a JSON list". Retry as list-form succeeded the schema check.
- **Proposed fix:** Rephrase the help string to plural ("inside `changes_json` ops list" or similar) and/or include an inline JSON shape example. Alternatively, substrate-side accept both singular and list forms.
- **Severity:** minor (single retry recovers cleanly; just paper-cut friction).

### F11 — `extensions.fork_tree` is read-only despite write-suggestive name

- **Observed:** Chatbot reached for `fork_tree` to create a fork of `change_loop_v1`. Substrate returned "no descendants" and did not create a fork — it's a lineage view only. Chatbot pivoted to `build_branch` with a fresh spec_json.
- **Proposed fix:** Either rename `fork_tree` → `lineage_tree` / `branch_descendants` (read-only intent clear), or add a paired `extensions.fork_branch(source_branch_id, new_name)` write primitive that does what the name suggests.
- **Severity:** major (naming sends chatbots down a dead end; the real fork affordance is non-obvious).

### F12 — Wiki severity enum (`critical|major|minor|cosmetic`) not discoverable upfront

- **Observed:** Chatbot called `wiki.file_bug` with `severity=P0` (matching the priority framing it had been using throughout the session). Substrate correctly rejected with structured error stating the valid enum. Chatbot retried with `severity=critical`.
- **Proposed fix:** Surface the enum in the `wiki.file_bug` tool schema description, OR have the substrate auto-map common aliases (`P0/P1/P2/P3` → `critical/major/minor/cosmetic`).
- **Severity:** minor (single retry recovers; documentation/discoverability gap only).

### F7 — Generation-error class after consent grant (distinct from BUG-067 silent stall)

- **Observed:** All 5 write attempts in today's session ended in "Something went wrong while generating the response. Retry" rather than the BUG-067 silent-stall pattern. Both occur in the post-grant phase but they're observably distinct UI outcomes.
- **Proposed disposition:** Fold into PR-080 / BUG-067 / BUG-069 as a third variant marker, OR file as its own BUG- entry once writes work. Recommend amendment over new filing.
- **Severity:** P0/critical (it's part of the PR-080 class).

### F8 — Chatbot doesn't self-verify substrate state after a write error

- **Observed:** After each write error, the chatbot did NOT spontaneously call `describe_branch` or `wiki.since` to check whether the mutation landed. The user had to drive that discipline four times.
- **Proposed fix:** Either bake "verify state after write error" into a chatbot-side standing prompt / skill, OR make the substrate-side write response always return a structured `applied: true/false` flag that the chatbot must echo back. Latter is cleaner since it lives in the substrate.
- **Severity:** minor (chatbot-coachable, but a substrate-side guarantee would compound).

## Suggested PR sequencing once write path works

1. **PR-080 amends first** — fold today's expanded coverage (build_branch + wiki.file_bug + substrate-side non-mutation finding) into PR-080's body. Once PR-080's substrate fix ships, validate by re-running today's exact four-call sequence as the canary.
2. **F11 (`fork_tree` naming + paired write primitive)** — clear-cut, low-risk, unblocks one of the user-buildable-loop paths Mark hit.
3. **F1 (`read.page` over repo paths or new primitive)** — bigger affordance change but the highest-payoff for user-sim depth.
4. **F4 + F12 (schema-hint pluralization + severity enum discoverability)** — paper-cut cluster; can be one small PR.
5. **F2 + F3 (tool surface stability + consent grouping)** — substrate-runtime + UX bundle; might be coupled to other ongoing MCP work.
6. **F8 (substrate-side `applied:` flag)** — natural follow-on to PR-080.

## What I did with the session findings

- Saved a Cowork memory `reference_pr_080_canonical_substrate_write_failure.md` pointing to the canonical pages and capturing today's empirical expansion. Memory index updated under "Substrate-evolution learning".
- Did NOT file new patch_requests in the brain (writes were broken and would have duplicated PR-080 anyway).
- Wrapped the user-sim thread in a clean state (branch unchanged, chatbot acknowledged PR-080 already covers the class).
- Left this in-repo coord note for Codex to pick up since the wiki-coord-note path is itself blocked by the bug.

## Next moves (host-directed)

> "we are going back to working with codex to now get the pr's through the loop ... we will come back to the user when we think we have merged all the fixes to the friction that we saw"

So Cowork's role from here:
- Help Codex drive PR-080 (and any of F1–F12 he agrees should be elevated) through writer → checker → merge.
- Keep watching for the writer-prompt gap (auto-fix-bug.yml still routes architectural filings into `docs/design-notes/proposed/` — that's its own active issue).
- Re-run today's exact user-sim probe once PR-080 ships, as the canonical canary that confirms the user-buildable-substrate thesis is empirically demonstrable.
