---
name: idea-refine
description: Refines raw ideas into actionable designs, then gates implementation on an approved design. Use when starting any creative or build work, or when asked to refine, ideate, stress-test, or sharpen an idea before committing it to the project.
---

# Idea Refine

Turn raw ideas into sharp, buildable designs through divergent then convergent
thinking — and do not start building until a design is approved.

## The Hard Gate

```
NO implementation skill, code, scaffolding, or build action
until a design is presented AND the user approves it.
```

This applies to EVERY project regardless of perceived simplicity. "Too simple to
need a design" is exactly where unexamined assumptions waste the most work — the
design can be a few sentences, but it must be presented and approved.

## Philosophy

Simplicity is the ultimate sophistication — push to the simplest version that
still solves the real problem. Start from the user experience, work back to the
tech. Say no to 1,000 things; focus beats breadth. Challenge every assumption
("how it's usually done" is not a reason). YAGNI ruthlessly.

## Process

Adapt to the conversation — this is a dialogue, not a template.

### Phase 1 — Understand & expand (divergent)

1. **Restate the idea** as a crisp "How Might We" problem statement.
2. **Ask sharpening questions — one at a time**, multiple-choice when possible
   (3–5 total): who exactly is this for, what does success look like, real
   constraints, what's been tried, why now. If the user is unavailable, state
   reasonable assumptions and capture open questions in the artifact.
3. **Generate 5–8 variations** using lenses: inversion, constraint-removal,
   audience-shift, combination, simplification (10x simpler), 10x-scale, expert
   lens. Push beyond what was asked. Read [frameworks.md](frameworks.md) and pick
   the lenses that fit — don't run every framework mechanically.

Inside a codebase: scan existing architecture, patterns, and prior art with
Glob/Grep/Read and ground variations in what actually exists. Before refining
details, assess scope: if the request is really multiple independent subsystems,
flag it and help decompose into sub-projects, each getting its own
design→plan→implementation cycle.

### Phase 2 — Evaluate & converge

1. **Cluster** what resonated into 2–3 meaningfully different directions.
2. **Stress-test** each on user value (painkiller or vitamin?), feasibility
   (hardest part?), and differentiation (would anyone switch?). Full rubric in
   [refinement-criteria.md](refinement-criteria.md).
3. **Surface hidden assumptions** — what you're betting is true but haven't
   validated, what could kill it, what you're choosing to ignore and why. Most
   ideation fails here; don't skip it. Be honest, not a yes-machine — push back
   on weak ideas with specificity and kindness.

### Phase 3 — Design & approve

Propose 2–3 approaches with trade-offs, leading with your recommendation. Then
present the design in sections scaled to complexity (a few sentences to ~300
words), asking after each whether it's right: cover architecture, components,
data flow, error handling, testing. Design for isolation — small units, one
clear purpose each, well-defined interfaces, independently testable.

Produce a markdown one-pager: **Problem Statement · Recommended Direction · Key
Assumptions to validate · MVP Scope · Not Doing (and why) · Open Questions.** The
"Not Doing" list is the most valuable part — focus is saying no to good ideas.

### Phase 4 — Spec & handoff

If executing now: write the validated design to a spec doc, self-review with
fresh eyes (placeholder scan, internal consistency, scope, ambiguity — fix
inline), then ask the user to review the written spec before proceeding. Once
approved, hand off to `planning-and-task-breakdown` to create the implementation
plan — that's the only next step. (Heavier spec-driven projects route through the
`openspec` CLI instead.)

If not executing now: save the one-pager under `ideas/` (INBOX.md or
PIPELINE.md) so other sessions can see it.

## Red Flags

20+ shallow variations instead of 5–8 considered ones · skipping "who is this
for" · no assumptions surfaced before committing · yes-machining weak ideas ·
plan with no "Not Doing" list · ignoring codebase constraints · jumping to output
without Phases 1–2 · **starting implementation before design approval.**

## Verification

- [ ] Clear "How Might We" statement; target user + success criteria defined
- [ ] Multiple directions explored, not just the first idea
- [ ] Hidden assumptions listed with validation strategies
- [ ] "Not Doing" list makes trade-offs explicit
- [ ] Output is a concrete artifact, not just conversation
- [ ] User approved the design before any implementation work began
