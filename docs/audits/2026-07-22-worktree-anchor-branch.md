# Worktree anchor-branch audit — the "49 worktrees held by one unpushed branch" finding is FALSIFIED

**Date:** 2026-07-22
**Repo state at audit:** `origin/main` = `2b9639a3`; primary checkout `C:/Users/Jonathan/Projects/TinyAssets` on `main` @ `0bc841aa` (5 behind).
**Method:** read-only enumeration + reachability. **Nothing was pruned, removed, or deleted.**
**Cross-family review:** Codex (`codex exec`, read-only), independently reproduced every count. Verdict recorded in §9.

---

## 1. Headline — retraction

The originating report claimed:

> 49 registered worktrees under `C:/Users/Jonathan/.claude/jobs/aaaa5b09/tmp/wt-*` are on detached
> HEADs; every detached sha is reachable from **exactly one** ref,
> `refs/heads/chore/distexec-ci-authority-probes`; that branch exists on no remote; therefore 49
> worktrees' worth of review history is a single point of failure with **no copy anywhere else**.

**That is false.** The load-bearing clause — "no copy anywhere else" — does not survive contact with
the remote:

```
$ git fetch --prune origin
$ git rev-list --count chore/distexec-ci-authority-probes --not --remotes=origin
0
```

Zero commits on the anchor branch are unpublished. Every one of them is already reachable from a
branch that exists on `origin`. Server-side confirmation, independent of any local ref:

```
$ gh api repos/Jonnyton/TinyAssets/commits/41c0e67c9be36ebb99266a8423fe265fb0903465 --jq .sha
41c0e67c9be36ebb99266a8423fe265fb0903465
```

GitHub serves the anchor tip. It also serves the sampled detached job shas
(`69f6158f`, `dec60340`, `feb0fd45` — all returned their own sha).

**There is no single point of failure.** The recommended remediation (push the anchor branch as a
backup ref) was **not performed**, because its premise dissolved — see §7.

### What the original report got right

The one verifiable sub-claim holds: the branch *name* has no remote counterpart.

```
$ git ls-remote origin 'refs/heads/chore/distexec-ci-authority-probes'
(empty)
```

The error was inferring **data loss risk** from **name absence**. Those are different properties.
The commits are published under *other* branch names.

---

## 2. The 49 worktrees — enumeration and reachability

`git worktree list` reports **166** registered worktrees total, **49** of them under
`C:/Users/Jonathan/.claude/jobs/aaaa5b09/tmp/`. Directory-existence check on all 49:
**49 PRESENT, 0 MISSING.**

Split (the report said 46 detached; the true number is 47):

| Kind | Count |
|---|---|
| Detached HEAD | 47 |
| On a branch (`feat/auto-birth-home-universe`, `docs/patch-loop-reference-design`) | 2 |

The 49 worktrees share only **43 distinct HEAD shas** — six are duplicate checkouts of the same
commit (e.g. `wt-s1-base-r27` and `wt-s1-review-r26` are both `14920488`;
`wt-bundle-sweep-2` and `wt-core-r13-fable` are both `6c64375f`).

### Coverage by published ref

| Covering ref | Live tip (`ls-remote`) | Worktrees covered |
|---|---|---|
| `origin/chore/mutation-probe-coverage` | `cee48beb` ✓ matches local tracking | **47** |
| `origin/docs/patch-loop-reference-design` | `7f01d2c9` ✓ matches local tracking | **1** (`wt-patch-loop-design`) |
| *(none — genuinely local-only)* | — | **1** (`wt-auto-birth`) |

**Retention depth.** Coverage is not one thin thread. Codex measured, per detached tip, how many
post-fetch refs contain it:

```
DETACHED_ROWS=47
REMOTE_CONTAINERS_MIN=8      REMOTE_CONTAINERS_MAX=14
LOCAL_BRANCH_CONTAINERS_MIN=11
```

The *least*-covered detached tip is contained by **8 different `origin/*` refs**; the best-covered by
14. Deleting any one covering branch — including `feat/blob-locks-v2` — would not expose a single
history. That is the quantitative reason the "single point of failure" framing fails.

The anchor branch tip `41c0e67c` is itself an ancestor of `origin/feat/blob-locks-v2` @ `f6bee436`
(local tracking ref verified equal to `ls-remote`, so not a stale-tracking artifact):

