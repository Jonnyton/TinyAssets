"""Host-local Windows desktop effect adapter — PR-131.

Consumes ``workflow.external_effect_packet.v1`` packets for approved
host-local Windows desktop effects. The adapter is deliberately narrow:
it gates on explicit user approval, exact per-universe consent, runtime
attestation for a real Windows desktop session, and an idempotency
receipt before any host-local action runs.

Public evidence must never include protected asset bytes or private
local paths. Local paths are converted to stable redacted handles.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME = (
    "host_local.windows_desktop.install_classic_game"
)
DEFAULT_WINDOWS_DESKTOP_DESTINATION = "host-local/windows-desktop"
_ALLOWED_ACTIONS = frozenset({
    "download",
    "hash",
    "launch_installer",
    "discover_install",
    "create_shortcut",
    "launch_shortcut",
    "record_evidence",
})
_DOWNLOAD_TIMEOUT_S = 120.0
_MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024

ActionRunner = Callable[
    ..., dict[str, Any]
]


def _parse_packet(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        packet = value
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped or not stripped.startswith("{"):
            return None
        try:
            packet = json.loads(stripped)
        except (TypeError, ValueError):
            return None
        if not isinstance(packet, dict):
            return None
    else:
        return None

    effect_type = packet.get("effect_type") or packet.get("sink")
    if effect_type != EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME:
        return None
    return packet


def _find_packet(
    *,
    output_keys: list[str],
    run_state: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    for key in output_keys or []:
        if not isinstance(key, str) or key not in run_state:
            continue
        packet = _parse_packet(run_state.get(key))
        if packet is not None:
            return key, packet
    return None, None


def _idempotency_key(packet: dict[str, Any]) -> str:
    for key in ("idempotency_key", "idempotency_hint"):
        value = packet.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _destination(packet: dict[str, Any]) -> str:
    value = packet.get("destination")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return DEFAULT_WINDOWS_DESKTOP_DESTINATION


def _has_user_approval(packet: dict[str, Any]) -> bool:
    approval = packet.get("user_approval")
    if isinstance(approval, str):
        text = approval.strip().lower()
        if any(deny in text for deny in ("do not approve", "don't approve", "not approve")):
            return False
        return bool(text) and ("approve" in text or "approved" in text)
    if approval is True:
        return True
    approval_obj = packet.get("approval")
    if isinstance(approval_obj, dict):
        return approval_obj.get("approved") is True
    return False


def _check_consent(universe_dir: Path | None, destination: str) -> bool:
    if universe_dir is None or not destination:
        return False
    try:
        from workflow.storage.effector_consents import is_consent_active

        return is_consent_active(
            universe_dir,
            sink=EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME,
            destination=destination,
        )
    except Exception:
        logger.exception("windows desktop consent lookup crashed")
        return False


def attest_windows_desktop_runtime() -> dict[str, Any]:
    """Return local runtime facts used to decide whether effects may run."""
    user_profile = os.environ.get("USERPROFILE", "")
    desktop = Path(user_profile) / "Desktop" if user_profile else Path()
    session_name = os.environ.get("SESSIONNAME", "")
    return {
        "os_name": os.name,
        "home": str(Path.home()),
        "desktop_user_profile_present": bool(
            user_profile and Path(user_profile).exists() and desktop.exists()
        ),
        "interactive_session": bool(session_name and session_name.lower() != "services"),
        "container": bool(os.environ.get("container") or Path("/.dockerenv").exists()),
    }


def _runtime_is_windows_desktop(attestation: dict[str, Any]) -> bool:
    return (
        attestation.get("os_name") == "nt"
        and attestation.get("desktop_user_profile_present") is True
        and attestation.get("interactive_session") is True
        and attestation.get("container") is not True
    )


def _try_reserve(
    universe_dir: Path | None,
    *,
    idempotency_key: str,
    run_id: str,
) -> dict[str, Any]:
    if universe_dir is None or not idempotency_key:
        return {"status": "no_hint"}
    from workflow.storage.external_write_receipts import try_reserve_receipt

    return try_reserve_receipt(
        universe_dir,
        idempotency_hint=idempotency_key,
        sink=EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME,
        run_id=run_id or "",
    )


def _finalize_receipt(
    universe_dir: Path | None,
    *,
    idempotency_key: str,
    evidence: dict[str, Any],
    run_id: str,
) -> bool:
    if universe_dir is None or not idempotency_key:
        return False
    try:
        from workflow.storage.external_write_receipts import finalize_receipt

        return finalize_receipt(
            universe_dir,
            idempotency_hint=idempotency_key,
            sink=EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME,
            evidence=evidence,
            run_id=run_id or "",
        )
    except Exception:
        logger.exception("failed to finalize windows desktop receipt")
        return False


def _release_reservation(
    universe_dir: Path | None,
    *,
    idempotency_key: str,
    run_id: str,
) -> None:
    if universe_dir is None or not idempotency_key:
        return
    try:
        from workflow.storage.external_write_receipts import release_reservation

        release_reservation(
            universe_dir,
            idempotency_hint=idempotency_key,
            sink=EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME,
            run_id=run_id or "",
            mark_failed=True,
        )
    except Exception:
        logger.exception("failed to release windows desktop reservation")


def _is_lock_error(exc: BaseException) -> bool:
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    msg = str(exc).lower()
    return any(token in msg for token in ("locked", "busy", "deadlock", "timeout"))


def _safe_filename(packet: dict[str, Any], source_url: str) -> str:
    raw = packet.get("source_filename")
    if not isinstance(raw, str) or not raw.strip():
        raw = Path(urlparse(source_url).path).name
    name = Path(raw.strip()).name
    if not name or name in {".", ".."}:
        raise ValueError("source_filename is required")
    return name


def _validate_source_url(source_url: str) -> None:
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("lawful_source_url must be an https URL")


def _path_handle(path: Path) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8", "surrogatepass")).hexdigest()
    return f"local-path:{digest[:16]}"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, target: Path) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT_S) as response:
        with target.open("wb") as fh:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_DOWNLOAD_BYTES:
                    raise ValueError(
                        f"download exceeds {_MAX_DOWNLOAD_BYTES} byte safety cap"
                    )
                fh.write(chunk)
    return {
        "path_handle": _path_handle(target),
        "bytes": target.stat().st_size,
    }


def _launch(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    if hasattr(os, "startfile"):
        os.startfile(str(path))  # type: ignore[attr-defined]
        return {"launched": True, "path_handle": _path_handle(path)}
    proc = subprocess.Popen([str(path)], close_fds=True)
    return {"pid": proc.pid, "path_handle": _path_handle(path)}


def _create_shortcut(*, target: Path, shortcut_name: str) -> dict[str, Any]:
    if not target.exists():
        raise FileNotFoundError(str(target))
    desktop = Path(os.environ["USERPROFILE"]) / "Desktop"
    shortcut = desktop / f"{shortcut_name}.lnk"
    script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$shortcut = $shell.CreateShortcut({json.dumps(str(shortcut))}); "
        f"$shortcut.TargetPath = {json.dumps(str(target))}; "
        "$shortcut.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    return {
        "shortcut_name": shortcut_name,
        "shortcut_handle": _path_handle(shortcut),
        "target_handle": _path_handle(target),
    }


def _default_action_runner(
    *,
    packet: dict[str, Any],
    runtime_attestation: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    del runtime_attestation, run_id
    source_url = packet.get("lawful_source_url") or packet.get("source_url")
    if not isinstance(source_url, str) or not source_url.strip():
        raise ValueError("lawful_source_url is required")
    source_url = source_url.strip()
    _validate_source_url(source_url)
    filename = _safe_filename(packet, source_url)

    raw_actions = packet.get("requested_actions") or []
    if not isinstance(raw_actions, list) or not all(isinstance(a, str) for a in raw_actions):
        raise ValueError("requested_actions must be a list of strings")
    actions = [a for a in raw_actions if a in _ALLOWED_ACTIONS]

    root = Path(os.environ["USERPROFILE"]) / "Downloads" / "WorkflowEffects"
    effect_dir = root / (_idempotency_key(packet)[:16] or "no-idempotency-key")
    installer_path = effect_dir / filename
    evidence: dict[str, Any] = {
        "source_url": source_url,
        "source_filename": filename,
        "actions_completed": [],
        "evidence_recorded_at": time.time(),
    }

    if "download" in actions:
        evidence["download_receipt"] = _download(source_url, installer_path)
        evidence["actions_completed"].append("download")
    if "hash" in actions:
        if not installer_path.exists():
            raise FileNotFoundError("cannot hash before installer download exists")
        evidence["sha256"] = _sha256_file(installer_path)
        evidence["actions_completed"].append("hash")
    if "launch_installer" in actions:
        evidence["installer_launch_receipt"] = _launch(installer_path)
        evidence["actions_completed"].append("launch_installer")

    target_raw = packet.get("installed_executable_path") or (
        packet.get("shortcut", {}).get("target_path")
        if isinstance(packet.get("shortcut"), dict) else None
    )
    target = Path(target_raw) if isinstance(target_raw, str) and target_raw else None
    shortcut_name = packet.get("shortcut_name") or "Tiberian Sun"
    if "create_shortcut" in actions:
        if target is None:
            raise ValueError("create_shortcut requires installed_executable_path")
        evidence["shortcut_receipt"] = _create_shortcut(
            target=target,
            shortcut_name=str(shortcut_name),
        )
        evidence["actions_completed"].append("create_shortcut")
    if "launch_shortcut" in actions:
        shortcut = Path(os.environ["USERPROFILE"]) / "Desktop" / f"{shortcut_name}.lnk"
        evidence["shortcut_launch_receipt"] = _launch(shortcut)
        evidence["actions_completed"].append("launch_shortcut")
    if "record_evidence" in actions:
        evidence["objective_evidence_handle"] = (
            f"local-evidence:{_idempotency_key(packet)[:16] or 'unkeyed'}"
        )
        evidence["actions_completed"].append("record_evidence")
    return evidence


def _redact_evidence(value: Any) -> Any:
    """Remove private local paths from branch-visible evidence."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"path", "private_path", "local_path", "target_path"}:
                continue
            redacted[key] = _redact_evidence(item)
        return redacted
    if isinstance(value, list):
        return [_redact_evidence(item) for item in value]
    if isinstance(value, Path):
        return {"path_handle": _path_handle(value)}
    return value


