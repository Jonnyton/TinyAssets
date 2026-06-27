# Legacy Branch Plan

Purpose: publish Fantasy Writer and Fantasy Author as older versions / ancestor systems of TinyAssets without polluting `TinyAssets/main`.

## Target Branches

- `legacy/fantasy-writer`
- `legacy/fantasy-author`

Each branch should have a root README that starts with:

> This branch preserves an archived ancestor of TinyAssets. It is not the current product. TinyAssets evolved from this system after the orchestration, memory, evaluation, and agent-workflow pieces became more general than fiction writing.

## Why Branches Instead Of Main

Branches make the relationship visible inside the `TinyAssets` GitHub repo while keeping the default branch focused.

This gives recruiters two levels:

- quick path: inspect `TinyAssets/main`
- deeper path: follow `docs/project-lineage.md` into legacy branches and see the real evolution

## Required Cleanup Before Pushing

For each source repo:

1. Create a staging clone or export.
2. Remove runtime/private/generated material.
3. Run full working-tree secret scan.
4. Run history-level secret scan if preserving commits.
5. Add an archive README.
6. Push to a test/private remote or local bare repo first.
7. Only then push the branch to `Jonnyton/TinyAssets`.

## Current Scan Finding

Lightweight local scan on 2026-04-29:

- `Fantasy Writer`: no high-signal provider-token candidates found in the scanned history.
- `Fantasy Author`: provider credential material was found in historical `STATUS.md` commits.

Result:

- Do not publish `Fantasy Author` full history as-is.
- Treat that credential as exposed and rotate/revoke it if it is still active.
- Publish Fantasy Author only as a cleaned snapshot or after a proper history rewrite and re-scan.
- `Fantasy Writer` is a better candidate for a full-history legacy branch, but still needs a real scanner pass before push.

## Exclude

- `.env`
- account-specific settings
- provider credentials
- generated books, canon dumps, audio, runtime universes
- caches: `.pytest_cache`, `.ruff_cache`, `.obsidian`, `.worktrees`
- databases and WAL files
- Electron/Godot builds and binaries
- copied vendor/tool skill bundles unless intentionally licensed and useful

## Commands Sketch

These are notes, not commands to run blindly.

```powershell
# From a clean temporary clone/export after cleanup:
git checkout -b legacy/fantasy-writer
git remote add workflow https://github.com/Jonnyton/TinyAssets.git
git push workflow legacy/fantasy-writer
```

For preserving full history safely, prefer a temporary clone plus a proper secret scan before pushing. Do not push directly from the current local dirty folders.

## Fallback

If history cleanup is too risky, create a separate `fantasy-agent-workflow-lab` repo with curated snapshots and link it from `TinyAssets/docs/project-lineage.md`.
