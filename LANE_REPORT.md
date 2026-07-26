# Lane report — `complete-independent-full-platform-targets` handoffs cluster

**Branch:** `claude/o5-handoffs` (off `origin/main` @ `bc1227ee`)
**Date:** 2026-07-25 → 2026-07-26
**Scope:** tasks 5.1, 5.2, 5.4; then 5.6/5.7 if their in-lane predecessors completed.
**No PR opened** (per lane instruction).

---

## Per-task outcome

| Task | State | Pushed SHA | Why |
|---|---|---|---|
| **5.1** models + store + registry extension + migration | **BUILT — checked** | `cf8a03f5`, `88d1c04e` | Landed with evidence. |
| **5.2** consent/confirmation, receipt-bound creation, dedup, provenance, router | **BUILT — checked** | `cf8a03f5`, `f8c3c6e9`, `14547803` | Landed with authenticated persisted-run authority. |
| **5.3** signed webhooks / provider polling | **DEFERRED — unchecked** | `93ea0fb1` | Shares the inbound receiver with boundary inbox URLs; needs a host decision. |
| **5.4** integrate through canonical effect owners | **BUILT — checked** | `cf8a03f5`, `f8c3c6e9`, `e46b04ab` | Canonical authority/identity/receipt path plus replay recovery. |
| **5.5** disputes + five test files | **PARTIAL — unchecked** | `93ea0fb1` | 4 of 5 test files landed; verification needs 5.3 and disputes remain moderation-owned. |
| **5.6** §14 handoff proof | **PARTIAL — unchecked** | `93ea0fb1` | Concurrency/exactly-once proven; webhook/poll and 10× provider mix need 5.3. |
| **5.7** rendered chatbot proof | **BLOCKED — unchecked** | `93ea0fb1` | Unmerged and later verification depends on 5.3. |
| **6.1** collision re-check | Note appended | `93ea0fb1` | Write-set expansion recorded. |

**5.6/5.7 were not reachable.** They gate on 5.3–5.5, and 5.3 was deferred by
instruction. Neither was checked; both carry per-clause notes stating exactly
which clauses are proven and which are not, so the partial proof cannot be
mistaken for the gate.

---

## Premise verification against today's `main` (before building)

| Claim in `tasks.md` | Verified state |
|---|---|
| `tinyassets/handoffs/` does not exist | **True** — created by this lane. |
| `tinyassets/outcomes/schema.py` is the `outcome_event` DDL owner, not `api/extensions.py` | **True** — `api/market.py` holds the router actions; the DDL is in `outcomes/schema.py`. |
| 5.4's named paths (`tinyassets/external_effects.py`, `tinyassets/external_write_receipts.py`) do not exist | **True** — real owners are `tinyassets/effectors/`, `tinyassets/storage/external_write_receipts.py`, `tinyassets/storage/effector_consents.py`. |
| Outbound-boundary effector identity landed | **True** — `idempotency.derive_effect_key` + `resolve_effector_identity`; receipts have reserve/finalize/hold/confirm/activate/release plus identity-alias parity. |
| Next free migration number | **014** — `013_paid_market_workflow.sql` is the highest on main; `migrate.discover_migrations` requires a gap-free chain. |
| 5.3 has an inbound receiver to attach to | **False** — none on main. Confirms the deferral. |

**A premise the task file did not state, found while building:** a handoff
declaration cannot live at the top level of a published version snapshot.
`branch_versions._canonical_snapshot` whitelists eight fields, so a
`snapshot["handoffs"]` key is silently stripped at publication. Declarations
therefore live on `NodeDefinition.handoffs`, which `node_defs` carries verbatim —
also the better model, since the spec says *a node version* declares the handoff,
and it is what makes the declaration immutable per content hash.

---

## De-collision compliance

- **5.3 deferred**, left honestly unchecked with a note naming the shared
  receiver and the host decision.
- **5.4 consumes the landed effector identity.** `derive_handoff_effect_key`
  delegates to `tinyassets.idempotency.derive_effect_key` rather than hashing its
  own — one `effect:v1:` key space, one implementation, and the receipt store's
  identity-alias/parity machinery applies unchanged. **No second dedup identity.**
