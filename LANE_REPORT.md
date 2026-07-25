# Lane Report — `complete-independent-full-platform-targets`

- **Branch:** `claude/o5-independent-platform-targets` (based on `origin/main` @ `898b9edc`)
- **Date:** 2026-07-24
- **Scope:** OpenSpec change `openspec/changes/complete-independent-full-platform-targets/`
- **Fence honored:** no file under `tinyassets/moderation/` or any moderation test was written or staged.

## Headline

The change did not reach completion, and it should not have. It is a
**target-only** change — its own `design.md` Non-Goals forbid claiming any
target behavior is built and forbid syncing before implementation — while its
tasks 2.1-5.7 are worded as greenfield runtime builds for four subsystems, each
ending in a §14 concurrency/load proof and a rendered live-connector chatbot
acceptance. **Zero of the four capabilities has any implementation on
`origin/main`.** No amount of spec work in one lane closes that, and closing the
checkboxes any other way would have produced exactly the as-built overclaim the
change exists to prevent.

What this lane did instead was make the preserved implementation plan *correct*.
Premise verification found that **four task premises named files that do not
exist**, and that one capability had quietly started landing outside the change.
An implementer following the old wording would have built against dead paths and
collided with two open PRs.

Task count is unchanged where it matters: **28 implementation/proof/foldback
tasks remain open.** Five new verification tasks (section 0) were added and
checked; they record this lane's work only.

## Tasks completed

Section 0 (new, added by this lane — verification work, not implementation):

