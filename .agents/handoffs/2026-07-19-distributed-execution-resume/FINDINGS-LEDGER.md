# Distributed-execution — open findings ledger

**Opened:** 2026-07-20, on resuming Kimi Code's lane after its credit ran out.
**Purpose:** one durable place for findings produced by the standing fleet, so nothing
is lost between rounds. Kimi's `output/s2-gate/s2-fix2-report.md` remains the canonical
S2 review-cycle log; this ledger is the *cross-slice* open-items view.

**Fleet:** `>=4` Codex + `>=4` Claude/Fable `peer_agent.py` lanes held continuously by
the `.claude/hooks/fleet_floor_guard.py` Stop hook. Status: `python scripts/fleet_status.py`.
Lane artifacts land in `C:/Users/Jonathan/Projects/TinyAssets/output/s2-gate/`.

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

A Fable lane is auditing the remaining program for the same class and testing whether a
single invariant closes it (`fable-structural-audit.md`, in flight). The §9 settlement
path is the priority: money moving on a self-asserted claim is the worst case.

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
