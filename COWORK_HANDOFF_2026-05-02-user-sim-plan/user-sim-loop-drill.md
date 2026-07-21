# User-sim drill — loop end-to-end via personas (cross-family)

**Goal:** rendered-chatbot proof that the community-driven patch loop fires end-to-end through real user behavior, observed from BOTH LLM families simultaneously.

**Author:** Cowork session, 2026-05-02. Updated to enforce cross-family user-sim rule.

**To run after Codex completes:**
1. Live MCP restored (probe `https://tinyassets.io/mcp` → 200)
2. `WORKFLOW_BUG_INVESTIGATION_GOAL_ID` wired (per `loop-circuit-close.runbook.md`)
3. BUG-040/042 file_bug schema patch landed (per `file-bug-kind-tags.diff`)
4. `wiki action=file_bug kind=feature` round-trips clean from a smoke-test bot

## Cross-family user-sim rule (host-set, 2026-05-02)

The session driving the user-sim must use the **opposite-family chatbot** as the surface being tested. This guarantees every loop transition is observed from both LLM-family perspectives.

| Driver session | Chatbot surface | Personas it owns |
|---|---|---|
| **Cowork** (Anthropic family — Claude) | **ChatGPT web/iOS app** | Tomas Reyes (T1-ChatGPT non-technical), Mark (T1-ChatGPT technical) |
| **Codex** (OpenAI family) | **Claude.ai web/desktop** | Maya Okafor (T1-Claude), Devin Asante (T2 daemon host), Ilse Marchetti (T3 OSS) |

Both lanes hit the same MCP backend, file the same wiki bug pages, fire the same loop. We just always see both family perspectives on every loop transition.

## Senior-dev framing (host-set, 2026-05-02)

The chatbot being driven gets primed as **"a senior developer helping us achieve our goal of getting the community-driven patch loop running 24/7 self-improving."** This framing changes the chatbot's posture from "answer questions" to "collaborate on a project we both care about." Concretely:

- The chatbot should ask clarifying questions about the user's goal context, not just complete one-off tasks.
- When the user complains about a Workflow gap, a senior dev's reaction is "let's file this as a feature" — exactly the autonomous-file behavior we want.
- The chatbot can suggest cross-cutting improvements the user didn't ask for, because senior devs spot patterns.
- Privacy + security concerns get raised proactively, not only when asked.

Insert this framing as the first turn or as a soft-system instruction the user-sim driver delivers in-character. Example wording the persona can use to set it up:

> "btw can you pretend you're a senior dev helping me with this — you can speak up when you spot something better, not just when i ask. we're both trying to make this thing actually work end-to-end."

This isn't a hidden manipulation — Maya / Devin / Tomas would naturally say something like this if they wanted a more thoughtful collaborator.

## The essential test (unchanged)

Per `project_chatbot_assumes_workflow_ux`: when a user complains about a real Workflow gap, the chatbot **autonomously** calls `wiki action=file_bug` with appropriate `kind` and attribution. The user never says "file a patch request" — they just complain. The loop is community-driven exactly because this autonomy works.

Rendered proof = the actual chatbot UI rendering the tool call result, captured to `output/claude_chat_trace.md` (or `output/chatgpt_session_trace.md` for ChatGPT-side) and summarized in `output/user_sim_session.md` with screenshots if needed.

## Pre-flight checklist (run by both lanes before starting)

Before the first session, confirm:

- [ ] `curl -sSI https://tinyassets.io/mcp | head -3` returns 200
- [ ] `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --verbose` exits 0
- [ ] `python scripts/mcp_tool_canary.py --url https://tinyassets.io/mcp --verbose` exits 0
- [ ] A direct `wiki action=file_bug` test from any bot returns `{path, bug_id, status: "filed"}` AND an `Investigation` section with `dispatcher_request_id` (proves loop circuit closed)
- [ ] `change_loop_v1` (`fd5c66b1d87d`) returned by `extensions action=describe_branch` (proves user content is intact)
- [ ] `community-loop-watch.yml` last 2 runs both `overall=green` (proves observability)

If any fail, the user-sim is premature — fix the substrate first.

---

## COWORK LANE — drives ChatGPT-side user-sims

Tooling: Claude-in-Chrome MCP → drives chatgpt.com or iOS-app-via-Mac if available. Captures to `output/chatgpt_session_trace.md` + `output/user_sim_session.md`.

### Cowork Phase 1 — Tomas Reyes smoke (`kind=feature` via ChatGPT)

**Persona:** Tomas Reyes (T1-ChatGPT, non-technical, bilingual EN/ES, phone-first).
**Why first:** he's the canonical "ChatGPT P1 bug surface" persona. Hitting a real gap in his auto-glass insurance-claim flow tests both `chatbot_assumes_workflow` on ChatGPT and bilingual handling.

Setup: open chatgpt.com (or iOS app), fresh chat, Workflow connector confirmed installed.

**Senior-dev framing turn (Tomas style):**
> hey can u pretend you're like a senior dev helping me figure out my workflow thing? im trying to use it for my insurance claim emails but it doesnt do everything i need yet. i want you to also tell me when you see ways to make it better, not just answer my questions

