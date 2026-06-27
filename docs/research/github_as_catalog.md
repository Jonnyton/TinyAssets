# GitHub as Catalog

Reference for the git-native community model: GitHub holds the canonical shared state, every user clones and runs locally, contributions flow through PRs. No hosted multi-tenant runtime, no custom auth, no central DB. Items marked **unconfirmed** need a live verification pass before commitment.

## 1. Prior-art patterns

| Pattern | What's git-tracked | Contribution flow | Fit | Migration effort |
|---|---|---|---|---|
| **Homebrew formulae** (`Homebrew/homebrew-core`) | One Ruby file per package under `Formula/`. Hard schema enforced by class. CI validates on PR. | Fork → edit one file → PR. Bot-assisted bumps. | Strong fit conceptually — flat per-artifact files, tight schema, automated validation. Scales to ~7k formulae. | Low — directory-per-Goal mirrors `Formula/` |
| **Nixpkgs** | One Nix expression per package, deeply nested under `pkgs/by-name/`. CI builds every PR. | PR-based, heavy review. | Higher complexity than we need; nested-by-name pattern is interesting for scale. | Medium |
| **Jekyll/Hugo themes** (`jekyll/jekyll-theme-*` repos) | Each theme is its own repo; index repo lists them. | Submit listing PR; theme stays in author's own repo. | Federation pattern — index + sovereign author repos. Good if Branches grow large; overkill if they're small YAML. | Medium |
| **Awesome-* lists** | One Markdown file with curated links. | PR adds a line. | Closest to "minimum viable catalog." Good for the public landing page. | Trivial |
| **LangChain Hub / `langchain-ai/langchain` templates** | `templates/<name>/` with code + README + pyproject. | PR-based. | Direct precedent for "agent workflow templates as community contributions." Worth mirroring directory shape. **Unconfirmed:** current discoverability surface (the standalone Hub product moved/closed). |
| **Obsidian community-plugins / community-themes** | `community-plugins.json` is one big JSON registry. Plugin code stays in author's repo. | PR adds a line to the registry; Obsidian fetches and indexes. | Cleanest "git as registry, code stays sovereign" pattern. Strong fit for Branches authored across many repos. |
| **dbt Hub / packages.yml** | Per-package `packages.yml` lists git refs; `hub.getdbt.com` indexes via daily crawl. | Author submits package metadata; central crawler picks up. | Same federation shape as Obsidian. Demonstrates a thin always-on indexer over sovereign repos. |
| **BettaFish** | Per `docs/bettafish-refactor-research-2026-04-09.md` — file-based shared state, framework-minimal. Doesn't address community contribution flow. | — | Validates the file-first instinct, not the catalog shape. |

**Recommendation profile.** Start in the Homebrew/awesome shape (single repo, flat per-Goal directories, PR-reviewed). When Branches grow large or get binary assets, evolve toward Obsidian/dbt federation (registry of pointers + sovereign author repos). The first shape is one decision away from the second; don't over-engineer day one.

## 2. Storage layout

| Layout | Phone-legibility | Diff-friendliness | Pros | Cons |
|---|---|---|---|---|
| **YAML files, flat by Goal** (`goals/<slug>/goal.yaml`, `goals/<slug>/branches/<slug>/branch.yaml`, `goals/<slug>/branches/<slug>/nodes/<slug>.yaml`) | Strong | Strong (line-oriented diffs) | Easy to read, easy to PR-review, easy to grep. Schema-validatable with JSON Schema. | YAML's whitespace traps; multi-line prompts get awkward. |
| **JSON files** | Weak (braces noise) | Medium (formatter-sensitive) | Direct mapping from current `branches.py` dataclasses. No serializer surprises. | Phone-hostile in PR diffs; comments not allowed. |
| **Markdown + YAML frontmatter** (`goals/<slug>/branches/<slug>.md` with frontmatter for structured fields, body for human description) | Strongest | Strong | Mixes structured config with human prose; renders nicely on GitHub. | Two-format parsing; structured fields constrained to frontmatter scope. |
| **Nested-by-author** (`goals/<slug>/branches/<author>/<slug>/`) | Medium | Strong | Authorship visible in path; collision-free namespacing. | Path duplication when forking; harder to find "all branches for goal X". |

**Recommendation.** Markdown + YAML frontmatter for Goals and Branches (these have meaningful prose: premise, intent, README). Pure YAML for Nodes (mostly structured; occasional prompt body in a `|` literal block). Flat directories keyed by slug for v1, with an `author:` field in frontmatter; promote to nested-by-author only if collisions become noisy.

**Drafts.** `.gitignore` `drafts/` and `*.draft.{yaml,md}`. The MCP `build_branch` action writes to `drafts/` by default; an explicit `publish` action moves the file out of `drafts/` and stages it. This keeps experiments off the main branch without forcing every keystroke into git.

## 3. MCP-action-to-git bridge

| Pattern | Auto-commit? | Complexity | When to use |
|---|---|---|---|
| **Tool writes file, returns "edit complete"** | No | Trivial | Drafts. User runs `git status` themselves. |
| **Tool writes + auto-stages, never commits** | Half | Low | Default for working changes. User commits in their own cadence. |
| **Tool writes + commits with conventional message** | Yes | Low–Medium | `publish_branch`, `accept_node_revision` — semantically discrete user intents. |
| **Tool writes + commits + pushes + opens PR** | Yes | Medium | Explicit `share_branch` / `submit_to_community` action. |

