---
title: Project-instruction-files cross-check — AGENTS / CLAUDE / LAUNCH_PROMPT / CLAUDE_LEAD_OPS
date: 2026-04-28
author: dev-2
status: read-only audit; refreshed 2026-05-01T17:21-07:00 against current AGENTS/CLAUDE files
companion:
  - docs/audits/2026-04-28-agent-memory-cross-drift-sweep.md (sibling — same day; reuses some findings)
  - docs/conventions.md "Frontmatter status: field" section (this session's reverse-engineered convention)
load-bearing-question: Where do the 4 project-instruction files (AGENTS / CLAUDE / LAUNCH_PROMPT / CLAUDE_LEAD_OPS) carry stale branding, internal contradictions, or coverage gaps relative to the rules now visible across agent memories?
audience: lead, host (selectively)
---

# Project-instruction-files cross-check

## Current refresh - 2026-05-01

All repo-local action items from this audit are now closed:

- Finding #3 is closed: AGENTS now uses stable concrete Files examples
  (`tinyassets/api/wiki.py, tinyassets/storage/__init__.py`), not
  `author_server.py`.
- Findings #4/#5/#6 are closed in AGENTS: no-destructive-git is Hard Rule
  13, plugin mirror rebuild is in Testing, and audit-decay is in Truth And
  Freshness.
- Finding #7 is informational: AGENTS now says "60-line canonical (~4 KB
  guidance)", and current STATUS.md is 50 lines / 7,344 chars.

Finding #2 remains lead-environment-only and cannot be edited from this
checkout. The original findings below are retained as history.

## Original TL;DR

Read 4 files (~750 lines total). Found:
- **0 open STALE-BRANDING hits** after 2026-04-28 cleanup. Original AGENTS.md + CLAUDE_LEAD_OPS.md hits are resolved; see finding rows #1-2.
- **1 STALE-EXAMPLE hit** (AGENTS.md L204 cites `author_server.py` as a Files-column example — that file is the in-flight Arc B rename target).
- **3 COVERAGE GAPS** vs rules in agent memory: no-destructive-git, plugin-mirror-rebuild, audit-staleness — all are repeat-rules across multiple agent memories with no shared codification in AGENTS.md.
- **1 INTERNAL CONTRADICTION** (low severity): AGENTS.md "Three Living Files" table at L49-53 says STATUS.md ≤4 KB / 60 lines. STATUS.md current (2026-04-28) is at 60 lines but ~5.2 KB — exceeds the byte budget. Unclear which is canonical.
- **0 cross-file contradictions** between AGENTS / CLAUDE / LAUNCH_PROMPT / CLAUDE_LEAD_OPS — the 4 files are mutually consistent (CLAUDE/LAUNCH_PROMPT are thin pointers to AGENTS, CLAUDE_LEAD_OPS adds situational content without contradicting).

## Original Findings

| # | Severity | File:line | Finding | Recommended action |
|---|---|---|---|---|
| 1 | **RESOLVED 2026-04-28** | `AGENTS.md:169` | Original stale branding ("Universe Server MCP connector") is gone; current text says "installed TinyAssets MCP connector at `https://tinyassets.io/mcp`". | No action. |
| 2 | **RESOLVED 2026-04-28** | `CLAUDE_LEAD_OPS.md:129` | Original stale branding ("Restart the Universe Server") is gone; current text says "Restart the TinyAssets MCP server when new code needs to go live." | No action. |
| 3 | **STALE-EXAMPLE** | `AGENTS.md:204` | "Be concrete: `api.py, author_server.py` not `backend`." `author_server.py` is the in-flight Arc B rename target — already a `_rename_compat` shim per current state, scheduled for deletion in Phase 5. Using it as a "be-concrete" example teaches future contributors a name that's about to disappear. | Replace example with two stable canonical-tree filenames, e.g. `api.py, daemon_server.py` or `runs.py, market.py`. |
| 4 | **COVERAGE GAP** | `AGENTS.md` (no section) | No-destructive-git rule is host-explicit standing rule per lead memory `feedback_git_destructive` + dev memory `feedback_no_git_stash_for_diagnostics` + navigator memory `feedback_no_diagnostic_stash` + (just-saved) dev-2 memory. Rule lives in 4 agent memories but NOT in AGENTS.md proper. New contributor / new agent without those memories doesn't see the rule. | Add a 1-line "**No destructive git ops without approval.**" entry under either Hard Rules or a new "Git Discipline" subsection. References agent memory for fuller context. |
| 5 | **COVERAGE GAP** | `AGENTS.md` (no section) | Plugin-mirror-rebuild rule (`python packaging/claude-plugin/build_plugin.py` after `tinyassets/*` canonical edits, otherwise pre-commit blocks the commit) lives in dev memory + navigator memory + (just-saved) dev-2 memory. Not codified in AGENTS.md or any shared truth file. | Add a 1-line entry under Testing or a new "Packaging Mirrors" subsection. References `packaging/INDEX.md` for the broader packaging map. |
| 6 | **COVERAGE GAP** | `AGENTS.md` (no section) | Audit-staleness rule (audits >24h are routinely stale; freshness-check before dispatching) lives in 4 agent memories (dev/navigator/lead/dev-2). The "Truth And Freshness" section L104-111 covers verification-claim freshness but not audit-doc freshness specifically. | Add a 1-line entry under "Truth And Freshness" — "**Audit docs decay too.** Run a freshness check (git log + grep + spot-read) on any audit older than ~24h before dispatching its prescriptions." References memory. |
| 7 | **INTERNAL CONTRADICTION (low severity)** | `AGENTS.md:53` vs current STATUS.md size | "STATUS.md … ≤4 KB / 60 lines." STATUS.md as of 2026-04-28 is 60 lines but ~5.2 KB (lines are dense). Either the byte budget is canonical and STATUS is over budget, or the line budget is canonical and the byte budget is informational. | Clarify in AGENTS.md whether the budget is byte-canonical or line-canonical. STATUS.md often hits the budget edge; ambiguity costs reader/janitor confidence. |

