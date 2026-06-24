## Why

The substrate vocabulary was host-ratified on 2026-05-06: the user-facing MCP surface is exactly **5 handles** (`read.graph`, `write.graph`, `run.graph`, `read.page`, `write.page`) over the 6 primitives. That collapse was implemented and merged (PR-047 / GitHub #617, triple-key approved 2026-05-08) — but on a **separate** `workflow/directory_server.py` ("/mcp-directory") surface. The live public connector at `https://tinyassets.io/mcp` is served by `workflow/universe_server.py`, which was never cut over. As of 2026-06-23 the live endpoint still advertises the legacy fat surface — 7 tools / ~175 named actions (extensions=80, universe=46, plus goals/gates/wiki/get_status/community_change_context) — and no `*.graph` / `*.page` handle exists. A ratified design has been functionally absent from the live path for ~6 weeks. This is spec-vs-implementation drift, not a missing primitive: the design exists and was built; it just never reached production. Tracked as PR-178.

## What Changes

- Expose the 5 canonical handles (`read.graph`, `write.graph`, `run.graph`, `read.page`, `write.page`) as the user-facing tools on the LIVE server `workflow/universe_server.py` (the process behind `https://tinyassets.io/mcp`).
- Implement each handle as a thin dispatch layer (a `shape=` / payload router) over the EXISTING action handlers in `workflow/api/*` — no behavior change to the underlying primitives, only the surface shape. Forward-port the PR-047/#617 `directory_server` implementation rather than rebuild from scratch where possible.
- **BREAKING (intended):** deprecate the legacy fat tools (`universe`, `extensions`, `goals`, `gates` as ~175 enumerated actions) behind the 5 handles. Provide a clear deprecation path / mapping (the canonical 6+5 page already gives the action→handle fold-map). `wiki` reads/writes fold into `read.page`/`write.page`; `get_status` remains as a read.
- Add a **public-canary assertion** (per Hard Rule #11) that the live `/mcp` advertises exactly the 5 handles after any DNS/tunnel/Worker/connector change, so this surface can never silently drift again.
- Retire `workflow/directory_server.py` as a parallel surface once `universe_server.py` is the single source of the 5-handle contract.

## Capabilities

### New Capabilities
- `mcp-five-handle-surface`: The live user-facing MCP contract — exactly five tools (`read.graph`, `write.graph`, `run.graph`, `read.page`, `write.page`), their `shape=` parameter mapping to the 6 primitives, their routing to existing `workflow/api` handlers, and the canary invariant that the deployed `/mcp` advertises exactly these handles.

### Modified Capabilities
<!-- No existing openspec/specs/ capability covers the MCP surface yet; this is the first spec to define it. Legacy fat-surface behavior is captured as the "removed/deprecated" half of the new capability's delta. -->

## Impact

- **Code:** `workflow/universe_server.py` (tool registration cutover), `workflow/api/*` (handler routing under a `shape=` dispatcher), `workflow/directory_server.py` (retire after cutover), the `packaging/claude-plugin` runtime mirror (must stay byte-parity).
- **Deploy:** new image + `scripts/mcp_public_canary.py` extended to assert the 5-handle advertisement; post-deploy public canary required.
- **External consumers:** any chatbot/app wired to the legacy actions (incl. the Polsia handoff doc and Claude.ai/ChatGPT connectors) must migrate to the handles; the handoff doc must be updated once the surface is live.
- **Governance:** ships through the triple-key merge gate (Codex execution key + Cowork checker key + explicit host key) with the canonical position records, per substrate-framing-locked.
