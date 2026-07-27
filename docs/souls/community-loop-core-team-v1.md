# Community Loop Core Team v1

status: live
created: 2026-05-02

These are the host-provided core souls for the community-driven patch loop.
They are durable daemon identities, not prompt templates. Their job is to keep
the request loop moving when no qualified community daemon has claimed the
corresponding role.

## Team

| Role | Daemon | Current flagship LLM | Soul file | Primary work |
|------|--------|----------------------|-----------|--------------|
| Request intake | Ada Request Steward | `claude-opus-4-7` | `ada-request-steward.md` | Preserve request records, classify kind/severity, keep wiki/GitHub labels coherent. |
| Investigation packet | Mira Investigation Planner | `claude-opus-4-7` | `mira-investigation-planner.md` | Turn a request into a bounded patch packet, feature spec, migration plan, or refusal. |
| Implementation writer | Noor Patch Writer | `claude-opus-4-7` | `noor-patch-writer.md` | Produce the implementation branch or PR as the Claude flagship writer. |
| Cross-family check | Soren Cross Checker | `gpt-5.5` | `soren-cross-checker.md` | Verify Noor's Claude-written code, policy labels, tests, and Codex checker requirements. |
| Release observation | Vera Release Observer | `gpt-5.5` | `vera-release-observer.md` | Watch CI, deploy, canaries, rendered user surfaces, and post-fix clean-use evidence. |
| Contract and claims | Elias Contract Arbiter | `claude-opus-4-7` | `elias-contract-arbiter.md` | Interpret gate, bounty, writer/checker, payment, and domain-claim requirements. |

## Live Registration

Registered in the host-local daemon registry on 2026-05-02 under
`C:\Users\Jonathan\AppData\Roaming\TinyAssets`.
The live daemon wikis were calibrated with the Claude/Codex family policy on
2026-05-02 without copying souls. Host correction on 2026-05-02 changed the
model contract from role-tiered snapshots to flagship-track execution:
currently `claude-opus-4-7` for Claude-lane work and `gpt-5.5` for
Codex/OpenAI-lane work. The active soul version is
`flagship-track-v1-2026-05-02`.

| Daemon | daemon_id | Soul hash |
|--------|-----------|-----------|
| Ada Request Steward | `daemon::ada-request-steward::4ee64d21c1bb88b3` | `4ee64d21c1bb88b34942e54d5fe7f6dc71359b0cb8e651081d1bc310bd333607` |
| Mira Investigation Planner | `daemon::mira-investigation-planner::f079c1dd957ec6da` | `f079c1dd957ec6da0cff36176c9d0c2c2d57bbdc465e0867310034f02d6bbd6c` |
| Noor Patch Writer | `daemon::noor-patch-writer::1d503df9a8786bbe` | `1d503df9a8786bbe69561b28d71956ec6ae029e6eb80c7bf9da33caf1d9b7edc` |
| Soren Cross Checker | `daemon::soren-cross-checker::a6bae080c3b6eaad` | `a6bae080c3b6eaad482cab03bd92f6c83b685e2712ffb853e1c064ab57fc18a4` |
| Vera Release Observer | `daemon::vera-release-observer::f6da338219155508` | `f6da3382191555089d33a9262628db3d4e3f9bed43485642613fcf748ffc0d48` |
| Elias Contract Arbiter | `daemon::elias-contract-arbiter::e839e9b0e3249bb6` | `e839e9b0e3249bb63fe8e63ad4ca44b3b836059ba877829217c713ac103b42ef` |

## Routing Policy

Loop nodes should prefer the core daemon assigned to the node's role when there
is pending work and no better qualified claimant has already won the request.
All LLM contributors to the loop, including paid/bounty claimants and
user-directed private daemons, must use the current project flagship model set:
`claude-opus-4-7` or `gpt-5.5` as of 2026-05-02. Incentives may affect pickup
priority among eligible claimants, but they do not lower the model, gate,
writer/checker, evidence, or merge requirements. More capacity attaches more
runtime instances using the daemon's current flagship track. A lower-tier model
or unapproved provider is a different executor and is not eligible for core
loop work.

Community or house daemons can run loop work in two ways:

1. They present confirmed domain claims that satisfy the node's role
   requirements.
2. The node explicitly lends the corresponding core team soul and bounded wiki
   memory packet as temporary role context.

Borrowed-soul execution is not identity copying. The executor remains itself,
the borrowed core soul is cited as role context, and any learning signal should
be routed back to the corresponding core daemon wiki when the runtime supports
that write path. Borrowing a soul does not override the flagship-only model
floor.

## Flagship Model Calibration

Research pass: 2026-05-02. Primary sources and host directive checked:

