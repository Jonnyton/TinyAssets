# STATUS.md write contention — measurement

**Date:** 2026-07-22
**Author:** claude-code (lane `claude/status-write-contention`)
**Cross-family review:** Codex (`gpt-5`), read-only refutation pass — verdict in §8.
**Type:** measurement audit. **No restructuring proposed as a decision** — options
only, plus one `host-decision` STATUS row.
**Premise status:** the headline number this lane was dispatched on is **refuted**,
with a verified root cause. See §1.

---

## 0. TL;DR

| Question | Answer |
|---|---|
| How many open PRs write `STATUS.md`? | **14** (13 eleven minutes earlier). Not 23. |
| Where did 23 come from? | **A substring match on `status`** instead of exact path equality. Reproduced exactly. §1.2 |
| How many are single-row edits? | **8 of 14** change ≤2 lines per side; **9 of 14** ≤3. §2 |
| How many actually conflict on `STATUS.md`? | **9 of 14**. §3 |
| How many are blocked *solely* by `STATUS.md`? | **1** (`#1550`). §3.2 |
| Would sharding `STATUS.md` unblock the backlog? | **No.** It would unblock exactly one PR. §3.2 |

The trend the lane was dispatched to act on (`12 → 13 → 23`) is not a trend — the
23 is a different metric. The contention *is* mechanical (§2), but it is blocking
far less than believed (§3). Recommendation in §5: **land `#1523` first**, then
re-measure.

---

## 1. The writer count

### 1.1 Measurement

Documented command (from the dispatch brief), run twice:

```bash
mkdir -p .tmp && : > .tmp/pr-files-cache.txt
for n in $(gh pr list --state open --limit 120 --json number --jq '.[].number'); do
  gh pr view $n --json files --jq '.files[].path' | sed "s/^/$n\t/" >> .tmp/pr-files-cache.txt; done
awk -F'\t' '$2=="STATUS.md"' .tmp/pr-files-cache.txt | wc -l
```

| when | open PRs | `STATUS.md` writers |
|---|---|---|
| 2026-07-22T08:09Z | 93 | **13** |
| 2026-07-22T08:20Z | 94 | **14** (`#1581` opened at 08:12Z) |

Distinct PR numbers equal the row count in both runs — no double-counting.
Re-running with `--limit 200` changes nothing (93/94 open PRs is under either cap).

### 1.2 Where the 23 actually came from — reproduced

The 23 is a **real count of a different thing**: PRs touching any path containing
`status`, case-insensitively — not PRs touching `STATUS.md`.

```bash
# exact path equality (correct)
awk -F'\t' '$2=="STATUS.md"{print $1}'        .tmp/cache.txt | sort -u | wc -l   # -> 14
# case-insensitive substring (what produces 23)
awk -F'\t' 'tolower($2) ~ /status/{print $1}' .tmp/cache.txt | sort -u | wc -l   # -> 24
# same, excluding #1581 which opened at 08:12Z, i.e. the earlier survey's view
awk -F'\t' 'tolower($2) ~ /status/ && $1!=1581{print $1}' .tmp/cache.txt | sort -u | wc -l   # -> 23
```

**The substring count at the earlier survey's snapshot is exactly 23.** The false
positives are ordinary files that happen to contain the word:

```
tinyassets/api/status.py                     scripts/worktree_status.py
tests/test_api_status.py                     scripts/fleet_status.py
tests/test_get_status_primitive.py           docs/audits/2026-07-22-status-backlog-audit.md
tests/test_sandbox_status.py                 docs/audits/2026-07-22-status-janitor-pr1506-codex-review.md
tests/test_get_status_engine_binding.py      docs/audits/2026-07-22-status-concerns-staleness-residue.md
tests/test_worktree_status_clones.py         packaging/.../runtime/tinyassets/api/status.py
```

Note the irony: three of the false positives are *audit documents about STATUS.md*,
so the act of auditing the contention inflates the next survey's contention number.

