---
title: Consumer AI Anticipation Gap — Jones 2026-05-05
date: 2026-05-07
status: living page
source_wiki_path: pages/concepts/consumer-ai-anticipation-gap-jones-2026-05-05.md
source_wiki_sha256: 3067ce2a7e8f1d0c9859bcd1ffdd2d6c936f523c8a4c22c504233e38a38330d5
---

# Consumer AI Anticipation Gap — Jones 2026-05-05

Source: https://shows.acast.com/ai-news-strategy-daily-with-nate-b-jones/episodes/consumer-ai-has-a-problem-nobodys-naming

Type: industry-framing concept note

## Core Claim

Consumer AI's unsolved problem is not raw capability or tool access. It is
attention burden. Most agents still make the user notice the task, remember the
agent, translate the situation into a prompt, manage progress, and supervise
cleanup. That turns agents into a new inbox instead of an assistant.

Jones names the missing layer the anticipation gap: the system should know when
a situation matters, when to stay quiet, when to suggest, when to draft, when to
ask for confirmation, and only later when to act autonomously.

## Permission Ladder

The useful consumer/prosumer ladder is:

1. Read: the agent can see relevant context.
2. Suggest: the agent points out what likely matters.
3. Draft: the agent prepares the action but does not commit it.
4. Act with confirmation: the agent prepares or navigates the action and asks
   at the consequence boundary.
5. Autonomous: the agent acts without interrupting, only after trust is earned.

Workflow implication: access, meaning, and authority classification is
necessary but not sufficient for proactive work. The branch or loop also needs a
salience and permission posture: why now, why this user, what evidence makes
interruption justified, and what rung of authority is allowed.

## Why Coding Agents Got There First

Coding has bounded context and dense verification: tests, compilers, linters,
git history, review gates, and issue trackers. Consumer life has subjective
success, messy signals, and no obvious test suite. Workflow can generalize from
coding only if it creates comparable meaning and evidence artifacts for other
domains.

## Workflow Fit

This reinforces the current direction:

- Do not build more chatbots or operator dashboards that increase management
  burden.
- The loop should reduce host attention by detecting stale base, wrong
  sequencing, missing source-read proof, missing cross-family maturation, and
  stale branches itself.
- User-facing branches should make situations legible enough for agents to
  anticipate responsibly.
- The brain should capture lived user intent, project taste, prior decisions,
  and permission boundaries so fresh sessions do not ask the user to restate
  everything.

## Design Pressure

Do not rush to autonomous action. The next near-term target is reliable
suggest/draft/confirm behavior with evidence. For Workflow, that means:

- every proactive proposal should carry source-read evidence and a why-now
  reason;
- every action should identify the permission rung it is operating under;
- every interruption should be reversible, dismissible, and learnable;
- loop autonomy should first remove operator chores with objective checks before
  expanding into subjective user-life domains.

## Relationship To Existing Brain Pages

- Extends `work-primitive-industry-framing-jones-2026-05-06` with salience and
  proactivity.
- Supports PR-069 / #577 access-meaning-authority classification, but suggests
  a later refinement: add anticipation, salience, and permission-rung metadata
  once the base classifier lands.
- Supports #566/#576/#579/#580 loop-discipline stack because those remove
  agent-management burden from the host.

## Immediate Action

No immediate code patch follows from this note alone. Treat it as design context
for future request-classification and proactive-assistant work. If #577 lands
cleanly, the smallest follow-on is to evaluate whether request classification
should include `permission_rung` and `why_now` fields rather than adding any new
MCP tool.
