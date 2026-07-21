---
status: active
---

# Classic-Game Restoration Branch (Pre-Draft Spec)

**Date:** 2026-04-30
**Author:** codex-gpt5-desktop
**Status:** Live v0 branch created through MCP. Community-built branch/domain workflow. No new platform primitive approved.

## 0. Live MCP Proof

Created through the live Workflow MCP controls on 2026-04-30:

- Goal: `62f977e7ff0c` — `Play classic games on modern computers`
- Branch: `cc727837fe8a` — `classic_game_restoration_v0`
- Branch shape: 8 nodes, 9 edges, 20 state fields
- Published branch version: `cc727837fe8a@0fac969d`
- Goal canonical set to: `cc727837fe8a@0fac969d`

Important caveat: live `extensions action=get_branch` returns the full branch
topology, but live `extensions action=get_branch_version` for
`cc727837fe8a@0fac969d` returns an empty `graph_nodes` / `edges` snapshot.
Filed as BUG-037 (`extensions.publish_version`). Until fixed, users should
fork/read from the live `branch_def_id` `cc727837fe8a`, not from the canonical
version snapshot.

Local code patch added 2026-04-30: `workflow/branch_versions.py` now normalizes
DB-row branch shapes before content-addressing, with regression coverage in
`tests/test_publish_version.py`. Verification:
`python -m pytest tests/test_publish_version.py tests/test_branch_versions_rollback_columns.py tests/test_canonical_branch_mcp.py -q`
→ 66 passed. Live MCP still needs redeploy before BUG-037 is closed.

## 1. Objective

Build a Workflow branch that lets a user say, in a chatbot, roughly:

> I want to play an old game I used to play. I do not remember the exact title.

The chatbot uses Workflow to identify the likely game, find legal public/free sources or user-owned media paths, prepare a modern-system install/patch plan, ask for approval, install locally, create a desktop icon, and launch the game.

Success means the user only had to describe the remembered game and approve the local action. The branch handles discovery, compatibility, installation, launcher creation, and verification.

## 2. Assumptions

1. This is a user/community branch or domain workflow, not platform core.
2. Local installation/play requires a local-app capability tier. Browser-only users can author the request and inspect the plan, but cannot install/play on a machine until a local host grants capability access.
3. The first MVP targets Windows because the existing shortcut helper is Windows-only; the spec keeps macOS/Linux as required design targets.
4. "Free old games" means legally available material only: public domain, open source, freeware with redistribution rights, official free releases, demos where license allows, source ports with user-provided assets, or user-owned media supplied by the user.
5. The branch must fail closed when provenance, license, checksums, or OS compatibility are unclear.

## 3. User Flow

1. User describes a remembered game: era, platform, genre, visuals, characters, music, publisher, place they played it, or fragments of title.
2. Branch runs web discovery over public sources and returns candidate titles with evidence.
3. User/chatbot selects or narrows the candidate.
4. Branch checks legal acquisition paths and compatibility options for the user's OS/CPU/GPU.
5. Branch produces a dry-inspect plan: source URLs, license/provenance, binaries/assets, patches/emulators/source ports, install path, desktop icon, expected disk/network/admin permissions.
6. Chat asks for explicit allow.
7. Branch downloads or imports user-owned media, verifies checksums/signatures where available, applies patches/config, creates launcher/shortcut, and starts the game.
8. Branch records what was installed, where, provenance evidence, rollback/uninstall instructions, and launch verification.

## 4. Branch Topology

Suggested node chain:

| Node | Purpose |
|---|---|
| `memory_intake` | Convert vague user recollection into searchable facts and unknowns. |
| `web_game_discovery` | Search public web sources, catalogs, forums, archives, publisher pages, source-port registries, and preservation databases. |
| `candidate_resolver` | Rank likely titles with citations and ask clarifying questions only when needed. |
| `provenance_license_check` | Confirm legal availability, redistribution/install rights, asset ownership requirements, and source trust. |
| `host_capability_check` | Inspect OS, CPU arch, GPU basics, available runtimes/emulators, install permissions, and user policy. |
| `compatibility_plan` | Choose native installer, source port, compatibility layer, emulator, DOSBox/ScummVM-style runtime, patch set, or user-media import path. |
| `dry_inspect_install` | Produce an auditable install plan and risk list before touching the machine. |
| `approved_acquire_and_patch` | After approval, fetch/import, verify, patch, configure, and install. |
| `launcher_create` | Create desktop/start-menu launcher using platform helpers. |
| `launch_verify` | Start the game, check process/window/log evidence, and report success or failure. |
| `rollback_record` | Persist install manifest, provenance, checksums, patch notes, and uninstall steps. |

