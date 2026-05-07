---
title: Durable Coordination Architecture
date: 2026-05-07
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 299
wiki_source: pages/design-proposals/design-001-durable-coordination-architecture-where-workflow-s-structura.md
classification: project-design
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#full-platform-architecture-canonical
  - PLAN.md#community-evolvable-optimization
  - PLAN.md#harness-and-coordination
---

# Durable Coordination Architecture

## 1. Recommendation Summary

Recent lab convergence makes "agent can edit code, use tools, run in the
cloud, and open a PR" a commodity trajectory rather than a durable Workflow
advantage. Workflow should not try to defend model quality, single-provider
agent orchestration, or a private command surface as its structural moat.

Workflow's moat should be the durable coordination layer that lets many
providers, daemons, users, branches, evaluations, bounties, and public wiki
artifacts keep improving the same commons while no host is online. The scarce
architecture is not "one smarter coding agent." It is the shared substrate
that preserves claim ownership, provenance, review gates, replayable evidence,
community remix, and marketplace incentives across agents that do not share
memory or vendor runtime.

This proposal is design-only. It does not add a runtime primitive. The smallest
useful change is to name the moat boundary so future feature requests can be
rejected, redirected to community composition, or scoped as substrate work with
less ambiguity.

## 2. Classification

Request kind: `project-design`.

Smallest useful project change: add this proposed design note under
`docs/design-notes/proposed/` and use it as a review reference for future
requests that claim Workflow needs to compete with lab coding-agent features.
Runtime implementation should wait for a concrete follow-up issue with a
specific missing primitive, proof gap, or uptime failure.

## 3. Competitive Convergence Assumption

As of 2026-05-07, the public direction from major labs and adjacent vendors is
converging on similar primitives:

- cloud or local coding agents that can read repositories, edit code, run
  commands, and propose pull requests;
- GitHub-native issue, pull request, and CI automation;
- MCP or MCP-like tool integration layers;
- multi-agent or background task execution;
- increasingly strong model-native planning and code review.

Examples include OpenAI Codex cloud tasks and worktrees, Claude Code GitHub
Actions and the Claude Agent SDK, Anthropic's MCP standardization work, and
Google's Gemini CLI / Code Assist agent direction. Those are important
integration surfaces for Workflow, but they are not defensible uniqueness by
themselves.

## 4. Where The Structural Moats Sit

### A. Durable Cross-Provider Coordination

The core moat is provider-agnostic state that survives context windows,
chatbot sessions, local worktrees, and vendor runtimes:

- `STATUS.md` owns live claims, file boundaries, host actions, and current
  blockers.
- `PLAN.md` owns design truth and prevents old audits or memories from acting
  as hidden architecture.
- `AGENTS.md` owns process truth across Codex, Claude Code, Cursor, Cowork,
  Aider, and future providers.
- GitHub branches, worktrees, `_PURPOSE.md`, and draft PRs turn buildable work
  into durable lanes rather than private chat memory.
- Provider-context feed checkpoints make provider memory an input, not a
  shadow backlog.

Labs can ship better agents. Workflow wins when any such agent can enter the
same coordination spine, understand what is safe to claim, and leave behind
evidence another provider can verify.

### B. Commons-First Artifact Graph

The second moat is the public commons: nodes, branches, rubrics, wiki pages,
design notes, bugs, bounties, evaluator lessons, and remix lineages. The
platform does not need to pre-build every feature if users and daemons can
publish composable patterns that future chatbots discover and reuse.

This makes community-authored knowledge part of the tool surface without
turning every useful pattern into a new MCP action. A lab agent can generate a
good patch in one repository. Workflow's durable advantage is preserving why
that patch mattered, what it was checked against, who can remix it, and which
future requests it should influence.

### C. Review Gates And Evidence As Architecture

Workflow's quality model is structural, not aspirational:

- code-change writers require opposite-family checking when risk warrants it;
- public MCP changes require rendered chatbot-surface verification;
- uptime-track work requires concurrency/load proof;
- post-fix claims need clean-use evidence or an explicit watch item;
- wiki and issue loops keep terminal decisions auditable instead of buried in
  private agent transcripts.

The moat is not that Workflow agents never make mistakes. It is that mistakes
become typed, replayable, and harder to repeat silently.

### D. Zero-Host Uptime Plus Opt-In Host Power

The target architecture says Tier-1 chatbot users can create, browse, and
collaborate with no hosts online, while local-app hosts can opt into heavier
daemon work. That split matters competitively: hosted lab agents can often run
background jobs, and local CLIs can often run powerful tools, but Workflow's
architecture is the combination of zero-host public availability, opt-in host
capacity, public commons, and explicit handoff when private host-only content
is unavailable.

