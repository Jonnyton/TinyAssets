# Distributed-execution — open findings ledger

**Opened:** 2026-07-20, on resuming Kimi Code's lane after its credit ran out.
**Purpose:** one durable place for findings produced by the standing fleet, so nothing
is lost between rounds. Kimi's `output/s2-gate/s2-fix2-report.md` remains the canonical
S2 review-cycle log; this ledger is the *cross-slice* open-items view.

**Fleet:** `>=4` Codex + `>=4` Claude/Fable `peer_agent.py` lanes held continuously by
the `.claude/hooks/fleet_floor_guard.py` Stop hook. Status: `python scripts/fleet_status.py`.
Lane artifacts land in `C:/Users/Jonathan/Projects/TinyAssets/output/s2-gate/`.

---

## Live state (2026-07-20)

**S2 fix-5 is COMMITTED at `eb793409`** on `feat/patch-loop-leasestore-fix2` — ledger-anchored
one-shot completion + taxonomy closure. Codex built it but its sandbox denied writes to the
worktree git metadata, so the commit is host-side. Verification was **independently re-run
before committing**, not taken from the builder's report: 156 passed focused; ruff clean on
the 3 changed files; vault CORE zero-diff; scope exactly 3 files (+1202/-19); and the
daemon-route failure **ID set is byte-identical** to the same suites at `5a307576`
(11 failed/127 passed both sides — pre-existing, no regression and no masked pass/fail swap).
**Dual-family gate is firing on `eb793409` now.**

> Method note: the first ID-diff I ran reported "identical" against two *empty* sets, because
> pytest's ANSI codes meant `grep '^FAILED'` matched nothing. Re-ran with `--color=no`. A
> green result from a comparison that matched zero rows is the same vacuity trap this program
> keeps finding in its own tests — check that a diff actually compared something.

**Resolved host questions:**
- **§13.18 load — PostgreSQL is NOT required** (`codex-load-architecture.md`, fails-tunable).
  The filesystem MVP does not pass as-is, but can likely survive on one SQLite writer after
  S4 protocol changes. Decision: build S4 around SQLite as sole job/lease authority, remove
  JSON and poll writes from the hot path, fix transaction-time authority, run the load gate
  early — and **do not approve the current S4 brief unchanged**. Exact from code: one
  concurrent writer globally (`BEGIN IMMEDIATE`), WAL, `synchronous=FULL`, and every
  30s-heartbeat takes that same global lock. No measured numbers exist; all capacity figures
  are UNVERIFIED estimates.

**Still open for the host:** the orphan effect route needs an owning slice
(`fable-orphan-effect-route.md`, confirmed-orphan).

### fix-5 GATE: **BOTH FAMILIES REJECT `eb793409`** — independently, on different defects

- **Fable: reject (CRITICAL)** — the completion authority is forgeable *within its own stated
  boundary*; machine-reproduced. Detail below.
- **Codex: reject (High)** — public past-expiry replay still misfiles stored corruption as a
  client 409. Repro: legitimately complete, then set `status='leased'`, clear the accepted
  columns, and set `lease_expires_at` one second in the past. The direct store correctly
  raises `StoredStateCorruptError` ("completed event exists but job row is not terminal"), but
  `complete_job` runs its row-status/expiry preflight (`execution_jobs.py:185`) *before* the
  store consults its task-scoped `completed` ledger, so the public path returns
  `StaleLeaseError` / 409. Same shape as the taxonomy defect fix-5 was built to close, one
  layer up.

Neither family approved, and neither found the other's defect — two independent rejects on one
commit. That is the dual-family rule working exactly as intended.

#### Fable's finding in detail (`gate-verdict-fable-fix5.md`)

**The builder's own stated invariant is false.** The commit message said the anchor is
"tamper-resistant only while schema objects remain intact… the open question for the gate."
The gate answered it by *reproducing* a durable, replay-clean completion of a body the
validator **never signed**, with every trigger and both unique indexes intact.

