#!/usr/bin/env python3
"""Reduce a systemd/Compose journal window to fixed public-safe signals."""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from typing import Any

MAX_JOURNAL_BYTES = 262_144
_WINDOW_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"
)

_STAGE_MARKERS = (
    ("container_create", "container tinyassets-daemon creating"),
    ("container_created", "container tinyassets-daemon created"),
    ("container_starting", "container tinyassets-daemon starting"),
    ("container_started", "container tinyassets-daemon started"),
)

_FAILURE_MARKERS = (
    (
        "port_bind_conflict",
        (
            "port is already allocated",
            "address already in use",
            "failed to bind host port",
            "bind for ",
        ),
    ),
    (
        "mount_failure",
        ("error mounting", "mounts denied", "invalid mount config"),
    ),
    ("permission_denied", ("permission denied",)),
    (
        "network_failure",
        ("network not found", "failed to create endpoint", "network sandbox"),
    ),
    (
        "dependency_failure",
        ("dependency failed to start", "dependency failed to complete"),
    ),
    (
        "compose_config_failure",
        ("invalid compose project", "validating ", "services must be a mapping"),
    ),
    (
        "unit_start_limit",
        ("start request repeated too quickly", "start-limit-hit"),
    ),
    (
        "process_terminated",
        ("code=killed, status=15/term", "terminated by signal", "signal=term"),
    ),
    (
        "process_exit_failure",
        ("main process exited, code=exited", "failed with result 'exit-code'"),
    ),
    (
        "unit_restart_scheduled",
        ("scheduled restart job",),
    ),
)


def validate_window(
    since_utc: str,
    until_utc: str,
    *,
    now: datetime.datetime | None = None,
) -> None:
    """Reject unsafe or ambiguous production journal windows."""

    values = (since_utc, until_utc)
    if not all(_WINDOW_PATTERN.fullmatch(value) for value in values):
        raise ValueError("diagnostic timestamps must be strict UTC seconds")
    start, end = (
        datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        for value in values
    )
    if end <= start:
        raise ValueError("diagnostic window end must follow start")
    if end - start > datetime.timedelta(minutes=10):
        raise ValueError("maximum diagnostic window is 10 minutes")
    current = now or datetime.datetime.now(datetime.UTC)
    if end > current:
        raise ValueError("diagnostic window must be in the past")


def sanitize_journal(raw: bytes) -> dict[str, Any]:
    """Return fixed stage/failure names without copying journal text."""

    input_truncated = len(raw) > MAX_JOURNAL_BYTES
    bounded = raw[-MAX_JOURNAL_BYTES:]
    decoded = bounded.decode("utf-8", errors="replace")
    normalized_lines = [
        " ".join(line.casefold().split()) for line in decoded.splitlines()
    ]
    attempt_starts = [
        index
        for index, line in enumerate(normalized_lines)
        if _STAGE_MARKERS[0][1] in line
    ]
    if attempt_starts:
        normalized_lines = normalized_lines[attempt_starts[-1] :]
    normalized = " ".join(normalized_lines)

    stages = [name for name, marker in _STAGE_MARKERS if marker in normalized]
    failure_classes = [
        name
        for name, markers in _FAILURE_MARKERS
        if any(marker in normalized for marker in markers)
    ]
    recognized_failure = bool(failure_classes)
    generic_failure = any(
        marker in normalized
        for marker in ("error", "failed", "failure", "fatal")
    )
    if generic_failure and not recognized_failure:
        failure_classes.append("other_failure")

    if "container_started" in stages:
        derived_state = "started"
    elif "container_starting" in stages:
        derived_state = "start_attempted"
    elif "container_created" in stages:
        derived_state = "created_without_start"
    elif "container_create" in stages:
        derived_state = "create_attempted"
    else:
        derived_state = "no_container_stage"

    return {
        "schema_version": 1,
        "raw_bytes": len(bounded),
        "raw_lines": len(decoded.splitlines()),
        "input_truncated": input_truncated,
        "derived_state": derived_state,
        "stages": stages,
        "failure_classes": failure_classes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--validate-window",
        nargs=2,
        metavar=("SINCE_UTC", "UNTIL_UTC"),
    )
    args = parser.parse_args()
    if args.validate_window:
        try:
            validate_window(*args.validate_window)
        except ValueError as exc:
            parser.error(str(exc))
        return 0
    result = sanitize_journal(sys.stdin.buffer.read())
    json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
