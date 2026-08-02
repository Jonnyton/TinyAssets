## Why

The checked-in MCP Registry manifest advertises `https://tinyassets.io/mcp-directory/catalog/2026-05-07-issue-269`, which now returns HTTP 404. The live connector catalog has advanced to `2026-06-24-underscore-handles`, and the existing generator already derives that current URL from `tinyassets.connector_catalog`, but nothing in CI proves the committed `server.json` matches the generator. External directory consumers therefore receive a broken discovery URL even while the canonical `/mcp` connector is healthy.

## What Changes

- Make the registry generator runnable directly from a clean repository checkout.
- Regenerate `packaging/registry/server.json` from the current connector-catalog source of truth.
- Add deterministic test and packaging-CI gates that fail when the checked-in manifest drifts from generated output.
- Verify the generated versioned catalog URL serves the current directory catalog without changing the live MCP server or its advertised handle set.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `live-mcp-connector-surface`: require published registry metadata to follow the current versioned directory catalog and fail repository checks on generated-artifact drift.

## Impact

Changes are limited to the registry generator, generated `server.json`, its focused tests, the packaging workflow, and this OpenSpec change. There is no runtime MCP behavior change and no production deployment. External-directory acceptance through real chatbot hosts remains a separate host-owned proof after the repository metadata is repaired.