```
$ git merge-base --is-ancestor 41c0e67c refs/remotes/origin/feat/blob-locks-v2 ; echo $?
0
```

### The one genuinely unpublished lane

`wt-auto-birth` @ `41f7a412` on `feat/auto-birth-home-universe` — **5 unpublished commits**,
14 files / +989 / −246 vs `origin/main`. This is real, unpublished, single-copy work:

```
41f7a412 fix(auto-birth): Codex round-4 — repair a surviving incomplete bound home
5fd69f75 fix(auto-birth): Codex round-3 — atomic create + completeness-verified home
332d013e fix(auto-birth): Codex round-2 — materialization lock + honest read contract
f3d792d4 fix(auto-birth): Codex ADAPT — serialize schema init + refresh onboarding prompts
8e1ac2b2 feat(onboarding): auto-birth the founder's home universe on first connect
```

It is **not** among the lanes the original report flagged.

### Reproduction method

```bash
export MSYS_NO_PATHCONV=1          # REQUIRED on Git Bash
git fetch --prune origin
git worktree list --porcelain \
  | awk '/^worktree /{p=substr($0,10)} /^HEAD /{h=$2} \
         /^detached/{print p"\t"h"\tDETACHED"} /^branch /{print p"\t"h"\t"$2}'
# then per entry:
#   [ -d "$p" ]                                     # directory existence
#   git rev-list --count "$h" --not --remotes=origin  # THE publication metric
```

> **Path-form trap.** Use the exact path form `git worktree list` prints (`C:/Users/...`). Rewriting
> them as `/c/Users/...` makes every `git -C` fail with *"No such file or directory"*, which reads
> exactly like "the worktree is orphaned" when it is not.

> **`awk` field trap.** Porcelain emits `branch refs/heads/foo`, so the branch name is `$2`, not
> `$3`. Using `$3` silently yields empty branch names and inflates the detached count.

---

## 3. Nothing is currently lost — and why the proof is sound

Two independent lines of evidence:

1. **Local reachability.** `git rev-list --count <ref> --not --remotes=origin` = 0 for the anchor
   branch, and for 152 of the 166 registered worktrees.
2. **Server-side existence.** `gh api .../commits/<sha>` returns the sha for the anchor tip and for
   sampled detached job shas. This bypasses local refs entirely.

Three attacks on the proof were tested and all fail to overturn it:

- **The repository is shallow** (`git rev-parse --is-shallow-repository` → `true`, one boundary at
  `d16421b2`, 2026-05-10). Shallowness truncates *old* history, so it can only cause ancestry checks
  to return **false negatives**, never false positives. Every positive `--is-ancestor` result here
  therefore stands, and all the commits in question post-date the boundary by two months.
- **Stale remote-tracking refs.** Ruled out: every covering ref's local tracking sha was compared to
  live `git ls-remote` output and **matched**.
- **Grafts / replace refs.** `git replace -l` → empty; `.git/info/grafts` does not exist.

One further point, from Codex: a checked-out worktree HEAD is its **own GC root** via the
`worktrees/<id>/HEAD` pseudo-ref (verified: `git rev-parse worktrees/wt-bundle-sweep/HEAD` resolves,
and `git reflog exists` returns 0 for it). So even absent every branch ref, `git gc` would not
collect these commits while their worktrees remain registered. That is a *third*, independent layer
of protection the original report did not account for — **but it is the weakest of the three**: it
lasts only while the worktree stays registered, and any residual reflog protection expires. It is a
reason not to panic, not a reason to keep 49 worktrees forever.

---

## 4. `/tmp/pr1435` — orphaned registration, no loss

```
worktree /tmp/pr1435
HEAD c9b2f62d915d86b52ec3949d397698a612427d49
branch refs/heads/pr1435
locked initializing
```

The directory is **gone**; the registration survives because it is `locked`. Its sha is reachable
from `origin/claude/workos-slice1-tinyassets`, and
`git rev-list --count refs/heads/pr1435 --not --remotes=origin` = **0**.

**No data loss. Not pruned** — per Hard Rule 13 this audit records only.
Note that `git worktree prune --dry-run --verbose` produces **no output** at all: the lock means
even a deliberate prune would skip it. Clearing it would require explicitly unlocking first, which
is a host decision (§8).

