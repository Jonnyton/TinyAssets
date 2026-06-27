# TinyAssets Rename Migration

Status: accepted direction, migration plan slice
Date: 2026-06-27
Owner: codex-gpt5-desktop

## Problem

`Workflow` was a working engineering name from the discovery phase. It still appears as the project root folder name, GitHub repository name, Python package, connector/app name, public docs name, deployment path, env-var prefix, data-volume name, and many historical references. That now conflicts with the product model:

- `Tiny` is the personified intelligence users and developers interact with: the acting persona shaped as an extension of the founder's will.
- `TinyAssets` is the website, platform, repository, distribution, and app/listing brand.
- `Workflow` / `workflow` is not a permanent internal substrate name. It exists only during migration and retires once replacements are proven.

## Decision

Use a staged retirement, not a global replace.

The canonical boundary is:

| Term | Meaning | Not this |
|---|---|---|
| `Tiny` | The acting personification: the intelligence/person users and developers talk to when a universe/persona is bound, shaped as an extension of the founder's will. | The repo, legal/product listing, package, or website brand. |
| `TinyAssets` | The platform, website, GitHub/repository, distribution, connector/app listing, and OSS project brand. | The first-person acting persona. |
| `Workflow` / `workflow` | Migration-only compatibility name for existing imports, env vars, paths, registry IDs, installed connectors, historical docs, and user installs. | A durable product, repo, connector, package, or architecture brand. |
| `workflow` as common noun | A plain-English process/sequence when literally describing user work. | A namespace, product, connector, or platform name. |

No new public surface should introduce `Workflow` as a brand. Any remaining instance must be classified as one of: historical context, temporary compatibility, or migration blocker.

## Current Surface Inventory

Initial evidence from this branch:

| Surface | Evidence | Migration posture |
|---|---|---|
| Public URL | `tinyassets.io` is already canonical for `https://tinyassets.io/mcp`, `/mcp-directory`, `/connect`, and `/fine-print`. | Keep. This is the destination brand. |
| Python package | `pyproject.toml` has `name = "workflow"`, scripts `workflow-cli`, `workflow-mcp`, `workflow-universe-server`, `workflow-probe`, GUI script `workflow`, package `workflow`, entry-point group `workflow.domains`. | Replace with `tinyassets` package/distribution in a later high-risk slice; compatibility must be explicit and time-bounded. |
| MCP registry | `packaging/registry/server.json` uses `io.github.Jonnyton/workflow-universe-server`, title `Workflow`, repository `Jonnyton/Workflow`, and raw GitHub icon URL. | Publish/submit a TinyAssets listing path; decide whether old listing redirects or remains deprecated until host directories update. |
| ChatGPT submission | `chatgpt-app-submission.json` display name and test prompts use `Workflow`; tool justifications refer to Workflow state. | Rename app metadata to TinyAssets; prompts should invoke TinyAssets, with Tiny as persona only after binding. Requires ChatGPT web/mobile proof. |
| Claude plugin | `packaging/claude-plugin` uses `workflow-universe-server`, `workflow-plugins`, `Workflow Data Directory`, `WORKFLOW_DATA_DIR`, and imports `workflow.universe_server`. | Rename marketplace/display first; package/runtime rename later with plugin mirror build and install proof. |
| Local MCP config | `.mcp.example.json` registers server key `workflow` and runs `python -m workflow.mcp_server`. | Provide TinyAssets example first; remove `workflow` example after package entry point changes. |
| Website copy | `WebSite/site/src/lib/i18n/en.json` and design-source copy have headings like `Why Workflow?`, `Workflow Goals`, invocations like `Workflow: ...`, and GitHub paths `github.com/Workflow/Workflow`. | First public-copy slice after this plan. Use TinyAssets for platform and Tiny only for persona/chat moments. |
| Brand assets | `assets/brand/README.md` and filenames use `workflow-logo-*`. | Rename to TinyAssets assets, preserve old names only as temporary compatibility if referenced by live listings. |
| README / contributor docs | `README.md` title, clone command, entry paths, and architecture prose are Workflow-branded. | Rename user-facing brand in the first docs slice; code paths stay literal until package rename. |
| Deploy/ops | `/opt/workflow`, `/etc/workflow`, Docker volumes `workflow-data`, containers, services, and `WORKFLOW_*` env vars appear heavily in `deploy/`, `.github/workflows/`, and scripts. | High-risk operational migration; needs aliases or explicit cutover plus deploy/DR proof. |
| Code/imports/tests | Thousands of `from workflow...`, `import workflow`, test names, plugin mirror imports, and `workflow/` path guards. | Highest-risk slice. Must not move until public brand/docs are clean and import/packaging migration strategy is accepted. |
| Historical docs | Older audits and design notes discuss Workflow/Fantasy/Author migration history. | Preserve as historical unless they compete with current instructions; add archive/supersession stamps only where needed. |

## Migration Principles

1. Public brand first: website, README, app/listing metadata drafts, and user-facing docs move before imports.
2. Compatibility is temporary: every `Workflow`/`workflow` alias needs a removal gate, not indefinite coexistence.
3. No blind replacement: each occurrence gets classified by surface and risk.
4. No runtime cutover without proof: package/env/path changes need import smoke, packaging mirror, deploy canaries, DR proof where relevant, and chatbot-surface tests when connector behavior changes.
5. Historical record stays readable: old docs can keep old names when they are clearly historical.
6. Host-memory boundary stays intact: Tiny persona copy must preserve the anti-collision contract from Brain v2 and universe-personification review.

## Recommended Replacement Defaults

| Old surface | Replacement default |
|---|---|
| Product/platform name `Workflow` | `TinyAssets` |
| Acting intelligence/persona | `Tiny` |
| GitHub repo `Jonnyton/Workflow` | `Jonnyton/TinyAssets` or `Jonnyton/tinyassets`; prefer exact GitHub repo casing decision before cutover. |
| Python distribution `workflow` | `tinyassets` |
| Python import `workflow` | `tinyassets` with a temporary migration adapter only if required for external installs. |
| CLI `workflow-*` | `tinyassets-*` |
| Env prefix `WORKFLOW_*` | `TINYASSETS_*` |
| Paths `/etc/workflow`, `/opt/workflow` | `/etc/tinyassets`, `/opt/tinyassets` |
| Docker volumes/services `workflow-*` | `tinyassets-*` |
| MCP server/listing `workflow-universe-server` | `tinyassets` or `tinyassets-mcp`; final shape depends on host directory constraints. |

## Open Decisions

1. GitHub repo casing: `TinyAssets` vs `tinyassets`.
2. Connector display: recommendation is `TinyAssets`; Tiny appears in persona responses after a universe/persona binding.
3. Compatibility style under the project's no-shims posture: either explicit short-lived adapters with warnings and removal tests, or a breaking cutover with migration tooling. Runtime slices must choose one per surface.
4. Whether old MCP registry IDs can be redirected/deprecated in-place or require a second listing.

## Acceptance

The rename is complete only when:

- No active public/user-facing product surface brands the platform as `Workflow`.
- New installs use TinyAssets package/config names.
- Existing installs have a tested migration path or a documented breaking cutover.
- Live ChatGPT/Claude connector tests invoke TinyAssets and receive Tiny persona behavior only when authorized/bound.
- Post-cutover traces show clean user use or STATUS.md keeps a watch item until first-user evidence exists.
- `Workflow` remains only in historical documents or removed compatibility paths, with no active runtime dependency.