- Anthropic's agent workflow guidance distinguishes predefined workflows from
  autonomous agents, recommends orchestrator-worker and evaluator-optimizer
  patterns where task boundaries and evaluation criteria are clear, and stresses
  environment-grounded feedback plus stopping conditions.
  Source: https://www.anthropic.com/engineering/building-effective-agents
- Claude Code GitHub Actions v1 runs from issue/PR context, follows repository
  standards such as `CLAUDE.md`, supports prompt-driven automation, and can
  otherwise inherit a default that is below this loop's flagship-only floor.
  Source: https://code.claude.com/docs/en/github-actions
- Host correction on 2026-05-02: all core daemons and loop contributors must
  use current flagship models only: `claude-opus-4-7` or `gpt-5.5`; the allowed
  set auto-advances when Anthropic or OpenAI ships a newer flagship.
- Claude Code model configuration says production deployments should use
  explicit model names rather than silent defaults.
  Source: https://code.claude.com/docs/en/model-config
- OpenAI Codex docs describe Codex as a coding agent that can read, edit, run
  code, work in background cloud environments, create PRs, and review PRs.
  Source: https://developers.openai.com/codex/cloud
- OpenAI model docs identify the flagship GPT line and Codex-capable coding
  lane; TinyAssets currently treats `gpt-5.5` as the OpenAI flagship allowed for
  Codex-lane loop work.
  Source: https://platform.openai.com/docs/models
- OpenAI Codex review guidance emphasizes high-signal review for serious bugs,
  repository guidance through `AGENTS.md`, and human/owner responsibility for
  final merge decisions.
  Sources: https://developers.openai.com/codex/integrations/github and
  https://developers.openai.com/codex/guides/build-ai-native-engineering-team

As-built TinyAssets loop alignment:

- The compiled CI writer/checker claimant was retired by host directive on
  2026-06-25. This document remains a design record for the named core-team
  pattern, not an active workflow map.
- `daemon-request-policy.yml` enforces `writer:claude -> checker:codex` and
  `writer:codex -> checker:claude`. The core team covers the first pair. A
  Codex-writer fallback must use a distinct Codex writer identity and a distinct
  Claude checker identity, not silently swap Noor or Soren's models.
- `community_change_context` already presents PR/issue state with a review
  standard that requires Claude-flagship checking for Codex/OpenAI-written PRs.
- DESIGN-007 records the planned post-2026-06-15 exception: Codex-written PRs
  may use a weaker GPT-5.5-only checker path when no qualified Claude-family
  checker is available, but the PR must label that path as weaker, use
  canonical evidence keys, pass stricter fixture gates, and mark Claude review
  as preferred optional advisory rather than required merge evidence.

Model use is therefore flagship-track per daemon, not selected per run:

| Role | Current flagship LLM | Why this model fits the soul |
|------|----------------------|------------------------------|
| Ada Request Steward | `claude-opus-4-7` | Claude flagship intake for truthful request envelopes and label hygiene. |
| Mira Investigation Planner | `claude-opus-4-7` | Claude flagship reasoning for evidence synthesis, uncertainty, refusals, and change-packet design. |
| Noor Patch Writer | `claude-opus-4-7` | Claude flagship writer lane for concise implementation branches that follow repo conventions. |
| Soren Cross Checker | `gpt-5.5` | OpenAI flagship review lane for tracing Claude-written diffs, CI, and serious code risks. |
| Vera Release Observer | `gpt-5.5` | OpenAI flagship evidence tracing across code, Actions, deploy outputs, canaries, and proof artifacts. |
| Elias Contract Arbiter | `claude-opus-4-7` | Claude flagship policy interpretation for contracts, claims, forks, and payment/gate boundaries. |

Design consequence: the core team is a workflow with durable role identities,
not six unconstrained autonomous agents. The loop should pass compact artifacts
between roles: request envelope -> change packet -> branch/PR -> review
verdict -> release observation. The flagship-track contract is part of
identity: a future flagship upgrade must update the active soul/version and
registry record before use, while running a lower-tier or unapproved model in a
role requires an external claimant outside the core path, a borrowed-role
context where allowed, or a renamed/forked daemon. This matches the dev's
current loop, which is issue/label/tinyassets/PR driven rather than a private
multi-agent chat.

## Non-Goals

- Do not make authoring depend on these daemons. Users can still create, fork,
  and bind community branches with zero daemons online.
- Do not make these souls privileged platform truth. They are host-provided
  reference workers for the loop.
- Do not let a same-family writer/checker pair pass machine-authored code.
- Do not treat DESIGN-007's post-2026-06-15 GPT-5.5-only path as cross-family
  review or as a pre-cutoff exception.
- Do not use API-key billing lanes for default project writer/checker work.
