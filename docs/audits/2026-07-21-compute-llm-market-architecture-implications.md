# Compute, LLM, Task, and Fabrication Market Architecture Implications

**Status:** Codex initial research; implementation authority is blocked on an
independent Claude research review and host approval of any resulting OpenSpec
change. This document does not amend `PLAN.md` or the as-built specs.

**Freshness:** official product, protocol, and standards sources checked from
the United States on 2026-07-21. TinyAssets code and OpenSpec were checked at
`origin/main` commit `0bc841aa`.

## Executive judgment

TinyAssets has the right destination and most of the right pieces. Its current
specs already describe user-owned trained models, market-priced fine-tuning and
training, permissionless hosting of newly minted model capabilities, pooled
funding and revenue shares, hardware design, fabrication, and task bounties.
The missing piece is a small interoperability kernel that makes those pieces
one market without falsely making their products fungible.

The clean shape is **one minimal commercial envelope feeding existing,
domain-native execution and acceptance protocols**:

1. interactive inference: short-lived firm quotes and prequalified routing;
2. batch inference: batch clearing over comparable token capacity;
3. reserved inference capacity: standardized, physically settled forwards;
4. training: RFQ or sealed all-or-nothing tenders for device/topology windows;
5. goal bounties and agent tasks: machine-checkable gate acceptance; human-
   accepted contract work stays deferred behind a separate trust design;
6. fabrication: job quotes defined by process, material, tolerance, quantity,
   lead time, shipping, and inspection requirements; and
7. hardware shuttle capacity: milestone and signoff-gated fabrication seats.

The decentralized-exchange analogy is useful for **intents, aggregation,
solvers, firm quotes, capacity locks, collateral, and receipts**. It is not a
good basis for an automated market maker. Token inventories are fungible and
durable; compute and manufacturing capacity are heterogeneous, expiring,
location-sensitive services whose delivery occurs after the match.

The strategic product is therefore not another closed cloud. It is a neutral
best-execution fabric: outside hosted APIs initially provide reference prices
and ceilings, community hosts can beat them, users can bring owned capacity,
and newly verified commons artifacts can immediately become new supply. Any
future executable external-provider path must be explicitly designed as BYOK or
seller-bundled capacity; the platform does not silently become the reseller.

Host clarification 2026-07-21 makes the boundary absolute: TinyAssets does not
provide user compute. Every run uses requester-authorized BYOC/BYOM capacity or
an explicitly accepted market offer. Founder/maintainer Claude and OpenAI
subscriptions, quotas, credentials, local hardware, and billing remain
owner-scoped and are never a fallback, shared pool, or subsidy for user work.
No eligible route means `pending/held`, not consumption of a personal account.
This host-approved PLAN rule now conflicts with the provider-routing spec's
mandatory host-local fallback and must be aligned through OpenSpec before build;
the active R2-1 credential fail-closed lane addresses the related runtime leak.

## How might we

How might TinyAssets let any user design a workflow, agent, model, hardware
component, or physical device; buy the exact computation or fabrication needed
to create it at a competitive executable price; verify what was delivered; and
then let anyone host or manufacture the resulting commons artifact—without
making TinyAssets a custodian, hiding quality differences, or locking the
ecosystem to one provider?

## What TinyAssets already gets right

The current OpenSpec surface is unusually aligned with this vision:

- `paid-market-economy` defines integer-micro accounting, one money writer,
  atomic claims, immutable settlements, and a dark-by-default market.
- `paid-market-price-index-and-forwards` defines token-normalized spot prices,
  freshness, manipulation resistance, hosted-provider ceilings, and physically
  settled, non-transferable capacity forwards.
- `paid-market-training` defines user-owned fine-tunes, colocated gang training,
  research-gated swarm training, checkpoint settlement, eval gates, and a
  capability minted from immutable weights and provenance that any host may
  serve.
- `pooled-training-ownership` defines exact funding shares, revenue shares,
  lineage, and no secondary share trading.
