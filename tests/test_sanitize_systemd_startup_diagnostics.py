from __future__ import annotations

import datetime
import json

import pytest

from scripts.sanitize_systemd_startup_diagnostics import (
    journalctl_window,
    sanitize_framed_journal,
    sanitize_journal,
    validate_window,
)


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


def test_journal_sanitizer_emits_only_allowlisted_oauth_rejection_categories():
    token = "eyJ-private-token-material"
    result = sanitize_journal(
        (
            "WorkOS bearer token rejected category=audience suppressed=0\n"
            "WorkOS bearer token rejected category=expired suppressed=2\n"
            "WorkOS bearer token rejected category=audience suppressed=4\n"
            "WorkOS bearer token rejected category=private-claim suppressed=0\n"
            f"unrelated detail {token}\n"
        ).encode()
    )

    assert result["oauth_rejection_categories"] == ["audience", "expired"]
    rendered = json.dumps(result)
    assert token not in rendered
    assert "private-claim" not in rendered


def test_journal_sanitizer_requires_exact_oauth_diagnostic_shape():
    result = sanitize_journal(
        b"WorkOS bearer token rejected category=issuer suppressed=not-a-count\n"
        b"WorkOS bearer token rejected category=signature suppressed=1 trailing\n"
        b"prefix WorkOS bearer token rejected category=malformed suppressed=0\n"
        b"WorkOS bearer token rejected category=signing_key suppressed=12\n"
    )

    assert result["oauth_rejection_categories"] == ["signing_key"]


def test_journal_sanitizer_uses_only_the_terminal_compose_attempt():
    result = sanitize_journal(
        b"Container tinyassets-daemon Creating\n"
        b"Container tinyassets-daemon Created\n"
        b"Container tinyassets-daemon Starting\n"
        b"Container tinyassets-daemon Started\n"
        b"Container tinyassets-daemon Creating\n"
        b"Container tinyassets-daemon Created\n"
        b"tinyassets-daemon.service: Scheduled restart job\n"
    )

    assert result["stages"] == ["container_create", "container_created"]
    assert result["derived_state"] == "created_without_start"
    assert result["failure_classes"] == ["unit_restart_scheduled"]


def test_journal_sanitizer_resets_on_starting_only_retry():
    result = sanitize_journal(
        b"Container tinyassets-daemon Starting\n"
        b"Container tinyassets-daemon Started\n"
        b"Container tinyassets-daemon Starting\n"
        b"tinyassets-daemon.service: Main process exited, code=exited, status=1/FAILURE\n"
    )

    assert result["stages"] == ["container_starting"]
    assert result["derived_state"] == "start_attempted"
    assert result["failure_classes"] == ["process_exit_failure"]


def test_journal_sanitizer_preserves_name_conflict_and_mixed_unknown_failure():
    token = "token-bearing-unknown-detail"
    result = sanitize_journal(
        (
            "Container tinyassets-daemon Creating\n"
            'Conflict. The container name "/tinyassets-logs" '
            'is already in use by container "abc".\n'
            "tinyassets-daemon.service: Scheduled restart job\n"
            f"fatal unclassified condition: {token}\n"
        ).encode()
    )

    assert result["failure_classes"] == [
        "container_name_conflict",
        "unit_restart_scheduled",
        "other_failure",
    ]
    assert token not in json.dumps(result)


def test_journal_sanitizer_names_only_the_allowlisted_conflicting_container():
    token = "private-conflicting-container"
    result = sanitize_journal(
        (
            "Container tinyassets-daemon Creating\n"
            "Container tinyassets-daemon Created\n"
            "Container tinyassets-worker-codex-2 Starting\n"
            'Conflict. The container name "/tinyassets-logs" is already in use '
            f'by container "{token}".\n'
        ).encode()
    )

    assert result["failure_classes"] == ["container_name_conflict"]
    assert result["conflict_containers"] == ["tinyassets-logs"]
    assert token not in json.dumps(result)


def test_journal_sanitizer_does_not_prefix_match_allowlisted_worker_names():
    result = sanitize_journal(
        b"Container tinyassets-daemon Creating\n"
        b'Conflict. The container name "/tinyassets-worker-codex-2" '
        b'is already in use by container "opaque"\n'
    )

    assert result["conflict_containers"] == ["tinyassets-worker-codex-2"]


