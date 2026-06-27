---
title: User-capability-axis principle — implications across the project
date: 2026-04-26
author: navigator
status: read-only strategic discovery sweep — host curates response
companion:
  - project_user_capability_axis (memory — host directive 2026-04-26, the principle this audit applies)
  - project_user_tiers (memory — install-friction frame; complementary to capability-axis runtime frame)
  - project_minimal_primitives_principle (memory — interacts: a primitive earns more weight if it works on both tiers + both providers)
  - project_chatgpt_response_too_large_failure (memory — concrete provider-asymmetry incident)
  - docs/design-notes/2026-04-18-full-platform-architecture.md (existing capability matrix at §2.4; this audit cross-checks against it)
load-bearing-question: Where does the capability-axis principle (browser-only vs local-app × Claude vs OpenAI) change the calculus or surface implications worth surfacing?
audience: lead, host
---

# User-capability-axis implications sweep

## Executive Summary

**Total findings: 23 across 8 axes.** The principle reshapes the calculus in three structural ways:

1. **ChatGPT-side bugs (BUG-034 + the 4 STATUS Concerns 2026-04-25) reclassify from "not server bug, use the other client" to P1 product bugs.** Treating ChatGPT users as second-class violates `project_user_capability_axis` "Provider parity" imperative. 5 STATUS Concerns shift category.

2. **The full-platform architecture's §2.4 capability matrix is the install-friction frame, not the runtime-capability frame.** AGENTS.md / PLAN.md need a complementary capability-axis section so future feature scoping can label features local-app-only vs tier-portable. Cross-cutting design risk: features get scoped on the assumption "local-app for everyone" without realizing browser-only users are blocked.

3. **User-sim persona coverage has 3 critical gaps.** No T1-ChatGPT-web persona, no phone-tier persona on either provider, no T2-with-OpenAI-desktop-computer-use. Existing 5 personas skew Claude-heavy + desktop-heavy.

**Top 5 highest-leverage findings:**

