---
title: Markovic Fingerprint RD Scaling Program
date: 2026-05-07
status: research
source: pages/plans/markovic-fingerprint-rd-scaling-program.md
source_issue: 343
source_sha256: 2cc628ef094a5214d51abd3ccd2bb630db265ea149c1325a6a77c0bfe31821fa
---

# Markovic Fingerprint RD Scaling Program

Community wiki source:
`pages/plans/markovic-fingerprint-rd-scaling-program.md`, retrieved from the
live wiki on 2026-05-07. This repository note keeps the research-program plan
visible to coding sessions without promoting it to canonical `PLAN.md` truth
and without attesting the off-platform scientific artifacts.

## Classification

Request kind: docs/ops.

Smallest useful repo change: preserve the wiki research program as a tracked
reference and spell out the boundary between platform coordination state and
local scientific execution. No runtime code change is implied by this issue.

## Program Summary

The page records a computational-systems-biology research program attached to
Goal `cbc96a78d7ff`: test whether the published Glover et al. 2023
EDAR-WNT-BMP modified Gierer-Meinhardt parameters can quantitatively predict
fingerprint ridge-count scaling across differently sized digits without
digit-specific parameter tuning.

The plan is explicitly a platform-side lab-notebook analogue, not an
executable Workflow run. Local simulation and data artifacts remain local; the
platform records provenance, milestones, gate state, and what future primitives
would be needed to attest external runs.

## Current Gate State From Wiki Source

As of the source page update on 2026-05-05:

- Validation gates 001-003 were closed.
- Gate 004's lightweight masked-domain prototype was rejected: 0 of 5 seeds
  met the predeclared orientation acceptance rule.
- The rejection is documented as a prototype methods rejection, not biological
  falsification.
- B2 was decomposed into the Validation 004 ladder: V004-A through V004-D.
- V004-A was accepted for the rectangular linear-mode validation of the new
  finite-volume diffusion operator.
- V004-B was in progress in full mode, with no scientific result until
  `validation/04_fv_nonlinear_wavelength_full.json` exists locally.
- V004-C remained diagnostic-only and blocked behind V004-B pass.
- V004-D remained the unchanged rerun of original Gate 004, blocked behind
  V004-A and V004-B pass.
- Platform execution stayed no-go pending SOP-RXD-001 clearance.

## Five-Stage Ladder

The wiki page's five-stage program is:

1. B1 - validation provenance and canonical kinetics: closed.
2. B2 - masked digit geometry Gate 004: open; closes only if V004-D passes
   the unchanged acceptance rule.
3. B3 - digit-size scaling ensemble: blocked behind V004-D pass.
4. B4 - empirical dermatoglyphic data anchor: blocked behind B3.
5. B5 - manuscript evidence map: blocked behind B3 and B4.

The important discipline is that the acceptance bar does not move after the
prototype rejection. V004-C can explain behavior, but it cannot change the
V004-D acceptance rule.

## Relationship To Current Plan

This research program aligns with existing `PLAN.md` direction without
requiring a platform primitive in this branch:

- `State And Artifacts` separates durable coordination records from temporary
  execution artifacts.
- `Daemon-Driven` and `Evaluation` support gate-based progress, but only when
  evidence is real and reproducible.
- `API And MCP Interface` treats MCP clients as control stations, not as
  authority for local files they cannot inspect.
- The scoping rules keep this in community/wiki space until a structural
  primitive gap is proven.

The page does identify adjacent platform gaps, especially external-run
attestation and in-progress long-run heartbeat records. Those are already
represented by the wiki cross-references to PR-017 and PR-030, and should be
handled as separate scoped lanes rather than bundled into this docs/ops issue.

## Implementation Implications

Future work touching this program should keep these boundaries:

- Do not claim V004-B, V004-C, V004-D, B3, B4, or B5 progress from chat text or
  platform summaries alone.
- Treat local paths such as `validation/04_fv_nonlinear_wavelength_full.json`
  as off-platform evidence until an attestation primitive exists.
- Preserve the distinction between methods rejection, biological
  reinterpretation, and program falsification.
- Keep benchmark or heartbeat output out of acceptance decisions unless the
  predeclared gate says it is a result.
- Promote any new platform primitive need through a separate patch/design
  request with its own tests and opposite-family review.

## Open Questions

- What exact shape should completed external-run attestations use for local
  artifacts, hashes, command lines, and environment metadata?
- What fields belong in an in-progress long-run heartbeat without creating a
  remote-control channel into the local solver process?
- How should browser-only users inspect a research-program gate without
  seeing private local simulation files?
- Which public evidence can safely move into commons records if empirical
  dermatoglyphic data is later used?
