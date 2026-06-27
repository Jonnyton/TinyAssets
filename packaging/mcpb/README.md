# MCPB Bundle Template

`packaging/mcpb/` is the source template for the TinyAssets Server
MCP Bundle. It is not the final packable directory by itself.

Use the build script to stage a minimal bundle that contains:

- the official MCPB `manifest.json`
- a small runtime project with only the FastMCP dependency
- a stdio wrapper server
- a synced copy of `fantasy_author/universe_server.py`
- the bundle icon asset

## Commands

Validate the staged bundle:

```powershell
python packaging/mcpb/build_bundle.py --validate
```

Pack the staged bundle into `packaging/dist/tinyassets-universe-server.mcpb`:

```powershell
python packaging/mcpb/build_bundle.py --pack
```

## Why a staging step exists

The repo's runtime source of truth stays in
`fantasy_author/universe_server.py`, but the MCPB bundle needs a small,
self-contained runtime surface. The staging script copies the current
TinyAssets Server file into the staged bundle so the packaged extension does
not depend on the whole repo layout or the full project dependency set.

The current official MCPB validator still requires `server.type` to be one of
`python`, `node`, or `binary`, so the manifest uses `python` while the actual
launcher command still runs the bundled server through `uv`.

Any time the TinyAssets Server MCP surface changes, rebuild the staged bundle
before validating or packing.
