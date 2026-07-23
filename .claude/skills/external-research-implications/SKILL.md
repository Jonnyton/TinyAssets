---
name: external-research-implications
description: Research an external project, repository, paper, article, or codebase and derive TinyAssets implications, plans, and integration slices. Use when the user points an agent at outside work and asks what we should learn, copy, avoid, integrate, or build from it.
---

# External Research Implications

## Overview

Turn outside work into durable TinyAssets learning. Use this when the user points
at a project, repo, research paper, article, architecture, product, benchmark,
or competitor and asks for implications, integration, comparison, or a plan.

The output is not a generic summary. The job is to understand the outside work,
map it against TinyAssets, decide what matters for our users, and leave behind a
reusable plan or artifact that future sessions can act on.

## Trigger Examples

- "Study this repo and tell us what it means for TinyAssets."
- "Read this paper and build an implementation plan."
- "Compare our architecture to this project."
- "What should we learn from this?"
- "Turn this research into steps toward integration."
- "Anytime I point an agent at a project/research paper/repo."
- "Find the most important frontier project for our direction."
- "Scan for paradigm shifts and tell us what to align with early."

## Core Stance

TinyAssets users are people with MCP-connected chatbots. They should be able to
steer, redesign, fork, evolve, and improve branches through conversation. The
project should become more community-evolvable and self-improving, not more
dependent on maintainers or local research harnesses.

When importing outside ideas:

- adapt them into TinyAssets primitives;
- preserve MCP/chatbot-first user surfaces;
- preserve community remix, lineage, attribution, and branch evolution;
- preserve uptime with zero hosts online where applicable;
- reject sidecars that bypass TinyAssets' control plane, privacy model,
  evaluator evidence, host pool, or provenance chain.

## TinyAssets

### 1. Orient And Claim

1. Read `STATUS.md` first.
2. Run `python scripts/claim_check.py --provider <provider>`.
3. Run `python scripts/provider_context_feed.py --provider <provider> --phase claim`
   so prior-provider memories, idea-feed items, pending implications, and
   automation notes are visible before scoping.
4. If you will write a durable artifact, run `claim_check.py --check-files`.
5. Claim a narrow write-set in `STATUS.md` before editing.
6. Load `PLAN.md` sections relevant to the study. Full-load only when the
   outside work could affect platform architecture or product direction.

### 2. Canonicalize The Outside Source

Find the authoritative source, not just the first search hit.

For a repo:

- identify canonical URL, owner, default branch, latest commit, license,
  language/runtime, and last push date;
- clone read-only into a temp directory or inspect via official source APIs;
- never vendor code as part of the study unless the user explicitly asks.

For a paper:

- find the paper page, PDF, repo, authors, date/version, and related artifacts;
- prefer primary sources: arXiv, publisher, official project page, official
  GitHub/Hugging Face repos.

Use web research when freshness matters, which is almost always true for
external projects, papers, products, standards, and active repos.

### 3. Map Both Systems

Map the outside system module by module:

- entrypoints and user surface;
- execution loop;
- storage/state;
- evaluation/metrics;
- memory/retrieval;
- provider/model usage;
- concurrency/distribution;
- safety/sandbox/privacy;
- artifacts and provenance;
- tests, demos, and operational gaps.

Map the relevant TinyAssets modules the same way:

- use `rg --files`, AST summaries, tests, and targeted `docview.py`;
- connect claims to `PLAN.md`, design notes, and current code;
- note where TinyAssets already has a stronger primitive;
- note where the outside system exposes a real gap.

### 4. Research Adjacent Work

Look beyond the named source when it improves judgment:

- sibling repos and implementations;
- cited papers;
- independent replications or critiques;
- current best practice for the pattern;
- security/safety warnings;
- licensing and adoption constraints.

Separate evidence from inference. Cite sources in the durable artifact.

### 5. Frontier Radar Mode

Use this mode when the user asks which outside project, paper, repo, or
movement matters most, rather than naming a single source.

When the user asks for another, next, or second project/repo, first scan
existing `docs/audits/`, `ideas/PIPELINE.md`, and active `STATUS.md` rows so
the result does not simply rediscover an already-promoted concept. A repeated
concept is acceptable only when the new source materially changes the
implementation path; otherwise choose a distinct frontier axis and state how it
relates to prior picks.

Scan for frontier candidates across primary sources, recent papers, official
repos, and reputable technical writeups. Do not optimize for launch noise,
stars, funding, or flashy demos. Rank candidates by:

- paradigm shift: does it change the unit of design or improvement?
- TinyAssets fit: does it map to MCP users, branches, evaluators, host capacity,
  provenance, privacy, and community evolution?
- implementation gravity: is the industry likely to rediscover this direction
  within 6 months to 3 years?
- evidence quality: primary paper/repo, benchmark signal, reproducibility,
  and visible limitations;
- integration leverage: can TinyAssets adopt the underlying primitive without
  copying a sidecar platform?
- anti-hype discipline: penalize projects that are only wrappers, demos,
  ungrounded agent claims, or local-only workflows with no durable state.

Expected output:

- short candidate table;
- one chosen frontier bet;
- why it beats the runner-up choices;
- what to adopt, adapt, avoid, defer, and watch;
- first TinyAssets-native integration slice;
- what this should change in this skill or project docs.

### 6. Derive TinyAssets Implications

Classify each implication:

- `Adopt`: fits TinyAssets and should become a native primitive.
- `Adapt`: useful idea, but needs TinyAssets-specific shape.
- `Avoid`: tempting but conflicts with users, uptime, privacy, or architecture.
- `Defer`: good idea, wrong time or blocked by other work.
- `Watch`: promising but too unproven or unstable.

For each material implication, include:

- why it matters for MCP-chatbot users;
- which TinyAssets primitive it maps to;
- smallest credible integration slice;
- risks and failure modes;
- verification needed;
- whether PLAN.md or STATUS.md must change.

When the outside work is a trace, data-flywheel, observability, or training-data
project, also evaluate:

- capture surfaces and supported agents/clients;
- schema shape for steps, tools, observations, outcomes, artifacts, and cost;
- privacy, redaction, review, consent, and export gates;
- attribution links from trace to commit, branch, node, evaluator, or user;
- whether the data should remain private, become a community artifact, or feed
  evaluator/training datasets.

Never recommend automatic public trace upload as a first slice. Start with
private-by-default capture and explicit review.

### 7. Leave Durable Artifacts

Default artifact location:

`docs/audits/YYYY-MM-DD-<source>-architecture-implications.md`

Use a design note instead when the user accepts a direction:

`docs/design-notes/YYYY-MM-DD-<topic>.md`

If implementation should follow, create a narrow `STATUS.md` work row with
specific files and dependencies. Do not bury active work only in the report.

When the concept is approved or likely to become implementation, land the
implication into the repo's worktree discipline as a worktree-ready handoff.
The Claude Code team may continue improving the automation around worktrees,
but this skill must leave enough structure for any provider to pick it up.

Add a `Worktree Landing Packet` to the report and mirror its essentials into
`STATUS.md` or `ideas/PIPELINE.md`. Include:

- proposed branch name, using the provider convention when known
  (`codex/<slug>`, `claude/<slug>`, or the eventual team convention);
- proposed worktree directory, normally `../wf-<slug>` unless the local
  worktree manager says otherwise;
- relevant `PLAN.md` modules reviewed or needing review before build;
- idea feed refs from `ideas/INBOX.md`, if loose captured ideas should be
  remembered at the bottom of the lane;
- GitHub fold-back object: draft PR while blocked/reviewing, ready PR only
  after verification gates pass;
- prior-provider memory refs from the session that produced the finding or
  preceding work, such as `.claude/agent-memory/<role>/<file>.md`;
- related implication refs that must be cross-considered during planning,
  build, and review;
- base branch or dependency, including any review artifact that must land
  first;
- exact write-set for the `STATUS.md` Files cell;
- read dependencies that should be rechecked after upstream work lands;
- first implementation slice small enough to commit independently;
- expected verification gates before commit, before push, and before live
  acceptance;
- fold-back path: PR/merge target, STATUS row retirement, and follow-up row or
  `ideas/PIPELINE.md` update if work remains.

If the cross-provider review gate blocks build work, still land the
implementation lane into the git/worktree discipline immediately. The review
gate is part of the lane, not a reason to keep the lane invisible.

Required shape for an unreviewed but implementation-bound concept:

- create the opposite-provider review row as claimable work;
- create or reserve the implementation branch/worktree lane with status
  `pending` and a Depends cell naming the review artifact/verdict;
- do not advance implementation beyond research/design stubs until the review
  verdict is `approve` or `adapt`;
- if worktree tooling exists and the repo is in a safe state, materialize the
  branch/worktree immediately with only the research artifact, queue metadata,
  and blocked handoff; otherwise reserve it in `STATUS.md` and the report so
  the worktree manager can materialize it later;
