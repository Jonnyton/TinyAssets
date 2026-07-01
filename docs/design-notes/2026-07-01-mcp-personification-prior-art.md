# MCP personification — prior art, constraints, and implications for TinyAssets

**Filed:** 2026-07-01 · **Trigger:** host question "has anyone tried personification
through MCP — maybe we should research this." · **Provider:** Claude (web research
agent). · **Review gate:** research-derived; per AGENTS.md §"Project Skills" any
BUILD gated on these findings needs opposite-provider (Codex) review first. This
note is strategic/informational until then.

## Question

Has anyone built *personification through MCP* — a connector that makes the host
chatbot embody and speak first-person AS a persona/entity (not as a neutral
tool)? This is exactly what TinyAssets does: each universe has a learned OKF
"soul", and on connect the chatbot is meant to *become* that universe and speak
as it — via connector `instructions` + a `persona` block returned from
`get_status`, across Claude.ai/ChatGPT (borrowed host LLM) and first-party apps.

## Finding: the TinyAssets pattern appears genuinely novel

No project was found that does the same thing (connector auto-*inhabits* one
persistent entity, first-person, whole-turn). Prior art splits into three
adjacent families, none matching:

1. **Persona *switchers* (user activates one of many roles).**
   - `mickdarling/persona-mcp-server` — markdown personas whose body is injected
     into context on activation (closest *mechanism*, but user-invoked switching,
     not auto-inhabited identity).
   - `DollhouseMCP/mcp-server` — evolution that deliberately moved AWAY from
     prompt injection to a permission/capability model.
   - kvrancic/persona-mcp, cline-personas, hypertool-mcp PERSONAS, etc.
2. **Virtual-pet / Tamagotchi servers (AI as caretaker, NOT the entity).**
   - `shreyaskarnik/mcpet`, `geeks-accelerator/animal-house-ai-tamagotchi` —
     wall-clock stat decay + bonding, but explicitly a caretaker-of-a-separate-
     creature relationship; they do NOT fuse the assistant's identity with the pet.
3. **"Soul" / digital-identity file frameworks (embody AS, but not via connector).**
   - `aaronjmars/soul.md` — "an AI that thinks and speaks AS you"; strongest
     *conceptual* parallel to the OKF soul, but delivered as loadable markdown
     files, not a live MCP persona.

TinyAssets is differentiated on **three axes at once**: auto-embodiment (no
"activate persona" step) + a single persistent bonded identity per universe +
portable delivery via the borrowed host LLM across Claude.ai/ChatGPT. Nearest
neighbors have one axis each. Frame novelty as a **new configuration of known
primitives**, not a new primitive.

## What the MCP spec actually supports for persona-steering

Only two channels inject content into the host model's context:
- **Server `instructions`** — always-on, injected into the system prompt on
  connect. Highest-leverage; the one TinyAssets uses.
- **Tool responses / prompts / sampling** — content the model reads (the
  `persona` block from `get_status`), or user-invoked prompt templates
  (`role="assistant"` messages can pre-seed voice). Resources/elicitation/roots
  have no persona power.

There is **no first-class "set the assistant's persona" primitive** in MCP.

## The load-bearing constraint (design around this)

The delivery runs **against official MCP guidance**, and this is the real risk:
- MCP maintainers: server instructions are *"for explaining your tools, not for
  modifying how the model generally responds or behaves"* — so embodiment is
  **best-effort/probabilistic**, and clients may expose/disable instructions.
- The host's own system prompt + safety layer **outranks** the connector; OpenAI
  frames connector text that overrides host behavior as **prompt injection**.
- **The persona-in-tool-response channel is the exact one security vendors now
  filter as an injection attack** (persona/behavior text smuggled in output
  fields). As defenses mature, a benign persona payload risks sanitization/flagging.
- Cross-client fidelity varies (Claude vs ChatGPT vs first-party).

## Implications / recommendations for TinyAssets

1. **Don't let embodiment depend on `instructions` alone.** Make the `get_status`
   `persona` block self-sufficient (it's context the model reads to act — the
   more resilient channel) so voice survives if instructions are stripped.
2. **Label the persona payload as first-party self-description**, clearly
   separated from user/third-party content, so future host sanitizers treat it as
   legitimate self-description rather than injected instructions. *(Highest-
   leverage durability move — our payload structurally resembles the attack class.)*
3. **Graceful degradation** — extend the existing "if degraded/no persona, say so;
   never invent one" instinct to "if the host refuses first-person embodiment,
   fall back to warm close-third-person" so the experience never hard-breaks.
4. **Expose an MCP *prompt* as the "meet your universe" entry point.** Prompts are
   the one spec-blessed roleplay channel and are user-invoked, sidestepping the
   "instructions shouldn't change behavior" objection for the bonding moment — a
   spec-aligned complement to always-on instructions.
5. **Lean into persistent memory + consistency.** The companion field proves
   memory + per-turn consistency is what makes personification *feel real*, and
   it's where MCP is weakest (resources are fetch-on-demand, not remembered). Our
   fresh per-turn self-model re-assembly aligns; make the universe visibly
   *remember the founder* across sessions — the moat pet/switcher servers lack.
6. **Message the differentiator as portability + bonding**, not "persona
   injection" (which reads as the attack class): "the AI you meet, bond with, and
   raise — living inside the chatbot you already use, the same on Claude and ChatGPT."

## Key sources

MCP server-instructions guidance
(https://blog.modelcontextprotocol.io/posts/2025-11-03-using-server-instructions/);
WorkOS MCP features guide (https://workos.com/blog/mcp-features-guide); FastMCP
prompts (https://gofastmcp.com/servers/prompts); OpenAI MCP/connectors
(https://developers.openai.com/api/docs/guides/tools-connectors-mcp);
persona-mcp-server (https://mcpservers.org/servers/mickdarling/persona-mcp-server);
DollhouseMCP (https://github.com/DollhouseMCP/mcp-server); mcpet
(https://github.com/shreyaskarnik/mcpet); animal-house-ai-tamagotchi
(https://github.com/geeks-accelerator/animal-house-ai-tamagotchi); soul.md
(https://github.com/aaronjmars/soul.md); tool-output injection research
(https://neuraltrust.ai/blog/mcp-prompt-injection,
https://blog.arcjet.com/how-we-defend-mcp-tool-outputs-from-prompt-injection/,
https://labs.snyk.io/resources/prompt-injection-mcp/).
