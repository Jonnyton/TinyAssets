---
status: shipped
shipped_date: 2026-04-14
shipped_in: d79df2d  # Packaging Option 1: auto-build bundle + plugin from tinyassets/
---

# Packaging Mirror Decision

**Status:** Planner + Explorer co-authored design spike. Explorer contract-check evidence confirmed 2026-04-15.
**Related:** STATUS.md Concern "Packaging mirror (`packaging/`) stale vs live `tinyassets/`. Host: auto-built or hand-maintained?"
**Target surfaces:** `packaging/mcpb/`, `packaging/claude-plugin/`, `packaging/registry/`, plus docs referencing them.

## TL;DR

The packaging directory is not merely stale. It is **structurally broken**: the bundle source-of-truth points at a shim that can't run inside the bundle. Recommendation: **fix the pointer, auto-build both surfaces from `tinyassets/universe_server.py`, retire the manual mirror.** Confidence: high (85%).

## 1. Current contract

What `packaging/` exists for:

| Subdir | Purpose | Source of truth | Build mechanism | Consumer |
|---|---|---|---|---|
| `packaging/mcpb/` | Builds `tinyassets-universe-server.mcpb` — the MCPB extension artifact users install via Claude Desktop / compatible MCP hosts. | `build_bundle.py:32` copies from `fantasy_author/universe_server.py`. | `python packaging/mcpb/build_bundle.py --pack` | End users installing the MCP bundle. |
| `packaging/claude-plugin/` | Claude plugin marketplace package — validated with `claude plugin validate`. Per `docs/distribution_validation.md:6-14`. | Staged copy of `fantasy_author/universe_server.py` at `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/fantasy_author/universe_server.py`. | **No build script.** Hand-copied once. | Claude plugin marketplace submissions. |
| `packaging/registry/` | Generates `server.json` for MCP Registry submission per the official schema at `static.modelcontextprotocol.io/.../server.schema.json`. | Derived from the built `.mcpb` bundle (sha256 + version). | `python packaging/registry/generate_server_json.py` | MCP Registry listing at `io.github.jonnyton/tinyassets-universe-server`. |
| `packaging/dist/` | Build output. Not a source. | — | Produced by build scripts. | — |
| `packaging/conway/` | Speculative Conway panel metadata per INDEX.md. | — (experimental) | — | Future Conway UI. |

### The structural break

`fantasy_author/universe_server.py` is a **2-line shim**:

```python
"""Shim: use workflow.universe_server instead."""
from workflow.universe_server import *  # noqa: F401,F403
```

Both `packaging/mcpb/build_bundle.py:32` and the hand-copied `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/fantasy_author/universe_server.py` use this as the source. The MCPB bundle stages the shim inside `packaging/dist/tinyassets-universe-server-src/fantasy_author/universe_server.py` — **but does not include the `tinyassets/` package the shim imports from.** When the bundle launches, the shim's `from workflow.universe_server import *` either (a) fails with ImportError because `tinyassets/` isn't in the bundle, or (b) silently resolves against the user's system Python if they happen to have this repo installed — a debug-only accident, not a distribution.

The docs at `docs/mcpb_packaging.md:15-22` still describe `fantasy_author/universe_server.py` as "the repository source of truth for the packaged server." That claim has been stale since the shim landed. The Phase 5 `c85efa1` commit is the last packaging touch; the shim was created after.

### Staleness vs drift

Explorer's 5–6-day staleness finding understates the damage. The shim migration (`scripts/build_shims.py:40-41`) landed ~2025-11-10. Both `packaging/dist/tinyassets-universe-server-src/fantasy_author/universe_server.py` (1406 lines, 2025-11-06) and `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/fantasy_author/universe_server.py` (1407 lines, 2025-11-06) are **pre-shim snapshots of the canonical server**. Timestamps (explorer-verified):

- Live `tinyassets/universe_server.py`: 9250 lines, 2025-11-12
- Live `fantasy_author/universe_server.py`: 2-line shim, 2025-11-10
- Staged `packaging/dist/...`: 1406 lines frozen at 2025-11-06
- `packaging/mcpb/manifest.json`: touched 2025-11-10 but not regenerated
- `packaging/dist/tinyassets-universe-server.mcpb`: built 2025-11-06

Nobody has rebuilt the bundle since the shim landed. If they did, it would break immediately — the staged shim has no `tinyassets/` package to import from and the staged `pyproject.toml` lists only `fastmcp`.

