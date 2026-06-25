"""Evaluation subsystem — extracted from workflow/universe_server.py
(Task #12 — decomp Step 5).

Houses the Phase-4 multi-criteria judgment loop (judge_run / list_judgments /
compare_runs / suggest_node_edit / get_node_output / list_node_versions /
rollback_node) and the branch-versioning metadata handlers (publish_version /
get_branch_version / list_branch_versions). The MCP tool decoration stays in
``workflow/universe_server.py`` (Pattern A2 from the decomp plan); this
module is plain functions consumed via the ``extensions()`` MCP tool.

Public surface (back-compat re-exported via ``workflow.universe_server``):
    _JUDGMENT_ACTIONS          : 7-handler Phase 4 dispatch table
    _JUDGMENT_WRITE_ACTIONS    : ledger-gating frozenset
    _dispatch_judgment_action  : ledger-aware dispatcher
    _BRANCH_VERSION_ACTIONS    : 3-handler version-metadata dispatch table
    _action_judge_run / _action_list_judgments / _action_compare_runs /
    _action_suggest_node_edit / _action_get_node_output /
    _action_list_node_versions / _action_rollback_node : Phase 4 handlers
    _action_publish_version / _action_get_branch_version /
    _action_list_branch_versions : branch-version metadata handlers
    _split_tag_csv             : eval-only CSV-tag parser

Cross-module note: ``_append_global_ledger``, ``_truncate``, ``_current_actor``,
``_node_body_summary``, ``_ensure_workflow_db``, ``logger`` all live in
their owning API/helper modules and are lazy-imported inside the functions that
use them. This avoids the load-time cycle (universe_server back-compat-imports
symbols from this module).
Same pattern as Task #11 (workflow/api/runs.py) used for its 7 cross-module
symbols.

Source ranges extracted (current line numbers, post-#11 land):
- L7379–7459 — Branch versioning banner + 3 handlers + dispatch dict
- L8092–8859 — Phase 4 banner + helpers + 7 handlers + dispatch tables + dispatcher
"""

from __future__ import annotations

import json
import logging
from typing import Any

from workflow.api.helpers import _base_path

logger = logging.getLogger("universe_server.evaluation")


# ───────────────────────────────────────────────────────────────────────────
# Phase 4: Eval + iteration hooks
# ───────────────────────────────────────────────────────────────────────────
# Five small actions on the `extensions` tool that close the
# build → run → judge → edit → rerun loop. No numeric scoring (spec
# §Non-goals). No AI-in-the-loop judge. `suggest_node_edit` bundles
# context so Claude.ai makes the edit in ~one tool call, not four.


def _split_tag_csv(raw: str) -> list[str]:
    return [t.strip() for t in (raw or "").split(",") if t.strip()]


def _action_judge_run(kwargs: dict[str, Any]) -> str:
    """Attach a natural-language judgment to a run (optionally to a node)."""
    from workflow.api.engine_helpers import _current_actor
    from workflow.api.runs import _branch_name_for_run
    from workflow.runs import add_judgment
    from workflow.runs import get_run as _get_run

    rid = (kwargs.get("run_id") or "").strip()
    text = (kwargs.get("judgment_text") or "").strip()
    if not rid:
        return json.dumps({"error": "run_id is required."})
    if not text:
        return json.dumps({"error": "judgment_text is required."})

    run_record = _get_run(_base_path(), rid)
    if run_record is None:
        return json.dumps({"error": f"Run '{rid}' not found."})

    node_id = (kwargs.get("node_id") or "").strip() or None
    tag_list = _split_tag_csv(kwargs.get("tags", ""))

    saved = add_judgment(
        _base_path(),
        run_id=rid, text=text, node_id=node_id,
        tags=tag_list, author=_current_actor(),
    )
    scope = f"node `{node_id}`" if node_id else "whole run"
    tag_suffix = f" ({', '.join(tag_list)})" if tag_list else ""
    branch_label = _branch_name_for_run(run_record)
    text_md = (
        f"**Judgment recorded** on workflow '{branch_label}' — "
        f"{scope}{tag_suffix}.\n\n"
        f"> {text[:240]}"
        + ("…" if len(text) > 240 else "")
    )
    # Merge: put saved fields first, then overlay the rendered text +
    # status so the response-level `text` isn't clobbered by the
    # judgment's own free-form text field.
    response: dict[str, Any] = dict(saved)
    response["text"] = text_md
    response["status"] = "recorded"
    response["judgment_text"] = saved.get("text", "")
    return json.dumps(response, default=str)


