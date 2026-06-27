# TinyAssets Hard Rename

Status: accepted direction, in implementation
Date: 2026-06-27
Owner: codex-gpt5-desktop

## Decision

`Workflow` was a temporary engineering name from the discovery phase. The project is cutting over now; it is not a transitional, legacy, or compatibility brand.

The canonical boundary is:

| Term | Meaning | Not this |
|---|---|---|
| `Tiny` | The acting personification users and developers interact with: the intelligence shaped as an extension of the founder's will. | The repo, legal/product listing, package, website, or platform brand. |
| `TinyAssets` | The website, platform, GitHub/repository, distribution, package, connector/app listing, and OSS project brand. | The first-person acting persona. |
| `workflow` as common noun | A plain-English process or graph of work when literally describing user work. | A namespace, product, connector, package, repository, or platform name. |

Current active surfaces must use `TinyAssets` for the platform and `Tiny` for the acting persona. `Workflow` as a product/repo/package/connector name is retired.

## Cutover Scope

This is a breaking rename, not a staged coexistence plan.

- GitHub repository: `Jonnyton/Workflow` -> `Jonnyton/TinyAssets`.
- Python distribution and import package: `workflow` -> `tinyassets`.
- CLI and GUI entry points: `workflow-*` / `workflow` -> `tinyassets-*` / `tinyassets`.
- Public website, README, app/listing metadata, registry metadata, and brand assets use TinyAssets.
- Deployment paths, services, env vars, Docker labels, volumes, and operator docs use TinyAssets naming.
- Connector-facing prompts say TinyAssets; Tiny appears as the persona only where the product is speaking/acting.

Historical artifacts may still mention the old name when they are clearly old records. They must not act as current instructions.

## Replacement Defaults

| Old surface | Replacement |
|---|---|
| Product/platform name | `TinyAssets` |
| Acting intelligence/persona | `Tiny` |
| GitHub repo | `Jonnyton/TinyAssets` |
| Python distribution/import | `tinyassets` |
| CLI | `tinyassets-*` |
| GUI command | `tinyassets` |
| Env prefix | `TINYASSETS_*` |
| Data/config paths | `/etc/tinyassets`, `/opt/tinyassets`, `~/.tinyassets`, `%APPDATA%\\TinyAssets` |
| Docker/service names | `tinyassets-*` |
| MCP bundle/listing | `tinyassets-universe-server` unless a host directory requires a different slug |

## Verification Bar

The hard rename is complete when:

- Current public/user-facing surfaces do not brand the product as `Workflow`.
- New installs clone, configure, import, run, and connect via TinyAssets names.
- Import smoke and packaging/plugin probes load `tinyassets.*`.
- Website checks and rendered browser proof pass after copy and asset updates.
- The GitHub repo and local remote point at `Jonnyton/TinyAssets`.
- Any remaining old-name occurrence is either ordinary English or a clearly historical record.
