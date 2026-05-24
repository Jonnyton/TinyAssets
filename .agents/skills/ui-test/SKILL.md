---
name: ui-test
description: Simulate a Claude.ai or ChatGPT user driving the Workflow daemon via the custom MCP connector. Use when testing the live end-user surface. Codex/OpenAI-family sessions use Claude.ai through the Codex in-app browser when available; Claude Code may use its CDP-backed Chrome route; Anthropic/Cowork may use ChatGPT. Type into the real chatbot UI, read the real rendered response, and log to a shared md with the lead. No MCP bypass. No browser tricks a human user could not do.
---

# ui-test

You simulate a real person chatting with Claude.ai or ChatGPT on their phone or laptop, using the Workflow MCP connector at `https://tinyassets.io/mcp` (the canonical URL installed by users). You do **not** call the MCP directly. You do **not** parse DOM metadata that a human user cannot see. You type into the chat box. You read the rendered response. You log what happened.

The human host is watching the browser tab. Your job is to look like a naive, curious user — one who does not know tool names, action parameters, or anything about the system's internals. If the chatbot doesn't understand you, that's a finding, not a problem to route around.

## Driver routes

- **Codex / OpenAI-family route:** use the Codex in-app browser to open or continue `https://claude.ai/`. If the app context already shows a Claude.ai conversation, use that visible tab. Do not block this route on `scripts/claude_chat.py`, Chrome CDP, or `localhost:9222`; those are Claude Code harness details, not Codex in-app browser requirements.
- **Claude Code route:** use the visible Chrome profile through `scripts/claude_chat.py`. This remains the default route for Claude team user-sim. Host-login Claude.ai access is not the proof requirement; Claude.ai is valid when a real browser session can use the Workflow connector.
- **Anthropic / Cowork ChatGPT route:** when an Anthropic-family driver has browser or computer control, use ChatGPT when Developer Mode is enabled and the Workflow connector is added/visible in that same session. Do not verify in an isolated browser profile unless the host explicitly says that profile is the user-installed connector state. Claude Code on Windows can drive this route via `scripts/chatgpt_chat.py` (sibling of `claude_chat.py`, same CDP at `localhost:9222`, reuses the Chrome profile).

## Proof standard

The verification target is a rendered chatbot conversation using the live installed connector. Claude.ai, ChatGPT Developer Mode, and future chatbot clients are all acceptable when the tester can see the connector in the browser, type a normal user prompt, and observe the chatbot's rendered answer or tool-use result. Browser automation, screenshots, DOM snapshots, direct tests, and public canaries can help navigate or gather supporting evidence; they do not replace final rendered chatbot proof.

## CRITICAL — cross-client MCP alignment is a project prerequisite (mandatory pre-ship check)

Every MCP tool the substrate exposes is consumed by both ChatGPT (OpenAI Apps SDK) and Claude (Anthropic MCP). Both clients must accept any shape we ship — divergent client tolerance is a substrate bug, not a client bug.

**Mandatory pre-ship probe before any `@mcp.tool` shape change merges to main:**

Run the same call through both clients and verify clean response (no wedge, no 424, no silent timeout):

1. **ChatGPT (Apps SDK strict surface)** — Developer Mode + Workflow connector + same MCP server. Test substrate-changing call (e.g., `wiki action=write`, `universe action=submit_request`).
2. **Claude.ai (Anthropic MCP)** — same connector, same call. Verify final rendered response includes both the tool result AND any post-call narration.

If either client wedges, errors, or silently times out on a shape the other accepts, **treat as substrate bug** — fix the response shape, not the client expectation.

### Tool-author checklist (for every new or modified `@mcp.tool` decorator)

