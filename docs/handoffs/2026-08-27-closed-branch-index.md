# Closed-but-preserved branches — 2026-08-27

Thirty pull requests were closed on 2026-08-27. **Closing a PR does not delete its
branch**: every head sha below is still on the remote, and every PR can be reopened.

They were closed because there is no session that will pick them up. The founder
resumes exactly one lane (the 2026-08-26 handoff), so an open PR nobody owns is not
a queue -- it is landfill on the surface that replaced `STATUS.md`.

Resume any one of them with:

```bash
git fetch origin <branch>
git worktree add -b resume/<slug> ../wf-<slug> origin/<branch>
gh pr reopen <number>       # the PR and its history come back
```

| PR | Branch | Head | Draft | Files | What it was |
|---|---|---|---|---|---|
| #1492 | `feat/migration-crossprocess-lock` | `f20311b1` | no | 3 | fix(storage): cross-process migration lock (stacked on #1486) |
| #1662 | `codex/moderation-abuse-runtime` | `99ab18bc` | yes | 8 | feat: establish moderation authority contracts |
| #1667 | `codex/moderation-flag-planner` | `14a3a428` | yes | 4 | feat: plan duplicate-safe moderation flags |
| #1792 | `codex/implement-production-load-harness-main-20260725` | `e199b58d` | yes | 7 | spec: define shared production-load evidence implementation |
| #1819 | `codex/retire-loop-snapshots` | `77fe68fb` | yes | 100 | snapshot: rebuild public graph from canonical sources |
| #1935 | `codex/chatgpt-oauth-cloud-drain-20260730` | `0dcfff8f` | yes | 17 | draft: repair ChatGPT OAuth continuity for cloud automation |
| #2041 | `fix/oauth-cimd-persistence` | `ef8be31e` | yes | 13 | fix: repair ChatGPT OAuth registration continuity |
| #2239 | `drain/20260803-145030-a7ecd9/refine-openspec-moderation-abuse-response` | `043c469a` | no | 1 | chore: narrow moderation refinery slice |
| #2293 | `claude/openspec-precondition-guard` | `a8af865b` | no | 2 | feat(scripts): guard against OpenSpec preconditions naming changes that don't exist |
| #2314 | `claude/select-among-own-provider-bindings` | `0e0763ce` | no | 3 | fix(automation): let an owner say WHICH of their own providers to use |
| #2315 | `claude/ledger-to-zero` | `d7d938ce` | no | 24 | test: drain the quarantine ledger to 0 — every removal proven on Linux |
| #2318 | `claude/admit-slack-app-events` | `f046c517` | no | 32 | feat(slack): admit Slack app events over HTTP, and answer them from the user's own universe |
| #2320 | `claude/oauth-rfc9728-discovery` | `da5cb9a2` | no | 13 | fix(oauth): serve RFC 9728 discovery at the path clients actually probe |
| #2331 | `claude/canary-probes-failed-deploys` | `c84af2ac` | no | 2 | fix(canary): probe production when a deploy FAILS, not only when it succeeds |
| #2340 | `claude/outage-incident-record` | `13bf6d6e` | no | 1 | docs(audit): the /mcp outage and the fence deadlock |
| #2357 | `claude/drain-blocker-record` | `69ab651b` | no | 1 | docs(audit): the drain's root cause, and three rows destroyed finding it |
| #2368 | `claude/true-root-cause-record` | `8ba7be8e` | no | 1 | docs(audit): the true root cause — the universe has no engine |
| #2393 | `claude/slack-socket-mode` | `e1ef8eb7` | no | 84 | Slack universe agent: build/run/deliver, X posting, and cross-turn memory (live-proven) |
| #2394 | `claude/agent-persistent-memory` | `045ff837` | no | 32 | feat(agent-memory): durable session-anchored conversation store (persistent agent) |
| #2395 | `auto/add-changelog` | `8d8b5d56` | yes | 1 | chore: add CHANGELOG.md |
| #2411 | `claude/retire-cloud-worker-fleet` | `6094124d` | yes | 100 | Retire cloud-worker fleet → credential-driven execution |
| #2412 | `claude/fix-serving-admission-ro-lock` | `d7d978fa` | yes | 3 | fix: u-tiny silent — shared provider-assignment lock crashes on read-only /data |
| #2413 | `claude/fix-slack-serving-binding-routing` | `103ddb9d` | yes | 5 | fix(slack): serving-capable universes orphan their own channel routing |
| #2415 | `claude/enable-claude-serving` | `29ef1f66` | yes | 21 | Enable Claude serving (byo-llm deposit boundary + snapshot) + served-budget leak fix |
| #2416 | `claude/ux-universe-resolution-switch-status` | `db4a3a88` | no | 10 | feat(connector): universe-name resolution, per-universe get_status serving, one-call provider switch |
| #2417 | `claude/bake-live-daemon-app` | `f21714eb` | no | 30 | chore(bake): capture proven-live daemon /app hot-patches for durable deploy |
| #2421 | `claude/engine-tools-enable-residuals` | `f775590f` | yes | 13 | fix(engine-tools): enable-residuals for the read-only MCP slice (Codex ADAPT closed) |
| #2427 | `feat/fail-safe-deploy` | `5c2ce51e` | no | 3 | fix(deploy): fail-safe swap replaces the stop-writer fence (24/7 uptime) |
| #2475 | `fix/universe-project-folder` | `f4851437` | yes | 8 | universe = fully-open customizable harness + brain (agent controls any file type; credentials masked, relocation to follow) |
| #2513 | `claude/diagnose-exec-capacity` | `418f3057` | no | 3 | served write_graph: author-gated delete op (universe deletes its own workflows) |