Root cause: the append-only triggers (`lease_store.py:226-234`) block only **UPDATE and
DELETE** on `lease_events` — **INSERT is a data-row write and is allowed**. The
generation-scoped unique index blocks a *duplicate* `result_submitted` within one
`(task_id, lease_id, fence)`, and the completion `count != 1` gate catches duplicates.
**Neither blocks a singleton anchor for a generation that has no genuine event.** So the
attacker doctors the row onto a fabricated generation `(L2, F2)`, INSERTs one anchor with
`content_sha256 = H'`, and completion accepts. Both routes fall: the active path appends a
forged `completed` event (task-scoped index has room), and the terminal-replay path reuses
the genuine task-scoped `completed` while comparing an attacker-doctored column against
itself — so the "anchor is the sole surviving witness" assumption fails.

> **"No count/index layer can close this, because the substrate permits fresh-generation
> INSERT."**

That is a proof that **fix-6-as-more-armor is impossible**, not an opinion. It is the fifth
consecutive instance of the identical root class: fix-2 receipt fields -> fix-3 row-status +
unfiltered event -> fix-4 row-status routing key -> fix-5 attacker-chosen generation. The
earlier ledger note said the simplification trigger should fire on a *sixth forgery vector*
rather than on the TOCTOU. **It has now fired.**

What the gate found SOUND and worth salvaging: the taxonomy 500-vs-409 split, the atomic
migration (individual `execute()` in one `BEGIN IMMEDIATE`, index-shape validation, typed
failure on legacy-unanchored rows), and the fix-4 reopen guard — verified non-vacuous. The
gate's phrasing: these are *"well-built — but they harden the wrong layer."*

Why the anchor pins missed it: every anchor test doctors **within the current generation**
(UPDATE-doctor authoring path). Not one test moves the row onto a fabricated generation and
INSERTs a matching anchor. `test_foreign_result_event_…` inserts a foreign-generation event
but leaves the row on the genuine generation, so it is filtered out — it proves the opposite
of coverage.

### The big open question: should S2 RETIRE most of what five rounds built?

`fable-s2-simplification.md` (**path-b**) argues the anchor/receipt machinery defends an
adversary that **cannot exist**:

- B2 daemons never touch the SQLite file — B2 is an HTTP protocol; daemons are remote machines
  reaching `tinyassets.io/mcp` through the Cloudflare tunnel with OS-keystore keys and
  <=5-minute tokens. No SQL access of any kind (plan:607-700, :1144).
- Everyone who *can* reach the file has **full** access, not row-only. SQLite has no privilege
  system: no connection can be granted `UPDATE lease_tasks` while denied `DROP TRIGGER`.
  **Fix-5's own migration docstring concedes this** (`lease_store.py:277-283` @ `eb793409`).
  So the "schema-intact, data-rows-only" adversary is **unoccupiable** — what that boundary
  really describes is the control plane's own code paths: **bugs, not adversaries**.
- Single-writer is explicit plan through B2 and beyond (plan:1226, :1283, :1307); the
  1,000-daemon test scales API clients, not DB writers (plan:1158).

Proposed fix-6 **reshape, before S2 merges** — RETIRE receipt rederivation, anchor enforcement,
write/replay count gates and their migration; KEEP submission-time S5 verification, CAS +
fences, partial UNIQUE indexes, append-only triggers, slim taxonomy; ADD one Ed25519
re-verification at completion + the in-transaction clock fix. Timing argument: `LeaseStore`
has **zero production instantiations** and there are no users, so pre-merge is the cheapest
this reshape will ever be.

**CROSS-FAMILY VERDICT: `partial`** (`codex-pathb-gate.md`) — *the conclusion survives, the
reasoning does not.*

- **The "unoccupiable adversary" claim is FALSE, and Codex proved it empirically** by running
  SQLite 3.50.4: the per-connection **authorizer API** can allow `UPDATE` while denying
  `DROP TRIGGER` (`has_set_authorizer True` / `update_result 2` /
  `drop_trigger DatabaseError not authorized`). A broker process can expose constrained DML
  without exposing the file, and **a future Postgres deployment would naturally grant DML
  without schema ownership**. So the row-only actor is entirely constructible.