def _action_list_judgments(kwargs: dict[str, Any]) -> str:
    from workflow.runs import list_judgments as _list_judgments

    bid = (kwargs.get("branch_def_id") or "").strip()
    rid = (kwargs.get("run_id") or "").strip()
    nid = (kwargs.get("node_id") or "").strip()
    if not (bid or rid or nid):
        return json.dumps({
            "error": (
                "Pass at least one filter: branch_def_id, run_id, or "
                "node_id. Full-table scans are disabled."
            ),
        })

    rows = _list_judgments(
        _base_path(),
        branch_def_id=bid, run_id=rid, node_id=nid,
        limit=int(kwargs.get("limit", 30) or 30),
    )
    if rows:
        lines = [f"**{len(rows)} judgment(s):**", ""]
        for j in rows[:12]:
            scope = (
                f"node=`{j['node_id']}`" if j.get("node_id")
                else "run-scoped"
            )
            tags_str = (
                f" [{', '.join(j['tags'])}]" if j.get("tags") else ""
            )
            first_line = (j.get("text") or "").split("\n", 1)[0]
            if len(first_line) > 100:
                first_line = first_line[:100].rstrip() + "…"
            lines.append(
                f"- `{j['author']}` · {scope}{tags_str} · {first_line}"
            )
        if len(rows) > 12:
            lines.append(
                f"- … and {len(rows) - 12} more. Narrow with "
                "run_id or node_id."
            )
        text_md = "\n".join(lines)
    else:
        text_md = "No judgments match the filter."
    return json.dumps({
        "text": text_md,
        "judgments": rows,
        "count": len(rows),
    }, default=str)


def _action_compare_runs(kwargs: dict[str, Any]) -> str:
    """Render a side-by-side diff of two runs' final outputs.

    Topology diff emitted only when branch_version changed — avoids
    visual noise for prompt-only edits (the common case).
    """
    from workflow.runs import get_lineage
    from workflow.runs import get_run as _get_run

    rid_a = (kwargs.get("run_a_id") or "").strip()
    rid_b = (kwargs.get("run_b_id") or "").strip()
    if not (rid_a and rid_b):
        return json.dumps({
            "error": "run_a_id and run_b_id are both required.",
        })

    rec_a = _get_run(_base_path(), rid_a)
    rec_b = _get_run(_base_path(), rid_b)
    if rec_a is None or rec_b is None:
        missing = rid_a if rec_a is None else rid_b
        return json.dumps({"error": f"Run '{missing}' not found."})

    lineage_a = get_lineage(_base_path(), rid_a) or {}
    lineage_b = get_lineage(_base_path(), rid_b) or {}
    version_a = int(lineage_a.get("branch_version", 0) or 0)
    version_b = int(lineage_b.get("branch_version", 0) or 0)
    topology_changed = bool(version_a and version_b and version_a != version_b)

    field = (kwargs.get("field") or "").strip()
    out_a = rec_a.get("output") or {}
    out_b = rec_b.get("output") or {}

    differences: list[dict[str, Any]] = []
    if field:
        a_val = out_a.get(field)
        b_val = out_b.get(field)
        differences.append({
            "node_id": field,
            "change_type": "unchanged" if a_val == b_val else "changed",
            "a_value": a_val,
            "b_value": b_val,
            "field": field,
        })
    else:
        keys = sorted(set(out_a) | set(out_b))
        for k in keys:
            a_val = out_a.get(k)
            b_val = out_b.get(k)
            if k not in out_a:
                change_type = "added"
            elif k not in out_b:
                change_type = "removed"
            elif a_val == b_val:
                change_type = "unchanged"
            else:
                change_type = "changed"
            differences.append({
                "node_id": k,
                "change_type": change_type,
                "a_value": a_val,
                "b_value": b_val,
                "field": k,
            })

    # Build phone-legible markdown.
    lines = [
        f"**Comparing runs** `{rid_a}` ↔ `{rid_b}`.",
        f"Branch version: {version_a} → {version_b}"
        + (
            " (topology changed)" if topology_changed
            else " (same version)" if version_a == version_b
            else ""
        ),
        "",
    ]
    changed = [d for d in differences if d["change_type"] != "unchanged"]
    unchanged_count = len(differences) - len(changed)
    if unchanged_count:
        lines.append(
            f"_{unchanged_count} field(s) unchanged._"
        )
        lines.append("")
    if changed:
        for d in changed:
            lines.append(f"### {d['node_id']} — {d['change_type']}")
            a_preview = str(d.get("a_value", ""))[:240]
            b_preview = str(d.get("b_value", ""))[:240]
            lines.append("```diff")
            lines.append(f"- {a_preview}")
            lines.append(f"+ {b_preview}")
            lines.append("```")
            lines.append("")
    else:
        lines.append("No field-level differences between the two runs.")

    return json.dumps({
        "text": "\n".join(lines).rstrip(),
        "run_a": {
            "run_id": rid_a,
            "branch_version": version_a,
            "final_state": out_a,
        },
        "run_b": {
            "run_id": rid_b,
            "branch_version": version_b,
            "final_state": out_b,
        },
        "differences": differences,
        "topology_changed": topology_changed,
    }, default=str)