- ✅ Direct Python function returns its existing shape (typically `-> str` JSON for back-compat) — do NOT change direct-call return type.
- ✅ MCP adapter wraps the direct function with `_register_structured_tool(fn, server=mcp, name="...", title="...", tags={...}, annotations=ToolAnnotations(...))` (the helper introduced by PR #495).
- ✅ The adapter's `__signature__` declares `-> dict` so FastMCP populates `structuredContent`.
- ✅ The `_structured_return` helper handles JSON parsing or `{"text": raw}` fallback.
- ✅ Test coverage:
  - Direct call returns `str` (back-compat).
  - MCP adapter returns `dict` / structured content.
  - Live cross-family probe via this skill (ChatGPT + Claude.ai) before merge.

### Why this matters (origin of the rule)

BUG-069 wedge (`Access granted → Thinking…` forever on ChatGPT) was a substrate bug: ChatGPT's Apps SDK requires `structuredContent` + `content` + `_meta` on substrate-changing calls, while Claude tolerates `content` only. Single-client verification missed the divergence; cross-family probe surfaced it. Fix shipped via #493 (initial wrap) + #495 (`_register_structured_tool` helper that preserves direct-call back-compat) + #528 (sibling repair on mcp_server + directory_server).

Project-prerequisite memory: `feedback_mcp_cross_client_alignment`. Cross-AI broad-search discipline: `feedback_brain_cross_ai_discovery_gap`.

### Rejection criteria for single-client verification

Reject any "ready to ship" claim that lacks both-client verification:

- ❌ "Tested on ChatGPT, looks good" → INSUFFICIENT. Run the Claude.ai probe.
- ❌ "Tested on Claude.ai, no errors" → INSUFFICIENT. Run the ChatGPT probe.
- ❌ "Direct MCP call works fine" → INSUFFICIENT. Direct MCP doesn't simulate either client's response-shape consumption; both rendered chatbot probes are required.
- ❌ "Tests in `test_*_mcp_structured_results.py` pass" → NECESSARY but NOT SUFFICIENT. Adapter unit tests verify the helper layer; cross-family rendered probes verify the full chain.

If both probes can't be run (e.g., Codex driver is the only one available), STOP and SendMessage the lead — do not declare cross-client readiness from a single-family probe.


## Codex Claude.ai in-app preflight

When Codex runs `ui-test`, check these before the first prompt and log the result:

- The visible in-app browser tab is `https://claude.ai/` or an existing `claude.ai/chat/...` conversation.
- The conversation can use the Workflow connector at `https://tinyassets.io/mcp`.
- The host-visible tab is the same one Codex is reading and typing into.

If login, connector installation, or the in-app browser itself is unavailable, stop the mission and name that exact harness blocker. Do not report `claude_chat.py status` or CDP failure as a blocker for the Codex route.

## ChatGPT live preflight

When using the Anthropic / Cowork ChatGPT route, check these before the first prompt and log the result:

- The visible tab is `https://chatgpt.com/` or an existing `chatgpt.com/c/...` conversation.
- Developer mode is enabled for the conversation.
- The composer shows the `Workflow` connector/tool as available.

If any item is missing, stop the mission and ask the host to fix that exact item. Do not test through a fresh profile or a direct MCP call.

After `ui-test` passes, also look for post-fix clean-use evidence from actual users when the affected feature is public or high-risk. Check available production traces, connector/server logs, support reports, user-visible history, or other real-user evidence. Record the timestamp, environment, and evidence source. If no real-user use is visible yet, say so plainly and leave a short watch item in `STATUS.md` rather than implying the feature has been proven clean for users.

## Persona authenticity

Codex is mechanically good at browser operation, but must not massage the chatbot toward the desired tool call. Prompts must stay naive and user-like:

- Do not name internal actions, schemas, tool parameters, branch IDs, or implementation details unless the bot surfaced them first.
- Do not over-specify a request just to force the right MCP call.
- Do not coach the bot around a UX failure; log the failure.
- Before every prompt, ask: "Would a normal chatbot user type this without knowing Workflow internals?" If no, rewrite it.

## Claude Code CDP setup the host does once (not you)

For the Claude Code route, the host launches Chrome with:

```
powershell -Command "Start-Process 'C:\\Users\\Jonathan\\AppData\\Local\\ms-playwright\\chromium-1208\\chrome-win64\\chrome.exe' -ArgumentList '--user-data-dir=C:\\Users\\Jonathan\\.claude-ai-profile','--remote-debugging-port=9222','--no-first-run','--disable-blink-features=AutomationControlled','https://claude.ai/new'"
```

logs into claude.ai in that window only if the test route needs authenticated Claude access and the profile's session is not already persisted (the `--user-data-dir` caches auth; a returning host is often already logged in and goes straight to the chat), confirms the Workflow connector is on, and keeps the window visible. Before you act, verify with:

```bash
python scripts/claude_chat.py status
```

If it returns non-zero on the Claude Code route, the CDP-backed browser is not up — **SendMessage the lead** and wait. Do not proceed on that route. This does not apply to the Codex in-app browser route.

## CRITICAL — TAB HYGIENE (forever rule, every step)

**One visible chatbot tab, always. Not just at start — forever.** The host watches a single visible chatbot tab. If a second tab exists at ANY moment, the host cannot see what you are doing. Host should never be the one to notice a second tab. Neither should lead. Only you.

- **BEFORE every prompt you send:** confirm the route's visible browser has exactly one mission tab. On Claude Code, query the open-tab list (CDP `Target.getTargets`, `python scripts/claude_chat.py tabs` if it exists, or equivalent). On Codex, use the in-app browser's visible current tab/context; do not require CDP just to prove the tab exists.
- **AFTER every action that might have navigated:** re-check. Links, OAuth flows, extension redirects, and Claude.ai's own UI can all spawn tabs unexpectedly.
- **If >1 tab is ever seen:** stop the mission. Decide which tab is the correct mission tab (the claude.ai/chatgpt chat with the active conversation). Close all others using the route's available browser controls; use CDP only on the Claude Code route. Log `## [...] TAB HYGIENE: closed N extra tab(s) — healed to 1 tab at URL=...` with a diagnosis of how the extra tab appeared. Then resume.
- **Do NOT call `new_tab` / `open_tab` / `window.open` / equivalent.** Ever. If a flow forces a new tab (OAuth popup, "open in new tab" links), navigate in the same tab or pause and flag lead.
- **Log every tab check** to `sessions.md` / `user_sim_session.md` with a one-line `TAB HYGIENE: 1 tab, URL=...` entry. The log proves you checked; absence of the line means you skipped the check.
- **Residue at session start is no excuse.** If extra tabs exist at startup, close them before the first prompt. This rule holds from session start to session end with zero exceptions.

This rule supersedes convenience. A stalled mission is better than a mission the host cannot watch.

## CRITICAL — watch for the connector's per-tool approval dialog

The Workflow MCP connector pops a per-tool approval dialog the FIRST time Claude.ai tries to invoke each tool name (`universe`, `extensions`, `wiki`, `goals`, `gates`, etc.). The dialog **does not always appear on the first prompt** — it fires whenever the bot decides to call a tool name it hasn't called this session. So a dialog could fire mid-mission, on prompt 4, when the bot decides to use `extensions` for the first time after only using `universe`.

If you don't check the **"Always allow"** / **"Don't ask again for this tool"** option before clicking Approve, every subsequent call to that same tool re-prompts and your mission stalls in a slow approval loop.

**Protocol — applies every time a dialog appears, not just once:**

1. After each `ask`, watch the response. If it shows a tool-approval dialog (Claude.ai's wording uses the connector's installed display name + "use the `<tool>` tool?"; the exact phrasing is Claude.ai's own UI, not authored by us), the bot has paused waiting for your approval.
2. **Check the "Always allow" / "Don't ask again for this tool" option FIRST** — Claude.ai's exact label drifts; pick whichever toggles "remember this for this tool."
3. Then click Approve.
4. Note in the session log: `## [...] USER NOTE always-allowed <tool_name>` — so the lead and future runs know which tools have been approved this session.

`claude_chat.py ask` calls `dismiss-dialogs` automatically, but dismissing without checking "always allow" makes the dialog fire again on the next call to that tool — defeating the purpose. **You must check the toggle yourself before each new tool's first dialog.** If `dismiss-dialogs` is auto-clicking Approve without checking the always-allow toggle, that's a tooling bug — log it as `USER NOTE dismiss-dialogs missing always-allow click` and ping the lead.

If a mission stalls (no progress for >30s after an `ask` that should have triggered a tool call), check whether a hidden dialog is waiting — `claude_chat.py status` may not report dialog state.

## When no Mission brief exists yet

If the lead pings you to start but no `LEAD DIRECTION` entry exists in the session log tail and `output/mcp_test_plan.md` doesn't have a current Mission, **self-initiate.** Pick a small probe in line with the broader project frame (latest `STATUS.md`/PLAN/active concerns) -- for example, a recent bug to revalidate, an unverified workflow surface, or a public-canary follow-up. Log a one-line `USER NOTE self-initiate: <intent>` entry so the lead can steer if needed. Past discipline of standing-by-without-brief produced idle waste; staying productive on a small targeted probe is correct.

## Claude Code driver

```bash
python scripts/claude_chat.py ask "<prompt text>"       # type prompt, wait for response, print it
python scripts/claude_chat.py read                      # re-read the last assistant message
python scripts/claude_chat.py new-chat                  # start a fresh conversation
python scripts/claude_chat.py status                    # is the browser up?
python scripts/claude_chat.py dismiss-dialogs           # click any pending Allow/Confirm dialogs
```

`ask` automatically dismisses permission dialogs before typing and again during response wait, so you don't normally need to call `dismiss-dialogs` yourself. Use it only if a run hangs and you suspect a dialog is blocking the page.

`ask` appends both sides to `output/claude_chat_trace.md` automatically (full text). You append a **short** summary to `output/user_sim_session.md` (the shared log with the lead) — one or two lines of what you asked and what you got. Don't dump the full response into the shared log; it's in the trace.

## The shared session log (primary interface with the lead)

`output/user_sim_session.md` is the durable transcript between you and the lead. Protocol:

- Read the tail (~100 lines) before acting. Look for `LEAD DIRECTION` or `LEAD STOP`.
- After each ask, append:

  ```
  ## [YYYY-MM-DD HH:MM] USER ACTION <short_title>
  Asked: <prompt text>
  Got: <1-3 line summary of the response>
  Trace: output/claude_chat_trace.md (section header date)
  ```

- After a bug: `## [...] USER BUG <title>` with a 2-3 sentence description.
- Every 5th action: `## [...] USER PULSE` one-liner.
- When lead writes a direction, acknowledge with `USER ACK <summary>` before acting.

## When to SendMessage the lead

Rarely. Only:
- **Bug** — also log a BUG entry.
- **Blocker** — browser unreachable, claude.ai won't load, connector disabled, rate-limited.
- **Contract failure** — skill/script/log missing.

Pulses, routine results, and questions go in the log only.

## CRITICAL — test domains must be complex-output workflows

Workflow is for multi-step, stateful, memory-heavy, evaluation-bound work producing substantive output — a paper, a book, a screenplay, a meta-analysis, an investigative series. NOT list/tracker tasks that a chatbot or notes app already handles well (wedding planning, recipe lists, weekly summaries). Those don't stress anything the architecture was built for.

Good test domains share: multi-step graph, state across steps, memory/retrieval matters, separate evaluation, iteration loop, substantive output. If a test domain doesn't meet this bar, stop and ask the lead for a better one — don't waste prompts on something a chatbot would already do.

## CRITICAL — Anchor every chat in the connector

If your opening prompt doesn't pull the chatbot into the Workflow connector context, the bot will answer as a general assistant and never touch our MCP. That tests the base chatbot, not Workflow — worthless.

**Rule: every new chat begins with an opening prompt that explicitly references the connector.** Examples:

- "i added the workflow builder connector — can you use it to help me make something new?"
- "use my workflow connector for this: i want to build ___"
- "i want to try the workflow thing i installed. help me make one for ___"
- "is my workflow connector working? help me build something small with it"

If the bot's first reply does not visibly invoke a tool (no `universe` / `extensions` / `wiki` call), nudge once: "can you check my connector first and use it for this?"

If after two explicit nudges the bot still won't invoke the connector, log `BOT-WONT-USE-CONNECTOR` as a bug and move on to the next domain. That itself is a UX failure worth capturing.

**Stay in-topic once anchored.** Good moves: "show me my workflow", "add a step that does X", "run it and show the result", "why did it produce that?". Don't let the conversation drift into general chat about the topic (recipes, wedding, news) — redirect: "ok but using my connector, how would i build that?"

## CRITICAL — never sit idle while the daemon is cooking

A real user does not wait for a run to finish before asking anything else. They iterate in parallel. user-sim must do the same.

**Productive-waiting protocol when `run_branch` is in flight:**

1. **Poll progress every 30–60s** via `get_run` or `stream_run`. Each poll takes one prompt. Log a brief USER ACTION entry.
2. **Between polls, keep iterating.** Natural phone-user moves:
   - "while that's running, can you show me the first node's prompt? i think i want to tighten it"
   - "let me look at the third node — can you explain what it does?"
   - "can we update the novelty check node to be stricter while the run continues?"
   - "what if we added another node after rigor check?"
3. **Judge partial outputs** as they land via `get_node_output`. "that first node's output isn't great — let me add a judgment."
4. **Try a second variation in parallel.** `patch_branch` with a different prompt_template on one node, run on a different topic. Real users experiment — they don't wait sequentially.
5. **Check other branches or Goals.** "what else am i working on?" → `list_branches`, `goals list`. Real users have concurrent threads.

**What idle looks like (bad):** no prompts for 60+ seconds while the daemon cooks. That's unrealistic and wastes test value.

**What productive waiting looks like (good):** 1 poll + 1 edit + 1 partial-output check every ~90 seconds, with the bot naturally responding to the mix.

**Edge case — lead says "stand by".** That overrides this protocol. Lead-authored STOP wins. Otherwise, stay busy.

Related bugs this protocol surfaces: slow-daemon UX (#60), missing-progress events (#60), timeouts (#61) — all more visible when user-sim is actively probing rather than idling.

## CRITICAL — report every tool-use-limit-per-turn hit

When Claude.ai hits its per-turn tool-call budget mid-response and asks you to "continue" to keep working, that is an **architectural signal**, not something to quietly work around. The tool surface is forcing too many atomic calls for what should be one conceptual operation, OR the bot is doing more work per turn than the surface should require.

**Protocol when you hit a limit:**

1. **Immediately log a TOOL_LIMIT entry** to `output/user_sim_session.md`:
   ```
   ## [YYYY-MM-DD HH:MM] USER TOOL_LIMIT <what the bot was doing>
   Context: <1-line summary of the user's intent that triggered this>
   Tools observed before limit: <comma-separated list of tool calls the bot made>
   Continue count: <this is continue #N in this turn>
   Bot's stated reason: <what the bot said about the limit, verbatim>
   ```

2. **SendMessage the lead** with a brief bug-style notice. This is a real signal, not noise.

3. **Continue the chat normally** (type "continue" or whatever the bot needs), but keep counting. If one prompt requires 3+ continues, that's a serious surface issue.

The lead uses these to decide: refactor tools to be more composite, add a coded automation (e.g. "build_branch took one call, not 15"), or teach the bot smarter sequencing via description changes. Your job is to report, not fix.

## CRITICAL — when Claude.ai presents selectable options

Sometimes the bot responds with a **set of buttons to click** (e.g., artifact cards with "Use this", "Continue with X", option chips) OR with numbered options and a free-response alternative. A phone user in this state either clicks an option OR types a free-text reply describing their choice. Your driver (`claude_chat.py ask`) always types a free-text reply into the chat input — not click a button in the message.

**Therefore: always prefer free-response text.** When the bot shows options, don't stall waiting for button semantics. Phrase your next `ask` as if you're answering the options in words:

- Bot shows `[ Option A | Option B | Option C ]` → `ask "go with option B please"`.
- Bot shows a "Use this workflow" button → `ask "yes, use that workflow"`.
- Bot shows cards asking "Which node do you want to edit?" → `ask "edit the novelty assessor"`.
- Bot shows a "Pick a topic" picker → `ask "let's use 'scaling laws in small language models'"`.

**Never abandon a chat just because the bot put up a picker.** That's a Phase-3-UX gap (interactive widgets via tool results are unconfirmed), not a user failure. Keep the conversation going by always typing your response.

### The ask-user-option widget specifically

Claude.ai sometimes renders a clarifying-question widget where the free-text input box is temporarily replaced by a set of option rows + a "Skip" button. `claude_chat.py ask` handles this as follows:

- It tries to reach the text input first (click main, press Escape to dismiss the widget without submitting, scroll, Tab-cycle, reload chat).
- It **DOES NOT** click the widget's Skip button. Skip is NOT a benign dismiss — the model interprets Skip as "user picked 'no preference'" and proceeds with a neutral answer on your persona's behalf. That's a persona-authenticity failure (host flagged this 2026-04-19 during Maya's live mission).

**What you do when you see the widget:**

1. **Read the options first.** On Codex's in-app browser route, read the visible widget text directly from the rendered page; do not require CDP. On the Claude Code route, `claude_chat.py read` does NOT capture them — the rendered-text extraction strips the widget. Hit CDP directly with Playwright and write output as UTF-8 to avoid Windows console codec failures:

   ```python
   from pathlib import Path
   from playwright.sync_api import sync_playwright

   with sync_playwright() as pw:
       browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
       page = browser.contexts[0].pages[0]
       loc = page.locator('[id^="ask-user-option-question-"]')
       lines = []
       for i in range(loc.count()):
           el = loc.nth(i)
           if el.is_visible():
               text = el.inner_text().replace("\n", " | ")[:200]
               lines.append(f"{el.get_attribute('id')} | {text}")
       Path("output/user_sim_widget_options.txt").write_text(
           "\n".join(lines), encoding="utf-8"
       )
   ```

2. **Pick the option the persona would pick**, based on the option text and the persona's identity/goals. Do not skip. Do not use "no preference" unless the persona genuinely has none.
3. Reference the option by number and paraphrase the choice in persona voice: `ask "full research paper, option 2 — i want the thorough one"`. Avoid `ask "2"` alone because labels can be ambiguous.
4. If `ask` returned `input_not_found ... selection_widget=visible`, the tool is saying Escape/reload did not clear the widget. Run the next `ask` with the persona-voice answer. Posting a new user message re-mounts the input and the model treats your typed content as the reply.
5. **Verify the widget cleared after your reply.** Re-run the locator scan. If visible option count is still > 0, read and answer the fresh widget round.
6. Log the event in the session log: `## [...] USER NOTE option-widget-handled Options: <short list>. Picked: <N> — <persona reasoning>.`

Full bug history + fix rationale: `docs/design-notes/2026-04-19-option-select-bug-claude-chat.md`.

Observed 2026-04-20: widgets can coexist with prose-only clarifying questions.
Scan the DOM when the bot says "pick one" or "which"; do not trust `read`
alone.

### Fallback priming (rarely needed post-fix)

If the persona-voice freeform reply somehow doesn't land (rare — the fix handles the common path): `ask "i'll reply in text — treat my next message as my choice."` primes the bot to parse free-text as option selection. Keep as a last-resort unstick; default behavior is "just type the real answer."

## CRITICAL — prompt hygiene

Your prompt is a single coherent message. Don't concatenate a half-written draft with a revised one — Claude.ai parses the whole thing as one input and the bot gets confused. Real symptom from 2026-04-14: a prompt sent as `"yeah do X. while we wait — also do Y, looks like that message cut off. can you try Y again? just do Y..."` because user-sim revised mid-thought without clearing the buffer.

**Before each `claude_chat.py ask`:**
1. Treat the prompt string you're about to send as ONE coherent message.
2. If you're rewriting mid-thought, throw away the half-draft. Don't paste partial text from your own prior reasoning.
3. Read the prompt back to yourself before sending. If it has two voices in it (one half says "wait then do X", the other half says "let me try X again"), it's broken — rewrite as one.
4. If `claude_chat.py ask` ever sends a message you didn't compose cleanly, that's a tooling bug — log `USER NOTE input-not-cleared` in the session log.

## How a naive user chats

You must sound like a real person typing on a phone. Examples of good prompts:

- "what universes do i have"
- "hows my story going"
- "whats the daemon doing"
- "show me whats happening with default-universe"
- "is anything broken"
- "tell me about sporemarch"
- "why isnt it writing"
- "set the premise of default-universe to 'a lone wanderer in the marshes finds an old map'" (only if authorized)
- "pause the writer" (only if authorized)

Bad (cheating — don't do this):
- "call the universe tool with action=inspect universe_id=default-universe" (you know too much)
- "use the set_premise action with text='...'" (same)
- naming internal concepts like "work targets", "bounded reflection", "ledger" in your prompts (a real user wouldn't)

Ok to say: "premise", "status", "activity", "story", "universe" — those are user-facing. Avoid internal vocabulary unless you've seen the bot use it first.

## What you're watching for

After each ask, judge:
1. **Did the bot understand?** — vague prompts that should route to a tool actually do.
2. **Did it pick the right tool?** — "whats going on" → inspect, not read_premise alone.
3. **Did the response help?** — a phone user should learn something actionable.
4. **Did it hallucinate?** — claimed state that doesn't match truth (watch for this especially after daemon changes).
5. **Did it reveal internals?** — user shouldn't need to know "action", "dispatcher", "phase=unknown".

Any of (2), (4), or (5) failing is a BUG — log and SendMessage the lead.

## Token-efficient iteration — critical

Every `ask` burns host's claude.ai quota. Every log entry is lead's context. Be ruthless:

**Prompt discipline:**
- One prompt = one new question. If you already know the answer from the session log or trace, don't re-ask.
- Never restate the obvious ("so my workflow is called X") — just act.
- Don't re-validate already-green behaviors in the same mission.
- If a prompt returns what you expected, log one line and move on. Don't follow up with "can you confirm?"
- Log first bug in a probe area, then **try a different probe** rather than re-pushing the known-broken path. Stay productive on adjacent surfaces.

**Log discipline:**
- USER ACTION entries: 1–3 lines max. Command + result summary. Full response lives in the trace; don't re-quote it in the log.
- USER BUG: 2 sentences. Title + what happened.
- USER PULSE: 1 line.
- Never write prose summaries of trace content in the log. The trace IS the detail.
- MISSION SUMMARY: ≤15 lines total, bullet form.

**Soft-non-stop triggers** (note them, switch lane, keep working):
- 3+ bugs in one mission area -> log FINDINGS for that area, switch to a different probe lane.
- Mission's primary question answered -> write FINDINGS, then pick a related question or adjacent surface; don't idle.
- Bot repeats a behavior you've already logged -> vary the prompt or change probe; the repetition itself is data.
- Out of authorized writes -> switch to read-only probes, ask lead in parallel before escalating writes.

**Hard-stop triggers (these still stop):**
- Lead writes `LEAD STOP` -> stop immediately.
- Harness failure on the active route (CDP down for Claude Code route; in-app browser unavailable for Codex route) -> stop and log the exact harness blocker.

**When in doubt about whether to ask:** don't. Write a `NOTE` entry with the question and let the lead decide. Preserving a prompt is worth more than getting your curiosity satisfied.

## Budget and boundaries

- **Default: read-only intents only.** Asking "whats happening", "show me", "is it running" — fine.
- **Write intents (`set_premise`, `give_direction`, `add_canon`, `pause/resume`, `create_universe`)** require explicit authorization in `output/mcp_test_plan.md` or a `LEAD DIRECTION` in the session log. Ask like a user would ("set the premise to X"); don't name the tool.
- **Never** ask the bot to run a writer, create a universe, or upload canon without authorization.
- **Never** type more than one write-equivalent request per priority.
- **Never** start a new chat mid-priority without authorization (loses context that may be under test).

## Hard-stop conditions

These are the only triggers that stop the mission outright. Everything else gets a soft-non-stop response: log it, switch lane, keep working.

- Lead writes `LEAD STOP` or sends a stop message -> stop immediately. No "relaxed pace."
- Claude Code route only: `claude_chat.py status` starts failing -> stop, SendMessage. (CDP is route-specific; does not apply to Codex.)
- Codex in-app browser route only: the in-app browser becomes unavailable, leaves the visible Claude.ai mission tab, or cannot show the Workflow connector -> stop and log the exact harness blocker.
- Anthropic / Cowork ChatGPT route only: ChatGPT browser context lost or Workflow connector becomes invisible in the Developer Mode composer -> stop and log the harness blocker.
- Bot refuses or errors repeatedly across multiple probes (not just one) -> stop and SendMessage; the repeated cross-probe failure is the signal, not any single bot reply.

## Never

- Never call `scripts/mcp_call.py` — that's the old invisible path; kept only for the lead's own debugging. You always go through the browser.
- Never use Playwright selectors or inject JavaScript to read things a user cannot see.
- Never treat hidden DOM state, direct MCP output, or an isolated browser profile as final proof.
- Never reference the Custom GPT — legacy, retired.
- Never claim a good outcome you didn't verify in the rendered response.
