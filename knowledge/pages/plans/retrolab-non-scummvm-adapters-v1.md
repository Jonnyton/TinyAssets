---
title: RetroLab Non-ScummVM Runtime Adapters v1
type: plan
status: proposed
request_id: WIKI-DOCS
github_issue: 348
updated: 2026-05-06
---

# RetroLab Non-ScummVM Runtime Adapters v1

## Goal

Define the first non-ScummVM RetroLab runtime adapters:

- RetroArch portable with Stella for Atari 2600 targets.
- RetroArch portable with Mesen for NES/Famicom targets.
- FS-UAE with the AROS Kickstart-replacement path for Amiga targets.

This page is a plan, not an implementation record. It exists so a future
daemon or contributor can build the adapters without turning emulator-specific
details into new platform primitives.

## Scope

The v1 adapter work should make each runtime launchable from a portable,
rights-safe bundle:

- Resolve the runtime executable and core/emulator files from an adapter-local
  directory.
- Accept a game payload path plus a small, explicit adapter config.
- Emit a launch manifest that records executable path, core/emulator choice,
  game path, generated config files, and user-facing setup errors.
- Keep proprietary firmware, BIOS, ROM, and game files out of git.
- Prefer per-adapter config generation over mutating a user's global emulator
  profile.

Out of scope for v1:

- Netplay, shader packs, achievements, overlays, save-state sync, cloud saves,
  and library scraping.
- Shipping copyrighted game files or proprietary Kickstart ROMs.
- Adding a new MCP primitive when a wiki plan plus adapter composition can
  express the work.

## Adapter Notes

### RetroArch Portable - Stella

Use RetroArch as the process runner and Stella as the Atari 2600 core. The
adapter should generate a minimal config rooted in the portable bundle and
surface missing-core or invalid-ROM errors before launch when possible.

Acceptance evidence:

- Launches a rights-cleared Atari 2600 test payload.
- Does not read or write a global RetroArch config path during the smoke test.
- Produces a manifest showing the selected Stella core and payload path.

### RetroArch Portable - Mesen

Use RetroArch as the process runner and Mesen as the NES/Famicom core. The
adapter should preserve the same portable-config and manifest conventions as
the Stella adapter so future RetroArch cores can reuse the pattern.

Acceptance evidence:

- Launches a rights-cleared NES/Famicom test payload.
- Does not read or write a global RetroArch config path during the smoke test.
- Produces a manifest showing the selected Mesen core and payload path.

### FS-UAE + AROS Kickstart Replacement

Use FS-UAE for Amiga targets and default to the AROS Kickstart-replacement path
for rights-safe testing. The adapter must make the firmware source explicit in
the manifest and must fail closed if a proprietary Kickstart path is requested
without host-provided proof that the file is rights-cleared.

Acceptance evidence:

- Launches a rights-cleared Amiga test payload using the AROS replacement path.
- Records the firmware mode in the manifest.
- Documents any compatibility gap where a target needs an original Kickstart
  ROM instead of AROS.

## Gate Requirements

Code-change writers are Claude or Codex only. A code implementation requires an
opposite-family checker before it is treated as landed.

Minimum gate ladder:

1. Adapter unit tests cover manifest generation, missing runtime/core errors,
   and config path isolation.
2. A local smoke test proves one rights-cleared payload per adapter family.
3. No proprietary firmware, BIOS, ROM, or game asset is committed.
4. Public-surface changes, if any, get final rendered chatbot verification
   through the live Workflow connector.
5. Bounty settlement, if a paid bounty is later attached, follows the issue's
   declared `bounty_requirements`.

## Open Questions

- Which exact portable RetroArch distribution path should be canonical for
  Linux, macOS, and Windows bundles?
- Should adapter manifests live beside run artifacts or in a RetroLab-specific
  subdirectory?
- What rights-cleared test payloads should become the standard smoke fixtures?
- Should FS-UAE AROS compatibility failures become adapter warnings, blocked
  gates, or separate per-game notes?
