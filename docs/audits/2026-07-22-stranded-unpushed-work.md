# Stranded unpushed work: what is actually lost, and why lanes stop before the PR

**Freshness:** swept 2026-07-21 PDT / 2026-07-22 UTC against `origin/main`
`2c1f63cb`. Every classification below was re-derived from `git`/`gh` at that
point; none is carried over from a prior document. Commands are in §7 so any
claim can be re-run.

**Scope:** read-and-report. No scratch directory or worktree was modified,
cleaned, or deleted (AGENTS.md Hard Rule 13). The only file this lane creates is
this audit.

---

## 1. Headline

The commissioning brief was right that finished work is dying on local disk, and
right about the specific instance. It was **wrong about the severity framing**,
and **four of its five supporting examples have since resolved**. Both
corrections matter, because the wrong framing is what would send the next lane
chasing a production outage that does not exist.

| Claim in the brief | Verdict |
|---|---|
| A completed canary fix sits unpushed in `.codex-scratch-uptime-canary-1461/` with no PR | **CONFIRMED** |
| It is a fix to "a live P0" / "the P0 stayed red for four days" | **REFUTED** — see §2 |
| Four `../wf-audit-*` lanes "opened no PR" | **STALE** — all four have open PRs #1508–#1511 |

Across 114 registered worktrees, 34 `.claude/worktrees/` entries, 25 `codex-tmp/`
entries and one scratch clone, exactly **two** lanes hold work that is both
absent from every origin ref and still worth something. Everything else is
landed, superseded, or composition-only. Stranded is common; stranded *and
valuable* is rare.

---

## 2. Correction to the brief: the P0 is a false red

The brief describes the canary fix as rescuing a live P0 that "stayed red for
four days." That framing does not survive contact with the evidence.

PR **#1513** (branch `claude/docs/audit-canary-false-red-0722`, opened
2026-07-22T02:03Z) documents the incident in full: production was healthy for
**all 104 consecutive red runs** from `2026-07-15T21:31:53Z` to
`2026-07-22T01:11:35Z`. The probe was asserting a response contract that commit
`972d0cc3` retired 37 minutes before the first red — anonymous pure-write calls
are now rejected *pre-dispatch* with HTTP 401 + `WWW-Authenticate`, so the
tool-result envelope the canary looked for is unreachable in production.

