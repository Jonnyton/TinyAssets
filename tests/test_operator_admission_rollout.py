from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tinyassets.daemon_server import initialize_author_server
from tinyassets.request_admission_rollout import (
    AdmissionRolloutDecision,
    OnlineWorkerEvidence,
    RolloutTransitionError,
    evaluate_operator_admission_rollout,
    publish_rollout_manifest,
)
from tinyassets.storage import db_path

_READER_SHA = "a" * 40
_SERVER_SHA = "b" * 40
_CONFIG_HASH = "c" * 64
_NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
_WRITES_ON = {"TINYASSETS_OPERATOR_REQUEST_WRITES": "true"}


def _publish(
    base_path: Path,
    *,
    state: str,
    expected_state: str | None,
    universe_id: str = "universe-a",
    activated_at: str | None = None,
    expires_at: str | None = None,
) -> None:
    publish_rollout_manifest(
        base_path,
        universe_id=universe_id,
        rollout_id=f"rollout-{universe_id}",
        state=state,
        expected_state=expected_state,
        allowed_reader_shas=(_READER_SHA,),
        allowed_server_shas=(_SERVER_SHA,),
        config_hash=_CONFIG_HASH,
        owner_id="operator-a",
        activated_at=activated_at,
        expires_at=expires_at,
        evidence={"change": "operator-request-trigger-contract"},
        updated_at=_NOW.isoformat().replace("+00:00", "Z"),
    )


def _advance_to_active(
    base_path: Path,
    *,
    final_state: str = "enabled",
    universe_id: str = "universe-a",
    activated_at: str = "2026-07-25T11:59:00Z",
    expires_at: str | None = "2026-07-25T12:05:00Z",
) -> None:
    _publish(
        base_path,
        state="disabled",
        expected_state=None,
        universe_id=universe_id,
    )
    _publish(
        base_path,
        state="readers_only",
        expected_state="disabled",
        universe_id=universe_id,
    )
    _publish(
        base_path,
        state="canary",
        expected_state="readers_only",
        universe_id=universe_id,
        activated_at=activated_at,
        expires_at=expires_at,
    )
    if final_state == "enabled":
        _publish(
            base_path,
            state="enabled",
            expected_state="canary",
            universe_id=universe_id,
            activated_at=activated_at,
            expires_at=expires_at,
        )


def _evaluate(
    base_path: Path,
    *,
    universe_id: str = "universe-a",
    environment: dict[str, str] | None = None,
    reader_sha: str = _READER_SHA,
    server_sha: str = _SERVER_SHA,
    current_config_hash: str = _CONFIG_HASH,
    online_workers: tuple[OnlineWorkerEvidence, ...] = (),
    now: datetime = _NOW,
) -> AdmissionRolloutDecision:
    return evaluate_operator_admission_rollout(
        base_path,
        universe_id=universe_id,
        reader_sha=reader_sha,
        server_sha=server_sha,
        current_config_hash=current_config_hash,
        online_workers=online_workers,
        environment={} if environment is None else environment,
        now=now,
    )


