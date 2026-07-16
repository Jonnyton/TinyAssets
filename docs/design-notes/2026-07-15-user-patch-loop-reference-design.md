# The patch loop is a user branch — reference design (2026-07-15)

**Status:** draft — awaiting host approval (design-approval gate before build).
**Basis:** host steer 2026-07-15 (verbatim intent, this session): the patch loop
is an ordinary **user-built branch**, not platform infrastructure. Jonathan is
*just another user* whose managed project happens to be the platform itself. A
game developer running "player comments → ready-to-merge patches → my repo"
through TinyAssets is the **same flow**; the only difference is which GitHub
the PRs target. All branches are shared, remixable designs any user's chatbot
can see and take; owners review from any surface (phone included) whenever they
get around to it; merge policy is per-remix (manual approve / auto / timer).

## 1. Why now

- `change_loop_v1` (`fd5c66b1d87d`) — the only patch loop that ever ran — was a
  live-authored branch with no repo-backed form. The 2026-07-13 volume closure
  deleted it unrecoverably. Filings still enqueue investigations against a dead
  branch ref (live evidence: PR-181, request queued forever, trigger pointing
  at nonexistent `0ca6e9c97f65`).
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

One published, public, remixable branch: **`patch_loop_reference`**.

Node graph (each node = existing primitive; no new platform machinery):

| Node | Does | Substrate it composes |
|---|---|---|
| `intake` | Drain patch requests / comments filed against the bound project | wiki patch-requests + requests queue (dispatcher `request_type=bug_investigation` compatible) |
| `investigate` | Reproduce + analyze against the bound repo | cloud worker; sub-branch invocation (Phase A, landed) |
| `draft_patch` | Produce the fix on a branch of the bound repo | daemon-driven coding agent (`claude -p` / `codex exec` subprocess — hard rule 3), sandboxed (engine-isolation posture from the 2026-07-03 P0) |
| `verify` | Run the repo's tests/CI; loop back to `draft_patch` until green | conditional edges (landed); gate-branch verdict shape (`docs/conventions/gate-branch-shape.md`) |
| `present` | Open the PR + queue it on the owner's review surface | `github_pr` effector (vault-first credential, landed) + auto-ship attempt ledger |
| `owner_gate` | manual / auto / timer merge policy; reshape sends the PR back to `draft_patch` with the owner's notes | gate claims + effector consent (landed verbs); **new:** founder-OAuth-per-merge option |
| `merge` | Merge on approval (or policy) | `github_pr` effector |

**Parameters a remix sets:** target repo, credential binding, merge policy
(+ OAuth-per-merge flag), intake source(s), verify command(s), cadence.

## 4. Durability requirement (the lesson of 2026-07-13)

The reference design's `spec_json` **lives in this repo**
(`tinyassets/branch_designs/patch_loop_reference.json`) and is **seeded into
the commons idempotently at deploy** (re-seed heals a wiped registry). A commons
volume loss can never again delete the design class — only live remix instances,
which re-fork from the reference. Published instance + repo seed carry the same
design version id so drift is detectable.

## 5. Gaps this design closes (found live, this session)

1. **Nothing to remix** — the commons has no patch-loop design (G1: the
   reference artifact + seeding).
2. **Discovery gap** — the connector's `read_graph` targets couldn't enumerate
   shareable branch designs; `write_graph target=branch` only patches existing
   defs. Remix must work end-to-end through the canonical five handles
   (G2: discovery + fork on the public surface).
3. **No review surface** — approve / reshape / reject queued PRs, phone-first
   (G3: the owner console; relay/app + website read of the same queue).
4. **Dead-ref dispatch** — filings enqueue against nonexistent branch defs
   silently; the dispatcher must fail loudly (fail-loud rule) when the resolved
   handler doesn't exist (G4: guard + surfaced error on file response).

## 6. Slices

- **S1 — Reference design + durable seed** (the artifact; G1 + G4 guard).
- **S2 — Remix path on the connector** (discover → fork → bind repo/credential →
  set policy, all via canonical handles from a chatbot; G2).
- **S3 — Owner review surface + merge policies** (approve/reshape/reject from
  phone; manual/auto/timer; founder-OAuth-per-merge; G3).
- **S4 — Dogfood proof:** Jonathan's chatbot remixes the reference, binds the
  TinyAssets repo, and **PR-181 flows through it** end-to-end to a founder-
  approved merge. Friction found during S4 is product signal, filed and fixed.

Each slice ships with tests + opposite-provider review; S2/S3 surface changes
get the rendered-chatbot ui-test per AGENTS quality gates.

## 7. Security posture

- Vault credentials never leave effectors; recommend PR-scope (`contents:write`
  + `pull_requests:write`) tokens; never in node inputs/outputs or logs.
- `draft_patch` runs under the engine sandbox posture (WebFetch-only, cwd-pinned,
  tool denylist) — a remixed loop must not become an exfiltration vector for
  the host it runs on.
- OAuth-per-merge (Jonathan's flag): the merge effector requires a fresh
  founder-authenticated approval action, not a standing consent.
- Auto/timer merge policies require the verify gate green — no policy merges a
  red PR.

## 8. Explicitly rejected shapes

- Env-var-hardwired platform handler (`TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID`
  as the permanent mechanism) — retire fully once the goal-canonical binding
  points at a live remix (it becomes the compatibility fallback only).
- Hand-fixing filed patch requests outside the loop while claiming the loop
  works — dogfood over speed (host, this session).
- Any "platform-only" branch the community can't remix.
