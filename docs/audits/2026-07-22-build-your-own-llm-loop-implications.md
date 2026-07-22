# Build Your Own LLM Loop: Tinker, Karpathy, and TinyAssets

Date: 2026-07-22

Initial provider: Codex (`codex-gpt5-desktop-llm-loop`)

Required reviewer: Claude

Review posture: host-authorized pre-user testing proceeds before Claude review;
Claude reviews the accumulated current build on Friday.

Scheduling note: on 2026-07-22 the host reported Claude rate-limited until
Friday evening, 2026-07-24, and explicitly authorized multiple testing
iterations before that review because no real users are at risk yet. This is a
lane-specific host override; the Friday review evaluates the then-current build.

## Executive judgment

TinyAssets should not add a platform-level "LLM builder" feature. The useful
product is a user-owned, remixable workflow graph that composes the existing
Node/Edge/State/Run substrate with the already-specified training market, data
commons, gates, provenance, and capability minting.

The best synthesis is:

- borrow Tinker's separation between a locally authored training loop and
  remotely managed GPU execution;
- borrow Karpathy's legible, end-to-end learning ladder, single complexity dial,
  fast experimental scale, and explicit capability metric;
- use TinyAssets for the durable experiment graph, independent evaluation,
  provenance, budget/market routing, checkpoint evidence, community remix, and
  long-running iteration.

The current platform cannot honestly promise paid training compute yet.
`paid-market-economy` says the money path is default-off and the pure market
library has no live money-moving MCP transport. The first workflow therefore
ends its market path at a readiness/quote/reservation gate until the existing
Track E transport lane ships. It may still route to the user's own compute or a
separately authorized provider such as Tinker.

## Source freshness stamp

Verified 2026-07-22 from primary sources:

| Source | Canonical reference | Version / license | Relevant evidence |
|---|---|---|---|
| Tinker | [Official documentation](https://tinker-docs.thinkingmachines.ai/) | Live docs, accessed 2026-07-22 | Users write loops locally while Tinker handles remote GPU clusters; advertised algorithms include SFT, RL, DPO, and distillation. |
| Tinker Cookbook | [Official repository](https://github.com/thinking-machines-lab/tinker-cookbook) | HEAD `3e04119ce293a2b6ba5284e35267c9ba6d27c5da`; Apache-2.0 | Exposes small training primitives (`forward_backward`, `optim_step`, checkpoint save/load) plus recipes and weight export. |
| nanochat | [Official repository](https://github.com/karpathy/nanochat) | HEAD `92d63d4e8bb4df75c3b71618f31ddde2378b2bcd`; MIT | Cohesive tokenizer-to-chat pipeline, quick experiment sizes, a single `depth` dial, and "time to GPT-2" as the optimization target. |
| build-nanogpt | [Official repository](https://github.com/karpathy/build-nanogpt) | HEAD `6104ab1b53920f6e2159749676073ff7d815c1fa`; MIT | Stepwise empty-file-to-GPT-2 reproduction; explicitly covers pretraining, not chat fine-tuning. |
| Zero to Hero | [Official course page](https://karpathy.ai/zero-to-hero.html) | Live course page, accessed 2026-07-22 | Pedagogical ladder from backpropagation and simple language models through GPT and tokenizer construction. |

Cost statements in the Karpathy repos are project claims tied to their stated
hardware assumptions, not current TinyAssets market quotes. They must never be
shown to users as guaranteed prices.

## Outside-system maps

### Tinker

| Dimension | Shape |
|---|---|
| User surface | Python SDK, cookbook recipes, tutorials, and API console. |
| Execution loop | User owns algorithm/control flow; remote service performs distributed training. |
| State | Training client plus named saved states/checkpoints; weights can be exported. |
| Evaluation | User/cookbook-defined evaluation and reward logic; examples include verifiable code/math rewards. |
| Compute | Managed remote GPU clusters behind an API. |
| Model scope | Strongest fit is post-training existing supported models; the public headline is LoRA fine-tuning, not ground-up pretraining. |
| Provenance/privacy | Data and algorithm control remain with the user at the API boundary, but the service still receives training requests/data; TinyAssets must not imply local-only privacy. |
| Operational gap for TinyAssets | Tinker is one possible executor/provider, not the durable goal, graph, market, ownership, or commons layer. |

### Karpathy's ground-up path

| Dimension | `build-nanogpt` | `nanochat` |
|---|---|---|
| Entry point | Stepwise lecture/commit history. | One cohesive experimental harness. |
| Scope | GPT-2-style pretraining only. | Tokenization, pretraining, midtraining/post-training, evaluation, inference, chat. |
| Core loop | Implement, train, compare loss/eval, improve. | Change a candidate, run a small depth, compare metrics, then scale. |
| Primary metric | Reproduce GPT-2 behavior/capability. | Wall-clock "time to GPT-2" plus loss, CORE score, throughput, MFU, VRAM. |
| Complexity control | Explicit code and model configuration. | One user-facing `depth` dial derives most other hyperparameters. |
| Compute posture | Cloud GPU assumed for the full reproduction. | Small CPU/MPS path for learning; full target uses a multi-GPU node. |
| Artifact | Readable training code and checkpoint. | Full model plus chat surface and research leaderboard. |

The key lesson is not to copy either repository. It is to make the experimental
loop legible: small run first, one bounded hypothesis, independent evidence,
checkpoint, compare, then deliberately spend more compute.

## TinyAssets comparison

| Outside concept | Existing TinyAssets primitive / spec | Assessment |
|---|---|---|
| Local loop, remote GPUs | Node/Edge/State/Run plus `paid-market-training` F1/F2 | Native composition; transport is not live yet. |
| Training step primitives | Ordinary nodes with declared inputs/outputs and checkpoint artifacts | No new MCP verb is justified. |
| Saved training state | Checkpointed runs plus training checkpoint hashes/attestations | Stronger provenance shape than a provider-local checkpoint alone. |
| One complexity dial | User-owned State field such as `depth`, interpreted by workflow nodes | Commons pattern, not platform schema. |
| "Time to GPT-2" | Goal gate with held-out metric and cost/time evidence | Native Goals & Gates composition. |
| Remote cost selection | Track E spot/forward quote plus F1/F2 training instruments | Specified, not yet live; fail closed. |
| Dataset preparation | `data-commons` manifest, license lattice, dedup, contamination gate | Already stronger and more explicit. |
| Training ownership | Capability minting plus `pooled-training-ownership` | Already specified; no secondary share transfer in v1. |
| Continuous improvement | Branch remix, evaluator evidence, lineage, standing goals | TinyAssets' main advantage over a one-off script. |
| Chat surface | Seven canonical live MCP handles through an installed connector | Suitable for conversational composition and steering. |

Relevant architecture reviewed: PLAN.md Scoping Rules; Engine & Domains; Daemon
Platform; Goals & Gates; Evolution & Evaluation; API & MCP Interface; Harness &
Coordination. Relevant OpenSpec capabilities reviewed:

- `openspec/specs/paid-market-training/spec.md`
- `openspec/specs/paid-market-price-index-and-forwards/spec.md`
- `openspec/specs/paid-market-economy/spec.md`
- `openspec/specs/data-commons/spec.md`
- `openspec/specs/pooled-training-ownership/spec.md`
- `openspec/specs/demand-side/spec.md`
- `openspec/specs/graph-execution-substrate/spec.md`
- `openspec/specs/evaluation-outcomes-and-attribution/spec.md`
- `openspec/specs/live-mcp-connector-surface/spec.md`

## TinyAssets-native workflow blueprint

### Standing goal

"Create the smallest model I fully understand, then improve it through
evidence-backed experiments until it reaches my chosen capability and budget
gate."

The user chooses one of two honest tracks in the same branch:

1. **Learning track:** micrograd/makemore-sized experiments, tiny transformer,
   tokenizer, and a small chat-capable model on owned/local compute.
2. **Capability track:** nanochat-style pretraining and post-training with
   rented or contributed compute, only after dataset, license, budget, and
   market-readiness gates pass.

### Graph

1. `define_goal_and_metric` — record learning objective, target capability,
   maximum spend, privacy constraints, and stop conditions.
2. `build_curriculum_baseline` — select the smallest runnable baseline and
   produce an explanation artifact for every major component.
3. `create_data_manifest` — identify data, hash it, record provenance/license,
   deduplicate, and check benchmark contamination.
4. `choose_complexity_dial` — set `depth` (or an equally legible scalar) and
   derive the detailed configuration in an artifact.
5. `select_compute_route` — rank owned compute, an explicitly authorized
   training API, and the TinyAssets market when live; never silently substitute.
6. `implement_candidate` — produce versioned tokenizer/model/train code or a
   post-training recipe.
7. `smoke_train` — run the cheapest diagnostic scale and emit checkpoint,
   logs, cost, throughput, and failure evidence.
8. `evaluate_candidate` — use held-out loss plus capability-specific gates;
   evaluator is separate from candidate generation.
9. `diagnose_and_propose_one_change` — turn the evidence into one bounded
   hypothesis and a new branch version.
10. `scale_decision` — stop, repeat cheaply, or reserve more compute only when
    the expected evidence gain justifies it.
11. `full_train_and_attest` — checkpoint-hash chain, loss continuity, sampled
    re-execution, and held-out probes; disabled until an executor is available.
12. `post_train_for_chat` — SFT/preference/RL stage when the goal is a chat
    model; ground-up GPT pretraining alone is not mislabeled as ChatGPT.
13. `mint_and_release_capability` — weights URI/hash, base, provenance, license,
    eval evidence, chat demo, and ownership terms.
14. `collect_use_feedback` — convert clean-use evidence and failures into new
    data/eval candidates, then return to manifest review.

### Loops

```text
cheap experiment:
  candidate -> smoke train -> evaluate -> diagnose one change -> candidate

scaling:
  evaluate -> scale decision -> quote/reserve compute -> full train -> evaluate

lifecycle:
  release -> clean-use/failure evidence -> data/eval review -> post-train -> release
```

Every loop has an explicit budget and stop condition. No loop can spend, train,
or publish merely because the previous node completed.

## Adopt / adapt / avoid / defer / watch

### Adopt

- Legible end-to-end progression from fundamentals to a chat-capable model.
- Cheap diagnostic runs before expensive scale.
- One primary complexity dial and one clearly named capability target.
- Checkpoint/save/resume as first-class loop operations.

### Adapt

- Tinker's remote-execution seam becomes a provider-neutral compute-route node;
  Tinker may be one explicitly authorized executor.
- Karpathy's leaderboard metric becomes a user-owned Goal/gate, not a global
  platform ranking formula.
- Training recipes become remixable branches carrying provenance and evidence.

### Avoid

- A new `build_llm` MCP action or hard-coded LLM domain topology.
- Treating provider-reported training completion as verified ground truth.
- Publishing raw user training data or traces to the commons by default.
- Calling a pretrained base plus LoRA "from scratch."
- Promising current GPU prices from repository examples.

### Defer

- Live TinyAssets-paid training execution until Track E transport, F1
  instrument wiring, identity hardening, and cross-client proof are live.
- F3 swarm pretraining until its separate research and verification gate passes.
- Fractional share transfer and secondary markets pending legal review.

### Watch

- Whether Tinker expands from post-training into a suitable pretraining
  executor.
- Whether nanochat's depth-derived compute-optimal settings remain robust across
  datasets, hardware, and model-family changes.
- Whether real users prefer education-first branches or immediately start from
  an existing open base model.

## Roadmap

### Slice 0 — now, host-authorized pre-review testing

Create one user-owned branch through the live connector containing the goal,
graph, gates, budgets, and market-readiness stop. Do not purchase compute. Run
only a planning/validation pass if the live surface supports it without paid
effects.

Exit evidence: rendered chatbot conversation, connector tool use, visible branch
summary, and the trace/session log.

### Slice 1 — commons archetype

After the live composition is useful, publish the branch definition and rubric
as a remixable commons archetype. Keep user datasets, credentials, checkpoints,
and private traces on an authorized host.

### Slice 2 — owned/Tinker execution adapter as user composition

Attach an ordinary external execution node for the user's own compute or an
explicitly authorized Tinker account. The node emits checkpoint/provenance
artifacts into the same graph contract. This is not a privileged platform
integration unless repeated composition proves a structural gap.

### Slice 3 — TinyAssets market route

When existing Track E/F work is live, let `select_compute_route` consume real
quotes, reserve an F1/F2 window, stream checkpoint settlement, and mint the
capability. This lane depends on those existing market specs; it does not fork a
parallel market design.

## Cross-provider Friday review

Claude will independently re-check the primary sources, listed TinyAssets specs,
and accumulated UI-test evidence on Friday, then leave
`docs/audits/2026-07-22-build-your-own-llm-loop-claude-review.md` with one verdict:
`approve`, `adapt`, `defer`, or `reject`.

Host decision 2026-07-22: pre-user live workflow creation and testing may proceed
before that verdict. Do not expose real users, move money, buy compute, publish
private data, or claim cross-provider acceptance. A Friday `adapt` verdict must
enumerate corrections against the current tested build.

## Pickup packet

- Concept: user-owned build-your-own-LLM experiment loop.
- Initial provider: Codex.
- Required reviewer: Claude.
- Affected domains: graph composition, training compute, data commons,
  evaluation, market routing, capability minting.
- Applies when touching: Track E/F transport, external training executors,
  training archetypes, dataset manifests, model ownership, connector onboarding.
- Next home: `STATUS.md` research/UI lane plus Claude review lane.
- Exact next action: Claude verdict, then one live connector composition mission.
- Write boundary: this artifact, Claude review artifact, and `output/` UI logs.
- Blocker: opposite-provider verdict.
- Exit check: rendered connector conversation creates a faithful graph while
  plainly stating that TinyAssets-paid training is not yet live.
- Platform code: none proposed.

## Worktree landing packet

- Branch: `codex/own-llm-training-loop`.
- Worktree: `C:\Users\Jonathan\Projects\wf-own-llm-training-loop`.
- Base: `origin/main` at `de64fe57` when created.
- Review dependency:
  `docs/audits/2026-07-22-build-your-own-llm-loop-claude-review.md`.
- Current write set: `STATUS.md`, `.agents/worktrees.md`, this artifact, and
  `output/{mcp_test_plan.md,user_sim_session.md,claude_chat_trace.md}`.
- First independent slice: research artifact and review verdict.
- Live slice: one branch creation/inspection/optional no-cost run through the
  installed connector.
- Verification: `git diff --check`, source freshness, review verdict, ui-test
  preflight, rendered transcript, and no paid-effect call.
- Publish route: keep as a draft/research branch until the host chooses to land
  the artifact; no platform implementation PR is necessary from this finding.
- Fold-back: remove the two STATUS rows when the artifact/review and UI mission
  are complete; carry any actual market gap into the existing Track E/F lane.

## Open questions and verification gaps

- Can the live chatbot reliably compose this 14-node graph through the seven
  coarse handles without exposing internal action vocabulary?
- Does the current branch builder preserve explicit cycles with exits, or will
  the chatbot need to represent each experiment as a versioned acyclic run plus
  a standing-goal trigger?
- Can a browser-only user inspect budget, license, and market-readiness gates in
  ordinary language?
- There is no post-fix clean-use evidence because no fix is proposed. The UI
  mission will test an existing public composition surface, not validate the
  not-yet-live training market.
