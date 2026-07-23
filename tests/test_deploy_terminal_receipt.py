"""Table-driven contract tests for the terminal deploy receipt classifier.

The workflow owns observation, mutation, and atomic installation.  The module
under test owns only deterministic validation, classification, projection, and
wording policy.  Its executable interface reads one JSON observation object
from stdin and writes one canonical JSON receipt to stdout.
"""

from __future__ import annotations

import base64
import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from scripts.deploy_terminal_receipt import (
    build_terminal_receipt,
    initial_terminal_receipt_result,
    rollback_issue_sentence,
    rollback_step_exit_code,
    terminal_receipt_issue_sentence,
)

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "scripts" / "deploy_terminal_receipt.py"

_ATTEMPTED = f"ghcr.io/tinyassets/tinyassets@sha256:{'a' * 64}"
_PREVIOUS = f"ghcr.io/tinyassets/tinyassets@sha256:{'b' * 64}"
_ANCESTOR = f"ghcr.io/tinyassets/tinyassets@sha256:{'c' * 64}"
_OTHER = f"ghcr.io/tinyassets/tinyassets@sha256:{'d' * 64}"
_ATTEMPTED_SHA = "1" * 40
_PREVIOUS_SHA = "2" * 40
_TERMINAL_AT = "2026-07-23T20:21:22Z"
_PRIOR_DEPLOYED_AT = "2026-07-20T01:02:03Z"
_CONFIG_HASH = f"sha256:{'e' * 64}"

_LEGACY_KEYS = {
    "git_sha",
    "image_tag",
    "image_ref",
    "image_digest",
    "build_run_id",
    "build_run_url",
    "deploy_run_id",
    "deploy_run_url",
    "config_hash",
    "config_version",
    "schema_migration_rev",
    "canary_bundle_status",
    "deployed_at",
    "rollback_target",
    "actor",
    "repository",
    "workflow_event",
}

_ENUMS = {
    "outcome": {
        "deployed",
        "rolled_back",
        "rollback_failed",
        "failed_without_rollback",
    },
    "forward_deploy_status": {"succeeded", "failed"},
    "forward_canary_status": {"passed", "failed", "not_run"},
    "prior_receipt_match_status": {
        "absent",
        "invalid",
        "mismatch",
        "v1_identity_match",
        "v2_terminal_proof_match",
    },
    "attempted_source_provenance": {"digest_revision_label", "unknown"},
    "active_source_provenance": {
        "attempted_digest",
        "digest_revision_label",
        "v2_terminal_proof",
        "unknown",
    },
    "active_identity_status": {
        "agreed",
        "mismatch",
        "configured_unknown",
        "running_unknown",
        "both_unknown",
    },
    "rollback_result": {"succeeded", "failed", "not_attempted"},
    "rollback_canary_status": {"passed", "failed", "not_run"},
    "rollback_reason": {
        "attempted",
        "not_needed",
        "pre_host_write_failure",
        "image_mutation_not_started",
        "no_valid_target",
    },
}


def _observations(**overrides: Any) -> dict[str, Any]:
    """Return a fully green workflow-run observation."""

    value: dict[str, Any] = {
        "production_mutation_started": True,
        "image_mutation_started": True,
        "forward_deploy_status": "succeeded",
        "forward_canary_status": "passed",
        "rollback_attempted": False,
        "rollback_result": "not_attempted",
        "rollback_canary_status": "not_run",
        "rollback_reason": "not_needed",
        "attempted_image_tag": "ghcr.io/tinyassets/tinyassets:build-111",
        "attempted_image_ref": _ATTEMPTED,
        "attempted_revision_label": _ATTEMPTED_SHA,
        "workflow_event": "workflow_run",
        "workflow_head_sha": _ATTEMPTED_SHA,
        "github_sha": "f" * 40,
        "build_run_id": "111",
        "build_run_url": "https://github.com/tinyassets/tinyassets/actions/runs/111",
        "deploy_run_id": "222",
        "deploy_run_url": "https://github.com/tinyassets/tinyassets/actions/runs/222",
        "actor": "deploy-bot",
        "repository": "tinyassets/tinyassets",
        "previous_configured_image_ref": _PREVIOUS,
        "previous_running_image_ref": _PREVIOUS,
        "configured_image_ref": _ATTEMPTED,
        "running_image_ref": _ATTEMPTED,
        "config_hash": _CONFIG_HASH,
        "terminal_at": _TERMINAL_AT,
        "prior_receipt_b64": "",
    }
    value.update(overrides)
    return value