The currently-built bundle (pre-shim, Nov 6) still "works" as a frozen snapshot, but represents the MCP surface from before Phase D-H. Every Phase D/E/F/G/H tool/handler/invariant the team has shipped in four months is absent from the only installable artifact.

## 2. Options

### Option 1 — Retire the mirror, rewrite build to pull from `tinyassets/`

Fix `build_bundle.py` to copy from `tinyassets/universe_server.py` directly and bundle the full `tinyassets/` package. Delete the hand-copied claude-plugin runtime and replace it with a `build_plugin.py` that does the same staging. Update docs.

**Cost:**
- Rewrite `build_bundle.py`: ~30 LOC delta. Change source path, add `tinyassets/` tree copy (walk `tinyassets/` excluding `__pycache__`, `.db`, etc).
- New `build_plugin.py` for claude-plugin: ~60 LOC (mirrors `build_bundle.py` but targets `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/`).
- Delete `fantasy_author/universe_server.py` shim if no other consumer needs it. (**Verification required** — explorer to confirm no test/import depends on the shim.)
- Update `docs/mcpb_packaging.md` and `docs/distribution_validation.md`: ~20 LOC.
- Test: one-shot `build_bundle.py --pack`, run the bundle, confirm MCP tools expose current Phase H surface.

**Benefits:**
- Bundle actually works. Today's bundle is a latent break.
- Source of truth is the live file. Zero drift possible between commits.
- One less concept for readers: "what's `fantasy_author/universe_server.py`?" → nothing, it's gone.
- Releases become reproducible: run script, get artifact, sha256 matches.

**Risks:**
- Bundle size grows from ~1 file to ~50 files (workflow package). MCPB manifests handle this fine; `@anthropic-ai/mcpb` validator cares about manifest shape, not file count.
- Bundle now depends on the workflow package's transitive imports. If `workflow.universe_server` imports anything not available in the bundled Python env (`pyproject.toml` inside the bundle), bundle fails at runtime. Mitigation: the staging script should import-probe the staged bundle before packing (`python -c "from workflow.universe_server import *"` inside the stage dir) and fail loudly if it breaks.
- Daemon engine code (which may evolve faster than the MCP surface contract) now ships inside the extension. A new release cadence question — but an existing one we've been ignoring.

### Option 2 — Keep the mirror, add a freshness check

Keep `fantasy_author/universe_server.py` as a curated export surface (not a shim). Make `build_bundle.py` compare a hash of the curated file against the shim's re-export at build time; fail if drift detected. Humans maintain the curated file by hand.

**Cost:**
- Define what "curated export surface" means: which symbols, which tools, which not. ~1-2 days design work.
- Rewrite the shim as a curated re-export listing specific symbols: ~100 LOC maintenance burden per phase.
- Freshness check CI: ~50 LOC.
- Every Phase adds 1-3 tool surfaces; each requires curated-export update before landing.

**Benefits:**
- Bundle stays minimal in file count.
- Forces deliberate API-surface decisions ("is this daemon-internal or public MCP?").

**Risks:**
- **High maintenance tax.** Every phase that extends the MCP surface needs a second commit updating the mirror. Nobody has paid this tax since Phase 2-5, which is exactly why we're here. Reinstituting the tax without reinstituting the discipline fails in the same way.
- Two sources of truth is the class of bug PLAN.md's "mirrors drift; sources don't" principle avoids.

### Option 3 — Retire `packaging/` entirely

Stop shipping an MCPB bundle. Users install by cloning the repo. Delete `packaging/` and the docs pointing at it.

**Cost:**
- ~5 minutes (delete + commit).
- Docs update: ~20 LOC.

**Benefits:**
- Least complexity.
- Removes a concept that's been broken for months without anyone noticing — implying demand is low.

