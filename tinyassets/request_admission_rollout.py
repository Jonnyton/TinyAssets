"""Fail-closed rollout gate for protocol-v2 operator request admission.

The public admission call site supplies current release and worker evidence.
This module rereads the deployment switch and per-universe SQLite manifest for
every decision; it deliberately keeps no process-local effective-state cache.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tinyassets.storage.request_admissions import RequestAdmissionStore

OPERATOR_REQUEST_WRITES_ENV = "TINYASSETS_OPERATOR_REQUEST_WRITES"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_ACTIVE_STATES = frozenset({"canary", "enabled"})
_ALL_STATES = frozenset(
    {
        "disabled",
        "readers_only",
        "canary",
        "enabled",
        "rollback",
    }
)
_TRANSITIONS = {
    "disabled": "readers_only",
    "readers_only": "canary",
    "canary": "enabled",
    "enabled": "rollback",
}
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_CONFIG_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class RolloutTransitionError(ValueError):
    """The requested manifest write is stale or skips a rollout state."""


@dataclass(frozen=True, slots=True)
class OnlineWorkerEvidence:
    """Release-derived evidence for one currently online worker."""

    build_sha: str
    config_hash: str
    capabilities: frozenset[str]


@dataclass(frozen=True, slots=True)
class AdmissionRolloutDecision:
    """One admission's fail-closed rollout decision."""

    allowed: bool
    reason: str
    rollout_id: str
    state: str


@dataclass(frozen=True, slots=True)
class _Manifest:
    rollout_id: str
    state: str
    required_capability: str
    allowed_reader_shas: tuple[str, ...]
    allowed_server_shas: tuple[str, ...]
    config_hash: str
    activated_at: datetime | None
    expires_at: datetime | None