def _b64_json(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return base64.b64encode(payload).decode("ascii")


def _v1_prior(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "release_state_version": 1,
        "git_sha": _PREVIOUS_SHA,
        "image_tag": "ghcr.io/tinyassets/tinyassets:old-v1",
        "image_ref": _PREVIOUS,
        "image_digest": _PREVIOUS,
        "build_run_id": "v1-build",
        "build_run_url": "https://example.invalid/v1-build",
        "deploy_run_id": "v1-deploy",
        "deploy_run_url": "https://example.invalid/v1-deploy",
        "deployed_at": _PRIOR_DEPLOYED_AT,
        "rollback_target": _ANCESTOR,
    }
    value.update(overrides)
    return value


def _v2_terminal_proof(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "release_state_version": 2,
        "outcome": "deployed",
        "forward_deploy_status": "succeeded",
        "forward_canary_status": "passed",
        "production_mutation_started": True,
        "image_mutation_started": True,
        "prior_receipt_match_status": "absent",
        "attempted_source_provenance": "digest_revision_label",
        "attempted_git_sha": _PREVIOUS_SHA,
        "attempted_image_tag": "ghcr.io/tinyassets/tinyassets:prior",
        "attempted_image_ref": _PREVIOUS,
        "attempted_image_digest": _PREVIOUS,
        "active_identity_status": "agreed",
        "configured_image_ref": _PREVIOUS,
        "running_image_ref": _PREVIOUS,
        "active_image_ref": _PREVIOUS,
        "active_image_digest": _PREVIOUS,
        "active_git_sha": _PREVIOUS_SHA,
        "active_source_provenance": "digest_revision_label",
        "git_sha": _PREVIOUS_SHA,
        "image_tag": "ghcr.io/tinyassets/tinyassets:prior",
        "image_ref": _PREVIOUS,
        "image_digest": _PREVIOUS,
        "build_run_id": "prior-build",
        "build_run_url": "https://github.com/tinyassets/tinyassets/actions/runs/100",
        "deploy_run_id": "prior-deploy",
        "deploy_run_url": "https://github.com/tinyassets/tinyassets/actions/runs/101",
        "config_hash": f"sha256:{'9' * 64}",
        "config_version": "tinyassets-env-v1",
        "schema_migration_rev": "not_applicable",
        "canary_bundle_status": "passed",
        "deployed_at": _PRIOR_DEPLOYED_AT,
        "rollback_target": _ANCESTOR,
        "rollback_attempted": False,
        "rollback_result": "not_attempted",
        "rollback_canary_status": "not_run",
        "rollback_reason": "not_needed",
        "terminal_at": _PRIOR_DEPLOYED_AT,
        "actor": "prior-actor",
        "repository": "tinyassets/tinyassets",
        "workflow_event": "workflow_run",
    }
    value.update(overrides)
    return value


def _failed_before_image_mutation(**overrides: Any) -> dict[str, Any]:
    value = _observations(
        image_mutation_started=False,
        forward_deploy_status="failed",
        forward_canary_status="not_run",
        rollback_reason="image_mutation_not_started",
        configured_image_ref=_PREVIOUS,
        running_image_ref=_PREVIOUS,
    )
    value.update(overrides)
    return value


def _failed_rollback(**overrides: Any) -> dict[str, Any]:
    value = _observations(
        forward_deploy_status="failed",
        forward_canary_status="failed",
        rollback_attempted=True,
        rollback_result="failed",
        rollback_canary_status="not_run",
        rollback_reason="attempted",
    )
    value.update(overrides)
    return value


def _expected_legacy(**overrides: str) -> dict[str, str]:
    value = {
        "git_sha": "",
        "image_tag": "",
        "image_ref": "",
        "image_digest": "",
        "build_run_id": "",
        "build_run_url": "",
        "deploy_run_id": "222",
        "deploy_run_url": "https://github.com/tinyassets/tinyassets/actions/runs/222",
        "config_hash": _CONFIG_HASH,
        "config_version": "tinyassets-env-v1",
        "schema_migration_rev": "not_applicable",
        "canary_bundle_status": "not_run",
        "deployed_at": "",
        "rollback_target": "",
        "actor": "deploy-bot",
        "repository": "tinyassets/tinyassets",
        "workflow_event": "workflow_run",
    }
    value.update(overrides)
    return value


# ---------------------------------------------------------------------------
# Mutation boundaries, outcomes, and rollback exit policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("production_started", "expected"),
    [
        pytest.param(False, "not_applicable", id="pre-host-write"),
        pytest.param(True, "failed", id="writer-default-is-visible-before-work"),
    ],
)
def test_initial_terminal_receipt_result_is_safe_before_fallible_work(
    production_started: bool, expected: str
) -> None:
    assert initial_terminal_receipt_result(production_started) == expected


def test_production_mutation_before_image_mutation_publishes_failed_terminal_truth() -> None:
    receipt = build_terminal_receipt(_failed_before_image_mutation())

    assert receipt["outcome"] == "failed_without_rollback"
    assert receipt["production_mutation_started"] is True
    assert receipt["image_mutation_started"] is False
    assert receipt["rollback_attempted"] is False
    assert receipt["rollback_result"] == "not_attempted"
    assert receipt["rollback_canary_status"] == "not_run"
    assert receipt["rollback_reason"] == "image_mutation_not_started"


