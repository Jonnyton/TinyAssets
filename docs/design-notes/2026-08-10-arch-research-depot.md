# Architectural research: Depot (depot.dev) — agent sandboxes / Claude Code sessions

**Date:** 2026-08-10 · **Initial provider:** claude (Claude Code research session) ·
**Required reviewer:** codex (cross-provider gate per AGENTS.md § Project Skills) ·
**Style:** external-research-implications · **Sibling note:** `2026-08-10-subscription-platform-precedents.md`
(Depot is ranked there as "the de-risked posture to copy" for BYO-subscription; this note is the
full architecture study behind that ranking.)

All external claims below are stamped `[E]` (evidence: fetched 2026-08-10 from the cited source)
or `[I]` (inference from evidence). Depot's docs are markdown-addressable (`<url>.md`) and indexed
at `depot.dev/llms.txt` — cheap to re-verify.

---

## 1. Canonical summary

Depot (founded 2022, YC; ~$10M Series A Mar 2026 from Felicis/YC/Pioneer Fund; small team that
"more than tripled" during 2025; millions of builds/month) began as a Docker build accelerator and
has iterated into a general fast-compute platform: container builds → GitHub Actions runners →
Depot Cache/Registry → Depot CI → **Sandbox SDK** → **remote agent sandboxes ("`depot claude`")**
→ Depot Metal (bare-metal microVM substrate, Jul 2026) → Depot Code (agent-scale git hosting,
private beta Jul 2026). `[E: finsmes.com Series A; depot.dev/blog index; depot.dev/about via search]`

The agent product genealogy matters more than any single feature:

| Date | Step | What shipped |
|---|---|---|
| 2025-07-01 | **Claude Code sessions** | `depot claude` as a *session-file sync wrapper*: monitors Claude's session file in `$HOME/.claude`, syncs via Depot API → create/resume/list/share sessions org-wide, across laptop and CI. No sandbox yet. `[E: blog/now-available-claude-code-sessions-in-depot]` |
| 2025-08-13 | **Remote agent sandboxes** | `depot claude` defaults to launching an isolated remote sandbox: 2 vCPU/4 GB, <5 s start, persistent filesystem auto-mounted with repo + context, async-only (returns a session URL), $0.01/min metered by the second only while the agent is processing, auto-shutdown on agent exit. `[E: blog/now-available-remote-agent-sandboxes]` |
| 2025-10-18 → 2026-06-23 | **Sandbox SDK** | `@depot/sandbox` (TypeScript): programmatic microVM sandboxes — "direct access to the compute layer that underpins Depot CI". `[E: changelog; blog/now-available-the-depot-sandbox-sdk]` |
| 2026-05→07 | **microVM generation / Depot Metal** | Cloud Hypervisor on KVM on bare metal; JIT allocation, **no warm pool**, P50 0.6 s boot; CI + Sandboxes migrated to Metal, "microVM startup went from ~10 s to sub-second". `[E: blog/optimizing-microvm-boot-times; blog/announcing-depot-metal]` |
| 2026-07-29 | **"GitHub is the wrong shape"** | Thesis post: software delivery should be six primitives (source control, execution, artifacts, caching, identity, policy) that agents consume at machine speed. `[E: blog/github-is-the-wrong-shape-for-this-new-world]` |

**Target user:** engineering teams (org-scoped everything) who want Claude Code running async in
the cloud/CI with persistent context — a B2B dev-tool, not a consumer agent platform. `[I]`

---

## 2. Architecture findings

### 2.1 Sandbox architecture — genuine microVMs, JIT, no warm pool

- The 2025 agent sandboxes were **containers** (2 vCPU/4 GB, <5 s start). `[E: Aug-2025 blog]`
  The 2026 Sandbox SDK generation is explicitly **not** containers: "Each sandbox is a genuine VM
  with full syscall compatibility, with nothing stopping you from running Docker … starting nested
  virtual machines." They prototyped containers first and rejected them: "there was no replacement
  for an actual machine." `[E: blog/now-available-the-depot-sandbox-sdk]` Nested virtualization is
  supported on CI sandboxes (2026-05-20). `[E: blog index]`
