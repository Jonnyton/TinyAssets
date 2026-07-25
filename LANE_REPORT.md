# Lane report — `brain-okf-canonical-store` builder lane

**Branch:** `claude/o5-brain-okf-canonical-store` (based on `origin/main` @ `6dd2bdf0`)
**Date:** 2026-07-24
**Result:** partial — 1 of 7 open tasks completed; 6 correctly cannot be completed in this lane.

## Headline

The lane goal was "drive `tasks.md` (7 open, 15 done) to completion." **Premise
verification says that goal is unreachable, and that the unreachability is the
correct state, not a lane failure.** Of the 7 open tasks: 1 was live and is now
done, 2 are blocked on an open host decision, 1 is downstream of those, and 3 are
explicitly out of scope by their own section heading. Checking any of the 6 off
would have been a false completion claim.

The change now records a verified disposition for every one of them, so the next
reader does not re-derive this.

## Tasks completed

| Task | What was done |
|---|---|
| **2.2** Keep STATUS dependencies explicit | Done. Two halves. The *legacy-is-not-authority* half had already landed independently — `docs/specs/INDEX.md` disclaims current authority for the whole legacy directory, and `docs/audits/2026-07-22-legacy-spec-disposition.md` classifies the research companion as **HISTORY** (line 67) and the TINY narrative as **CLAIMED** (line 69). The *dependency-is-explicit* half was live and is the STATUS edit in `5114da3f`. |

## Tasks skipped — landed / partially landed elsewhere (recorded, not built)

| Task | Finding |
|---|---|
| **5.1** OKF compatibility shim | **PARTIALLY LANDED, in the opposite direction.** All four projection mechanics named by 5.1 ship in `tinyassets/wiki/okf_export.py` as a one-way *export*: `_convert_wikilinks`, `_write_index` (root `index.md` frontmatter is `okf_version: "0.1"` and nothing else, line 199), `_write_log` (dated), `_EXCLUDED_ROOTS = {"drafts","raw","daemon-wiki"}` (line 15). Already as-built spec truth in `openspec/specs/knowledge-retrieval-and-memory/spec.md:386,404`. **Still unbuilt:** the D5 *in-place read* shim for slice-1 `assemble(lens)` — the exporter writes a separate bundle and refuses a target inside the source root (line 38); `assemble(lens)` does not exist and there is no `tinyassets/brain/` package. Left unchecked, with a reuse pointer so a future builder does not rebuild the projection. |
| **5.3** Conformance validation + `okf_version` pin + steward | **Split.** Pin ships (`OKF_VERSION = "0.1"`, line 12) and a structural validator ships (`_conformance_report`, line 232) — but deliberately narrow: it validates only the *generated* bundle, and the as-built spec is explicit that its `conformant` flag "does not claim complete upstream OKF or canonical-store conformance". Substrate-wide validation and the composable steward are unbuilt (repo-wide search finds no OKF steward). Left unchecked. |
| **4.2** (already `[x]`) | Its trailing clause "merge to `main` still host-key gated" is **stale**: PR #1369 merged 2026-06-25 (`95d63682`, verified an ancestor of `origin/main`). Annotated. |

## Tasks skipped — blocked

| Task | Blocker |
|---|---|
| **2.1** Fold the store architecture into PLAN | **Host decision.** `PLAN.md` carries no brain/OKF store decision; its only canonical-store statement (line 560, "GitHub is an export sink… Canonical state lives in Postgres") is *platform* goal/branch/node state — a different scope that neither approves nor contradicts the OKF decision. The approval is the open STATUS row **"Resolve target-spec PLAN conflicts — store, private data, primitives, privacy guidance"** (`host-decision`), which `docs/audits/2026-07-22-legacy-spec-disposition.md:69` independently names as the owner of this residue. AGENTS.md: PLAN changes require user approval — a builder must not write it on the host's behalf. |
| **4.1** `sync-specs` into `openspec/specs/` | **Two independent blockers, either sufficient.** (1) The change's own ordering: task 2.1, `design.md` D6, and `proposal.md` §Impact all require host-approved PLAN foldback *before* spec sync. (2) `openspec/specs/` is **as-built** truth per AGENTS.md, and no file under it declares itself target-state; `brain-canonical-store` is entirely unbuilt (`docs/audits/2026-07-22-openspec-full-coverage-audit.md:105` calls it "future brain-store migration"). Syncing would assert requirements the system does not satisfy. Note the *stated* gate — "after host merge key" — **is** satisfied; the blockers are elsewhere. |
| **4.3** Archive the change | Downstream of 4.1, **and not a safe no-op**: `openspec archive` syncs delta specs as a side effect, so archiving would perform the sync D6 forbids. Correct sequence recorded: host store decision → 2.1 → 4.1 → §5 relocated to a successor change → 4.3. |
| **5.2** Write commit protocol | Wholly unbuilt, and §5 is out of scope by its own heading ("NOT in this change; behind the Codex 6 pre-build gates"). Building it here would violate the change's scope and its pre-build gates. |

