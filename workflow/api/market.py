"""Paid-market subsystem — extracted from workflow/universe_server.py
(Task #14 — decomp Step 7).

Houses the 5 paid-market economy primitives: escrow, outcomes, attribution
chain, goals, and outcome gates. The MCP tool decorations for `goals()` and
`gates()` stay in `workflow/universe_server.py` (Pattern A2 from the decomp
plan); plain `goals(...)` and `gates(...)` callables are exposed here, and
the wrappers there delegate to them.

Public surface (back-compat re-exported via ``workflow.universe_server``):
    Dispatch tables:
        _ESCROW_ACTIONS / _OUTCOME_ACTIONS / _ATTRIBUTION_ACTIONS
        _GOAL_ACTIONS / _GOAL_WRITE_ACTIONS / _dispatch_goal_action
        _GATES_ACTIONS / _GATE_EVENT_ACTIONS

    Plain MCP-tool callables (Pattern A2):
        goals(action, ...)  / gates(action, ...)

    Escrow handlers:
        _action_escrow_lock / _action_escrow_release / _action_escrow_refund /
        _action_escrow_inspect

    Outcome handlers:
        _action_record_outcome / _action_list_outcomes / _action_get_outcome

    Attribution handlers:
        _action_record_remix / _action_get_provenance

    Goal handlers (9):
        _action_goal_propose / _action_goal_update / _action_goal_bind /
        _action_goal_list / _action_goal_get / _action_goal_search /
        _action_goal_leaderboard / _action_goal_common_nodes /
        _action_goal_set_canonical

    Gates handlers (9 + 6 gate_event):
        _action_gates_define_ladder / _action_gates_get_ladder /
        _action_gates_claim / _action_gates_retract /
        _action_gates_list_claims / _action_gates_leaderboard /
        _action_gates_stake_bonus / _action_gates_unstake_bonus /
        _action_gates_release_bonus
        _action_attest_gate_event / _action_verify_gate_event /
        _action_dispute_gate_event / _action_retract_gate_event /
        _action_get_gate_event / _action_list_gate_events

    Internal helper:
        _current_actor_or_anon (goals-internal wrapper around _current_actor)

Cross-module note: ``_append_global_ledger``, ``_truncate``, ``_current_actor``,
``_ensure_workflow_db``, ``_storage_backend``, ``_format_commit_failed``,
``_format_dirty_file_conflict``, ``_filter_claims_by_branch_visibility``,
``_filter_leaderboard_by_branch_visibility``, ``_split_csv`` all live in
their owning API/helper modules and are lazy-imported inside the functions that
use them. Same pattern as Tasks
#11/#12/#13 used for their cross-module symbols.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from workflow.api.helpers import _base_path
from workflow.catalog import CommitFailedError, DirtyFileError

logger = logging.getLogger("universe_server.market")

PATCH_REQUEST_AUTHORITY_BOUNDARY: dict[str, bool] = {
    "affects_pickup_priority": True,
    "affects_acceptance": False,
    "affects_release": False,
    "affects_merge": False,
}
PATCH_REQUEST_PICKUP_SIGNAL_WEIGHT = 5.0
_PATCH_REQUEST_MEANING_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("bug", ("bug", "broken", "crash", "error", "fail", "flake", "regression")),
    ("project_design", ("architecture", "design note", "plan.md", "principle")),
    ("docs_ops", ("docs", "documentation", "runbook", "ops", "deploy", "ci")),
    ("feature", ("feature", "add support", "new capability")),
    ("patch", ("patch", "fix", "update", "change", "cleanup")),
)
_REQUEST_TYPE_MEANING: dict[str, str] = {
    "branch_proposal": "branch_refinement",
    "canon_change": "patch",
    "general": "patch",
    "revision": "patch",
    "scene_direction": "branch_refinement",
}


def classify_patch_request(
    *,
    text: str,
    request_type: str,
    requester_id: str,
    host_id: str,
    directed_daemon: bool = False,
) -> dict[str, Any]:
    """Classify patch-loop intake before daemon implementation work starts."""
    lower_text = text.lower()
    meaning = _REQUEST_TYPE_MEANING.get(request_type, "patch")
    for candidate, keywords in _PATCH_REQUEST_MEANING_KEYWORDS:
        if any(keyword in lower_text for keyword in keywords):
            meaning = candidate
            break

    authority_scope = (
        "host_priority_allowed" if requester_id == host_id else "requester_pickup_only"
    )
    if directed_daemon:
        authority_scope = f"{authority_scope}+proposal_only_directed_daemon"

    return {
        "access": {
            "claimable_by": ["free_daemon", "paid_daemon"],
            "code_writer_gate": "claude_or_codex",
            "checker_gate": "opposite_family_checker",
        },
        "meaning": meaning,
        "authority": {
            "scope": authority_scope,
            "boundary": dict(PATCH_REQUEST_AUTHORITY_BOUNDARY),
        },
    }


def normalize_patch_request_incentive(
    terms: str,
    *,
    requester_id: str,
    visibility: str = "public",
) -> dict[str, Any]:
    """Return bounded pickup-only incentive metadata for a patch request."""
    clean_terms = terms.strip()
    if not clean_terms:
        return {
            "enabled": False,
            "terms": "",
            "visibility": visibility,
            "requester_id": requester_id,
            "pickup_signal_weight": 0.0,
        }
    return {
        "enabled": True,
        "terms": clean_terms,
        "visibility": visibility,
        "requester_id": requester_id,
        "pickup_signal_weight": PATCH_REQUEST_PICKUP_SIGNAL_WEIGHT,
        "authority_boundary": dict(PATCH_REQUEST_AUTHORITY_BOUNDARY),
    }


# ── Escrow MCP handlers ────────────────────────────────────────────────────────

def _action_escrow_lock(kwargs: dict[str, Any]) -> str:
    """Lock escrow for a node request. Requires WORKFLOW_PAID_MARKET=on."""
    from workflow.payments.actions import action_escrow_lock
    from workflow.producers.node_bid import paid_market_enabled
    from workflow.storage import _connect

    if not paid_market_enabled():
        return json.dumps({
            "status": "not_available",
            "error": "Escrow actions require WORKFLOW_PAID_MARKET=on.",
        })

    node_id = (kwargs.get("node_id") or "").strip()
    claimer = os.environ.get("UNIVERSE_SERVER_USER", "anonymous")
    currency = (kwargs.get("currency") or "MicroToken").strip()
    raw_amount = kwargs.get("amount", 0)
    try:
        amount = int(raw_amount)
    except (TypeError, ValueError):
        return json.dumps({
            "status": "rejected",
            "error": f"amount must be an integer, got {raw_amount!r}.",
        })

    with _connect(_base_path()) as conn:
        result = action_escrow_lock(
            conn,
            node_id=node_id,
            amount=amount,
            claimer=claimer,
            currency=currency,
        )
    return json.dumps(result)


def _action_escrow_release(kwargs: dict[str, Any]) -> str:
    """Release locked escrow to a recipient on completion verdict."""
    from workflow.payments.actions import action_escrow_release
    from workflow.producers.node_bid import paid_market_enabled
    from workflow.storage import _connect

    if not paid_market_enabled():
        return json.dumps({
            "status": "not_available",
            "error": "Escrow actions require WORKFLOW_PAID_MARKET=on.",
        })

    lock_id = (kwargs.get("lock_id") or "").strip()
    recipient_id = (kwargs.get("recipient_id") or "").strip()
    evidence = (kwargs.get("evidence") or "").strip()

    if not recipient_id:
        return json.dumps({
            "status": "rejected",
            "error": "recipient_id is required for escrow_release.",
        })

    with _connect(_base_path()) as conn:
        result = action_escrow_release(
            conn,
            lock_id=lock_id,
            recipient_id=recipient_id,
            evidence=evidence,
        )
    return json.dumps(result)


def _action_escrow_refund(kwargs: dict[str, Any]) -> str:
    """Refund locked escrow to staker on abandonment or rejection."""
    from workflow.payments.actions import action_escrow_refund
    from workflow.producers.node_bid import paid_market_enabled
    from workflow.storage import _connect

    if not paid_market_enabled():
        return json.dumps({
            "status": "not_available",
            "error": "Escrow actions require WORKFLOW_PAID_MARKET=on.",
        })

    lock_id = (kwargs.get("lock_id") or "").strip()
    reason = (kwargs.get("reason") or "").strip()

    with _connect(_base_path()) as conn:
        result = action_escrow_refund(conn, lock_id=lock_id, reason=reason)
    return json.dumps(result)


def _action_escrow_inspect(kwargs: dict[str, Any]) -> str:
    """Read-only inspection of escrow lock(s). No paid-market gate."""
    from workflow.payments.actions import action_escrow_inspect
    from workflow.storage import _connect

    node_id = (kwargs.get("node_id") or "").strip()
    lock_id = (kwargs.get("lock_id") or "").strip()

    with _connect(_base_path()) as conn:
        result = action_escrow_inspect(conn, node_id=node_id, lock_id=lock_id)
    return json.dumps(result)


_ESCROW_ACTIONS: dict[str, Any] = {
    "escrow_lock": _action_escrow_lock,
    "escrow_release": _action_escrow_release,
    "escrow_refund": _action_escrow_refund,
    "escrow_inspect": _action_escrow_inspect,
}

# ── Outcome event MCP actions ─────────────────────────────────────────────


def _outcome_db_path(base_path: "Path") -> "Path":
    return base_path / ".runs.db"


def _outcome_connect(base_path: "Path") -> Any:
    import sqlite3 as _sqlite3

    from workflow.outcomes.schema import migrate_outcome_schema
    db = _outcome_db_path(base_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = _sqlite3.connect(str(db), timeout=30.0)
    conn.row_factory = _sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    migrate_outcome_schema(conn)
    conn.commit()
    return conn


def _outcome_row_to_dict(row: Any) -> dict:
    return {
        "outcome_id": row["outcome_id"],
        "run_id": row["run_id"],
        "outcome_type": row["outcome_type"],
        "evidence_url": row["evidence_url"],
        "verified_at": row["verified_at"],
        "verified_by": row["verified_by"],
        "claim_run_id": row["claim_run_id"],
        "payload": json.loads(row["payload"] or "{}"),
        "recorded_at": row["recorded_at"],
        "note": row["note"] or "",
    }


def _action_record_outcome(kwargs: dict[str, Any]) -> str:
    import uuid as _uuid
    from datetime import datetime, timezone

    from workflow.outcomes.schema import OUTCOME_TYPES

    run_id = (kwargs.get("run_id") or "").strip()
    outcome_type = (kwargs.get("outcome_type") or "").strip()
    if not run_id:
        return json.dumps({"error": "run_id is required."})
    if not outcome_type:
        return json.dumps({"error": "outcome_type is required."})
    if outcome_type not in OUTCOME_TYPES:
        return json.dumps({
            "error": f"Unknown outcome_type '{outcome_type}'.",
            "valid": sorted(OUTCOME_TYPES),
        })
    evidence_url = (kwargs.get("evidence_url") or "").strip() or None
    gate_event_id = (kwargs.get("gate_event_id") or "").strip() or None
    note = (kwargs.get("note") or "").strip()
    raw_payload = kwargs.get("payload_json") or "{}"
    try:
        payload = json.dumps(
            json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
        )
    except (json.JSONDecodeError, TypeError):
        payload = "{}"
    outcome_id = str(_uuid.uuid4())
    recorded_at = datetime.now(timezone.utc).isoformat()
    base = _base_path()
    with _outcome_connect(base) as conn:
        conn.execute(
            """
            INSERT INTO outcome_event
                (outcome_id, run_id, outcome_type, evidence_url,
                 claim_run_id, payload, recorded_at, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (outcome_id, run_id, outcome_type, evidence_url,
             gate_event_id, payload, recorded_at, note),
        )
    return json.dumps({
        "status": "recorded",
        "outcome_id": outcome_id,
        "run_id": run_id,
        "outcome_type": outcome_type,
        "recorded_at": recorded_at,
    })


