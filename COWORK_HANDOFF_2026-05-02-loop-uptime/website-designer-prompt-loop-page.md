# /loop page — designer prompt

Audience: a designer/dev redesigning `tinyassets.io/loop`. They have access to the
Workflow MCP (`https://tinyassets.io/mcp`), the GitHub repo (`Jonnyton/Workflow`),
and the existing SvelteKit site source (`WebSite/site/src/`).

## Goal of the page

Let a visitor — enthusiast dev OR creative-curious-non-dev — walk through the
loop AS IT IS RIGHT NOW, see real evidence, and feel the system reasoning out
loud. The page should turn "the loop ran" into "I understand what the loop just
decided, and why, and I can poke at it." Successful outcome: a visitor leaves
either (a) ready to file their first patch idea, or (b) able to explain to
someone else what the loop just did and why it mattered.

## What's broken with the current page

The hero is "watch live patch traffic" with six stage cards waiting for events.
When the MCP feed is empty (most of the time today, since the loop only fires on
real user filings), all six say "Waiting for live event" and the page reads dead.
The stage names (Intake / Investigation / Gate / Coding / Release / Watch) are
the loop's TOPOLOGY, not its STORY. Nobody lands here wanting to memorize stage
names; they want to feel the system move and read its reasoning.

Three concrete failure modes the redesign must fix:

1. **Dead-feed default state.** The page must always show real data, even when
   no event fired in the last hour. Solution: pull the most recent durable
   completed run from the connector and render it as the headline. Never empty.
2. **No interactive entry point.** Visitor can only watch. Should be able to
   click into a stage, swap which run is being walked, peek the actual JSON,
   and (if they want) file their own patch idea from the page.
3. **No personality.** The loop has a voice — its `coding_packet.reason_for_downgrade`
   field literally says things like *"BUG-045 states this node cannot attach/invoke
   the child packet from here, so no dispatch/execution claim is allowed."* That's
   the system narrating its own constraints in plain English. Surface those
   quotes prominently. Let the loop speak.

## What's available as durable, page-friendly data

Everything below is reachable today via the Workflow MCP and persists
indefinitely. The page should READ these surfaces, not depend on real-time
events:

| Surface | Returns | Use it for |
|---|---|---|
| `extensions action=list_runs limit=10` | Last 10 runs ever, persists forever | "Recent runs" picker |
| `extensions action=get_run run_id=...` | Full run state for any historical run | Stage walk-through data |
| `extensions action=get_node_output run_id=... node_id=...` | Coding packet, gate verdicts, evidence | The loop's "voice" quotes |
| `wiki action=list category=bugs` | All filed bugs persist forever | "What users have filed" feed |
| `wiki action=list category=feature-requests` | Same, for feature requests | Same |
| `universe action=queue_list` | BranchTask queue with status/lease/ages | Current activity health |
| `universe action=inspect` | Daemon liveness, last activity timestamp | Footer health badge |
| GitHub PR / commit history (Octokit) | Substrate evolution over time | "Substrate vs content" timeline |
| `.agents/activity.log` (raw text) | Cross-AI coordination timeline | "How a recent fix happened" |

Notice: every one of these is durable + categorizable. The page never needs
editing when the loop adds a new field, runs a new bug, or evolves its
prompts — the page just renders whatever the live state is, with explanations
attached to each field.

## Concrete examples to feature

These are real runs that just happened today (2026-05-03). The redesign should
use them as the default-state examples until newer ones land:

- **BUG-052** (`pages/bugs/bug-052-wiki-bug-list-contains-duplicate-stale-bug-pages...`)
  — naive user filed a wiki-cleanup request through ChatGPT. Loop reasoned about
  it, drafted a candidate patch packet, and **REJECTED its own candidate**
  because no terminal runtime evidence was attached. Lab log says verbatim:
  *"Reject the candidate for KEEP because the score remains 2/10 and there is
  still no terminal run evidence."* This is the loop being honest about its
  limits — exactly the personality the page should surface.
- **BUG-049, BUG-050, BUG-051** — earlier runs in the same evolution arc. Each
  produced a structured `coding_packet` with `parent_invocation_status: PROVEN`,
  `child_keep_reject_decision: REVIEW_READY`, and `attached_child_evidence_handle`
  pointing at a real child run. Pick any one for the default headline; let the
  visitor swap.

## Layout proposal (designer can take or leave)

**Hero strip:** "The loop just decided this →" plus a one-sentence verdict
pulled live from the most recent successful run. Example: *"BUG-052 → REJECT
(score 2/10) — loop drafted a wiki-cleanup patch but refused KEEP without
terminal runtime evidence."* Real text from the run. Updates whenever a new run
completes.

**Stage walkthrough:** Same six stages as today, but each card is now POPULATED
from the headline run. Click "Stage 4 · Coding" → see the actual `coding_packet`
JSON for THAT run. Click "Stage 5 · Release" → see the gate verdict + reason
text. The stage rail stops being a topology diagram and becomes an interactive
replay.