@pytest.mark.parametrize(
    ("name", "observations", "expected_outcome", "expected_canary"),
    [
        (
            "forward success",
            _observations(),
            "deployed",
            "passed",
        ),
        (
            "rollback success",
            _observations(
                forward_deploy_status="failed",
                forward_canary_status="failed",
                rollback_attempted=True,
                rollback_result="succeeded",
                rollback_canary_status="passed",
                rollback_reason="attempted",
                configured_image_ref=_PREVIOUS,
                running_image_ref=_PREVIOUS,
            ),
            "rolled_back",
            "passed",
        ),
        (
            "rollback command failure",
            _failed_rollback(),
            "rollback_failed",
            "not_run",
        ),
        (
            "rollback canary failure",
            _failed_rollback(rollback_canary_status="failed"),
            "rollback_failed",
            "failed",
        ),
        (
            "rollback identity failure after green canary",
            _failed_rollback(
                rollback_result="succeeded",
                rollback_canary_status="passed",
                configured_image_ref=_PREVIOUS,
                running_image_ref=_OTHER,
            ),
            "rollback_failed",
            "passed",
        ),
        (
            "no rollback target",
            _observations(
                forward_deploy_status="failed",
                forward_canary_status="failed",
                rollback_reason="no_valid_target",
                previous_configured_image_ref="",
                previous_running_image_ref="",
            ),
            "failed_without_rollback",
            "failed",
        ),
    ],
)
def test_terminal_outcome_matrix(
    name: str,
    observations: dict[str, Any],
    expected_outcome: str,
    expected_canary: str,
) -> None:
    del name
    receipt = build_terminal_receipt(observations)

    assert receipt["outcome"] == expected_outcome
    assert receipt["canary_bundle_status"] == expected_canary


@pytest.mark.parametrize(
    ("name", "observations", "expected_exit"),
    [
        (
            "pre-host write",
            _observations(
                production_mutation_started=False,
                image_mutation_started=False,
                forward_deploy_status="failed",
                forward_canary_status="not_run",
                rollback_reason="pre_host_write_failure",
            ),
            0,
        ),
        (
            "production mutation before image mutation",
            _failed_before_image_mutation(),
            0,
        ),
        (
            "fully green forward path",
            _observations(),
            0,
        ),
        (
            "required rollback has no target",
            _observations(
                forward_deploy_status="failed",
                forward_canary_status="failed",
                rollback_reason="no_valid_target",
                previous_configured_image_ref="",
                previous_running_image_ref="",
            ),
            1,
        ),
        (
            "rollback proven",
            _observations(
                forward_deploy_status="failed",
                forward_canary_status="failed",
                rollback_attempted=True,
                rollback_result="succeeded",
                rollback_canary_status="passed",
                rollback_reason="attempted",
                configured_image_ref=_PREVIOUS,
                running_image_ref=_PREVIOUS,
            ),
            0,
        ),
        (
            "rollback command failed",
            _failed_rollback(),
            1,
        ),
        (
            "rollback canary failed",
            _failed_rollback(rollback_canary_status="failed"),
            1,
        ),
        (
            "rollback canary passed but identity mismatched",
            _failed_rollback(
                rollback_result="succeeded",
                rollback_canary_status="passed",
                configured_image_ref=_PREVIOUS,
                running_image_ref=_OTHER,
            ),
            1,
        ),
        (
            "missing output",
            {
                key: value
                for key, value in _observations().items()
                if key != "rollback_reason"
            },
            1,
        ),
        (
            "contradictory markers",
            _observations(
                production_mutation_started=False,
                image_mutation_started=True,
                forward_deploy_status="failed",
                rollback_attempted=True,
                rollback_result="succeeded",
                rollback_canary_status="passed",
                rollback_reason="attempted",
            ),
            1,
        ),
    ],
)
def test_rollback_step_exact_exit_matrix(
    name: str, observations: dict[str, Any], expected_exit: int
) -> None:
    del name
    assert rollback_step_exit_code(observations) == expected_exit


# ---------------------------------------------------------------------------
# Issue wording is conservative and complete
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {
                "terminal_outcome": "deployed",
                "terminal_active_identity_status": "agreed",
                "terminal_canary_status": "passed",
            },
            "Rollback was not needed because terminal outcome is deployed, "
            "active image identity agrees, and the applicable canary passed.",
        ),
        (
            {
                "terminal_outcome": "rollback_failed",
                "terminal_active_identity_status": "agreed",
                "terminal_canary_status": "passed",
            },
            "Rollback was not attempted; forward production health is unproven.",
        ),
        (
            {
                "terminal_outcome": "deployed",
                "terminal_active_identity_status": "mismatch",
                "terminal_canary_status": "passed",
            },
            "Rollback was not attempted; forward production health is unproven.",
        ),
        (
            {
                "terminal_outcome": "deployed",
                "terminal_active_identity_status": "agreed",
                "terminal_canary_status": "failed",
            },
            "Rollback was not attempted; forward production health is unproven.",
        ),
        (
            {
                "terminal_outcome": "",
                "terminal_active_identity_status": "",
                "terminal_canary_status": "",
            },
            "Rollback was not attempted; forward production health is unproven.",
        ),
    ],
)
def test_not_needed_issue_wording_requires_complete_terminal_health_tuple(
    overrides: dict[str, str], expected: str
) -> None:
    outputs = {
        "production_mutation_started": True,
        "image_mutation_started": True,
        "rollback_attempted": False,
        "rollback_result": "not_attempted",
        "rollback_canary_status": "not_run",
        "rollback_reason": "not_needed",
        **overrides,
    }
    assert rollback_issue_sentence(outputs) == expected


