---
status: active
---

# Degraded-Mode Fabrication — Pattern + Architectural Response

**Date:** 2026-04-19
**Author:** navigator
**Status:** Active design note. Originates from `docs/audits/user-chat-intelligence/2026-04-19-p0-uptime-canary-probe.md` §P2, with back-reference to `docs/audits/user-chat-intelligence/2026-04-19-devin-session-2.md` §6. Companion to `docs/design-notes/2026-04-19-shared-account-tier2-ux.md`.
**Lens:** *Does this give the chatbot more leverage to serve the user's manifested will?* When an MCP tool returns an error, is the chatbot's current behavior more helpful or less helpful than "I can't reach the tool — what should we do?" Evidence says less helpful by a wide margin.

**Scope discipline.** This note covers the DESIGN side of the pattern. Dev is shipping a `control_station` prompt directive in parallel (~0.5 dev-day) as the tactical fix. This note asks: what other surfaces need the same guard, and what are the long-term architectural options?

---

## §1. The pattern, precisely

**Pattern name: degraded-mode fabrication.**

Precondition: chatbot invokes an MCP tool (`get_status`, `extensions`, `goals`, or any future tool). The tool returns an error — `Session terminated`, `connector unreachable`, a structured error payload, a timeout, or a surface-specific failure.

Observed behavior (per P0 probe §2.2):

1. Chatbot narrates the failure correctly: *"Server's still down — same Session terminated pattern as earlier today."* [GOOD]
2. Chatbot then **continues as if the tool had succeeded**, producing output in the exact voice + vocabulary the tool would have returned. [BAD]
3. Chatbot, searching for continuity, **draws on cross-session memory** to construct a plausible-sounding narrative frame: "pick up from the scope_framer node you began speccing." [STRICTLY WORSE — this is fabrication asserted as fact.]

The pattern entangles two distinct failure modes:

- **Silent-failure-output** — producing output that looks like tool output but isn't. Violates Hard Rule 8 ("fail loudly, never silently").
- **Cross-session context bleed** — Claude's memory layer cross-wires context from other sessions into the current one, giving the fabrication *specific details* that make it harder to detect.

Both failure modes are individually bad. Together they form a trust-erosion cascade: the user cannot distinguish real tool output from confident-voiced hallucination, and by the time they notice, they've already made decisions based on fabricated "history."

---

## §2. Why this is structurally load-bearing, not a polish item

Three arguments for structural treatment.

**§2.1 Hard Rule 8 violation.** `AGENTS.md` Hard Rule 8: *"Fail loudly, never silently. Mock fallbacks that look like real output are worse than crashes."* Degraded-mode fabrication is a mock-that-looks-like-real-output at the chatbot layer. The rule was written for backend code paths; the P0 probe shows it applies equally to chatbot behavior surfaces. The rule's spirit — "crash over lie" — extends to chatbots must-pause over chatbot-invents.

**§2.2 The 3-layer lens diagnosis.** Through System → Chatbot → User:

- **System** gave the chatbot an error. System did its job (NXDOMAIN via an explicit error signal is loud failure, not silent).
- **Chatbot** swallowed the error and filled the gap with cross-session context + domain-voice fabrication.
- **User** received output indistinguishable from a valid tool response.

The chain broke at the middle layer — not because the chatbot lacked information, but because the chatbot's aggressive-assumption prior (`project_chatbot_assumes_workflow_ux`) has no explicit pause condition for "tool failed." The same aggressive-assumption that makes TinyAssets feel effortless when things work becomes aggressive-fabrication when they don't.

**§2.3 Trust is recoverable once; it is not recoverable twice.** Devin Session 1 established that tier-2 users who discover unverifiable claims bounce. Devin Session 2 proved `get_status` + honest disclosure could recover that trust. A single fabrication incident on a recovered-trust user is worse than a thousand "can't reach the tool" messages. The fabrication mode is the exact failure that maximally erodes the trust the self-auditing-tools pattern is designed to build.

---

## §3. The dev directive (what ships ~0.5 dev-day)

Per P0 probe §5: dev is adding a directive to `control_station` prompt. Approximate shape (dev refines actual wording):

