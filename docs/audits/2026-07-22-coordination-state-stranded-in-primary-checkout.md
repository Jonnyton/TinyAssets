# Coordination state stranded in the primary checkout

**Date:** 2026-07-22
**Lane:** `claude/audit-stranded-coordination-state`
**Provider:** claude-code
**Base:** `origin/main` @ `398b3256`
**Scope:** audit + recovery of two uncontended files. Proposes a fix; implements none.

---

## 1. Summary

Three **shared coordination files** were dirty in the primary checkout
(`C:/Users/Jonathan/Projects/TinyAssets`), and their added content existed on **no git ref
anywhere** — not unpushed, never committed:

| File | Added | What it holds |
|---|---:|---|
| `.agents/worktrees.md` | +39 | 27 `CREATE` + 12 `REMOVE` lane records, all dated 2026-07-22 |
| `.agents/uptime.log` | +6 | 6 RED probe records, 2026-07-21T18:45→19:19 −07:00 |
| `STATUS.md` | +2 | a **P0 security Concern** against merged PR #1489, and a `host-action` Work row |

This PR commits the two uncontended files. It deliberately does **not** touch `STATUS.md`
(§7 explains; §6 gives the rows for the owning lane to fold in).

`AGENTS.md` designates `.agents/worktrees.md` and `STATUS.md` as *the* cross-provider shared
state — the durable layer that exists precisely because "a branch is not memory." The stranding
has reached the coordination files themselves.

---

## 2. Zero-refs proof

Run from the primary checkout with `MSYS_NO_PATHCONV=1` set (without it,
`git show origin/main:<path>` can silently return empty on Git Bash for Windows):

```bash
$ git diff --stat STATUS.md .agents/worktrees.md .agents/uptime.log
 .agents/uptime.log   |  6 ++++++
 .agents/worktrees.md | 39 +++++++++++++++++++++++++++++++++++++++
 STATUS.md            |  2 ++

$ git cat-file blob origin/main:STATUS.md | grep -c "1489"                  -> 0
$ git cat-file blob origin/main:STATUS.md | grep -c "wf-daemon-key-binding" -> 0
$ git log --all --oneline -S "wf-daemon-key-binding" -- STATUS.md           -> (empty)
```

`-S` across `--all` is the load-bearing check: it proves the string never entered *any* commit
on *any* ref, which "unpushed" would not.

**The ledger grew while this audit was being written.** The commissioning brief measured +37;
by the time the recovery worktree existed it was **+39** — `wf-issue-1346-triage` and this
lane's own `CREATE` record appended in the interval. Creating the worktree that fixes the
problem *demonstrated* the problem. That record is included in this commit rather than stripped:
it is a true event, and the honest count is 39.

---

## 3. `.agents/worktrees.md` — 39 lane records

27 `CREATE`, 12 `REMOVE`, 39 distinct branches, all stamped 2026-07-22. All 12 `REMOVE` records
carry `merged=True`.

