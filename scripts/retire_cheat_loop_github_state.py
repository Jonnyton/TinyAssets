#!/usr/bin/env python3
"""Receipt-bound retirement of legacy TinyAssets GitHub state.

The command-line surface is intentionally read-only.  It can inventory the
repository and produce deterministic plans, but it does not contain a live
GitHub mutator.  ``apply_actions`` is the tested, dependency-injected apply
engine for the later quiescent migration.  Keeping the live reader and writer
as different types makes a dry run incapable of mutating GitHub.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import contextlib
import copy
import datetime as dt
import hashlib
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
from urllib.parse import parse_qsl, quote, urlsplit

import rfc8785

SCHEMA = "tinyassets.github-state-retirement-receipt"
SCHEMA_VERSION = 1
LABEL_OPERATION = "retired_labels_v1"
AUTO_MERGE_OPERATION = "auto_merge_v1"
OPERATIONS = frozenset({LABEL_OPERATION, AUTO_MERGE_OPERATION})
LABEL_DEFINITION_FIELDS = frozenset(
    {"node_id", "database_id", "name", "color", "description", "url"}
)
LABEL_ASSOCIATION_FIELDS = frozenset(
    {
        "label_node_id",
        "label_name",
        "item_node_id",
        "number",
        "kind",
        "state",
        "url",
    }
)
APPLY_DOMAIN = "tinyassets/github-state-retirement/apply/v1"
AUTO_ENROLL_WORKFLOW_ID = 317815472
GITHUB_ACTIONS_BOT_NODE_ID = "MDM6Qm90NDE4OTgyODI="
GITHUB_ACTIONS_BOT_LOGIN = "github-actions"
TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHAS = (
    "1e3d8996644756a8fedf1baacd473cffd614c91b",
)
TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHA = TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHAS[-1]
AUTO_ENROLL_WORKFLOW_PATH = ".github/workflows/auto-enroll-merge.yml"
AUTO_ENROLL_PATH_INTRODUCTION_COMMIT = (
    "0efd2a34cd9d479bd16da84b4aef8dafed304d0e"
)
AUTO_ENROLL_EXACT_COMMAND = 'gh pr merge "$PR" --repo "$REPO" --auto --squash'
MAX_LOG_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_LOG_UNCOMPRESSED_BYTES = 25 * 1024 * 1024
MAX_LOG_ENTRIES = 1_000
MAX_REST_PAGES = 1_000

RETIRED_LABELS = (
    "auto-bug",
    "auto-change",
    "auto-checker-dispatched",
    "auto-checker-failed",
    "auto-fix-already-fixed",
    "auto-fix-attempted",
    "auto-fix-auth-expired",
    "auto-fix-auth-missing",
    "auto-fix-blocked",
    "auto-fix-branch-push-blocked",
    "auto-fix-claude-subscription-missing",
    "auto-fix-codex-subscription-missing",
    "auto-fix-exhausted",
    "auto-fix-pr-blocked",
    "auto-fix-provider-exhausted",
    "auto-fix-retries-1",
    "auto-fix-retries-2",
    "auto-fix-retries-3",
    "auto-fix-retries-4",
    "auto-fix-retries-5",
    "auto-fix-reviewed",
    "auto-fix-stale-gate",
    "auto-fix-superseded",
    "auto-fix-writer-failed",
    "community-loop-red",
    "loop-consent",
    "priority:loop-discipline",
    "ready_for_checker",
)
RETIRED_LABEL_SET = frozenset(RETIRED_LABELS)

PRESERVED_LABEL_PREFIXES = (
    "request:",
    "payment:",
    "checker:",
    "writer:",
    "writer-pool:",
    "priority:primitive-",
)
PRESERVED_LABELS = frozenset(
    {
        "daemon-request",
        "gate-required",
        "needs-human",
        "patch_request",
        "merge-effector",
        "secure-merge",
    }
)

NONTERMINAL_RUN_STATUSES = frozenset(
    {"queued", "in_progress", "waiting", "requested", "pending"}
)


class RetirementError(RuntimeError):
    """Base error for a refused retirement operation."""


class PlanError(RetirementError):
    """The supplied inventory or receipt is incomplete or changed."""


class ApplyBlocked(RetirementError):
    """Apply authorization is incomplete or ambiguous."""


class JournalConflict(RetirementError):
    """A durable apply key was reused for a different immutable plan."""


def canonical_bytes(value: Any) -> bytes:
    """Return RFC 8785/JCS bytes or fail rather than weakening the digest."""

    try:
        return rfc8785.dumps(value)
    except (rfc8785.CanonicalizationError, TypeError, ValueError) as exc:
        raise PlanError(f"value is not RFC 8785 canonicalizable: {exc}") from exc


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _is_sha256_digest(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", value)
    )


def _without(mapping: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    result = copy.deepcopy(dict(mapping))
    for key in keys:
        result.pop(key, None)
    return result


def derive_apply_key(
    operation: str, repo_node_id: str, plan_digest: str
) -> str:
    return digest(
        {
            "domain": APPLY_DOMAIN,
            "operation": operation,
            "repo_node_id": repo_node_id,
            "plan_digest": plan_digest,
        }
    )


def _sorted_json_records(
    rows: Iterable[Mapping[str, Any]], key: Callable[[Mapping[str, Any]], Any]
) -> list[dict[str, Any]]:
    return [copy.deepcopy(dict(row)) for row in sorted(rows, key=key)]


def _validate_repo(repo: Mapping[str, Any]) -> dict[str, Any]:
    required = ("node_id", "database_id", "name_with_owner", "default_branch")
    missing = [field for field in required if repo.get(field) in (None, "")]
    if missing:
        raise PlanError(f"repository identity is missing {', '.join(missing)}")
    return {field: repo[field] for field in required}


def _validate_complete_connections(
    connections: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for connection in connections:
        allowed_connection_fields = {
            "kind",
            "label_name",
            "pages",
            "count",
            "total_count",
            "complete",
            "completion_basis",
        }
        if connection.get("complete") is not True:
            raise PlanError("inventory contains an incomplete paginated connection")
        count = connection.get("count")
        total = connection.get("total_count")
        pages = connection.get("pages")
        if not all(_is_integer(value) and value >= 0 for value in (count, pages)):
            raise PlanError(
                "connection count and pages must be non-negative integers"
            )
        if pages < 1:
            raise PlanError("complete pagination requires one response page")
        completion_basis = connection.get("completion_basis")
        if completion_basis == "github_link_header_chain_v1":
            allowed_connection_fields.update(
                {"snapshot_consistency", "mutation_authority", "pagination"}
            )
            if (
                "snapshot_consistency" in connection
                and connection.get("snapshot_consistency") != "single_pass_live"
            ):
                raise PlanError("Link pagination snapshot consistency is unreviewed")
            if (
                "mutation_authority" in connection
                and connection.get("mutation_authority") is not False
            ):
                raise PlanError("read-only pagination cannot carry mutation authority")
            if total is not None:
                raise PlanError(
                    "Link-paginated array connections cannot invent a server total"
                )
            pagination = connection.get("pagination")
            page_receipts = (
                pagination.get("page_receipts")
                if isinstance(pagination, Mapping)
                else None
            )
            terminal = (
                pagination.get("terminal")
                if isinstance(pagination, Mapping)
                else None
            )
            if (
                not isinstance(pagination, Mapping)
                or set(pagination) != {"mode", "page_receipts", "terminal"}
                or pagination.get("mode") != "github_link_header_chain_v1"
                or not isinstance(page_receipts, list)
                or len(page_receipts) != pages
                or not isinstance(terminal, Mapping)
                or set(terminal) != {"oracle", "page_ordinal"}
                or terminal.get("oracle") != "rel_next_absent"
                or terminal.get("page_ordinal") != pages - 1
            ):
                raise PlanError("Link pagination lacks exact terminal evidence")
            observed = 0
            for ordinal, page in enumerate(page_receipts):
                if (
                    not isinstance(page, Mapping)
                    or set(page)
                    != {
                        "ordinal",
                        "request_id",
                        "request_url_digest",
                        "response_body_digest",
                        "item_count",
                        "next_url_digest",
                    }
                    or page.get("ordinal") != ordinal
                    or not _is_integer(page.get("item_count"))
                    or page["item_count"] < 0
                    or not isinstance(page.get("request_id"), str)
                    or not page["request_id"]
                    or not _is_sha256_digest(page.get("request_url_digest"))
                    or not _is_sha256_digest(page.get("response_body_digest"))
                    or (
                        ordinal < pages - 1
                        and not _is_sha256_digest(page.get("next_url_digest"))
                    )
                    or (
                        ordinal == pages - 1
                        and page.get("next_url_digest") is not None
                    )
                ):
                    raise PlanError("Link pagination page receipt is malformed")
                observed += int(page["item_count"])
            if any(
                page_receipts[ordinal]["next_url_digest"]
                != page_receipts[ordinal + 1]["request_url_digest"]
                for ordinal in range(len(page_receipts) - 1)
            ):
                raise PlanError("Link pagination receipt chain is broken")
            if observed != count:
                raise PlanError("Link pagination count does not match its page receipts")
        elif completion_basis in {
            "reported_total_count",
            "graphql_total_count",
        }:
            if not _is_integer(total) or total < 0:
                raise PlanError(
                    "server-counted connection total must be a non-negative integer"
                )
        else:
            raise PlanError("paginated connection lacks a recognized completion basis")
        unknown_fields = set(connection) - allowed_connection_fields
        if unknown_fields:
            raise PlanError(
                "paginated connection contains unreviewed fields: "
                + ", ".join(sorted(str(field) for field in unknown_fields))
            )
        if total is not None and count != total:
            raise PlanError(
                f"paginated connection count mismatch: observed {count}, expected {total}"
            )
        normalized.append(copy.deepcopy(dict(connection)))
    return sorted(
        normalized,
        key=lambda row: (
            str(row.get("kind", "")),
            str(row.get("label_name", "")),
        ),
    )


def _normalize_label_inventory(inventory: Mapping[str, Any]) -> dict[str, Any]:
    definitions = _sorted_json_records(
        inventory.get("definitions", []),
        key=lambda row: (str(row.get("name", "")).casefold(), str(row.get("node_id", ""))),
    )
    names = [str(row.get("name", "")) for row in definitions]
    if len(names) != len(RETIRED_LABELS):
        raise PlanError(
            f"expected {len(RETIRED_LABELS)} retired definitions, found {len(names)}"
        )
    if len({name.casefold() for name in names}) != len(names):
        raise PlanError("retired definition names are not case-insensitively unique")
    if set(names) != RETIRED_LABEL_SET:
        missing = sorted(RETIRED_LABEL_SET - set(names))
        extra = sorted(set(names) - RETIRED_LABEL_SET)
        raise PlanError(f"retired definition mismatch; missing={missing}, extra={extra}")
    for definition in definitions:
        actual_fields = set(definition)
        if actual_fields != LABEL_DEFINITION_FIELDS:
            raise PlanError(
                "label definition fields are not the exact collector schema; "
                f"missing={sorted(LABEL_DEFINITION_FIELDS - actual_fields)}, "
                f"unknown={sorted(actual_fields - LABEL_DEFINITION_FIELDS)}"
            )
        if not isinstance(definition["node_id"], str) or not definition["node_id"]:
            raise PlanError("label definition node_id must be a non-empty string")
        if (
            not _is_integer(definition["database_id"])
            or definition["database_id"] < 1
        ):
            raise PlanError("label definition database_id must be a positive integer")
        if not isinstance(definition["name"], str) or not definition["name"]:
            raise PlanError("label definition name must be a non-empty string")
        if (
            not isinstance(definition["color"], str)
            or re.fullmatch(r"[0-9a-fA-F]{6}", definition["color"]) is None
        ):
            raise PlanError("label definition color must be six hexadecimal characters")
        if definition["description"] is not None and not isinstance(
            definition["description"], str
        ):
            raise PlanError("label definition description must be a string or null")
        if definition["url"] is not None and (
            not isinstance(definition["url"], str) or not definition["url"]
        ):
            raise PlanError("label definition url must be a non-empty string or null")

    associations = _sorted_json_records(
        inventory.get("associations", []),
        key=lambda row: (
            str(row.get("item_node_id", "")),
            str(row.get("label_name", "")),
        ),
    )
    seen: set[tuple[str, str]] = set()
    for row in associations:
        actual_fields = set(row)
        if actual_fields != LABEL_ASSOCIATION_FIELDS:
            raise PlanError(
                "label association fields are not the exact collector schema; "
                f"missing={sorted(LABEL_ASSOCIATION_FIELDS - actual_fields)}, "
                f"unknown={sorted(actual_fields - LABEL_ASSOCIATION_FIELDS)}"
            )
        label_name = row.get("label_name")
        if not isinstance(label_name, str) or label_name not in RETIRED_LABEL_SET:
            raise PlanError(f"association contains non-retired label {label_name!r}")
        for field in ("label_node_id", "item_node_id"):
            if not isinstance(row[field], str) or not row[field]:
                raise PlanError(f"association {field} must be a non-empty string")
        if not _is_integer(row["number"]) or row["number"] < 1:
            raise PlanError("association number must be a positive integer")
        if not isinstance(row["kind"], str) or row["kind"] not in {
            "issue",
            "pull_request",
        }:
            raise PlanError("association kind must be issue or pull_request")
        if not isinstance(row["state"], str) or row["state"] not in {
            "open",
            "closed",
        }:
            raise PlanError("association state must be open or closed")
        if row["url"] is not None and (
            not isinstance(row["url"], str) or not row["url"]
        ):
            raise PlanError("association url must be a non-empty string or null")
        identity = (row["item_node_id"], label_name)
        if identity in seen:
            raise PlanError(f"duplicate association {identity}")
        seen.add(identity)

    connections = _validate_complete_connections(inventory.get("connections", []))
    connection_keys = [
        (str(row.get("kind", "")), str(row.get("label_name", "")))
        for row in connections
    ]
    expected_keys = {("label_definitions", "")} | {
        ("retired_label_associations", name) for name in RETIRED_LABELS
    }
    if len(connection_keys) != len(set(connection_keys)) or set(connection_keys) != expected_keys:
        raise PlanError(
            "label inventory must contain one definition connection and "
            "one association connection per retired label"
        )
    connection_by_key = {
        (str(row["kind"]), str(row["label_name"])): row for row in connections
    }
    if connection_by_key[("label_definitions", "")]["count"] < len(definitions):
        raise PlanError("label-definition connection is smaller than captured definitions")
    association_counts = {name: 0 for name in RETIRED_LABELS}
    for row in associations:
        association_counts[str(row["label_name"])] += 1
    for name, observed in association_counts.items():
        if (
            connection_by_key[("retired_label_associations", name)]["count"]
            != observed
        ):
            raise PlanError(
                f"association connection count does not match captured rows for {name}"
            )
    planned_actions_value = inventory.get("planned_actions", [])
    if not isinstance(planned_actions_value, list):
        raise PlanError("retired-label planned_actions must be a JSON array")
    planned_actions = _normalize_planned_actions(planned_actions_value)
    if planned_actions:
        raise PlanError(
            "retired-label planned actions are not implemented; "
            "this increment is inventory-only"
        )
    apply_complete = inventory.get("apply_complete") is True
    if apply_complete:
        raise PlanError(
            "complete retired-label apply plans are not implemented; "
            "this increment is inventory-only"
        )
    return {
        "definitions": definitions,
        "associations": associations,
        "connections": connections,
        "planned_actions": planned_actions,
        "apply_complete": apply_complete,
        "manifest": list(RETIRED_LABELS),
        "manifest_digest": digest(list(RETIRED_LABELS)),
    }


def _normalize_planned_actions(
    actions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    for action in actions:
        ordinal = action.get("ordinal")
        if not isinstance(ordinal, int) or isinstance(ordinal, bool):
            raise PlanError("planned action ordinal must be an integer")
    normalized = _sorted_json_records(
        actions,
        key=lambda row: (
            int(row.get("ordinal", -1)),
            str(row.get("kind", "")),
            str(row.get("target_node_id", "")),
        ),
    )
    for expected_ordinal, action in enumerate(normalized):
        if action.get("ordinal") != expected_ordinal:
            raise PlanError("planned action ordinals must be contiguous from zero")
        for field in (
            "kind",
            "target_node_id",
            "planned_before",
            "planned_after",
        ):
            if field not in action:
                raise PlanError(f"planned action is missing {field}")
        if not isinstance(action["planned_before"], Mapping) or not isinstance(
            action["planned_after"], Mapping
        ):
            raise PlanError("planned before/after values must be objects")
    identities = {
        (str(action["kind"]), str(action["target_node_id"]), int(action["ordinal"]))
        for action in normalized
    }
    if len(identities) != len(normalized):
        raise PlanError("planned actions contain duplicate identities")
    return normalized


def _validate_auto_merge_attribution_bindings(
    *,
    pull_requests: Sequence[Mapping[str, Any]],
    connections: Sequence[Mapping[str, Any]],
    workflow_runs: Any,
    workflow_jobs: Sequence[Mapping[str, Any]],
    source_history: Any,
    attribution: Sequence[Mapping[str, Any]],
) -> None:
    """Validate collected attribution even when it cannot authorize apply."""

    if not attribution:
        return
    expected_source_history = {
        "source_commit": None,
        "source_commit_status": "unavailable_from_stable_api",
        "default_branch": "main",
        "workflow_path": AUTO_ENROLL_WORKFLOW_PATH,
        "path_introduction_commit": AUTO_ENROLL_PATH_INTRODUCTION_COMMIT,
        "active_blob_sha": TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHA,
        "mapping_basis": "unchanged-default-branch-path-history",
        "commits": [
            {
                "sha": AUTO_ENROLL_PATH_INTRODUCTION_COMMIT,
                "committed_at": "2026-07-22T00:38:24Z",
            }
        ],
    }
    if source_history != expected_source_history:
        raise PlanError("attribution lacks the reviewed workflow source history")
    source_connections = [
        row for row in connections if row.get("kind") == "workflow_source_history"
    ]
    if (
        len(source_connections) != 1
        or source_connections[0].get("label_name") != AUTO_ENROLL_WORKFLOW_PATH
        or source_connections[0].get("count") != 1
    ):
        raise PlanError("attribution lacks one source-history connection")
    if not isinstance(workflow_runs, list):
        raise PlanError("attribution lacks the workflow-run inventory")
    run_connection = [
        row
        for row in connections
        if row.get("kind") == "workflow_runs" and row.get("label_name") == ""
    ]
    if len(run_connection) != 1 or run_connection[0].get("count") != len(
        workflow_runs
    ):
        raise PlanError("attribution lacks one exact workflow-run connection")
    run_by_id: dict[int, Mapping[str, Any]] = {}
    for run in workflow_runs:
        if not isinstance(run, Mapping) or not _is_integer(run.get("id")):
            raise PlanError("attribution workflow run lacks an integer id")
        run_id = int(run["id"])
        if run_id in run_by_id:
            raise PlanError("attribution workflow runs contain duplicate ids")
        run_by_id[run_id] = run
    job_by_identity: dict[tuple[int, int], Mapping[str, Any]] = {}
    jobs_per_run: dict[int, int] = {}
    for job in workflow_jobs:
        run_id = job.get("run_id")
        job_id = job.get("id")
        if not _is_integer(run_id) or not _is_integer(job_id):
            raise PlanError("attribution workflow job lacks exact identity")
        identity = (int(run_id), int(job_id))
        if identity in job_by_identity:
            raise PlanError("attribution workflow jobs contain duplicate identities")
        job_by_identity[identity] = job
        jobs_per_run[int(run_id)] = jobs_per_run.get(int(run_id), 0) + 1
    job_connections = {
        int(row["label_name"]): row
        for row in connections
        if row.get("kind") == "workflow_jobs"
        and isinstance(row.get("label_name"), str)
        and row["label_name"].isdigit()
    }
    if set(job_connections) != set(jobs_per_run) or any(
        job_connections[run_id].get("count") != count
        for run_id, count in jobs_per_run.items()
    ):
        raise PlanError("attribution lacks exact workflow-job connections")
    pr_by_id = {str(row["node_id"]): row for row in pull_requests}
    attr_by_id = {
        str(row.get("pull_request_node_id")): row for row in attribution
    }
    if (
        len(pr_by_id) != len(pull_requests)
        or len(attr_by_id) != len(attribution)
        or set(attr_by_id) != set(pr_by_id)
    ):
        raise PlanError("attribution does not cover each captured enrollment exactly")
    for pr_id, row in attr_by_id.items():
        evidence = row.get("evidence")
        if not isinstance(evidence, list):
            raise PlanError("attribution evidence must be an array")
        recomputed = classify_auto_merge(pr_by_id[pr_id], evidence)
        if (
            row.get("classification") != recomputed["classification"]
            or canonical_bytes(evidence) != canonical_bytes(recomputed["evidence"])
        ):
            raise PlanError("attribution is not proven by its bound evidence")
        for bound in evidence:
            run_id = bound.get("run_id")
            if not _is_integer(run_id):
                raise PlanError("attribution evidence lacks a run identity")
            run = run_by_id.get(int(run_id))
            if run is None:
                raise PlanError("attribution evidence run was not captured")
            if bound.get("evidence_status") == "log_unavailable":
                expected_unavailable = {
                    "evidence_status": "log_unavailable",
                    "reason": "log_read_failed",
                    "workflow_id": run.get("workflow_id"),
                    "run_id": int(run_id),
                    "event": run.get("event"),
                    "run_status": run.get("status"),
                    "conclusion": run.get("conclusion"),
                    "pull_request_number": pr_by_id[pr_id].get("number"),
                    "head_sha": run.get("head_sha"),
                    "run_created_at": run.get("created_at"),
                    "run_updated_at": run.get("updated_at"),
                    "run_url": run.get("html_url"),
                }
                if bound != expected_unavailable:
                    raise PlanError(
                        "log-unavailable evidence does not match its captured run"
                    )
                linked = run.get("pull_requests")
                if not isinstance(linked, list) or not any(
                    isinstance(item, Mapping)
                    and item.get("number") == pr_by_id[pr_id].get("number")
                    for item in linked
                ):
                    raise PlanError(
                        "log-unavailable run is not linked to its pull request"
                    )
                continue
            job_id = bound.get("job_id")
            if not _is_integer(job_id):
                raise PlanError("attribution evidence lacks a job identity")
            run_fields = {
                "workflow_id": "workflow_id",
                "workflow_path": "path",
                "event": "event",
                "run_status": "status",
                "conclusion": "conclusion",
                "head_sha": "head_sha",
                "run_created_at": "created_at",
                "run_updated_at": "updated_at",
                "run_url": "html_url",
            }
            if any(
                bound.get(evidence_field) != run.get(run_field)
                for evidence_field, run_field in run_fields.items()
            ):
                raise PlanError("attribution evidence does not match its run")
            linked = run.get("pull_requests")
            if not isinstance(linked, list) or not any(
                isinstance(item, Mapping)
                and item.get("number") == pr_by_id[pr_id].get("number")
                for item in linked
            ):
                raise PlanError("attribution run is not linked to its pull request")
            job = job_by_identity.get((int(run_id), int(job_id)))
            if (
                job is None
                or bound.get("job_name") != job.get("name")
                or bound.get("job_status") != job.get("status")
                or bound.get("job_conclusion") != job.get("conclusion")
                or bound.get("job_started_at") != job.get("started_at")
                or bound.get("job_completed_at") != job.get("completed_at")
            ):
                raise PlanError("attribution evidence does not match its job")
            steps = job.get("steps")
            matching_steps = (
                [
                    step
                    for step in steps
                    if isinstance(step, Mapping)
                    and step.get("number") == bound.get("step_number")
                ]
                if isinstance(steps, list)
                else []
            )
            if len(matching_steps) != 1:
                raise PlanError("attribution evidence lacks one captured step")
            step = matching_steps[0]
            step_fields = {
                "step_name": "name",
                "step_status": "status",
                "step_conclusion": "conclusion",
                "step_started_at": "started_at",
                "step_completed_at": "completed_at",
            }
            if any(
                bound.get(evidence_field) != step.get(step_field)
                for evidence_field, step_field in step_fields.items()
            ):
                raise PlanError("attribution evidence does not match its step")


def _normalize_auto_merge_inventory(inventory: Mapping[str, Any]) -> dict[str, Any]:
    pull_requests = _sorted_json_records(
        inventory.get("pull_requests", []),
        key=lambda row: (str(row.get("node_id", "")), int(row.get("number", 0))),
    )
    for pr in pull_requests:
        required = (
            "node_id",
            "number",
            "state",
            "is_draft",
            "base_ref_name",
            "head_ref_name",
            "head_ref_oid",
            "repository",
            "base_repository",
            "head_repository",
            "auto_merge_request",
        )
        if any(field not in pr for field in required):
            raise PlanError("auto-merge pull request lacks an exact tuple field")
    connections = _validate_complete_connections(inventory.get("connections", []))
    connection_keys = [
        (str(row.get("kind", "")), str(row.get("label_name", "")))
        for row in connections
    ]
    if len(connection_keys) != len(set(connection_keys)) or (
        "open_pull_requests",
        "",
    ) not in set(connection_keys):
        raise PlanError("auto-merge inventory lacks one exact open-PR connection")
    open_pr_connection = next(
        row for row in connections if row["kind"] == "open_pull_requests"
    )
    if open_pr_connection["count"] < len(pull_requests):
        raise PlanError("open-PR connection is smaller than captured enrollments")
    attribution = _sorted_json_records(
        inventory.get("attribution", []),
        key=lambda row: str(row.get("pull_request_node_id", "")),
    )
    workflow_jobs = _sorted_json_records(
        inventory.get("workflow_jobs", []),
        key=lambda row: (int(row.get("run_id", 0)), int(row.get("id", 0))),
    )
    source_history = copy.deepcopy(inventory.get("source_history"))
    _validate_auto_merge_attribution_bindings(
        pull_requests=pull_requests,
        connections=connections,
        workflow_runs=inventory.get("workflow_runs"),
        workflow_jobs=workflow_jobs,
        source_history=source_history,
        attribution=attribution,
    )
    planned_actions = _normalize_planned_actions(
        inventory.get("planned_actions", [])
    )
    apply_complete = inventory.get("apply_complete") is True
    if apply_complete:
        workflow = inventory.get("workflow")
        if not isinstance(workflow, Mapping) or {
            "id": workflow.get("id"),
            "path": workflow.get("path"),
            "state": workflow.get("state"),
        } != {
            "id": AUTO_ENROLL_WORKFLOW_ID,
            "path": ".github/workflows/auto-enroll-merge.yml",
            "state": "disabled_manually",
        } or not workflow.get("node_id"):
            raise PlanError("complete plan does not bind the disabled workflow identity")
        workflow_runs = inventory.get("workflow_runs")
        if not isinstance(workflow_runs, list):
            raise PlanError("complete plan lacks the workflow-run inventory")
        run_connection = [
            row for row in connections if row["kind"] == "workflow_runs"
        ]
        if (
            len(run_connection) != 1
            or run_connection[0]["label_name"] != ""
            or run_connection[0]["count"] != len(workflow_runs)
        ):
            raise PlanError("complete plan lacks one complete workflow-run connection")
        run_ids: set[int] = set()
        for run in workflow_runs:
            if (
                not isinstance(run, Mapping)
                or not isinstance(run.get("id"), int)
                or not isinstance(run.get("status"), str)
            ):
                raise PlanError("workflow run lacks exact id/status")
            if run["id"] in run_ids:
                raise PlanError("workflow-run inventory contains duplicate IDs")
            run_ids.add(run["id"])
            if run["status"] != "completed":
                raise PlanError(
                    "workflow-run inventory contains a nonterminal or unknown status"
                )
        expected_source_history = {
            "source_commit": None,
            "source_commit_status": "unavailable_from_stable_api",
            "default_branch": "main",
            "workflow_path": AUTO_ENROLL_WORKFLOW_PATH,
            "path_introduction_commit": AUTO_ENROLL_PATH_INTRODUCTION_COMMIT,
            "active_blob_sha": TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHA,
            "mapping_basis": "unchanged-default-branch-path-history",
            "commits": [
                {
                    "sha": AUTO_ENROLL_PATH_INTRODUCTION_COMMIT,
                    "committed_at": "2026-07-22T00:38:24Z",
                }
            ],
        }
        if source_history != expected_source_history:
            raise PlanError("complete plan lacks the reviewed workflow source history")
        source_connections = [
            row for row in connections if row["kind"] == "workflow_source_history"
        ]
        if (
            len(source_connections) != 1
            or source_connections[0]["label_name"] != AUTO_ENROLL_WORKFLOW_PATH
            or source_connections[0]["count"] != 1
        ):
            raise PlanError("complete plan lacks one workflow source-history connection")
        job_by_identity: dict[tuple[int, int], dict[str, Any]] = {}
        jobs_per_run: dict[int, int] = {}
        for job in workflow_jobs:
            run_id = job.get("run_id")
            job_id = job.get("id")
            if not _is_integer(run_id) or not _is_integer(job_id):
                raise PlanError("workflow job lacks exact run/job identity")
            identity = (run_id, job_id)
            if identity in job_by_identity:
                raise PlanError("workflow-job inventory contains duplicate identities")
            job_by_identity[identity] = job
            jobs_per_run[run_id] = jobs_per_run.get(run_id, 0) + 1
        job_connections = {
            int(row["label_name"]): row
            for row in connections
            if row["kind"] == "workflow_jobs" and row["label_name"].isdigit()
        }
        if set(job_connections) != set(jobs_per_run) or any(
            job_connections[run_id]["count"] != count
            for run_id, count in jobs_per_run.items()
        ):
            raise PlanError("complete plan lacks exact workflow-job connections")
        quiescence = inventory.get("quiescence")
        if not isinstance(quiescence, Mapping):
            raise PlanError("complete plan lacks ordered quiescence evidence")
        disabled_at = _parse_time(quiescence.get("workflow_disabled_verified_at"))
        scanned_at = _parse_time(quiescence.get("runs_scanned_at"))
        if (
            disabled_at is None
            or scanned_at is None
            or disabled_at > scanned_at
        ):
            raise PlanError("workflow disable must be verified before the run scan")
        pr_by_id = {str(row["node_id"]): row for row in pull_requests}
        run_by_id = {int(row["id"]): row for row in workflow_runs}
        if len(pr_by_id) != len(pull_requests):
            raise PlanError("auto-merge inventory contains duplicate pull requests")
        attr_by_id = {
            str(row.get("pull_request_node_id")): row for row in attribution
        }
        if len(attr_by_id) != len(attribution) or set(attr_by_id) != set(pr_by_id):
            raise PlanError("complete auto-merge plan requires one attribution per PR")
        if any(
            row.get("classification") not in {"attributed", "explicit_preserve"}
            for row in attribution
        ):
            raise PlanError("complete auto-merge plan contains ambiguity")
        for pr_id, row in attr_by_id.items():
            evidence = row.get("evidence")
            if not isinstance(evidence, list):
                raise PlanError("auto-merge attribution evidence must be an array")
            recomputed = classify_auto_merge(pr_by_id[pr_id], evidence)
            if (
                row.get("classification") != recomputed["classification"]
                or canonical_bytes(evidence)
                != canonical_bytes(recomputed["evidence"])
            ):
                raise PlanError(
                    "auto-merge attribution is not proven by its bound evidence"
                )
            if row.get("classification") == "attributed" and (
                len(evidence) != 1
                or evidence[0].get("run_id") not in run_ids
            ):
                raise PlanError("attribution is not bound to a captured workflow run")
            if row.get("classification") == "attributed":
                bound = evidence[0]
                run = run_by_id[int(bound["run_id"])]
                run_fields = {
                    "workflow_id": "workflow_id",
                    "workflow_path": "path",
                    "event": "event",
                    "run_status": "status",
                    "conclusion": "conclusion",
                    "head_sha": "head_sha",
                    "run_created_at": "created_at",
                    "run_updated_at": "updated_at",
                    "run_url": "html_url",
                }
                if any(
                    bound.get(evidence_field) != run.get(run_field)
                    for evidence_field, run_field in run_fields.items()
                ):
                    raise PlanError(
                        "attribution evidence does not match its captured workflow run"
                    )
                linked_pull_requests = run.get("pull_requests")
                if not isinstance(linked_pull_requests, list) or not any(
                    isinstance(linked, Mapping)
                    and linked.get("number") == pr_by_id[pr_id].get("number")
                    for linked in linked_pull_requests
                ):
                    raise PlanError(
                        "captured workflow run is not linked to the attributed pull request"
                    )
                job = job_by_identity.get(
                    (int(bound["run_id"]), int(bound.get("job_id", -1)))
                )
                if (
                    job is None
                    or bound.get("job_name") != job.get("name")
                    or bound.get("job_status") != job.get("status")
                    or bound.get("job_conclusion") != job.get("conclusion")
                    or bound.get("job_started_at") != job.get("started_at")
                    or bound.get("job_completed_at") != job.get("completed_at")
                ):
                    raise PlanError(
                        "attribution evidence does not match its captured workflow job"
                    )
                steps = job.get("steps")
                matching_steps = [
                    step
                    for step in steps
                    if isinstance(steps, list)
                    and isinstance(step, Mapping)
                    and step.get("number") == bound.get("step_number")
                ] if isinstance(steps, list) else []
                if len(matching_steps) != 1:
                    raise PlanError(
                        "attribution evidence lacks one captured workflow step"
                    )
                step = matching_steps[0]
                step_fields = {
                    "step_name": "name",
                    "step_status": "status",
                    "step_conclusion": "conclusion",
                    "step_started_at": "started_at",
                    "step_completed_at": "completed_at",
                }
                if any(
                    bound.get(evidence_field) != step.get(step_field)
                    for evidence_field, step_field in step_fields.items()
                ):
                    raise PlanError(
                        "attribution evidence does not match its captured workflow step"
                    )
        attributed_ids = {
            pr_id
            for pr_id, row in attr_by_id.items()
            if row["classification"] == "attributed"
        }
        action_ids: set[str] = set()
        for action in planned_actions:
            if action["kind"] != "disable_auto_merge":
                raise PlanError("auto-merge plan contains an unrelated action kind")
            target = str(action["target_node_id"])
            if target not in attributed_ids or target in action_ids:
                raise PlanError(
                    "auto-merge action targets an explicit, ambiguous, or duplicate PR"
                )
            expected_before = pr_by_id[target]
            expected_after = copy.deepcopy(expected_before)
            expected_after["auto_merge_request"] = None
            if (
                action["planned_before"] != expected_before
                or action["planned_after"] != expected_after
            ):
                raise PlanError("auto-merge action does not bind the full exact PR tuple")
            action_ids.add(target)
        if action_ids != attributed_ids:
            raise PlanError("complete auto-merge plan lacks an attributed PR action")
    return {
        "pull_requests": pull_requests,
        "connections": connections,
        "workflow": copy.deepcopy(inventory.get("workflow")),
        "workflow_runs": _sorted_json_records(
            inventory.get("workflow_runs", []),
            key=lambda row: int(row.get("id", 0)),
        ),
        "workflow_jobs": workflow_jobs,
        "source_history": source_history,
        "attribution": attribution,
        "quiescence": copy.deepcopy(inventory.get("quiescence")),
        "planned_actions": planned_actions,
        "apply_complete": apply_complete,
    }


def _validate_auto_merge_repository_binding(
    inventory: Mapping[str, Any], repo: Mapping[str, Any]
) -> None:
    expected = {
        "id": repo["node_id"],
        "nameWithOwner": repo["name_with_owner"],
    }
    for pull_request in inventory.get("pull_requests", []):
        if any(
            pull_request.get(field) != expected
            for field in ("repository", "base_repository", "head_repository")
        ):
            raise PlanError(
                "auto-merge pull request repository tuple is not receipt-bound"
            )


def build_receipt(
    *,
    operation: str,
    repo: Mapping[str, Any],
    source_revision: str,
    inventory: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the deterministic dry-run receipt for an exact inventory."""

    if operation not in OPERATIONS:
        raise PlanError(f"unsupported operation {operation!r}")
    if not source_revision:
        raise PlanError("source_revision is required")
    normalized_repo = _validate_repo(repo)
    normalized_inventory = (
        _normalize_label_inventory(inventory)
        if operation == LABEL_OPERATION
        else _normalize_auto_merge_inventory(inventory)
    )
    if operation == AUTO_MERGE_OPERATION:
        _validate_auto_merge_repository_binding(normalized_inventory, normalized_repo)
    plan = {
        "operation": operation,
        "repo": normalized_repo,
        "source_revision": source_revision,
        "inventory": normalized_inventory,
    }
    plan_digest = digest(plan)
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "operation": operation,
        "repo": normalized_repo,
        "source_revision": source_revision,
        "plan": plan,
        "plan_digest": plan_digest,
        "apply_key": derive_apply_key(operation, normalized_repo["node_id"], plan_digest),
        "execution": {"mode": "dry_run", "status": "planned"},
    }
    receipt["receipt_digest"] = digest(receipt)
    return receipt


