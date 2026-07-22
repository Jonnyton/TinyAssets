# The alarms that can open but never close — 65 issues, and one stage out of three that knows how to reconcile

**Filed:** 2026-07-22
**Provider:** claude-code (`claude/stale-alarm-issues`)
**Evidence freshness:** all GitHub API + live-watcher observations taken 2026-07-22T04:10–04:35Z. Run
lists, issue counts, and watcher output move; re-run the commands in §7 before relying on any number here.
**Scope:** the `tier3-broken` and `deploy-failed` alarm labels. The `p0-outage` half of this class is
[`2026-07-22-uptime-canary-false-red-incident.md`](2026-07-22-uptime-canary-false-red-incident.md)
(PR #1513) — that audit does not mention `tier3-broken` or `deploy-failed`, and this one does not
touch issue #1461.

---

## 1. The finding in one paragraph

Two GitHub Actions workflows open an issue when they fail. Neither has ever closed one. Between
2026-04-20 and 2026-05-06 they accumulated **65 open, zero-comment alarm issues** — 17 `tier3-broken`
and 48 `deploy-failed`. Both underlying surfaces have been green for over two months. The issues are
still open because *nothing in the repo can close them*: the filing workflows only know how to
`issues.create`, and of the three consumers that could reconcile an alarm against observed reality,
exactly one does. That one — `tier3_clone_smoke_stage` — has been reporting **`yellow`** continuously
since 2026-05-07 while the surface it watches went green 74 nights in a row. The guard did its job
(no false red) and, in doing so, made the never-closing bug invisible for 2.5 months.

## 2. The inventory

All 65 issues carry **zero comments**. Counts are open-state as of 2026-07-22T04:20Z:

| Label | Open | Filed by | Range | Ever closed one? |
|---|---|---|---|---|
| `tier3-broken` | **17** | `.github/workflows/tier3-oss-clone-nightly.yml` step *Open tier3-broken issue* (~L84) | 2026-04-20 → 2026-05-06 | **No — zero closed, ever** (`gh issue list --state closed --label tier3-broken` → `[]`) |
| `deploy-failed` | **48** | `.github/workflows/deploy-prod.yml` step *Open deploy-failed issue* (~L944) | 2026-04-20 → 2026-05-05 | No |

> **Correction to the premise this lane was dispatched on.** The brief named three issues (#384,
> #399, #506) and described them as "three alarm issues from May". They are not three isolated
> issues — they are the **newest members of two cohorts totalling 65**. The undercount came from
> `gh issue list --limit 200` silently truncating: the repo has **294 open issues**. The live
> watcher is what exposed it, by printing `17 open tier3-broken issue(s)` where the brief predicted
> two. Anyone re-running this: pass an explicit `--label` filter, not a global limit.

This matters operationally, not just for tidiness: **closing #384 and #506 does not turn the tier-3
stage green.** Fifteen older `tier3-broken` issues remain, so the stage stays `yellow` regardless.
The brief's implied outcome ("the Tier-3 stage is stuck permanently yellow … purely because two May
issues are open") is wrong on the cause; it is stuck because seventeen are.

## 3. Why filing stopped in May — the filer is healthy, and one gap is correct

The tier-3 nightly failed **17 consecutive nights**, 2026-04-20 through 2026-05-06 — one issue per
night, exactly matching the 17 open issues. It has been green since:

- First green after the streak: run `25488453292`, 2026-05-07T09:46:45Z.
- Since 2026-05-06: **75 runs, 74 success**.
- The one non-success, run `29011930820` (2026-07-09T10:32:20Z), reports run-level
  `conclusion: failure` but its only job, `fresh-clone-smoke`, is **`cancelled`**. Steps guarded by
  `if: failure()` do not run on cancellation, so no 18th issue was filed.

That last point was worth chasing: a filer that stopped filing could have meant a silently dead
alarm — the more dangerous failure mode. It doesn't. 17 failures produced 17 issues, and the 18th
non-success was a cancellation where *not* filing is the right behavior. **The filing half works.
Only the closing half is missing.**

## 4. The asymmetry — three consumers, one reconciler

`scripts/community_loop_watch.py` reads two of these three labels (`P0_OUTAGE_LABEL = "p0-outage"`
L40, `TIER3_BROKEN_LABEL = "tier3-broken"` L41). The three alarm signals are handled three different
ways:

**(a) `tier3_clone_smoke_stage` (L333–410) reconciles.** If open issues exist *but* the latest
tier-3 run is completed + success + newer than the newest open issue, it downgrades red → yellow:

```python
    if (
        latest is not None
        and latest.get("status") == "completed"
        and latest.get("conclusion") == "success"
        and latest_time is not None
        and newest_issue_time is not None
        and latest_time > newest_issue_time
    ):
        return _stage(
            "Tier-3 clone smoke",
            "yellow",
            (
                f"latest {WORKFLOWS['tier3']} success is newer than "
                f"{len(issues)} open {TIER3_BROKEN_LABEL} issue(s)"
            ),
```

**(b) `incident_stage` (L307–330) does not.** Any open `p0-outage` issue is unconditionally red. No
workflow run is consulted at all:

```python
    issues = list_open_issues_by_label(repo, P0_OUTAGE_LABEL, api=api, token=token, timeout=timeout)
    if issues:
        issue = issues[0]
        return _stage(
            "Observation incidents",
            "red",
            f"{len(issues)} open {P0_OUTAGE_LABEL} issue(s)",
```

**(c) `deploy-failed` has no consumer at all.** Repo-wide, it appears only where it is *written*
(`deploy-prod.yml` L11/L944/L952), as a contrast note in `p0-outage-triage.yml` L19, and as prose in
`deploy/DEPLOY.md` L474 and a 2026-04-20 design note. No watcher stage, no script, no gate reads it.
`WORKFLOWS["deploy_prod"]` exists in the watcher, but the "Production deploy" stage reads *run
conclusions*, never the label. **48 issues have accumulated on a write-only alarm.**

## 5. Live watcher output — the guard working, and hiding

```
Community loop status: RED
Checked: 2026-07-22T04:28:18.396456Z
- RED    Observation canary: uptime-canary.yml latest run concluded failure
         run 29888685398 at 2026-07-22T03:31:53Z
- RED    Observation incidents: 1 open p0-outage issue(s)  →  #1461
- YELLOW Tier-3 clone smoke: latest tier3-oss-clone-nightly.yml success is newer
         than 17 open tier3-broken issue(s)
- GREEN  Production deploy: deploy-prod.yml latest run succeeded  →  run 29882303754
- GREEN  Website deploy
```

Read those three lines together and the asymmetry is stark. The **same underlying condition** — a
stale alarm issue nobody closed — produces `yellow` in one stage, `red` in another, and *nothing at
all* for the 48 `deploy-failed` issues, which do not appear in the report in any form.

Note the tier-3 evidence string says "newest issue #506" using `issues[0]`. That happens to be
correct here (GitHub's issue list defaults to created-desc), but it is a positional assumption, not a
computed one — `newest_issue_time` is properly a `max()` over all issues a few lines above, while the
number printed beside it is not.

## 6. A fossil: the label description records a server migration nobody updated

The live `deploy-failed` label description reads:

> CI deploy to **Hetzner** failed; auto-rollback attempted.

`origin/main`'s `deploy-prod.yml` L969 says:

> CI deploy to **DO Droplet** failed; auto-rollback attempted.

Both are "correct" — the workflow calls `createLabel` **only inside a 404 handler**, so the
description is written once, at first-ever failure, and never reconciled afterward. The label was
bootstrapped 2026-04-20 by issue #1; `.agents/activity.log:126` records that same day:
*"deploy-prod.yml retargeted from Hetzner to DO Droplet (Task #20) — CI was deploying to wrong
provider"*. The label has carried the pre-migration provider name for three months.

Minor on its own. Included because it is the **same shape as the main finding**: state that a
workflow can create but never update, drifting silently from the reality it describes.

## 7. Staleness verification — per issue

An alarm issue is not stale because it is old; it is stale because the condition it reports has since
been *observed* green. Commands to reproduce:

```bash
gh issue list --state open --label tier3-broken  --limit 100 --json number,createdAt,comments
gh issue list --state open --label deploy-failed --limit 100 --json number,createdAt,comments
gh run list --workflow tier3-oss-clone-nightly.yml --limit 200 --json databaseId,createdAt,conclusion
gh run list --workflow deploy-prod.yml            --limit 200 --json databaseId,createdAt,conclusion
python scripts/community_loop_watch.py
```

| Issue | Reports | Superseded by | Verdict |
|---|---|---|---|
| **#384** (2026-05-05T09:23:36Z) | fresh-clone install + `import_graph_smoke.py` + `pytest tests/smoke/` broken on main | run `29819348969`, success, **2026-07-21T09:42:36Z**; and 74 nightly successes since run `25488453292` (2026-05-07T09:46:45Z) | **STALE** |
| **#506** (2026-05-06T09:37:32Z) | same | same | **STALE** |
| **#399** (2026-05-05T19:40:35Z) | CI deploy to prod failed; auto-rollback attempted | run `29882303754`, success, **2026-07-22T01:09:05Z** — **and production confirms delivery**, below | **STALE** |

For the tier-3 pair, "a later success" is genuinely a re-test: the nightly re-clones `main` from
scratch and re-runs the identical smoke on a schedule, so a green run exercises the same condition
that failed, not a correlated proxy.

For #399 the workflow-run success alone would be weaker — so it is corroborated against production
per **Hard Rule 14** (*merged is not deployed*). Live `get_status.release_state`, read
2026-07-22T04:33Z:

```
deploy_run_id:        29882303754      ← the exact run cited as superseding #399
deploy_run_url:       https://github.com/Jonnyton/TinyAssets/actions/runs/29882303754
deployed_at:          2026-07-22T01:11:27.601589Z
git_sha:              1605349e888c918dc9ef8fd1452cb40d83a5dc51
canary_bundle_status: passed
```

Production is serving the artifact from the superseding run and its canary bundle passed. The deploy
path is not merely green in CI — it delivered.

**The Hetzner/DO straddle, checked.** If the deploy pipeline was rebuilt between the failure and the
success, a later green would be *obsolescence*, not supersession — a different pipeline succeeding
says nothing about the old one. That concern does not apply to #399: the retarget landed 2026-04-20
and #399 was filed 2026-05-05, so it is a DO-era failure superseded by DO-era successes, same target
throughout. It **does** apply to the oldest `deploy-failed` issues (#1–#7, all 2026-04-20), which
straddle the retarget — one reason this audit does not bulk-close that cohort (§9).

## 8. What was closed

Closed in this lane, each with a comment carrying the superseding run id + timestamp: **#384, #506,
#399**. Nothing was closed silently.

## 9. What was deliberately *not* done

- **The other 62 issues were left open.** They are, as far as this audit can tell, stale by the same
  reasoning — but the dispatch authorized three closures, and 65 bulk closures on a shared repo is a
  materially different, outward-facing action. The oldest `deploy-failed` cohort also straddles the
  Hetzner→DO retarget (§7) and deserves its own verification pass rather than inheriting #399's.
  **Recommended next step: an explicit host go-ahead to bulk-close the remaining 14 `tier3-broken`
  and 47 `deploy-failed` issues** — the tier-3 remainder is what actually unsticks the watcher stage.
- **`scripts/community_loop_watch.py` was not edited** — PR #1513 owns that file.
- **`.github/workflows/**` was not edited** — the workflow change belongs with the code fix, and
  touching it here would require the `infra-change` label for the *Diff scope declared* check.
- **Issue #1461 was not touched**, per PR #1513's explicit decision.
- **Issue #1460** (`community-loop-red`, 2026-07-15T21:32:49Z) was **left open and is entangled**.
  It was filed 3 minutes *before* #1461 (21:35:49Z), so it is not merely downstream of it — but the
  loop is red right now for two independent reasons (#1461 via `incident_stage`, plus the
  uptime-canary run `29888685398` failing at 2026-07-22T03:31:53Z). It cannot be verified stale
  while the watcher is genuinely red. Leaving it.

## 10. The proposed fix — and why the obvious one is wrong for incidents

Recorded here; **not applied in this lane** (see §9). Full patch text is in the PR body.

**Recommended: close-on-success in the filing workflows.** The alarm that opened the issue is the
only thing that knows the condition well enough to clear it. Add to each workflow an `if: success()`
step that closes open issues carrying its own label. For tier-3 this is unambiguously sound — a
green nightly is a full re-test of the identical condition. For `deploy-failed`, close on the next
successful deploy that reaches the post-canary step, which is what `release_state` already proves.

**Rejected for `incident_stage`: giving it the tier-3 reconciliation guard.** This is the tempting
symmetry fix and it is unsafe, because a P0 outage alarm is a *different kind of signal* from a
nightly smoke alarm:

| | tier-3 nightly | uptime canary / `p0-outage` |
|---|---|---|
| Cadence | once a night | frequent |
| What one green run proves | the full fresh-clone condition was re-tested end-to-end | the service answered *one probe, once* |
| "Success newer than issue" means | the failing condition no longer reproduces | possibly just a gap between flaps |

A flapping outage emits green probes between failures. Under a run-is-newer-than-issue guard, an
*ongoing* P0 would be auto-downgraded to yellow within minutes of being filed, every time it briefly
answered. The tier-3 guard is safe **only** because of the slow cadence and the full re-test; port it
to incidents and it becomes an outage-suppressor. If `incident_stage` gets any reconciliation at all,
it should require sustained green (N consecutive successes over a defined window), never a single
newer run.

**Also needed: `deploy-failed` gets a consumer, or stops being filed.** A label that 48 issues
accumulate on and nothing reads is a write-only alarm — it is strictly worse than no alarm, because
it looks like coverage.

**A guard that turns red into yellow is a reporting fix, not a hygiene fix.** The issues still need
closing either way. The evidence for this framing is in this repo's own history: the tier-3 stage has
reported `yellow` — never `green` — since 2026-05-07, through 74 consecutive green nightlies. The
guard correctly prevented a false red, and simultaneously converted a loud, actionable signal into a
steady state nobody pages on. The alarm was never cleared; it was merely made quiet enough to ignore
for 2.5 months. Any fix that stops at the reporting layer reproduces exactly that outcome.

## 11. Proposed STATUS.md concern

Not applied — STATUS.md is contended (#1506/#1507). Text in the PR body for whoever lands those.
