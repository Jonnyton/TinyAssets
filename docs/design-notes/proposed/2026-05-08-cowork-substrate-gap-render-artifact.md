---
title: Cowork Substrate Gap Render Artifact
date: 2026-05-08
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 438
wiki_source: pages/notes/pages-notes-cowork-substrate-gap-render-artifact-2026-05-05.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#harness-and-coordination
  - PLAN.md#uptime-and-alarm-path
  - .agents/skills/loop-uptime-maintenance/incidents/2026-05-04-cowork-stale-index-regression.md
---

# Cowork Substrate Gap Render Artifact

## 1. Recommendation Summary

Treat Issue #438 as a project-design filing for a Cowork harness substrate
gap, not as a runtime bug. The referenced wiki page is not present in this
checkout and GitHub issue #438 has no additional body or comments, so this
note must not infer a specific Cowork UI failure beyond the title-level signal:
"Cowork substrate gap render artifact."

The smallest useful project change is to define what a future Cowork render
artifact should prove before any implementation work starts. The recommended
shape is a durable evidence packet produced by the Cowork harness whenever a
task depends on rendered output: source inputs, generated file paths, render
command or application route, captured image/PDF/html output, and a short
checker verdict. It should remain an operator/harness artifact in v1, not a
new MCP action or product runtime primitive.

## 2. Problem Boundary

Cowork already has known substrate-specific risk around local filesystem and
rendering surfaces:

- FUSE-backed file operations can make successful-looking writes or commits
  untrustworthy unless a purpose-built helper verifies the result.
- Rendered artifacts are often the only user-visible proof for website,
  document, image, diagram, or generated-report work.
- Chat-only summaries are weak evidence when the user's actual deliverable is
  visual or file-shaped.

The architectural gap is therefore not "add Cowork support" in general. It is:
when Cowork claims a render-dependent task is done, the shared project state
needs a compact, inspectable artifact that lets another provider or the host
verify what was actually rendered without reconstructing Cowork's private UI
session.

## 3. Proposed Artifact Contract

A Cowork render artifact is a directory or markdown packet adjacent to the
task's normal output path. It should contain:

| Field | Purpose |
|---|---|
| `source_request` | The issue, wiki path, STATUS row, or user request that required rendered output. |
| `render_target` | The file, URL, route, app command, or document path that was rendered. |
| `environment` | OS/app/provider surface, date, relevant command versions, and whether FUSE was involved. |
| `inputs` | Minimal list of source files or prompts used to produce the render. |
| `capture` | Screenshot, PDF, HTML export, generated image, or other user-inspectable output. |
| `checks` | Commands or manual checks run against the rendered output. |
| `known_gaps` | What could not be verified from Cowork and must be checked by another provider. |
| `checker_verdict` | Opposite-family or independent checker result when the task requires a gate. |

The packet should be small enough to review in a PR or linked from
`output/`. Large binaries should be referenced by path or release artifact
rather than embedded into markdown.

## 4. Workflow Placement

V1 belongs in harness discipline and task evidence, not product runtime:

1. A Cowork session doing render-dependent work creates or links the packet.
2. The task's final note cites the packet path and the exact rendered target.
3. An opposite-family checker reviews the packet and, when possible, reruns or
   independently opens the rendered target.
4. Only after the checker verdict is recorded may the lane claim rendered
   acceptance.

This composes with the existing cross-provider coordination spine. `STATUS.md`
still owns active claims, GitHub owns branch/PR history, and the render packet
is supporting evidence. The packet is not design truth and does not replace
PLAN.md, AGENTS.md, tests, or final public-surface verification.

## 5. Non-Goals

- Do not add a new public MCP action for "render artifact" in v1.
- Do not add runtime code to Workflow based only on this filing.
- Do not require every Cowork task to produce screenshots; only
  render-dependent tasks need this evidence.
- Do not treat a screenshot as sufficient for public MCP, connector, or
  website acceptance when the project already requires live browser/chatbot
  verification.

## 6. Acceptance Criteria For Future Implementation

A later implementation or process update should be considered complete only
when it can demonstrate:

1. A Cowork render-dependent task produces a packet with the fields above.
2. A checker can locate the packet from the task/PR without private chat
   history.
3. The packet distinguishes generated output from source inputs.
4. The packet records what was actually rendered and when.
5. A missing or stale capture is a visible gate failure, not a silent pass.

## 7. Open Questions

1. Where should the canonical packet live: `output/render-artifacts/<id>/`,
   task-local `output/<request-id>/`, or PR-attached release artifacts?
   Recommendation: start under `output/<request-id>/` for local review and
   promote to release artifacts only when binary size or retention requires it.

2. Should this become a cross-provider AGENTS.md convention or remain
   Cowork-specific? Recommendation: the evidence contract is cross-provider;
   the implementation details are Cowork-specific. If accepted, put the
   shared rule in AGENTS.md and keep Cowork FUSE details in the Cowork-facing
   harness notes.

3. Should render packets be generated by a helper script? Recommendation: yes
   after the first repeated manual packet. The first pass can be a markdown
   template; repeated misses should ratchet into a script or hook.

## References

- GitHub Issue #438: `[WIKI-DESIGN] Cowork substrate gap render artifact`
- `PLAN.md` Scoping Rules
- `PLAN.md` Harness And Coordination
- `PLAN.md` Uptime And Alarm Path
- `.agents/skills/loop-uptime-maintenance/incidents/2026-05-04-cowork-stale-index-regression.md`