@pytest.mark.parametrize(
    ("outputs", "expected"),
    [
        (
            {
                "production_mutation_started": False,
                "image_mutation_started": False,
                "rollback_attempted": False,
                "rollback_result": "not_attempted",
                "rollback_canary_status": "not_run",
                "rollback_reason": "pre_host_write_failure",
            },
            "Production host write did not start; image rollback was not attempted.",
        ),
        (
            {
                "production_mutation_started": True,
                "image_mutation_started": False,
                "rollback_attempted": False,
                "rollback_result": "not_attempted",
                "rollback_canary_status": "not_run",
                "rollback_reason": "image_mutation_not_started",
            },
            "Production mutation started, but image mutation did not; "
            "image rollback was not required.",
        ),
        (
            {
                "production_mutation_started": True,
                "image_mutation_started": True,
                "rollback_attempted": False,
                "rollback_result": "not_attempted",
                "rollback_canary_status": "not_run",
                "rollback_reason": "no_valid_target",
            },
            "Rollback was not attempted because no validated immutable previous "
            "image was available.",
        ),
        (
            {
                "production_mutation_started": True,
                "image_mutation_started": True,
                "rollback_attempted": True,
                "rollback_result": "succeeded",
                "rollback_canary_status": "passed",
                "rollback_reason": "attempted",
                "terminal_outcome": "rolled_back",
                "terminal_active_identity_status": "agreed",
                "terminal_active_image_ref": _PREVIOUS,
                "previous_image_ref": _PREVIOUS,
            },
            "Rollback succeeded and the rollback canary passed.",
        ),
        (
            {
                "production_mutation_started": True,
                "image_mutation_started": True,
                "rollback_attempted": True,
                "rollback_result": "failed",
                "rollback_canary_status": "failed",
                "rollback_reason": "attempted",
            },
            "Rollback failed; the rollback canary failed.",
        ),
        (
            {
                "production_mutation_started": True,
                "image_mutation_started": True,
                "rollback_attempted": True,
                "rollback_result": "failed",
                "rollback_canary_status": "not_run",
                "rollback_reason": "attempted",
            },
            "Rollback failed before the rollback canary ran.",
        ),
        (
            {
                "production_mutation_started": True,
                "image_mutation_started": True,
                "rollback_attempted": True,
                "rollback_result": "succeeded",
                "rollback_canary_status": "passed",
                "rollback_reason": "attempted",
                "terminal_outcome": "rollback_failed",
                "terminal_active_identity_status": "mismatch",
                "terminal_active_image_ref": "",
                "previous_image_ref": _PREVIOUS,
            },
            "Rollback was not proven: the canary passed but configured and running "
            "image identity did not agree with the rollback target.",
        ),
        (
            {
                "production_mutation_started": True,
                "image_mutation_started": True,
                "rollback_attempted": "maybe",
                "rollback_result": "",
                "rollback_canary_status": "",
                "rollback_reason": "",
            },
            "Rollback status is unavailable; rollback success was not proven.",
        ),
    ],
)
def test_complete_rollback_issue_wording_matrix(
    outputs: dict[str, Any], expected: str
) -> None:
    assert rollback_issue_sentence(outputs) == expected


@pytest.mark.parametrize(
    ("result", "production_started", "expected"),
    [
        ("published", True, "Terminal release-state receipt published."),
        (
            "failed",
            True,
            "Terminal release-state publication failed; durable active-release truth "
            "is not proven and the prior receipt may be stale.",
        ),
        (
            "not_applicable",
            False,
            "Terminal release-state publication was not applicable; the prior receipt "
            "was left unchanged.",
        ),
        (
            "not_applicable",
            True,
            "Terminal release-state status is unavailable or inconsistent; durable "
            "active-release truth is not proven.",
        ),
        (
            "",
            True,
            "Terminal release-state status is unavailable or inconsistent; durable "
            "active-release truth is not proven.",
        ),
    ],
)
def test_terminal_receipt_issue_sentence_matrix(
    result: str, production_started: bool, expected: str
) -> None:
    assert terminal_receipt_issue_sentence(result, production_started) == expected


# ---------------------------------------------------------------------------
# Provenance and prior-receipt trust separation
# ---------------------------------------------------------------------------


def test_manual_old_tag_never_inherits_github_sha_or_build_provenance() -> None:
    observations = _observations(
        workflow_event="workflow_dispatch",
        workflow_head_sha="",
        github_sha="f" * 40,
        attempted_image_tag="ghcr.io/tinyassets/tinyassets:arbitrary-old-tag",
        attempted_revision_label="",
    )

    receipt = build_terminal_receipt(observations)

    assert receipt["attempted_git_sha"] == ""
    assert receipt["attempted_source_provenance"] == "unknown"
    assert receipt["active_git_sha"] == ""
    assert receipt["active_source_provenance"] == "unknown"
    assert receipt["git_sha"] == ""
    assert receipt["build_run_id"] == ""
    assert receipt["build_run_url"] == ""


