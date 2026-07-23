# s2-gate lane conversion: nothing vanished, 36 lanes finished and could not publish

**Filed:** 2026-07-22 · **Analyst:** claude-code (`claude/audit-lane-conversion`) · **Kind:** audit, no behavior change

**Freshness stamp.** Cohort snapshot taken 2026-07-22T05:03Z (2026-07-21T22:03 local, UTC−7);
liveness re-checked 2026-07-22T05:12Z. Environment: Windows 11, primary checkout
`C:/Users/Jonathan/Projects/TinyAssets`, analysis run from a clean worktree off `origin/main` at
`a69dd70a`. The fleet was **still running throughout this audit** — counts move. Every number below
is stamped to the snapshot, not to "now". Commands are listed in §8.

---

## 1. Answer first

Of **93 briefs** dispatched from `output/s2-gate/_queue/dispatched/` between 2026-07-21T18:00 and
22:03 local:

| Outcome | Lanes |
|---|---:|
| Work reached GitHub (own PR, or push to an existing PR, or rescued by another lane) | **35** |
| **Work finished, committed locally, publication blocked — stranded on disk** | **36** |
| Correctly ended with no PR (by design / premise refuted / already done / host-blocked) | **15** |
| Branch pushed, PR deliberately withheld pending a cross-family verdict | **1** |
| Still in flight at snapshot | **6** |
| **Total** | **93** |

**Zero lanes vanished.** No lane in this cohort died leaving no trace. Every brief is accounted for
by a final report, a running process, or a local commit.

The gap is not evaporation — it is **a publication failure with a single, exact predictor**:

> **All 36 stranded lanes were dispatched to `codex`. Zero `claude` lanes stranded.**
> 36/36 vs 0/41. The provider *is* the predictor.

The fleet is not losing a third of its runs. It is completing them and then failing to publish
every Codex one.

---

## 2. Correcting the brief's own premise

The brief that commissioned this audit measured `84 dispatched briefs` against `53 PRs` and
inferred a ~31-lane gap. That subtraction is apples-to-oranges and **understates** the problem:

- Briefs and PRs are not 1:1. Some lanes correctly produce no PR (review verdicts, queue
  restocking, lanes that act on an *existing* PR). Two lanes shared one PR (`#1513`, `#1516`).
- Several PRs in the window did not come from the fleet at all — the `feat/`, `fix/` and `ci/`
  branches numbered #1481–#1500 are patch-loop program work from other sessions.

Measured per-lane instead of by subtraction, **58 of 93 lanes produced no PR of their own** — not
31. Of those 58, **15 ended correctly** and **36 are recoverable work sitting on local disk**.

This is the outcome the brief explicitly allowed for: refuting the premise is a successful result.
The premise was directionally right (there *is* a large gap) and quantitatively wrong (it is
bigger, and its composition is the opposite of "lanes died").

---

## 3. The predictor, and why it is causal rather than correlational

| Class | codex | claude | total |
|---|---:|---:|---:|
| stranded-on-disk | **36** | **0** | 36 |
| produced a PR of its own | 0 | 31 | 31 |
| stranded then rescued by another lane | 3 | 0 | 3 |
| pushed to an existing PR | 1 | 0 | 1 |
| correct no-PR outcome | 7 | 8 | 15 |
| branch pushed, PR held | 0 | 1 | 1 |
| in flight at snapshot | 5 | 1 | 6 |
| **total dispatched** | **52** | **41** | **93** |

Three independent lines of evidence, not just the correlation:

**(a) The lanes say so, in their own words.** 36 final reports converge on one sentence. Verbatim:

- `get-status-reports-ok-from-file-presence`: *"Implementation is complete and committed locally;
  only draft PR publication is blocked… outbound GitHub access is blocked and the connector write
  was cancelled."*
- `universe-visibility-impl`: *"Publication is the only blocker: sandbox egress rejected `git push`,
  and the GitHub connector branch write was cancelled."*
- `test-identity-and-reset-impl`: *"Publication is blocked: direct GitHub egress is sandbox-denied,
  and the GitHub connector's branch-creation write was cancelled."*
- `worktree-sweep`: *"Direct push could not reach GitHub, and the GitHub app cancelled its write
  before creating a branch."*

**(b) The sandbox is named on disk.** Codex lane worktrees are owned by a separate Windows account:

```
$ git -C .codex-worktrees/wf-branch-liveness-0722 log --oneline -3
fatal: detected dubious ownership in repository at '…/wf-branch-liveness-0722'
  is owned by: DESKTOP-KCPMGP3/CodexSandboxOffline (S-1-5-21-…-1003)
  but the current user is: DESKTOP-KCPMGP3/Jonathan (S-1-5-21-…-1001)
```

The account is literally called **`CodexSandboxOffline`**.

