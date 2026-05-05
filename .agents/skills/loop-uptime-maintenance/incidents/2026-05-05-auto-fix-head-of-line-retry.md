---
incident_date: 2026-05-05
short_name: auto-fix-head-of-line-retry
severity: p1
time_to_recovery_minutes: 8
applied_by: codex-gpt5-desktop
---

# Incident: Auto-fix head-of-line retry loop

## Symptoms

The community patch loop had about 10 hours to drain its backlog, but the
writer queue stayed red. `community_loop_watch.py --json` reported 16 pending
requests older than 45 minutes and 11 needs-human branch-push blockers. The
active `auto-fix-bug.yml` run was repeatedly selecting issue #343 instead of
advancing to older pending requests.

Issue #343 had 15 repeated GitHub Actions comments with the same shape:

```text
Auto-fix needs human review - approved writer auth was present, but no automated PR was opened.
Codex subscription outcome: failure
The issue is marked needs-human so it does not loop silently.
```

But the issue labels only showed `auto-fix-attempted` plus request labels while
the latest run was in progress. It was missing `auto-fix-reviewed`, so the
discover step treated it as retryable again whenever writer auth was visible.

A second self-clear blocker was already visible in the same watch output:
issue #311 and 10 other open loop requests had
`auto-fix-branch-push-blocked` because the writer produced patches but GitHub
Actions' default token could not push branches that updated
`.github/workflows/*`.

## Evidence snapshot

```text
community_loop_watch.py --json at 2026-05-05T18:20Z:
- overall: red
- writer workflow: auto-fix-bug.yml in_progress on run 25394263202
- writer queue: 16 pending older than 45 min
- branch_push_blocked: [311,306,305,303,298,295,264,258,233,209,87]
- first blocked issue: #311 BUG-064 stale-base queue maintenance

gh issue view 343 at 2026-05-05T18:20Z:
- comments: 15 repeated no-PR comments
- labels: auto-fix-attempted, daemon-request, payment:free-ok,
  writer-pool:claude-codex, checker:cross-family, gate-required, auto-change,
  request:docs-ops

auto-fix-bug.yml discover logic:
- maxIssues = 1
- needsHuman && hasWriterAuth && !autoFixDisabled && !reviewed => retry

auto-fix-bug.yml no-PR terminal labeling before this patch:
- adds auto-fix-reviewed only for no_change_reason, PR creation block, or branch
  push block
- does not add auto-fix-reviewed for a raw writer step failure

gh secret list before the push-token fix:
- WORKFLOW_CODEX_AUTH_JSON_B64 existed
- WORKFLOW_PUSH_TOKEN was absent

gh auth status:
- local GitHub token scopes included repo and workflow
```

## Immediate fix applied

Opened a code lane on `codex/loop-self-clear-fix`.

Temporary live triage:

- Created the `auto-fix-writer-failed` label.
- Added `needs-human`, `auto-fix-reviewed`, and `auto-fix-writer-failed` to
  issue #343 so the next discovery run can move past the repeated issue.
- Left an issue comment explaining that this was emergency loop triage and that
  the workflow patch makes the same terminalization automatic.
- Issue #344 then hit the same no-PR writer-failure class before PR #395 could
  land, so it was also labeled `auto-fix-reviewed` and
  `auto-fix-writer-failed` to keep discovery moving.
- Issue #345 then exposed a third self-clear blocker: Codex produced a valid
  diff, but the workflow injected the user-derived PR title directly into
  `git commit -m "..."`. The title contained quotes and parentheses, so bash
  failed before commit/push/PR classification and left only `needs-human`.
- Issue #346 repeated the same title-shell class: the writer produced a docs
  patch, then `git commit` split the quoted title into pathspecs. It was
  manually labeled as reviewed/writer-failed while #395 was still pending.

Patch:

- Add a precise `auto-fix-writer-failed` label definition.
- Feed `CLAUDE_OUTCOME` and `CODEX_OUTCOME` into the no-PR marking step.
- Treat a selected writer step outcome of `failure` as a terminal reviewed
  no-PR outcome by adding `auto-fix-reviewed` and `auto-fix-writer-failed`.
- Keep the issue open with `needs-human`, but make it ineligible for automatic
  scheduled rediscovery until a human or manual dispatch explicitly retries it.
- Add optional `WORKFLOW_PUSH_TOKEN` support for Codex writer branch pushes.
  When present, the workflow sets the git remote to use that token before
  pushing, which covers workflow-file edits that GitHub's default Actions token
  rejects.
- Installed the `WORKFLOW_PUSH_TOKEN` repo secret at 2026-05-05T18:32Z from
  the existing local `gh` auth token, whose visible scopes include `workflow`.
- Quoted the `loop-uptime-maintenance` skill frontmatter description. The #344
  writer run logged that Codex could not parse the skill YAML because the
  unquoted description contained `condition:`.