def _action_suggest_node_edit(kwargs: dict[str, Any]) -> str:
    """Bundle everything Claude.ai needs to propose an edit, in one call.

    Per spec: this does NOT call an LLM. It assembles context. The
    calling client proposes the edit.
    """
    from workflow.api.branches import _ensure_workflow_db
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import get_branch_definition
    from workflow.runs import (
        list_judgments as _list_judgments,
    )
    from workflow.runs import (
        list_runs as _list_runs,
    )
    from workflow.runs import (
        node_output_from_run,
    )

    bid = (kwargs.get("branch_def_id") or "").strip()
    nid = (kwargs.get("node_id") or "").strip()
    user_context = (kwargs.get("context") or "").strip()
    if not (bid and nid):
        return json.dumps({
            "error": "branch_def_id and node_id are both required.",
        })

    _ensure_workflow_db()
    try:
        source = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({"error": f"Branch '{bid}' not found."})
    branch = BranchDefinition.from_dict(source)
    node = next((n for n in branch.node_defs if n.node_id == nid), None)
    if node is None:
        return json.dumps({
            "error": f"Node '{nid}' not found on branch '{bid}'.",
        })

    # Recent runs on this branch.
    recent_runs = _list_runs(_base_path(), branch_def_id=bid, limit=5)
    recent_outputs: list[dict[str, Any]] = []
    for r in recent_runs:
        snap = node_output_from_run(
            _base_path(), run_id=r["run_id"], node_id=nid,
        )
        if snap is None:
            continue
        detail = snap.get("detail") or {}
        response = str(
            detail.get("response")
            or detail.get("output")
            or ""
        )
        if len(response) > 500:
            response = response[:500].rstrip() + "…"
        recent_outputs.append({
            "run_id": r["run_id"],
            "status": r.get("status"),
            "output_summary": response,
        })
        if len(recent_outputs) >= 3:
            break

    # Judgments scoped to this node.
    judgments = _list_judgments(
        _base_path(), branch_def_id=bid, node_id=nid, limit=30,
    )

    body_kind = (
        "prompt_template" if node.prompt_template else (
            "source_code" if node.source_code else "passthrough"
        )
    )
    body = node.prompt_template or node.source_code or ""

    # Compose a framed prompt block Claude.ai can act on directly.
    branch_label = branch.name or "(unnamed workflow)"
    lines = [
        f"**Suggest edit for node `{nid}`** on workflow "
        f"'{branch_label}' (`{node.display_name}`).",
        "",
        f"**Current {body_kind}:**",
        "",
        "```",
        body or "(empty)",
        "```",
        "",
    ]
    if recent_outputs:
        lines.append("**Recent outputs:**")
        lines.append("")
        for ro in recent_outputs:
            preview = ro["output_summary"] or "(no output captured)"
            lines.append(f"- `{ro['run_id']}` ({ro['status']}): {preview}")
        lines.append("")
    if judgments:
        lines.append("**Judgments targeting this node:**")
        lines.append("")
        for j in judgments[:10]:
            tag_str = (
                f" [{', '.join(j['tags'])}]" if j.get("tags") else ""
            )
            first_line = (j.get("text") or "").split("\n", 1)[0]
            if len(first_line) > 140:
                first_line = first_line[:140].rstrip() + "…"
            lines.append(
                f"- {j['author']}{tag_str}: {first_line}"
            )
        lines.append("")
    if user_context:
        lines.append(f"**User context:** {user_context}")
        lines.append("")
    lines.append(
        "Now propose a new `prompt_template` (or `source_code`) and "
        "apply it via `update_node` when the user agrees."
    )

    return json.dumps({
        "text": "\n".join(lines),
        "node": node.to_dict(),
        "recent_runs": recent_outputs,
        "judgments": judgments,
        "user_context": user_context,
    }, default=str)


