# MCPB Packaging

The official MCPB packaging path lives under `packaging/mcpb/`. Auto-built from the live `tinyassets/` package per design-note `2026-04-14-packaging-mirror-decision.md` (Option 1) — no shim, no hand-maintained snapshot.

## What is checked in

- `packaging/mcpb/manifest.json`: spec-aligned MCPB manifest template
- `packaging/mcpb/pyproject.toml`: bundle runtime config — declares the MCP-control-plane subset of `tinyassets/`'s deps
- `packaging/mcpb/server.py`: stdio entrypoint that imports `workflow.universe_server` from the bundled package
- `packaging/mcpb/build_bundle.py`: stages the bundle source, runs an import probe, then validates / packs `tinyassets-universe-server.mcpb`

## Source of truth

The repository source of truth for the packaged server is `tinyassets/universe_server.py` (and the rest of the `tinyassets/` package it imports). `build_bundle.py` stages the entire `tinyassets/` tree into `packaging/dist/tinyassets-universe-server-src/tinyassets/` and then runs a subprocess import probe (`python -c "import workflow.universe_server"` against the staged dir) to confirm the bundle is launchable before packing.

The legacy `fantasy_author/universe_server.py` shim path is no longer in the bundle. It survives in the repo only for runtime callers (`fantasy_author/__main__.py`, `universe_tray.py`) until the Author → Daemon mass-rename completes.

## Commands

Stage + import-probe (always run):

```powershell
python packaging/mcpb/build_bundle.py
```

Stage + validate:

```powershell
python packaging/mcpb/build_bundle.py --validate
```

Stage + validate + pack:

```powershell
python packaging/mcpb/build_bundle.py --pack
```

For a minimal CI matrix without runtime deps, `--skip-probe` bypasses the import probe (use sparingly — it's the load-bearing safety check).

## Runtime shape

The packaged bundle runs as a local stdio MCP server. During installation, the host client prompts for:

- `Universe Base Directory`: required directory containing universe folders
- `Default Universe`: optional universe ID used when the client does not pass one

The bundle then launches `packaging/mcpb/server.py`, which inserts the bundle root into `sys.path` and runs `workflow.universe_server.main(transport="stdio")`.

## Companion: claude-plugin runtime

`packaging/claude-plugin/build_plugin.py` mirrors the build contract for the Claude plugin marketplace surface. Same exclusion rules, same import probe, same single source of truth.

## CI

`.github/workflows/build-bundle.yml` runs the stage + import probe on every push to main and on every PR that touches `tinyassets/` or `packaging/`. On a tagged release, the workflow also packs the `.mcpb` and uploads it as a release asset.

## Notes

The official `@anthropic-ai/mcpb` validator currently rejects `server.type = "uv"` even though the public manifest docs mention it. The manifest therefore uses `server.type = "python"` while `mcp_config.command` still launches the bundle with `uv run`.
