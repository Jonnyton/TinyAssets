"""Focused tests for the receipt-bound GitHub-state retirement tool."""

from __future__ import annotations

import base64
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("retire_cheat_loop_github_state.py")
SPEC = importlib.util.spec_from_file_location("retire_github_state", MODULE_PATH)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def repo() -> dict:
    return {
        "node_id": "R_repo",
        "database_id": 42,
        "name_with_owner": "Jonnyton/TinyAssets",
        "default_branch": "main",
    }


def complete_connection(
    *,
    kind: str,
    label_name: str,
    count: int,
    completion_basis: str,
    pages: int = 1,
) -> dict:
    value = {
        "kind": kind,
        "label_name": label_name,
        "pages": pages,
        "count": count,
        "total_count": (
            None
            if completion_basis == "github_link_header_chain_v1"
            else count
        ),
        "complete": True,
        "completion_basis": completion_basis,
    }
    if completion_basis == "github_link_header_chain_v1":
        request_endpoint = (
            f"repos/Jonnyton/TinyAssets/{kind}?per_page=100"
        )
        value["pagination"] = {
            "mode": "github_link_header_chain_v1",
            "page_size": 100,
            "page_receipts": [
                {
                    "ordinal": 0,
                    "request_id": "fixture-request-id",
                    "request_endpoint": request_endpoint,
                    "request_url_digest": mod.digest(
                        {"method": "GET", "endpoint": request_endpoint}
                    ),
                    "response_body_digest": mod.digest(
                        {"fixture": kind, "count": count}
                    ),
                    "item_count": count,
                    "next_url_digest": None,
                }
            ],
            "terminal": {"oracle": "rel_next_absent", "page_ordinal": 0},
        }
    return value


def label_inventory() -> dict:
    definitions = [
        {
            "node_id": f"L_{index}",
            "database_id": index,
            "name": name,
            "color": f"{index:06x}",
            "description": "café" if index == 1 else None,
            "url": f"https://api.example.invalid/labels/{index}",
        }
        for index, name in enumerate(reversed(mod.RETIRED_LABELS), 1)
    ]
    return {
        "definitions": definitions,
        "associations": [
            {
                "label_node_id": definitions[-1]["node_id"],
                "label_name": mod.RETIRED_LABELS[0],
                "item_node_id": "I_1",
                "number": 1,
                "kind": "issue",
                "state": "open",
                "url": "https://example.invalid/1",
            }
        ],
        "connections": [
            complete_connection(
                kind="label_definitions",
                label_name="",
                count=28,
                completion_basis="github_link_header_chain_v1",
            ),
            *[
            complete_connection(
                kind="retired_label_associations",
                label_name=name,
                count=1 if name == "auto-bug" else 0,
                completion_basis="github_link_header_chain_v1",
            )
            for name in reversed(mod.RETIRED_LABELS)
            ],
        ],
        "planned_actions": [],
        "apply_complete": False,
    }


def receipt() -> dict:
    return mod.build_receipt(
        operation=mod.LABEL_OPERATION,
        repo=repo(),
        source_revision="abc123",
        inventory=label_inventory(),
    )


def redigest_receipt(value: dict) -> dict:
    value["plan_digest"] = mod.digest(value["plan"])
    value["apply_key"] = mod.derive_apply_key(
        value["operation"],
        value["repo"]["node_id"],
        value["plan_digest"],
    )
    value["receipt_digest"] = mod.digest(mod._without(value, "receipt_digest"))
    return value


def auto_pr(
    actor_type="Bot",
    login=mod.GITHUB_ACTIONS_BOT_LOGIN,
    *,
    node_id="PR_1",
    number=7,
    head_ref_oid="deadbeef",
) -> dict:
    repository = {"id": "R_repo", "nameWithOwner": "Jonnyton/TinyAssets"}
    return {
        "node_id": node_id,
        "number": number,
        "state": "OPEN",
        "is_draft": False,
        "base_ref_name": "main",
        "head_ref_name": "feature",
        "head_ref_oid": head_ref_oid,
        "repository": repository,
        "base_repository": repository,
        "head_repository": repository,
        "auto_merge_request": {
            "enabled_at": "2026-07-25T01:00:02Z",
            "merge_method": "SQUASH",
            "commit_headline": None,
            "commit_body": None,
            "author_email": None,
            "enabled_by": {
                "__typename": actor_type,
                "login": login,
                "id": mod.GITHUB_ACTIONS_BOT_NODE_ID,
            },
        },
    }


def exact_evidence(
    *,
    pull_request_number=7,
    head_sha="deadbeef",
    run_id=101,
    job_id=202,
) -> dict:
    return {
        "workflow_id": mod.AUTO_ENROLL_WORKFLOW_ID,
        "run_id": run_id,
        "job_id": job_id,
        "step_number": 3,
        "workflow_path": ".github/workflows/auto-enroll-merge.yml",
        "workflow_blob_shas": list(mod.TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHAS),
        "workflow_blobs_verified": True,
        "historical_source_commit_status": "unavailable_from_stable_api",
        "source_commit": None,
        "default_branch": "main",
        "path_introduction_commit": mod.AUTO_ENROLL_PATH_INTRODUCTION_COMMIT,
        "active_blob_sha": mod.TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHA,
        "mapping_basis": "unchanged-default-branch-path-history",
        "enrollment_source_identical_across_trusted_blobs": True,
        "run_url": f"https://example.invalid/actions/runs/{run_id}",
        "event": "pull_request_target",
        "run_status": "completed",
        "conclusion": "success",
        "pull_request_number": pull_request_number,
        "head_sha": head_sha,
        "current_head_sha": head_sha,
        "run_created_at": "2026-07-25T01:00:00Z",
        "run_updated_at": "2026-07-25T01:00:04Z",
        "job_name": "Enroll for auto-merge",
        "job_status": "completed",
        "job_conclusion": "success",
        "job_started_at": "2026-07-25T01:00:00Z",
        "job_completed_at": "2026-07-25T01:00:04Z",
        "step_name": "Enable auto-merge",
        "step_status": "completed",
        "step_conclusion": "success",
        "step_started_at": "2026-07-25T01:00:01Z",
        "step_completed_at": "2026-07-25T01:00:03Z",
        "source_contains_exact_auto_squash_command": True,
        "log_archive_sha256": "a" * 64,
        "log_member_name": "0_Enroll for auto-merge.txt",
        "log_member_sha256": "b" * 64,
        "log_matching_member_count": 1,
        "log_pr_number_matches": True,
        "log_repo_matches": True,
        "log_contains_enrollment_success": True,
        "log_contains_exact_auto_squash_command": True,
    }