- Hypervisor stack: **Cloud Hypervisor v51 on KVM**, bare-metal EC2 (i7i.metal-24xl → Depot Metal
  on 5th-gen AMD EPYC), Debian 13 hosts. `[E: blog/optimizing-microvm-boot-times]`
- **Boot time engineering** (the load-bearing trick): 7–9 s vanilla Ubuntu → 0.6 s P50 / 1.2 s P90
  via direct kernel boot of a minimal custom kernel (-50%), replacing cloud-init with the fw_cfg
  firmware device, replacing systemd with a custom parallel-init initramfs, kernel cmdline tuning
  (`clocksource=kvm-clock`, `tsc=reliable`, no serial console), and 1 GB hugepages backing memory.
  `[E: same post, full table]`
- **Scheduling is just-in-time**: "VMs only start when a build request actually arrives. There's no
  pre-warming and warm pool of standby VMs." Fast cold start made warm pools unnecessary. `[E]`
- **Storage**: qcow2 + Direct I/O; root disks and snapshots stored **in the Depot Registry
  OCI-style**, with multi-tier disk-chunk caching and on-demand chunk serving for missing chunks;
  Metal adds dedicated NVMe storage nodes over NVMe-oF/TCP, S3 for durability. `[E: microVM post;
  Metal post]` So the deployable unit is an immutable image pulled lazily, never a mutated host. `[I]`
- **Persistence between sessions**: agent sandboxes keep a persistent filesystem + conversation
  context per session; sessions can be resumed and **forked** (`--resume --fork-session`) — fork
  duplicates the sandbox filesystem state under a new session id. `[E: Aug-2025 blog; quickstart]`
  In the SDK generation, snapshots/persistent disks are "on the way" — not GA (sandboxes die at
  timeout, default 120 min, cap 24 h). `[E: SDK post + reference]`

### 2.2 Credential / secrets model

