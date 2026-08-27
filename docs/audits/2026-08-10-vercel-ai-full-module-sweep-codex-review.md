# Vercel AI v7 Full-Module Sweep — Opposite-Provider Review

**Date:** 2026-08-10  
**Reviewer:** Codex (opposite-provider review of Claude-authored note)  
**Reviewed note:** `docs/design-notes/2026-08-10-vercel-ai-full-module-sweep.md`  
**TinyAssets baseline:** `origin/main` at `7b451b2c98abb9b411d35b32def96a319d721594`  
**Upstream baseline:** `vercel/ai` at `74556f7946cdf50aa41c01c5d5b3bd2b733acc86`; npm `ai@7.0.59`, `@ai-sdk/harness@1.0.65`, Claude/Codex harness adapters `1.0.67`  
**Overall verdict:** ADAPT

The sweep found useful mechanisms and the top five point in broadly productive
directions. It does not pass unchanged: it attributes AI SDK Core timeout and
approval-signing features to `HarnessAgent`, treats an existing TinyAssets
idempotency substrate as absent, overstates what the normal CLI provider paths
already receive and discard, and understates the isolation gap between a real
sandbox provider and TinyAssets' current in-process confinement.

## 1. Fact review — ADAPT

| Claim | Verdict | One-line review |
|---|---|---|
| HarnessAgent runs Claude Code and Codex in sandboxed subprocess runtimes | **APPROVE WITH PRECISION** | The host starts a Node bridge inside a required sandbox; the bridge uses the Anthropic Agent SDK or Codex SDK to drive the agent runtime. This is real sandbox execution, not merely TinyAssets-style cwd pinning. |
| Host-injected tools | **APPROVE WITH CAVEAT** | Host-defined tools cross the bridge and execute on the host; adapter built-ins execute inside the harness. Codex currently rejects built-in permission modes other than `allow-all`, so this is not a blanket least-privilege claim. |
| Session detach/resume | **APPROVE** | Detach, stop, destroy, opaque state export, cross-process resume, replay, and Codex attach/rerun fallback paths are present in current source. |
| Suspended-turn continuation | **APPROVE** | `suspendTurn` plus `continueStream`/`continueGenerate` persist a continuation cursor and resume a pending turn. |
| HMAC-signed approvals are a HarnessAgent capability | **REJECT** | Optional `experimental_toolApprovalSecret` HMAC-SHA256 signing belongs to AI SDK Core `generateText`/`streamText`; HarnessAgent exposes tool approval but not that secret setting. The sweep conflates layers. |
| HarnessAgent has four-way timeout budgets | **REJECT** | AI SDK Core currently exposes total, step, first-chunk, inter-chunk, tool, and per-tool budgets. HarnessAgent passes only its `AbortSignal` into its adapter path, not Core's timeout object. |
| `runs.token_count` is dead | **APPROVE** | The column and update parameter exist, but no current caller supplies a token count. |
| Usage/cost already sits in CLI JSON envelopes TinyAssets discards | **ADAPT** | Both installed CLIs can emit usage. Only Claude's separate JSON helper currently requests an envelope and discards all but `result`; normal Claude and Codex hot paths request plain output, so they do not already receive those envelopes. |
| TinyAssets has zero streaming | **ADAPT** | There is no incremental model/tool-result streaming or MCP progress notification on the user path; providers buffer with `communicate()`. “No streaming anywhere” is too broad because the transport can use SSE and legacy run-event polling exists. |
| TinyAssets has no MCP progress | **APPROVE** | `universe_server.py` emits no progress-token or `notifications/progress` messages; `converse` blocks to one final JSON result. |
| Every registered tool has `output_schema=None` | **APPROVE** | The shared registration wrapper sets `output_schema=None`. The seven are the advertised canonical handles, not the total number of internally registered compatibility tools. |