def _action_list_outcomes(kwargs: dict[str, Any]) -> str:
    branch_def_id = (kwargs.get("branch_def_id") or "").strip()
    run_id = (kwargs.get("run_id") or "").strip()
    outcome_type = (kwargs.get("outcome_type") or "").strip()
    try:
        limit = min(int(kwargs.get("limit") or 50), 200)
    except (TypeError, ValueError):
        limit = 50

    base = _base_path()

    # If filtering by branch_def_id, resolve matching run_ids first.
    if branch_def_id and not run_id:
        try:
            from workflow.runs import initialize_runs_db, query_runs
            initialize_runs_db(base)
            runs = query_runs(base, branch_def_id=branch_def_id, limit=1000)
            run_ids = [r["run_id"] for r in runs]
            if not run_ids:
                return json.dumps({"outcomes": [], "count": 0})
        except Exception:
            return json.dumps({"outcomes": [], "count": 0})
    else:
        run_ids = [run_id] if run_id else []

    with _outcome_connect(base) as conn:
        clauses: list[str] = []
        params: list[Any] = []
        if run_ids:
            placeholders = ",".join("?" * len(run_ids))
            clauses.append(f"run_id IN ({placeholders})")
            params.extend(run_ids)
        if outcome_type:
            clauses.append("outcome_type = ?")
            params.append(outcome_type)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = conn.execute(
            f"SELECT * FROM outcome_event {where} ORDER BY recorded_at DESC LIMIT ?",
            params,
        ).fetchall()
    outcomes = [_outcome_row_to_dict(r) for r in rows]
    return json.dumps({"outcomes": outcomes, "count": len(outcomes)})


def _action_get_outcome(kwargs: dict[str, Any]) -> str:
    outcome_id = (kwargs.get("outcome_id") or "").strip()
    if not outcome_id:
        return json.dumps({"error": "outcome_id is required."})
    base = _base_path()
    with _outcome_connect(base) as conn:
        row = conn.execute(
            "SELECT * FROM outcome_event WHERE outcome_id = ?",
            (outcome_id,),
        ).fetchone()
    if row is None:
        return json.dumps({"error": f"outcome_id '{outcome_id}' not found."})
    return json.dumps(_outcome_row_to_dict(row))


_OUTCOME_ACTIONS: dict[str, Any] = {
    "record_outcome": _action_record_outcome,
    "list_outcomes": _action_list_outcomes,
    "get_outcome": _action_get_outcome,
}

# ── Attribution chain ──────────────────────────────────────────────────────

def _attribution_connect(base_path: "Path") -> Any:
    import sqlite3 as _sqlite3

    from workflow.attribution.schema import migrate_attribution_schema

    db = base_path / ".runs.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = _sqlite3.connect(str(db), timeout=30.0)
    conn.row_factory = _sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    migrate_attribution_schema(conn)
    conn.commit()
    return conn


_VALID_CONTRIBUTION_KINDS = frozenset({"original", "remix", "patch", "template"})


