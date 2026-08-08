# Vercel AI SDK → TinyAssets: what our agents should be able to do

**Source:** `https://github.com/vercel/ai` (AI SDK), docs at `ai-sdk.dev`.
**Read:** agents/overview, foundations/agents, agents/loop-control, agents/workflows,
ai-sdk-core/tools-and-tool-calling, ai-sdk-ui/chatbot-tool-usage,
ai-sdk-ui/streaming-data. Fetched 2026-08-07.
**Initial provider:** claude-code. **Requires opposite-provider review:** Codex.

## Correction (2026-08-08): the foundational gap this review missed

This audit mapped the SDK's *features* (loop control, typed errors, tool-state
UX, approval states, workflow patterns) and missed its *substrate*: an SDK agent
runs over a **`messages` array that accumulates across the loop** — conversation
state IS the model; `generateText`/`streamText`/`ToolLoopAgent` are built around
it. TinyAssets' universe turn is **stateless by construction** (fresh `claude -p`,
persona system prompt + current message only), which is a first-order divergence
from the exact thing being compared — and it was not written down. Live on
2026-08-08 it bit hard: a costly post 402'd, the founder said "try again", and
the turn had no memory of what to retry (the only cross-turn carrier is the
consumed-on-use pending-approval band-aid). See module 0 below and memory
[[agent-needs-cross-turn-memory]]. Process lesson: map the substrate (state,
memory) BEFORE the features bolted onto it.

## Executive judgment

The SDK is the same problem we are solving, one layer down: a provider-agnostic
agent loop with typed tools and a UI protocol. Three of its ideas name defects
we hit LIVE in the 2026-08-07 Slack rounds, and one of them we already have and
did not know.

The single largest gap is not capability. It is **visibility**. The SDK's whole
UI model is that a user watches tool calls stream through states as they happen.
Our Slack user gets 2–4 minutes of silence and then one message — I spent this
entire session reading MCP logs to know what the agent did, and the founder has
no equivalent. For a phone-first product that is the product.

## Module-by-module

### 0. The agent runs over a CONVERSATION — memory is the substrate (added 2026-08-08)

Every SDK entry point (`generateText`, `streamText`, `ToolLoopAgent`) takes a
`messages` array and appends to it every step: user turn, assistant turn, tool
calls, tool results all accumulate, and the next model call sees the whole
history. The loop is stateful *by construction* — memory of the conversation is
not a feature, it is the thing the agent runs on.

**TinyAssets:** the universe turn is stateless. Each `converse`/Slack-agent turn
shells to a fresh `claude -p` with the persona system prompt + the current
message only; prior turns are invisible. The consent-across-turns band-aid
(`action_approvals` pending record injected into the prompt) is the ONLY bridge,
and it is deleted the moment it is acted on — so a failed costly run leaves
nothing to retry (live 2026-08-08).

**Adopt — this is foundational, above the visibility gap.** Feed bounded recent
conversation history into the turn (both the Slack-agent and `converse` paths),
so the agent actually remembers what was said. Consent stays a separate gate.
Detail + fix direction: memory [[agent-needs-cross-turn-memory]].


### 1. The agent loop — `ToolLoopAgent`, `stopWhen`

The SDK treats an agent turn as a LOOP with an explicit stopping condition, not
one generation. Built-ins: `isStepCount(count)` (**default 20**, a runaway
guard), `hasToolCall(...names)`, `isLoopFinished()`. Custom conditions receive
the `steps` array — including `usage`, `toolCalls`, `toolResults` — so
cost-based termination is expressible.

