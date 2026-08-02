# OpenSpec backlog triage — all 40 live changes premise-verified

**Freshness:** 2026-08-02, verified at origin/main `90978653` by four parallel
read-only classifiers (de-bloat program phase 3). Method per the stale-backlog
incident ledger: PR state over reachability, symbols-on-disk over checkbox
counts, supersession sweep over title matching.

## Headline

- **Zero DEAD changes.** Every premise checked held against code — the backlog
  is not rot; it is real work that is over-sized, un-owned, or host-gated.
- **5 LANDED-SYNC** (implementation shipped, needs sync/archive),
  **1 UNCOMPLETABLE**, **2 UNCLEAR**, **2 HOLD**, rest ACTIVE/READY.
- **Default `openspec archive` is unsafe for most of the tree**: it syncs ALL
  deltas, and 7 changes carry target-only deltas over capabilities that already
  exist as as-built specs (paid-market-economy, shared-goals-and-convergence,
  graph-execution-substrate, provider-routing, wiki-commons,
  live-mcp-connector-surface, external-effect-receipts). Archive only with a
  per-change sync-safety verdict from the table below.
- **Two phantom owners:** `activate-connector-requester-authority` and
  `activate-requester-host-engines` are cited as authoritative owners by 5
  changes — and inside constrain-set-engine's delta spec text — but exist
  nowhere. Syncing constrain-set-engine as-is writes dangling owners into
  canonical specs.
- **The drain was the de-facto owner of moving lanes.** With it off, those
  lanes need explicit STATUS rows, not a drain restart:
  `bind-host-principal-to-account` was claimed by the dead drain identity with
  unowned draft PR #2150 (14/29 done, 56 KB implementation);
  `distributed-execution` (18/108, D0 spine landed, 3 rows depend on it) and
  `harden-background-branch-execution-authority` (11/77, three modules + tests
  shipped dark) have NO owning row at all.

## Classification table

