"""Branch authoring + node CRUD subsystem — extracted from
``workflow/universe_server.py`` (Task #15 — decomp Step 8).

The largest single submodule extracted from the monolith: 17 ``_ext_branch_*``
handlers, the ``_action_fork_tree`` action
handlers, the build/patch composite engine (``_ext_branch_build`` /
``_ext_branch_patch`` / ``_ext_branch_update_node`` / ``_ext_branch_patch_nodes``),
the node-spec resolver + apply machinery (``_resolve_node_spec``,
``_apply_node_spec``, ``_apply_edge_spec``, ``_apply_conditional_edge_spec``,
``_apply_state_field_spec``, ``_apply_patch_op``, ``_lookup_node_body``,
``_staged_branch_from_spec``), the wiki-cross-reference helper group
(``_related_wiki_pages``, ``_related_summary``, ``_RELATED_WIKI_CAP``,
``_RELATED_SUMMARY_MAX``), the mermaid renderer (``_branch_mermaid``,
``_mermaid_node_id``, ``_mermaid_label``), the ``_BRANCH_ACTIONS`` /
``_BRANCH_WRITE_ACTIONS`` dispatch surface, the ``_dispatch_branch_action``
ledger-aware dispatcher, the ``_resolve_branch_id`` / ``_resolve_udir``
resolvers, the bulk-patch coercer (``_coerce_patch_nodes_value``,
``_PATCH_NODES_FIELDS``), the build-summary text composer
(``_build_branch_text``, ``_suggest_entry_point``, ``_closest_state_type``,
``_errors_to_suggestions``, ``_VALID_STATE_TYPES``), and the branch-design
guide markdown body (``_BRANCH_DESIGN_GUIDE``,
``_branch_design_guide_prompt``).

The ``@mcp.prompt("Branch Design Guide")`` decoration stays in
``workflow/universe_server.py`` (Pattern A2) so FastMCP introspection
sees the chatbot-facing signature exactly as before. The
``branch_design_guide()`` wrapper there delegates to
``_branch_design_guide_prompt()`` from this module.

Public surface (back-compat re-exported via ``workflow.universe_server``):
    _BRANCH_ACTIONS                : dispatch table (17 handlers)
    _BRANCH_WRITE_ACTIONS          : frozenset of write actions for ledger gating
    _RELATED_WIKI_CAP              : cap on related-wiki page list
    _dispatch_branch_action        : ledger-aware dispatcher
    _ext_branch_*                  : 15 individual handlers
    _action_fork_tree              : ancestor + descendant lineage walk
    _resolve_branch_id             : branch-name → branch_def_id resolver
    _resolve_node_spec             : node-spec resolver (node_ref / inline)
    _resolve_udir                  : universe-dir resolver
    _related_summary               : first-paragraph summary helper
    _related_wiki_pages            : wiki cross-reference scan
    _branch_mermaid                : flowchart renderer
    _mermaid_node_id, _mermaid_label : mermaid escape helpers
    _build_branch_text             : composite build text composer
    _suggest_entry_point           : entry-point inference helper
    _closest_state_type            : state-type fuzzy match
    _errors_to_suggestions         : validation-error → fix-hint mapper
    _staged_branch_from_spec       : spec → staging-BranchDefinition
    _apply_node_spec, _apply_edge_spec, _apply_conditional_edge_spec,
    _apply_state_field_spec, _apply_patch_op : per-spec applicators
    _lookup_node_body              : node_ref body lookup (standalone or branch)
    _coerce_patch_nodes_value      : bulk-patch type coercer
    _PATCH_NODES_FIELDS            : whitelisted bulk-patch field map
    _split_csv, _coerce_node_keys  : input shape helpers
    _append_global_ledger          : branch-attribution ledger writer
    _ensure_workflow_db            : lazy SQLite schema bootstrap
    _BRANCH_DESIGN_GUIDE           : prompt body markdown
    _branch_design_guide_prompt    : prompt-body accessor for the
                                      universe_server.py @mcp.prompt wrapper

Cross-module note: ``_current_actor``, ``_truncate``, ``_append_ledger``,
``_storage_backend``, ``_format_dirty_file_conflict``, ``_format_commit_failed``,
``_load_nodes``, ``VALID_PHASES``, ``logger`` all live in ``workflow.universe_server``
(universe-engine territory) and are lazy-imported inside the functions that use
them. This avoids the load-time cycle (universe_server back-compat-imports
symbols from this module). ``_gates_enabled`` is also lazy-imported, but from
``workflow.api.market`` (its real home post-Step-7).
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from workflow.api.helpers import (
    _base_path,
    _find_all_pages,
    _read_text,
    _universe_dir,
    _wiki_drafts_dir,
    _wiki_pages_dir,
)
from workflow.api.wiki import (
    _page_rel_path,
    _parse_frontmatter,
)
from workflow.catalog import CommitFailedError, DirtyFileError

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────────────────────
# Community Branches: author/edit BranchDefinition over MCP
# ───────────────────────────────────────────────────────────────────────────
# Branches are domain-agnostic graph topologies that live in the same SQLite
# backing store as the rest of the multiplayer substrate (base_path /
# .workflow.db, table branch_definitions). Each write action appends to
# the global ledger at base_path / "ledger.json" for public attribution —
# branches are not scoped to a universe, so the ledger target is the global
# base_path rather than a per-universe directory.


def _split_csv(text: str) -> list[str]:
    return [p.strip() for p in text.split(",") if p.strip()]


def _coerce_node_keys(
    value: Any, field_name: str,
) -> tuple[list[str], str]:
    """Coerce input_keys / output_keys to list[str], or return an error.

    Accepts list[str], JSON-encoded list strings (e.g. '["a","b"]'),
    CSV strings ("a, b, c"), and bare single tokens ("a"). Rejects
    anything else — in particular, naked iteration over an un-parsed
    string like "node.output" was silently yielding a per-character
    list, which then validated as a node spec but was unrunnable.

    Returns (keys, error). On success error is "". On failure keys is
    [] and error is a human-readable reason.
    """
    if value is None:
        return [], ""
    if isinstance(value, list):
        out: list[str] = []
        for idx, item in enumerate(value):
            if not isinstance(item, str):
                return [], (
                    f"{field_name}[{idx}] must be a string, got "
                    f"{type(item).__name__}"
                )
            trimmed = item.strip()
            if not trimmed:
                return [], f"{field_name}[{idx}] is empty"
            out.append(trimmed)
        return out, ""
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return [], ""
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                return [], (
                    f"{field_name} looks like JSON but did not parse: {exc}"
                )
            if not isinstance(parsed, list):
                return [], (
                    f"{field_name} JSON must decode to a list, got "
                    f"{type(parsed).__name__}"
                )
            return _coerce_node_keys(parsed, field_name)
        # CSV path — also handles the bare single-token case.
        return [p.strip() for p in raw.split(",") if p.strip()], ""
    return [], (
        f"{field_name} must be a list or string, got "
        f"{type(value).__name__}"
    )


def _append_global_ledger(
    action: str,
    *,
    target: str,
    summary: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append a branch-authoring ledger entry at base_path/ledger.json.

    Branch definitions are global artifacts (not scoped to a universe), so the
    ledger target is the base_path rather than a universe directory. Never
    raises: failures are logged but don't roll back the mutation.
    """
    from workflow.api.engine_helpers import _append_ledger

    _append_ledger(
        _base_path(), action,
        target=target, summary=summary, payload=payload,
    )


def _ensure_workflow_db() -> None:
    """Ensure the shared SQLite schema exists before any branch action runs.

    Branch handlers read/write ``base_path/.workflow.db``. Calling this
    lazily keeps tests and first-use paths from needing a separate init step.
    """
    from workflow.daemon_server import initialize_author_server

    initialize_author_server(_base_path())


def _dispatch_branch_action(
    action: str,
    handler: Any,
    kwargs: dict[str, Any],
) -> str:
    """Run a branch handler and append to the global ledger on success.

    Read-only branch actions (get/list/validate/describe) bypass the ledger.
    Write actions (create/add/connect/set/delete) are funneled here so no
    handler can silently skip attribution.
    """
    from workflow.api.engine_helpers import _format_dirty_file_conflict, _truncate

    _ensure_workflow_db()
    try:
        result_str = handler(kwargs)
    except DirtyFileError as exc:
        # Phase 7.3: surface local-edit conflicts as a structured MCP
        # response so the client can render actionable options. Ledger
        # is intentionally skipped — no write landed.
        return json.dumps(_format_dirty_file_conflict(exc))

    if action not in _BRANCH_WRITE_ACTIONS:
        return result_str

    try:
        result = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        return result_str

    if not isinstance(result, dict):
        return result_str
    # Skip ledger on any error-shaped response. Composite actions signal
    # failure via status="rejected" + errors[]; atomic actions use "error"
    # (singular string). Treat both as "don't attribute a write that
    # didn't land".
    if "error" in result:
        return result_str
    if result.get("status") == "rejected":
        return result_str

    try:
        target = result.get("branch_def_id", "") or kwargs.get("branch_def_id", "")
        summary_bits: list[str] = [action]
        if kwargs.get("name"):
            summary_bits.append(kwargs["name"])
        if kwargs.get("node_id"):
            summary_bits.append(f"node={kwargs['node_id']}")
        if kwargs.get("from_node") and kwargs.get("to_node"):
            summary_bits.append(f"{kwargs['from_node']}->{kwargs['to_node']}")
        if kwargs.get("field_name"):
            summary_bits.append(f"field={kwargs['field_name']}")
        # Composite summary hints — one ledger entry per call, not per op.
        if action == "build_branch":
            summary_bits.append(
                f"nodes={result.get('node_count', '?')}"
            )
        if action == "patch_branch":
            summary_bits.append(
                f"ops={result.get('ops_applied', '?')}"
            )
        summary = _truncate(" ".join(summary_bits))
        _append_global_ledger(
            action, target=str(target), summary=summary, payload=None,
        )
    except Exception as exc:
        logger.warning("Ledger write failed for branch action %s: %s", action, exc)

    return result_str


def _ext_branch_create(kwargs: dict[str, Any]) -> str:
    from workflow.api.engine_helpers import (
        _current_actor,
        _format_commit_failed,
        _storage_backend,
    )
    from workflow.branches import BranchDefinition
    from workflow.identity import git_author

    name = kwargs.get("name", "").strip()
    if not name:
        return json.dumps({"error": "name is required for create_branch."})

    visibility_in = (kwargs.get("visibility") or "public").strip().lower()
    visibility = "private" if visibility_in == "private" else "public"
    branch = BranchDefinition(
        name=name,
        description=kwargs.get("description", ""),
        domain_id=kwargs.get("domain_id") or "workflow",
        author=kwargs.get("author") or _current_actor(),
        visibility=visibility,
    )
    try:
        saved, _commit = _storage_backend().save_branch_and_commit(
            branch,
            author=git_author(_current_actor()),
            message=f"branches.create_branch: {name}",
            force=bool(kwargs.get("force", False)),
        )
    except CommitFailedError as exc:
        return json.dumps(_format_commit_failed(exc))
    return json.dumps({
        "branch_def_id": saved["branch_def_id"],
        "name": saved["name"],
        "visibility": saved.get("visibility", "public"),
        "status": "created",
    })


def _resolve_branch_id(bid_or_name: str, base_path: str) -> str:
    """Return branch_def_id for either a branch_def_id or a branch name.

    Tries exact ID match first (fast path via get_branch_definition).
    Falls back to case-insensitive name search via list_branch_definitions.
    Returns the original string unchanged if no match is found — the caller's
    KeyError handler will surface the "not found" error as usual.
    """
    from workflow.api.engine_helpers import _current_actor
    from workflow.daemon_server import get_branch_definition, list_branch_definitions

    if not bid_or_name:
        return bid_or_name
    try:
        get_branch_definition(base_path, branch_def_id=bid_or_name)
        return bid_or_name
    except KeyError:
        pass
    needle = bid_or_name.lower()
    for b in list_branch_definitions(base_path, viewer=_current_actor()):
        if (b.get("name") or "").lower() == needle:
            return b["branch_def_id"]
    return bid_or_name


