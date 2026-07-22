## Context

`tinyassets.connector_catalog` owns the versioned `/mcp-directory/catalog/<version>` path used to invalidate host caches when the chatbot-visible catalog changes. `packaging/registry/generate_server_json.py` already consumes that helper, but the committed artifact was not regenerated after the catalog version changed and packaging CI does not run the generator's `--check` mode. Direct execution of the generator from repository root also fails before checking drift because Python places the script directory, rather than the repository root, on `sys.path`.

## Goals / Non-Goals

**Goals:**

- Restore a working external-directory discovery URL in the checked-in registry manifest.
- Keep `tinyassets.connector_catalog` as the single source of catalog-version truth.
- Make future artifact drift fail deterministically in tests and packaging CI.
- Preserve clean-clone usability of the documented generator command.

**Non-Goals:**

- Change `/mcp`, `/mcp-directory`, their authentication policy, or the seven canonical connector-safe handles.
- Retire hidden legacy MCP tools or `directory_server.py`.
- Submit or approve the repaired manifest in an external registry.
- Make a live network request part of ordinary CI.

## Decisions

1. **Generate; do not duplicate the URL.** The manifest continues to consume `directory_mcp_remote_url()`. Tests compare the committed JSON with the generator's complete deterministic document rather than hard-coding a second version string.
2. **Run the existing drift mode in packaging CI.** `build-bundle.yml` already runs when `tinyassets/**` or `packaging/**` changes. A direct `generate_server_json.py --check` step makes drift a blocking packaging failure.
3. **Bootstrap only the repository import root.** The generator resolves its own repository root before importing `tinyassets.connector_catalog`, so the same direct command works in a clean clone on Windows and Linux. It does not install dependencies, mutate environment variables, or add a package shim.
4. **Keep live reachability out of CI.** The repair records a fresh read-only GET as acceptance evidence, while CI remains deterministic and offline. External availability is monitored by the existing public-surface probes.

## Risks / Trade-offs

- **A catalog version changes without regenerating metadata** → focused equality test and packaging `--check` both fail.
- **The generated URL exists in code but is not mounted live** → a fresh read-only live probe is required before this change archives.
- **Import bootstrapping masks packaging defects** → add only the resolved repository root and keep the generator dependent on the real `tinyassets.connector_catalog` module.
- **External registry caches the old artifact** → this change repairs source metadata; host-owned resubmission/acceptance remains separately tracked in `STATUS.md`.

## Migration Plan

Add a failing drift test, make direct generation executable, regenerate `server.json`, wire the deterministic CI check, and verify the generated live URL. Then sync the added requirement into `openspec/specs/live-mcp-connector-surface/spec.md` and archive this completed change. Rollback is a revert of the metadata commit; no service state changes.

## Open Questions

None.