- `hardware-creation` defines a ladder from simulation through FPGA, shuttle,
  and system integration, plus print/CNC-style fabrication with quotes and
  acceptance gates.
- `demand-side` and the paid-market core already distinguish
  standing goals and outcome bounties from raw compute capacity.
- The pure `tinyassets/paid_market/` core keeps price/index/matching/training/
  fabrication math independent of transport and side effects.

Those choices should be preserved. Under the current ratified spec, external
hosted prices remain ceilings and reference inputs only—not executable market
instruments and not an oracle that declares the value of work. Training should
settle against checkpoints and gates, not elapsed GPU time alone.

## What the frontier is converging on

### Inference aggregation

[Hugging Face Inference Providers](https://huggingface.co/docs/inference-providers/en/index)
and [OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection)
show convergence on a single client API with provider selection, fallback,
price/latency/throughput policies, tool and structured-output capability
filtering, privacy controls, and per-provider metadata. Hugging Face additionally
exposes model/provider price, context, tool support, first-token latency, and
throughput through its [Hub API](https://huggingface.co/docs/inference-providers/en/hub-api).

The lesson is not to copy their catalogs. It is to accept adapters from them and
from any compatible provider into a TinyAssets quote surface. OpenRouter itself
is curated rather than permissionless—its
[provider application](https://openrouter.ai/providers/apply) is an approval
queue—so TinyAssets still needs its own open-host path and verification rules.

### General compute and training scheduling

[Vast.ai offers](https://docs.vast.ai/api-reference/search/search-offers) expose
the dimensions that make GPU capacity only conditionally substitutable:
device/count/memory, reliability, region, CUDA, interconnect, network, storage,
duration, and interruptibility. [Akash](https://akash.network/docs/learn/core-concepts/deployments/)
uses deployment -> order -> bid -> lease -> manifest, with providers bidding
under a user maximum and capacity reserved by the lease. AWS Spot demonstrates
that the market price and interruption risk are separate facts; capacity can be
reclaimed even when a workload is otherwise valid, and checkpoint/rebalance
design is required ([AWS Spot concepts](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-spot-instances.html)).

[SkyPilot](https://docs.skypilot.ai/en/stable/overview.html) demonstrates a
useful separation: the workload description stays stable while an optimizer
chooses available cloud/region/zone capacity. Kubernetes
[Kueue](https://kueue.sigs.k8s.io/docs/overview/) adds quota reservation,
resource-flavor fungibility, all-or-nothing admission, multi-cluster dispatch,
and topology-aware scheduling. These are execution backends and adapters, not
the public economic truth.

### Agent and task interoperability

MCP is the correct chatbot/tool transport boundary, not a market schema. The
[MCP introduction](https://modelcontextprotocol.io/docs/getting-started/intro)
standardizes how AI applications reach tools, data, and workflows.
[A2A 1.0](https://github.com/a2aproject/A2A/blob/main/docs/specification.md)
adds useful independent concepts for opaque agents: signed/discoverable Agent
Cards, stateful Tasks, Messages, Artifacts, streaming, push notifications, and
extensions. TinyAssets should map to these at its edge rather than make its
internal node/gate model subordinate to them.

### Exchange mechanisms

[0x Swap API](https://docs.0x.org/docs/introduction/quickstart/swap-tokens-with-0x-swap-api)
separates an indicative read-only price from a firm executable quote and can
split execution across sources. [CoW Protocol](https://docs.cow.fi/) uses
permissionless solver competition and combinatorial batch auctions over signed
constraints. Both are strong inspirations for a compute aggregator.

[Uniswap's AMM](https://developers.uniswap.org/docs/get-started/concepts/how-uniswap-works)
is the wrong matching primitive for capacity. Its price changes as fungible
inventory moves along a pool curve; even concentrated liquidity remains a
fungible-asset position over a price range. Compute cannot be withdrawn from a
pool after its time window expires, and two nominally identical GPUs can differ
in topology, reliability, data policy, and delivered performance.

### Artifact and manufacturing interoperability

[Hugging Face model cards](https://huggingface.co/docs/hub/en/model-cards)
provide a practical discovery envelope for intended use, limitations, training
data, parameters, and evaluations. [MLflow Model Registry](https://www.mlflow.org/docs/latest/ml/model-registry/workflow/)
separates immutable versions from mutable deployment aliases and records source
runs/signatures. OCI descriptors provide content-addressed digests and media
types for executable or arbitrary artifacts
([OCI image spec](https://github.com/opencontainers/image-spec)). TinyAssets
should interoperate with these identifiers while keeping its own capability,
ownership, gate, and lineage truth.

For additive manufacturing, STL is too weak as the canonical handoff.
[3MF](https://3mf.io/spec/) is royalty-free, ISO/IEC 25422:2025, full-fidelity,
and explicitly targets interoperability among design tools, services, and
printers. Commercial networks such as
[Protolabs Network](https://www.protolabs.com/about-us/digital-factories-x-partner-network/)
show the same pattern as compute routing: upload a typed design, receive
market-based quotes with manufacturability feedback, then route to an internal
factory or vetted partner network. TinyAssets can open that pattern to community
printers and CNC shops while adding evidence and commons lineage.

Production evidence can remain interoperable too:
[MTConnect](https://www.mtconnect.org/about) or
[OPC UA Machine Tools](https://reference.opcfoundation.org/specs/OPC-40501-1/4.2.3.3)
can adapt machine/job/state observations, while
[QIF](https://qifstandards.org/overview/) can carry inspection plans, measured
results, resources, and traceability. These are evidence adapters, not
replacements for TinyAssets acceptance gates. Keep parametric code-CAD as the
remixable source; use signed STEP/3MF as production outputs.

## Recommended minimal domain model

### Scoping Rules pass: lifecycle roles, not twelve new primitives

The labels below are a protocol vocabulary for analysis. They must not become
twelve new MCP actions, storage tables, or platform abstractions by default.
PLAN Scoping Rules 1–2 produce a smaller implementation boundary:

- Reuse the existing paid-market request, bid, claim, and settlement records;
  node artifacts, gates/reviews, and capability minting remain the creation and
  acceptance primitives.
- Add only the irreducible structural gap: a versioned capability descriptor
  that allows independent parties to decide whether demand and supply are
  substitutable. It should normally be embedded in existing requests/offers.
- Model indicative/firm state, expiry, capacity lock, attempt facts, and typed
  acceptance evidence as fields or child receipts on those primitives unless
  implementation proves a distinct consistency boundary requires a record.
- Keep adapter implementations, routing objectives, verification profiles,
  maker qualification rubrics, and pricing strategies community-built commons
  artifacts. Platform code owns minimal schemas, identity/authority, money
  conservation, capacity locking, and evidence boundaries—not market taste.

This is the irreducibility test the follow-on OpenSpec change must repeat before
freezing names. `DemandIntent`, `EligibleOffer`, and the other labels can remain
roles in one lifecycle even when no same-named class or table exists.

The common lifecycle should be:

```text
DemandIntent + ArtifactManifest(s)
  -> WorkloadSpec
  -> CapabilityRequirement
  -> EligibleOffer
  -> IndicativeQuote
  -> FirmQuote / Reservation
  -> FulfillmentBinding (domain-native claim/lease/work order)
  -> AttemptLedger
  -> EvidenceReceipt
  -> AcceptanceBundle
  -> Settlement
  -> CapabilityMint (when the output is reusable)
```

The model deliberately distinguishes three things often collapsed by cloud and
crypto markets:

- **Capability:** what outcome or service can be produced.
- **Capacity:** a bounded provider commitment capable of producing it.
- **Artifact:** an immutable input or output with lineage, license, and gates.

Artifact references used for settlement must be immutable digests or immutable
versions. Settlement identity itself is the authorized contract/domain claim
plus its fence or idempotency key and the accepted artifact digest. Aliases,
tags, repository branches, catalog rows, model slugs, and deployment names are
discovery pointers only. OCI-style typed subject/referrer links can
connect a model, dataset, environment, checkpoint, SBOM, scan, evaluation,
license decision, and attestation without rewriting the artifact being
described.

### Execution substrate boundary

The commercial envelope selects and funds fulfillment; it does not replace the
execution protocols. Market-selected `repo`/`source_exec` jobs enter the existing
B2 offer/claim/lease/result/completion protocol after selection. No second
market worker protocol is introduced for those jobs. Settlement for that lane
remains fenced to:

```text
job_id : lease_fence : accepted_result_sha256
```

The B2 completion CAS must accept the current lease/fence before evidence can
authorize payment. Goal bounties retain first-verified-machine-gate settlement.
Training retains checkpoint/eval acceptance. Fabrication requires its own work
order, inspection, delivery, cure/rework, rejection, and risk-of-loss states.
Interactive inference uses a domain-native streaming serving contract with
request, cancellation, partial-output, token-metering, latency, and retry
semantics; it is not routed through B2. Batch inference likewise maps to its
serving/batch protocol, not the patch-loop lease state machine.
The shared nouns describe commercial handoffs; they do not make these state
machines interchangeable.

### DemandIntent

User constraints: required outcome, maximum total price, deadline, privacy/data
residency, reliability, acceptable interruption, quality gates, substitution
policy, partial-fill policy, and whether external retail providers are allowed.
Private payloads and data are host-resident by construction under Commons-first:
the platform never stores them, encrypted or otherwise. Platform matching sees
only the minimum public constraints, hashes/commitments, and explicitly
published commons artifacts required for a market action. A private job waits
or returns a graceful no-host signal when no authorized host is online.
Every binding market action also carries principal/tenant, authenticated actor
grant, contract/offer identity, signature domain, nonce/expiry, idempotency key,
and the relevant lease fence or domain claim token. Artifact identity does not
confer authority.

### CapabilityRequirement

A typed, versioned descriptor. Inference requirements need immutable model
revision/hash, runtime family, quantization, context, modalities, tool/structured
output support, latency/throughput class, region/data policy, and attestation
class. Training adds accelerator count/memory, topology/interconnect, gang
semantics, duration, checkpoint cadence, container digest, dataset access mode,
and restart policy. Fabrication adds source format, process, material, tolerance,
finish, quantity, dimensions, certification, inspection, destination, and lead
time.

### EligibleOffer and quote

An offer declares provider identity, capability descriptor, available window,
units, price function, minimum/maximum fill, location, privacy/retention policy,
reliability evidence, collateral, expiry, and adapter provenance. An indicative
quote is browseable and nonbinding. A firm quote is signed, nonce-bound,
short-lived, tenant-scoped, and backed by a capacity lock. Quote issuer,
authorized money actor, credential owner, verifier, and eventual receipt issuer
remain explicit and may be different parties.

### EvidenceReceipt

Evidence must remain typed:

- resource identity: hardware/runtime/model or machine/process identity;
- availability: reservation and challenge/heartbeat;
- execution: metering, trace, checkpoint, or process-step commitments;
- quality: held-out evals, randomized replay, inspection, or redundant work;
- delivery: tokens, latency, checkpoint/artifact hash, dimensions, or shipment.

Uptime, hardware attestation, and payment escrow are not proof that a requested
computation or physical part was correctly delivered.

### AttemptLedger and AcceptanceBundle

The route decision, execution attempts, evidence, acceptance, and billing truth
must not be collapsed. Each retry/fallback records its ordinal, concrete
endpoint/worker, route reason, native request ID, start/end, partial-output
state, measured units, estimated cost, and failure/interruption class. The
acceptance bundle applies the domain-specific gate profile to all relevant
receipts. A later provider invoice or immutable TinyAssets settlement remains
financial truth; gateway estimates do not silently become charges.

## Routing and price discovery

There is no honest single "price of compute." TinyAssets should publish a
**price surface per substitutability class**:

- inference: input/output/cached-token prices plus latency, throughput, context,
  privacy, and reliability class;
- training: device-hour or accelerator-window price plus topology, interrupt
  risk, checkpoint/recovery terms, and total expected job cost;
- tasks: fixed/bid/bounty price for an accepted outcome and its gates;
- fabrication: total and per-unit quote plus tooling, material, inspection,
  lead time, shipping, and acceptance terms.

For each sufficiently liquid class, retain TinyAssets' current composite:
fresh VWAP, best ask, external hosted-provider ceiling, timestamp, volume,
distinct-owner count, and confidence/manipulation flags. The user-facing number
should be the **best currently executable total quote under the user's policy**,
not a stale midpoint.

Every observation needs `observed_at`, source, the exact resource envelope, and
a TTL or `valid_until`. Historical reliability, instantaneous capacity
confidence, interruption notice, contractual SLA, and SLA remedy are separate
fields. A catalog listing is neither a reservation nor a delivery promise.

The platform first exposes the four peer fulfillment paths already defined by
the full-platform architecture: dry-run, free public queue, paid request, or
self-host. The chatbot explains or recommends; the user chooses. **The platform
does not choose whether the user pays.** Only after the paid/BYO path is chosen
does deterministic economic routing occur:

1. validate artifact, license, privacy, and capability substitutability;
2. filter offers that cannot satisfy hard constraints;
3. compute expected total cost, including failure/interruption/retry and data
   movement—not just nominal unit price;
4. compare eligible community offers or the selected owner/BYO binding;
5. reserve capacity before exposing a firm route;
6. execute with typed evidence and deterministic settlement; and
7. record performance without leaking prompts, datasets, CAD, or private demand.

External-provider integration has three deliberately separate modes:

1. **Price-reference adapter (ratified now):** fetches public hosted prices as a
   ceiling; it cannot execute, claim, or settle.
2. **User-owned/BYOK route (future explicit design):** the user owns the account,
   credential, upstream terms, and bill; usage stays outside TinyAssets market
   accounting. TinyAssets must not store the credential on the platform.
3. **Seller-bundled route (deferred):** a native TinyAssets seller may someday
   bundle upstream service only if it is the authorized money actor, owns or is
   authorized for the credential, accepts upstream terms/abuse/invoice risk,
   and supplies fenced evidence. The platform still does not buy or custody the
   upstream service.

Anyone may implement reference adapters as commons artifacts, but quote origin,
terms, mode, and freshness remain explicit. Proprietary-model instruments and
executable external-provider resale stay outside the current spec until a
separate host-approved OpenSpec change resolves custody and liability.

At the observability and cost edges, export version-pinned
[OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai)
and map finalized usage toward the provider/host-provider and billed/effective
cost distinctions in [FOCUS](https://focus.finops.org/focus-specification/).
Neither standard should become TinyAssets' internal settlement model.

## Mechanism by market lane

| Lane | Matching | Why |
|---|---|---|
| Interactive inference | prequalified router + signed short-lived RFQ | an auction adds unacceptable request latency |
| Batch inference | periodic uniform-price batch clearing | comparable jobs can trade latency for cost and fair allocation |
| Reserved inference | transparent standardized seller order book | capacity windows are inspectable and physically deliverable |
| F1 fine-tuning | RFQ or sealed tender | data/privacy and runtime details are bespoke |
| F2 gang training | combinatorial all-or-nothing tender | the whole topology must be available together |
| F3 swarm training | research-only | adversarial coordination and verification are not mature enough |
| Standing-goal bounty | funded bounty; first verified claim wins | machine-checkable gates only; no poster human-acceptance/griefing surface |
| Human-accepted contract work | defer | requires a different authority, inspection, dispute, and trust design |
| Fabrication | RFQ with typed quote comparison | geometry, process, material, tolerance, QA, and shipping dominate |

Adopt CoW-style reproducible solver competition for batch allocation, but keep
solvers non-custodial and make the winning allocation independently recomputable.
Use Dutch price movement only as an explicit urgency policy near a deadline or
for expiring unsold capacity. Do not add secondary trading, cash settlement, or
an AMM/bonding curve for capacity.

## The democratized creation loop

The full-stack commons vision becomes a repeated supply-creation loop:

1. A user creates or remixes a workflow, harness, dataset recipe, model design,
   hardware design, CAD/code-CAD program, or device specification.
2. The node declares the capabilities, budget, ownership, license, required
   inputs, evidence, and acceptance gates.
3. The chatbot presents the peer fulfillment paths and the user chooses. If the
   user selects paid fulfillment, the deterministic selector ranks eligible
   native offers under the user's approved cap; no hidden platform fallback or
   purchase occurs.
4. Gates verify the output and record provenance and costs.
5. A reusable output is minted as a new immutable capability/artifact version.
6. Any compatible host or maker may publish capacity for it and compete on
   executable price, delivery, privacy, and reliability.
7. Usage settles attribution and revenue according to the artifact's explicit
   ownership/license terms.

NVIDIA, a home GPU owner, a model author, a cloud, a fab, and a printer shop are
all providers at different layers. TinyAssets should not erase those layers; it
should give them the same open entry, description, evidence, and settlement
grammar.

### Hardware and maker invariants do not collapse into compute

The existing hardware ladder remains binding. FPGA verification precedes
shuttle admission; a full-die shuttle request pays full cost and an isolated
failure cannot charge unrelated seats; garage silicon is evidence and learning,
not production compute; and process-chemistry/safety documentation fails closed.
Community maker onboarding must visibly separate garage, verified production,
certified, regulated, and export-controlled supply.

Physical work orders additionally bind critical-to-quality dimensions,
tolerances/datums/measurement method, material and lot, process/machine/operator,
calibration, inspection authority and sampling, shipment and risk of loss,
receipt, dispute, cure/rework, replacement, rejection, and return. These map to
typed fabrication acceptance states rather than a generic compute receipt.

## Security, abuse, and regulatory boundaries

Before any public money or mainnet path, the market needs specialist review for
payments/money transmission, commodities or derivatives, sanctions, export
controls, privacy, taxes, consumer protection, and fractional ownership. The
existing non-transferable physical-delivery design is directionally safer than
cash-settled or secondary instruments but is not a legal conclusion.
[FinCEN's virtual-currency guidance](https://www.fincen.gov/resources/statutes-regulations/guidance/application-fincens-regulations-persons-administering),
[OFAC's sanctions guidance](https://ofac.treasury.gov/system/files/126/virtual_currency_guidance_brochure.pdf),
and [BIS's AI-training policy statement](https://www.bis.gov/media/documents/ai-policy-statement-training-ai-models-may-13-2025)
make custody/transmission, counterparty/geography, advanced compute, end-user,
and end-use controls design inputs rather than a post-launch compliance layer.
The BIS statement is narrower than a general AI-training ban: it identifies
possible EAR Part 744 license triggers involving covered advanced-computing
items or U.S.-person support, knowledge of WMD or military-intelligence end
use/user, and training for or on behalf of parties headquartered in Country
Group D:5 countries (including China) or Macau.

The relevant CFTC question is the statutory forward-contract exclusion, not
whether TinyAssets calls an instrument a forward. The cited
[CFTC/SEC interpretation](https://www.cftc.gov/LawRegulation/FederalRegister/finalrules/2015-11946.html)
centers actual delivery, non-severable optionality, commercial-party intent to
make/take delivery, and physical or regulatory reasons for volume variation.
Whether compute capacity is a qualifying nonfinancial commodity and whether a
specific contract satisfies the facts-and-circumstances test require counsel;
physical settlement alone is not a safe harbor.

Technical controls must cover:

- Sybil hosts, related-party/wash settlements, self-dealing, bid copying,
  capacity withholding, and index manipulation;
- provider/solver/verifier collusion and evaluator gaming;
- malicious models, datasets, containers, CAD, firmware, and fabricated parts;
- model and dataset license compatibility and attribution;
- prompt/training-data retention, residency, and live-memory exposure on
  untrusted hosts;
- export-controlled hardware/model training and restricted end users/end uses;
- capacity double-selling, false benchmarks, counterfeit hardware, checkpoint
  fabrication, and inspection fraud; and
- unsafe or regulated physical designs.

Mitigations include owner/payment/failure-domain clustering, per-owner index
weight caps, distinct-owner thresholds, exclusion of related-party trades from
indices, private payload intake, randomized verifier assignment after
commitment, objective buyer-compensating collateral, signed expiries/nonces,
capacity locks, immutable artifact digests, and typed dispute windows. Never
slash for a subjective quality opinion.

## Gap assessment

| Area | Current shape | Needed refinement |
|---|---|---|
| Economic core | strong, pure, deterministic | keep unchanged unless typed instruments require a generic envelope |
| Live transport | Wave 2 proposal exists; B2 execution is separate | capacity locks and signed quote expiry/nonce before unchanged B2; fence settlement to accepted result CAS |
| Capability key | token-normalized but intentionally coarse | widen before live routing to artifact/runtime/performance/privacy/topology identity |
| External prices | hosted ceiling parser; proprietary instruments excluded | open read-only adapter protocol first; BYOK/seller-bundled execution needs separate ratification |
| Provider routing | static role/health/privacy fallback | separate economic best-execution router; reuse receipt identity/attempt facts without overloading model-role routing |
| Training | strong F1/F2/F3 staged design | typed tenders, topology and interruption cost, verifier independence |
| Model registry | minted weights URI/hash/provenance/license | immutable artifact graph plus separate license, access, validation, promotion, publication, deployment, and alias states |
| Task market | standing goals plus machine-gated bounties | A2A/MCP edge adapters; preserve first-verified gate settlement and defer human acceptance |
| Fabrication | quote, code-CAD, hardware ladder, QA concepts | domain work-order/inspection/shipping/cure/rejection states and tiered maker qualification |
| Price index | strong thin-market controls | price surfaces by substitutability class; never one global compute scalar |

## Adopt / adapt / avoid / defer

| Decision | Items |
|---|---|
| **Adopt** | existing request/bid/claim/settlement core; unchanged fenced B2 execution; standing goals and machine-gated bounties; capability minting; immutable artifacts and typed evidence |
| **Adapt** | DEX intents/RFQs/solvers into non-custodial allocation; OCI/HF/MLflow/3MF/QIF at adapter edges; capability descriptors and expiring quotes as fields around existing primitives |
| **Avoid** | universal execution protocol; AMM/bonding curve; platform-picked paid path; platform-held private payloads or provider credentials; artifact hash as authority; human-accepted bounties; hidden upstream resale |
| **Defer** | proprietary-model instruments, seller-bundled hosted APIs, secondary/cash-settled capacity, F3 swarm economics, human contract market, regulated fabrication, and production use of garage silicon |

## Builder pickup packet

- **Source lane:** branch `codex/compute-market-frontier-research`, worktree
  `C:\Users\Jonathan\Projects\wf-compute-market-research`, research artifact
  and Claude opposite-provider review in this directory.
- **Existing build lane:** paid-market Wave 2 draft PR #1542; do not broaden the
  active R2-1 credential/provider-receipt Files boundary.
- **Write boundary for the follow-on:** a new OpenSpec change only. No runtime,
  schema, API, or PLAN edits before host design approval.
- **Required reads:** `paid-market-economy`,
  `paid-market-price-index-and-forwards`, `paid-market-training`,
  `pooled-training-ownership`, `hardware-creation`, `demand-side`, the active
  distributed-execution proposal/plan, and full-platform architecture §20.2.
- **Hard dependencies:** incorporate the Claude `ADAPT` findings; preserve
  Commons-first residency, user-selected fulfillment, unchanged B2 and fenced
  settlement, current hosted-price-only boundary, and domain-specific maker
  acceptance.
- **First deliverable:** OpenSpec exploration/proposal that maps every proposed
  field to an existing primitive, labels any irreducible gap, and contains no
  implementation code. Opposite-provider review and host approval gate apply.

## Source provenance notes

Mutable product documentation was freshness-checked 2026-07-21 and must be
revalidated before implementation. Stable references used here include A2A
1.0.0, 3MF ISO/IEC 25422:2025, OCI Image/Distribution 1.1.1 (Apache-2.0), and
FOCUS 1.4 (CC BY 4.0). OpenTelemetry GenAI conventions remain evolving; any
adapter must pin an explicit release (v1.41.1 was current when checked), never
track `main` as a settlement contract.

## Recommended sequence

No implementation should start from this report until Claude independently
re-checks the sources and TinyAssets context, and the host approves the design
direction.

1. **Ratify roles and map them to existing primitives in OpenSpec.** Repeat the
   irreducibility/composition pass; preserve request/bid/claim/settlement,
   artifact/gate/capability, and unchanged B2 execution for repo/source jobs.
   Freeze only structural
   gaps such as the capability descriptor and required fence/authority fields.
   Keep PLAN architecture changes separate and host-approved.
2. **Specify a minimal Compute Capability Descriptor and adapter contract.** It
   should be versioned/extensible, use immutable artifact digests, and map to
   OpenAI-compatible inference, Hugging Face/OCI artifacts, MCP/A2A tasks,
   Kueue/SkyPilot-style jobs, and 3MF/STEP fabrication without copying any one
   system's schema.
3. **Add read-only quote aggregation first.** Combine external hosted-reference
   quotes and native TinyAssets asks. Publish executable native totals plus
   reference ceilings, freshness, origin, and policy fit; make no automatic
   purchases. Owned/subscription comparison remains user-local until the BYOK
   design is separately ratified.
4. **Specify, then dark-launch native-offer best-execution inference.** After the
   user chooses paid fulfillment, validate substitutability, reserve a community
   offer, and use an explicitly specified streaming inference contract—not B2.
   Compare output/latency/cost and adversarially test cancellation, partial
   output, metering, no-host pending, privacy, double-selling, quote expiry, and
   wash-index attacks. Keep external providers price-only in this phase.
5. **Activate verified open hosting.** Let anyone advertise a model/runtime
   capability, but require immutable identity, metering/evidence, objective
   disputes, and buyer-compensating collateral before price-index inclusion.
6. **Add F1 then F2 training tenders.** Checkpoint/recovery economics and
   all-or-nothing topology admission precede public gang training. Keep F3 dark.
7. **Extend the commercial envelope—not B2—to makers.** Start with community
   FDM/3MF work orders, explicit tolerances and inspection/shipping/cure states;
   preserve the hardware ladder and add CNC or regulated/high-risk processes
   only with stronger qualification.
8. **Prove §14 scale and clean user use.** Every public lane needs concurrency,
   manipulation, failure, rendered chatbot, and post-fix organic-use evidence.

## Decision for the current paid-market Wave 2 proposal

PR #1542 is directionally compatible and should not be discarded. Before it is
treated as implementation-ready, its opposite-provider review should determine
whether to add only the foundational quote/capacity-lock fields now or to keep
Wave 2 narrowly transport-only and create a dependent OpenSpec change for the
interoperable market kernel. The safer default is the latter: land a minimal,
reliable transport, then widen capability identity and adapters in a separately
ratified change before any live best-execution routing.

The active R2-1 credential/provider-receipt lane is adjacent but should not be
broadened mid-flight. Its fail-closed provider identity and routing evidence can
become inputs to a later market attempt ledger; economic quotes, reservations,
settlement, and capability matching remain in the paid-market changes after the
research gate. R2-1 and Wave 2's money-actor/authority hardening address the
same ambient-host-authority failure class in separate modules, so their receipt
and actor identities must be cross-checked before either schema is treated as a
shared market identity.
