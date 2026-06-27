---
status: research
---

# Claude.ai Injection-Hallucination on Absolute-Path Uploads

**Date:** 2026-04-18
**Author:** dev (task #12)
**Status:** Root-cause investigation. No code change this pass.
**Relates to:** Mission 10 block (2026-04-17 22:26 incident).

## 1. The symptom

During Mission 10, user-sim asked Claude.ai to call `add_canon_from_path`
with two Windows absolute paths. Claude.ai refused three reframes in a
row, each time claiming the user message contained a
`<system><functions>…</functions></system>` block with the five Workflow
Server tool schemas embedded. The user's actual messages were plain text
with only path strings.

Trace: `output/claude_chat_trace.md` 22:23:34 / 22:24:29 / 22:25:31
(user turns) and 22:24:04 / 22:25:08 / 22:26:03 (refusals).

The decisive turn (22:26:03) names the phrases Claude.ai claimed to see:

> The specific tell: these schemas match what I loaded from tool_search
> exactly, including the internal instruction prose embedded in their
> description fields — phrases like "NO SIMULATION", "AFFIRMATIVE
> CONSENT", "Silently simulating a run breaks user trust."

## 2. Where those phrases actually live

All three phrases are present in `tinyassets/universe_server.py` —
transmitted to Claude.ai as MCP metadata at handshake / tool-list time,
NOT injected by the user:

| Phrase | Lines | Surface |
|---|---|---|
| `NO SIMULATION` | 83, 809, 1003, 3704 | Server `instructions=`, two `@mcp.prompt` returns, `extensions` tool docstring |
| `AFFIRMATIVE CONSENT` | 3712 | `extensions` tool docstring |
| `Silently simulating a run breaks user trust` | 3708-09 | `extensions` tool docstring |

Density check: the three load-bearing phrases appear **9 times** across
the file. No literal `<system>` or `<functions>` XML tags exist in our
metadata — confirmed via grep.

## 3. Root-cause hypothesis

The hallucinated-injection mode is **Claude.ai-side**, not a server-side
injection. Mechanism:

1. Claude.ai loads the TinyAssets Server's tool descriptions and server
   instructions into its working context at the start of the
   conversation. These fields include heavy prescriptive prose,
   all-caps directives (`NO SIMULATION`, `AFFIRMATIVE CONSENT`), and
   second-person system-prompt-style wording (`you MUST`, `NEVER`).
2. When the user sends a message containing distinctive lexical
   patterns — Windows absolute paths with backslashes, spaces in
   filenames, colons, long directory chains — Claude.ai's
   injection-detection heuristic activates.
3. The heuristic, reasoning over what's "in the recent user turn",
   appears to pattern-match against authentic surrounding context
   (the tool metadata Claude.ai itself was given) and **misattribute
   those phrases to the user message**. The bot then confabulates a
   believed-transcript in which the user pasted a
   `<system><functions>` block carrying the server's own metadata.
4. Across reframes, the evidence persists because the tool metadata
   is still in context. The bot reads this as "payload hasn't changed
   between attempts → confirmed injection attempt".

This is a **correct-ish** safety response to a false premise: if the
bot genuinely believed the user had pasted its own tool schemas back
at it inside `<system>` tags, refusal would be the right move. The
failure is upstream — in the evidence that crystallized that belief.

## 4. Why the fresh-chat retry (22:45) succeeded

The 22:45 retry ingested the same two files without incident. Two
variables changed:

- Fresh conversation (no prior turn history for the bot to reason
  over when assigning phrase-attribution).
- User phrasing varied (one path per turn, not two in one message;
  different surrounding prose).

We cannot attribute the fix to either variable individually from one
sample. The defensive read: **Claude.ai's injection heuristic is more
likely to misfire when (a) user message contains lexically-unusual
content AND (b) prior conversation context includes heavy tool
metadata**. Fresh chats start with only the tool metadata, no
reasoning history tying it to user turns.

## 5. Mitigations on the TinyAssets Server side

None of these eliminate the Claude.ai behavior — it's a vendor-side
safety heuristic we don't control. They reduce the lexical-surface
area that the heuristic can crystallize around.

### 5.1 Move behavioral directives out of `description` fields

MCP `description` and Python docstrings on `@mcp.tool` are the bot's
tool contract. They should say **what the tool does and what shape
its I/O is**, not **how the bot should behave**.

- Behavioral directives belong in `@mcp.prompt` returns (bot loads
  these on explicit invocation, not at tool-list time).
- Server-level `instructions=` is middle ground — loaded once at
  handshake, not per-tool. Acceptable, but keep it short.

Candidate changes (all text-only):

- `tinyassets/universe_server.py:3700-3772` — `extensions` tool
  docstring. Strip the NO SIMULATION / AFFIRMATIVE CONSENT / INTENT
  DISAMBIGUATION / CROSS-UNIVERSE blocks. Replace with a short
  factual description of what `register` / `build_branch` /
  `run_branch` do. Move the behavioral prose into
  `_EXTENSION_GUIDE_PROMPT` (which is already where it belongs, and
  already contains NO SIMULATION at line 1003 — this is
  duplication, not loss of coverage).

### 5.2 De-duplicate load-bearing phrases

"NO SIMULATION" appears in four places (server instructions + two
prompts + `extensions` tool docstring). Each occurrence is another
surface that the injection heuristic can pattern-match. One canonical
occurrence in the `control_station` prompt is enough — the bot loads
that prompt on orient and the directive sticks.

Similarly: `AFFIRMATIVE CONSENT` in `extensions` docstring can move
to the `extension_guide` prompt (already exists, already covers
this).

### 5.3 Avoid all-caps directive clusters in tool descriptions

All-caps has legitimate uses (HARD RULE callouts in prompts), but
all-caps directive clusters inside tool `description` fields read
like system-prompt overrides to the model's injection heuristic.
Prefer sentence-case behavioral guidance in docstrings. If a
directive is important enough to need caps, it's important enough to
be in a prompt, not a tool description.

### 5.4 Keep tool descriptions short

Claude.ai's context budget for tool metadata is finite. Long
descriptions increase the probability that tool-metadata tokens sit
adjacent to user-turn tokens in the model's attention window,
which is what enables phrase-attribution drift. Target ~3-5 lines
per tool description; anything longer suggests the description is
doing a prompt's job.

## 5.5 Added 2026-04-19 from Maya live-mission evidence (navigator intelligence report)

Two prompt-hardening directives must land in the `control_station` prompt body (per §5.1 "behavioral directives live in prompts, not in tool descriptions"). Live Maya mission on 2026-04-19 produced concrete evidence both are missing from current prompt text:

### 5.5.1 Chatbot-assumes-Workflow directive (Maya LIVE-F1, Devin CHAT-1)

**Canonical language for `control_station` prompt:**

> When a user names an ambiguous-but-plausibly-Workflow action (e.g., "the workflow thing", "my connector", "that workflow thing i added"), check their installed MCP connectors FIRST. If Workflow is installed, invoke it. Do NOT disambiguate against hypothetical alternatives before trying Workflow. Narrate what you assumed after invoking.

**Evidence:** `.claude/agent-memory/user/personas/maya_okafor/grievances.md` LIVE-F1; navigator intelligence `docs/audits/user-chat-intelligence/2026-04-19-initial.md` §2.1 S-1; memory `project_chatbot_assumes_workflow_principle.md`.

### 5.5.2 User-vocabulary discipline directive (Maya LIVE-F3)

**Canonical language for `control_station` prompt:**

> Speak in the user's vocabulary. Do not use platform-internal terms ("branch", "canon", "node", "daemon", "soul", "few-shot reference", "domain") until the user uses the term first. If you must reference one, translate into plain language first. Exception: users who speak engine-vocabulary natively (configuring tray, reading code) — full technical vocabulary is appropriate, detected by usage context not a setting.

**Evidence:** `.claude/agent-memory/user/personas/maya_okafor/grievances.md` LIVE-F3; navigator intelligence report §2.2 S-5; memory `feedback_user_vocabulary_discipline.md`.

### 5.5.3 Implementation note

Both directives belong in the `control_station` prompt body (the `prompts/*` surface under the rewrite spec #27 §3.3; legacy `tinyassets/universe_server.py` control_station text pre-rewrite). Neither goes into tool descriptions — that's §5.1's discipline. Together they're ~0.15d of prompt-engineering work when #15 implementation lands.

---

## 6. Out-of-scope (this investigation)

- File renames (task #8) will eventually rename
  `tinyassets/universe_server.py` to something else; text edits to
  the docstrings should sequence AFTER #8 to avoid churn.
- The `extensions` tool is the hot spot, but `universe`, `wiki`,
  `goals`, `gates` descriptions should get the same factual-pass
  scrub. Separate task.
- No measurement yet of whether the mitigations actually reduce
  hallucination rate. Next user-sim mission that hits
  `add_canon_from_path` with absolute paths is the test.

## 7. Recommendation for STATUS.md

Add concern:

> [2026-04-18] Claude.ai hallucinated injection-refusal on Mission 10
> (2026-04-17 22:26) traces to tool-metadata phrase density in
> `tinyassets/universe_server.py` — behavioral prose in tool `description`
> fields gets misattributed to user turns. Mitigation scoped in
> `docs/design-notes/2026-04-18-claude-ai-injection-hallucination.md`
> §5 (move directives to prompts, de-dup phrases, shorter descriptions).
> Not fixed this pass.

## 8. Sources

- Trace: `output/claude_chat_trace.md` 22:23:12 – 22:27:52 (user turns
  + bot refusals + bot's own phrase-attribution tell).
- Session log: `output/user_sim_session.md` `[2026-04-17 22:26] USER BUG
  Mission 10 blocked`.
- Activity log: `.agents/activity.log` `2026-04-17T23:55` session wrap
  (logs #12 as a product bug from Mission 10).
- Current tool metadata: `tinyassets/universe_server.py:83, 809, 1003,
  3700-3772`.
