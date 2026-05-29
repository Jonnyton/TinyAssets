"""read_repo_files opaque callable — read side of the patch-request loop.

Mocks ``_read_request`` so no network is touched. Covers happy read, missing ->
null, denied, rejected paths, too-large, truncation (file-count and total-byte),
token resolution (separate read map, not the write map), and registration.

Design note: docs/design-notes/2026-05-29-read-repo-files-primitive.md
"""

from __future__ import annotations

import base64
import json

from workflow.effectors import github_read as gr

_DEST = "Jonnyton/Workflow"


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _file_resp(text: str) -> tuple[dict, None]:
    body = text.encode("utf-8")
    return {"type": "file", "size": len(body), "content": _b64(text)}, None


def _scripted_reader(by_path):
    """Build a fake _read_request from a {path: (parsed, error)} map."""
    def fake(*, destination, path, token):
        fake.calls.append((destination, path, token))
        if path in by_path:
            return by_path[path]
        return None, {"http_status": 404, "detail": "Not Found"}
    fake.calls = []
    return fake


def _run(state, monkeypatch, reader=None, env=None):
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    if reader is not None:
        monkeypatch.setattr(gr, "_read_request", reader)
    result = gr.read_repo_files(state)
    return (
        json.loads(result["current_contents_json"]),
        json.loads(result["read_status_json"]),
    )


def test_happy_read_returns_contents_and_present_status(monkeypatch):
    reader = _scripted_reader({"a.py": _file_resp("print('a')\n")})
    contents, status = _run(
        {"read_destination": _DEST, "target_paths": "a.py"}, monkeypatch, reader
    )
    assert contents == {"a.py": "print('a')\n"}
    assert status["a.py"] == "present"
    assert status["_truncated"] is False
    assert status["_errors"] == {}


def test_missing_file_is_null_not_error(monkeypatch):
    reader = _scripted_reader({})  # everything 404
    contents, status = _run(
        {"read_destination": _DEST, "target_paths": "nope.py"}, monkeypatch, reader
    )
    assert contents == {"nope.py": None}
    assert status["nope.py"] == "missing"
    assert "nope.py" not in status["_errors"]


def test_denied_maps_to_scope_signal(monkeypatch):
    reader = _scripted_reader(
        {"secret.py": (None, {"http_status": 403, "detail": "no access"})}
    )
    contents, status = _run(
        {"read_destination": _DEST, "target_paths": "secret.py"}, monkeypatch, reader
    )
    assert "secret.py" not in contents
    assert status["secret.py"] == "denied"
    assert status["_errors"]["secret.py"] == "read_contents_denied"


def test_absolute_and_traversal_paths_rejected(monkeypatch):
    reader = _scripted_reader({})
    contents, status = _run(
        {"read_destination": _DEST, "target_paths": "/etc/passwd, ../../secrets.env"},
        monkeypatch,
        reader,
    )
    assert status["/etc/passwd"] == "rejected"
    assert status["../../secrets.env"] == "rejected"
    assert status["_errors"]["/etc/passwd"] == "read_path_rejected"
    # Rejected paths never hit the network.
    assert reader.calls == []


def test_encoded_traversal_and_backslash_paths_rejected(monkeypatch):
    reader = _scripted_reader({})
    paths = [
        "%2e%2e/secrets.env",
        ".%2e/secrets.env",
        "safe\\evil.py",
        "a/%2F/b.py",
        "a/./b.py",
    ]
    _contents, status = _run(
        {"read_destination": _DEST, "target_paths": paths},
        monkeypatch,
        reader,
    )
    for path in paths:
        assert status[path] == "rejected"
        assert status["_errors"][path] == "read_path_rejected"
    assert reader.calls == []


def test_read_request_quotes_path_component(monkeypatch):
    urls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {"type": "file", "size": 1, "content": _b64("x")}
            ).encode("utf-8")

    def fake_urlopen(req, timeout):
        urls.append(req.full_url)
        return FakeResponse()

    monkeypatch.setattr(gr.urllib.request, "urlopen", fake_urlopen)

    parsed, err = gr._read_request(
        destination=_DEST,
        path="dir/a b#c?ref=other.py",
        token="",
    )

    assert err is None
    assert parsed["type"] == "file"
    assert urls == [
        "https://api.github.com/repos/Jonnyton/Workflow/contents/"
        "dir/a%20b%23c%3Fref%3Dother.py"
    ]