def _action_record_remix(kwargs: dict[str, Any]) -> str:
    import uuid as _uuid
    from datetime import datetime, timezone

    parent_id = (kwargs.get("parent_branch_def_id") or "").strip()
    child_id = (kwargs.get("child_branch_def_id") or "").strip()
    if not parent_id:
        return json.dumps({"error": "parent_branch_def_id is required."})
    if not child_id:
        return json.dumps({"error": "child_branch_def_id is required."})
    if parent_id == child_id:
        return json.dumps({"error": "parent_branch_def_id and child_branch_def_id must differ."})

    contribution_kind = (kwargs.get("contribution_kind") or "remix").strip()
    if contribution_kind not in _VALID_CONTRIBUTION_KINDS:
        return json.dumps({
            "error": f"Unknown contribution_kind '{contribution_kind}'.",
            "valid": sorted(_VALID_CONTRIBUTION_KINDS),
        })

    try:
        credit_share = float(kwargs.get("credit_share") or 0.0)
    except (TypeError, ValueError):
        credit_share = 0.0
    credit_share = max(0.0, min(1.0, credit_share))

    actor_id = (kwargs.get("actor_id") or "anonymous").strip() or "anonymous"
    base = _base_path()

    with _attribution_connect(base) as conn:
        # Cycle guard: reject if child already appears as an ancestor of parent.
        # Walk attribution_edge parents of parent_id up to 50 hops.
        ancestors: set[str] = set()
        frontier = [parent_id]
        for _ in range(50):
            if not frontier:
                break
            placeholders = ",".join("?" * len(frontier))
            rows = conn.execute(
                f"SELECT parent_id FROM attribution_edge WHERE child_id IN ({placeholders})",
                frontier,
            ).fetchall()
            frontier = []
            for r in rows:
                pid = r["parent_id"]
                if pid not in ancestors:
                    ancestors.add(pid)
                    frontier.append(pid)
        if child_id in ancestors or child_id == parent_id:
            return json.dumps({
                "error": "Cycle detected: child is already an ancestor of parent."
            })

        # Compute generation_depth = max depth of parent + 1 (minimum 1).
        row = conn.execute(
            "SELECT MAX(generation_depth) AS d FROM attribution_edge WHERE child_id = ?",
            (parent_id,),
        ).fetchone()
        parent_depth = int(row["d"] or 0) if row and row["d"] is not None else 0
        generation_depth = parent_depth + 1

        edge_id = str(_uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        try:
            conn.execute(
                """
                INSERT INTO attribution_edge
                    (edge_id, parent_id, child_id, parent_kind, child_kind,
                     generation_depth, contribution_kind, created_at)
                VALUES (?, ?, ?, 'branch', 'branch', ?, ?, ?)
                """,
                (edge_id, parent_id, child_id, generation_depth, contribution_kind, created_at),
            )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                return json.dumps({"error": f"Edge {parent_id} → {child_id} already exists."})
            raise

        # Record credit for the remixing actor on the child artifact.
        if credit_share > 0.0:
            credit_id = str(_uuid.uuid4())
            conn.execute(
                """
                INSERT OR IGNORE INTO attribution_credit
                    (credit_id, artifact_id, artifact_kind, actor_id,
                     credit_share, royalty_share, generation_depth,
                     contribution_kind, recorded_at)
                VALUES (?, ?, 'branch', ?, ?, 0.0, ?, ?, ?)
                """,
                (credit_id, child_id, actor_id, credit_share,
                 generation_depth, contribution_kind, created_at),
            )

    return json.dumps({
        "status": "recorded",
        "edge_id": edge_id,
        "parent_branch_def_id": parent_id,
        "child_branch_def_id": child_id,
        "contribution_kind": contribution_kind,
        "generation_depth": generation_depth,
        "credit_share": credit_share,
        "actor_id": actor_id,
        "created_at": created_at,
    })


def _action_get_provenance(kwargs: dict[str, Any]) -> str:
    child_id = (kwargs.get("child_branch_def_id") or "").strip()
    if not child_id:
        return json.dumps({"error": "child_branch_def_id is required."})
    try:
        max_depth = max(1, min(50, int(kwargs.get("max_depth") or 10)))
    except (TypeError, ValueError):
        max_depth = 10

    base = _base_path()
    chain: list[dict[str, Any]] = []

    with _attribution_connect(base) as conn:
        frontier = [child_id]
        visited: set[str] = {child_id}
        depth = 0
        while frontier and depth < max_depth:
            placeholders = ",".join("?" * len(frontier))
            rows = conn.execute(
                f"""
                SELECT e.parent_id, e.child_id, e.generation_depth,
                       e.contribution_kind, e.edge_id, e.created_at,
                       c.actor_id, c.credit_share
                FROM attribution_edge e
                LEFT JOIN attribution_credit c
                    ON c.artifact_id = e.child_id AND c.artifact_kind = 'branch'
                WHERE e.child_id IN ({placeholders})
                ORDER BY e.generation_depth ASC
                """,
                frontier,
            ).fetchall()
            next_frontier: list[str] = []
            for r in rows:
                chain.append({
                    "edge_id": r["edge_id"],
                    "parent_branch_def_id": r["parent_id"],
                    "child_branch_def_id": r["child_id"],
                    "generation_depth": r["generation_depth"],
                    "contribution_kind": r["contribution_kind"],
                    "actor_id": r["actor_id"],
                    "credit_share": r["credit_share"],
                    "created_at": r["created_at"],
                })
                pid = r["parent_id"]
                if pid not in visited:
                    visited.add(pid)
                    next_frontier.append(pid)
            frontier = next_frontier
            depth += 1

    return json.dumps({
        "child_branch_def_id": child_id,
        "chain": chain,
        "count": len(chain),
    })


_ATTRIBUTION_ACTIONS: dict[str, Any] = {
    "record_remix": _action_record_remix,
    "get_provenance": _action_get_provenance,
}

# ═══════════════════════════════════════════════════════════════════════════
# TOOL 3 — Goals (first-class shared primitive above Branches)
# ═══════════════════════════════════════════════════════════════════════════
# Phase 5 per docs/specs/community_branches_phase5.md. A Goal is the
# intent a Branch serves — "produce a research paper", "plan a
# wedding". Many Branches bind to one Goal. 8 actions: propose,
# update, bind, list, get, search, leaderboard, common_nodes.
# Storage in workflow/author_server.py.


def _current_actor_or_anon() -> str:
    """Wrapper around the existing ``_current_actor`` for clarity in
    the Goals surface. Identical behavior."""
    from workflow.api.engine_helpers import _current_actor

    return _current_actor()


def _format_goal_catalog_line(g: dict[str, Any]) -> str:
    tags = g.get("tags") or []
    tag_suffix = f" [{', '.join(tags[:3])}]" if tags else ""
    desc = (g.get("description") or "").strip().split("\n", 1)[0]
    if len(desc) > 100:
        desc = desc[:100].rstrip() + "…"
    name = g.get("name") or "(unnamed)"
    return (
        f"- `{g['goal_id']}` · **{name}** · {g.get('author')}"
        f"{tag_suffix}" + (f" · {desc}" if desc else "")
    )


def _action_goal_propose(kwargs: dict[str, Any]) -> str:
    from workflow.api.branches import (
        _ensure_workflow_db,
        _split_csv,
    )
    from workflow.api.engine_helpers import (
        _current_actor,
        _format_commit_failed,
        _storage_backend,
    )
    from workflow.identity import git_author

    name = (kwargs.get("name") or "").strip()
    if not name:
        return json.dumps({
            "status": "rejected",
            "error": "name is required for propose.",
        })
    _ensure_workflow_db()
    tags = _split_csv(kwargs.get("tags", ""))
    visibility = (kwargs.get("visibility") or "public").strip().lower()
    if visibility not in {"public", "private"}:
        return json.dumps({
            "status": "rejected",
            "error": (
                "visibility must be 'public' or 'private' at propose "
                "time. Use the `delete_goal` action to soft-delete."
            ),
        })
    goal_dict = {
        "name": name,
        "description": kwargs.get("description", ""),
        "author": _current_actor_or_anon(),
        "tags": tags,
        "visibility": visibility,
    }
    try:
        saved, _commit = _storage_backend().save_goal_and_commit(
            goal_dict,
            author=git_author(_current_actor()),
            message=f"goals.propose: {name}",
            force=bool(kwargs.get("force", False)),
        )
    except CommitFailedError as exc:
        return json.dumps(_format_commit_failed(exc))
    text = (
        f"**Proposed Goal: {saved['name']}.**\n\n"
        "Bind existing workflows to this Goal with the `goals` action "
        "`bind` (pass the Goal name and workflow name). Search for "
        "related intent with `goals action=search query=...`."
    )
    return json.dumps({
        "text": text,
        "status": "proposed",
        "goal": saved,
    }, default=str)


def _action_goal_update(kwargs: dict[str, Any]) -> str:
    from workflow.api.branches import (
        _ensure_workflow_db,
        _split_csv,
    )
    from workflow.api.engine_helpers import (
        _current_actor,
        _format_commit_failed,
        _storage_backend,
    )
    from workflow.daemon_server import get_goal
    from workflow.daemon_server import update_goal as _update
    from workflow.identity import git_author

    gid = (kwargs.get("goal_id") or "").strip()
    if not gid:
        return json.dumps({
            "status": "rejected",
            "error": "goal_id is required.",
        })
    _ensure_workflow_db()
    try:
        current = get_goal(_base_path(), goal_id=gid)
    except KeyError:
        return json.dumps({
            "status": "rejected",
            "error": f"Goal '{gid}' not found.",
        })

    # Soft ownership: author-only for update. Host is ambient so future
    # host-admin override can be bolted on without schema change.
    actor = _current_actor_or_anon()
    if current["author"] != actor and actor != "host":
        return json.dumps({
            "status": "rejected",
            "error": (
                f"Goal '{gid}' is owned by '{current['author']}'. "
                "Only the author can update it (Phase 5 default). "
                "Propose a new Goal to capture your variant."
            ),
        })

    updates: dict[str, Any] = {}
    for fld in ("name", "description"):
        if kwargs.get(fld):
            updates[fld] = kwargs[fld]
    if kwargs.get("tags"):
        updates["tags"] = _split_csv(kwargs["tags"])
    if kwargs.get("visibility"):
        vis = (kwargs["visibility"] or "").strip().lower()
        if vis not in {"public", "private", "deleted"}:
            return json.dumps({
                "status": "rejected",
                "error": (
                    "visibility must be 'public', 'private', or "
                    "'deleted'."
                ),
            })
        updates["visibility"] = vis
    if not updates:
        return json.dumps({
            "status": "rejected",
            "error": (
                "No fields to update. Pass one or more of name, "
                "description, tags, visibility."
            ),
        })

    # Apply the SQLite update (owns column-level merging + validation).
    # Then route the resulting full goal dict through the cached backend
    # so the YAML mirror refreshes + single commit lands.
    updated = _update(_base_path(), goal_id=gid, updates=updates)
    try:
        saved, _commit = _storage_backend().save_goal_and_commit(
            updated,
            author=git_author(_current_actor()),
            message=f"goals.update: {gid}",
            force=bool(kwargs.get("force", False)),
        )
    except CommitFailedError as exc:
        return json.dumps(_format_commit_failed(exc))
    changed = sorted(updates.keys())
    text = (
        f"**Updated Goal '{saved['name']}'.** Fields changed: "
        f"{', '.join(changed)}."
    )
    return json.dumps({
        "text": text,
        "status": "updated",
        "changed_fields": changed,
        "goal": saved,
    }, default=str)


def _action_goal_bind(kwargs: dict[str, Any]) -> str:
    from workflow.api.branches import _ensure_workflow_db
    from workflow.api.engine_helpers import (
        _current_actor,
        _format_commit_failed,
        _storage_backend,
    )
    from workflow.daemon_server import (
        get_branch_definition,
        get_goal,
        update_branch_definition,
    )

    bid = (kwargs.get("branch_def_id") or "").strip()
    gid = (kwargs.get("goal_id") or "").strip()
    if not bid:
        return json.dumps({
            "status": "rejected",
            "error": "branch_def_id is required.",
        })
    _ensure_workflow_db()
    try:
        branch = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({
            "status": "rejected",
            "error": f"Branch '{bid}' not found.",
        })

    if gid:
        try:
            goal = get_goal(_base_path(), goal_id=gid)
        except KeyError:
            return json.dumps({
                "status": "rejected",
                "error": f"Goal '{gid}' not found.",
            })
        if goal.get("visibility") == "deleted":
            return json.dumps({
                "status": "rejected",
                "error": (
                    f"Goal '{gid}' is soft-deleted. Propose a new Goal "
                    "or re-open the deleted one first."
                ),
            })
    else:
        goal = None

    from workflow.branches import BranchDefinition
    from workflow.identity import git_author

    update_branch_definition(
        _base_path(), branch_def_id=bid,
        updates={"goal_id": gid or None},
    )
    # Re-read post-update and route through cached backend so the YAML
    # mirror + single commit capture the cross-table edit. Commit targets
    # the branch path only (goal row isn't mutated by bind).
    updated_branch = get_branch_definition(_base_path(), branch_def_id=bid)
    branch_obj = BranchDefinition.from_dict(updated_branch)
    if gid and goal is not None:
        commit_msg = f"goals.bind: {branch['name']} → {goal['name']}"
    else:
        commit_msg = f"goals.bind: {branch['name']} ∅ (unbind)"
    try:
        _storage_backend().save_branch_and_commit(
            branch_obj,
            author=git_author(_current_actor()),
            message=commit_msg,
            force=bool(kwargs.get("force", False)),
        )
    except CommitFailedError as exc:
        return json.dumps(_format_commit_failed(exc))
    if gid:
        text = (
            f"**Bound** workflow '{branch['name']}' to "
            f"Goal '{goal['name']}'. Inspect the Goal with "
            "`goals action=get` (Goal name or id in structuredContent)."
        )
        status = "bound"
    else:
        text = (
            f"**Unbound** workflow '{branch['name']}' from its "
            "previous Goal."
        )
        status = "unbound"
    return json.dumps({
        "text": text,
        "status": status,
        "branch_def_id": bid,
        "goal_id": gid or None,
    }, default=str)


def _action_goal_list(kwargs: dict[str, Any]) -> str:
    from workflow.api.branches import (
        _ensure_workflow_db,
        _split_csv,
    )
    from workflow.daemon_server import list_goals

    _ensure_workflow_db()
    rows = list_goals(
        _base_path(),
        author=kwargs.get("author", ""),
        tag=(_split_csv(kwargs.get("tags", ""))[:1] or [""])[0],
        limit=int(kwargs.get("limit", 50) or 50),
    )
    if rows:
        lines = [f"**{len(rows)} Goal(s):**", ""]
        for g in rows[:12]:
            lines.append(_format_goal_catalog_line(g))
        if len(rows) > 12:
            lines.append(
                f"- … and {len(rows) - 12} more. Narrow with "
                "`tags=...` or `author=...`."
            )
        text = "\n".join(lines)
    else:
        text = "No Goals match the filter yet. Propose one with `goals action=propose name=...`."
    return json.dumps({
        "text": text,
        "goals": rows,
        "count": len(rows),
    }, default=str)


def _action_goal_get(kwargs: dict[str, Any]) -> str:
    from workflow.api.branches import _ensure_workflow_db
    from workflow.api.engine_helpers import (
        _current_actor,
    )
    from workflow.api.market import _gates_enabled
    from workflow.daemon_server import (
        branches_for_goal,
        get_goal,
        goal_gate_summary,
    )

    gid = (kwargs.get("goal_id") or "").strip()
    if not gid:
        return json.dumps({
            "status": "rejected",
            "error": "goal_id is required.",
        })
    _ensure_workflow_db()
    try:
        goal = get_goal(_base_path(), goal_id=gid)
    except KeyError:
        return json.dumps({
            "status": "rejected",
            "error": f"Goal '{gid}' not found.",
        })

    # Phase 6.2.2 — viewer-aware. Private Branches owned by other
    # actors are excluded from this Goal's published Branch list.
    branches = branches_for_goal(
        _base_path(), goal_id=gid, viewer=_current_actor(),
    )
    is_deleted = goal.get("visibility") == "deleted"

    # Phase 6.4: gate_summary rides alongside branches/is_deleted.
    # When GATES_ENABLED=0, return a flag-gated placeholder so the
    # UI can render "gates off" without mistaking it for "no claims".
    if _gates_enabled():
        gate_summary = goal_gate_summary(_base_path(), goal_id=gid)
    else:
        gate_summary = {"status": "gates_disabled"}

    lines = [
        f"**Goal: {goal['name']}**",
        f"Author: {goal['author']}   Visibility: {goal['visibility']}",
    ]
    if goal.get("tags"):
        lines.append(f"Tags: {', '.join(goal['tags'])}")
    if goal.get("description"):
        lines.append("")
        lines.append(goal["description"])
    lines.append("")
    if branches:
        lines.append(
            f"**{len(branches)} Branch(es)** bound to this Goal:"
        )
        lines.append("")
        for b in branches[:12]:
            lines.append(
                f"- `{b['branch_def_id']}` · **{b['name']}** · "
                f"{b['author']} · v{b.get('version', 1)}"
            )
        if len(branches) > 12:
            lines.append(
                f"- … and {len(branches) - 12} more. Filter with "
                f"`extensions action=list_branches goal_id={gid}`."
            )
    else:
        lines.append(
            "_No Branches yet. Bind an existing Branch with "
            f"`goals action=bind branch_def_id=... goal_id={gid}`._"
        )
    if is_deleted:
        lines.append("")
        lines.append(
            "_Note: this Goal is soft-deleted. Existing binds remain "
            "resolvable but new binds are rejected._"
        )

    return json.dumps({
        "text": "\n".join(lines),
        "goal": goal,
        "is_deleted": is_deleted,
        "branches": branches,
        "branch_count": len(branches),
        "gate_summary": gate_summary,
    }, default=str)


def _action_goal_search(kwargs: dict[str, Any]) -> str:
    from workflow.api.branches import _ensure_workflow_db
    from workflow.daemon_server import search_goals

    query = (kwargs.get("query") or "").strip()
    if not query:
        return json.dumps({
            "status": "rejected",
            "error": "query is required for search.",
        })
    _ensure_workflow_db()
    rows = search_goals(
        _base_path(), query=query,
        limit=int(kwargs.get("limit", 20) or 20),
    )
    if rows:
        lines = [f"**{len(rows)} match(es) for `{query}`:**", ""]
        for g in rows[:12]:
            lines.append(_format_goal_catalog_line(g))
        if len(rows) > 12:
            lines.append(
                f"- … and {len(rows) - 12} more. Tighten the query."
            )
        text = "\n".join(lines)
    else:
        text = (
            f"No Goals match `{query}`. Propose a new Goal if the "
            "intent doesn't already exist."
        )
    return json.dumps({
        "text": text,
        "query": query,
        "goals": rows,
        "count": len(rows),
    }, default=str)


_V1_LEADERBOARD_METRICS = ("run_count", "forks", "outcome")
_GATE_EVENT_LEADERBOARD_METRICS = ("gate_events",)
_ALL_LEADERBOARD_METRICS = _V1_LEADERBOARD_METRICS + _GATE_EVENT_LEADERBOARD_METRICS


def _action_goal_leaderboard(kwargs: dict[str, Any]) -> str:
    from workflow.api.branches import _ensure_workflow_db
    from workflow.api.engine_helpers import (
        _current_actor,
    )
    from workflow.api.market import _gates_enabled
    from workflow.daemon_server import (
        get_goal,
        goal_leaderboard,
    )

    gid = (kwargs.get("goal_id") or "").strip()
    if not gid:
        return json.dumps({
            "status": "rejected",
            "error": "goal_id is required.",
        })
    metric = (kwargs.get("metric") or "run_count").strip().lower()
    _ensure_workflow_db()
    try:
        goal = get_goal(_base_path(), goal_id=gid)
    except KeyError:
        return json.dumps({
            "status": "rejected",
            "error": f"Goal '{gid}' not found.",
        })

    if metric not in _ALL_LEADERBOARD_METRICS:
        return json.dumps({
            "status": "rejected",
            "error": f"Unknown metric '{metric}'.",
            "available_metrics": list(_ALL_LEADERBOARD_METRICS),
        })

    # gate_events metric: rank by attributed real-world gate events.
    if metric == "gate_events":
        from workflow.gate_events import leaderboard_by_gate_events
        window = (kwargs.get("window") or "all").strip().lower()
        limit = int(kwargs.get("limit", 20) or 20)
        try:
            lb = leaderboard_by_gate_events(
                _base_path(), goal_id=gid, window=window, limit=limit,
            )
        except ValueError as exc:
            return json.dumps({"status": "rejected", "error": str(exc)})
        lines = [
            f"**Gate-event leaderboard for Goal '{goal.get('name', gid)}'**"
            f" — window `{window}`",
            "",
        ]
        if lb["ranked"]:
            for rank, entry in enumerate(lb["ranked"], 1):
                lines.append(
                    f"{rank}. `{entry['branch_version_id']}` · "
                    f"gate events: {entry['gate_event_count']} "
                    f"({entry['verified_event_count']} verified) · "
                    f"score: {entry['score']:.1f} · "
                    f"latest: {entry['most_recent_event_date']}"
                )
        else:
            lines.append("_No gate events attributed to any workflow under this Goal._")
        return json.dumps({
            "text": "\n".join(lines),
            "goal_id": gid,
            "metric": metric,
            "window": lb["window"],
            "ranked": lb["ranked"],
            "total_events_in_window": lb["total_events_in_window"],
        }, default=str)

    # GATES_ENABLED gates the outcome metric. When the flag is off,
    # return a friendly flag-gated envelope rather than letting the
    # live leaderboard path run against an empty ladder (which would
    # confuse the UI into thinking the Goal simply has no claims).
    # Flag flips in 6.3 per spec.
    if metric == "outcome" and not _gates_enabled():
        return json.dumps({
            "text": (
                "**Leaderboard metric `outcome`** is gated by the "
                "`GATES_ENABLED` flag (Phase 6.2). Set "
                "`GATES_ENABLED=1` on the Workflow Server to opt in, "
                "or use `metric=run_count` / `metric=forks` today."
            ),
            "status": "gates_disabled",
            "goal_id": gid,
            "metric": metric,
            "entries": [],
        }, default=str)

    try:
        entries = goal_leaderboard(
            _base_path(), goal_id=gid, metric=metric,
            limit=int(kwargs.get("limit", 20) or 20),
            viewer=_current_actor(),
        )
    except ValueError as exc:
        return json.dumps({
            "status": "rejected",
            "error": str(exc),
            "available_metrics": list(_ALL_LEADERBOARD_METRICS),
        })

    lines = [
        f"**Leaderboard for Goal '{goal['name']}'**"
        f" — metric `{metric}`",
        "",
    ]
    if entries:
        for rank, entry in enumerate(entries, 1):
            value = entry.get("value", 0)
            if metric == "outcome":
                name = entry.get("branch_name") or entry.get("name", "")
                rung = entry.get("highest_rung_key", "")
                lines.append(
                    f"{rank}. **{name}** · rung `{rung}` "
                    f"(index {value}) · {entry.get('claimed_at', '')}"
                )
            else:
                lines.append(
                    f"{rank}. **{entry['name']}** · {entry['author']} · "
                    f"{metric}={value}"
                )
    elif metric == "outcome":
        lines.append(
            "_No gate claims yet. Define a ladder with "
            "`gates action=define_ladder` and have Branches submit "
            "`gates action=claim`._"
        )
    else:
        lines.append(
            "_No workflows bound to this Goal yet. Use "
            "`goals action=bind` with the workflow name and Goal name._"
        )

    return json.dumps({
        "text": "\n".join(lines),
        "goal_id": gid,
        "metric": metric,
        "entries": entries,
    }, default=str)


def _action_goal_common_nodes(kwargs: dict[str, Any]) -> str:
    from workflow.api.branches import _ensure_workflow_db
    from workflow.api.engine_helpers import (
        _current_actor,
    )
    from workflow.daemon_server import (
        get_goal,
        goal_common_nodes,
        goal_common_nodes_all,
    )

    _ensure_workflow_db()
    min_branches = int(kwargs.get("min_branches", 2) or 2)
    limit = int(kwargs.get("limit", 20) or 20)
    scope = (kwargs.get("scope") or "this_goal").strip().lower() or "this_goal"
    if scope not in ("this_goal", "all"):
        return json.dumps({
            "status": "rejected",
            "error": (
                f"scope='{scope}' is unknown. Use 'this_goal' (default) "
                "to limit to one Goal, or 'all' for cross-Goal "
                "aggregation."
            ),
        })

    if scope == "all":
        # Phase 6.2.2 — viewer-aware cross-Goal aggregation; private
        # Branches owned by other actors don't contribute.
        entries = goal_common_nodes_all(
            _base_path(),
            min_branches=min_branches,
            limit=limit,
            viewer=_current_actor(),
        )
        lines = [
            "**Common nodes across ALL Goals** "
            f"appearing in ≥{min_branches} workflows.",
            "",
        ]
        if entries:
            for e in entries[:12]:
                goal_tag = ""
                if e.get("goal_ids"):
                    gl = e["goal_ids"][:3]
                    goal_tag = (
                        f" · goals: {', '.join(gl)}"
                        + (" …" if len(e["goal_ids"]) > 3 else "")
                    )
                lines.append(
                    f"- `{e['node_id']}` · **{e['display_name']}** · "
                    f"used in {e['occurrence_count']} branches"
                    f"{goal_tag}"
                )
            if len(entries) > 12:
                lines.append(f"- … and {len(entries) - 12} more.")
            lines.append("")
            lines.append(
                "_Reuse an existing node via `node_ref={source, "
                "node_id}` in build_branch / add_node (#66)._"
            )
        else:
            lines.append(
                "_No node_ids repeat across Branches yet. Consider "
                "using the same node_id when nodes serve the same "
                "role so the reuse surface can discover them._"
            )
        return json.dumps({
            "text": "\n".join(lines),
            "scope": "all",
            "min_branches": min_branches,
            "entries": entries,
        }, default=str)

    gid = (kwargs.get("goal_id") or "").strip()
    if not gid:
        return json.dumps({
            "status": "rejected",
            "error": (
                "goal_id is required for scope='this_goal'. Pass "
                "scope='all' to skip the Goal filter."
            ),
        })
    try:
        goal = get_goal(_base_path(), goal_id=gid)
    except KeyError:
        return json.dumps({
            "status": "rejected",
            "error": f"Goal '{gid}' not found.",
        })

    # Phase 6.2.2 — viewer-aware aggregation; private Branches
    # owned by other actors don't contribute their node inventory.
    entries = goal_common_nodes(
        _base_path(), goal_id=gid,
        min_branches=min_branches,
        limit=limit,
        viewer=_current_actor(),
    )
    lines = [
        f"**Common nodes in Goal '{goal['name']}'** "
        f"appearing in ≥{min_branches} workflows.",
        "",
    ]
    if entries:
        for e in entries[:12]:
            lines.append(
                f"- `{e['node_id']}` · **{e['display_name']}** · "
                f"used in {e['occurrence_count']} branches "
                f"(first seen: `{e['first_seen_in']}`)"
            )
        if len(entries) > 12:
            lines.append(
                f"- … and {len(entries) - 12} more."
            )
    else:
        lines.append(
            "_No nodes repeated across Branches yet — each Branch "
            "uses its own node_ids. Consider renaming nodes to share "
            "identity when they serve the same role._"
        )
    return json.dumps({
        "text": "\n".join(lines),
        "goal_id": gid,
        "scope": "this_goal",
        "min_branches": min_branches,
        "entries": entries,
    }, default=str)


def _action_goal_set_canonical(kwargs: dict[str, Any]) -> str:
    from workflow.api.branches import _ensure_workflow_db
    from workflow.api.engine_helpers import (
        _current_actor,
    )
    from workflow.daemon_server import get_goal, set_canonical_branch

    gid = (kwargs.get("goal_id") or "").strip()
    if not gid:
        return json.dumps({"status": "rejected", "error": "goal_id is required."})
    branch_version_id = (kwargs.get("branch_version_id") or "").strip() or None
    _ensure_workflow_db()

    try:
        goal = get_goal(_base_path(), goal_id=gid)
    except KeyError:
        return json.dumps({"status": "rejected", "error": f"Goal '{gid}' not found."})

    # Authority: only Goal author or host may set canonical.
    actor = _current_actor()
    host_actor = os.environ.get("UNIVERSE_SERVER_HOST_USER", "host")
    if actor != goal["author"] and actor != host_actor:
        return json.dumps({
            "status": "rejected",
            "error": (
                "Only the Goal author or a host-level actor may set the canonical branch. "
                f"Goal author is '{goal['author']}'; request actor is '{actor}'."
            ),
        })

    try:
        updated = set_canonical_branch(
            _base_path(), goal_id=gid,
            branch_version_id=branch_version_id, set_by=actor,
        )
    except ValueError as exc:
        return json.dumps({"status": "rejected", "error": str(exc)})

    if branch_version_id:
        text = (
            f"Canonical branch for Goal '{goal['name']}' set to "
            f"`{branch_version_id}`. New users forking this Goal will "
            f"start from this version."
        )
    else:
        text = (
            f"Canonical branch for Goal '{goal['name']}' unset. "
            f"No starter branch is currently designated."
        )

    return json.dumps({
        "status": "ok",
        "text": text,
        "goal_id": gid,
        "canonical_branch_version_id": updated.get("canonical_branch_version_id"),
    }, default=str)


_GOAL_ACTIONS: dict[str, Any] = {
    "propose": _action_goal_propose,
    "update": _action_goal_update,
    "bind": _action_goal_bind,
    "list": _action_goal_list,
    "get": _action_goal_get,
    "search": _action_goal_search,
    "leaderboard": _action_goal_leaderboard,
    "common_nodes": _action_goal_common_nodes,
    "set_canonical": _action_goal_set_canonical,
}

# Provider-routing compatibility: ChatGPT can render `/mcp-directory` tool
# names but dispatch them through the legacy `Goals` wrapper.
_GOAL_ACTION_ALIASES: dict[str, str] = {
    "list_workflow_goals": "list",
    "search_workflow_goals": "search",
    "get_workflow_goal": "get",
    "propose_workflow_goal": "propose",
}

_GOAL_WRITE_ACTIONS: frozenset[str] = frozenset({
    "propose", "update", "bind", "set_canonical",
})


def _canonical_goal_action(action: str) -> str:
    return _GOAL_ACTION_ALIASES.get(action, action)


def _available_goal_actions() -> list[str]:
    return sorted(set(_GOAL_ACTIONS.keys()) | set(_GOAL_ACTION_ALIASES.keys()))


def _dispatch_goal_action(
    action: str, handler: Any, kwargs: dict[str, Any],
) -> str:
    """Run a Goal action; ledger write actions for public attribution.

    Catches :class:`DirtyFileError` from cached-backend writes (per H2)
    and formats it as the structured ``local_edit_conflict`` payload so
    chat clients render actionable options rather than a raw traceback.
    """
    from workflow.api.branches import _append_global_ledger
    from workflow.api.engine_helpers import (
        _format_dirty_file_conflict,
        _truncate,
    )

    try:
        result_str = handler(kwargs)
    except DirtyFileError as exc:
        return json.dumps(_format_dirty_file_conflict(exc))
    if action not in _GOAL_WRITE_ACTIONS:
        return result_str
    try:
        result = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        return result_str
    if not isinstance(result, dict):
        return result_str
    if result.get("error") or result.get("status") == "rejected":
        return result_str
    try:
        target = (
            result.get("goal", {}).get("goal_id")
            or result.get("goal_id")
            or kwargs.get("goal_id", "")
            or kwargs.get("branch_def_id", "")
        )
        summary_bits = [f"goals.{action}"]
        if kwargs.get("name"):
            summary_bits.append(kwargs["name"])
        if kwargs.get("goal_id"):
            summary_bits.append(f"goal={kwargs['goal_id']}")
        if kwargs.get("branch_def_id"):
            summary_bits.append(f"branch={kwargs['branch_def_id']}")
        _append_global_ledger(
            f"goals.{action}",
            target=str(target),
            summary=_truncate(" ".join(summary_bits)),
            payload=None,
        )
    except Exception as exc:
        logger.warning("Ledger write failed for goals.%s: %s", action, exc)
    return result_str


def goals(
    action: str,
    goal_id: str = "",
    branch_def_id: str = "",
    branch_version_id: str = "",
    name: str = "",
    description: str = "",
    tags: str = "",
    visibility: str = "",
    query: str = "",
    metric: str = "",
    min_branches: int = 2,
    author: str = "",
    limit: int = 50,
    scope: str = "",
    force: bool = False,
) -> str:
    """Goals — first-class shared primitives above workflow Branches.

    A Goal captures the intent a workflow serves ("produce a research
    paper", "plan a wedding"). Many Branches bind to one Goal. Users
    discover existing Goals before building a new Branch so the
    "reuse vs invent" decision is tractable.

    Actions:
      propose      Create a new Goal. Needs `name`. Optional
                   description, tags (CSV), visibility (public/private).
      update       Patch a Goal you own. Fields: name, description,
                   tags, visibility. Non-owners cannot update — propose
                   a new Goal instead.
      bind         Attach a Branch to a Goal. Pass goal_id="" to
                   unbind. Needs branch_def_id.
      set_canonical Mark a branch_version_id as the Goal's canonical
                   (best-known) branch. Author-only or host-only.
                   Pass branch_version_id="" to unset.
      list         Browse Goals. Optional author, tags (CSV first
                   value only), limit. Soft-deleted Goals hidden.
      get          Full Goal view + bound Branches. Needs goal_id.
      search       LIKE-based substring search over name, description,
                   tags. Needs query.
      leaderboard  Rank bound Branches by metric. v1 supports
                   `run_count` and `forks`. `outcome` returns a Phase 6
                   stub today; the same call will surface real outcome
                   rankings once Phase 6 ships.
      common_nodes Nodes appearing in ≥`min_branches` Branches.
                   With `scope="this_goal"` (default), restricts to
                   one Goal's Branches. With `scope="all"`, aggregates
                   across every Goal and every unbound Branch — use
                   this when helping a user decide "is there already
                   a node that does X somewhere on this server?" even
                   if they haven't committed to a Goal yet.

    Args:
      action: see above.
      goal_id: Goal target for bind/get/update/search/leaderboard,
        and for common_nodes when scope='this_goal'.
      branch_def_id: Branch target for bind.
      branch_version_id: Published branch_version_id for set_canonical
        (pass empty string to unset). Must reference a row in
        `branch_versions` — only published versions may be canonical.
      name/description/tags/visibility: Goal fields for propose/update.
      query: search query.
      metric: leaderboard metric (run_count/forks/outcome).
      min_branches: common_nodes cutoff (default 2).
      scope: common_nodes aggregation. 'this_goal' (default) restricts
        to one Goal; 'all' aggregates cross-Goal.
      author: list filter.
      limit: cap on returned rows.
      force: override `local_edit_conflict` refusal on propose/update/bind
        when the target YAML has uncommitted local edits. Default False —
        the conflict surfaces as a structured response so the caller can
        commit / stash / discard first.
    """
    from workflow.api.branches import _ensure_workflow_db

    _ensure_workflow_db()
    goal_kwargs: dict[str, Any] = {
        "goal_id": goal_id,
        "branch_def_id": branch_def_id,
        "branch_version_id": branch_version_id,
        "name": name,
        "description": description,
        "tags": tags,
        "visibility": visibility,
        "query": query,
        "metric": metric,
        "min_branches": min_branches,
        "author": author,
        "limit": limit,
        "scope": scope,
        "force": force,
    }
    canonical_action = _canonical_goal_action(action)
    handler = _GOAL_ACTIONS.get(canonical_action)
    if handler is None:
        return json.dumps({
            "error": f"Unknown action '{action}'.",
            "available_actions": _available_goal_actions(),
        })
    return _dispatch_goal_action(canonical_action, handler, goal_kwargs)

# ═══════════════════════════════════════════════════════════════════════════
# TOOL 3b — Outcome Gates (Phase 6.1)
# ═══════════════════════════════════════════════════════════════════════════
#
# Flag-gated by GATES_ENABLED=1. Phase 6.1 ships schema + three actions
# (define_ladder / get_ladder / claim) write-through SQLite only. Git
# commit integration + remaining actions (retract / list_claims /
# leaderboard) ship in 6.2 / 6.3.


def _gates_enabled() -> bool:
    import os
    return os.environ.get("GATES_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _validate_evidence_url(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url or "")
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return ""
    return (
        "evidence_url must be an http(s) URL with a host "
        "(e.g. https://example.com/path)."
    )


def _action_gates_define_ladder(kwargs: dict[str, Any]) -> str:
    from workflow.api.branches import _ensure_workflow_db
    from workflow.api.engine_helpers import (
        _current_actor,
        _format_commit_failed,
        _storage_backend,
    )
    from workflow.catalog.layout import slugify
    from workflow.daemon_server import get_goal
    from workflow.identity import git_author

    gid = (kwargs.get("goal_id") or "").strip()
    if not gid:
        return json.dumps({
            "status": "rejected",
            "error": "goal_id is required for define_ladder.",
        })
    ladder_raw = (kwargs.get("ladder") or "").strip()
    if not ladder_raw:
        return json.dumps({
            "status": "rejected",
            "error": "ladder JSON is required for define_ladder.",
        })
    try:
        ladder = json.loads(ladder_raw)
    except json.JSONDecodeError as exc:
        return json.dumps({
            "status": "rejected",
            "error": f"ladder must be a JSON list. {exc}",
        })
    if not isinstance(ladder, list):
        return json.dumps({
            "status": "rejected",
            "error": "ladder must be a JSON list of rung objects.",
        })
    seen: set[str] = set()
    for idx, rung in enumerate(ladder):
        if not isinstance(rung, dict):
            return json.dumps({
                "status": "rejected",
                "error": f"ladder[{idx}] must be an object.",
            })
        key = (rung.get("rung_key") or "").strip()
        if not key:
            return json.dumps({
                "status": "rejected",
                "error": f"ladder[{idx}].rung_key is required.",
            })
        if key in seen:
            return json.dumps({
                "status": "rejected",
                "error": f"duplicate rung_key '{key}' in ladder.",
            })
        seen.add(key)
    _ensure_workflow_db()
    try:
        goal = get_goal(_base_path(), goal_id=gid)
    except KeyError:
        return json.dumps({
            "status": "rejected",
            "error": f"Goal '{gid}' not found.",
        })
    actor = _current_actor_or_anon()
    if goal.get("author") and goal["author"] != actor and actor != "host":
        return json.dumps({
            "status": "rejected",
            "error": (
                "Only the Goal author can define its ladder. "
                f"Owner: {goal['author']}."
            ),
        })
    # Ride the ladder through `save_goal_and_commit` — spec §Migration
    # 5: ladder is a dict key on the goal, no backend protocol change
    # beyond the existing save_goal_and_commit. Commit namespace is
    # `goals.define_ladder` because the file written is
    # `goals/<slug>.yaml`, not `gates/...`.
    updated_goal = dict(goal)
    updated_goal["gate_ladder"] = ladder
    force = bool(kwargs.get("force", False))
    goal_slug = slugify(goal.get("name") or gid)
    try:
        saved, _commit = _storage_backend().save_goal_and_commit(
            updated_goal,
            author=git_author(_current_actor()),
            message=f"goals.define_ladder: {goal_slug}",
            force=force,
        )
    except CommitFailedError as exc:
        return json.dumps(_format_commit_failed(exc))
    return json.dumps({
        "status": "defined",
        "goal_id": gid,
        "gate_ladder": saved.get("gate_ladder", []),
    }, default=str)


def _action_gates_get_ladder(kwargs: dict[str, Any]) -> str:
    from workflow.api.branches import _ensure_workflow_db
    from workflow.daemon_server import get_goal_ladder

    gid = (kwargs.get("goal_id") or "").strip()
    if not gid:
        return json.dumps({
            "status": "rejected",
            "error": "goal_id is required for get_ladder.",
        })
    _ensure_workflow_db()
    try:
        ladder = get_goal_ladder(_base_path(), goal_id=gid)
    except KeyError:
        return json.dumps({
            "status": "rejected",
            "error": f"Goal '{gid}' not found.",
        })
    return json.dumps({
        "status": "ok",
        "goal_id": gid,
        "gate_ladder": ladder,
    }, default=str)


def _action_gates_claim(kwargs: dict[str, Any]) -> str:
    from workflow.api.branches import _ensure_workflow_db
    from workflow.api.engine_helpers import (
        _current_actor,
        _format_commit_failed,
        _storage_backend,
    )
    from workflow.catalog.layout import slugify
    from workflow.daemon_server import (
        get_branch_definition,
        get_gate_claim,
        get_goal,
        get_goal_ladder,
    )
    from workflow.identity import git_author

    bid = (kwargs.get("branch_def_id") or "").strip()
    rung_key = (kwargs.get("rung_key") or "").strip()
    evidence_url = (kwargs.get("evidence_url") or "").strip()
    force = bool(kwargs.get("force", False))
    if not (bid and rung_key and evidence_url):
        return json.dumps({
            "status": "rejected",
            "error": (
                "branch_def_id, rung_key, evidence_url are required."
            ),
        })
    url_err = _validate_evidence_url(evidence_url)
    if url_err:
        return json.dumps({"status": "rejected", "error": url_err})
    _ensure_workflow_db()
    try:
        branch = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({
            "status": "rejected",
            "error": f"Branch '{bid}' not found.",
        })
    goal_id = branch.get("goal_id") or ""
    if not goal_id:
        return json.dumps({
            "status": "rejected",
            "error": (
                "Branch is not bound to a Goal. "
                "Bind it via `goals action=bind` before claiming."
            ),
        })
    try:
        goal = get_goal(_base_path(), goal_id=goal_id)
    except KeyError:
        return json.dumps({
            "status": "rejected",
            "error": f"Goal '{goal_id}' not found.",
        })
    # Rebind guard: if an ACTIVE (non-retracted) claim exists for
    # (branch, rung) under a different Goal, the Branch was rebound
    # between claims. Reject so the original Goal's leaderboard keeps
    # its history; caller must retract the stale claim before
    # re-claiming under the new Goal. Retracted prior claims are
    # resolved intent — re-claim reactivates under the new Goal.
    existing = get_gate_claim(
        _base_path(), branch_def_id=bid, rung_key=rung_key,
    )
    if (
        existing is not None
        and not existing.get("retracted_at")
        and (existing.get("goal_id") or "") != goal_id
    ):
        return json.dumps({
            "status": "rejected",
            "error": "branch_rebound",
            "original_goal_id": existing.get("goal_id") or "",
            "current_goal_id": goal_id,
            "hint": (
                "Retract the existing claim under the original Goal "
                "first, then re-claim under the new Goal."
            ),
        })
    ladder = get_goal_ladder(_base_path(), goal_id=goal_id)
    available = [r.get("rung_key") for r in ladder if r.get("rung_key")]
    if rung_key not in available:
        return json.dumps({
            "status": "rejected",
            "error": "unknown_rung",
            "available_rungs": available,
        })
    from workflow.daemon_server import BranchRebindError

    goal_slug = slugify(goal.get("name") or goal_id)
    branch_slug = slugify(branch.get("name") or bid)
    try:
        saved, _commit = _storage_backend().save_gate_claim_and_commit(
            branch_def_id=bid,
            goal_id=goal_id,
            rung_key=rung_key,
            evidence_url=evidence_url,
            evidence_note=kwargs.get("evidence_note", ""),
            claimed_by=_current_actor_or_anon(),
            goal_slug=goal_slug,
            branch_slug=branch_slug,
            author=git_author(_current_actor()),
            message=f"gates.claim: {goal_slug}/{branch_slug}@{rung_key}",
            force=force,
        )
    except BranchRebindError as exc:
        # Storage-layer guard fired — means another caller rebound the
        # Branch between this handler's pre-check and the storage
        # write. Surface the same envelope as the handler pre-check.
        return json.dumps({
            "status": "rejected",
            "error": "branch_rebound",
            "original_goal_id": exc.original_goal_id,
            "current_goal_id": exc.current_goal_id,
            "hint": (
                "Retract the existing claim under the original Goal "
                "first, then re-claim under the new Goal."
            ),
        })
    except CommitFailedError as exc:
        return json.dumps(_format_commit_failed(exc))
    return json.dumps({
        "status": "claimed",
        "claim": saved,
    }, default=str)


def _action_gates_retract(kwargs: dict[str, Any]) -> str:
    from workflow.api.branches import _ensure_workflow_db
    from workflow.api.engine_helpers import (
        _current_actor,
        _format_commit_failed,
        _storage_backend,
    )
    from workflow.catalog.layout import slugify
    from workflow.daemon_server import (
        get_branch_definition,
        get_gate_claim,
        get_goal,
    )
    from workflow.identity import git_author

    bid = (kwargs.get("branch_def_id") or "").strip()
    rung_key = (kwargs.get("rung_key") or "").strip()
    reason = (kwargs.get("reason") or "").strip()
    force = bool(kwargs.get("force", False))
    if not (bid and rung_key):
        return json.dumps({
            "status": "rejected",
            "error": "branch_def_id and rung_key are required for retract.",
        })
    if not reason:
        return json.dumps({
            "status": "rejected",
            "error": "reason is required for retract (non-empty).",
        })
    _ensure_workflow_db()
    existing = get_gate_claim(
        _base_path(), branch_def_id=bid, rung_key=rung_key,
    )
    if existing is None:
        return json.dumps({
            "status": "rejected",
            "error": "claim_not_found",
            "message": (
                f"No claim exists for branch '{bid}' at rung "
                f"'{rung_key}'."
            ),
        })
    if existing.get("retracted_at"):
        # Idempotent: a second retract on an already-retracted claim is
        # a no-op return, not a fresh write. Keeps owners from churning
        # retracted_at timestamps. No YAML rewrite either.
        return json.dumps({
            "status": "already_retracted",
            "claim": existing,
        }, default=str)
    actor = _current_actor_or_anon()
    # Owner-retract: original claimant, Goal author, or ambient host.
    claimed_by = existing.get("claimed_by") or ""
    goal_author = ""
    goal_id = existing.get("goal_id") or ""
    goal_name = ""
    if goal_id:
        try:
            goal = get_goal(_base_path(), goal_id=goal_id)
            goal_author = goal.get("author") or ""
            goal_name = goal.get("name") or ""
        except KeyError:
            pass
    allowed = {actor_id for actor_id in (claimed_by, goal_author) if actor_id}
    if actor not in allowed and actor != "host":
        return json.dumps({
            "status": "rejected",
            "error": (
                "Only the claim author or Goal owner can retract "
                f"(claimant: '{claimed_by}', goal owner: "
                f"'{goal_author}')."
            ),
        })
    # Verify branch still exists (defensive; claim-time check is in claim).
    try:
        branch = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({
            "status": "rejected",
            "error": f"Branch '{bid}' not found.",
        })
    goal_slug = slugify(goal_name or goal_id)
    branch_slug = slugify(branch.get("name") or bid)
    try:
        saved, _commit = _storage_backend().retract_gate_claim_and_commit(
            branch_def_id=bid,
            rung_key=rung_key,
            reason=reason,
            goal_slug=goal_slug,
            branch_slug=branch_slug,
            author=git_author(_current_actor()),
            message=f"gates.retract: {goal_slug}/{branch_slug}@{rung_key}",
            force=force,
        )
    except CommitFailedError as exc:
        return json.dumps(_format_commit_failed(exc))
    return json.dumps({
        "status": "retracted",
        "claim": saved,
    }, default=str)


_LIST_CLAIMS_LIMIT_CAP = 500


def _action_gates_list_claims(kwargs: dict[str, Any]) -> str:
    from workflow.api.branches import _ensure_workflow_db
    from workflow.api.engine_helpers import (
        _current_actor,
        _filter_claims_by_branch_visibility,
    )
    from workflow.daemon_server import get_goal, list_gate_claims

    bid = (kwargs.get("branch_def_id") or "").strip()
    gid = (kwargs.get("goal_id") or "").strip()
    if bool(bid) == bool(gid):
        return json.dumps({
            "status": "rejected",
            "error": (
                "list_claims requires exactly one of branch_def_id "
                "or goal_id."
            ),
            "available_filters": ["branch_def_id", "goal_id"],
        })
    include_retracted = bool(kwargs.get("include_retracted", False))
    limit = int(kwargs.get("limit", 50) or 50)
    limit = max(1, min(limit, _LIST_CLAIMS_LIMIT_CAP))
    _ensure_workflow_db()
    # Unknown goal_id is a hard reject (caller asked about a specific
    # ID). Unknown branch_def_id falls through to an empty result set,
    # matching `branch list` ergonomics.
    if gid:
        try:
            get_goal(_base_path(), goal_id=gid)
        except KeyError:
            return json.dumps({
                "status": "rejected",
                "error": f"Goal '{gid}' not found.",
            })
    try:
        claims = list_gate_claims(
            _base_path(),
            branch_def_id=bid,
            goal_id=gid,
            include_retracted=include_retracted,
            limit=limit,
        )
    except ValueError as exc:
        return json.dumps({"status": "rejected", "error": str(exc)})
    # Phase 6.2.2 — hide private-Branch claims from non-owners.
    claims = _filter_claims_by_branch_visibility(
        claims, viewer=_current_actor(),
    )
    return json.dumps({
        "status": "ok",
        "filter": {
            "branch_def_id": bid,
            "goal_id": gid,
            "include_retracted": include_retracted,
        },
        "claims": claims,
        "count": len(claims),
    }, default=str)


def _action_gates_leaderboard(kwargs: dict[str, Any]) -> str:
    from workflow.api.branches import _ensure_workflow_db
    from workflow.api.engine_helpers import (
        _current_actor,
        _filter_leaderboard_by_branch_visibility,
    )
    from workflow.daemon_server import (
        gates_leaderboard,
        get_goal,
        get_goal_ladder,
    )

    gid = (kwargs.get("goal_id") or "").strip()
    if not gid:
        return json.dumps({
            "status": "rejected",
            "error": "goal_id is required for leaderboard.",
        })
    _ensure_workflow_db()
    try:
        goal = get_goal(_base_path(), goal_id=gid)
    except KeyError:
        return json.dumps({
            "status": "rejected",
            "error": f"Goal '{gid}' not found.",
        })
    ladder = get_goal_ladder(_base_path(), goal_id=gid)
    if not ladder:
        return json.dumps({
            "status": "ok",
            "goal_id": gid,
            "goal_name": goal.get("name", ""),
            "entries": [],
            "count": 0,
            "note": "Goal has no ladder defined.",
        }, default=str)
    limit = int(kwargs.get("limit", 50) or 50)
    entries = gates_leaderboard(_base_path(), goal_id=gid, limit=limit)
    # Phase 6.2.2 — hide private-Branch entries from non-owners.
    entries = _filter_leaderboard_by_branch_visibility(
        entries, viewer=_current_actor(),
    )
    return json.dumps({
        "status": "ok",
        "goal_id": gid,
        "goal_name": goal.get("name", ""),
        "entries": entries,
        "count": len(entries),
    }, default=str)


def _action_gates_stake_bonus(kwargs: dict[str, Any]) -> str:
    """Lock a bonus stake on an existing gate claim.

    Requires: claim_id, bonus_stake (int), node_id.
    Rejected when WORKFLOW_PAID_MARKET is off, claim is retracted,
    or claim already has a bonus staked.
    """
    from workflow.api.branches import _ensure_workflow_db
    from workflow.gates.actions import stake_bonus, validate_stake_amount
    from workflow.producers.node_bid import paid_market_enabled

    if not paid_market_enabled():
        return json.dumps({
            "status": "not_available",
            "error": (
                "Gate bonuses require WORKFLOW_PAID_MARKET=on. "
                "Enable the paid-market flag to use bonus staking."
            ),
        })

    claim_id = (kwargs.get("claim_id") or "").strip()
    node_id = (kwargs.get("node_id") or "").strip()
    attachment_scope = (kwargs.get("attachment_scope") or "node").strip()
    raw_stake = kwargs.get("bonus_stake", 0)

    if not claim_id:
        return json.dumps({"status": "rejected", "error": "claim_id is required."})
    if not node_id:
        return json.dumps({"status": "rejected", "error": "node_id is required."})

    stake, err = validate_stake_amount(raw_stake)
    if err:
        return json.dumps({"status": "rejected", "error": err})
    if stake == 0:
        return json.dumps({
            "status": "rejected",
            "error": "bonus_stake must be > 0 to stake a bonus.",
        })

    _ensure_workflow_db()
    from workflow.storage import _connect as _storage_connect
    with _storage_connect(_base_path()) as conn:
        result = stake_bonus(
            conn,
            claim_id=claim_id,
            bonus_stake=stake,
            node_id=node_id,
            attachment_scope=attachment_scope,
        )
    return json.dumps(result, default=str)


def _action_gates_unstake_bonus(kwargs: dict[str, Any]) -> str:
    """Remove a bonus stake from a gate claim (refund to original staker).

    Requires: claim_id. Only the original staker can unstake.
    """
    from workflow.api.branches import _ensure_workflow_db
    from workflow.gates.actions import unstake_bonus
    from workflow.producers.node_bid import paid_market_enabled

    if not paid_market_enabled():
        return json.dumps({
            "status": "not_available",
            "error": "Gate bonuses require WORKFLOW_PAID_MARKET=on.",
        })

    claim_id = (kwargs.get("claim_id") or "").strip()
    if not claim_id:
        return json.dumps({"status": "rejected", "error": "claim_id is required."})

    actor = _current_actor_or_anon()
    _ensure_workflow_db()
    from workflow.storage import _connect as _storage_connect
    with _storage_connect(_base_path()) as conn:
        result = unstake_bonus(conn, claim_id=claim_id, actor=actor)
    return json.dumps(result, default=str)


def _action_gates_release_bonus(kwargs: dict[str, Any]) -> str:
    """Release or refund a bonus based on an evaluator verdict.

    Requires: claim_id, eval_verdict ("pass"|"fail"|"skip"),
    node_last_claimer (who gets the payout on pass).
    Rejected when no verdict supplied or bonus_stake is 0.
    """
    from workflow.api.branches import _ensure_workflow_db
    from workflow.gates.actions import release_bonus
    from workflow.producers.node_bid import paid_market_enabled

    if not paid_market_enabled():
        return json.dumps({
            "status": "not_available",
            "error": "Gate bonuses require WORKFLOW_PAID_MARKET=on.",
        })

    claim_id = (kwargs.get("claim_id") or "").strip()
    eval_verdict = (kwargs.get("eval_verdict") or "").strip()
    node_last_claimer = (kwargs.get("node_last_claimer") or "").strip()

    if not claim_id:
        return json.dumps({"status": "rejected", "error": "claim_id is required."})
    if not eval_verdict:
        return json.dumps({
            "status": "rejected",
            "error": (
                "eval_verdict is required ('pass', 'fail', or 'skip'). "
                "Use the Evaluator protocol to obtain a verdict before releasing."
            ),
        })
    if not node_last_claimer:
        return json.dumps({
            "status": "rejected",
            "error": (
                "node_last_claimer is required "
                "(the actor holding the node at gate-pass time)."
            ),
        })

    staker = _current_actor_or_anon()
    _ensure_workflow_db()
    from workflow.storage import _connect as _storage_connect
    with _storage_connect(_base_path()) as conn:
        result = release_bonus(
            conn,
            claim_id=claim_id,
            eval_verdict=eval_verdict,
            node_last_claimer=node_last_claimer,
            staker=staker,
        )
    return json.dumps(result, default=str)


def _action_attest_gate_event(kwargs: dict[str, Any]) -> str:
    from workflow.api.engine_helpers import _current_actor
    from workflow.gate_events import attest_gate_event

    goal_id = (kwargs.get("goal_id") or "").strip()
    event_type = (kwargs.get("event_type") or "").strip()
    event_date = (kwargs.get("event_date") or "").strip()
    attested_by = (kwargs.get("attested_by") or _current_actor()).strip()
    notes = (kwargs.get("note") or "").strip()
    cites_raw = (kwargs.get("cites_json") or "[]").strip()
    try:
        cites = json.loads(cites_raw) if cites_raw else []
        if not isinstance(cites, list):
            return json.dumps({"error": "cites_json must be a JSON array."})
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"cites_json is not valid JSON: {exc}"})
    try:
        evt = attest_gate_event(
            _base_path(),
            goal_id=goal_id,
            event_type=event_type,
            event_date=event_date,
            attested_by=attested_by,
            cites=cites,
            notes=notes,
        )
    except (ValueError, KeyError) as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"status": "attested", "event_id": evt.event_id,
                       "goal_id": evt.goal_id, "event_type": evt.event_type,
                       "event_date": evt.event_date, "attested_by": evt.attested_by,
                       "verification_status": evt.verification_status,
                       "cite_count": len(evt.cites)})