def publish_rollout_manifest(
    base_path: str | Path,
    *,
    universe_id: str,
    rollout_id: str,
    state: str,
    expected_state: str | None,
    allowed_reader_shas: Sequence[str],
    allowed_server_shas: Sequence[str],
    config_hash: str,
    owner_id: str,
    activated_at: str | None,
    expires_at: str | None,
    evidence: Mapping[str, Any],
    updated_at: str,
    required_capability: str = "operator_request_v1",
) -> None:
    """Atomically create or advance one universe's rollout manifest.

    Initial publication must be ``disabled``. Updates are compare-and-swap
    transitions through the exact declared state chain.
    """

    clean_universe = _required_string(universe_id, "universe_id")
    clean_rollout = _required_string(rollout_id, "rollout_id")
    clean_owner = _required_string(owner_id, "owner_id")
    clean_capability = _required_string(
        required_capability,
        "required_capability",
    )
    if state not in _ALL_STATES:
        raise ValueError("rollout state is invalid")
    if expected_state is not None and expected_state not in _ALL_STATES:
        raise ValueError("expected rollout state is invalid")

    reader_shas = _validated_shas(allowed_reader_shas, "allowed_reader_shas")
    server_shas = _validated_shas(allowed_server_shas, "allowed_server_shas")
    if _CONFIG_HASH_RE.fullmatch(config_hash) is None:
        raise ValueError("config_hash must be a lowercase SHA-256 digest")
    activation = _optional_timestamp(activated_at, "activated_at")
    expiry = _optional_timestamp(expires_at, "expires_at")
    update_time = _required_timestamp(updated_at, "updated_at")
    if state in _ACTIVE_STATES and (activation is None or expiry is None):
        raise ValueError("active rollout states require activation and expiry")
    if activation is not None and expiry is not None and expiry <= activation:
        raise ValueError("expires_at must be later than activated_at")
    if not isinstance(evidence, Mapping):
        raise TypeError("evidence must be a mapping")
    evidence_json = json.dumps(
        dict(evidence),
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    store = RequestAdmissionStore(base_path)
    with store.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            current = conn.execute(
                """
                SELECT rollout_id, state
                FROM request_admission_rollouts
                WHERE universe_id = ?
                """,
                (clean_universe,),
            ).fetchone()
            if current is None:
                if expected_state is not None or state != "disabled":
                    raise RolloutTransitionError("a new rollout must start in disabled state")
                conn.execute(
                    """
                    INSERT INTO request_admission_rollouts (
                        universe_id, rollout_id, state, queue_epoch,
                        required_capability, allowed_reader_shas_json,
                        allowed_server_shas_json, config_hash, owner_id,
                        activated_at, expires_at, evidence_json, updated_at
                    ) VALUES (?, ?, ?, 2, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        clean_universe,
                        clean_rollout,
                        state,
                        clean_capability,
                        _json_array(reader_shas),
                        _json_array(server_shas),
                        config_hash,
                        clean_owner,
                        _timestamp_text(activation),
                        _timestamp_text(expiry),
                        evidence_json,
                        _timestamp_text(update_time),
                    ),
                )
            else:
                if str(current["rollout_id"]) != clean_rollout:
                    raise RolloutTransitionError(
                        "rollout_id cannot change during a universe rollout"
                    )
                current_state = str(current["state"])
                if current_state != expected_state:
                    raise RolloutTransitionError("rollout manifest compare-and-swap state mismatch")
                if _TRANSITIONS.get(current_state) != state:
                    raise RolloutTransitionError(
                        f"rollout cannot transition {current_state} -> {state}"
                    )
                conn.execute(
                    """
                    UPDATE request_admission_rollouts
                    SET state = ?,
                        required_capability = ?,
                        allowed_reader_shas_json = ?,
                        allowed_server_shas_json = ?,
                        config_hash = ?,
                        owner_id = ?,
                        activated_at = ?,
                        expires_at = ?,
                        evidence_json = ?,
                        updated_at = ?
                    WHERE universe_id = ? AND state = ?
                    """,
                    (
                        state,
                        clean_capability,
                        _json_array(reader_shas),
                        _json_array(server_shas),
                        config_hash,
                        clean_owner,
                        _timestamp_text(activation),
                        _timestamp_text(expiry),
                        evidence_json,
                        _timestamp_text(update_time),
                        clean_universe,
                        current_state,
                    ),
                )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def evaluate_operator_admission_rollout(
    base_path: str | Path,
    *,
    universe_id: str,
    reader_sha: str,
    server_sha: str,
    current_config_hash: str,
    online_workers: Sequence[OnlineWorkerEvidence] = (),
    environment: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> AdmissionRolloutDecision:
    """Reread both rollout gates and decide one admission.

    Missing, malformed, stale, expired, or incompatible evidence always
    returns a refusal. An empty online-worker set is valid zero-host state.
    """

    environ = os.environ if environment is None else environment
    raw_switch = environ.get(OPERATOR_REQUEST_WRITES_ENV)
    if type(raw_switch) is not str or raw_switch.strip().lower() not in _TRUE_VALUES:
        return _decision(False, "deployment_kill_switch_off")

    try:
        manifest = _read_manifest(base_path, universe_id)
    except (TypeError, ValueError, json.JSONDecodeError, sqlite3.Error):
        return _decision(False, "rollout_manifest_invalid")
    if manifest is None:
        return _decision(False, "rollout_manifest_missing")

    decision_time = now or datetime.now(timezone.utc)
    if decision_time.tzinfo is None:
        return _manifest_decision(
            manifest,
            False,
            "rollout_evaluation_time_invalid",
        )
    decision_time = decision_time.astimezone(timezone.utc)
    if manifest.state not in _ACTIVE_STATES:
        return _manifest_decision(
            manifest,
            False,
            f"rollout_state_{manifest.state}",
        )
    if manifest.activated_at is None or decision_time < manifest.activated_at:
        return _manifest_decision(
            manifest,
            False,
            "rollout_manifest_not_active",
        )
    if manifest.expires_at is not None and decision_time >= manifest.expires_at:
        return _manifest_decision(
            manifest,
            False,
            "rollout_manifest_expired",
        )
    if (
        type(current_config_hash) is not str
        or _CONFIG_HASH_RE.fullmatch(current_config_hash) is None
        or current_config_hash != manifest.config_hash
    ):
        return _manifest_decision(
            manifest,
            False,
            "deployment_config_mismatch",
        )
    if reader_sha not in manifest.allowed_reader_shas:
        return _manifest_decision(
            manifest,
            False,
            "reader_build_not_allowed",
        )
    if server_sha not in manifest.allowed_server_shas:
        return _manifest_decision(
            manifest,
            False,
            "server_build_not_allowed",
        )
    for worker in online_workers:
        if (
            type(worker) is not OnlineWorkerEvidence
            or type(worker.build_sha) is not str
            or type(worker.config_hash) is not str
            or type(worker.capabilities) is not frozenset
            or any(
                type(capability) is not str or not capability for capability in worker.capabilities
            )
        ):
            return _manifest_decision(
                manifest,
                False,
                "online_worker_evidence_invalid",
            )
        if worker.build_sha not in manifest.allowed_reader_shas:
            return _manifest_decision(
                manifest,
                False,
                "unknown_online_worker",
            )
        if manifest.required_capability not in worker.capabilities:
            return _manifest_decision(
                manifest,
                False,
                "online_worker_missing_capability",
            )
        if worker.config_hash != manifest.config_hash:
            return _manifest_decision(
                manifest,
                False,
                "online_worker_config_mismatch",
            )
    return _manifest_decision(
        manifest,
        True,
        f"rollout_{manifest.state}",
    )


def _read_manifest(
    base_path: str | Path,
    universe_id: str,
) -> _Manifest | None:
    clean_universe = _required_string(universe_id, "universe_id")
    with RequestAdmissionStore(base_path).connection() as conn:
        row = conn.execute(
            """
            SELECT rollout_id, state, queue_epoch, required_capability,
                   allowed_reader_shas_json, allowed_server_shas_json,
                   config_hash, owner_id, activated_at, expires_at,
                   evidence_json, updated_at
            FROM request_admission_rollouts
            WHERE universe_id = ?
            """,
            (clean_universe,),
        ).fetchone()
    if row is None:
        return None
    if int(row["queue_epoch"]) != 2 or str(row["state"]) not in _ALL_STATES:
        raise ValueError("rollout manifest protocol fields are invalid")
    rollout_id = _required_string(str(row["rollout_id"]), "rollout_id")
    capability = _required_string(
        str(row["required_capability"]),
        "required_capability",
    )
    config_hash = str(row["config_hash"])
    if _CONFIG_HASH_RE.fullmatch(config_hash) is None:
        raise ValueError("rollout manifest config hash is invalid")
    _required_string(str(row["owner_id"]), "owner_id")
    evidence = json.loads(str(row["evidence_json"]))
    if type(evidence) is not dict:
        raise ValueError("rollout manifest evidence must be a JSON object")
    _required_timestamp(row["updated_at"], "updated_at")
    manifest = _Manifest(
        rollout_id=rollout_id,
        state=str(row["state"]),
        required_capability=capability,
        allowed_reader_shas=_decoded_shas(str(row["allowed_reader_shas_json"])),
        allowed_server_shas=_decoded_shas(str(row["allowed_server_shas_json"])),
        config_hash=config_hash,
        activated_at=_optional_timestamp(
            row["activated_at"],
            "activated_at",
        ),
        expires_at=_optional_timestamp(row["expires_at"], "expires_at"),
    )
    if manifest.state in _ACTIVE_STATES and (
        manifest.activated_at is None or manifest.expires_at is None
    ):
        raise ValueError("active rollout manifest lacks activation or expiry")
    return manifest


def _validated_shas(values: Sequence[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{field} must be a sequence of build SHAs")
    clean = tuple(values)
    if not clean or any(
        type(value) is not str or _SHA_RE.fullmatch(value) is None for value in clean
    ):
        raise ValueError(f"{field} must contain lowercase 40-character SHAs")
    if tuple(sorted(set(clean))) != clean:
        raise ValueError(f"{field} must be sorted and unique")
    return clean


def _decoded_shas(raw: str) -> tuple[str, ...]:
    values = json.loads(raw)
    if type(values) is not list:
        raise ValueError("rollout SHA allowlist must be a JSON array")
    return _validated_shas(values, "rollout SHA allowlist")


def _required_string(value: object, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value


def _required_timestamp(value: object, field: str) -> datetime:
    timestamp = _optional_timestamp(value, field)
    if timestamp is None:
        raise ValueError(f"{field} is required")
    return timestamp


def _optional_timestamp(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    if type(value) is not str or not value:
        raise ValueError(f"{field} must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _timestamp_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _json_array(values: tuple[str, ...]) -> str:
    return json.dumps(values, separators=(",", ":"))


def _decision(allowed: bool, reason: str) -> AdmissionRolloutDecision:
    return AdmissionRolloutDecision(
        allowed=allowed,
        reason=reason,
        rollout_id="",
        state="",
    )


def _manifest_decision(
    manifest: _Manifest,
    allowed: bool,
    reason: str,
) -> AdmissionRolloutDecision:
    return AdmissionRolloutDecision(
        allowed=allowed,
        reason=reason,
        rollout_id=manifest.rollout_id,
        state=manifest.state,
    )


__all__ = [
    "AdmissionRolloutDecision",
    "OPERATOR_REQUEST_WRITES_ENV",
    "OnlineWorkerEvidence",
    "RolloutTransitionError",
    "evaluate_operator_admission_rollout",
    "publish_rollout_manifest",
]