def test_directory_type_rejected(monkeypatch):
    reader = _scripted_reader({"src": ({"type": "dir"}, None)})
    _contents, status = _run(
        {"read_destination": _DEST, "target_paths": "src"}, monkeypatch, reader
    )
    assert status["src"] == "rejected"
    assert status["_errors"]["src"] == "read_path_rejected"


def test_too_large_by_size_returns_null(monkeypatch):
    reader = _scripted_reader(
        {"big.py": ({"type": "file", "size": 999_999, "content": _b64("x")}, None)}
    )
    contents, status = _run(
        {"read_destination": _DEST, "target_paths": "big.py"},
        monkeypatch,
        reader,
        env={"WORKFLOW_GITHUB_READ_MAX_BYTES_PER_FILE": "100"},
    )
    assert contents == {"big.py": None}
    assert status["big.py"] == "too_large"
    assert status["_errors"]["big.py"] == "read_file_too_large"


def test_file_count_cap_truncates_extras(monkeypatch):
    reader = _scripted_reader(
        {"a.py": _file_resp("a"), "b.py": _file_resp("b")}
    )
    contents, status = _run(
        {"read_destination": _DEST, "target_paths": "a.py, b.py"},
        monkeypatch,
        reader,
        env={"WORKFLOW_GITHUB_READ_MAX_FILES": "1"},
    )
    assert "a.py" in contents and contents["a.py"] == "a"
    assert status["b.py"] == "truncated"
    assert status["_errors"]["b.py"] == "read_truncated"
    assert status["_truncated"] is True


def test_total_byte_cap_truncates(monkeypatch):
    reader = _scripted_reader(
        {"a.py": _file_resp("aaaaa"), "b.py": _file_resp("bbbbb")}
    )
    contents, status = _run(
        {"read_destination": _DEST, "target_paths": "a.py, b.py"},
        monkeypatch,
        reader,
        env={"WORKFLOW_GITHUB_READ_MAX_TOTAL_BYTES": "6"},
    )
    assert contents["a.py"] == "aaaaa"
    assert status["b.py"] == "truncated"
    assert status["_truncated"] is True


def test_invalid_destination(monkeypatch):
    _contents, status = _run(
        {"read_destination": "not-a-repo", "target_paths": "a.py"}, monkeypatch
    )
    assert status["_errors"]["_destination"] == "read_destination_invalid"


def test_no_target_paths(monkeypatch):
    _contents, status = _run({"read_destination": _DEST}, monkeypatch)
    assert status["_errors"]["_paths"] == "no_target_paths"


def test_json_array_paths_parsed(monkeypatch):
    reader = _scripted_reader({"a.py": _file_resp("a"), "b.py": _file_resp("b")})
    contents, _status = _run(
        {"read_destination": _DEST, "target_paths": '["a.py", "b.py"]'},
        monkeypatch,
        reader,
    )
    assert set(contents) == {"a.py", "b.py"}


def test_read_token_uses_separate_map_not_write_map(monkeypatch):
    # Write map present, read map absent -> reads stay unauthenticated (empty
    # token), proving we do NOT reuse the write credential.
    monkeypatch.setenv("WORKFLOW_GITHUB_PR_CAPABILITIES", json.dumps({_DEST: "WRITETOKEN"}))
    monkeypatch.delenv("WORKFLOW_GITHUB_READ_CAPABILITIES", raising=False)
    reader = _scripted_reader({"a.py": _file_resp("a")})
    _run({"read_destination": _DEST, "target_paths": "a.py"}, monkeypatch, reader)
    assert reader.calls[0][2] == ""  # token empty -> unauthenticated


def test_read_token_resolved_from_read_map(monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_READ_CAPABILITIES", json.dumps({_DEST: "READTOKEN"})
    )
    reader = _scripted_reader({"a.py": _file_resp("a")})
    _run({"read_destination": _DEST, "target_paths": "a.py"}, monkeypatch, reader)
    assert reader.calls[0][2] == "READTOKEN"


def test_registration_resolves_in_domain_registry():
    from workflow.domain_registry import resolve_domain_callable

    gr.register_read_repo_files()
    assert resolve_domain_callable("workflow", "read_repo_files") is gr.read_repo_files