def enrollment_log_zip(
    *,
    number: int = 7,
    repo_name: str = "Jonnyton/TinyAssets",
    include_success: bool = True,
    success_number: int | None = None,
) -> bytes:
    lines = [
        f"  PR: {number}",
        f"  REPO: {repo_name}",
        'if gh pr merge "$PR" --repo "$REPO" --auto --squash 2>err.txt; then',
    ]
    if include_success:
        lines.append(
            f"PR #{success_number if success_number is not None else number} "
            "enrolled for auto-merge (squash)."
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("0_Enroll for auto-merge.txt", "\n".join(lines))
    return buffer.getvalue()


def trusted_workflow_blob_response(
    blob_sha: str = mod.TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHA,
) -> dict:
    source = subprocess.run(
        ["git", "cat-file", "-p", blob_sha],
        cwd=MODULE_PATH.parents[1],
        check=True,
        capture_output=True,
    ).stdout
    header = f"blob {len(source)}\0".encode("ascii")
    assert hashlib.sha1(header + source).hexdigest() == blob_sha
    encoded = base64.b64encode(source).decode("ascii")
    return {
        "sha": blob_sha,
        "size": len(source),
        "encoding": "base64",
        "content": "\n".join(
            encoded[index : index + 60] for index in range(0, len(encoded), 60)
        ),
    }


def included_json_response(
    rows: list[dict],
    *,
    request_id: str | None = "REQ_fixture",
    link: str | None = None,
) -> str:
    headers = ["HTTP/2.0 200 OK", "content-type: application/json"]
    if request_id is not None:
        headers.append(f"x-github-request-id: {request_id}")
    if link is not None:
        headers.append(f"link: {link}")
    return "\r\n".join(headers) + "\r\n\r\n" + json.dumps(rows)


def complete_auto_receipt() -> tuple[dict, dict]:
    pr = auto_pr()
    after = copy.deepcopy(pr)
    after["auto_merge_request"] = None
    action = {
        "ordinal": 0,
        "kind": "disable_auto_merge",
        "target_node_id": pr["node_id"],
        "planned_before": pr,
        "planned_after": after,
    }
    inventory = {
        "pull_requests": [pr],
        "connections": [
            complete_connection(
                kind="open_pull_requests",
                label_name="",
                count=1,
                completion_basis="graphql_total_count",
            ),
            complete_connection(
                kind="workflow_runs",
                label_name="",
                count=1,
                completion_basis="reported_total_count",
            ),
            complete_connection(
                kind="workflow_source_history",
                label_name=mod.AUTO_ENROLL_WORKFLOW_PATH,
                count=1,
                completion_basis="github_link_header_chain_v1",
            ),
            complete_connection(
                kind="workflow_jobs",
                label_name="101",
                count=1,
                completion_basis="reported_total_count",
            ),
        ],
        "workflow": {
            "id": mod.AUTO_ENROLL_WORKFLOW_ID,
            "node_id": "W_auto",
            "path": ".github/workflows/auto-enroll-merge.yml",
            "state": "disabled_manually",
        },
        "workflow_runs": [
            {
                "id": 101,
                "workflow_id": mod.AUTO_ENROLL_WORKFLOW_ID,
                "path": mod.AUTO_ENROLL_WORKFLOW_PATH,
                "event": "pull_request_target",
                "status": "completed",
                "conclusion": "success",
                "head_sha": "deadbeef",
                "pull_requests": [{"number": 7}],
                "created_at": "2026-07-25T01:00:00Z",
                "updated_at": "2026-07-25T01:00:04Z",
                "html_url": "https://example.invalid/actions/runs/101",
            }
        ],
        "workflow_jobs": [
            {
                "run_id": 101,
                "id": 202,
                "name": "Enroll for auto-merge",
                "status": "completed",
                "conclusion": "success",
                "started_at": "2026-07-25T01:00:00Z",
                "completed_at": "2026-07-25T01:00:04Z",
                "steps": [
                    {
                        "number": 3,
                        "name": "Enable auto-merge",
                        "status": "completed",
                        "conclusion": "success",
                        "started_at": "2026-07-25T01:00:01Z",
                        "completed_at": "2026-07-25T01:00:03Z",
                    }
                ],
            }
        ],
        "source_history": {
            "source_commit": None,
            "source_commit_status": "unavailable_from_stable_api",
            "default_branch": "main",
            "workflow_path": mod.AUTO_ENROLL_WORKFLOW_PATH,
            "path_introduction_commit": mod.AUTO_ENROLL_PATH_INTRODUCTION_COMMIT,
            "active_blob_sha": mod.TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHA,
            "mapping_basis": "unchanged-default-branch-path-history",
            "commits": [
                {
                    "sha": mod.AUTO_ENROLL_PATH_INTRODUCTION_COMMIT,
                    "committed_at": "2026-07-22T00:38:24Z",
                }
            ],
        },
        "attribution": [
            {
                "pull_request_node_id": pr["node_id"],
                "classification": "attributed",
                "evidence": [exact_evidence()],
            }
        ],
        "planned_actions": [action],
        "apply_complete": True,
        "quiescence": {
            "workflow_disabled_verified_at": "2026-07-25T00:59:00Z",
            "runs_scanned_at": "2026-07-25T01:01:00Z",
        },
    }
    return (
        mod.build_receipt(
            operation=mod.AUTO_MERGE_OPERATION,
            repo=repo(),
            source_revision="abc123",
            inventory=inventory,
        ),
        action,
    )


def complete_two_action_receipt() -> tuple[dict, list[dict]]:
    value, first = complete_auto_receipt()
    inventory = copy.deepcopy(value["plan"]["inventory"])
    second_pr = auto_pr(node_id="PR_2", number=8, head_ref_oid="cafebabe")
    second_after = copy.deepcopy(second_pr)
    second_after["auto_merge_request"] = None
    second = {
        "ordinal": 1,
        "kind": "disable_auto_merge",
        "target_node_id": second_pr["node_id"],
        "planned_before": second_pr,
        "planned_after": second_after,
    }
    inventory["pull_requests"].append(second_pr)
    inventory["connections"][0]["count"] = 2
    inventory["connections"][0]["total_count"] = 2
    inventory["attribution"].append(
        {
            "pull_request_node_id": second_pr["node_id"],
            "classification": "attributed",
            "evidence": [
                exact_evidence(
                    pull_request_number=8,
                    head_sha="cafebabe",
                    run_id=102,
                    job_id=203,
                )
            ],
        }
    )
    inventory["workflow_runs"].append(
        {
            **copy.deepcopy(inventory["workflow_runs"][0]),
            "id": 102,
            "head_sha": "cafebabe",
            "pull_requests": [{"number": 8}],
            "html_url": "https://example.invalid/actions/runs/102",
        }
    )
    run_connection = next(
        row for row in inventory["connections"] if row["kind"] == "workflow_runs"
    )
    run_connection["count"] = 2
    run_connection["total_count"] = 2
    inventory["workflow_jobs"].append(
        {
            **copy.deepcopy(inventory["workflow_jobs"][0]),
            "run_id": 102,
            "id": 203,
        }
    )
    inventory["connections"].append(
        complete_connection(
            kind="workflow_jobs",
            label_name="102",
            count=1,
            completion_basis="reported_total_count",
        )
    )
    inventory["planned_actions"] = [first, second]
    return (
        mod.build_receipt(
            operation=mod.AUTO_MERGE_OPERATION,
            repo=repo(),
            source_revision="abc123",
            inventory=inventory,
        ),
        [first, second],
    )


def authority_proof(operation: str = mod.AUTO_MERGE_OPERATION) -> dict:
    proof = {
        "repo": repo(),
        "source_revision": "abc123",
        "permission": "ADMIN",
        "required_endpoint_capability": True,
        "all_producers_removed": True,
        "runs_drained": True,
        "pagination_complete": True,
        "ambiguity_count": 0,
    }
    if operation == mod.LABEL_OPERATION:
        proof.update(
            {
                "task_4_2_complete": True,
                "all_label_consumers_removed": True,
            }
        )
    else:
        proof.update(
            {
                "workflow_id": mod.AUTO_ENROLL_WORKFLOW_ID,
                "workflow_state": "disabled_manually",
            }
        )
    return proof


class ReceiptTests(unittest.TestCase):
    def test_manifest_is_exact_and_disjoint_from_preserved_labels(self) -> None:
        self.assertEqual(28, len(mod.RETIRED_LABELS))
        self.assertEqual(28, len(set(mod.RETIRED_LABELS)))
        self.assertTrue(mod.RETIRED_LABEL_SET.isdisjoint(mod.PRESERVED_LABELS))
        for prefix in mod.PRESERVED_LABEL_PREFIXES:
            self.assertFalse(any(name.startswith(prefix) for name in mod.RETIRED_LABELS))

    def test_canonical_receipt_ignores_input_order_and_preserves_unicode(self) -> None:
        left = receipt()
        inventory = label_inventory()
        inventory["definitions"].reverse()
        inventory["connections"].reverse()
        right = mod.build_receipt(
            operation=mod.LABEL_OPERATION,
            repo=dict(reversed(list(repo().items()))),
            source_revision="abc123",
            inventory=inventory,
        )
        self.assertEqual(left, right)
        self.assertIn("café".encode(), mod.canonical_bytes(left))

    def test_tampering_and_apply_key_mismatch_are_rejected(self) -> None:
        value = receipt()
        changed = copy.deepcopy(value)
        changed["plan"]["source_revision"] = "evil"
        with self.assertRaises(mod.PlanError):
            mod.verify_receipt(changed)
        changed = copy.deepcopy(value)
        changed["execution"]["status"] = "applied"
        with self.assertRaises(mod.PlanError):
            mod.verify_receipt(changed)
        with self.assertRaises(mod.ApplyBlocked):
            mod.verify_apply_authority(
                value,
                authority_proof(),
                apply_key="sha256:" + "0" * 64,
                confirm_plan_digest=value["plan_digest"],
            )

    def test_top_level_and_plan_identity_cannot_be_split(self) -> None:
        value = receipt()
        changed = copy.deepcopy(value)
        changed["source_revision"] = "different"
        changed["receipt_digest"] = mod.digest(
            mod._without(changed, "receipt_digest")
        )
        with self.assertRaises(mod.PlanError):
            mod.verify_receipt(changed)

        changed = copy.deepcopy(value)
        changed["plan"]["inventory"]["unexpected_authority"] = True
        changed["plan_digest"] = mod.digest(changed["plan"])
        changed["apply_key"] = mod.derive_apply_key(
            changed["operation"], changed["repo"]["node_id"], changed["plan_digest"]
        )
        changed["receipt_digest"] = mod.digest(
            mod._without(changed, "receipt_digest")
        )
        with self.assertRaises(mod.PlanError):
            mod.verify_receipt(changed)

    def test_receipt_envelope_and_nested_pagination_schema_are_closed(self) -> None:
        def redigest(value: dict, *, plan_changed: bool = False) -> dict:
            if plan_changed:
                value["plan_digest"] = mod.digest(value["plan"])
                value["apply_key"] = mod.derive_apply_key(
                    value["operation"],
                    value["repo"]["node_id"],
                    value["plan_digest"],
                )
            value["receipt_digest"] = mod.digest(
                mod._without(value, "receipt_digest")
            )
            return value

        cases = []

        changed = copy.deepcopy(receipt())
        changed["execution"] = {"mode": "live_apply", "status": "complete"}
        cases.append(("execution", redigest(changed)))

        changed = copy.deepcopy(receipt())
        changed["mutation_authority"] = True
        cases.append(("top_level_authority", redigest(changed)))

        changed = copy.deepcopy(receipt())
        changed["plan"]["inventory"]["connections"][0][
            "mutation_authority"
        ] = True
        cases.append(("connection_authority", redigest(changed, plan_changed=True)))

        changed = copy.deepcopy(receipt())
        link_connection = next(
            row
            for row in changed["plan"]["inventory"]["connections"]
            if row["completion_basis"] == "github_link_header_chain_v1"
        )
        link_connection["pagination"]["mode"] = "unreviewed"
        cases.append(("pagination_mode", redigest(changed, plan_changed=True)))

        for name, changed in cases:
            with self.subTest(name=name), self.assertRaises(mod.PlanError):
                mod.verify_receipt(changed)

    def test_label_definition_schema_rejects_unknown_fields(self) -> None:
        changed = copy.deepcopy(receipt())
        changed["plan"]["inventory"]["definitions"][0]["mutation_authority"] = True

        with self.assertRaises(mod.PlanError):
            mod.verify_receipt(redigest_receipt(changed))

    def test_label_association_schema_rejects_unknown_fields(self) -> None:
        changed = copy.deepcopy(receipt())
        changed["plan"]["inventory"]["associations"][0]["mutation_authority"] = True

        with self.assertRaises(mod.PlanError):
            mod.verify_receipt(redigest_receipt(changed))

    def test_label_inventory_receipt_rejects_non_empty_planned_actions(self) -> None:
        changed = copy.deepcopy(receipt())
        changed["plan"]["inventory"]["planned_actions"] = [
            {
                "ordinal": 0,
                "kind": "delete_label",
                "target_node_id": "L_1",
                "planned_before": {"name": mod.RETIRED_LABELS[0]},
                "planned_after": {},
            }
        ]

        with self.assertRaises(mod.PlanError):
            mod.verify_receipt(redigest_receipt(changed))

    def test_collected_label_records_round_trip_through_shared_exact_schemas(
        self,
    ) -> None:
        class FakeLabelClient:
            repo = "Jonnyton/TinyAssets"

            def bind_repo_database_id(self, database_id):
                self.database_id = database_id

            def rest(self, endpoint):
                self.repo_endpoint = endpoint
                return {
                    "node_id": "R_repo",
                    "id": 42,
                    "full_name": "Jonnyton/TinyAssets",
                    "default_branch": "main",
                }

            def rest_array_collection(self, endpoint):
                if endpoint.endswith("/labels?per_page=100"):
                    rows = [
                        {
                            "node_id": f"L_{index}",
                            "id": index,
                            "name": name,
                            "color": f"{index:06x}",
                            "description": None,
                            "url": f"https://api.example.invalid/labels/{index}",
                        }
                        for index, name in enumerate(mod.RETIRED_LABELS, 1)
                    ]
                    return rows, complete_connection(
                        kind="label_definitions",
                        label_name="",
                        count=len(rows),
                        completion_basis="github_link_header_chain_v1",
                    )
                label_name = next(
                    name
                    for name in mod.RETIRED_LABELS
                    if f"labels={mod.quote(name, safe='')}" in endpoint
                )
                rows = (
                    [
                        {
                            "node_id": "I_1",
                            "number": 1,
                            "state": "open",
                            "html_url": "https://example.invalid/issues/1",
                        }
                    ]
                    if label_name == mod.RETIRED_LABELS[0]
                    else []
                )
                return rows, complete_connection(
                    kind="retired_label_associations",
                    label_name=label_name,
                    count=len(rows),
                    completion_basis="github_link_header_chain_v1",
                )

        repo_value, inventory = mod.collect_label_inventory(FakeLabelClient())
        value = mod.build_receipt(
            operation=mod.LABEL_OPERATION,
            repo=repo_value,
            source_revision="abc123",
            inventory=inventory,
        )
        mod.verify_receipt(value)

        injected = copy.deepcopy(inventory)
        injected["definitions"][0]["collector_only_field"] = True
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.LABEL_OPERATION,
                repo=repo_value,
                source_revision="abc123",
                inventory=injected,
            )

        self.assertEqual(
            set(inventory["definitions"][0]),
            set(mod.LABEL_DEFINITION_FIELDS),
        )
        self.assertEqual(
            set(inventory["associations"][0]),
            set(mod.LABEL_ASSOCIATION_FIELDS),
        )

    def test_label_definition_values_use_closed_collector_types(self) -> None:
        invalid_values = {
            "node_id": ({}, [], 1, True, ""),
            "database_id": ({}, [], "1", 1.0, True, None, 0, -1),
            "name": ({}, [], 1, True, ""),
            "color": ({}, [], 1, True, "", "#123456", "zzzzzz"),
            "description": ({}, [], 1, True),
            "url": ({}, [], 1, True, ""),
        }
        for field, values in invalid_values.items():
            for invalid in values:
                with self.subTest(field=field, invalid=invalid):
                    inventory = label_inventory()
                    inventory["definitions"][0][field] = invalid
                    with self.assertRaises(mod.PlanError):
                        mod.build_receipt(
                            operation=mod.LABEL_OPERATION,
                            repo=repo(),
                            source_revision="abc123",
                            inventory=inventory,
                        )

    def test_label_association_values_use_closed_collector_types(self) -> None:
        invalid_values = {
            "label_node_id": ({}, [], 1, True, ""),
            "item_node_id": ({}, [], 1, True, ""),
            "kind": ({}, [], 1, True, None, "bug"),
            "state": ({}, [], 1, True, None, "merged"),
            "number": ({}, [], "1", 1.0, True, None, 0, -1),
            "url": ({}, [], 1, True, ""),
        }
        for field, values in invalid_values.items():
            for invalid in values:
                with self.subTest(field=field, invalid=invalid):
                    inventory = label_inventory()
                    inventory["associations"][0][field] = invalid
                    with self.assertRaises(mod.PlanError):
                        mod.build_receipt(
                            operation=mod.LABEL_OPERATION,
                            repo=repo(),
                            source_revision="abc123",
                            inventory=inventory,
                        )

    def test_label_planned_actions_requires_a_json_array(self) -> None:
        for invalid in ("x", {"ordinal": 0}, 1, None):
            with self.subTest(invalid=invalid):
                inventory = label_inventory()
                inventory["planned_actions"] = invalid
                with self.assertRaises(mod.PlanError):
                    mod.build_receipt(
                        operation=mod.LABEL_OPERATION,
                        repo=repo(),
                        source_revision="abc123",
                        inventory=inventory,
                    )

    def test_label_planned_actions_rejects_malformed_non_empty_arrays(self) -> None:
        for invalid in ([1], ["x"], [None], [[]]):
            with self.subTest(invalid=invalid):
                inventory = label_inventory()
                inventory["planned_actions"] = invalid
                with self.assertRaises(mod.PlanError):
                    mod.build_receipt(
                        operation=mod.LABEL_OPERATION,
                        repo=repo(),
                        source_revision="abc123",
                        inventory=inventory,
                    )

    def test_incomplete_or_truncated_pagination_is_rejected(self) -> None:
        inventory = label_inventory()
        inventory["connections"][0]["complete"] = False
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.LABEL_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )

    def test_label_apply_and_link_server_total_cannot_be_fabricated(self) -> None:
        inventory = label_inventory()
        inventory["apply_complete"] = True
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.LABEL_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )

        connection = complete_connection(
            kind="fixture",
            label_name="",
            count=0,
            completion_basis="github_link_header_chain_v1",
        )
        connection["total_count"] = 0
        with self.assertRaises(mod.PlanError):
            mod._validate_complete_connections([connection], repo=repo())

        terminal_full = complete_connection(
            kind="fixture",
            label_name="",
            count=100,
            completion_basis="github_link_header_chain_v1",
        )
        terminal_full["pagination"]["page_receipts"][0]["item_count"] = 100
        with self.assertRaises(mod.PlanError):
            mod._validate_complete_connections([terminal_full], repo=repo())

        mismatched_request = complete_connection(
            kind="fixture",
            label_name="",
            count=0,
            completion_basis="github_link_header_chain_v1",
        )
        endpoint = "repos/Jonnyton/TinyAssets/fixture?per_page=30"
        page = mismatched_request["pagination"]["page_receipts"][0]
        page["request_endpoint"] = endpoint
        page["request_url_digest"] = mod.digest(
            {"method": "GET", "endpoint": endpoint}
        )
        with self.assertRaises(mod.PlanError):
            mod._validate_complete_connections([mismatched_request], repo=repo())

        stale_request_digest = complete_connection(
            kind="fixture",
            label_name="",
            count=0,
            completion_basis="github_link_header_chain_v1",
        )
        stale_request_digest["pagination"]["page_size"] = 30
        page = stale_request_digest["pagination"]["page_receipts"][0]
        page["request_endpoint"] = (
            "repos/Jonnyton/TinyAssets/fixture?per_page=30"
        )
        with self.assertRaises(mod.PlanError):
            mod._validate_complete_connections([stale_request_digest], repo=repo())

        boolean_page_size = complete_connection(
            kind="fixture",
            label_name="",
            count=0,
            completion_basis="github_link_header_chain_v1",
        )
        endpoint = "repos/Jonnyton/TinyAssets/fixture?per_page=1"
        boolean_page_size["pagination"]["page_size"] = True
        page = boolean_page_size["pagination"]["page_receipts"][0]
        page["request_endpoint"] = endpoint
        page["request_url_digest"] = mod.digest(
            {"method": "GET", "endpoint": endpoint}
        )
        with self.assertRaises(mod.PlanError):
            mod._validate_complete_connections([boolean_page_size], repo=repo())

        first_endpoint = "repos/Jonnyton/TinyAssets/fixture?per_page=100"
        second_endpoint = (
            "https://api.github.com/repositories/42/fixture"
            "?per_page=100&page=2"
        )
        oversized_nonterminal = {
            "kind": "fixture",
            "label_name": "",
            "pages": 2,
            "count": 101,
            "total_count": None,
            "complete": True,
            "completion_basis": "github_link_header_chain_v1",
            "pagination": {
                "mode": "github_link_header_chain_v1",
                "page_size": 100,
                "page_receipts": [
                    {
                        "ordinal": 0,
                        "request_id": "REQ_first",
                        "request_endpoint": first_endpoint,
                        "request_url_digest": mod.digest(
                            {"method": "GET", "endpoint": first_endpoint}
                        ),
                        "response_body_digest": mod.digest({"page": 1}),
                        "item_count": 101,
                        "next_url_digest": mod.digest(
                            {"method": "GET", "endpoint": second_endpoint}
                        ),
                    },
                    {
                        "ordinal": 1,
                        "request_id": "REQ_second",
                        "request_endpoint": second_endpoint,
                        "request_url_digest": mod.digest(
                            {"method": "GET", "endpoint": second_endpoint}
                        ),
                        "response_body_digest": mod.digest({"page": 2}),
                        "item_count": 0,
                        "next_url_digest": None,
                    },
                ],
                "terminal": {"oracle": "rel_next_absent", "page_ordinal": 1},
            },
        }
        with self.assertRaises(mod.PlanError):
            mod._validate_complete_connections([oversized_nonterminal], repo=repo())

        valid_multi_page = copy.deepcopy(oversized_nonterminal)
        valid_multi_page["count"] = 101
        valid_multi_page["pagination"]["page_receipts"][0]["item_count"] = 100
        valid_multi_page["pagination"]["page_receipts"][1]["item_count"] = 1
        mod._validate_complete_connections([valid_multi_page], repo=repo())

        broken_chain = copy.deepcopy(valid_multi_page)
        broken_chain["pagination"]["page_receipts"][0]["next_url_digest"] = (
            mod.digest({"unrelated": "request"})
        )
        with self.assertRaises(mod.PlanError):
            mod._validate_complete_connections(
                [broken_chain],
                repo=repo(),
            )

        extra_pagination_field = copy.deepcopy(valid_multi_page)
        extra_pagination_field["pagination"]["unreviewed_authority"] = True
        with self.assertRaises(mod.PlanError):
            mod._validate_complete_connections(
                [extra_pagination_field],
                repo=repo(),
            )

        wrong_terminal_ordinal = copy.deepcopy(valid_multi_page)
        wrong_terminal_ordinal["pagination"]["terminal"]["page_ordinal"] = 0
        with self.assertRaises(mod.PlanError):
            mod._validate_complete_connections(
                [wrong_terminal_ordinal],
                repo=repo(),
            )

        full_second_terminal = copy.deepcopy(valid_multi_page)
        full_second_terminal["count"] = 200
        full_second_terminal["pagination"]["page_receipts"][1]["item_count"] = 100
        with self.assertRaises(mod.PlanError):
            mod._validate_complete_connections(
                [full_second_terminal],
                repo=repo(),
            )

        hostile_continuations = (
            "https://api.github.com/repositories/99/fixture"
            "?per_page=100&page=2",
            "https://evil.example/repositories/42/fixture"
            "?per_page=100&page=2",
            "https://api.github.com/repositories/42/fixture"
            "?per_page=100&page=3",
            "https://api.github.com/repositories/42/fixture"
            "?per_page=100&state=open&page=2",
            "https://api.github.com/repositories/42/fixture"
            "?per_page=100&after=a&after=b&page=2",
        )
        for hostile_endpoint in hostile_continuations:
            with self.subTest(hostile_endpoint=hostile_endpoint):
                hostile_continuation = copy.deepcopy(valid_multi_page)
                first_page = hostile_continuation["pagination"]["page_receipts"][0]
                second_page = hostile_continuation["pagination"]["page_receipts"][1]
                first_page["next_url_digest"] = mod.digest(
                    {"method": "GET", "endpoint": hostile_endpoint}
                )
                second_page["request_endpoint"] = hostile_endpoint
                second_page["request_url_digest"] = mod.digest(
                    {"method": "GET", "endpoint": hostile_endpoint}
                )
                with self.assertRaises(mod.PlanError):
                    mod._validate_complete_connections(
                        [hostile_continuation],
                        repo=repo(),
                    )

        malformed_page = copy.deepcopy(valid_multi_page)
        malformed_page["pagination"]["page_receipts"][0] = None
        with self.assertRaises(mod.PlanError):
            mod._validate_complete_connections(
                [malformed_page],
                repo=repo(),
            )

        for unsafe_endpoint in (
            "https://evil.example/fixture?per_page=100",
            "repos/AnotherOwner/AnotherRepo/fixture?per_page=100",
            "repos/Jonnyton/TinyAssets/fixture?per_page=100&page=999",
            "repos/Jonnyton/TinyAssets/fixture?per_page=100&after=cursor",
            "repos/Jonnyton/TinyAssets/fixture?per_page=100&page=2&page=9",
        ):
            with self.subTest(unsafe_endpoint=unsafe_endpoint):
                cross_scope = complete_connection(
                    kind="fixture",
                    label_name="",
                    count=0,
                    completion_basis="github_link_header_chain_v1",
                )
                page = cross_scope["pagination"]["page_receipts"][0]
                page["request_endpoint"] = unsafe_endpoint
                page["request_url_digest"] = mod.digest(
                    {"method": "GET", "endpoint": unsafe_endpoint}
                )
                with self.assertRaises(mod.PlanError):
                    mod._validate_complete_connections(
                        [cross_scope],
                        repo=repo(),
                    )

        for completion_basis in (
            "reported_total_count",
            "graphql_total_count",
        ):
            with self.subTest(completion_basis=completion_basis), self.assertRaises(
                mod.PlanError
            ):
                mod._validate_complete_connections(
                    [
                        complete_connection(
                            kind="fixture",
                            label_name="",
                            count=0,
                            pages=0,
                            completion_basis=completion_basis,
                        )
                    ],
                    repo=repo(),
                )

        inventory = label_inventory()
        empty_connection = inventory["connections"][2]
        empty_connection.update(
            {
                "pages": 0,
                "count": 0,
                "total_count": None,
                "pagination": {
                    "mode": "github_link_header_chain_v1",
                    "page_receipts": [],
                    "terminal": {
                        "oracle": "rel_next_absent",
                        "page_ordinal": -1,
                    },
                },
            }
        )
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.LABEL_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )

    def test_float_ordinals_and_naive_quiescence_times_are_rejected(self) -> None:
        value, _ = complete_auto_receipt()
        inventory = copy.deepcopy(value["plan"]["inventory"])
        inventory["planned_actions"][0]["ordinal"] = 0.0
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.AUTO_MERGE_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )
        inventory = copy.deepcopy(value["plan"]["inventory"])
        inventory["quiescence"]["workflow_disabled_verified_at"] = "2026-07-25T00:59:00"
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.AUTO_MERGE_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )
        inventory = label_inventory()
        inventory["connections"] = []
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.LABEL_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )
        inventory = label_inventory()
        inventory["connections"][0]["count"] = 0
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.LABEL_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )

    def test_atomic_receipt_round_trip_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "receipt.json"
            value = receipt()
            mod.atomically_write_json(path, value)
            loaded = json.loads(path.read_text(encoding="utf-8"))
            mod.verify_receipt(loaded)
            self.assertEqual(mod.canonical_bytes(value), path.read_bytes())