This root cause was found by the Codex cross-family pass (§8) and then verified
independently by the command above.

**Corroborating arithmetic** — 23 was never reachable as a true writer count.
Since 2026-07-21T00:00Z, **28** PRs closed, of which exactly **2** touched
`STATUS.md` (`#1559`, `#1506`). With 14 open writers now, the population ceiling
anywhere in that window is ~16.

**Process note.** This is the project's recurring stale-premise class, with a new
variant worth naming: **a metric that decays is one problem; a metric that was
never measuring the stated thing is a worse one.** The `12 → 13 → 23` series
silently switched units between samples. Trends assembled from snapshots taken by
different sessions must re-derive every point with one command, or not be quoted
as a trend.

### 1.3 Measurement traps for anyone re-running this

Three tooling routes are silently unreliable:

- **Substring vs. exact path.** Use `$2=="STATUS.md"`. `grep STATUS.md` is also
  unsafe — `.` is a regex wildcard.
- **`gh pr view --json files` caps at 100 files.** `#1471`, `#1472`, `#1477`,
  `#1491` all return exactly `100`; their real file lists are longer. `STATUS.md`
  sorts inside the first 100 for all four so this audit is unaffected, but a file
  sorting later **would be silently missed**. Treat `length == 100` as "truncated".
- **`gh pr diff` returns 0 bytes** for those same four PRs — not an error, an empty
  result. A `gh pr diff | grep` pipeline scores them as "does not touch STATUS.md".

The only route that worked for all 14 was the per-file counts inside `files[]`:
`.files[]|select(.path=="STATUS.md")|.additions,.deletions`.

---

## 2. Edit shape — is the contention mechanical?

This is the ratio the brief correctly identified as the whole argument: if most
writers add or remove **one row**, contention is mechanical and fixable; if they
rewrite the table, it is not.

| PR | + | − | draft | merge state | branch |
|---|---|---|---|---|---|
| 1581 | 1 | 0 | **non-draft** | BEHIND | `openspec/reconcile-round2` |
| 1574 | 2 | 3 | draft | BEHIND | `codex/compute-market-frontier-research` |
| 1550 | 1 | 1 | **non-draft** | DIRTY | `codex/wiki-discovery-separation` |
| 1542 | 1 | 1 | draft | BEHIND | `codex/paid-market-track-e-wave2-spec` |
| 1507 | 1 | 0 | **non-draft** | DIRTY | `claude/status-release-cron-watch` |
| 1491 | 9 | 11 | draft | DIRTY | `chore/mutation-probe-coverage` |
| 1478 | 5 | 4 | draft | CLEAN | `feat/authority-ci-gates` |
| 1477 | 9 | 11 | draft | DIRTY | `feat/patch-loop-leasestore-fix2` |
| 1472 | 1 | 1 | draft | UNSTABLE | `feat/patch-loop-runner` |
| 1471 | 2 | 7 | draft | DIRTY | `feat/patch-loop-integration` |
| 1469 | 1 | 0 | draft | DIRTY | `feat/credential-vault` |
| 1464 | 2 | 7 | draft | DIRTY | `feat/patch-loop-s1` |
| 1439 | 1 | 0 | draft | BEHIND | `worktree-website-app-download` |
| 1438 | 1 | 0 | draft | DIRTY | `claude/android-universe-conversation` |

**The ratio: 8 of 14 (57%) change ≤2 lines on each side. 9 of 14 (64%) change ≤3.**

Reading the actual hunks shows the granularity is better than the counts suggest —
**all 14 operate on whole lines**. Not one reflows the table, renames a column, or
changes the schema. The five "pure append" cases (`#1581`, `#1507`, `#1469`,
`#1439`, `#1438`) add exactly one Work row or one Concern bullet and touch nothing
else.

The remaining 5 (`#1464`, `#1471`, `#1477`, `#1478`, `#1491`) are **janitor-scale**
— batch-deleting resolved Concern bullets and replacing Work rows. `#1478`
additionally renumbers the ordered `Next` list (`5.` → `5.`,`6.`), the one
genuinely structural coupling found anywhere in the set.