The stranded commit's own message agrees: `fix: align wiki canary with OAuth
challenge contract`. Its publish brief spells the framing out — *"production is
healthy; this fixes a broken instrument, not a production outage."*

**Why this correction is load-bearing.** "Stranded P0 fix" implies urgency to
restore service. The truth is that a *monitoring surface* was blind for 6.15
days, which is a different and arguably worse problem — but it is not an outage,
and a lane dispatched to "restore the P0" would be chasing nothing. This is the
`stale-backlog-rows-misdirect` failure mode (2026-07-21: 5 of 5 dispatched rows
had false premises) reproducing inside the brief that cites it.

---

## 3. Inventory

### 3.1 Genuinely stranded and still valuable — 2 lanes

#### `.codex-scratch-uptime-canary-1461/` — the canary contract fix

| | |
|---|---|
| Kind | standalone **shallow clone**, not a registered worktree |
| Branch | `fix/uptime-canary-contract` |
| HEAD | `01e815c7` (2026-07-21), parent `2c1f63cb` = current `origin/main` tip |
| Files | `.github/workflows/uptime-canary.yml`, `STATUS.md`, `scripts/wiki_canary.py`, `tests/test_wiki_canary.py` (+139 / −80) |
| On origin | **no** — `git ls-remote --heads origin fix/uptime-canary-contract` is empty |
| PR | **none** — `gh pr view 1461` resolves to no PullRequest |

Parented directly on the current origin tip, so it still applies cleanly. This
is the highest-value strand in the sweep. **Not fixed here** — it is queued to
the codex lane as `land-stranded-canary-p0-fix.md`; that lane should carry the
§2 correction into the PR body so the fix is not published as an outage remedy.

One caveat for whoever lands it: the commit touches `STATUS.md`, which is
contended by #1506/#1507. That hunk will need dropping or rebasing.

#### `../wf-plan-authority-model/` — the authority-derivation design record

| | |
|---|---|
| Branch | `docs/plan-authority-derivation`, HEAD `dc4031cf` (2026-07-21) |
| Commits | `dc4031cf` "give the authority-derivation entry a tracked source"; `14a2fab1` "record the unified authority-derivation model (DRAFT — needs host sign-off)" |
| Content | `PLAN.md` +14; `docs/design-notes/…-unified-authority-derivation-approved.md` (160 lines); `…-alternative-rejected.md` (301 lines) |
| On origin | **no** — both commits reachable from **0** remote refs |

`origin/main`'s `PLAN.md` contains **zero** occurrences of "authority
derivation". This is the written record of a host architectural decision
(2026-07-20: one unified authority-derivation model chosen over surface-by-surface
patches) whose *implementation* is proceeding on other branches — `73f0bbc4`
(S2 fix-9), `16ab2f67` (M1 authority foundation). The code is landing; the
rationale, and the 301-line record of the rejected alternative, exist on one
local disk. That is the expensive half to reconstruct.

### 3.2 Stranded but superseded — 3 lanes, low value

| Lane | Commit | Why superseded |
|---|---|---|
| `../wf-sandbox-runner-design` | `e2a84957` (2026-07-16) — `docs/design-notes/2026-07-16-per-job-sandbox-runner.md`, 157 lines | Design note absent from origin, but `origin/feat/per-job-sandbox-runner` exists with the implementation (`tinyassets/sandbox_runner.py`, `sandbox/detect.py`, 4 test files). Design-ahead-of-impl; impl won. |
| `.claude/worktrees/agent-a9631530733b04902` | `d98f0184`, `2289871b` (2026-06-30) — `tinyassets/api/permissions.py`, `universe_self_model.py` | Both target files exist on `origin/main` via the merged `claude/founder-identity-allslices` (`b91a6b07`, confirmed ancestor of origin/main). Pre-merge synthesis lane. |
| `.claude/worktrees/agent-af72d4d2d234fea80` | `80ffef19` (2026-07-02) — per-universe engine + vault resolution | Its own test file `tests/test_per_universe_engine_resolution.py` is present on `origin/feat/credential-vault` (PR #1469). |

Worth a skim before any eventual cleanup, but nothing here blocks anything.

### 3.3 Landed elsewhere — the lane is stale, not the work

| Lane | Landed as |
|---|---|
| `codex-tmp/wf-daemon-key-binding` @ `c67ff97f` | `3e7d16f2` on `origin/chore/mutation-probe-coverage` = **PR #1491**. Same fix ("a one-column DML write achieved full daemon impersonation"). |
| `../wf-review-auto-ship-ledger` @ `3ada97b` | `4284f89d` on `origin/main` — same title, same date (2026-05-02). Pre-rename layout (`workflow/api/status.py`); ~11 weeks stale. |
| `.claude/worktrees/permissions-fail-closed` @ `06061c63` | `claude/founder-identity-allslices`, merged as `b91a6b07`; remote branch deleted post-merge, which is why it reads as "no remote". |
| `../wf-audit-{release-chain,vacuous-tests,status-backlog,stale-pr-triage}` | PRs **#1508 / #1509 / #1510 / #1511**, all open drafts. |

Two of these are actively misleading right now:

- **`codex-tmp/wf-daemon-key-binding`.** `STATUS.md` carries a `host-action` row
  — *"Publish #1491 replacement: local `codex-tmp/wf-daemon-key-binding` at
  `c67ff97f`; branch-create was cancelled"* — asking the host to publish work
  that **is already on origin**. Note `c67ff97f` is not a valid object in the
  primary checkout (`git cat-file -t` fails); the commit exists only inside that
  scratch clone, which is what makes the row look unresolved.
- **The four `wf-audit-*` `_PURPOSE.md` files** still read "lane wrote it, opened
  no PR" / "committed locally, could not push". All four were pushed and have
  PRs. The session-start provider-context feed replays these stale lines every
  session, so the same false signal is served to every new agent — including the
  one that wrote the brief for this audit.

### 3.4 Composition-only — no unique content

`../wf-deployable` (`integration/deployable-2026-07-21`, 24 commits) and
`../wf-integration` (`integration/predeploy-2026-07-21`, 267 commits) hold
local-only *merge* commits, but **every non-merge commit is contained in at least
one origin ref**. The integration topology is local; the content is all
published. Nothing to rescue.

### 3.5 Not checkouts / no unique commits

The remaining ~55 `../wf-*` lanes are pushed with open PRs (spot-verified against
the 42-PR open list), or sit at an ancestor of `origin/main` with zero commits
ahead. The nine `codex-tmp/` git checkouts all sit on local `main` `e2a30f21`
(an ancestor of `origin/main`) with 0 commits ahead — stale checkouts, not
strands. The rest of `codex-tmp/` is pytest output, uv caches, and verdict
markdown. Most `.claude/worktrees/` entries are likewise at `main` with 0 ahead;
the four `agent-*` patch-loop lanes (S1–S4) are all pushed with PRs
#1464/#1465/#1467/#1468.

---

## 4. Root cause

### 4.1 Verified — the mechanism in the canary case

This one is not inferred. The scratch clone contains its own dispatch record:

- **`peer-publish-brief.md`** — a correct, complete brief: verify the four-file
  diff, push without force, open a draft PR with specified body, comment on issue
  #1461, *"If authentication or network blocks any step, report the exact blocker
  and stop."*
- **`peer-publish-result.md`** — the entire content is:

  ```
  [peer_agent] ERROR: claude exited 1 after 179s
  stderr: (empty)
  ```

So: the work was finished, the publish step *was* correctly delegated, and the
delegate **died silently** — exit 1, no stderr, after 179 seconds. The failure
was written to a result file that nothing downstream read. No push, no branch, no
PR, and no alarm.

This is a precise recurrence of the already-recorded
`silent-failure-dispatch-and-tests` pattern (dead agent lanes reported as
running, empty-stderr model failure). The `2c1f63cb` commit on `origin/main` —
*"docs(activity): record four s2-gate lanes that produced no PR"* — is the same
pattern logged four more times. PR #1513 independently reports three further
remediation lanes that "were dispatched and produced no branch and no PR."

**The structural gap:** the lane contract ends at *"dispatch the publish step."*
Nothing asserts the postcondition — that a PR now exists. A dispatch that
silently fails is indistinguishable from one that succeeded, because success is
never checked.

### 4.2 Verified — the strand is invisible to the tool that should surface it

`scripts/worktree_status.py` enumerates lanes via `git worktree list`
(114 registered). `.codex-scratch-uptime-canary-1461/` is a **separate shallow
clone**, not a registered worktree — `git worktree list --porcelain | grep -c
codex-scratch` returns **0**. The repo's own lane-visibility tool is structurally
blind to the exact directory holding the most valuable strand.

Separately, `worktree_status.py` contains **no** `ls-remote`, `gh pr`, or
equivalent check (grep for `ls-remote|gh pr|unpushed|stranded` → no matches). Its
`_upstream_state()` reports `none` when a branch has no configured upstream —
which is the *normal* state for a fresh `wt.py new` lane, so it carries no
signal. "Has commits but no PR" is not a state the tool can currently express.

### 4.3 Suspected — not established by this sweep

Stated as open threads, not findings:

- **Push permissions failing silently.** Plausible and consistent with an exit-1
  / empty-stderr death, but the result file preserves no stderr, so it is
  unproven. Other lanes pushed successfully in the same window (PRs #1508–#1513
  were created 2026-07-22), which argues *against* a blanket auth outage and
  toward a per-invocation failure.
- **Agents writing into scratch dirs instead of worktrees.** Observably true
  (`codex-tmp/`, `.codex-scratch-*`), and it is what defeats `worktree_status.py`
  per §4.2 — but whether it *causes* non-publication or merely hides it is not
  established here.
- **`worktree-subagent-write-redirect`.** The known behavior (subagent writes
  land in the session's current worktree, not the prompted cwd) would produce
  exactly this shape. Not tested in this sweep; flagged as the most likely
  explanation for the `codex-tmp/*` checkouts being separate clones rather than
  worktrees.
- **Recurrence is established even if the mechanism is not.** `d4d279a0`
  ("recover 32 documents that existed only in one stale checkout", PR #1490)
  already landed a recovery for this class. The primary checkout right now still
  carries 16 untracked entries including three `docs/audits/2026-07-22-*.md`
  files and four `scripts/*.py`. Prior remediation was instance-level, not
  class-level — the same shape PR #1513 identifies for the canary itself.

---

## 5. Prescription — one guard

**Add `scripts/check_stranded_lanes.py`, and put it in the session-start ritual
next to `worktree_status.py`.**

For every checkout it can find, it reports `STRANDED` and exits non-zero when a
lane has commits that exist nowhere else:

```
STRANDED  ⟺  rev-list --count origin/main..HEAD > 0
             AND ( git ls-remote --heads origin <branch>  is empty
                   OR gh pr list --head <branch> --state all  is empty )
```

Enumeration must be the union of — this is the part that makes it work, per §4.2:

1. `git worktree list --porcelain` (the 114 registered lanes), **and**
2. a glob sweep for sibling/scratch clones: `.codex-scratch-*/`, `codex-tmp/*/`,
   `.claude/worktrees/*/`, `../wf-*/` — any directory with a `.git` that is not
   already in (1).

Exit codes: `0` clean, `2` on any STRANDED lane, listing path, branch, HEAD,
commit count, and which half of the predicate failed (no remote branch vs. no
PR). Requires `git config --global --add safe.directory` for sandbox-owned
scratch dirs, or the check errors rather than reporting — it should treat an
unreadable checkout as `UNKNOWN` and still exit 2, never skip silently.

**Checkable acceptance test:** run it against the tree as of `2c1f63cb`. It must
exit 2 and name at minimum `.codex-scratch-uptime-canary-1461`
(`fix/uptime-canary-contract`, 1 commit, no remote branch) and
`../wf-plan-authority-model` (`docs/plan-authority-derivation`, 2 commits, no
remote branch). If it does not name the scratch clone, enumeration rule (2) is
not working and the guard is theatre.

**What this does and does not do — stated plainly.** It is a *detector*, not a
preventer. It would not have stopped the publish agent from dying; it would have
made the resulting strand fail loudly at the next session start instead of
surviving ~7 hours undetected until a human went looking. Fixing the silent death
itself — having the dispatcher assert its own postcondition and treat an
unread/failed `*-result.md` as a hard error — is the deeper fix, and it belongs
in its own lane rather than being bundled here.

---

## 6. Proposed wording for contended files (NOT applied by this lane)

`STATUS.md` (#1506/#1507) and `AGENTS.md` (#1501) are mid-flight, so this lane
edits neither. Proposed text for whoever lands those:

**→ `STATUS.md` Concerns**, one line:

```
- **[P1 filed:2026-07-22]** Lanes finish work and never publish it — publish agent
  died `exit 1 / stderr empty`, strand undetected ~7h; no tool reports "commits but
  no PR" and `worktree_status.py` cannot see scratch clones. Audit:
  docs/audits/2026-07-22-stranded-unpushed-work.md