- **Built on the existing outcome registry.** `outcome_event` remains the sole
  generic owner; the extension is additive side tables in the same database, with
  their DDL beside the registry owner so the evidence vocabulary has one
  definition. `record_outcome` keeps exactly one owner.
- **Not touched:** `tinyassets/api/branches.py`, `tinyassets/payments/`,
  `tinyassets/universe_server.py`.

---

## Four real defects found and closed

**1. Handoffs bypassed generic soul-scoped effect authority.** Every shipped
effector (`github_pr`, `twitter_post`, `wiki_write_back`) consults
`tinyassets/effectors/authority.resolve_soul_effect_authority` *before* its
consent gate. The handoff path did not, so a handoff could have reached a
destination the universe's own soul refuses for every other effect path — exactly
what 5.4's "without bypassing generic effect authority" forbids. Both gates are
now required, neither substitutes for the other, and the transitional
`UNDECLARED` fall-through matches the landed effectors. Four tests plus a
mutation.

**2. `record_outcome` did not enter the evidence lifecycle.** The capability
requires the *existing* action to become the user-attestation entry point. It now
writes its `outcome_evidence` row in the **same transaction** as the claim, at
`user_attested`, so a claim cannot exist without its level — the failure mode that
would let an unverified attestation read as verified. The attester is resolved
server-side from the credential-validated request, never a caller kwarg.

**3. `record_outcome` did not bind the attestation to persisted run ownership.**
The router now refuses anonymous and foreign-run attestations before any outcome
table is written. The actor comes from authenticated request context and the
authority decision comes from the persisted run record; caller strings are never
accepted as authority.

**4. Accepted receipt replay could not repair a missing outcome link.** A crash
after receipt finalization but before registry linkage left the handoff accepted
forever with no outcome, because replay skipped outcome creation. Replays now
repair the link, while a partial unique index elects one writer if recoveries
race and all other callers return the shared evidence.

---

## Test evidence (Windows, Python 3.14, 2026-07-26)

```
tests/test_handoff_authority.py     37 passed
tests/test_handoff_receipts.py      31 passed
tests/test_handoff_concurrency.py    9 passed   (3 consecutive runs, no flake)
tests/test_handoff_store.py          5 passed
tests/test_outcome_events.py        32 passed
```

Touched-and-adjacent run (adds `test_outcomes_schema`, `test_outcome_mcp`,
`test_external_write_receipts`, `test_effector_consents`,
`test_outbound_effect_boundary`, `test_authoring_sessions`, and
`test_soul_scoped_effect_authority`): **242 passed, 0 failed**.

`ruff check` on this lane's files: **clean**. The 7 `E501`s in
`tinyassets/api/market.py` are **pre-existing** — verified by linting
the pre-lane file at the same 7 line numbers — this lane did not alter those
lines.

`openspec validate complete-independent-full-platform-targets --strict`: **valid**.
`python packaging/claude-plugin/build_plugin.py`: mirror parity verified by the
pre-commit gate on every commit.

### Pre-existing `main` red, verified not from this branch

An earlier run showed 13 failures in `tests/test_outcome_gates.py`
(`KeyError: 'branch_def_id'` from `create_branch`, alongside a
`_append_global_ledger() missing 1 required keyword-only argument: 'actor'`
warning). Verified by checking out a detached `origin/main` worktree
(`c1f0d404`) and running the same file: **13 failed, 4 passed** — identical.
Nothing in this branch touches `create_branch` or `_append_global_ledger`. This
overlaps the existing STATUS "main-red round 2" row.

### Mutation probe — 32/32 go red

`python scripts/handoff_mutation_probe.py` → *every mutation went red (32
checked)*. Each removes exactly one invariant and is confirmed to turn its named
test red; original bytes are restored in a `finally` block and no git
restore/reset is used.

**The probe found two defects in its own gates, both fixed in-lane:**

