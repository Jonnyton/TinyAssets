from __future__ import annotations

import json

from scripts.sanitize_systemd_startup_diagnostics import sanitize_journal


def test_journal_sanitizer_emits_fixed_stages_and_classes_only():
    token = "token-bearing-private-host-path"
    raw = f"""
Container tinyassets-daemon  Creating
Container tinyassets-daemon  Created
tinyassets-daemon.service: Main process exited, code=killed, status=15/TERM
driver failed programming external connectivity: address already in use {token}
tinyassets-daemon.service: Start request repeated too quickly.
""".encode()

    result = sanitize_journal(raw)
    rendered = json.dumps(result)

    assert result["stages"] == ["container_create", "container_created"]
    assert result["failure_classes"] == [
        "port_bind_conflict",
        "unit_start_limit",
        "process_terminated",
    ]
    assert token not in rendered
    assert "address already in use" not in rendered


def test_journal_sanitizer_distinguishes_created_without_start():
    result = sanitize_journal(
        b"Container tinyassets-daemon Creating\n"
        b"Container tinyassets-daemon Created\n"
        b"tinyassets-daemon.service: Scheduled restart job\n"
    )

    assert result["derived_state"] == "created_without_start"
    assert result["failure_classes"] == ["unit_restart_scheduled"]


def test_journal_sanitizer_bounds_input_and_unknown_failure():
    token = b"token-bearing-unknown-failure"
    raw = b"x" * 300_000 + b"\nerror: " + token

    result = sanitize_journal(raw)

    assert result["input_truncated"] is True
    assert result["raw_bytes"] == 262_144
    assert result["failure_classes"] == ["other_failure"]
    assert token.decode() not in json.dumps(result)


def test_journal_sanitizer_never_echoes_hostile_shell_or_json_text():
    token = "$(echo secret) `whoami` | \\\"quoted\\\" /private/path"
    result = sanitize_journal(
        (
            "Container tinyassets-daemon Starting\n"
            f"permission denied: {token}\n"
        ).encode()
    )

    assert result["stages"] == ["container_starting"]
    assert result["failure_classes"] == ["permission_denied"]
    assert token not in json.dumps(result)