- make the reviewer responsible for unblocking, adapting, deferring, or
  rejecting the implementation lane in their review artifact and shared queue
  edits.

If the user explicitly approves the direction before review, record the
approval in `PLAN.md` or a design note as appropriate, but still keep runtime,
push, live rollout, and acceptance-test advancement blocked until the
opposite-provider review lands.

### 8. Require Cross-Provider Research Review

If a finding may lead to implementation, git push, live rollout, or acceptance
testing, it needs an independent research review from a different provider
before build work starts.

- Record the `initial_provider` in the durable artifact.
- If Codex made the initial finding, Claude must research and review it.
- If Claude made the initial finding, Codex must research and review it.
- If another provider made the initial finding, name a different reviewer
  provider explicitly in `STATUS.md`; prefer the Codex/Claude pair when
  available.
- The reviewer must re-check primary sources, inspect the relevant TinyAssets
  context, and leave a durable review artifact with a verdict:
  `approve`, `adapt`, `defer`, or `reject`.
- Any build/push/live/test work row must depend on the review artifact.

This is a research gate, not a rubber stamp. The reviewer should be able to
change the plan before implementation starts.

### 9. Create A Pickup Packet

A study is not complete until another provider can pick up the next step with
no chat history.

Before creating the pickup packet, run
`python scripts/provider_context_feed.py --provider <provider> --phase plan`.
Before writing a review artifact, run the same command with `--phase review`.
Before folding the concept into a PR/worktree lane, run it with
`--phase foldback`. The feed is not build authority; it is the mandatory scan
that prevents provider memories, loose ideas, or related implication lanes from
being missed.

For every `Adopt` or `Adapt` concept, create a pickup packet in the report and
mirror it into the right shared queue:

- `STATUS.md` Work row when there is an actionable next step now;
- `ideas/PIPELINE.md` Active Promotions row when the concept should not be
  forgotten but still needs review, design, or sizing;
- `docs/exec-plans/active/` when delivery needs multiple checkpoints;
- `PLAN.md` or a design note only when design truth has been accepted.

The pickup packet records:

- concept name;
- source artifact and source URLs;
- initial provider and required reviewer provider;
- affected domains and "applies when touching" cues;
- next home (`STATUS.md`, `ideas/PIPELINE.md`, design note, or exec plan);
- exact next action;
- file write boundary;
- blockers and dependencies;
- verification or exit check;
- whether build work is blocked on cross-provider review.
- worktree landing packet: branch, worktree dir, base/dependency, write-set,
  first slice, verification gates, GitHub PR/fold-back path, PLAN module refs,
  memory refs, related implication refs, and optional bottom-of-lane idea feed
  refs.

Do not leave a concept only in a report or final chat. If no pickup entry is
created, say why in the report.

For cross-cutting concepts, put the "applies when touching" cues in the
`STATUS.md` or `ideas/PIPELINE.md` row text. A future builder working on a
different task should be able to notice the implication during the
provider-session cross-implication scan before coding.

### 10. Self-Iterate The Skill

At the end of any substantial external-research implications study, ask:

- Did this reveal a repeatable step future agents should perform?
- Did the agent miss a source type, artifact type, or verification step?
- Did the user explicitly say "make this process repeatable"?

If yes, update this skill immediately, then run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync-skills.ps1
python scripts/validate_skills.py
git diff --check -- .agents/skills .claude/skills
```

## Output Shape

For a substantial study, produce:

1. executive judgment;
2. source freshness stamp;
3. module-by-module outside-system map;
4. module-by-module TinyAssets comparison;
5. adjacent research summary;
6. adopted/adapted/avoided/deferred implications;
7. recommended implementation roadmap;
8. cross-provider review gate;
9. pickup packet;
10. worktree landing packet;
11. open questions and verification gaps.

For a quick user-facing answer, summarize only the highest-level implications
and link to the durable artifact.

## Verification

- `STATUS.md` reflects any live work or new host decision.
- External source URL, commit/version/date, and license are recorded.
- Claims that depend on current outside facts are web-verified.
- Large local docs were read with `scripts/docview.py`.
- The output distinguishes evidence from inference.
- Suggested integration slices preserve MCP-chatbot-first users.
- Suggested integration slices preserve community evolvability.
- Findings that could lead to build work have an opposite-provider review gate.
- Adopt/adapt concepts have a pickup packet in `STATUS.md` or `ideas/PIPELINE.md`.
- Cross-cutting findings include "applies when touching" cues for future builders.
- Skill changes, if any, were synced to provider mirrors and validated.
