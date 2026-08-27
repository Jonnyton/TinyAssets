# vercel/ai full module sweep — everything the first two passes did not cover

Date: 2026-08-10 (all web citations accessed 2026-08-10). Status: **research note /
external evaluation only** — no code touched beyond this file.
**Initial provider: claude (Fable 5, Claude Code harness). Requires opposite-provider
review: Codex** (AGENTS.md §Project Skills gate) before any build/push/live rollout
based on this note.

**Prior passes this builds on (not duplicated):**

1. **Agent-loop + UX audit** — `docs/audits/2026-08-07-vercel-ai-sdk-agent-and-ux-implications.md`,
   dated 2026-08-07, corrected 2026-08-08 with "module 0" (the substrate lesson: the SDK
   agent runs over an accumulating `messages` array; map substrate before features).
   **Finding: this artifact is NOT on `origin/main`** — it exists only on branches
   `claude/agent-persistent-memory` / `claude/slack-socket-mode` (commits `73d1d444`,
   `8fcb8ff9`). A durable research artifact stranded on an unmerged feature branch is
   itself a process defect; fold it back to main docs.
2. **Memory-pattern pass** (2026-08-08/09, memory `agent-needs-cross-turn-memory`) —
   mined `loadChat/saveChat`, durable-step retry, resume-streams. Its output is now
   **merged and live**: `tinyassets/conversation_store.py` + `conversation_memory.py`
   landed on `origin/main` today (#2400 `d9471d1e`, hardening #2401 `91729b9b`).
3. **Provider/auth layer pass** — `docs/design-notes/2026-08-10-vercel-ai-provider-layer.md`
   (separate agent, same day). Covers custom providers, CLI-wrapping subscription
   providers, Gateway BYOK, and the `ProviderMiddleware` seam proposal. **Skipped
   entirely here**; where middleware consumers are discussed below they reference that
   note's seam rather than re-proposing it.

**Checkout caveat:** the local working tree used for code mapping (`3124e2d8`) is 689
commits behind `origin/main` (`7b451b2c`). Citations marked `[OM]` were verified against
`origin/main`; unmarked citations are long-stable code identical in both trees.

---

## 1. What changed in vercel/ai since the prior audit

**Version state (web-verified 2026-08-10):** current major is **AI SDK 7** (`ai@7.0.59`,
released today). Timeline: v4.0 2024-11-18 → v5 2025-07-31 → v6 2025-12-22 → **v7
2026-06-25** ("This release sets the foundation for agents and AI platforms in
production: approvals, durability, telemetry" — vercel.com/changelog/ai-sdk-7).

**Since 2026-08-07 specifically (patch-level, 3 days):** nothing structural. Three
relevant patches:

- **Gateway retried-`doStart` idempotency** — mints an idempotency token per logical
  start and forwards it as an `idempotency-key` header so a retried start cannot
  produce a duplicate billable generation. This is *exactly* the shape of our open
  action-attempt-ledger follow-up (memory `agent-needs-cross-turn-memory`: an
  indeterminate delivery must HOLD, a retry must be provably side-effect-free).
- **Resumed-stream cancellation hardening** — stop pending AND active resumed chat
  streams after cancellation; prevent overlapping resumptions applying stale updates.
  (Lesson filed under §3 durability: resumability creates a concurrent-resume race
  class you must design for.)
- xAI image-generation server-side tool (not relevant).

**The real delta:** the 2026-08-07 audit read v7-era docs but sampled ~a fifth of v7
(loop control, done-tool, typed tool errors, tool-state UX, approval states, workflow
pattern names). The June v7 release repositioned the SDK from chat library to **agent
platform**, and the un-sampled 80% is this note's subject: WorkflowAgent durability
semantics, HarnessAgent, MCP client hardening, `@ai-sdk/otel` telemetry, approval
HMAC-hardening, timeout budgets, `runtimeContext`/`toolsContext`, structured-output
repair, AI Elements/transports, and release engineering.

**Most surprising single fact:** v7's `HarnessAgent` wraps **Claude Code and Codex as
sandboxed subprocess runtimes with host-executed tools, session detach/resume, and
event streaming over a sandbox-exposed WebSocket** — i.e., the frontier TypeScript SDK
now ships *our* `converse` architecture (genuine-CLI subprocess in a confined workspace,
tools granted from outside, turn-scoped policy) as a named first-class primitive. That
is independent convergence on the shape we chose, plus a mineable reference for the
controls we still lack at that boundary (session resume, suspended-turn continuation,
per-step semantic stopping).

---

## 2. Module-by-module sweep

Verdict vocabulary: **COPY** (adopt the mechanism as a TinyAssets-native primitive),
**LEARN** (adopt the idea/schema, different shape), **AVOID** (rejected for our
architecture), **KEEP-OURS** (we are ahead; export the lesson, import nothing),
**PRIOR** (already adopted by an earlier pass). Patterns over library adoption
throughout — the one genuine library case is flagged in §2.5.

### 2.1 Agent loop — Agent interface, loop control, approvals

**vercel/ai (v7):** `Agent` is an interface; `ToolLoopAgent` is the default
implementation (LLM call → execute tools → repeat; default 20 steps). `stopWhen`
(`isStepCount`, `hasToolCall`, `isLoopFinished`, custom predicates over `steps` incl.
usage), `prepareCall` (once, pre-loop) vs `prepareStep` (per step: model, `activeTools`,
`toolChoice`, messages, sampling). **`runtimeContext`** — serializable shared state
flowing through `prepareStep`, approvals, callbacks, and telemetry. **`toolsContext`** —
per-tool map; each tool's `execute` sees *only its own* `contextSchema`-validated entry
(scoped secrets/config). **Tool approval**: v6 `needsApproval` (bool or async predicate
on input) → v7 `toolApproval` policies (user-approval / auto-approve / auto-deny /
typed functions), and **approval replay is hardened with HMAC signing to prevent
argument tampering** between request and grant. **First-class timeout budgets**: total,
per-step, per-chunk, per-tool.

**TinyAssets (origin/main):** the universe turn is a **zero-tool, two-shot, no-loop**
call — one `claude -p` for the reply, one for learning extraction
(`tinyassets/universe_intelligence.py`; `_ENGINE_ALLOWED_TOOLS = ("WebFetch",)`), no
step counter, no stop condition, no completion signal; the only timeout is one flat
300s subprocess budget (`providers/claude_provider.py:145-157`) plus per-node
`NodeTimeoutError` in graph runs. The 43-tool agent loop with a `finish` tool and
approval actions (`universe_agent_server.py`, `universe_agent_actions.py`) exists
**only on the rejected-trust-gate branch** — `action_approvals` /
`record_approval` / `consume_if_granted` have zero matches on `origin/main`.

**Verdicts:**

- **COPY — HMAC-sign approval payloads.** When the approval lane re-lands, the pending
  record must bind `(universe, action_key, canonical input digest)` under an HMAC so
  the granted args cannot drift from the requested args between turns. The SDK added
  this *because* replay tampering happened; our single-use pending records (branch
  design) have the identical hole. Cheap, and it composes with the action-attempt
  ledger already specified in memory.
- **COPY — the four-way timeout budget.** Split our one 300s wall into
  total-turn / per-provider-call / per-tool budgets when the tool loop lands. Today a
  turn on `origin/main` can legally block ~90s of retry backoff + 2×300s provider
  timeouts `[OM]` (`_WRITER_RETRY_BACKOFFS_S`, `universe_intelligence.py:537`) with no
  intermediate bound.
- **LEARN — `toolsContext` scoping.** "Each tool sees only its own validated context
  entry" is the antidote to the `permissive-helper-used-as-restrictive` failure family
  and is the right shape for R2-1's credential materialization: the tool/provider gets
  a validated slice, never the ambient env.
- **PRIOR** — `stopWhen`, done-tool, `activeTools`, step ceiling: adopted by the
  2026-08-07 audit; built on the branch; blocked with the trust-gate rework.

### 2.2 Workflows / durability

**vercel/ai (v7, `@ai-sdk/workflow`):** `WorkflowAgent` — execution state persisted to
durable storage between steps; survives deploys, restarts, delayed approvals. A tool
`execute` marked `'use step'` gets **automatic retry (default 3 attempts total),
result persistence, and per-step observability**; unmarked tools are in-memory. An approval request
**suspends the workflow durably** — the pending approval survives process restarts.
`WorkflowChatTransport` resumes a broken client stream from `startIndex` against a
`runId`. Context must be serializable (identifiers, not clients).

**TinyAssets:** we already own the substrate the SDK had to build: LangGraph +
`SqliteSaver` with `thread_id == run_id` (`tinyassets/runs.py:2355-2374`), WAL-forced
checkpointing with retention (`checkpointing/sqlite_saver.py`), `resume_run` with
typed `ResumeError` reasons and branch-version matching (`runs.py:3218-3500`),
startup recovery flipping in-flight runs to `interrupted` (`runs.py:3503-3536`),
lazy orphan detection on read (`runs.py:112-241`), a crash-refiring scheduler
(`scheduler.py:559-632`, `last_fired_at` stamped only after a successful fire), and
three heartbeat layers (lease `branch_tasks.py:362-405`, supervisor
`cloud_worker.py:808-816`, staleness reader `api/status.py:546-604`).

What we do **not** have, precisely:

- **No checkpoint-based step retry for ordinary nodes.** A node whose logic fails
  kills the run (`runs.py:2375-2543` converts everything to terminal statuses);
  besides provider-level tenacity, the one existing step-retry is the child-branch
  class (`on_child_fail="retry"` with a thread-local budget,
  `graph_compiler.py:2318-2363`, `2000-2023` — Codex spot-check correction). The
  checkpoint exists; nothing automatically resumes from it for transient failure
  classes on ordinary nodes.
- **No durable pending approval** (no approvals on main at all — and the branch design
  consumes the grant *before* the effect, so a transient failure burns it; the live
  402 incident).
- **Two stale docstrings actively denying resume exists** — `runs.py:3509-3515` and
  `api/runs.py:539` claim mid-run resume "is not available today" while
  `resume_run` / `_action_resume_run` implement exactly that. Small defect; fix.

**Verdicts:**

- **COPY — `'use step'` semantics on our own substrate.** Classify node failures
  (transient: timeout, empty response, provider-exhausted vs. permanent: compile,
  validation) and auto-resume-from-checkpoint N times for the transient class before
  declaring the run failed. This is the platform-level twin of the deferred "Layer-5
  durable-step retry" already on the books for the conversational turn — one design,
  two consumers. Zero new storage; it is a retry policy over `SqliteSaver` checkpoints
  we already write.
- **COPY — idempotency keys on external effects.** The Aug-10 gateway patch (mint an
  idempotency token per *logical* start, forward on every retry) is the exact
  mechanism the action-attempt ledger needs so "retry after 402" can never double-post.
  Effectors should accept and dedupe on an idempotency key derived from the approval
  id + payload digest.
- **LEARN — approval-suspends-durable-workflow.** When approvals land, a pending
  approval is a *durable suspension point* (survives restart/deploy), not an in-memory
  wait. Our conversation store + run store both already know how to persist; wire the
  pending approval into one of them, don't invent a third.
- **KEEP-OURS** — self-hosted SQLite durability. `WorkflowAgent` requires the Vercel
  Workflows runtime; our equivalent is vendor-free. Also KEEP the resumability-race
  lesson from their own patch: concurrent resumes of one stream must be
  single-flighted (we have the idle-cycle single-flight pattern to reuse,
  `idle_cycle.py:217-300`).

### 2.3 Tools / MCP surface

**vercel/ai (v7, `@ai-sdk/mcp`, protocol `2025-11-25`):** `createMCPClient` with
http/sse/stdio transports, OAuth `authProvider` (+
`validateAuthorizationServerURL` origin restriction), session reattachment
(`initialSessionId`, `onSessionIdChange`, `onSessionExpired`). Tools load either
schema-discovered (dynamic, untyped) or with explicit per-tool schemas (typed, loads
only the named tools). **`outputSchema` validates `structuredContent`** returns.
**`fingerprintTools` + `detectToolDrift`** (exported from the core `ai` package —
Codex spot-check correction) digest security-relevant fields (description, schema,
title) against a persisted baseline — anti rug-pull.
**Elicitation**: a server can request user input mid-tool
(`onElicitationRequest` → accept/decline/cancel). `maxRetries` for transient
`tools/call` failures, explicitly warned off for non-idempotent operations. **MCP
Apps**: model-visible vs app-only tool separation + sandboxed iframe rendering.

**TinyAssets (server side of the same protocol):** seven static handles registered via
`_register_structured_tool` (`universe_server.py:145-182`) with signature-rewriting +
docstring-derived `Field` descriptions (`mcp_schema_utils.py:102-147`) — but
**`output_schema=None` on every tool**; `_structured_return` emits `structuredContent`
without ever declaring its shape. `_faithful_text_content` (6000-char budget) keeps
text-only clients honest. Deprecated fat tools are hidden-but-dispatchable via FastMCP
middleware (`universe_server.py:1936-1960`). `anonymous_write_challenge` produces a
real 401 + `WWW-Authenticate` so clients launch OAuth. Drift protection is the
`--assert-handles` canary (Hard Rule 11) asserting the **handle name set only**.
Version-pinned catalog path (`connector_catalog.py`) for host cache invalidation.

**Verdicts:**

- **COPY — declare `outputSchema` on the seven handles.** v7-class clients (and the
  ChatGPT Apps SDK) validate `structuredContent` against it; today our returns are
  shapeless by contract. This also gives the planned mobile app (§2.5) a typed client
  surface for free, and makes the connector contract testable (`get_status` already
  has `schema_version: 1` — the only tool that versions its shape).
- **COPY — deepen the drift canary from names to fingerprints.** `--assert-handles`
  catches a renamed/removed handle; it cannot catch a mutated tool *description* —
  which is an instruction surface injected into every client conversation (the exact
  channel `fingerprintTools` exists to guard). Extend `mcp_public_canary.py` to hash
  `(name, title, description, inputSchema)` per tool against a committed baseline;
  exit 4 on drift. Small script change; closes a real injection/rot channel.
- **ADAPT/WATCH — elicitation as the MCP-native approval channel.** Server-requested
  user input mid-tool is the *principled* transport for "are you sure" on `costly`
  actions over MCP — better than prompt-embedded approval bands. Gate: unknown
  whether claude.ai/ChatGPT render elicitation today (open question §5). Design the
  approval lane so elicitation can become its MCP transport without rework.
- **LEARN — session reattachment semantics.** `initialSessionId`/`onSessionExpired`
  is the client-side contract our `converse:<universe_id>:<actor>` session ids
  (conversation store `[OM]`) will need the day any client resumes across
  connections. Cheap to keep the id shapes compatible now.
- **LEARN — MCP Apps' model-visible vs app-only split** is the same invariant as our
  brain-write **relay directive** (`_BRAIN_WRITE_RELAY_ACTIONS`,
  `universe_server.py:1014-1019`): some tools exist for the surface, not the model.
  Their formulation is worth citing when we spec which handles a client app may call
  directly vs must relay.

### 2.4 Structured output + error taxonomy

**vercel/ai (v7):** `Output.object/array/choice/json/text` on `generateText`/agents;
`elementStream` yields only complete schema-validated elements;
`AI_NoObjectGeneratedError` carries `.text`, `.response`, `.usage`, `.cause`;
`repairToolCall` fixes malformed tool calls without polluting history;
`extractJsonMiddleware` strips fences; v7 adds "JSON Schema post-processing and
malformed JSON repair" as a reliability layer. Errors are **typed classes** checked via
`isInstance`.

**TinyAssets:** a deliberate prompt-contract regime because 3 of 6 providers are
CLI-wrapped with no native `response_format` (`graph_compiler.py:855-880`):
`_needs_json_contract` → plain-text RESPONSE FORMAT suffix → `_extract_json_object`
(3-step syntactic salvage: parse → fence regex → bare-object regex) → `_coerce_value`
type coercion → **on failure, `CompilerError` kills the run** (`:1285-1311`), no
re-ask. The learning path silently returns `{}` on bad JSON
(`universe_intelligence.py:237-255`). The branch validator returns structured
`suggestions` with computed `proposed_fix` (`api/branches.py:1327-1405`) — strict-with-
suggestions, machine-readable repair data. Failure classification at the API boundary
is **substring matching over lowercased prose** (`api/runs.py:333-486`), producing a
genuinely good routing field the SDK lacks: `actionable_by ∈ {chatbot, host, user,
none}`.

**Verdicts:**

- **COPY — one bounded repair re-ask at the node JSON layer.** The SDK treats
  malformed structured output as a *recoverable stage*; for us it is a run-killer.
  Add exactly one re-ask (error + `response[:400]` + expected keys, same provider)
  before raising `CompilerError`. Bounded, observable as a run event, and directly
  reduces the `empty_response`/malformed-JSON failure class that burns whole runs.
  (The prior audit's adopt-item — feed `proposed_fix` back on branch-build — is the
  same idea one layer up; both remain unbuilt on main.)
- **LEARN — typed failure classes over prose-matching.** Two of our mappers re-derive
  structure from strings that other code owns: `_classify_run_error` (substring
  taxonomy) and `_errors_to_suggestions` (substring → proposed_fix; a reworded
  validator message silently degrades to the generic fallback). The durable shape is
  the one the engine already uses internally (typed exceptions with structured
  payloads, `exceptions.py`, `AllProvidersExhaustedError.chain_state`): let
  `validate()` return codes+params, render prose at the edge.
- **KEEP-OURS — `actionable_by` routing and `evidence_caveats`.** "Who can fix this"
  is a contract the SDK does not have; it is load-bearing for a chatbot-mediated
  product. Export as a lesson, change nothing.

### 2.5 Streaming / UI — chatbot relay, site, mobile app

**vercel/ai (v7):** message parts with a watchable tool lifecycle
(`input-streaming → input-available → output-available/output-error`,
`approval-requested/responded/output-denied`), persistent vs **transient** data parts,
reconcile-by-id, `DirectChatTransport` (UI → agent, no server),
`WorkflowChatTransport` (resume from `startIndex`), AI Elements (20+ shadcn/ui chat
components incl. tool displays), `@ai-sdk/tui` for terminal testing, `finalStep`
separation of full-run vs last-step results.

**TinyAssets:** **no streaming exists anywhere in the stack.** `proc.communicate()`
buffers the whole subprocess (`claude_provider.py:148`); the MCP `converse` returns
one JSON blob; grep for `report_progress|progressToken|notifications/progress`
across `tinyassets/` returns zero — we never use MCP's own progress-notification
channel. Slack posts once at the end (`slack_agent_turn.py` `[OM]`; no `chat.update`
anywhere; the ingress handler cannot post at all by design — a failed turn is silent
to the user). The site has no live chat (the 593-line MCP Playground and the ChatDemo
capture are unrouted; SSE parsed first-`data:`-line-only, `playground.ts:69-73`). The
mobile app exists only as today's design note
(`docs/design-notes/2026-08-10-minimal-onboarding-android-app.md`), whose preferred
endpoint decision is **option A: the app speaks MCP directly to `tinyassets.io/mcp`
with the WorkOS bearer**.

**Verdicts:**

- **COPY — emit MCP progress notifications from `converse` and `run_graph`.** The
  protocol supports `progressToken`/`notifications/progress`; the server already
  knows its phases (`status.json.current_phase` is written today and only ever
  polled, `_activity.py:59-80`). Chatbot hosts may ignore it — the **option-A mobile
  app will not**, and building the tool surface progress-capable now is what makes
  the app's chat UI able to show tool-lifecycle states at all. A turn that can
  legally take minutes with zero feedback is the prior audit's "the visibility gap is
  the product" finding; this is its MCP-native transport.
- **LEARN — transient vs persistent parts.** When progress lands (Slack `chat.update`
  or app), distinguish "I'm working" notices (transient, never persisted) from
  tool-result parts (persisted, reconciled by id). The conversation store should
  never accumulate progress spam — the SDK drew this line for exactly that reason.
- **Genuine library case (the one in this sweep):** if the app/site chat client is
  built in JS (React Native / web view / SvelteKit island), **AI SDK UI + AI
  Elements is the strong candidate for the client half** — typed message parts,
  tool-state rendering, resume transports, maintained components — talking to our
  MCP server via a custom transport. This imports zero server-side dependency and
  replaces the weakest part of the app plan (hand-rolling a streaming chat UI).
  Kotlin-native would forfeit this; weigh in the app design gate.
- **KEEP-OURS** — the relay contract (chat surface is a control station, never the
  author; `PLAN.md` API & MCP module) is orthogonal to and compatible with all of
  the above.

### 2.6 Telemetry / observability / evals

**vercel/ai (v7):** `registerTelemetry` + `@ai-sdk/otel` emitting **GenAI
semantic-convention spans** (`invoke_agent`/`chat {modelId}`/`execute_tool {toolName}`;
`gen_ai.usage.input_tokens/output_tokens`, `operation.duration`,
`time_to_first_chunk`, `time_per_output_chunk`), lifecycle callbacks, `enrichSpan`,
DevTools as a pluggable integration, and **sensitive-context allowlists**
(`recordInputs/recordOutputs: false`; `includeRuntimeContext`/`includeToolsContext`
name exactly which fields telemetry may see). **The SDK has no eval framework** —
DevTools inspects; nothing grades.

**TinyAssets:** zero OTel by construction; observability is files + SQLite + external
canaries. Per-call telemetry is `_call_meta = {model, family, latency_ms, degraded,
attempts}` (`providers/router.py:569-584`). **`runs.token_count` exists and is never
populated** — the code says so itself: "token_count and model are not yet collected
(no LLM billing hooks)" (`runs.py:3947-3950`). `get_status` is a self-auditing
evidence blob (release receipts, `policy_hash` config-drift detection,
`evidence_caveats` honesty strings — `api/status.py`). Canaries are the real
observability layer (independent GHA vantage, open-issue-as-consecutive-state,
`--assert-handles`). Evals: a full stack the SDK lacks — structural (zero-LLM tier),
editorial judge **routed cross-family to Codex by the `judge` fallback chain**
(`evaluation/editorial.py:136` → `router.py:89-94`, `claude-code` deliberately absent),
process/trajectory evaluation, scenario runner, deterministic KEEP rubric, and a spec
that *forbids* LLM-graded numeric scoring on the judgment loop
(`openspec/specs/evaluation-outcomes-and-attribution/spec.md:12`).

**Verdicts:**

- **COPY — populate usage from the CLI JSON envelopes.** Highest-leverage small item
  in this sweep. `claude -p --output-format json` (and codex JSON modes) return usage
  metadata we currently discard (`complete_json` reads `parsed["result"]` only;
  `converse` doesn't even use the JSON path). Wire usage → `_call_meta` →
  `runs.token_count` + a per-universe cost ledger. Everything downstream needs it:
  paid-market pricing/settlement (Track E), user-subscription capacity
  (`universe-writer-rate-limit`), per-turn budgets, and honest `get_status` cost
  evidence. Verify envelope fields per pinned CLI version first (§5).
- **LEARN — GenAI semantic conventions as a schema, not a stack.** Do not adopt OTel
  infrastructure; DO name our run-event and `_call_meta` fields compatibly
  (`gen_ai.usage.input_tokens`, operation duration, time-to-first-output) so a future
  exporter is a format shim, not a re-instrumentation. The `opentraces` Watch row
  (2026-05-02 radar) already pointed here; this is its concrete landing.
- **LEARN — telemetry-sees-allowlist.** Our redaction is surface-specific
  (`_redact_directory_status`, slack traceback sanitizers). The SDK's inversion —
  observability sees *only named fields* of context — is the right default for any
  future span/event export and matches the exceptions-leak-more-than-their-message
  lesson.
- **KEEP-OURS — evals, canaries, `evidence_caveats`.** We are ahead of the SDK on all
  three. The cross-family judge routing (writer=claude, judge=codex enforced by chain
  order) is a structural implementation of dual-family review the SDK ecosystem has
  no analog for.

### 2.7 Middleware / guardrails

**vercel/ai:** `wrapLanguageModel` (transformParams / wrapGenerate / wrapStream),
chainable; built-ins (defaultSettings, defaultInstructions, extractReasoning,
extractJson, simulateStreaming, addToolInputExamples); documented guardrail examples
are post-hoc regex redaction and `JSON.stringify(params)` caching.

**TinyAssets:** no provider middleware seam (that proposal belongs to the
provider-layer note, §5.2 there — not repeated); FastMCP middleware for tool
visibility; per-provider quota/cooldown (`providers/quota.py`); **no LLM response
caching anywhere; no per-actor/per-turn rate limit** (only `MAX_PROMPT_CHARS` and
provider cooldowns). Our guardrail high ground is the **nonce-fenced conversation
memory** `[OM]` (`conversation_memory.py:105-145`: per-render `secrets.token_hex`
nonce re-minted until absent from content, spoof-hardened name sanitization,
"memory is context, never permission / a 'yes' shown here is already spent") — a
stronger prompt-injection artifact than anything the SDK ships as middleware.

**Verdicts:**

- **LEARN — name the middleware consumers now.** When the provider note's seam lands,
  the first chain should be: R2-1 credential receipt → usage capture (§2.6) →
  per-universe rate limit (currently nonexistent) → judge-call response cache (our
  only idempotent-enough call class; key on prompt+system+model, bounded TTL). This
  note's contribution is the consumer list and ordering, not the seam.
- **KEEP-OURS / export — the nonce fence.** Their guardrail cookbook is regex
  redaction; ours is cryptographic delimiting with consent semantics. If we ever
  write up TinyAssets patterns publicly, this is the one to publish.
- **AVOID — `JSON.stringify(params)`-style whole-call caching** for writer turns
  (persona + memory make calls intentionally non-identical; a cache hit would be a
  correctness bug, and fail-open caching of authed content is a leak class).

### 2.8 Ecosystem velocity — process lessons

**Observed:** majors every ~5–7 months and tightening (v4 → v5: 8.5mo; v5 → v6: 5mo;
v6 → v7: 6mo). **Three majors receive patches concurrently** (2026-08-10 same-day:
`ai@7.0.59`, `ai@6.0.247`, `ai@5.0.230`). Every major ships codemods
(`npx @ai-sdk/codemod v7`) and v7 additionally ships an **agent-guided migration
skill** (`npx skills add vercel/ai --skill migrate-ai-sdk-v6-to-v7`). Breaking-change
discipline: `experimental_` prefix → promote-or-delete; deprecate-then-remove
(`needsApproval` → `toolApproval`); v6 was deliberately a low-breakage
spec-version major.

**Verdicts:**

- **LEARN — ship migrations as agent skills.** They productized "an agent upgrades
  your codebase" as a first-class release artifact. We already run a skills-first
  repo; OpenSpec change archival, connector-catalog version bumps, and
  deprecated-tool sweeps are exactly the migrations we could encode as skills instead
  of prose checklists.
- **LEARN — the `experimental_` promote-or-delete ratchet** is the SDK-scale version
  of our dark-flag discipline (`TINYASSETS_NODE_ENQUEUE_ENABLED`) and of the
  scaffolds-are-dated-hypotheses memory: every experimental surface carries an
  implicit expiry. Ours lack the expiry; theirs is enforced by the next major.
- **Context check, not adoption:** three concurrent patch lanes require release
  automation we should not build at zero users (forward-only deploy policy stands;
  Level-2 rollback remains founder-gated per memory).

---

## 3. Coverage vs the full TinyAssets module map

Sweep areas mapped onto every PLAN.md module (and the openspec capabilities they
own). "—" = no meaningful vercel/ai counterpart exists; noted where that is a
strength signal in either direction.

| PLAN.md module | vercel/ai counterpart | This sweep | Net direction |
|---|---|---|---|
| Engine & Domains | ToolLoopAgent/WorkflowAgent loops | §2.1, §2.2, §2.4 | Import: step-retry, repair re-ask, timeout budgets |
| Daemon Platform | none (no multi-tenant dispatch, souls, fleets) | §2.1 (`toolsContext`) | KEEP-OURS; import context-scoping idea only |
| Brain | provider memory tools; load-on-start pattern | prior memory pass (merged today) | Done; substrate now on main |
| Goals & Gates | approval states only | §2.1, §2.2 | Import: HMAC + durable suspension when lane lands |
| Evolution & Evaluation | **none — SDK has no evals** | §2.6 | KEEP-OURS (structural/editorial/process/scenario stack) |
| Providers | LanguageModel spec, registry, middleware | provider-layer note (skipped) | see that note |
| API & MCP Interface | `@ai-sdk/mcp` client, MCP Apps | §2.3 | Import: outputSchema, fingerprint canary; WATCH elicitation |
| Distribution & Discoverability | provider/tool directories | §2.3 (catalog versioning) | Neutral; our version-pinned catalog is adequate |
| Harness & Coordination | codemods + migration skills; HarnessAgent | §2.8, §1 | Import: migration-as-skill; HarnessAgent validates our shape |
| Uptime & Alarms | **none — no outside-in probing model** | §2.6 | KEEP-OURS (canary family + GHA vantage) |
| Constraints | — | — | n/a |

openspec capabilities most touched: `graph-execution-substrate` (§2.2, §2.4),
`live-mcp-connector-surface` (§2.3, §2.5), `universe-personification-and-relay`
(§2.1, §2.5), `provider-routing` (provider note + §2.6 usage), `paid-market-economy`
(§2.6 usage prerequisite), `evaluation-outcomes-and-attribution` (KEEP-OURS §2.6),
`knowledge-retrieval-and-memory` (prior pass, merged).

---

## 4. Top-5 actionable implications (any module)

1. **Populate LLM usage/cost from the CLI JSON envelopes** (§2.6). `runs.token_count`
   has been a dead column since inception; the data is already in the subprocess
   output we discard. Unblocks paid-market settlement math, subscription capacity
   planning, per-universe budgets, and honest cost evidence in `get_status`.
   Files: `providers/claude_provider.py`, `providers/codex_provider.py`,
   `providers/router.py` (`_call_meta`), `runs.py`, `api/status.py`.
2. **Transient-failure auto-resume on the run substrate + idempotency keys on
   external effects** (§2.2). We write checkpoints and then never use them for
   recovery; the SDK's `'use step'` semantics and its Aug-10 idempotency-key patch
   together answer both halves of the already-filed retry/ledger follow-up. Files:
   `runs.py` (retry policy over existing `SqliteSaver`), effector modules
   (idempotency-key dedupe).
3. **MCP-native progress transport** (§2.5). Emit `notifications/progress` from
   `converse`/`run_graph` phases the server already tracks; declare `outputSchema` on
   all seven handles (§2.3) in the same change since both harden the connector
   contract the planned option-A mobile app will consume raw. Files:
   `universe_server.py`, `universe_intelligence.py`, `mcp_schema_utils.py`.
4. **Approval hardening pattern-pack for the re-landing approval lane** (§2.1, §2.2,
   §2.3): HMAC-bind grant to canonical requested args; make pending approvals durable
   suspension points that survive restart; do not consume grants before effects
   succeed; design elicitation-compatibility so MCP can become the approval transport
   when clients support it. This is review input to the trust-gate rework
   (Codex-as-builder lane), not a new lane.
5. **Fingerprint the advertised tool surface, not just its names** (§2.3). Extend
   `mcp_public_canary.py` with a committed `(name, title, description, inputSchema)`
   digest baseline and a drift exit code — the client-side `fingerprintTools` idea
   applied to our own Hard-Rule-11 guard. Files: `scripts/mcp_public_canary.py`,
   `scripts/_canary_common.py`, baseline JSON under `docs/ops/` or `packaging/`.

Honorable mentions: bounded node-JSON repair re-ask (§2.4); typed validator error
codes replacing substring→suggestion mapping (§2.4); fix the two stale "resume is not
available" docstrings (§2.2 — genuine small defect, 5-minute fix); AI SDK UI as the
mobile/site chat client library **iff** the app is JS-based (§2.5 — feeds the app
design gate, not a standalone lane).

## 5. Open questions / verification gaps

- **Client support for MCP progress + elicitation:** do claude.ai and ChatGPT render
  `notifications/progress` or elicitation requests today? Determines whether §4.3 is
  app-only or benefits chatbot users immediately. Verify empirically via `ui-test`.
- **CLI usage envelopes:** exact usage/cost fields in `claude -p --output-format json`
  and codex JSON output on our pinned CLI versions — verify before sizing §4.1.
- **Where does the durable pending approval live** — conversation store, run store, or
  its own table? Design-gate question for the trust-gate rework; §4.4 constrains but
  does not answer it.
- **Mobile app client framework** (Kotlin vs JS-based) — decides the §2.5 library
  case. Belongs to the app design note's approval, not here.
- **Prior-audit fold-back:** `2026-08-07-vercel-ai-sdk-agent-and-ux-implications.md`
  should be cherry-picked to main `docs/audits/` (it is referenced by memory and by
  this note but is invisible to a fresh main checkout).

## 6. Review gate and pickup

- **Cross-provider gate:** initial provider claude; **Codex review required** before
  any of §4 becomes a build lane (AGENTS.md §Project Skills). Suggested review frame:
  "refute the five implications; check the SDK claims against ai-sdk.dev v7 docs and
  the cited TinyAssets files on origin/main."
- **Inline Codex adversarial spot-check already run (2026-08-10, thread
  `019feec0-8450-7341-ba61-c66bf7e9ebaf`, read-only, against `origin/main@7b451b2c`
  and upstream `vercel/ai@74556f7`):** claims on dead `token_count`, missing
  `outputSchema`/progress notifications, and the stale resume docstrings
  **CONFIRMED**; two corrections applied above (child-branch `on_child_fail="retry"`
  exists, so "no per-step retry" was overbroad; `'use step'` is 3 *attempts* and
  `fingerprintTools`/`detectToolDrift` live in core `ai`). This spot-check is NOT the
  formal review — the full gate above stays open.
- **No STATUS.md row was added by this session:** the dispatching task was scoped
  read-only with a single deliverable file, and every §4 item is review-blocked
  behind the Codex gate anyway. Whoever picks this up: add one Work row per approved
  implication, smallest first (§4.1 or the docstring fix), with this note in Depends.

## Sources

- vercel.com/changelog/ai-sdk-7 (v7 announcement, 2026-06-25); vercel.com/blog/ai-sdk-6
  (2025-12-22); vercel.com/blog/ai-sdk-5; vercel.com/blog/ai-sdk-4-0
- github.com/vercel/ai/releases (versions + 2026-08-08..10 patches)
- ai-sdk.dev: /v7/docs/agents/workflow-agent, /docs/ai-sdk-harnesses/harness-agent,
  /docs/ai-sdk-core/{telemetry, middleware, mcp-tools, generating-structured-data},
  /docs/agents/workflows
- github.com/vercel/ai-elements; vercel.com/changelog/introducing-ai-elements;
  vercel.com/changelog/program-agent-harnesses-with-ai-sdk
- TinyAssets file citations: working tree `3124e2d8` and `origin/main` `7b451b2c`
  (marked `[OM]`), enumerated inline.

---

## Codex formal review — VERCEL_SWEEP_VERDICT: ADAPT (2026-08-10)

Adopt over the body: several claims were overstated — core approval/timeout features
mis-attributed to HarnessAgent; our idempotency substrate treated as absent (it exists);
provider paths do not "discard" envelopes they never request; the harness sandbox and our
confinement are NOT architectural equivalents; the nonce fence is prompt-injection FRICTION,
not a cryptographic boundary; the 7 advertised handles are not the whole registered tool set.
"Import nothing" is complacent — import CONTRACTS, lifecycle semantics, and adversarial tests
without the Vercel-dependent runtime. Key additions: the genuine OS/network sandbox gap is the
sweep's biggest lesson; harness `permissionMode` defaults to allow-all (scrutinize defaults);
harness's versioned opaque RESUME STATE deserves top-rank; usage needs a PER-PROVIDER-CALL
ledger with ALLOWLISTED fields (envelopes may carry session/identity metadata — never persist
raw), not just runs.token_count; typed outputs need a stable versioned success/error union
first; we need a native HIERARCHICAL DEADLINE spanning subprocess/retries/tools/cancellation;
the tool-fingerprint baseline must come from an independently reviewed artifact. The note is
research input — every substantive item still needs its own OpenSpec change; split the MCP
progress vs output-schema proposals.
