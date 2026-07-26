# Full Product Vision Completion Audit

Date: 2026-07-25 (America/Los_Angeles)

Repository base: `origin/main@b759682fbcb226a7cd90b62092676ef7e3555e3f`

Production release observed: `b759682fbcb226a7cd90b62092676ef7e3555e3f`

Environment: Windows, Python 3.14, live `https://tinyassets.io/mcp`, GitHub Actions and PR metadata

## Verdict

TinyAssets has the right product shape, but the full product is **not close to
done as a production system**. It is in the early-to-middle integration stage:
the composable graph, goal, evaluation, provider, authoring, pricing, pure
economic foundations, wired narrow effect boundary, and dark market spine are
substantial; shared transactional authority, requester-owned execution,
distributed supply, live market activation, organization, compliance, and
end-to-end acceptance are not complete.

Recomputed against current main, the 34 audited outcomes still classify as:

| State | Count | Meaning |
|---|---:|---|
| `PROVEN` | 1 | Current intended public path and fresh production evidence exist |
| `IMPLEMENTED-NOT-PROVEN` | 9 | User-reachable meaningful runtime exists, but production/user/load proof is incomplete |
| `IMPLEMENTED-DARK` | 1 | Meaningful runtime exists, but no intended non-test call path activates it |
| `SPECIFIED-NOT-BUILT` | 9 | Binding target exists; required runtime or acceptance does not |
| `PARTIAL-CONTRADICTED` | 9 | Some pieces exist, but a known gap or contradictory path defeats the promise |
| `MISSING` | 5 | No accepted end-to-end capability contract or implementation exists |

This count is deliberately unweighted. It is not a claim that the product is
`1/34` complete by engineering effort: several implemented foundations support
many outcomes, while several missing outcomes are large programs. It does show
why a high completion percentage would be misleading.

## Proof standard and freshness

- Specs and research do not count as implementation.
- Unit tests do not count as production or rendered-user proof.
- A public chatbot capability is not proven until a real rendered chatbot uses
  the installed connector, followed by post-fix clean-use evidence.
- A concurrency claim is not proven by mocks or one-process tests.
- A BYOC claim is not proven until the requester authority is bound through the
  complete execution path and receipts show no maintainer/founder capacity.
- A market is not proven by pure pricing and settlement functions when no live
  request, capacity lock, delivery, and settlement transport invokes them.

Fresh evidence collected for this audit:

- The live canary passed against `https://tinyassets.io/mcp` with exact server
  name `TinyAssets`, the canonical seven handles, and required uptime fields.
- `/mcp-directory`, `/mcp-directory/`, `/mcp-directory/sse`, and
  `/mcp-directory/messages` each returned ordinary `404` with no redirect.
- Live `get_status` reported exact release `b759682fbcb2`, image digest
  `sha256:402af662cc5330141cc32bf1fc3ce4678ee4b5bd711d56ee05e25358cfe4c9b5`,
  deployed `2026-07-26T05:00:33Z`, with the canary bundle passed.
- The newest full uptime canary was green in GitHub Actions run `30186841153`.
  The immediately prior scheduled run `30186819560` saw one edge `502`; the
  workflow-run retry passed every layer about one minute later. This is
  recovered availability evidence, not zero-downtime proof.
- The latest full DR drill was green on 2026-07-24, run `30066361115`.
- Identity fingerprint evidence is degraded:
  `unavailable:key_not_provisioned`.
- Focused provider/custody routing tests:
  `64 passed, 1 skipped in 0.99s`.
- Independent focused market/provider/distributed-authority command:

  ```powershell
  python -m pytest tests/test_paid_market_core.py tests/test_paid_market_instruments.py tests/test_paid_market_routing.py tests/test_paid_market_quotes.py tests/test_paid_market_price_surface.py tests/test_api_market.py tests/test_paid_market_transport.py tests/test_provider_allowlist.py tests/test_distributed_execution_authority.py -q --noconftest
  ```

  Result: `362 passed in 4.97s`. This proves local contract behavior only.

