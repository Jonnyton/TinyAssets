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
| S2-3 | ? | **NEW CLASS — TOCTOU, not forgery.** `now` sampled BEFORE `BEGIN IMMEDIATE` acquires the write lock; a writer queued behind another can pass an expiry check with pre-expiry time, so an expired lease may renew or complete (`lease_store.py:893-904,1179-1220` @ `5a307576`; violates plan :830-839). Surfaced by the S4 schema gate, not an S2 lane. | verification dispatched (`codex-stale-time-verify.md`) |

**S2-3 is the one to watch.** Findings 1-4 were all forgery vectors; this is a different
class found by a different lane. If confirmed, it does *not* by itself mean the design is
thrashing — but a sixth round on this store is the point to ask whether the
durable-receipt/ledger design has too many trust surfaces and wants simplifying rather
than more hardening (per the `no-users-build-correct-shape` host directive).

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

### S10 / S11 — no lookaheads existed (`fable-s10-s11-lookahead.md` in flight)

- S10 is where the daemon migrates from the JSON claim route to `LeaseStore.claim`,
  inverting the fail-closed guard
  `test_lease_store_claim_has_no_production_dispatch_caller`. A botched cutover is a live
  daemon outage — exactly the FINDING B outage fix-2 had to repair.
- S11 is the first B2 live test: the goal milestone. Needs an accurate list of §13
  acceptance criteria that nothing currently satisfies.

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