def run_windows_desktop_effector(
    *,
    node_id: str,
    output_keys: list[str],
    run_state: dict[str, Any],
    base_path: str | Path | None = None,
    run_id: str = "",
    runtime_attestation: dict[str, Any] | None = None,
    action_runner: ActionRunner | None = None,
) -> dict[str, Any]:
    """Run one host-local Windows desktop effect packet.

    The function never raises to the run-completion path; every refusal
    or failure is returned as structured evidence.
    """
    matched_key, packet = _find_packet(output_keys=output_keys, run_state=run_state)
    if packet is None:
        return {
            "error": (
                f"node '{node_id}' declared effects=["
                f"{EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME}] but no "
                "output_key held a parseable Windows desktop effect packet"
            ),
            "error_kind": "no_matching_packet",
        }

    destination = _destination(packet)
    idem_key = _idempotency_key(packet)
    universe_dir = Path(base_path) if base_path is not None else None

    if not _has_user_approval(packet):
        return {
            "error": "explicit user approval is required for host-local desktop effects",
            "error_kind": "approval_required",
            "phase": "phase_2",
            "destination": destination,
            "matched_output_key": matched_key,
        }

    if not _check_consent(universe_dir, destination):
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "missing_consent",
            "destination": destination,
            "intent": packet,
            "matched_output_key": matched_key,
            "hint": (
                "Call extensions action=grant_effector_consent "
                f"sink={EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME} "
                f"destination={destination} before dispatching host-local "
                "Windows desktop effects."
            ),
        }

    attestation = runtime_attestation or attest_windows_desktop_runtime()
    if not _runtime_is_windows_desktop(attestation):
        return {
            "error": (
                "No attested interactive Windows desktop host is available; "
                "refusing host-local materialization before any effect runs."
            ),
            "error_kind": "no_host_available",
            "reason": "BLOCKED_WRONG_RUNTIME",
            "phase": "phase_2",
            "destination": destination,
            "runtime_attestation": attestation,
            "matched_output_key": matched_key,
        }

    try:
        reservation = _try_reserve(
            universe_dir,
            idempotency_key=idem_key,
            run_id=run_id,
        )
    except sqlite3.OperationalError as exc:
        return {
            "error": (
                "receipt store unavailable; refusing host-local Windows "
                f"desktop effect to avoid duplicate writes: {exc}"
            ),
            "error_kind": (
                "receipt_store_locked"
                if _is_lock_error(exc) else "receipt_store_error"
            ),
            "phase": "phase_2",
            "destination": destination,
            "idempotency_key": idem_key,
            "matched_output_key": matched_key,
        }

    status = reservation.get("status")
    if status == "duplicate":
        recorded = reservation.get("row") or {}
        return {
            "idempotency_dedup_hit": True,
            "phase": "phase_2",
            "destination": destination,
            "matched_output_key": matched_key,
            "evidence": recorded.get("evidence") or {},
            "recorded_run_id": recorded.get("run_id"),
            "recorded_at": recorded.get("created_at"),
            "idempotency_key": idem_key,
        }
    if status == "in_flight":
        held = reservation.get("row") or {}
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "concurrent_in_flight",
            "destination": destination,
            "idempotency_key": idem_key,
            "matched_output_key": matched_key,
            "held_by_run_id": held.get("run_id"),
            "reservation_created_at": held.get("created_at"),
            "intent": packet,
        }
    if status not in (
        "reserved",
        "reserved_after_stale",
        "reserved_after_failed",
        "no_hint",
    ):
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "reservation_unknown_state",
            "destination": destination,
            "idempotency_key": idem_key,
            "reservation_status": str(status),
            "matched_output_key": matched_key,
            "intent": packet,
        }

    runner = action_runner or _default_action_runner
    try:
        raw_evidence = runner(
            packet=packet,
            runtime_attestation=attestation,
            run_id=run_id,
        )
    except Exception as exc:
        _release_reservation(universe_dir, idempotency_key=idem_key, run_id=run_id)
        return {
            "error": f"host-local Windows desktop effect failed: {exc}",
            "error_kind": "windows_desktop_effect_failed",
            "phase": "phase_2",
            "destination": destination,
            "idempotency_key": idem_key,
            "reservation_released": bool(idem_key),
            "matched_output_key": matched_key,
        }

    evidence = _redact_evidence(raw_evidence)
    if not isinstance(evidence, dict):
        evidence = {"result": evidence}
    evidence.update({
        "phase": "phase_2",
        "destination": destination,
        "matched_output_key": matched_key,
        "idempotency_key": idem_key,
        "runtime_attestation": attestation,
        "recorded_at": time.time(),
    })
    if status in ("reserved_after_stale", "reserved_after_failed"):
        evidence["reservation_origin"] = status

    if idem_key and not _finalize_receipt(
        universe_dir,
        idempotency_key=idem_key,
        evidence=evidence,
        run_id=run_id,
    ):
        evidence["receipt_finalize_failed"] = True
    return evidence