## Per-file character

### AGENTS.md (382 lines, ~17.6 KB)

The most content-heavy of the 4. Owns process truth + hard rules + env-var contract. Findings cluster here because it's the largest target.

Section structure is well-organized:
- Forever Rule + Three Living Files + How to Work + Team Norms + Two Task Systems + Parallel Dispatch + Hard Rules + Testing + Configuration + Project Files

The STATUS.md rules section (L94-102) and the Truth-And-Freshness section (L104-111) are both strong but overlap slightly (both cover "delete resolved concerns"). Not a contradiction — just minor redundancy.

### CLAUDE.md (49 lines, ~2.5 KB)

Thin Claude-Code-specific routing layer. Inherits AGENTS.md + STATUS.md (`@AGENTS.md`, `@STATUS.md`). Adds: Agent Teams system, verification implementation, skill mirroring, agent memory location, lead-ops pointer, continuous-learning rule.

Internal consistency: clean. No findings.

### LAUNCH_PROMPT.md (115 lines, ~5.2 KB)

Session startup + team spawn protocol + lead norms. The 4 core teammates (dev/dev-2/verifier/navigator) + on-demand (user/critic). Stale-team-recovery mechanics. Floater swap protocol.

Internal consistency: clean. References `docs/audits/2026-04-25-despawn-chain-protocol.md` for the despawn chain — verified that audit exists. No findings.

### CLAUDE_LEAD_OPS.md (157 lines, ~7.5 KB)

Situational lead guidance: foundation-vs-feature, daemon-economy-as-foundation, code-before-agents (invariant hooks), name-collision awareness, tool-use-limit-as-architectural-signal, minimum-active-dev-floor, continuous-live-shipping, token-efficiency, user-sim lifecycle.

Original stale-branding hit at L129 is resolved. Otherwise content is current and aligned with agent-memory rules (continuous-dev-queue, dev-always-busy, never-idle).

## Cross-file consistency check

### "Continuous dev queue / minimum active-dev floor"

- `LAUNCH_PROMPT.md:81-87` (Continuous Dev Queue)
- `CLAUDE_LEAD_OPS.md:98-122` (Minimum Active-Dev Floor — "Hard rule: 2 devs always running, always busy")
- Lead memory: `feedback_dev_always_busy.md` + `feedback_keep_dev_active.md` + `feedback_floating_fifth_teammate.md`

All three surfaces agree; LEAD_OPS goes deepest. Consistent.

### "Verification is structural" / "Final chatbot-surface verification is live Claude.ai"

- `AGENTS.md:163-178` (Quality Gates section)
- `CLAUDE.md:18-23` (Verification Implementation)

CLAUDE.md correctly defers to AGENTS.md for invariants and adds Claude-Code-specific implementation (persistent verifier teammate). Consistent.

### "STATUS.md is host-managed / evidence-based-retire is OK"

- `AGENTS.md:94-102` (STATUS.md deletion rules — owned by anyone reading it)
- Lead memory: `feedback_status_md_host_managed.md` (don't auto-delete) + `feedback_status_md_evidence_based_retire.md` (OK with evidence)

These are NOT contradictory but they're nuanced. AGENTS.md says "every reader is a janitor" (L65). Lead memory says "host curates and reverts auto-trims" (the host-managed rule). The reconciliation is the evidence-based-retire refinement: lead/navigator may retire with citation, but gut-feel-trim is forbidden.

**Soft suggestion (not a finding):** the evidence-based-retire refinement is in lead memory only. Worth surfacing to AGENTS.md so other agents/providers see it. Not a hard contradiction; just a clearer place to put it.

## Current action queue - 2026-05-01

No repo-local action remains from this audit. Findings #3/#4/#5/#6 are closed
in AGENTS. Finding #7 is informational under the current "60-line canonical
(~4 KB guidance)" wording. Finding #2 remains lead-environment-only.

## Original summary action queue

| Priority | Finding | Effort | Who |
|---|---|---|---|
| 1 | #1 + #2 stale branding (3 string substitutions across AGENTS.md L169 + CLAUDE_LEAD_OPS.md L129) | 5 min | dev-2 with lead approval |
| 2 | #3 stale example (AGENTS.md L204 `author_server.py` example) | 2 min | dev-2 with lead approval |
| 3 | #4 + #5 + #6 coverage-gap entries (3 new lines in AGENTS.md) | 10 min | dev-2 with lead approval |
| 4 | #7 STATUS.md budget clarification (1 word) | 2 min | lead-only (project-instruction file) |
| Optional | Soft suggestion: surface evidence-based-retire refinement to AGENTS.md | 5 min | lead-only |

## Verifier handoff

Refreshed recommendation document. No instruction file was edited by this refresh; it only records that the repo-local AGENTS changes this audit requested are already present.

No code touched. No test files touched. No dev #18 lock-set touched.