**Recommendation.** Three-tier vocabulary:
- **Draft actions** (`build_branch`, `update_node`) → write to `drafts/`, no git. Phone-friendly, no commit ceremony.
- **Local accept actions** (`publish_branch`, `commit_my_work`) → move out of `drafts/`, `git add` + `git commit` with a structured message ("workflow: publish branch <slug>"), no push.
- **Share actions** (`share_branch`, `open_pr`) → push current branch, open PR via GitHub API, return URL.

Prior art for git-over-MCP wrappers is thin: Anthropic's `mcp-server-git` reference server exposes low-level git plumbing (status/diff/log/commit), not domain-level "publish a workflow" verbs. Useful as a baseline; we'd build the domain verbs on top. **Unconfirmed:** any third-party MCP server bundling GitHub PR creation as a single tool call.

## 4. Discovery via git — what we lose vs gain

| Current (SQLite) | Git-native replacement | Net change |
|---|---|---|
| `ledger` table of all writes | `git log` of the catalog repo | **Gain:** signed, immutable, GitHub-rendered. **Lose:** sub-second indexed query — `git log` is linear scan. Mitigate with periodic JSON snapshot under `index/`. |
| `NodeDefinition.author` field | `git blame` + commit author | **Gain:** verified via GitHub identity. **Lose:** authorship lookup costs a blame call; cache in frontmatter. |
| `search_nodes` action backed by SQLite FTS | GitHub code search API + local grep | **Gain:** zero infra. **Lose:** rate limits (GitHub: 30 search/min unauthed, 5k/h authed); semantic search (would need local embeddings on cloned tree). |
| Outcome-gate storage (Phase 6) | GitHub Issues + labels per Goal | **Gain:** UI exists, notifications free, cross-references easy. **Lose:** structured queries — must use Issues API or a periodic export. |
| PR / review system | GitHub PRs natively | **Gain:** review tooling exists. **Lose:** bot-driven auto-merge needs explicit GitHub Actions setup. |
| Schema validation | GitHub Actions running JSON Schema validator on PR | **Gain:** review-time enforcement, public CI badge. **Lose:** instant local feedback unless we also ship a `pre-commit` hook. |
| Branch fork lineage | `lineage:` frontmatter field + git history | **Gain:** human-readable. **Lose:** transitive lineage queries cost a graph walk; cache an `index/lineage.json`. |

**Net:** for a community-scale catalog (hundreds to low thousands of artifacts), git wins on operability, transparency, and zero-infra cost. The lost capabilities (sub-second search, transitive queries) are recoverable by periodically generating snapshot indexes under `index/` from a GitHub Action.

## 5. Sync cadence and conflicts

- **Default:** `git pull` on TinyAssets MCP server start; manual `pull_latest` MCP action thereafter. Daemon does NOT auto-pull mid-run (avoids surprise mutations during agent execution).
- **Drift detection:** before `share_branch` opens a PR, auto-fetch and warn if upstream advanced.
- **Conflicts:** drafts live in untracked `drafts/`, so user drafts cannot collide with upstream. Published artifacts live under per-author paths or use slug-collision detection at PR time. Real merge conflicts are rare in this layout (one file per artifact, one author per file).

## 6. Fork-and-remix

Heavy fork (whole repo): the GitHub default. Friction-rich for users who only want one Branch.

Light fork (recommended): an MCP `fork_branch` action that copies the source file into the user's draft area with `lineage: <source-slug>@<commit>` in frontmatter, opens it for editing. `share_branch` later submits the variant back to the catalog repo as a PR adding a new file under the user's namespace. The heavy fork is reserved for users who want to maintain their own catalog.

## 7. Always-on demo

`tinyassets.io/mcp` stays as a single shared demo TinyAssets MCP server — read-only-ish (allows building drafts, blocks `share_branch`/`open_pr`). Cloudflare Tunnel + the host's machine; if the host is offline, demo is offline (acceptable since the real product is "clone and run"). Landing page (static, served via GitHub Pages from the catalog repo) explains "try the demo OR clone in 3 commands."

## 8. Open questions for planner

1. One catalog repo or split (Goals separate from Branches separate from Nodes)? Single repo is simpler; splits help when one component scales differently.
2. Markdown+frontmatter vs pure YAML — does the readability win on GitHub justify the two-format parser?
3. GitHub OAuth as the only auth, or also accept anonymous PRs from non-GitHub-users? Anonymous PRs are GitHub-impossible; non-GitHub contribution would need a separate intake.
4. CI gate strictness on PR — full graph compilation + schema validation + lint, or schema only? Stricter CI = higher contributor friction.
5. License — MIT for the engine is settled; what license for community-contributed Branches? CC-BY-SA, MIT, public domain, or per-Branch in frontmatter?
6. Snapshot-index cadence (`index/*.json` for fast lookup) — GitHub Action on every merge to main, or daily? Trade-off: freshness vs PR noise.
7. How does the local TinyAssets MCP server know which catalog repo to pull from? Hardcoded `TinyAssets/catalog`, or configurable via `TINYASSETS_CATALOG_REPO` env? (Configurable enables alternative catalogs / private forks.)
