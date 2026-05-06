# Retrolab Recipe Forge V1

## Status

Proposed for issue #349 / WIKI-DESIGN.

## Classification

Project design. This is an architectural branch design for a community-authored retro-game discovery recipe that can produce a runner job plan. It is not a runtime implementation request.

## Context

The existing classic-game runtime decision in `docs/design-notes/2026-04-30-exact-classic-game-browser-runtime.md` defines the product contract after a target game is known: prefer lawful original media in a browser runtime, require rights-cleared firmware when needed, and label remakes or ports as fallbacks.

The missing upstream piece is a repeatable community branch shape that starts with a broad user request such as "find legal/free retro games like this" and ends with a runner-ready plan. That branch must avoid laundering abandonware or warez into Workflow, and it must not become a platform-built game catalog.

## Design Goal

Create a branch pattern, `retrolab_recipe_forge_v1`, that lets daemons discover, score, and package legal/free retro-game candidates into runner job plans using existing Workflow primitives and community-authored rubrics.

This should be community-buildable over existing branch, node, gate, wiki, discovery, and runner-planning surfaces. No new MCP action or runtime primitive is proposed for v1.

## Non-Goals

- Do not host copyrighted game media, ROMs, firmware, cracks, or private downloads.
- Do not declare a game playable from metadata alone.
- Do not replace the exact-game browser-runtime contract.
- Do not ship a platform-maintained retro-game database.
- Do not auto-run untrusted archives or binaries during discovery.

## Branch Shape

The recipe branch has six node groups:

1. `intent_capture`: normalize the user's memory, platform hints, era, genre, visual clues, tolerance for remakes, and target capability tier.
2. `source_discovery`: collect candidate public sources with URLs, archive names, platform, publisher/author, stated license, redistribution notes, runtime requirements, and checksums when available.
3. `rights_triage`: classify each candidate as one of `rights_cleared_public`, `user_media_required`, `firmware_entitlement_required`, `source_port_or_fallback`, `unclear_do_not_package`, or `rejected_infringing`.
4. `candidate_score`: rank non-rejected candidates by intent match, provenance strength, runtime confidence, browser-only fit, and expected playable-proof cost.
5. `runtime_fit`: map rights-cleared or user-supplied candidates to a known browser/runtime path, local-app runner path, or blocked state.
6. `runner_job_plan`: emit a bounded execution plan for the next branch, including assets to fetch, verification gates, expected result state, and human review requirements.

Each node stores evidence references, not just conclusions. A candidate with no license or provenance evidence cannot advance past `rights_triage`.

## Candidate Record

The branch should use a simple structured record in notes or node output:

```yaml
title: ""
platform: ""
candidate_kind: original_media | source_port | official_release | remake | metadata_only
source_url: ""
source_operator: ""
license_or_distribution_claim: ""
redistribution_allowed: yes | no | unknown
requires_firmware: none | rights_cleared | user_owned | unknown
runtime_candidate: ""
asset_hashes: []
evidence_refs: []
triage_state: rights_cleared_public | user_media_required | firmware_entitlement_required | source_port_or_fallback | unclear_do_not_package | rejected_infringing
runner_state: original_media_candidate | fallback_candidate | blocked_rights | blocked_runtime | rejected
selection_score: 0
selection_reason: ""
```

## Runner Job Plan

The output plan for a follow-on runner branch contains:

- exact candidate record and evidence refs;
- selection score and reason, including why higher-risk candidates were not chosen;
- asset fetch steps limited to lawful public URLs or user-provided media prompts;
- runtime choice and capability tier, browser-only or local-app;
- expected branch contract state from the exact classic-game runtime note;
- acceptance proof target, such as title-to-gameplay with input and audio for the real game path;
- blocker text for rights, firmware, runtime, or provenance gaps;
- review gates: opposite-family checker for code changes, legal/provenance review before packaging, and real browser proof before claiming playable.

The runner branch must begin from the plan's `runner_state`. For example, `blocked_rights` may produce a user-media prompt or fallback recommendation, but cannot silently become `original_media_candidate`.

## Gates

`source_discovery` passes only if each candidate has at least one evidence ref and a source URL.

`rights_triage` passes only if every advanced candidate has an explicit distribution claim and a reviewer-readable reason. Unknown rights are blocked, not assumed free.

`runtime_fit` passes only if the plan names a proven runtime or records `blocked_runtime`.

`runner_job_plan` passes only if it names the expected exact-game branch state and the minimum playable-proof acceptance. Canvas render, emulator boot screen, archive download, or metadata match alone is not sufficient.

## Relationship To Existing Architecture

This design follows the PLAN.md scoping rules:

- Minimal primitives: v1 composes existing branch nodes, evidence refs, gates, and runner planning instead of adding a new MCP tool.
- Community-build over platform-build: the retro-game recipe lives as a remixable community branch pattern.
- Commons-first architecture: public candidate metadata and rubrics can live in the commons; private user media stays with the user or host.
- User capability axis: every runner plan names browser-only or local-app assumptions instead of treating a native emulator install as universal.
- Engine and domains: retro-game logic belongs in community/domain branch content unless a later implementation proves a missing shared engine primitive.

## Open Questions

- Which community wiki page should hold the first rights-triage rubric once wiki droplet write lanes clear?
- Should the first v1 sample target one known public-domain/freeware title, or start as a metadata-only dry run to harden the rights gate?
- What evidence format should downstream legal/provenance reviewers prefer for archived game pages that have weak or aging license text?

## Smallest Useful Next Change

After opposite-family review, seed a community recipe branch from this note with `intent_capture`, `source_discovery`, `rights_triage`, `candidate_score`, `runtime_fit`, and `runner_job_plan` nodes. Keep the first sample dry-run or rights-cleared-only until the runner plan has independent provenance review.