Current Harness sources: [agent](https://github.com/vercel/ai/blob/74556f7946cdf50aa41c01c5d5b3bd2b733acc86/packages/harness/src/agent/harness-agent.ts),
[session](https://github.com/vercel/ai/blob/74556f7946cdf50aa41c01c5d5b3bd2b733acc86/packages/harness/src/agent/harness-agent-session.ts),
[settings](https://github.com/vercel/ai/blob/74556f7946cdf50aa41c01c5d5b3bd2b733acc86/packages/harness/src/agent/harness-agent-settings.ts),
[Core timeout configuration](https://github.com/vercel/ai/blob/74556f7946cdf50aa41c01c5d5b3bd2b733acc86/packages/ai/src/prompt/request-options.ts), and
[approval signing](https://github.com/vercel/ai/blob/74556f7946cdf50aa41c01c5d5b3bd2b733acc86/packages/ai/src/generate-text/tool-approval-signature.ts).
Vercel's [Harness announcement](https://vercel.com/changelog/program-agent-harnesses-with-ai-sdk)
also confirms the sandbox/provider/tool/skill model, although its release label is
staler than the npm registry's current stable tags.

Fresh runtime evidence, Windows 2026-08-10: Claude Code `2.1.225` with
`-p --output-format json` returned `usage`, `modelUsage`, and `total_cost_usd`;
Codex CLI `0.146.0` with `exec --json` returned final input, cached-input,
cache-write-input, output, and reasoning-output token fields.

### TinyAssets code corrections

- `runs.model` is **not** dead: provider call metadata is tracked and completion
  writes the model on normal and resumed paths. `_ROUTING_EVIDENCE_CAVEAT` is stale
  where it says the model is not collected.
- `ProviderResponse` and router `_call_meta` have no usage shape. Correct capture
  requires changing invocation modes, parsers, provider-call evidence, and run
  aggregation—not merely assigning the existing column.
- `recover_in_flight_runs` still contains a stale “mid-run resume unavailable”
  docstring, while interrupted checkpoint resume now exists. Ordinary failed runs
  remain terminal and cannot use `resume_run`.

## 2. Top-five implications

| Rank | Verdict | Effort / payoff | One-line decision |
|---|---|---|---|
| 1. Populate usage/cost | **ADAPT** | **Medium / high** | Capture allowlisted per-call input/output/cache/reasoning usage, model, CLI version, and aggregation evidence; do not reduce it to one `token_count`, and do not treat subscription CLI estimates as settled monetary cost. |
| 2. Durable retry + idempotency | **ADAPT** | **High / very high** | Add typed transient-failure classification, attempt state, single-flight/lease and branch-version fences; retry only pure nodes or effectors already proven replay-safe. Checkpoints alone do not make failed runs resumable or effects safe. |
| 3. MCP progress + typed outputs | **ADAPT; SPLIT** | **Medium-high / high for schemas, conditional for progress** | Version typed output envelopes handle by handle; separately prove real Claude.ai/ChatGPT progress rendering before restructuring synchronous provider execution. One combined change hides two independent risks. |
| 4. Approval hardening pack | **ADAPT / DEFER TO ITS EXISTING LANE** | **Medium-high / conditional high** | Persist canonical request digest, actor, nonce, single-use state, and effect outcome server-side. Add HMAC only if an approval token must make an untrusted round trip; do not import the SDK's optional mechanism as the trust root. |
| 5. Tool-surface fingerprint canary | **ADAPT** | **Low-medium / medium** | Hash canonical semantic fields from a trusted catalog/build artifact, including output schema and annotations once defined. This detects release drift; a server hashing its own live description is not the SDK client's anti-rug-pull boundary. |

The second proposal's premise needs a direct correction. Current main already has
`tinyassets/idempotency.py`, replay-safe outbound execution, effect identities,
digests, reconciliation, and receipts across GitHub, wiki, Twitter, Windows, and
payment/execution paths. The missing work is to make retry policy consume those
capabilities and to close unkeyed sinks, not to invent idempotency from scratch.
“Zero new storage” is also unjustified: safe retry needs durable attempt/classification
and concurrency state even though the checkpoint database already exists.

For rank 3, declaring output schemas is the stronger near-term contract improvement.
The seven coarse handles return polymorphic action-specific success and error shapes,
so schema normalization/versioning must precede a blanket declaration. MCP progress
is useful only if the clients render it or TinyAssets owns a client that does; the
current synchronous `converse` path and buffered CLI adapters make it a real runtime
change, not a notification-only patch.

## 3. “We are ahead; import nothing” review — ADAPT

| Area | Verdict | One-line review |
|---|---|---|
| Evals | **ADAPT** | TinyAssets has richer product evaluation primitives than AI SDK Core, but writer=Claude/judge=Codex is fallback-chain preference, not invariant enforcement under pins, allowlists, availability, or fallback. Do not conflate the deterministic `judge_run` surface with the separate editorial evaluator. |
| Canaries | **ADAPT** | Outside-in product canaries are genuinely ours and should stay ours; comparing an operations platform to a model SDK is category-skewed, and a names-only tool probe plus a current production outage concern argues against complacency. |
| `evidence_caveats` | **APPROVE THE PATTERN; FIX FRESHNESS** | Structured caveats are a stronger self-auditing contract, but the stale “model not collected” claim demonstrates that caveats themselves require executable freshness checks. |
| Nonce-fenced memory | **ADAPT THE SECURITY CLAIM** | Keep the random, absent-from-content delimiter and untrusted-memory framing. It is useful prompt-injection friction, not a cryptographic security boundary; the model can still disregard prompt instructions. |

The overall “KEEP-OURS” decision is fair as an anti-vendoring rule. “Import nothing”
is too absolute: import contract ideas and adversarial test cases, then implement
them in TinyAssets-native primitives. Most importantly, do not let relative strength
in evals or canaries obscure a weaker runtime isolation boundary.

## 4. Material misrepresentations

1. **Feature-layer conflation:** HMAC approvals and multi-axis Core timeouts are not
   current HarnessAgent capabilities.
2. **Sandbox equivalence:** “HarnessAgent validates our shape” is directionally true
   only at the subprocess/workspace level. Harness requires a sandbox provider with
   network-policy machinery; current TinyAssets `converse` has cwd pinning, a tool
   allowlist/denylist, and in-process confinement, not OS isolation.
3. **Idempotency absence:** current TinyAssets has a substantial effect-identity,
   dedupe, reconciliation, and receipt substrate.
4. **Envelope availability:** CLI JSON usage is available on request, but the normal
   provider hot paths do not currently request it.
5. **Cross-family enforcement:** provider chain order is a preference, not proof that
   every writer/judge pair uses different families.
6. **Cryptographic memory fence:** a random delimiter is not an enforcement boundary.
7. **No-streaming absolute:** the true gap is incremental LLM/tool output and MCP
   progress, not the absence of every SSE/polling mechanism in the stack.
8. **Seven registered tools:** seven are advertised canonically; compatibility tools
   can remain registered but hidden.

## 5. Missed items that matter

1. **The actual sandbox gap is the largest lesson.** Harness's required sandbox
   handle, bridge placement, filesystem lifecycle, and egress controls are stronger
   than TinyAssets' live boundary. Adapt the contract to the existing Engine OS
   sandbox lane; do not vendor a Vercel-dependent runtime into a goal-agnostic OSS
   engine.
2. **Harness defaults need threat review.** Default `permissionMode` is `allow-all`,
   and the Codex adapter does not support the built-in approval modes. Harness is not
   automatically a security exemplar merely because it runs in a sandbox.
3. **Session lifecycle is under-ranked.** Opaque, versioned resume state, explicit
   detach/stop/destroy, cursor validation, and replay/rerun fallbacks are more relevant
   to durable `converse` than the note's broad architecture-validation claim.
4. **Usage needs a ledger, not a scalar.** Provider calls need input, cached input,
   cache-write input, output, reasoning output, provider/model/CLI version, provenance,
   aggregation rules, and missing-data caveats. Paid-market settlement must remain
   separate from subscription-capacity accounting.
5. **Persist only allowlisted envelope fields.** Full CLI envelopes may carry session
   identifiers and other metadata; usage capture should not become an accidental
   transcript/identity telemetry channel.
6. **Output schemas require error normalization.** The action-dispatch handles need a
   stable versioned success/error union before a useful `outputSchema` can be promised.
7. **Timeout design remains unsolved.** TinyAssets' single provider budget plus writer
   retry backoffs can exceed the intended turn budget, but HarnessAgent does not supply
   the proposed solution. Define a TinyAssets-native hierarchical deadline propagated
   through subprocesses, retries, tools, and graph/run cancellation.
8. **Fingerprint trust placement matters.** SDK client fingerprinting compares a
   trusted earlier definition to a later one. A public canary should compare live
   output against an independently generated, reviewed release contract—not a digest
   recomputed from the same server serialization.

## Gate decision

The research note is suitable as **ADAPT** input after the corrections above. It
should not directly authorize implementation. Each substantive item still needs an
OpenSpec change, and the progress/output-schema bundle should be split before sizing.

VERCEL_SWEEP_VERDICT: ADAPT