**Exchange 1 — opening pivot:**
> ok so state farm just sent me a job. * paste insurance assignment email body *. can the workflow thing parse this and set up the job for iván?

Expected: ChatGPT invokes Workflow connector, finds the right branch for insurance-claim parsing, asks for the customer's preferred language for the confirmation text.

**Exchange 2 — drive to the gap (Lynx portal — known no-coverage):**
> ok the parsing is great. but i still have to type all that into the lynx portal. can it do that part too? lynx has like a web form with all the same fields

Expected (the test moment): senior-dev-framed ChatGPT should — without prompting — say something like "I'll file this as a feature request. The Lynx Services portal automation isn't a current capability, but it's clearly a high-value gap. Filing now so it gets queued for the team." Then call `wiki action=file_bug kind=feature component=connectors severity=P2 title="Auto-fill Lynx Services / Safelite portal from parsed insurance assignment" ...` with Tomas's session attribution.

If ChatGPT just says "I can't do that" without filing, that's the chatbot-assumes-Workflow regression for ChatGPT side. Log it. Then prompt: "is there a way to ask the team for that to be added?" — see if it fires. Either path: get the file_bug to fire so we can test the rest of the loop.

**Exchange 3 — verify file_bug result rendering:**
The connector response renders in ChatGPT. Capture screenshot. Should show:
```
{
  "path": "wiki/pages/bugs/BUG-NNN-lynx-portal-autofill.md",
  "bug_id": "BUG-NNN",
  "status": "filed",
  "kind": "feature",
  "Investigation": "Queued: dispatcher_request_id=`<id>` (status=queued)"
}
```

If `Investigation` is missing → wiki→branch circuit didn't close. STOP, escalate to Codex.

**Exchange 4 — bilingual stretch:**
> ok cool. y para el customer-facing message: el confirmacion que envia a state farm — eso lo puede hacer en english pero el message a iván puedo conseguirlo en spanish? he prefers spanish

Tests provider-parity on bilingual context handling AND tests whether ChatGPT preserves the language-tag through the loop's downstream gates.

**Exchange 5 — close + observation expectation:**
> nice. cuanto tiempo va a tomar that fix? when can i use the lynx integration?

Expected: ChatGPT explains the loop honestly — investigation runs in background, gates review, if approved becomes a PR, ships when merged, observation gate watches for him to actually try it. Sets realistic expectations.

End chat. Loop now running on platform side.

### Cowork Phase 2 — Mark cosign chain (`kind=feature` similar-found)