- **But it is absent here.** Exhaustive branch grep found no `set_authorizer`, no SQL broker,
  no constrained connection, no direct SQL endpoint; `LeaseStore` connections have
  unrestricted SQL capability (`lease_store.py:167-175`).
- **The accurate invariant** is therefore *"No deployment currently grants an untrusted actor
  DML access to the lease store"* — **not** "SQLite makes such an actor impossible." Writing
  the categorical version into the plan would bake in a claim that silently breaks the moment
  anyone adds Postgres or an SQL broker.
- **B2 access boundary confirmed.** The historical four-worker co-mount *did* create an
  out-of-process filesystem actor — but with full file/schema power, not row-only — and commit
  `764a4f65` retired those workers (ancestor of `eb793409`); compose now mounts the data volume
  only into the daemon. Two remaining **full-compromise** paths deserve naming: the log sidecar
  holds the Docker socket (root-equivalent; `:ro` on the socket path does not make Docker API
  requests read-only) and the root backup job exports/restores the whole volume. Neither
  produces the narrow adversary; both enlarge the full-compromise domain.
- **Retirement list is too aggressive.** Reshape before merge and retire the anchor tower, but
  **preserve a compact receipt/event consistency mechanism that the signature check does not
  replace.**

> This is the clearest case of the session's pattern: Fable's *conclusion* was right and its
> *justification* was categorically false. Adopting it unreviewed would have written a false
> invariant into the plan. The fix was one lane of opposite-family review — the same move that
> corrected the S6 amendment and Edit 3 of invariant 26.

**Status: still NOT ACTED ON** pending the one remaining question — whether the proposed
Ed25519 re-check actually closes the *demonstrated* fix-5 forge, which turns on whether
`lease_id`/`lease_fence` are inside the signed `ExecutionResultBodyV1`
(`fable-does-signature-close-forge.md`, in flight). If they are not signed, Path B does not
close it either and fix-6 needs a different shape. A contingent fix-6 brief is being pre-drafted
(`fable-fix6-reshape-brief.md`) with a hard requirement to name, for every retired guard, what
property it provided and what now provides it — deleting a guard whose property has no
replacement is how a simplification becomes a regression. The two fix-5 gates were left
running rather than killed on an unverified recommendation; if Path B confirms, their verdicts
still say whether the KEPT parts are sound.

If Path B holds, the honest read is that five rounds were not spent on a bad design — they
were spent hardening against a threat model nobody had checked. That is a gate-coverage
lesson, not a code lesson, and it is the same root as S2-3 (four rounds of forgery-hunting
missed a classic TOCTOU because no lane probed the time axis).

### §13 criterion 1 is NOT claimable today

`fable-verdict-index-backfill.md` (**gaps-4**): all four merged slices (S0/S1/S3/S5) lack a
recorded dual-family verdict against the **merged** sha. "Codex reviewed it several times" is
not dual-family approval, and neither is "Fable approved an earlier revision". Combined with
the S1 trust-root `reject`, the merged substrate is less verified than the slice table implies.

---

## The recurring defect class

Five independent findings, one shape: **an authority boundary is asserted at one layer
that the substrate underneath never actually establishes.** The system trusts a party's
own claim about itself, or hands a component more authority than its role needs.

| Slice | The trusted party asserts | Artifact |
|---|---|---|
| S2 (5 rounds) | its own result hashes -> receipts -> ledger events -> row status | `gate-verdict-codex-fix{,3,4}.md` |
| S6 HIGH-1 | its own sandbox pins; both sides of the check come from the supplier | `fable-s6-check.md` |
| S7 HIGH-1 | broker gets a write handle to the terminalizing store | `fable-s7-attack.md` |
| S7 HIGH-2 | one unscoped S3 credential lets a broker sign a result and complete | `fable-s7-attack.md` |
| S8 OPEN-1 | "credential-free staging" with no rule making it true | `codex-s8-amendment.md` |
| **S1 (LANDED)** | its own signing root — `create_execution_capsule` takes any caller-supplied `SigningKey` + arbitrary `signing_key_id`, and verification takes a caller-supplied `VerifyKey` + `signing_key_active=True`. Crypto is sound; the caller supplies its own trust root. **Sixth instance, and the first in merged code.** Reachability under determination (`codex-s1-trustroot-reach.md`) | `codex-landed-substrate-audit.md` (**reject**) |
| **S14 settlement** | the PAYER asserts "my replay disagreed" — blocking payment, triggering refund, and posting negative reputation, with the patch already fetched from CAS. No defined adjudicator, so whoever asserts first wins | `fable-structural-audit.md` HIGH-B |