def _action_get_node_output(kwargs: dict[str, Any]) -> str:
    """Return a single node's output from a specific run — the hook
    users need to judge a specific node rather than the final state."""
    from workflow.api.runs import _branch_name_for_run
    from workflow.runs import get_run as _get_run
    from workflow.runs import node_output_from_run

    rid = (kwargs.get("run_id") or "").strip()
    nid = (kwargs.get("node_id") or "").strip()
    if not (rid and nid):
        return json.dumps({
            "error": "run_id and node_id are both required.",
        })
    run_record = _get_run(_base_path(), rid)
    if run_record is None:
        return json.dumps({"error": f"Run '{rid}' not found."})

    snap = node_output_from_run(_base_path(), run_id=rid, node_id=nid)
    if snap is None:
        return json.dumps({
            "error": (
                f"Node '{nid}' did not emit a 'ran' event on run "
                f"'{rid}'. Possible: node skipped, run failed before "
                "reaching it, or run not yet complete."
            ),
        })

    detail = snap.get("detail") or {}
    output_preview = str(
        detail.get("response") or detail.get("output") or ""
    )
    truncated = len(output_preview) > 2000
    if truncated:
        output_preview = output_preview[:2000].rstrip() + "…"

    branch_label = _branch_name_for_run(run_record)
    lines = [
        f"**Node `{nid}` output** from a run of workflow "
        f"'{branch_label}' (step {snap.get('step_index')}).",
        "",
        "```",
        output_preview or "(no output captured)",
        "```",
    ]
    if truncated:
        lines.append("")
        lines.append(
            "_(Output truncated to 2000 chars in text; full detail "
            "in structuredContent.)_"
        )

    return json.dumps({
        "text": "\n".join(lines),
        "run_id": rid,
        "node_id": nid,
        "step_index": snap.get("step_index"),
        "output": detail,
        "tool_calls": detail.get("tool_calls", []),
    }, default=str)


# ── #50: node version rollback ─────────────────────────────────────────
# `rollback_node` restores a node's body to an earlier version snapshot
# preserved in the node_edit_audit log. Rollback is itself an edit —
# bumps the branch version and emits its own audit row with
# ``edit_kind="rollback"`` so forward history is preserved. Judgments
# stay attached to the runs that produced them (their lineage points at
# specific versions), so rolling back doesn't strip accumulated signal.


def _node_body_summary(node_def: dict[str, Any]) -> str:
    """One-line summary for the version list. Phone-legible."""
    display = node_def.get("display_name") or node_def.get("node_id") or "?"
    if node_def.get("prompt_template"):
        body = (node_def.get("prompt_template") or "").strip()
        preview = body.replace("\n", " ")
        if len(preview) > 60:
            preview = preview[:60].rstrip() + "…"
        return f"{display} · prompt: {preview}"
    if node_def.get("source_code"):
        return (
            f"{display} · source_code "
            f"({len(node_def['source_code'])} chars)"
        )
    return f"{display} · passthrough"


