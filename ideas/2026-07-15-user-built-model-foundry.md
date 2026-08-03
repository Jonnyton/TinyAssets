# User-Built Model Foundry: Arbitrary Algorithms on Open Compute

**Captured:** 2026-07-15  
**Source:** host design conversation  
**Status:** host-approved platform principle and hard `$0` MVP constraint;
resource-gated scale design under review  
**Implementation authority:** none until a specification is approved  
**PLAN foldback:** required after the active `PLAN.md` write claim clears  
**Research review gate:** a Claude-family reviewer must independently re-check
pricing, sources, safety boundaries, and TinyAssets composition before build  
**Parent:** `ideas/2026-07-15-democratized-compute-stack.md`

## Host Direction

Full-stack democratization includes the right for a user to create model
algorithms and train them, not merely select or fine-tune a platform-approved
model. A user proposing a genuinely new language model, world model, learning
algorithm, or possible AGI architecture should be able to express and pursue
that research through their chatbot. The Branch may obtain market quotes, but
its effective Universe/Goal/run spending cap controls execution. It may also
request below-market or zero-reward contributions from compute hosts who choose
to support open-source group work.

## Core Principle

TinyAssets is an **algorithm-agnostic research and resource orchestration
substrate**, not a model menu or AutoML wizard.

The platform may provide reusable Branches for Transformers, state-space
models, diffusion, reinforcement learning, simulators, multimodal world models,
and known training stacks, but none is privileged in the core schema. A user
may supply arbitrary source, containers, compilers, data pipelines, training
loops, state representations, objectives, evaluators, and distributed runtime
adapters.

If lawful resources and capability adapters are available, the user's budget
and authorization—not a hard-coded architecture or parameter ceiling—bound the
experiment. The platform does not promise scientific success, AGI, unrestricted
hardware access, or availability of every resource. It promises not to make
known model families the ceiling of what users can attempt.

## What “Theoretically Build It” Must Mean

A future architecture that does not exist today is supportable when its Branch
can define:

- editable source and build environment;
- datasets, simulators, environments, licenses, and provenance;
- resource requirements for CPU, GPU, TPU/accelerator, RAM, storage, network,
  power, duration, region, and confidentiality;
- single-node or distributed launch and shutdown contracts;
- checkpoints, resume/migration behavior, and preemption policy;
- telemetry, loss/health signals, experiment comparisons, and stop-loss gates;
- independent evaluators and real-world outcome gates;
- budget envelopes and explicit approvals at irreversible spend boundaries;
- secrets, access control, sandboxing, and artifact publication policy;
- attribution and ancestry for algorithms, code, data, weights, and hardware.

TinyAssets then composes capability providers: rented clusters, user machines,
data vendors, simulation services, human researchers, evaluators, and later
user-designed accelerators. The Branch remains portable even when one provider
cannot satisfy its resource contract.

## Platform Capability Stack

1. **Conversational research specification:** the chatbot turns the user's
   hypothesis into architecture, experiment, evaluator, resource, budget, and
   stop conditions without narrowing it to known model templates.
2. **Executable arbitrary code:** versioned source/container artifacts and
   generic external-tool nodes run user research code under declared authority.
3. **Open resource acquisition:** resource requests receive provider/vendor
   bids with price, capacity, topology, timing, data-egress, and interruption
   terms. The same request may invite below-market or zero-reward contributed
   capacity under explicit license, attribution, privacy, and result-access
   terms.
4. **Pilot and scaling estimator:** compile test, one-device smoke test, short
   scaling sweep, throughput/memory profiling, and a cost confidence interval
   precede the full authorization.
5. **Checkpointed execution:** long jobs resume across interruption, preserve
   raw logs, and cannot silently restart spending from zero.
6. **Independent evaluation:** candidate-generating jobs cannot rewrite locked
   tests or promote their own claims.
7. **Lineage and remix:** every architecture, dataset recipe, checkpoint,
   evaluator, optimization, and result is independently forkable under its
   actual license.
8. **Outcome truth:** a failed new architecture is still a valuable, searchable
   result; only measured gates justify stronger claims.

## Proof Ladder

| Claim level | What the user creates | Minimum evidence |
|---|---|---|
| Composed | prompts, retrieval, tools around an inherited model | reproducible run + eval |
| Adapted | user/daemon data, fine-tuning, quantization, evaluator | new weights/adapter + lineage + held-out eval |
| Trained from scratch | architecture/training code and weights initialized from random state | data receipt + checkpoints + full training/eval receipt |
| Algorithmically novel | material change to model/state/objective/learning algorithm | ablations against locked baselines |
| Distributed original research | novel system trained across paid, donated, or owned cluster resources | scaling, failure recovery, budget/contribution, and reproducibility evidence |
| Frontier/world-model pursuit | open-ended research program using any lawful market resources | honest milestone ladder; no AGI claim without external outcome evidence |

Claims never collapse. A fine-tune is not “trained from scratch”; a new
attention layer is not automatically a new learning paradigm; a large spend is
not evidence of intelligence.

## Current Market-Compute Cost Envelope