@pytest.mark.parametrize("workflow_event", ["workflow_run", "workflow_dispatch"])
def test_fresh_digest_bound_revision_is_the_only_current_source_provenance(
    workflow_event: str,
) -> None:
    observations = _observations(workflow_event=workflow_event)
    if workflow_event == "workflow_dispatch":
        observations["workflow_head_sha"] = ""

    receipt = build_terminal_receipt(observations)

    assert receipt["attempted_git_sha"] == _ATTEMPTED_SHA
    assert receipt["attempted_source_provenance"] == "digest_revision_label"
    assert receipt["active_git_sha"] == _ATTEMPTED_SHA
    assert receipt["active_source_provenance"] == "attempted_digest"
    expected_build_run = "111" if workflow_event == "workflow_run" else ""
    assert receipt["build_run_id"] == expected_build_run


def test_workflow_run_build_provenance_requires_revision_head_sha_agreement() -> None:
    receipt = build_terminal_receipt(
        _observations(workflow_head_sha="3" * 40, github_sha=_ATTEMPTED_SHA)
    )

    assert receipt["attempted_git_sha"] == ""
    assert receipt["attempted_source_provenance"] == "unknown"
    assert receipt["build_run_id"] == ""
    assert receipt["build_run_url"] == ""


def test_v1_prior_receipt_matches_identity_but_inherits_no_provenance_or_ancestry() -> None:
    receipt = build_terminal_receipt(
        _failed_before_image_mutation(prior_receipt_b64=_b64_json(_v1_prior()))
    )

    assert receipt["prior_receipt_match_status"] == "v1_identity_match"
    assert receipt["active_image_ref"] == _PREVIOUS
    assert receipt["active_image_digest"] == _PREVIOUS
    assert receipt["active_source_provenance"] == "unknown"
    assert receipt["active_git_sha"] == ""
    assert receipt["git_sha"] == ""
    assert receipt["image_tag"] == ""
    assert receipt["build_run_id"] == ""
    assert receipt["build_run_url"] == ""
    assert receipt["deployed_at"] == ""
    assert receipt["rollback_target"] == ""
    assert receipt["deploy_run_id"] == "222"
    assert receipt["deploy_run_url"].endswith("/222")


def test_v1_source_is_derived_afresh_from_matching_digest_revision() -> None:
    receipt = build_terminal_receipt(
        _failed_before_image_mutation(
            prior_receipt_b64=_b64_json(_v1_prior()),
            active_revision_label=_PREVIOUS_SHA,
        )
    )

    assert receipt["prior_receipt_match_status"] == "v1_identity_match"
    assert receipt["active_git_sha"] == _PREVIOUS_SHA
    assert receipt["git_sha"] == _PREVIOUS_SHA
    assert receipt["active_source_provenance"] == "digest_revision_label"
    assert receipt["image_tag"] == ""
    assert receipt["build_run_id"] == ""
    assert receipt["deployed_at"] == ""
    assert receipt["rollback_target"] == ""


def test_matching_v2_terminal_proof_may_seed_validated_provenance_and_ancestry() -> None:
    receipt = build_terminal_receipt(
        _failed_before_image_mutation(
            prior_receipt_b64=_b64_json(_v2_terminal_proof())
        )
    )

    assert receipt["prior_receipt_match_status"] == "v2_terminal_proof_match"
    assert receipt["active_source_provenance"] == "v2_terminal_proof"
    assert receipt["active_git_sha"] == _PREVIOUS_SHA
    assert receipt["git_sha"] == _PREVIOUS_SHA
    assert receipt["image_tag"] == "ghcr.io/tinyassets/tinyassets:prior"
    assert receipt["build_run_id"] == "prior-build"
    assert receipt["build_run_url"].endswith("/100")
    assert receipt["deployed_at"] == _PRIOR_DEPLOYED_AT
    assert receipt["rollback_target"] == _ANCESTOR


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("release_state_version", 3),
        ("outcome", "rollback_failed"),
        ("active_identity_status", "mismatch"),
        ("configured_image_ref", _OTHER),
        ("running_image_ref", _OTHER),
        ("active_image_ref", _OTHER),
        ("active_image_digest", _OTHER),
        ("image_ref", _OTHER),
        ("image_digest", _OTHER),
        ("canary_bundle_status", "failed"),
    ],
)
def test_v2_receipt_must_satisfy_every_terminal_proof_invariant(
    field: str, bad_value: Any
) -> None:
    prior = _v2_terminal_proof()
    prior[field] = bad_value

    receipt = build_terminal_receipt(
        _failed_before_image_mutation(prior_receipt_b64=_b64_json(prior))
    )

    assert receipt["prior_receipt_match_status"] == "invalid"
    assert receipt["active_source_provenance"] != "v2_terminal_proof"
    assert receipt["git_sha"] == ""
    assert receipt["build_run_id"] == ""
    assert receipt["deployed_at"] == ""
    assert receipt["rollback_target"] == ""