- `openspec validate --all --strict` passed all 51 current specs and changes.
- OpenSpec strict task counts on the refreshed audit base include:

  | Change | Complete | Total |
  |---|---:|---:|
  | `build-forward-platform-capabilities` | 5 | 19 |
  | `complete-plan-gated-platform-targets` | 8 | 58 |
  | `data-commons-contribution` | 0 | 57 |
  | `constrain-set-engine-provider-authority` | 35 | 83 |
  | `paid-market-live-price-discovery` | 19 | 31 |
  | `paid-market-track-e-wave-2-transport` | 22 | 37 |
  | `distributed-execution` | 18 | 108 |
  | `harden-production-load-evidence` | 6 | 19 |
  | `outbound-boundary-layer` | 12 | 28 |
  | `demand-side-signals` | 0 | 49 |
  | `moderation-and-abuse-response` | 3 | 12 |
  | `universe-creation` | 11 | 34 |
  | `universe-visibility` | 9 | 10 |
  | `provider-attempt-receipts` | 1 | 15 |
  | `build-brain-canonical-store` | 3 | 14 |
  | `complete-independent-full-platform-targets` | 15 | 32 |
  | `reconcile-external-connector-manifests` | 18 | 49 |
  | `scoped-wiki-canary-token` | 12 | 12 |
  | `harden-branch-access-authority` | 5 | 39 |
  | `test-identity-and-reset` | 6 | 9 |

## Requirement-to-evidence matrix

### Public product, authoring, and cognition

| Product outcome | State | Current evidence | What remains |
|---|---|---|---|
| Exact product identity `TinyAssets`, canonical endpoint `https://tinyassets.io/mcp`, retired `/mcp-directory*` absent | `PROVEN` | PLAN Distribution module, live connector spec, live exact-name/seven-handle canary, four live `404` probes | External client registrations still need replacement/registration under the exact identity |
| Public MCP remains available while the founder PC is off | `IMPLEMENTED-NOT-PROVEN` | Cloud-hosted endpoint, host-independent GitHub Actions and a successful full DR drill prove founder-PC independence | Scheduled run `30186819560` saw an edge `502` before a full green retry about one minute later; root cause/recurrence, fingerprint recovery and a sustained zero-downtime window remain |
| Rendered chatbot use plus clean organic-user evidence | `MISSING` | Acceptance requirements exist; `output/user_sim_session.md` is absent on the audit base | Register the ChatGPT connector and run provider-free OAuth/read/write conversations now; BYOC proof remains separately blocked on requester authority, then watch real use |
| Friendly first contact creates/binds the user’s home and explains unavailable execution before spending | `PARTIAL-CONTRADICTED` | Founder-home birth/binding and actionable `held/setup_required` replies are implemented and tested; #1784 now defines the request-scoped provider-authority target | The three provider-authority successor changes do not exist yet; universe-creation authority tasks remain; current setup guidance still follows a provider attempt rather than gating dispatch, and accepted-market success is absent |
| Conversational node/evaluator authoring with inspect, edit, test, dry effects, publish | `IMPLEMENTED-NOT-PROVEN` | `tinyassets/authoring/`, canonical-handle actions, authoring tests and scale tests landed in PR #1770 and are in the live release | No complete rendered chatbot authoring transcript or post-fix organic-use proof |
| Long-horizon graphs, branches, goals, gates, evaluations, checkpoints, lineage | `IMPLEMENTED-NOT-PROVEN` | Canonical graph/evaluation/goal specs and substantial runtime/tests | Public multi-user goal-to-outcome acceptance and production-scale evidence remain incomplete |
| Design a model/training mission conversationally on the platform | `IMPLEMENTED-NOT-PROVEN` | Generic graph/Goal/Gate authoring substrate composes the design experience | No accepted reference archetype or end-to-end rendered model-design mission; actual training execution remains a separate unbuilt row below |
| Static provider/local-model inference routing | `IMPLEMENTED-NOT-PROVEN` | `tinyassets/providers/router.py`, provider-routing spec, focused allowlist tests | This is not economic routing; requester-owned live execution and receipts remain unproven |
| Commons brain canonical store and user-designed brain organizations | `SPECIFIED-NOT-BUILT` | PLAN decision, `build-brain-canonical-store`, and the target-only `data-commons-contribution` admission successor | Write path, commit protocol, custom-organization seam, rebuild/redaction proof, and acceptance remain |

### Compute, model, task, and fabrication market