def verify_receipt(receipt: Mapping[str, Any]) -> None:
    if receipt.get("schema") != SCHEMA or receipt.get("schema_version") != SCHEMA_VERSION:
        raise PlanError("unsupported receipt schema")
    operation = receipt.get("operation")
    if operation not in OPERATIONS:
        raise PlanError("unsupported receipt operation")
    plan = receipt.get("plan")
    if not isinstance(plan, Mapping) or digest(plan) != receipt.get("plan_digest"):
        raise PlanError("receipt plan digest mismatch")
    repo = _validate_repo(receipt.get("repo", {}))
    source_revision = receipt.get("source_revision")
    if not isinstance(source_revision, str) or not source_revision:
        raise PlanError("receipt source revision is required")
    if plan.get("operation") != operation:
        raise PlanError("top-level operation does not match the bound plan")
    if plan.get("repo") != repo:
        raise PlanError("top-level repository does not match the bound plan")
    if plan.get("source_revision") != source_revision:
        raise PlanError("top-level source revision does not match the bound plan")
    normalized_inventory = (
        _normalize_label_inventory(plan.get("inventory", {}))
        if operation == LABEL_OPERATION
        else _normalize_auto_merge_inventory(plan.get("inventory", {}))
    )
    if operation == AUTO_MERGE_OPERATION:
        _validate_auto_merge_repository_binding(normalized_inventory, repo)
    expected_plan = {
        "operation": operation,
        "repo": repo,
        "source_revision": source_revision,
        "inventory": normalized_inventory,
    }
    if canonical_bytes(plan) != canonical_bytes(expected_plan):
        raise PlanError("receipt plan is not the normalized operation schema")
    expected_key = derive_apply_key(operation, repo["node_id"], receipt["plan_digest"])
    if receipt.get("apply_key") != expected_key:
        raise PlanError("receipt apply key mismatch")
    if digest(_without(receipt, "receipt_digest")) != receipt.get("receipt_digest"):
        raise PlanError("terminal receipt digest mismatch")
    expected_receipt = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "operation": operation,
        "repo": repo,
        "source_revision": source_revision,
        "plan": expected_plan,
        "plan_digest": digest(expected_plan),
        "apply_key": expected_key,
        "execution": {"mode": "dry_run", "status": "planned"},
    }
    expected_receipt["receipt_digest"] = digest(expected_receipt)
    if canonical_bytes(receipt) != canonical_bytes(expected_receipt):
        raise PlanError("receipt envelope is not the normalized dry-run schema")