def _ext_branch_get(kwargs: dict[str, Any]) -> str:
    from workflow.api.engine_helpers import _current_actor
    from workflow.api.market import _gates_enabled
    from workflow.daemon_server import get_branch_definition, list_gate_claims

    bid = _resolve_branch_id(kwargs.get("branch_def_id", "").strip(), _base_path())
    if not bid:
        return json.dumps({"error": "branch_def_id is required."})
    try:
        branch = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({"error": f"Branch '{bid}' not found."})
    # Phase 6.2.2 — private Branches are not discoverable by non-owners.
    # Match the "not found" envelope so existence isn't leaked.
    visibility = branch.get("visibility", "public") or "public"
    if visibility == "private" and branch.get("author", "") != _current_actor():
        return json.dumps({"error": f"Branch '{bid}' not found."})
    # Phase 6.4: non-retracted claims for this Branch across all
    # Goals. Flag-gated placeholder when GATES_ENABLED=0 so UIs
    # render "gates off" distinct from "no claims yet."
    if _gates_enabled():
        branch["gate_claims"] = list_gate_claims(
            _base_path(),
            branch_def_id=bid,
            include_retracted=False,
        )
    else:
        branch["gate_claims"] = []
        branch["gate_status"] = "gates_disabled"
    related = _related_wiki_pages(branch)
    branch["related_wiki_pages"] = related["items"]
    branch["related_wiki_pages_truncated"] = related["truncated_count"]
    unapproved_sc = [
        {"node_id": nd.get("node_id", ""), "display_name": nd.get("display_name", "")}
        for nd in branch.get("node_defs", [])
        if nd.get("source_code") and not nd.get("approved", False)
    ]
    branch["unapproved_source_code_nodes"] = unapproved_sc
    branch["runnable"] = not unapproved_sc
    return json.dumps(branch, default=str)


def _ext_branch_list(kwargs: dict[str, Any]) -> str:
    from workflow.api.engine_helpers import _current_actor
    from workflow.daemon_server import list_branch_definitions

    # Phase 6.2.2 — visibility-aware listing. Viewer sees public
    # Branches and any private Branches they authored.
    rows = list_branch_definitions(
        _base_path(),
        domain_id=kwargs.get("domain_id", ""),
        author=kwargs.get("author", ""),
        goal_id=kwargs.get("goal_id", ""),
        viewer=_current_actor(),
    )

    # requires_sandbox filter: "none" = design-only branches only (no node
    # has requires_sandbox=True); "any" = branches that have at least one
    # sandbox-requiring node. Omit / empty = no filter.
    rs_filter = (kwargs.get("requires_sandbox") or "").strip().lower()

    summaries = []
    for r in rows:
        node_defs = r.get("node_defs", [])
        has_sandbox_nodes = any(nd.get("requires_sandbox") for nd in node_defs)
        if rs_filter == "none" and has_sandbox_nodes:
            continue
        if rs_filter == "any" and not has_sandbox_nodes:
            continue

        # node_count MUST match describe_branch's count
        # (``len(branch.node_defs)`` at line ~4924) — that's the
        # source of truth. The old formula added ``graph.nodes +
        # node_defs`` which double-counted because graph.nodes is a
        # compiled-topology view that overlaps with node_defs.
        node_count = len(node_defs)
        summaries.append({
            "branch_def_id": r.get("branch_def_id"),
            "name": r.get("name"),
            "author": r.get("author"),
            "domain_id": r.get("domain_id"),
            "goal_id": r.get("goal_id"),
            "node_count": node_count,
            "skill_count": len(r.get("skills", []) or []),
            "published": r.get("published", False),
            "visibility": r.get("visibility", "public"),
            "has_sandbox_nodes": has_sandbox_nodes,
        })
    return json.dumps({"branches": summaries, "count": len(summaries)})


def _ext_branch_delete(kwargs: dict[str, Any]) -> str:
    from workflow.daemon_server import delete_branch_definition

    bid = kwargs.get("branch_def_id", "").strip()
    if not bid:
        return json.dumps({"error": "branch_def_id is required."})
    removed = delete_branch_definition(_base_path(), branch_def_id=bid)
    if not removed:
        return json.dumps({"error": f"Branch '{bid}' not found."})
    return json.dumps({"branch_def_id": bid, "status": "deleted"})


def _ext_branch_add_node(kwargs: dict[str, Any]) -> str:
    from workflow.api.engine_helpers import (
        _current_actor,
        _format_commit_failed,
        _storage_backend,
    )
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import get_branch_definition
    from workflow.identity import git_author

    verbose = str(kwargs.get("verbose") or "").strip().lower() in ("true", "1", "yes")
    bid = kwargs.get("branch_def_id", "").strip()
    nid = kwargs.get("node_id", "").strip()
    if not bid or not nid:
        return json.dumps({
            "error": "branch_def_id and node_id are required.",
        })

    # Normalize kwargs into a node spec dict so we can share the
    # build_branch resolver (which checks node_ref / intent and
    # refuses to silently shadow an existing standalone node — #66).
    raw: dict[str, Any] = {
        "node_id": nid,
        "display_name": kwargs.get("display_name", "").strip(),
        "description": kwargs.get("description", ""),
        "phase": kwargs.get("phase", "") or "custom",
        "input_keys": kwargs.get("input_keys", ""),
        "output_keys": kwargs.get("output_keys", ""),
        "source_code": kwargs.get("source_code", ""),
        "prompt_template": kwargs.get("prompt_template", ""),
        "author": kwargs.get("author") or _current_actor(),
    }
    if "node_ref" in kwargs:
        raw["node_ref"] = kwargs["node_ref"]
    if "intent" in kwargs:
        raw["intent"] = kwargs["intent"]

    try:
        source_dict = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({"error": f"Branch '{bid}' not found."})

    branch = BranchDefinition.from_dict(source_dict)
    err = _apply_node_spec(branch, raw)
    if err:
        return json.dumps({"error": err})

    # The resolved node may have been renamed; capture the final id
    # from the mutated branch BEFORE persisting.
    final_nid = branch.node_defs[-1].node_id
    try:
        _storage_backend().save_branch_and_commit(
            branch,
            author=git_author(_current_actor()),
            message=f"branches.add_node: {bid}.{final_nid}",
            force=bool(kwargs.get("force", False)),
        )
    except CommitFailedError as exc:
        return json.dumps(_format_commit_failed(exc))
    add_node_payload: dict[str, Any] = {
        "branch_def_id": bid,
        "node_id": final_nid,
        "status": "added",
    }
    if verbose:
        added = next(
            (n for n in branch.node_defs if n.node_id == final_nid), None
        )
        if added is not None:
            add_node_payload["node_def"] = added.to_dict()
    return json.dumps(add_node_payload, default=str)


def _ext_branch_connect_nodes(kwargs: dict[str, Any]) -> str:
    from workflow.api.engine_helpers import (
        _current_actor,
        _format_commit_failed,
        _storage_backend,
    )
    from workflow.branches import BranchDefinition, EdgeDefinition
    from workflow.daemon_server import get_branch_definition
    from workflow.identity import git_author

    verbose = str(kwargs.get("verbose") or "").strip().lower() in ("true", "1", "yes")
    bid = kwargs.get("branch_def_id", "").strip()
    src = kwargs.get("from_node", "").strip()
    dst = kwargs.get("to_node", "").strip()
    if not (bid and src and dst):
        return json.dumps({
            "error": "branch_def_id, from_node, and to_node are required.",
        })

    try:
        source_dict = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({"error": f"Branch '{bid}' not found."})

    branch = BranchDefinition.from_dict(source_dict)
    branch.edges.append(EdgeDefinition(from_node=src, to_node=dst))

    try:
        _storage_backend().save_branch_and_commit(
            branch,
            author=git_author(_current_actor()),
            message=f"branches.connect_nodes: {bid} {src}->{dst}",
            force=bool(kwargs.get("force", False)),
        )
    except CommitFailedError as exc:
        return json.dumps(_format_commit_failed(exc))
    connect_payload: dict[str, Any] = {
        "branch_def_id": bid,
        "from_node": src,
        "to_node": dst,
        "status": "connected",
    }
    if verbose:
        connect_payload["edge_count"] = len(branch.edges)
    return json.dumps(connect_payload, default=str)


def _ext_branch_set_entry_point(kwargs: dict[str, Any]) -> str:
    from workflow.api.engine_helpers import (
        _current_actor,
        _format_commit_failed,
        _storage_backend,
    )
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import get_branch_definition
    from workflow.identity import git_author

    verbose = str(kwargs.get("verbose") or "").strip().lower() in ("true", "1", "yes")
    bid = kwargs.get("branch_def_id", "").strip()
    nid = kwargs.get("node_id", "").strip()
    if not (bid and nid):
        return json.dumps({
            "error": "branch_def_id and node_id are required.",
        })

    try:
        source_dict = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({"error": f"Branch '{bid}' not found."})

    branch = BranchDefinition.from_dict(source_dict)
    branch.entry_point = nid

    try:
        _storage_backend().save_branch_and_commit(
            branch,
            author=git_author(_current_actor()),
            message=f"branches.set_entry_point: {bid}.{nid}",
            force=bool(kwargs.get("force", False)),
        )
    except CommitFailedError as exc:
        return json.dumps(_format_commit_failed(exc))
    entry_payload: dict[str, Any] = {
        "branch_def_id": bid,
        "entry_point": nid,
        "status": "set",
    }
    if verbose:
        entry_payload["node_count"] = len(branch.node_defs)
    return json.dumps(entry_payload, default=str)


def _ext_branch_add_state_field(kwargs: dict[str, Any]) -> str:
    from workflow.api.engine_helpers import (
        _current_actor,
        _format_commit_failed,
        _storage_backend,
    )
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import get_branch_definition
    from workflow.identity import git_author

    verbose = str(kwargs.get("verbose") or "").strip().lower() in ("true", "1", "yes")
    bid = kwargs.get("branch_def_id", "").strip()
    fname = kwargs.get("field_name", "").strip()
    ftype = kwargs.get("field_type", "").strip() or "str"
    if not (bid and fname):
        return json.dumps({
            "error": "branch_def_id and field_name are required.",
        })

    try:
        source_dict = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({"error": f"Branch '{bid}' not found."})

    branch = BranchDefinition.from_dict(source_dict)
    if any(f.get("name") == fname for f in branch.state_schema):
        return json.dumps({
            "error": f"State field '{fname}' already exists on this branch.",
        })

    field_entry: dict[str, Any] = {
        "name": fname,
        "type": ftype,
        "description": kwargs.get("description", ""),
    }
    reducer = kwargs.get("reducer", "").strip()
    if reducer:
        field_entry["reducer"] = reducer
    default = kwargs.get("field_default", "")
    if default != "":
        field_entry["default"] = default

    branch.state_schema.append(field_entry)
    try:
        _storage_backend().save_branch_and_commit(
            branch,
            author=git_author(_current_actor()),
            message=f"branches.add_state_field: {bid}.{fname}",
            force=bool(kwargs.get("force", False)),
        )
    except CommitFailedError as exc:
        return json.dumps(_format_commit_failed(exc))
    state_payload: dict[str, Any] = {
        "branch_def_id": bid,
        "field_name": fname,
        "status": "added",
    }
    if verbose:
        state_payload["field_count"] = len(branch.state_schema)
    return json.dumps(state_payload, default=str)