| # | Finding | Action | Urgency |
|---|---|---|---|
| 1 | BUG-034 + 4 ChatGPT-approval Concerns (STATUS 2026-04-25) reclassify as P1 product bugs, not "use other client" workarounds | Re-prioritize: each becomes a real investigation, not a workaround note. Whichever the platform CAN fix gets fixed; whichever needs OpenAI cooperation gets a documented escalation path + a "while you're stuck" platform-side mitigation. | **P1** — directly violates "provider parity" imperative |
| 2 | Persona coverage gap: no T1-ChatGPT user means we have ZERO live evidence of zero-install ChatGPT UX | Add a persona: T1 ChatGPT-web user, non-technical, recreates Maya's payables flow on the OpenAI side. Drives the dispatch list for ChatGPT-side P1 bugs. | **P1** |
| 3 | "Phone-Claude.ai user" lowest-capability test target — sharp question, but evidence supports it as RIGHT canonical persona, with one refinement | Refine to "phone-Claude.ai-OR-ChatGPT user." Phone constraints (small screen, no shift-click, fat-finger, possible network drop) AND provider asymmetry stack. Lowest = phone × either provider. Recommend BOTH as canonical lowest-capability targets, not one. | **P1** — design floor |
| 4 | Recency + continue_branch primitives (host-approved 2026-04-26, queued post-#18) need re-scoped under capability-axis | Run irreducibility test (per `feedback_irreducibility_test_before_spec`) AND check both providers + both tiers. If the primitive helps local-app-with-file-system but not browser-only, fails the capability-portability test → don't ship. | **P1** — validates next pre-spec gate |
| 5 | A.1 fantasy_daemon/ unpack arc is fully aligned (engine-side reorg, no capability-tier dependency) — full speed | No re-scoping needed. The arc reduces shim surface; same principle the capability-axis serves on the layout side. | **P0** continue |

**Findings that shifted the in-flight queue: 8** (5 STATUS Concerns reclassified, plus #2 #3 #4 above, plus 1 PLAN.md edit candidate).

**Findings that ratified existing direction: 9.** The minimal-primitives principle (re-tested under capability-axis), the A.1 unpack arc, decomp arcs, methods-prose REFRAME, privacy-modes REFRAME, the SWEEP 1 + SWEEP 2 dispatch queue — all ratified.

**Findings flagged for backlog: 6.** UX-tier-specific docs (phone-Claude.ai conventions doc, ChatGPT-MCP differences doc), persona expansion, skill-tier annotation pass.

---

## 1. In-flight code + design work — capability-tier sensitivity

### F1 — Recency + continue_branch primitives (host-approved 2026-04-26)

**Location:** Queue post-#18 SHIP per STATUS Work table.

**What the principle changes:** A primitive earns its keep MORE if it works equivalently across both tiers + both providers. Test before drafting spec:
- Does `extensions action=my_recent_runs` work the same way on Claude.ai (T1) AND ChatGPT (T1) AND Claude Code (T2 local-app) AND ChatGPT desktop (T2 local-app)?
- Specifically: ChatGPT's "response too large" failure (`project_chatgpt_response_too_large_failure`) means the response shape needs to fit OpenAI's stream-folding budget. Recency tool returning N runs with full metadata might cross the threshold for ChatGPT but not Claude. Provider-asymmetric output is itself a design failure.

**Recommended action:** When this lands on navigator's queue, run TWO tests sequentially:
1. **Irreducibility** (per `feedback_irreducibility_test_before_spec`): can a competent chatbot compose this in <5 reasoning steps? If yes → community-build.
2. **Capability-portability**: does the proposed shape work on (Claude.ai phone) AND (ChatGPT desktop)? If response budget asymmetric, design a SUMMARY-by-default shape with `verbose=true` opt-in per `project_chatgpt_response_too_large_failure` system-fix recipe.

**Who picks it up:** navigator (when on queue post-#18).

**Urgency:** P1 — first concrete application of the principle to a host-approved primitive.

### F2 — Methods-prose evaluator (REFRAMED community-build per STATUS Concern 2026-04-26)

**What the principle changes:** Already validated under `project_minimal_primitives_principle`. Capability-axis adds a check: the wiki-rubric + chatbot-composition workaround works on T1 browser-only too (no local-app required). Confirmed alignment.

**Action:** No change. The REFRAME stands. Capability-axis principle ratifies the decision.

**Urgency:** P2 — already resolved; flagging for completeness.

### F3 — Privacy-modes design note (3 host Qs blocked per STATUS 2026-04-17)

**Location:** `docs/design-notes/2026-04-18-privacy-modes-for-sensitive-workflows.md` — explicitly opens with "Constraint: The chat interface is Claude.ai webchat. Not optional. Local-chatbot alternatives are out of scope for this design."

**What the principle changes:** The design note's constraint is correct for T1 browser-only Claude.ai, but the privacy story is INCOMPLETE without parallel notes for:
- T1 ChatGPT-web (different retention policies, different injection surface)
- T2 local-app on either provider (where local-LLM routing IS available — alternative privacy model)

Per the principle, "Provider parity: Bugs that work on Claude.ai but not ChatGPT (or vice versa) are P1 product bugs." Privacy-mode design omitting ChatGPT means ChatGPT users get no privacy answer.

**Recommended action:** Privacy-modes note stays as-is for Claude.ai, but flag that a SIBLING note is needed for the OpenAI-side privacy story before this design ships. Alternatively, generalize the existing note to cover both providers' webchat flow with the same enforcement-at-response-body strategy.

**Who picks it up:** navigator (when host unblocks the 3 Qs and re-engages with the spec).

**Urgency:** P2 — already blocked on host-Qs; capability-axis adds 1-2 more Qs to the batch.

### F4 — Claude.ai injection mitigation (STATUS 2026-04-18 blocked on host-Q batch)

**Location:** `docs/design-notes/2026-04-18-claude-ai-injection-hallucination.md`

**What the principle changes:** Same shape as F3. Mitigation is Claude.ai-specific by design. ChatGPT has its own injection vectors (different prompt-injection surface, different system-message handling). The mitigation work covers ONE provider; the other gets nothing.

**Recommended action:** Same as F3 — sibling note for OpenAI side, OR generalize.

**Urgency:** P2.

### F5 — `add_canon_from_path` sensitivity note (STATUS 2026-04-18, 3 host asks)

**Location:** `docs/design-notes/2026-04-18-add-canon-from-path-sensitivity.md`

**What the principle changes:** `add_canon_from_path` tool requires LOCAL FILE SYSTEM access — by definition only works for T2 local-app users. Browser-only T1 users CAN'T use it (no file system). This is a tier-restricted tool that must be flagged.

**Recommended action:** Confirm the design note treats this as local-app-only explicitly. If browser users hit `add_canon_from_path` via the chatbot, the response should detect tier and return "this requires local app capability; here are 3 alternative ways to provide canon: paste it inline, paste a URL we can fetch, upload to a wiki page." Tier-aware error path.

**Urgency:** P2 — already blocked on host-Qs; add capability-aware error path to the spec.

### F6 — `chatgpt_response_too_large_failure` (STATUS Concern 2026-04-25 + memory)

**Location:** `project_chatgpt_response_too_large_failure` memory + STATUS rows.

**What the principle changes:** Currently the workaround list reads "use Claude.ai instead" as one of the bullet points. Per the principle, that's an anti-pattern: "Use Claude Code instead as a fix for a Claude.ai web bug — abandons the browser-only tier."

**Recommended action:** Promote the SYSTEM-side fix (SUMMARY-by-default response shape with `verbose=true` opt-in) to a P1 design item. The existing user-facing workarounds stay, but "try Claude.ai" should be the LAST resort, not the first.

**Who picks it up:** navigator drafts spec for SUMMARY-by-default response shape; dispatchable to dev once host approves.

**Urgency:** P1 — validates the principle directly, fixes the asymmetry.

---

## 2. STATUS Concerns — re-prioritization

### F7 — BUG-034 ("All extensions actions: No approval received") — RECLASSIFY from "not server bug" to P1 PRODUCT BUG

**Current STATUS row (2026-04-26):**
> "BUG-034 ("No approval received") = ChatGPT connector approval bug, not server bug. Workaround in wiki chatbot-builder-behaviors page; status-comment deferred to post-redeploy."

**What the principle changes:** "Not server bug" treats this as out-of-scope. Per `project_user_capability_axis` Provider Parity imperative, ChatGPT-only bugs are P1 platform bugs. The right framing: "ChatGPT connector approval flow has a UX failure on every `extensions` action; until OpenAI fixes the connector, we ship a platform-side mitigation that EITHER routes around the approval prompt OR makes the approval flow more reliable."

**Recommended action:** Promote BUG-034 to active investigation. Two parallel tracks:
1. **Platform-side:** can we shape the `extensions` tool calls so they trigger fewer approval-prompt failures? (e.g., call signatures that ChatGPT recognizes as safer, error responses that prompt retry, etc.)
2. **OpenAI-side escalation:** file a bug with the ChatGPT connector team if not already done. Track in STATUS.

**Who picks it up:** navigator drafts the investigation framing; dev investigates platform-side; host escalates OpenAI-side.

**Urgency:** P1 — directly violates principle.

### F8 — STATUS 2026-04-25 "ChatGPT publish blocked in current login" — RECLASSIFY

**Current state:** Workspace-admin issue blocking publication.

**What the principle changes:** Same pattern. Treating "publish blocked because login is wrong tier" as a host-action item is correct, but the underlying problem is ChatGPT users have a bumpier path to discovery than Claude.ai users.

**Recommended action:** Resolve the workspace-admin login (host-action), AND add a STATUS row "ChatGPT discovery friction = P1 product issue" tracking the broader UX gap (e.g., what should the ChatGPT GPT Store listing say? Is it findable?).

**Urgency:** P1.

### F9 — STATUS 2026-04-25 "ChatGPT connector approval bug: Update Node approval errored"

**What the principle changes:** Same as F7. RECLASSIFY to P1 product bug.

**Recommended action:** Same playbook as F7 — platform-side mitigation track + OpenAI-side escalation track.

**Urgency:** P1.

### F10 — STATUS 2026-04-25 "ChatGPT Run Branch approval stalled"

**What the principle changes:** Same as F7. RECLASSIFY.

**Urgency:** P1.

### F11 — STATUS 2026-04-25 "ChatGPT UX: normal users need name-based workflow refs, not raw branch IDs"

**What the principle changes:** This is a legitimate UX gap that affects T1-ChatGPT users harder than T1-Claude.ai users (Claude.ai chatbot can compose the name→ID mapping more reliably from context). Per provider parity, this is a P1 product issue.

**Recommended action:** Promote to active spec work. Name-based refs as a primitive that BOTH providers' chatbots can use.

**Urgency:** P1 — chatbot-leverage win; capability-portable.

### F12 — STATUS 2026-04-26 BUG-034 + chatgpt_response_too_large_failure (covered F7 + F6)

Already addressed.

### F13 — Cloud daemon redeploy (STATUS Work-table host-action)

**What the principle changes:** Current state lists it as "host action — DO droplet." Per capability-axis, a cloud-daemon redeploy that closes 5 ChatGPT-side concerns (per STATUS 2026-04-25) becomes higher priority because it's the GATE for the capability-portability bug class.

**Recommended action:** Re-flag as time-critical. Every additional day of delay is a day of provider-parity violation.

**Urgency:** P0 — already on host-action queue but capability-axis sharpens it.

---

## 3. Dispatch queue — invalidate / accelerate / deprioritize

### F14 — Tool-description hardening (#22 queued post-#18)

**Description:** "Move behavioral directives to prompts so chatbots don't absorb tool descriptions as instructions."

**What the principle changes:** Tool descriptions are read by BOTH Claude.ai's MCP layer AND ChatGPT's MCP layer. They render differently — Claude weighs them as system context, ChatGPT may inject them differently. The hardening work is capability-portable BUT must be tested on both providers, not just Claude.ai.

**Recommended action:** When dispatching #22, add explicit verification step: live mission on BOTH Claude.ai AND ChatGPT (via Mark-style ChatGPT connector) confirms hardened descriptions don't change behavior negatively on either.

**Urgency:** P1 — already queued; just add the cross-provider verification gate.

### F15 — A.1 fantasy_daemon/ unpack arc (host queue)

**What the principle changes:** Engine-internal reorganization; no capability-tier dependency. The 4 substantial files (api.py, __main__.py, branch_registrations.py, testing/__main__.py) and 118 shims are all behind the engine seam — chatbot users (any tier, any provider) see no difference.

**Recommended action:** No change. Continue full speed. The arc REDUCES surface complexity which is the same direction the capability-axis principle points (smaller, sharper primitive set works on more clients).

**Urgency:** P2 — host queue.

### F16 — Phase-docstring + B.1 bundle (Task #21, queued post-#18)

**What the principle changes:** Internal docstrings + test rename. Zero capability-tier dependency. Continue.

**Urgency:** P2.

### F17 — Decomp Steps 1-11 + Arc B/C/Phase 6 (in flight + queued)

**What the principle changes:** All reduce primitive surface / shim mass / aliasing. Aligned with the capability-axis principle's spirit (the smaller the surface, the more uniformly it works across clients).

**Urgency:** P0 continue.

### F18 — Recency + continue_branch (host-approved 2026-04-26) — covered F1

Already addressed.

---

## 4. PLAN.md — capability-axis annotations

### F19 — PLAN.md needs a §"Capability axis" complementing §"Engine and Domains"

**Current state:** PLAN.md's user-tier framing matches `project_user_tiers` (install-friction). The runtime-capability axis (browser-only vs local-app × Claude vs OpenAI) is in `project_user_capability_axis` memory but NOT in PLAN.md. Future feature scoping reading PLAN.md gets only half the frame.

Per AGENTS.md "Architecture truth lives in PLAN.md," the principle deserves a PLAN.md section.

**Recommended action:** Lead surfaces to host: add a §"Capability axis" to PLAN.md cross-referencing `project_user_capability_axis`. Not a doc-edit task for navigator — host owns PLAN.md changes.

Recommended PLAN.md text (suggestion only):
> **Capability axis (orthogonal to install tier).** Every feature and primitive labels its capability dependency:
> - **TIER-PORTABLE** — works on browser-only T1 + local-app T2 equally.
> - **LOCAL-APP-ONLY** — requires file system / local execution / computer-use. Browser-only users see a tier-aware fallback or "unavailable in your tier" message.
> - **PROVIDER-AGNOSTIC** — works on Claude AND ChatGPT.
> - **PROVIDER-SPECIFIC** — flag explicitly. Provider-specific features must include a parallel design for the other provider.
> Default expectation: every new primitive is tier-portable + provider-agnostic. Exceptions are documented in the design note.

**Who picks it up:** lead/host (PLAN.md change).

**Urgency:** P1 — affects every future scoping decision.

### F20 — PLAN.md §"Module Layout" should call out tier-restricted modules

**Current state:** PLAN.md likely doesn't enumerate which modules are local-app-only (e.g., `tinyassets/desktop/launcher.py`, `tinyassets/sandbox/`, `add_canon_from_path` in `tinyassets/api/extensions.py`). New contributors don't know which features are tier-restricted vs tier-portable.

**Recommended action:** Lead surfaces to host: add a "Tier dependency" annotation to module-layout entries that have one. Cross-references `project_user_capability_axis`.

**Urgency:** P2 — readability win.

---

## 5. Skills — tier assumptions

### F21 — `ui-test/SKILL.md` is Claude.ai-biased

**Location:** `.agents/skills/ui-test/SKILL.md` (and 2 mirrors).

**Current state:** Skill description: "Simulate a Claude.ai phone user driving the TinyAssets daemon via the custom MCP connector." All examples reference Claude.ai phone. ChatGPT path mentioned briefly ("Codex / ChatGPT desktop route: when Codex has browser or computer control, use it only to drive the same live Claude.ai session...").

**What the principle changes:** Per provider parity, ui-test should support BOTH Claude.ai AND ChatGPT user-simulation as first-class. "Drive the same live Claude.ai session" via Codex defeats the purpose of testing the OpenAI side.

**Recommended action:** Edit skill to add a parallel "ChatGPT-web user-sim" mode with its own driver script (like `claude_chat.py` but for ChatGPT). Hosts can then verify on either provider via the same skill. This dovetails with F2 (T1-ChatGPT persona need).

**Who picks it up:** navigator drafts edit; lead dispatches to dev or dev-2.

**Urgency:** P1 — load-bearing skill, capability-portability gap.

### F22 — Other skills are tier-agnostic — no further action

`cloudflare-ops`, `godaddy-ops`, `git-workflow-and-versioning`, `code-review-and-quality`, etc. are operator/dev skills, not user-tier-tied. No capability-axis implications.

---

## 6. User-sim coverage — persona gaps

### F23 — Persona tier+provider mix matrix

| Persona | Tier | Provider | Surface |
|---|---|---|---|
| Maya Okafor | T1 | Claude.ai | Phone + laptop browser |
| Priya Ramaswamy | T1 | Claude.ai | Laptop browser (rarely phone) |
| Devin Asante | T2 | Claude.ai (?) | Daemon host, terminal-comfortable |
| Mark | T2 | ChatGPT connector | Desktop, ChatGPT-primary |
| Ilse Marchetti | T3 | (provider-agnostic, OSS) | Desktop, dev tools |

**Coverage gaps:**

1. **No T1-ChatGPT-web user.** Maya + Priya are both Claude.ai. We have ZERO live evidence of how a non-technical user does the Workflow zero-install flow on ChatGPT. **HIGH RISK** — every T1-ChatGPT bug we hit (BUG-034 + 4 STATUS Concerns 2026-04-25) is hitting a population we don't simulate.
2. **No phone-ChatGPT user.** Maya covers phone-Claude. ChatGPT phone has its own UX shape (different chat UI, different MCP rendering, different copy/paste behavior).
3. **No T2-local-app-with-OpenAI-desktop-computer-use user.** Mark uses the ChatGPT connector but isn't using OpenAI's desktop app's computer-use. As OpenAI gets parity with Claude Code's local capabilities, we have no persona testing that.

**Recommended action:** Add 1-2 personas. Highest leverage:
- **NEW PERSONA: T1-ChatGPT-web non-technical user.** Recreates Maya's payables flow on ChatGPT side. Names: clerical, accounting, bookkeeping persona but with ChatGPT as primary AI. **PRIORITY: P1** — drives the dispatch list for ChatGPT-side P1 bugs.
- **NEW PERSONA: T1-phone-ChatGPT user.** Recreates Maya's phone-during-commute pattern but on ChatGPT mobile.

**Who picks it up:** navigator drafts persona briefs (identity.md + passion_project.md); host approves; user-sim dispatches mission.

**Urgency:** P1 — gap directly violates principle's "provider parity" + "phone canonical lowest-capability target."

### F24 — Mark's coverage is genuine but recent — keep building on it

Mark is the only ChatGPT-connector live evidence. The 5 STATUS Concerns 2026-04-25 + BUG-034 all came from Mark sessions. Mark continues to drive ChatGPT-side discovery. But Mark is a TECHNICAL persona (AI developer); ChatGPT also has a HUGE non-technical user base. Mark's bugs reproduce for clerical-Maya-on-ChatGPT, but we have no live evidence.

**Recommended action:** Keep Mark active; PARALLEL non-technical ChatGPT persona per F23.

**Urgency:** P1 (folds into F23).

---

## 7. Provider-parity bug class — confirmed asymmetries from existing artifacts

### F25 — Documented asymmetries (Claude works, ChatGPT doesn't or vice versa)

| Asymmetry | Source | Status |
|---|---|---|
| ChatGPT "response too large" on `build_branch` / `patch_branch` ≥30-50 KB | `project_chatgpt_response_too_large_failure` memory | LIVE — system fix proposed (SUMMARY-by-default + verbose opt-in), not yet shipped |
| BUG-034 "All extensions actions: No approval received" on ChatGPT, all extensions actions broken | wiki BUG-034 + STATUS 2026-04-26 | LIVE — workaround documented in `pages/plans/chatbot-builder-behaviors.md` |
| ChatGPT Update Node approval errored, retry works | STATUS 2026-04-25 | LIVE — root cause unknown |
| ChatGPT Run Branch approval stalled after access grant; no run ID rendered | STATUS 2026-04-25 | LIVE — root cause unknown |
| ChatGPT raw-branch-ID UX: ChatGPT can't reliably compose name → ID, Claude.ai can | STATUS 2026-04-25 | LIVE — name-based refs as primitive (F11) |
| Claude.ai chatbot vocabulary memory absorbs project-internal vocabulary (LIVE-F7 Devin Session 1); ChatGPT may have different absorption pattern | `tests/test_vocabulary_hygiene.py` + Devin session | KNOWN; ChatGPT-side untested |
| Tool descriptions: Claude weighs as system context, ChatGPT may render differently | F14 above | UNKNOWN — needs cross-provider verification on tool-description-hardening pass |
| Claude.ai default 5-year retention vs ChatGPT retention TBD | privacy-modes design note + ChatGPT TOS | KNOWN ASYMMETRY |
| Claude.ai shared-chat-history hallucination (Devin Session 2 §6) on fresh chat; ChatGPT-side equivalent unknown | output/user_sim_session.md L1775 | KNOWN; ChatGPT-side untested |

**Recommended action:** Compile this into a living "Provider Asymmetries" wiki page or design note. Currently spread across STATUS / memory / wiki / chat trace. Each asymmetry needs an owner + a track-or-resolve decision.

**Who picks it up:** navigator drafts the consolidated doc; lead routes ownership.

**Urgency:** P1 — central capability-axis enforcement surface.

---

## 8. Lowest-capability test target — refining the "phone-Claude.ai user" canonical persona

### F26 — Sharp question + recommendation

**Lead's question to host:** is "phone-Claude.ai user" the right canonical lowest-capability test target?

**Evidence FOR:**
- `ui-test/SKILL.md` already canonicalizes phone-Claude.ai user-sim as the default driver.
- Maya (Tier-1) primary persona is phone-during-commute on Claude.ai.
- Phone constraints are real (small screen, no shift-click, no copy-paste reliability, possible network drop).
- "Browser-only" subsumes phone (mobile is a strict subset of browser-only by capability).

**Evidence AGAINST (sole canonical):**
- Provider parity: phone-Claude.ai is HALF the lowest-capability surface. Phone-ChatGPT is the other half.
- ChatGPT mobile has different MCP rendering, different chat UI conventions, different connector approval flow (BUG-034 may manifest worse on phone).
- A test that passes on phone-Claude.ai but fails on phone-ChatGPT still violates the principle.

**Recommendation:** **The lowest-capability canonical persona is "phone-Claude.ai-OR-ChatGPT user."** Both must pass. Treating them as a single conceptual persona (a phone-browser-only user with tier-portable AI) keeps the test-target small, while forcing both providers to be exercised. Add to user-sim coverage per F23.

**Refinement to propose:** the canonical test isn't "phone-Claude.ai user can do X." It's "phone-browser-only user (provider doesn't matter) can do X" — and the test runs on BOTH providers' phone-web UIs.

**Who picks it up:** host decides; lead implements per skill update + persona expansion.

**Urgency:** P1 — design floor decision.

---

## 9. Cross-cutting recommendations

### Compile a "Provider Asymmetries" living surface (F25)

Currently provider-asymmetric bugs/behaviors are scattered. Centralize into one of:
- `docs/concerns/provider-asymmetries.md` (concern-tier surface) — recommend
- New STATUS section "Provider parity" — too noisy for STATUS budget
- Wiki page `pages/plans/provider-parity.md` — could work, but wiki is user-writable, less authoritative

**Recommendation:** `docs/concerns/provider-asymmetries.md` per AGENTS.md concerns convention. Lead dispatches to navigator (or dev-2 once dispatched).

### Add F23's persona briefs to user-sim coverage plan

T1-ChatGPT-non-technical persona is the highest-leverage gap. Brief should include:
- Demographic: non-technical, ChatGPT as primary AI
- Persona names: TBD (lead/host pick)
- Tier: 1
- Capability surface: browser-only + ChatGPT
- Mission scaffolding: recreate Maya's payables flow on ChatGPT side; surface every parity gap

### Audit 5 STATUS Concerns 2026-04-25/26 with reclassification

Per F7-F12: each ChatGPT-side concern reclassifies from "use other client" to P1 product bug. Lead curates STATUS Concern wording.

---

## 10. Decision asks for the lead → host

1. **Confirm the reclassification** of 5 STATUS Concerns from "ChatGPT-side, not server bug" to P1 product bugs requiring platform-side mitigation tracks?
2. **Approve T1-ChatGPT non-technical persona** addition to user-sim coverage? Highest-leverage gap.
3. **Refine canonical lowest-capability target** to "phone-browser-only user (Claude.ai OR ChatGPT)"? Both must pass.
4. **Approve PLAN.md §"Capability axis" addition** per F19? (PLAN.md changes need host approval per AGENTS.md.)
5. **Approve `docs/concerns/provider-asymmetries.md` consolidation** per F25 + cross-cutting recommendation?
6. **`ui-test` skill** edit to add ChatGPT-web user-sim mode as parallel driver per F21?
7. **For Recency + continue_branch primitives** (F1): when this lands on navigator's queue post-#18, should I (a) run the irreducibility + capability-portability tests THEN draft spec, or (b) draft spec then test? Recommend (a) — gates wasted spec work.

---

## 11. Cross-references

- `project_user_capability_axis` (memory — host directive 2026-04-26, the principle this audit applies)
- `project_user_tiers` (install-friction frame — complementary)
- `project_minimal_primitives_principle` (interacts: capability-portability is a multiplier on irreducibility test)
- `project_chatgpt_response_too_large_failure` (memory — concrete asymmetry incident)
- `project_chatbot_assumes_workflow_ux` (applies to both tiers + both providers)
- `project_chatbot_visuals_first` (applies to both — needs cross-provider verification)
- `feedback_irreducibility_test_before_spec` (navigator-applied test — extend with capability-portability check per F1)
- `docs/design-notes/2026-04-18-full-platform-architecture.md` §2.4 (existing capability matrix; ratifies but is install-friction-only)
- `docs/audits/2026-04-26-legacy-branding-comprehensive-sweep.md` + `2026-04-26-architecture-edges-sweep.md` (sibling audits)
- `tests/test_vocabulary_hygiene.py` (chatbot-vocabulary regression contract — needs cross-provider verification per F14 + F25)
- STATUS.md Concerns 2026-04-25 + 2026-04-26 (re-categorize per F7-F12)
- `.agents/skills/ui-test/SKILL.md` (Claude.ai-biased — F21)
- `output/user_sim_session.md` + `output/claude_chat_trace.md` (chat-trace evidence base)
- `docs/design-notes/2026-04-18-privacy-modes-for-sensitive-workflows.md` (Claude.ai-only — F3)
- `docs/design-notes/2026-04-18-claude-ai-injection-hallucination.md` (Claude.ai-only — F4)
- `docs/design-notes/2026-04-18-add-canon-from-path-sensitivity.md` (local-app-only — F5)

---

## ADDENDUM 2026-04-27 — OSS-client compatibility bucket (host directive update)

Host updated `project_user_capability_axis` mid-sweep to add the long-tail OSS-client tier:

> **Long-tail OSS-clients** (OpenClaw, Cline, Aider, Continue, Cursor chat, OpenWebUI, LibreChat, etc.) — most use Claude or OpenAI keys under the hood, so the underlying model is in-target even when the wrapper is third-party. Provider-portable patterns are the rule. OSS clients get best-effort support via MCP-to-spec; client-specific quirks are documented but don't drive platform design.

**New anti-pattern added to memory:**
> Hard-coding assumptions about which chat client renders responses (e.g., assuming Claude.ai's mermaid rendering is universal — Cline/Aider/OpenWebUI may render differently or not at all). Test on at least one OSS client periodically to keep the provider-portable assumption honest.

### F27 — `tinyassets/api/prompts.py` `_CONTROL_STATION_PROMPT` is Claude.ai-named in 15 places

**Location:** `tinyassets/api/prompts.py` (the canonical chatbot-facing system prompt loaded by every MCP session).

**What the principle changes:** 15 references to `Claude.ai` / `ChatGPT` / `connector` in `_CONTROL_STATION_PROMPT` text. Examples:
- L91 ("Shared-account / cross-session: ... One Claude.ai account may be used by multiple people")
- L149 ("Mermaid renders in Claude.ai and ChatGPT both; markdown tables render everywhere")
- L228 ("Claude.ai per-turn tool-call budget. Default to `build_branch`")

OSS-client users (Cline, Aider, OpenWebUI) reading these via MCP get false signals: "your account isn't a Claude.ai account; this rule doesn't apply to you" or worse, the rule's intent is opaque.

**Recommended action:** Reword to provider-portable language. Replace "Claude.ai account" → "chat-client account"; "Claude.ai per-turn tool-call budget" → "chat-client per-turn tool-call budget"; "Mermaid renders in Claude.ai and ChatGPT" → "Mermaid renders in many chat clients but markdown tables render everywhere — prefer tables when one form must work" (this also addresses F30 below). Provider-specific phrasing only when truly client-specific (e.g., OAuth approval flow text for shared-account asking).

This bundles cleanly into Task #22 (tool-description hardening) — same scope, same skill. Recommend EXTEND #22's brief to explicitly include client-portability rewording.

**Who picks it up:** dev-2 via Task #22 (post-#18).
**Urgency:** P1 — every MCP session reads this prompt.

### F28 — `add_canon_from_path` design note assumes "Claude Desktop / Claude.ai" approval UX

**Location:** `docs/design-notes/2026-04-18-add-canon-from-path-sensitivity.md:63`:
> "There is no FastMCP primitive we can set to force Claude Desktop / Claude.ai to re-prompt on every call."

**What the principle changes:** Statement is correct for those two clients but doesn't reflect that OSS clients (Cline, Aider, OpenWebUI) likely have NO approval UX at all — meaning there's no client-side gate to rely on for sensitive operations. Tool that assumes client-side approval as a guard fails-open on OSS clients.

**Recommended action:** Sibling note OR generalize. Recommend: add §"Approval-flow assumptions across clients" to the existing note enumerating the matrix — Claude.ai (per-tool prompt), ChatGPT (per-tool prompt, BUG-034 flaky), Claude Desktop (per-tool prompt + always-allow), OSS clients (varies, often none). Server-side defenses (path-whitelist, sensitivity tier) are the only portable enforcement.

**Who picks it up:** navigator (folds into existing F5 "host-Q batch waiting").
**Urgency:** P2 — already blocked on host-Qs; addendum tightens the scope.

### F29 — Injection-hallucination mitigation (`2026-04-18-claude-ai-injection-hallucination.md`) is Claude.ai-specific by name AND content

**Location:** Full file is Claude.ai-named. 8+ refs in body explicitly cite "Claude.ai's injection heuristic" as the failure mode.

**What the principle changes:** ChatGPT may have its own injection heuristics. OSS clients (especially those passing prompts through Claude/OpenAI APIs directly) may inherit the same heuristic OR have completely different ones. The mitigation strategy needs cross-client validation.

**Recommended action:** Already flagged as F4. Sibling note or generalization required. ADDENDUM scope: also test on at least one OSS client (Cline or OpenWebUI) to keep the assumption honest per the new anti-pattern.

**Who picks it up:** navigator (when host unblocks F4 host-Q batch).
**Urgency:** P2.

### F30 — Mermaid rendering as a load-bearing chatbot-output convention

**Location:**
- `tinyassets/api/branches.py:742-770` — `_branch_mermaid()` renderer
- `tinyassets/api/runs.py:84,89` — `get_run` emits ```mermaid``` block
- `tinyassets/universe_server.py:541` — comment "`get_run` emits a ```mermaid``` diagram for Claude.ai auto-render"
- `project_chatbot_visuals_first` memory — visuals-first rule

**What the principle changes:** Mermaid renders in Claude.ai web + ChatGPT + Claude Code. **Probably DOES NOT render in:** OpenWebUI (renders only if mermaid plugin installed), Cline (terminal-based, no render), Aider (terminal-based, no render), LibreChat (varies by config). For these, mermaid blocks render as raw fenced text — readable but ugly + no graph layout.

The comment at `universe_server.py:541` ("for Claude.ai auto-render") even explicitly cites Claude.ai as the assumption.

**Recommended action:**
1. Update `project_chatbot_visuals_first` memory: visuals-first means "prefer visuals, but always include a markdown-table fallback that renders everywhere."
2. Audit all canonical mermaid emitters (3 files above) to ensure they ALSO emit a markdown-table or ASCII-flow representation alongside or as fallback. `_branch_mermaid()` could return mermaid + a small node-list table; chatbot picks based on its own knowledge of client capability.
3. Update the comment at `universe_server.py:541` to drop "Claude.ai" (post-decomp it's already a docstring inside the canonical post-rename file).
4. The control-station prompt at `prompts.py:149` already tells the chatbot "markdown tables render everywhere" — this is the correct framing. Verify the codebase EMITS in that frame, not just instructs the chatbot to.

**Who picks it up:** navigator drafts the fallback strategy; dev-2 implements per dispatch.
**Urgency:** P1 — affects every chatbot-rendered diagram. Folds into Task #22 OR a sibling task ("output-rendering-portability").

### F31 — `chatbot_assumes_workflow` rule wording test against OpenWebUI

**Location:** `tinyassets/api/prompts.py:_CONTROL_STATION_PROMPT` rules 1-12 + the user-vocabulary rule.

**What the principle changes:** Per the new anti-pattern, "test on at least one OSS client periodically." The `chatbot_assumes_workflow` rule body should be re-read as if the reader is Cline / Aider / OpenWebUI. Specifically:
- Rule 1 ("when user says 'workflow thing' or 'the connector'..."): "the connector" is Claude.ai-specific UI vocabulary. Cline says "MCP server"; OpenWebUI says "tool" or "function." A user on OpenWebUI typing "the workflow tool" might not match the rule's pattern.
- Rule 11 ("One Claude.ai account may be used by multiple people"): only applies to Claude.ai's account model. OSS clients have local config only, no account.

**Recommended action:** Reword rule 1's vocabulary list to be inclusive: "the workflow thing", "the connector" (Claude.ai), "the MCP" (most clients), "the tool/server" (most), "my builder" (Claude.ai), etc. Reword rule 11 to start "When chat clients have shared-account semantics (e.g., one Claude.ai account, household-shared Bitwarden)…" rather than asserting it as universal.

**Who picks it up:** dev-2 via extended Task #22 (folds into F27).
**Urgency:** P1 — bundles with F27.

### F32 — `ui-test` skill is Claude.ai-only by description (already F21)

Already covered in F21. ADDENDUM scope: the skill should grow a **third driver mode** beyond Claude.ai-phone + ChatGPT-desktop: an OSS-client mode that exercises at least one (Cline or OpenWebUI) periodically per the new anti-pattern. Probably quarterly cadence — not every mission, but never zero.

**Recommended action:** Skill edit per F21 + add OSS-client quarterly verification cadence as §"Cross-client honesty" subsection.

**Urgency:** P2 (folds into F21).

### F33 — Tool descriptions in `tinyassets/api/*` — verify NONE name a specific client

**Scan result:** Searched `tinyassets/api/` for tool description strings naming "Claude.ai" or "ChatGPT". **Zero canonical-tree matches.** Tool descriptions are already client-portable. Good.

**Recommended action:** No action needed. Confirms one axis is already clean. Tests/test_vocabulary_hygiene.py regression contract works on this axis already.

**Urgency:** N/A — ratification.

### F34 — User-sim coverage gap: zero OSS-client persona

**What the principle changes:** Per F23 the existing 5 personas already miss T1-ChatGPT-non-technical and phone-ChatGPT. Now with OSS-client tier added, there's a third gap: **no persona using Cline / OpenWebUI / Aider as primary chat client.**

Recommended persona shape: a Cline OR OpenWebUI user — small developer cohort, "I run my own LLM proxy" type. Different from Mark (technical, but ChatGPT). Different from Devin (T2 daemon host, not OSS-client).

**Recommended action:** Add to the persona-expansion proposal in F23. Lower priority than T1-ChatGPT-non-technical (which serves a much larger user population), but worth a quarterly mission per F32.

**Urgency:** P2 — backlog after F23.

### F35 — Provider-asymmetries doc (F25) needs OSS-client column

When `docs/concerns/provider-asymmetries.md` consolidation lands per F25, the asymmetry table needs THREE columns minimum: Claude / ChatGPT / OSS-clients (best-effort). Some asymmetries (mermaid rendering, approval UX) become THREE-WAY rather than two-way splits.

**Recommended action:** F25's document scope expands to a 3-column table.
**Urgency:** P1 (folds into F25).

---

### Net additions to dispatch from OSS-client addendum

**8 new findings (F27-F34, F35 expands F25):**

- **F27 + F31** — bundle into Task #22 (tool-description hardening) — extends scope to client-portability rewording. ~30 min added work.
- **F28 + F29** — fold into existing F4 + F5 host-Q batches.
- **F30** — mermaid + table fallback strategy. New small task: ~1-2h dev-2 dispatch (3 files to edit + memory update). **Could bundle as a "rendering-portability" sibling to Task #22.**
- **F32** — folds into F21 (ui-test skill edit) — adds OSS-client quarterly cadence subsection.
- **F33** — ratification, no work.
- **F34** — folds into F23 (persona expansion) — adds OSS-client persona to the priority backlog.
- **F35** — folds into F25 (provider-asymmetries doc) — 3-column table.

**Total net addendum dispatch volume: ~2-3h additional dev-2 work + ~30 min navigator persona-brief work.**

### Refined "Top 5" with addendum

The original Top 5 stand. Additions worth promoting:
- **#3 (canonical lowest-capability target) refines further:** "phone-browser-only-OR-ChatGPT" PLUS quarterly verification on at least one OSS-client. Phone is the floor by capability; OSS-client is the floor by client-control assumption.
- **#4 (Recency + continue_branch capability-portability test) gets a third gate:** does response shape work in plain markdown when no fancy rendering is available? If yes, OSS-client compatible. If no, add fallback.

### Verdict

OSS-client tier addition is a real signal but doesn't change the audit's structural conclusions. It adds **8 small follow-up findings**, all of which bundle cleanly into existing dispatch buckets (Task #22 for prompt rewording, F25 for asymmetry doc, F23 for persona expansion). No new structural arc.

The principle's spirit is consistent: "use the other one" is the anti-pattern; "best-effort via MCP-to-spec + document quirks" is the rule.
