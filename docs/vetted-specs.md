# Navigator-vetted specs

Specs for user-submitted ideas — bugs, feature requests, design proposals — that have cleared both navigator passes (safety + strategy). Dev reads from this file. Lead dispatches from this file. When a spec lands in code, both the pointer row in `STATUS.md` and the H2 section here are removed together (commit is the record).

This file is **navigator-owned and git-tracked, never wiki-writable.** No `BUG-NNN` cross-references — titles are descriptive. Each H2 heading is the anchor; slug-ify the heading to get the `#anchor` in pointer rows.

Rule context: `feedback_wiki_bugs_vet_before_implement` + `project_bug_reports_are_design_participation`.

---

# Deferred specs — needs scoping before dev-dispatchable

The rows below trace from the `project_daemon_souls_and_summoning` architectural landing (host directive 2026-04-22) plus the 2026-05-01 daemon-learning-wiki extension, soul/wiki/runtime boundary, and bounded-memory cap model. Each is strategy-cleared under the SHIP-IT default (primitive expansions that fit `project_user_builds_we_enable`) but needs a scoping session before dev picks it up — they touch tray UX, identity model changes, cryptographic primitives, or new data-model tiers that navigator alone should not scope unilaterally. Flagging here for visibility so they're not dropped; promote to full dev-dispatchable spec when lead + host schedule scoping.

---

## [deferred] Daemon roster + soul.md authoring surface

**One-line:** Tray/chatbot UX + backend for host-authored named daemons, each with a persistent soul.md identity file. Creating a soul = creating an inactive daemon. Summoning activates a specific named daemon. Hosts may summon as many daemons as their provider capacity supports; same-provider repeats show warning-only subscription/rate-limit estimates, not a platform cap.

**Foundational.** The specs below all depend on this one being scoped first — daemon-as-persistent-named-object is the substrate. Touches `workflow_tray.py` (new daemon list + editor UX), `workflow/daemon/` likely new submodule (daemon registry, soul persistence, activation lifecycle), `workflow/storage/` (soul path resolution under `$WORKFLOW_DATA_DIR/daemons/<name>/soul.md`), MCP surface (new actions: `daemons action=list | create | edit_soul | summon | banish`). The current `author_definitions` / soul-hash / runtime-instance substrate is transitional: preserve soul hash, fork, fingerprint, and runtime concepts, but migrate or rename them into a project-wide daemon registry rather than entrenching a fantasy-author-specific author model.

**Open scoping questions:** tray interaction pattern for soul editor (external editor vs embedded); chatbot-first daemon control wording; live-daemon soul-edit semantics (hot-reload vs require-banish-resummon); soul versioning schema; default-soul shape for users who never author one; migration path from today's generic `UNIVERSE_SERVER_HOST_USER` identity to named-daemons; relationship to `cloud-droplet` executor identity (is cloud-worker a single default-souled daemon, or multiple?); provider-plan estimate source for second-and-later same-provider warnings; daemon fleet process supervision at high counts.

**Needs scoping with:** host (UX + identity model), dev team (tray + storage), navigator (strategy + security of soul-spoof attacks).

---

## [deferred] Daemon learning wiki

**One-line:** Every soul-bearing daemon gets a host-local markdown wiki that records raw node/gate signals, maintains synthesis pages, and guides recursive self-learning according to the daemon's soul.

**Primitive shape:** The platform supplies the storage layout and signal-ingest contract, not a fixed personality curriculum. `soul.md` is the identity contract; `wiki/raw/signals/` stores immutable passed/failed/blocked/cancelled node and gate records; `wiki/pages/` stores maintained self-model, decision-policy, interests, failure modes, skills, and soul-evolution pages; `wiki/decision_log/` stores candidate work considered, chosen work, declined work, offers, and soul-policy conflicts; `wiki/soul_versions/` stores immutable amendments and forks; `wiki/claim_proofs/` stores domain claims and attestations; `WIKI.md` is the schema future daemon runs follow. The soul file defines "best version of itself"; the wiki helps the daemon evolve tactics and self-understanding toward that soul.

