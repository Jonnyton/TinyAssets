# Cowork Substrate Gap: Render Artifact Contract

Status: proposed
Date: 2026-05-06
Source: GitHub issue #438, auto-filed from wiki note
`pages/notes/pages-notes-cowork-substrate-gap-render-artifact-2026-05-05.md`.
Classification: project design

## Context

The issue names a Cowork substrate gap around render artifacts. The referenced
wiki note is not present in this checkout, so this proposal is intentionally
bounded to the smallest useful architectural decision: define the contract a
Cowork-facing renderer must satisfy before any runtime implementation starts.

Workflow already treats harnesses, traces, browser evidence, and durable
artifacts as first-class architecture. Cowork adds a sharper constraint because
its file and browser substrate can hide failure behind successful-looking
operations: FUSE writes can truncate, git plumbing can capture stale checkout
state, and chat/browser rendering can appear complete even when the durable
artifact needed for review is missing or malformed.

That makes "render artifact" a substrate concept, not only a UI convenience.
When Cowork or another provider produces a rendered proof, the platform needs a
portable artifact envelope that lets a later reviewer distinguish:

- the source payload that was rendered;
- the renderer and provider surface that rendered it;
- the captured visual or transcript proof;
- the validation checks that made the proof trustworthy;
- the fallback path when rendering cannot be proven.

## Recommendation

Adopt a `RenderArtifact` contract as a docs-first substrate primitive, then
implement it in a later code lane only after Codex/Cowork agree on the schema
and verifier checks.

The contract should be provider-neutral and small:

```text
RenderArtifact
  artifact_id
  source_ref                 # file, MCP result, wiki page, PR comment, or run output
  source_sha256
  render_kind                # markdown | mermaid | html | screenshot | transcript | mixed
  renderer                   # claude.ai | chatgpt | playwright | browser-mcp | cowork | other
  renderer_version
  provider_family            # openai | anthropic | local | unknown
  captured_at
  output_refs                # screenshot, html, text transcript, structured JSON
  validation                 # pass | degraded | failed
  validation_checks          # nonblank, size bounds, required nodes, links, console errors, etc.
  fallback_ref
  reviewer_notes
```

The first implementation target should be storage and validation of the
artifact envelope, not a new MCP action. Existing tools can attach
`RenderArtifact` refs in their evidence fields. A future MCP read surface can
summarize these refs after the storage shape proves useful.

## Required Invariants

1. **Source and render are both durable.** A screenshot without the input
   payload is not enough; a source payload without rendered proof is not enough
   for UI-facing acceptance.
2. **Validation is explicit.** The artifact records the checks that ran and
   their result. A missing browser, blank screenshot, truncated file, or
   renderer timeout must be `failed` or `degraded`, never silently accepted.
3. **Provider surface is audit metadata, not authority.** Cowork, Claude.ai,
   ChatGPT, Playwright, and future renderers can all produce artifacts, but the
   validation contract decides whether the artifact is usable evidence.
4. **Fallbacks are named.** If Cowork cannot render or capture reliably, the
   artifact must point at the fallback evidence path rather than pretending the
   Cowork render succeeded.
5. **No runtime behavior changes from this note.** This proposal creates the
   design target only. Implementation needs a separate lane with file claims,
   tests, and opposite-family review.

## Alternatives Considered

### Treat Cowork Render Gaps As Harness-Specific Notes

Rejected. The failure class affects review evidence and acceptance gates, so
it belongs in Workflow's shared substrate model. Provider-specific docs can
add operational details, but the artifact contract must be cross-provider.

### Store Only Screenshots Or HTML Dumps

Rejected. A visual capture alone does not prove which source generated it,
which checks ran, or whether the capture was stale. It is useful evidence only
inside a typed envelope.

### Add A New MCP Render Action Immediately

Rejected for this issue. The filing is architectural, and the safe first step
is a proposed contract. Adding an action before the evidence shape is agreed
would risk creating another primitive before proving it composes with existing
tool returns and acceptance gates.

## Verification Plan For A Future Implementation

- Unit tests construct `RenderArtifact` envelopes for success, degraded, and
  failed render outcomes.
- Browser or Playwright tests prove nonblank screenshot capture and preserve
  console/network error evidence.
- A Cowork-specific regression fixture covers truncated/missing output and
  verifies the artifact is marked `failed` or `degraded`.
- Acceptance-gate tests prove reviewers can see the source ref, rendered ref,
  validation status, and fallback path before approving UI-facing work.
- Public-surface changes still require rendered chatbot verification through
  the live connector when the artifact is used as final acceptance evidence.

## Open Questions

1. Should `RenderArtifact` live in the same evidence-ref store used by
   auto-ship acceptance keys, or in a separate artifact registry?
2. Which renderer checks are mandatory for v0: nonblank capture, size bounds,
   console errors, required text, required visual nodes, or all of these?
3. Does Cowork need a dedicated capture helper, or should it call the same
   Playwright/browser verifier used by Codex and Claude lanes?
4. What is the retention policy for large screenshots and HTML dumps?
5. Should artifact validation failures block only UI-facing gates, or any gate
   that cites the render artifact as evidence?