### Proposed closure: invariant 26 + a mandatory gate probe

The structural audit's answer to "does one principle close this class?" was **yes, but the
sentence alone provably does not work** — invariant 22 already said essentially this, was
scoped to market attestation, was enforced nowhere, and instances 2-4 happened anyway. The
contribution is the **gate probe**: *"for each decision, which comparand or precondition
could the constrained/paid party have authored?"* Both sides, or the load-bearing one, = RED
without needing an exploit demo. It retroactively catches S2 fix-2/-3/-4, S6 HIGH-1,
S7 HIGH-1/2 and S8 OPEN-1 — defects that cost multi-round gates to find live.

A same-family stress test (`fable-invariant26-stress.md`, **adopt-with-edits**) found the
probe mechanically decidable and correct on **10 of 13** real decisions, but caught three
defects in the proposed text: "eligibility" in the prohibited class makes §9.2 matching
**unimplementable** (no independent source exists or can exist pre-execution for a remote
host's RAM or image); no trust-domain scope, so it outlaws the B2 owner-BYO completion that
§13 requires; and the "constrained/paid party" wording **misses the audit's own HIGH-B**,
since a payer-authored replay verdict is authored by neither. Four exact edits proposed,
plus a rider to fold the S6 pin amendment in the same commit. **Cross-family gate in flight
(`codex-invariant26-gate.md`) — nothing adopted until it returns**, since both the proposal
and its stress test came from the same family.

### A SECOND class the probe is blind to: reset-by-multiplicity

The stress test constructed a defect the probe structurally cannot see: the attacker does not
author a comparand, it **multiplies the decision** — fresh identity, attempt, lease, or
idempotency key — until an aggregate constraint resets. Every individual decision is properly
provenanced. Known instances: the per-capsule **model budget reset** (lapse the lease,
re-claim, get a fresh budget, indefinitely, billed to the owner) and **sybil reputation
reset** (abandon `daemon_id`, re-enrol). A dedicated audit returned **7 findings**
(`fable-reset-multiplicity.md`). The probe interrogates one decision's provenance and is
blind to cardinality across decisions; stretching invariant 26 to cover it would destroy its
one-question decidability, so it needs its own treatment.

---

## Open findings

### S2 — fenced lease store (fix-5 build in flight)

| ID | Sev | Finding | State |
|---|---|---|---|
| S2-1 | HIGH | Terminal rows reopenable by doctoring `status` back to `leased`, routing around replay verification; a second completion succeeds. Exactly-once must be enforced AT WRITE TIME (zero `completed` events for the generation before completing). | fix-5 scope (Item 0) |
| S2-2 | MED | Malformed persisted candidate hashes surface as client-409 instead of 500-class corruption (`execution_jobs.py:305`, `lease_store.py:858`). | fix-5 scope (taxonomy F1-F3) |
| S2-3 | HIGH | **CONFIRMED — TOCTOU, a different class from findings 1-4.** No relevant operation samples authoritative time after lock acquisition. `_transaction()` runs `BEGIN IMMEDIATE` behind a **30-second busy timeout**, so a writer can wait up to 30s and then proceed on 30-second-stale time. Claim (`:539` before `:541`), heartbeat (`:700-701` before `:702`), candidate submission and completion (caller-supplied `now`, normalized pre-lock) all check expiry with stale time, and **no CAS statement carries an expiry predicate** (`:720-727`, `:928-945`, `:1063-1083`). Evidence: `codex-stale-time-verify.md` @ `5a307576`. | fix required; **not in fix-5 scope** |

**On S2-3's fix:** the caller-supplied `now` makes this worse, not safer — moving
`_operation_time(now)` below the `with self._transaction()` would still use a frozen
datetime. Expiry authority must come from a **server-owned clock invoked after
`BEGIN IMMEDIATE` succeeds**; a supplied datetime may remain an observational request
timestamp but cannot authorize lease validity. The CAS statements need an expiry predicate.
Note the verifier also found the original claim's line numbers pointed at a different tree
(committed `lease_store.py` ends at 1094) — the race is real, the citation was not.

**Does S2-3 mean the design is wrong-shaped? On the evidence, no — but the *review* was.**
Findings 1-4 were forgery vectors and they did narrow toward closure. This one is a classic
concurrency-discipline defect that would exist in **any** design of this store; it is not a
symptom of durable-receipt/ledger complexity. Four rounds of forgery-hunting missed it
because no lane probed the *time* axis at all — and it was ultimately found by an S4 schema
gate, not by any S2 lane. Read that as a **gate-coverage gap, not a design-shape problem**.
The `no-users-build-correct-shape` simplification trigger should fire on a *sixth forgery
vector*, not on this.

### S4 — heartbeat / lease lifecycle (`codex-s4-schema-v2-gate.md`, adapt)

- **Blocking 1:** the S2-3 stale-time race above. Fix: sample authoritative time AFTER
  lock acquisition for claim, heartbeat, completion, sweep, and cancel co-triggers; add a
  barrier test holding the writer lock across exact expiry.
- **Blocking 2:** W2's completion-less terminal `cancelled` (terminal row, no `completed`
  event) is treated as *corrupt* by current completion authority — so v2's promised typed
  409 is actually a 500-class error.