**Bounded memory contract:** The wiki has a hard size cap by default. V1 default users get an age-scaled cap that starts smaller and plateaus: target 16 MiB during the first month, 64 MiB by one year, then fixed at 64 MiB unless the host changes policy. Workflow-owned always-on daemons use the same contract with a larger default plateau of 128 MiB. Hosts may opt into `fixed`, `age_scaled`, or `custom` cap policies and raise caps with explicit storage/context warnings. Compaction keeps the daemon useful under the cap: raw signals are compact records with links to large artifacts, synthesis pages are rewritten in place, decision logs roll up by period/domain, and low-value memories are evicted unless protected by audit, claim-proof, or soul-version rules. Prompt memory is capped separately: the runtime loads a bounded memory packet, not the wiki; target 2k-6k tokens, hard cap 8k tokens of soul/wiki overhead for a normal run.

**Soul-edit rule:** The wiki may draft rare soul-evolution proposals, but it must not automatically rewrite the soul after failures. Failures first update tactics, known failure modes, and decision policy. Soul edits should clarify or mature the original spirit rather than replace it.

**Depends on:** Daemon roster + soul.md authoring surface. Soulless daemons continue using default platform memory/dispatch and do not get a personal learning wiki.

**Open scoping questions:** exact cap defaults by host tier; when to run synthesis passes (after every node/gate vs batched idle pass); how to prevent low-quality/noisy signals from corrupting the wiki; whether users can inspect/edit daemon wikis from tray/chat; whether host cap increases are manual-only or may auto-scale by daemon age/activity; whether repeated contradictions can force a soul-evolution review gate; whether users can publish selected wiki pages as remixable commons artifacts while keeping the default host-local.

---

## [deferred] Per-node/gate soul_policy field

**One-line:** Add `soul_policy: Literal['allow_daemon_soul', 'forbid_daemon_soul', 'require_verified_soul', 'use_node_soul', 'prepend_node_header', 'hybrid']`, optional `node_soul: str`, and optional domain requirements to node/gate definitions. Sibling to the (also-queued) `llm_policy` field — both are authoring decisions that shape how the daemon behaves on that node or gate.

**Depends on:** Daemon roster + soul.md authoring surface (the "host soul" referent must exist first).

**Open scoping questions:** hybrid-merge semantics (who wins on conflict); validation of node/gate-provided souls (are they user-writable untrusted content that navigator must vet?); precedence at run time (how prompt composition combines daemon soul + node/gate header + provided soul); does claim-time filtering reject incompatible daemon souls before execution; how domain requirements are expressed without hardcoding platform roles; which policies are advisory vs hard eligibility.

**Shares authoring surface with:** per-node llm_policy (dev-dispatchable) — when that lands, coordinate UX so both fields are surfaced together in the build/patch-branch spec flow.

---

## [deferred] Soul-guided daemon decision node

**One-line:** After each node/gate completion, a soul-bearing daemon enters a decision step that sees eligible work, soul policies, domain requirements, provider/capability requirements, wiki-derived preferences, decision history, and any offer/bid, then chooses, declines, or asks for capacity according to its soul. Soulless daemons use the default dispatcher policy.

**Depends on:** Daemon roster + soul.md authoring surface (the soul exists); daemon learning wiki (preferences and learned failure modes); per-node/gate soul_policy (eligibility); claim-time soul-fingerprint if a policy requires verified souls; paid-market/dispatcher task surfaces for offers.

**Audit requirement:** Each decision writes a durable record: candidate work considered, eligibility filters, offers, chosen work, declined work, soul-policy conflicts, and the daemon's stated reason. This feeds the daemon wiki and gives hosts/markets a reviewable trail when a daemon chases money, avoids work, or refuses soul-incompatible tasks.

**Open scoping questions:** deterministic audit trail for model-chosen claims; how much candidate metadata to expose to the daemon; whether a soul may decline all eligible work; starvation controls when many daemons prefer the same lucrative work; how to represent soul interests without hardcoding platform taxonomies; how default soulless policy maps to today's dispatcher; how claim-time filtering and post-run model choice split responsibility.

**Likely touch points:** `workflow/dispatcher.py`, `workflow/branch_tasks.py`, `workflow/producers/node_bid.py`, host-pool bid polling, decision logs surfaced in tray/chat, and runtime prompt composition for soul-aware decisions.

---

## [deferred] Branch-contribution ledger

**One-line:** Track `(daemon_id, node_id, step_count, earned_fraction)` across a multi-node branch run so branch-level bonuses can distribute proportionally across daemons that contributed (not just the finisher).

**Depends on:** Daemon roster + soul.md (daemon_id as first-class persistent identity).