def test_internally_valid_v2_receipt_for_another_active_image_is_mismatch() -> None:
    prior = _v2_terminal_proof(
        configured_image_ref=_OTHER,
        running_image_ref=_OTHER,
        active_image_ref=_OTHER,
        active_image_digest=_OTHER,
        image_ref=_OTHER,
        image_digest=_OTHER,
    )

    receipt = build_terminal_receipt(
        _failed_before_image_mutation(prior_receipt_b64=_b64_json(prior))
    )

    assert receipt["prior_receipt_match_status"] == "mismatch"
    assert receipt["active_source_provenance"] != "v2_terminal_proof"
    assert receipt["rollback_target"] == ""


# ---------------------------------------------------------------------------
# Strict prior-receipt transport and exact decoded-size bound
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prior_receipt_b64",
    [
        pytest.param("!!!!", id="invalid-alphabet"),
        pytest.param("e30=\n", id="otherwise-valid-base64-with-whitespace"),
        pytest.param(base64.b64encode(b"{not-json").decode(), id="malformed-json"),
        pytest.param(base64.b64encode(b"[]").decode(), id="json-not-object"),
        pytest.param(base64.b64encode(b"\xff").decode(), id="invalid-utf8"),
    ],
)
def test_invalid_prior_receipt_transport_is_untrusted_but_outcome_is_reportable(
    prior_receipt_b64: str,
) -> None:
    receipt = build_terminal_receipt(
        _failed_before_image_mutation(prior_receipt_b64=prior_receipt_b64)
    )

    assert receipt["outcome"] == "failed_without_rollback"
    assert receipt["prior_receipt_match_status"] == "invalid"
    assert receipt["git_sha"] == ""
    assert receipt["rollback_target"] == ""


@pytest.mark.parametrize(
    ("decoded_size", "expected_match"),
    [
        pytest.param(65_536, "v1_identity_match", id="exact-limit-is-accepted"),
        pytest.param(65_537, "invalid", id="one-byte-over-limit-is-rejected"),
    ],
)
def test_prior_receipt_decoded_size_bound_is_exact(
    decoded_size: int, expected_match: str
) -> None:
    payload = json.dumps(
        _v1_prior(), sort_keys=True, separators=(",", ":")
    ).encode()
    assert len(payload) < decoded_size
    padded_payload = payload + (b" " * (decoded_size - len(payload)))
    assert len(padded_payload) == decoded_size

    receipt = build_terminal_receipt(
        _failed_before_image_mutation(
            prior_receipt_b64=base64.b64encode(padded_payload).decode("ascii")
        )
    )

    assert receipt["prior_receipt_match_status"] == expected_match


# ---------------------------------------------------------------------------
# Dual-observation identity, exact enums, and legacy projection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("configured", "running", "expected_status", "expected_active"),
    [
        (_ATTEMPTED, _ATTEMPTED, "agreed", _ATTEMPTED),
        (_ATTEMPTED, _PREVIOUS, "mismatch", ""),
        ("", _ATTEMPTED, "configured_unknown", ""),
        ("mutable:tag", _ATTEMPTED, "configured_unknown", ""),
        (_ATTEMPTED, "", "running_unknown", ""),
        (_ATTEMPTED, "sha256:abc", "running_unknown", ""),
        ("", "", "both_unknown", ""),
    ],
)
def test_terminal_identity_requires_configured_and_running_canonical_agreement(
    configured: str,
    running: str,
    expected_status: str,
    expected_active: str,
) -> None:
    receipt = build_terminal_receipt(
        _observations(
            configured_image_ref=configured,
            running_image_ref=running,
        )
    )

    assert receipt["configured_image_ref"] == configured
    assert receipt["running_image_ref"] == running
    assert receipt["active_identity_status"] == expected_status
    assert receipt["active_image_ref"] == expected_active
    assert receipt["active_image_digest"] == expected_active
    assert receipt["image_ref"] == expected_active
    assert receipt["image_digest"] == expected_active
    if expected_status != "agreed":
        assert receipt["outcome"] != "deployed"
        assert receipt["git_sha"] == ""
        assert receipt["image_tag"] == ""
        assert receipt["canary_bundle_status"] != "passed"


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("production_mutation_started", 1),
        ("image_mutation_started", "true"),
        ("forward_deploy_status", "green"),
        ("forward_canary_status", "skipped"),
        ("rollback_attempted", "false"),
        ("rollback_result", "skipped"),
        ("rollback_canary_status", "skipped"),
        ("rollback_reason", "unknown"),
    ],
)
def test_input_markers_and_enums_are_exact(field: str, invalid_value: Any) -> None:
    observations = _observations()
    observations[field] = invalid_value

    with pytest.raises(ValueError, match=field):
        build_terminal_receipt(observations)


@pytest.mark.parametrize(
    "observations",
    [
        _observations(),
        _failed_before_image_mutation(),
        _failed_rollback(),
        _failed_rollback(rollback_canary_status="failed"),
        _failed_rollback(
            rollback_result="succeeded",
            rollback_canary_status="passed",
            configured_image_ref=_PREVIOUS,
            running_image_ref=_PREVIOUS,
        ),
    ],
)
def test_every_emitted_classification_uses_an_exact_bounded_enum(
    observations: dict[str, Any],
) -> None:
    receipt = build_terminal_receipt(observations)

    for field, allowed in _ENUMS.items():
        assert receipt[field] in allowed, f"{field} must be one of {sorted(allowed)}"
    assert type(receipt["production_mutation_started"]) is bool
    assert type(receipt["image_mutation_started"]) is bool
    assert type(receipt["rollback_attempted"]) is bool