def test_manifest_allows_only_declared_state_transitions(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    _publish(tmp_path, state="disabled", expected_state=None)

    with pytest.raises(RolloutTransitionError):
        _publish(
            tmp_path,
            state="enabled",
            expected_state="disabled",
            activated_at="2026-07-25T11:59:00Z",
            expires_at="2026-07-25T12:05:00Z",
        )
    with pytest.raises(RolloutTransitionError):
        _publish(tmp_path, state="readers_only", expected_state="canary")

    _publish(tmp_path, state="readers_only", expected_state="disabled")
    _publish(
        tmp_path,
        state="canary",
        expected_state="readers_only",
        activated_at="2026-07-25T11:59:00Z",
        expires_at="2026-07-25T12:05:00Z",
    )
    _publish(
        tmp_path,
        state="enabled",
        expected_state="canary",
        activated_at="2026-07-25T11:59:00Z",
        expires_at="2026-07-25T12:05:00Z",
    )
    _publish(
        tmp_path,
        state="rollback",
        expected_state="enabled",
    )


def test_active_manifest_requires_expiry_and_corruption_fails_closed(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    _publish(tmp_path, state="disabled", expected_state=None)
    _publish(tmp_path, state="readers_only", expected_state="disabled")
    with pytest.raises(
        ValueError,
        match="require activation and expiry",
    ):
        _publish(
            tmp_path,
            state="canary",
            expected_state="readers_only",
            activated_at="2026-07-25T11:59:00Z",
            expires_at=None,
        )

    _publish(
        tmp_path,
        state="canary",
        expected_state="readers_only",
        activated_at="2026-07-25T11:59:00Z",
        expires_at="2026-07-25T12:05:00Z",
    )
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute(
            """
            UPDATE request_admission_rollouts
            SET expires_at = NULL
            WHERE universe_id = 'universe-a'
            """
        )
    assert (
        _evaluate(
            tmp_path,
            environment=_WRITES_ON,
        ).reason
        == "rollout_manifest_invalid"
    )


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {"TINYASSETS_OPERATOR_REQUEST_WRITES": ""},
        {"TINYASSETS_OPERATOR_REQUEST_WRITES": "invalid"},
        {"TINYASSETS_OPERATOR_REQUEST_WRITES": "false"},
    ],
)
def test_kill_switch_absent_invalid_or_false_fails_closed(
    tmp_path: Path,
    environment: dict[str, str],
) -> None:
    initialize_author_server(tmp_path)
    _advance_to_active(tmp_path)

    decision = _evaluate(tmp_path, environment=environment)

    assert decision == AdmissionRolloutDecision(
        allowed=False,
        reason="deployment_kill_switch_off",
        rollout_id="",
        state="",
    )


def test_canary_is_scoped_to_the_manifest_universe(tmp_path: Path) -> None:
    initialize_author_server(tmp_path)
    _advance_to_active(tmp_path, final_state="canary")

    assert _evaluate(tmp_path, environment=_WRITES_ON).allowed is True
    assert _evaluate(
        tmp_path,
        universe_id="universe-b",
        environment=_WRITES_ON,
    ) == AdmissionRolloutDecision(
        allowed=False,
        reason="rollout_manifest_missing",
        rollout_id="",
        state="",
    )


def test_invalid_persisted_manifest_fails_closed(tmp_path: Path) -> None:
    initialize_author_server(tmp_path)
    _advance_to_active(tmp_path)
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute(
            """
            UPDATE request_admission_rollouts
            SET allowed_reader_shas_json = 'not-json'
            WHERE universe_id = 'universe-a'
            """
        )

    assert _evaluate(
        tmp_path,
        environment=_WRITES_ON,
    ) == AdmissionRolloutDecision(
        allowed=False,
        reason="rollout_manifest_invalid",
        rollout_id="",
        state="",
    )