```

**→ `STATUS.md` Work table**, replacing the now-false `host-action` row for
`codex-tmp/wf-daemon-key-binding` (§3.3 — the content is on origin as `3e7d16f2`
via PR #1491; the row should simply be **deleted**, and its deletion is the whole
fix).

**→ `AGENTS.md`**, §"GitHub/Worktree Coordination Spine", as an invariant rather
than a new Hard Rule (it is lane procedure, not a global prohibition):

```
- **A lane is not finished until a PR exists.** Commits ahead of origin/main with
  no pushed branch or no PR is a STRANDED lane, not a completed one. Run
  `python scripts/check_stranded_lanes.py` at session start; it exits 2 on any
  strand. When a publish step is delegated, the delegating agent MUST verify the
  PR exists afterward — a dispatch that returns an error file nobody reads is a
  silent failure, not a completion.
```

**→ `_PURPOSE.md` hygiene (no file contention):** the four `wf-audit-*` lanes'
"opened no PR" lines are false as of 2026-07-22 and are replayed into every
session by the provider-context feed. They should be updated to name PRs
#1508–#1511.

---

## 7. Reproduction

```bash
# origin tip this sweep is stamped against
git rev-parse --short origin/main                      # 2c1f63cb

# the headline strand
git config --global --add safe.directory \
  C:/Users/Jonathan/Projects/TinyAssets/.codex-scratch-uptime-canary-1461