def _ext_branch_validate(kwargs: dict[str, Any]) -> str:
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import get_branch_definition

    bid = kwargs.get("branch_def_id", "").strip()
    if not bid:
        return json.dumps({"error": "branch_def_id is required."})
    try:
        source_dict = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({"error": f"Branch '{bid}' not found."})

    branch = BranchDefinition.from_dict(source_dict)
    errors = branch.validate()

    # BUG-031: surface unapproved source_code nodes so the chatbot can warn
    # the user before they attempt run_branch (which would fail with a
    # permission-denied error and no clear remediation path).
    unapproved_sc = [
        {"node_id": nd.get("node_id", ""), "display_name": nd.get("display_name", "")}
        for nd in source_dict.get("node_defs", [])
        if nd.get("source_code") and not nd.get("approved", False)
    ]

    # sandbox-compat warning: list any requires_sandbox=True nodes when
    # the host's bwrap probe says sandbox is unavailable. Non-fatal.
    sandbox_warnings: list[str] = []
    try:
        from workflow.providers.base import get_sandbox_status
        sb = get_sandbox_status()
        if not sb.get("bwrap_available"):
            sandbox_nodes = [
                nd.node_id
                for nd in branch.node_defs
                if getattr(nd, "requires_sandbox", False)
            ]
            if sandbox_nodes:
                reason = sb.get("reason") or "bwrap unavailable"
                sandbox_warnings.append(
                    f"This branch contains {len(sandbox_nodes)} node(s) that "
                    f"require a sandbox ({', '.join(sorted(sandbox_nodes))}) but "
                    f"the host sandbox probe returned: {reason}. "
                    f"These nodes will fail at runtime. Options: enable bwrap "
                    f"on the host, or use a branch variant without "
                    f"requires_sandbox=true nodes (design-only branch)."
                )
    except Exception:  # noqa: BLE001 — best-effort non-blocking warning
        pass

    return json.dumps({
        "branch_def_id": bid,
        "valid": not errors,
        "errors": errors,
        "runnable": not errors and not unapproved_sc,
        "unapproved_source_code_nodes": unapproved_sc,
        "sandbox_warnings": sandbox_warnings,
    })


_MERMAID_ID_SAFE = re.compile(r"[^A-Za-z0-9_]")


def _mermaid_node_id(raw: str) -> str:
    """Return a Mermaid-safe node identifier.

    Mermaid IDs must be alphanumeric/underscore. Node IDs in our branches
    are usually snake_case so this is a noop for well-formed inputs.
    """
    cleaned = _MERMAID_ID_SAFE.sub("_", raw)
    if cleaned and cleaned[0].isdigit():
        cleaned = "n_" + cleaned
    return cleaned or "node"


def _mermaid_label(text: str) -> str:
    """Escape label text for use inside Mermaid's ``["..."]`` node form."""
    return text.replace('"', "'").replace("\n", " ")


def _branch_mermaid(branch: Any) -> str:
    """Render a BranchDefinition as a Mermaid ``flowchart LR`` block.

    Claude.ai and many markdown clients auto-render fenced ``mermaid``
    code blocks. The returned string includes the fence so callers can
    embed it directly in prose. START/END are rendered as stadium shapes;
    everything else uses the default rectangle with its display_name.
    """
    lines: list[str] = ["```mermaid", "flowchart LR"]

    # START/END get stadium shape so they read as terminals.
    lines.append('    START(["START"])')
    lines.append('    END(["END"])')

    for node in branch.node_defs:
        nid = _mermaid_node_id(node.node_id)
        label = _mermaid_label(node.display_name or node.node_id)
        lines.append(f'    {nid}["{label}"]')

    # Include graph_nodes that weren't also declared as node_defs.
    defined_ids = {_mermaid_node_id(n.node_id) for n in branch.node_defs}
    for gn in branch.graph_nodes:
        nid = _mermaid_node_id(gn.id)
        if nid not in defined_ids and nid not in ("START", "END"):
            lines.append(f'    {nid}["{gn.id}"]')
            defined_ids.add(nid)

    for edge in branch.edges:
        src = _mermaid_node_id(edge.from_node)
        dst = _mermaid_node_id(edge.to_node)
        lines.append(f"    {src} --> {dst}")

    for cedge in branch.conditional_edges:
        src = _mermaid_node_id(cedge.from_node)
        for label, target in cedge.conditions.items():
            dst = _mermaid_node_id(target)
            lines.append(f"    {src} -.{_mermaid_label(label)}.-> {dst}")

    if branch.entry_point:
        entry_id = _mermaid_node_id(branch.entry_point)
        if entry_id not in ("START", "END"):
            lines.append(f"    class {entry_id} entry")
            lines.append(
                "    classDef entry stroke:#4a90e2,stroke-width:3px"
            )

    lines.append("```")
    return "\n".join(lines)


# STATUS.md Approved-bugs 2026-04-22 reshape of BUG-018 (maintainer-notes).
# The wiki already carries the cross-reference surface this feature needs —
# instead of adding a per-node `related_notes` field to NodeDefinition,
# surface wiki pages whose text mentions the branch_def_id or any of its
# node_ids. Always-on (no flag); always-bounded (top 20, summary ≤140 chars).
_RELATED_WIKI_CAP = 20
_RELATED_SUMMARY_MAX = 140


def _related_summary(body: str, meta: dict[str, str]) -> str:
    """First prose paragraph of ``body`` clipped to ``_RELATED_SUMMARY_MAX``.

    Skips heading-only lines (``#`` prefix) when picking the first
    paragraph. Falls back to the frontmatter ``description`` field if
    no prose is found; empty string if neither exists.
    """
    paragraph: list[str] = []
    for raw_line in body.split("\n"):
        line = raw_line.strip()
        if not line:
            if paragraph:
                break
            continue
        if line.startswith("#"):
            if paragraph:
                break
            continue
        paragraph.append(line)
    text = " ".join(paragraph).strip()
    if not text:
        text = (meta.get("description", "") or "").strip()
    if len(text) > _RELATED_SUMMARY_MAX:
        # Reserve one char for the ellipsis so total stays ≤ cap.
        return text[: _RELATED_SUMMARY_MAX - 1].rstrip() + "…"
    return text


def _related_wiki_pages(branch: dict[str, Any]) -> dict[str, Any]:
    """Find wiki pages that mention this branch's id or any node id.

    Returns ``{"items": [...], "truncated_count": int}``. Each item has
    ``path``, ``title``, ``summary``, ``matched_via``. Sorted by
    (matched_via count desc, title asc). Capped at ``_RELATED_WIKI_CAP``.
    """
    bid = (branch.get("branch_def_id") or "").strip()
    node_ids: list[str] = []
    for n in branch.get("node_defs", []) or []:
        nid = (n.get("node_id") or "").strip() if isinstance(n, dict) else ""
        if nid and nid not in node_ids:
            node_ids.append(nid)

    terms: list[tuple[str, str]] = []
    if bid:
        terms.append(("branch_def_id", bid.lower()))
    for nid in node_ids:
        terms.append((f"node:{nid}", nid.lower()))
    if not terms:
        return {"items": [], "truncated_count": 0}

    pages = (
        _find_all_pages(_wiki_pages_dir()) + _find_all_pages(_wiki_drafts_dir())
    )
    scored: list[dict[str, Any]] = []
    for p in pages:
        raw = _read_text(p)
        if not raw:
            continue
        meta, body = _parse_frontmatter(raw)
        title = meta.get("title", p.stem)
        haystack = (title + "\n" + body).lower()
        matched_via: list[str] = []
        for label, needle in terms:
            if needle and needle in haystack:
                matched_via.append(label)
        if not matched_via:
            continue
        scored.append({
            "path": _page_rel_path(p),
            "title": title,
            "summary": _related_summary(body, meta),
            "matched_via": matched_via,
        })

    scored.sort(key=lambda x: (-len(x["matched_via"]), x["title"].lower()))
    total = len(scored)
    top = scored[:_RELATED_WIKI_CAP]
    truncated = total - len(top) if total > _RELATED_WIKI_CAP else 0
    return {"items": top, "truncated_count": truncated}


def _ext_branch_describe(kwargs: dict[str, Any]) -> str:
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import get_branch_definition

    bid = _resolve_branch_id(kwargs.get("branch_def_id", "").strip(), _base_path())
    if not bid:
        return json.dumps({"error": "branch_def_id is required."})
    try:
        source_dict = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({"error": f"Branch '{bid}' not found."})

    branch = BranchDefinition.from_dict(source_dict)
    errors = branch.validate()

    unapproved_sc = [
        {"node_id": nd.get("node_id", ""), "display_name": nd.get("display_name", "")}
        for nd in source_dict.get("node_defs", [])
        if nd.get("source_code") and not nd.get("approved", False)
    ]

    node_lines = [
        f"  - {n.node_id}: {n.display_name}"
        + (f" ({n.phase})" if n.phase != "custom" else "")
        for n in branch.node_defs
    ] or ["  (no nodes yet)"]

    edge_lines = [
        f"  - {e.from_node} -> {e.to_node}" for e in branch.edges
    ] or ["  (no edges yet)"]

    state_lines = [
        f"  - {f.get('name')}: {f.get('type', 'str')}"
        + (f" [{f.get('reducer')}]" if f.get("reducer") else "")
        for f in branch.state_schema
    ] or ["  (no state fields yet)"]

    approval_warning_lines = [
        f"  - APPROVAL REQUIRED: node '{n['node_id']}' ({n['display_name']}) has"
        " unapproved source_code — host must run extensions action=approve_source_code"
        " before this branch can run."
        for n in unapproved_sc
    ]

    problem_lines = (
        [f"  - {err}" for err in errors]
        if errors
        else ["  (none — structure is valid)"]
    )

    mermaid = _branch_mermaid(branch)

    summary_parts = [
        f"Branch: {branch.name or '(unnamed)'}  [{branch.branch_def_id}]",
        f"Author: {branch.author}   Domain: {branch.domain_id}",
        f"Entry point: {branch.entry_point or '(not set)'}",
        "",
        f"Nodes ({len(branch.node_defs)}):",
        *node_lines,
        "",
        f"Edges ({len(branch.edges)}):",
        *edge_lines,
        "",
        f"State schema ({len(branch.state_schema)}):",
        *state_lines,
        "",
        "Open problems:",
        *problem_lines,
    ]
    if approval_warning_lines:
        summary_parts += ["", "Approval warnings (branch NOT runnable):"]
        summary_parts += approval_warning_lines
    run_note = (
        "Note: this branch has unapproved source_code nodes and must be "
        "approved before it can run."
        if unapproved_sc
        else (
            "Note: run this branch with action='run_branch' once validated. "
            "Pass state field values via inputs_json."
        )
    )
    summary_parts += ["", "Graph:", mermaid, "", run_note]
    summary = "\n".join(summary_parts)
    related = _related_wiki_pages(source_dict)

    # Lineage: expose fork_from + compute fork_descendants.
    fork_from = source_dict.get("fork_from")
    from workflow.branch_versions import list_branch_versions
    from workflow.daemon_server import list_branch_definitions

    my_versions = list_branch_versions(_base_path(), bid, limit=500)
    my_version_ids = {v.branch_version_id for v in my_versions}
    fork_descendants: list[dict[str, Any]] = []
    for b in list_branch_definitions(_base_path(), include_private=False):
        ff = b.get("fork_from")
        if ff and ff in my_version_ids:
            fork_descendants.append({
                "branch_def_id": b["branch_def_id"],
                "author": b.get("author", ""),
                "published_versions_count": len(
                    list_branch_versions(_base_path(), b["branch_def_id"], limit=500)
                ),
            })

    return json.dumps({
        "branch_def_id": bid,
        "summary": summary,
        "mermaid": mermaid,
        "valid": not errors,
        "error_count": len(errors),
        "runnable": not errors and not unapproved_sc,
        "unapproved_source_code_nodes": unapproved_sc,
        "fork_from": fork_from,
        "fork_descendants": fork_descendants,
        "related_wiki_pages": related["items"],
        "related_wiki_pages_truncated": related["truncated_count"],
    })


# ── Composite: build_branch / patch_branch ────────────────────────────────
# Per docs/specs/composite_branch_actions.md: Claude.ai's per-turn tool-call
# budget tops out around 15–20 atomic actions, below a full workflow build.
# Composite actions let a client ship one spec / one batch and get back a
# validated branch. build_branch is strict-with-suggestions (reject
# ambiguous, propose concrete fixes). patch_branch is transactional (all
# ops land or none).


