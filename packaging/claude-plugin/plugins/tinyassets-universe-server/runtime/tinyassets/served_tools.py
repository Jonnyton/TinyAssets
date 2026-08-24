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
#:   write_graph   — BUILD a branch (the "when the user creates things" parity),
#:       CREATE-ONLY, target=branch. Purpose-built (NOT the broad connector
#:       write_graph): it SANITIZES the spec and calls the author-gated,
#:       EFFECT-FREE build_branch directly with least-privilege caps (no
#:       submit_request). Two Codex review rounds (2026-08-23) hardened it — every
#:       known path to a persisted APPROVED source_code node is closed: submitted
#:       approval/author/fork stripped at node level, `node_ref` (foreign-node
#:       dereference) rejected, nested `graph` blob rejected, `fork_from` stripped,
#:       visibility forced private, size/node/type guards. A served-built
#:       source_code node persists UNAPPROVED, so run_graph's fail-closed
#:       _validate_source_code refuses to execute it until the founder approves the
#:       source via the browser. Gated to the same per-universe run allowlist as
#:       run_graph (u-tiny). RESIDUAL, tracked as the pre-second-user harden gate
#:       (served-agent-build-run): branches are author-scoped not universe-scoped,
#:       and build_branch's approval surface is broad enough that the robust
#:       multi-tenant fix is a force-unapproved build MODE (clear approval after
#:       any inherit/deref, before persist) + a branch↔universe binding. EDIT
#:       (patch) stays off this surface (its op set can publish / change
#:       visibility / fork) — a separate reviewed slice.
#:
#:   source_channel — APPROVE an outbound channel for your own universe (the consent
#:       half of "add a channel via the channel-agnostic node"). Owner-gated
#:       (source_channel's impl requires an admin ACL row for the bound founder;
#:       anonymous / read-write collaborators get auth_failed), graph-PINNED
#:       (universe_id is never caller-supplied), SECRET-FREE (consent is a
#:       (sink, destination) allow — the token is deposited out of band via the browser
#:       form / connect_http, which is deliberately NOT here). SINK CONSENT ONLY:
#:       channel_type=="source_code" is refused (that approval sets approved_source_hash,
#:       the code-execution gate the create-only write_graph strips — keeping it off this
#:       surface preserves the RCE closure). action=approve only; set_policy/get_policy
#:       and the raw-secret connect_http stay off-surface. Gated to the same u-tiny run
#:       allowlist; the outbound call also needs TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED.
#:
#: write_graph (BUILD half of the channel slice, 2026-08-25): the ONE channel-agnostic
#:   effect node (``authenticated_external_call``) is now allowed in a served create — an
#:   allowlist (every other sink, incl. ``wiki_write_back``, and the typed ``handoffs``
#:   path are refused), capped at a small effect-node count per build. Building declares
#:   only the sink NAME and fires nothing; the run-time effector re-checks the
#:   connection-grant-bound-to-this-universe + per-destination consent (granted via
#:   source_channel) + TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED + SSRF per dispatch.
#:
#: Deliberately EXCLUDED pending their own review (tracked by the
#: ``served-agent-build-run`` OpenSpec change):
#:   write_graph PATCH/edit — see above (separate slice)
#:   remix_shape   — cross-author commons remix
#:   connect_http  — deposits a RAW SECRET; stays on the browser deposit form
#:   a proper per-root-run effect-dispatch cap (all surfaces) — the served build cap on
#:       effect-node count is the interim structural bound
SERVED_ENGINE_MCP_TOOLS: tuple[str, ...] = (
    "read_graph",
    "get_status",
    "run_graph",
    "write_graph",
    "browse_commons",
    "read_commons_shape",
    "read_brain",
    "write_brain",
    "connect_compute",
    "source_channel",
)