def atomically_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write canonical bytes and fsync both file and containing directory."""

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(canonical_bytes(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        if os.name != "nt":
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


class MigrationJournal:
    """Durable restart authority for retirement mutations."""

    _RUN_STATES = (
        "'planned','applying','host_review','complete','failed'"
    )
    _INTENT_STATES = (
        "'intent_persisted','pre_read_authorized','succeeded',"
        "'succeeded_after_restart','stale_needs_replan','host_review','failed'"
    )

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextlib.contextmanager
    def _session(self):
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self._session() as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS migration_runs (
                    apply_key TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL CHECK(schema_version = 1),
                    operation TEXT NOT NULL CHECK(operation IN (
                        '{LABEL_OPERATION}','{AUTO_MERGE_OPERATION}'
                    )),
                    repo_node_id TEXT NOT NULL,
                    plan_digest TEXT NOT NULL,
                    plan_json BLOB NOT NULL,
                    phase TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ({self._RUN_STATES})),
                    final_json BLOB,
                    final_digest TEXT,
                    executor_token TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mutation_intents (
                    apply_key TEXT NOT NULL REFERENCES migration_runs(apply_key),
                    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
                    action_kind TEXT NOT NULL,
                    target_node_id TEXT NOT NULL,
                    planned_before_digest TEXT NOT NULL,
                    planned_before_json BLOB NOT NULL,
                    planned_after_digest TEXT NOT NULL,
                    planned_after_json BLOB NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ({self._INTENT_STATES})),
                    preread_digest TEXT,
                    preread_json BLOB,
                    client_mutation_id TEXT NOT NULL,
                    postread_digest TEXT,
                    postread_json BLOB,
                    outcome TEXT,
                    error_class TEXT,
                    PRIMARY KEY(apply_key, ordinal),
                    UNIQUE(apply_key, action_kind, target_node_id)
                );
                """
            )

    def claim_apply(
        self, apply_key: str, executor_token: str, *, recovery_authorized: bool
    ) -> None:
        """Serialize an apply run.

        A crashed/incomplete run remains blocked until an operator explicitly
        authorizes recovery.  That is conservative because GitHub mutations do
        not offer an expected-state CAS.
        """

        now = dt.datetime.now(dt.timezone.utc).isoformat()
        with self._session() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status FROM migration_runs WHERE apply_key = ?",
                (apply_key,),
            ).fetchone()
            if row is None:
                raise JournalConflict("apply plan is not registered")
            if row["status"] != "planned" and not (
                recovery_authorized
                and row["status"] in {"host_review", "failed"}
            ):
                raise ApplyBlocked(
                    f"apply journal is {row['status']}; explicit recovery is required"
                )
            conn.execute(
                """
                UPDATE migration_runs
                   SET phase = 'mutations', status = 'applying',
                       executor_token = ?, updated_at = ?
                 WHERE apply_key = ?
                """,
                (executor_token, now, apply_key),
            )

    def mark_executor_abandoned(
        self, apply_key: str, expected_executor_token: str
    ) -> None:
        """Fence a proven-dead executor before recovery is allowed.

        This has no command-line surface. A future operator flow must prove the
        executor has stopped before invoking it with the exact old token.
        """

        now = dt.datetime.now(dt.timezone.utc).isoformat()
        with self._session() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                UPDATE migration_runs
                   SET phase = 'host_review', status = 'host_review',
                       executor_token = NULL, updated_at = ?
                 WHERE apply_key = ? AND status = 'applying'
                   AND executor_token = ?
                """,
                (now, apply_key, expected_executor_token),
            )
            if cursor.rowcount != 1:
                raise JournalConflict("abandoned executor token does not match")

    def finish_apply(
        self, apply_key: str, executor_token: str, *, status: str
    ) -> None:
        if status not in {"complete", "host_review", "failed"}:
            raise ValueError("invalid terminal apply status")
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        with self._session() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute(
                """
                UPDATE migration_runs
                   SET phase = ?, status = ?, executor_token = NULL, updated_at = ?
                 WHERE apply_key = ? AND executor_token = ? AND status = 'applying'
                """,
                (status, status, now, apply_key, executor_token),
            )
            if cursor.rowcount != 1:
                raise JournalConflict("apply executor lost its journal claim")

    def register(self, receipt: Mapping[str, Any]) -> None:
        verify_receipt(receipt)
        plan_bytes = canonical_bytes(receipt["plan"])
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        with self._session() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT plan_digest, plan_json FROM migration_runs WHERE apply_key = ?",
                (receipt["apply_key"],),
            ).fetchone()
            if row is not None:
                if (
                    row["plan_digest"] != receipt["plan_digest"]
                    or bytes(row["plan_json"]) != plan_bytes
                ):
                    raise JournalConflict("apply key already binds a different immutable plan")
                return
            conn.execute(
                """
                INSERT INTO migration_runs (
                    apply_key, schema_version, operation, repo_node_id,
                    plan_digest, plan_json, phase, status, created_at, updated_at
                ) VALUES (?, 1, ?, ?, ?, ?, 'planned', 'planned', ?, ?)
                """,
                (
                    receipt["apply_key"],
                    receipt["operation"],
                    receipt["repo"]["node_id"],
                    receipt["plan_digest"],
                    plan_bytes,
                    now,
                    now,
                ),
            )

    def persist_intent(
        self,
        *,
        apply_key: str,
        executor_token: str,
        ordinal: int,
        action_kind: str,
        target_node_id: str,
        planned_before: Mapping[str, Any],
        planned_after: Mapping[str, Any],
    ) -> tuple[str, str | None]:
        before_json = canonical_bytes(planned_before)
        after_json = canonical_bytes(planned_after)
        client_id = hashlib.sha256(
            canonical_bytes(
                {
                    "apply_key": apply_key,
                    "ordinal": ordinal,
                    "action_kind": action_kind,
                    "target_node_id": target_node_id,
                    "planned_before_digest": digest(planned_before),
                }
            )
        ).hexdigest()
        immutable = (
            action_kind,
            target_node_id,
            digest(planned_before),
            before_json,
            digest(planned_after),
            after_json,
            client_id,
        )
        with self._session() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._assert_executor(conn, apply_key, executor_token)
            row = conn.execute(
                "SELECT * FROM mutation_intents WHERE apply_key = ? AND ordinal = ?",
                (apply_key, ordinal),
            ).fetchone()
            if row is not None:
                existing = (
                    row["action_kind"],
                    row["target_node_id"],
                    row["planned_before_digest"],
                    bytes(row["planned_before_json"]),
                    row["planned_after_digest"],
                    bytes(row["planned_after_json"]),
                    row["client_mutation_id"],
                )
                if existing != immutable:
                    raise JournalConflict("mutation intent cannot be overwritten")
                return client_id, str(row["state"])
            conn.execute(
                """
                INSERT INTO mutation_intents (
                    apply_key, ordinal, action_kind, target_node_id,
                    planned_before_digest, planned_before_json,
                    planned_after_digest, planned_after_json, state,
                    client_mutation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'intent_persisted', ?)
                """,
                (apply_key, ordinal, *immutable),
            )
        return client_id, None

    @staticmethod
    def _assert_executor(
        conn: sqlite3.Connection, apply_key: str, executor_token: str
    ) -> None:
        row = conn.execute(
            """
            SELECT status, executor_token
              FROM migration_runs
             WHERE apply_key = ?
            """,
            (apply_key,),
        ).fetchone()
        if (
            row is None
            or row["status"] != "applying"
            or row["executor_token"] != executor_token
        ):
            raise JournalConflict("journal write rejected for stale apply executor")

    def set_pre_read(
        self,
        apply_key: str,
        executor_token: str,
        ordinal: int,
        value: Mapping[str, Any],
        state: str,
    ) -> None:
        if state not in {"pre_read_authorized", "stale_needs_replan", "host_review"}:
            raise ValueError("invalid pre-read state")
        with self._session() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._assert_executor(conn, apply_key, executor_token)
            cursor = conn.execute(
                """
                UPDATE mutation_intents
                   SET preread_digest = ?, preread_json = ?, state = ?
                 WHERE apply_key = ? AND ordinal = ?
                """,
                (digest(value), canonical_bytes(value), state, apply_key, ordinal),
            )
            if cursor.rowcount != 1:
                raise JournalConflict("pre-read intent row is missing")

    def set_outcome(
        self,
        apply_key: str,
        executor_token: str,
        ordinal: int,
        value: Mapping[str, Any],
        *,
        state: str,
        outcome: str,
        error_class: str | None = None,
    ) -> None:
        if state not in {
            "succeeded",
            "succeeded_after_restart",
            "host_review",
            "failed",
        }:
            raise ValueError("invalid outcome state")
        with self._session() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._assert_executor(conn, apply_key, executor_token)
            cursor = conn.execute(
                """
                UPDATE mutation_intents
                   SET postread_digest = ?, postread_json = ?, state = ?,
                       outcome = ?, error_class = ?
                 WHERE apply_key = ? AND ordinal = ?
                """,
                (
                    digest(value),
                    canonical_bytes(value),
                    state,
                    outcome,
                    error_class,
                    apply_key,
                    ordinal,
                ),
            )
            if cursor.rowcount != 1:
                raise JournalConflict("outcome intent row is missing")

    def intent_rows(self, apply_key: str) -> list[dict[str, Any]]:
        with self._session() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM mutation_intents WHERE apply_key = ? ORDER BY ordinal",
                    (apply_key,),
                )
            ]


def verify_apply_authority(
    receipt: Mapping[str, Any],
    proof: Mapping[str, Any],
    *,
    apply_key: str,
    confirm_plan_digest: str,
) -> None:
    """Fail closed unless the exact quiescence proof authorizes this plan."""

    verify_receipt(receipt)
    failures: list[str] = []
    if apply_key != receipt["apply_key"]:
        failures.append("apply key does not match the body-bound receipt")
    if confirm_plan_digest != receipt["plan_digest"]:
        failures.append("confirmed plan digest does not match")
    if proof.get("repo") != receipt["repo"]:
        failures.append("repository identity drifted")
    if proof.get("source_revision") != receipt["source_revision"]:
        failures.append("source revision drifted")
    if proof.get("permission") not in {"ADMIN", "MAINTAIN"}:
        failures.append("ADMIN or MAINTAIN permission is required")
    for field in (
        "required_endpoint_capability",
        "all_producers_removed",
        "runs_drained",
        "pagination_complete",
    ):
        if proof.get(field) is not True:
            failures.append(f"{field} is not proven")
    if int(proof.get("ambiguity_count", -1)) != 0:
        failures.append("ambiguity remains")
    if receipt["operation"] == LABEL_OPERATION:
        if proof.get("task_4_2_complete") is not True:
            failures.append("OpenSpec task 4.2 is incomplete")
        if proof.get("all_label_consumers_removed") is not True:
            failures.append("retired-label consumers remain")
    else:
        if proof.get("workflow_id") != AUTO_ENROLL_WORKFLOW_ID:
            failures.append("wrong auto-enroll workflow identity")
        if proof.get("workflow_state") != "disabled_manually":
            failures.append("auto-enroll workflow is not disabled_manually")
        inventory = receipt["plan"]["inventory"]
        pr_ids = {str(row["node_id"]) for row in inventory["pull_requests"]}
        attribution = inventory["attribution"]
        attributed_ids = {
            str(row.get("pull_request_node_id")) for row in attribution
        }
        if attributed_ids != pr_ids:
            failures.append("auto-merge attribution is incomplete")
        if any(
            row.get("classification") not in {"attributed", "explicit_preserve"}
            for row in attribution
        ):
            failures.append("auto-merge attribution remains ambiguous")
    if receipt["plan"]["inventory"].get("apply_complete") is not True:
        failures.append("receipt is an inventory-only plan, not a complete apply plan")
    if failures:
        raise ApplyBlocked("; ".join(failures))


class ExactReader(Protocol):
    def read_exact(self, action: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


class Mutator(Protocol):
    def mutate(self, action: Mapping[str, Any], client_mutation_id: str) -> None:
        ...


def apply_actions(
    *,
    receipt: Mapping[str, Any],
    proof: Mapping[str, Any],
    apply_key: str,
    confirm_plan_digest: str,
    actions: Sequence[Mapping[str, Any]],
    journal: MigrationJournal,
    reader: ExactReader,
    mutator: Mutator,
    proof_refresher: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    recovery_authorized: bool = False,
) -> None:
    """Apply exact injected actions after durable intent and immediate reads.

    There is intentionally no live ``Mutator`` implementation in this module.
    """

    verify_apply_authority(
        receipt,
        proof,
        apply_key=apply_key,
        confirm_plan_digest=confirm_plan_digest,
    )
    planned_actions = receipt["plan"]["inventory"].get("planned_actions", [])
    if canonical_bytes(list(actions)) != canonical_bytes(planned_actions):
        raise ApplyBlocked("requested actions do not exactly match the receipt plan")
    journal.register(receipt)
    executor_token = uuid.uuid4().hex
    journal.claim_apply(
        apply_key, executor_token, recovery_authorized=recovery_authorized
    )
    try:
        for ordinal, raw_action in enumerate(actions):
            action = copy.deepcopy(dict(raw_action))
            before = action["planned_before"]
            after = action["planned_after"]
            fresh_proof = proof_refresher(action)
            if not isinstance(fresh_proof, Mapping):
                raise ApplyBlocked("per-action authority proof is unavailable")
            verify_apply_authority(
                receipt,
                fresh_proof,
                apply_key=apply_key,
                confirm_plan_digest=confirm_plan_digest,
            )
            client_id, prior_intent_state = journal.persist_intent(
                apply_key=apply_key,
                executor_token=executor_token,
                ordinal=ordinal,
                action_kind=str(action["kind"]),
                target_node_id=str(action["target_node_id"]),
                planned_before=before,
                planned_after=after,
            )
            current = dict(reader.read_exact(action))
            if prior_intent_state in {"succeeded", "succeeded_after_restart"}:
                if digest(current) == digest(after):
                    continue
                raise ApplyBlocked(
                    f"terminal target {action['target_node_id']} changed after success"
                )
            if prior_intent_state in {
                "host_review",
                "stale_needs_replan",
                "failed",
            }:
                raise ApplyBlocked(
                    f"target {action['target_node_id']} requires a fresh plan"
                )
            if digest(current) == digest(after):
                if prior_intent_state != "pre_read_authorized":
                    journal.set_pre_read(
                        apply_key,
                        executor_token,
                        ordinal,
                        current,
                        "host_review",
                    )
                    raise ApplyBlocked(
                        f"target {action['target_node_id']} lacks a prior "
                        "mutation-authorizing intent"
                    )
                journal.set_outcome(
                    apply_key,
                    executor_token,
                    ordinal,
                    current,
                    state="succeeded_after_restart",
                    outcome="already_matches_planned_after",
                )
                continue
            if digest(current) != digest(before):
                journal.set_pre_read(
                    apply_key,
                    executor_token,
                    ordinal,
                    current,
                    "stale_needs_replan",
                )
                raise ApplyBlocked(
                    f"target {action['target_node_id']} changed before mutation"
                )
            journal.set_pre_read(
                apply_key,
                executor_token,
                ordinal,
                current,
                "pre_read_authorized",
            )
            mutator.mutate(action, client_id)
            post = dict(reader.read_exact(action))
            if digest(post) != digest(after):
                journal.set_outcome(
                    apply_key,
                    executor_token,
                    ordinal,
                    post,
                    state="host_review",
                    outcome="post_read_mismatch",
                    error_class="REMOTE_STATE_AMBIGUOUS",
                )
                raise ApplyBlocked(
                    f"target {action['target_node_id']} did not reach planned state"
                )
            journal.set_outcome(
                apply_key,
                executor_token,
                ordinal,
                post,
                state="succeeded",
                outcome="post_read_verified",
            )
    except Exception:
        journal.finish_apply(apply_key, executor_token, status="host_review")
        raise
    journal.finish_apply(apply_key, executor_token, status="complete")


def _parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _is_safe_log_member_name(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > 1_024:
        return False
    path = Path(value)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and not value.endswith(("/", "\\"))
    )


def classify_auto_merge(
    pr: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Classify an enrollment without granting authority from actor alone."""

    request = pr.get("auto_merge_request")
    if not request:
        return {"classification": "none", "evidence": []}
    actor = request.get("enabled_by") or {}
    if actor.get("__typename") == "User":
        return {"classification": "explicit_preserve", "evidence": []}
    if (
        actor.get("__typename") != "Bot"
        or actor.get("login") != GITHUB_ACTIONS_BOT_LOGIN
        or actor.get("id") != GITHUB_ACTIONS_BOT_NODE_ID
    ):
        return {"classification": "ambiguous_preserve", "evidence": []}
    eligible = (
        pr.get("state") == "OPEN"
        and pr.get("is_draft") is False
        and pr.get("base_ref_name") == "main"
        and pr.get("repository") == pr.get("base_repository") == pr.get("head_repository")
    )
    if not eligible:
        return {"classification": "ambiguous_preserve", "evidence": []}
    enabled_at = _parse_time(request.get("enabled_at"))
    matches: list[dict[str, Any]] = []
    unavailable = [
        copy.deepcopy(dict(row))
        for row in evidence
        if row.get("evidence_status") == "log_unavailable"
    ]
    for row in evidence:
        run_start = _parse_time(row.get("run_created_at"))
        run_end = _parse_time(row.get("run_updated_at"))
        job_start = _parse_time(row.get("job_started_at"))
        job_end = _parse_time(row.get("job_completed_at"))
        step_start = _parse_time(row.get("step_started_at"))
        step_end = _parse_time(row.get("step_completed_at"))
        if (
            enabled_at is not None
            and row.get("workflow_id") == AUTO_ENROLL_WORKFLOW_ID
            and row.get("event") == "pull_request_target"
            and row.get("run_status") == "completed"
            and row.get("conclusion") == "success"
            and row.get("pull_request_number") == pr.get("number")
            and isinstance(row.get("head_sha"), str)
            and bool(row.get("head_sha"))
            and row.get("current_head_sha") == pr.get("head_ref_oid")
            and row.get("job_name") == "Enroll for auto-merge"
            and row.get("step_name") == "Enable auto-merge"
            and row.get("job_status") == "completed"
            and row.get("job_conclusion") == "success"
            and row.get("step_status") == "completed"
            and row.get("step_conclusion") == "success"
            and _is_integer(row.get("run_id"))
            and _is_integer(row.get("job_id"))
            and _is_integer(row.get("step_number"))
            and row.get("workflow_path") == AUTO_ENROLL_WORKFLOW_PATH
            and row.get("workflow_blob_shas")
            == list(TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHAS)
            and row.get("workflow_blobs_verified") is True
            and row.get("historical_source_commit_status")
            == "unavailable_from_stable_api"
            and row.get("source_commit") is None
            and row.get("default_branch") == "main"
            and row.get("path_introduction_commit")
            == AUTO_ENROLL_PATH_INTRODUCTION_COMMIT
            and row.get("active_blob_sha")
            == TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHA
            and row.get("mapping_basis")
            == "unchanged-default-branch-path-history"
            and row.get("enrollment_source_identical_across_trusted_blobs") is True
            and isinstance(row.get("run_url"), str)
            and bool(row.get("run_url"))
            and row.get("source_contains_exact_auto_squash_command") is True
            and _is_sha256_hex(row.get("log_archive_sha256"))
            and _is_safe_log_member_name(row.get("log_member_name"))
            and _is_sha256_hex(row.get("log_member_sha256"))
            and _is_integer(row.get("log_matching_member_count"))
            and row.get("log_matching_member_count") == 1
            and row.get("log_pr_number_matches") is True
            and row.get("log_repo_matches") is True
            and row.get("log_contains_enrollment_success") is True
            and row.get("log_contains_exact_auto_squash_command") is True
            and all(
                stamp is not None
                for stamp in (
                    run_start,
                    run_end,
                    job_start,
                    job_end,
                    step_start,
                    step_end,
                )
            )
            and (
                run_start
                <= job_start
                <= step_start
                <= enabled_at
                <= step_end
                <= job_end
                <= run_end
            )
        ):
            matches.append(copy.deepcopy(dict(row)))
    if unavailable:
        return {
            "classification": "ambiguous_preserve",
            "evidence": [*matches, *unavailable],
        }
    if len(matches) == 1:
        return {"classification": "attributed", "evidence": matches}
    return {"classification": "ambiguous_preserve", "evidence": matches}