**(c) The dispatcher asks for it.** `scripts/peer_agent.py:113` `build_codex_cmd()` appends
`--full-auto` for write lanes — codex's `workspace-write` sandbox, which denies network access by
default. `build_claude_cmd()` (`scripts/peer_agent.py:105`) passes
`--dangerously-skip-permissions` and no sandbox, so Claude lanes reach GitHub normally. That
asymmetry is exactly the observed 36/0 split.

**A caveat this audit does not resolve.** Two blockers are reported together — no shell egress *and*
a cancelled GitHub-connector confirmation. Either alone would be sufficient to strand a lane, so
this evidence does not isolate which to fix. `approval_policy=never`
(`scripts/peer_agent.py:120`) means a connector write that needs confirmation cannot get one, so
the approval path is at least equally implicated. **Fixing only the sandbox network flag may not be
enough.** Whoever fixes this should verify against both.

### Cutover

Codex lanes could publish earlier in the window and then stopped. The last successful Codex push was
`origin/feat/blob-locks-v2` at **2026-07-21T18:39 local** — PR #1487, from lane
`pr1487-committed-red` (confirmed: three commits on #1487 dated 2026-07-22T01:37–01:39Z). Every
Codex lane dispatched after that stranded. This audit did not determine what changed at ~18:40;
that is the highest-value follow-up question and is *not* answered here.

---

## 4. The 36 stranded lanes — recovery table

Each finished, self-verified, and committed locally. Branch/commit/checkout as reported by the lane
itself. **These are not lost; they need a push from a network-enabled shell.** Several report
independent review already passed, and several are security-relevant.

| Lane | Branch | Commit | Checkout |
|---|---|---|---|
| `announce-patch-broken-script-paths` | `fix/announce-paths` | `3a73579f` | `codex-tmp/wf-fix-announce-paths` |
| `announce-patch-move-scripts-to-social` | `claude/announce-social-path` | `c7a5add1` | `codex-tmp/wf-announce-social-path` |
| `announce-patch-workflow-path-fix` | `claude/fix-announce-patch-path` | `cef85575` | `.tmp-fix-announce-wt` |
| `attic-tests-never-collected` | `agent/revive-attic-tests` | `bb940d78` | `codex-tmp/wf-revive-attic-tests` |
| `attribution-payout-stale-float-tests` | — | `b572056d` | `codex-tmp/wf-attribution-payout-test-semantics-min` |
| `auth-surface-sweep` | (audit text only, 17.8 KB, no file written) | — | — |
| `auto-merge-automation-skips-build-and-stalls` | `fix/auto-enroll-release-reconcile` | `5e99cd0b` | `.codex-worktrees/wf-auto-enroll-release-reconcile` |
| `bseries-container-venv-regression` | `feat/patch-loop-integration` | `511f6b0d` | `.codex-worktrees/bseries-venv-fix` |
| `canary-swallows-its-own-diagnostic` | `fix/canary-error-reporting` | `cae6d99b` | `.claude/worktrees/codex-canary-error-reporting` |
| `check-stranded-lanes-guard` | `feat/check-stranded-lanes` | `4b05b3f7` | `.codex-worktrees/wf-check-stranded-lanes` |
| `codex-review-hangs-on-stdin-in-background` | `fix/codex-review-stdin` | `b2bde4bd` | `codex-tmp/wf-codex-review-stdin-2` |
| `command-center-lan-failopen-p0` ⚠ | `claude/fix-command-center-failopen` | `b587f8e8` | `codex-tmp/wf-fix-command-center-failopen` |
| `fix-required-tests-xdist` | (→ `ci/required-test-gate`) | `f66d9353` | `codex-tmp/pr1502-codex` |
| `fix-wiki-canary-standing-red` | `fix/uptime-canary-contract` | `01e815c7` | `.codex-scratch-uptime-canary-1461` |
| `get-status-reports-ok-from-file-presence` | `agent/auth-health-evidence` | `28f30bbf` | `.codex-worktrees/auth-health-evidence-4-1` |
| `land-stranded-canary-fix-STILL-unlanded` | `claude/canary-401-challenge` | `1e0996df` | `.tmp/` |
| `land-stranded-canary-p0-fix` | `fix/canary-p0-fix` | `f985ee7a` | `.tmp/wf-canary-p0-fix` |
| `layer2-probe-red-not-skip` | `fix/layer2-probe-skip-detection` | `16cb6a7b` | — |
| `m2-m3-authority` ⚠ | `fix/unified-authority-derivation` | `382b239f` | `.codex-worktrees/wf-unified-authority` |
| `p0-outage-triage-never-fires` | — | — | `codex-tmp/p0-triage-dispatch-proof2-20260722` |
| `pr1492-stranded-on-dead-base-branch` | (rebase of #1492) | `13262230` | — |
| `release-reconcile-compare-receipt-not-headsha` | (verification only) | — | — |
| `required-test-gate` | `agent/required-test-aggregator` | `0bac219d` | `.claude/worktrees/codex-required-test-aggregator` |
| `required-test-gate-failure-triage` | `docs/required-test-triage` | `b119ff37` | `.claude/worktrees/required-test-final` |
| `resurrected-dead-site-code-playground` | `chore/attic-resurrected-playground` | `e6e0f992` | `codex-tmp/wf-resurrected-playground` |
| `s2-stack-unblock` | (audit written into the **dirty primary checkout**, untracked) | — | `docs/audits/2026-07-22-s2-stack-landing-order.md` |
| `test-fixture-branches-leaked-into-catalog` | — | `35a6f498` | `codex-tmp/wf-branch-yaml-leak` |
| `test-identity-and-reset-impl` ⚠ | `feature/test-identity-and-reset-impl` | `375b0155` | `.codex-worktrees/test-identity-reset-fresh` |
| `tray-test-headless-collection-error` | — | `9117e96f` | `codex-tmp/wf-tray-headless-guard` |
| `universe-visibility-impl` ⚠ | `feat/universe-visibility-v2` | `a89b3fae` | `.tmp-wf-universe-visibility` |
| `uptime-canary-false-red-fix` | — | — | `codex-tmp/wf-uptime-canary-false-red` |
| `uptime-canary-false-red-p0` | `fix/wiki-canary-401-contract` | `9337d850` | `.codex-worktrees/wf-fix` |
| `vacuous-test-mutation-verification` | `claude/verify-vacuous-tests` | `26f67feb` | `.codex-worktrees/wf-verify-vacuous-tests` |
| `vacuous-tests-execute-the-mutations` | — | `0f687841` | `codex-tmp/wf-vacuous-mutate-probe-clone` |
| `workflow-script-path-guard` | `codex/guard-workflow-script-paths` | `45d6b808` | `codex-tmp/wf-guard-workflow-script-paths` |
| `worktree-sweep` | `codex/worktree-reconciliation-20260721` | `1ca97fe7` | `.codex-worktrees/worktree-sweep-20260721` |

⚠ = the lane's own report describes a security or authority fix. `command-center-lan-failopen-p0`
is the P0 in the top STATUS Concern row (#1489 unauth LAN). Its fix is written, verified
(*"53 passed… all required probes observed RED on `origin/main`, then GREEN"*), independently
reviewed — and unpublished.

**Recovery is harder than a push.** Those `.codex-worktrees/` paths are owned by
`CodexSandboxOffline` (§3b). `git -C` into them fails with `dubious ownership` for the normal user,
so recovery needs `git config --global --add safe.directory <path>` (or `takeown`) per lane before
the branch is even readable. This is the same ACL class already documented in
AGENTS.md § *Sandbox test-temp hygiene*, but applied to whole worktrees holding finished work
rather than to pytest temp dirs.

---

## 5. The 15 lanes that correctly ended with no PR

Counted so the actionable number is not inflated. These are healthy.

**No PR by design (7)** — the lane's product is a verdict, a queue action, or a change to an
existing PR: `credential-vault-r12` (returned `ADAPT`), `restock-the-backlog` (queued 9 briefs),
`rebase-conflicting-doc-prs-1501-1507`, `post-stale-pr-verdicts-1435-1432-1397`,
`post-stale-pr-verdicts-1435-1432-1397-1506`, `pr1489-land`,
`pr1516-carries-a-verdict-already-superseded` (left review comments on #1516).

**Premise correctly refuted (4)** — the brief was wrong and the lane said so and stopped:
`salvage-chrome-bin-fix-without-reverting-1483` (*"Stopped: the premise no longer holds"*),
`pr1491-recheck` (*"The defect did not ship on current `origin/main`"*), `reconcile-cron-reliability`
(*"no workflow change was warranted"*), `land-stranded-audits-deliver-1506-verdicts`
(*"I did not open the requested PR — its premise was stale"*).

**Already done elsewhere (3)** — `publish-stranded-plan-authority-model` (→ #1518),
`pr1506-deliver-codex-adapt-verdict` (→ #1516), `pr1490-recovery-scope-overrun` (→ #1519).

**Host-blocked (1)** — `canary-contract-drift-guard` correctly refused to build on an unlanded P0
dependency.

---

## 6. Two lanes already worked around this — one of them proves the loss is recoverable

`harvest-fleet-outputs` (a Claude lane) read the stranded Codex reports and carried three of them
into PRs **#1508**, **#1509**, **#1511**, byte-verifying each body against its source. Its own
summary names the mechanism:

> *"`stale-pr-triage` had already committed its audit locally at `d4286864` — then hit no `gh`
> login and no GitHub egress. Its closing paragraph asks a pickup to push it."*

That lane also flagged the same class this audit measures: *"Three lanes are finished code builds
sitting uncommitted… none pushed to origin. **This is probably the bigger finding.**"* It was right,
and the rate is 36.

A Claude lane rescuing Codex output is a working mitigation but a lossy one — it carries *documents*
well and cannot carry *code* without a build/test gate. 33 of the 36 stranded lanes are still
waiting.

---

## 7. Secondary finding: the fleet's liveness monitor reports an empty fleet

Not the brief's question, but it is why this class stayed invisible and it is a live defect.

At snapshot, `scripts/fleet_status.py` printed `FLEET: 0 live lane(s) — none` while **12
`peer_agent.py` lanes were running**. Root cause is one swallowed exception:

`_powershell_processes()` (`scripts/fleet_status.py:45`) shells out to `Get-CimInstance |
ConvertTo-Json`, then `json.loads` the result. One process's `CommandLine` contains a raw control
character, which PowerShell 5.1 emits unescaped. Python's strict parser rejects it:

```
json.JSONDecodeError: Invalid control character at: line 1 column 2451 (char 2450)
```

`_powershell_processes` catches `JSONDecodeError` and returns `[]` (`scripts/fleet_status.py:61-62`),
so the failure renders as a confident **"0 live lanes"** rather than an error. Reproduced three
times consecutively; the underlying PowerShell call succeeds in 0.4 s and returns 12,801 bytes, so
this is a parse bug, not a timeout.

Consequence for this audit: **the absence of an out file means "still running", not "died"**. All
four lanes that first looked like `no-trace` were live processes. Any future measurement that
treats a missing `output/s2-gate/<stem>.md` as a dead lane will over-report loss — and any operator
consulting `fleet_status.py` is told the fleet is idle while it is saturated.

This is a fresh instance of the saved `silent-failure-dispatch-and-tests` class: a guard that fails
closed to a reassuring number. **Not fixed here** — this is an audit lane; it needs its own.

---

## 8. Method and commands

Cohort = briefs in `output/s2-gate/_queue/dispatched/` with mtime in the window. Ground truth per
lane = `output/s2-gate/<brief-stem>.md`, the agent's own final report, which `fleet_supervisor.py`
points each lane at via `--out` (`scripts/fleet_supervisor.py:118`). Provider per lane =
`dispatched <provider> <brief>` lines in `output/s2-gate/_queue/supervisor.log`.

```bash
export MSYS_NO_PATHCONV=1

# cohort
find output/s2-gate/_queue/dispatched -name '*.md' -newermt '2026-07-21 18:00' | wc -l    # 93

# PRs in window
gh pr list --state all --limit 250 --json number,title,headRefName,createdAt,state

# provider per lane
grep 'dispatched' output/s2-gate/_queue/supervisor.log | awk '{print $1"\t"$3"\t"$4}'

# orphan branches (pushed, no PR)
gh pr list --head <branch> --state all --json number      # per origin ref in window

# liveness (what fleet_status.py cannot see)
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" |
  Where-Object { \$_.CommandLine -match 'peer_agent.py' }"
```

Classification was mechanical (signature match on each report) then **hand-verified by reading**;
every lane in §4 and §5 was read individually. Cross-family review: dispatched to Codex via
`scripts/codex_review.py` with an instruction to refute the 36/0 split, the sandbox root cause, and
the 18:39 cutover; verdict recorded in the PR body.

**Two orphan branches** exist in the window (pushed, no PR): `claude/required-test-gate` — a known
separate incident, counted not investigated per the brief — and `claude/fix-ideas-pipeline`, where
the lane deliberately held the PR pending its cross-family verdict. Neither is lost work.

### What this audit does not establish

- **What changed at ~18:40** to end Codex's ability to publish. The cutover is measured; its cause
  is not.
- **Which of the two blockers to fix** — sandbox network vs `approval_policy=never` (§3 caveat).
- **Whether the 36 branches are mergeable.** This audit read each lane's self-report; it did not
  check out, build, or test any stranded branch. Their green-test claims are the lanes' own.
- **Whether the rate is stable.** This is one 4-hour window on one day.

---

## 9. Consequences worth acting on

1. **36 finished units of work are unpublished**, including the fix for the P0 in the top STATUS
   Concern row. Recovery needs a `safe.directory` exception per lane, then a push (§4).
2. **Dispatching to `codex` currently means the work will not reach GitHub.** Until the publication
   path is fixed, Codex lanes should be scoped to work whose product is a *report* (which a Claude
   lane can carry, per §6) rather than a branch — or the fleet should route buildable briefs to
   `claude`.
3. **The fleet cannot see itself** (§7), so neither the stranding nor the true liveness is visible
   from `fleet_status.py`.
4. **Restocking a queue whose Codex half cannot publish burns budget at ~0% yield.** 52 Codex lanes
   in this window produced one push to an existing PR and zero new PRs.