def test_success_receipt_contains_every_legacy_field_with_exact_projection() -> None:
    receipt = build_terminal_receipt(_observations())

    assert _LEGACY_KEYS <= receipt.keys()
    assert {key: receipt[key] for key in _LEGACY_KEYS} == {
        "git_sha": _ATTEMPTED_SHA,
        "image_tag": "ghcr.io/tinyassets/tinyassets:build-111",
        "image_ref": _ATTEMPTED,
        "image_digest": _ATTEMPTED,
        "build_run_id": "111",
        "build_run_url": "https://github.com/tinyassets/tinyassets/actions/runs/111",
        "deploy_run_id": "222",
        "deploy_run_url": "https://github.com/tinyassets/tinyassets/actions/runs/222",
        "config_hash": _CONFIG_HASH,
        "config_version": "tinyassets-env-v1",
        "schema_migration_rev": "not_applicable",
        "canary_bundle_status": "passed",
        "deployed_at": _TERMINAL_AT,
        "rollback_target": _PREVIOUS,
        "actor": "deploy-bot",
        "repository": "tinyassets/tinyassets",
        "workflow_event": "workflow_run",
    }


@pytest.mark.parametrize(
    ("name", "observations", "expected"),
    [
        (
            "rolled back with trusted prior provenance",
            _observations(
                forward_deploy_status="failed",
                forward_canary_status="failed",
                rollback_attempted=True,
                rollback_result="succeeded",
                rollback_canary_status="passed",
                rollback_reason="attempted",
                configured_image_ref=_PREVIOUS,
                running_image_ref=_PREVIOUS,
                prior_receipt_b64=_b64_json(_v2_terminal_proof()),
            ),
            _expected_legacy(
                git_sha=_PREVIOUS_SHA,
                image_tag="ghcr.io/tinyassets/tinyassets:prior",
                image_ref=_PREVIOUS,
                image_digest=_PREVIOUS,
                build_run_id="prior-build",
                build_run_url=(
                    "https://github.com/tinyassets/tinyassets/actions/runs/100"
                ),
                canary_bundle_status="passed",
                deployed_at=_TERMINAL_AT,
                rollback_target=_ANCESTOR,
            ),
        ),
        (
            "rollback failed with attempted image still active",
            _failed_rollback(
                configured_image_ref=_ATTEMPTED,
                running_image_ref=_ATTEMPTED,
            ),
            _expected_legacy(
                git_sha=_ATTEMPTED_SHA,
                image_tag="ghcr.io/tinyassets/tinyassets:build-111",
                image_ref=_ATTEMPTED,
                image_digest=_ATTEMPTED,
                build_run_id="111",
                build_run_url=(
                    "https://github.com/tinyassets/tinyassets/actions/runs/111"
                ),
                rollback_target=_PREVIOUS,
            ),
        ),
        (
            "failed without rollback with trusted prior image still active",
            _failed_before_image_mutation(
                configured_image_ref=_PREVIOUS,
                running_image_ref=_PREVIOUS,
                prior_receipt_b64=_b64_json(_v2_terminal_proof()),
            ),
            _expected_legacy(
                git_sha=_PREVIOUS_SHA,
                image_tag="ghcr.io/tinyassets/tinyassets:prior",
                image_ref=_PREVIOUS,
                image_digest=_PREVIOUS,
                build_run_id="prior-build",
                build_run_url=(
                    "https://github.com/tinyassets/tinyassets/actions/runs/100"
                ),
                deployed_at=_PRIOR_DEPLOYED_AT,
                rollback_target=_ANCESTOR,
            ),
        ),
    ],
)
def test_every_terminal_outcome_has_an_exact_complete_legacy_projection(
    name: str, observations: dict[str, Any], expected: dict[str, str]
) -> None:
    del name
    receipt = build_terminal_receipt(observations)

    assert _LEGACY_KEYS <= receipt.keys()
    assert {key: receipt[key] for key in _LEGACY_KEYS} == expected


def test_unknown_active_identity_keeps_all_unproven_legacy_values_empty() -> None:
    receipt = build_terminal_receipt(
        _observations(configured_image_ref=_ATTEMPTED, running_image_ref="")
    )

    assert receipt["git_sha"] == ""
    assert receipt["image_tag"] == ""
    assert receipt["image_ref"] == ""
    assert receipt["image_digest"] == ""
    assert receipt["build_run_id"] == ""
    assert receipt["build_run_url"] == ""
    assert receipt["deployed_at"] == ""
    assert receipt["rollback_target"] == ""
    assert receipt["config_hash"] == _CONFIG_HASH
    assert receipt["config_version"] == "tinyassets-env-v1"
    assert receipt["deploy_run_id"] == "222"
    assert receipt["schema_migration_rev"] == "not_applicable"