| Product outcome | State | Current evidence | What remains |
|---|---|---|---|
| Requester BYOC/BYOM or accepted-market authority; never maintainer quota | `PARTIAL-CONTRADICTED` | Safe child-environment and credential-vault boundaries plus #1784’s approved transport-evidence, sink-bound authority, requester-local Ollama, and credential-blind remote-proxy target | #1784 is target-only and active/unsynced; its three runtime successors are absent; `allowed_providers` still lacks the complete production write path, production workers expose shared maintainer auth homes, and first-contact/R2-1a/R2-1b remain |
| Pure price surfaces, quotes, firm/reference distinction, deterministic best execution | `IMPLEMENTED-NOT-PROVEN` | `tinyassets/paid_market/{price_surface,quotes,routing,index,instruments}.py`, PR #1737, focused tests | Pure libraries are not a public market; descriptor completion, live observations, public reads, capacity revalidation and user proof remain |
| Public live market prices for inference/training/tasks/fabrication | `SPECIFIED-NOT-BUILT` | Active live-price OpenSpec defines class-scoped fields, freshness, caveats, caching and manipulation controls | No public read, live adapters, capacity lock, load proof, canary, rendered quote conversation or organic evidence |
| Best Internet price / OpenRouter-style executable routing | `PARTIAL-CONTRADICTED` | Economic router and reference-ceiling design are clean | External providers are intentionally reference-only today; executable BYOK/seller-bundled routes need separately approved custody/liability contracts |
| Paid request to bid, deterministic match, claim, delivery, acceptance/dispute, settlement | `IMPLEMENTED-DARK` | Request/inbox/bid/match/claim, Realtime projection, accounting hooks, and migration 013 landed in #1786; Wave 2 is 22/37, but `market_realtime` has no non-test activation path | Production migration/Realtime are not provisioned; `lease_fence` and `accepted_result_sha256` have zero implementations; delivery, acceptance/dispute, settlement completion, canaries, load and rendered proof remain |
| Permissionless hosts advertise and sell verified compute | `SPECIFIED-NOT-BUILT` | Distributed-execution, market capability, and #1784 provider-authority targets | D0 authority carriers exist, but V1-V8/S0-S16 execution, host enrollment/account binding, supply publication, metering and settlement do not |
| F1 fine-tuning and atomic F2 training windows | `SPECIFIED-NOT-BUILT` | Training target defines instruments, checkpoints, gates, license/provenance and capability minting | No successor owner; needs data manifests, transport, distributed execution, attestation and gate evidence |
| A newly created model becomes a durable artifact that anyone can host and users can buy inference from | `MISSING` | The vision and research describe it | No accepted model registry/deployment/alias/serving/metering lifecycle or owning OpenSpec successor |
| Pure fabrication, shuttle, quote and settlement economics | `IMPLEMENTED-NOT-PROVEN` | `tinyassets/paid_market/{fabrication,shuttle}.py` and canonical pure-economy spec | No seller discovery, work order, artifact admission, inspection, shipping, persistence, payment or user proof |
| 3D-printer/CNC/maker and chip-design lifecycle | `SPECIFIED-NOT-BUILT` | Hardware target defines verified ladder, code-CAD artifacts, QA, safety and fabrication settlement | No successor owner; blocked by transaction, boundary, data, gates, training/pool provenance and legal/safety evidence |

The DEX/OpenRouter analogy is being used correctly: intents, RFQs, solvers,
firm quotes, capacity locks, collateral, evidence and receipts are useful.
An AMM or one universal “compute token” is not. Compute and fabrication are
heterogeneous, expiring, location-sensitive services. Price surfaces must stay
separate by substitutability class, and economic routing must remain separate
from provider/domain execution authority. The load-bearing capacity-lock fence
is still absent: neither `lease_fence` nor `accepted_result_sha256` has a
runtime implementation, even after the dark workflow spine landed.

### Zapier-equivalent automation

| Product outcome | State | Current evidence | What remains |
|---|---|---|---|
| Expressive Zapier-class graph outcomes: branches, loops/subgraphs, checkpoints, AI composition | `IMPLEMENTED-NOT-PROVEN` | Graph compiler, branch/run substrate and tests are more expressive than a linear automation core | No rendered outcome-parity pack through the public connector |
| Durable triggers, schedules, delays, webhook/email ingress and safe retry | `PARTIAL-CONTRADICTED` | Scheduler stores definitions | Production startup is unwired; events are process-memory; crash windows can lose or duplicate; boundary and demand changes are unbuilt |
| General OAuth/API app connections, outbound MCP/OpenAPI adapters and safe effects | `IMPLEMENTED-NOT-PROVEN` | Outbound waves 1–3 landed in #1787: grant ledger, scoped credential-blind proxy, action caps and effect keys are wired into the shipped GitHub, Twitter, wiki and Windows effectors | Change is 12/28; generic OAuth/MCP/OpenAPI transport, inbound lifecycle, reconciliation/revocation completion, rendered outcome pack and clean-use proof remain |
| “Anything users currently do on Zapier” accepted end to end | `MISSING` | Historical research defines a testable outcome benchmark | No approved parity capability, authorized integration matrix, rendered 11-outcome pack or clean-use evidence |

The right product shape is outcome parity through a small integration and
effect-safety kernel, not a Zapier UI clone or thousands of platform-owned
connectors. Community connector definitions and compositions should be
discoverable/remixable; private grants and credentials must remain outside the
commons.

