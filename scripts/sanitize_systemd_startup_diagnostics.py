#!/usr/bin/env python3
"""Reduce a systemd/Compose journal window to fixed public-safe signals."""

from __future__ import annotations

import json
import sys
from typing import Any

MAX_JOURNAL_BYTES = 262_144

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


def sanitize_journal(raw: bytes) -> dict[str, Any]:
    """Return fixed stage/failure names without copying journal text."""

    input_truncated = len(raw) > MAX_JOURNAL_BYTES
    bounded = raw[-MAX_JOURNAL_BYTES:]
    decoded = bounded.decode("utf-8", errors="replace")
    normalized = " ".join(decoded.casefold().split())

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
    result = sanitize_journal(sys.stdin.buffer.read())
    json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