- **Agent sandboxes:** org-scoped secret store — `depot claude secrets add|list|remove`. Values are
  **write-only** ("never displayed"); injected into sandboxes as environment variables. Two Anthropic
  auth paths, documented side by side: `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` (recommended
  for Max subscribers) or `ANTHROPIC_API_KEY`. Git access via a repo-scoped **GitHub App** ("Depot
  Code") or `GIT_CREDENTIALS` / `--git-secret` for other hosts. `[E: quickstart; CLI reference;
  Aug-2025 blog]`
- **Depot CI secrets** (the mature sibling): KMS **envelope encryption** (AES-256-GCM), "plaintext
  values are never persisted and are masked in all log output", write-only after creation, org
  owners only; **secret variants scoped by environment, repository, branch, and workflow file**
  (2026-05-11); multi-line secret files (2026-04-01). `[E: docs/security.md; changelog]`
- **Gap:** the Sandbox SDK has **no secrets injection yet** (listed "not yet available" with
  snapshots and custom base images). `[E: SDK reference]`
- Note the tenancy shape: one `CLAUDE_CODE_OAUTH_TOKEN` per **organization** — a shared token for
  the whole team's sandboxes. That is a pooled-credential posture acceptable for a B2B team tool;
  it is exactly what TinyAssets' per-universe binding rule forbids for consumer multi-tenancy. `[I]`

### 2.3 Orchestration & session lifecycle

- CLI-first, **async-by-default**: `depot claude --session-id X --repository URL --branch B "<prompt>"`
  returns a dashboard URL immediately; `--wait` blocks; `--resume <id> -p "<prompt>"` continues;
  `--local` runs locally with the same session sync; `list-sessions` is org-wide and interactive.
  `[E: CLI reference; quickstart]`
- **CI integration** is just resume-by-convention: `depot/setup-action@v1` + `depot claude --resume
  pr-${{ github.event.pull_request.number }} -p "review …"` — a session per PR, shared between
  humans and CI turns. `[E: Jul-2025 blog]`
- No parallel-fleet primitive ("run N Claude Codes") is productized; parallelism is just N sessions.
  Their agent-loop thinking (blog 2026-05-13) is **sequential context isolation**: an `/orc` pipeline
  of subagents (Planner → Clarifier → human gate → Builder → parallel Reviewers → Reviewer Boss)
  passing "structured handoffs" (a Build Packet), never full history — "the main thread is not where
  the work happens. I steer." `[E: blog/context-isolation-in-coding-agent-loops]`
- **Internal orchestration of their own compute** (Depot CI): three-layer **Lambda durable
  functions** — Run λ (parse, compile job DAG) → Workflow λ (per-workflow state machine) → compute
  sandbox; SQS-fed; **entirely callback-driven, no polling**; every callback carries a timeout whose
  expiry wakes the orchestrator to mark work timed out ("preventing indefinite hangs from lost
  compute"); crash recovery by replay from checkpoints. `[E: blog/building-ci-with-durable-lambda]`

### 2.4 Observability / steering

- Web dashboard (`depot.dev/orgs/_/claude`): session list with status + timestamps, **full
  conversation history**, sandbox execution history, resume/start/fork from the browser; sessions
  shareable across the org. `[E: docs/agents/overview; changelog 2025-11-03]`
- SDK-level: streaming `logs()` with backpressure semantics (`SlowConsumerError` drops output rather
  than blocking), 16 MiB output cap, per-sandbox `activeCpuUsageMs` + `networkUsage` + `exitCode` +
  `errorMessage` properties. `[E: SDK reference]`
- Steering is coarse: prompt-per-resume + `--allowedTools` grants. No mid-turn approval UI; the
  human gate in their own loop is a CLI convention, not a product surface. `[E/I]`

### 2.5 Billing

- Agent sandboxes: **$0.01/min, tracked by the second, no 1-minute minimum**, accrues **only while
  the agent is actively processing**; sandbox auto-stops when the agent exits. Available on all
  plans, no included usage. `[E: pricing; Aug-2025 blog]`
- Sandbox SDK: same compute rate as Depot CI — $0.00005/vCPU-second (≈ $0.006/min for the default
  2 vCPU). Storage $0.20/GB/mo. `[E: pricing; SDK post]`
- **Model spend never touches Depot** — it rides the user's Claude subscription or API key. Infra
  and inference are cleanly separated invoices. `[E: quickstart]`

### 2.6 Ops maturity signals

Strong: four platform generations in four years ("Metal is the 4th iteration"); publishes deep
engineering postmortem-grade posts (boot-time tables, TLA+ verification post 2026-07-20, durable-λ
implementation notes); per-build mTLS certs; single-tenant builders "never shared across
organizations"; fresh EC2 instance per Actions job, destroyed after; KMS envelope secrets;
Tailscale/egress-filtering/PrivateLink options on Business. `[E: docs/security.md; blog index;
pricing]` Weaker: **no compliance certification (SOC 2 / ISO) mentioned anywhere in docs**; no data
retention policy for conversation history; agent product still "Claude Code only, more agents coming
soon" a year after launch; async-only; no MCP servers inside sandboxes; SDK beta missing secrets /
snapshots / custom images. `[E: docs/security.md; agents overview; SDK reference]`

---

## 3. Module-by-module comparison vs TinyAssets

TinyAssets modules per `PLAN.md` (§ Module Map) and as-built `openspec/specs/`. Verdicts:
**COPY** (adopt the mechanism), **LEARN** (adopt the principle, our shape), **AVOID** (their
choice is wrong for us), **N/A-ADV** (they have nothing; our advantage).

| TinyAssets module | Depot's answer | TinyAssets today | Verdict |
|---|---|---|---|
| **Daemon Platform — worker fleet + queue** (`daemon-runtime-and-dispatch` spec: file-locked single-winner claims, lease-aware recovery, supervisor backoff, auth quarantine) | Callback-driven durable-function state machine; **every callback has a timeout that wakes the orchestrator**; replay-based crash recovery; JIT compute, nothing long-lived | Leases + watchdog + healthcheck asserting liveness-not-existence — same invariants, process-shaped instead of replay-shaped | **LEARN**: our supervisor already encodes their invariants; the gap is our *long-lived writer* itself (see deploy row). Their "timeout on every wake-source" is worth auditing our lease/heartbeat set against — the `compatible_worker_count=0` wedge (memory: queue-blocked 2026-08-06) is exactly a "lost compute, nothing woke the orchestrator" class. |
| **Engine sandbox / isolation** (P1 concern: no OS engine sandbox; `converse` is in-process-confined: WebFetch-only, cwd-pin, rot-prone denylist) | Genuine microVMs, full syscall, Docker-in-VM, JIT sub-second boot, per-session persistent FS | In-process confinement only; sandbox is the PRODUCT unlock (memory: commit-learning-is-not-agency) | **LEARN + rent-don't-build option** (Implication #2). The durable pattern: *ephemeral compute + persistent per-identity disk*. Their rejection of containers after prototyping them is a data point for our lane: the target is a real machine boundary, not a hardened process. |
| **Providers / serving bindings** (`provider-routing` spec: subscription-only default, per-universe allowlist, auth-health quarantine) | The live proof of our shape: genuine `claude` CLI in a hosted sandbox on a pasted `setup-token`, API-key alternative always documented beside it, zero Anthropic enforcement observed (sibling note) | Same posture planned; per-universe (not org-pooled) bindings; multi-provider chains Depot lacks | **COPY the posture, not the tenancy**: their org-wide shared OAuth token is pooled custody — forbidden by our one-credential-per-universe rule. Copy: side-by-side auth docs, quiet marketing, infra-vs-model invoice split. |
| **Credential vault** (`credential-vault` spec: **cleartext + file perms as-built**; STATUS R2-1: vault fails OPEN into host creds) | Write-only secrets (unreadable after creation), KMS envelope encryption, masked in all logs, org-owner-only management, **scoped variants** (env/repo/branch/workflow) | Cleartext-under-file-mode; fail-open inheritance is the active P-lane | **COPY** (Implication #1): write-only semantics + scoping variants + fail-closed are all mechanism-level and portable. Their SDK's *missing* secrets injection also shows the failure mode of shipping compute before custody — we have the reverse ordering opportunity. |
| **Run transcripts / observability** (`get_status`, `output/*/notes.json`, conversation_store PR #2394, wiki) | Sessions are **first-class org objects**: listable, resumable, forkable, shareable, with full conversation + execution history in a web UI | `get_status` is a point probe; conversation_store is durable but has no browsing surface; no "list my universe's sessions" | **LEARN** (Implication #3): the unit users reason about is the *session/run as a named, revisitable object*, not a status snapshot. |
| **Deploy / infra** (compose-on-droplet; stop-writer fence; **failed deploy = ZERO containers**, 3 outages 2026-08-07; forward-only) | Immutable rootfs images distributed via OCI registry with lazy chunk pull; JIT boot of the *new* image; the old thing is never mutated or stopped-before-replacement — there is no fence because there is no in-place upgrade | Mutate-in-place: stop old writer → start new; failure strands prod at zero | **LEARN** (Implication #4): the direction (not the scale) transfers — prove-new-before-stop-old on the same box. Their bare-metal/microVM stack itself: **AVOID** building; it's a 4-generation specialist platform, not a weekend lane. |
| **Automations / scheduling** (persisted schedules, exactly-once events, 24/7 heartbeat) | Cron/webhook → SQS → durable λ; session-per-PR convention in CI. Nothing resembling a persistent always-on agent, channels, or heartbeat | 24/7 universe with ingress (Slack/MCP/mobile) is the whole product | **N/A-ADV**: Depot confirms the white space. Their agent is a *task* you launch; ours is an *account that lives*. Closest convergence risk is Depot Code's "future SDK for agent workflows" — watch. |
| **Billing / paid market** (fee on settlement; infra vs model split planned) | $0.01/min by-the-second **only while the agent is processing**; auto-stop on exit; usage caps; no included usage | Hosting economics unpriced; idle-cycle machinery exists | **COPY**: active-time-only metering + auto-idle is both the honest price and the survival trait the precedents note names (charge for compute/orchestration, let model spend ride the user's plan, never market API-cost avoidance). |
| **Brain / memory** | Persistence = filesystem + Claude's own session file. No memory abstraction, no learned state, no identity | Durable memory, souls, wiki, lineage | **N/A-ADV**. Notable mechanism anyway: their v1 shipped by *syncing `$HOME/.claude` session files* — the agent's native state file as the portable resume unit. Cheap trick for our own cross-machine writer moves. `[E: Jul-2025 blog]` |
| **Evolution / evaluation** | Failure fingerprints for tests; AI analysis of CI workflows; their agent loop uses multiple reviewers + a "Reviewer Boss" | Evaluator primitives, dual-family review | **LEARN** (minor): "Reviewer Boss consolidating parallel reviewer verdicts" is our judge-ensemble shape, independently converged. |
| **Distribution / API & MCP surface** | CLI + REST + TS SDK; **no MCP inside sandboxes**; not an MCP citizen at all | MCP-first user surface | **N/A-ADV**; also a reminder that their "agents" are headless-CLI-shaped, which is why they don't need consent surfaces we do. |
| **Harness & Coordination** (Three Living Files, lanes, cross-provider) | "GitHub is the wrong shape": delivery = six primitives — source control, execution, artifacts, caching, identity, policy — consumed by agents at machine speed | Our platform thesis is a superset (add memory, economy, provenance) | **LEARN**: independent validation of the primitives-not-apps direction (PLAN Scoping Rule 1). Depot Code (stateless git workers over S3 packfiles + transactional refs) is a candidate future substrate for our repo-delivery effects — **Watch**, private beta. |

---

## 4. Top-5 actionable implications

1. **[Adapt — feeds active lane R2-1] Vault mechanics: write-only, masked, scoped, fail-closed.**
   Depot's secret store never returns a value after write, masks in all log output, and scopes
   variants by environment/repo/branch. Our as-built vault is cleartext-under-file-mode and fails
   *open* into host credentials (R2-1). Smallest slice: make `credential_vault` reads write-only at
   the API boundary (summaries only), add masking to every log/exception path (memory:
   exceptions-carry-more-than-their-message), and make missing-credential resolution raise — which
   R2-1 already specifies. Verification: mutate-probe tests that a missing cred *fails*, not
   inherits. Files: `tinyassets/credential_vault.py`, `providers/base.py`. No STATUS change needed —
   strengthens the existing claimed row.

2. **[Adapt / Watch] Rent the machine boundary instead of building it.** The P1 "no OS engine
   sandbox" concern assumes we must build isolation on a 1.9 Gi droplet. Depot's Sandbox SDK (and
   the E2B/Daytona class) sells *metered genuine microVMs* at ~$0.006/min that boot in seconds,
   with full syscall + Docker. An engine adapter that runs a `converse`/engine turn inside a rented
   sandbox (env-injected, egress-controlled, destroyed after) would close the P1 as a *product*
   capability, not an infra project. Blockers making this Watch-not-Adopt: Depot SDK has **no
   secrets injection yet**, no snapshots, Node-only SDK, and custody/privacy review is mandatory
   (user code + credentials on a fourth party). Applies when touching: `engine-os-sandbox` lane,
   `tinyassets/providers/`, #1485 fail-closed seam.

3. **[Adopt] Sessions/runs as first-class browsable objects.** Depot's centerpiece is not the
   sandbox — it's `list-sessions` + a dashboard where any org member can open a session's full
   conversation and execution history, resume it, or fork it. Our `get_status` is a point probe and
   `conversation_store` has no listing/browsing surface. Smallest slice: a `sessions` view over
   conversation_store + run records (id, status, timestamps, last turn) exposed via the existing
   MCP read surface — the chatbot can then *show* a user their universe's history. Their
   **fork-session is our remix primitive at session granularity** — lineage-preserving session fork
   fits our commons model better than it fits their product. Applies when touching:
   `tinyassets/api/universe.py`, conversation_store, `get_status`.

4. **[Adopt — deploy pain] Prove-new-before-stop-old.** Depot never mutates running compute; every
   run boots a fresh immutable image, so "failed deploy leaves zero containers" is structurally
   impossible for them. Our stop-writer fence is the inverse and produced 3 same-day P0 outages
   (2026-08-07). The transferable principle at droplet scale: start the new container (distinct
   name/port), pass the candidate-load/health gate, *then* stop and swap the old — fence only the
   final cutover, not the whole deploy. Caution: Level-2 rollback territory reverses the
   forward-only policy → founder authorization per memory `deploy-pipeline-outage-window-and-level2`;
   but reordering start-before-stop within a forward-only deploy is not rollback. Applies when
   touching: `deploy-prod.yml`, `deploy/compose.yml`, stop-writer preflight.

5. **[Adopt — posture confirmation] The BYO-subscription mechanics are proven and copyable.**
   Depot is the live, funded, engineering-respectable instance of exactly our provider-binding
   shape: `claude setup-token` → platform secret store → genuine CLI in hosted compute, API-key
   path documented beside it, infra billed by the second, model spend on the user's plan, zero
   policy caveats and zero observed enforcement (sibling note, re-verified 2026-08-10). Two deltas
   to keep, not copy: per-universe (never org-pooled) token custody, and our multi-provider
   fallback chains (Depot is Claude-only — a real fragility their users carry). Applies when
   touching: R2-1, `credential-vault` spec, onboarding copy.

**Bonus (Watch):** Depot Code — stateless git servers over S3 packfiles with transactional refs,
built explicitly because "collaboration patterns are now the primary bottleneck" for agent fleets.
If its SDK ships, it is a candidate rail for our repo-delivery effects (memory:
repo-delivery-effect-not-emitted). Private beta; no pricing; revisit on GA.

---

## 5. Open questions / verification gaps

1. **Which substrate do agent sandboxes run on today?** Aug-2025 launch says containers; Jul-2026
   Metal post says "Depot Sandboxes" run on Metal microVMs. `[I: migrated]` — unconfirmed whether
   `depot claude` sandboxes specifically moved.
2. **Conversation/data retention** for synced session files and dashboard history: undocumented.
   Matters if we ever recommend Depot-class rails to users (their transcripts include repo content).
3. **Compliance**: no SOC 2 / ISO claim found in docs — surprising for a company selling to
   platform teams; either unpublicized or absent. Check before any rent-the-sandbox slice.
4. **Org-pooled OAuth token vs Anthropic ToS**: Depot's org-scoped `CLAUDE_CODE_OAUTH_TOKEN` shares
   one subscription across a team's sandboxes. No enforcement observed, but it is a *worse* custody
   posture than ours; do not treat its survival as clearance for pooling (precedents note § 3).
5. **Agent-sandbox secrets encryption**: KMS envelope encryption is documented for *Depot CI*
   secrets; the `depot claude secrets` store is described only as "stored securely", org-scoped.
   `[I: same infrastructure]` — unverified.
6. **Does `--allowedTools` still gate sandboxes, and did MCP support land after Aug 2025?** The
   limitation list is from launch; changelog shows no MCP entry through 2026-08.

## 6. Cross-provider review gate & pickup packet

- **Gate:** initial_provider = claude; **Codex must review before any build work** derived from
  implications #1–#5 (re-check depot.dev sources — they are `.md`-addressable — and the named
  TinyAssets files; verdict approve/adapt/defer/reject into `docs/audits/`).
- **Pickup packet (next actions, no new lanes opened by this read-only session):**
  - #1 folds into the already-claimed **R2-1** row (no new row needed; this note is context).
  - #4 → candidate STATUS row: "deploy start-before-stop reorder" — Files: `.github/workflows/deploy-prod.yml`,
    `deploy/compose.yml`; Depends: Codex review of this note; blocked-on-review.
  - #3 → `ideas/PIPELINE.md` candidate: "sessions as browsable objects + session-fork-as-remix" —
    Files: `tinyassets/api/universe.py`, conversation_store.
  - #2, #6 → Watch items; re-run when Depot ships SDK secrets injection / Depot Code GA.
- **Applies-when-touching cues:** deploy fence (#4), credential vault & provider bindings (#1, #5),
  engine-os-sandbox lane (#2), get_status/conversation surfaces (#3), repo-delivery effects (#6).

## 7. Sources (all fetched 2026-08-10)

- depot.dev/blog/now-available-remote-agent-sandboxes (2025-08-13)
- depot.dev/blog/now-available-claude-code-sessions-in-depot (2025-07-01)
- depot.dev/blog/now-available-the-depot-sandbox-sdk (2026-06-23)
- depot.dev/blog/optimizing-microvm-boot-times (2026-05-06)
- depot.dev/blog/announcing-depot-metal (2026-07-07)
- depot.dev/blog/building-ci-with-durable-lambda (2026-04-29)
- depot.dev/blog/context-isolation-in-coding-agent-loops (2026-05-13)
- depot.dev/blog/github-is-the-wrong-shape-for-this-new-world (2026-07-29)
- depot.dev/blog/now-available-depot-code-beta (2026-07-09)
- depot.dev/docs/agents/overview, /docs/agents/claude-code/quickstart, /docs/cli/reference/agents,
  /docs/api/sandbox-sdk-reference, /docs/security, /docs (nav), /llms.txt, /pricing, /changelog
- finsmes.com/2026/03/depot-raises-10m-in-series-a-funding.html; ycombinator.com/companies/depot
- Internal: `docs/design-notes/2026-08-10-subscription-platform-precedents.md`; `PLAN.md` modules
  (Providers, Daemon Platform, Engine & Domains, Uptime & Alarms, Harness & Coordination,
  Constraints); `openspec/specs/{credential-vault,daemon-runtime-and-dispatch,provider-routing}/spec.md`

---

## Codex opposite-provider review — DEPOT_VERDICT: ADAPT (2026-08-10)

Key adaptations to adopt over the body:
- Org-pooled OAuth caveat APPROVED + STRENGTHENED: Anthropic guidance makes plan credits
  PER-USER (cannot pool across teammates); our per-universe binding + aggregate-per-account
  budgets (task 1.10) are the complementary right pair.
- Deploy: HTTP health alone cannot prove deploy safety — add a SIDE-EFFECT-DISABLED candidate
  mode to the prove-new-before-cutover design.
- Custody: at-rest encryption needs a key hierarchy + OPERATOR BLINDNESS + rotation/revocation
  (sharpens task 1.8).
- Sessions: provider session files (~/.claude jsonl) are ADAPTER formats — TinyAssets' portable
  core contract stays conversation_store, never a vendor file. Retention/export/deletion/consent
  rules must accompany any sessions-as-objects surface.
- Not every workload needs microVM isolation; scope isolation tiers to workload risk.
- Corrections to our own state in the table: the engine-sandbox row understates the landed
  fail-closed admission seam; the fleet-wedge symptom is historical, not current.
