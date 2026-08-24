"""Single source of truth for the served agent's engine-MCP tool allowlist.

Founder rule: every surface does the same things. The served universe answers on
different provider families (codex via ``codex exec``, claude via ``claude -p``),
and each wires the engine-MCP server with an ``enabled_tools`` allowlist. Those
two allowlists MUST be identical — a codex-served and a claude-served universe get
exactly the same capability. They used to be two hand-maintained tuples
(``codex_provider._ENGINE_MCP_ENABLED_TOOLS`` and
``universe_intelligence._ENGINE_MCP_TOOLS``), which silently drifted: ``run_graph``
landed on the claude list only, so a codex-served founder could not run their own
automations at all (caught 2026-08-23).

Making both providers import THIS one tuple removes the drift class structurally —
they are now the same object, so "meant to be in sync" is guaranteed by
construction, not by a guard test that only notices after the fact. To change what
the served agent can do, edit this list ONCE and every surface moves together.

Kept deliberately dependency-free so any provider module can import it without a
cycle.
"""

from __future__ import annotations

#: The engine-MCP handles the served agent may call, on EVERY provider surface.
#: A handler is only reachable when it is BOTH registered (``@mcp.tool`` in
#: ``engine_mcp_server``) AND present here.
#:
#: Included:
#:   read_graph, get_status, browse_commons, read_commons_shape  — read surfaces
#:   read_brain, write_brain                                     — the universe's own brain
#:   connect_compute                                             — register a compute
#:       provider (candidate-only, owner-gated, graph-pinned, secret-free; no
#:       execution / cross-universe reach)
#:   run_graph                                                   — RUN one of THIS
#:       universe's approved automations end-to-end (the "do the workflow you
#:       built" parity). Safety rests on #2498's sanitized invoke_branch
#:       (delegated child-authority + fail-closed actor + mapping/await
#:       confidentiality) PLUS run_graph's own gates: per-universe run allowlist,
#:       effect-spam rate limit, IDOR read/execute gate, founder-scoped
#:       capabilities. NOTE: run_graph is NOT author-only — its branch resolver
#:       admits a founder-owned OR a PUBLIC-foreign branch (a foreign PRIVATE
#:       branch is refused); the delegated-authority sanitization is what keeps
#:       that safe, not an author gate.
#:
#: Deliberately EXCLUDED pending their own review (tracked by the
#: ``served-agent-build-run`` OpenSpec change):
#:   write_graph   — BUILD a branch (the "when the user creates things" parity).
#:       REBUILT 2026-08-23 as a purpose-built, BRANCH-ONLY handler
#:       (engine_mcp_server.write_graph, target=branch, op in {create, patch}). It
#:       no longer delegates to the broad connector write_graph — it calls the
#:       author-gated, EFFECT-FREE extensions functions DIRECTLY (build_branch /
#:       patch_branch) with least-privilege caps (no submit_request), so the
#:       automation / version / provider-rebind paths that failed three earlier
#:       Codex rounds are simply unreachable. Stays DARK (registered, not
#:       allowlisted) only until a fresh Codex exact-diff review of THIS handler
#:       clears it — then it moves into the tuple below. run_graph — approved +
#:       live — already covers the RUN parity.
#:   remix_shape   — cross-author commons remix
#:   grant_effector_consent / channel-connection verbs — user-built channels
SERVED_ENGINE_MCP_TOOLS: tuple[str, ...] = (
    "read_graph",
    "get_status",
    "run_graph",
    "browse_commons",
    "read_commons_shape",
    "read_brain",
    "write_brain",
    "connect_compute",
)