- Partially resolved: post-completion heartbeat no-op rule is overbroad for 410 and lacks
  atomic ordering; expiry co-triggers do not give the claimed liveness bound; heartbeat
  idempotency still unspecified; 410 epoch-revocation conflicts with A2.
- **S4 build must not start** until these close. Brief design-gate in flight
  (`fable-s4-brief-gate.md`).

### S6 — sandbox runner (`fable-s6-check.md`, adapt)

- Lookahead is accurate against branch code but **stale**: never folds in the binding
  sandbox-review adapt items (gVisor `runsc` normative, capsule-bound backend-profile
  identity, measured-overhead gate) that `output/research/INDEX.md:12` marks REQUIRED
  pre-build. `OPEN-S6-1` as posed would steer the brief to the wrong menu.
- **HIGH-1 — REFUTED as an acceptance bypass** by cross-family verification
  (`codex-crossfamily-verify-s6-s7.md`). The narrow observation stands (§8.4 lets the
  daemon submit its own pins; no signed registry in eligibility), but settlement already
  requires the fenced B2 completion CAS *plus* the verification tier, and invariant 22
  already demotes self-report to attribution. **Fable's proposed fix was also wrong:** a
  signed registry does not prove a dishonest host *used* an allowed pin — it can simply
  echo a registered value. Correct fix = pin echo is explicitly attribution-only, with
  independent verification preserved.
- **Two further corrections to Fable's amendment**, both material:
  - the optional lower-trust `linux-bwrap` / `linux-rootless-oci` profiles create parallel
    execution routes, violating **Hard Rule 11** (single clean route, no dual paths);
  - **`external_dispatch` is the wrong abstraction.** The capsule's execution capability is
    the semantic class `"repo" | "source_exec"`, and B3 must feed the *unchanged* B2
    protocol. Venue/supply type belongs in a backend-profile or market-offer dimension,
    not as a replacement for the capability class.
- Staleness finding: **CONFIRMED** (gVisor `runsc`, capsule-bound profile identity,
  readiness/per-job receipt separation, measured-overhead gate all absent).
- Final reconciled amendment text dispatched (`codex-s6-amendment-final.md`), instructed to
  judge on merits rather than defer to the later reviewer.

> **Process note.** This is the cross-family gate paying for itself on a *review*, not a
> build: adopting Fable's text as written would have introduced a Rule 11 violation and a
> wrong abstraction into the plan. A finding being real does not make its proposed fix right.