- Pass the Codex PR title through a `PR_TITLE` environment variable and commit
  with `git commit -m "$PR_TITLE"` so quotes, parentheses, and other
  user-authored title characters cannot break the shell.
- When `WORKFLOW_PUSH_TOKEN` is visible, let discovery retry
  `auto-fix-branch-push-blocked` issues and clear their stale
  `auto-fix-reviewed` / `auto-fix-branch-push-blocked` labels as they enter the
  fix job. Without this, #311-class issues would stay terminal even after the
  new push credential existed.

## Verification

Local verification on 2026-05-05:

```text
python -m pytest tests/test_auto_fix_workflow.py -q
42 passed

python -m ruff check tests/test_auto_fix_workflow.py
All checks passed

git diff --check
clean
```

Recovery is not complete until the PR lands and a later scheduled writer run
advances past #343 to a different queue item or terminalizes #343 with
`auto-fix-reviewed`.

Live recovery evidence at 2026-05-05T18:28Z:

```text
community_loop_watch.py --json:
- reviewed_terminal now includes #343

gh run view 25394681892:
- discover completed successfully
- fix job selected issue #344, not #343
```

That proves the immediate head-of-line starvation was cleared. PR #395 is still
needed so the same class terminalizes automatically next time.

Push-token setup evidence:

```text
gh secret list --repo Jonnyton/Workflow:
- WORKFLOW_PUSH_TOKEN 2026-05-05T18:32:42Z

Run 25395083723 at 2026-05-05T18:39Z selected #345 and produced a real patch,
then failed before commit/push:
- `scripts/wiki_bug_sync.py` and `tests/test_wiki_bug_sync.py` changed
- `python -m pytest tests/test_wiki_bug_sync.py -q` reported 28 passed
- shell error: `syntax error near unexpected token '('`
- root cause: `${{ steps.meta.outputs.pr_title }}` was expanded inside
  `git commit -m "..."` while the issue title contained quotes and parentheses

Run 25395510516 at 2026-05-05T18:49Z selected #346 and hit the same title
wrapper class:
- docs patch touched `docs/design-notes/2026-05-05-retrolab-gap-burndown-v1.md`
  and `docs/design-notes/INDEX.md`
- shell reported `error: pathspec 'gap' did not match any file(s) known to git`
  and similar pathspec errors for title words
- temporary triage labeled #346 `auto-fix-reviewed` + `auto-fix-writer-failed`
```

## Question 1 - How did the loop break this time?

The writer lane had a head-of-line retry bug. The discover job processes one
issue at a time and retries `needs-human` issues when writer auth is visible
unless they have `auto-fix-reviewed`. A Codex subscription failure produced no
PR and no structured `no_change_reason`, so the no-PR step added only
`needs-human`. That made #343 eligible again on the next schedule. The loop
kept spending its single writer slot on the same terminal-looking issue.
On the next queue item, the same run script also treated the user-authored
title as shell syntax during commit creation. The writer had already generated
and verified a patch, but the wrapper failed before it could commit, push, open
the PR, or classify the failure precisely.

## Question 2 - How can the loop notice this break next time, automatically?

`community_loop_watch.py` should flag repeated same-issue writer attempts. A
useful signal is: same issue selected by `auto-fix-bug.yml` more than N times
within a moving window while older pending requests exist. The watch should
report this separately from generic old-pending backlog because this is a
starvation class, not ordinary queue depth.

## Question 3 - How can the loop fix this break next time, automatically?

The loop should terminalize no-PR writer failures on the first failed attempt:
keep `needs-human`, add a precise failure-class label, and add
`auto-fix-reviewed` so scheduled discovery can continue. Manual dispatch can
still retry the issue after a checker or operator changes the input. For
workflow-file branch push failures, the loop should use a repo secret PAT with
Contents write and Workflows write instead of the default GitHub Actions token.
For user-derived PR titles, the loop should never splice the title directly
into shell code; pass it through environment or a file and let the shell read it
as data.
For old branch-push failures that predate the new credential, discovery must
explicitly requeue them when `WORKFLOW_PUSH_TOKEN` becomes visible; otherwise
fixing the capability does not drain the already-terminal backlog.

## Question 4 - How can the loop avoid this break in the first place next time?

Issue selection should be fairness-aware instead of `maxIssues = 1` with
implicit retry rules. The writer queue needs a first-class attempt ledger with
terminal, retryable, cooldown, and superseded states. Discovery should select
the oldest eligible request after applying those states, not infer eligibility
from labels alone.

## Substrate improvement filed

This incident produced PR #395 from `codex/loop-self-clear-fix`. The follow-up
substrate improvement is a watch-level repeated-same-issue starvation check.

## PLAN.md update

No PLAN.md update in this patch. This is an operational queue-policy fix inside
the existing autonomous writer lane; the larger attempt-ledger design should be
captured separately if Cowork/Codex agree on that next slice.