class JournalTests(unittest.TestCase):
    def test_same_key_same_plan_replays_but_immutable_intent_cannot_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal = mod.MigrationJournal(Path(tmp) / "journal.sqlite3")
            value = receipt()
            journal.register(value)
            journal.register(value)
            journal.claim_apply(
                value["apply_key"], "executor", recovery_authorized=False
            )
            journal.persist_intent(
                apply_key=value["apply_key"],
                executor_token="executor",
                ordinal=0,
                action_kind="remove_label",
                target_node_id="I_1",
                planned_before={"labels": ["auto-bug", "keep"]},
                planned_after={"labels": ["keep"]},
            )
            with self.assertRaises(mod.JournalConflict):
                journal.persist_intent(
                    apply_key=value["apply_key"],
                    executor_token="executor",
                    ordinal=0,
                    action_kind="remove_label",
                    target_node_id="I_1",
                    planned_before={"labels": ["auto-bug", "different"]},
                    planned_after={"labels": ["different"]},
                )
            rows = journal.intent_rows(value["apply_key"])
            self.assertEqual("intent_persisted", rows[0]["state"])

    def test_stale_executor_cannot_write_or_update_missing_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal = mod.MigrationJournal(Path(tmp) / "journal.sqlite3")
            value = receipt()
            journal.register(value)
            journal.claim_apply(value["apply_key"], "old", recovery_authorized=False)
            journal.mark_executor_abandoned(value["apply_key"], "old")
            journal.claim_apply(value["apply_key"], "new", recovery_authorized=True)
            with self.assertRaises(mod.JournalConflict):
                journal.persist_intent(
                    apply_key=value["apply_key"],
                    executor_token="old",
                    ordinal=0,
                    action_kind="remove_label",
                    target_node_id="I_1",
                    planned_before={"labels": ["auto-bug", "keep"]},
                    planned_after={"labels": ["keep"]},
                )
            with self.assertRaises(mod.JournalConflict):
                journal.set_pre_read(
                    value["apply_key"], "new", 0, {"labels": []}, "host_review"
                )
            with self.assertRaises(mod.JournalConflict):
                journal.set_outcome(
                    value["apply_key"], "new", 0, {"labels": []},
                    state="host_review", outcome="missing_row"
                )

    def test_same_apply_key_cannot_bind_changed_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            journal = mod.MigrationJournal(Path(tmp) / "journal.sqlite3")
            value = receipt()
            journal.register(value)
            changed = copy.deepcopy(value)
            changed["plan"]["source_revision"] = "changed"
            changed["plan_digest"] = mod.digest(changed["plan"])
            # Simulate an adversarial collision/reuse of the original apply key.
            changed["receipt_digest"] = mod.digest(
                mod._without(changed, "receipt_digest")
            )
            with self.assertRaises(mod.PlanError):
                journal.register(changed)