def _action_verify_gate_event(kwargs: dict[str, Any]) -> str:
    from workflow.api.engine_helpers import _current_actor
    from workflow.gate_events import verify_gate_event

    event_id = (kwargs.get("event_id") or "").strip()
    verifier_id = (kwargs.get("verifier_id") or _current_actor()).strip()
    if not event_id:
        return json.dumps({"error": "event_id is required."})
    try:
        evt = verify_gate_event(_base_path(), event_id=event_id, verifier_id=verifier_id)
    except (ValueError, KeyError) as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"status": "verified", "event_id": evt.event_id,
                       "verification_status": evt.verification_status,
                       "verified_by": evt.verified_by})


def _action_dispute_gate_event(kwargs: dict[str, Any]) -> str:
    from workflow.api.engine_helpers import _current_actor
    from workflow.gate_events.store import dispute_gate_event

    event_id = (kwargs.get("event_id") or "").strip()
    disputed_by = (kwargs.get("disputed_by") or _current_actor()).strip()
    reason = (kwargs.get("reason") or "").strip()
    if not event_id:
        return json.dumps({"error": "event_id is required."})
    try:
        evt = dispute_gate_event(_base_path(), event_id=event_id,
                                 disputed_by=disputed_by, reason=reason)
    except (ValueError, KeyError) as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"status": "disputed", "event_id": evt.event_id,
                       "verification_status": evt.verification_status})