### A second path-shaped registration

`C:/c/Users/Jonathan/Projects/wf-lintbase-tmp` (note the doubled `c`) is registered and its
directory **does exist** — a real directory literally named `c` at the drive root, created by a
path-conversion bug in some earlier session. Its sha `519fb2ea` is fully published (0 unpublished).
Harmless, but it is filesystem litter from a `MSYS_NO_PATHCONV` mishap and worth knowing about.

---

## 5. The `wf-*` lanes — classified

103 registered worktrees live under `C:/Users/Jonathan/Projects/wf-*`. Of these, **20** sit on
branches absent from `origin` (the report said 22; the count drifts as branches are pushed and
`--prune` runs). But branch-name absence is *not* the risk metric. By unpublished-commit count:

| Class | Count |
|---|---|
| Fully published (0 unpublished commits) | 93 |
| Has genuinely unpublished commits | 10 |

### 5a. Lanes with real unpublished content — worth a future publish decision

| Lane | Sha | Branch | On origin? | Unpublished |
|---|---|---|---|---|
| `wf-ci-test-gate` | `da6acf04` | `claude/required-test-gate` | yes | **52** |
| `wf-integration` | `7c6058fe` | `integration/predeploy-2026-07-21` | no | **10** |
| `wf-deployable` | `edfa377d` | `integration/deployable-2026-07-21` | no | **8** |
| `wf-credential-vault-design` | `61314295` | `codex/credential-vault-design` | no | 2 |
| `wf-status-janitor-0722` | `c8c0e09e` | `claude/status-janitor-0722` | yes | 2 |
| `wf-status-release-cron-watch` | `8622c5ee` | `claude/status-release-cron-watch` | yes | 2 |
| `wf-relay-spec-alignment` | `1dd94427` | `codex/relay-spec-alignment` | no | 1 |
| `wf-release-chain-log` | `0f54523f` | `claude/release-chain-log` | yes | 1 |
| `wf-sandbox-runner-design` | `e2a84957` | `codex/sandbox-runner-design` | no | 1 |
| `wf-tinyassets-rename-migration` | `740d3a74` | `codex/tinyassets-hard-rename-sweep` | no | 1 |

Note that four of these are on branches that **do** exist on origin — the branch was pushed, then
local commits were added on top. Branch-presence checks miss these entirely.

### 5b. Branch absent from origin but nothing at risk (0 unpublished)

`wf-activity-null-results`, `wf-anon-identity`, `wf-backlog-fix`, `wf-blob-locks`, `wf-ci-probes`,
`wf-ios-app-scaffold`, `wf-patch-loop-leasestore-kimi`, `wf-r2-provider-receipt`, `wf-s3-devkey`,
`wf-suite-baseline`, `wf-test-identity`, `wf-visibility`, `wf-worktree-sweep-0722`,
`wf-worktree-sweep-0722b`.

### 5c. Three of the four lanes the report named as "real unpublished deltas" are artifacts

| Lane | Report's claim | Actual unpublished | Verdict |
|---|---|---|---|
| `integration/deployable-2026-07-21` @ `edfa377d` | 199 files, +43,263 | **8 commits** | ✅ real |
| `feat/blob-lock-redesign` @ `8d9a7791` | named as real delta | **0** (218 "ahead", 382 files) | ❌ artifact |
| `feat/s3-device-key-signed-enrollment` @ `4e0a22e2` | named as real delta | **0** (223 "ahead", 400 files) | ❌ artifact |
| `feat/patch-loop-leasestore-kimi` @ `35f56034` | named as real delta | **0** (203 "ahead", 378 files) | ❌ artifact |

---

## 6. The metric trap — and a correction to the report's own remedy

The report correctly warned (its item 6) that a stale `origin/main` inflates
`git rev-list --count origin/main..HEAD` into meaningless numbers like 236 or 267. That warning is
right, and this audit confirms it: `wf-ci-probes` reports **236 ahead / 404 files changed** while
having **0 unpublished commits**.

But the report's prescribed replacement — *"always measure `git diff --stat <real-origin-main-sha>...HEAD`"*
— **is also the wrong metric**, and it is what produced three of its four false positives.

- `git diff --stat <main>...HEAD` measures **divergence from main**. A branch can differ from `main`
  by 400 files and still be 100% published.