class ApplyTests(unittest.TestCase):
    class Reader:
        def __init__(self, values):
            self.values = list(values)

        def read_exact(self, action):
            return self.values.pop(0)

    class Writer:
        def __init__(self):
            self.calls = []

        def mutate(self, action, client_mutation_id):
            self.calls.append((action, client_mutation_id))

    @staticmethod
    def fresh_proof(proof):
        return lambda action: copy.deepcopy(proof)

    def test_every_quiescence_gate_is_required(self) -> None:
        value, _ = complete_auto_receipt()
        for field in (
            "required_endpoint_capability",
            "all_producers_removed",
            "runs_drained",
            "pagination_complete",
        ):
            proof = authority_proof()
            proof[field] = False
            with self.subTest(field=field), self.assertRaises(mod.ApplyBlocked):
                mod.verify_apply_authority(
                    value,
                    proof,
                    apply_key=value["apply_key"],
                    confirm_plan_digest=value["plan_digest"],
                )

    def test_inventory_only_receipt_and_unbound_actions_are_rejected(self) -> None:
        inventory = label_inventory()
        inventory_only = mod.build_receipt(
            operation=mod.LABEL_OPERATION,
            repo=repo(),
            source_revision="abc123",
            inventory=inventory,
        )
        with self.assertRaises(mod.ApplyBlocked):
            mod.verify_apply_authority(
                inventory_only,
                authority_proof(mod.LABEL_OPERATION),
                apply_key=inventory_only["apply_key"],
                confirm_plan_digest=inventory_only["plan_digest"],
            )

        value, _ = complete_auto_receipt()
        unbound = {
            "ordinal": 0,
            "kind": "disable_auto_merge",
            "target_node_id": "PR_foreign",
            "planned_before": {"auto_merge_request": {"merge_method": "SQUASH"}},
            "planned_after": {"auto_merge_request": None},
        }
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(
            mod.ApplyBlocked
        ):
            mod.apply_actions(
                receipt=value,
                proof=authority_proof(mod.AUTO_MERGE_OPERATION),
                apply_key=value["apply_key"],
                confirm_plan_digest=value["plan_digest"],
                actions=[unbound],
                journal=mod.MigrationJournal(Path(tmp) / "journal.sqlite3"),
                reader=self.Reader([]),
                mutator=self.Writer(),
                proof_refresher=self.fresh_proof(authority_proof()),
            )

    def test_complete_plan_binds_exact_before_and_after_tuples(self) -> None:
        value, _action = complete_auto_receipt()
        for tuple_name in ("planned_before", "planned_after"):
            inventory = copy.deepcopy(value["plan"]["inventory"])
            inventory["planned_actions"][0][tuple_name]["head_ref_oid"] = "drifted"
            with self.subTest(tuple_name=tuple_name), self.assertRaises(
                mod.PlanError
            ):
                mod.build_receipt(
                    operation=mod.AUTO_MERGE_OPERATION,
                    repo=repo(),
                    source_revision="abc123",
                    inventory=inventory,
                )

    def test_pre_read_drift_persists_hold_and_never_mutates(self) -> None:
        value, action = complete_auto_receipt()
        writer = self.Writer()
        drifted = copy.deepcopy(action["planned_before"])
        drifted["head_ref_oid"] = "foreign"
        with tempfile.TemporaryDirectory() as tmp:
            journal = mod.MigrationJournal(Path(tmp) / "journal.sqlite3")
            with self.assertRaises(mod.ApplyBlocked):
                mod.apply_actions(
                    receipt=value,
                    proof=authority_proof(mod.AUTO_MERGE_OPERATION),
                    apply_key=value["apply_key"],
                    confirm_plan_digest=value["plan_digest"],
                    actions=[action],
                    journal=journal,
                    reader=self.Reader([drifted]),
                    mutator=writer,
                    proof_refresher=self.fresh_proof(authority_proof()),
                )
            self.assertEqual([], writer.calls)
            self.assertEqual(
                "stale_needs_replan",
                journal.intent_rows(value["apply_key"])[0]["state"],
            )

    def test_intent_is_durable_before_mutation_and_postread_is_verified(self) -> None:
        value, action = complete_auto_receipt()
        writer = self.Writer()
        with tempfile.TemporaryDirectory() as tmp:
            journal = mod.MigrationJournal(Path(tmp) / "journal.sqlite3")
            mod.apply_actions(
                receipt=value,
                proof=authority_proof(mod.AUTO_MERGE_OPERATION),
                apply_key=value["apply_key"],
                confirm_plan_digest=value["plan_digest"],
                actions=[action],
                journal=journal,
                reader=self.Reader(
                    [action["planned_before"], action["planned_after"]]
                ),
                mutator=writer,
                proof_refresher=self.fresh_proof(authority_proof()),
            )
            self.assertEqual(1, len(writer.calls))
            self.assertEqual(
                "succeeded", journal.intent_rows(value["apply_key"])[0]["state"]
            )

    def test_restart_reconciles_exact_planned_after_without_mutating(self) -> None:
        value, action = complete_auto_receipt()
        writer = self.Writer()
        with tempfile.TemporaryDirectory() as tmp:
            journal = mod.MigrationJournal(Path(tmp) / "journal.sqlite3")
            journal.register(value)
            journal.claim_apply(value["apply_key"], "crashed", recovery_authorized=False)
            journal.persist_intent(
                apply_key=value["apply_key"],
                executor_token="crashed",
                ordinal=0,
                action_kind=action["kind"],
                target_node_id=action["target_node_id"],
                planned_before=action["planned_before"],
                planned_after=action["planned_after"],
            )
            journal.set_pre_read(
                value["apply_key"],
                "crashed",
                0,
                action["planned_before"],
                "pre_read_authorized",
            )
            journal.mark_executor_abandoned(value["apply_key"], "crashed")
            mod.apply_actions(
                receipt=value,
                proof=authority_proof(mod.AUTO_MERGE_OPERATION),
                apply_key=value["apply_key"],
                confirm_plan_digest=value["plan_digest"],
                actions=[action],
                journal=journal,
                reader=self.Reader([action["planned_after"]]),
                mutator=writer,
                recovery_authorized=True,
                proof_refresher=self.fresh_proof(authority_proof()),
            )
            self.assertEqual([], writer.calls)
            self.assertEqual(
                "succeeded_after_restart",
                journal.intent_rows(value["apply_key"])[0]["state"],
            )

    def test_already_after_without_prior_intent_is_ambiguous(self) -> None:
        value, action = complete_auto_receipt()
        with tempfile.TemporaryDirectory() as tmp:
            journal = mod.MigrationJournal(Path(tmp) / "journal.sqlite3")
            writer = self.Writer()
            with self.assertRaises(mod.ApplyBlocked):
                mod.apply_actions(
                    receipt=value,
                    proof=authority_proof(mod.AUTO_MERGE_OPERATION),
                    apply_key=value["apply_key"],
                    confirm_plan_digest=value["plan_digest"],
                    actions=[action],
                    journal=journal,
                    reader=self.Reader([action["planned_after"]]),
                    mutator=writer,
                    proof_refresher=self.fresh_proof(authority_proof()),
                )
            self.assertEqual([], writer.calls)
            self.assertEqual(
                "host_review", journal.intent_rows(value["apply_key"])[0]["state"]
            )
            with self.assertRaises(mod.ApplyBlocked):
                mod.apply_actions(
                    receipt=value,
                    proof=authority_proof(mod.AUTO_MERGE_OPERATION),
                    apply_key=value["apply_key"],
                    confirm_plan_digest=value["plan_digest"],
                    actions=[action],
                    journal=journal,
                    reader=self.Reader([action["planned_before"]]),
                    mutator=writer,
                    recovery_authorized=True,
                    proof_refresher=self.fresh_proof(authority_proof()),
                )
            self.assertEqual([], writer.calls)
            self.assertEqual(
                "host_review", journal.intent_rows(value["apply_key"])[0]["state"]
            )

    def test_second_executor_cannot_enter_an_active_journal(self) -> None:
        value = receipt()
        with tempfile.TemporaryDirectory() as tmp:
            journal = mod.MigrationJournal(Path(tmp) / "journal.sqlite3")
            journal.register(value)
            journal.claim_apply(
                value["apply_key"], "executor-one", recovery_authorized=False
            )
            with self.assertRaises(mod.ApplyBlocked):
                journal.claim_apply(
                    value["apply_key"], "executor-two", recovery_authorized=False
                )
            with self.assertRaises(mod.ApplyBlocked):
                journal.claim_apply(
                    value["apply_key"], "executor-two", recovery_authorized=True
                )

    def test_recovery_preserves_terminal_first_action_and_reconciles_second(self) -> None:
        value, actions = complete_two_action_receipt()
        writer = self.Writer()
        with tempfile.TemporaryDirectory() as tmp:
            journal = mod.MigrationJournal(Path(tmp) / "journal.sqlite3")
            journal.register(value)
            journal.claim_apply(value["apply_key"], "crashed", recovery_authorized=False)
            first = actions[0]
            journal.persist_intent(
                apply_key=value["apply_key"], executor_token="crashed", ordinal=0,
                action_kind=first["kind"], target_node_id=first["target_node_id"],
                planned_before=first["planned_before"], planned_after=first["planned_after"],
            )
            journal.set_pre_read(
                value["apply_key"], "crashed", 0, first["planned_before"],
                "pre_read_authorized",
            )
            journal.set_outcome(
                value["apply_key"], "crashed", 0, first["planned_after"],
                state="succeeded", outcome="post_read_verified",
            )
            journal.mark_executor_abandoned(value["apply_key"], "crashed")
            mod.apply_actions(
                receipt=value, proof=authority_proof(), apply_key=value["apply_key"],
                confirm_plan_digest=value["plan_digest"], actions=actions, journal=journal,
                reader=self.Reader([
                    first["planned_after"], actions[1]["planned_before"],
                    actions[1]["planned_after"],
                ]),
                mutator=writer, recovery_authorized=True,
                proof_refresher=self.fresh_proof(authority_proof()),
            )
            self.assertEqual(1, len(writer.calls))
            self.assertEqual(
                ["succeeded", "succeeded"],
                [row["state"] for row in journal.intent_rows(value["apply_key"])],
            )

    def test_terminal_success_is_not_reapplied_after_remote_reenrollment(self) -> None:
        value, action = complete_auto_receipt()
        writer = self.Writer()
        with tempfile.TemporaryDirectory() as tmp:
            journal = mod.MigrationJournal(Path(tmp) / "journal.sqlite3")
            journal.register(value)
            journal.claim_apply(
                value["apply_key"], "crashed", recovery_authorized=False
            )
            journal.persist_intent(
                apply_key=value["apply_key"],
                executor_token="crashed",
                ordinal=0,
                action_kind=action["kind"],
                target_node_id=action["target_node_id"],
                planned_before=action["planned_before"],
                planned_after=action["planned_after"],
            )
            journal.set_pre_read(
                value["apply_key"],
                "crashed",
                0,
                action["planned_before"],
                "pre_read_authorized",
            )
            journal.set_outcome(
                value["apply_key"],
                "crashed",
                0,
                action["planned_after"],
                state="succeeded",
                outcome="post_read_verified",
            )
            journal.mark_executor_abandoned(value["apply_key"], "crashed")
            with self.assertRaises(mod.ApplyBlocked):
                mod.apply_actions(
                    receipt=value,
                    proof=authority_proof(),
                    apply_key=value["apply_key"],
                    confirm_plan_digest=value["plan_digest"],
                    actions=[action],
                    journal=journal,
                    reader=self.Reader([action["planned_before"]]),
                    mutator=writer,
                    recovery_authorized=True,
                    proof_refresher=self.fresh_proof(authority_proof()),
                )
            self.assertEqual([], writer.calls)
            self.assertEqual(
                "succeeded", journal.intent_rows(value["apply_key"])[0]["state"]
            )

    def test_proof_refresher_blocks_drift_between_actions(self) -> None:
        value, actions = complete_two_action_receipt()
        writer = self.Writer()
        proofs = [authority_proof(), authority_proof()]
        proofs[1]["source_revision"] = "drifted"
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(mod.ApplyBlocked):
            mod.apply_actions(
                receipt=value, proof=authority_proof(), apply_key=value["apply_key"],
                confirm_plan_digest=value["plan_digest"], actions=actions,
                journal=mod.MigrationJournal(Path(tmp) / "journal.sqlite3"),
                reader=self.Reader([
                    actions[0]["planned_before"], actions[0]["planned_after"],
                ]),
                mutator=writer,
                proof_refresher=lambda action: proofs.pop(0),
            )
        self.assertEqual(1, len(writer.calls))


