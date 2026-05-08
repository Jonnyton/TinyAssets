---
title: Retrolab Recipe Forge V1
date: 2026-05-08
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 349
wiki_source: pages/plans/retrolab-recipe-forge-v1-design.md
scope: design-only; no runtime code in this branch
builds_on:
  - docs/design-notes/2026-04-30-exact-classic-game-browser-runtime.md
  - PLAN.md#scoping-rules
  - PLAN.md#distribution-and-discoverability
  - PLAN.md#community-evolvable-optimization
---

# Retrolab Recipe Forge V1

## 1. Recommendation Summary

Treat Retrolab Recipe Forge as a branch recipe and runner-job plan for finding
lawful, free retro-game play paths. Do not add a new platform primitive or MCP
action in v1. The useful project change is a design contract that a chatbot or
daemon can instantiate from existing Workflow primitives: create a branch,
discover candidates, record rights evidence, run browser-runtime probes, and
emit a reviewed job plan for the next runner.

The design extends the exact classic-game runtime decision without weakening
it. A recipe may recommend remakes, ports, open-source engines, public-domain
media, or user-owned-media paths, but it must not call a remake "the original"
and must not imply that abandonware or easily downloaded ROMs are lawful.

## 2. Product Boundary

Retrolab answers this user need:

> Find retro games I can legally play for free in a browser or through a
> clearly described local-app path, then prepare the smallest runner job that
> can verify and publish one playable result.

V1 is not a general game catalog, ROM scraper, emulator mirror, or legal
advice engine. It is a Workflow branch pattern that converts messy discovery
into typed evidence and a next-runner handoff.

Target capability tiers:

- Browser-only users get hosted browser-runtime links, PWA/result URLs, or a
  clear "needs user-owned media" stop state.
- Local-app users may additionally get a local runner job that invokes
  installed emulators or converters under host approval.
- Both tiers use the same evidence taxonomy; only the execution path changes.

## 3. Branch Recipe Shape

Each Retrolab branch should contain these nodes:

| Node | Purpose | Required output |
|---|---|---|
| `intent_parse` | Identify desired era, platform, genre, exact-title tolerance, and browser/local capability tier. | Search brief with user constraints and disallowed assumptions. |
| `candidate_discovery` | Find games, engines, remakes, ports, or media sources. | Candidate list with source URLs and claimed license/free status. |
| `rights_evidence_review` | Classify whether each candidate is lawful to use in Workflow. | Rights status, evidence links, and uncertainty notes. |
| `runtime_fit_probe` | Match candidate media or engine to a browser/local runtime. | Runtime state using the contract in section 4. |
| `runner_job_plan` | Select one or more candidates and write the next executable job. | Minimal job plan with inputs, gates, expected artifacts, and stop conditions. |
| `publication_review` | Decide what can be published to the commons. | Publishable artifact list and attribution requirements. |

This is intentionally a composition pattern over branches, evaluators, gates,
wiki notes, and runner jobs. If future implementations find that chatbots
cannot compose these nodes reliably, the gap to fix is likely typed evidence
storage or evaluator wiring, not a new `find_free_retro_game` action.

## 4. Evidence And State Contract

Every candidate must end in exactly one rights state and one runtime state.

Rights states:

- `PUBLIC_DOMAIN_CONFIRMED`: credible source identifies the game/media as
  public domain or equivalent, with enough provenance to cite.
- `OPEN_SOURCE_OR_FREEWARE_CONFIRMED`: license or author statement permits the
  proposed use; redistribution terms are explicit.
- `FREE_TO_PLAY_NO_REDISTRIBUTION`: play is free at the source, but Workflow
  may link only; it must not mirror assets.
- `USER_OWNED_MEDIA_REQUIRED`: no lawful public copy is available; the user
  must provide their own disk, ROM, CD image, or firmware.
- `RIGHTS_UNCLEAR`: claims exist but are too weak, conflicting, or uncited.
- `DISALLOWED`: source appears infringing, malware-adjacent, or depends on
  unauthorized copyrighted media.

Runtime states:

- `BROWSER_PLAYABLE_VERIFIED`: the candidate launched in a browser runtime with
  allowed assets and a recorded smoke proof.
- `BROWSER_RUNTIME_PLAUSIBLE`: the runtime path exists, but the runner has not
  verified boot/play yet.
- `LOCAL_APP_RUNNER_REQUIRED`: legal path exists, but needs host-local software
  or files.
- `NEEDS_RIGHTS_CLEARED_FIRMWARE`: public game media exists, but proprietary
  firmware or BIOS must be rights-cleared before instant browser play.
