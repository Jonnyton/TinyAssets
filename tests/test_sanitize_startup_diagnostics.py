from __future__ import annotations

import json

from scripts.sanitize_startup_diagnostics import (
    sanitize_candidate_state,
    sanitize_startup_log,
)

_REVISION = "a" * 40
_IMAGE = f"ghcr.io/jonnyton/tinyassets-daemon@sha256:{'b' * 64}"


def test_sanitizer_emits_only_allowlisted_traceback_signals():
    tunnel_token = "eyJh-secret-tunnel-token-that-must-never-survive"
    api_secret = "sk-live-super-secret-value"
    raw = f"""
tinyassets-tunnel cloudflared tunnel --token {tunnel_token}
request authorization=Bearer {api_secret}
Traceback (most recent call last):
  File "/app/tinyassets/universe_server.py", line 412, in main
    start_with_secret("{api_secret}")
  File "/app/tinyassets/outcomes/schema.py", line 87, in migrate
    cursor.execute(user_controlled_sql)
sqlite3.OperationalError: no such column: branches.owner_subject
""".encode()

    result = sanitize_startup_log(raw)
    serialized = json.dumps(result, sort_keys=True)

    assert tunnel_token not in serialized
    assert api_secret not in serialized
    assert "cloudflared tunnel" not in serialized
    assert "cursor.execute" not in serialized
    assert result["schema_version"] == 1
    assert result["raw_bytes"] == len(raw)
    assert "raw_sha256" not in result
    assert set(result) == {
        "schema_version",
        "raw_bytes",
        "raw_lines",
        "input_truncated",
        "signals",
    }
    assert result["signals"] == [
        {
            "kind": "python_frame",
            "path": "tinyassets/universe_server.py",
        },
        {
            "kind": "python_frame",
            "path": "tinyassets/outcomes/schema.py",
        },
        {
            "category": "missing_database_object",
            "exception": "sqlite3.OperationalError",
            "kind": "python_exception",
        },
    ]


def test_sanitizer_drops_unapproved_paths_and_exception_names():
    secret = "tenant-secret-identifier"
    raw = f"""
  File "/data/{secret}/plugin.py", line 1, in run
  File "/app/../../data/{secret}.py", line 2, in steal
  File "/app/{secret}/plugin.py", line 3, in {secret}
  File "/app/tinyassets/{secret}.py", line 4, in {secret}
SecretTokenError: {secret}
PermissionError: [Errno 13] Permission denied: '/data/{secret}'
""".encode()

    result = sanitize_startup_log(raw)
    serialized = json.dumps(result, sort_keys=True)

    assert secret not in serialized
    assert result["signals"] == [
        {
            "category": "permission_denied",
            "exception": "PermissionError",
            "kind": "python_exception",
        }
    ]


def test_sanitizer_maps_forged_valid_frame_to_public_source_identity_only():
    function_secret = "tenant_secret_identifier"
    numeric_secret = "876543210"
    raw = (
        f'  File "/app/tinyassets/universe_server.py", '
        f"line {numeric_secret}, in {function_secret}\n"
    ).encode()

    result = sanitize_startup_log(raw)
    serialized = json.dumps(result, sort_keys=True)

    assert function_secret not in serialized
    assert numeric_secret not in serialized
    assert result["signals"] == [
        {"kind": "python_frame", "path": "tinyassets/universe_server.py"}
    ]


def test_sanitizer_bounds_input_and_signal_count():
    frame = b'  File "/app/tinyassets/universe_server.py", line 1, in boot\n'
    raw = b"x" * 140_000 + frame * 100

    result = sanitize_startup_log(raw)

    assert result["raw_bytes"] == 131_072
    assert result["input_truncated"] is True
    assert len(result["signals"]) == 1


def test_candidate_state_requires_exact_image_and_revision_match():
    raw = (
        f"exited|false|false|1|false|unhealthy|{_REVISION}|{_IMAGE}\n"
    ).encode()

    result = sanitize_candidate_state(
        raw,
        target_revision=_REVISION,
        target_image_ref=_IMAGE,
    )

    assert result["candidate_identity_match"] is True
    assert result["container_revision"] == _REVISION
    assert result["container_image_ref"] == _IMAGE
    assert result["exit_code"] == 1


def test_candidate_state_rejects_each_identity_mismatch_without_raw_disclosure():
    token = "token-bearing-forged-state"
    valid_raw = (
        f"exited|false|false|1|false|unhealthy|{_REVISION}|{_IMAGE}\n"
    ).encode()

    revision_mismatch = sanitize_candidate_state(
        valid_raw,
        target_revision="c" * 40,
        target_image_ref=_IMAGE,
    )
    image_mismatch = sanitize_candidate_state(
        valid_raw,
        target_revision=_REVISION,
        target_image_ref=f"ghcr.io/jonnyton/tinyassets-daemon@sha256:{'d' * 64}",
    )
    malformed = sanitize_candidate_state(
        f"{token}|{token}".encode(),
        target_revision=_REVISION,
        target_image_ref=_IMAGE,
    )

    assert revision_mismatch["candidate_identity_match"] is False
    assert image_mismatch["candidate_identity_match"] is False
    assert revision_mismatch["container_revision"] == "unavailable"
    assert revision_mismatch["container_image_ref"] == "unavailable"
    assert image_mismatch["container_revision"] == "unavailable"
    assert image_mismatch["container_image_ref"] == "unavailable"
    assert malformed == {
        "candidate_identity_match": False,
        "capture": "unavailable",
    }
    assert token not in json.dumps(malformed)