| Task | What it did |
|---|---|
| 0.1 | Premise-verified all 28 open tasks against `origin/main`; labeled each unbuilt-target / path-corrected / in-flight external / blocked |
| 0.2 | Corrected the four task premises that named nonexistent files (see below) |
| 0.3 | Recorded that moderation implementation started outside this change (#1662, #1667) and fenced section 2 |
| 0.4 | Recorded the host-owned gates that block section 3 in full |
| 0.5 | Re-ran the pre-claim collision guard and strict-validated the change |

### The four premise corrections

1. **5.4** named `tinyassets/external_effects.py` and
   `tinyassets/external_write_receipts.py`. **Neither path exists.** Real
   canonical owners: the `tinyassets/effectors/` package (incl. `authority.py`),
   `tinyassets/storage/external_write_receipts.py`, and
   `tinyassets/storage/effector_consents.py`.
2. **5.1 / 5.2** located the whole `outcome_event` registry in
   `tinyassets/api/extensions.py`. The DDL and `OutcomeEvent` dataclass actually
   live in **`tinyassets/outcomes/schema.py`**; `extensions.py` only routes
   `record_outcome` / `list_outcomes` / `get_outcome` and the `gate_event`
   actions. The old wording would have extended the router and missed the store.
3. **4.4** said to reuse `tinyassets/runtime/lease_store.py`. That path does not
   exist, and `openspec/changes/distributed-execution/` is still an active,
   unarchived change — so the reuse conditional is currently **false**.
4. **3.1** enumerated `packaging/` imprecisely and read as repo-wide absence.
   Corrected, and explicitly scoped to native-installer packaging so it does not
   deny the connector/plugin packaging (incl. OAuth code under
   `packaging/claude-plugin/`) that does exist.

## Tasks skipped — landed

**None.** No capability in this change has any implementation on `origin/main`.
This was verified path-by-path, not inferred: `tinyassets/moderation/`,
`tinyassets/authoring/`, `tinyassets/autoresearch/`, `tinyassets/handoffs/`,
`packaging/{windows,macos,linux}/`, `tests/desktop_install/`,
`.github/workflows/desktop-release.yml`, and all 13 named test files are absent.

## Tasks fenced — external, in flight

Section 2 (`moderation-and-abuse-response`), 5 tasks. Checkboxes untouched.

| Task | Ownership found |
|---|---|
| 2.1 | `models.py` + `__init__.py` on draft PR #1662. `store.py` and the migration **unowned** |
| 2.2 | `policy.py` on #1662, `service.py` on #1667. Neither merged; neither covers the full service surface |
| 2.3 | **Unowned** — no open PR touches `tinyassets/api/` for moderation |
| 2.4 | `test_moderation_authority.py` on #1662, `test_moderation_service.py` on #1667. `test_moderation_concurrency.py` **unowned** |
| 2.5 | Unbuilt; gated on 2.1-2.4 |

**Structural finding worth a reviewer's attention:** moderation code is landing
*outside* this change while its delta spec is held *inside* it. That is precisely
the partial-implementation drift `design.md` warns against ("partial code must
not cause the whole target change to be synced"). Task 6.3's split obligation is
therefore now **live** for that capability. This lane **recorded it but did not
discharge it** — a split executed from here would collide with the fenced lanes.
Discharging it needs the full delegation shape: create the successor, physically
transfer the delta and section 2 tasks out, and assign implementation,
acceptance, sync, and archive ownership. A naming note is not a split.

## Tasks skipped — blocked

**Section 3, packaged tray (5 tasks) — blocked on host, entire section.**
Nothing in 3.1-3.5 can be *proven* without a Windows Authenticode signing
identity, an Apple Developer ID plus notarization account, a Linux package
signing key, and a clean-machine OS matrix. None exists as a provisioned CI
secret. Building 3.1-3.3 anyway would yield unverifiable artifacts and a release
workflow that can never go green — 3.3 in particular would become a permanently
red required check. Recorded as blocked with the gate named, per instruction.

**Section 4, authoring/autoresearch (7 tasks) — live unbuilt target.** Not
blocked by a host decision; simply four-subsystems-of-greenfield, ending in a
100-concurrent-session §14 proof and a rendered live-connector acceptance.
Deliberately not started here: a speculative dump of `tinyassets/authoring/` +
`tinyassets/autoresearch/` in one unreviewed lane contradicts the standing steer
to ship enabling primitives rather than pre-built complexity, and 4.4's lease
reuse is genuinely blocked until `distributed-execution` lands. Flagged in 4.2:
the authoring sandbox must not assume an OS isolation boundary the platform does
not yet have (open STATUS P1; proposal on draft PR #1573).

**Section 5, handoffs/outcomes (7 tasks) — live unbuilt target, 5.5 part-fenced.**
Same reasoning. 5.3 additionally has no inbound webhook receiver on
`origin/main` to attach to — the transport surface is part of the work, not a
given. 5.5's dispute half depends on the fenced `tinyassets/moderation/service.py`.

**Section 6, foldback (4 tasks) — deliberately open.**
6.1 is a *recurring* obligation (re-run before every write-set expansion), so one
clear run does not close it. 6.2 is the implementation foldback gate. 6.3's
disposition is recorded as **sync nothing**. 6.4 is not applicable — archiving
now would sync four target-only deltas into canonical specs as as-built truth.

## No runtime was built, and why

Cross-family review was asked directly for the smallest runtime slice that could
be built honestly here. Its answer: evolving `outcome_event` evidence history
(`tinyassets/outcomes/schema.py` + the outcome actions + a migration + focused
idempotency/concurrency tests, explicitly excluding provider handoffs, moderation
disputes, and live acceptance) — **as its own successor change, not inside this
target-only umbrella.** That is a good forward slice and is recorded here as a
recommendation rather than executed, because building it inside this change would
mix as-built code into a change whose deltas must stay unsynced.

## Validation evidence

All commands run 2026-07-24 in this worktree on `claude/o5-independent-platform-targets`.

```
$ openspec validate complete-independent-full-platform-targets --strict
Change 'complete-independent-full-platform-targets' is valid          # exit 0

$ openspec validate --all --strict
Totals: 41 passed, 0 failed (41 items)                                # exit 0

$ python scripts/claim_check.py --provider claude-o5-independent-targets \
    --check-files "openspec/changes/complete-independent-full-platform-targets/"
CLEAR: no overlap with another provider's claimed/in-flight Files
```

`openspec` CLI version 1.4.1. Pre-commit hooks ran clean on the commit
(mirror parity N/A, mojibake scan clean, cross-provider drift clean, skills
valid).

**Scope guard:** `gh pr list --limit 60` reviewed. No open PR branch touches
`openspec/changes/complete-independent-full-platform-targets/`. Interactions
noted rather than duplicated: #1662/#1667 (moderation — fenced), #1573 (engine
OS sandbox — affects 4.2), #1684 (host target-architecture direction — the
canonical-seven-handle and single-`/mcp`-endpoint direction is reflected in the
4.3 note).

### Cross-family review (verbatim verdict)

Dispatched to Codex, read-only sandbox, 2026-07-24. Verdict **adapt**; all three
adaptations applied before commit.

```
VERDICT: adapt
P1: CONFIRMED  (external_effects.py / external_write_receipts.py absent)
P2: CONFIRMED  (tinyassets/runtime absent; distributed-execution still active)
P3: CONFIRMED  (outcome_event DDL in tinyassets/outcomes/schema.py)
P4: WRONG as literally stated — all six target paths confirmed absent and no
    keyring/OAuth/notarization/updater code under tinyassets/desktop, but
    packaging/ also contains INDEX.md / PACKAGING_MAP.md and nested
    Claude-plugin OAuth code.
Q1: Delegation is legitimate only after rewriting the relevant tasks as explicit
    delegate/release tasks, creating each successor, transferring its complete
    delta, and assigning implementation, acceptance, sync, and archive
    ownership. build-forward-platform-capabilities 1.1 and 2.1 are valid
    precedent because those tasks explicitly require delegation and physical
    delta release; they do not justify checking the present runtime tasks
    3.1-5.7 complete by annotation. Keep the umbrella active until every
    successor lands.
RISKS:
- Marking existing "implement/add/prove" tasks complete by delegation would
  create false checklist progress.
- Merely naming successors, without transferring their complete deltas and
  acceptance obligations, would hollow out the umbrella.
- Foldback tasks 6.1-6.4 cannot be completed spec-only; implementation proofs,
  sync, and archive must remain open.
- Host-gated or external-PR-dependent work is blocked, not complete, and needs
  explicit dependency edges.
- Path corrections must distinguish target-specific absence from repo-wide
  absence, especially the overly broad P4 OAuth claim.
```

Applied: P4 precision fix in the 3.1 note; an explicit "no implementation task
is checked by this lane, and none may be checked by annotation, delegation, or
host-gating" statement in section 0; and an explicit statement in 6.3 that the
moderation split was recorded, not discharged.

## Commits pushed

- `826b6b6c` — `spec: premise-verify the independent full-platform target tasks`
- plus this report.

Both on `claude/o5-independent-platform-targets`. **No PR opened**, per
instruction — cross-family review precedes any PR.

## For the reviewer

1. The honest disposition is that this change stays **active and unsynced**. If
   the intent was for it to close, the change needs slicing into per-capability
   successors with implementation lanes — not more spec work.
2. The moderation split (6.3) is the one live structural obligation and it needs
   an owner who is not fenced out of `tinyassets/moderation/`.
3. Section 3 needs a host decision before any lane touches it: provision the
   three signing identities and the clean-machine matrix, or explicitly park
   packaged distribution.
