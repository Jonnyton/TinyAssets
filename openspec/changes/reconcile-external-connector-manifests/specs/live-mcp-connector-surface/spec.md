## MODIFIED Requirements

### Requirement: Public Canary And Directory Review Surface
The platform SHALL provide a stdlib-only public canary
(`scripts/mcp_public_canary.py`) whose `--assert-handles` mode performs a full
handshake, reads `tools/list`, and fails (exit 4) unless the live surface
advertises the required canonical handles and nothing beyond the allowed
advertised set, plus a lightweight uptime canary (`scripts/uptime_canary.py`).
The platform SHALL also expose a narrower directory surface
(`tinyassets/directory_server.py`, served at `/mcp-directory`) intended for
reviewed host directories such as Claude's Connectors Directory and ChatGPT
Apps: it advertises no catch-all `action` inputs and serves the redacted status
view through `read_graph(target=status)`; the directory surface does not
advertise a `get_status` handle. The redacted view strips operator diagnostics
and injects a `directory_privacy_note`.

#### Scenario: Canary fails on advertised-handle drift
- **WHEN** the live `tools/list` is missing a required canonical handle or advertises a handle outside the allowed set (for example a leaked legacy fat tool)
- **THEN** `mcp_public_canary.py --assert-handles` exits with code 4 and reports the missing/extra handle sets

#### Scenario: Directory status redacts operator diagnostics
- **WHEN** a directory client reads status through `read_graph(target=status)` on the `/mcp-directory` surface
- **THEN** raw activity logs and internal diagnostics are stripped and the payload carries a `directory_privacy_note`, whereas the live `/mcp` `read_graph target=status` returns the full unredacted status
