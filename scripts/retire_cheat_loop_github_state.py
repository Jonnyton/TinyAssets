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
import copy
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
from urllib.parse import quote
import uuid

import rfc8785


SCHEMA = "tinyassets.github-state-retirement-receipt"
SCHEMA_VERSION = 1
LABEL_OPERATION = "retired_labels_v1"
AUTO_MERGE_OPERATION = "auto_merge_v1"
OPERATIONS = frozenset({LABEL_OPERATION, AUTO_MERGE_OPERATION})
APPLY_DOMAIN = "tinyassets/github-state-retirement/apply/v1"
AUTO_ENROLL_WORKFLOW_ID = 317815472

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
        if connection.get("complete") is not True:
            raise PlanError("inventory contains an incomplete paginated connection")
        count = connection.get("count")
        total = connection.get("total_count")
        pages = connection.get("pages")
        if not all(isinstance(value, int) and value >= 0 for value in (count, total, pages)):
            raise PlanError("connection count, total_count, and pages must be non-negative integers")
        if count != total:
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
        for field in ("node_id", "name", "color"):
            if definition.get(field) in (None, ""):
                raise PlanError(f"label definition is missing {field}")

    associations = _sorted_json_records(
        inventory.get("associations", []),
        key=lambda row: (
            str(row.get("item_node_id", "")),
            str(row.get("label_name", "")),
        ),
    )
    seen: set[tuple[str, str]] = set()
    for row in associations:
        label_name = row.get("label_name")
        if label_name not in RETIRED_LABEL_SET:
            raise PlanError(f"association contains non-retired label {label_name!r}")
        required = ("label_node_id", "item_node_id", "number", "kind", "state")
        if any(row.get(field) in (None, "") for field in required):
            raise PlanError("association is missing an exact target field")
        identity = (str(row["item_node_id"]), str(label_name))
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
    planned_actions = _normalize_planned_actions(inventory.get("planned_actions", []))
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
        "attribution": attribution,
        "quiescence": copy.deepcopy(inventory.get("quiescence")),
        "planned_actions": planned_actions,
        "apply_complete": apply_complete,
    }


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
    if plan.get("operation") != operation:
        raise PlanError("top-level operation does not match the bound plan")
    if plan.get("repo") != repo:
        raise PlanError("top-level repository does not match the bound plan")
    if plan.get("source_revision") != receipt.get("source_revision"):
        raise PlanError("top-level source revision does not match the bound plan")
    normalized_inventory = (
        _normalize_label_inventory(plan.get("inventory", {}))
        if operation == LABEL_OPERATION
        else _normalize_auto_merge_inventory(plan.get("inventory", {}))
    )
    expected_plan = {
        "operation": operation,
        "repo": repo,
        "source_revision": receipt.get("source_revision"),
        "inventory": normalized_inventory,
    }
    if canonical_bytes(plan) != canonical_bytes(expected_plan):
        raise PlanError("receipt plan is not the normalized operation schema")
    expected_key = derive_apply_key(operation, repo["node_id"], receipt["plan_digest"])
    if receipt.get("apply_key") != expected_key:
        raise PlanError("receipt apply key mismatch")
    if digest(_without(receipt, "receipt_digest")) != receipt.get("receipt_digest"):
        raise PlanError("terminal receipt digest mismatch")


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
                    operation TEXT NOT NULL CHECK(operation IN ('{LABEL_OPERATION}','{AUTO_MERGE_OPERATION}')),
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
                if row["plan_digest"] != receipt["plan_digest"] or bytes(row["plan_json"]) != plan_bytes:
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
                        f"target {action['target_node_id']} lacks a prior mutation-authorizing intent"
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
    if actor.get("login") != "app/github-actions" or actor.get("__typename") != "Bot":
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
    for row in evidence:
        run_start = _parse_time(row.get("run_created_at"))
        run_end = _parse_time(row.get("run_updated_at"))
        step_start = _parse_time(row.get("step_started_at"))
        step_end = _parse_time(row.get("step_completed_at"))
        if (
            enabled_at is not None
            and row.get("workflow_id") == AUTO_ENROLL_WORKFLOW_ID
            and row.get("event") == "pull_request_target"
            and row.get("conclusion") == "success"
            and row.get("pull_request_number") == pr.get("number")
            and row.get("head_sha") == pr.get("head_ref_oid")
            and row.get("job_name") == "Enroll for auto-merge"
            and row.get("step_name") == "Enable auto-merge"
            and row.get("step_conclusion") == "success"
            and isinstance(row.get("run_id"), int)
            and isinstance(row.get("job_id"), int)
            and isinstance(row.get("step_number"), int)
            and row.get("workflow_path")
            == ".github/workflows/auto-enroll-merge.yml"
            and isinstance(row.get("workflow_source_sha"), str)
            and bool(row.get("workflow_source_sha"))
            and isinstance(row.get("run_url"), str)
            and bool(row.get("run_url"))
            and row.get("source_contains_exact_auto_squash_command") is True
            and all(
                stamp is not None
                for stamp in (run_start, run_end, step_start, step_end)
            )
            and run_start <= enabled_at <= run_end
            and step_start <= enabled_at <= step_end
        ):
            matches.append(copy.deepcopy(dict(row)))
    if len(matches) == 1:
        return {"classification": "attributed", "evidence": matches}
    return {"classification": "ambiguous_preserve", "evidence": matches}


