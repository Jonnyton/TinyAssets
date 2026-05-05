---
title: Durable Coordination Architecture
date: 2026-05-05
status: research
source: pages/design-proposals/design-001-durable-coordination-architecture-where-workflow-s-structura.md
source_issue: 299
---

# Durable Coordination Architecture

Community wiki source:
`pages/design-proposals/design-001-durable-coordination-architecture-where-workflow-s-structura.md`,
filed as GitHub Issue #299. This repository note keeps the project-design
request visible to coding sessions without promoting it to canonical
`PLAN.md` truth.

## Classification

Request kind: project-design.

Smallest useful repo change: preserve the design implication as a tracked
design reference and name the architectural boundary that future work should
respect. No runtime code change, new MCP action, new primitive, or wiki-droplet
edit is implied by this issue.

## Freshness Baseline

External agent platforms have converged on capabilities that Workflow should
not treat as durable moats:

- OpenAI's Responses API added remote MCP server support, built-in tools,
  background mode, and other agent-building features in 2025.
- Anthropic describes the Claude Agent SDK as a way to build general-purpose
  agents on top of the Claude Code harness, with file, terminal, and tool
  access as the load-bearing affordance.
- Google's ADK presents production agent development as prompts plus tool
  calls that scale into multi-agent orchestration, graph workflows,
  evaluation, and deployment.

Evidence checked 2026-05-05:

- OpenAI, "New tools and features in the Responses API," 2025-05-21:
  https://openai.com/index/new-tools-and-features-in-the-responses-api/
- Anthropic, "Building agents with the Claude Agent SDK," 2025-09-29:
  https://claude.com/blog/building-agents-with-the-claude-agent-sdk
- Google ADK documentation, accessed 2026-05-05:
  https://adk.dev/

The strategic conclusion is narrow: agent harness quality, tool calling,
computer use, background execution, and provider-native orchestration are
becoming table stakes. Workflow's defensible architecture must sit above
those capabilities.

## Where The Structural Moats Sit

Workflow's moat is not "our agent can code" or "our chatbot can call tools."
Those claims decay as labs converge. The durable advantage is the coordination
substrate that lets many users, daemons, providers, and reviewers improve the
same commons while no single host is online.

The load-bearing moats are:

- Public commons as product memory: wiki pages, design notes, issues, PRs,
  branches, run records, gate evidence, and attribution events become
  discoverable remix material instead of private chat residue.
- Provider-neutral control station: Claude, ChatGPT, IDE agents, local shells,
  and future MCP clients steer the same Workflow primitives rather than
  becoming separate product surfaces.
- Durable coordination spine: `STATUS.md`, purpose-named branches, worktrees,
  `_PURPOSE.md`, PRs, and provider-context feeds make cross-provider work
  recoverable after any single session disappears.
- Minimal primitives plus community-build: platform code ships only the
  smallest primitive gaps; policies, workflows, privacy patterns, and domain
  methods evolve as community artifacts.
- Reviewable evidence chain: gates, tests, live chatbot-surface proof,
  post-fix use evidence, and issue re-entry make claims falsifiable.
- Hostless uptime posture: public state and cloud-visible loop status remain
  readable and actionable when local daemon hosts are offline.
- Lineage and attribution: users and daemons can reuse, fork, converge, and
  reward work because provenance survives across versions and providers.

## Non-Moats

These should not absorb platform scope unless they expose a primitive gap:

- Prompt templates that one lab product can reproduce.
- A single provider's agent team shape.
- A fixed "coding team" pipeline owned by Workflow.
- Provider-specific computer-use behavior.
- Private data hosting on the platform.
- Convenience MCP verbs that a capable chatbot can compose from existing
  primitives.
- One-off dashboards that are not backed by typed durable state.

## Architecture Decision

Treat Workflow as a durable coordination layer over converging agent labs.

The platform should invest in shared state, typed records, discovery, remix,
lineage, claims, leases, review gates, and hostless visibility. It should not
compete with labs on generic agent execution, coding strength, or proprietary
harness UX. Those external systems are replaceable workers and control
stations; Workflow's job is to make their work composable, auditable, and
recoverable.

This aligns with current `PLAN.md`:

- `Scoping Rules`: new capability proposals must pass minimal-primitives,
  community-build, commons-first, and user-capability-axis checks.
- `Harness And Coordination`: the Three Living Files, worktree spine, verifier
  paths, traces, and provider-context feeds are architectural capabilities, not
  incidental process.
- `Community Evolvable Optimization`: useful pieces should be improvable by
  users and daemons without maintainers online.
- `Work Targets And Review Gates`: daemon-chosen work requires a unified
  target registry and justified review gates.

## Design Implications

Future project-design proposals should classify requested work by which moat
it strengthens:

- Commons memory: adds durable, discoverable, attributed public artifacts.
- Coordination recovery: helps another provider resume safely from current
  state.
- Primitive composition: reduces platform surface area while increasing what
  chatbots can build.
- Evidence quality: makes claims testable, replayable, or falsifiable through
  user-visible proof.
- Hostless uptime: keeps public surfaces useful when no personal host is
  online.
- Provider parity: works through multiple MCP clients instead of binding to
  one lab.

If a proposal strengthens none of those, it is likely a convenience, demo, or
provider-specific imitation and should stay in community space.

## Follow-Up Candidates

These are follow-up lanes, not work authorized by this note:

1. Add a design-review checklist item that asks which durable moat a proposal
   strengthens.
2. Extend community-loop status records so project-design issues can show
   "preserved as research," "promoted to PLAN," or "rejected as non-moat"
   without relying on prose-only comments.
3. Draft a contributor-facing "how to write Workflow-native project designs"
   guide using the moat categories above.
4. Audit existing active design notes for provider-specific assumptions that
   should be reframed as provider-neutral coordination requirements.

## Open Questions

- Which moat category should block merge when absent, and which should merely
  guide prioritization?
- Should design issues that are preserved as research automatically get a
  wiki/GitHub status update, or should that remain manual until the community
  loop is healthier?
- What typed record should eventually represent design-request lifecycle state:
  wiki page metadata, GitHub issue labels, Workflow run records, or a dedicated
  request table?
- How should post-fix clean-use evidence apply to docs-only project-design
  changes?
