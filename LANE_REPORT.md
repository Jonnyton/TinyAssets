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
| 0.1 | Premise-verified all 28 open tasks against `origin/main`; labeled each unbuilt-target / path-corrected / owner-corrected / in-flight external / blocked |
| 0.2 | Corrected the four misdirecting task premises — three dead paths, one misattributed owner (see below) |
| 0.3 | Recorded that moderation implementation started outside this change (#1662, #1667) and fenced section 2 |
| 0.4 | Recorded the host-owned gates in section 3, scoped to the two steps they gate: signed publication and final acceptance |
| 0.5 | Re-ran the pre-claim collision guard and strict-validated the change |

### The four premise corrections

Two kinds, deliberately kept distinct: a **dead path** (the named file does not
exist) and a **misattributed owner** (the named file exists but does not own
what the task said it owns). Conflating them misleads an implementer in
opposite directions.

1. **5.4 — dead path.** Named `tinyassets/external_effects.py` and
   `tinyassets/external_write_receipts.py`. **Neither path exists.** Real
   canonical owners: the `tinyassets/effectors/` package (incl. `authority.py`),
   `tinyassets/storage/external_write_receipts.py`, and
   `tinyassets/storage/effector_consents.py`.
2. **5.1 / 5.2 — misattributed owner, not a dead path.** They located the whole
   `outcome_event` registry in `tinyassets/api/extensions.py`. That path
   **exists** and legitimately owns the router half (`record_outcome` /
   `list_outcomes` / `get_outcome` and the `gate_event` actions); the DDL and
   `OutcomeEvent` dataclass live in **`tinyassets/outcomes/schema.py`**. The old
   wording would have extended the router and missed the store. Round-2
   cross-family review caught that this lane first filed it as `path-corrected`,
   which wrongly implied `extensions.py` was absent; it is now
   `owner-corrected`.
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

**Section 3, packaged tray (5 tasks) — one task blocked end-to-end, the rest
buildable with one gated step.** The three signing identities (Windows
Authenticode, Apple Developer ID + notarization, Linux package key) and the
clean-machine OS matrix are genuinely absent — `gh secret list` on 2026-07-24
shows no signing, notarization, or Apple/Authenticode credential of any kind.
What that gates is narrow: **signed publication** of installable artifacts, and
**3.5's final acceptance proof**, which the spec explicitly says build success
cannot satisfy. Only 3.5 is blocked as a whole task, because 3.5 *is* a proof.

3.1's packaging definitions and signing hooks, 3.2's onboarding/credential/
updater modules, 3.4's clean-machine and upgrade tests, and a 3.3 workflow whose
signing and publication steps are gated on secret presence can all proceed now.

This corrects an overstatement in the first version of this report and of
`tasks.md`: a section-wide "nothing can be proven" blanket, plus a claim that
adding `desktop-release.yml` early yields a permanently red *required* check.
That claim is false — `main`'s protection requires exactly two contexts,
`policy` and `Diff scope declared` (verified 2026-07-24), and required checks
are an explicit allowlist, so a new workflow is only gating if someone adds it.
The blanket also contradicted 3.2/3.4 carrying a plain `unbuilt-target` label;
the blanket was the error, not those labels.

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

### Cross-family review, round 2 (post-commit)

The committed result was dispatched back to Codex, read-only, 2026-07-24.
Verdict **adapt** again, with two required corrections plus one miscount. It
independently re-confirmed everything else: the packaged-tray and handoff
absences, the 4.4/5.4 dead paths and their replacement owners, the #1662/#1667
moderation scope and the fence matching it, all 28 runtime tasks still open with
only 0.1-0.5 checked, no requirement spec touched, and strict validation green.

Both corrections were verified against `origin/main` before folding — the
reviewer was right on both, and on the miscount:

1. **5.1/5.2 misclassified as `path-corrected`.** Verified: `git cat-file -e
   origin/main:tinyassets/api/extensions.py` succeeds, and `origin/main`'s
   pre-lane 5.1 text reads "extend the existing `outcome_event` registry ... in
   `tinyassets/api/extensions.py`". The path was never dead; the ownership
   attribution was wrong. Folded as a new `owner-corrected` label, with 0.2, the
   note vocabulary, and both task notes reworded.
2. **Section-3 blocker overstated.** Verified in both directions: no signing
   credential exists (`gh secret list`), *and* `main` requires only the `policy`
   and `Diff scope declared` contexts, so the "permanently red required check"
   rationale does not hold. Folded by scoping the gate to signed publication and
   3.5's acceptance proof — see *Tasks skipped — blocked* above.
3. **Miscount:** 31 workflow files on `origin/main`, not 32. Fixed in the 3.3
   note. Confirmed by `git ls-tree -r --name-only origin/main .github/workflows`.

Nothing in round 2 was refuted; no counter-evidence was found against either
required fold.

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
3. Section 3 does **not** need a host decision before a lane touches it. A build
   lane can take 3.1, 3.2, 3.4, and a publication-gated 3.3 today. The host
   decision — provision the three signing identities and the clean-machine
   matrix, or explicitly park packaged distribution — is what unblocks signed
   publication and 3.5's acceptance proof, and it can be made in parallel with
   that build work rather than ahead of it.