**Overlaps with:** (1) existing `Sub-branch invocation primitive` spec (queued) — sub-branch invocation already needs to track which daemons executed which child-run steps; ledger plumbing is probably shared. (2) `Node checkpoints` spec (queued) — per-node earned-fraction already exists for node-level partial credit; branch ledger aggregates those upward. (3) `project_node_escrow_and_abandonment` — branch ledger is the escrow-tier above node-level. When both are implemented, there's one ledger with (daemon, node_id, earned_fraction) rows and a branch-level aggregator view.

**Open scoping questions:** step-count definition (langgraph step ≠ node if fan-out nodes have multiple inner steps); proportional distribution weighting (equal-per-step vs earned-fraction-weighted vs hybrid); privacy (branch ledger is claims-visibility vs contributor-visibility); partial-credit handling when a daemon contributes + abandons before checkpoint (probably zero per escrow rule, but interacts with aggregation).

---

## [deferred] Claim-time soul-fingerprint (anti-spoof)

**One-line:** Cryptographic primitive that lets a claiming daemon prove their soul is what they say it is, without the dispatcher having to trust claimer-asserted metadata. This also underpins node/gate domain requirements when eligibility depends on a verified claim or proof.

**Depends on:** Daemon roster + soul.md (souls are stable addressable entities).

**Open scoping questions:** fingerprint scheme (sha256 of soul.md content vs keyed HMAC with a platform-side secret vs on-chain signature once crypto ledger lands); enforcement level (advisory display in claim UX vs hard match against a registry); key management for hosts (every host needs to sign their souls — keypair management burden); interaction with soul-editing (does a soul edit invalidate outstanding claims with the old fingerprint?); whether fingerprint is required OR opt-in per node/gate (probably opt-in: `requires_verified_soul: bool`); how verified domain claims attach to a soul and who is allowed to attest them.

**Important but not urgent:** spoofing matters once daemon identity drives gate-bonus payouts. Today with no paid-market live, the threat model is thin. Spec when Paid-Market flag comes on AND gate-bonus primitive lands.

---

## [deferred] Flexible escrow splits — arbitrary distributions declared by the escrow-setter

**One-line:** Extends the paid-market post-a-request surface with setter-declared split primitives. The escrow-setter (per-request staker) can express **any distribution they want**: claimer-on-completion, cut-to-designer(s), gate-bonus pool, checkpoint partial-credit, real-world-outcome bonus, patronage, attribution-chain lineage cut, voluntary bounty-pool donation, platform-take. Platform provides templates for common patterns; setter can always customize.

**Critical role distinction** (`project_designer_royalties_and_bounties` §"Two distinct roles — designer vs escrow-setter"): the escrow-setter is NOT the designer. Staking money to run a node doesn't make you that node's creator; the designer identity is permanent and immutable on the artifact. Each request is a new escrow with its own distribution rules — the same node run by two different requesters can have two totally different distributions. Attribution chain stays the same; escrow varies per-request.

**Strategy rationale:** makes the escrow model express-the-setter's-intent rather than platform-mandate-one-pattern. OSS-commons strategy (0% to designers, 100% to claimer), patronage (high cut to a named designer), real-world-outcome stakes, quality-weighted splits — all are valid setter choices. Platform's job is to provide split primitives + a small template library; setters compose their own distribution.

**Depends on:** `project_node_escrow_and_abandonment` (base escrow model), `project_monetization_crypto_1pct` (platform-take floor), Attribution chain primitive (below — for lineage weights when setter chooses to cut the lineage), Minimum-royalty enforcement (below — platform-side floor that rejects non-compliant setter splits at escrow-setup).

**Open scoping questions:** template library shape (named templates like "standard" / "OSS-commons" / "patronage" / "real-world-outcome" / "quality-weighted"); template customization UX (fully editable vs template-lock-with-parameters); precision + rounding for percentage splits; behavior when setter's split violates a referenced node's minimum-royalty (rejected at escrow-setup — that's the minimum-royalty-enforcement spec's job); behavior when setter names a nonexistent recipient (reject with structured error); immutability of declared split once escrow is locked (probably immutable — changing mid-flight violates claimer expectations).

**Needs scoping with:** host (template library + what primitives setters can express), navigator (default-template shapes that reflect fair-distribution biases so setters have a good starting point), dev (escrow ledger columns + rounding invariants + split-validation at setup).

---

## [deferred] Minimum-royalty enforcement on NodeDefinition + BranchDefinition

**One-line:** Platform-provided knobs designers attach to their own work so escrow-setters can't post runs that free-ride past a declared floor. Adds `minimum_royalty: dict` field to NodeDefinition + BranchDefinition: `{default_percent: float, per_tier: {paid_market?: float, free_queue?: float, host_internal?: float}}`. Escrow-setup validates the setter's split against all referenced nodes'/branches' floors; rejects with structured error naming the violating node + floor if cut is insufficient.