| Change | Class | Sync-safe? | Next action |
|---|---|---|---|
| activate-custom-agent-runtime-core | ACTIVE | no | continue codex lane (draft PR #2145); needs explicit STATUS claim |
| activate-custom-agent-runtimes | ACTIVE | no | tick discharged 2.1; gate 2.2-2.5 spawns against WIP limit |
| activate-hosted-preview-publication | HOLD (host-action) | no | park; zero agent-buildable tasks until Cloudflare account exists |
| activate-main-universe-spec-drain | HOLD (host-decision) | no | conflict: cloud drain build vs rollback test — host call filed in STATUS |
| agent-interchange-pipeline | LANDED-SYNC | YES | archive after universe-custom-agents (its 4.2 ordering); move 4.1/4.2 evidence to a monitoring row |
| bind-host-principal-to-account | ACTIVE (orphaned) | no | reap dead drain claim; resume from draft PR #2150 |
| build-brain-canonical-store | READY | no (own fence 3.1) | buildable next |
| build-forward-platform-capabilities | UNCOMPLETABLE | NO — actively false | retire the change; keep design.md ledger as a plain doc; 3 STATUS rows cite it |
| complete-independent-full-platform-targets | READY | no | execute its own 6.3: split unbuilt capabilities out so handoffs can finish alone |
| complete-plan-gated-platform-targets | READY (mega, 8/58) | no | split per capability before any build |
| connector-tool-selection-accuracy | READY (host-only left) | no | reclassify row host-action — no agent-buildable task remains |
| constrain-set-engine-provider-authority | READY | no (+ phantom-owner text) | start §2; fix dangling owner refs before any sync |
| data-commons-contribution | READY | no | build §2 manifest immutability |
| demand-side-signals | READY (0/49) | no (own prohibition) | run §0 revalidation first |
| distributed-execution | READY (orphan) | no | add STATUS row; carve ≤12-task slice from §2 |
| engine-os-sandbox | READY (spec-only) | no | author handoffs 2.1-2.4 |
| establish-postgres-control-plane | READY | no | only 2.1 agent-side; rest host-gated (Supabase) |
| harden-background-branch-execution-authority | READY (orphan, dark runtime landed) | no | add STATUS row; resume at 2.6 |
| harden-background-provider-execution-authority | ACTIVE (cloud-drain lane) | no | leave with that lane; checkboxes lie low (dark core landed as prose) |
| harden-branch-access-authority | READY (31/41) | no (6.7 load gate) | next 6.1 two-actor proof + 2.5; STATUS "waves 1-3" row is STALE (#1797 merged) |
| harden-production-load-evidence | READY | no (1.6/4.4 forbid) | build §2 protocol (tests/load/_protocol/ unclaimed) |
| moderation-and-abuse-response | READY | no | fence holds (#1662/#1667 still open drafts); claim the unowned §2 |
| operator-request-trigger-contract | READY (39/63) | no | slice per row; 4.9 unblocked today (#1718 retired /mcp-directory) |
| outbound-boundary-layer | READY (live momentum, no row) | no (6.3 pairing rule) | build 4.1-4.2 — unblocks V1 demo row |
| paid-market-live-price-discovery | READY (22/31) | no | build 5.1/5.2, 6.1-6.4; 5.5 is external-counsel host-bound |
| paid-market-track-e-wave-2-transport | READY | NO — highest overwrite risk, no archive guard | build 4.7; re-scope stale-unchecked 4.3 (013 migration + tests exist) |
| per-user-goal-canonicals | READY (17/22) | no (explicit guard) | best small build: 4.1-4.4 (~5 tasks, clean premise) |
| provider-attempt-receipts | UNCLEAR | no | re-verify gate 1.1 vs merged #1784 (its cited #1691 closed unmerged); row's "1.2/1.3 building" is stale |
| public-read-completeness | READY | no | build slice 1A (1A.4 self-declares ungated) |
| reconcile-external-connector-manifests | READY (18/49) | no (half-overwrite) | build §3; record the ~8-day unlogged 404-monitoring window (5.7) |
| reconcile-preflight-stray-writer-processes | LANDED-SYNC | YES (decouple 2.3 first) | 2.3 is another lane's OAuth acceptance — decouple, sync daemon-runtime-and-dispatch, archive |
| reconcile-universe-personification-relay | READY (28/33) | NO — 6.11 would overwrite shipped relay with reversed embodiment | build 6.4/6.9 only; NEVER default-archive |
| repair-chatgpt-connector-oauth-continuity | UNCLEAR | no | one rendered reconnect observation (1.2), then re-derive the delta's layer (attachment vs JWT) |
| repair-daemon-image-gh-cli-pin | LANDED-SYNC | YES | VERIFIED 2026-08-02: PR #2149 merged with ZERO reviews — 2.1's independent exact-head review never happened; obtain retro review citing d6072f29, then tick 2.1/2.2 (runs 30737655671 + 30737837143), sync, archive |
| retire-cheat-loop | READY (9/39) | no | §1-3 buildable now; largest genuine build available |
| retire-legacy-live-mcp-tools | READY (gate-blocked) | no | blocked at 1.1/1.5; NOTE trap 2.3-F: auth/provider.py:516-618 action-scope registry looks legacy but is load-bearing |
| retire-mcp-provider-secret-deposit | READY (gate-blocked) | no | #1746 was SPEC-ONLY (title-implies-runtime trap); 1.7 requires creating the phantom activate-requester-host-engines change first |
| test-identity-and-reset | LANDED-SYNC (partial) | SPLIT — identity-auth yes, test-identity-harness no | selective sync only; never default archive |
| universe-creation | READY (partial) | no | 3.3/3.4 uncompletable as written (phantom owners); 5.4-5.6 scripts flagged DO-NOT-RUN |
| universe-custom-agents | LANDED-SYNC | YES | VERIFIED 2026-08-02: 5.2's rendered clause is NOT satisfied — `output/user_sim_session.md` (2026-08-01) records acceptance incomplete (Claude spend limit; ChatGPT OAuth-continuity dead-end). Canary half IS green (assert-handles exit 0, 2026-08-02). Archive after a passing rendered custom-agent conversation; organic half decouples to the STATUS monitoring row |

## Execution verification (2026-08-02, same day)

Spot-verification of the two "cleanest" archive candidates found both blocked
by unmet gates the classifiers had over-credited — the archive count executed
today is therefore ZERO, honestly. Every LANDED-SYNC candidate funnels through
one blocker cluster: the ChatGPT OAuth-continuity bug (blocks rendered
acceptance on that surface), the host Claude.ai spend limit (blocks the other
surface), and review-less auto-merges (#2149: 0 reviews). Clearing the OAuth
bug or restoring a rendered surface unblocks three archives at once.

## Systemic actions (this program)

1. **Decouple acceptance evidence from sync/archive.** Three archive-ready
   changes are hostage to cross-lane acceptance tasks (OAuth acceptance,
   rendered demo, organic telemetry). Convention: organic/rendered evidence
   lives in a dated STATUS monitoring row, not as an archive-blocking task.
2. **Split-verdict changes need selective sync.** The default archive verb is
   wrong for test-identity-and-reset and reconcile-universe-personification-
   relay; sync deltas individually.
3. **Mega-changes split before build.** 110 open tasks across the three vision
   changes produce no behavior; each capability becomes its own ≤12-task
   change when (and only when) someone is about to build it.
4. **Create-or-kill the phantom owners.** 5 changes and 2 delta-spec texts
   reference the two nonexistent activate-* changes; either author them or
   re-point the references.