def test_journal_sanitizer_does_not_echo_unallowlisted_conflicting_name():
    private_name = "private-customer-container"
    result = sanitize_journal(
        (
            "Container tinyassets-daemon Creating\n"
            f'Conflict. The container name "/{private_name}" is already in use '
            'by container "opaque"\n'
        ).encode()
    )

    assert result["failure_classes"] == ["container_name_conflict"]
    assert result["conflict_containers"] == []
    assert private_name not in json.dumps(result)


@pytest.mark.parametrize(
    "private_name",
    (
        "private_tinyassets-logs_backup",
        "private.tinyassets-logs.backup",
        "αtinyassets-logsβ",
        "TINYASSETS-LOGS",
        "tinyaßets-logs",
        "tinyaſsets-logs",
        "/tinyassets-logs",
    ),
)
def test_journal_sanitizer_requires_exact_case_sensitive_conflict_operand(
    private_name: str,
):
    result = sanitize_journal(
        (
            "Container tinyassets-daemon Creating\n"
            f'Conflict. The container name "/{private_name}" is already in use '
            'by container "opaque"\n'
        ).encode()
    )

    assert result["failure_classes"] == ["container_name_conflict"]
    assert result["conflict_containers"] == []
    assert private_name not in json.dumps(result)


def test_journal_sanitizer_ignores_unrelated_allowlisted_name_on_conflict_line():
    result = sanitize_journal(
        b"Container tinyassets-daemon Creating\n"
        b'Conflict. The container name "/private-container" is already in use '
        b'by container "opaque"; service tinyassets-daemon\n'
    )

    assert result["conflict_containers"] == []


def test_journal_sanitizer_conflict_names_follow_only_the_terminal_attempt():
    result = sanitize_journal(
        b"Container tinyassets-daemon Creating\n"
        b'Conflict. The container name "/tinyassets-worker" is already in use '
        b'by container "old"\n'
        b"Container tinyassets-daemon Creating\n"
        b'Conflict. The container name "/tinyassets-logs" is already in use '
        b'by container "new-1"\n'
        b'Conflict. The container name "/tinyassets-tunnel" is already in use '
        b'by container "new-2"\n'
    )

    assert result["conflict_containers"] == ["tinyassets-tunnel", "tinyassets-logs"]


def test_framed_journal_reports_source_truncation_within_transport_cap():
    payload = b"Container tinyassets-daemon Created\n"

    truncated = sanitize_framed_journal(b"1" + payload)
    complete = sanitize_framed_journal(b"0" + payload)

    assert truncated["input_truncated"] is True
    assert complete["input_truncated"] is False
    with pytest.raises(ValueError, match="truncation flag"):
        sanitize_framed_journal(b"x" + payload)


def test_window_validator_accepts_a_strict_bounded_past_window():
    validate_window(
        "2026-07-31T18:34:00Z",
        "2026-07-31T18:36:36Z",
        now=datetime.datetime(2026, 7, 31, 19, 0, tzinfo=datetime.UTC),
    )


def test_journalctl_window_normalizes_strict_utc_to_unambiguous_epoch():
    assert journalctl_window(
        "2026-07-31T18:34:00Z",
        "2026-07-31T18:36:36Z",
        now=datetime.datetime(2026, 7, 31, 19, 0, tzinfo=datetime.UTC),
    ) == ("@1785522840", "@1785522996")


@pytest.mark.parametrize(
    ("since_utc", "until_utc", "message"),
    (
        ("$(touch /tmp/pwn)", "2026-07-31T18:36:36Z", "strict UTC"),
        ("2026-07-31T18:34:00Z", "invalid", "strict UTC"),
        ("2026-07-31T18:36:36Z", "2026-07-31T18:34:00Z", "must follow"),
        ("2026-07-31T18:00:00Z", "2026-07-31T18:36:36Z", "10 minutes"),
        ("2026-07-31T19:00:00Z", "2026-07-31T19:01:00Z", "in the past"),
    ),
)
def test_window_validator_rejects_unsafe_inputs(
    since_utc: str,
    until_utc: str,
    message: str,
):
    with pytest.raises(ValueError, match=message):
        validate_window(
            since_utc,
            until_utc,
            now=datetime.datetime(2026, 7, 31, 19, 0, tzinfo=datetime.UTC),
        )
    with pytest.raises(ValueError, match=message):
        journalctl_window(
            since_utc,
            until_utc,
            now=datetime.datetime(2026, 7, 31, 19, 0, tzinfo=datetime.UTC),
        )
