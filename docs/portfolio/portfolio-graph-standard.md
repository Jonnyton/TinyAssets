# Portfolio Graph Standard

Goal: make the public GitHub portfolio maintain itself as projects evolve.

Every project should carry a small manifest that tells AI agents how the project fits into the larger story. Agents update the manifest when they start, resume, archive, or meaningfully change a project.

## Manifest File

Recommended filename:

```text
PROJECT_GRAPH.yml
```

## Example

```yaml
project:
  name: Hex Strategy Lab
  slug: hex-strategy-lab
  status: archived
  public_visibility: public-ready
  portfolio_role: ancestor
  primary_repo: https://github.com/Jonnyton/hex-strategy-lab

summary:
  short: Physical and digital hex strategy game lineage that later fed Echoes and TinyAssets.
  current_state: Archived learning/project-iteration artifact.
  public_pitch: Shows product iteration from tabletop idea to Electron/Godot prototypes.

lineage:
  preceded_by: []
  evolved_into:
    - echoes-of-the-cosmos
  influenced:
    - fantasy-agent-workflow-lab
    - workflow
  related:
    - Echoes of the Cosmos

evidence:
  local_paths:
    - C:\Users\Jonathan\Projects\Hex
    - C:\Users\Jonathan\Projects\HexConquest
  public_links: []
  live_links: []

skills:
  languages:
    - TypeScript
    - GDScript
  systems:
    - Electron
    - Godot
  themes:
    - game state
    - UI iteration
    - strategy systems

maintenance:
  update_profile_readme: true
  update_workflow_lineage: true
  safe_to_auto_publish: false
  requires_human_publish_gate: true
```

## Default Visibility

Default policy:

```yaml
public_visibility: public-draft
maintenance:
  default_visibility_policy: public_until_marked_private
```

Projects are assumed public-facing unless they are explicitly marked private or blocked.

Examples that should be private unless deliberately sanitized:

- OpenClaw conversation memories
- NemoClaw private memory/state
- provider credentials
- private account config
- unpublished personal notes
- generated content not intended for public canon

## Portfolio Roles

Use one:

- `flagship`: current main project
- `ancestor`: older project that evolved into a current project
- `supporting-tool`: reusable tool/scaffold that supports the main work
- `domain-world`: creative/worldbuilding domain that runs inside TinyAssets
- `product-iteration`: product/game/app experiment
- `research-bridge`: research/prototype that influenced another project
- `archive`: public historical artifact with limited active development

## Status Values

Use one:

- `active`
- `paused`
- `archived`
- `planned`
- `private`
- `deprecated`

## Visibility Values

Use one:

- `public-ready`
- `public-draft`
- `private`
- `needs-scan`
- `blocked-sensitive`

## Required Agent Behavior

When an AI agent starts work in any project, it should:

1. Look for `PROJECT_GRAPH.yml`.
2. If missing, create a draft from the repo/folder context.
3. Check whether the current work changes the project's role, status, lineage, or public summary.
4. Update the manifest when needed.
5. If the project is connected to TinyAssets, update or queue a note for the central portfolio index.
6. Default to public-draft for ordinary project work, but mark private or blocked-sensitive for memories, credentials, private conversations, or unclear source/licensing.
7. Never mark `safe_to_auto_publish: true` if secrets, private data, generated private content, or unclear licensing might be present.

## Central Index

Recommended central file:

```text
portfolio-index/projects.yml
```

Each project manifest can be copied or summarized there. A generator can build:

- GitHub profile README
- TinyAssets `docs/project-lineage.md`
- project index page
- pinned repo descriptions
- website project sections

## Auto-Maintenance Flow

```text
project changes
  -> agent updates PROJECT_GRAPH.yml
  -> local scan/generator updates portfolio-index
  -> profile README and lineage docs regenerate
  -> publish gate checks sensitive data and visibility
  -> approved public changes push to GitHub
```

## Publishing Gate

Auto-maintenance should not mean reckless auto-publishing.

Safe automation:

- update local manifests
- update local portfolio drafts
- update public docs in an already-public active repo if the repo is already safe
- open a PR or staged branch

Human-gated:

- making a private project public
- creating a new public repo
- pushing old history
- publishing generated creative content
- publishing anything with unclear source/licensing

Default-public does not bypass the publish gate. It only means the project should be shaped as if it may eventually be public unless explicitly marked private.

## Standard Prompt For Future Agents

Add this to project instructions:

> This project participates in Jonathan's portfolio graph. Before changing public-facing docs, project status, repo structure, or lineage, inspect `PROJECT_GRAPH.yml`. If the change affects how the project should appear publicly, update the manifest and any central portfolio index entry. Keep claims honest: distinguish live, prototype, archived, planned, and private work. Do not publish or mark public-ready until scans and the publish gate pass.