**So: the contention is mechanical.** The edits are row-granular by nature. This
is the part of the brief's thesis that survives measurement intact.

---

## 3. What is actually conflicting

Counting *writers* overstates the problem: two PRs can both write a file and still
merge cleanly. The real metric is a merge trial:

```bash
br=$(gh pr view $n --json headRefName --jq '.headRefName'); git fetch origin "$br" -q
git merge-tree --write-tree --name-only origin/main FETCH_HEAD | grep CONFLICT
```

### 3.1 Correcting the brief's three DIRTY PRs

The brief states two of the three conflict on `STATUS.md`. Measured:

| PR | brief says | **actually conflicts on** |
|---|---|---|
| `#1550` | STATUS.md | **`STATUS.md`** ✓ |
| `#1507` | STATUS.md | **`.agents/activity.log`** ✗ — its `STATUS.md` auto-merges cleanly |
| `#1524` | openspec tasks.md | `openspec/changes/universe-creation/tasks.md` ✓ |

**Only 1 of the 3 conflicts on `STATUS.md`.** The brief's designated "sharpest
case" — `#1507`, chosen precisely because it touches both high-contention files —
is blocked by the **activity.log** conflict. Its `STATUS.md` change (`+1` Concern
bullet) merges without complaint.

That inverts what `#1507` is evidence *for*: it argues for landing `#1523` (the
activity-log sharding fix, already built and owned), not for restructuring
`STATUS.md`.

### 3.2 Full conflict matrix — the decisive number

| PR | STATUS.md conflict? | also conflicts on | behind main |
|---|---|---|---|
| 1581 | no | — | 0 |
| 1574 | no | — | 2 |
| **1550** | **YES** | **— (nothing else)** | 8 |
| 1542 | no | — | 7 |
| 1507 | no | `.agents/activity.log` | 11 |
| 1491 | YES | `providers/base.py`, `pyproject.toml`, tests, exec-plan | 28 |
| 1478 | YES | `providers/base.py`, `pyproject.toml`, tests, exec-plan | 28 |
| 1477 | YES | `providers/base.py`, `pyproject.toml`, tests, exec-plan | 28 |
| 1472 | YES | `providers/base.py`, `pyproject.toml`, tests, exec-plan | 29 |
| 1471 | YES | `providers/base.py`, `pyproject.toml`, tests | 29 |
| 1469 | YES | `pyproject.toml` | 29 |
| 1464 | YES | `tests/test_get_status_primitive.py` | 29 |
| 1439 | no | — | 46 |
| 1438 | YES | `docs/design-notes/INDEX.md` | 51 |

**9 of 14 conflict on `STATUS.md`. But exactly 1 — `#1550` — is blocked solely by it.**

For the other 8, `STATUS.md` is a passenger. They are conflicted on
`tinyassets/providers/base.py`, `pyproject.toml`, and test files. Resolving
`STATUS.md` for any of them unblocks nothing; they are stale long-lived feature
branches 28–51 commits behind main, and their real problem is branch age.

**Any `STATUS.md` sharding scheme would, today, unblock one pull request.**

### 3.3 The counter-example that constrains the design

`#1439` is **46 commits behind main** and its `STATUS.md` **still auto-merges**. It
is a pure single-row append. Meanwhile `#1550` is only **8 commits behind** and
conflicts.

Distance from main is not the driver — *where you edit* is. A single-row append at
a stable anchor survived 46 commits of drift. That is direct evidence the
mechanical fix in §4 would work if adopted, and equally that most writers do not
currently need it.

### 3.4 Cause

`STATUS.md` took **18 commits on `origin/main` across 6 distinct days** since
2026-07-13 (~2/day). Only **2** of those 18 were janitor-scale (≥8 changed lines);
the rest were row-level claims and releases.

