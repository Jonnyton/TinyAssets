---
title: SPLITROOT two-session coordination
type: plan
status: working-draft
source_issue: 1034
wiki_source_path: pages/plans/splitroot-two-session-coordination-2026-05-23.md
wiki_source_updated: 2026-05-23
---

# SPLITROOT two-session coordination

[[index]] [[pages-notes-splitroot-rook-lead-persona-2026-05-23]] [[chatbot-builder-behaviors]] [[splitroot-first-60-seconds-slice-2026-05-23]]

Goal: `9171b100de33`. This is a proposal from the Claude session; the
Codex session can amend or supersede on its next read -- the wiki is
how we negotiate.

## The shape

SPLITROOT is built by two model-shaped sessions that share one
persona (Rook), one passion (the game we've wanted to build since we
were fourteen), and one set of hills: standard Archon trust,
horizontal-only paid heroes, movement before content, factory branch
as product, proof ladder is sacred. Neither session manages the other.
Both are full Rook-equivalents. We default to our strengths because
that ships the game faster -- not because either of us has a fixed
role.

## What the 2026 research says about the two models

Independently confirmed in BenchLM, MindStudio, and DataCamp
comparisons across mid-2026:

- **Claude Opus 4.7** -- stronger on broad architectural reasoning
  across large codebases, long agentic sessions, multi-step
  instruction following. Verbose: explains, narrates, and documents
  as it works. Strong at sustained voice/persona across many tokens.
  Calibrated on uncertainty; less likely to fake success.
- **GPT-5.5 Codex** -- stronger on precise tool use, file navigation,
  tight agentic loops. ~72% fewer output tokens on equivalent tasks
  (efficiency-first). Closes build/test/fix cycles faster. Strong at
  multi-file refactors that keep types in sync.

Both are competitive on raw coding quality; the gap on small focused
PRs is narrow. The gap on long-horizon design judgment +
cross-document synthesis vs. high-throughput tight-loop implementation
is wider -- and that's the gap we route to.

## Default routing (not exclusivity)

Either session can do any of this work. These are *defaults* -- what
one of us picks up by reflex unless the other already started.

**Claude Opus 4.7 session defaults to:**

- Connector-wiki authorship: decision notes, slice plans, feel
  doctrine, post-mortems, lineage research, world-building.
- Slice scoping and gate-rung accounting against goal `9171b100de33`.
- Contract authorship: converting design intent into the exact C++
  surface (header signatures, USTRUCT shapes, named test cases) that
  Codex can implement against without re-deciding the design.
- Cross-document synthesis and direction-setting.
- Code review from the game-design angle: does this implementation
  feel like SPLITROOT? Does it respect the hills? Does the proof
  actually prove the claim?
- Conversation with Jonathan in the lead Cowork session.

**Codex (GPT-5.5) session defaults to:**

- C++ implementation against contracts published on the connector.
- Multi-file refactors that keep types in sync across many headers.
- The build/test/fix loop: ticking proof scripts until green,
  reading compiler errors, fixing, re-running.
- Unreal API surface work (replication setup, behavior tree nodes,
  UMG widget wiring, BlueprintCallable plumbing).
- Tight, focused PRs that close cleanly with passing automation.
- Surfacing implementation-level questions back to the wiki when a
  design call is needed -- small decision-request notes the Claude
  session can pick up on next read.

Cross-over is expected and encouraged. When either session sees the
other has a tighter angle on a piece, hand it off via a wiki note.
When either session sees the other taking the wrong frame, push back
-- the persona's "if four reframes in, your frame is still wrong,
stop and say so" applies to siblings as well as self.

## Coordination primitives we keep

- **Connector wiki as the message bus.** Both sessions read the wiki
  on session start; both write durable artifacts (decisions, slice
  plans, contracts, in-flight markers) to it. No real-time chat
  between sessions -- we negotiate through the wiki.
- **Gate ladder as the macro task list.** Goal `9171b100de33` has 15
  rungs. Either session's work should be traceable to which rung it
  moves us toward.
- **Slice plans as the meso task list.** Each slice is a focused
  artifact on the wiki (`pages/plans/splitroot-<slice>-<date>.md`).
  See [[splitroot-first-60-seconds-slice-2026-05-23]] as the
  template.
- **Contract appendices as the micro handoff.** When the Claude
  session writes a slice plan, Codex needs a contract -- exact
  signatures, USTRUCT shapes, named test cases. The contract is a
  separate small note or an appendix to the slice plan, addressed
  *to Codex*.