### Organizations, company brains, and regulated situations

| Product outcome | State | Current evidence | What remains |
|---|---|---|---|
| Canonical organization, membership, groups/RBAC, invitations and SCIM/HRIS offboarding | `MISSING` | Research and idea-inbox successor exist | No active OpenSpec, owner, organization authority model or lifecycle implementation |
| Shareable company-brain blueprint plus isolated organization instance | `PARTIAL-CONTRADICTED` | PLAN targets user-designed brain organizations; existing universe, ACL and graph runtime are aligned foundations | The brain-organization write path/seam, organization-universe binding, collaborative membership authority, blueprint upgrade contract and settled per-instance custody mode are absent |
| Manage the company brain and employees from Slack/Teams/email/CRM/HR systems | `MISSING` | Research defines these as conformance adapters over one authority boundary | No Slack/Teams installation, actor mapping, admin cards, SCIM adapter or rendered conversation |
| Situational best-practice visibility so the user’s chatbot can compose what applies | `PARTIAL-CONTRADICTED` | PLAN correctly makes guidance community-built and enforcement boundaries platform-owned; wiki/remix primitives exist | No accepted applicability/freshness/profile composition and no HIPAA-shaped user acceptance |
| Versioned compliance profiles, enforcement receipts, evidence, retention/hold/deletion and incident workflows | `PARTIAL-CONTRADICTED` | Generic ACL/effect receipts and pure economic route-receipt/retention fragments exist; the regulated-industry model remains research-only | No accepted compliance OpenSpec/owner or end-to-end data-class, purpose, copy graph, vendor-contract/BAA, persisted evidence, subject-rights or incident lifecycle; no assessor-owned pilot |

TinyAssets should not advertise a “HIPAA mode” or infer certification. The
clean design is a versioned, remixable situational control profile that maps
cited authority to frozen enforcement gates and evidence while leaving legal
applicability and final claims with the user, counsel and assessor. HIPAA can
be the first profile without becoming a special runtime branch.

### Scale, collaboration, discovery, and safety

| Product outcome | State | Current evidence | What remains |
|---|---|---|---|
| Thousands of concurrent users with tenant fairness and no data/authority bleed | `PARTIAL-CONTRADICTED` | Target architecture is horizontally clean; local concurrency tests exist; load evidence protocol is strict-valid | Current public origin/storage/session correctness is still singleton/process/file/SQLite shaped; no approved isolated envelope or production capacity result |
| Complete platform works 24/7 with zero compute hosts online | `SPECIFIED-NOT-BUILT` | Control-plane/authoring/market-pending target is canonical | Only the current MCP service/DR path is proven; collaboration, market, moderation and hostless transactional authority are incomplete |
| Node discovery, remix and convergence | `PARTIAL-CONTRADICTED` | Existing fork/remix/provenance primitives plus the landed `complete-plan-gated-platform-targets` discovery/remix target | No canonical production catalog/query/ranking/convergence implementation or rendered public proof; branch/wiki authority hardening remains |
| Realtime collaborative editing/presence | `SPECIFIED-NOT-BUILT` | The landed plan-gated target specifies versioned-row/CAS/broadcast presence | No canonical production Realtime collaboration implementation or load evidence |
| Moderation, abuse response, appeals and rate limits | `SPECIFIED-NOT-BUILT` | Active moderation target and draft PRs #1662/#1667 | Persistence, API route and concurrency proof remain incomplete/unowned |
| Shared PostgreSQL control-plane authority for catalog/ledger/inbox/market | `SPECIFIED-NOT-BUILT` | PLAN decision and draft PR #1670 define the contract | PR #1670 is a stacked draft, not landed main authority; production baseline/migration home and runtime cutover remain |

## What is genuinely done

1. The public identity is now coherent: exact `TinyAssets`, exact `/mcp`, exact
   canonical seven, and retired route absence are live.
2. The remote MCP and its DR/canary path do not depend on the founder PC being
   online.
3. The graph, branch, run, checkpoint, goal/gate, evaluator and lineage
   foundations are substantial.
4. Node/evaluator authoring now has a real guarded runtime and canonical-handle
   surface.
5. Provider isolation, allowlist, credential-child isolation and market
   best-execution foundations have meaningful local contract coverage; the
   provider-authority target now closes the intended transport/sink contract.
6. Pure economic functions for spot, forwards, training checkpoints, pooling,
   fabrication, shuttles and matching are substantial and conservation-tested.