**Run picker:** "Walk a different run" dropdown listing the last 10. Always
populated because runs persist. Filterable by outcome (succeeded / failed /
KEEP-readied / rejected once we have those).

**Evidence chain breadcrumb:** wiki bug → BranchTask → parent run → child run
→ coding packet → release gate → (eventually) PR → commit → observation. Each
crumb is a real link to a real artifact; click into any of them to see the
underlying data. This is the "make real breakthroughs in understanding" entry
for an enthusiast dev.

**File-a-bug widget:** Right at the bottom of the rail. Tiny form: title +
observed + expected. Submits via `wiki action=file_bug`. Visitor watches their
own bug appear in the queue, get claimed, run through the stages, produce a
coding_packet — all on the same page. Highest-engagement interaction; turns the
visitor from spectator into participant.

  - Note for safety: this is the highest-leverage idea AND the highest
    contamination risk. If we ship it, throttle to 1 filing per visitor session,
    require a "this is a real idea, not a test" confirm, and clearly label
    test/probe filings so the loop knows to discount them.

**Known-unknowns shelf:** "Where the loop is confused right now." Lists open
BUG-* tagged loop-content or substrate-self-awareness, with one-sentence
descriptions. Inexperienced visitor reads "loop misinterprets its own successful
invocation" and goes "oh I have an idea about that" → file a follow-up.

**Cross-AI timeline:** "How today's fix happened" — real timeline pulled from
`.agents/activity.log` showing wiki filing → Cowork chat → Codex SSH → PR →
merge → deploy → first verified live, with AI labels on each touch. Today's
BUG-009 RCA (closed by PRs #196 + #205) is a perfect example: 4 hours, 6 PRs,
4 different AIs collaborating, all timestamped publicly. Shows the multi-agent
coordination the system actually runs on.

## Layered disclosure (one page, three depths)

- **Surface layer** — plain-English summaries that an inexperienced visitor
  reads and understands the gist ("the loop decided to hold this patch because
  it couldn't prove the child invocation worked").
- **Click-through layer** — tap the card, see the actual JSON + the rationale
  verbatim. Enthusiast sees the contract.
- **Source layer** — link to the GitHub PR + commit + activity log entry. Power
  user follows it all the way to ground truth.

Same data, three depths. Inexperienced visitors don't get scared off by JSON;
enthusiasts don't get bored by hand-waving.

## What makes this page durable (no constant editing)

Page renders STRUCTURES, not STRINGS. As the loop adds new coding_packet
fields (`automation_claim_status`, `parent_invocation_status`, eventually
`auto_ship_outcome`, `rubric_violations`, etc.), the page just shows them with
a "what's this?" tooltip pulled from the field's docstring or a doc reference.
Editing the page is reserved for adding new VIEWS or new INTERACTIONS, NOT for
keeping content in sync with loop evolution. That's the discipline that keeps
the page useful long-term without becoming a maintenance burden.

## Personality / voice direction

Pull verbatim quotes from:
- `coding_packet.reason_for_downgrade`
- `release_gate_result` reason text
- `evolution_notes`
- `lab_log_entry` (when present)

Render as quotes, attributed to the loop. Example treatment:

> "Reject the candidate for KEEP because the score remains 2/10 and there is
> still no terminal run evidence."
> — change_loop_v1, BUG-052 lab log, 2026-05-03

That voice IS the page's personality. Don't paraphrase. Don't decorate. The
loop sounds like a careful engineer thinking out loud. Let it.

## What to avoid

- Stage cards with placeholder text. If a real run isn't available, swap to an
  older one; don't show "waiting for event" prose.
- Loop topology as the navigation primary. Stages are an implementation detail;
  evidence chains are the user-meaningful unit.
- Marketing-speak in the loop's voice. Pull the loop's words verbatim. Add your
  own framing in the surrounding chrome.
- A static demo ("watch this video of the loop"). If the page can't pull live
  data on every visit, it doesn't tell the truth.
- Anything that requires constant content updates as the loop evolves. Render
  schemas + examples from the connector; never hard-code copy that names a
  specific run, packet field, or stage outcome.

## Acceptance criteria for the redesign

A visitor on the page should be able to, in 60 seconds:
1. Read one verbatim sentence from the loop about a real recent decision.
2. Click into one stage of one run and see real data (not lorem-ipsum).
3. Click into the GitHub PR or commit that landed the substrate change being
   discussed.
4. (If file-a-bug ships) submit a one-line patch idea from the page and see
   their request appear in the queue within 60 seconds.

If all four work on a fresh load with no real events firing during the visit,
the page is "done well." If any of the four fail, the page is incomplete.

## Source notes

This prompt synthesizes the dev-partner chat about /loop redesign with real
data from the Workflow loop's first end-to-end day (2026-05-02 through
2026-05-03). The runs and bugs named here are real artifacts in the repo +
connector as of writing.
