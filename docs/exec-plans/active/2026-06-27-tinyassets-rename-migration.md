# TinyAssets Rename Migration Execution Plan

Status: active planning lane
Date: 2026-06-27
Branch: `codex/tinyassets-rename-migration`
Worktree: `../wf-tinyassets-rename-migration`

## Goal

Retire `Workflow` / `workflow` as the project/platform namespace after migrating public, package, connector, env, data-path, and deployment surfaces to the Tiny/TinyAssets boundary.

## Phase 0: Land The Boundary

**Files:** `PLAN.md`, `docs/design-notes/2026-06-27-tinyassets-rename-migration.md`, this file, `STATUS.md`, `ideas/PIPELINE.md`, `ideas/INBOX.md`

Acceptance:

- `PLAN.md` says Tiny = persona, TinyAssets = platform, Workflow/workflow = migration-only.
- Design note inventories the major affected surfaces and declares no global replace.
- STATUS and idea pipeline show this as an active promoted lane.
- No runtime, package, connector, or deploy behavior changes in this phase.

Verification:

- `python scripts/docview.py section --heading "Canonical Vocabulary" PLAN.md`
- `python scripts/claim_check.py --provider codex-gpt5-desktop --check-files "PLAN.md, docs/design-notes/2026-06-27-tinyassets-rename-migration.md, docs/exec-plans/active/2026-06-27-tinyassets-rename-migration.md, STATUS.md, ideas/PIPELINE.md, ideas/INBOX.md"`
- `git diff --check`

## Phase 1: Public Copy And OSS Front Door

**Files:** `README.md`, `assets/brand/*`, `WebSite/site/src/lib/i18n/en.json`, `WebSite/design-source/source_copy/en.json`, website components that hard-code brand names, public docs that are install/readme/front-door surfaces.

Acceptance:

- Website and README brand the platform as TinyAssets.
- Tiny appears only where a persona/assistant is acting, not as the repo/platform brand.
- GitHub clone paths are either updated after repo rename or explicitly marked pending host repo rename.
- Asset names and alt text have TinyAssets replacements; old asset paths stay only where a live external listing still references them.

Verification:

- Website build/test per `website-editing` skill.
- Browser screenshot proof for changed website pages.
- `rg -n "Workflow|workflow" README.md assets WebSite/site/src WebSite/design-source/source_copy` reviewed and classified; no unclassified public-brand occurrences.

## Phase 2: App, Registry, Connector, And Directory Metadata

**Files:** `chatgpt-app-submission.json`, `packaging/registry/server.json`, `docs/ops/mcp-*`, `docs/ops/openai-app-submission-*`, `packaging/claude-plugin/.claude-plugin/marketplace.json`, `packaging/claude-plugin/plugins/*/.claude-plugin/plugin.json`, `.mcp.example.json`.

Acceptance:

- App/listing display name is TinyAssets.
- Test prompts invoke TinyAssets.
- Tool justifications avoid Workflow as product brand.
- Existing live endpoints remain reachable.
- Any old server/listing IDs are explicitly deprecated or carried as compatibility with a removal gate.

Verification:

- Direct `/mcp-directory` canary.
- ChatGPT web and mobile proof after re-registration.
- Claude connector proof where directory/admin access is available.
- `python packaging/claude-plugin/build_plugin.py` after plugin metadata/runtime changes.

## Phase 3: Package, Imports, CLI, And Plugin Runtime

**Files:** `pyproject.toml`, `workflow/`, tests, `packaging/claude-plugin/build_plugin.py`, plugin runtime, `.mcp.example.json`, import/entry-point smoke tests.

Acceptance:

- New package/import path is `tinyassets`.
- CLI/script names use `tinyassets-*`.
- Any `workflow` import path is a temporary compatibility adapter with warning/removal tests, or is removed in a documented breaking cutover.
- Plugin runtime stages the new package path.
- Domain entry-point group replacement is defined and tested.

Verification:

- `pip install -e .[dev]`
- Import smoke for `tinyassets` and all public entry points.
- Focused packaging/plugin tests.
- Full or relevant pytest suite, depending on blast radius.

## Phase 4: Env Vars, Data Paths, Deploy, And DR

**Files:** `deploy/`, `.github/workflows/`, ops runbooks, deploy scripts, service files, backup/restore scripts, data-dir resolver tests.

Acceptance:

- New env prefix is `TINYASSETS_*`.
- New paths are `/etc/tinyassets`, `/opt/tinyassets`, and `tinyassets-*` Docker/service names.
- Existing production data has a migration path with rollback.
- Backup/restore and DR scripts use the new names or explicitly bridge old volumes during migration.

Verification:

- Deploy canaries.
- DR drill or equivalent restore proof for the renamed data/service paths.
- `actionlint` for workflow changes.
- Data resolver tests for old-to-new migration behavior.

## Phase 5: Final Retirement

**Files:** compatibility adapters, old docs that still act as live instructions, old metadata, old env/path aliases.

Acceptance:

- `Workflow` / `workflow` remains only in historical docs or ordinary English usage.
- Compatibility adapters and old env/path aliases are removed.
- Search inventory has zero active blockers.
- Post-cutover clean-use evidence exists, or a STATUS watch item remains until first-user evidence appears.

Verification:

- Full inventory report with every remaining match classified as historical/generic or removed.
- Full tests and packaging checks.
- Live connector proof.
- Post-fix clean-use evidence check.