## Spot-checked, so the list is not uniform

I did not verify all thirty. Four were checked because they carry the most work
or the most risk of being re-done:

| PR | Finding |
|---|---|
| **#2427** fail-safe deploy | **Superseded.** `deploy-prod.yml` already routes through `deploy/deploy_fail_safe.sh` (7 references), and the swap+canary+rollback chain was verified end-to-end live on 2026-08-23. Nothing to resume. |
| **#2411** retire cloud-worker fleet | **Genuinely unlanded.** `tinyassets/cloud_worker.py` still exists, so the fleet is not retired. 100 files of real work. Reopen this one if fleet retirement is wanted. |
| **#2413** Slack serving-binding routing | **Target file is gone** — `tinyassets/app_channel_routing.py` no longer exists on `main`, so this cannot merge as written. It also carried a Codex ADAPT verdict (`>=` violates exact-revision authority). Re-derive from the current code rather than resuming the diff. |
| Lane 2, `claude/fleet-slice1-reconciler` | **Already landed.** `tinyassets/runtime_reconcile.py` carries `build_stale_fleet_plan`, and `reconcile-stale-retired-fleet-artifacts` is archived complete. The 2026-08-26 handoff guessed this; it is confirmed. The branch is redundant. |

The other 26 were closed unexamined. That is a deliberate trade, stated plainly:
their branches are intact and reopening is one command, which is cheaper than
auditing 26 stale diffs nobody has asked for.

## The one lane that stays open

**PR #2559** · `claude/run-provider-session` — Lane 1 of the 2026-08-26 handoff,
the only live lane. Its last commit is explicitly unreviewed WIP committed so a
worktree teardown could not lose it; read `git log -p 3eb798eb..19524770` before
trusting it. Its `_PURPOSE.md` describes a *different* lane than its commits --
the commits are the truth.

---

## All 218 local branches archived and cleared (2026-08-27)

The local checkout carried 218 branches beyond `main`. **Only 8 had their tip
reachable from any remote** — the other 210 existed on exactly one machine. That
is the class that held `99529969`, a droplet-diagnostics commit found on no
remote during the 2026-08-26 audit.

Two classification attempts both failed to answer "does this hold unlanded
work?":

| Attempt | Why it failed |
|---|---|
| Tip reachable from a remote or `main` | Squash-merge guarantees a merged branch's tip is unreachable even when its content landed in full — 210 of 218 flagged |
| Changed files still differing from `main` | `main` moves forward, so an old branch differs even when its work landed — 213 of 218 flagged |

So classification was abandoned in favour of **preserving everything**, which
makes the question unnecessary:

```bash
# every local branch pushed to a namespace that does not appear in the branch UI
git push origin 'refs/heads/<name>:refs/archive/2026-08-27/<name>'
```

**218 archived, verified sha-by-sha against the local tips — zero mismatches —
then 218 local refs deleted.** Local branches: **931 → 3** (`main` plus two
worktree lanes).

`pr1435` needed a stale `refs/heads/pr1435.lock` from 2026-07-01 cleared first;
it was archived before that, and no git process held it.

### Recovering an archived branch

```bash
git fetch origin 'refs/archive/2026-08-27/*:refs/archive/2026-08-27/*'
git ls-remote origin 'refs/archive/2026-08-27/*'          # list everything
git branch <name> refs/archive/2026-08-27/<name>          # restore one
```

`refs/archive/*` is a custom namespace: GitHub stores it, `git ls-remote` finds
it, and it does not clutter the branch list or the PR surface. Nothing here was
deleted — it was moved off the one machine that was holding it.