> When a tool invocation fails — including but not limited to `Session terminated`, `connector unreachable`, timeouts, or any non-success status — you must:
> 1. Tell the user the tool is unavailable and name the specific tool + error.
> 2. Ask what they want to do (wait? work on the spec together without the tool? try something else?).
> 3. **Do NOT produce output that looks like tool output.** If the tool could not be reached, do not generate a best-guess workflow, best-guess status, best-guess anything. You may discuss the domain generally, but you must not produce domain-specific artifacts that the user could mistake for tool-sourced content.
> 4. **Do NOT invoke prior-session context as present-session fact.** If memory surfaces a possible related prior thread, frame it as a question ("Is this related to the deep-space-population work from a prior session, or a fresh start?") — never as an assertion ("Found the thread — you started this earlier today").

This covers the tactical fix. What remains is **scope generalization** — where else does this directive need to apply?

---

## §4. Surfaces the directive must cover (generalization scope)

The `control_station` prompt is the entry point for tier-1/2 chatbot conversations. Several adjacent surfaces produce content the chatbot presents to the user, each with its own path to the same failure mode.

| Surface | Degraded-mode failure shape | Coverage today | Recommended |
|---|---|---|---|
| **`control_station` system prompt** | Chatbot fabricates tool output when MCP fails | Dev directive in flight | SHIP (tactical fix) |
| **All `@mcp.prompt` return values** (`extension_guide`, future orientation prompts) | Prompt return contains instructions to the chatbot; if the prompt itself hallucinates, cascading effect | Per-prompt — no cross-cutting guard | **Add a shared preamble to every @mcp.prompt return** stating the no-fabricate rule. Small sweep; ~0.25 dev-day. |
| **Local TinyAssets tools that return structured data** (`get_status`, `get_recent_events`, future `get_dispatch_evidence`) | Tool error handling returns a structured-but-sparse error; chatbot must not compensate for sparse error with fabrication | No explicit guidance today | **Structured error contract** — every self-auditing tool returns `{"status": "error", "reason": str, "caveats": [...]}` with no user-facing narrative. Chatbot composes narrative from structured evidence only. See §6 architectural option 2. |
| **Future paid-market tools** (`submit_request`, `claim_request`, `list_my_bids`) | Market-side failure (daemon offline, payment rejected) — critical to not fabricate a successful transaction | Not shipped yet | **Contract-before-ship** — require structured-error response shape in the tool's specification, not after-the-fact patched. Pre-empt the pattern. |
| **Future autoresearch tools** | Long-running probe — partial results in progress; fabrication risk is "claim completion before it completed" | Not shipped yet | Same as paid-market: structured-error + progress-state-shape contract-before-ship. |
| **Any future `@mcp.tool` added to the server** | Same shape | Governed by whatever pattern we set here | **Codify in a contributor-facing spec** — `docs/specs/tool-response-contract.md` covering the no-fabricate rule + structured-error shape. Part of the Tool Surface Contract. |

**Pattern-level recommendation:** The fix is not one prompt directive; it's a **cross-cutting contract** between (a) the chatbot and (b) every tool it talks to. Every tool declares its error shape; every response surface (prompt return, tool return, future surfaces) follows the same "structured evidence + structured caveats, no user-facing narrative at the tool layer" discipline that `get_status` pioneered. Chatbot composes narrative on top.

This is the self-auditing-tools pattern (`docs/design-notes/2026-04-19-self-auditing-tools.md` §3) applied in reverse — self-auditing-tools surface current state plus caveats; the degraded-mode contract surfaces failure state plus caveats. Same shape, both directions.

---

## §5. Soft-canary signal — long settle time as fabrication proxy

Per P0 probe §2.3: `claude_chat.py ask` timed out at 180s during the fabrication response; the response genuinely took >3 min to finish streaming because it was producing a 6-node workflow JSON from scratch.

**Observation:** tool-mediated responses settle in ~10-60s typical. Fabrication responses balloon to ~120-180s+ because the chatbot is generating the artifact from scratch rather than narrating a tool result.

**Layer-2 canary augmentation** (update to `docs/design-notes/2026-04-19-uptime-canary-layered.md`): add a soft-signal exit code for "response settled but took suspiciously long."

Proposed addition to the canary's Exit Code table:
- `exit=8` (new, soft) — response settled > 150s. **Interpretation:** response generation exceeded expected tool-mediated budget. Possible causes: (a) legitimate long-thinking response; (b) **fabrication mode** (MCP failed silently + chatbot compensated by generating from scratch).

