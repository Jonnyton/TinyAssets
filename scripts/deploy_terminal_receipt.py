#!/usr/bin/env python3
"""Build a deterministic terminal production-deploy receipt.

The workflow observes and mutates production.  This module only validates
those explicit observations, classifies the terminal state, and projects the
version-2 receipt.  The importable core performs no I/O.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_REPO_DIGEST_RE = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]+)?"
    r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+"
    r"@sha256:[0-9a-f]{64}$"
)
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_CONFIG_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_UTC_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
_MAX_PRIOR_RECEIPT_BYTES = 65_536

_FORWARD_DEPLOY_STATUSES = frozenset({"succeeded", "failed"})
_CANARY_STATUSES = frozenset({"passed", "failed", "not_run"})
_ROLLBACK_RESULTS = frozenset({"succeeded", "failed", "not_attempted"})
_ROLLBACK_REASONS = frozenset(
    {
        "attempted",
        "not_needed",
        "pre_host_write_failure",
        "image_mutation_not_started",
        "no_valid_target",
    }
)


def _is_repo_digest(value: object) -> bool:
    return isinstance(value, str) and _REPO_DIGEST_RE.fullmatch(value) is not None


def _is_git_sha(value: object) -> bool:
    return isinstance(value, str) and _GIT_SHA_RE.fullmatch(value) is not None


def _is_timestamp(value: object) -> bool:
    return isinstance(value, str) and _UTC_TIMESTAMP_RE.fullmatch(value) is not None


def _string(values: Mapping[str, Any], field: str, *, required: bool = False) -> str:
    value = values.get(field, "")
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    if required and not value:
        raise ValueError(f"{field} must not be empty")
    return value


def _bool(values: Mapping[str, Any], field: str) -> bool:
    value = values.get(field)
    if type(value) is not bool:
        raise ValueError(f"{field} must be a boolean")
    return value


def _enum(values: Mapping[str, Any], field: str, allowed: frozenset[str]) -> str:
    value = values.get(field)
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}")
    return value


def _agreed_ref(configured: object, running: object) -> str:
    if _is_repo_digest(configured) and configured == running:
        return str(configured)
    return ""


def _identity_status(configured: object, running: object) -> tuple[str, str]:
    configured_valid = _is_repo_digest(configured)
    running_valid = _is_repo_digest(running)
    if configured_valid and running_valid:
        if configured == running:
            return "agreed", str(configured)
        return "mismatch", ""
    if configured_valid:
        return "running_unknown", ""
    if running_valid:
        return "configured_unknown", ""
    return "both_unknown", ""


def _decode_prior_receipt(encoded: object) -> tuple[str, dict[str, Any] | None]:
    if encoded == "":
        return "absent", None
    if not isinstance(encoded, str):
        return "invalid", None
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return "invalid", None
    if base64.b64encode(payload).decode("ascii") != encoded:
        return "invalid", None
    if len(payload) > _MAX_PRIOR_RECEIPT_BYTES:
        return "invalid", None
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "invalid", None
    if not isinstance(decoded, dict):
        return "invalid", None
    return "decoded", decoded


def _v1_identity(prior: Mapping[str, Any]) -> str:
    version = prior.get("release_state_version")
    image_ref = prior.get("image_ref")
    image_digest = prior.get("image_digest", "")
    if type(version) is not int or version != 1 or not _is_repo_digest(image_ref):
        return ""
    if image_digest not in ("", image_ref):
        return ""
    if not isinstance(image_digest, str):
        return ""
    return str(image_ref)


def _validated_prior_string(prior: Mapping[str, Any], field: str) -> tuple[bool, str]:
    value = prior.get(field, "")
    return isinstance(value, str), value if isinstance(value, str) else ""


def _v2_terminal_identity(prior: Mapping[str, Any]) -> str:
    if type(prior.get("release_state_version")) is not int:
        return ""
    if prior.get("release_state_version") != 2:
        return ""
    if prior.get("outcome") not in {"deployed", "rolled_back"}:
        return ""
    if prior.get("active_identity_status") != "agreed":
        return ""
    if prior.get("canary_bundle_status") != "passed":
        return ""

    identity_fields = (
        "configured_image_ref",
        "running_image_ref",
        "active_image_ref",
        "active_image_digest",
        "image_ref",
        "image_digest",
    )
    identities = [prior.get(field) for field in identity_fields]
    if not identities or not _is_repo_digest(identities[0]):
        return ""
    if any(identity != identities[0] for identity in identities[1:]):
        return ""
    return str(identities[0])


def _validate_v2_reusable_fields(
    prior: Mapping[str, Any],
) -> tuple[bool, dict[str, str]]:
    reusable: dict[str, str] = {}
    for field in (
        "git_sha",
        "active_git_sha",
        "image_tag",
        "build_run_id",
        "build_run_url",
        "deployed_at",
        "rollback_target",
    ):
        valid_type, value = _validated_prior_string(prior, field)
        if not valid_type:
            return False, {}
        reusable[field] = value

    for field in ("git_sha", "active_git_sha"):
        if reusable[field] and not _is_git_sha(reusable[field]):
            return False, {}
    if (
        reusable["git_sha"]
        and reusable["active_git_sha"]
        and reusable["git_sha"] != reusable["active_git_sha"]
    ):
        return False, {}
    if reusable["deployed_at"] and not _is_timestamp(reusable["deployed_at"]):
        return False, {}
    if reusable["rollback_target"] and not _is_repo_digest(reusable["rollback_target"]):
        return False, {}
    return True, reusable


def _classify_prior_receipt(
    encoded: object, active_ref: str, attempted_ref: str
) -> tuple[str, dict[str, str]]:
    transport_status, prior = _decode_prior_receipt(encoded)
    if transport_status != "decoded":
        return transport_status, {}
    assert prior is not None

    version = prior.get("release_state_version")
    if type(version) is not int:
        return "invalid", {}
    if version == 1:
        identity = _v1_identity(prior)
        if not identity:
            return "invalid", {}
        if not active_ref or identity != active_ref:
            return "mismatch", {}
        return "v1_identity_match", {}
    if version != 2:
        return "invalid", {}

    identity = _v2_terminal_identity(prior)
    reusable_valid, reusable = _validate_v2_reusable_fields(prior)
    if not identity or not reusable_valid:
        return "invalid", {}
    if not active_ref or identity != active_ref:
        return "mismatch", {}
    if reusable["rollback_target"] == attempted_ref:
        reusable["rollback_target"] = ""
    return "v2_terminal_proof_match", reusable


def _validate_rollback_tuple(
    production_started: bool,
    image_started: bool,
    forward_status: str,
    forward_canary: str,
    rollback_attempted: bool,
    rollback_result: str,
    rollback_canary: str,
    rollback_reason: str,
) -> None:
    if image_started and not production_started:
        raise ValueError("image_mutation_started requires production_mutation_started")
    if rollback_attempted:
        if (
            not image_started
            or forward_status != "failed"
            or rollback_reason != "attempted"
            or rollback_result not in {"succeeded", "failed"}
        ):
            raise ValueError("rollback_attempted tuple is contradictory")
        if rollback_result == "succeeded" and rollback_canary != "passed":
            raise ValueError("rollback_result tuple is contradictory")
        if rollback_result == "failed" and rollback_canary == "passed":
            raise ValueError("rollback_result tuple is contradictory")
        return

    if rollback_result != "not_attempted" or rollback_canary != "not_run":
        raise ValueError("rollback_attempted tuple is contradictory")
    valid_reason = (
        (
            rollback_reason == "pre_host_write_failure"
            and not production_started
            and not image_started
        )
        or (
            rollback_reason == "image_mutation_not_started"
            and production_started
            and not image_started
        )
        or (
            rollback_reason == "not_needed"
            and production_started
            and image_started
            and forward_status == "succeeded"
            and forward_canary == "passed"
        )
        or (
            rollback_reason == "no_valid_target"
            and production_started
            and image_started
            and forward_status == "failed"
        )
    )
    if not valid_reason:
        raise ValueError("rollback_reason tuple is contradictory")


def _classify_outcome(
    *,
    production_started: bool,
    image_started: bool,
    forward_status: str,
    forward_canary: str,
    rollback_attempted: bool,
    rollback_result: str,
    rollback_canary: str,
    rollback_reason: str,
    attempted_ref: str,
    previous_ref: str,
    active_ref: str,
) -> str:
    deployed = (
        production_started
        and image_started
        and forward_status == "succeeded"
        and forward_canary == "passed"
        and not rollback_attempted
        and rollback_result == "not_attempted"
        and rollback_canary == "not_run"
        and rollback_reason == "not_needed"
        and active_ref == attempted_ref
    )
    if deployed:
        return "deployed"

    rolled_back = (
        production_started
        and image_started
        and forward_status == "failed"
        and rollback_attempted
        and rollback_result == "succeeded"
        and rollback_canary == "passed"
        and rollback_reason == "attempted"
        and bool(previous_ref)
        and active_ref == previous_ref
    )
    if rolled_back:
        return "rolled_back"
    if image_started and rollback_reason != "no_valid_target":
        return "rollback_failed"
    return "failed_without_rollback"


def _applicable_canary(
    outcome: str,
    active_identity_status: str,
    forward_canary: str,
    rollback_attempted: bool,
    rollback_canary: str,
) -> str:
    if outcome == "deployed":
        status = forward_canary
    elif outcome == "rolled_back" or rollback_attempted:
        status = rollback_canary
    else:
        status = forward_canary
    if active_identity_status != "agreed" and status == "passed":
        return "failed"
    return status


def build_terminal_receipt(observations: Mapping[str, Any]) -> dict[str, Any]:
    """Validate explicit observations and return a version-2 terminal receipt."""

    if not isinstance(observations, Mapping):
        raise ValueError("observations must be an object")

    production_started = _bool(observations, "production_mutation_started")
    image_started = _bool(observations, "image_mutation_started")
    forward_status = _enum(observations, "forward_deploy_status", _FORWARD_DEPLOY_STATUSES)
    forward_canary = _enum(observations, "forward_canary_status", _CANARY_STATUSES)
    rollback_attempted = _bool(observations, "rollback_attempted")
    rollback_result = _enum(observations, "rollback_result", _ROLLBACK_RESULTS)
    rollback_canary = _enum(observations, "rollback_canary_status", _CANARY_STATUSES)
    rollback_reason = _enum(observations, "rollback_reason", _ROLLBACK_REASONS)
    _validate_rollback_tuple(
        production_started,
        image_started,
        forward_status,
        forward_canary,
        rollback_attempted,
        rollback_result,
        rollback_canary,
        rollback_reason,
    )

    attempted_ref = _string(observations, "attempted_image_ref", required=True)
    if not _is_repo_digest(attempted_ref):
        raise ValueError("attempted_image_ref must be a canonical RepoDigest")
    attempted_tag = _string(observations, "attempted_image_tag")
    configured_ref = _string(observations, "configured_image_ref")
    running_ref = _string(observations, "running_image_ref")
    previous_configured_ref = _string(observations, "previous_configured_image_ref")
    previous_running_ref = _string(observations, "previous_running_image_ref")
    previous_ref = _agreed_ref(previous_configured_ref, previous_running_ref)
    active_identity_status, active_ref = _identity_status(configured_ref, running_ref)

    attempted_revision = _string(observations, "attempted_revision_label")
    workflow_event = _string(observations, "workflow_event")
    workflow_head_sha = _string(observations, "workflow_head_sha")
    attempted_git_sha = ""
    if _is_git_sha(attempted_revision):
        if workflow_event != "workflow_run" or attempted_revision == workflow_head_sha:
            attempted_git_sha = attempted_revision
    attempted_source_provenance = "digest_revision_label" if attempted_git_sha else "unknown"

    prior_match_status, prior = _classify_prior_receipt(
        observations.get("prior_receipt_b64", ""), active_ref, attempted_ref
    )
    active_revision = _string(observations, "active_revision_label")
    active_git_sha = ""
    active_source_provenance = "unknown"
    if active_ref:
        if active_ref == attempted_ref and attempted_git_sha:
            active_git_sha = attempted_git_sha
            active_source_provenance = "attempted_digest"
        elif _is_git_sha(active_revision):
            active_git_sha = active_revision
            active_source_provenance = "digest_revision_label"
        elif prior_match_status == "v2_terminal_proof_match":
            active_git_sha = prior["git_sha"] or prior["active_git_sha"]
            if active_git_sha:
                active_source_provenance = "v2_terminal_proof"

    build_run_id = ""
    build_run_url = ""
    image_tag = ""
    if active_ref == attempted_ref:
        image_tag = attempted_tag
        if (
            workflow_event == "workflow_run"
            and attempted_git_sha
            and attempted_git_sha == workflow_head_sha
        ):
            build_run_id = _string(observations, "build_run_id")
            build_run_url = _string(observations, "build_run_url")
    elif prior_match_status == "v2_terminal_proof_match":
        image_tag = prior["image_tag"]
        build_run_id = prior["build_run_id"]
        build_run_url = prior["build_run_url"]

    outcome = _classify_outcome(
        production_started=production_started,
        image_started=image_started,
        forward_status=forward_status,
        forward_canary=forward_canary,
        rollback_attempted=rollback_attempted,
        rollback_result=rollback_result,
        rollback_canary=rollback_canary,
        rollback_reason=rollback_reason,
        attempted_ref=attempted_ref,
        previous_ref=previous_ref,
        active_ref=active_ref,
    )
    canary_bundle_status = _applicable_canary(
        outcome,
        active_identity_status,
        forward_canary,
        rollback_attempted,
        rollback_canary,
    )

    terminal_at = _string(observations, "terminal_at", required=True)
    if not _is_timestamp(terminal_at):
        raise ValueError("terminal_at must be a UTC timestamp")
    if outcome in {"deployed", "rolled_back"}:
        deployed_at = terminal_at
    elif prior_match_status == "v2_terminal_proof_match":
        deployed_at = prior["deployed_at"]
    else:
        deployed_at = ""

    prior_target = (
        prior.get("rollback_target", "") if prior_match_status == "v2_terminal_proof_match" else ""
    )
    rollback_target = ""
    if outcome == "deployed" and active_ref == attempted_ref:
        rollback_target = previous_ref
    elif outcome == "rolled_back" and active_ref == previous_ref:
        rollback_target = prior_target
    elif outcome in {"rollback_failed", "failed_without_rollback"}:
        if active_ref == attempted_ref:
            rollback_target = previous_ref
        elif active_ref == previous_ref:
            rollback_target = prior_target
    if rollback_target == attempted_ref or not _is_repo_digest(rollback_target):
        rollback_target = ""

    config_hash_observed = _string(observations, "config_hash")
    config_hash = (
        config_hash_observed if _CONFIG_HASH_RE.fullmatch(config_hash_observed) is not None else ""
    )
    deploy_run_id = _string(observations, "deploy_run_id")
    deploy_run_url = _string(observations, "deploy_run_url")
    actor = _string(observations, "actor")
    repository = _string(observations, "repository")

    return {
        "release_state_version": 2,
        "outcome": outcome,
        "forward_deploy_status": forward_status,
        "forward_canary_status": forward_canary,
        "production_mutation_started": production_started,
        "image_mutation_started": image_started,
        "prior_receipt_match_status": prior_match_status,
        "attempted_source_provenance": attempted_source_provenance,
        "attempted_git_sha": attempted_git_sha,
        "attempted_image_tag": attempted_tag,
        "attempted_image_ref": attempted_ref,
        "attempted_image_digest": attempted_ref,
        "active_source_provenance": active_source_provenance,
        "active_identity_status": active_identity_status,
        "configured_image_ref": configured_ref,
        "running_image_ref": running_ref,
        "active_git_sha": active_git_sha,
        "active_image_ref": active_ref,
        "active_image_digest": active_ref,
        "rollback_attempted": rollback_attempted,
        "rollback_result": rollback_result,
        "rollback_canary_status": rollback_canary,
        "rollback_reason": rollback_reason,
        "terminal_at": terminal_at,
        "git_sha": active_git_sha,
        "image_tag": image_tag,
        "image_ref": active_ref,
        "image_digest": active_ref,
        "build_run_id": build_run_id,
        "build_run_url": build_run_url,
        "deploy_run_id": deploy_run_id,
        "deploy_run_url": deploy_run_url,
        "config_hash": config_hash,
        "config_version": "tinyassets-env-v1" if config_hash else "",
        "schema_migration_rev": "not_applicable",
        "canary_bundle_status": canary_bundle_status,
        "deployed_at": deployed_at,
        "rollback_target": rollback_target,
        "actor": actor,
        "repository": repository,
        "workflow_event": workflow_event,
    }


def initial_terminal_receipt_result(production_mutation_started: object) -> str:
    """Return the safe writer result emitted before any fallible work."""

    return "failed" if production_mutation_started is True else "not_applicable"


def rollback_step_exit_code(observations: Mapping[str, Any]) -> int:
    """Return zero only for an exact valid rollback terminal tuple."""

    if not isinstance(observations, Mapping):
        return 1
    production_started = observations.get("production_mutation_started")
    image_started = observations.get("image_mutation_started")
    rollback_attempted = observations.get("rollback_attempted")
    rollback_result = observations.get("rollback_result")
    rollback_canary = observations.get("rollback_canary_status")
    rollback_reason = observations.get("rollback_reason")

    if (
        production_started is False
        and image_started is False
        and rollback_attempted is False
        and rollback_result == "not_attempted"
        and rollback_canary == "not_run"
        and rollback_reason == "pre_host_write_failure"
    ):
        return 0
    if (
        production_started is True
        and image_started is False
        and rollback_attempted is False
        and rollback_result == "not_attempted"
        and rollback_canary == "not_run"
        and rollback_reason == "image_mutation_not_started"
    ):
        return 0

    attempted_ref = observations.get("attempted_image_ref")
    configured_ref = observations.get("configured_image_ref")
    running_ref = observations.get("running_image_ref")
    if (
        production_started is True
        and image_started is True
        and observations.get("forward_deploy_status") == "succeeded"
        and observations.get("forward_canary_status") == "passed"
        and rollback_attempted is False
        and rollback_result == "not_attempted"
        and rollback_canary == "not_run"
        and rollback_reason == "not_needed"
        and _is_repo_digest(attempted_ref)
        and configured_ref == running_ref == attempted_ref
    ):
        return 0

    previous_ref = _agreed_ref(
        observations.get("previous_configured_image_ref"),
        observations.get("previous_running_image_ref"),
    )
    if (
        production_started is True
        and image_started is True
        and observations.get("forward_deploy_status") == "failed"
        and rollback_attempted is True
        and rollback_result == "succeeded"
        and rollback_canary == "passed"
        and rollback_reason == "attempted"
        and previous_ref
        and configured_ref == running_ref == previous_ref
    ):
        return 0
    return 1


def rollback_issue_sentence(outputs: Mapping[str, Any]) -> str:
    """Select the conservative rollback sentence from bounded step outputs."""

    production_started = outputs.get("production_mutation_started")
    image_started = outputs.get("image_mutation_started")
    attempted = outputs.get("rollback_attempted")
    result = outputs.get("rollback_result")
    canary = outputs.get("rollback_canary_status")
    reason = outputs.get("rollback_reason")

    if (
        production_started is False
        and image_started is False
        and attempted is False
        and result == "not_attempted"
        and canary == "not_run"
        and reason == "pre_host_write_failure"
    ):
        return "Production host write did not start; image rollback was not attempted."
    if (
        production_started is True
        and image_started is False
        and attempted is False
        and result == "not_attempted"
        and canary == "not_run"
        and reason == "image_mutation_not_started"
    ):
        return (
            "Production mutation started, but image mutation did not; "
            "image rollback was not required."
        )
    if (
        production_started is True
        and image_started is True
        and attempted is False
        and result == "not_attempted"
        and canary == "not_run"
        and reason == "not_needed"
    ):
        if (
            outputs.get("terminal_outcome") == "deployed"
            and outputs.get("terminal_active_identity_status") == "agreed"
            and outputs.get("terminal_canary_status") == "passed"
        ):
            return (
                "Rollback was not needed because terminal outcome is deployed, "
                "active image identity agrees, and the applicable canary passed."
            )
        return "Rollback was not attempted; forward production health is unproven."
    if (
        production_started is True
        and image_started is True
        and attempted is False
        and result == "not_attempted"
        and canary == "not_run"
        and reason == "no_valid_target"
    ):
        return (
            "Rollback was not attempted because no validated immutable previous "
            "image was available."
        )
    if (
        production_started is True
        and image_started is True
        and attempted is True
        and result == "succeeded"
        and canary == "passed"
        and reason == "attempted"
    ):
        proven = (
            outputs.get("terminal_outcome") == "rolled_back"
            and outputs.get("terminal_active_identity_status") == "agreed"
            and _is_repo_digest(outputs.get("previous_image_ref"))
            and outputs.get("terminal_active_image_ref") == outputs.get("previous_image_ref")
        )
        if proven:
            return "Rollback succeeded and the rollback canary passed."
        return (
            "Rollback was not proven: the canary passed but configured and running "
            "image identity did not agree with the rollback target."
        )
    if (
        production_started is True
        and image_started is True
        and attempted is True
        and result == "failed"
        and canary == "failed"
        and reason == "attempted"
    ):
        return "Rollback failed; the rollback canary failed."
    if (
        production_started is True
        and image_started is True
        and attempted is True
        and result == "failed"
        and canary == "not_run"
        and reason == "attempted"
    ):
        return "Rollback failed before the rollback canary ran."
    return "Rollback status is unavailable; rollback success was not proven."


def terminal_receipt_issue_sentence(
    terminal_receipt_result: object, production_mutation_started: object
) -> str:
    """Select the conservative terminal-receipt publication sentence."""

    if terminal_receipt_result == "published":
        return "Terminal release-state receipt published."
    if terminal_receipt_result == "failed":
        return (
            "Terminal release-state publication failed; durable active-release truth "
            "is not proven and the prior receipt may be stale."
        )
    if terminal_receipt_result == "not_applicable" and production_mutation_started is False:
        return (
            "Terminal release-state publication was not applicable; the prior "
            "receipt was left unchanged."
        )
    return (
        "Terminal release-state status is unavailable or inconsistent; durable "
        "active-release truth is not proven."
    )


def _read_cli_input(path: str | None) -> str:
    if path is None:
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic terminal deploy receipt.")
    parser.add_argument(
        "--input",
        metavar="FILE",
        help="read the observation JSON object from FILE instead of stdin",
    )
    args = parser.parse_args(argv)
    try:
        observations = json.loads(_read_cli_input(args.input))
        receipt = build_terminal_receipt(observations)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"deploy_terminal_receipt: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