class AttributionTests(unittest.TestCase):
    def pr(self, actor_type="Bot", login=mod.GITHUB_ACTIONS_BOT_LOGIN) -> dict:
        return auto_pr(actor_type, login)

    def evidence(self) -> dict:
        return exact_evidence()

    def test_human_enrollment_is_preserved(self) -> None:
        result = mod.classify_auto_merge(self.pr("User", "jonnyton"), [])
        self.assertEqual("explicit_preserve", result["classification"])

    def test_app_actor_without_exact_history_is_ambiguous(self) -> None:
        result = mod.classify_auto_merge(self.pr(), [])
        self.assertEqual("ambiguous_preserve", result["classification"])

    def test_unknown_bot_is_ambiguous_not_explicit(self) -> None:
        result = mod.classify_auto_merge(self.pr("Bot", "another-app"), [])
        self.assertEqual("ambiguous_preserve", result["classification"])

    def test_exact_bot_login_with_wrong_node_id_is_ambiguous(self) -> None:
        pr = self.pr()
        pr["auto_merge_request"]["enabled_by"]["id"] = "B_wrong"
        result = mod.classify_auto_merge(pr, [self.evidence()])
        self.assertEqual("ambiguous_preserve", result["classification"])

    def test_exact_unique_historical_evidence_attributes(self) -> None:
        result = mod.classify_auto_merge(self.pr(), [self.evidence()])
        self.assertEqual("attributed", result["classification"])
        result = mod.classify_auto_merge(
            self.pr(), [self.evidence(), self.evidence()]
        )
        self.assertEqual("ambiguous_preserve", result["classification"])

    def test_historical_enrollment_head_may_precede_current_pr_head(self) -> None:
        evidence = self.evidence()
        evidence["head_sha"] = "historical-head"
        result = mod.classify_auto_merge(self.pr(), [evidence])
        self.assertEqual("attributed", result["classification"])

    def test_attribution_requires_the_full_pull_request_eligibility_tuple(self) -> None:
        cases = {
            "closed": ("state", "CLOSED"),
            "draft": ("is_draft", True),
            "non_main": ("base_ref_name", "release"),
            "fork_head": (
                "head_repository",
                {"id": "R_fork", "nameWithOwner": "someone/fork"},
            ),
        }
        for name, (field, value) in cases.items():
            pr = self.pr()
            pr[field] = value
            result = mod.classify_auto_merge(pr, [self.evidence()])
            with self.subTest(name=name):
                self.assertEqual("ambiguous_preserve", result["classification"])

    def test_complete_plan_cannot_target_human_preserved_enrollment(self) -> None:
        valid, _ = complete_auto_receipt()
        pr = self.pr("User", "jonnyton")
        after = copy.deepcopy(pr)
        after["auto_merge_request"] = None
        inventory = copy.deepcopy(valid["plan"]["inventory"])
        inventory["pull_requests"] = [pr]
        inventory["attribution"] = [
            {
                "pull_request_node_id": pr["node_id"],
                "classification": "explicit_preserve",
                "evidence": [],
            }
        ]
        inventory["planned_actions"] = [
            {
                "ordinal": 0,
                "kind": "disable_auto_merge",
                "target_node_id": pr["node_id"],
                "planned_before": pr,
                "planned_after": after,
            }
        ]
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.AUTO_MERGE_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )

    def test_complete_plan_requires_disabled_workflow_and_drained_runs(self) -> None:
        valid, _ = complete_auto_receipt()
        inventory = copy.deepcopy(valid["plan"]["inventory"])
        inventory["workflow"]["state"] = "active"
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.AUTO_MERGE_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )

    def test_complete_plan_rejects_fabricated_run_or_job_binding(self) -> None:
        valid, _ = complete_auto_receipt()
        inventory = copy.deepcopy(valid["plan"]["inventory"])
        inventory["attribution"][0]["evidence"][0]["job_id"] = 999
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.AUTO_MERGE_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )

        inventory = copy.deepcopy(valid["plan"]["inventory"])
        inventory["workflow_runs"][0]["pull_requests"] = [{"number": 999}]
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.AUTO_MERGE_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )

        inventory = copy.deepcopy(valid["plan"]["inventory"])
        inventory["attribution"][0]["evidence"][0]["run_url"] = (
            "https://example.invalid/actions/runs/fabricated"
        )
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.AUTO_MERGE_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )

        inventory = copy.deepcopy(valid["plan"]["inventory"])
        inventory["workflow_runs"][0]["status"] = "in_progress"
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.AUTO_MERGE_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )

        inventory = copy.deepcopy(valid["plan"]["inventory"])
        inventory["workflow_runs"][0]["status"] = "future_unknown"
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.AUTO_MERGE_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )

    def test_inventory_only_receipt_still_binds_attribution_evidence(self) -> None:
        valid, _ = complete_auto_receipt()
        inventory = copy.deepcopy(valid["plan"]["inventory"])
        inventory["apply_complete"] = False
        inventory["workflow"]["state"] = "active"
        inventory["planned_actions"] = []
        inventory["quiescence"] = None
        inventory["attribution"][0]["evidence"][0]["job_id"] = 999
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.AUTO_MERGE_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )

        malformed_fields = (
            ("log_archive_sha256", "z" * 64),
            ("log_member_sha256", "z" * 64),
            ("log_matching_member_count", True),
            ("log_member_name", ""),
            ("log_member_name", "../escaped.txt"),
        )
        for field, malformed in malformed_fields:
            with self.subTest(field=field, malformed=malformed):
                inventory = copy.deepcopy(valid["plan"]["inventory"])
                inventory["apply_complete"] = False
                inventory["workflow"]["state"] = "active"
                inventory["planned_actions"] = []
                inventory["quiescence"] = None
                inventory["attribution"][0]["evidence"][0][field] = malformed
                with self.assertRaises(mod.PlanError):
                    mod.build_receipt(
                        operation=mod.AUTO_MERGE_OPERATION,
                        repo=repo(),
                        source_revision="abc123",
                        inventory=inventory,
                    )

        for target in ("run", "job", "step"):
            with self.subTest(nonterminal_target=target):
                inventory = copy.deepcopy(valid["plan"]["inventory"])
                inventory["apply_complete"] = False
                inventory["workflow"]["state"] = "active"
                inventory["planned_actions"] = []
                inventory["quiescence"] = None
                if target == "run":
                    inventory["workflow_runs"][0]["status"] = "in_progress"
                elif target == "job":
                    inventory["workflow_jobs"][0]["status"] = "in_progress"
                else:
                    inventory["workflow_jobs"][0]["steps"][0]["status"] = (
                        "in_progress"
                    )
                with self.assertRaises(mod.PlanError):
                    mod.build_receipt(
                        operation=mod.AUTO_MERGE_OPERATION,
                        repo=repo(),
                        source_revision="abc123",
                        inventory=inventory,
                    )

        inventory = copy.deepcopy(valid["plan"]["inventory"])
        inventory["apply_complete"] = False
        inventory["workflow"]["state"] = "active"
        inventory["planned_actions"] = []
        inventory["quiescence"] = None
        early = "2026-07-24T01:00:01Z"
        inventory["workflow_jobs"][0]["steps"][0]["started_at"] = early
        inventory["attribution"][0]["evidence"][0]["step_started_at"] = early
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.AUTO_MERGE_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )

        inventory = copy.deepcopy(valid["plan"]["inventory"])
        inventory["apply_complete"] = False
        inventory["workflow"]["state"] = "active"
        inventory["planned_actions"] = []
        inventory["quiescence"] = None
        source_connection = next(
            row
            for row in inventory["connections"]
            if row["kind"] == "workflow_source_history"
        )
        source_connection.update({"pages": True, "count": True, "total_count": True})
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.AUTO_MERGE_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=inventory,
            )

    def test_workflow_blob_is_verified_as_the_exact_git_object(self) -> None:
        class BlobClient:
            repo = "Jonnyton/TinyAssets"

            def rest(self, endpoint):
                self.endpoint = endpoint
                return trusted_workflow_blob_response()

        client = BlobClient()
        proof = mod.verify_trusted_workflow_blob(client)
        self.assertEqual(
            mod.TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHA, proof["workflow_blob_sha"]
        )
        self.assertTrue(proof["workflow_blob_verified"])
        self.assertTrue(proof["source_contains_exact_auto_squash_command"])
        self.assertTrue(client.endpoint.endswith(proof["workflow_blob_sha"]))

        bad = trusted_workflow_blob_response()
        bad["content"] = base64.b64encode(b"changed").decode("ascii")

        class BadBlobClient:
            repo = "Jonnyton/TinyAssets"

            def rest(self, endpoint):
                return bad

        with self.assertRaises(mod.PlanError):
            mod.verify_trusted_workflow_blob(BadBlobClient())

    def test_log_archive_requires_exact_pr_repo_command_and_success(self) -> None:
        payload = enrollment_log_zip()
        proof = mod.inspect_enrollment_log_archive(
            payload, pull_request_number=7, repo_name="Jonnyton/TinyAssets"
        )
        self.assertEqual(hashlib.sha256(payload).hexdigest(), proof["log_archive_sha256"])
        self.assertTrue(proof["log_pr_number_matches"])
        self.assertTrue(proof["log_repo_matches"])
        self.assertTrue(proof["log_contains_exact_auto_squash_command"])
        self.assertTrue(proof["log_contains_enrollment_success"])

        no_success = mod.inspect_enrollment_log_archive(
            enrollment_log_zip(include_success=False),
            pull_request_number=7,
            repo_name="Jonnyton/TinyAssets",
        )
        self.assertFalse(no_success["log_contains_enrollment_success"])

        confused = enrollment_log_zip(number=70, success_number=7)
        confused_proof = mod.inspect_enrollment_log_archive(
            confused,
            pull_request_number=7,
            repo_name="Jonnyton/TinyAssets",
        )
        self.assertFalse(confused_proof["log_pr_number_matches"])

    def test_log_archive_rejects_unsafe_and_encrypted_members(self) -> None:
        unsafe = io.BytesIO()
        with zipfile.ZipFile(unsafe, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("../escape.txt", "not trusted")
        with self.assertRaisesRegex(mod.PlanError, "unsafe entry"):
            mod.inspect_enrollment_log_archive(
                unsafe.getvalue(),
                pull_request_number=7,
                repo_name="Jonnyton/TinyAssets",
            )

        encrypted = bytearray(enrollment_log_zip())
        for signature, flag_offset in (
            (b"PK\x03\x04", 6),
            (b"PK\x01\x02", 8),
        ):
            offset = encrypted.find(signature)
            self.assertGreaterEqual(offset, 0)
            start = offset + flag_offset
            flags = int.from_bytes(encrypted[start : start + 2], "little") | 0x1
            encrypted[start : start + 2] = flags.to_bytes(2, "little")
        with self.assertRaisesRegex(mod.PlanError, "unsafe entry"):
            mod.inspect_enrollment_log_archive(
                bytes(encrypted),
                pull_request_number=7,
                repo_name="Jonnyton/TinyAssets",
            )

    def test_attribution_collector_binds_run_job_step_log_and_blob(self) -> None:
        pr = self.pr()
        run = {
            "id": 101,
            "node_id": "WR_101",
            "workflow_id": mod.AUTO_ENROLL_WORKFLOW_ID,
            "path": ".github/workflows/auto-enroll-merge.yml",
            "event": "pull_request_target",
            "status": "completed",
            "conclusion": "success",
            "run_number": 1,
            "run_attempt": 1,
            "created_at": "2026-07-25T01:00:00Z",
            "run_started_at": "2026-07-25T01:00:00Z",
            "updated_at": "2026-07-25T01:00:04Z",
            "head_branch": "feature",
            "head_sha": "historical-head",
            "actor": {"login": "jonnyton", "id": 1, "node_id": "U_1"},
            "triggering_actor": {"login": "jonnyton", "id": 1, "node_id": "U_1"},
            "pull_requests": [
                {
                    "number": 7,
                    "head": {"sha": "historical-head"},
                    "base": {"ref": "main"},
                }
            ],
            "html_url": "https://example.invalid/actions/runs/101",
        }
        ignored_run = copy.deepcopy(run)
        ignored_run["id"] = 102
        ignored_run["node_id"] = "WR_102"
        ignored_run["status"] = "in_progress"
        ignored_run["conclusion"] = None
        ignored_run["created_at"] = "2026-07-25T02:00:00Z"
        ignored_run["updated_at"] = "2026-07-25T02:00:04Z"
        competing_run = copy.deepcopy(run)
        competing_run["id"] = 103
        competing_run["node_id"] = "WR_103"
        competing_run["html_url"] = "https://example.invalid/actions/runs/103"
        job = {
            "id": 202,
            "name": "Enroll for auto-merge",
            "status": "completed",
            "conclusion": "success",
            "started_at": "2026-07-25T01:00:00Z",
            "completed_at": "2026-07-25T01:00:04Z",
            "head_branch": "feature",
            "head_sha": "deadbeef",
            "html_url": "https://example.invalid/jobs/202",
            "steps": [
                {
                    "number": 3,
                    "name": "Enable auto-merge",
                    "status": "completed",
                    "conclusion": "success",
                    "started_at": "2026-07-25T01:00:01Z",
                    "completed_at": "2026-07-25T01:00:03Z",
                }
            ],
        }

        class AttributionClient:
            repo = "Jonnyton/TinyAssets"

            def __init__(self, *, competing=False, failed_log_run=None):
                self.competing = competing
                self.failed_log_run = failed_log_run

            def rest(self, endpoint):
                if "/git/blobs/" in endpoint:
                    return trusted_workflow_blob_response(endpoint.rsplit("/", 1)[-1])
                if "/contents/" in endpoint:
                    return {
                        "sha": mod.TRUSTED_AUTO_ENROLL_WORKFLOW_BLOB_SHA,
                        "size": 4255,
                    }
                raise AssertionError(endpoint)

            def rest_array_collection(self, endpoint, *, max_pages=1000):
                self.history_endpoint = endpoint
                rows = [
                    {
                        "sha": mod.AUTO_ENROLL_PATH_INTRODUCTION_COMMIT,
                        "commit": {
                            "committer": {"date": "2026-07-22T00:38:24Z"}
                        },
                    }
                ]
                return rows, complete_connection(
                    kind="workflow_source_history",
                    label_name=mod.AUTO_ENROLL_WORKFLOW_PATH,
                    count=1,
                    completion_basis="github_link_header_chain_v1",
                )

            def rest_collection(self, endpoint, *, list_key):
                if list_key == "workflow_runs":
                    runs = [run, ignored_run]
                    if self.competing:
                        runs.append(competing_run)
                    return runs, complete_connection(
                        kind="workflow_runs",
                        label_name="",
                        count=len(runs),
                        completion_basis="reported_total_count",
                    )
                if list_key == "jobs":
                    self.job_endpoint = endpoint
                    matching_run = next(
                        (
                            run_id
                            for run_id in (101, 103)
                            if f"/runs/{run_id}/" in endpoint
                        ),
                        None,
                    )
                    if matching_run is None:
                        raise AssertionError(endpoint)
                    matching_job = copy.deepcopy(job)
                    matching_job["id"] = 202 if matching_run == 101 else 203
                    return [matching_job], complete_connection(
                        kind="workflow_jobs",
                        label_name=str(matching_run),
                        count=1,
                        completion_basis="reported_total_count",
                    )
                raise AssertionError((endpoint, list_key))

            def bytes(self, endpoint):
                self.log_endpoint = endpoint
                if (
                    self.failed_log_run is not None
                    and f"/runs/{self.failed_log_run}/" in endpoint
                ):
                    raise mod.RetirementError("simulated transient log failure")
                return enrollment_log_zip()

        inventory = {
            "pull_requests": [pr],
            "connections": [
                complete_connection(
                    kind="open_pull_requests",
                    label_name="",
                    count=1,
                    completion_basis="graphql_total_count",
                )
            ],
            "workflow": {
                "id": mod.AUTO_ENROLL_WORKFLOW_ID,
                "node_id": "W_auto",
                "path": ".github/workflows/auto-enroll-merge.yml",
                "state": "active",
            },
            "workflow_runs": [],
            "attribution": [],
            "planned_actions": [],
            "apply_complete": False,
        }
        client = AttributionClient()
        result = mod.collect_auto_merge_attribution(client, inventory)
        self.assertEqual("attributed", result["attribution"][0]["classification"])
        evidence = result["attribution"][0]["evidence"]
        self.assertEqual(1, len(evidence))
        self.assertEqual(101, evidence[0]["run_id"])
        self.assertEqual(202, evidence[0]["job_id"])
        self.assertTrue(evidence[0]["workflow_blobs_verified"])
        self.assertTrue(evidence[0]["log_contains_enrollment_success"])
        self.assertEqual("historical-head", evidence[0]["head_sha"])
        self.assertEqual("deadbeef", evidence[0]["current_head_sha"])
        connections = {
            (row["kind"], row["label_name"]): row for row in result["connections"]
        }
        self.assertEqual(2, connections[("workflow_runs", "")]["count"])
        self.assertEqual(1, connections[("workflow_jobs", "101")]["count"])
        self.assertEqual(
            mod.AUTO_ENROLL_PATH_INTRODUCTION_COMMIT,
            result["source_history"]["path_introduction_commit"],
        )
        self.assertIn("sha=main", client.history_endpoint)
        self.assertTrue(client.log_endpoint.endswith("/actions/runs/101/logs"))

        ambiguous = mod.collect_auto_merge_attribution(
            AttributionClient(competing=True, failed_log_run=103),
            inventory,
        )
        row = ambiguous["attribution"][0]
        self.assertEqual("ambiguous_preserve", row["classification"])
        self.assertEqual(
            [101, 103],
            sorted(evidence["run_id"] for evidence in row["evidence"]),
        )
        unavailable = [
            evidence
            for evidence in row["evidence"]
            if evidence.get("evidence_status") == "log_unavailable"
        ]
        self.assertEqual(1, len(unavailable))
        self.assertEqual("log_read_failed", unavailable[0]["reason"])
        ambiguous_receipt = mod.build_receipt(
            operation=mod.AUTO_MERGE_OPERATION,
            repo=repo(),
            source_revision="abc123",
            inventory=ambiguous,
        )
        mod.verify_receipt(ambiguous_receipt)
        forged = copy.deepcopy(ambiguous)
        next(
            evidence
            for evidence in forged["attribution"][0]["evidence"]
            if evidence.get("evidence_status") == "log_unavailable"
        )["reason"] = "pretend_absent"
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.AUTO_MERGE_OPERATION,
                repo=repo(),
                source_revision="abc123",
                inventory=forged,
            )

    def test_actor_query_preserves_ids_for_every_supported_actor_shape(self) -> None:
        for fragment in (
            "... on Bot { id }",
            "... on EnterpriseUserAccount { id }",
            "... on Mannequin { id }",
            "... on Organization { id }",
            "... on User { id }",
        ):
            self.assertIn(fragment, mod.AUTO_MERGE_QUERY)


