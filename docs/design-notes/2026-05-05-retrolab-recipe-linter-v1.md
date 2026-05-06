---
title: RetroLab recipe linter v1
date: 2026-05-05
status: research
source: pages/plans/retrolab-recipe-linter-v1.md
source_issue: 350
---

# RetroLab Recipe Linter v1

Community wiki source:
`pages/plans/retrolab-recipe-linter-v1.md`, retrieved from the live wiki on
2026-05-06. This repository note keeps the proposal visible to coding sessions
without promoting it to canonical `PLAN.md` truth or claiming that a RetroLab
runtime linter has shipped.

## Classification

Request kind: docs/ops.

Smallest useful repo change: preserve the wiki plan as a tracked design
reference and extract the concrete linter gates future RetroLab recipe work
must satisfy before runner dispatch. No runtime code change is implied by this
issue.

## Proposed Placement

The wiki plan defines a pure-function linter for `GameRecipe` records. It
consumes only the recipe plus dereferenced `LegalSource`, `RuntimeAdapter`, and
`ProofObjective` records, with an optional `RunnerJobPlan` for dispatch-time
checks.

The linter is intended to run twice in the recipe forge pipeline:

1. Stage 6.5, between `recipe_generation` and `proof_objective_selection`.
2. Stage 8.5, between `job_plan_synthesis` and runner dispatch.

The output is a `LinterResult` with `PASS` or `FAIL`, failed gates with
severity/reason/remediation, passed gate ids, `linter_version: "v1"`, and an
evaluation timestamp.

## Gate Families

The plan defines fifteen gates, grouped by risk:

| Family | Gates | Purpose |
| --- | --- | --- |
| Legality | LINT-G1..G4 | Require a dereferenced legal source, accepted legal-source kind, primary evidence URL, and durable evidence capture. |
| Hash and artifacts | LINT-G5..G8 | Require runtime and game-data artifacts, strict SHA-256 pins, primary artifact URLs, and runner-supported archive formats. |
| Proof objective | LINT-G9..G12 | Reject dangling proof objectives, title-screen-only proof, weak pass conditions, and proof runs that are not shortcut-bound. |
| Headlessness | LINT-G13..G15 | Reject non-allowlisted runner actions, declared manual/user-account steps, and generated files outside the RetroLab root. |

## Hard Failure Rules

Future implementation should treat these as non-negotiable fail gates:

- Anti-piracy: `legal_source.kind` must be one of
  `rights-holder-release`, `publisher-freeware`, `open-source`,
  `public-domain`, or `homebrew-author-release`. `abandonware`,
  `aggregator`, `unknown`, and unrecognized values fail.
- Primary evidence: `legal_source.primary_evidence_url` must be present and
  must not be an aggregator-only source.
- Hash pins: every artifact must carry a lowercase 64-character SHA-256 value;
  placeholders such as `NEEDS_PIN`, uppercase values, empty strings, or wrong
  lengths fail.
- Artifact source: artifact URLs must resolve to primary publisher,
  project, rights-holder, or rights-holder archive hosts, not secondary ROM or
  abandonware aggregators.
- Non-trivial proof: proof kind must not be `engine_init` or
  `title_screen_only`.
- Pass-condition coverage: proof conditions must show both runtime/content
  initialization and a non-title-screen state such as gameplay/menu overlay,
  savefile creation, item/level progress, or a command-line warp marker.
- Shortcut-bound proof: the launched payload must be byte-equal to the
  shortcut readback, preventing a proof harness from launching a different
  command than the recipe installs.
- Headless runner contract: procedures and job plans may only use the runner
  S3 allowlist: `fs_fetch`, `fs_extract`, `shell_create_shortcut`,
  `shell_read_shortcut`, `proc_launch`, `ui_screenshot`, `ui_send_keys`, and
  `proc_kill`.
- No manual steps: recipe metadata must not include keys matching
  `manual_step`, `user_action_required`, `requires_eula_accept`,
  `requires_login`, or `requires_account`.
- Path containment: generated file paths must resolve under
  `%USERPROFILE%/RetroLab/**` and must not use `..` or system directories.

## Severity Model

The wiki plan marks `LINT-G4 LegalEvidenceCaptured` as a warning. All other
critical and major failures produce `result: FAIL`.

Critical gates:
`LINT-G1`, `LINT-G2`, `LINT-G3`, `LINT-G5`, `LINT-G6`, `LINT-G9`,
`LINT-G10`, `LINT-G12`, `LINT-G13`, and `LINT-G14`.

Major gates:
`LINT-G7`, `LINT-G8`, `LINT-G11`, and `LINT-G15`.

Warning gate:
`LINT-G4`.

## Implementation Implications

This plan should shape future RetroLab implementation, but it should not by
itself add a new public MCP primitive or runner surface.

1. The linter can start as a deterministic, side-effect-free function over
   structured records, with fixtures covering every gate failure named above.
2. Promotion to runner dispatch must require a clean linter result. Warning
   gates may remain visible to curators without blocking dispatch.
3. Tests need explicit negative fixtures for piracy/aggregator sources,
   missing or malformed hashes, title-screen-only proof, missing shortcut
   readback equivalence, manual-step metadata, and path traversal.
4. Any later runtime implementation must keep the aggregator blocklist and
   runner action allowlist data-driven enough to update without changing the
   linter algorithm.
5. The linter result should be stored or surfaced beside recipe readiness so a
   curator can see the exact remediation rather than a generic "not ready"
   state.

## Open Follow-Up

The wiki plan references `GameRecipe`, `LegalSource`, `RuntimeAdapter`,
`ProofObjective`, and `RunnerJobPlan` records that are not canonical repo
interfaces in this branch. Before implementation, define those record shapes or
point the linter at the branch that owns them, then add the focused fixture
suite before wiring any dispatch gate.
