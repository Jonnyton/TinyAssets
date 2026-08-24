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
#:   write_graph   — BUILD a branch / manage an automation (the "when the user
#:       creates things" parity). The confined served handler IS implemented +
#:       tested (engine_mcp_server.write_graph, target in {branch, automation}),
#:       but confining the broad connector handler surfaced authority quirks over
#:       three Codex rounds (rebind provider-backdoor, foreign-version selection),
#:       so it stays DARK (registered, not allowlisted) until a dedicated
#:       purpose-built review clears it. run_graph — approved + live — is enough for
#:       the RUN parity; write_graph exposure is the next slice.
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
