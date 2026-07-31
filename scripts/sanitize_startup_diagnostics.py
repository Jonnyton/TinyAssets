#!/usr/bin/env python3
"""Reduce failed-startup logs to a public-safe structural diagnosis."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

MAX_RAW_BYTES = 131_072
MAX_SIGNALS = 64
STATE_SEPARATOR = "|"

_FRAME = re.compile(
    r'^\s*File "/app/(?P<path>[A-Za-z0-9_./-]{1,240})", '
    r"line (?P<line>[1-9][0-9]{0,8}), "
    r"in [A-Za-z_][A-Za-z0-9_]{0,127}\s*$"
)
_REPO_ROOT = Path(__file__).resolve().parents[1]
_TRUSTED_SOURCE_ROOT = _REPO_ROOT / "tinyassets"
_EXCEPTION = re.compile(
    r"^(?P<exception>(?:[A-Za-z_][A-Za-z0-9_]*\.)*"
    r"[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))(?::.*)?$"
)
_ALLOWED_EXCEPTIONS = {
    "AssertionError",
    "FileNotFoundError",
    "ImportError",
    "KeyError",
    "ModuleNotFoundError",
    "OSError",
    "PermissionError",
    "RuntimeError",
    "TypeError",
    "ValueError",
    "pydantic.ValidationError",
    "pydantic_core.ValidationError",
    "sqlite3.DatabaseError",
    "sqlite3.IntegrityError",
    "sqlite3.OperationalError",
    "sqlalchemy.exc.DatabaseError",
    "sqlalchemy.exc.IntegrityError",
    "sqlalchemy.exc.OperationalError",
}
_CANONICAL_IMAGE = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]+)?"
    r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+"
    r"@sha256:[0-9a-f]{64}$"
)


def _exception_category(exception: str, lowered_line: str) -> str:
    if "no such table" in lowered_line or "no such column" in lowered_line:
        return "missing_database_object"
    if "database is locked" in lowered_line:
        return "database_locked"
    if "malformed" in lowered_line or "corrupt" in lowered_line:
        return "database_corrupt"
    if exception == "PermissionError":
        return "permission_denied"
    if exception == "FileNotFoundError":
        return "missing_file"
    if exception in {"ImportError", "ModuleNotFoundError"}:
        return "import_failure"
    if "ValidationError" in exception:
        return "validation_failed"
    return "unclassified"


def _trusted_source_path(path: str) -> bool:
    """Accept only immutable Python source paths present in this checkout."""

    parts = path.split("/")
    if (
        len(parts) < 2
        or parts[0] != "tinyassets"
        or any(part in {"", ".", ".."} for part in parts)
        or not path.endswith(".py")
    ):
        return False
    candidate = _REPO_ROOT.joinpath(*parts)
    try:
        candidate.relative_to(_TRUSTED_SOURCE_ROOT)
    except ValueError:
        return False
    return candidate.is_file()


def sanitize_startup_log(raw: bytes) -> dict[str, Any]:
    """Return only fixed-schema, allowlisted signals from a bounded log tail."""

    input_truncated = len(raw) > MAX_RAW_BYTES
    bounded = raw[-MAX_RAW_BYTES:]
    decoded = bounded.decode("utf-8", errors="replace")
    signals: list[dict[str, Any]] = []
    seen: set[str] = set()

    for line in decoded.splitlines():
        signal: dict[str, Any] | None = None
        frame = _FRAME.fullmatch(line)
        if frame:
            path = frame.group("path")
            if _trusted_source_path(path):
                signal = {
                    "kind": "python_frame",
                    "path": path,
                }
        else:
            exception_match = _EXCEPTION.fullmatch(line.strip())
            if exception_match:
                exception = exception_match.group("exception")
                if exception in _ALLOWED_EXCEPTIONS:
                    signal = {
                        "kind": "python_exception",
                        "exception": exception,
                        "category": _exception_category(exception, line.lower()),
                    }

        if signal is None:
            continue
        identity = json.dumps(signal, sort_keys=True, separators=(",", ":"))
        if identity in seen:
            continue
        seen.add(identity)
        signals.append(signal)
        if len(signals) >= MAX_SIGNALS:
            break

    return {
        "schema_version": 1,
        "raw_bytes": len(bounded),
        "raw_lines": len(decoded.splitlines()),
        "input_truncated": input_truncated,
        "signals": signals,
    }


def sanitize_candidate_state(
    raw: bytes,
    *,
    target_revision: str,
    target_image_ref: str,
) -> dict[str, Any]:
    """Validate fixed-field container state and bind it to the candidate."""

    unavailable: dict[str, Any] = {
        "candidate_identity_match": False,
        "capture": "unavailable",
    }
    try:
        values = (
            raw.decode("utf-8", errors="strict").strip().split(STATE_SEPARATOR)
        )
    except UnicodeDecodeError:
        return unavailable
    if len(values) != 8:
        return unavailable
    (
        status,
        running,
        restarting,
        exit_code,
        oom_killed,
        health,
        container_revision,
        container_image_ref,
    ) = values
    if status not in {
        "created",
        "running",
        "paused",
        "restarting",
        "removing",
        "exited",
        "dead",
    }:
        return unavailable
    if running not in {"true", "false"} or restarting not in {"true", "false"}:
        return unavailable
    if oom_killed not in {"true", "false"}:
        return unavailable
    if health not in {"", "starting", "healthy", "unhealthy"}:
        return unavailable
    try:
        parsed_exit_code = int(exit_code)
    except ValueError:
        return unavailable

    valid_container_revision = bool(re.fullmatch(r"[0-9a-f]{40}", container_revision))
    valid_container_image = bool(_CANONICAL_IMAGE.fullmatch(container_image_ref))
    identity_match = bool(
        re.fullmatch(r"[0-9a-f]{40}", target_revision)
        and valid_container_revision
        and container_revision == target_revision
        and _CANONICAL_IMAGE.fullmatch(target_image_ref)
        and valid_container_image
        and container_image_ref == target_image_ref
    )
    return {
        "status": status,
        "running": running == "true",
        "restarting": restarting == "true",
        "exit_code": parsed_exit_code,
        "oom_killed": oom_killed == "true",
        "health": health or None,
        "container_revision": (
            container_revision if identity_match else "unavailable"
        ),
        "container_image_ref": (
            container_image_ref if identity_match else "unavailable"
        ),
        "candidate_identity_match": identity_match,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", action="store_true")
    parser.add_argument("--target-revision", default="")
    parser.add_argument("--target-image-ref", default="")
    args = parser.parse_args()
    if args.state:
        result = sanitize_candidate_state(
            sys.stdin.buffer.read(),
            target_revision=args.target_revision,
            target_image_ref=args.target_image_ref,
        )
    else:
        result = sanitize_startup_log(sys.stdin.buffer.read())
    json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    if args.state and result.get("candidate_identity_match") is not True:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