def _action_list_node_versions(kwargs: dict[str, Any]) -> str:
    """Return the version history for a single node on a branch."""
    from workflow.api.branches import _ensure_workflow_db
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import get_branch_definition
    from workflow.runs import list_node_edit_audits

    bid = (kwargs.get("branch_def_id") or "").strip()
    nid = (kwargs.get("node_id") or "").strip()
    if not (bid and nid):
        return json.dumps({
            "error": "branch_def_id and node_id are both required.",
        })

    _ensure_workflow_db()
    try:
        source = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({"error": f"Branch '{bid}' not found."})
    branch = BranchDefinition.from_dict(source)
    current_node = next(
        (n for n in branch.node_defs if n.node_id == nid), None,
    )
    if current_node is None:
        return json.dumps({
            "error": f"Node '{nid}' not found on branch '{bid}'.",
        })

    audits = list_node_edit_audits(
        _base_path(), branch_def_id=bid, node_id=nid, limit=200,
    )

    current_version = int(branch.version or 1)
    versions: list[dict[str, Any]] = []
    seen: set[int] = set()

    versions.append({
        "version": current_version,
        "kind": "current",
        "timestamp": None,
        "node": current_node.to_dict(),
        "summary": _node_body_summary(current_node.to_dict()),
        "triggered_by_judgment_id": None,
    })
    seen.add(current_version)

    for a in audits:
        va = int(a["version_after"])
        if va not in seen and a.get("node_after"):
            versions.append({
                "version": va,
                "kind": a.get("edit_kind", "update"),
                "timestamp": a.get("timestamp"),
                "node": a["node_after"],
                "summary": _node_body_summary(a["node_after"]),
                "triggered_by_judgment_id": a.get(
                    "triggered_by_judgment_id"
                ),
            })
            seen.add(va)
        vb = int(a["version_before"])
        if vb not in seen and a.get("node_before"):
            versions.append({
                "version": vb,
                "kind": "previous",
                "timestamp": None,
                "node": a["node_before"],
                "summary": _node_body_summary(a["node_before"]),
                "triggered_by_judgment_id": None,
            })
            seen.add(vb)

    versions.sort(key=lambda v: v["version"], reverse=True)

    branch_label = branch.name or "(unnamed workflow)"
    lines = [
        f"**{len(versions)} version(s) of node `{nid}`** on workflow "
        f"'{branch_label}' (current: v{current_version}).",
        "",
        "| Version | Kind | Summary |",
        "|---:|---|---|",
    ]
    for v in versions[:20]:
        marker = (
            "← current" if v["version"] == current_version else ""
        )
        lines.append(
            f"| v{v['version']} | {v['kind']} | "
            f"{v['summary']} {marker} |".rstrip()
        )
    if len(versions) > 20:
        lines.append("")
        lines.append(
            f"_(showing 20 of {len(versions)} versions — full history "
            "in structuredContent)_"
        )
    lines.append("")
    lines.append(
        f"Rollback with `rollback_node branch_def_id={bid} "
        f"node_id={nid} to_version=<N>`."
    )

    return json.dumps({
        "text": "\n".join(lines),
        "branch_def_id": bid,
        "node_id": nid,
        "current_version": current_version,
        "versions": versions,
    }, default=str)


