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

_CONTAINER_NAME_CONFLICT_MARKERS = (
    "container name is already in use",
    "is already in use by container",
    "conflict. the container name",
)
_CANONICAL_CONTAINER_NAMES = (
    "tinyassets-daemon",
    "tinyassets-tunnel",
    "tinyassets-logs",
    "tinyassets-worker",
    "tinyassets-worker-codex-2",
    "tinyassets-worker-claude-1",
    "tinyassets-worker-claude-2",
)
_CONFLICT_NAME_PATTERN = re.compile(
    r'The container name "([^"\r\n]+)" is already in use by container'
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
        "container_name_conflict",
        _CONTAINER_NAME_CONFLICT_MARKERS,
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


def journalctl_window(
    since_utc: str,
    until_utc: str,
    *,
    now: datetime.datetime | None = None,
) -> tuple[str, str]:
    """Return an unambiguous, old-systemd-compatible journal window."""

    validate_window(since_utc, until_utc, now=now)
    return tuple(
        f"@{int(datetime.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp())}"
        for value in (since_utc, until_utc)
    )


def sanitize_journal(
    raw: bytes,
    *,
    source_truncated: bool = False,
) -> dict[str, Any]:
    """Return fixed stage/failure names without copying journal text."""

    input_truncated = source_truncated or len(raw) > MAX_JOURNAL_BYTES
    bounded = raw[-MAX_JOURNAL_BYTES:]
    decoded = bounded.decode("utf-8", errors="replace")
    source_lines = decoded.splitlines()
    normalized_lines = [
        " ".join(line.casefold().split()) for line in source_lines
    ]
    attempt_starts = [
        index
        for index, line in enumerate(normalized_lines)
        if _STAGE_MARKERS[0][1] in line or _STAGE_MARKERS[2][1] in line
    ]
    if attempt_starts:
        terminal_start = attempt_starts[-1]
        normalized_lines = normalized_lines[terminal_start:]
        source_lines = source_lines[terminal_start:]
    normalized = " ".join(normalized_lines)

    exact_conflict_names = {
        operand[1:] if operand.startswith("/") else operand
        for line in source_lines
        for operand in _CONFLICT_NAME_PATTERN.findall(line)
    }
    conflict_containers = [
        name
        for name in _CANONICAL_CONTAINER_NAMES
        if name in exact_conflict_names
    ]

    stages = [name for name, marker in _STAGE_MARKERS if marker in normalized]
    failure_classes = [
        name
        for name, markers in _FAILURE_MARKERS
        if any(marker in normalized for marker in markers)
    ]
    generic_failure_lines = (
        line
        for line in normalized_lines
        if any(marker in line for marker in ("error", "failed", "failure", "fatal"))
    )
    if any(
        not any(
            marker in line
            for _name, markers in _FAILURE_MARKERS
            for marker in markers
        )
        for line in generic_failure_lines
    ):
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
        "conflict_containers": conflict_containers,
    }


def sanitize_framed_journal(raw: bytes) -> dict[str, Any]:
    """Decode a one-byte truncation flag within the 256 KiB transport cap."""

    if not raw or raw[:1] not in {b"0", b"1"}:
        raise ValueError("journal frame has no valid truncation flag")
    return sanitize_journal(raw[1:], source_truncated=raw[:1] == b"1")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--validate-window",
        nargs=2,
        metavar=("SINCE_UTC", "UNTIL_UTC"),
    )
    parser.add_argument(
        "--journalctl-window",
        nargs=2,
        metavar=("SINCE_UTC", "UNTIL_UTC"),
    )
    parser.add_argument("--framed-input", action="store_true")
    args = parser.parse_args()
    if args.validate_window:
        try:
            validate_window(*args.validate_window)
        except ValueError as exc:
            parser.error(str(exc))
        return 0
    if args.journalctl_window:
        try:
            normalized = journalctl_window(*args.journalctl_window)
        except ValueError as exc:
            parser.error(str(exc))
        sys.stdout.write("\n".join(normalized) + "\n")
        return 0
    raw = sys.stdin.buffer.read()
    try:
        result = sanitize_framed_journal(raw) if args.framed_input else sanitize_journal(raw)
    except ValueError as exc:
        parser.error(str(exc))
    json.dump(result, sys.stdout, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