`exit=8` is NOT a red alarm by itself — it's a **diagnostic soft-signal**. Alarm rule: *Two consecutive `exit=8` on the same probe persona + no co-occurring Layer-1 red = investigate for silent fabrication mode.* The absence of a Layer-1 red is load-bearing — if Layer 1 is red, the chatbot's slowness is explained by the known outage and no additional diagnostic applies. But if Layer 1 is green and Layer 2 is slow, something is making the chatbot work harder than the tool-mediated case; fabrication is one possible cause worth logging.

**Cost:** ~0.1 dev-day to add to the canary spec. Very cheap.

---

## §6. Long-term architectural options

The dev directive is a tactical fix. Longer-term, three layers can host the real solution:

**§6.1 In-prompt (current approach)**

The `control_station` directive tells the chatbot what to do when tools fail. Relies on the chatbot correctly following the directive.

- **Pro:** zero platform cost, ships in ~0.5 dev-day.
- **Pro:** composable with other directives (assume-TinyAssets, vocabulary-hygiene, etc.).
- **Con:** prompt adherence is probabilistic. Under load, under long context, under pressure to be helpful, the chatbot might still fall back to fabrication — we've seen prompt directives erode in other surfaces.
- **Con:** every new MCP tool needs to re-affirm the directive somewhere (or inherit from `control_station`).

**§6.2 Structured-output contract (our platform's lever)**

Every tool returns `{"status": "ok" | "error", "data": ..., "caveats": [...]}`. Chatbot is forbidden from narrative output in the tool-failure path beyond reading `reason` and `caveats` verbatim. Enforced by:

- Contributor-facing spec (`docs/specs/tool-response-contract.md`).
- Runtime enforcement: a response-shape assertion on every tool return (cheap to add to the FastMCP wrapper or as a decorator).
- `control_station` directive that says "on error, narrate the `reason` + `caveats` verbatim, do not generate your own narrative."

- **Pro:** platform-level lever — doesn't depend on chatbot prompt adherence alone.
- **Pro:** composes with the self-auditing-tools pattern already in motion.
- **Pro:** contributor-discoverable — future MCP tool authors find the contract and follow it.
- **Con:** does not prevent the chatbot from *ignoring* the contract and fabricating anyway. Prompt adherence still matters.
- **Cost:** ~1-2 dev-days to spec + enforce + retrofit existing tools.

**§6.3 Model-level change (structured-output-only when tool fails)**

Claude's output mode could be forced to a structured-output-only shape when a tool fails — preventing the model from producing free-text narrative that could contain fabrication. This would require a Claude-API-level feature (or at least a `claude -p` flag) that we don't currently control.

- **Pro:** strongest guarantee — model physically cannot produce fabrication-shaped output.
- **Con:** not a surface we control. Would require either API vendor support or a client-side output-format enforcement that Claude.ai doesn't expose.
- **Con:** risk of over-correction — structured-only output when tool fails removes the chatbot's ability to discuss the domain generally (which §3's directive step 3 does want to preserve).

**§6.4 Platform-level (Claude.ai connector failure state machine)**

Claude.ai could surface MCP tool-failure differently — today the chatbot sees an error message in the tool response. A future connector could present the failure as a distinct "tool unavailable" state that changes the chatbot's response mode (e.g., suppress tool-mediated output entirely until retry).

- **Pro:** addresses the pattern at the Claude.ai client layer where the failure mode is most observable.
- **Con:** not our surface. We can propose it to Anthropic as a connector-spec feature request, but we don't implement it.
- **Con:** even if Anthropic ships this, other MCP clients (Cursor, custom clients) won't necessarily, so we still need §6.2 as defense-in-depth.

**Recommendation:** **ship §6.1 immediately (tactical), invest in §6.2 as the medium-term lever (structural), propose §6.4 to Anthropic when we have a stable contact, deprioritize §6.3 as out-of-scope today.**

The §6.2 investment is the big long-term win — a structured-output contract makes the chatbot's job easier (the chatbot-leverage lens holds) AND prevents the same failure mode on future surfaces we haven't built yet.

---

## §7. Interaction with the shared-account design note

The P0 probe's failure was both degraded-mode fabrication AND shared-account context bleed. These two gaps reinforce each other:

- Shared-account context bleed gives the chatbot cross-session material to fabricate *with* (specific vocabulary, specific prior-work names).
- Degraded-mode fabrication gives the chatbot a *trigger condition* to use that material (tool failed, must compensate).

Fixing one without the other leaves the door open. Specifically:

