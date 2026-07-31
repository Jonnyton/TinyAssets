from __future__ import annotations

import json

from scripts.sanitize_startup_diagnostics import sanitize_startup_log


def test_sanitizer_emits_only_allowlisted_traceback_signals():
    tunnel_token = "eyJh-secret-tunnel-token-that-must-never-survive"
    api_secret = "sk-live-super-secret-value"
    raw = f"""
tinyassets-tunnel cloudflared tunnel --token {tunnel_token}
request authorization=Bearer {api_secret}
Traceback (most recent call last):
  File "/app/tinyassets/universe_server.py", line 412, in main
    start_with_secret("{api_secret}")
  File "/app/tinyassets/storage/schema.py", line 87, in migrate
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
            "function": "main",
            "kind": "python_frame",
            "line": 412,
            "path": "tinyassets/universe_server.py",
        },
        {
            "function": "migrate",
            "kind": "python_frame",
            "line": 87,
            "path": "tinyassets/storage/schema.py",
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


def test_sanitizer_bounds_input_and_signal_count():
    frame = b'  File "/app/tinyassets/a.py", line 1, in boot\n'
    raw = b"x" * 140_000 + frame * 100

    result = sanitize_startup_log(raw)

    assert result["raw_bytes"] == 131_072
    assert result["input_truncated"] is True
    assert len(result["signals"]) == 1