- `NEEDS_USER_OWNED_MEDIA`: execution depends on user-provided media.
- `FALLBACK_REMAKE_OR_PORT`: playable alternative exists, but it is not the
  exact original.
- `NO_VIABLE_RUNTIME`: no suitable runtime path is known for the candidate.

The runner may advance only candidates whose rights state is one of
`PUBLIC_DOMAIN_CONFIRMED`, `OPEN_SOURCE_OR_FREEWARE_CONFIRMED`,
`FREE_TO_PLAY_NO_REDISTRIBUTION`, or `USER_OWNED_MEDIA_REQUIRED`. It must stop
or ask for review on `RIGHTS_UNCLEAR` and must reject `DISALLOWED`.

## 5. Runner Job Plan

The handoff from recipe to runner should be a small declarative plan, not an
open-ended instruction blob:

```yaml
job_kind: retrolab_runtime_probe
candidate:
  title: "Scorched Tanks"
  platform: amiga
  source_url: "https://example.invalid/source"
  rights_state: PUBLIC_DOMAIN_CONFIRMED
  runtime_state: BROWSER_RUNTIME_PLAUSIBLE
inputs:
  media:
    source: allowed_url
    expected_hash: "sha256:..."
  firmware:
    policy: rights_cleared_or_user_owned_only
allowed_writes:
  - output/retrolab/<run_id>/
  - WebSite/site/static/play/<slug>/SOURCES.md
gates:
  - verify_source_accessible
  - verify_hash_or_record_hash
  - verify_no_bundled_proprietary_firmware
  - browser_smoke_launch
stop_conditions:
  - rights_unclear
  - firmware_required_without_entitlement
  - runtime_blank_or_uninteractive
publishable_artifacts:
  - SOURCES.md
  - runtime_smoke_report.md
  - screenshot_or_trace_path
```

The runner job should prefer one candidate at a time. Batch discovery is fine,
but verification and publication should stay narrow so rights and runtime
failures do not contaminate unrelated candidates.

## 6. Gates

### Discovery Gate

Discovery may collect candidate links from catalogs, author pages, archives,
open-source repositories, package registries, and prior Workflow branches. It
must preserve source URLs and the exact claim being made. "Free download" is
not a rights claim.

### Rights Gate

Rights review blocks before media is mirrored, transformed, or published.
Allowed evidence includes author/license pages, repository licenses, archive
metadata with provenance, or user-owned upload attestations. Weak forum claims,
abandonware labels, and mirror-site availability are not enough.

### Runtime Gate

Runtime probing must record the environment, input media hash when available,
browser/local capability tier, and observed result. A blank canvas, firmware
prompt, crash screen, or title-screen-only boot is not the same as verified
playability unless the user asked only for preservation or inspection.

### Publication Gate

The commons may store branch recipes, evidence summaries, source links, hashes,
smoke reports, screenshots when lawful, and runtime wrapper code. It must not
store proprietary firmware, unauthorized ROMs, or media whose license forbids
redistribution.

## 7. Relationship To Existing Architecture

- PLAN.md Scoping Rules: this remains a community-build composition. The
  platform should not ship a new convenience action for one domain-specific
  search workflow.
- PLAN.md Distribution And Discoverability: the design reuses the declarative
  software surface. Browser runtimes and local emulators are capabilities to
  resolve through existing host policy, not hidden subprocesses.
- PLAN.md Community Evolvable Optimization: future recipe improvements can be
  evaluated as branch variants with locked rights/runtime gates.
- `docs/design-notes/2026-04-30-exact-classic-game-browser-runtime.md`: this
  proposal adopts its distinction between exact original media and fallback
  ports/remakes.

## 8. Open Questions

1. Should the first public recipe target one verified candidate, such as the
   existing Scorched Tanks slice, or a broader catalog of 5-10 candidates?
   Recommendation: one verified candidate first; catalog breadth can follow
   once the gates are proven.

2. Where should reusable rights rubrics live? Recommendation: wiki/community
   guidance first. Promote to code only if a recurring structural evidence
   field is impossible to preserve in branch artifacts.

3. Should candidate discovery use web search directly from runners?
   Recommendation: yes only when the runner environment has network approval
   and records sources. Offline replays should consume captured source lists
   and hashes.

4. What is the first acceptance proof? Recommendation: a rendered chatbot
   conversation starts a Retrolab branch, receives a candidate with rights and
   runtime states, and gets a runner job plan that stops before any unclear or
   disallowed media.

## References

- `docs/design-notes/2026-04-30-exact-classic-game-browser-runtime.md`
- `PLAN.md` Scoping Rules
- `PLAN.md` Distribution And Discoverability
- `PLAN.md` Community Evolvable Optimization