def _action_retract_gate_event(kwargs: dict[str, Any]) -> str:
    from workflow.api.engine_helpers import _current_actor
    from workflow.gate_events.store import retract_gate_event

    event_id = (kwargs.get("event_id") or "").strip()
    retracted_by = (kwargs.get("retracted_by") or _current_actor()).strip()
    note = (kwargs.get("note") or "").strip()
    if not event_id:
        return json.dumps({"error": "event_id is required."})
    try:
        evt = retract_gate_event(_base_path(), event_id=event_id,
                                 retracted_by=retracted_by, note=note)
    except (ValueError, KeyError) as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"status": "retracted", "event_id": evt.event_id,
                       "verification_status": evt.verification_status})


def _action_get_gate_event(kwargs: dict[str, Any]) -> str:
    from workflow.gate_events.store import get_gate_event

    event_id = (kwargs.get("event_id") or "").strip()
    if not event_id:
        return json.dumps({"error": "event_id is required."})
    evt = get_gate_event(_base_path(), event_id)
    if evt is None:
        return json.dumps({"error": f"event_id '{event_id}' not found."})
    return json.dumps({
        "event_id": evt.event_id,
        "goal_id": evt.goal_id,
        "event_type": evt.event_type,
        "event_date": evt.event_date,
        "attested_by": evt.attested_by,
        "attested_at": evt.attested_at,
        "verification_status": evt.verification_status,
        "verified_by": evt.verified_by,
        "notes": evt.notes,
        "cites": [
            {"branch_version_id": c.branch_version_id, "run_id": c.run_id,
             "contribution_summary": c.contribution_summary}
            for c in evt.cites
        ],
    }, default=str)