git -C .codex-scratch-uptime-canary-1461 log --oneline -2
git -C .codex-scratch-uptime-canary-1461 show --stat HEAD
git ls-remote --heads origin fix/uptime-canary-contract   # empty
gh pr view 1461                                           # no PullRequest
cat .codex-scratch-uptime-canary-1461/peer-publish-result.md

# per-lane sweep: commits ahead, and whether each is on any remote ref
for d in ../wf-* .claude/worktrees/*/ codex-tmp/*/; do
  git -C "$d" rev-parse --git-dir >/dev/null 2>&1 || continue
  echo "$d $(git -C "$d" rev-parse --abbrev-ref HEAD) \
ahead=$(git -C "$d" rev-list --count origin/main..HEAD)"
  git -C "$d" log --no-merges --format='%h %s' origin/main..HEAD | while read -r sha rest; do
    echo "   $sha on_$(git -C "$d" branch -r --contains "$sha" | wc -l)_remote_refs :: $rest"
  done
done

# supersession spot-checks
git -C ../wf-integration branch -r --contains 3e7d16f2    # origin/chore/mutation-probe-coverage
git merge-base --is-ancestor 4284f89d origin/main && echo landed
git merge-base --is-ancestor b91a6b07 origin/main && echo landed
git show origin/main:PLAN.md | grep -ci "authority.derivation"   # 0
git ls-tree -r --name-only origin/feat/credential-vault \
  | grep test_per_universe_engine_resolution                     # present

# §4.2: the tool is blind to the scratch clone
git worktree list --porcelain | grep -c codex-scratch            # 0
grep -nE "ls-remote|gh pr|unpushed|stranded" scripts/worktree_status.py  # no matches
```

---

## 8. Cross-family review

Dispatched to Codex (read-only) with all eight claims above, including an
explicit instruction to push back on the §5 prescription. Verdict recorded in
§8.1 on return; until then every claim here rests on first-party evidence
reproduced by this lane via the §7 commands.

### 8.1 Verdict

_Pending — to be filled in on return._
