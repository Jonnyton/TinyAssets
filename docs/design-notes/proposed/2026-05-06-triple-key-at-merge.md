---
title: Triple Key At Merge
date: 2026-05-06
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 452
wiki_source: pages/notes/pages-notes-cowork-substrate-framing-correction-triple-key-at-merge-2026-05-06.md
scope: design-only; no runtime code in this branch
builds_on:
  - docs/exec-plans/active/2026-04-30-live-community-reiteration-loop.md
  - docs/specs/2026-05-03-dual-key-auto-ship-acceptance.md
  - docs/specs/2026-05-04-loop-autonomy-roadmap.md
  - docs/ops/wiki-bug-sync-runbook.md
---

# Triple Key At Merge

## 1. Correction

Host approval is a merge-time key, not a filing-time or checker-key
precondition.

Community probes, wiki filings, issue sync, branch drafts, investigation
packets, and PR creation should flow without host approval when the request is
otherwise valid. The host key is required only for ship classes whose merge
policy declares it, such as runtime, substrate, API, deploy, auth, secrets, or
other high-risk classes. For those classes, the gate becomes triple-key at the
merge step: Codex-family review, Anthropic-family review, and host approval or
an explicit host-delegated policy.

This corrects the unsafe framing that treats host approval as a blocker before
checker participation. Early host blocking starves the community loop of
evidence. The right safety boundary is immediately before merge, after the
loop has produced a concrete PR, checks have run, and reviewers can evaluate a
specific diff.

## 2. Stage Map

The community loop keeps these stages distinct:

| Stage | Gate |
|---|---|
| Wiki filing / issue sync | Request shape, labels, dedup, abuse filters |
| Investigation / probe branch | Daemon eligibility, declared file scope, branch safety |
| PR creation | Ship-class path envelope, rollback handle if required |
| Merge | Required reviewer keys, host key if class requires it, CI, branch protection, final envelope re-check |
| Deploy / observation | Canary, user-surface proof where applicable, rollback or watch item on red |

The key rule is simple: probes generate evidence; merge consumes approvals.
Checker keys and host keys belong at merge because that is where approval has a
specific object: the PR head, changed paths, validation envelope, CI state, and
rollback plan.

## 3. Gate Contract

Every request may still declare gate requirements at filing time. Those
requirements tell daemons what work they may claim and tell users what evidence
will be needed later. They do not mean every key must already be turned.

Recommended interpretation:

- `daemon-request`: paid or free daemons may claim if they satisfy the
  declared requirements.
- `writer-pool:claude-codex`: code-changing writers are restricted to the
  current flagship Claude/Codex lanes.
- `checker:cross-family`: a code-changing PR needs the opposite family as a
  checker before merge.
- `gate-required`: the request has a declared gate ladder; inspect the request
  or ship-class policy for the merge requirements.
- Host approval: required only when the merge policy for the ship class names
  a host key, or when an explicit host-decision label says the request cannot
  advance.

For low-risk design-only or docs-only branches, the host key is normally absent
unless the request changes canonical project commitments. For runtime,
substrate, API, deploy, auth, secret, migration, or public-surface behavior,
the host key remains a merge blocker until delegated by policy.

## 4. Why This Shape

Filing-time host approval creates a hidden single-person bottleneck and makes
the public request loop look dead whenever the host is offline. It also asks
the host to approve an abstraction before there is a diff, test result, or
release packet to inspect.

Merge-time approval preserves safety while improving uptime:

- community daemons can investigate and propose changes while the host is
  offline;
- opposite-family checkers can review concrete branches early;
- risky work still cannot merge without its declared keys;
- rejected or held PRs feed findings back into loop memory instead of being
  invisible blocked filings;
- probes remain cheap and reversible because they do not imply acceptance.

The correction matches the existing auto-ship specs: approval keys are policy
gates on PR-backed ships, with GitHub review state and branch protection as the
canonical substrate. Host approval is an additional required key for selected
classes, not a replacement for cross-family review and not a prerequisite for
request intake.

## 5. Policy Implications

Implementation work that follows this note should keep the following
invariants:

1. Do not block wiki sync, issue creation, investigation, or PR creation merely
   because a host key is missing.
2. Do block merge when the ship class requires host approval and the host key
   is missing, expired, held, or rejected.
3. Keep key state visible in PR comments, loop health, or the auto-ship ledger
   so a waiting host key is an observable parked state.
4. Re-read GitHub review state, CI, changed paths, and the validation envelope
   immediately before merge.
5. Treat host-decision labels as explicit blockers only when they say the
   request cannot advance, not as a default condition for all high-risk probes.

## 6. Open Questions

1. Which exact ship classes require the host key in v0? Recommendation:
   runtime, substrate, API/MCP behavior, deploy, auth, secrets, migrations,
   and public-surface behavior.

2. How should host delegation be represented? Recommendation: a ship-class
   policy field such as `required_keys: [codex_reviewer, cowork_reviewer,
   host]`, with a later `host_delegated_to` field only after a separate
   accepted proposal.

3. Should project-design notes require host approval before merge?
   Recommendation: only when they modify accepted canonical design truth
   (`PLAN.md`) or authorize runtime implementation. Proposed notes under
   `docs/design-notes/proposed/` can be drafted freely and reviewed normally.

## References

- `docs/exec-plans/active/2026-04-30-live-community-reiteration-loop.md`
- `docs/specs/2026-05-03-dual-key-auto-ship-acceptance.md`
- `docs/specs/2026-05-04-loop-autonomy-roadmap.md`
- `docs/ops/wiki-bug-sync-runbook.md`