### S7 — model broker (`fable-s7-attack.md`, adapt; `codex-s7-opens-resolution.md` in flight)

- **HIGH-1:** reconciled sub-spec co-locates the broker ledger in the lease-store DB using
  `BEGIN IMMEDIATE`, handing a daemon-side broker a write handle to the tables S2
  terminalizes with — and contradicts the draft's network-RPC reservation with a 5s
  deadline. An implementer cannot build from both. Must pick network-RPC and delete the
  same-database language.
- **HIGH-2 — CONFIRMED** by cross-family verification, with one literal correction and an
  important scoping: S3 does *not* mint exactly one token (up to 8 concurrent 5-minute
  tokens, `daemon_enrollment.py:50,183-190`), but every token belongs to the **same
  undifferentiated authority class**. The token object carries only `daemon_id`, key
  thumbprint, credential epoch, and expiry — **no audience, no operation scope, no
  job/lease/fence binding, no broker principal** (`daemon_auth.py:142-147`). Request
  signing binds method/path/body/nonce, but that is proof-of-possession and replay
  protection, **not authorization**; the verifier returns `AuthenticatedDaemon` and performs
  **no endpoint or action-scope check** (`daemon_enrollment.py:920-999`).
  **Exploitability: a pre-build contract defect, NOT a presently reachable landed exploit** —
  the completion endpoints are not mounted yet (`execution_jobs.py:3-4,221,309`; S4 merges
  HTTP routing later). So the fix must land **before S4 mounts the routes**, at which point
  it becomes live. Fix belongs in S3, which is already merged.
- **HIGH-3:** budget aggregation key and cost ceiling are not signed capsule fields, so
  anti-reset and cost-cap defenses are unverified.

**OPENs resolution + cross-family check** (`codex-s7-opens-resolution.md` ->
`fable-s7-opens-crossfamily.md`, **adapt**). All six OPENs got real, implementable decisions
rather than restatements, and ~15 code citations across four modules verified accurate. It
**closes HIGH-1 in design** (picks the draft's network-RPC side and relocates `BEGIN IMMEDIATE`
inside the control-plane action — the correct resolution of the mutual exclusivity) and
**closes HIGH-3 outright** (policy-side binding via the existing signed `policy_sha256`;
"may lower, never raise without owner authorization, never resets spend"). OPEN-S7-08 fixed a
real crypto defect in r2, which paired XChaCha20 with the application `sequence` doubling as
the AEAD nonce — an invitation to nonce misuse; now pinned to
`Noise_NNpsk0_25519_ChaChaPoly_SHA256` with nonce ownership in Noise `CipherState`.

Three adapt items still block the S7 implementation gate:
- **It ROUTES AROUND HIGH-2** — explicitly asserts "no new broker authentication family is
  needed", reusing the unscoped S3 daemon credential that the attack identified as a second
  terminalizer. This is the finding that becomes live when S4 mounts the completion routes.
- The r2 ledger-co-location sentence is never actually deleted, so the contradictory text
  survives in the spec even though the decision went the other way.