- The question "is this work at risk of being lost?" is answered only by
  **`git rev-list --count <sha> --not --remotes=origin`**.

Three metrics, three different questions:

| Command | Answers | Fooled by |
|---|---|---|
| `rev-list --count origin/main..HEAD` | how far ahead of *my cached* main | stale tracking refs |
| `diff --stat <main>...HEAD` | how different the content is from main | long-lived branches, merges |
| **`rev-list --count HEAD --not --remotes=origin`** | **what is unpublished** | *(nothing here; shallow clones only cause under-reporting of ancestry)* |

Only the third one bears on data loss. Same illusion family as the squash-merge reachability trap
already recorded in memory — a count that *looks* like work but measures topology instead.

---

## 7. Why the backup push was not performed

The authorized action was `git push origin chore/distexec-ci-authority-probes`, justified as
"removes the single-point-of-failure and costs nothing." **Both halves are false**, so it was not
exercised.

**Half one — there is no single point of failure to remove.** Every tip has 8–14 remote retention
refs (§2).

**Half two — it does not cost nothing.** Two distinct costs:

1. *Git objects: zero.* Codex confirmed
   `ANCHOR_OBJECT_LINES_NOT_IN_BLOB_LOCKS=0` and a `--dry-run` push reporting `[new branch]`.
   Codex also sharpened the wording: **"zero new Git objects" is correct; "zero bytes transferred"
   is not** — protocol traffic and one new remote ref still happen.
2. *CI: a full Docker build-and-smoke run.* This is the cost neither the report nor I anticipated.
   `.github/workflows/docker-build.yml` is the **only** workflow in the repo whose `push:` trigger
   has **no `branches:` filter** — it fires on a push to *any* branch, gated only on paths
   (`Dockerfile`, `pyproject.toml`, `tinyassets/**`, `domains/**`, `deploy/**`, `.dockerignore`).
   The anchor branch touches **117** files matching those filters, so the push fires a
   15-minute-timeout job that builds the image and runs a container smoke test.

   The report reasoned *"a branch with no PR is not enrolled in any auto-merge automation, so this is
   safe."* That is true **for auto-merge** and does not generalize: `pull_request`-triggered
   automation is indeed skipped, but an unfiltered `push:` trigger does not care whether a PR exists.
   Verified non-destructive — `docker-build.yml` has no registry login, no `push: true`, and no
   deploy step, so nothing outward-facing happens — but "costs nothing" is wrong.

**Codex's verdict was `adapt`, not `approve`,** and it argued the push is still worthwhile *as an
explicit retention marker*: the covering branch names (`feat/blob-locks-v2`,
`chore/mutation-probe-coverage`) are semantically unrelated to "preserve the review-round history,"
which makes accidental deletion by a future janitor more plausible than the ref count alone suggests.
Its own framing, though, is the deciding one: **"preventive hygiene, not emergency object rescue."**

Preventive hygiene with a real CI cost, on data protected 8–14 ways, whose authorization rested on a
premise the evidence removed, is a **host decision** (§8) — not something an agent should do on a
falsified rationale. The command is above and is safe to run if the host wants the named anchor.

---

## 8. Host decision

These worktrees and their branches are **not sweepable by any current tool**, and their fate is the
host's call:

- **49 job worktrees under `.claude/jobs/aaaa5b09/`** — artifacts of the S1–S5 / vault / seam
  Fable-family review rounds. All published except `wt-auto-birth`. They are safe to leave
  indefinitely; they cost disk and they inflate `git worktree list` for every session that runs the
  cold-start ritual.
- **`wt-auto-birth` (5 unpublished commits)** — the only job lane holding single-copy work. If the
  auto-birth work matters, it wants a push or a PR; if it was superseded, it wants an explicit
  abandon record. Currently it is neither.
- **The 10 `wf-*` lanes in §5a** — same question, ten times. `wf-ci-test-gate` (52 unpublished) is
  the largest single block of unpublished work in the checkout.
- **`/tmp/pr1435`** — a locked registration whose directory is gone. Unlocking + pruning is the only
  way to clear it, and both are outside this audit's mandate.
