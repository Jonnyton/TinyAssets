---
title: Auto Hydrate Then Invoke V1
date: 2026-05-08
author: codex-wiki-docs
status: proposed
request_id: WIKI-DOCS
github_issue: 684
wiki_source: pages/concepts/auto-hydrate-then-invoke-v1.md
scope: design-only; no runtime code in this branch
cohit_check:
  command: python scripts/check_primitive_exists.py action auto_hydrate_then_invoke_v1
  result: clean on 2026-05-08
builds_on:
  - PLAN.md#scoping-rules
  - PLAN.md#community-evolvable-optimization
  - PLAN.md#api-and-mcp-interface
---

# Auto Hydrate Then Invoke V1

## 1. Classification

Issue #684 is a docs/ops concept filing for a Stage A bridge convention:
before the community loop invokes a user-authored classifier, the loop should
hydrate the classifier's declared `source_bundle_refs` into a bounded source
bundle. This is not a reproduced runtime bug, and it should not add a new MCP
action in v1. The smallest useful project change is to preserve the convention
as a proposed design note for future loop implementation.

## 2. Recommendation

Adopt `auto_hydrate_then_invoke_v1` as an internal loop convention, not as a
public primitive. A classifier invocation that carries `source_bundle_refs`
means:

1. Resolve each reference through the existing repository/wiki/artifact
   readers.
2. Build a deterministic `source_bundle` with snippets, provenance, and
   truncation metadata.
3. Invoke the user-authored classifier with both its original input and the
   hydrated bundle.
4. Record the exact refs, resolver version, and truncation decisions beside
   the classifier result.

The loop owns hydration because it is the actor that has repository context and
can apply shared size, provenance, and safety rules consistently. The
classifier remains authored by the community and should stay a pure decision
function over explicit inputs.

## 3. Contract Shape

The bridge contract should be explicit enough for user-authored classifiers to
be portable across daemon hosts:

```yaml
classifier:
  id: stale-caution-language-v1
  authored_by: community
  input_schema: patch_request_v1
  source_bundle_refs:
    - kind: wiki_page
      path: pages/bugs/bug-051-stale-caution-language.md
      purpose: root_cause_context
    - kind: repo_file
      path: docs/ops/auto-fix-runbook.md
      purpose: release_gate_context
    - kind: issue
      number: 684
      purpose: request_context
```

Hydrated invocation shape:

```json
{
  "classifier_id": "stale-caution-language-v1",
  "input": {
    "request_id": "WIKI-DOCS",
    "request_kind": "docs-ops"
  },
  "source_bundle": {
    "resolver_version": "auto_hydrate_then_invoke_v1",
    "items": [
      {
        "ref": {"kind": "repo_file", "path": "docs/ops/auto-fix-runbook.md"},
        "status": "hydrated",
        "content_type": "text/markdown",
        "excerpt": "...",
        "truncated": true,
        "sha": "optional commit or artifact id"
      }
    ]
  }
}
```

Reference kinds should start narrow: `repo_file`, `wiki_page`, `issue`,
`issue_comment`, and `artifact`. Each resolver must produce provenance and a
bounded excerpt. Missing or unreadable refs are classifier inputs, not hidden
exceptions, unless the classifier declares a ref as required.

## 4. Guardrails

- Hydration is read-only. It must not edit wiki pages, repository files,
  issues, or artifacts.
- Hydration must be deterministic for a given ref set, resolver version, and
  commit/artifact state.
- Bundle limits are part of the contract: item count, bytes per item, total
  bytes, and truncation marker format.
- Private host-local paths are not valid Stage A refs. Future local-app support
  needs a separate capability-tier rule before private source hydration exists.
- User-authored classifier output must include the hydrated bundle metadata or
  a digest of it, so reviews can tell what context was actually considered.
- A classifier that needs source context must declare refs up front. It should
  not ask the language model to browse or infer missing context inside the
  classifier prompt.

These guardrails keep the bridge aligned with `PLAN.md` scoping rules:
hydration improves composition reliability without expanding the public MCP
tool surface or turning a community-authored classifier into platform policy.

## 5. Implementation Sketch

Future implementation can land in three small steps:

1. Add a resolver helper that accepts `source_bundle_refs` and returns a
   typed, bounded `source_bundle`.
2. Add classifier-runner tests for hydrated, missing, unreadable, and truncated
   refs.
3. Wire the community loop's classifier invocation path to call the resolver
   before invoking user-authored classifiers.

Acceptance evidence should include a fixture where a classifier changes result
only after a wiki or repo ref is hydrated, plus a fixture proving missing refs
are visible in the classifier input rather than silently ignored.

## 6. Open Questions

1. Should `wiki_page` resolve against the live wiki droplet, a checked-out wiki
   mirror, or the GitHub issue body generated by wiki-change-sync? Stage A can
   support one resolver first, but the source identity must be explicit.
2. Should required refs be declared per item (`required: true`) or at the
   classifier level? Per-item is more precise.
3. What is the first production classifier that needs this bridge? The likely
   candidate is a community loop classifier that evaluates stale request
   language against the current runbook and BUG wiki context.

## References

- `PLAN.md` Scoping Rules
- `PLAN.md` Community Evolvable Optimization
- `PLAN.md` API And MCP Interface
- `docs/design-notes/proposed/2026-05-06-escalation-replay-on-substrate-fix.md`