**These costs are not the MVP budget.** They remain the future resource ladder
that TinyAssets must be able to estimate, authorize, and execute when a user can
fund it.

These are order-of-magnitude planning ranges in USD as of 2026-07-15, not
quotes. Current self-service listings put A100-class GPUs around
`$1.39–$2.79/GPU-hour` and H100-class GPUs around
`$2.89–$4.19/GPU-hour`. Storage, CPU/RAM, networking, cluster premiums, failed
runs, data, evaluations, and labor are additional.

| Project | Raw final-run compute | Realistic research program |
|---|---:|---:|
| Cookbook LoRA/PEFT adaptation of an open 1B–7B model | roughly $20–$500 | roughly $500–$10,000 |
| Full/domain continued training of an inherited compact model | roughly $500–$20,000 | roughly $5,000–$100,000 |
| New 50M–300M architecture trained from random initialization | roughly $500–$10,000 | roughly $5,000–$100,000 |
| Strong approximately 1B base model from scratch | roughly $50,000–$100,000 empirical floor | roughly $100,000–$500,000 |
| Llama-2-scale 7B final pretraining run | roughly $256,000–$514,000 at current A100 listings | roughly $1M–$5M with experiments/data/evals |
| Llama-2-scale 70B final pretraining run | roughly $2.4M–$4.8M at current A100 listings | roughly $10M–$50M with experiments/data/evals |
| Frontier/novel AGI or world-model program | not credibly fixed in advance | tens/hundreds of millions; potentially $1B+ |

Why the 1B floor is not a guess: TinyLlama's published training plan used 16
A100 GPUs for 90 days to train 1.1B parameters on 3T tokens—34,560 GPU-hours,
or about `$48,000–$96,000` at current listed A100 rates. Llama 2 reported
184,320 A100-80GB GPU-hours for 7B and 1,720,320 for 70B; multiplying by today's
listed A100 rates gives the final-run ranges above.

The program column is the number to budget. Novel model work requires failed
runs, ablations, data cleaning/licensing, evaluation, checkpoint storage, and
specialist review. A single successful run understates the cost of discovering
the configuration that deserves that run.

## Recommended First Proof: Two Independent Tracks

**Host budget reframe, 2026-07-15:** none of the rented-training or custom-
hardware ranges are currently affordable. The MVP must require no new purchase
and must not imply that dry-run resource plans are completed physical work.

Prove product value and algorithmic openness separately using only hardware,
software, accounts, and lawful data already available to the user:

### Track A — Cookbook experience simulator

Through the real connector conversation, create the recipe schema, coaching
behavior, dual-screen interface, timers, substitutions, and evaluation flow.
Run the two “pages” as a split-screen browser application or two windows on an
existing computer, using its microphone and speakers. Complete real cook
sessions and a downstream software/recipe remix. This proves the user journey
and Branch composition but makes **no custom-device or physical-stack claim**.

### Track B — Model-foundry proof

From the same chatbot surface, a user defines a small original architecture or
meaningful learning-algorithm variant, initializes it from random weights,
trains it on licensed or synthetic data using an already-owned CPU/GPU, resumes
from a forced interruption, runs locked baselines/ablations, and publishes the
complete lineage. Start around 1M–20M parameters and shrink further if that is
what the available machine can complete. It need not outperform established
models or power the cookbook to count; negative results remain honest and
reusable.

Track B must also produce, but not purchase, a market-resource manifest for a
larger run. That dry run proves the Branch can describe GPUs, storage,
networking, checkpoints, budget, and provider bids; it does not prove rented
execution until a funded or contributed descendant actually runs it. The
request may be published with a `$0`, below-market, or market-rate maximum
reward. Quotes above the effective spending cap remain visible as the exact
resource shortfall but cannot start work.

After both tracks pass, resource-available descendants climb explicit gates:

1. low-cost rented accelerator canary;
2. 50M–300M from-scratch run;
3. adapted model on a purchased cookbook compute module;
4. custom carrier PCB and two-screen enclosure;
5. larger 1B/7B/world-model, accelerator, chip, and lithography Branches.

Every rung reuses the same source/resource/checkpoint/evaluator/lineage
contracts rather than requiring a different platform. Capacity may be paid,
donated, sponsored, reciprocally shared, or supplied by a future user-owned
machine; the execution and evidence contract remains the same.

## Scale-Ready at Zero Spend

**How might TinyAssets prove that an ambitious model Branch can traverse the
real end-to-end execution path while spending `$0`, without mislabeling an
unexecuted large run as scale-proven?**

Three directions were considered:

| Direction | Strength | Fatal weakness |
|---|---|---|
| Quote-only | cheapest way to expose realistic costs | proves procurement planning, not distributed execution |
| Volunteer-only | can produce real external execution for `$0` | arrival, topology, reliability, and timing are unpredictable |
| **Resource-gated hybrid — recommended** | proves the runner at small scale, quotes the target scale, and can accept voluntary capacity without redesign | needs strong sandboxing, verification, and truthful state labels |

The recommended Branch moves through explicit states:

`specified -> local canary passed -> multi-worker canary passed -> quoted ->
resource blocked -> partially contributed -> distributed canary passed ->
authorized -> running -> evaluated`

For MVP-0, the **multi-worker canary** may use multiple isolated workers on one
owned computer. It must exercise the same job manifest, shard assignment,
heartbeat, checkpoint, forced worker loss, resume, artifact merge, and evaluator
interfaces intended for a large run. It proves the scheduler and recovery path
at zero spend, not multi-host networking or target cluster scale. A
**distributed canary** requires at least two independently administered hosts
already available or voluntarily contributed; it is recorded only if those
hosts actually execute.

The unlaunched target run still has a complete, machine-readable **resource
envelope**:

- immutable source/container, data, evaluator, topology, checkpoint, and stop
  manifests;
- minimum/target compute, memory, storage, network, duration, and geographic or
  data-governance constraints;
- timestamped comparable quotes with low/expected/high totals;
- Universe, Goal, and run caps, with the lowest applicable cap enforced;
- exact resource and cash shortfalls;
- a public contribution listing whose maximum reward may be `$0`, below market,
  or market rate; and
- declared licenses, attribution, result access, acceptable host capabilities,
  validation rules, and contribution receipts.

A `$0` cap means no positive-price bid can be accepted, even when a quote is
displayed. A host may voluntarily offer all or part of the requested capacity.
TinyAssets records the host's declared terms and contribution; it does not
assume why they contributed. Plausible reasons include unused capacity,
sponsorship, reputation, scientific interest, community membership, reciprocal
access, and advancing a shared open-source artifact.

The truthful public label is **scale-ready / resource-blocked** until the target
run actually executes. If enough compatible capacity is contributed, the same
authorized manifest runs without a new design, and only measured throughput,
recovery, convergence, evaluation, and reproducibility evidence may advance it
to **scale-proven**.

## Spend and Contribution Safety Contract

Every resource-seeking training Branch must:

1. estimate data volume, FLOPs/accelerator-hours, storage, network, and human
   services;
2. solicit comparable market bids rather than silently select one vendor;
3. enforce the lowest applicable Universe, Goal, and run spending cap before
   accepting any positive-price offer;
4. permit explicitly voluntary or below-market offers without treating them as
   guaranteed capacity;
5. run the smallest meaningful smoke/scaling test;
6. show a low/expected/high cost interval, resource shortfall, and scientific
   uncertainty;
7. require user approval for the bounded resource envelope and any material
   change to contributor terms;
8. sandbox untrusted hosts, disclose no undeclared secrets/private data, verify
   returned artifacts, and quarantine inconsistent workers;
9. checkpoint and expose live spend, contribution, throughput, and failure
   telemetry;
10. pause automatically at cap, stop-loss, anomaly, or evaluation boundaries;
    and
11. produce a final cost/contribution/model/data/evidence receipt whether
    successful or not.

## Not Doing

- No platform-owned fixed catalog of permissible model architectures.
- No claim that market money guarantees scarce capacity, lawful data, talent,
  scientific insight, safety approval, or a successful AGI design.
- No arbitrary source execution without sandboxing, secrets isolation,
  authorization, monitoring, and abuse controls.
- No automatic billion-dollar continuation because an early loss curve looks
  promising.
- No conflation of adaptation, continued pretraining, from-scratch training,
  architectural novelty, and demonstrated new capability.
- No requirement that training occur on the final edge device; ownership comes
  from source, authority, receipts, weights, and reproducibility, not where the
  rented accelerator sits.
- No claim that a quote, scale estimate, simulator, or resource listing proves
  the target large run worked.
- No expectation that hosts donate compute, and no pressure to accept unsafe,
  incompatible, or encumbered contributed capacity.
- No private or license-restricted training data sent to an untrusted volunteer
  host merely because its offer is free.

## Open Decisions

1. **Resolved by host, 2026-07-15:** MVP cash spending is strictly `$0`; use
   only already-available hardware/accounts and voluntary capacity.
2. What existing CPU/GPU/RAM and local model tooling may the proof use? The
   micro-model size/timebox must be derived from that inventory.
3. May MVP-0 pass with a one-machine multi-worker canary while the independently
   hosted distributed canary remains pending? Recommended: yes; otherwise an
   optional volunteer controls whether the zero-spend MVP can finish.
4. Which licenses and result-access terms are acceptable for contributed
   compute, checkpoints, and datasets?
5. Which novel-algorithm claim requires independent scientific review before a
   Branch may advertise itself as more than an implementation variant?

## Primary Sources

- Runpod GPU pricing, current self-service rates:
  <https://www.runpod.io/pricing>
- Lambda GPU instance pricing:
  <https://lambda.ai/instances>
- TinyLlama 1.1B training plan and checkpoints:
  <https://github.com/jzhang38/TinyLlama>
- Llama 2 reported A100 GPU-hours:
  <https://arxiv.org/pdf/2307.09288>
- Compute-optimal language-model scaling:
  <https://arxiv.org/abs/2203.15556>
- Epoch AI frontier training-cost analysis:
  <https://epoch.ai/publications/how-much-does-it-cost-to-train-frontier-ai-models>
