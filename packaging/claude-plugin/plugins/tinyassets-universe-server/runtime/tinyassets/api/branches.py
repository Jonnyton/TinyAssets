"""Branch authoring + node CRUD subsystem — extracted from
``tinyassets/universe_server.py`` (Task #15 — decomp Step 8).

The largest single submodule extracted from the monolith: 18 ``_ext_branch_*``
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
``tinyassets/universe_server.py`` (Pattern A2) so FastMCP introspection
sees the chatbot-facing signature exactly as before. The
``branch_design_guide()`` wrapper there delegates to
``_branch_design_guide_prompt()`` from this module.

Public surface (back-compat re-exported via ``tinyassets.universe_server``):
    _BRANCH_ACTIONS                : dispatch table (18 handlers)
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
``_load_nodes``, ``VALID_PHASES``, ``logger`` all live in ``tinyassets.universe_server``
(universe-engine territory) and are lazy-imported inside the functions that use
them. This avoids the load-time cycle (universe_server back-compat-imports
symbols from this module). ``_gates_enabled`` is also lazy-imported, but from
``tinyassets.api.market`` (its real home post-Step-7).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tinyassets.api.helpers import (
    _base_path,
    _find_all_pages,
    _read_text,
    _universe_dir,
    _wiki_drafts_dir,
    _wiki_pages_dir,
)
from tinyassets.api.wiki import (
    _page_rel_path,
    _parse_frontmatter,
)
from tinyassets.catalog import CommitFailedError, DirtyFileError

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────────────────────────────────
# Community Branches: author/edit BranchDefinition over MCP
# ───────────────────────────────────────────────────────────────────────────
# Branches are domain-agnostic graph topologies that live in the same SQLite
# backing store as the rest of the multiplayer substrate (base_path /
# .tinyassets.db, table branch_definitions). Each write action appends to
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
    from tinyassets.api.engine_helpers import _append_ledger

    _append_ledger(
        _base_path(), action,
        target=target, summary=summary, payload=payload,
    )


def _source_code_hash(source_code: str) -> str:
    return hashlib.sha256(source_code.encode("utf-8")).hexdigest()


def _clear_source_code_approval(node: Any) -> None:
    node.approved = False
    node.approved_by = ""
    node.approved_at = ""
    node.approved_source_hash = ""
    node.approval_reason = ""


def _approval_provenance_valid(
    approved: Any, source_code: str, approved_source_hash: str,
) -> bool:
    """True only when an ``approved`` flag is backed by hash provenance.

    A source_code node is genuinely approved iff the recorded
    ``approved_source_hash`` equals the hash of the *current* source_code.
    A bare ``approved=True`` with no/stale hash is forged or stale and must
    not authorize execution. Prompt-template (non-source) nodes carry no
    executable surface to gate, so an empty source_code is treated as
    matching an empty hash only when no hash was recorded.
    """
    if not approved:
        return False
    if not source_code:
        # No executable content to gate. Approval is meaningless here but
        # also harmless — the compiler only gates source_code nodes.
        return True
    return bool(approved_source_hash) and (
        approved_source_hash == _source_code_hash(source_code)
    )


def _reconcile_copied_approval(merged: dict[str, Any]) -> None:
    """Strip approval metadata from a copied/merged node body unless the
    effective source hash still matches the recorded approved hash.

    Used by the ``node_ref`` copy path: a caller can inherit an approved
    body and then override ``source_code``/other executable content. The
    inherited ``approved=True`` must not survive a content change the
    approver never reviewed. See Codex ADAPT review on PR #1349.
    """
    if not _approval_provenance_valid(
        merged.get("approved"),
        merged.get("source_code") or "",
        merged.get("approved_source_hash") or "",
    ):
        merged["approved"] = False
        merged["approved_by"] = ""
        merged["approved_at"] = ""
        merged["approved_source_hash"] = ""
        merged["approval_reason"] = ""


def _node_source_code_unrunnable(nd: dict[str, Any]) -> bool:
    """True when a node dict has executable source_code but is NOT genuinely
    approved (provenance-checked), so the fail-closed runtime gate would refuse
    it. Used by the describe/validate/get_branch runnability surfaces so what
    they report matches what ``_validate_source_code`` will actually accept: a
    bare ``approved=True`` with a missing/stale ``approved_source_hash`` is
    reported as unrunnable, not runnable. PR #1349.
    """
    if not nd.get("source_code"):
        return False
    return not _approval_provenance_valid(
        nd.get("approved", False),
        nd.get("source_code") or "",
        nd.get("approved_source_hash") or "",
    )


def _reconcile_node_approval(node: Any) -> Any:
    """Object-level twin of :func:`_reconcile_copied_approval`.

    Re-validates a carried/restored ``NodeDefinition`` object's approval
    against its current source hash and clears the approval metadata when the
    provenance does not match. Used by paths that carry node bodies forward as
    NodeDefinition objects rather than dicts: ``build_branch`` fork-copy
    (inherits the parent's ``node_defs`` wholesale) and ``rollback_node``
    (restores a raw audit body). A trusted/legacy snapshot carrying
    ``source_code`` + ``approved=True`` + empty/stale ``approved_source_hash``
    must not survive the copy as still-approved. Closes the Codex final
    residual on PR #1349 (carried-snapshot bypass).

    Returns the node for chaining.
    """
    if not _approval_provenance_valid(
        getattr(node, "approved", False),
        getattr(node, "source_code", "") or "",
        getattr(node, "approved_source_hash", "") or "",
    ):
        _clear_source_code_approval(node)
    return node


def _ensure_workflow_db() -> None:
    """Ensure the shared SQLite schema exists before any branch action runs.

    Branch handlers read/write ``base_path/.tinyassets.db``. Calling this
    lazily keeps tests and first-use paths from needing a separate init step.
    """
    from tinyassets.daemon_server import initialize_author_server

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
    from tinyassets.api.engine_helpers import _format_dirty_file_conflict, _truncate

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
    from tinyassets.api.engine_helpers import (
        _current_actor,
        _format_commit_failed,
        _storage_backend,
    )
    from tinyassets.branches import BranchDefinition
    from tinyassets.identity import git_author

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
    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.daemon_server import get_branch_definition, list_branch_definitions

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
    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.api.market import _gates_enabled
    from tinyassets.daemon_server import get_branch_definition, list_gate_claims

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
        if _node_source_code_unrunnable(nd)
    ]
    branch["unapproved_source_code_nodes"] = unapproved_sc
    branch["runnable"] = not unapproved_sc
    return json.dumps(branch, default=str)


def _ext_branch_approve_source_code(kwargs: dict[str, Any]) -> str:
    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import (
        get_branch_definition,
        save_branch_definition,
    )

    bid = _resolve_branch_id(
        (kwargs.get("branch_def_id") or "").strip(), str(_base_path()),
    )
    nid = (kwargs.get("node_id") or "").strip()
    if not bid or not nid:
        return json.dumps({
            "status": "rejected",
            "error": "branch_def_id and node_id are required.",
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
    if not target_node.source_code:
        return json.dumps({
            "status": "rejected",
            "error": f"Node '{nid}' has no source_code to approve.",
        })

    actor = _current_actor()
    source_hash = _source_code_hash(target_node.source_code)
    target_node.approved = True
    target_node.approved_by = actor
    target_node.approved_at = datetime.now(timezone.utc).isoformat()
    target_node.approved_source_hash = source_hash
    target_node.approval_reason = (kwargs.get("reason") or "").strip()

    saved = save_branch_definition(_base_path(), branch_def=staging.to_dict())
    persisted = BranchDefinition.from_dict(saved)
    approved_node = next(
        (n for n in persisted.node_defs if n.node_id == nid), target_node,
    )
    warning = (
        "approval recorded with anonymous actor; configure authenticated "
        "host identity before relying on this for shared-host policy"
        if actor == "anonymous" else ""
    )
    return json.dumps({
        "status": "approved",
        "branch_def_id": bid,
        "node_id": nid,
        "approved": approved_node.approved,
        "approved_by": approved_node.approved_by,
        "approved_at": approved_node.approved_at,
        "approved_source_hash": approved_node.approved_source_hash,
        "approval_reason": approved_node.approval_reason,
        "approval_warning": warning,
    }, default=str)


_VALID_BRANCH_LIST_SCOPES = {"published", "all", "mine"}


def _ext_branch_list(kwargs: dict[str, Any]) -> str:
    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.daemon_server import list_branch_definitions

    scope = (kwargs.get("scope") or "published").strip().lower()
    if scope not in _VALID_BRANCH_LIST_SCOPES:
        return json.dumps({
            "error": (
                f"unknown scope '{scope}'. "
                f"Valid scopes: {sorted(_VALID_BRANCH_LIST_SCOPES)}."
            ),
        })

    actor = _current_actor()

    # Phase 6.2.2 — visibility-aware listing. Viewer sees public
    # Branches and any private Branches they authored.
    rows = list_branch_definitions(
        _base_path(),
        domain_id=kwargs.get("domain_id", ""),
        author=kwargs.get("author", ""),
        goal_id=kwargs.get("goal_id", ""),
        viewer=actor,
    )

    # requires_sandbox filter: "none" = design-only branches only (no node
    # has requires_sandbox=True); "any" = branches that have at least one
    # sandbox-requiring node. Omit / empty = no filter.
    rs_filter = (kwargs.get("requires_sandbox") or "").strip().lower()

    summaries = []
    for r in rows:
        published_version_id = None
        if scope == "published":
            # Newest ACTIVE version only — a rolled-back version must not stay
            # discoverable (Codex S2 latest-model, finding 3).
            active = _newest_active_branch_version(
                _base_path(), r.get("branch_def_id", ""),
            )
            if active is None:
                continue
            published_version_id = active.branch_version_id
        elif scope == "mine":
            if (r.get("author") or "") != actor:
                continue
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
        summary = {
            "branch_def_id": r.get("branch_def_id"),
            "name": r.get("name"),
            "author": r.get("author"),
            "domain_id": r.get("domain_id"),
            "goal_id": r.get("goal_id"),
            "node_count": node_count,
            "skill_count": len(r.get("skills", []) or []),
            "published": True if scope == "published" else r.get("published", False),
            "visibility": r.get("visibility", "public"),
            "has_sandbox_nodes": has_sandbox_nodes,
        }
        if published_version_id is not None:
            summary["branch_version_id"] = published_version_id
        summaries.append(summary)
    return json.dumps({"branches": summaries, "count": len(summaries)})


def _ext_branch_delete(kwargs: dict[str, Any]) -> str:
    from tinyassets.daemon_server import delete_branch_definition

    bid = kwargs.get("branch_def_id", "").strip()
    if not bid:
        return json.dumps({"error": "branch_def_id is required."})
    removed = delete_branch_definition(_base_path(), branch_def_id=bid)
    if not removed:
        return json.dumps({"error": f"Branch '{bid}' not found."})
    return json.dumps({"branch_def_id": bid, "status": "deleted"})


def _ext_branch_add_node(kwargs: dict[str, Any]) -> str:
    from tinyassets.api.engine_helpers import (
        _current_actor,
        _format_commit_failed,
        _storage_backend,
    )
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition
    from tinyassets.identity import git_author

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
    from tinyassets.api.engine_helpers import (
        _current_actor,
        _format_commit_failed,
        _storage_backend,
    )
    from tinyassets.branches import BranchDefinition, EdgeDefinition
    from tinyassets.daemon_server import get_branch_definition
    from tinyassets.identity import git_author

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
    from tinyassets.api.engine_helpers import (
        _current_actor,
        _format_commit_failed,
        _storage_backend,
    )
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition
    from tinyassets.identity import git_author

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
    from tinyassets.api.engine_helpers import (
        _current_actor,
        _format_commit_failed,
        _storage_backend,
    )
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition
    from tinyassets.identity import git_author

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
    # BUG-094: also accept canonical ``default_value`` (StateFieldDecl) and
    # write both keys so PR #932's ``_state_schema_defaults`` seeding finds it.
    default = kwargs.get(
        "default_value", kwargs.get("field_default", ""),
    )
    if default != "":
        field_entry["default_value"] = default
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
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition

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
        if _node_source_code_unrunnable(nd)
    ]

    # sandbox-compat warning: list any requires_sandbox=True nodes when
    # the host's bwrap probe says sandbox is unavailable. Non-fatal.
    sandbox_warnings: list[str] = []
    try:
        from tinyassets.providers.base import get_sandbox_status
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
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition

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
        if _node_source_code_unrunnable(nd)
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
    from tinyassets.branch_versions import list_branch_versions
    from tinyassets.daemon_server import list_branch_definitions

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


def _branch_authoring_batch_receipt(
    branch: Any,
    *,
    action: str,
    operation_count: int,
    request_id: str = "",
) -> dict[str, Any]:
    """Return structured evidence for one composite Branch authoring call."""
    from tinyassets.api.engine_helpers import _current_actor

    node_defs = list(getattr(branch, "node_defs", []) or [])
    source_code_node_count = 0
    approved_source_code_node_count = 0
    unapproved_nodes: list[dict[str, str]] = []
    for node in node_defs:
        if not getattr(node, "source_code", ""):
            continue
        source_code_node_count += 1
        # PR #1349 fail-closed: count as approved only when the approval is
        # backed by matching hash provenance, mirroring the runtime gate.
        if _approval_provenance_valid(
            getattr(node, "approved", False),
            getattr(node, "source_code", "") or "",
            getattr(node, "approved_source_hash", "") or "",
        ):
            approved_source_code_node_count += 1
        else:
            unapproved_nodes.append({
                "node_id": getattr(node, "node_id", ""),
                "display_name": getattr(node, "display_name", ""),
            })

    receipt: dict[str, Any] = {
        "receipt_type": "branch_authoring_batch",
        "action": action,
        "actor": _current_actor(),
        "branch_def_id": getattr(branch, "branch_def_id", ""),
        "branch_name": getattr(branch, "name", ""),
        "operation_count": operation_count,
        "node_count": len(node_defs),
        "edge_count": len(getattr(branch, "edges", []) or []),
        "skill_count": len(getattr(branch, "skills", []) or []),
        "state_field_count": len(getattr(branch, "state_schema", []) or []),
        "validation": {
            "status": "ok",
            "valid": True,
            "error_count": 0,
        },
        "source_code_approval": {
            "source_code_node_count": source_code_node_count,
            "approved_count": approved_source_code_node_count,
            "unapproved_count": len(unapproved_nodes),
            "unapproved_nodes": unapproved_nodes,
            "runnable": len(unapproved_nodes) == 0,
        },
        "authorization_effect": {
            "grants_authorization": False,
            "grants_scoped_trust_session": False,
            "bypasses_client_approval_prompts": False,
            "approved_action_scope": [],
            "revocation_handle": None,
            "note": (
                "Evidence-only receipt: clients may display or audit it, but must "
                "not treat it as permission to execute future writes."
            ),
        },
        "caveats": [
            "This receipt records what landed; it is not an authorization grant.",
            (
                "It does not bypass source_code approval, host-owned gates, "
                "or client approval prompts."
            ),
        ],
    }

    normalized_request_id = str(request_id or "").strip()
    if normalized_request_id:
        receipt["plan_context"] = {
            "request_id": normalized_request_id,
            "authoritative": False,
            "note": (
                "Caller-supplied context for correlating this batch; "
                "not an approval token."
            ),
        }
    return receipt


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
    from tinyassets.api.extensions import _load_nodes

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
            "output_keys", "strict_input_isolation", "source_code",
            "prompt_template", "tools_allowed", "timeout_seconds", "author",
        ):
            if field_key in raw and raw[field_key] not in (None, ""):
                merged[field_key] = raw[field_key]
        # SECURITY (Codex ADAPT, PR #1349): approval provenance must follow
        # the *executable content*, never the inherited boolean. A caller can
        # node_ref an approved node and then override ``source_code`` — that
        # forges/staleifies approval for code the approver never saw. Approval
        # only survives when the effective source hash still matches the
        # approved hash; otherwise strip every approval field so this copy is
        # treated as unapproved and re-runs the approve gate.
        _reconcile_copied_approval(merged)
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
    from tinyassets.api.extensions import _load_nodes

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
            "tools_allowed": list(hit.get("tools_allowed") or []),
            "strict_input_isolation": bool(
                hit.get("strict_input_isolation", True),
            ),
            "source_code": hit.get("source_code", ""),
            "prompt_template": hit.get("prompt_template", ""),
            "author": hit.get("author", ""),
            "approved": bool(hit.get("approved", False)),
            "approved_by": hit.get("approved_by", ""),
            "approved_at": hit.get("approved_at", ""),
            "approved_source_hash": hit.get("approved_source_hash", ""),
            "approval_reason": hit.get("approval_reason", ""),
        }, ""

    # Otherwise treat `source` as a branch_def_id.
    from tinyassets.daemon_server import get_branch_definition

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
                "tools_allowed": list(nd.get("tools_allowed") or []),
                "strict_input_isolation": bool(
                    nd.get("strict_input_isolation", True),
                ),
                "source_code": nd.get("source_code", ""),
                "prompt_template": nd.get("prompt_template", ""),
                "author": nd.get("author", ""),
                "approved": bool(nd.get("approved", False)),
                "approved_by": nd.get("approved_by", ""),
                "approved_at": nd.get("approved_at", ""),
                "approved_source_hash": nd.get("approved_source_hash", ""),
                "approval_reason": nd.get("approval_reason", ""),
            }, ""
    return {}, (
        f"node '{node_id}' not found on branch '{source}'. "
        "Use `extensions action=get_branch` to list its nodes."
    )


# Node fields _apply_node_spec sets explicitly via the NodeDefinition(...)
# constructor call below. Approval fields are set there too, guarded by
# _approval_provenance_valid. Every OTHER NodeDefinition field is applied
# generically by _apply_passthrough_node_fields so export -> import round-trips
# losslessly and future node fields survive without editing an allowlist
# (Codex S2 adapt, finding 1).
_NODE_SPEC_CONSTRUCTOR_FIELDS = frozenset({
    "node_id", "display_name", "description", "phase",
    "input_keys", "output_keys", "tools_allowed", "strict_input_isolation",
    "source_code", "prompt_template", "model_hint", "reasoning_effort",
    "llm_policy", "timeout_seconds", "author",
    "invoke_branch_spec", "invoke_branch_version_spec", "await_run_spec",
    "effects",
})
_NODE_SPEC_APPROVAL_FIELDS = frozenset({
    "approved", "approved_by", "approved_at",
    "approved_source_hash", "approval_reason",
})

# Resolved NodeDefinition field types, cached. Passthrough is generic AND
# type-checked (Codex S2 adapt round 2, finding 1): a hostile import that sends
# a string for a bool field ("false"), or a mis-shaped list/dict, is REJECTED
# loudly (hard rule 8) instead of persisting a truthy garbage value. Validation
# is driven off the dataclass's own type hints, so it stays generic — no
# hand-maintained per-field type list.
_NODE_FIELD_HINTS: dict[str, Any] | None = None


def _node_field_hints() -> dict[str, Any]:
    global _NODE_FIELD_HINTS
    if _NODE_FIELD_HINTS is None:
        import typing

        from tinyassets.branches import NodeDefinition

        _NODE_FIELD_HINTS = typing.get_type_hints(NodeDefinition)
    return _NODE_FIELD_HINTS


def _value_matches_node_type(value: Any, hint: Any) -> bool:
    """True when a JSON-decoded ``value`` satisfies the declared field type.

    Bool is checked strictly (a JSON string "false" is NOT a bool); numbers
    reject bools; containers must match list/dict and, for typed lists, their
    element type. Union/Optional accept any member. Unknown/``Any`` accept.
    """
    import types as _types
    import typing

    origin = typing.get_origin(hint)
    if origin is None:
        if hint is bool:
            return isinstance(value, bool)
        if hint is int:
            return isinstance(value, int) and not isinstance(value, bool)
        if hint is float:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if hint is str:
            return isinstance(value, str)
        if hint is type(None):
            return value is None
        if hint is Any:
            return True
        return isinstance(value, hint) if isinstance(hint, type) else True
    if origin in (typing.Union, getattr(_types, "UnionType", ())):
        return any(_value_matches_node_type(value, a) for a in typing.get_args(hint))
    if origin is list:
        if not isinstance(value, list):
            return False
        args = typing.get_args(hint)
        return all(_value_matches_node_type(v, args[0]) for v in value) if args else True
    if origin is dict:
        return isinstance(value, dict)
    if origin in (tuple, set, frozenset):
        return isinstance(value, list)
    return True


def _node_type_label(hint: Any) -> str:
    import types as _types
    import typing

    origin = typing.get_origin(hint)
    if origin is list:
        return "a JSON array"
    if origin is dict:
        return "a JSON object"
    if origin in (typing.Union, getattr(_types, "UnionType", ())):
        parts = [
            _node_type_label(a) for a in typing.get_args(hint)
            if a is not type(None)
        ]
        return " or ".join(parts) if parts else "null"
    return getattr(hint, "__name__", str(hint))


def _apply_passthrough_node_fields(node: Any, raw: dict[str, Any]) -> str:
    """Carry every behavior-affecting NodeDefinition field the explicit
    constructor call did not set — ``requires_sandbox``, ``enabled``,
    ``retry_policy``, ``dependencies``, ``checkpoints``,
    ``evaluation_criteria``, and any FUTURE field such as S3's ``node_kind``.

    Generic by construction: it iterates the dataclass fields, so a new node
    field round-trips through export/import with no allowlist edit. Each value
    is type-checked against the field's declared type BEFORE persistence, and a
    mismatch returns a loud error (nothing is applied). Approval provenance is
    excluded — the constructor path already gated it and a raw passthrough must
    never overwrite that decision.

    Returns "" on success, or a human-readable error string on a type mismatch.
    """
    from tinyassets.branches import NodeDefinition

    hints = _node_field_hints()
    handled = _NODE_SPEC_CONSTRUCTOR_FIELDS | _NODE_SPEC_APPROVAL_FIELDS
    # Two-pass: validate everything first, then apply — so a rejected node is
    # never left half-populated.
    updates: dict[str, Any] = {}
    for fname in NodeDefinition.__dataclass_fields__:
        if fname in handled or fname not in raw:
            continue
        value = raw[fname]
        hint = hints.get(fname)
        if hint is not None and not _value_matches_node_type(value, hint):
            return (
                f"node field '{fname}' has the wrong type: expected "
                f"{_node_type_label(hint)}, got {type(value).__name__} "
                f"({value!r}). Imports/specs must be correctly typed — no "
                "string booleans, no mis-shaped lists/objects."
            )
        updates[fname] = value
    for key, val in updates.items():
        setattr(node, key, val)
    return ""


def _apply_node_spec(branch: Any, raw: dict[str, Any]) -> str:
    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.branches import GraphNodeRef, NodeDefinition

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
    strict_input_isolation = raw.get("strict_input_isolation", True)
    if not isinstance(strict_input_isolation, bool):
        return (
            f"node '{nid}' strict_input_isolation must be a JSON boolean "
            "(true or false)."
        )

    phase = (raw.get("phase") or "").strip() or "custom"
    in_keys, err = _coerce_node_keys(raw.get("input_keys"), "input_keys")
    if err:
        return err
    out_keys, err = _coerce_node_keys(raw.get("output_keys"), "output_keys")
    if err:
        return err
    tools_allowed, err = _coerce_node_keys(
        raw.get("tools_allowed"), "tools_allowed",
    )
    if err:
        return err
    model_hint, err = _coerce_model_hint_update(
        raw.get("model_hint", ""), "model_hint",
    )
    if err:
        return err
    reasoning_effort = str(raw.get("reasoning_effort", "") or "").strip().lower()
    if reasoning_effort and reasoning_effort not in _VALID_REASONING_EFFORTS:
        return (
            f"node '{nid}' reasoning_effort must be empty or one of: "
            f"{', '.join(sorted(_VALID_REASONING_EFFORTS))}"
        )
    llm_policy, err = _coerce_llm_policy_update(
        raw.get("llm_policy"), f"node '{nid}' llm_policy",
    )
    if err:
        return err
    timeout_seconds_raw = raw.get("timeout_seconds", 300.0)
    if timeout_seconds_raw in (None, ""):
        timeout_seconds = 300.0
    else:
        try:
            timeout_seconds = float(timeout_seconds_raw)
        except (TypeError, ValueError):
            return f"node '{nid}' timeout_seconds must be a number."
    # BUG-045: thread the three sub-branch / sibling-run spec fields. The
    # compiler reads them (tinyassets/graph_compiler.py:_build_invoke_branch /
    # invoke_branch_version / await_run callables) and NodeDefinition
    # declares them (tinyassets/branches.py:267/285/294), but this authoring
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
    # PR-122 Phase 1: ``effects`` declares external-write sinks the node's
    # outputs should be routed to after the run completes. Validated by
    # NodeDefinition.__post_init__ (list of strings) — same partition
    # pattern as input_keys/output_keys plumbing.
    effects_raw = raw.get("effects", [])
    if effects_raw is None:
        effects_arg: list[str] = []
    elif isinstance(effects_raw, list):
        effects_arg = list(effects_raw)
    else:
        return (
            f"node '{nid}' effects must be a JSON array of strings"
        )
    # SECURITY (Codex ADAPT, PR #1349): a node is only approved when the
    # recorded approval hash matches the *effective* source_code being stored.
    # This is the authoring-time half of the provenance gate; the compiler
    # enforces the same check at run time (_validate_source_code). Without
    # this, a caller could pass a bare ``approved=True`` (or inherit one via
    # an inline override) for code no approver ever reviewed. We only carry
    # the approval boolean + provenance forward when the hash matches; any
    # mismatch demotes the node to unapproved with blank provenance.
    approved_source_hash = (raw.get("approved_source_hash") or "").strip()
    if _approval_provenance_valid(
        raw.get("approved"), source_code, approved_source_hash,
    ):
        approved_arg = bool(raw.get("approved"))
        approved_by_arg = raw.get("approved_by") or ""
        approved_at_arg = raw.get("approved_at") or ""
        approved_hash_arg = approved_source_hash if source_code else ""
        approval_reason_arg = raw.get("approval_reason") or ""
    else:
        approved_arg = False
        approved_by_arg = ""
        approved_at_arg = ""
        approved_hash_arg = ""
        approval_reason_arg = ""
    try:
        node = NodeDefinition(
            node_id=nid,
            display_name=display,
            description=raw.get("description", ""),
            phase=phase,
            input_keys=in_keys,
            output_keys=out_keys,
            tools_allowed=tools_allowed,
            strict_input_isolation=strict_input_isolation,
            source_code=source_code,
            prompt_template=prompt_template,
            model_hint=model_hint,
            reasoning_effort=reasoning_effort,
            llm_policy=llm_policy,
            timeout_seconds=timeout_seconds,
            author=raw.get("author") or _current_actor(),
            approved=approved_arg,
            approved_by=approved_by_arg,
            approved_at=approved_at_arg,
            approved_source_hash=approved_hash_arg,
            approval_reason=approval_reason_arg,
            invoke_branch_spec=invoke_branch_arg,
            invoke_branch_version_spec=invoke_branch_version_arg,
            await_run_spec=await_run_arg,
            effects=effects_arg,
        )
    except ValueError as exc:
        return str(exc)

    # Preserve every behavior-affecting field the constructor didn't set
    # (requires_sandbox, enabled, node_kind, …) so import/build is lossless.
    # Type-validated: a mis-typed passthrough field rejects the whole node.
    passthrough_err = _apply_passthrough_node_fields(node, raw)
    if passthrough_err:
        return passthrough_err

    if any(n.node_id == nid for n in branch.node_defs):
        return f"node '{nid}' already exists on the branch"

    branch.node_defs.append(node)
    branch.graph_nodes.append(GraphNodeRef(
        id=nid, node_def_id=nid, position=len(branch.graph_nodes),
    ))
    return ""


def _apply_edge_spec(branch: Any, raw: dict[str, Any]) -> str:
    from tinyassets.branches import EdgeDefinition

    src = (raw.get("from") or raw.get("from_node") or "").strip()
    dst = (raw.get("to") or raw.get("to_node") or "").strip()
    if not src or not dst:
        return "edge spec missing 'from' or 'to'"
    branch.edges.append(EdgeDefinition(from_node=src, to_node=dst))
    return ""


def _apply_conditional_edge_spec(branch: Any, raw: dict[str, Any]) -> str:
    from tinyassets.branches import ConditionalEdge

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
    # BUG-094: ``default_value`` is the canonical StateFieldDecl key
    # (tinyassets/branches.py:224). Read it first, fall back to the legacy
    # ``default`` / ``field_default`` spec shapes. Write to ``default_value``
    # so PR #932's ``_state_schema_defaults`` finds the seed value at runtime;
    # also dual-write ``default`` for back-compat with any reader that still
    # uses the legacy storage key.
    default = raw.get(
        "default_value",
        raw.get("default", raw.get("field_default", "")),
    )
    if default != "":
        entry["default_value"] = default
        entry["default"] = default
    branch.state_schema.append(entry)
    if ftype_raw.lower() not in _VALID_STATE_TYPES:
        return (
            f"state field '{fname}' type '{ftype_raw}' unknown; "
            f"coerced to '{ftype}'."
        )
    return ""


def _coerce_model_hint_update(raw: Any, field: str) -> tuple[str, str]:
    if raw is None:
        return "", ""
    if not isinstance(raw, str):
        return "", f"{field} must be a string."
    return raw, ""


def _coerce_llm_policy_update(
    raw: Any, field: str,
) -> tuple[dict[str, Any] | None, str]:
    if raw is None:
        return None, ""
    if isinstance(raw, dict):
        policy = raw
    elif isinstance(raw, str):
        value = raw.strip()
        if not value or value == "null":
            return None, ""
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            return None, f"{field} is not valid JSON: {exc}"
        if decoded is None:
            return None, ""
        if isinstance(decoded, dict):
            policy = decoded
        else:
            return None, f"{field} must be a JSON object or null."
    else:
        return None, f"{field} must be a JSON object or null."

    from tinyassets.branches import _validate_llm_policy_shape

    errors = _validate_llm_policy_shape(policy, context=field)
    if errors:
        return None, "; ".join(errors)
    return policy, ""


_NODE_UPDATE_PATCH_META_FIELDS = frozenset({"op", "node_id"})
_VALID_REASONING_EFFORTS = frozenset({"minimal", "low", "medium", "high", "xhigh"})
_NODE_UPDATE_FIELDS = frozenset({
    "display_name",
    "description",
    "phase",
    "prompt_template",
    "source_code",
    "model_hint",
    "reasoning_effort",
    "llm_policy",
    "input_keys",
    "output_keys",
    "tools_allowed",
    "timeout_seconds",
    "retry_policy",
    "enabled",
    "invoke_branch_spec",
    "invoke_branch_version_spec",
    "await_run_spec",
})
_NODE_UPDATE_SPEC_FIELDS = (
    "invoke_branch_spec",
    "invoke_branch_version_spec",
    "await_run_spec",
)


def _coerce_node_update_bool(raw: Any, field: str) -> tuple[bool | None, str]:
    if isinstance(raw, bool):
        return raw, ""
    value = str(raw).strip().lower()
    if value in {"true", "1", "yes", "on"}:
        return True, ""
    if value in {"false", "0", "no", "off"}:
        return False, ""
    return None, f"{field} must be a boolean."


def _coerce_timeout_seconds_update(raw: Any, field: str) -> tuple[float, str]:
    try:
        return float(raw), ""
    except (TypeError, ValueError):
        return 0.0, f"{field} must be a number."


def _coerce_retry_policy_update(raw: Any, field: str) -> tuple[dict[str, Any], str]:
    if isinstance(raw, dict):
        return dict(raw), ""
    if isinstance(raw, str):
        value = raw.strip()
        if not value:
            return {}, f"{field} must be a JSON object."
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            return {}, f"{field} is not valid JSON: {exc}"
        if isinstance(decoded, dict):
            return dict(decoded), ""
    return {}, f"{field} must be a JSON object."


def _coerce_node_spec_update(
    raw: Any, field: str,
) -> tuple[dict[str, Any] | None, str]:
    if raw in (None, ""):
        return None, ""
    if isinstance(raw, dict):
        return raw, ""
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            return None, f"{field} is not valid JSON: {exc}"
        if isinstance(decoded, dict):
            return decoded, ""
    return None, f"{field} must be a JSON object or null."


def _apply_node_updates(
    node: Any,
    updates: dict[str, Any],
    *,
    ignored_fields: frozenset[str] = frozenset(),
) -> str:
    """Apply validated node update fields shared by both update surfaces."""
    from tinyassets.api.extensions import VALID_PHASES
    from tinyassets.phase_vocab import normalize_phase

    editable_updates = {
        key: value
        for key, value in updates.items()
        if key not in ignored_fields
    }
    unknown = sorted(set(editable_updates) - _NODE_UPDATE_FIELDS)
    if unknown:
        return (
            "update_node unsupported field(s): "
            f"{', '.join(unknown)}. Supported: "
            f"{', '.join(sorted(_NODE_UPDATE_FIELDS))}"
        )
    if not editable_updates:
        return "update_node requires at least one field to update"

    incoming_template = editable_updates.get("prompt_template", "")
    incoming_source = editable_updates.get("source_code", "")
    if incoming_template and incoming_source:
        return "Pass prompt_template OR source_code, not both."

    if "display_name" in editable_updates:
        node.display_name = editable_updates["display_name"]
    if "description" in editable_updates:
        node.description = editable_updates["description"]
    if "phase" in editable_updates:
        new_phase = editable_updates["phase"] or "custom"
        if new_phase not in VALID_PHASES:
            return (
                f"Invalid phase '{new_phase}'. Must be one of: "
                f"{', '.join(sorted(VALID_PHASES))}"
            )
        node.phase = normalize_phase(new_phase)
    if "prompt_template" in editable_updates:
        node.prompt_template = editable_updates["prompt_template"]
        if node.prompt_template:
            node.source_code = ""
            _clear_source_code_approval(node)
    if "source_code" in editable_updates:
        next_source = editable_updates["source_code"]
        if next_source != node.source_code:
            _clear_source_code_approval(node)
        node.source_code = next_source
        if node.source_code:
            node.prompt_template = ""
    if "model_hint" in editable_updates:
        model_hint, err = _coerce_model_hint_update(
            editable_updates["model_hint"], "model_hint",
        )
        if err:
            return err
        node.model_hint = model_hint
    if "reasoning_effort" in editable_updates:
        effort = str(editable_updates["reasoning_effort"] or "").strip().lower()
        if effort and effort not in _VALID_REASONING_EFFORTS:
            return (
                f"Invalid reasoning_effort '{effort}'. Must be empty (provider "
                f"default) or one of: {', '.join(sorted(_VALID_REASONING_EFFORTS))}"
            )
        node.reasoning_effort = effort
    if "llm_policy" in editable_updates:
        llm_policy, err = _coerce_llm_policy_update(
            editable_updates["llm_policy"],
            f"node '{node.node_id}' llm_policy",
        )
        if err:
            return err
        node.llm_policy = llm_policy
    if "input_keys" in editable_updates:
        keys, err = _coerce_node_keys(
            editable_updates["input_keys"], "input_keys",
        )
        if err:
            return err
        node.input_keys = keys
    if "output_keys" in editable_updates:
        keys, err = _coerce_node_keys(
            editable_updates["output_keys"], "output_keys",
        )
        if err:
            return err
        node.output_keys = keys
    if "tools_allowed" in editable_updates:
        tools_allowed, err = _coerce_node_keys(
            editable_updates["tools_allowed"], "tools_allowed",
        )
        if err:
            return err
        node.tools_allowed = tools_allowed
    if "timeout_seconds" in editable_updates:
        timeout_seconds, err = _coerce_timeout_seconds_update(
            editable_updates["timeout_seconds"],
            f"node '{node.node_id}' timeout_seconds",
        )
        if err:
            return err
        node.timeout_seconds = timeout_seconds
    if "retry_policy" in editable_updates:
        retry_policy, err = _coerce_retry_policy_update(
            editable_updates["retry_policy"],
            f"node '{node.node_id}' retry_policy",
        )
        if err:
            return err
        node.retry_policy = retry_policy
    if "enabled" in editable_updates:
        enabled, err = _coerce_node_update_bool(
            editable_updates["enabled"], "enabled",
        )
        if err:
            return err
        node.enabled = bool(enabled)
    for spec_field in _NODE_UPDATE_SPEC_FIELDS:
        if spec_field in editable_updates:
            val, err = _coerce_node_spec_update(
                editable_updates[spec_field], spec_field,
            )
            if err:
                return err
            setattr(node, spec_field, val)
    return ""


def _staged_branch_from_spec(
    spec: dict[str, Any],
) -> tuple[Any, list[str]]:
    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.branches import BranchDefinition, normalize_branch_skill_snapshots

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

    # PR-037: accept the nested `graph` shape that `get_branch` RETURNS.
    # Without this, a user trying to fork by mirroring a live branch's
    # response shape (`{"graph": {"edges": [...], "conditional_edges":
    # [...], "entry_point": "..."}}`) has their edges silently dropped
    # during staging. The validator then reports "node not reachable
    # from entry point" — diagnostics that contradict what the submitted
    # spec literally contains. This mirrors what
    # `BranchDefinition.from_dict` already does for the DB-row path.
    graph_blob = spec.get("graph") if isinstance(spec.get("graph"), dict) else None

    def _spec_get(key: str, default=None):
        """Top-level key wins; otherwise fall back to graph_blob[key]."""
        top = spec.get(key)
        if top is not None:
            return top
        if graph_blob is not None and graph_blob.get(key) is not None:
            return graph_blob.get(key)
        return default

    def _spec_has_graph_key(key: str) -> bool:
        return key in spec or (
            graph_blob is not None and graph_blob.get(key) is not None
        )

    if branch.fork_from:
        from tinyassets.branch_versions import get_branch_version

        parent_version = get_branch_version(_base_path(), branch.fork_from)
        if parent_version is not None:
            parent = BranchDefinition.from_dict(parent_version.snapshot)
            parent_copy = BranchDefinition.from_dict(parent.to_dict())
            parent_skills = parent_copy.skills
            if not parent_skills and parent.branch_def_id:
                from tinyassets.daemon_server import get_branch_definition

                try:
                    parent_def = get_branch_definition(
                        _base_path(), branch_def_id=parent.branch_def_id,
                    )
                except KeyError:
                    parent_def = {}
                if parent_def:
                    parent_skills = BranchDefinition.from_dict(parent_def).skills
            branch.parent_def_id = parent.branch_def_id
            if "skills" not in spec:
                branch.skills = parent_skills
            if "node_defs" not in spec and "nodes" not in spec:
                # SECURITY (Codex final residual, PR #1349): the parent's
                # node_defs are inherited wholesale. A carried node whose
                # source no longer matches its recorded approval hash — or
                # which carries approved=True with an empty/legacy hash — must
                # not survive the fork as still-approved. Re-validate each
                # carried node against its source hash; the fail-closed runtime
                # gate is the backstop, this keeps the persisted snapshot
                # honest at authoring time.
                branch.node_defs = [
                    _reconcile_node_approval(n) for n in parent_copy.node_defs
                ]
                branch.graph_nodes = parent_copy.graph_nodes
            if not _spec_has_graph_key("edges"):
                branch.edges = parent_copy.edges
            if not _spec_has_graph_key("conditional_edges"):
                branch.conditional_edges = parent_copy.conditional_edges
            if not _spec_has_graph_key("entry_point"):
                branch.entry_point = parent_copy.entry_point
            if "state_schema" not in spec:
                branch.state_schema = list(parent_copy.state_schema)
            # Branch-level routing/concurrency inherit through a fork too, or a
            # remix silently loses them (Codex S2 F2).
            if "default_llm_policy" not in spec:
                branch.default_llm_policy = parent_copy.default_llm_policy
            if "concurrency_budget" not in spec:
                branch.concurrency_budget = parent_copy.concurrency_budget

    for idx, raw in enumerate(spec.get("node_defs") or spec.get("nodes") or []):
        err = _apply_node_spec(branch, raw)
        if err:
            errors.append(f"node[{idx}]: {err}")

    for idx, raw in enumerate(_spec_get("edges") or []):
        err = _apply_edge_spec(branch, raw)
        if err:
            errors.append(f"edge[{idx}]: {err}")

    for idx, raw in enumerate(_spec_get("conditional_edges") or []):
        err = _apply_conditional_edge_spec(branch, raw)
        if err:
            errors.append(f"conditional_edge[{idx}]: {err}")

    for idx, raw in enumerate(spec.get("state_schema") or []):
        err = _apply_state_field_spec(branch, raw)
        if err:
            errors.append(f"state_schema[{idx}]: {err}")

    entry = (spec.get("entry_point") or "").strip()
    if not entry and graph_blob is not None:
        entry = (graph_blob.get("entry_point") or "").strip()
    if entry:
        branch.entry_point = entry

    # Branch-level knobs: explicit spec values override any inherited default,
    # with typed validation and no silent coercion (Codex S2 F2).
    if "default_llm_policy" in spec:
        raw_policy = spec.get("default_llm_policy")
        if raw_policy is None:
            branch.default_llm_policy = None
        elif isinstance(raw_policy, dict):
            from tinyassets.branches import _validate_llm_policy_shape

            policy_errors = _validate_llm_policy_shape(
                raw_policy, context="default_llm_policy",
            )
            if policy_errors:
                errors.extend(policy_errors)
            else:
                branch.default_llm_policy = raw_policy
        else:
            errors.append(
                "default_llm_policy must be a JSON object or null, got "
                f"{type(raw_policy).__name__}"
            )
    if "concurrency_budget" in spec:
        raw_budget = spec.get("concurrency_budget")
        if (
            isinstance(raw_budget, bool)
            or not isinstance(raw_budget, int)
            or raw_budget < 1
        ):
            errors.append(
                "concurrency_budget must be a positive integer, got "
                f"{type(raw_budget).__name__} ({raw_budget!r})"
            )
        else:
            branch.concurrency_budget = raw_budget

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
    from tinyassets.daemon_server import save_branch_definition

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

    top_level_goal_id = (kwargs.get("goal_id") or "").strip()
    if top_level_goal_id:
        spec = {**spec, "goal_id": top_level_goal_id}

    branch, staging_errors = _staged_branch_from_spec(spec)
    validation_errors = branch.validate()
    errors = staging_errors + validation_errors

    # Validate fork_from points to a real branch_version_id.
    if branch.fork_from:
        from tinyassets.branch_versions import get_branch_version
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
    from tinyassets.branches import BranchDefinition as _BD

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
        "batch_receipt": _branch_authoring_batch_receipt(
            persisted,
            action="build_branch",
            operation_count=1,
            request_id=kwargs.get("request_id", ""),
        ),
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
    if name == "set_state_field_default":
        # BIND op (patch-loop S2): set the default value of an EXISTING state
        # field. This is how a user binds a repo-blind reference's unbound
        # params (target_repo / credential_ref / merge_policy) as a user act —
        # the value is seeded into initial run state via _state_schema_defaults.
        # It never creates a field (use add_state_field for that) and never
        # bakes a value into the design itself; it sets the owner's binding on
        # their own remixed copy.
        fname = (op.get("name") or op.get("field_name") or "").strip()
        if not fname:
            return "set_state_field_default requires name"
        target_field = next(
            (f for f in branch.state_schema if f.get("name") == fname), None,
        )
        if target_field is None:
            return (
                f"set_state_field_default: state field '{fname}' not found. "
                "Add it with add_state_field first, or fix the name."
            )
        if not any(k in op for k in ("default_value", "default", "value")):
            return (
                "set_state_field_default requires 'default_value' "
                f"for field '{fname}'."
            )
        default = op.get(
            "default_value", op.get("default", op.get("value", "")),
        )
        # Dual-write both keys, mirroring _apply_state_field_spec so PR #932's
        # _state_schema_defaults finds the seed value at runtime.
        target_field["default_value"] = default
        target_field["default"] = default
        # Mark this default as a personal BINDING value (Codex S2 F1a): export
        # redacts bound values so a user's repo/credential/intake binding never
        # travels in a portable artifact or a listing others can read.
        target_field["bound"] = True
        return ""
    if name == "update_node":
        nid = (op.get("node_id") or "").strip()
        if not nid:
            return "update_node requires node_id"
        for n in branch.node_defs:
            if n.node_id == nid:
                return _apply_node_updates(
                    n,
                    op,
                    ignored_fields=_NODE_UPDATE_PATCH_META_FIELDS,
                )
        return f"update_node: node '{nid}' not found"
    if name == "add_skill":
        from tinyassets.branches import normalize_branch_skill_snapshot

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
        from tinyassets.branches import normalize_branch_skill_snapshot

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
        from tinyassets.branches import normalize_branch_skill_snapshots

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
        from tinyassets.branch_versions import get_branch_version
        if get_branch_version(_base_path(), bvid) is None:
            return (
                f"set_fork_from: '{bvid}' is not a known branch_version_id. "
                "Pass a published branch_version_id, not a branch_def_id."
            )
        branch.fork_from = bvid
        return ""
    return f"unknown op '{name}'"


def _ext_branch_patch(kwargs: dict[str, Any]) -> str:
    import copy

    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import (
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

    # BUG-081: author-gate. Reject patch_branch on a non-author branch
    # unless the caller explicitly passes force=true. The previous shape
    # accepted any caller against any public branch, conflating
    # `visibility=public` (discoverable + readable) with mutation
    # authority. Slice-0 substrate-readiness probe 2026-05-13 demonstrated
    # the gap by mutating a chatgpt-community-builder-authored branch
    # from a non-author session. See pages/bugs/bug-081-... for the
    # filing.
    branch_author = (source.get("author") or "").strip()
    caller = (_current_actor() or "").strip()
    force_mutate = bool(kwargs.get("force", False))
    if branch_author and caller and branch_author != caller and not force_mutate:
        return json.dumps({
            "status": "rejected",
            "error": (
                f"patch_branch denied: branch '{bid}' is authored by "
                f"'{branch_author}'; caller is '{caller}'. Pass "
                "force=true to mutate another author's branch, or fork "
                "it (publish_version + build_branch with fork_from) and "
                "amend your own copy. See BUG-081."
            ),
            "branch_author": branch_author,
            "caller": caller,
        })

    old_name = source.get("name", "")
    staging = BranchDefinition.from_dict(copy.deepcopy(source))

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

    actor = _current_actor()
    try:
        parent_version = publish_branch_version(
            _base_path(),
            source,
            publisher=actor,
            notes="patch_branch pre-patch snapshot",
        )
    except (KeyError, ValueError) as exc:
        return json.dumps({
            "status": "rejected",
            "error": f"Could not snapshot pre-patch branch: {exc}",
        })

    saved = save_branch_definition(_base_path(), branch_def=staging.to_dict())
    persisted = BranchDefinition.from_dict(saved)
    try:
        branch_version = publish_branch_version(
            _base_path(),
            saved,
            publisher=actor,
            notes="patch_branch post-patch snapshot",
            parent_version_id=parent_version.branch_version_id,
        )
    except (KeyError, ValueError) as exc:
        return json.dumps({
            "status": "rejected",
            "error": f"Patch saved but post-patch version snapshot failed: {exc}",
            "branch_def_id": persisted.branch_def_id,
            "parent_version_id": parent_version.branch_version_id,
        })

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
        f"Published version `{branch_version.branch_version_id}`.",
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
        "branch_version_id": branch_version.branch_version_id,
        "content_hash": branch_version.content_hash,
        "published_at": branch_version.published_at,
        "parent_version_id": branch_version.parent_version_id,
        "ops_applied": len(changes),
        "node_count": len(persisted.node_defs),
        "edge_count": len(persisted.edges),
        "skill_count": len(persisted.skills),
        "patched_fields": patched_fields,
        "name_updated": name_updated,
        "new_name": persisted.name,
        "post_patch": post_patch,
        "batch_receipt": _branch_authoring_batch_receipt(
            persisted,
            action="patch_branch",
            operation_count=len(changes),
            request_id=kwargs.get("request_id", ""),
        ),
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
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import (
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
    # kwargs. Individual kwargs are the phone-friendly shape;
    # changes_json is for scripts batching.
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
            "prompt_template", "source_code", "model_hint",
            "input_keys", "output_keys", "tools_allowed",
            "timeout_seconds", "retry_policy", "enabled",
        ):
            if field in kwargs and kwargs.get(field) is not None and kwargs.get(field) != "":
                updates[field] = kwargs[field]
        if "llm_policy" in kwargs and kwargs.get("llm_policy") is not None:
            updates["llm_policy"] = kwargs["llm_policy"]
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
            if raw_val is not None and raw_val != "":
                updates[field] = raw_val

    if not updates:
        return json.dumps({
            "status": "rejected",
            "error": (
                "No fields to update. Pass one or more of "
                "display_name / description / phase / prompt_template / "
                "source_code / model_hint / llm_policy / retry_policy / "
                "timeout_seconds / input_keys / output_keys / tools_allowed, or a "
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

    try:
        update_error = _apply_node_updates(target_node, updates)
    except Exception as exc:
        return json.dumps({
            "status": "rejected",
            "error": f"Failed to apply update: {exc}",
        })
    if update_error:
        return json.dumps({"status": "rejected", "error": update_error})

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
        from tinyassets.runs import record_node_edit_audit

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
    from tinyassets.daemon_server import search_nodes

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
    from tinyassets.api.extensions import VALID_PHASES
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import (
        get_branch_definition,
        save_branch_definition,
    )
    from tinyassets.phase_vocab import normalize_phase

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
    if field == "phase":
        value = normalize_phase(str(value))

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
    #
    # SECURITY (Codex round-2, PR #1349): patch_nodes is an MCP-reachable
    # node-mutation path. Changing executable content (source_code /
    # prompt_template) must not leave a node ``approved=True`` for code the
    # approver never saw. Mirror the update_node surface: reconcile approval
    # against the *new* effective source via the round-1 helper, which
    # clears every approval field unless the recorded hash still matches the
    # post-patch source. This upholds the authoring-layer invariant the
    # runtime carve-out relies on (no persisted node ever carries
    # approved=True with an empty/stale approved_source_hash).
    for node in staging.node_defs:
        if node.node_id not in target_ids:
            continue
        setattr(node, field, value)
        if field == "prompt_template" and value:
            node.source_code = ""
            # Switched to a prompt node: no executable surface to gate, and
            # any prior source approval no longer describes the body.
            _clear_source_code_approval(node)
        elif field == "source_code":
            node.prompt_template = ""
            # Approval only survives when the recorded hash still matches the
            # new source; otherwise demote to unapproved (blank provenance).
            if not _approval_provenance_valid(
                node.approved, node.source_code or "",
                node.approved_source_hash or "",
            ):
                _clear_source_code_approval(node)

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


# ── Portable design artifacts: export / import / remix (patch-loop S2) ─────
# The connector remix path so a signed-in user's chatbot can take a published
# branch DESIGN and make it their own: discover (list_branches scope=published)
# -> import an artifact OR remix a published design by id -> bind params ->
# export back to the same portable envelope. These reuse the composite
# build_branch path and the record_remix provenance edge — no parallel
# machinery (PLAN commons-first + minimal-primitives). Design basis:
# docs/design-notes/2026-07-15-user-patch-loop-reference-design.md (G2/S2).


# Approval provenance is host/actor-scoped trust; it must NOT travel inside a
# portable artifact (a shared artifact carrying approved=True would smuggle
# execution authority across hosts). Everything ELSE on the node passes through.
# Re-import re-runs the approve gate (fail-closed, hard rule 8) and the runtime
# gate is the backstop.
_NODE_EXPORT_REDACTED_FIELDS = (
    "approved", "approved_by", "approved_at",
    "approved_source_hash", "approval_reason",
)


def _node_def_to_design_spec(nd: Any) -> dict[str, Any]:
    """Serialize a NodeDefinition into a build_branch node spec that PRESERVES
    every behavior-affecting field.

    Dumps the WHOLE dataclass via ``to_dict`` (not a hand-maintained allowlist)
    so security/behavior flags like ``requires_sandbox`` and ``enabled`` — and
    any FUTURE node field (e.g. S3's ``node_kind``) — round-trip through
    export -> import unchanged. The only redaction is approval provenance
    (see ``_NODE_EXPORT_REDACTED_FIELDS``). Codex S2 adapt (finding 1).
    """
    spec = dict(nd.to_dict())
    for redacted in _NODE_EXPORT_REDACTED_FIELDS:
        spec.pop(redacted, None)
    return spec


# A state field is a personal BINDING once the owner sets its default via the
# set_state_field_default op (which marks it ``bound``). Personal binding VALUES
# (repo identity, vault/credential refs, intake sources) must never travel in a
# portable artifact or a listing another user can read — export carries the
# field SCHEMA, never the bound value (Codex S2 latest-model, finding 1a).
_STATE_FIELD_VALUE_KEYS = ("default_value", "default")


def _state_field_to_design_spec(field: dict[str, Any]) -> dict[str, Any]:
    """Serialize a state_schema entry, redacting personal binding VALUES.

    - Design defaults (declared at build time, no ``bound`` marker) travel.
    - Bound values (set via BIND / set_state_field_default) are REDACTED: the
      artifact keeps the field slot (name/type/description/reducer) but never
      the value. The ``bound`` marker itself is owner-only and never travels.
    """
    spec = dict(field)
    spec.pop("bound", None)
    if field.get("bound"):
        for value_key in _STATE_FIELD_VALUE_KEYS:
            spec.pop(value_key, None)
    return spec


def _branch_to_design_spec(
    branch: Any, *, metadata_branch: Any = None,
) -> dict[str, Any]:
    """Reconstruct a build_branch-compatible spec from a BranchDefinition.

    ``branch`` supplies the TOPOLOGY (nodes/edges/state/skills) — for export
    this is the immutable active-version snapshot (finding 3). Branch-level
    METADATA (name/description/domain/goal/tags + the F2 routing/concurrency
    knobs) is not part of the content-hashed snapshot, so it comes from
    ``metadata_branch`` (the live row) when provided, else from ``branch``.

    Topology lives in an embedded graph blob on the raw registry row, so the
    caller MUST pass a rebuilt ``BranchDefinition`` (from_dict), never the raw
    row, or edges/conditional_edges come back empty (S1 review lesson).
    """
    from tinyassets.branch_designs import REFERENCE_TAG

    meta = metadata_branch if metadata_branch is not None else branch
    spec: dict[str, Any] = {
        "name": meta.name,
        "description": meta.description,
        "domain_id": meta.domain_id,
        "entry_point": branch.entry_point,
        "node_defs": [_node_def_to_design_spec(nd) for nd in branch.node_defs],
        "edges": [
            {"from": e.from_node, "to": e.to_node} for e in branch.edges
        ],
        "conditional_edges": [
            {"from": ce.from_node, "conditions": dict(ce.conditions)}
            for ce in branch.conditional_edges
        ],
        "state_schema": [
            _state_field_to_design_spec(f) for f in branch.state_schema
        ],
    }
    if meta.goal_id:
        spec["goal_id"] = meta.goal_id
    # Branch-level routing/cost/concurrency knobs must round-trip too, or a
    # remix silently loses provider routing + concurrency (Codex S2 F2).
    if getattr(meta, "default_llm_policy", None) is not None:
        spec["default_llm_policy"] = meta.default_llm_policy
    concurrency = getattr(meta, "concurrency_budget", None)
    if concurrency is not None:
        spec["concurrency_budget"] = concurrency
    # Drop the seed-only tags — an exported/imported copy is not the seeded
    # reference and must not masquerade as it (idempotency tag + reference tag).
    tags = [
        t for t in (meta.tags or [])
        if t != REFERENCE_TAG and not str(t).startswith("design:")
    ]
    if tags:
        spec["tags"] = tags
    if getattr(branch, "skills", None):
        spec["skills"] = branch.skills
    return spec


def _newest_active_branch_version(base_path: Any, branch_def_id: str) -> Any:
    """Newest ACTIVE published version of a branch, or ``None``.

    A rolled-back / superseded version must never be listed, remixed, or
    exported (Codex S2 latest-model, finding 3): select the newest version
    whose ``status == "active"``, deriving from that immutable snapshot rather
    than the mutable branch row.
    """
    from tinyassets.branch_versions import list_branch_versions

    for version in list_branch_versions(base_path, branch_def_id, limit=200):
        if (getattr(version, "status", "active") or "active") == "active":
            return version
    return None


def _load_owned_or_public_branch(bid_or_name: str) -> tuple[Any, str]:
    """Resolve + load a branch, applying the private-author visibility gate.

    Returns ``(BranchDefinition_or_None, error_json)``. Mirrors
    ``_ext_branch_get``: a private branch owned by someone else answers the
    "not found" envelope so existence isn't leaked.
    """
    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition

    bid = _resolve_branch_id((bid_or_name or "").strip(), _base_path())
    if not bid:
        return None, json.dumps({"error": "branch_def_id is required."})
    try:
        row = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return None, json.dumps({"error": f"Branch '{bid}' not found."})
    visibility = row.get("visibility", "public") or "public"
    if visibility == "private" and row.get("author", "") != _current_actor():
        return None, json.dumps({"error": f"Branch '{bid}' not found."})
    return BranchDefinition.from_dict(row), ""


def _ext_branch_export_design(kwargs: dict[str, Any]) -> str:
    """Export an owned/public branch as a portable design artifact envelope.

    Read-only. Anyone may export what they can read (public branches are the
    remix commons); private branches are author-gated via
    ``_load_owned_or_public_branch``.
    """
    from tinyassets.branch_designs import wrap_spec_as_design_artifact
    from tinyassets.branch_versions import list_branch_versions
    from tinyassets.branches import BranchDefinition

    branch, err = _load_owned_or_public_branch(
        kwargs.get("branch_def_id", "") or kwargs.get("name", ""),
    )
    if err:
        return err

    # Topology comes from the newest ACTIVE version's immutable snapshot, never
    # the mutable row (finding 3): a rolled-back topology is not exportable.
    # Branch-level metadata (name/description/routing) is not in the snapshot,
    # so it comes from the row. A published-but-all-rolled-back branch refuses;
    # an unpublished draft (no versions) exports its live row for the owner.
    active = _newest_active_branch_version(_base_path(), branch.branch_def_id)
    if active is not None:
        topology_branch = BranchDefinition.from_dict(active.snapshot)
    elif list_branch_versions(_base_path(), branch.branch_def_id, limit=1):
        return json.dumps({
            "status": "rejected",
            "error": (
                f"Branch '{branch.branch_def_id}' has no active published "
                "version (its latest versions were rolled back); nothing safe "
                "to export. Publish a fresh version first."
            ),
        })
    else:
        topology_branch = branch  # unpublished draft — the row is the only state

    spec = _branch_to_design_spec(topology_branch, metadata_branch=branch)
    design_id = (kwargs.get("design_id") or branch.branch_def_id or "").strip()
    try:
        design_version = int(kwargs.get("design_version") or 1)
    except (TypeError, ValueError):
        design_version = 1
    artifact = wrap_spec_as_design_artifact(
        spec,
        design_id=design_id,
        design_version=design_version,
        title=branch.name,
        provenance=(
            f"Exported from TinyAssets branch {branch.branch_def_id} "
            f"by {branch.author}"
        ),
    )
    return json.dumps({
        "status": "exported",
        "branch_def_id": branch.branch_def_id,
        "design_id": design_id,
        "artifact": artifact,
        "artifact_json": json.dumps(artifact),
    }, default=str)


def _ext_branch_import_design(kwargs: dict[str, Any]) -> str:
    """Import a design artifact (envelope OR raw spec) as a NEW owned branch.

    Reuses the composite ``build_branch`` path. Identity/lineage fields are
    stripped (an import is a fresh owned branch, not a fork — remix_design is
    the lineage-preserving path), and the caller becomes the author.
    """
    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.branch_designs import is_design_envelope, unwrap_design_artifact

    raw = (kwargs.get("artifact_json") or kwargs.get("spec_json") or "").strip()
    if not raw:
        return json.dumps({
            "status": "rejected",
            "error": (
                "artifact_json is required for import_design (a design "
                "envelope or a raw build_branch spec)."
            ),
        })
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return json.dumps({
            "status": "rejected",
            "error": f"artifact_json is not valid JSON: {exc}",
        })

    if is_design_envelope(data):
        try:
            spec = unwrap_design_artifact(data)
        except ValueError as exc:
            return json.dumps({
                "status": "rejected",
                "error": f"invalid design envelope: {exc}",
            })
    elif isinstance(data, dict):
        spec = dict(data)
    else:
        return json.dumps({
            "status": "rejected",
            "error": (
                "artifact_json must decode to a design envelope or a "
                "build_branch spec object."
            ),
        })

    # An import is a fresh owned branch: strip identity + lineage so build
    # does not try to resolve a foreign branch_version_id, and force the
    # caller as author.
    for identity_key in ("branch_def_id", "fork_from"):
        spec.pop(identity_key, None)
    spec["author"] = _current_actor()

    out_str = _ext_branch_build({"spec_json": json.dumps(spec)})
    try:
        out = json.loads(out_str)
    except (json.JSONDecodeError, TypeError):
        return out_str
    if out.get("status") == "built":
        out["status"] = "imported"
        out["imported_as"] = out.get("branch_def_id", "")
    return json.dumps(out, default=str)


def _design_needs_attested_sandbox(node_defs: Any) -> bool:
    """True when any node in the design must run on an attested-sandbox host.

    Derived purely from NODE DATA — a node with ``requires_sandbox`` set, or
    ``node_kind == "coding"`` (S3's coding-node capability) — NOT from S3 code.
    ``getattr`` defaults keep this working on this branch (where NodeDefinition
    has no ``node_kind`` field yet) AND after the S1->S3->S2 rebase (where the
    seeded reference carries the flag and the runtime gate fails coding nodes
    closed without attestation). Codex S2 adapt round 3, finding 1(i).
    """
    for nd in node_defs or []:
        if getattr(nd, "requires_sandbox", False):
            return True
        if (getattr(nd, "node_kind", "") or "").strip().lower() == "coding":
            return True
    return False


def _ext_branch_remix_design(kwargs: dict[str, Any]) -> str:
    """Fork-copy a PUBLISHED design into the caller's own branch + record it.

    Discovery/remix promise covers PUBLISHED public designs only: the source
    must have a published version (private branches answer "not found" via the
    visibility gate; unpublished ones are refused). The child inherits the
    parent's topology via ``build_branch fork_from`` and a ``record_remix``
    provenance edge is written so lineage is queryable.
    """
    from tinyassets.api.engine_helpers import _current_actor
    from tinyassets.branch_versions import list_branch_versions
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import (
        delete_branch_definition,
        get_branch_definition,
        save_branch_definition,
    )

    branch, err = _load_owned_or_public_branch(kwargs.get("branch_def_id", ""))
    if err:
        return err

    # Remix the newest ACTIVE version only — a rolled-back / superseded version
    # must not be remixable (finding 3).
    active = _newest_active_branch_version(_base_path(), branch.branch_def_id)
    if active is None:
        if list_branch_versions(_base_path(), branch.branch_def_id, limit=1):
            return json.dumps({
                "status": "rejected",
                "error": (
                    f"Branch '{branch.branch_def_id}' has no active published "
                    "version (its latest versions were rolled back); a "
                    "regressed design is not remixable. Publish a fresh "
                    "version first."
                ),
            })
        return json.dumps({
            "status": "rejected",
            "error": (
                f"Branch '{branch.branch_def_id}' is not a published design; "
                "only published designs are remixable. Ask the author to "
                "publish a version, or import an exported artifact instead."
            ),
        })
    parent_version_id = active.branch_version_id

    child_name = (kwargs.get("name") or "").strip() or f"{branch.name} (remix)"
    spec = {
        "name": child_name,
        "description": branch.description,
        "fork_from": parent_version_id,
        "author": _current_actor(),
    }
    out_str = _ext_branch_build({"spec_json": json.dumps(spec)})
    try:
        out = json.loads(out_str)
    except (json.JSONDecodeError, TypeError):
        return out_str
    if out.get("status") != "built" or not out.get("branch_def_id"):
        return out_str

    child_id = out["branch_def_id"]

    # Atomic provenance (finding 4): the child exists only if its lineage edge
    # is recorded. On any provenance failure (returned-error OR raised
    # exception) delete the orphan child and fail loudly — never a fake success.
    from tinyassets.api.market import _action_record_remix

    try:
        provenance = json.loads(_action_record_remix({
            "parent_branch_def_id": branch.branch_def_id,
            "child_branch_def_id": child_id,
            "contribution_kind": "remix",
            "actor_id": _current_actor(),
        }))
    except Exception as exc:  # noqa: BLE001 - compensate then fail loud
        delete_branch_definition(_base_path(), branch_def_id=child_id)
        return json.dumps({
            "status": "rejected",
            "error": (
                "remix aborted: recording provenance raised "
                f"{type(exc).__name__}: {exc}. The orphan copy was removed."
            ),
        })
    if not isinstance(provenance, dict) or provenance.get("error"):
        delete_branch_definition(_base_path(), branch_def_id=child_id)
        reason = (
            provenance.get("error")
            if isinstance(provenance, dict) else "malformed provenance response"
        )
        return json.dumps({
            "status": "rejected",
            "error": (
                f"remix aborted: recording provenance failed ({reason}). "
                "The orphan copy was removed."
            ),
        })

    # A remix is the caller's PRIVATE working copy by default (finding 1b): its
    # bound values must never become discoverable/readable by another user. The
    # owner explicitly publishes/opens it to share the DESIGN (export redacts
    # bound values regardless).
    child_def = BranchDefinition.from_dict(
        get_branch_definition(_base_path(), branch_def_id=child_id),
    )
    child_def.visibility = "private"
    save_branch_definition(_base_path(), branch_def=child_def.to_dict())

    # Honest next-steps guidance: do NOT promise "bind and run" when the design
    # carries a coding/sandbox-required node. Such a node runs ONLY on an
    # attested-sandbox host — after the S1->S3->S2 merge the runtime gate fails
    # it closed without attestation. Derived from node data so it is correct on
    # this branch and after rebase (Codex S2 adapt round 3, finding 1(i)).
    needs_sandbox = _design_needs_attested_sandbox(child_def.node_defs)
    if needs_sandbox:
        guidance = (
            f"Remixed '{branch.name}' into your own branch '{child_name}' "
            f"({child_id}). Bind it (write_graph target=branch, "
            "set_state_field_default ops for target_repo / credential_ref / "
            "merge_policy). NOTE: this design has a coding node that runs "
            "ONLY on an attested-sandbox host — until it runs on one, that "
            "step is refused (fails closed) and the loop stays inert. Do not "
            "expect it to open PRs from an unattested host."
        )
    else:
        guidance = (
            f"Remixed '{branch.name}' into your own branch '{child_name}' "
            f"({child_id}). Bind it (write_graph target=branch, "
            "set_state_field_default ops) then run it."
        )
    return json.dumps({
        "status": "remixed",
        "branch_def_id": child_id,
        "name": child_name,
        "parent_branch_def_id": branch.branch_def_id,
        "fork_from": parent_version_id,
        "node_count": out.get("node_count"),
        "visibility": "private",
        "requires_attested_sandbox": needs_sandbox,
        "provenance": provenance,
        "text": guidance,
    }, default=str)


def _action_fork_tree(kwargs: dict[str, Any]) -> str:
    from tinyassets.branch_versions import get_branch_version, list_branch_versions
    from tinyassets.daemon_server import get_branch_definition, list_branch_definitions

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
    "approve_source_code": _ext_branch_approve_source_code,
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
    "export_design": _ext_branch_export_design,
    "import_design": _ext_branch_import_design,
    "remix_design": _ext_branch_remix_design,
}

_BRANCH_WRITE_ACTIONS: frozenset[str] = frozenset({
    "create_branch", "add_node", "connect_nodes",
    "set_entry_point", "add_state_field", "delete_branch",
    "build_branch", "patch_branch", "patch_nodes", "update_node",
    "approve_source_code",
    # Remix path (patch-loop S2): both mint a new owned branch.
    "import_design", "remix_design",
})


# ───────────────────────────────────────────────────────────────────────────
# Branch Design Guide — chatbot-facing prompt body
# ───────────────────────────────────────────────────────────────────────────
# The @mcp.prompt("Branch Design Guide") decoration stays in
# ``tinyassets/universe_server.py`` (Pattern A2) so FastMCP introspection sees
# the chatbot-facing signature exactly as before. The wrapper there delegates
# to ``_branch_design_guide_prompt()`` below.


def _branch_design_guide_prompt() -> str:
    """Return the Branch Design Guide markdown body.

    Wraps the module-level ``_BRANCH_DESIGN_GUIDE`` constant so the
    universe_server-side ``@mcp.prompt`` wrapper has a single delegation
    target. Plain function (no decoration) — the FastMCP registration
    lives in ``tinyassets.universe_server.branch_design_guide``.
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
On success, `build_branch` returns a structured `batch_receipt` that records
what landed, validation status, and source_code approval status. Treat this
receipt as evidence only: it is not an authorization grant, trust session, or
approval-token bypass. Check `batch_receipt.authorization_effect` for the
machine-readable non-grant/non-bypass flags before narrating approval scope.

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

Successful `patch_branch` responses also include `batch_receipt`. Rejected
patches do not. The receipt lets the chatbot summarize the batch and point to
remaining blockers, but it never overrides `source_code` approval or host-owned
gates. Check `batch_receipt.authorization_effect` for the machine-readable
non-grant/non-bypass flags before narrating approval scope.

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
