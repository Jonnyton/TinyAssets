# Distribution Validation

The current launch surfaces are validated with native tools rather than
custom repo-specific assumptions.

## Claude plugin marketplace

- Root marketplace manifest: `packaging/claude-plugin/.claude-plugin/marketplace.json`
- Plugin manifest: `packaging/claude-plugin/plugins/tinyassets-universe-server/.claude-plugin/plugin.json`
- Validation command:

```powershell
claude plugin validate packaging/claude-plugin
```

The plugin bundles a Python bootstrapper plus the live `tinyassets/` package
(staged into the plugin runtime by `packaging/claude-plugin/build_plugin.py`)
so the MCP server can run from Claude's plugin cache using
`${CLAUDE_PLUGIN_ROOT}`. On first launch, the bootstrapper creates a local
virtual environment under the plugin runtime and installs the dep set declared
in `requirements.txt` (the MCP-control-plane subset of `tinyassets/`'s deps —
see `docs/mcpb_packaging.md`).

Re-stage the plugin runtime after touching `tinyassets/`:

```powershell
python packaging/claude-plugin/build_plugin.py
```

## MCP Registry

- Draft server metadata: `packaging/registry/server.json`
- Generator: `packaging/registry/generate_server_json.py`
- Validation source:
  `https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json`

Refresh the registry draft from the current built bundle:

```powershell
python packaging/registry/generate_server_json.py --validate
```

Validation can be checked locally with a small `jsonschema` script. The
current registry draft assumes the packaged bundle will be uploaded to a
GitHub release at:

`https://github.com/Jonnyton/TinyAssets/releases/download/v0.1.0/tinyassets-universe-server-0.1.0.mcpb`

Until that release asset exists publicly, the registry file should be treated
as a schema-valid publishing draft rather than a fully publishable listing.