class ReadOnlyClientTests(unittest.TestCase):
    def test_client_exposes_only_structured_reads_and_rest_forces_get(self) -> None:
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(
                args, 0, stdout=included_json_response([])
            )

        client = mod.ReadOnlyGitHub("Jonnyton/TinyAssets", runner=runner)
        self.assertFalse(hasattr(client, "mutate"))
        self.assertFalse(hasattr(client, "_json"))
        self.assertFalse(hasattr(client, "_run"))
        self.assertEqual([], client.rest("repos/Jonnyton/TinyAssets"))
        self.assertEqual(
            [
                [
                    "gh",
                    "api",
                    "--hostname",
                    "github.com",
                    "--include",
                    "--method",
                    "GET",
                    "repos/Jonnyton/TinyAssets",
                ]
            ],
            calls,
        )

    def test_invalid_repositories_and_rest_endpoints_never_reach_runner(self) -> None:
        for invalid_repo in (
            "Jonnyton",
            "Jonnyton/TinyAssets/extra",
            "@owner/TinyAssets",
            "Jonnyton/@repo",
            "Jonny ton/TinyAssets",
            "-Jonnyton/TinyAssets",
        ):
            with self.subTest(repo=invalid_repo), self.assertRaises(ValueError):
                mod.ReadOnlyGitHub(invalid_repo)

        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, stdout="{}")

        client = mod.ReadOnlyGitHub("Jonnyton/TinyAssets", runner=runner)
        for endpoint in (
            "-Ftitle=x",
            "-ftitle=x",
            "--field=title=x",
            "https://api.github.com/repos/Jonnyton/TinyAssets",
            "repos/foreign/repository/issues",
            "orgs/Jonnyton",
            "repos/Jonnyton/TinyAssets/issues -Ftitle=x",
            "repos/Jonnyton/TinyAssets/%2e%2e/issues",
            "repos/Jonnyton/TinyAssets/issues%2f1",
            "repos/Jonnyton/TinyAssets/issues%5c1",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(mod.ApplyBlocked):
                client.rest(endpoint)
        self.assertEqual([], calls)

    def test_page_size_parser_rejects_missing_duplicate_bounds_and_non_ascii(self) -> None:
        invalid = (
            "repos/Jonnyton/TinyAssets/issues",
            "repos/Jonnyton/TinyAssets/issues?per_page=100&per_page=100",
            "repos/Jonnyton/TinyAssets/issues?per_page=0",
            "repos/Jonnyton/TinyAssets/issues?per_page=101",
            "repos/Jonnyton/TinyAssets/issues?per_page=" + chr(0xFF11),
            "repos/Jonnyton/TinyAssets/issues?per_page=" + chr(0x00B2),
        )
        for endpoint in invalid:
            with self.subTest(endpoint=endpoint), self.assertRaises(mod.PlanError):
                mod._requested_page_size(endpoint)
        self.assertEqual(
            100,
            mod._requested_page_size(
                "repos/Jonnyton/TinyAssets/issues?per_page=100"
            ),
        )

    def test_graphql_accepts_only_exact_query_and_plain_owner_name(self) -> None:
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, stdout="[]")

        client = mod.ReadOnlyGitHub("Jonnyton/TinyAssets", runner=runner)
        self.assertEqual(
            [],
            client.graphql_pages(
                mod.AUTO_MERGE_QUERY,
                {"owner": "Jonnyton", "name": "TinyAssets"},
            ),
        )
        self.assertEqual(1, len(calls))
        self.assertIn("github.com", calls[0])
        self.assertEqual(
            ["--hostname", "github.com"],
            calls[0][2:4],
        )
        self.assertNotIn("-F", calls[0])
        self.assertIn(f"query={mod.AUTO_MERGE_QUERY}", calls[0])

        rejected = (
            (
                mod.AUTO_MERGE_QUERY + "\n",
                {"owner": "Jonnyton", "name": "TinyAssets"},
            ),
            (
                mod.AUTO_MERGE_QUERY,
                {"owner": "Jonnyton", "name": "TinyAssets", "query": "@payload.graphql"},
            ),
            (mod.AUTO_MERGE_QUERY, {"owner": "@payload", "name": "TinyAssets"}),
            (mod.AUTO_MERGE_QUERY, {"owner": "Jonnyton", "name": "@-"}),
            (mod.AUTO_MERGE_QUERY, {"owner": "Jonnyton"}),
        )
        for query, fields in rejected:
            with self.subTest(query=query, fields=fields), self.assertRaises(
                mod.ApplyBlocked
            ):
                client.graphql_pages(query, fields)
        self.assertEqual(1, len(calls))

    def test_link_pagination_follows_next_after_short_page_and_proves_terminal(self) -> None:
        endpoint = (
            "repos/Jonnyton/TinyAssets/issues"
            "?state=all&labels=auto-bug&per_page=100"
        )
        next_url = (
            "https://api.github.com/repositories/42/issues"
            "?state=all&labels=auto-bug&per_page=100"
            "&after=opaque-github-cursor&page=2"
        )
        responses = [
            included_json_response(
                [{"id": 1}],
                request_id="REQ_page_1",
                link=f'<{next_url}>; rel="next"',
            ),
            included_json_response([{"id": 2}], request_id="REQ_page_2"),
        ]
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, stdout=responses.pop(0))

        client = mod.ReadOnlyGitHub("Jonnyton/TinyAssets", runner=runner)
        client.bind_repo_database_id(42)
        rows, connection = client.rest_array_collection(endpoint)
        self.assertEqual([{"id": 1}, {"id": 2}], rows)
        self.assertEqual(
            [
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
                [
                    "gh",
                    "api",
                    "--hostname",
                    "github.com",
                    "--include",
                    "--method",
                    "GET",
                    next_url,
                ],
            ],
            calls,
        )
        self.assertEqual(2, connection["pages"])
        self.assertEqual(2, connection["count"])
        self.assertIsNone(connection["total_count"])
        self.assertTrue(connection["complete"])
        self.assertEqual(
            "github_link_header_chain_v1", connection["completion_basis"]
        )
        pagination = connection["pagination"]
        self.assertEqual("github_link_header_chain_v1", pagination["mode"])
        self.assertEqual(100, pagination["page_size"])
        self.assertEqual(
            [0, 1],
            [page["ordinal"] for page in pagination["page_receipts"]],
        )
        self.assertEqual(
            [1, 1],
            [page["item_count"] for page in pagination["page_receipts"]],
        )
        self.assertIsNotNone(
            pagination["page_receipts"][0]["next_url_digest"]
        )
        self.assertEqual(
            pagination["page_receipts"][0]["next_url_digest"],
            pagination["page_receipts"][1]["request_url_digest"],
        )
        self.assertIsNone(pagination["page_receipts"][1]["next_url_digest"])
        self.assertEqual(
            {"oracle": "rel_next_absent", "page_ordinal": 1},
            pagination["terminal"],
        )
        mod._validate_complete_connections([connection], repo=repo())

    def test_link_pagination_rejects_full_page_without_next_link(self) -> None:
        endpoint = "repos/Jonnyton/TinyAssets/issues?state=all&per_page=100"
        response = included_json_response(
            [{"id": index} for index in range(1, 101)],
            request_id="REQ_full_terminal",
        )

        def runner(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, stdout=response)

        client = mod.ReadOnlyGitHub("Jonnyton/TinyAssets", runner=runner)
        client.bind_repo_database_id(42)
        with self.assertRaises(mod.PlanError):
            client.rest_array_collection(endpoint)

    def test_link_pagination_rejects_page_larger_than_requested_bound(self) -> None:
        endpoint = "repos/Jonnyton/TinyAssets/issues?state=all&per_page=30"
        next_url = (
            "https://api.github.com/repositories/42/issues"
            "?state=all&per_page=30&page=2"
        )
        responses = [
            included_json_response(
                [{"id": index} for index in range(1, 32)],
                request_id="REQ_oversized",
                link=f'<{next_url}>; rel="next"',
            ),
            included_json_response([], request_id="REQ_terminal"),
        ]

        def runner(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, stdout=responses.pop(0))

        client = mod.ReadOnlyGitHub("Jonnyton/TinyAssets", runner=runner)
        client.bind_repo_database_id(42)
        with self.assertRaises(mod.PlanError):
            client.rest_array_collection(endpoint)

    def test_link_pagination_rejects_untrusted_or_incomplete_chains(self) -> None:
        endpoint = (
            "repos/Jonnyton/TinyAssets/issues"
            "?state=all&labels=auto-bug&per_page=100"
        )
        valid_next = (
            "https://api.github.com/repositories/42/issues"
            "?state=all&labels=auto-bug&per_page=100&page=2"
        )
        cases = {
            "missing_request_id": [
                included_json_response([{"id": 1}], request_id=None)
            ],
            "malformed_link": [
                included_json_response(
                    [{"id": 1}], link="this is not an RFC 8288 link"
                )
            ],
            "foreign_host": [
                included_json_response(
                    [{"id": 1}],
                    link=(
                        '<https://evil.invalid/repositories/42/issues'
                        '?state=all&labels=auto-bug&per_page=100&page=2>; rel="next"'
                    ),
                )
            ],
            "foreign_repo": [
                included_json_response(
                    [{"id": 1}],
                    link=(
                        '<https://api.github.com/repositories/99/issues'
                        '?state=all&labels=auto-bug&per_page=100&page=2>; rel="next"'
                    ),
                )
            ],
            "scope_change": [
                included_json_response(
                    [{"id": 1}],
                    link=(
                        '<https://api.github.com/repositories/42/issues'
                        '?state=all&labels=other&per_page=100&page=2>; rel="next"'
                    ),
                )
            ],
            "unexpected_query_key": [
                included_json_response(
                    [{"id": 1}],
                    link=(
                        '<https://api.github.com/repositories/42/issues'
                        '?state=all&labels=auto-bug&per_page=100'
                        '&unexpected=value&page=2>; rel="next"'
                    ),
                )
            ],
            "duplicate_cursor": [
                included_json_response(
                    [{"id": 1}],
                    link=(
                        '<https://api.github.com/repositories/42/issues'
                        '?state=all&labels=auto-bug&per_page=100'
                        '&after=one&after=two&page=2>; rel="next"'
                    ),
                )
            ],
            "blank_cursor": [
                included_json_response(
                    [{"id": 1}],
                    link=(
                        '<https://api.github.com/repositories/42/issues'
                        '?state=all&labels=auto-bug&per_page=100'
                        '&after=&page=2>; rel="next"'
                    ),
                )
            ],
            "loop": [
                included_json_response(
                    [{"id": 1}],
                    link=(
                        '<https://api.github.com/repositories/42/issues'
                        '?state=all&labels=auto-bug&per_page=100>; rel="next"'
                    ),
                )
            ],
            "duplicate_item": [
                included_json_response(
                    [{"id": 1}], link=f'<{valid_next}>; rel="next"'
                ),
                included_json_response([{"id": 1}], request_id="REQ_page_2"),
            ],
        }
        for name, configured_responses in cases.items():
            responses = list(configured_responses)

            def runner(args, **kwargs):
                return subprocess.CompletedProcess(args, 0, stdout=responses.pop(0))

            client = mod.ReadOnlyGitHub("Jonnyton/TinyAssets", runner=runner)
            client.bind_repo_database_id(42)
            with self.subTest(name=name), self.assertRaises(mod.RetirementError):
                client.rest_array_collection(endpoint)

    def test_link_pagination_rejects_a_chain_beyond_the_page_bound(self) -> None:
        endpoint = "repos/Jonnyton/TinyAssets/labels?per_page=100"
        page_2 = (
            "https://api.github.com/repositories/42/labels"
            "?per_page=100&page=2"
        )
        page_3 = (
            "https://api.github.com/repositories/42/labels"
            "?per_page=100&page=3"
        )
        responses = [
            included_json_response(
                [{"id": 1}], link=f'<{page_2}>; rel="next"'
            ),
            included_json_response(
                [{"id": 2}],
                request_id="REQ_page_2",
                link=f'<{page_3}>; rel="next"',
            ),
        ]

        def runner(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, stdout=responses.pop(0))

        client = mod.ReadOnlyGitHub("Jonnyton/TinyAssets", runner=runner)
        client.bind_repo_database_id(42)
        with self.assertRaises(mod.RetirementError):
            client.rest_array_collection(endpoint, max_pages=2)

    def test_rest_collection_rejects_truncated_object_pages(self) -> None:
        def runner(args, **kwargs):
            value = [
                {
                    "total_count": 2,
                    "workflow_runs": [{"id": 1}],
                }
            ]
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(value))

        client = mod.ReadOnlyGitHub("Jonnyton/TinyAssets", runner=runner)
        with self.assertRaises(mod.PlanError):
            client.rest_collection(
                "repos/Jonnyton/TinyAssets/actions/runs?per_page=100",
                list_key="workflow_runs",
            )

    def test_gh_failure_and_graphql_structure_are_sanitized(self) -> None:
        def failing_runner(args, **kwargs):
            raise subprocess.CalledProcessError(
                1, args, stderr="token=top-secret-value", output="not for callers"
            )

        client = mod.ReadOnlyGitHub("Jonnyton/TinyAssets", runner=failing_runner)
        with self.assertRaises(mod.RetirementError) as failed:
            client.rest("repos/Jonnyton/TinyAssets")
        self.assertNotIn("top-secret-value", str(failed.exception))

        def missing_runner(args, **kwargs):
            raise OSError("sensitive local process detail")

        with self.assertRaises(mod.RetirementError) as missing:
            mod.ReadOnlyGitHub(
                "Jonnyton/TinyAssets", runner=missing_runner
            ).bytes("repos/Jonnyton/TinyAssets/actions/runs/1/logs")
        self.assertNotIn("sensitive local process detail", str(missing.exception))

        class MalformedGraphQLClient:
            repo = "Jonnyton/TinyAssets"

            def bind_repo_database_id(self, database_id):
                self.database_id = database_id

            def rest(self, endpoint):
                return {
                    "node_id": "R_repo", "id": 42,
                    "full_name": "Jonnyton/TinyAssets", "default_branch": "main",
                }

            def graphql_pages(self, query, fields):
                return [{"data": {"repository": None}}]

        with self.assertRaises(mod.RetirementError):
            mod.collect_auto_merge_inventory(MalformedGraphQLClient())

    def test_auto_inventory_rejects_truncated_graphql_nodes(self) -> None:
        repository = {"id": "R_repo", "nameWithOwner": "Jonnyton/TinyAssets"}
        page = {
            "data": {
                "repository": {
                    "pullRequests": {
                        "totalCount": 2,
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                        "nodes": [
                            {
                                "id": "PR_1",
                                "number": 1,
                                "state": "OPEN",
                                "isDraft": False,
                                "baseRefName": "main",
                                "headRefName": "feature",
                                "headRefOid": "head",
                                "repository": repository,
                                "baseRepository": repository,
                                "headRepository": repository,
                                "autoMergeRequest": None,
                            }
                        ],
                    }
                }
            }
        }

        class FakeClient:
            repo = "Jonnyton/TinyAssets"

            def bind_repo_database_id(self, database_id):
                self.database_id = database_id

            def rest(self, endpoint):
                if endpoint.endswith(str(mod.AUTO_ENROLL_WORKFLOW_ID)):
                    return {
                        "id": mod.AUTO_ENROLL_WORKFLOW_ID,
                        "node_id": "W_1",
                        "path": ".github/workflows/auto-enroll-merge.yml",
                        "state": "active",
                    }
                return {
                    "node_id": "R_repo",
                    "id": 42,
                    "full_name": "Jonnyton/TinyAssets",
                    "default_branch": "main",
                }

            def graphql_pages(self, query, fields):
                return [page]

        with self.assertRaises(mod.PlanError):
            mod.collect_auto_merge_inventory(FakeClient())

        duplicate_page = copy.deepcopy(page)
        duplicate_page["data"]["repository"]["pullRequests"]["totalCount"] = 2
        duplicate_page["data"]["repository"]["pullRequests"]["nodes"] *= 2

        class DuplicateClient(FakeClient):
            def graphql_pages(self, query, fields):
                return [duplicate_page]

        with self.assertRaises(mod.PlanError):
            mod.collect_auto_merge_inventory(DuplicateClient())

        error_page = copy.deepcopy(page)
        error_page["errors"] = [{"message": "do not expose remote details"}]

        class ErrorClient(FakeClient):
            def graphql_pages(self, query, fields):
                return [error_page]

        with self.assertRaises(mod.RetirementError) as failed:
            mod.collect_auto_merge_inventory(ErrorClient())
        self.assertNotIn("remote details", str(failed.exception))