def _action_rollback_node(kwargs: dict[str, Any]) -> str:
    """Restore a node to a previously recorded version.

    Rollback is itself an edit: bumps the branch version and emits a new
    audit row with ``edit_kind="rollback"``. Forward history is never
    destroyed — the old body stays retrievable via list_node_versions.
    """
    from workflow.api.branches import _ensure_workflow_db
    from workflow.branches import BranchDefinition, NodeDefinition
    from workflow.daemon_server import (
        get_branch_definition,
        save_branch_definition,
    )
    from workflow.runs import (
        find_node_snapshot,
        list_node_edit_audits,
        record_node_edit_audit,
    )

    bid = (kwargs.get("branch_def_id") or "").strip()
    nid = (kwargs.get("node_id") or "").strip()
    if not (bid and nid):
        return json.dumps({
            "status": "rejected",
            "error": "branch_def_id and node_id are both required.",
        })

    _ensure_workflow_db()
    try:
        source = get_branch_definition(_base_path(), branch_def_id=bid)
    except KeyError:
        return json.dumps({
            "status": "rejected",
            "error": f"Branch '{bid}' not found.",
        })

    branch = BranchDefinition.from_dict(source)
    current_node = next(
        (n for n in branch.node_defs if n.node_id == nid), None,
    )
    if current_node is None:
        return json.dumps({
            "status": "rejected",
            "error": f"Node '{nid}' not found on branch '{bid}'.",
        })

    current_version = int(branch.version or 1)

    to_version_raw = kwargs.get("to_version", "")
    to_version: int | None = None
    if isinstance(to_version_raw, int):
        to_version = to_version_raw
    elif isinstance(to_version_raw, str) and to_version_raw.strip():
        try:
            to_version = int(to_version_raw.strip())
        except ValueError:
            return json.dumps({
                "status": "rejected",
                "error": (
                    f"to_version must be an integer, got "
                    f"{to_version_raw!r}."
                ),
            })

    restored_body: dict[str, Any] = {}
    if to_version is None:
        audits = list_node_edit_audits(
            _base_path(), branch_def_id=bid, node_id=nid, limit=10,
        )
        latest = next(
            (
                a for a in audits
                if int(a["version_after"]) == current_version
            ),
            None,
        )
        if latest is None:
            return json.dumps({
                "status": "rejected",
                "error": (
                    f"No recorded previous version of node '{nid}'. "
                    "Nothing to roll back to."
                ),
            })
        restored_body = latest.get("node_before") or {}
        to_version = int(latest["version_before"])
    elif to_version == current_version:
        return json.dumps({
            "status": "rejected",
            "error": (
                f"Node '{nid}' is already at version {current_version}."
            ),
        })
    else:
        restored_body = find_node_snapshot(
            _base_path(),
            branch_def_id=bid, node_id=nid, at_version=to_version,
        ) or {}
        if not restored_body:
            return json.dumps({
                "status": "rejected",
                "error": (
                    f"No snapshot of node '{nid}' at version "
                    f"{to_version}. Run list_node_versions to see "
                    "available targets."
                ),
            })

    try:
        restored_node = NodeDefinition.from_dict(restored_body)
    except Exception as exc:
        return json.dumps({
            "status": "rejected",
            "error": f"Restored body is not a valid NodeDefinition: {exc}",
        })

    # SECURITY (Codex final residual, PR #1349): the restored body is a RAW
    # audit snapshot. A snapshot of an old version may carry source_code +
    # approved=True with an empty or stale approved_source_hash (e.g. approved
    # before the provenance field existed, or rolled back across an unapproved
    # edit). Restoring it verbatim would re-bless code the current approval
    # provenance does not cover. Re-validate the restored node's approval
    # against its source hash and clear it on mismatch. The fail-closed runtime
    # gate is the backstop; this keeps the persisted node honest.
    from workflow.api.branches import _reconcile_node_approval

    _reconcile_node_approval(restored_node)

    node_before_body = current_node.to_dict()

    new_node_defs = [
        restored_node if n.node_id == nid else n
        for n in branch.node_defs
    ]
    branch.node_defs = new_node_defs

    new_version = current_version + 1
    staging_dict = branch.to_dict()
    staging_dict["version"] = new_version
    saved = save_branch_definition(_base_path(), branch_def=staging_dict)
    persisted = BranchDefinition.from_dict(saved)
    persisted_node = next(
        (n for n in persisted.node_defs if n.node_id == nid),
        restored_node,
    )

    try:
        record_node_edit_audit(
            _base_path(),
            branch_def_id=bid,
            version_before=current_version,
            version_after=new_version,
            nodes_changed=[nid],
            triggered_by_judgment_id=None,
            node_before=node_before_body,
            node_after=persisted_node.to_dict(),
            edit_kind="rollback",
        )
    except Exception:
        logger.exception("rollback audit failed for %s/%s", bid, nid)

    branch_label = persisted.name or "(unnamed workflow)"
    text_lines = [
        f"**Rolled back node `{nid}`** on workflow '{branch_label}' to "
        f"v{to_version} (workflow now at v{new_version}).",
        "",
        f"- Restored body: "
        f"{_node_body_summary(persisted_node.to_dict())}",
        "",
        "_Rollback is itself an edit — the previous body is still in "
        "history if you need to go forward again. List versions with "
        "`list_node_versions`._",
    ]

    return json.dumps({
        "text": "\n".join(text_lines),
        "status": "rolled_back",
        "branch_def_id": bid,
        "node_id": nid,
        "restored_from_version": to_version,
        "version_before": current_version,
        "version_after": new_version,
        "node": persisted_node.to_dict(),
    }, default=str)


_JUDGMENT_ACTIONS: dict[str, Any] = {
    "judge_run": _action_judge_run,
    "list_judgments": _action_list_judgments,
    "compare_runs": _action_compare_runs,
    "suggest_node_edit": _action_suggest_node_edit,
    "get_node_output": _action_get_node_output,
    "rollback_node": _action_rollback_node,
    "list_node_versions": _action_list_node_versions,
}

