## Context

The Workflow connector is served to all chatbots/apps from `workflow/universe_server.py` (FastMCP, Streamable HTTP) behind `https://tinyassets.io/mcp`. It currently registers 7 coarse `@mcp.tool` handlers (`universe`, `extensions`, `goals`, `gates`, `wiki`, `get_status`, plus prompts), each multiplexing dozens of `action=` values — ~175 enumerated actions in total. The substrate vocabulary was frozen on 2026-05-06 to 6 primitives + 5 MCP handles; the action→handle fold-map is documented on `pages/concepts/...-6-primitives-5-mcp-handles`. PR-047 (GitHub #617) already implemented the 5-handle surface and passed the triple-key gate, but on a parallel `workflow/directory_server.py` ("/mcp-directory") that the live endpoint does not serve. That file is now gone from the working tree, so the implementation must be recovered from git history (#617) or rebuilt. Filed as PR-178.

## Goals / Non-Goals

**Goals:**
- The live `/mcp` (served by `universe_server.py`) advertises exactly five user-facing tools: `read.graph`, `write.graph`, `run.graph`, `read.page`, `write.page`.
- Each handle is a thin shape/payload router over the EXISTING `workflow/api/*` handlers — no change to primitive behavior, run semantics, or storage.
- A post-deploy public canary asserts the live handle set, making future drift impossible to ship silently.
- Single source of truth for the surface (retire the parallel `directory_server.py`).

**Non-Goals:**
- No new primitive, capability, or behavior is introduced (this is a surface-shape change, not a feature).
- No change to `get_status` (stays a read) or to the underlying action handlers' logic.
- Not redesigning the brain/page model or the economy/gates surfaces beyond mapping them onto `read.page`/`write.page` and `run.graph`.
- Auth/identity model unchanged.

## Decisions

- **Cut over `universe_server.py` in place rather than route traffic to `directory_server.py`.** Rationale: the public endpoint, Cloudflare Worker route, tunnel, and deploy image all target the `universe_server` process; re-pointing infra is higher-risk than changing the tool registration in the served process. Alternative considered (front `/mcp` with `directory_server`) rejected to avoid a second long-lived surface and infra churn.
- **Handles dispatch via a `shape=` parameter mapping 1:1 to the primitives**, exactly as the canonical 6+5 page specifies (e.g. `write.graph shape=node|edge|state`, `run.graph` is the only verb that produces a Run, `read.page`/`write.page` carry `path`/`content`). The handle functions translate `shape` + payload into the existing `_action_*` handlers, so the 175 actions become an internal dispatch table, not a user surface.
- **Forward-port #617.** Recover the directory_server implementation from git (`git show <merge-of-#617>:workflow/directory_server.py`) and adapt its router into `universe_server.py`, preserving its test coverage. Avoids re-deriving the fold-map.
- **Legacy tools deprecated, not instantly deleted.** Keep them registered for one release behind a deprecation notice so existing connectors (Claude.ai/ChatGPT/the Polsia app) can migrate; the canary tracks the 5 handles as the canonical set. A follow-up change removes the legacy tools.
- **Canary as the drift guard.** Extend `scripts/mcp_public_canary.py` to assert `tools/list` on the live `/mcp` equals exactly the 5 handles (+ allowed prompts). Wire into the post-DNS/tunnel/Worker/connector check mandated by Hard Rule #11.
- **Runtime mirror parity.** `packaging/claude-plugin` must stay byte-parity with `workflow/api` per existing rule; update both.

## Risks / Trade-offs

- **Breaking external consumers** → Mitigation: dual-register (handles + deprecated legacy) for one release; publish the action→handle mapping; update the Polsia handoff doc and any connector manifests before removing legacy tools.
- **#617 source rot / divergence from current `api/*`** → Mitigation: treat #617 as reference for the fold-map, but re-bind to the CURRENT handler signatures; rely on the recovered tests plus new contract tests.
- **Hidden coupling where chatbots depend on specific action names/strings** → Mitigation: keep an internal alias table; log deprecated-action hits during the dual-register window to find stragglers.
- **Deploy/canary gap on the gated `/mcp`** → the public canary must run against the real `tinyassets.io/mcp` (not the internal tunnel origin), consistent with existing canary practice.

## Migration Plan

1. Recover #617's `directory_server` router and tests from git history.
2. Add the 5 handle tools + `shape=` dispatcher to `universe_server.py`, routing to existing `api/*` handlers; keep legacy tools registered with deprecation metadata.
3. Add contract tests asserting the 5-handle `tools/list` and representative round-trips per handle; mirror into `packaging/claude-plugin`.
4. Triple-key gate (Codex execution key + Cowork checker key + explicit host key) via canonical position records.
5. Deploy; run extended `mcp_public_canary.py`; verify live `/mcp` advertises exactly the 5 handles.
6. Update the Polsia handoff doc + connector manifests; open a follow-up change to remove the deprecated legacy tools after the migration window.
7. Rollback: re-deploy prior image (legacy surface) if the canary fails; handles are additive until legacy removal, so rollback is non-destructive.

## Open Questions

- Exact merge SHA of #617 to recover `directory_server.py` from (locate via the PR-047/#617 wiki audit pages).
- Whether `gates`/`goals` fold fully under `read.graph`/`run.graph` + `read.page`, or warrant explicit `shape=` values — resolve against the canonical fold-map during the specs phase.
- Length of the dual-register deprecation window before legacy removal (one release vs. measured by deprecated-action telemetry).