- **`C:/c/Users/...` litter** — a stray directory from a path-conversion bug.
- **Push the anchor branch as a named retention marker?** Costs one Docker build-smoke CI run (§7)
  and buys insurance against a future janitor deleting all 8–14 covering refs. Codex says worthwhile
  as hygiene; the audit declines to decide it. One command:
  `git push origin chore/distexec-ci-authority-probes`.

No agent should act on any of these without an explicit host instruction: Hard Rule 13 forbids the
destructive half, and the non-destructive half (pushing 10+ branches) is an outward-facing
publication decision.

---

## 9. Detector coverage — do #1566 / #1567 already handle this?

Both are open **draft** PRs titled "(stranded lane, DO NOT MERGE)".

**PR #1566 — `scripts/check_stranded_lanes.py` (branch `feat/check-stranded-lanes`).**
**Yes, it already covers this class**, and this audit should not duplicate it. It parses
`git worktree list --porcelain`, unions in `.claude/worktrees` and scratch-clone locations, and
tests remote presence with `git ls-remote --heads origin refs/heads/<branch>`.

Two findings to feed back to that lane rather than re-implement:

1. **It gates on the inflated ahead-count.** `_inspect_lane` computes
   `git rev-list --count {base_ref}..HEAD` and returns `None` (clean) only when `ahead <= 0`. On a
   lane with a stale `origin/main` this is the exact number shown to be meaningless in §6 — so
   `wf-ci-probes` would be reported STRANDED on the strength of 236 phantom commits while holding
   nothing unpublished. Adding `git rev-list --count HEAD --not --remotes=origin` as the
   at-risk test would separate the 10 real lanes from the 93 noise ones.
2. **Detached HEAD is classified STRANDED unconditionally.** All 47 detached job worktrees would be
   flagged, though every one is published. Same fix applies.

**PR #1567 — `scripts/branch_janitor.py` (branch `fix/branch-liveness-report`).** Touches
`scripts/branch_janitor.py`, `tests/test_branch_liveness.py`,
`docs/specs/2026-07-22-branch-liveness-report.md`. It is squash-merge-aware for *branches*; grep for
`worktree` / `ls-remote` / `--not --remotes` in its version of the script returns nothing, so it does
**not** cover registered-worktree-with-no-origin-branch. That gap is #1566's, and #1566 fills it.

---

## 10. Cross-family review (Codex, read-only)

**Verdict: `adapt`.** Codex independently re-derived the enumeration with its own PowerShell
implementation and reproduced every count exactly: `MUTATION_COVERED=47`, `PATCH_COVERED=1`,
`NEITHER=1`, `UNIQUE_HEADS=43`, `DETACHED_ROWS=47`. It confirmed the falsification —
*"one missing remote branch name is plainly not the realized single point of failure alleged by the
report"* — and contributed four things this audit did not originally have:

- surfaced that the repo is **shallow** (`SHALLOW=true`, 1 boundary) — a genuine attack on the
  reachability argument, resolved in §3;
- confirmed `GRAFTS_ABSENT`, `REPLACE_REFS=0`;
- established the **worktree-HEAD-as-GC-root** layer and its expiry caveat (§3);
- measured **retention depth** at 8–14 remote refs per tip (§2), and corrected "zero objects" to
  "zero *new Git objects*, not zero bytes" (§7).

Its qualifications, all adopted above:

- all covering refs live in **one GitHub repository** — multiple retention refs, not multiple
  independent storage providers;
- a sufficiently broad janitor sweep could delete every covering ref at once;
- the covering branch names are **semantically unrelated** to the retention purpose, so accidental
  deletion is more plausible than the raw count implies;
- `wt-auto-birth` remains genuinely local-only.

Codex's recommended restatement, which this audit adopts: **48 of 49 worktree tips are published; all
47 detached tips have multiple verified remote retention refs; one branch-attached auto-birth history
of five commits is local-only.**

Dispatch note: sent via `codex exec -` reading the ask on **stdin**. The documented Windows footgun
(`cmd.exe` truncates `--prompt` at the first newline, so only the preamble reaches Codex) makes the
`--prompt` path unusable for a multi-paragraph ask; stdin worked first try.

---

## Provenance

- Enumeration, reachability, and classification: read-only `git` + `gh api`, 2026-07-22,
  `origin/main` = `2b9639a3`.
- **No worktree was pruned or removed. No branch was deleted. No ref was force-updated. Nothing was
  pushed.**