## Unblocking the dependent lanes

The lane brief noted this change is a dependency hub. Since it cannot land, the
useful deliverable is a **dependent-lane contract** added to `design.md`, so
`reconcile-universe-personification-relay` and the runtime-fiction promotion do
not wait on a host-blocked gate. It states what a dependent may rely on today
(this change's ownership of the canonical-store *target*; the shipped exporter
capability under `knowledge-retrieval-and-memory`) and what it must not
(`assemble(lens)` runtime; `openspec/specs/brain-canonical-store/` existing).

Also resolved one of `design.md`'s Open Questions in the export direction: the
shipped exporter treats `drafts/` as operational staging outside the bundle.
Flagged that this settles export, not canonical membership — they are not the
same claim.

## External lane check

`git fetch origin codex/runtime-fiction-openspec` → 2 commits ahead
(`cbbc2a75`, `9638bef1`), diff vs main is `.agents/worktrees.md` +`15` and
`STATUS.md` ±1 — **coordination only, no spec content yet**. It does not touch
`openspec/changes/brain-okf-canonical-store/` or `openspec/specs/`. No overlap,
no contradiction. Its STATUS claim edit is on the runtime-fiction row (line 28),
which this lane deliberately did **not** touch.

`gh pr list --limit 60`: no open PR touches
`openspec/changes/brain-okf-canonical-store/`. PR #1369 (the change's own PR) is
**MERGED**. Nothing built around.

## Evidence

| Check | Result |
|---|---|
| `openspec validate brain-okf-canonical-store --strict` | `Change 'brain-okf-canonical-store' is valid` — passes before **and** after the edits (openspec CLI 1.4.1) |
| `openspec list` | `brain-okf-canonical-store  10/16 tasks` (was 9/16) |
| `python -m pytest tests/test_okf_export.py -q` | **4 passed** in 0.34s — evidence for the 5.1/5.3 partially-landed findings |
| `python -m ruff check tinyassets/wiki/okf_export.py` | `All checks passed!` |
| Pre-commit hooks (both commits) | mirror parity N/A, mojibake clean, cross-provider-drift clean, skills-valid pass |
| `python scripts/check_context_budget.py` | STATUS.md **59/60 lines** (unchanged by this lane), bytes 9847 → **9920** |

**No Python was touched** — the diff is Markdown only, so "scoped pytest for
every module touched" is vacuous; the test run above is evidence for a *claim*,
not for a change. Nothing was weakened, xfailed, or skipped.

**Pre-existing red, reported honestly:** `check_context_budget.py` reports
STATUS.md `OVER-HARD` on bytes (9920 / 4096) — it was already `OVER-HARD` at
9847 before this lane, caused by other lanes' rows. This lane's edit added
**73 bytes** and **zero lines** to an already-red gate; it did not turn a green
gate red. The row was tightened after a first draft to cut that delta. Not fixed
here: trimming STATUS is other lanes' rows and would be uncoordinated deletion
while five fable-fleet lanes are ACTIVE.

**No STATUS Work row was added for this lane.** Adding one would breach the
60-line hard ceiling and duplicate the host ask that already exists as the
"Resolve target-spec PLAN conflicts" row — AGENTS.md requires coalescing
duplicate host asks to one. The dependency was made explicit inside that row
instead.

## Cross-family gate

Per CLAUDE.md's standing Codex reflex, the blocking analysis was dispatched to
Codex (`codex exec`, read-only, `approval_policy=never`, lane-local out path) with
an explicit **refute-this** framing and the exact verify commands. Verdict:

```
VERDICT_A: confirmed        (4.1 and 4.3 must not be executed now)
VERDICT_B: confirmed        (5.1 is partially landed in the export direction)
RECOMMENDED_TERMINAL_STATE: ii   (leave 4.1/4.3 unchecked with recorded block
                                  reasons; finish only unblocked work)
```

Codex cited `tasks.md:12`, `design.md:58,61`, `PLAN.md:560`, `STATUS.md:30`,
`okf_export.py:1,15,25`, and `knowledge-retrieval-and-memory/spec.md:386,404`,
and independently confirmed #1369 as MERGED at 2026-06-25T07:27:22Z. The verdict
file is at `.lane/codex_verdict.md` (gitignored, not committed).

## Commits pushed

| SHA | Subject |
|---|---|
| `5114da3f` | coord: name the brain-store decision's gated consumers on the host-decision row |
| `dda6b9f4` | spec(brain-okf): record a verified disposition for all 7 open tasks |

Pushed to `origin/claude/o5-brain-okf-canonical-store`. **No PR opened**, per the
lane brief — cross-family review precedes any PR.

## What the host needs to decide

One thing, and it unblocks 2.1 → 4.1 → 4.3 in order: **the target-spec PLAN
store decision** (the existing `host-decision` STATUS row). Until it lands, this
change is correctly parked. §5 additionally needs a successor change created to
own the forward build; it should not be resurrected inside this one.
