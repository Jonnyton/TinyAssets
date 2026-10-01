# Stop committing the plugin mirror: build it at release (design, 2026-10-01)

**Status:** proposed, for lead review. Not built.
**Founder prompt (2026-10-01):** an hour of tests per PR "may even be enforcing
bad architecture". The plugin mirror is the largest single duplicated truth in
the repo: the same code committed twice.

## What exists

- **The mirror itself.** `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/`
  holds 542 tracked files. 536 of them, under `runtime/tinyassets/`, are a byte
  copy of `tinyassets/` staged by
  `packaging/claude-plugin/build_plugin.py`.
- **Three gates keep it in step:**
  - `mirror-parity` (in the required `invariants` check, through
    `scripts/check_mirror_parity.py`);
  - the `pre-commit` hook (`scripts/git-hooks/pre-commit` §2);
  - the "committed plugin runtime is stale" step in `build-bundle.yml`.
- **Cost, measured:** **284 of the 520 commits since 2026-09-01 (55%) touched the
  mirror.** Every `tinyassets/` edit is two edits.
- **Universes cannot ship a one-file change** through the Contents API, because the
  mirror makes it two files (`docs/concerns/2026-08-28-the-agent-shippable-file-is-mirrored.md`).
- **Concurrent builds deleted tracked mirror files** (#4195 adds a build lock).
- **`pr-scope-guard`'s authority regex** has to name both trees.
- **The MCPB bundle already uses the target shape.** `packaging/mcpb/build_bundle.py`
  stages into the ignored `packaging/dist/` and packs a `.mcpb` only on a GitHub
  release (`build-bundle.yml` `pack-mcpb`). Nothing of it is committed.

## Who actually consumes the committed mirror

Verified 2026-10-01:

- **No working install path reads it from GitHub.** `/plugin marketplace add
  owner/repo` reads `.claude-plugin/marketplace.json` at the repo root, and that
  file does not exist (`gh api .../contents/.claude-plugin` returns 404). The
  marketplace manifest sits at `packaging/claude-plugin/.claude-plugin/`, which
  only a local clone can add by path. A clone can run `build_plugin.py` first.
- **There is no published plugin or `.mcpb` release.** The only releases are
  Android debug builds. `packaging/registry/server.json` points at a
  `v0.1.0/...mcpb` asset that its own doc calls a draft
  (`docs/distribution_validation.md`).
- **No documentation tells a user to install the plugin.** `grep "marketplace
  add"` finds only a strategy note listing marketplace submission as a todo.
- **In-repo readers:**
  - `tests/test_packaging_build.py`, `tests/test_mirror_parity_gate.py`,
    `tests/test_pre_commit_mirror_parity.py` and `tests/test_invariants_framework.py`
    (mirror-parity cases);
  - `tests/test_fastmcp_pin_matches_runtime.py`, which compares the runtime
    `requirements.txt`. That file is outside `runtime/tinyassets/` and stays;
  - `pr-scope-guard.yml` `AUTHORITY_RE`;
  - `.gitignore` (the build lock).

So the committed copy guards a distribution path that does not work today. It
costs every commit.

## Design

1. **Untrack the generated tree.**
   - `git rm -r --cached packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets`.
   - Add that path to `.gitignore`.
   - Keep tracked what is not generated: `runtime/bootstrap.py`, `server.py`,
     `pyproject.toml`, `requirements.txt` and `models/`, the skills, `plugin.json`
     and `marketplace.json`.
2. **Delete the second definition's guards in the same PR.**
   - `scripts/invariants/mirror_parity.py` and `scripts/check_mirror_parity.py`, and
     their registration in `scripts/invariants_run.py`.
   - Pre-commit §2.
   - The `build-bundle.yml` staleness step.
   - Their tests.
   - The mirror half of `AUTHORITY_RE`.
   - `build_plugin.py`'s tracked-tree lock and swap machinery, which existed
     because the tree was tracked (#4195; coordinate, do not collide).
   - Hard rule in `AGENTS.md` § Testing ("After canonical `tinyassets/*` edits ...
     `build_plugin.py` (`mirror-parity` gates it)"): delete the line. The
     rulebook shrinks.
3. **Keep the build proven on every relevant PR.** `build-bundle.yml`
   `stage-and-probe` already runs `build_plugin.py` with its import probe. That
   step stays. It proves the plugin builds from the current `tinyassets/`,
   which is the property the mirror was standing in for.
4. **Publish from the build.** Add a `pack-plugin` job beside `pack-mcpb`, on
   `release: published`. It builds the plugin and publishes it in one of two ways:
   - **(a)** zip it as a release asset; or
   - **(b)** force-push the built plugin directory to an orphan `plugin-dist`
     branch carrying a root `.claude-plugin/marketplace.json`. Then
     `/plugin marketplace add TinyAssets/TinyAssets@plugin-dist` works. (I have not
     verified the `@ref` form against current Claude Code; a separate tiny
     `tinyassets-plugin` repo is the fallback.)

   **Recommend (b):** it is the only option that makes GitHub install work at
   all.
5. **Local developers:** `python packaging/claude-plugin/build_plugin.py` then
   `claude plugin validate packaging/claude-plugin`, as today. The tree is just
   no longer committed.

## Risks and how each is held

- **A release ships a plugin that does not import.** The import probe runs in
  `stage-and-probe` on every PR touching `tinyassets/**` or `packaging/**`, and
  again inside `pack-plugin`.
- **Someone relies on the committed tree.** Nobody found (above). If the
  founder knows of an install that does, it is a single-row host question
  before step 1.
- **A history-size bump.** It is one large deletion commit. The git history
  keeps the old copies, and nothing needs rewriting.

## Slice plan

One PR: 536 files untracked, roughly 10 hand-edited. Its review needs one Codex
refute, since it touches `invariants` (required) and `build-bundle.yml`.
After landing, run `docs/concerns/2026-08-28-...` resolution test: a universe
edits `request_theme.json` alone and goes green.