_VALID_STATE_TYPES = {"str", "int", "float", "bool", "list", "dict", "any"}


def _suggest_entry_point(branch: Any) -> str:
    if not branch.graph_nodes:
        return ""
    incoming: set[str] = set()
    for e in branch.edges:
        if e.to_node and e.to_node != "START":
            incoming.add(e.to_node)
    for gn in branch.graph_nodes:
        if gn.id not in incoming:
            return gn.id
    return branch.graph_nodes[0].id


def _closest_state_type(raw: str) -> str:
    lower = (raw or "").lower()
    if lower in _VALID_STATE_TYPES:
        return lower
    for valid in _VALID_STATE_TYPES:
        if valid.startswith(lower) or lower.startswith(valid):
            return valid
    return "any"


def _errors_to_suggestions(
    branch: Any, errors: list[str],
) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []
    for err in errors:
        low = err.lower()
        if "entry point is required" in low:
            suggestions.append({
                "issue": err,
                "proposed_fix": (
                    f"Set entry_point to '{_suggest_entry_point(branch)}'."
                    if _suggest_entry_point(branch)
                    else "Add at least one node before setting entry_point."
                ),
            })
        elif "not a defined node" in low or "is not defined" in low:
            suggestions.append({
                "issue": err,
                "proposed_fix": (
                    "Either add the missing node via node_defs, or remove "
                    "the edge / entry_point that references it."
                ),
            })
        elif "not reachable from" in low:
            suggestions.append({
                "issue": err,
                "proposed_fix": (
                    "Add an incoming edge from a reachable node, or remove "
                    "the orphan node."
                ),
            })
        elif "cycle without exit" in low:
            suggestions.append({
                "issue": err,
                "proposed_fix": (
                    "Add an edge from a node inside the cycle to END, or "
                    "convert one edge to a conditional edge with an END "
                    "target."
                ),
            })
        elif "collides with a graph node id" in low:
            state_field = ""
            match = re.search(r"State field name '([^']+)'", err)
            if match:
                state_field = match.group(1)
            suggestions.append({
                "issue": err,
                "proposed_fix": (
                    f"Rename state_schema field '{state_field}' or the "
                    f"graph node ID '{state_field}' so they are distinct "
                    "before running this branch."
                    if state_field
                    else "Rename the colliding state_schema field or graph "
                    "node ID so they are distinct before running this branch."
                ),
            })
        elif "at least one node" in low:
            suggestions.append({
                "issue": err,
                "proposed_fix": (
                    "Add at least one node_def + graph_node entry."
                ),
            })
        elif "branch name is required" in low:
            suggestions.append({
                "issue": err,
                "proposed_fix": "Pass a non-empty 'name' in the spec.",
            })
        elif "duplicate" in low:
            suggestions.append({
                "issue": err,
                "proposed_fix": "Rename the duplicate id to a unique value.",
            })
        else:
            suggestions.append({
                "issue": err,
                "proposed_fix": "Review this error and reshape the spec.",
            })
    return suggestions