class ReadOnlyGitHub:
    """Structured read-only ``gh api`` adapter.  No caller supplies argv."""

    def __init__(
        self,
        repo: str,
        runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    ):
        if not re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9][A-Za-z0-9_.-]*",
            repo,
        ):
            raise ValueError("repo must be OWNER/NAME")
        self.repo = repo
        self._runner = runner
        self._repo_database_id: int | None = None

    def bind_repo_database_id(self, database_id: Any) -> None:
        if not _is_integer(database_id) or database_id <= 0:
            raise PlanError("repository database identity is invalid")
        if self._repo_database_id not in (None, database_id):
            raise PlanError("repository database identity changed during inventory")
        self._repo_database_id = int(database_id)

    def _validate_repo_endpoint(self, endpoint: str) -> str:
        if (
            not isinstance(endpoint, str)
            or not endpoint
            or any(character.isspace() for character in endpoint)
            or "\\" in endpoint
            or endpoint.startswith(("-", "@", "/", "http:", "https:"))
        ):
            raise ApplyBlocked("read-only GitHub client rejected an unsafe endpoint")
        path = urlsplit(endpoint).path
        root = f"repos/{self.repo}"
        if "%" in path:
            raise ApplyBlocked("read-only GitHub client rejected an encoded path")
        if path != root and not path.startswith(root + "/"):
            raise ApplyBlocked("read-only GitHub client rejected a cross-repository endpoint")
        if any(part in {"", ".", ".."} for part in path.split("/")):
            raise ApplyBlocked("read-only GitHub client rejected an ambiguous endpoint")
        return endpoint

    def _parse_included_json(
        self, completed: subprocess.CompletedProcess[Any]
    ) -> tuple[Any, dict[str, str]]:
        stdout = completed.stdout
        if not isinstance(stdout, str):
            raise RetirementError("GitHub read returned non-text output")
        parts = re.split(r"\r?\n\r?\n", stdout, maxsplit=1)
        if len(parts) != 2:
            raise RetirementError("GitHub read omitted response headers")
        header_text, body_text = parts
        header_lines = header_text.splitlines()
        if not header_lines or not re.fullmatch(
            r"HTTP/\S+\s+2\d\d(?:\s+.*)?", header_lines[0], flags=re.IGNORECASE
        ):
            raise RetirementError("GitHub read returned a non-success response")
        headers: dict[str, str] = {}
        for line in header_lines[1:]:
            if ":" not in line:
                raise RetirementError("GitHub read returned malformed response headers")
            name, value = line.split(":", 1)
            key = name.strip().lower()
            if not key or key in headers:
                raise RetirementError("GitHub read returned duplicate response headers")
            headers[key] = value.strip()
        try:
            return json.loads(body_text), headers
        except (json.JSONDecodeError, TypeError):
            raise RetirementError("GitHub read returned invalid JSON") from None

    def _rest_page(
        self, endpoint: str, *, linked: bool = False
    ) -> tuple[Any, dict[str, str]]:
        if not linked:
            endpoint = self._validate_repo_endpoint(endpoint)
        try:
            completed = self._runner(
                [
                    "gh",
                    "api",
                    "--hostname",
                    "github.com",
                    "--include",
                    "--method",
                    "GET",
                    endpoint,
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except subprocess.CalledProcessError as exc:
            raise RetirementError(
                f"GitHub read failed with exit status {exc.returncode}"
            ) from None
        except OSError:
            raise RetirementError("GitHub read process was unavailable") from None
        return self._parse_included_json(completed)

    @staticmethod
    def _next_link(link_header: str | None) -> str | None:
        if link_header is None:
            return None
        relationships: dict[str, str] = {}
        for part in link_header.split(","):
            match = re.fullmatch(
                r'\s*<([^>]+)>\s*;\s*rel="([^"]+)"\s*',
                part,
                flags=re.IGNORECASE,
            )
            if match is None:
                raise PlanError("GitHub Link header is malformed")
            url, relationship = match.groups()
            relationship = relationship.lower()
            if relationship in relationships:
                raise PlanError("GitHub Link header repeats a relationship")
            relationships[relationship] = url
        return relationships.get("next")

    def _validate_next_link(
        self, initial_endpoint: str, next_url: str, *, expected_page: int
    ) -> str:
        if self._repo_database_id is None:
            raise PlanError("repository database identity is not bound for pagination")
        parsed = urlsplit(next_url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "api.github.com"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or parsed.fragment
        ):
            raise PlanError("GitHub pagination left the trusted API origin")
        initial = urlsplit(initial_endpoint)
        prefix = f"repos/{self.repo}/"
        if not initial.path.startswith(prefix):
            raise PlanError("initial pagination endpoint is outside the repository")
        suffix = initial.path[len(prefix) :]
        if parsed.path != f"/repositories/{self._repo_database_id}/{suffix}":
            raise PlanError("GitHub pagination changed repository or endpoint scope")
        initial_pairs = sorted(parse_qsl(initial.query, keep_blank_values=True))
        next_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        page_values = [value for key, value in next_pairs if key == "page"]
        if page_values != [str(expected_page)]:
            raise PlanError("GitHub pagination did not advance one exact page")
        cursor_values = [value for key, value in next_pairs if key == "after"]
        if len(cursor_values) > 1 or any(not value for value in cursor_values):
            raise PlanError("GitHub pagination contains an invalid forward cursor")
        scoped_next = sorted(
            (key, value)
            for key, value in next_pairs
            if key not in {"after", "page"}
        )
        if scoped_next != initial_pairs:
            raise PlanError("GitHub pagination changed query scope")
        return next_url

    def bytes(self, endpoint: str) -> bytes:
        """Read one binary REST response without exposing a mutation option."""

        endpoint = self._validate_repo_endpoint(endpoint)
        try:
            completed = self._runner(
                [
                    "gh",
                    "api",
                    "--hostname",
                    "github.com",
                    "--method",
                    "GET",
                    endpoint,
                ],
                check=True,
                capture_output=True,
                text=False,
            )
        except subprocess.CalledProcessError as exc:
            raise RetirementError(
                f"GitHub binary read failed with exit status {exc.returncode}"
            ) from None
        except OSError:
            raise RetirementError("GitHub binary read process was unavailable") from None
        value = completed.stdout
        if not isinstance(value, bytes):
            raise RetirementError("GitHub binary read returned non-bytes output")
        return value

    def rest(self, endpoint: str) -> Any:
        value, _headers = self._rest_page(endpoint)
        return value

    def rest_array_collection(
        self, endpoint: str, *, max_pages: int = MAX_REST_PAGES
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Follow and receipt-bind one REST array's exact GitHub Link chain."""

        initial_endpoint = self._validate_repo_endpoint(endpoint)
        if not _is_integer(max_pages) or max_pages <= 0:
            raise ValueError("max_pages must be a positive integer")
        current_endpoint = initial_endpoint
        linked = False
        seen_urls: set[str] = set()
        seen_identities: set[tuple[str, Any]] = set()
        rows: list[dict[str, Any]] = []
        page_receipts: list[dict[str, Any]] = []
        while True:
            if len(page_receipts) >= max_pages:
                raise PlanError("GitHub pagination exceeded its page bound")
            if current_endpoint in seen_urls:
                raise PlanError("GitHub pagination contains a URL loop")
            seen_urls.add(current_endpoint)
            page, headers = self._rest_page(current_endpoint, linked=linked)
            if not isinstance(page, list) or any(
                not isinstance(row, Mapping) for row in page
            ):
                raise PlanError("paginated REST response page is not an object array")
            for row in page:
                if _is_integer(row.get("id")):
                    identity = ("id", int(row["id"]))
                elif isinstance(row.get("sha"), str) and row["sha"]:
                    identity = ("sha", row["sha"])
                elif isinstance(row.get("node_id"), str) and row["node_id"]:
                    identity = ("node_id", row["node_id"])
                else:
                    raise PlanError("paginated REST row lacks a stable identity")
                if identity in seen_identities:
                    raise PlanError("paginated REST response contains duplicate identities")
                seen_identities.add(identity)
                rows.append(copy.deepcopy(dict(row)))
            request_id = headers.get("x-github-request-id")
            if not request_id:
                raise PlanError("GitHub pagination response lacks a request identity")
            next_url = self._next_link(headers.get("link"))
            ordinal = len(page_receipts)
            page_receipts.append(
                {
                    "ordinal": ordinal,
                    "request_id": request_id,
                    "request_url_digest": digest(
                        {"method": "GET", "endpoint": current_endpoint}
                    ),
                    "response_body_digest": digest(page),
                    "item_count": len(page),
                    "next_url_digest": (
                        digest({"method": "GET", "endpoint": next_url})
                        if next_url
                        else None
                    ),
                }
            )
            if next_url is None:
                break
            current_endpoint = self._validate_next_link(
                initial_endpoint,
                next_url,
                expected_page=ordinal + 2,
            )
            linked = True
        return rows, {
            "pages": len(page_receipts),
            "count": len(rows),
            "total_count": None,
            "complete": True,
            "completion_basis": "github_link_header_chain_v1",
            "snapshot_consistency": "single_pass_live",
            "mutation_authority": False,
            "pagination": {
                "mode": "github_link_header_chain_v1",
                "page_receipts": page_receipts,
                "terminal": {
                    "oracle": "rel_next_absent",
                    "page_ordinal": len(page_receipts) - 1,
                },
            },
        }

    def rest_collection(
        self, endpoint: str, *, list_key: str
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Exhaust a REST object connection and validate its total count."""

        endpoint = self._validate_repo_endpoint(endpoint)
        try:
            completed = self._runner(
                [
                    "gh",
                    "api",
                    "--hostname",
                    "github.com",
                    "--method",
                    "GET",
                    "--paginate",
                    "--slurp",
                    endpoint,
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except subprocess.CalledProcessError as exc:
            raise RetirementError(
                f"GitHub read failed with exit status {exc.returncode}"
            ) from None
        except OSError:
            raise RetirementError("GitHub read process was unavailable") from None
        try:
            result = json.loads(completed.stdout)
        except (json.JSONDecodeError, TypeError):
            raise RetirementError("GitHub read returned invalid JSON") from None
        if not isinstance(result, list) or not result:
            raise PlanError("paginated REST object response has no pages")
        rows: list[dict[str, Any]] = []
        total: int | None = None
        for page in result:
            if not isinstance(page, Mapping):
                raise PlanError("paginated REST object page is not an object")
            page_rows = page.get(list_key)
            page_total = page.get("total_count")
            if (
                not isinstance(page_rows, list)
                or not _is_integer(page_total)
                or page_total < 0
                or any(not isinstance(row, Mapping) for row in page_rows)
            ):
                raise PlanError("paginated REST object page has an invalid shape")
            if total is None:
                total = page_total
            elif page_total != total:
                raise PlanError("paginated REST total_count changed between pages")
            rows.extend(copy.deepcopy(dict(row)) for row in page_rows)
        if len(rows) != total:
            raise PlanError(
                f"paginated REST count mismatch: observed {len(rows)}, expected {total}"
            )
        row_ids = [row.get("id") for row in rows]
        if any(not _is_integer(row_id) for row_id in row_ids):
            raise PlanError("paginated REST object row lacks an integer id")
        if len(row_ids) != len(set(row_ids)):
            raise PlanError("paginated REST object response contains duplicate ids")
        return rows, {
            "pages": len(result),
            "count": len(rows),
            "total_count": total,
            "complete": True,
            "completion_basis": "reported_total_count",
        }

    def graphql_pages(
        self, query: str, fields: Mapping[str, str]
    ) -> list[dict[str, Any]]:
        owner, name = self.repo.split("/", 1)
        if (
            query != AUTO_MERGE_QUERY
            or fields != {"owner": owner, "name": name}
            or any(value.startswith("@") for value in fields.values())
        ):
            raise ApplyBlocked("read-only GraphQL client rejected an unreviewed query")
        try:
            completed = self._runner(
                [
                    "gh",
                    "api",
                    "--hostname",
                    "github.com",
                    "graphql",
                    "--paginate",
                    "--slurp",
                    "-f",
                    f"query={AUTO_MERGE_QUERY}",
                    "-f",
                    f"owner={owner}",
                    "-f",
                    f"name={name}",
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except subprocess.CalledProcessError as exc:
            raise RetirementError(
                f"GitHub read failed with exit status {exc.returncode}"
            ) from None
        except OSError:
            raise RetirementError("GitHub read process was unavailable") from None
        try:
            result = json.loads(completed.stdout)
        except (json.JSONDecodeError, TypeError):
            raise RetirementError("GitHub read returned invalid JSON") from None
        if not isinstance(result, list) or any(not isinstance(page, dict) for page in result):
            raise PlanError("paginated GraphQL response was not an array of pages")
        return result


def collect_label_inventory(client: ReadOnlyGitHub) -> tuple[dict[str, Any], dict[str, Any]]:
    repo_raw = client.rest(f"repos/{client.repo}")
    client.bind_repo_database_id(repo_raw["id"])
    repo = {
        "node_id": repo_raw["node_id"],
        "database_id": repo_raw["id"],
        "name_with_owner": repo_raw["full_name"],
        "default_branch": repo_raw["default_branch"],
    }
    all_definitions, definition_connection = client.rest_array_collection(
        f"repos/{client.repo}/labels?per_page=100"
    )
    selected = {
        row["name"]: {
            "node_id": row["node_id"],
            "database_id": row["id"],
            "name": row["name"],
            "color": row["color"],
            "description": row.get("description"),
            "url": row.get("url"),
        }
        for row in all_definitions
        if row.get("name") in RETIRED_LABEL_SET
    }
    associations: dict[tuple[str, str], dict[str, Any]] = {}
    connections: list[dict[str, Any]] = [
        {
            "kind": "label_definitions",
            "label_name": "",
            **definition_connection,
        }
    ]
    for label_name in RETIRED_LABELS:
        rows, association_connection = client.rest_array_collection(
            f"repos/{client.repo}/issues?state=all&labels={quote(label_name, safe='')}&per_page=100"
        )
        connections.append(
            {
                "kind": "retired_label_associations",
                "label_name": label_name,
                **association_connection,
            }
        )
        definition = selected.get(label_name)
        if definition is None:
            continue
        for row in rows:
            item_node_id = row["node_id"]
            associations[(item_node_id, label_name)] = {
                "label_node_id": definition["node_id"],
                "label_name": label_name,
                "item_node_id": item_node_id,
                "number": row["number"],
                "kind": "pull_request" if "pull_request" in row else "issue",
                "state": row["state"],
                "url": row.get("html_url"),
            }
    return repo, {
        "definitions": list(selected.values()),
        "associations": list(associations.values()),
        "connections": connections,
        "planned_actions": [],
        "apply_complete": False,
    }


AUTO_MERGE_QUERY = """
query($owner:String!, $name:String!, $endCursor:String) {
  repository(owner:$owner, name:$name) {
    pullRequests(
      states:OPEN,
      first:100,
      after:$endCursor,
      orderBy:{field:CREATED_AT,direction:ASC}
    ) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        id number state isDraft baseRefName headRefName headRefOid
        repository { id nameWithOwner }
        baseRepository { id nameWithOwner }
        headRepository { id nameWithOwner }
        autoMergeRequest {
          enabledAt mergeMethod commitHeadline commitBody authorEmail
          enabledBy {
            __typename
            login
            ... on Bot { id }
            ... on EnterpriseUserAccount { id }
            ... on Mannequin { id }
            ... on Organization { id }
            ... on User { id }
          }
        }
      }
    }
  }
}
"""


def verify_trusted_workflow_blob(
    client: ReadOnlyGitHub,
    blob_sha: str = TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHA,
) -> dict[str, Any]:
    """Verify one reviewed workflow blob from its exact Git object bytes."""

    if blob_sha not in TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHAS:
        raise PlanError("workflow blob is outside the reviewed allowlist")
    raw = client.rest(f"repos/{client.repo}/git/blobs/{blob_sha}")
    if not isinstance(raw, Mapping):
        raise PlanError("workflow blob response is not an object")
    content = raw.get("content")
    size = raw.get("size")
    if (
        raw.get("sha") != blob_sha
        or raw.get("encoding") != "base64"
        or not _is_integer(size)
        or size < 0
        or not isinstance(content, str)
    ):
        raise PlanError("workflow blob response has an invalid identity or encoding")
    try:
        decoded = base64.b64decode("".join(content.split()), validate=True)
    except (ValueError, binascii.Error):
        raise PlanError("workflow blob content is not valid base64") from None
    if len(decoded) != size:
        raise PlanError("workflow blob size does not match decoded content")
    git_header = f"blob {len(decoded)}\0".encode("ascii")
    if hashlib.sha1(git_header + decoded).hexdigest() != blob_sha:
        raise PlanError("workflow blob bytes do not match the reviewed Git object")
    try:
        source = decoded.decode("utf-8")
    except UnicodeDecodeError:
        raise PlanError("workflow blob is not valid UTF-8") from None
    if AUTO_ENROLL_EXACT_COMMAND not in source:
        raise PlanError("reviewed workflow blob lacks the exact auto-squash command")
    return {
        "workflow_blob_sha": blob_sha,
        "workflow_blob_size": size,
        "workflow_blob_verified": True,
        "source_contains_exact_auto_squash_command": True,
    }


def inspect_enrollment_log_archive(
    payload: bytes,
    *,
    pull_request_number: int,
    repo_name: str,
) -> dict[str, Any]:
    """Inspect bounded run logs without retaining raw output or secret-bearing env."""

    if not isinstance(payload, bytes) or len(payload) > MAX_LOG_ARCHIVE_BYTES:
        raise PlanError("workflow log archive is unavailable or exceeds its bound")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_LOG_ENTRIES:
                raise PlanError("workflow log archive has an invalid entry count")
            total_size = 0
            matches: list[dict[str, Any]] = []
            for info in infos:
                if (
                    info.flag_bits & 0x1
                    or not _is_safe_log_member_name(info.filename)
                    or info.file_size < 0
                ):
                    raise PlanError("workflow log archive contains an unsafe entry")
                total_size += info.file_size
                if total_size > MAX_LOG_UNCOMPRESSED_BYTES:
                    raise PlanError("workflow log archive exceeds its expanded bound")
                try:
                    member = archive.read(info).decode("utf-8")
                except (RuntimeError, UnicodeDecodeError, zipfile.BadZipFile):
                    raise PlanError("workflow log archive member is unreadable") from None
                normalized_lines = []
                for line in member.splitlines():
                    line = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", line).lstrip(
                        "\ufeff"
                    )
                    line = re.sub(
                        r"^\d{4}-\d{2}-\d{2}T\S+Z\s+", "", line
                    ).strip()
                    normalized_lines.append(line)
                pr_marker = f"PR: {pull_request_number}"
                repo_marker = f"REPO: {repo_name}"
                success_marker = (
                    f"PR #{pull_request_number} enrolled for auto-merge (squash)."
                )
                proof = {
                    "log_member_name": info.filename,
                    "log_member_sha256": hashlib.sha256(
                        member.encode("utf-8")
                    ).hexdigest(),
                    "log_pr_number_matches": pr_marker in normalized_lines,
                    "log_repo_matches": repo_marker in normalized_lines,
                    "log_contains_enrollment_success": (
                        success_marker in normalized_lines
                    ),
                    "log_contains_exact_auto_squash_command": any(
                        AUTO_ENROLL_EXACT_COMMAND in line
                        and line.startswith(("if gh pr merge", "gh pr merge"))
                        for line in normalized_lines
                    ),
                }
                if all(
                    proof[field] is True
                    for field in (
                        "log_pr_number_matches",
                        "log_repo_matches",
                        "log_contains_enrollment_success",
                        "log_contains_exact_auto_squash_command",
                    )
                ):
                    matches.append(proof)
    except zipfile.BadZipFile:
        raise PlanError("workflow log archive is not a valid ZIP") from None
    result: dict[str, Any] = {
        "log_archive_sha256": hashlib.sha256(payload).hexdigest(),
        "log_matching_member_count": len(matches),
        "log_pr_number_matches": False,
        "log_repo_matches": False,
        "log_contains_enrollment_success": False,
        "log_contains_exact_auto_squash_command": False,
    }
    if len(matches) == 1:
        result.update(matches[0])
    return result


def _normalized_workflow_run(raw: Mapping[str, Any]) -> dict[str, Any]:
    fields = (
        "id",
        "node_id",
        "workflow_id",
        "path",
        "event",
        "status",
        "conclusion",
        "run_number",
        "run_attempt",
        "created_at",
        "run_started_at",
        "updated_at",
        "head_branch",
        "head_sha",
        "actor",
        "triggering_actor",
        "pull_requests",
        "html_url",
    )
    return {field: copy.deepcopy(raw.get(field)) for field in fields}


def collect_workflow_source_history(client: ReadOnlyGitHub) -> dict[str, Any]:
    """Bind the reviewed blob to complete default-branch path history."""

    rows, connection = client.rest_array_collection(
        (
            f"repos/{client.repo}/commits?sha=main&path="
            f"{quote(AUTO_ENROLL_WORKFLOW_PATH, safe='')}&per_page=100"
        )
    )
    if any(not isinstance(row, Mapping) for row in rows):
        raise PlanError("workflow source history contains a malformed commit")
    commits = []
    for row in rows:
        commit = row.get("commit")
        committer = commit.get("committer") if isinstance(commit, Mapping) else None
        commits.append(
            {
                "sha": row.get("sha"),
                "committed_at": (
                    committer.get("date") if isinstance(committer, Mapping) else None
                ),
            }
        )
    expected = [
        {
            "sha": AUTO_ENROLL_PATH_INTRODUCTION_COMMIT,
            "committed_at": "2026-07-22T00:38:24Z",
        }
    ]
    if commits != expected:
        raise PlanError("default-branch workflow path history is not the reviewed set")
    encoded_path = quote(AUTO_ENROLL_WORKFLOW_PATH, safe="/")
    content = client.rest(
        (
            f"repos/{client.repo}/contents/{encoded_path}"
            f"?ref={AUTO_ENROLL_PATH_INTRODUCTION_COMMIT}"
        )
    )
    if (
        not isinstance(content, Mapping)
        or content.get("sha") != TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHA
        or content.get("size") != 4255
    ):
        raise PlanError("workflow introduction commit is not bound to the trusted blob")
    return {
        "source_commit": None,
        "source_commit_status": "unavailable_from_stable_api",
        "default_branch": "main",
        "workflow_path": AUTO_ENROLL_WORKFLOW_PATH,
        "path_introduction_commit": AUTO_ENROLL_PATH_INTRODUCTION_COMMIT,
        "active_blob_sha": TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHA,
        "mapping_basis": "unchanged-default-branch-path-history",
        "commits": commits,
        "connection": {
            "kind": "workflow_source_history",
            "label_name": AUTO_ENROLL_WORKFLOW_PATH,
            **connection,
        },
    }


def _run_matches_pull_request(
    run: Mapping[str, Any], pull_request: Mapping[str, Any]
) -> bool:
    linked = run.get("pull_requests")
    if not isinstance(linked, list):
        return False
    for row in linked:
        if not isinstance(row, Mapping):
            continue
        if row.get("number") == pull_request.get("number"):
            return True
    return False


def _run_can_explain_enrollment(
    run: Mapping[str, Any], pull_request: Mapping[str, Any]
) -> bool:
    request = pull_request.get("auto_merge_request") or {}
    enabled_at = _parse_time(request.get("enabled_at"))
    created_at = _parse_time(run.get("created_at"))
    updated_at = _parse_time(run.get("updated_at"))
    return (
        enabled_at is not None
        and created_at is not None
        and updated_at is not None
        and run.get("workflow_id") == AUTO_ENROLL_WORKFLOW_ID
        and run.get("path") == AUTO_ENROLL_WORKFLOW_PATH
        and run.get("event") == "pull_request_target"
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and created_at <= enabled_at <= updated_at
        and _run_matches_pull_request(run, pull_request)
    )


def collect_auto_merge_attribution(
    client: ReadOnlyGitHub,
    inventory: Mapping[str, Any],
) -> dict[str, Any]:
    """Add conservative historical evidence to an inventory without mutations."""

    result = copy.deepcopy(dict(inventory))
    blob_proofs = [
        verify_trusted_workflow_blob(client, blob_sha)
        for blob_sha in TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHAS
    ]
    if any(
        proof.get("source_contains_exact_auto_squash_command") is not True
        for proof in blob_proofs
    ):
        raise PlanError("reviewed workflow blobs do not share the enrollment command")
    source_history = collect_workflow_source_history(client)
    result["source_history"] = {
        key: copy.deepcopy(value)
        for key, value in source_history.items()
        if key != "connection"
    }
    raw_runs, run_connection = client.rest_collection(
        (
            f"repos/{client.repo}/actions/workflows/{AUTO_ENROLL_WORKFLOW_ID}"
            "/runs?per_page=100"
        ),
        list_key="workflow_runs",
    )
    runs = [_normalized_workflow_run(run) for run in raw_runs]
    result["workflow_runs"] = runs
    result["connections"] = [
        row
        for row in result.get("connections", [])
        if row.get("kind") != "workflow_runs"
    ]
    result["connections"].append(
        {"kind": "workflow_runs", "label_name": "", **run_connection}
    )
    result["connections"].append(source_history["connection"])
    jobs_by_run: dict[int, list[dict[str, Any]]] = {}
    workflow_jobs: list[dict[str, Any]] = []
    log_by_run_pr: dict[tuple[int, int], dict[str, Any]] = {}
    attribution: list[dict[str, Any]] = []
    for pull_request in result.get("pull_requests", []):
        candidate_evidence: list[dict[str, Any]] = []
        request = pull_request.get("auto_merge_request") or {}
        actor = request.get("enabled_by") or {}
        exact_bot = (
            actor.get("__typename") == "Bot"
            and actor.get("login") == GITHUB_ACTIONS_BOT_LOGIN
            and actor.get("id") == GITHUB_ACTIONS_BOT_NODE_ID
        )
        if exact_bot:
            for run in runs:
                run_id = run.get("id")
                if (
                    not _is_integer(run_id)
                    or not _run_can_explain_enrollment(run, pull_request)
                ):
                    continue
                if run_id not in jobs_by_run:
                    jobs, job_connection = client.rest_collection(
                        (
                            f"repos/{client.repo}/actions/runs/{run_id}"
                            "/jobs?filter=all&per_page=100"
                        ),
                        list_key="jobs",
                    )
                    jobs_by_run[run_id] = jobs
                    result["connections"].append(
                        {
                            "kind": "workflow_jobs",
                            "label_name": str(run_id),
                            **job_connection,
                        }
                    )
                    workflow_jobs.extend(
                        {"run_id": run_id, **copy.deepcopy(dict(job))}
                        for job in jobs
                    )
                log_key = (run_id, int(pull_request["number"]))
                if log_key not in log_by_run_pr:
                    try:
                        log_by_run_pr[log_key] = inspect_enrollment_log_archive(
                            client.bytes(
                                f"repos/{client.repo}/actions/runs/{run_id}/logs"
                            ),
                            pull_request_number=int(pull_request["number"]),
                            repo_name=client.repo,
                        )
                    except (PlanError, RetirementError):
                        log_by_run_pr[log_key] = {
                            "evidence_status": "log_unavailable",
                            "reason": "log_read_failed",
                            "workflow_id": run.get("workflow_id"),
                            "run_id": run_id,
                            "event": run.get("event"),
                            "run_status": run.get("status"),
                            "conclusion": run.get("conclusion"),
                            "pull_request_number": pull_request.get("number"),
                            "head_sha": run.get("head_sha"),
                            "run_created_at": run.get("created_at"),
                            "run_updated_at": run.get("updated_at"),
                            "run_url": run.get("html_url"),
                        }
                log_proof = log_by_run_pr[log_key]
                if log_proof.get("evidence_status") == "log_unavailable":
                    candidate_evidence.append(copy.deepcopy(log_proof))
                    continue
                for job in jobs_by_run[run_id]:
                    if job.get("name") != "Enroll for auto-merge":
                        continue
                    steps = job.get("steps")
                    if not isinstance(steps, list):
                        continue
                    for step in steps:
                        if (
                            not isinstance(step, Mapping)
                            or step.get("name") != "Enable auto-merge"
                        ):
                            continue
                        candidate_evidence.append(
                            {
                                "workflow_id": run["workflow_id"],
                                "run_id": run_id,
                                "job_id": job.get("id"),
                                "step_number": step.get("number"),
                                "workflow_path": run["path"],
                                "workflow_blob_shas": list(
                                    TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHAS
                                ),
                                "workflow_blobs_verified": True,
                                "historical_source_commit_status": (
                                    "unavailable_from_stable_api"
                                ),
                                "source_commit": None,
                                "default_branch": source_history["default_branch"],
                                "path_introduction_commit": source_history[
                                    "path_introduction_commit"
                                ],
                                "active_blob_sha": source_history["active_blob_sha"],
                                "mapping_basis": source_history["mapping_basis"],
                                "enrollment_source_identical_across_trusted_blobs": True,
                                "run_url": run.get("html_url"),
                                "event": run.get("event"),
                                "run_status": run.get("status"),
                                "conclusion": run.get("conclusion"),
                                "pull_request_number": pull_request.get("number"),
                                "head_sha": run.get("head_sha"),
                                "current_head_sha": pull_request.get("head_ref_oid"),
                                "run_created_at": run.get("created_at"),
                                "run_updated_at": run.get("updated_at"),
                                "job_name": job.get("name"),
                                "job_status": job.get("status"),
                                "job_conclusion": job.get("conclusion"),
                                "job_started_at": job.get("started_at"),
                                "job_completed_at": job.get("completed_at"),
                                "step_name": step.get("name"),
                                "step_status": step.get("status"),
                                "step_conclusion": step.get("conclusion"),
                                "step_started_at": step.get("started_at"),
                                "step_completed_at": step.get("completed_at"),
                                "source_contains_exact_auto_squash_command": True,
                                **log_proof,
                            }
                        )
        classified = classify_auto_merge(pull_request, candidate_evidence)
        attribution.append(
            {
                "pull_request_node_id": pull_request.get("node_id"),
                **classified,
            }
        )
    result["attribution"] = attribution
    result["workflow_jobs"] = workflow_jobs
    result["planned_actions"] = []
    result["apply_complete"] = False
    return result


def collect_auto_merge_inventory(
    client: ReadOnlyGitHub,
    *,
    with_attribution: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    repo_raw = client.rest(f"repos/{client.repo}")
    client.bind_repo_database_id(repo_raw["id"])
    repo = {
        "node_id": repo_raw["node_id"],
        "database_id": repo_raw["id"],
        "name_with_owner": repo_raw["full_name"],
        "default_branch": repo_raw["default_branch"],
    }
    owner, name = client.repo.split("/", 1)
    pages = client.graphql_pages(AUTO_MERGE_QUERY, {"owner": owner, "name": name})
    if not pages:
        raise PlanError("GitHub GraphQL returned no open-PR pages")
    nodes: list[dict[str, Any]] = []
    expected_total: int | None = None
    observed_total = 0
    seen_node_ids: set[str] = set()
    seen_numbers: set[int] = set()
    for page_index, page in enumerate(pages):
        if page.get("errors"):
            raise RetirementError("GitHub GraphQL returned an error response")
        try:
            connection = page["data"]["repository"]["pullRequests"]
            page_nodes = connection["nodes"]
            page_total = connection["totalCount"]
            page_info = connection["pageInfo"]
        except (KeyError, TypeError):
            raise RetirementError(
                "GitHub GraphQL response omitted the pull-request connection"
            ) from None
        if (
            not isinstance(connection, Mapping)
            or not isinstance(page_nodes, list)
            or not _is_integer(page_total)
            or page_total < 0
            or not isinstance(page_info, Mapping)
            or not isinstance(page_info.get("hasNextPage"), bool)
            or page_info["hasNextPage"] != (page_index < len(pages) - 1)
        ):
            raise PlanError("GitHub GraphQL pull-request connection is malformed")
        if expected_total is None:
            expected_total = page_total
        elif page_total != expected_total:
            raise PlanError("GitHub GraphQL totalCount changed between pages")
        observed_total += len(page_nodes)
        for raw in page_nodes:
            if (
                not isinstance(raw, Mapping)
                or not isinstance(raw.get("id"), str)
                or not _is_integer(raw.get("number"))
                or raw["id"] in seen_node_ids
                or raw["number"] in seen_numbers
            ):
                raise PlanError("GitHub GraphQL returned a duplicate or invalid PR")
            seen_node_ids.add(raw["id"])
            seen_numbers.add(raw["number"])
            request = raw.get("autoMergeRequest")
            if request is None:
                continue
            try:
                node = {
                    "node_id": raw["id"],
                    "number": raw["number"],
                    "state": raw["state"],
                    "is_draft": raw["isDraft"],
                    "base_ref_name": raw["baseRefName"],
                    "head_ref_name": raw["headRefName"],
                    "head_ref_oid": raw["headRefOid"],
                    "repository": raw["repository"],
                    "base_repository": raw["baseRepository"],
                    "head_repository": raw["headRepository"],
                    "auto_merge_request": {
                        "enabled_at": request["enabledAt"],
                        "merge_method": request["mergeMethod"],
                        "commit_headline": request.get("commitHeadline"),
                        "commit_body": request.get("commitBody"),
                        "author_email": request.get("authorEmail"),
                        "enabled_by": request["enabledBy"],
                    },
                }
            except (KeyError, TypeError):
                raise RetirementError(
                    "GitHub GraphQL auto-merge tuple is incomplete"
                ) from None
            nodes.append(node)
    if observed_total != expected_total:
        raise PlanError(
            f"open-PR GraphQL count mismatch: observed {observed_total}, "
            f"expected {expected_total}"
        )
    workflow = client.rest(
        f"repos/{client.repo}/actions/workflows/{AUTO_ENROLL_WORKFLOW_ID}"
    )
    inventory = {
        "pull_requests": nodes,
        "connections": [
            {
                "kind": "open_pull_requests",
                "label_name": "",
                "pages": len(pages),
                "count": observed_total,
                "total_count": expected_total or 0,
                "complete": bool(pages)
                and pages[-1]["data"]["repository"]["pullRequests"]["pageInfo"][
                    "hasNextPage"
                ]
                is False,
                "completion_basis": "graphql_total_count",
            }
        ],
        "workflow": {
            "id": workflow["id"],
            "node_id": workflow["node_id"],
            "path": workflow["path"],
            "state": workflow["state"],
        },
        "workflow_runs": [],
        "attribution": [],
        "planned_actions": [],
        "apply_complete": False,
    }
    if with_attribution:
        inventory = collect_auto_merge_attribution(client, inventory)
    return repo, inventory


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise PlanError("JSON root must be an object")
    return value


def _repo_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    inventory_parser = sub.add_parser(
        "inventory", help="read GitHub and write a deterministic dry-run receipt"
    )
    inventory_parser.add_argument(
        "--operation", required=True, choices=sorted(OPERATIONS)
    )
    inventory_parser.add_argument("--repo", default="Jonnyton/TinyAssets")
    inventory_parser.add_argument("--source-revision")
    inventory_parser.add_argument("--out", type=Path, required=True)
    inventory_parser.add_argument(
        "--with-attribution",
        action="store_true",
        help="collect read-only Actions/blob/log evidence for auto-merge inventory",
    )

    plan_parser = sub.add_parser(
        "plan", help="build a receipt from an already-captured inventory"
    )
    plan_parser.add_argument("--operation", required=True, choices=sorted(OPERATIONS))
    plan_parser.add_argument("--repo-json", type=Path, required=True)
    plan_parser.add_argument("--inventory-json", type=Path, required=True)
    plan_parser.add_argument("--source-revision", required=True)
    plan_parser.add_argument("--out", type=Path, required=True)

    verify_parser = sub.add_parser(
        "verify",
        help="verify receipt integrity without re-verifying external GitHub evidence",
    )
    verify_parser.add_argument("receipt", type=Path)

    args = parser.parse_args(argv)
    if args.command == "inventory":
        if args.with_attribution and args.operation != AUTO_MERGE_OPERATION:
            parser.error("--with-attribution is only valid for auto_merge_v1")
        client = ReadOnlyGitHub(args.repo)
        if args.operation == LABEL_OPERATION:
            repo, inventory = collect_label_inventory(client)
        else:
            repo, inventory = collect_auto_merge_inventory(
                client, with_attribution=args.with_attribution
            )
        receipt = build_receipt(
            operation=args.operation,
            repo=repo,
            source_revision=args.source_revision or _repo_head(),
            inventory=inventory,
        )
        atomically_write_json(args.out, receipt)
        print(
            json.dumps(
                {
                    "mode": "dry_run",
                    "operation": args.operation,
                    "plan_digest": receipt["plan_digest"],
                    "apply_key": receipt["apply_key"],
                    "out": str(args.out),
                },
                sort_keys=True,
            )
        )
        return 0
    if args.command == "plan":
        captured_inventory = _load_json(args.inventory_json)
        if args.operation == AUTO_MERGE_OPERATION and any(
            captured_inventory.get(field)
            for field in (
                "attribution",
                "source_history",
                "workflow_jobs",
            )
        ):
            raise PlanError(
                "offline plan cannot mint auto-merge attribution; "
                "use live inventory --with-attribution"
            )
        receipt = build_receipt(
            operation=args.operation,
            repo=_load_json(args.repo_json),
            source_revision=args.source_revision,
            inventory=captured_inventory,
        )
        atomically_write_json(args.out, receipt)
        return 0
    receipt = _load_json(args.receipt)
    verify_receipt(receipt)
    print(
        json.dumps(
            {
                "integrity_valid": True,
                "external_evidence_verified": False,
                "receipt_digest": receipt["receipt_digest"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RetirementError as exc:
        print(f"blocked: {exc}", file=sys.stderr)
        raise SystemExit(2)