**Strategy rationale** (`project_designer_royalties_and_bounties` §"What designers control about their own work"): most designers who want broad adoption pick 0% default and earn via voluntary escrow cuts + attribution-chain decay. Designers who want to monetize directly set a floor. Per-tier lets public work enforce a paid-tier royalty without blocking free-tier adoption — a designer can publish for free-queue use while requiring paid-market posts to pay them X%.

**Sibling designer knobs in the same memory** (either co-specced or called out as adjacent):
- **Private / access-gated node:** only specific users can post escrow for it. Escape hatch for proprietary work. Likely a separate `visibility` / `access_control` field (may overlap with existing branch-visibility from Phase 6.2.2).
- **Unpublished node:** exists only for the designer's own workspace. Simplest — a `published: bool` field; unpublished nodes cannot be escrow-posted by anyone but the designer.

**Depends on:** Flexible escrow splits (above — enforcement fires at escrow-setup validation); Attribution chain primitive (below — floor applies to designer named in the artifact's author field, so author identity must be durable).

**Open scoping questions:** floor-stacking when a branch references multiple nodes (sum of minimums vs independent per-node floors — probably independent, so setter must satisfy each); tier-naming (paid_market / free_queue / host_internal per memory — is there a catch-all `other` tier, or unnamed tier rejects); mid-life floor changes (designer raises floor after publishing — does that affect existing escrow setups with locked splits? Probably grandfathers existing escrows + applies to new setups only); interaction with remix — does a remix inherit the parent's floor, lower it, or reset it (memory is silent — probably remix is free to re-declare, but attribution-chain lineage cut still flows regardless, so setting 0% on remix doesn't escape lineage royalties); default shape for designers who never set a floor (default 0% = free commons matches memory §"Most designers who want broad adoption will pick 0% default").

**Needs scoping with:** host (tier naming + grandfather rules + remix-inheritance policy), navigator (interaction with fair-distribution + remix-lineage), dev (field schema + validation at escrow-setup + error-shape for floor violations).

---

## [deferred] Attribution chain primitive (remix provenance)

**One-line:** Lineage metadata on branches + nodes preserved through fork/remix/patch_branch. Carries parent-id + author + source-hash through N generations; queryable for royalty distribution.

**Strategy rationale** (`project_designer_royalties_and_bounties` §"Attribution chain"): multi-generation royalty flow (Carol earns → Carol 60%, Bob 25%, Alice 10% per suggested decay) requires durable lineage. Today fork/remix silently loses parent context. Chatbot auto-attributes on remix; deliberate declaration required to strip the chain. Makes "remix = collaboration" economically real per `project_convergent_design_commons`.

**Depends on:** `project_daemon_souls_and_summoning` (author_id is first-class — today's `author: "anonymous"` default on NodeDefinition isn't enough), Flexible escrow splits (above — needs author-id to route royalties).

**Open scoping questions:** decay function (hardcoded platform parameter vs per-split-template configurable — if hardcoded, what curve: geometric / linear / manual per-generation); lineage depth cap (unbounded vs max-10-generations to avoid ledger bloat); strip-chain semantics (chatbot-asserted "this is new inspired-by" vs human-ratified; audit trail for stripped claims); fork-diff threshold (does a 1-line edit count as "remix" earning lineage, or structural-novelty threshold navigator enforces); node-level vs branch-level lineage (probably both, independently tracked); handling when parent branch/node is deleted or privacy-flipped.

**Overlaps with:** the queued **Sub-branch invocation** spec — child-parent run linkage is execution-time provenance; this is design-time provenance. Should share lineage-schema where plausible.

**Needs scoping with:** host (decay parameters + strip-chain policy), navigator (fair-weighting bias), dev (lineage storage + query performance).

---

## [deferred] Real-world outcome evaluator hook (one escrow-template among many)

**One-line:** Extends the Evaluator primitive with "external outcome" variants that verify real-world signals (paper-published / MVP-shipped / contract-awarded / competition-won / revenue-threshold-hit). Used as **one common escrow-template** for setters who want to stake on external outcomes — not a canonical platform pattern.