7. A dark, non-activated runtime spine now exists for paid request through
   claim and Realtime/accounting. Separately, outbound grants and the
   credential-blind proxy are wired into four narrow shipped effectors. Neither
   is a live general market or Zapier-parity proof.
8. The scoped stateful wiki write-roundtrip canary is implemented and its
   target change is 12/12.
9. The architecture correctly separates transactional Postgres domains,
   commons brain storage, user-selected private custody, economic routing and
   execution authority.

## Critical path from here

The shortest shared-dependency path has two parallel roots:

1. **1A — requester execution authority, the immediate safety boundary.**
   #1784 settled the target contract; now author and land its three named
   successors for background receipts, host/stdio/plugin authority, and Tier-1
   accepted-market activation, alongside universe creation, branch/run
   authority, R2-1a allowed-provider selection and R2-1b attempt receipts.
   Every route must end in requester-owned capacity, an accepted market lease,
   or honest `held`; first-contact must decide this before provider dispatch.
2. **1B — PostgreSQL transactional control-plane authority.** In parallel,
   resolve draft
   PR #1670’s stacked base and production migration ownership. Catalog, ledger,
   inbox, market, tenancy and outbox work cannot safely scale on competing
   local authorities.
3. **Finish and broaden the non-value boundary.** Waves 1–3 are wired into
   four narrow effectors. Complete generic OAuth/MCP/OpenAPI transport, durable
   ingress, typed artifacts, reconciliation, revocation and production
   acceptance to unlock Zapier outcomes, Slack/Teams and handoffs. They join
   requester identity before authorized use; value-moving effects join
   PostgreSQL/market transport later.
4. **Finish distributed execution and the dark market spine.** #1786 landed
   request through claim plus Realtime/accounting foundations; complete one
   request-to-host-to-fenced-result-to-acceptance/settlement vertical path
   before training, model hosting or hardware.
5. **Run the shared production-load protocol.** First baseline the current
   connector/provider-free path; then test Postgres, Realtime, market and fleet
   scenarios in their owning lanes.
6. **Finish public discovery/remix/collaboration/moderation and rendered
   acceptance.** These are complete-product uptime surfaces, not optional UI.
7. **Build the model lifecycle.** Data manifests, F1/F2 training,
   content-addressed model artifacts, deployment aliases, permissionless
   serving, metering and settlement need explicit successors.
8. **Build organization authority, then adapters and assurance profiles.**
   Organization/RBAC/SCIM precedes Slack/Teams; enforcement/evidence primitives
   precede HIPAA or other profile pilots.
9. **Extend the same envelope to makers.** Start with bounded FDM/3MF work
   orders and objective inspection, then add CNC and higher-risk hardware only
   with stronger qualification and legal/safety evidence.

## Host actions that unblock work

1. Register `TinyAssets` at `https://tinyassets.io/mcp` in the ChatGPT workspace
   so provider-free rendered OAuth/read/write acceptance can run. Registration
   alone does not unblock BYOC acceptance; that still requires universe
   creation authority plus R2-1a/R2-1b and provider-attempt receipts.
2. Approve an isolated provider-free `/mcp` load environment and traffic
   envelope.
3. Provision `TINYASSETS_IDENTITY_FINGERPRINT_KEY`.
4. Provide read-only Supabase production inventory access and decide the
   production migration home.
5. Obtain specialist legal review before any forward, training or hardware
   route is advertised in a jurisdiction.

Everything else in this audit can proceed through separate claimed
OpenSpec/worktree lanes without using the founder’s Claude/OpenAI quota for
users.

## Review note

Three independent Codex agents audited:

- compute/training/inference/model hosting and maker hardware;
- Zapier outcomes, organizations/company brains and regulated profiles; and
- scale/concurrency, zero-host uptime, BYOC, discovery/remix, moderation and
  public acceptance.

All three returned the same substantive conclusion: the architecture is
coherent and the pure foundations are significant, but no full compute market,
training/model-hosting loop, Zapier-equivalent product, organization brain,
regulated profile, or thousands-concurrent envelope is proven end to end.
After factual and classification corrections were folded into this file, all
three independent final reviews returned `APPROVE`.

After the current-main restack, Claude Opus 5 independently returned `ADAPT`.
It found the recovered edge `502`, the wired—not dark—outbound boundary, the
dark market activation gap, #1784’s spec-only status, six new OpenSpec changes,
and the absent capacity-lock fence. Those findings are folded into this
revision; an exact-revision Opus re-review remains the merge gate.

Historical 2026-07-21 research already received opposite-provider `ADAPT`
reviews and was corrected. This completion audit adds no new external-research
build authority. Any future implementation derived from those reports still
requires its own current OpenSpec claim and required review gate.