**TinyAssets:** `converse` is one-shot. It runs one `claude -p` turn and returns
whatever that turn ended with. This is the direct cause of every partial
completion on 2026-08-07: built a branch and stopped, listed and stopped, read
and stopped, across five rounds. I patched it with prompt text ("finish the job
before you answer"), which helped — tool kinds per turn went 2 → 5 — but a
prompt is not a stopping condition.

**Adopt.** A real stop condition on the universe turn, with a step ceiling as a
runaway guard. We currently have NO bound on a turn's tool calls.

### 2. `HarnessAgent` — we are already this, without the controls

> "When you want to run a preconfigured established harness, such as Claude
> Code" — rather than building your own loop.

**TinyAssets:** `converse` shells to `claude -p`. So we ARE a HarnessAgent
consumer — we inherit Claude Code's internal loop and get none of the loop
control around it. That explains a lot: the agent loops well *inside* a turn and
cannot be steered *across* one.

**Watch/Adapt.** Worth knowing that the frontier has named this pattern; our
"engine" is a harness, and the interesting controls live at its boundary.

### 3. `toolChoice: 'required'` + a `done` tool — the real fix for stopping halfway

The docs give an explicit recipe for forcing completion:

> Combine `toolChoice: 'required'` with a `done` tool (lacking an `execute`
> function) to force explicit completion signals.

**TinyAssets:** nothing. This is a strictly better version of the prompt hack I
shipped — the agent cannot end the turn without declaring it is done, and
"declaring done" is observable rather than inferred from it having stopped
talking.

**Adopt.** Highest-leverage single change for the "builds a branch then stops"
class.

### 4. `prepareStep` — per-step control

Runs before each iteration; can override `model`, `activeTools`, `toolChoice`,
`messages`, sampling params, even the sandbox, for that step only.

**TinyAssets:** nothing. Notably `activeTools` — our agent now carries ~20 tools
(workspace, branch, automation, agent, chat-surface, operation-scope) on every
turn regardless of task.

**Defer, but note:** `activeTools` scoping is the cheap half and would reduce
the surface a turn must reason about.

### 5. Tool errors are TYPED and feed recovery

`NoSuchToolError`, `InvalidToolInputError`, `ToolCallRepairError`. Execution
errors surface as `'tool-error'` content parts, "enabling automated LLM recovery
in multi-step scenarios." `repairToolCall` fixes malformed calls without adding
steps that pollute history.

**TinyAssets:** errors are strings. BUT — we already have the interesting half
and I did not recognise it: our branch-build validator returns structured
`suggestions` with a `proposed_fix` per error. When I got the branch spec wrong
twice (missing `entry_point`, then `source`/`target` instead of `from`/`to`), it
told me exactly what to change both times. That is repair data nothing consumes
automatically.

**Adopt.** Feed `proposed_fix` back to the model as a repair step rather than a
plain rejection.

### 6. THE UX GAP — tool parts stream through states

Tool calls are message parts with a lifecycle the user watches:
`input-streaming` → `input-available` → `output-available` / `output-error`.
Inputs stream character-by-character. Plus approval states:
`approval-requested`, `approval-responded`, `output-denied`.

> "a transparent agentic experience where users observe each step of the model's
> reasoning and tool usage unfold in real-time"

**TinyAssets:** the Slack user sees NOTHING until a final post, minutes later.
Every diagnosis in this session came from
`mcp-logs-tinyassets-universe/*.jsonl`, which no founder can read.

**Adopt — this is the top priority.** Slack has the primitives: post a working
message immediately, then `chat.update` it as steps complete (Slack's own
progressive-disclosure pattern). The agent already knows its steps; nothing
transports them.

### 7. Approval before costly/irreversible tools

`approval-requested` / `approval-responded` / `output-denied` are first-class
states, and the loop pauses for them.

**TinyAssets:** none. Our agent spends the founder's own compute
(`run_branch` is scope-gated as `costly`) and can open PRs against their
repository, with no confirmation step. We gate on DECLARED authority, which is
correct, but authority is not the same as "are you sure".

**Adopt (security-relevant).** At minimum for `costly` operations. Slack has
interactive buttons; the shape exists.

### 8. Progress transport for non-React clients

`createUIMessageStream` + `writer.write({...})`. Persistent data parts join
message history; **transient parts** (`transient: true`) reach the client and
skip history — exactly right for "I'm working on it" notices. Reconciliation by
reusing an `id` so later writes merge into the same part.

**TinyAssets:** nothing. The reconciliation-by-id pattern maps precisely onto
one Slack message updated in place rather than a spam of new ones.

### 9. Workflow patterns — we have the substrate, ship none of the shapes

Sequential chaining, routing, parallel processing, orchestrator-worker,
evaluator-optimizer.

**TinyAssets:** our branches ARE nodes + edges — the substrate is strictly more
general. What we lack is any of these as REMIXABLE STARTING POINTS. The agent
composed a two-node `scan → deliver` branch from scratch on 2026-08-07 because
there was nothing to start from.

**Adopt as commons content, NOT platform code.** These five are exactly the
"powerful primitives the power user loves" — seed branches a user remixes.
Shipping them as classes would be the bundled-workflow trap; shipping them as
branch templates is the commons working as designed.

### 10. `dynamicTool()` and MCP

The SDK treats MCP tools as dynamic (unknown schema, runtime validation),
"suited for rapid iteration but lacking the type safety and performance of
native tools".

**TinyAssets:** our universe agent's entire surface is an MCP server. So we sit
on the "rapid iteration, no type safety" side by construction — worth knowing
when a tool's contract matters.

## What to do, in order

0. **Give the turn conversation memory** (added 2026-08-08 — the foundational
   miss). Feed bounded recent history into the universe turn, both paths. Without
   it there is no agent, only a series of amnesiac one-shots; it is the cause of
   the "try again" failure and the reason the consent band-aid had to exist.
1. **Stream progress to Slack.** One message posted immediately, updated as
   steps complete. Biggest UX win available and it needs no new authority model.
2. **`done`-tool completion signal.** Replaces the prompt hack; makes "did it
   finish" observable.
3. **Feed `proposed_fix` back as tool-call repair.** The data already exists.
4. **Approval for `costly` operations**, via Slack buttons.
5. **Seed the five workflow patterns as remixable branches**, not classes.
6. `activeTools` scoping per task; step ceiling as a runaway guard.

## Open questions

- Does a step ceiling belong to the platform or to the user's automation? By our
  own rule (capabilities are user-declared) it is arguably a per-automation
  budget, not a constant.
- Approval interrupts a turn that currently runs to completion in one
  subprocess. Does the harness support pausing, or does approval have to happen
  BEFORE the turn (pre-authorising a plan) rather than mid-loop?