def test_allowed_builds_and_worker_capability_gate_active_rollout(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    _advance_to_active(tmp_path)
    allowed_worker = OnlineWorkerEvidence(
        build_sha=_READER_SHA,
        config_hash=_CONFIG_HASH,
        capabilities=frozenset({"operator_request_v1"}),
    )

    assert (
        _evaluate(
            tmp_path,
            environment=_WRITES_ON,
            online_workers=(allowed_worker,),
        ).allowed
        is True
    )
    assert (
        _evaluate(
            tmp_path,
            environment=_WRITES_ON,
            reader_sha="d" * 40,
        ).reason
        == "reader_build_not_allowed"
    )
    assert (
        _evaluate(
            tmp_path,
            environment=_WRITES_ON,
            server_sha="e" * 40,
        ).reason
        == "server_build_not_allowed"
    )
    assert (
        _evaluate(
            tmp_path,
            environment=_WRITES_ON,
            current_config_hash="f" * 64,
        ).reason
        == "deployment_config_mismatch"
    )
    assert (
        _evaluate(
            tmp_path,
            environment=_WRITES_ON,
            online_workers=(
                OnlineWorkerEvidence(
                    build_sha="f" * 40,
                    config_hash=_CONFIG_HASH,
                    capabilities=frozenset({"operator_request_v1"}),
                ),
            ),
        ).reason
        == "unknown_online_worker"
    )
    assert (
        _evaluate(
            tmp_path,
            environment=_WRITES_ON,
            online_workers=(
                OnlineWorkerEvidence(
                    build_sha=_READER_SHA,
                    config_hash=_CONFIG_HASH,
                    capabilities=frozenset(),
                ),
            ),
        ).reason
        == "online_worker_missing_capability"
    )
    assert (
        _evaluate(
            tmp_path,
            environment=_WRITES_ON,
            online_workers=(
                OnlineWorkerEvidence(
                    build_sha=_READER_SHA,
                    config_hash="d" * 64,
                    capabilities=frozenset({"operator_request_v1"}),
                ),
            ),
        ).reason
        == "online_worker_config_mismatch"
    )
    assert (
        _evaluate(
            tmp_path,
            environment=_WRITES_ON,
            online_workers=(
                OnlineWorkerEvidence(
                    build_sha=_READER_SHA,
                    config_hash=_CONFIG_HASH,
                    capabilities=None,  # type: ignore[arg-type]
                ),
            ),
        ).reason
        == "online_worker_evidence_invalid"
    )


def test_zero_online_workers_do_not_block_zero_host_admission(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    _advance_to_active(tmp_path)

    decision = _evaluate(
        tmp_path,
        environment=_WRITES_ON,
        online_workers=(),
    )

    assert decision.allowed is True
    assert decision.reason == "rollout_enabled"


def test_online_workers_must_be_supplied_at_evaluation_boundary(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    _advance_to_active(tmp_path)

    with pytest.raises(TypeError, match="online_workers"):
        evaluate_operator_admission_rollout(
            tmp_path,
            universe_id="universe-a",
            reader_sha=_READER_SHA,
            server_sha=_SERVER_SHA,
            current_config_hash=_CONFIG_HASH,
            environment=_WRITES_ON,
            now=_NOW,
        )


@pytest.mark.parametrize(
    ("activated_at", "expires_at", "reason"),
    [
        (
            "2026-07-25T11:59:00Z",
            "2026-07-25T12:00:00Z",
            "rollout_manifest_expired",
        ),
        (
            "2026-07-25T12:01:00Z",
            "2026-07-25T12:05:00Z",
            "rollout_manifest_not_active",
        ),
    ],
)
def test_expired_or_not_yet_active_manifest_fails_closed(
    tmp_path: Path,
    activated_at: str,
    expires_at: str,
    reason: str,
) -> None:
    initialize_author_server(tmp_path)
    _advance_to_active(
        tmp_path,
        final_state="canary",
        activated_at=activated_at,
        expires_at=expires_at,
    )

    assert (
        _evaluate(
            tmp_path,
            environment=_WRITES_ON,
            now=datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc),
        ).reason
        == reason
    )


def test_each_admission_rereads_manifest_and_observes_rollback_within_60_seconds(
    tmp_path: Path,
) -> None:
    initialize_author_server(tmp_path)
    _advance_to_active(tmp_path)
    assert _evaluate(tmp_path, environment=_WRITES_ON).allowed is True

    rollback_at = datetime(2026, 7, 25, 12, 0, 59, tzinfo=timezone.utc)
    publish_rollout_manifest(
        tmp_path,
        universe_id="universe-a",
        rollout_id="rollout-universe-a",
        state="rollback",
        expected_state="enabled",
        allowed_reader_shas=(_READER_SHA,),
        allowed_server_shas=(_SERVER_SHA,),
        config_hash=_CONFIG_HASH,
        owner_id="operator-a",
        activated_at=None,
        expires_at=None,
        evidence={"reason": "operator rollback"},
        updated_at=rollback_at.isoformat().replace("+00:00", "Z"),
    )

    decision = _evaluate(
        tmp_path,
        environment=_WRITES_ON,
        now=rollback_at,
    )

    assert decision.allowed is False
    assert decision.reason == "rollout_state_rollback"