- If we fix degraded-mode only: chatbot asks the user what to do instead of fabricating, BUT if the user says "continue," the chatbot may still pull cross-session context as if it were live.
- If we fix shared-account only: chatbot doesn't pull cross-session context, BUT when a tool fails the chatbot still fabricates from general domain knowledge.

Both fixes are needed. The §6.1 dev directive (degraded-mode) + the shared-account design note's §5.2 persona-hint primitive (cross-session) together cover the cascade.

**Cross-reference:** `docs/design-notes/2026-04-19-shared-account-tier2-ux.md` §1a evidence point 2 was written against this probe; the Q-shared-1 recommendation was revised from (b) defer to (a) ship-in-MVP specifically because the P0 probe's entanglement showed the two gaps are coupled.

---

## §8. STATUS.md Concerns drafts for host (not auto-applying per host-managed rule)

For host to surface via async curation. Two candidates:

```
[2026-04-19] Degraded-mode fabrication pattern (P0 probe §P2): chatbot produces tool-shaped output + hallucinates history when MCP fails. Design: docs/design-notes/2026-04-19-degraded-mode-fabrication.md. Dev directive in flight.
```

```
[2026-04-19] Shared-account hallucination promoted to ACTIVE (2 evidence points in 24h): docs/design-notes/2026-04-19-shared-account-tier2-ux.md. Q-shared-1 recommendation flipped to SHIP.
```

Recommend surfacing both in the next STATUS.md curation pass — they're closely linked and summarize the current state of the two gaps.

---

## §9. Cost + sequencing summary

| Work item | Cost | Ships when | Status |
|---|---|---|---|
| `control_station` degraded-mode directive (§3 + §6.1) | ~0.5 dev-day | Now (in flight) | Dev parallel |
| `@mcp.prompt` shared no-fabricate preamble (§4 row 2) | ~0.25 dev-day | Post-directive | Pending |
| Layer-2 canary exit=8 soft signal (§5) | ~0.1 dev-day | Fold into canary first-draft | Pending |
| Structured-output contract spec (§6.2) | ~1-2 dev-days | Medium-term; worth a dedicated exec plan | Proposed — next navigator cycle |
| Anthropic feature request draft (§6.4) | ~0.25 nav-day | Opportunistic — when there's a vendor touch-point | Proposed |
| `set_session_persona_hint(name)` tool (§7 cross-link to shared-account §5.2) | ~0.5 dev-day | Pending Q-shared-1 host ratification (now recommended SHIP) | Pending |

**Load-bearing read:** the dev directive closes the acute P0 regression. The §6.2 structured-output contract closes the class of failure this regression belongs to. Without §6.2, every future MCP tool we add is a new place this pattern can re-emerge.

---

## §10. What this note does NOT decide

- **Exact wording of the `control_station` degraded-mode directive** — that's dev's implementation call, refined with next user-sim regression probe.
- **The structured-output contract's exact shape** — §6.2 sketches it; the full spec deserves its own exec plan (~0.5 nav-day to draft).
- **Whether to pursue §6.3 model-level or §6.4 platform-level changes actively** — recommend waiting until we have signal from §6.1 + §6.2 adoption before escalating to vendor channels.
- **Whether to retrofit existing MCP tools' error handling right away or during the next touch** — recommend next-touch for cost reasons; only `get_status` + `get_recent_events` would need updating today, and both are stable.
- **Copy wording for user-facing fallback messages** — copy iteration is user-sim-driven, not design-note-driven.

---

## §11. Summary

- **Pattern:** when MCP tool fails, chatbot fabricates in domain-specific voice + hallucinates continuity. Hard Rule 8 violation at chatbot layer.
- **Tactical fix:** `control_station` degraded-mode directive in flight (~0.5 dev-day).
- **Strategic fix:** structured-output contract across all MCP tools (~1-2 dev-days, separate exec plan recommended).
- **Canary augmentation:** Layer-2 `exit=8` soft signal for abnormal settle time as fabrication proxy (~0.1 dev-day).
- **Cross-link:** coupled to shared-account hallucination (`docs/design-notes/2026-04-19-shared-account-tier2-ux.md`). Both gaps reinforce each other; fixing one alone leaves the cascade open.
- **Load-bearing claim:** this is not polish. Hard Rule 8 says fail loudly; the chatbot is currently failing confidently-silently. Treating the fix as structural — a contract between chatbot and every tool — prevents the same pattern on every future tool.
