"""Focused tests for the receipt-bound GitHub-state retirement tool."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


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


def label_inventory() -> dict:
    definitions = [
        {
            "node_id": f"L_{index}",
            "name": name,
            "color": f"{index:06x}",
            "description": "café" if index == 1 else None,
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
            {
                "kind": "label_definitions",
                "label_name": "",
                "pages": 1,
                "count": 28,
                "total_count": 28,
                "complete": True,
            },
            *[
            {
                "kind": "retired_label_associations",
                "label_name": name,
                "pages": 1,
                "count": 1 if name == "auto-bug" else 0,
                "total_count": 1 if name == "auto-bug" else 0,
                "complete": True,
            }
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


def auto_pr(actor_type="Bot", login="app/github-actions") -> dict:
    repository = {"id": "R_repo", "nameWithOwner": "Jonnyton/TinyAssets"}
    return {
        "node_id": "PR_1",
        "number": 7,
        "state": "OPEN",
        "is_draft": False,
        "base_ref_name": "main",
        "head_ref_name": "feature",
        "head_ref_oid": "deadbeef",
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
                "id": "B_1",
            },
        },
    }


def exact_evidence() -> dict:
    return {
        "workflow_id": mod.AUTO_ENROLL_WORKFLOW_ID,
        "run_id": 101,
        "job_id": 202,
        "step_number": 3,
        "workflow_path": ".github/workflows/auto-enroll-merge.yml",
        "workflow_source_sha": "workflow-source-sha",
        "run_url": "https://example.invalid/actions/runs/101",
        "event": "pull_request_target",
        "conclusion": "success",
        "pull_request_number": 7,
        "head_sha": "deadbeef",
        "run_created_at": "2026-07-25T01:00:00Z",
        "run_updated_at": "2026-07-25T01:00:04Z",
        "job_name": "Enroll for auto-merge",
        "step_name": "Enable auto-merge",
        "step_conclusion": "success",
        "step_started_at": "2026-07-25T01:00:01Z",
        "step_completed_at": "2026-07-25T01:00:03Z",
        "source_contains_exact_auto_squash_command": True,
    }


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
            {
                "kind": "open_pull_requests",
                "label_name": "",
                "pages": 1,
                "count": 1,
                "total_count": 1,
                "complete": True,
            },
            {
                "kind": "workflow_runs",
                "label_name": "",
                "pages": 1,
                "count": 1,
                "total_count": 1,
                "complete": True,
            },
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
                "status": "completed",
                "conclusion": "success",
            }
        ],
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
            journal.persist_intent(
                apply_key=value["apply_key"],
                ordinal=0,
                action_kind="remove_label",
                target_node_id="I_1",
                planned_before={"labels": ["auto-bug", "keep"]},
                planned_after={"labels": ["keep"]},
            )
            with self.assertRaises(mod.JournalConflict):
                journal.persist_intent(
                    apply_key=value["apply_key"],
                    ordinal=0,
                    action_kind="remove_label",
                    target_node_id="I_1",
                    planned_before={"labels": ["auto-bug", "different"]},
                    planned_after={"labels": ["different"]},
                )
            rows = journal.intent_rows(value["apply_key"])
            self.assertEqual("intent_persisted", rows[0]["state"])

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
            journal.persist_intent(
                apply_key=value["apply_key"],
                ordinal=0,
                action_kind=action["kind"],
                target_node_id=action["target_node_id"],
                planned_before=action["planned_before"],
                planned_after=action["planned_after"],
            )
            journal.set_pre_read(
                value["apply_key"],
                0,
                action["planned_before"],
                "pre_read_authorized",
            )
            mod.apply_actions(
                receipt=value,
                proof=authority_proof(mod.AUTO_MERGE_OPERATION),
                apply_key=value["apply_key"],
                confirm_plan_digest=value["plan_digest"],
                actions=[action],
                journal=journal,
                reader=self.Reader([action["planned_after"]]),
                mutator=writer,
                recovery_authorized=False,
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
                    reader=self.Reader([action["planned_after"]]),
                    mutator=writer,
                    recovery_authorized=True,
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


class AttributionTests(unittest.TestCase):
    def pr(self, actor_type="Bot", login="app/github-actions") -> dict:
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

    def test_exact_unique_historical_evidence_attributes(self) -> None:
        result = mod.classify_auto_merge(self.pr(), [self.evidence()])
        self.assertEqual("attributed", result["classification"])
        result = mod.classify_auto_merge(
            self.pr(), [self.evidence(), self.evidence()]
        )
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


class ReadOnlyClientTests(unittest.TestCase):
    def test_client_has_no_mutator_and_rejects_mutating_options(self) -> None:
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, stdout="{}")

        client = mod.ReadOnlyGitHub("Jonnyton/TinyAssets", runner=runner)
        self.assertFalse(hasattr(client, "mutate"))
        with self.assertRaises(mod.ApplyBlocked):
            client._json(["-X", "DELETE", "repos/x/y"])
        with self.assertRaises(mod.ApplyBlocked):
            client._json(["--method=DELETE", "repos/x/y"])
        with self.assertRaises(mod.ApplyBlocked):
            client._json(["-XDELETE", "repos/x/y"])
        with self.assertRaises(mod.ApplyBlocked):
            client._json(["repos/x/y", "-f", "state=closed"])
        with self.assertRaises(mod.ApplyBlocked):
            client._json(["repos/x/y", "--field=state=closed"])
        self.assertEqual([], calls)

    def test_rest_pagination_requires_page_arrays(self) -> None:
        def runner(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, stdout='[{"not":"a page"}]')

        client = mod.ReadOnlyGitHub("Jonnyton/TinyAssets", runner=runner)
        with self.assertRaises(mod.PlanError):
            client.rest_pages("repos/Jonnyton/TinyAssets/labels?per_page=100")

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

        repo_value, inventory = mod.collect_auto_merge_inventory(FakeClient())
        with self.assertRaises(mod.PlanError):
            mod.build_receipt(
                operation=mod.AUTO_MERGE_OPERATION,
                repo=repo_value,
                source_revision="abc123",
                inventory=inventory,
            )


if __name__ == "__main__":
    unittest.main()