The 12 `REMOVE` records are the ones with real forensic value: they are the only durable
statement that those branches were swept **after merging**, not abandoned. Without them a later
sweep re-derives merge status from reachability — and per the `stale-backlog-rows-misdirect`
memory (extended 2026-07-22, PR #1510), **squash merge makes `git rev-list main..branch` report
merged branches as unmerged forever.** The ledger is the cheap, correct record that squash-merge
reachability destroys. Losing it is not cosmetic.

---

## 4. `.agents/uptime.log` — 6 RED records that are FALSE REDs

```
2026-07-21T18:45:03-07:00 RED layer=wiki url=https://tinyassets.io/mcp exit=6 rtt_ms=510
    reason='HTTP 401 on tools/call: Unauthorized'
    ... 5 more through 19:19:47-07:00
```

**These are not evidence of an outage, and must not be read as one.** They are instances of the
class documented in PR #1513 (`docs/audits/2026-07-22-uptime-canary-false-red-incident.md`):
the probe asserts a response contract that `972d0cc3` retired, so it reports `exit=6` against a
healthy service. #1513 measured **104 consecutive false reds across 6.15 days, zero green**;
these six (2026-07-22T01:45→02:19Z) sit at the tail of that streak.

They are committed because the log is an append-only record of *what the probe emitted*, and
that is true. This section exists so the next reader does not open a P0 against a healthy
surface — the exact failure #1513 documents. The instrument is broken; the service is not.

---

## 5. Root cause — `wt.py` writes a ledger the writing lane cannot commit

Not "nobody remembered to commit it." The append is **structurally uncommittable by the lane
that generates it**.

`scripts/wt.py`:

```python
def repo_root() -> Path:
    # In a worktree, point at the main checkout so siblings are consistent.   # :95
    common = _run(["git", "rev-parse", "--git-common-dir"])
    ...
        if git_common.name == ".git":
            return git_common.parent                                          # :100

def log_event(root: Path, line: str) -> None:                                 # :104
    path = root / ".agents" / "worktrees.md"                                  # :105
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"- {stamp} {line}\n")
```

`repo_root()` resolves `--git-common-dir` to the **primary checkout** — deliberately, "so
siblings are consistent." So when a lane runs `wt.py new` from its own worktree, `log_event`
appends to `<primary>/.agents/worktrees.md`: a file that is **not in that lane's branch and not
in its checkout**. The lane commits its branch; the record is somewhere else entirely.

The append is simultaneously *correct* (one consistent ledger) and *guaranteed to strand*, because
the only checkout that could commit it is the primary one — which is dirty, sits on `main`, and
which `AGENTS.md` Hard Rule 13 and the dirty-main safety rule both forbid committing from. The
ledger is **write-only by construction**.

The commit history confirms it. Since `wt.py` landed (`4e14fc91`), `.agents/worktrees.md` has
reached `main` essentially once — `89edf995 "Rename project to TinyAssets"`, a mechanical rename
sweep. Not one deliberate ledger commit in the file's life under the tool that writes it.

`scripts/worktree_status.py` does not close the loop either. It references the ledger only inside
advisory **strings** (`:506`, `:612` — "Log remove/sweep in `.agents/worktrees.md`"); it never
checks whether the ledger is committed. Both halves of the tooling assume the other did it.

---

## 6. The two orphaned `STATUS.md` rows — verbatim, with premise checks

Reproduced verbatim for whoever lands the `STATUS.md` lane. **Both were premise-checked against
`origin/main` rather than restated**, per `stale-backlog-rows-misdirect`.

### Row A — P0 Concern (Concerns section)

```
- **[P0 filed:2026-07-21 verified:2026-07-21]** #1489: unauth LAN leaks sessions and permits CSRF writes/paid hires. Codex: ADAPT; do not LAN-run.
```

**Premise: CONFIRMED and live.** PR #1489 is `MERGED` (`220a1fc8`). `origin/main`'s `STATUS.md`
contains no row mentioning 1489. A P0 security finding against landed code is recorded in no
shared surface.

⚠ **The stranded hunk no longer applies.** PR #1506 merged as `398b3256` after the brief was
written and rewrote the Concerns section (67 lines/13.8 KB → 54 lines/5.3 KB). The hunk's anchor
context (`RESHAPE (host directive)`) has **0 matches** on current `origin/main`. Row A must be
re-added by hand, not rebased or `stash pop`-ed.

### Row B — `host-action` Work row

```
| Publish #1491 replacement: local `codex-tmp/wf-daemon-key-binding` at `c67ff97f`; branch-create was cancelled | tinyassets/api/daemon_enrollment.py, tests/test_daemon_enrollment_forge_probes.py | #1471 → #1472 (`c11b145b`) | host-action |
```

**Premise: the row's *conclusion* is CORRECT; its *mechanism* is stale — and the published
correction of it is also wrong.** Three-way check:

| Claim | Verdict | Evidence |
|---|---|---|
| Work is stranded on local disk only | **stale** | `3e7d16f2` *is* on origin — but on `origin/chore/mutation-probe-coverage`, the #1491 PR branch |
| PR #1491 merged; row is false, delete it (**asserted by open PR #1514**) | **wrong** | `#1491` is `OPEN`, `mergedAt=null`, head `cee48beb` |
| Work reached `origin/main` | **wrong** | `git merge-base --is-ancestor 3e7d16f2 origin/main` → fails; `git ls-tree -r origin/main \| grep -i enrollment` → **no matches**; both named files absent from `origin/main` entirely |

So: the work is pushed but **unmerged**. PR #1514's body states this row "is **false** and should
be deleted." Acting on that would delete the only STATUS-visible tracking of an **unmerged auth
fix** titled *"a one-column DML write achieved full daemon impersonation"* (`3e7d16f2`, 2 files,
+451 lines).

**Recommendation:** do not delete Row B — **rewrite** it, since its stated mechanism
("branch-create was cancelled", a local sha) is what went stale, not its need:

```
| Merge #1491 `chore/mutation-probe-coverage` (`3e7d16f2`, daemon-impersonation auth fix) — pushed, unmerged; `daemon_enrollment.py` absent from main | tinyassets/api/daemon_enrollment.py, tests/test_daemon_enrollment_forge_probes.py | - | host-action |
```

This is the `stale-backlog-rows-misdirect` class recursing one level: an audit written to catch
stale premises carries a stale premise about a stale premise. The generalizable rule —
**"pushed to a PR branch" and "on `origin/main`" are different states, and a row must be checked
against `origin/main`, never against "does a ref exist somewhere."**

---

## 7. Why this PR does not touch `STATUS.md`

`STATUS.md` is the contended file. #1506 merged mid-flight; #1507 is `CONFLICTING`/`DIRTY`; #1510
is open against it. Adding a third concurrent writer worsens a live conflict. This follows the
pattern PR #1513 established and #1514 repeated: write the recommended rows into the audit, let
the owning lane fold them in.

`.agents/activity.log` is the current hot conflict spot (#1506 and #1507 both conflicted there) —
**untouched here** as well.

Contention was verified, not assumed:

```bash
$ git merge-tree --write-tree origin/main claude/audit-stranded-coordination-state | grep CONFLICT
(no output)
```

`merge-tree` names the exact conflicting paths; GitHub's `mergeable` field is computed
asynchronously and returned `UNKNOWN` for every PR queried during this audit, so it was not
relied on.

---

## 8. Recurrence history

| # | What was stranded | Scale |
|---|---|---|
| #1489 | Agent Village command center — feature + tests, never committed | 26 files, 37 tests |
| #1490 | Documents existing only in one stale checkout | 32 documents |
| #1517 | Fundraising material unversioned behind a gitignore gap | 22 files |
| #1514 | Finished work stranded across ~170 checkouts | 2 lanes genuinely stranded |
| **this** | **The coordination files themselves** | **3 files, 45 lines, 39 lane records** |

The progression matters: #1489/#1490/#1517/#1514 stranded *product and documents*. This one
stranded *the mechanism that is supposed to make stranding visible.* A ledger that records what
the fleet did, which the fleet cannot see, cannot catch the next instance.

**Distinct from #1514.** #1514 audits work existing as git objects on unpushed/unmerged
branches. This audits working-tree modifications in **no commit at all**. #1514's ~170-checkout
sweep could not have found these — they are not in any checkout's history, they are uncommitted
edits in the primary tree.

---

## 9. Prevention proposal — not implemented here

Per the brief and `AGENTS.md`'s auto-iterate ladder (`WebSite/HOOKS_FUSE_QUIRKS.md`), this is
proposed and scoped separately. No hook is added and `wt.py` is unchanged in this PR.

**Union-merge alone does not fix this.** PR #1523 adds `merge=union` in `.gitattributes` for
`.agents/activity.log`, correctly, for a *different* failure: collision between lanes that each
commit the file. `.agents/worktrees.md` is never committed by any lane at all. Union-merge makes
concurrent commits *converge*; it cannot make an uncommitted file *reach a ref*. Applying #1523's
fix here and calling it done would leave the stranding untouched while looking addressed.

Ranked smallest-first:

**L1 — detection (smallest, immediate).** Teach `scripts/worktree_status.py` to report an
uncommitted `.agents/worktrees.md` in the primary checkout, with the carry recipe. It is already
a mandated session-start ritual (`AGENTS.md` § Provider session-start ritual, step 2), already
reads the primary checkout, and already prints advisory strings about this file — it just never
checks it. Cheapest durable rung, no new machinery. Does not stop stranding; guarantees it is
seen within one session.

**L2 — structural (recommended).** Split the ledger into per-lane append-only files —
`.agents/worktrees.d/<slug>.md` — written into **the lane's own worktree**, so the lane commits
its own record alongside its own PR. This inverts the defect in §5: the record travels with the
branch that caused it. Distinct files cannot collide, so it needs no merge driver. A digest
command concatenates `.agents/worktrees.d/*` for reading. Cost: `wt.py done` for a *removal* runs
after the lane is gone, so `REMOVE` records still need a home — likely the primary ledger, which
keeps a reduced version of the problem and is why L1 stays useful alongside L2.

**L3 — if it recurs after L1+L2.** `merge=union` on the residual shared ledger (composing with
#1523 rather than duplicating it), plus a `SessionStart` check that fails loudly.

**Recommendation: L1 now, L2 scoped as its own change, L3 held in reserve.** L1 and L2 are
independent and can land in either order. Per `AGENTS.md` § Spec-driven development, L2 is a
behavior change to a documented workflow tool and should start as an OpenSpec change; L1 is
arguably a bug fix to an existing diagnostic and may not need one.

---

## 10. What this PR does

- Commits `.agents/worktrees.md` (+39) and `.agents/uptime.log` (+6) — 2 files, 45 insertions.
- Adds this audit.
- Touches no other file. No `git add -A`: the primary checkout has **7,769** untracked paths
  (verified), including `data-room/`, `investor-list/`, and `pitch-deck/` — private company
  material in a public repo. Every path was staged explicitly.
- Leaves the primary checkout's working tree exactly as found. No `git clean`, `restore`,
  `checkout --`, or `reset` was run anywhere (Hard Rule 13); the stranded content was **copied**,
  not moved, so the primary checkout remains a fallback until this lands.

## 11. Open items for other lanes

1. **`STATUS.md` owner (#1506/#1507 lane):** fold in Row A verbatim; fold in Row B **rewritten**
   per §6 — do not delete it.
2. **PR #1514 author:** its "#1491 merged / row is false" claim is wrong (§6). #1491 is open and
   `daemon_enrollment.py` is absent from `origin/main`.
3. **The #1489 P0 itself is not addressed here** — a codex brief
   (`command-center-lan-failopen-p0.md`) is queued. This audit's obligation was that the concern
   is *recorded*, not that it is fixed.
4. **L1/L2 prevention (§9)** needs an owner.