- **MED race:** OPEN-S7-03 requires acceptance to compare cost fields against a *fresh*
  ledger recompute, but reconciliation is asynchronous — an authorization can legitimately move
  `usage_uncertain -> settled` between finalization and acceptance, so an HONEST result
  mismatches and is rejected. Under fix-5's candidate-swap guard the daemon then cannot
  resubmit under the same lease, **wedging the attempt**. Fix: bind the comparison to the
  ledger generation captured at finalization, not an acceptance-time recompute
  (the "generation-bound receipts" pattern from this project's own review-pattern list).

Method note worth keeping: the reviewer noticed the resolution stamped its S2 citations at
`5a307576` (fix-4), one commit behind the tip, and re-verified them at `eb793409` — line
numbers shift ~150 but the claims hold. Citations against a moving branch need a sha stamp.

### S8 — staging / bundle isolation (`codex-s8-amendment.md`, adapt)

- The strong "credential-free staging" claim **cannot be made** and was replaced with two
  enforceable guarantees: ambient-authority isolation + snapshot-object closure, with an
  exact permitted-object set (`base.commit` + `base.tree` recursive closure; parents,
  tags, notes, reflogs, dangling objects all excluded; mode `160000` rejected).
- Closure enforced at the quarantine-to-staging boundary, before any child launches.
- Cancellation-per-phase mapping corrected against heartbeat v2 grace rules.

### S9 — WSL2 broker transport (`fable-s9-check-v2.md` in flight)

- First run **audited the wrong tree** (searched `workflow/` on `main`; the program lives
  in `tinyassets/` on `feat/patch-loop-runner`), so its "absent from main" findings are
  artifacts. Re-dispatched with an explicit branch pin.
- Its one substantive claim, pending proper verification: S9 preserves a plaintext
  socketpair to an untrusted relay instead of terminating S7 §1.5 end-to-end encryption at
  the driver, so a compromised WSL2 guest could read and tamper with all broker traffic.

### S10 / S11 — lookaheads now exist (`fable-s10-s11-lookahead.md`, **gaps**)

**The real remaining program.** Of the 20 §13 B2 acceptance criteria, **11 have nothing
satisfying them**: 1 (as a gated set), 4, 6, 7, 8, 9, 11, 13, 15, 18, 20. Everything else
is substrate-partial on unmerged branches. Three items are program-level, not slice-level:

- **Criterion 4 — no run->job bridge.** `LeaseStore.add_task` has **zero production
  callers**; no MCP action creates a B2 job; a `host_daemon` run today parks QUEUED with no
  job record (`runs.py:2248-2271`). This is S10's OPEN-S10-1 and nothing upstream of it works
  without it.
- **Criterion 15 — ORPHAN DELIVERABLE.** No §12 slice's Files cell contains the §8.10
  GitHub-effect route. `auto_ship_pr.py` exists but belongs to the **retired** cheat-loop
  lane (`AUTO_FIX_DISABLED=true`) and implements none of §8.10's six independent
  verifications. This is the end of the value chain — a patch that never becomes a
  reviewable PR delivers nothing. Investigation dispatched (`fable-orphan-effect-route.md`).
- **Criterion 18 — may force an ARCHITECTURE decision, not a test.** 1,000 long-polling
  daemons + 10,000 queued jobs against a single-writer SQLite store; §17 [S4/infra] predicts
  the filesystem MVP may fail, which collides with §2.2's explicit no-Postgres non-goal.
  That is a **host decision**, not an agent one. Analysis dispatched
  (`codex-load-architecture.md`), including whether the 1,000-daemon bar is even right-sized
  for a platform with zero users. Note S2-3's 30s busy-timeout window is not a corner case
  at that concurrency.
- **Criterion 1 needs backfill:** S0/S1/S3/S5 merged after multi-round Codex review but have
  **no per-slice dual-family verdict record** equivalent to the S2 gate files. The criterion
  asks for a recorded set; that index has to be reconstructed.
- **Criterion 20** will realistically land on the watch-item arm (zero real users) — plan
  that wording into the acceptance artifact rather than treating it as a failure.

S10 also carries the guard inversion: migrating the daemon from the JSON claim route to
`LeaseStore.claim` flips the fail-closed
`test_lease_store_claim_has_no_production_dispatch_caller`. A botched cutover is a live
daemon outage — exactly the FINDING B outage fix-2 had to repair.

---

## Tooling notes (learned the hard way this session)

- `peer_agent.py --out` captures **only the peer's final message**. A lane that delivers
  in parts, or sends an addendum after a background search, loses its body. Briefs must
  say: deliver everything in ONE final message.
- Lanes search whatever tree they land in. Any brief touching code MUST pin the branch
  (`feat/patch-loop-runner`) and note the package is `tinyassets/`, not `workflow/` —
  otherwise "does not exist" findings are artifacts of the wrong checkout.
- The anti-deferral clause (Kimi's rule) is still required for Claude lanes; without it
  they dispatch their own sub-reviews and end with "I'll report when it returns".