def _action_list_gate_events(kwargs: dict[str, Any]) -> str:
    from workflow.gate_events.store import list_gate_events

    goal_id = (kwargs.get("goal_id") or "").strip()
    bvid = (kwargs.get("branch_version_id") or "").strip()
    limit = min(max(1, int(kwargs.get("limit") or 50)), 500)
    include_retracted = bool(kwargs.get("include_retracted", True))
    events = list_gate_events(
        _base_path(),
        goal_id=goal_id,
        branch_version_id=bvid,
        include_retracted=include_retracted,
        limit=limit,
    )
    return json.dumps({
        "goal_id": goal_id,
        "count": len(events),
        "events": [
            {"event_id": e.event_id, "event_type": e.event_type,
             "event_date": e.event_date, "attested_by": e.attested_by,
             "verification_status": e.verification_status,
             "cite_count": len(e.cites)}
            for e in events
        ],
    }, default=str)


_GATE_EVENT_ACTIONS: dict[str, Any] = {
    "attest_gate_event": _action_attest_gate_event,
    "verify_gate_event": _action_verify_gate_event,
    "dispute_gate_event": _action_dispute_gate_event,
    "retract_gate_event": _action_retract_gate_event,
    "get_gate_event": _action_get_gate_event,
    "list_gate_events": _action_list_gate_events,
}


