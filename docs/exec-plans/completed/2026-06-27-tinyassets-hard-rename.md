# TinyAssets Hard Rename Execution Plan

> **Retired 2026-07-22: LANDED — `origin` is `https://github.com/Jonnyton/TinyAssets.git`. Triage: `docs/audits/2026-07-22-exec-plan-liveness-triage.md`.**

Status: active implementation lane
Date: 2026-06-27
Branch: `codex/tinyassets-hard-rename`
Worktree: `../wf-tinyassets-rename-migration`

## Goal

Cut the project from `Workflow` / `workflow` to `TinyAssets` / `tinyassets` across active repo, website, package, connector, GitHub, deploy, and packaging surfaces.

## Steps

1. Rename GitHub repository to `Jonnyton/TinyAssets` and retarget local `origin`.
2. Move the Python package from `workflow/` to `tinyassets/` and retarget imports, entry points, packaging, plugin runtime, and tests.
3. Rename active launchers, brand assets, service files, data/env path docs, and MCP bundle/listing IDs.
4. Replace public website, README, app submission, registry, and design-source copy so TinyAssets is the platform and Tiny is the persona.
5. Regenerate package/plugin mirrors and run import, packaging, website, and focused runtime checks.
6. Classify remaining old-name hits as historical/generic or remove them.

## Verification

- `gh repo view Jonnyton/TinyAssets --json nameWithOwner,url`
- `git remote -v`
- `python packaging/claude-plugin/build_plugin.py`
- `python packaging/mcpb/build_bundle.py`
- `python -m pytest ...` focused rename/package tests
- `python -m ruff check ...` on touched runtime/test scripts
- `npm run check` and `npm run build` in `WebSite/site`
- Rendered website screenshots for changed public pages
- Targeted `rg` scans for active old-name surfaces

## Notes

This plan deliberately does not preserve a public compatibility brand. The old name can remain only in clearly historical records or where `workflow` is a literal common noun for a user-authored process.