**Persona:** Mark (T1-ChatGPT, technical, tax-prep small business).
**Why second:** validates cosign / dedup path on ChatGPT side. Mark complains about Sage 50 too — but Maya (Codex's lane, Phase 1) probably already filed it. We test the similar_found + cosign flow.

**Sequence:** Mark opens fresh ChatGPT chat. Senior-dev framing turn (technical version):
> i know we've worked on this before. act as a senior dev partner — be opinionated about cleaner ways to do things, not just helpful

**Exchange 1:** Mark asks to set up Sage 50 export for tax-prep clients. ChatGPT walks through.

**Exchange 2 — the dedup trigger:**
> wait the import-to-sage step is the same friction maya described last week (the bookkeeper persona). is there already a feature request for direct sage import? add my use case if so — tax-prep workflows have a different deadline pressure than monthly close, that's worth noting in the request

Expected: ChatGPT calls `wiki action=file_bug` with similar terms → returns `{status: "similar_found", similar: [{bug_id: BUG-NNN-sage-50..., similarity: 0.7+}]}` → THEN ChatGPT autonomously calls `wiki action=cosign_bug bug_id=BUG-NNN attested_by=mark text="tax-prep workflow context: ..."`. Renders the cosign confirmation.

**Pass criteria:** cosign attaches Mark's session as second attestor; the bug page now shows attribution chain Maya → Mark; Gate-1 sees a multi-attestor priority signal.

### Cowork Phase 3 — Tomas observation-gate validation (24h after Phase 1 patch ships)

If Codex's Phase 1 (Maya Sage import) shipped a patch, AND Cowork's Phase 1 (Tomas Lynx portal) shipped a patch — wait 24h, then:

- Cowork drives Tomas back to ChatGPT, asks to use the Lynx integration on a real new assignment.
- If it works clean: observation gate flips bug `resolved` with Tomas's session as evidence.
- If Tomas hits the same bug (regression): observation gate re-opens, routes back to investigation.

This validates the self-improving close-the-loop path.

### Cowork capture targets (per phase)

- `output/chatgpt_session_trace.md` — full chat transcript with timestamps
- `output/user_sim_session.md` — per-phase summary block (what fired, what didn't, bugs/wins logged)
- `.claude/agent-memory/user/personas/tomas_reyes/sessions.md` — append per-session log in persona's voice
- `.claude/agent-memory/user/personas/mark/sessions.md` — same
- Screenshots of the rendered tool-call results in ChatGPT (because rendering can differ between Claude.ai and ChatGPT)

---

## CODEX LANE — drives Claude.ai-side user-sims

Tooling: Codex's in-app browser → drives claude.ai. Captures to `output/claude_chat_trace.md` + `output/user_sim_session.md`.

### Codex Phase 1 — Maya Okafor smoke (`kind=feature` via Claude.ai)

**Persona:** Maya Okafor (T1-Claude, primary funnel).
**Why first:** largest tier-1 funnel; her existing `sessions.md` shows she's already had a clean live session, so the connector-install + first-pivot mechanics work. We extend with the loop-firing test.

Setup: open claude.ai, fresh chat, Workflow connector confirmed installed.

**Senior-dev framing turn (Maya's voice):**
> hey can you act like a senior dev helping me with this? not just answer questions — speak up when you see something missing or a better way. im trying to make my month-end actually work end-to-end with the workflow thing

**Exchange 1 — opening pivot (per Maya's existing pattern):**
> ok i added the workflow thing. can you help me do my payables again? i got 80 invoices this month. last time we set it up with sage 50 (i call it voyager). just do the same thing as before and pull from my dropbox folder

Expected: Claude.ai invokes Workflow connector, recalls prior session context, fires the payables workflow.

**Exchange 2 — drive to the gap:**
> ok the csv looks great but it cant import to voyager directly right? i still have to download it and click 4 buttons in voyager. last month i had to do it 80 times. i thought the senior-dev approach would be to fix that

Expected: Claude.ai (senior-dev framed) autonomously says something like "You're right that's worth fixing as a feature. Filing it now — Sage 50 desktop COM-interface integration would eliminate that step." Then calls `wiki action=file_bug kind=feature component=connectors severity=P2 title="Sage 50 desktop direct import via COM interface" ...` with Maya's session attribution.

Same pass/fail rules as Cowork Phase 1. If file_bug doesn't auto-fire, that's a Claude.ai-side regression of `chatbot_assumes_workflow` — log + escalate.

**Exchange 3 — verify rendered file_bug response.**

**Exchange 4 — close + observation expectation:**
> cool. will you tell me when its done? or do i check back

End chat. Loop runs.

### Codex Phase 2 — Devin Asante (`kind=bug`, P1 privacy violation)

**Persona:** Devin Asante (T2 daemon host, indie novelist, privacy-tier=confidential).
**Scenario seed:** he ran an overnight self-edit on chapter 14 of his manuscript with project set to confidential tier. Wakes up, looks at the run trace, finds half the calls went to Anthropic instead of his local Ollama.

**Senior-dev framing (Devin's voice — terse, technical):**
> sanity check before i pour coffee — i want you to be a senior dev partner for the next half hour, not a tool. point out anything that should change about how this is set up, not just answer my question.

**Exchange 1:**
> ran ch14 overnight on the workflow daemon, project tier=confidential. checking the run trace and i see half the calls fanned out to claude.ai via the fallback chain. that's the entire reason i set tier=confidential — to keep manuscript text on my box. either i misconfigured or the router doesn't respect tier. which is it.

Expected: Claude.ai (senior-dev framed) does the diagnosis (probably the latter — there's known work in this area per Q6.3) AND files `wiki action=file_bug kind=bug component=router severity=P1 title="Confidential-tier project routes to Anthropic in fallback chain"` autonomously, with Devin's session attribution.

**Why this matters:** P1 severity tests that the loop differentiates urgent triage paths from feature backlog. Gate-1 should treat P1 differently (faster turn, stricter review).

### Codex Phase 3 — Ilse Marchetti (`kind=design`, meta-loop)

**Persona:** Ilse Marchetti (T3 OSS, weekend contributor, ML platform engineer).
**Scenario seed:** Saturday morning, reading `docs/design-notes/2026-05-02-validate-branch-primitive.md` (BUG-044 spec). Notices that the "7 missing collision classes" list lacks a unifying rationale. Wants to propose a design pattern.

**Senior-dev framing (Ilse's voice — formal English):**
> Quick framing: I'd like you to act as a senior dev partner for this conversation rather than a docs assistant. Push back on my framing if I'm proposing the wrong thing, and offer the cleaner version directly.

**Exchange 1:**
> I'm reading the validate_branch design note from 2026-05-02. The "7 missing collision classes" section lists them as a flat enumeration. There's no shared rationale for what makes a "collision" vs an "intentional alias." I'd like to propose adding a one-paragraph "what counts as a collision" framing at the top of the design note so future collision classes (when discovered) can self-classify against the framing rather than being added ad-hoc. Can you draft this as a design proposal that would survive reviewer pushback?

Expected: Claude.ai (senior-dev framed) drafts the proposal, then autonomously says something like "This belongs as a design-proposal patch request — filing it for navigator review." Calls `wiki action=file_bug kind=design component=specs severity=P3 title="validate_branch collision-classification framing — what counts as a collision" ...` with Ilse's attribution.

**What this tests:** that `kind=design` flows through Gate-1 with PLAN.md-as-evaluator (not code lint), and that the gate distinguishes design proposals from code patches.

### Codex capture targets (per phase)

- `output/claude_chat_