1. `confirmation-binds-source-version` stayed green. The stale-version refusal is
   enforced by *two* redundant bindings (`effect_key`, which already derives from
   version+hash, and `fingerprint`, which contains `effect_key` again) — either
   alone suffices, so no single-field mutation could go red. The test was passing
   for a different reason than its docstring claimed. The mutation now neutralises
   both, and `confirmation_fingerprint`'s docstring no longer presents the
   version/hash fields as the mechanism.
2. `gate-events-stay-separate` was inert — it added an unused method, which cannot
   change behavior. It now makes an outcome transition actually write to
   `gate_event`, and goes red.

---

## Findings raised, not silently patched

**Receipt store races on first-touch WAL conversion.** The concurrency suite
initially failed intermittently with `sqlite3.OperationalError: database is
locked` from `PRAGMA journal_mode = WAL` in
`tinyassets/storage/external_write_receipts._connect`. SQLite cannot convert a
fresh database to WAL while other connections hold it, and that conversion is not
covered by `busy_timeout`, so N threads first-touching a brand-new receipts DB can
each fail there. In production the DB is normally already WAL, so this is a
cold-start window rather than a steady-state bug — but it is real, it is in a
landed file outside this lane's write-set, and the failure mode is a hard error on
a path whose whole job is to be safe under concurrency. The fixture warms the DB
so the suite measures duplicate suppression; the store itself is **not** patched.

**`migrate_outcome_schema` now runs two `INSERT OR IGNORE … SELECT` scans on every
connection open.** The legacy backfill is correct (rows are left unattributed),
but it is O(rows) per connect on a function called from every `_outcome_connect`.
Negligible at current scale; worth revisiting before the registry grows.

---

## Concurrent writer in this worktree

Another writer modified files underneath this session repeatedly (the harness
reported the edits as intentional), including one full revert of an
uncommitted working tree. Everything below was re-applied and is in the pushed
history. Three of those edits were materially wrong and were corrected rather
than accepted:

1. **A divergent evidence vocabulary** in `outcomes/schema.py`
   (`submitted`/`accepted`/`rejected`/`orphaned` as *evidence levels*) conflated
   lifecycle state with evidence strength and would have made
   `provider_submitted` violate the SQL CHECK while passing the Python guard. The
   registry now owns one vocabulary and `models.py` imports it; a test asserts
   they agree.
2. **A legacy backfill deriving `account_id` from `verified_by`** — attributing a
   claim to whoever *verified* it — plus a synthetic `legacy:unknown` account.
   Now backfilled unattributed, asserted by three tests.
3. **A `record_outcome` entry added to the handoff dispatch table**, permanently
   shadowed by market.py's owner in the router. It would have read as a live
   second attestation API while never executing. Removed; the canonical action
   itself was evolved instead.

---

## Pushed

| Commit | Contents |
|---|---|
| `cf8a03f5` | Implementation: `tinyassets/handoffs/`, registry extension, migration 014, router + scope wiring, plugin mirror. |
| `15cd7910` | Tests (4 suites) + mutation probe, probe self-findings fixed, concurrency flake diagnosed. |
| `88d1c04e` | Store-level lifecycle/registry tests. |
| `f8c3c6e9` | Soul effect-authority bypass closed; `record_outcome` becomes the attestation entry point. |
| `93ea0fb1` | `tasks.md` check-offs with evidence, 6.1 write-set record. |
| `cb7e2d4f` | Initial lane report with per-task built/deferred evidence. |
| `14547803` | Task 5.2: bind outcome attestations to authenticated persisted-run ownership. |
| `e46b04ab` | Task 5.4: recover accepted outcome linkage from canonical receipt replay. |
| *(final)* | Updated aggregate evidence and pushed SHA record. |

Branch pushed to `origin/claude/o5-handoffs`. No PR opened.

LANE_RESULT: partial - 5.1/5.2/5.4 built and checked off with 114 lane tests (242 touched-and-adjacent, 0 failed) and a 32/32 mutation probe; 5.3 remains deferred on the shared inbound-receiver host decision, so 5.5/5.6/5.7 remain honestly unchecked.
