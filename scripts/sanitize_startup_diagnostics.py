#!/usr/bin/env python3
"""Reduce failed-startup logs to a public-safe structural diagnosis."""

from __future__ import annotations

import json
import re
import sys
from typing import Any

MAX_RAW_BYTES = 131_072
MAX_SIGNALS = 64

_FRAME = re.compile(
    r'^\s*File "/app/(?P<path>[A-Za-z0-9_./-]{1,240})", '
    r"line (?P<line>[1-9][0-9]{0,8}), "
    r"in (?P<function>[A-Za-z_][A-Za-z0-9_]{0,127})\s*$"
)
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
            if ".." not in path.split("/"):
                signal = {
                    "kind": "python_frame",
                    "path": path,
                    "line": int(frame.group("line")),
                    "function": frame.group("function"),
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


def main() -> int:
    result = sanitize_startup_log(sys.stdin.buffer.read())
    json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