The conflicts cluster on branches cut *before* a janitor pass and merged *after*
it. `398b3256` ("janitor pass — 67 lines/13.8 KB → 55 lines/5.3 KB", `+28/−41`) is
the largest anchor-mover in the window. Janitor passes are not optional — the file
header mandates a **4 KB / 60-line budget** — so the periodic wholesale rewrite is
a *designed-in* property of `STATUS.md`, and it is what breaks the row-level
appends underneath it.

**The size budget and the low-conflict property are in direct tension.** Any option
in §4 that does not address the janitor pass leaves the dominant cause untouched.

---

## 4. Options

`STATUS.md` as the single shared claim surface is a deliberate `AGENTS.md` design
decision: *"STATUS.md Work table is the authoritative claim surface. No external
locks."* Per `AGENTS.md` ("if your approach conflicts with a principle, do NOT
implement it — record the conflict"), **nothing below is implemented.**

Every option is judged against the property `AGENTS.md` is protecting:

> *"A provider with a fresh checkout, no chat history, and no announcement should
> be able to start working productively in under a minute."*

Call it **the one-minute property**: one file, readable top to bottom, no build step.

### Option A — do nothing (baseline)

Land `#1523`; let branch-age attrition handle the rest.

- **Cost today:** one PR (`#1550`) needs a manual `STATUS.md` conflict resolution.
- **One-minute property:** fully preserved.
- **Risk:** if the writer population genuinely grows (it has not — §1.2), revisit.
  Re-measure per restock cycle rather than assuming.
- **Honest assessment:** the measured evidence supports this option. One blocked
  PR is not a structural problem.

### Option B — `scripts/status_claim.py` (single-row helper)

A script that adds / flips / deletes exactly one Work row, so agents never
hand-edit the table.

- **Preserves the one-minute property completely** — `STATUS.md` stays one
  human-readable file; the script is a convenience, not a format change.
- Keeps edits minimal and well-anchored, which §3.3 shows is what survives merges.
- **Does not fix the dominant cause.** Janitor passes (§3.4) are wholesale
  rewrites by design; a single-row helper cannot make a `+28/−41` budget-trim
  non-conflicting.
- Cheapest option with any real effect. Adoption is voluntary unless hook-enforced.

### Option C — `STATUS.d/` per-lane claim files (mirrors `#1523`)

Each lane owns `STATUS.d/<lane>.md`; a script folds them into a rendered view.

- **Eliminates claim-row conflicts structurally** — the proven shape, since `#1523`
  does exactly this for `.agents/activity.log`.
- **Breaks the one-minute property.** A fresh provider must read a directory and
  know a render command exists. This is the direct conflict with `AGENTS.md` and
  why it is not a default recommendation.
- Mitigable by committing a generated `STATUS.md` — but that reintroduces a single
  file every lane writes, i.e. the original problem plus a build step.
- **Cost/benefit today is poor:** structural fix deployed against 1 blocked PR.

### Option D — append-only claims file + periodic fold

Lanes append to `CLAIMS.md` (append-only ⇒ near-conflict-free); a janitor folds
entries into the `STATUS.md` table.

- Append-only files still conflict when two lanes append at the same EOF anchor —
  reduced, not eliminated.
- **Splits the one-minute property in a subtle, worse way:** truth lives in two
  places and a reader must check both to know whether a row is claimed. Strictly
  worse than C, which at least has one rendered view.
- Adds a fold step that can silently fall behind — a new stale-state class.

### Summary

| | conflicts fixed | one-minute property | cost | unblocks today |
|---|---|---|---|---|
| **A** do nothing | none | ✅ preserved | none | 1 (by hand) |
| **B** `status_claim.py` | row-level only | ✅ preserved | small | 0 (preventive) |
| **C** `STATUS.d/` | structural | ❌ **broken** | medium | 0 |
| **D** append-only + fold | partial | ⚠️ split across 2 files | medium | 0 |

None of B/C/D unblocks a PR today; all are preventive. Only A addresses the one
genuinely blocked PR.

---

## 5. Recommendation (for the host to accept or reject)