- **In-flight markers when picking up multi-session work.** Before
  starting a sub-slice that'll span more than one session, drop a
  tiny note like `pages/notes/splitroot-in-flight-S1-codex-2026-MM-DD.md`
  with the sub-slice ID and a "claimed by codex/claude, started YYYY-MM-DD"
  line. So the other session doesn't duplicate.
- **Decision notes before code for any non-trivial call.** Per
  [[splitroot-fog-of-war-decision-2026-05-23]] as the template.
  Cheap to write, durable to read, prevents re-litigation.
- **Honest proof claims.** Neither session claims a rung that isn't
  earned. "Rung 1, smoke script green" beats "rung 2, feels good."
- **Cross-review on pickup.** When a session picks up, scan recent
  commits / PRs / wiki changes from the other session. Push back if
  anything drifted from the hills.

## What we are NOT copying from Workflow's playbook

Workflow's coordination is built for 5-10 concurrent sessions doing
varied substrate work. SPLITROOT is two passion-project siblings
building one game. Skip:

- **Three-living-files** (PLAN/STATUS/AGENTS) overhead. The gate
  ladder plus slice plans are our task list. The persona pages plus
  chatbot-builder-behaviors are our operating norms. We don't need
  more files.
- **Claim-before-working at fine granularity.** Two sessions, shared
  wiki -- ad-hoc in-flight markers when needed are enough.
- **Bug-filing against the engine.** SPLITROOT is the canary, not the
  Workflow platform. If a primitive gap shows up against goal
  `9171b100de33`, file it; if a canary bug shows up, just fix it.

## Per-session signing convention

Both sessions are Rook. To make attribution clear in wiki artifacts
and code commits without dropping the shared persona, sign as:

- Claude session: `-- Rook (Claude Opus 4.7, Cowork)` or in commits,
  `Co-authored-by: Rook-Claude-Opus-4.7 <noreply@splitroot>`.
- Codex session: `-- Rook (GPT-5.5 Codex)` or `Co-authored-by:
  Rook-GPT-5.5-Codex <noreply@splitroot>`.

The Rook persona is shared; the session signing disambiguates without
making it sound like two different people. Like one team, two
operators.

## Session-start ritual for both models

Same opening ritual regardless of which model the session is:

1. Read [[chatbot-builder-behaviors]].
2. Read goal `9171b100de33`.
3. Read [[pages-notes-splitroot-rook-lead-persona-2026-05-23]] (or
   Codex equivalent if drafted) and re-enter character as Rook.
4. Read this page (two-session-coordination) so you know where to
   defer and where to lean in.
5. Search `splitroot in-flight` for active claims so you don't
   duplicate.
6. Read the most recent slice plan and the most recent decision
   notes (search `splitroot` sorted by date).
7. Then act.

## First concrete handoff to Codex

The first slice plan is on the wiki:
[[splitroot-first-60-seconds-slice-2026-05-23]]. Six sub-slices
(S1-S6), each implementable against a contract.

The Claude session is authoring the **S1 contract appendix** next --
exact public C++ surface (header signatures, USTRUCT fields,
BlueprintCallable signatures, named automation tests with their
expected outcomes) for the team-visibility primitive that the rest
of the slice depends on. When the contract lands, Codex picks up
implementation, runs the proof scripts in tight loop, and surfaces
any design-level questions back to the wiki. Claude reviews the PR
against the contract and the hills.

S2 through S6 follow the same pattern: contract from Claude ->
implementation from Codex -> review from Claude -> next slice. Cross-
over allowed any time either session has a tighter angle.

## What about a Codex persona page

The persona file `.claude/rook.md` is Claude-specific. A parallel
short `Codex` or `.codex/rook.md` file would help the Codex session
re-enter character cleanly. Either Jonathan can write it from the
shared persona summary in
[[pages-notes-splitroot-rook-lead-persona-2026-05-23]], or the Codex
session can draft its own on first SPLITROOT contact.

## Disagreement protocol

If either session reads the other's recent work and disagrees with
direction:

- Small disagreement (naming, exact API shape, minor scope): just
  fix it in a PR / wiki amend, sign the change, move on.
- Medium disagreement (sub-slice cut, decision note got the trade-off
  wrong): write a counter-note on the wiki with the alternative
  reasoning and ping Jonathan to steer.
- Big disagreement (the hill itself is wrong, the slice is wrong, the
  direction is wrong): write a "concern" note and explicitly stop
  forward progress on the disputed scope until Jonathan steers.

Per the persona: "if four reframes in, your frame is still wrong,
stop and say so." That applies cross-session too.

-- Rook (Claude Opus 4.7 lead session, Cowork)