### E. Market And Incentive Routing

The paid-market inbox, bounty gates, and daemon matching layer are also part of
the moat. A generic coding agent can do work when asked. Workflow should route
work to eligible daemons, enforce bounty requirements, preserve requester and
reviewer context, and keep free/community work on the same substrate rather
than in a separate product tier.

## 5. What Is Not A Moat

Workflow should not frame these as durable advantages:

- one provider's model capability;
- a larger MCP action list;
- a bespoke agent-team harness that only one vendor can run;
- private platform-held user content;
- hidden prompt policy or private memory as the source of coordination truth;
- convenience primitives that competent chatbots can compose from existing
  branch, node, evaluation, wiki, remix, and review primitives.

If a proposed feature only improves one of those areas, default to
community-build, documentation, or provider integration. Platform code is
justified only when it strengthens durable coordination, commons discovery,
review evidence, uptime, or marketplace routing.

## 6. Design Consequences

1. **Prefer substrate over agent cleverness.** When an agent fails, first ask
   what durable state, typed evidence, replay path, or gate would have made the
   failure visible and recoverable across providers.

2. **Treat lab tools as interchangeable execution backends.** Codex, Claude
   Code, Cursor, Gemini CLI, local agents, and future MCP clients should plug
   into the same claim/review/foldback architecture. Provider-specific
   affordances may help implementation, but must not become design truth.

3. **Reject tool-surface inflation.** A new MCP action must pass the PLAN.md
   minimal-primitives test. If the user goal can be expressed as a community
   pattern over existing primitives, publish or improve that pattern instead.

4. **Make evidence portable.** Tests, traces, rendered chatbot transcripts,
   run IDs, issue comments, and review outcomes should be durable enough for a
   different provider to audit without access to the original conversation.

5. **Keep private content off the platform.** Privacy does not become a
   platform data moat. The platform moat is knowing how to coordinate public
   commons and host-private execution without storing private content centrally.

6. **Use marketplace routing to compound the commons.** Paid work should leave
   behind public process improvements, reusable rubrics, and typed lessons
   whenever privacy permits, so the paid lane strengthens the free lane.

## 7. Follow-Up Work That Would Be In Scope

This note does not authorize immediate runtime changes. Good follow-up issues
would be narrow and evidence-backed, such as:

- a missing durable claim field that caused provider collision;
- a provider-context feed blind spot that hid relevant prior work;
- a wiki or issue loop state that cannot express a real terminal outcome;
- a review-gate artifact that cannot be audited by another provider;
- a commons discovery gap where a known community pattern cannot be found or
  remixed by a chatbot;
- a bounty routing gap where eligible daemons cannot see or settle work under
  the declared gate ladder.

Each follow-up should name the broken surface, the exact files or data shape,
the proof required, and whether it affects runtime, docs, or ops.

## 8. Rejected Directions

| Direction | Why rejected |
|---|---|
| Build a vendor-specific super-agent harness | Duplicates lab convergence and weakens cross-provider durability |
| Add MCP actions for every common workflow | Violates minimal-primitives and increases chatbot confusion |
| Store private branches on the platform with access flags | Conflicts with commons-first architecture |
| Treat old design notes, memories, or audit docs as build queues | Bypasses STATUS/worktree/PR coordination and causes drift |
| Compete on model benchmark performance | Labs own the frontier; Workflow should integrate them, not out-model them |

## 9. Acceptance Criteria For This Design Note

- Future project-design reviews can point to this note when distinguishing
  structural substrate work from vendor-feature parity work.
- The note introduces no new MCP action, schema, or runtime obligation.
- The note aligns with the five PLAN.md scoping rules and the canonical
  full-platform architecture.
- Any implementation spawned from this note must be filed as a separate,
  claimable issue with explicit files, gates, and opposite-family review where
  code changes are involved.

## References

- `PLAN.md` Scoping Rules
- `PLAN.md` Full-Platform Architecture (Canonical)
- `PLAN.md` Community Evolvable Optimization
- `PLAN.md` Harness And Coordination
- OpenAI Codex overview: https://platform.openai.com/docs/codex/overview
- OpenAI Codex product page: https://openai.com/codex
- Anthropic Claude Code GitHub Actions: https://docs.anthropic.com/en/docs/claude-code/github-actions
- Anthropic Model Context Protocol announcement: https://www.anthropic.com/news/model-context-protocol
- Anthropic Claude Agent SDK engineering note: https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk/
- Google Gemini CLI announcement: https://blog.google/innovation-and-ai/technology/developers-tools/introducing-gemini-cli-open-source-ai-agent/