class CliTests(unittest.TestCase):
    def test_offline_plan_rejects_attribution_bearing_auto_merge_inventory(self) -> None:
        value, _ = complete_auto_receipt()
        inventory = copy.deepcopy(value["plan"]["inventory"])
        inventory["apply_complete"] = False
        inventory["planned_actions"] = []
        inventory["workflow"]["state"] = "active"
        inventory["quiescence"] = None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_path = root / "repo.json"
            inventory_path = root / "inventory.json"
            output_path = root / "receipt.json"
            repo_path.write_text(json.dumps(repo()), encoding="utf-8")
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
            with self.assertRaises(mod.PlanError):
                mod.main(
                    [
                        "plan",
                        "--operation",
                        mod.AUTO_MERGE_OPERATION,
                        "--repo-json",
                        str(repo_path),
                        "--inventory-json",
                        str(inventory_path),
                        "--source-revision",
                        "abc123",
                        "--out",
                        str(output_path),
                    ]
                )
            self.assertFalse(output_path.exists())

    def test_verify_reports_integrity_without_claiming_external_evidence(self) -> None:
        value, _ = complete_auto_receipt()
        with tempfile.TemporaryDirectory() as tmp:
            receipt_path = Path(tmp) / "receipt.json"
            receipt_path.write_text(json.dumps(value), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = mod.main(["verify", str(receipt_path)])
        self.assertEqual(0, result)
        response = json.loads(output.getvalue())
        self.assertTrue(response["integrity_valid"])
        self.assertFalse(response["external_evidence_verified"])
        self.assertEqual(value["receipt_digest"], response["receipt_digest"])


if __name__ == "__main__":
    unittest.main()