**Risks:**
- **Loses the distribution story.** MCP Registry listing at `io.github.jonnyton/tinyassets-universe-server` goes away. Claude plugin marketplace submission goes away. The "how do external users install this?" question has no answer.
- PLAN.md §Distribution And Discoverability is explicitly a principle. Retiring packaging contradicts it.
- If MVP launch is on the roadmap (I'd need to confirm with host — not a planner memory I have), this becomes an emergency rebuild later.

## 3. Comparison

| Dimension | Option 1 (auto-build) | Option 2 (freshness-check mirror) | Option 3 (retire) |
|---|---|---|---|
| LOC delta | ~+110, -40 (net +70) | ~+150 per phase forever | ~-200 |
| Bundle works today | Yes | Only if mirror hand-updated | N/A |
| Ongoing maintenance tax | Zero | ~1-3 hr / phase | Zero |
| Breaks distribution story | No | No | Yes |
| Matches PLAN.md principle | Yes (single source) | Partial (dual source) | No (discoverability) |
| Fail mode if neglected | N/A — auto-derived | Silent drift (today's state) | N/A |
| Rollback | Revert commit | Revert commit | Recover from git history |

## 4. Recommendation

**Option 1 — auto-build from `tinyassets/`, retire the mirror.**

Confidence: 85%.

Reasoning:
- The mirror has been broken for an entire release cycle without detection. This is a screaming signal that nobody is maintaining it — retention just relabels the problem.
- PLAN.md's own principle ("sources don't drift; mirrors do") was written for exactly this shape. Re-deriving always beats hand-sync.
- The bundle size / import-surface concerns for Option 1 are real but bounded — they're engineering problems with known fixes (staging import probe; bundle pyproject dep spec). The mirror's failure mode is "silently broken distribution" — a product problem that fails users, not engineers.
- Option 3 costs the distribution story that PLAN.md §Distribution treats as a principle. Retiring that without a replacement is a bigger design change than #56 or anything else currently on the Concerns list. Out of scope for this spike.

### Suggested script interface (Option 1)

Keep the existing `build_bundle.py` CLI (`--validate`, `--pack`) — external-facing contract already documented. Internal changes:

```python
# REPO_ROOT unchanged
TINYASSETS_SRC = REPO_ROOT / "workflow"

def _stage_bundle() -> Path:
    # ... existing cleanup + template copy ...
    _copy_tree(
        TINYASSETS_SRC,
        STAGE_ROOT / "workflow",
        exclude=("__pycache__", "*.db", "*.log", ".pytest_cache"),
    )
    # Bundle server.py imports `workflow.universe_server`, not `fantasy_author.universe_server`
    # Probe it before packing:
    _probe_import(STAGE_ROOT, "workflow.universe_server")
    return STAGE_ROOT

def _probe_import(stage: Path, module: str) -> None:
    """Fail loudly if the staged bundle can't import its own entry point."""
    result = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(stage)!r}); __import__({module!r})"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Staged bundle import probe failed:\n{result.stderr}")
```

Same shape extends to a new `build_plugin.py` for `packaging/claude-plugin/` — lifted identically, different stage target.

### Flags for dev

- **Does the bundle actually need the whole `tinyassets/` package, or can we scope to the MCP-relevant subset?** Current shape suggests whole-package is simplest — daemon internals that `universe_server` imports aren't safe to cherry-pick without dependency analysis. Ship whole-package in v1; prune later if bundle size matters.
- **`fantasy_author/` shim deletion:** explorer confirms 2 internal callers depend on the shim (`fantasy_author/__main__.py:2103` daemon entrypoint, `universe_tray.py:334` tray process spawn). Neither is a packaging consumer — both are runtime entry points that happen to route through the shim. Shim deletion is gated on updating both callers to `from workflow.universe_server import ...`, which falls under the "Author → Daemon mass-rename" Work row already in STATUS.md.
- **Releases:** `packaging/registry/server.json` expects a GitHub release at `github.com/Jonnyton/TinyAssets/releases/download/v0.1.0/...` (per `distribution_validation.md:39`). That release **does not exist yet**. The registry draft is valid-but-unpublishable until the host decides to cut a release. Out of scope for this task; flagged for host.
- **CI:** no CI currently runs the build scripts. Adding `python packaging/mcpb/build_bundle.py --validate` to CI would have caught this break. Recommend as a separate follow-up.

## 5. Blast-radius check (Option 1)

Consumers that assume the current packaging layout (explorer-verified 2026-04-15):

1. `docs/mcpb_packaging.md` + `docs/distribution_validation.md` — describe the current (broken) shape. Update in this commit.
2. `packaging/registry/generate_server_json.py:19` — reads `packaging/mcpb/manifest.json`. Unchanged by Option 1.
3. `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/server.py` — hand-copied, **no build script exists for this mirror** (explorer confirmed). Replaced by new `build_plugin.py` output.
4. **External: zero consumers.** Explorer confirmed: no GitHub release (no tags, no release assets), no CI (`.github/workflows/` does not exist), no CD pipeline, no npm/PyPI publish. The registry `server.json` points at a URL (`github.com/Jonnyton/TinyAssets/releases/download/v0.1.0/...`) that does not exist and has never existed. `distribution_validation.md:41-42` already describes the registry file as a "schema-valid publishing draft rather than a fully publishable listing."
5. Obsidian hub / INDEX files reference `packaging/` as a directory — not file-specific, not broken by internal reorg.
6. **Shim has 2 internal callers, none in packaging.** `fantasy_author/__main__.py:2103` (daemon entrypoint) and `universe_tray.py:334` (tray process spawn) both import from `fantasy_author.universe_server`. No test imports it. These are runtime entry points, not packaging consumers — the packaging change doesn't touch them. The shim stays live until those two call sites migrate (part of the pending mass-rename).

**Implication:** the "Risk" column of this decision is uniformly low. There is no installed user base, no published artifact, no CI to break. Option 1 can ship without coordinated rollback because nothing downstream consumes the current (broken) shape.

## 6. PLAN.md alignment

- **§Distribution And Discoverability** (L186): Option 1 preserves the distribution story. Option 3 contradicts it.
- **§System Shape** (L80, principle about "sources don't drift; derived artifacts do"): Option 1 matches. Option 2 violates.
- No principle conflict for Option 1.

## 7. Open questions

1. **Release cadence.** Once build_bundle.py works, when do we cut v0.1.0 to populate the registry? Host decision, not blocking this spike.
2. **`fantasy_author/` as a concept.** Planner project memory notes the "Author → Daemon mass-rename" is pending. The shim's existence is a mid-rename artifact. Option 1 accelerates that rename by removing one of the last `fantasy_author/` references.
3. **Bundle deps — two distinct dep surfaces.** `packaging/mcpb/pyproject.toml` currently lists only fastmcp; staged bundle runs via `uv run --project` against it. `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/requirements.txt` also lists only `fastmcp>=3.2,<4`; the claude-plugin `bootstrap.py` creates a per-plugin venv and `pip install -r requirements.txt` at first launch. After Option 1, **both** need whatever `tinyassets/universe_server.py` transitively imports (langgraph, lancedb, …). The new `build_plugin.py` must emit a synced `requirements.txt` for the plugin side in the same pass that `build_bundle.py` updates the mcpb `pyproject.toml` — two paths, one dep source. Explorer is probing the transitive import surface; result will land in a §4 "must-resolve-before-shipping" bullet if anything heavy surfaces.
4. **Conway scaffold retention.** `packaging/conway/` has zero current consumer (explorer confirmed — it's a speculative readiness scaffold with its own `_note` admitting so). Option 1 doesn't touch it. Ask: should this whole directory be flagged for deletion too, or does readiness-scaffold status earn it a pass? Planner lean: keep for now; the cost is a few KB of JSON and the intent was explicit. Not worth a PR on its own.
5. **Explorer's alternative framings.** Explorer surfaced two paths between full auto-build (Option 1) and retire (Option 3):

   - **Option 1b — abandon the mirror until launch is near**: fix `build_bundle.py` + write `build_plugin.py` post-shim, delete the stale staged artifacts, but skip CI wiring. Bundle is one command away whenever the host decides to release. ~0.5 day.
   - **Option C — freeze + warn**: add a STALE banner to `packaging/PACKAGING_MAP.md`, `docs/mcpb_packaging.md`, and a `bids/README.md`-style "do not ship" note. Leave `build_bundle.py` broken until launch is real. Lowest-effort holding pattern. ~1 hr.

   Full decision table:

   | Dimension | Option 1 | **Option 1b** | **Option C** | Option 2 | Option 3 |
   |---|---|---|---|---|---|
   | Fix the build scripts | Yes | Yes | No | No | N/A |
   | Run in CI / pre-build dist | Yes | No, manual | No | No | N/A |
   | Delete stale dist artifacts | Yes | Yes | No (keep as frozen snapshot) | No | Yes |
   | STALE banner on docs + PACKAGING_MAP.md | No | No | Yes | No | N/A |
   | Effort | ~1 day | ~0.5 day | ~1 hr | ongoing | ~10 min |
   | Ready for release when host decides | Immediate | One-command | Requires build-script fix + rebuild | Requires mirror sync | Requires full rebuild |

   **Refined recommendation based on release horizon:**
   - Release within weeks → **Option 1** (auto-build + CI wiring).
   - Release within months → **Option 1b** (fix build, skip CI, delete stale dist).
   - Release deferred 6+ months → **Option C** (freeze + warn; cheapest holding pattern).

   Host signal needed on release horizon to lock the pick. Planner's default lean if no signal: **Option 1b** — close to Option C's cost, leaves a working build behind, and working builds are never wasted work. Option C is right only if the deferral is genuinely indefinite.