class ReadOnlyGitHub:
    """Read-only ``gh api`` adapter.  No mutating method exists."""

    def __init__(
        self,
        repo: str,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ):
        if repo.count("/") != 1:
            raise ValueError("repo must be OWNER/NAME")
        self.repo = repo
        self._runner = runner

    def _json(self, args: Sequence[str]) -> Any:
        is_graphql_query = bool(args) and args[0] == "graphql"
        if any(
            arg == "-X"
            or arg.startswith("-X")
            or arg == "--method"
            or arg.startswith("--method=")
            or arg == "--input"
            or arg.startswith("--input=")
            for arg in args
        ):
            raise ApplyBlocked("read-only GitHub client rejected a mutating option")
        if not is_graphql_query and any(
            arg in {"-f", "-F", "--field", "--raw-field"}
            or arg.startswith("--field=")
            or arg.startswith("--raw-field=")
            for arg in args
        ):
            raise ApplyBlocked(
                "read-only REST client rejected fields that make gh api use POST"
            )
        if any("mutation" in arg.lower() for arg in args):
            raise ApplyBlocked("read-only GitHub client rejected a GraphQL mutation")
        try:
            completed = self._runner(
                ["gh", "api", *args],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            return json.loads(completed.stdout)
        except subprocess.CalledProcessError as exc:
            raise RetirementError(
                f"GitHub read failed with exit status {exc.returncode}"
            ) from None
        except (json.JSONDecodeError, TypeError):
            raise RetirementError("GitHub read returned invalid JSON") from None

    def rest(self, endpoint: str) -> Any:
        return self._json([endpoint])

    def rest_pages(self, endpoint: str) -> list[list[dict[str, Any]]]:
        result = self._json(["--paginate", "--slurp", endpoint])
        if not isinstance(result, list) or any(not isinstance(page, list) for page in result):
            raise PlanError("paginated REST response was not an array of page arrays")
        return result

    def graphql_pages(
        self, query: str, fields: Mapping[str, str]
    ) -> list[dict[str, Any]]:
        args = ["graphql", "--paginate", "--slurp", "-f", f"query={query}"]
        for key, value in fields.items():
            args.extend(["-F", f"{key}={value}"])
        result = self._json(args)
        if not isinstance(result, list) or any(not isinstance(page, dict) for page in result):
            raise PlanError("paginated GraphQL response was not an array of pages")
        return result


def collect_label_inventory(client: ReadOnlyGitHub) -> tuple[dict[str, Any], dict[str, Any]]:
    repo_raw = client.rest(f"repos/{client.repo}")
    repo = {
        "node_id": repo_raw["node_id"],
        "database_id": repo_raw["id"],
        "name_with_owner": repo_raw["full_name"],
        "default_branch": repo_raw["default_branch"],
    }
    label_pages = client.rest_pages(f"repos/{client.repo}/labels?per_page=100")
    all_definitions = [row for page in label_pages for row in page]
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
            "pages": len(label_pages),
            "count": len(all_definitions),
            "total_count": len(all_definitions),
            "complete": True,
        }
    ]
    for label_name in RETIRED_LABELS:
        pages = client.rest_pages(
            f"repos/{client.repo}/issues?state=all&labels={quote(label_name, safe='')}&per_page=100"
        )
        rows = [row for page in pages for row in page]
        connections.append(
            {
                "kind": "retired_label_associations",
                "label_name": label_name,
                "pages": len(pages),
                "count": len(rows),
                "total_count": len(rows),
                "complete": True,
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
    pullRequests(states:OPEN, first:100, after:$endCursor, orderBy:{field:CREATED_AT,direction:ASC}) {
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
            ... on User { id }
          }
        }
      }
    }
  }
}
"""


def collect_auto_merge_inventory(
    client: ReadOnlyGitHub,
) -> tuple[dict[str, Any], dict[str, Any]]:
    repo_raw = client.rest(f"repos/{client.repo}")
    repo = {
        "node_id": repo_raw["node_id"],
        "database_id": repo_raw["id"],
        "name_with_owner": repo_raw["full_name"],
        "default_branch": repo_raw["default_branch"],
    }
    owner, name = client.repo.split("/", 1)
    pages = client.graphql_pages(AUTO_MERGE_QUERY, {"owner": owner, "name": name})
    nodes: list[dict[str, Any]] = []
    expected_total: int | None = None
    observed_total = 0
    for page in pages:
        try:
            connection = page["data"]["repository"]["pullRequests"]
            page_nodes = connection["nodes"]
            page_total = connection["totalCount"]
        except (KeyError, TypeError):
            raise RetirementError(
                "GitHub GraphQL response omitted the pull-request connection"
            ) from None
        if expected_total is None:
            expected_total = page_total
        observed_total += len(page_nodes)
        for raw in page_nodes:
            request = raw.get("autoMergeRequest")
            if request is None:
                continue
            nodes.append(
                {
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
            )
    workflow = client.rest(
        f"repos/{client.repo}/actions/workflows/{AUTO_ENROLL_WORKFLOW_ID}"
    )
    return repo, {
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

    plan_parser = sub.add_parser(
        "plan", help="build a receipt from an already-captured inventory"
    )
    plan_parser.add_argument("--operation", required=True, choices=sorted(OPERATIONS))
    plan_parser.add_argument("--repo-json", type=Path, required=True)
    plan_parser.add_argument("--inventory-json", type=Path, required=True)
    plan_parser.add_argument("--source-revision", required=True)
    plan_parser.add_argument("--out", type=Path, required=True)

    verify_parser = sub.add_parser("verify", help="verify a receipt without mutation")
    verify_parser.add_argument("receipt", type=Path)

    args = parser.parse_args(argv)
    if args.command == "inventory":
        client = ReadOnlyGitHub(args.repo)
        if args.operation == LABEL_OPERATION:
            repo, inventory = collect_label_inventory(client)
        else:
            repo, inventory = collect_auto_merge_inventory(client)
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
        receipt = build_receipt(
            operation=args.operation,
            repo=_load_json(args.repo_json),
            source_revision=args.source_revision,
            inventory=_load_json(args.inventory_json),
        )
        atomically_write_json(args.out, receipt)
        return 0
    receipt = _load_json(args.receipt)
    verify_receipt(receipt)
    print(json.dumps({"valid": True, "receipt_digest": receipt["receipt_digest"]}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RetirementError as exc:
        print(f"blocked: {exc}", file=sys.stderr)
        raise SystemExit(2)
