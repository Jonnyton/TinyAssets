# Project Lineage

TinyAssets is the current project. It grew out of a sequence of earlier systems that started with AI-assisted long-form fiction and gradually became a general engine for inspectable, branchable AI work.

## Short Version

Fantasy Author and Fantasy Writer were the first hard testbed. They used story generation because long-form fiction forces an AI system to deal with continuity, memory, evaluation, revision, source truth, and long-running state. As those pieces became more general than fiction, they were extracted into TinyAssets.

TinyAssets is the generalized system: live MCP tooling, branchable workflows, wiki/community feedback, gates, patch planning, and agent-team execution patterns.

## Timeline

### 0. Physical Hex Board Game And Worldbuilding Roots

Before the current coding projects, there was a physical hex-board game idea: cardboard hexagon terrain tiles and a Civilization-like board-game layout.

That idea later reappeared as computer prototypes in Electron/TypeScript and Godot, and parts of the systems/mythology fed into Echoes of the Cosmos.

What carried forward:

- terrain/world-system thinking
- strategy and civilization-scale mechanics
- interest in shared worlds that people can extend

Recommended public form:

- `hex-strategy-lab` as a clean product-iteration repo
- clearly marked as an older root, not the current AI-workflow product

### 0.5. Echoes Of The Cosmos

Echoes of the Cosmos is an open science-fantasy universe project. It has an early Reddit surface and local canon material, and it should eventually become a TinyAssets-hosted community universe.

What carried forward:

- open universe / community contribution model
- hard-science and canon-consistency constraints
- Reddit as an early community contribution surface
- AI-readable canon/source material for writers and agents
- the need for a live state where contributions can be reviewed, reconciled, and promoted

Recommended public form:

- standalone public universe repo
- domain-world entry in the portfolio graph
- future clean TinyAssets universe, not attached to an old test universe
- honest wording that the current community surface is early/thin and being refactored

### 1. Recursive Science Fantasy

Early experiment around autoresearch-style loops for writing systems.

What carried forward:

- proposal / evaluation / revision loops
- treating output quality as something that can be measured and improved
- early separation between generator behavior and evaluator behavior

Public status: currently visible as `Jonnyton/Recursive-Science-Fantasy`.

### 2. Fantasy Writer

Desktop/background writing daemon with tray/dashboard UX, universe scaffolds, source canon, and repeated PLAN / DRAFT / CHECK / REVISE loops.

What carried forward:

- long-running daemon model
- typed source ingestion and source memory
- multi-model judge/evaluation patterns
- inner loop and outer loop separation
- local state, logs, tests, and runtime artifacts as durable memory
- the idea that "the process gets better" matters more than a single generated output

Local evidence:

- local repo has 1012 commits
- substantial tests and changelog
- docs around source canon, learning loops, and multi-agent development

Recommended public form:

- sanitized `TinyAssets` branch: `legacy/fantasy-writer`
- branch README should mark it as an archived ancestor, not the current product

### 3. Fantasy Author

More explicit architecture pass that reframed the writing system as a benchmark for durable, tool-using, self-improving agent workflows.

What carried forward:

- PLAN / STATUS / AGENTS separation
- branch-first collaboration
- public action ledger concepts
- notes as durable feedback
- generator / evaluator / ground-truth separation
- multiplayer and named-author substrate concepts
- the thesis that fiction was the test, not the final abstraction

Local evidence:

- local repo has 88 commits
- `PLAN.md` directly describes the broader workflow-system thesis
- `STATUS.md` records design concerns, work queues, and verified fixes

Recommended public form:

- cleaned snapshot branch: `legacy/fantasy-author`
- branch README should state that TinyAssets was extracted/generalized from this system
- full raw history should not be published unless history cleanup passes, because local scan found credential material in historical status commits

### 4. TinyAssets

Current generalized project.

What is live or implemented:

- public MCP endpoint at `https://tinyassets.io/mcp`
- Python/FastMCP workflow-builder architecture
- wiki/community bug reporting
- branch and gate tooling for patch planning
- coding-team workflow scaffolding
- packaging work for MCPB / Claude plugin use

What is still under construction:

- full recursive community patch loop from bug report to patch packet to coding-team PR automation
- broader hosted marketplace/runtime behavior
- token utility integration beyond roadmap/scaffolded design

## Recommended GitHub Shape

Keep `TinyAssets/main` focused on the current product.

Add lineage links:

- `docs/project-lineage.md` on `main`
- `legacy/fantasy-writer` branch after secret/history cleanup
- `legacy/fantasy-author` cleaned snapshot branch, or rewritten history after credential cleanup

Avoid merging old project folders directly into `main`. The old systems are valuable as ancestry, but the default branch should stay easy for a recruiter to inspect.

## Honest Wording

Use:

> TinyAssets evolved from earlier Fantasy Author and Fantasy Writer systems. Those projects began as long-form AI writing daemons and became experiments in durable state, retrieval, branchable agent workflows, evaluation gates, and write-back learning. TinyAssets is the generalized engine extracted from that work.

Avoid:

> TinyAssets has always been one continuous codebase.

The relationship is real, but it is a lineage/extraction relationship, not one uninterrupted repository from day one.