_GATES_ACTIONS: dict[str, Any] = {
    "define_ladder": _action_gates_define_ladder,
    "get_ladder": _action_gates_get_ladder,
    "claim": _action_gates_claim,
    "retract": _action_gates_retract,
    "list_claims": _action_gates_list_claims,
    "leaderboard": _action_gates_leaderboard,
    "stake_bonus": _action_gates_stake_bonus,
    "unstake_bonus": _action_gates_unstake_bonus,
    "release_bonus": _action_gates_release_bonus,
}


def gates(
    action: str,
    goal_id: str = "",
    branch_def_id: str = "",
    rung_key: str = "",
    ladder: str = "",
    evidence_url: str = "",
    evidence_note: str = "",
    reason: str = "",
    include_retracted: bool = False,
    limit: int = 50,
    force: bool = False,
    claim_id: str = "",
    bonus_stake: int = 0,
    attachment_scope: str = "node",
    eval_verdict: str = "",
    node_last_claimer: str = "",
    node_id: str = "",
) -> str:
    """Outcome Gates — real-world impact claims per Branch.

    Each Goal declares a ladder of rungs (draft → peer-reviewed → published
    → cited → breakthrough). Branches self-report which rungs they've
    reached, with an evidence URL.

    All actions require GATES_ENABLED=1 on the server; the tool returns
    {"status": "not_available"} when the flag is off. Bonus actions
    additionally require WORKFLOW_PAID_MARKET=on.

    Actions (all live when GATES_ENABLED=1):
      define_ladder Owner sets the rung list on a Goal. Needs goal_id
                    and `ladder` (JSON list of {rung_key, name,
                    description}).
      get_ladder    Read a Goal's ladder. Needs goal_id.
      claim         Report a rung reached. Needs branch_def_id,
                    rung_key, evidence_url. Idempotent on (branch, rung).
      retract       Soft-delete a claim. Needs branch_def_id, rung_key,
                    reason. Claim author, Goal owner, or host can
                    retract.
      list_claims   Browse claims. Provide exactly one of branch_def_id
                    or goal_id. `include_retracted` optional; claims
                    whose rung no longer exists in the Goal's ladder
                    are tagged `orphaned`.
      leaderboard   Rank Branches bound to a Goal by highest rung
                    reached. Tiebreak: earliest claim wins. Also
                    callable as `goals leaderboard metric=outcome`.

    Bonus actions (live when GATES_ENABLED=1 + WORKFLOW_PAID_MARKET=on):
      stake_bonus   Lock a bonus stake on a claim. Needs claim_id,
                    bonus_stake (int > 0), node_id. attachment_scope
                    controls what the stake attaches to ("node" default).
      unstake_bonus Remove a bonus stake and refund the staker. Needs
                    claim_id. Only the original staker can unstake.
      release_bonus Resolve a bonus payout via evaluator verdict. Needs
                    claim_id, eval_verdict ("pass"|"fail"|"skip"),
                    node_last_claimer (recipient on pass).

    Evidence URL must be http(s) with a host; content is not fetched
    (local-first). Social accountability handles fraud in v1.

    Args:
      action: see Actions above.
      goal_id: Goal target for ladder / leaderboard / list_claims.
      branch_def_id: Branch that's claiming / retracting / listing.
      rung_key: matches a ladder entry's rung_key.
      ladder: JSON list string for define_ladder.
      evidence_url: http(s) URL pointing at the claim's evidence.
      evidence_note: optional human summary.
      reason: retract reason (required for retract, non-empty).
      include_retracted: list_claims filter (default False).
      limit: cap for leaderboard / list_claims.
      force: bypass the dirty-file guard on the target YAML when a
             user has uncommitted local edits. Same ergonomics as
             `goals propose/update/bind` and `branch` mutations.
      claim_id: target claim for stake_bonus / unstake_bonus /
                release_bonus.
      bonus_stake: integer token amount for stake_bonus (must be > 0).
                   Harmless when WORKFLOW_PAID_MARKET is off — the
                   action returns not_available before reading this arg.
      attachment_scope: what the stake attaches to; "node" (default)
                        or "branch". Used by stake_bonus.
      eval_verdict: evaluator decision for release_bonus —
                    "pass" (payout to node_last_claimer), "fail"
                    (refund to staker), or "skip" (no-op).
      node_last_claimer: actor_id of the node fulfiller who receives
                         payout on a "pass" release_bonus verdict.
      node_id: node target for stake_bonus.
    """
    from workflow.api.engine_helpers import (
        _format_dirty_file_conflict,
    )
    from workflow.api.market import _gates_enabled

    if not _gates_enabled():
        return json.dumps({
            "status": "not_available",
            "error": (
                "Outcome gates are gated by the GATES_ENABLED flag "
                "(Phase 6.1). Set GATES_ENABLED=1 on the Workflow Server "
                "to opt in."
            ),
        })
    handler = _GATES_ACTIONS.get(action)
    if handler is None:
        return json.dumps({
            "status": "rejected",
            "error": f"Unknown action '{action}'.",
            "available_actions": sorted(_GATES_ACTIONS.keys()),
        })
    kwargs: dict[str, Any] = {
        "goal_id": goal_id,
        "branch_def_id": branch_def_id,
        "rung_key": rung_key,
        "ladder": ladder,
        "evidence_url": evidence_url,
        "evidence_note": evidence_note,
        "reason": reason,
        "include_retracted": include_retracted,
        "limit": limit,
        "force": force,
        "claim_id": claim_id,
        "bonus_stake": bonus_stake,
        "attachment_scope": attachment_scope,
        "eval_verdict": eval_verdict,
        "node_last_claimer": node_last_claimer,
        "node_id": node_id,
    }
    try:
        return handler(kwargs)
    except DirtyFileError as exc:
        # Phase 6.3: dirty-file guard surfaces as the structured
        # local_edit_conflict payload (same shape as `goals` and
        # `branch` handlers). Chat-side renders the options;
        # force=True retries through.
        return json.dumps(_format_dirty_file_conflict(exc))