_JUDGMENT_WRITE_ACTIONS: frozenset[str] = frozenset({
    "judge_run", "rollback_node",
})


def _dispatch_judgment_action(
    action: str,
    handler: Any,
    kwargs: dict[str, Any],
) -> str:
    """Dispatch a Phase 4 action. ``judge_run`` is the only write; the
    rest are read-only and bypass the ledger."""
    from workflow.api.branches import _append_global_ledger
    from workflow.api.engine_helpers import _truncate

    result_str = handler(kwargs)
    if action not in _JUDGMENT_WRITE_ACTIONS:
        return result_str

    try:
        result = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        return result_str
    if not isinstance(result, dict) or "error" in result:
        return result_str

    try:
        target = (
            result.get("judgment_id")
            or result.get("run_id")
            or kwargs.get("run_id", "")
        )
        summary_bits = [action]
        if kwargs.get("run_id"):
            summary_bits.append(f"run={kwargs['run_id']}")
        if kwargs.get("node_id"):
            summary_bits.append(f"node={kwargs['node_id']}")
        _append_global_ledger(
            action,
            target=str(target),
            summary=_truncate(" ".join(summary_bits)),
            payload=None,
        )
    except Exception as exc:
        logger.warning(
            "Ledger write failed for judgment action %s: %s", action, exc,
        )
    return result_str

# ───────────────────────────────────────────────────────────────────────────
# Branch versioning — publish_version + get_branch_version + list_branch_versions
# ───────────────────────────────────────────────────────────────────────────


def _action_publish_version(kwargs: dict[str, Any]) -> str:
    from workflow.branch_versions import publish_branch_version
    from workflow.daemon_server import get_branch_definition

    bid = (kwargs.get("branch_def_id") or "").strip()
    notes = (kwargs.get("notes") or "").strip()
    parent_version_id = (kwargs.get("parent_version_id") or "").strip() or None
    publisher = (kwargs.get("publisher") or "anonymous").strip()

    if not bid:
        return json.dumps({"error": "branch_def_id is required."})

    base_path = _base_path()
    try:
        raw = get_branch_definition(base_path, branch_def_id=bid)
    except (KeyError, FileNotFoundError):
        return json.dumps({"error": f"Branch '{bid}' not found."})
    except Exception as exc:
        return json.dumps({"error": f"Could not load branch: {exc}"})

    try:
        version = publish_branch_version(
            base_path,
            raw,
            publisher=publisher,
            notes=notes,
            parent_version_id=parent_version_id,
        )
    except (KeyError, ValueError) as exc:
        return json.dumps({"error": str(exc)})

    return json.dumps({
        "branch_version_id": version.branch_version_id,
        "content_hash": version.content_hash,
        "published_at": version.published_at,
        "publisher": version.publisher,
        "parent_version_id": version.parent_version_id,
    })


def _action_get_branch_version(kwargs: dict[str, Any]) -> str:
    from workflow.branch_versions import get_branch_version

    version_id = (kwargs.get("branch_version_id") or "").strip()
    if not version_id:
        return json.dumps({"error": "branch_version_id is required."})

    base_path = _base_path()
    version = get_branch_version(base_path, version_id)
    if version is None:
        return json.dumps({"error": f"Version '{version_id}' not found."})
    return json.dumps(version.to_dict())


def _action_list_branch_versions(kwargs: dict[str, Any]) -> str:
    from workflow.branch_versions import list_branch_versions

    bid = (kwargs.get("branch_def_id") or "").strip()
    if not bid:
        return json.dumps({"error": "branch_def_id is required."})
    limit = int(kwargs.get("limit", 50) or 50)

    base_path = _base_path()
    versions = list_branch_versions(base_path, bid, limit=limit)
    return json.dumps({
        "branch_def_id": bid,
        "versions": [v.to_dict() for v in versions],
        "count": len(versions),
    })


_BRANCH_VERSION_ACTIONS: dict[str, Any] = {
    "publish_version": _action_publish_version,
    "get_branch_version": _action_get_branch_version,
    "list_branch_versions": _action_list_branch_versions,
}