1. **Land `#1523` first.** Built, owned, and it fixes the conflict actually
   blocking a non-draft auto-merge PR (`#1507`). It is itself stranded (non-draft,
   auto-merge enabled, `BEHIND`) — unstranding it is the highest-value action
   available and needs no new design.
2. **Then re-measure before building anything for `STATUS.md`.** On this data the
   `STATUS.md` fix is preventive, not corrective. Option **B** is the only one that
   does not trade away the one-minute property.
3. **Do not adopt C or D on current evidence.** Both break or split the property
   `AGENTS.md` exists to protect, in exchange for unblocking zero PRs.

## 6. Blocked work — recorded, not touched

Per scope, this lane did **not** rebase or resolve any other lane's branch.

- `#1550` — blocked by a real `STATUS.md` conflict. **Owner action required.** The
  only PR in the set where `STATUS.md` is the sole blocker.
- `#1507` — blocked by `.agents/activity.log`, not `STATUS.md`. Resolved by
  landing `#1523`.
- `#1524` — blocked by `openspec/changes/universe-creation/tasks.md`. Unrelated to
  either shared-file lane.

## 7. Reproduction

All commands are read-only. `git merge-tree --write-tree` writes only to the object
store; it touches no working tree and no ref.

```bash
export MSYS_NO_PATHCONV=1
git fetch --prune

# writer count — EXACT match, not substring
mkdir -p .tmp && : > .tmp/pr-files-cache.txt
for n in $(gh pr list --state open --limit 200 --json number --jq '.[].number'); do
  gh pr view $n --json files --jq '.files[].path' | sed "s/^/$n\t/" >> .tmp/pr-files-cache.txt; done
awk -F'\t' '$2=="STATUS.md"{print $1}' .tmp/pr-files-cache.txt | sort -u | wc -l

# the 23: same cache, substring match
awk -F'\t' 'tolower($2) ~ /status/{print $1}' .tmp/pr-files-cache.txt | sort -u | wc -l

# edit shape (NOT `gh pr diff` — returns 0 bytes on large PRs)
gh pr view $n --json files \
  --jq '.files[]|select(.path=="STATUS.md")|"\(.additions)+/\(.deletions)-"'

# what actually conflicts
br=$(gh pr view $n --json headRefName --jq '.headRefName'); git fetch origin "$br" -q
git merge-tree --write-tree --name-only origin/main FETCH_HEAD | grep CONFLICT

# main's churn
git log origin/main --since=2026-07-13 --format='%x00' --numstat -- STATUS.md
```

## 8. Cross-family review (Codex, read-only)

Dispatched as a refutation pass — "default to refuted if ambiguous" — against three
claims. Verdicts:

| Claim | Codex verdict | Outcome |
|---|---|---|
| 13 open PRs write `STATUS.md` | **refuted** | Correct: 14 by the time Codex ran (`#1581`). Adopted. |
| 23 unreachable; cause unknown | **refuted** | Codex supplied the actual cause — substring matching — which I then reproduced exactly (23). My "double-append" guess was wrong and is removed. |
| 9 conflict, only `#1550` STATUS-only | **confirmed** | Independent merge-trial reproduction. |

> **Codex, biggest error:** *"Counting `status.py`, tests, and status-related docs
> as `STATUS.md` writers instead of requiring exact path equality."*

Codex also corrected the closed-PR count (28, not 26 — two closed between the runs).

**Operational note for future dispatches.** The first two Codex attempts returned
no verdict: attempt 1 died on a POSIX-style `--cd` path (`os error 2`); attempt 2
spent its entire budget executing this repo's session-start orientation ritual
(skills, `worktree_status.py`, `claim_check.py`, `provider_context_feed.py`) and
never reached the question. Both exited **0** with no usable output — the
silent-failure shape. A read-only Codex fact-check needs an explicit
"do not run any session-orientation ritual; start answering immediately" preamble,
and its output must be checked for an actual verdict rather than a non-zero exit.
