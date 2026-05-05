---
title: RetroLab Runtime Adapters v1
date: 2026-05-05
status: research
source: pages/plans/retrolab-runtime-adapters-v1.md
source_issue: 352
---

# RetroLab Runtime Adapters v1

Community wiki source:
`pages/plans/retrolab-runtime-adapters-v1.md`, retrieved from the live wiki on
2026-05-05. This repository note keeps the proposal visible to coding sessions
without promoting it to canonical `PLAN.md` truth or claiming runtime support
has shipped.

## Classification

Request kind: docs/ops.

Smallest useful repo change: preserve the wiki plan as a tracked design
reference, call out the adapter records that are not implementation-ready, and
define the follow-up gates that must pass before code can consume the adapter
pins.

## Proposal Summary

RetroLab v1 wants four runtime adapter records that cover a seed catalog of
rights-clear classic-game workflows:

| Adapter family | Intended coverage | Proof model |
| --- | --- | --- |
| ScummVM | ScummVM-supported adventure engines and freeware game data | stdout engine markers plus Global Main Menu overlay screenshot |
| Chocolate Doom | Doom-engine IWAD workflows | command-line warp/timer run plus stdout and screenshot evidence |
| DOSBox Staging | DOS and DOS-protected-mode games | generated per-game config with autoexec, stdout mount markers, and rendered frame evidence |
| RetroArch plus Mesen | NES/Famicom ROM workflows | RetroArch log markers, libretro core load, savestate/screenshot evidence |

The adapter shape follows the wiki's referenced `RuntimeAdapter` concept:
install artifact, portable setup steps, launch templates, proof capabilities,
required runner actions, expected log markers, screenshots, and failure modes.

## Freshness Check

Verified on 2026-05-05 against publisher-controlled pages:

| Adapter | Wiki pin | Current source status | Repo-side treatment |
| --- | --- | --- | --- |
| ScummVM | `scummvm-2026.2.0` Windows x64 zip | Official ScummVM downloads list 2026.2.0 as latest stable and publish the same Windows x64 zip SHA-256. | Accept as verified publisher pin. |
| Chocolate Doom | `chocolate-doom-3.1.1` | Official Chocolate Doom downloads identify 3.1.1 as latest and state downloads are GPG-signed. | Accept version, but require artifact URL, signature, and/or hash pin at fetch time. |
| DOSBox Staging | `dosbox-staging-0.83.0` | Official Windows release page lists 0.82.2 as current stable with installer and portable ZIP SHA-256 values. | Treat 0.83.0 as speculative or stale until a publisher release page exists. |
| RetroArch plus Mesen | `retroarch-mesen-1.21` | Official RetroArch platform page reports current stable 1.22.2; the 1.21.0 buildbot folder still contains `RetroArch.7z`. | Treat 1.21 as an older explicit pin, not the current stable. Re-check core filename before implementation. |

Sources used:

- https://www.scummvm.org/downloads/
- https://www.chocolate-doom.org/wiki/index.php/Downloads
- https://www.dosbox-staging.org/releases/windows/
- https://www.retroarch.com/?page=platforms
- https://raw.libretro.com/stable/1.21.0/windows/x86_64/

## Implementation Implications

This plan should not directly trigger runtime code until the adapter records
clear these gates:

1. Every install artifact has a publisher-controlled URL and a publisher
   hash/signature source recorded beside the pinned artifact.
2. The runner has the declared extraction support. RetroArch currently needs
   7z handling or a project-hosted ZIP mirror with its own provenance.
3. Proof commands are verified on the target host OS with captured stdout/logs
   and screenshots from a real launched runtime, not inferred from docs.
4. Recipe-level legal classification decides which game data or IWAD/ROM
   files may be fetched, referenced, or require user-provided local paths.
5. Adapter records remain data. New MCP verbs are not required for this plan;
   missing runner operations should be scoped separately against existing
   runner capabilities.

## First Follow-Up Candidates

- Update the live wiki page or a successor plan to replace the DOSBox Staging
  speculative 0.83.0 pin with the current official stable release, or mark it
  as future-only.
- Decide whether RetroArch v1 should follow current stable 1.22.2 or retain
  1.21.0 for reproducibility.
- Add a small artifact-pinning checklist to the RetroLab recipe-forge plan so
  adapter records cannot enter a seed catalog with `NEEDS_PIN` fields.
- Run a Windows proof pass for ScummVM first; it has the cleanest publisher
  hash and runtime proof story.

## Non-Goals

- This note does not add runtime code, runner actions, or MCP tools.
- This note does not certify game data redistribution rights.
- This note does not make RetroLab canonical architecture. Any implementation
  lane still needs a concrete `STATUS.md` row, exact files, tests, and an
  opposite-family checker.