# ---------------------------------------------------------------------------
# Complete safe rollback_target matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "observations", "expected_outcome", "expected_target"),
    [
        (
            "deployed on attempted ref",
            _observations(),
            "deployed",
            _PREVIOUS,
        ),
        (
            "deployed without agreed previous ref",
            _observations(previous_running_image_ref=_OTHER),
            "deployed",
            "",
        ),
        (
            "rolled back to previous with v2 ancestry",
            _observations(
                forward_deploy_status="failed",
                forward_canary_status="failed",
                rollback_attempted=True,
                rollback_result="succeeded",
                rollback_canary_status="passed",
                rollback_reason="attempted",
                configured_image_ref=_PREVIOUS,
                running_image_ref=_PREVIOUS,
                prior_receipt_b64=_b64_json(_v2_terminal_proof()),
            ),
            "rolled_back",
            _ANCESTOR,
        ),
        (
            "rolled back to previous without v2 ancestry",
            _observations(
                forward_deploy_status="failed",
                forward_canary_status="failed",
                rollback_attempted=True,
                rollback_result="succeeded",
                rollback_canary_status="passed",
                rollback_reason="attempted",
                configured_image_ref=_PREVIOUS,
                running_image_ref=_PREVIOUS,
            ),
            "rolled_back",
            "",
        ),
        (
            "rollback failed while attempted ref is active",
            _failed_rollback(
                configured_image_ref=_ATTEMPTED,
                running_image_ref=_ATTEMPTED,
            ),
            "rollback_failed",
            _PREVIOUS,
        ),
        (
            "rollback failed while previous ref is active",
            _failed_rollback(
                configured_image_ref=_PREVIOUS,
                running_image_ref=_PREVIOUS,
                prior_receipt_b64=_b64_json(_v2_terminal_proof()),
            ),
            "rollback_failed",
            _ANCESTOR,
        ),
        (
            "rollback failed while another ref is active",
            _failed_rollback(
                configured_image_ref=_OTHER,
                running_image_ref=_OTHER,
                prior_receipt_b64=_b64_json(_v2_terminal_proof()),
            ),
            "rollback_failed",
            "",
        ),
        (
            "rollback failed without identity agreement",
            _failed_rollback(
                configured_image_ref=_ATTEMPTED,
                running_image_ref=_PREVIOUS,
                prior_receipt_b64=_b64_json(_v2_terminal_proof()),
            ),
            "rollback_failed",
            "",
        ),
        (
            "failed without rollback while attempted ref is active",
            _failed_before_image_mutation(
                configured_image_ref=_ATTEMPTED,
                running_image_ref=_ATTEMPTED,
            ),
            "failed_without_rollback",
            _PREVIOUS,
        ),
        (
            "failed without rollback while previous ref is active",
            _failed_before_image_mutation(
                configured_image_ref=_PREVIOUS,
                running_image_ref=_PREVIOUS,
                prior_receipt_b64=_b64_json(_v2_terminal_proof()),
            ),
            "failed_without_rollback",
            _ANCESTOR,
        ),
        (
            "failed without rollback while another ref is active",
            _failed_before_image_mutation(
                configured_image_ref=_OTHER,
                running_image_ref=_OTHER,
                prior_receipt_b64=_b64_json(_v2_terminal_proof()),
            ),
            "failed_without_rollback",
            "",
        ),
        (
            "failed without rollback and no identity agreement",
            _failed_before_image_mutation(
                configured_image_ref=_ATTEMPTED,
                running_image_ref=_PREVIOUS,
                prior_receipt_b64=_b64_json(_v2_terminal_proof()),
            ),
            "failed_without_rollback",
            "",
        ),
    ],
)
def test_complete_safe_rollback_target_matrix(
    name: str,
    observations: dict[str, Any],
    expected_outcome: str,
    expected_target: str,
) -> None:
    del name
    receipt = build_terminal_receipt(observations)

    assert receipt["outcome"] == expected_outcome
    assert receipt["rollback_target"] == expected_target
    if expected_outcome != "deployed":
        assert receipt["rollback_target"] != _ATTEMPTED


def test_v2_ancestry_never_reuses_failed_attempted_image() -> None:
    prior = _v2_terminal_proof(rollback_target=_ATTEMPTED)
    receipt = build_terminal_receipt(
        _failed_before_image_mutation(
            prior_receipt_b64=_b64_json(prior),
            configured_image_ref=_PREVIOUS,
            running_image_ref=_PREVIOUS,
        )
    )

    assert receipt["prior_receipt_match_status"] == "v2_terminal_proof_match"
    assert receipt["rollback_target"] == ""


# ---------------------------------------------------------------------------
# Direct executable contract
# ---------------------------------------------------------------------------


def test_cli_is_deterministic_canonical_json_and_matches_the_importable_core() -> None:
    observations = _observations()
    original = copy.deepcopy(observations)
    expected_receipt = build_terminal_receipt(observations)
    expected_stdout = (
        json.dumps(expected_receipt, sort_keys=True, separators=(",", ":")) + "\n"
    )
    stdin = json.dumps(observations, sort_keys=False)

    first = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=_REPO,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )
    second = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=_REPO,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout == expected_stdout
    assert observations == original, "the pure core must not mutate its input"
