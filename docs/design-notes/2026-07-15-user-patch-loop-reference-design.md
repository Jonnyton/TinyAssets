# The patch loop is a user branch — reference design (2026-07-15)

**Status:** APPROVED by host 2026-07-15 (this session); Codex design review
verdict `adapt` — all four required adaptations applied below (sandbox gap made
build-blocking, PR-181 claim narrowed, merge-policy verbs marked as gaps,
remix promise scoped to published public designs).
**Basis:** host steer 2026-07-15 (verbatim intent, this session): the patch loop
is an ordinary **user-built branch**, not platform infrastructure. Jonathan is
*just another user* whose managed project happens to be the platform itself. A
game developer running "player comments → ready-to-merge patches → my repo"
through TinyAssets is the **same flow**; the only difference is which GitHub
the PRs target. All **published public branch designs** are shared, remixable
designs any user's chatbot can see and take (private branches stay host-side
and author-gated per commons-first — the remix promise does not extend to
them); owners review from any surface (phone included) whenever they get
around to it; merge policy is per-remix (manual approve / auto / timer).

## 1. Why now

- `change_loop_v1` (`fd5c66b1d87d`) — the only patch loop that ever ran — was a
  live-authored branch with no repo-backed form. The 2026-07-13 volume closure
  deleted it unrecoverably. Verified live 2026-07-15/16: both `fd5c66b1d87d`
  and `0ca6e9c97f65` return not-found via `read_graph target=branch`, and
  `_resolve_investigation_handler` (`tinyassets/bug_investigation.py:395`)
  returns its env-fallback branch id **without validating the branch exists**,
  so filings can enqueue investigation requests that no runner will ever pick
  up (PR-181's dispatcher request shows queued with zero runs).
- The 2026-06-25 cheat-loop retirement already rejected the "env-var-hardwired
  platform loop" shape. Rebuilding it that way would re-import the anti-pattern.
- PLAN §"Commons-first architecture": *the platform doesn't build features; the
  community evolves them via discovery + similarity + remix.* The patch loop is
  the flagship proof: the platform's own maintenance runs as a commons design
  its founder remixed like any user.

## 2. Product shape (the user story)

A project owner (game dev, platform founder, anyone):

1. **Finds** the "Patch Loop" design in the commons from their chatbot
   ("I want user feedback to turn into patches for my repo").
2. **Remixes** it into their universe (fork-copy; provenance recorded).
3. **Binds** their GitHub repo + credential (per-universe vault; PR-scope token).
4. **Chooses a merge policy:** `manual` (default — PRs wait for owner approval),
   `auto` (merge when gates pass), or `timer` (merge after N hours unless
   held). Jonathan's own remix: `manual` + **founder-OAuth required per merge**.
5. **Lives their life.** The loop runs in the cloud through nodes. Ready-to-merge
   PRs accumulate. From their phone, whenever: **approve / reshape (send back
   with notes) / reject.**

The loop's output contract is non-negotiable: **ready-to-merge PRs** against
the bound repo — branch, passing checks, description linking the originating
user request. Anything less is a draft the loop keeps working, not output.

## 3. Reference design (the commons artifact)

One published, public, remixable branch: **`patch_loop_reference`** — and it is
**repo-blind by construction**: the design carries no repository identity
anywhere. Binding a repo (+ credential) is a **user act at remix time** — the
founder binding the platform's repo is the same gesture as a game dev binding
theirs. A reference with no binding is inert: it can be imported, inspected,
and remixed, but nothing executes.

The reference ships as a **portable design artifact** (export/import format):
a self-contained document a user can hand to their chatbot ("import this
branch") or export from any universe to share. Same format the repo seed uses.

Node graph:

| Node | Does | Substrate it composes | Status |
|---|---|---|---|
| `intake` | Drain patch requests / comments filed against the bound project | wiki patch-requests + requests queue (dispatcher `request_type=bug_investigation` compatible) | **partial:** landed only for TinyAssets' existing global patch-request queue — `file_bug`/`submit_request` carry no project/repo/intake-source binding today, so project-scoped intake (a game's own request stream) is part of GAP G2 |
| `investigate` | Reproduce + analyze against the bound repo | cloud worker; sub-branch invocation (Phase A) | landed |
| `draft_patch` | Produce the fix on a branch of the bound repo | daemon-driven coding agent (`claude -p` / `codex exec` subprocess — hard rule 3) | **GAP G5 — build-blocking:** ordinary branch prompt nodes are NOT sandboxed today (`providers/base.py` `sandbox_workspace=False`; codex nodes may run `--dangerously-bypass-approvals-and-sandbox`). The 2026-07-03 engine-isolation posture covers `universe_intelligence` only. The loop must not run against real repos until coding-node sandbox/tool policy is enforced. |
| `verify` | Run the repo's tests/CI; loop back to `draft_patch` until green | conditional edges; gate-branch verdict shape (`docs/conventions/gate-branch-shape.md`) | landed |
| `present` | Open the PR + queue it on the owner's review surface | `github_pr` effector (vault-first credential) + auto-ship attempt ledger | effector landed; **review queue = GAP G3** |
| `owner_gate` | manual / auto / timer merge policy; reshape sends the PR back to `draft_patch` with the owner's notes | **GAP G6:** today `github_merge` accepts only branch-protection authorization + expected head SHA. The owner review queue, timer policy, and founder-OAuth-per-merge do NOT exist yet and must be built — no implied platform merge-policy enum. | gap |
| `merge` | Merge on approval (or policy) | `github_merge` effector (extended per G6) | partial |

**Parameters a remix sets (all user acts, none baked into the reference):**
target repo, credential binding (vault), merge policy (+ OAuth-per-merge
flag), intake source(s), verify command(s), cadence, **and the engine/daemon
capacity that runs it (G7)**.

## 4. Durability requirement (the lesson of 2026-07-13)

The reference design's `spec_json` **lives in this repo**
(`tinyassets/branch_designs/patch_loop_reference.json`) and is **seeded into
the commons idempotently at deploy** (re-seed heals a wiped registry). A commons
volume loss can never again delete the design class — only live remix instances,
which re-fork from the reference. Published instance + repo seed carry the same
design version id so drift is detectable.

## 5. Gaps (found live, this session; host steers 2026-07-15)

1. **G1 — Nothing to remix:** the commons has no patch-loop design (the
   reference artifact + durable seeding).
2. **G2 — Discovery + import/export gap:** the connector's `read_graph`
   targets couldn't enumerate shareable branch designs; `write_graph
   target=branch` only patches existing defs; and there is no **portable
   export/import** — a user must be able to hand their chatbot a design
   artifact ("import this branch") or export one to share. Remix must work
   end-to-end through the canonical handles.
3. **G3 — No owner review surface:** approve / reshape / reject queued PRs,
   phone-first (relay/app + website read of the same queue).
4. **G4 — Dead-ref dispatch:** `_resolve_investigation_handler` returns branch
   ids without validating existence; filings enqueue silently against dead
   refs. Fail loudly (hard rule 8) **on the trigger, never the filing**: at
   file time, validate the resolved handler exists; when it doesn't, enqueue
   nothing and record + surface an explicit failed-trigger status in the
   filing response — but the user's filing always persists (a requester's
   report is never lost because the project owner's loop is misconfigured).
5. **G5 — Coding-node sandbox (build-blocking):** branch prompt/coding nodes
   are not sandboxed today (see §3 table). Enforce sandbox/tool policy for
   `draft_patch`-class nodes before any loop touches a real repo.
6. **G6 — Merge policies + review verbs don't exist yet:** `github_merge` is
   branch-protection + expected-SHA only; the review queue, timer policy, and
   founder-OAuth-per-merge are new builds.
7. **G7 — Engine/daemon onboarding (host steer):** no user — the founder
   included — has ever been taken through binding their engines
   (subscription CLIs / local / API) or hosting daemon capacity to their
   universe. Therefore **no ambient, unbound daemon work runs anywhere**:
   universes execute only on capacity explicitly bound to them — the owner's
   own engines, capacity another user has offered, or cloud/platform capacity
   **explicitly offered and per-universe-bound** (this preserves the Forever
   Rule: browser-only users are not second-classed, and a bound loop runs
   24/7 in the cloud with no host online — what changes is that binding is
   always a user act, never ambient default). The current platform-global
   daemon working unbound universes is the wrong shape — the PR-181
   idle-churn on `default-universe` is a live symptom. Setup flow: at (or
   after) first contact the founder is offered "bind an engine so your
   universe can run"; until bound, the universe is honestly idle.

## 6. Slices

- **S1 — Reference design as a portable artifact + durable seed + fail-loud
  guard** (G1 + the G2 import format + G4): author `patch_loop_reference` in
  the export/import format, commit it to the repo, seed it idempotently at
  deploy, validate handler existence at file time. Repo-blind per §3.
- **S2 — Remix/import path on the connector** (G2): discover → import/fork →
  bind repo + credential → set policy, all via canonical handles from a
  chatbot; export any owned branch as the same artifact.
- **S3 — Coding-node sandbox ENFORCEMENT** (G5): fail-closed enforcement +
  tool policy for draft_patch-class nodes — S3 makes `coding_nodes_runnable()`
  return `False`, so such nodes REFUSE to run. S3 does NOT supply the per-job
  RUNNER that actually confines + executes them.
- **BLOCKER — per-job sandbox RUNNER (Phase 2, host-approved):** the runner that
  lets a `requires_sandbox` node execute confined is an explicit, separate,
  host-approved Phase-2 slice. Until it lands, `_sandbox_enforcement_available()`
  stays `False` on S1 AND S1+S3, so no repo-touching node ever runs. This is the
  hard dependency for a live patch loop, distinct from S3's enforcement.
- **S4 — Owner review surface + merge policies** (G3 + G6): review queue with
  approve/reshape/reject from phone; manual/auto/timer; founder-OAuth-per-
  merge; extend `github_merge` accordingly.
- **S5 — Engine/daemon onboarding + platform-daemon reshape** (G7): the user
  setup flow for binding engines/daemon capacity to a universe; retire
  platform-global daemon work (host-gated production change — decided
  explicitly, not slipped into another slice).
- **S6 — Dogfood proof:** Jonathan's chatbot imports/remixes the reference,
  binds the TinyAssets repo + his engines, and **PR-181 flows through his
  loop** to a founder-OAuth-approved merge. Friction found is product signal,
  filed and fixed.

Each slice ships with tests + opposite-provider review; surface changes get
the rendered-chatbot ui-test per AGENTS quality gates.

**Bundled deploy (corrected 2026-07-15 — supersedes "S1/S2 may land ahead of
S3"):** the patch-loop stack merges to `main` in dependency order (S1 → S3 →
S4 → S2 → S5) and ships as ONE deploy; **no slice deploys independently.** The
seeded reference's repo-touching nodes (`investigate` repo-read, `verify`
repo-exec, `draft_patch` repo-write/coding) are sandbox-required and honestly
**FAIL CLOSED**: the compiled node **refuses to execute at invoke time (before
any provider dispatch)** while a real sandbox RUNNER is unavailable
(`graph_compiler._sandbox_enforcement_available` — feature-detects
`tinyassets.sandbox_policy.coding_nodes_runnable`; always False on S1, and still
False on S1+S3 because **S3 is enforcement-only — the per-job runner is a
separate host-approved Phase-2 slice**, NOT part of S3). `present` / `merge` EMIT
`github_pull_request` / `github_merge` effect packets whose effectors resolve at
run time (`github_merge` lands with S4). So the seeded reference is never live
without its runner — S1 in isolation SEEDS a discoverable/remixable template that
cannot RUN unconfined (Codex r13 #1 / r14 #1-#2: it now provably refuses, and the
gate is NOT bypassable by an env var — availability comes only from the real
runner capability). **Merged-stack proof (integration-activated, NOT yet
passing).** The S1→S3→S4 fail-closed proof activates ONLY at INTEGRATION — it
requires all three together (S1's seeded reference + S3's sandbox enforcement +
S4's effector) and is NOT provable on S1 alone (repo-touching nodes fail closed
until S3's runner). The proof lives in S4's bundle e2e
(`tests/test_patch_loop_bundle_e2e.py`). S1's only obligation is to keep the
artifact contract stable: reference nodes live under **`spec.node_defs`** (the
structural envelope test pins this). The S4 bundle test MUST read
`spec.node_defs` (not top-level `node_defs`) and MUST **FAIL — not silently
skip** — when the artifact exists but its node contract is unreadable, so a
contract mismatch can never masquerade as a passing (or skipped) proof. As of
Codex r18 the S4 reader still checks top-level `node_defs` and the bundle test
stays skipped; that test-quality fix is S4-owned (routed to S4), not S1.

**Phase-2 execution boundary (Codex r11 #2; host "build execution first").** The
S1 reference declares the full intended loop with correct effect + gate
*contracts*, but the loop cannot execute end-to-end yet, and S1 does not build
the executor. The gap: owner review must happen AFTER the PR effector writes the
PR, but the graph's inline `owner_gate → merge` edge decides BEFORE the
post-graph PR effector runs. Closing it needs a **Phase-2 durable two-stage
pause/resume subsystem** — S1 graph interrupt/suspend after `present`, S4 resume
on the owner's review-queue decision, and the run engine carrying state across
the suspend — which then reshapes the inline `owner_gate → merge` into that
resume flow. Phase-1 scope (done here): the reference is a correct declared
TEMPLATE — `present` emits a `github_pull_request` packet carrying the changes
reference (`changes_json` from `draft_patch`, produced by the Phase-2 sandbox
coding node) + S4 `payload.review_queue` metadata; `merge` emits a `github_merge`
packet; the effect/effector names + `review_queue` keys align with S4's
`_BUNDLE_READY` expectations (S4 reads `spec.node_defs`). Do NOT restructure the
graph or build the resume engine before Phase 2.

## 7. Security posture

- Vault credentials never leave effectors; recommend PR-scope (`contents:write`
  + `pull_requests:write`) tokens; never in node inputs/outputs or logs.
- `draft_patch` sandboxing is G5 and build-blocking — the 2026-07-03
  engine-isolation posture (WebFetch-only, cwd-pinned, tool denylist) must be
  EXTENDED to coding nodes; it does not cover them today. A remixed loop must
  not become an exfiltration vector for the capacity host it runs on.
- OAuth-per-merge (Jonathan's flag): the merge effector requires a fresh
  founder-authenticated approval action, not a standing consent.
- Auto/timer merge policies require the verify gate green — no policy merges a
  red PR.
- Work runs only on user-bound capacity (G7) — no ambient platform compute to
  abuse.

## 8. Acceptance: the clean-slate founder walkthrough (host, 2026-07-15)

When S1–S6 are done, the end-to-end proof is NOT a checklist of slices — it is
the founder walking the entire journey **as a brand-new user**:

1. **Reset (host-gated production step):** run the clean-slate reset
   (`tinyassets/reset.py` — already clears universes, daemons, `universe_acl`,
   `founder_home`; preserves commons/wiki/runs). The founder's WorkOS sign-in
   stays valid, but the platform holds **zero state for his sub** — he is
   indistinguishable from a new user.
2. **Arrive:** connect the chatbot, hit the sign-in flow like any user.
3. **Auto-birth:** first authenticated contact creates + binds his home
   universe (welcome card — no magic words).
4. **Engine setup (G7/S5 flow):** the universe is honestly idle and says so —
   he MUST hit the "bind an engine/daemon so your universe can run" setup
   beat, and completes it like any user would (subscription CLI / local / API
   choice).
5. **Import the loop:** hand his chatbot the `patch_loop_reference` artifact
   (or discover it in the commons) and remix it into his universe.
6. **Bind:** his GitHub repo + vault credential + merge policy
   (`manual` + founder-OAuth-per-merge).
7. **Run:** file a patch request (the PR-181 scheduler issue is the natural
   candidate); the loop produces a ready-to-merge PR; he reviews from his
   phone; founder-OAuth approves; it merges.

Every stumble in that walkthrough is a product gap: filed, fixed, and the
walkthrough re-run. The program is done when the walkthrough is smooth — not
when the slices merge.

## 9. Explicitly rejected shapes

- Env-var-hardwired platform handler (`TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID`
  as the permanent mechanism) — retire fully once the goal-canonical binding
  points at a live remix (it becomes the compatibility fallback only).
- Hand-fixing filed patch requests outside the loop while claiming the loop
  works — dogfood over speed (host, this session).
- Any "platform-only" branch the community can't remix.