## 5. Existing Platform Fit

This branch should compose from existing/accepted platform ideas:

- MCP remains the conversation control station; Workflow does the work.
- Branch/node/run primitives carry the workflow.
- `external_tool_node` and `required_capabilities` are the correct seam for local installers, emulators, source ports, patchers, archive tools, and launchers.
- Host approval gates guard downloads, installers, local execution, desktop icon creation, and any admin-elevation request.
- Discovery, wiki, branch remix, and public commons let the community improve per-game recipes over time.
- `workflow/desktop/create_shortcut.py` proves the Windows shortcut path exists today, but a cross-platform launcher abstraction is still needed for full MVP.

## 6. Boundaries

Always:

- Record source URL, license/provenance claim, checksum/signature evidence when available, install location, and launcher target.
- Ask for explicit approval before download, install, patch, local execution, desktop icon creation, or admin elevation.
- Prefer official sources, open-source engines, source ports, and preservation projects with clear legal terms.
- Keep user-owned media local unless the user explicitly publishes a derivative recipe without assets.
- Provide rollback/uninstall instructions.

Ask first:

- Any admin/elevation request.
- Installing third-party runtimes, emulators, drivers, compatibility layers, or package managers.
- Using user-owned disk images, ROMs, ISOs, CDs, save files, or account credentials.
- Publishing a per-game recipe to the commons.

Never:

- Download or facilitate pirated, cracked, warez, or "abandonware" copies without a clear legal right.
- Bypass DRM, copy protection, license checks, or account gates.
- Hide installer side effects or run unknown binaries without provenance and approval.
- Treat web search snippets as license proof.
- Claim a game is installed/playable without launch evidence.

## 7. MVP Acceptance Criteria

1. Given a vague game description, the branch returns 3-5 candidates with cited evidence and asks at most one clarifying question before ranking.
2. Given a selected candidate with a legal free/source-port path, the branch emits a dry-inspect install plan with provenance, required capabilities, side effects, and rollback.
3. After approval, the branch installs one test game on Windows, creates a desktop launcher, starts it, and records launch evidence.
4. If legal provenance is unclear, the branch refuses acquisition and offers legal alternatives: official page, source port requiring user-owned assets, demo, modern remake, or "cannot proceed."
5. If the host lacks required software/capability, the branch returns a concrete missing-capability report instead of improvising.

## 8. Test Strategy

- Unit tests for candidate ranking envelopes, provenance status classification, install-plan schema, and refusal cases.
- Fixture-based discovery tests with static HTML/search-result snapshots so tests do not depend on live web results.
- Windows integration test using a tiny legal fixture game or local dummy executable to verify install manifest + desktop shortcut + launch detection.
- Negative tests for "abandonware"/crack/DRM-bypass requests.
- Final public-surface acceptance, when MCP behavior changes, must use live Claude.ai `ui-test` with the installed Workflow connector and include post-change clean-use evidence if available.

## 9. First Implementation Slice

No platform code should start until this spec is reviewed. The smallest useful build slice is:

1. Define the branch recipe and typed artifacts:
   - `GameCandidate`
   - `ProvenanceReport`
   - `HostCapabilityReport`
   - `InstallPlan`
   - `InstallManifest`
2. Implement dry-inspect only with static discovery fixtures.
3. Add one legal tiny/dummy install fixture that proves launcher creation without downloading a real commercial game.
4. Only then add real web discovery and real game recipes.

Likely files after approval:

- `domains/classic_games/` or equivalent domain package, once domain registration is ready.
- `docs/specs/2026-04-30-classic-game-restoration-branch.md`
- tests under a narrow new `tests/test_classic_game_*` surface.
- launcher helper extensions under `workflow/desktop/` only if a reusable cross-platform abstraction is needed.

## 10. Open Questions

1. Should the first real proof target a public-domain/open-source game, an official freeware game, or a source-port-with-user-assets flow?
2. Should per-game install recipes live first as wiki pages, branch nodes, or package-style manifests inside the branch?
3. Is cross-platform launcher creation a platform primitive now, or can the first branch recipe keep it Windows-only until the domain proves value?
4. Which web sources are acceptable for discovery/provenance, and which are search-only hints that require stronger confirmation?
5. What is the visible chatbot wording for the approval card so users understand source, rights, side effects, and rollback before hitting allow?