def _resolve_node_spec(
    raw: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    """Resolve a raw node spec that may contain ``node_ref`` or just a
    ``node_id`` that collides with an existing standalone/branch node.

    Returns ``(resolved_spec, error)``. On success ``error`` is empty
    and ``resolved_spec`` is a fully-populated dict ready to build a
    ``NodeDefinition`` from. On failure ``resolved_spec`` is ``None``
    and ``error`` explains what the caller must do.

    The shape changes we accept are:

    - ``node_ref={"source": "standalone", "node_id": "X"}`` — copy the
      canonical standalone registration X into this branch.
    - ``node_ref={"source": "<branch_def_id>", "node_id": "X"}`` —
      copy node X from another branch.
    - Plain inline spec (``node_id``/``display_name``/...): used as-is,
      EXCEPT we refuse to silently shadow an existing standalone
      registration (#66). The caller must either pick a different
      ``node_id`` or pass ``intent="copy"`` to opt into the copy.

    ``intent="reference"`` is reserved for a future live-reference
    mode. v1 only supports ``intent="copy"``; other values error.
    """
    from workflow.api.extensions import _load_nodes

    nid = (raw.get("node_id") or "").strip()
    intent = (raw.get("intent") or "").strip().lower()
    if intent and intent not in ("copy", "reference"):
        return None, (
            f"intent='{raw.get('intent')}' is unknown. "
            "Use 'copy' to snapshot an existing node into this "
            "branch, or omit intent and pass inline fields."
        )
    if intent == "reference":
        return None, (
            "intent='reference' (live shared node) is not supported "
            "yet. Use intent='copy' to snapshot a standalone node "
            "into this branch."
        )

    node_ref = raw.get("node_ref")
    if node_ref:
        if not isinstance(node_ref, dict):
            return None, "node_ref must be an object with 'source' and 'node_id'."
        ref_source = (node_ref.get("source") or "").strip()
        ref_nid = (node_ref.get("node_id") or nid).strip()
        if not ref_source or not ref_nid:
            return None, "node_ref requires 'source' and 'node_id'."
        resolved, err = _lookup_node_body(ref_source, ref_nid)
        if err:
            return None, err
        # Start from the resolved body, then overlay any caller-supplied
        # fields so the client can, e.g., rename the copy.
        merged: dict[str, Any] = dict(resolved)
        merged["node_id"] = nid or ref_nid
        for field_key in (
            "display_name", "description", "phase", "input_keys",
            "output_keys", "source_code", "prompt_template", "author",
        ):
            if field_key in raw and raw[field_key] not in (None, ""):
                merged[field_key] = raw[field_key]
        return merged, ""

    # No explicit ref — fall back to raw. If the node_id shadows a
    # standalone registration, demand explicit intent so the caller
    # cannot silently create a hollow clone.
    if nid and intent != "copy":
        try:
            standalone = _load_nodes()
        except Exception:
            standalone = []
        hit = next(
            (n for n in standalone if n.get("node_id") == nid), None,
        )
        if hit:
            return None, (
                f"node_id '{nid}' matches an existing standalone "
                "registered node. Pass node_ref="
                f"{{'source': 'standalone', 'node_id': '{nid}'}} to "
                "copy its body into this branch, or pass intent='copy' "
                "on this spec if you intentionally want the existing "
                "body, or rename this node to avoid collision."
            )
    raw = dict(raw)
    raw.pop("approved", None)
    return raw, ""


def _lookup_node_body(
    source: str, node_id: str,
) -> tuple[dict[str, Any], str]:
    """Return the canonical node body for a ``node_ref`` lookup.

    ``source`` is either the literal string ``'standalone'`` (look in
    the standalone node registry) or a branch_def_id (look in that
    branch's ``node_defs``).
    """
    from workflow.api.extensions import _load_nodes

    if source == "standalone":
        try:
            nodes = _load_nodes()
        except Exception as exc:
            return {}, f"could not load standalone node registry: {exc}"
        hit = next(
            (n for n in nodes if n.get("node_id") == node_id), None,
        )
        if not hit:
            return {}, (
                f"standalone node '{node_id}' not found. "
                "Check `extensions action=list` for registered nodes."
            )
        return {
            "node_id": hit.get("node_id", node_id),
            "display_name": hit.get("display_name", node_id),
            "description": hit.get("description", ""),
            "phase": hit.get("phase", "custom"),
            "input_keys": list(hit.get("input_keys") or []),
            "output_keys": list(hit.get("output_keys") or []),
            "source_code": hit.get("source_code", ""),
            "prompt_template": hit.get("prompt_template", ""),
            "author": hit.get("author", ""),
            "approved": bool(hit.get("approved", False)),
        }, ""

    # Otherwise treat `source` as a branch_def_id.
    from workflow.daemon_server import get_branch_definition

    try:
        source_branch = get_branch_definition(
            _base_path(), branch_def_id=source,
        )
    except KeyError:
        return {}, (
            f"node_ref source '{source}' is neither 'standalone' nor a "
            "known branch_def_id."
        )
    for nd in source_branch.get("node_defs") or []:
        if nd.get("node_id") == node_id:
            return {
                "node_id": nd.get("node_id", node_id),
                "display_name": nd.get("display_name", node_id),
                "description": nd.get("description", ""),
                "phase": nd.get("phase", "custom"),
                "input_keys": list(nd.get("input_keys") or []),
                "output_keys": list(nd.get("output_keys") or []),
                "source_code": nd.get("source_code", ""),
                "prompt_template": nd.get("prompt_template", ""),
                "author": nd.get("author", ""),
                "approved": bool(nd.get("approved", False)),
            }, ""
    return {}, (
        f"node '{node_id}' not found on branch '{source}'. "
        "Use `extensions action=get_branch` to list its nodes."
    )


def _apply_node_spec(branch: Any, raw: dict[str, Any]) -> str:
    from workflow.api.engine_helpers import _current_actor
    from workflow.branches import GraphNodeRef, NodeDefinition

    resolved, err = _resolve_node_spec(raw)
    if err:
        return err
    raw = resolved  # resolved may be the same dict, or a merged copy

    nid = (raw.get("node_id") or "").strip()
    display = (raw.get("display_name") or "").strip()
    if not nid or not display:
        return "node spec missing node_id or display_name"

    source_code = raw.get("source_code") or ""
    prompt_template = raw.get("prompt_template") or ""
    if source_code and prompt_template:
        return (
            f"node '{nid}' has both source_code and prompt_template — "
            "pick one."
        )

    phase = (raw.get("phase") or "").strip() or "custom"
    in_keys, err = _coerce_node_keys(raw.get("input_keys"), "input_keys")
    if err:
        return err
    out_keys, err = _coerce_node_keys(raw.get("output_keys"), "output_keys")
    if err:
        return err
    # BUG-045: thread the three sub-branch / sibling-run spec fields. The
    # compiler reads them (workflow/graph_compiler.py:_build_invoke_branch /
    # invoke_branch_version / await_run callables) and NodeDefinition
    # declares them (workflow/branches.py:267/285/294), but this authoring
    # plumbing was silently dropping the keys — callers got a node that
    # validated fine but ran as a no-op prompt-template. Mutual exclusivity
    # is enforced in BranchDefinition.validate(); we accept whatever the
    # caller provided and let validate() catch invalid combinations.
    invoke_branch = raw.get("invoke_branch_spec")
    invoke_branch_version = raw.get("invoke_branch_version_spec")
    await_run = raw.get("await_run_spec")
    invoke_branch_arg = invoke_branch if isinstance(invoke_branch, dict) else None
    invoke_branch_version_arg = (
        invoke_branch_version if isinstance(invoke_branch_version, dict) else None
    )
    await_run_arg = await_run if isinstance(await_run, dict) else None
    try:
        node = NodeDefinition(
            node_id=nid,
            display_name=display,
            description=raw.get("description", ""),
            phase=phase,
            input_keys=in_keys,
            output_keys=out_keys,
            source_code=source_code,
            prompt_template=prompt_template,
            author=raw.get("author") or _current_actor(),
            approved=bool(raw.get("approved", False)),
            invoke_branch_spec=invoke_branch_arg,
            invoke_branch_version_spec=invoke_branch_version_arg,
            await_run_spec=await_run_arg,
        )
    except ValueError as exc:
        return str(exc)

    if any(n.node_id == nid for n in branch.node_defs):
        return f"node '{nid}' already exists on the branch"

    branch.node_defs.append(node)
    branch.graph_nodes.append(GraphNodeRef(
        id=nid, node_def_id=nid, position=len(branch.graph_nodes),
    ))
    return ""


def _apply_edge_spec(branch: Any, raw: dict[str, Any]) -> str:
    from workflow.branches import EdgeDefinition

    src = (raw.get("from") or raw.get("from_node") or "").strip()
    dst = (raw.get("to") or raw.get("to_node") or "").strip()
    if not src or not dst:
        return "edge spec missing 'from' or 'to'"
    branch.edges.append(EdgeDefinition(from_node=src, to_node=dst))
    return ""


def _apply_conditional_edge_spec(branch: Any, raw: dict[str, Any]) -> str:
    from workflow.branches import ConditionalEdge

    src = (raw.get("from") or raw.get("from_node") or "").strip()
    if not src:
        return "conditional edge spec missing 'from'"
    conditions_raw = raw.get("conditions")
    if not isinstance(conditions_raw, dict) or not conditions_raw:
        return (
            "conditional edge spec requires a non-empty 'conditions' "
            "object mapping outcome strings to target node ids"
        )
    conditions: dict[str, str] = {}
    for outcome, target in conditions_raw.items():
        outcome_str = str(outcome).strip()
        target_str = str(target).strip()
        if not outcome_str or not target_str:
            return (
                "conditional edge outcome/target must be non-empty strings"
            )
        conditions[outcome_str] = target_str
    # Merge onto any existing edge from the same source so callers can
    # add one outcome at a time without wiping siblings.
    for existing in branch.conditional_edges:
        if existing.from_node == src:
            existing.conditions.update(conditions)
            return ""
    branch.conditional_edges.append(
        ConditionalEdge(from_node=src, conditions=conditions)
    )
    return ""


def _apply_state_field_spec(branch: Any, raw: dict[str, Any]) -> str:
    fname = (raw.get("name") or raw.get("field_name") or "").strip()
    if not fname:
        return "state field spec missing 'name'"
    if any(f.get("name") == fname for f in branch.state_schema):
        return f"state field '{fname}' already exists on the branch"
    ftype_raw = (raw.get("type") or raw.get("field_type") or "str").strip()
    ftype = _closest_state_type(ftype_raw)
    entry: dict[str, Any] = {
        "name": fname,
        "type": ftype,
        "description": raw.get("description", ""),
    }
    if raw.get("reducer"):
        entry["reducer"] = raw["reducer"]
    default = raw.get("default", raw.get("field_default", ""))
    if default != "":
        entry["default"] = default
    branch.state_schema.append(entry)
    if ftype_raw.lower() not in _VALID_STATE_TYPES:
        return (
            f"state field '{fname}' type '{ftype_raw}' unknown; "
            f"coerced to '{ftype}'."
        )
    return ""


def _staged_branch_from_spec(
    spec: dict[str, Any],
) -> tuple[Any, list[str]]:
    from workflow.api.engine_helpers import _current_actor
    from workflow.branches import BranchDefinition, normalize_branch_skill_snapshots

    errors: list[str] = []
    branch = BranchDefinition(
        name=(spec.get("name") or "").strip(),
        description=spec.get("description") or "",
        domain_id=(spec.get("domain_id") or "").strip() or "workflow",
        goal_id=(spec.get("goal_id") or "").strip(),
        author=(spec.get("author") or _current_actor()),
        tags=list(spec.get("tags") or []),
        skills=[],
        fork_from=spec.get("fork_from") or None,
    )

    try:
        branch.skills = normalize_branch_skill_snapshots(spec.get("skills") or [])
    except ValueError as exc:
        errors.append(str(exc))

    for idx, raw in enumerate(spec.get("node_defs") or spec.get("nodes") or []):
        err = _apply_node_spec(branch, raw)
        if err:
            errors.append(f"node[{idx}]: {err}")

    for idx, raw in enumerate(spec.get("edges") or []):
        err = _apply_edge_spec(branch, raw)
        if err:
            errors.append(f"edge[{idx}]: {err}")

    for idx, raw in enumerate(spec.get("conditional_edges") or []):
        err = _apply_conditional_edge_spec(branch, raw)
        if err:
            errors.append(f"conditional_edge[{idx}]: {err}")

    for idx, raw in enumerate(spec.get("state_schema") or []):
        err = _apply_state_field_spec(branch, raw)
        if err:
            errors.append(f"state_schema[{idx}]: {err}")

    entry = (spec.get("entry_point") or "").strip()
    if entry:
        branch.entry_point = entry

    return branch, errors


def _build_branch_text(branch: Any, *, truncated: bool) -> str:
    node_count = len(branch.node_defs)
    edge_count = len(branch.edges)
    head = (
        f"**Built branch '{branch.name or 'unnamed'}'**: "
        f"{node_count} nodes, {edge_count} edges, "
        f"{len(getattr(branch, 'skills', []) or [])} skills, "
        f"entry=`{branch.entry_point}`."
    )
    if truncated:
        return "\n".join([
            head,
            "",
            "_(Branch exceeds 12-node phone-legibility limit; "
            "full topology in structuredContent. Mermaid summary:)_",
            "",
            "```mermaid",
            "flowchart LR",
            f'    START(["START"]) --> entry["{_mermaid_label(branch.entry_point)}"]',
            f"    entry --> more[\"... {node_count - 1} more nodes\"]",
            '    more --> END(["END"])',
            "```",
        ])
    mermaid = _branch_mermaid(branch)
    state_lines = [f"State schema: {len(branch.state_schema)} field(s)."]
    return "\n".join([head, "", mermaid, "", *state_lines])


def _ext_branch_build(kwargs: dict[str, Any]) -> str:
    from workflow.daemon_server import save_branch_definition

    verbose = str(kwargs.get("verbose") or "").strip().lower() in ("true", "1", "yes")
    raw = (kwargs.get("spec_json") or "").strip()
    if not raw:
        return json.dumps({
            "status": "rejected",
            "error": "spec_json is required for build_branch.",
            "suggestions": [{
                "issue": "Empty spec.",
                "proposed_fix": (
                    "Pass a JSON object with at minimum `name` and a "
                    "non-empty `node_defs` list. See branch_design_guide."
                ),
            }],
        })
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as exc:
        return json.dumps({
            "status": "rejected",
            "error": f"spec_json is not valid JSON: {exc}",
            "suggestions": [{
                "issue": "spec_json did not parse.",
                "proposed_fix": "Validate JSON shape before sending.",
            }],
        })
    if not isinstance(spec, dict):
        return json.dumps({
            "status": "rejected",
            "error": "spec_json must decode to a JSON object.",
            "suggestions": [{
                "issue": "Top-level spec is not an object.",
                "proposed_fix": "Wrap the spec in { ... }.",
            }],
        })

    branch, staging_errors = _staged_branch_from_spec(spec)
    validation_errors = branch.validate()
    errors = staging_errors + validation_errors

    # Validate fork_from points to a real branch_version_id.
    if branch.fork_from:
        from workflow.branch_versions import get_branch_version
        if get_branch_version(_base_path(), branch.fork_from) is None:
            errors.append(
                f"fork_from '{branch.fork_from}' is not a known branch_version_id. "
                "Pass a published branch_version_id, not a branch_def_id."
            )

    if errors:
        suggestions = _errors_to_suggestions(branch, errors)
        text_lines = [
            f"**Build failed.** {len(errors)} problem(s) in spec:",
            "",
            *[f"- {err}" for err in errors],
        ]
        if suggestions:
            text_lines += [
                "",
                "Suggested fixes:",
                *[f"- {s['proposed_fix']}" for s in suggestions],
            ]
        return json.dumps({
            "text": "\n".join(text_lines),
            "status": "rejected",
            "errors": errors,
            "suggestions": suggestions,
            "attempted_spec": spec,
        })

    saved = save_branch_definition(_base_path(), branch_def=branch.to_dict())
    from workflow.branches import BranchDefinition as _BD

    persisted = _BD.from_dict(saved)
    truncated = len(persisted.node_defs) > 12
    text = _build_branch_text(persisted, truncated=truncated)
    payload: dict[str, Any] = {
        "text": text,
        "status": "built",
        "branch_def_id": persisted.branch_def_id,
        "name": persisted.name,
        "node_count": len(persisted.node_defs),
        "edge_count": len(persisted.edges),
        "skill_count": len(persisted.skills),
        "entry_point": persisted.entry_point,
        "validation_summary": "ok",
    }
    if verbose:
        payload["branch"] = saved
    return json.dumps(payload, default=str)


def _apply_patch_op(branch: Any, op: dict[str, Any]) -> str:
    name = (op.get("op") or "").strip().lower()
    if name == "add_node":
        return _apply_node_spec(branch, op)
    if name == "add_edge":
        return _apply_edge_spec(branch, op)
    if name == "add_state_field":
        return _apply_state_field_spec(branch, op)
    if name == "set_entry_point":
        nid = (op.get("node_id") or "").strip()
        if not nid:
            return "set_entry_point requires node_id"
        branch.entry_point = nid
        return ""
    if name == "set_goal":
        gid = (op.get("goal_id") or "").strip()
        if not gid:
            return "set_goal requires goal_id"
        branch.goal_id = gid
        return ""
    if name == "unset_goal":
        branch.goal_id = ""
        return ""
    if name == "remove_node":
        nid = (op.get("node_id") or "").strip()
        if not nid:
            return "remove_node requires node_id"
        before_n = len(branch.node_defs)
        branch.node_defs = [n for n in branch.node_defs if n.node_id != nid]
        branch.graph_nodes = [g for g in branch.graph_nodes if g.id != nid]
        branch.edges = [
            e for e in branch.edges
            if e.from_node != nid and e.to_node != nid
        ]
        if branch.entry_point == nid:
            branch.entry_point = ""
        if len(branch.node_defs) == before_n:
            return f"remove_node: node '{nid}' not found"
        return ""
    if name == "remove_edge":
        src = (op.get("from") or op.get("from_node") or "").strip()
        dst = (op.get("to") or op.get("to_node") or "").strip()
        if not src or not dst:
            return "remove_edge requires from and to"
        before = len(branch.edges)
        branch.edges = [
            e for e in branch.edges
            if not (e.from_node == src and e.to_node == dst)
        ]
        if len(branch.edges) == before:
            return f"remove_edge: {src}->{dst} not found"
        return ""
    if name == "add_conditional_edge":
        return _apply_conditional_edge_spec(branch, op)
    if name == "remove_conditional_edge":
        src = (op.get("from") or op.get("from_node") or "").strip()
        if not src:
            return "remove_conditional_edge requires 'from'"
        outcome = (op.get("outcome") or "").strip()
        for i, ce in enumerate(branch.conditional_edges):
            if ce.from_node != src:
                continue
            if not outcome:
                del branch.conditional_edges[i]
                return ""
            if outcome not in ce.conditions:
                return (
                    f"remove_conditional_edge: outcome '{outcome}' not "
                    f"found on edge from '{src}'"
                )
            del ce.conditions[outcome]
            if not ce.conditions:
                del branch.conditional_edges[i]
            return ""
        return f"remove_conditional_edge: no conditional edge from '{src}'"
    if name == "remove_state_field":
        fname = (op.get("name") or op.get("field_name") or "").strip()
        if not fname:
            return "remove_state_field requires name"
        before = len(branch.state_schema)
        branch.state_schema = [
            f for f in branch.state_schema if f.get("name") != fname
        ]
        if len(branch.state_schema) == before:
            return f"remove_state_field: '{fname}' not found"
        return ""
    if name == "update_node":
        nid = (op.get("node_id") or "").strip()
        if not nid:
            return "update_node requires node_id"
        for n in branch.node_defs:
            if n.node_id == nid:
                if "display_name" in op:
                    n.display_name = op["display_name"]
                if "description" in op:
                    n.description = op["description"]
                if "prompt_template" in op:
                    n.prompt_template = op["prompt_template"]
                if "source_code" in op:
                    n.source_code = op["source_code"]
                if "input_keys" in op:
                    keys, err = _coerce_node_keys(
                        op["input_keys"], "input_keys",
                    )
                    if err:
                        return err
                    n.input_keys = keys
                if "output_keys" in op:
                    keys, err = _coerce_node_keys(
                        op["output_keys"], "output_keys",
                    )
                    if err:
                        return err
                    n.output_keys = keys
                return ""
        return f"update_node: node '{nid}' not found"
    if name == "add_skill":
        from workflow.branches import normalize_branch_skill_snapshot

        raw_skill = op.get("skill") if isinstance(op.get("skill"), dict) else op
        try:
            skill = normalize_branch_skill_snapshot(raw_skill)
        except ValueError as exc:
            return str(exc)
        if any(s.get("skill_id") == skill["skill_id"] for s in branch.skills):
            return f"skill '{skill['skill_id']}' already exists"
        branch.skills.append(skill)
        return ""
    if name == "update_skill":
        from workflow.branches import normalize_branch_skill_snapshot

        skill_id = (op.get("skill_id") or op.get("id") or "").strip()
        if not skill_id:
            return "update_skill requires skill_id"
        for idx, existing in enumerate(branch.skills):
            if existing.get("skill_id") != skill_id:
                continue
            merged = dict(existing)
            update_payload = (
                op.get("skill") if isinstance(op.get("skill"), dict) else op
            )
            for key, value in update_payload.items():
                if key != "op":
                    merged[key] = value
            merged["skill_id"] = skill_id
            try:
                branch.skills[idx] = normalize_branch_skill_snapshot(merged)
            except ValueError as exc:
                return str(exc)
            return ""
        return f"update_skill: skill '{skill_id}' not found"
    if name == "remove_skill":
        skill_id = (op.get("skill_id") or op.get("id") or "").strip()
        if not skill_id:
            return "remove_skill requires skill_id"
        before = len(branch.skills)
        branch.skills = [
            skill for skill in branch.skills
            if skill.get("skill_id") != skill_id
        ]
        if len(branch.skills) == before:
            return f"remove_skill: skill '{skill_id}' not found"
        return ""
    if name == "set_skills":
        from workflow.branches import normalize_branch_skill_snapshots

        if "skills" not in op:
            return "set_skills requires a skills list"
        try:
            branch.skills = normalize_branch_skill_snapshots(op.get("skills"))
        except ValueError as exc:
            return str(exc)
        return ""
    # Branch-level metadata ops (#67). These let patch_branch rename /
    # retag / redescribe / publish a branch atomically, without the
    # previous delete-and-rebuild workaround that lost run history and
    # judgments.
    if name == "set_name":
        new_name = (op.get("name") or "").strip()
        if not new_name:
            return "set_name requires a non-empty name"
        branch.name = new_name
        return ""
    if name == "set_description":
        if "description" not in op:
            return "set_description requires a description field"
        branch.description = op.get("description") or ""
        return ""
    if name == "set_tags":
        if "tags" not in op:
            return "set_tags requires a tags list"
        raw_tags = op.get("tags")
        if raw_tags is None:
            raw_tags = []
        if isinstance(raw_tags, str):
            # Accept CSV too for parity with other surfaces.
            raw_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        if not isinstance(raw_tags, list):
            return "set_tags 'tags' must be a list (or CSV string)"
        branch.tags = [str(t).strip() for t in raw_tags if str(t).strip()]
        return ""
    if name == "set_published":
        if "published" not in op:
            return "set_published requires a 'published' boolean"
        val = op.get("published")
        if not isinstance(val, bool):
            return "set_published 'published' must be true or false"
        branch.published = val
        return ""
    if name == "set_visibility":
        # Phase 6.2.2 — private hides Branch + its gate claims from
        # non-owner callers.
        if "visibility" not in op:
            return "set_visibility requires a 'visibility' string"
        raw = op.get("visibility")
        if not isinstance(raw, str):
            return "set_visibility 'visibility' must be 'public' or 'private'"
        normalized = raw.strip().lower()
        if normalized not in ("public", "private"):
            return (
                "set_visibility 'visibility' must be 'public' or 'private'"
            )
        branch.visibility = normalized
        return ""
    if name == "set_fork_from":
        bvid = (op.get("branch_version_id") or "").strip()
        if not bvid:
            return "set_fork_from requires branch_version_id"
        if branch.fork_from is not None:
            return (
                f"set_fork_from: fork_from is already set to '{branch.fork_from}' "
                "and is immutable after set."
            )
        from workflow.branch_versions import get_branch_version
        if get_branch_version(_base_path(), bvid) is None:
            return (
                f"set_fork_from: '{bvid}' is not a known branch_version_id. "
                "Pass a published branch_version_id, not a branch_def_id."
            )
        branch.fork_from = bvid
        return ""
    return f"unknown op '{name}'"


def _ext_branch_patch(kwargs: dict[str, Any]) -> str:
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import (
        get_branch_definition,
        save_branch_definition,
    )

    verbose = str(kwargs.get("verbose") or "").strip().lower() in ("true", "1", "yes")
    bid = _resolve_branch_id(
        (kwargs.get("branch_def_id") or "").strip(), str(_base_path())
    )
    if not bid:
        return json.dumps({
            "status": "rejected",
            "error": "branch_def_id is required.",
        })
    raw = (kwargs.get("changes_json") or "").strip()
    if not raw:
        return json.dumps({
            "status": "rejected",
            "error": "changes_json is required (ordered list of ops).",
        })

    try:
        changes = json.loads(raw)
    except json.JSONDecodeError as exc:
        return json.dumps({
            "status": "rejected",
            "error": f"changes_json is not valid JSON: {exc}",
        })
    if not isinstance(changes, list):
        return json.dumps({
            "status": "rejected",
            "error": "changes_json must decode to a JSON list.",
        })

    try:
        source = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({
            "status": "rejected",
            "error": f"Branch '{bid}' not found.",
        })

    old_name = source.get("name", "")
    staging = BranchDefinition.from_dict(source)

    per_op_errors: list[dict[str, Any]] = []
    for idx, op in enumerate(changes):
        if not isinstance(op, dict):
            per_op_errors.append({
                "op_index": idx, "op": op,
                "error": "op must be an object with an 'op' key",
            })
            continue
        err = _apply_patch_op(staging, op)
        if err:
            per_op_errors.append({
                "op_index": idx, "op": op, "error": err,
            })

    validation_errors: list[str] = []
    if not per_op_errors:
        validation_errors = staging.validate()

    if per_op_errors or validation_errors:
        suggestions = _errors_to_suggestions(staging, validation_errors)
        text_lines = [
            f"**Patch rejected.** {len(per_op_errors)} op error(s), "
            f"{len(validation_errors)} validation error(s). No changes "
            "were applied.",
        ]
        if per_op_errors:
            text_lines += ["", "Op errors:"]
            for pe in per_op_errors:
                op_name = (
                    pe['op'].get('op', '?')
                    if isinstance(pe['op'], dict) else str(pe['op'])
                )
                text_lines.append(
                    f"- op[{pe['op_index']}] {op_name}: {pe['error']}"
                )
        if validation_errors:
            text_lines += ["", "Validation:"]
            for err in validation_errors:
                text_lines.append(f"- {err}")
        if suggestions:
            text_lines += ["", "Suggested fixes:"]
            for s in suggestions:
                text_lines.append(f"- {s['proposed_fix']}")
        return json.dumps({
            "text": "\n".join(text_lines),
            "status": "rejected",
            "errors": per_op_errors,
            "validation_errors": validation_errors,
            "suggestions": suggestions,
        })

    saved = save_branch_definition(_base_path(), branch_def=staging.to_dict())
    persisted = BranchDefinition.from_dict(saved)

    _SKIP_DIFF = {"updated_at", "created_at", "node_defs", "edges",
                  "conditional_edges", "graph_nodes", "state_schema", "stats"}
    patched_fields = [
        k for k in source
        if k not in _SKIP_DIFF and source.get(k) != saved.get(k)
    ]

    post_patch = {
        "branch_def_id": persisted.branch_def_id,
        "name": persisted.name,
        "entry_point": persisted.entry_point,
        "node_count": len(persisted.node_defs),
        "edge_count": len(persisted.edges),
        "skill_count": len(persisted.skills),
        "visibility": persisted.visibility,
    }

    truncated = len(persisted.node_defs) > 12
    text_lines = [
        f"**Patched branch '{persisted.name}'**: applied {len(changes)} op(s). "
        f"{len(persisted.node_defs)} nodes, {len(persisted.edges)} edges, "
        f"{len(persisted.skills)} skills, entry=`{persisted.entry_point}`.",
    ]
    if patched_fields:
        text_lines += ["", f"Changed fields: {', '.join(patched_fields)}."]
    if truncated:
        text_lines += [
            "",
            "_(Branch exceeds 12 nodes; full topology in structuredContent.)_",
        ]
    else:
        text_lines += ["", _branch_mermaid(persisted)]
    name_updated = persisted.name != old_name
    patch_payload: dict[str, Any] = {
        "text": "\n".join(text_lines),
        "status": "patched",
        "branch_def_id": persisted.branch_def_id,
        "ops_applied": len(changes),
        "node_count": len(persisted.node_defs),
        "edge_count": len(persisted.edges),
        "skill_count": len(persisted.skills),
        "patched_fields": patched_fields,
        "name_updated": name_updated,
        "new_name": persisted.name,
        "post_patch": post_patch,
    }
    if verbose:
        patch_payload["branch"] = saved
    return json.dumps(patch_payload, default=str)


def _ext_branch_update_node(kwargs: dict[str, Any]) -> str:
    """Update a single node in-place, keeping ``node_id`` stable.

    Phase 4 lineage + judgments are keyed on node_id, so edits must
    preserve identity. Same update semantics as the patch op of the same
    name; this standalone action bumps BranchDefinition.version (+1)
    so downstream lineage can distinguish pre/post-edit runs.
    """
    from workflow.api.extensions import VALID_PHASES
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import (
        get_branch_definition,
        save_branch_definition,
    )

    bid = _resolve_branch_id(
        (kwargs.get("branch_def_id") or "").strip(), str(_base_path())
    )
    nid = (kwargs.get("node_id") or "").strip()
    if not bid or not nid:
        return json.dumps({
            "status": "rejected",
            "error": "branch_def_id and node_id are required.",
        })

    # Accept updates as a JSON blob (changes_json) OR as individual
    # kwargs (display_name, description, phase, prompt_template,
    # source_code, input_keys, output_keys). Individual kwargs are
    # the phone-friendly shape; changes_json is for scripts batching.
    changes_raw = (kwargs.get("changes_json") or "").strip()
    updates: dict[str, Any] = {}
    if changes_raw:
        try:
            parsed = json.loads(changes_raw)
        except json.JSONDecodeError as exc:
            return json.dumps({
                "status": "rejected",
                "error": f"changes_json is not valid JSON: {exc}",
            })
        if not isinstance(parsed, dict):
            return json.dumps({
                "status": "rejected",
                "error": "changes_json must decode to an object.",
            })
        updates = parsed
    else:
        # Pull supported fields from the top-level kwargs.
        for field in (
            "display_name", "description", "phase",
            "prompt_template", "source_code",
        ):
            if kwargs.get(field):
                updates[field] = kwargs[field]
        if kwargs.get("input_keys"):
            updates["input_keys"] = kwargs["input_keys"]
        if kwargs.get("output_keys"):
            updates["output_keys"] = kwargs["output_keys"]
        # BUG-045: same plumbing fix as _apply_node_spec for the
        # update_node write path. update_node has its own kwargs-merge
        # logic and writes through save_branch_definition without
        # routing through _apply_node_spec. Each spec-bearing field can
        # arrive as a JSON-encoded string (kwargs-only callers can't
        # send raw dicts) or as a dict (changes_json path).
        for field in (
            "invoke_branch_spec",
            "invoke_branch_version_spec",
            "await_run_spec",
        ):
            raw_val = kwargs.get(field)
            if not raw_val:
                continue
            if isinstance(raw_val, dict):
                updates[field] = raw_val
            elif isinstance(raw_val, str):
                try:
                    decoded = json.loads(raw_val)
                except json.JSONDecodeError as exc:
                    return json.dumps({
                        "status": "rejected",
                        "error": f"{field} is not valid JSON: {exc}",
                    })
                if not isinstance(decoded, dict):
                    return json.dumps({
                        "status": "rejected",
                        "error": f"{field} must decode to an object.",
                    })
                updates[field] = decoded

    if not updates:
        return json.dumps({
            "status": "rejected",
            "error": (
                "No fields to update. Pass one or more of "
                "display_name / description / phase / prompt_template / "
                "source_code / input_keys / output_keys, or a "
                "changes_json object."
            ),
        })

    try:
        source = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({
            "status": "rejected",
            "error": f"Branch '{bid}' not found.",
        })

    staging = BranchDefinition.from_dict(source)
    target_node = next(
        (n for n in staging.node_defs if n.node_id == nid), None,
    )
    if target_node is None:
        return json.dumps({
            "status": "rejected",
            "error": f"Node '{nid}' not found on branch '{bid}'.",
        })

    # Reject ambiguous prompt_template + source_code combos explicitly
    # so we don't silently end up with both set.
    incoming_template = updates.get("prompt_template", "")
    incoming_source = updates.get("source_code", "")
    if incoming_template and incoming_source:
        return json.dumps({
            "status": "rejected",
            "error": (
                "Pass prompt_template OR source_code, not both. "
                "To switch types, clear the other field first."
            ),
        })

    try:
        if "display_name" in updates:
            target_node.display_name = updates["display_name"]
        if "description" in updates:
            target_node.description = updates["description"]
        if "phase" in updates:
            # NodeDefinition.__post_init__ guards valid phases, so we
            # validate here too.
            new_phase = updates["phase"] or "custom"
            if new_phase not in VALID_PHASES:
                return json.dumps({
                    "status": "rejected",
                    "error": (
                        f"Invalid phase '{new_phase}'. Must be one of: "
                        f"{', '.join(sorted(VALID_PHASES))}"
                    ),
                })
            target_node.phase = new_phase
        if "prompt_template" in updates:
            target_node.prompt_template = updates["prompt_template"]
            if target_node.prompt_template:
                target_node.source_code = ""
        if "source_code" in updates:
            target_node.source_code = updates["source_code"]
            if target_node.source_code:
                target_node.prompt_template = ""
        if "input_keys" in updates:
            keys, err = _coerce_node_keys(
                updates["input_keys"], "input_keys",
            )
            if err:
                return json.dumps({"status": "rejected", "error": err})
            target_node.input_keys = keys
        if "output_keys" in updates:
            keys, err = _coerce_node_keys(
                updates["output_keys"], "output_keys",
            )
            if err:
                return json.dumps({"status": "rejected", "error": err})
            target_node.output_keys = keys
        # BUG-045: thread the three spec fields onto target_node. Mutual
        # exclusivity vs prompt_template / source_code is enforced by
        # BranchDefinition.validate() at compile time; we accept what
        # the caller asked for and let validate() catch invalid combos.
        for spec_field in (
            "invoke_branch_spec",
            "invoke_branch_version_spec",
            "await_run_spec",
        ):
            if spec_field in updates:
                val = updates[spec_field]
                setattr(
                    target_node,
                    spec_field,
                    val if isinstance(val, dict) else None,
                )
    except Exception as exc:
        return json.dumps({
            "status": "rejected",
            "error": f"Failed to apply update: {exc}",
        })

    # Snapshot the previous node body BEFORE we mutate further, so the
    # audit row captures rollback-capable state.
    before_branch = BranchDefinition.from_dict(source)
    before_node = next(
        (n for n in before_branch.node_defs if n.node_id == nid), None,
    )
    node_before_body = before_node.to_dict() if before_node else {}

    # Bump version so Phase 4 lineage can distinguish pre/post-edit runs.
    old_version = int(source.get("version") or 1)
    new_version = old_version + 1
    staging_dict = staging.to_dict()
    staging_dict["version"] = new_version
    saved = save_branch_definition(_base_path(), branch_def=staging_dict)

    # Re-hydrate to produce a clean NodeDefinition dict for the response.
    persisted = BranchDefinition.from_dict(saved)
    updated_node = next(
        (n for n in persisted.node_defs if n.node_id == nid), target_node,
    )

    # #50: emit a node_edit_audit row capturing full pre/post node
    # bodies so `rollback_node` can restore the exact prior state.
    # ``triggered_by_judgment_id`` is optional — callers applying a
    # judgment-driven edit can pass it.
    try:
        from workflow.runs import record_node_edit_audit

        triggered = (
            kwargs.get("triggered_by_judgment_id") or ""
        ).strip() or None
        record_node_edit_audit(
            _base_path(),
            branch_def_id=bid,
            version_before=old_version,
            version_after=new_version,
            nodes_changed=[nid],
            triggered_by_judgment_id=triggered,
            node_before=node_before_body,
            node_after=updated_node.to_dict() if updated_node else {},
            edit_kind="update",
        )
    except Exception:
        logger.exception("node_edit_audit failed for %s/%s", bid, nid)

    changed_fields = sorted(updates.keys())
    branch_label = persisted.name or "unnamed"
    text_lines = [
        f"**Updated node `{nid}`** on workflow '{branch_label}' "
        f"(version {old_version} → {new_version}). "
        f"Fields changed: {', '.join(changed_fields) or '(none)'}.",
    ]
    # Summarize the node briefly so Claude.ai sees the new shape.
    body_kind = "prompt_template" if updated_node.prompt_template else (
        "source_code" if updated_node.source_code else "passthrough"
    )
    text_lines += [
        "",
        f"- display_name: {updated_node.display_name}",
        f"- phase: {updated_node.phase}",
        f"- body: {body_kind}",
    ]
    if body_kind == "prompt_template":
        preview = updated_node.prompt_template
        if len(preview) > 240:
            preview = preview[:240].rstrip() + "…"
        text_lines += ["", f"Template preview:\n\n```\n{preview}\n```"]

    return json.dumps({
        "text": "\n".join(text_lines),
        "status": "updated",
        "branch_def_id": bid,
        "node_id": nid,
        "version_before": old_version,
        "version_after": new_version,
        "changed_fields": changed_fields,
        "node": updated_node.to_dict(),
    }, default=str)


def _ext_branch_search_nodes(kwargs: dict[str, Any]) -> str:
    """Search NodeDefinitions across every Branch for reuse candidates.

    #62 Part B. The bot's reuse-vs-invent decision depends on being
    able to ask "what nodes already exist that might fit the role I
    need?". This action returns phone-card-sized hits ranked by
    substring match + reuse_count across Branches.

    Combined with #66's ``node_ref`` primitive, the flow is:
    search_nodes → pick a hit → build_branch / add_node with
    ``node_ref={source, node_id}``.
    """
    from workflow.daemon_server import search_nodes

    query = (kwargs.get("query") or "").strip()
    role = (kwargs.get("role") or kwargs.get("phase") or "").strip()
    limit = int(kwargs.get("limit", 20) or 20)

    entries = search_nodes(
        _base_path(),
        query=query,
        role=role,
        limit=limit,
    )

    header = "**Reusable nodes**"
    if query:
        header += f" matching '{query}'"
    if role:
        header += f" (phase={role})"
    lines = [header, ""]
    if entries:
        for e in entries[:12]:
            reuse_tag = (
                f" · used by {e['reuse_count']} branch"
                f"{'es' if e['reuse_count'] != 1 else ''}"
            )
            phase_tag = f" · phase={e['phase']}" if e.get("phase") else ""
            lines.append(
                f"- `{e['node_id']}` · **{e['display_name']}**"
                f"{phase_tag}{reuse_tag}"
            )
            desc = (e.get("description") or "").strip()
            if desc:
                lines.append(f"  {desc[:120]}")
            preview = (e.get("prompt_template_preview") or "").strip()
            if preview:
                lines.append(f"  _prompt:_ `{preview}`")
        if len(entries) > 12:
            lines.append(f"- … and {len(entries) - 12} more.")
        lines.append("")
        lines.append(
            "_To reuse: call `add_node` with "
            "`node_ref_json={\"source\": \"<branch_def_id>\", "
            "\"node_id\": \"<node_id>\"}`, or include the same "
            "`node_ref` inside a `spec_json` / `changes_json` node "
            "entry on build_branch / patch_branch. See #66._"
        )
    else:
        if query or role:
            lines.append(
                "_No existing nodes match. If you invent one, "
                "consider a node_id future callers would search for "
                "(e.g. `citation_audit` rather than `node_7`)._"
            )
        else:
            lines.append(
                "_No nodes registered yet. Build one with "
                "`extensions action=build_branch` and future callers "
                "will find it here._"
            )

    return json.dumps({
        "text": "\n".join(lines),
        "query": query,
        "role": role,
        "count": len(entries),
        "entries": entries,
    }, default=str)


# #64: whitelisted fields for bulk `patch_nodes`. Type coercion per
# field so phone-entered strings land as the right Python type.
_PATCH_NODES_FIELDS: dict[str, Any] = {
    "display_name": str,
    "description": str,
    "phase": str,
    "prompt_template": str,
    "source_code": str,
    "model_hint": str,
    "timeout_seconds": float,
    "enabled": bool,
}


def _coerce_patch_nodes_value(
    field: str, raw: Any,
) -> tuple[Any, str | None]:
    """Coerce a bulk-patch value into the right Python type.

    Returns ``(coerced, error)``. ``error`` non-None → reject without
    mutating any node; atomic.
    """
    kind = _PATCH_NODES_FIELDS[field]
    if kind is bool:
        if isinstance(raw, bool):
            return raw, None
        s = str(raw).strip().lower()
        if s in {"true", "1", "yes", "on"}:
            return True, None
        if s in {"false", "0", "no", "off"}:
            return False, None
        return None, f"Cannot coerce {raw!r} to bool."
    if kind is float:
        try:
            return float(raw), None
        except (TypeError, ValueError):
            return None, f"Cannot coerce {raw!r} to float."
    return str(raw), None


def _ext_branch_patch_nodes(kwargs: dict[str, Any]) -> str:
    """Bulk-set one field across N nodes in one call (#64).

    Different from ``patch_branch`` (heterogeneous batches of ops).
    ``patch_nodes`` is homogeneous: same field, same value, filtered by
    ``node_ids`` (default: all nodes on the branch). Atomic — if any
    node rejects, nothing is written.
    """
    from workflow.api.extensions import VALID_PHASES
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import (
        get_branch_definition,
        save_branch_definition,
    )

    bid = (kwargs.get("branch_def_id") or "").strip()
    if not bid:
        return json.dumps({
            "status": "rejected",
            "error": "branch_def_id is required for patch_nodes.",
        })
    field = (kwargs.get("field") or "").strip()
    if field not in _PATCH_NODES_FIELDS:
        return json.dumps({
            "status": "rejected",
            "error": (
                f"Unknown field '{field}'. patch_nodes supports: "
                f"{', '.join(sorted(_PATCH_NODES_FIELDS))}"
            ),
        })
    raw_value = kwargs.get("value")
    if raw_value is None or raw_value == "":
        return json.dumps({
            "status": "rejected",
            "error": "value is required.",
        })

    value, err = _coerce_patch_nodes_value(field, raw_value)
    if err is not None:
        return json.dumps({
            "status": "rejected",
            "error": f"Field '{field}': {err}",
        })

    if field == "phase" and value not in VALID_PHASES:
        return json.dumps({
            "status": "rejected",
            "error": (
                f"Invalid phase '{value}'. Must be one of: "
                f"{', '.join(sorted(VALID_PHASES))}"
            ),
        })

    _ensure_workflow_db()
    try:
        source = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({
            "status": "rejected",
            "error": f"Branch '{bid}' not found.",
        })

    staging = BranchDefinition.from_dict(source)

    # Resolve target node set. Empty `node_ids` means "every node".
    target_ids_raw = kwargs.get("node_ids") or ""
    if isinstance(target_ids_raw, list):
        target_ids = [
            str(n).strip() for n in target_ids_raw if str(n).strip()
        ]
    else:
        target_ids = _split_csv(target_ids_raw)
    all_node_ids = [n.node_id for n in staging.node_defs]
    if not target_ids:
        target_ids = all_node_ids

    unknown = [nid for nid in target_ids if nid not in all_node_ids]
    if unknown:
        return json.dumps({
            "status": "rejected",
            "error": (
                f"Unknown node_ids on branch '{staging.name}': "
                f"{', '.join(unknown)}. Atomic — no node was patched."
            ),
        })

    if not target_ids:
        return json.dumps({
            "status": "rejected",
            "error": "Branch has no nodes to patch.",
        })

    # Apply the field. prompt_template / source_code are mutually
    # exclusive — clear the other when setting one.
    for node in staging.node_defs:
        if node.node_id not in target_ids:
            continue
        setattr(node, field, value)
        if field == "prompt_template" and value:
            node.source_code = ""
        elif field == "source_code" and value:
            node.prompt_template = ""

    old_version = int(source.get("version") or 1)
    new_version = old_version + 1
    staging_dict = staging.to_dict()
    staging_dict["version"] = new_version
    saved = save_branch_definition(_base_path(), branch_def=staging_dict)
    persisted = BranchDefinition.from_dict(saved)

    branch_label = persisted.name or "(unnamed workflow)"
    text = (
        f"**Updated `{field}` on {len(target_ids)} node(s)** of "
        f"workflow '{branch_label}'. New value: `{value}`. "
        f"(version {old_version} → {new_version})"
    )
    per_node = [
        {"node_id": nid, "status": "updated"} for nid in target_ids
    ]
    return json.dumps({
        "text": text,
        "status": "patched",
        "field": field,
        "value": value,
        "patched_count": len(target_ids),
        "version_before": old_version,
        "version_after": new_version,
        "node_results": per_node,
    }, default=str)


# ───────────────────────────────────────────────────────────────────────────
# Branch lineage helpers
# ───────────────────────────────────────────────────────────────────────────


def _resolve_udir() -> Path:
    """Return the active universe directory (best-effort; never raises)."""
    try:
        uid = os.environ.get("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "")
        if not uid:
            base = _base_path()
            if base.is_dir():
                subdirs = [d for d in base.iterdir() if d.is_dir()]
                if subdirs:
                    uid = subdirs[0].name
        if uid:
            return _universe_dir(uid)
    except Exception:  # noqa: BLE001
        pass
    return _base_path()


def _action_fork_tree(kwargs: dict[str, Any]) -> str:
    from workflow.branch_versions import get_branch_version, list_branch_versions
    from workflow.daemon_server import get_branch_definition, list_branch_definitions

    bid = (kwargs.get("branch_def_id") or "").strip()
    if not bid:
        return json.dumps({"error": "branch_def_id is required."})

    try:
        root = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({"error": f"branch_def_id '{bid}' not found."})

    # Walk ancestor chain via fork_from (branch_version_id → branch_def_id).
    ancestors: list[dict[str, Any]] = []
    seen_bids: set[str] = {bid}
    current_bvid = root.get("fork_from")
    while current_bvid:
        bv = get_branch_version(_base_path(), current_bvid)
        if bv is None:
            break
        anc_bid = bv.branch_def_id
        if anc_bid in seen_bids:
            break  # cycle guard
        seen_bids.add(anc_bid)
        try:
            anc = get_branch_definition(_base_path(), branch_def_id=anc_bid)
        except KeyError:
            break
        ancestors.append({
            "branch_def_id": anc_bid,
            "name": anc.get("name", ""),
            "author": anc.get("author", ""),
            "fork_from_version": current_bvid,
        })
        current_bvid = anc.get("fork_from")

    # Find descendants: branches whose fork_from matches any version of this branch.
    versions = list_branch_versions(_base_path(), bid, limit=200)
    version_ids = {v.branch_version_id for v in versions}
    descendants: list[dict[str, Any]] = []
    all_branches = list_branch_definitions(_base_path(), include_private=False)
    for b in all_branches:
        ff = b.get("fork_from")
        if ff and ff in version_ids:
            descendants.append({
                "branch_def_id": b["branch_def_id"],
                "name": b.get("name", ""),
                "author": b.get("author", ""),
                "fork_from_version": ff,
                "published_versions_count": len(
                    list_branch_versions(_base_path(), b["branch_def_id"], limit=500)
                ),
            })

    return json.dumps({
        "branch_def_id": bid,
        "name": root.get("name", ""),
        "fork_from": root.get("fork_from"),
        "ancestors": ancestors,
        "descendant_count": len(descendants),
        "descendants": descendants[:50],
    }, default=str)


_BRANCH_ACTIONS: dict[str, Any] = {
    "create_branch": _ext_branch_create,
    "get_branch": _ext_branch_get,
    "list_branches": _ext_branch_list,
    "delete_branch": _ext_branch_delete,
    "add_node": _ext_branch_add_node,
    "connect_nodes": _ext_branch_connect_nodes,
    "set_entry_point": _ext_branch_set_entry_point,
    "add_state_field": _ext_branch_add_state_field,
    "validate_branch": _ext_branch_validate,
    "describe_branch": _ext_branch_describe,
    "build_branch": _ext_branch_build,
    "patch_branch": _ext_branch_patch,
    "patch_nodes": _ext_branch_patch_nodes,
    "update_node": _ext_branch_update_node,
    "search_nodes": _ext_branch_search_nodes,
    "fork_tree": _action_fork_tree,
}

_BRANCH_WRITE_ACTIONS: frozenset[str] = frozenset({
    "create_branch", "add_node", "connect_nodes",
    "set_entry_point", "add_state_field", "delete_branch",
    "build_branch", "patch_branch", "patch_nodes", "update_node",
})


# ───────────────────────────────────────────────────────────────────────────
# Branch Design Guide — chatbot-facing prompt body
# ───────────────────────────────────────────────────────────────────────────
# The @mcp.prompt("Branch Design Guide") decoration stays in
# ``workflow/universe_server.py`` (Pattern A2) so FastMCP introspection sees
# the chatbot-facing signature exactly as before. The wrapper there delegates
# to ``_branch_design_guide_prompt()`` below.


def _branch_design_guide_prompt() -> str:
    """Return the Branch Design Guide markdown body.

    Wraps the module-level ``_BRANCH_DESIGN_GUIDE`` constant so the
    universe_server-side ``@mcp.prompt`` wrapper has a single delegation
    target. Plain function (no decoration) — the FastMCP registration
    lives in ``workflow.universe_server.branch_design_guide``.
    """
    return _BRANCH_DESIGN_GUIDE


_BRANCH_DESIGN_GUIDE = """\
You help users author community-designed graph branches through the
`extensions` tool. A branch is a LangGraph topology (nodes + edges +
state schema) the user can fork, share, and (in Phase 3) run.

## Before you invent — search for reusable nodes

Before you design any node for the user's new Branch, check whether an
existing node already fills the role. Every node already on the server
was written once and validated; reusing it preserves lineage and lets
comparative evaluation (judge_run, compare_runs) work across branches.

```
extensions action=search_nodes node_query="citation audit"
extensions action=search_nodes node_query="outline" phase="plan"
goals action=common_nodes scope=all min_branches=2
```

For each relevant hit, point the user at it and ask whether to reuse.
If yes, include a `node_ref` inside the `node_defs` entry rather than
restating source_code / prompt_template:

```
{"node_id": "citation_audit",
 "node_ref": {"source": "<branch_def_id_from_search>",
              "node_id": "citation_audit"}}
```

Copy semantics are the default and usually what the user wants — the
canonical body is snapshotted into the new Branch and diverges from
there. If the user later edits it on either side, the other stays
unchanged. (v1; live shared nodes may come later.)

Bare `node_id` that collides with an existing standalone registered
node is REJECTED by the server; you must pass `node_ref` or
`intent="copy"` or rename. This is intentional — silent shadowing was
a bug (#66).

## Author flow (PREFERRED — one round trip)

Use `build_branch` with the whole workflow in a single `spec_json`.
You get back a validated branch with a mermaid diagram in one call —
no per-node chatter, no tool-call budget burn:
This is the chat-native authoring path for small workflow units. Do NOT
send community users to GitHub Actions YAML, repo files, or CI config
when they ask to make or revise a workflow from chat; use `build_branch`
for new units and `patch_branch` for edits.

```
extensions action=build_branch spec_json='{
  "name": "Recipe tracker",
  "description": "Capture, categorize, archive recipes",
  "entry_point": "capture",
  "skills": [
    {
      "name": "Kitchen-note style",
      "body": "Keep notes terse, ingredient-focused, and reversible.",
      "source_url": "https://example.com/skill.md",
      "source_note": "User asked to copy this from a public post."
    }
  ],
  "node_defs": [
    {"node_id": "capture", "display_name": "Capture raw recipe",
     "prompt_template": "Read the user's message and extract recipe name."},
    {"node_id": "categorize", "display_name": "Categorize recipe",
     "prompt_template": "Classify by cuisine and meal type."},
    {"node_id": "archive", "display_name": "Archive to library",
     "prompt_template": "Format as a wiki entry and file it."}
  ],
  "edges": [
    {"from": "START", "to": "capture"},
    {"from": "capture", "to": "categorize"},
    {"from": "categorize", "to": "archive"},
    {"from": "archive", "to": "END"}
  ],
  "state_schema": [
    {"name": "raw_recipe", "type": "str"},
    {"name": "category", "type": "str"},
    {"name": "archived", "type": "bool", "default": false}
  ]
}'
```

If validation fails, `build_branch` returns concrete `suggestions` with
proposed fixes — apply them and retry. No partial branch is ever visible.

## Branch skills

When the user wants to create a skill, remix one, or copy one they found
elsewhere, attach it to the Branch as a `skills` snapshot. A skill is
Branch context, not executable code. It must include `name` and `body`;
include `source_url`, `source_note`, `parent_skill_id`, `license`,
`version`, `tags`, or `metadata` when the user gives that provenance.
Do not write skill text to the wiki as a workaround when the user wants
the Branch to carry it.

## Editing an existing workflow (PREFERRED)

Use `patch_branch` with a batch of ops. Transactional — all land or none:

```
extensions action=patch_branch branch_def_id=... changes_json='[
  {"op": "add_node", "node_id": "novelty_check",
   "display_name": "Novelty assessor",
   "prompt_template": "Rate novelty of: {claim}"},
  {"op": "add_edge", "from": "categorize", "to": "novelty_check"},
  {"op": "add_edge", "from": "novelty_check", "to": "archive"},
  {"op": "remove_edge", "from": "categorize", "to": "archive"},
  {"op": "add_state_field", "name": "novelty_score", "type": "float"},
  {"op": "add_skill",
   "skill": {"name": "Review checklist",
             "body": "Check tests, code shape, and live proof."}}
]'
```

## Atomic actions (single-item surgery only)

Use these ONLY when the user wants exactly one small change and the
per-turn tool-call budget is not at risk:

- `create_branch name="..." description="..."`
- `add_node branch_def_id=... node_id=... display_name=... prompt_template=...`
- `connect_nodes branch_def_id=... from_node=... to_node=...`
- `set_entry_point branch_def_id=... node_id=...`
- `add_state_field branch_def_id=... field_name=... field_type=...`
- `validate_branch branch_def_id=...`
- `describe_branch branch_def_id=...`

## Hard rule

After `describe_branch`, check `runnable` before telling the user their
branch is ready to run. If `runnable=false`, surface
`unapproved_source_code_nodes` or validation errors and stop. If
`runnable=true`, use `run_branch` with a JSON `inputs_json` that fills the
state_schema fields. The runner returns a `run_id`, final status, and
per-node trace.

## Power users

Pass `source_code="def run(state): ..."` instead of `prompt_template`
for code nodes. Pass `reducer="append"` on `add_state_field` for
accumulating list fields. The same 10 actions cover both audiences;
the difference is how much you abstract on the user's behalf.

## Running a branch

Once validated, execute with:

- `run_branch branch_def_id=... inputs_json='{"raw_recipe": "pasta"}'`
- `wait_for_run run_id=... since_step=-1 max_wait_s=60` to wait for progress
  without burning repeated tool calls.
- `get_run run_id=...` for a full snapshot with mermaid + per-node status.
- `stream_run run_id=... since_step=-1` only for low-level incremental reads.
- `get_run_output run_id=... field_name=archived` to pull one field.
- `cancel_run run_id=...` to request cooperative stop.

The never-simulate rule lives in `control_station` (hard rule 5):
if run_branch fails, the branch isn't validated, or a source_code node
isn't approved, state the reason and stop.
"""