**Framing correction** (`project_designer_royalties_and_bounties` §"Escrow design is open-ended"): real-world-outcome stakes are what a setter chooses to stake on, not what the platform mandates. A setter who cares only about a finished draft stakes on completion; a setter who cares about peer-reviewed publication stakes on that external signal. This spec ships the primitive that makes the latter expressible — the Evaluator variants + release mechanics. The distribution of the released bonus is whatever the setter declared in their escrow split (see Flexible escrow splits — could be "only finisher" or "split across all contributors weighted by navigator's fair-distribution calc"). The spec doesn't impose a distribution shape.

**Strategy rationale** (`project_real_world_effect_engine`): real-world outcomes are the product soul. Making external-signal-staking expressible is the direct economic incentive for setters who want to reward workflows that actually deliver. Setters who don't want to stake on externalities simply don't use this template. Platform supplies the template + ~5 common outcome-type evaluators; setters can author custom ones for niche cases.

**Depends on:** `project_evaluation_layers_unifying_frame` Evaluator primitive spec (the base Evaluator type this extends — itself not yet scoped), Attribution chain (above — needed when setter's distribution references lineage), Flexible escrow splits (above — the outcome-bonus slot is declared by setter, not platform).

**Open scoping questions:** which outcome signals are MVP-supported (peer-review status via DOI lookup? GitHub release published? self-attested + other-party-verified? on-chain contract awarded?); abuse vectors (how do we prevent self-attested "I published!" from draining escrow — probably requiring verifiable external signal OR multi-party-attested chatbot-judged claim); staker-defined vs platform-defined outcome types (probably both — platform ships ~5 common ones; stakers can author custom evaluators for niche cases); timeout + refund semantics (if outcome never arrives, does escrow refund to setter after N months?); tax / legal implications of platform-initiated outcome-bonus payouts (deferred per memory §"Deferred / open questions").

**Needs scoping with:** host (MVP outcome-type roster + staker-authored Evaluator policy), navigator (fair-distribution tree-weighting if setter chooses distributional shape), dev (external-signal plumbing — DOI APIs, GitHub-release webhooks, etc.).

---

## [deferred] Bug-bounty tracking + GitHub attribution

**One-line:** `file_bug` captures filer identity + optional `github_handle`. On ship (merged + deployed) + stability-period (7-30d) pass, reporter earns bounty from the 50%-of-1%-platform-take pool. Commit template auto-inserts `Co-Authored-By: <handle>` or `Reported-by: @handle` on bug-id-referenced commits. PR descriptions + release notes credit handles.

**Strategy rationale** (`project_designer_royalties_and_bounties` §"Bug + feature bounties" + §"GitHub attribution"): doubles user credit surface — bounty payout (money) + public GitHub attribution (reputation, portfolio, discoverability). Flywheel: platform volume → bounty pool → user-driven improvements → more volume. Reshaped bugs (like the maintainer-notes → describe_branch.related_wiki_pages reshape earlier this session) still credit the original reporter, possibly split with navigator if reshape was substantial.

**Depends on:** `project_monetization_crypto_1pct` live + platform-take accounting; `project_bug_reports_are_design_participation` framing (already landed); Fair-distribution calculator (below — for reshape splits).

**Open scoping questions:** stability-period duration (7d vs 30d vs platform-tuned-per-class); pool depletion semantics (defer payout until replenished, or pro-rate, or LIFO priority); low-quality-report rate-limiting + reputation to prevent bounty-farming (e.g. 5-report-per-week limit per filer, reputation decays on consistent rejections, navigator can ban abusive filers); bounty-amount schedule (trivial $5 / meaningful $100 / foundational $1000+ is illustrative per memory — needs platform-set table); handle collection UX (prompt-once-per-session in chatbot vs per-file_bug-call); handle validation (is `github_handle` verified against GitHub API, or accepted as-asserted with audit trail); payout rails (same crypto primitives as node-escrow or different?); tax / legal (deferred).

**Needs scoping with:** host (stability-period, amount schedule, handle validation policy, legal), navigator (reshape-split bias for the bounty-vs-navigator-cut decision), dev (file_bug schema extension + commit-template + post-merge stability monitor + pool accounting).

---

## [deferred] Fair-distribution calculator (navigator-adjudicator tooling)

**One-line:** Tool-assist for navigator's formal fair-distribution role. Given a payout event, compute a default split **within the rules the escrow-setter declared for that event**. Navigator reviews + overrides; dispute path escalates to host.

**Two distinct payout classes the calculator handles differently** (`project_designer_royalties_and_bounties` clarification):
- **Per-run payouts (setter-declared):** operate on whatever rules the escrow-setter declared for THIS run. Same node run by two different requesters can have totally different distributions. Calculator's job is to apply the setter's declared rules (e.g. "split across all contributors") using observed contribution data (step-counts, earned-fractions, attribution lineage). If setter said "only finisher," calculator just routes to the finisher — no fair-weighting needed.
- **Platform-set payouts (bug-bounty + navigator-reshape splits):** fully navigator-adjudicated from platform defaults. The 50%-of-1%-platform-take bounty pool routes by my fair-distribution heuristics — reporter vs navigator-reshape-cut vs (when applicable) dev-stipend. No escrow-setter involved; platform is the payer.

**Strategy rationale** (`project_designer_royalties_and_bounties` §"Navigator's fair-distribution role"): navigator is the only role that sees all contribution layers (dev/verifier/lead don't see full economics tree); natural place to adjudicate. Tooling makes the default computation transparent + reproducible; navigator's override is auditable; dispute path keeps the system human-appealable. Fairness bias baked into defaults: over-credit originators, under-credit shallow-relay remixes, reward structural novelty.

**Depends on:** Attribution chain primitive, Branch-contribution ledger (in daemon-souls deferred section), Flexible escrow splits, Real-world outcome evaluator hook, Bug-bounty tracking.

**Open scoping questions:** default-split formula (how much to each contribution layer at baseline — needs platform parameter table grounded in principles like "originator gets ≥25% regardless of remix depth"); override UX (CLI tool for navigator? MCP action? dispute-filing surface); transparency (is the computed split + navigator override public per-payout, or only visible to staker + payees); appeal SLA (how long do originators have to dispute; what does navigator produce in response — revised split + rationale, or refusal + rationale); repeat-payout pattern — for a frequently-used branch, does navigator adjudicate once per branch or once per event (probably once per branch with auto-apply, revisit on material contribution change); interaction with DAO weighted-votes governance (future) — does DAO override navigator's adjudication, or is it final.

**Needs scoping with:** host (fairness-bias parameters + dispute SLA + DAO-interaction), navigator (me — the tool needs to match my actual workflow and the fairness heuristics I'd apply manually), dev (the tooling itself — probably an MCP action + a persistent table for navigator-vetted splits).

**Importance:** this is the tool that makes navigator's new formal role executable at volume. Without it, each payout requires manual navigator computation, which doesn't scale past ~10/day. Priority should track paid-market + bounty-pool go-live.

---

## [deferred] RetroLab one-shot classic free-games branch

**One-line:** Community-authored plan for `retrolab-one-shot-classic-free-games-v1`, a 12-stage branch that turns a free-form classic-game request into exactly one of: a PASS `GameRecipe`, a NEAR-PASS `PatchBlocker`, or a BLOCKED family explanation.

**Source:** Workflow wiki `pages/plans/retrolab-one-shot-branch-core-v1.md`, synced to GitHub issue #358 as `request:docs-ops`. Companion wiki pages cover the adapter interface, capability matrix, patch router, recipe templates, and acceptance harness.

**Core invariant:** The branch must never invent legal facts, fabricate hashes, accept abandonware framing, accept title-screen-only proof, require manual install/payment/login steps, or claim local runner success before RUNNER-001..005 / PR-015 lands. PASS requires every critical and major evidence gate green, every hash pinned, every URL classified as primary, a resolved runtime adapter, an S3-allowlist runner plan, and a non-trivial shortcut-bound proof objective.

**Pipeline shape:** request intake -> candidate search -> legal classification -> artifact pinning -> family selection -> adapter capability -> config synthesis -> shortcut spec -> proof objective -> runner plan -> evidence grading -> catalog promotion. Failures become explicit blockers, not silent skips.

**Dispatch status:** Documentation-only until the local runner and named companion specs are available. Do not implement or redesign the branch from this pointer alone; use it as the durable intake record and require the companion pages plus the RUNNER-001..005 gate before runtime work.

**Open scoping questions:** exact source of the AuthoritativePoolRegistry entries for v1; how PR-015 runner gates map onto current Workflow branch execution primitives; whether the PASS/NEAR-PASS/BLOCKED catalog pages live only in the wiki or also need repo-tracked recipe fixtures; which opposite-family checker owns legal/evidence-gate review once runtime work starts.

**Needs scoping with:** host (legal-source policy and paid/free-game boundary), RetroLab branch author or navigator (intent-preserving companion-page review), dev (runner and branch-runtime feasibility), opposite-family checker (evidence gates and no-fabrication proof).
