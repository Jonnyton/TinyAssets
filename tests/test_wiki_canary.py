"""Tests for scripts/wiki_canary.py — wiki write-roundtrip canary.

All tests use a scripted ``post_fn`` so no network I/O occurs.
The ScriptedPost helper is patterned after test_mcp_tool_canary.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import wiki_canary as wc  # noqa: E402
from mcp_tool_canary import ToolCanaryError  # noqa: E402

# ---- scripted post helper --------------------------------------------------


class ScriptedPost:
    """Feeds pre-scripted (response, sid) tuples back one call at a time."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, url, sid, payload, timeout, *, step_code):
        self.calls.append({
            "url": url, "sid": sid,
            "method": payload.get("method"),
            "payload": payload,
            "step_code": step_code,
        })
        if not self._responses:
            raise AssertionError(
                f"ScriptedPost ran out of responses at call "
                f"{len(self.calls)} (method={payload.get('method')!r})"
            )
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


# ---- fixture helpers -------------------------------------------------------


def _init_resp(sid: str = "sess-wiki") -> tuple[dict, str]:
    return (
        {"jsonrpc": "2.0", "id": 1, "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "tinyassets", "version": "1.0"},
            "capabilities": {},
        }},
        sid,
    )


def _notif_resp(sid: str = "sess-wiki") -> tuple[None, str]:
    return (None, sid)


def _wiki_write_rejected_resp(
    sid: str = "sess-wiki",
    raw_text: str | None = None,
    structured_content: dict | None = None,
) -> tuple[dict, str]:
    # Post-#1441 happy path: anonymous write_page returns the rejection
    # envelope (not a tool error).
    body = json.dumps({
        "status": "rejected",
        "error": "write_page: Anonymous writes are disabled on this server.",
        "auth_required": True,
        "tool": "write_page",
    })
    result = {
        "content": [{
            "type": "text",
            "text": raw_text if raw_text is not None else body,
        }],
        "isError": False,
    }
    if structured_content is not None:
        result["structuredContent"] = structured_content
    return (
        {"jsonrpc": "2.0", "id": 2, "result": result},
        sid,
    )


def _wiki_write_accepted_resp(sid: str = "sess-wiki") -> tuple[dict, str]:
    # Pre-#1441 shape: anonymous write persisting. Now a gate REGRESSION.
    body = json.dumps({
        "status": "drafted",
        "path": f"drafts/{wc._CANARY_CATEGORY}/{wc._CANARY_FILENAME}.md",
    })
    return (
        {"jsonrpc": "2.0", "id": 2, "result": {
            "content": [{"type": "text", "text": body}],
            "isError": False,
        }},
        sid,
    )


def _wiki_read_ok_resp(
    sid: str = "sess-wiki",
    raw_text: str | None = None,
    structured_content: dict | None = None,
) -> tuple[dict, str]:
    # Read response body must contain the canary content text.
    body = json.dumps({
        "path": f"drafts/{wc._CANARY_CATEGORY}/{wc._CANARY_FILENAME}.md",
        "is_draft": True,
        "content": f"[DRAFT] {wc._CANARY_CONTENT}",
        "truncated": False,
    })
    result = {
        "content": [{
            "type": "text",
            "text": raw_text if raw_text is not None else body,
        }],
        "isError": False,
    }
    if structured_content is not None:
        result["structuredContent"] = structured_content
    return (
        {"jsonrpc": "2.0", "id": 3, "result": result},
        sid,
    )


def _happy_scripted() -> ScriptedPost:
    return ScriptedPost([
        _init_resp(),
        _notif_resp(),
        _wiki_write_rejected_resp(),
        _wiki_read_ok_resp(),
    ])


# ---- happy path ------------------------------------------------------------


def test_happy_path_run_canary_no_raise():
    wc.run_canary("https://fake/mcp", 5.0, post_fn=_happy_scripted())


def test_happy_path_accepts_structured_content_previews():
    scripted = ScriptedPost([
        _init_resp(),
        _notif_resp(),
        _wiki_write_rejected_resp(
            raw_text="Tool result available in structuredContent.",
            structured_content={
                "status": "rejected",
                "error": "write_page: Anonymous writes are disabled.",
                "auth_required": True,
                "tool": "write_page",
            },
        ),
        _wiki_read_ok_resp(
            raw_text="Tool result available in structuredContent.",
            structured_content={
                "path": f"drafts/{wc._CANARY_CATEGORY}/{wc._CANARY_FILENAME}.md",
                "is_draft": True,
                "content": f"[DRAFT] {wc._CANARY_CONTENT}",
                "truncated": False,
            },
        ),
    ])
    wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)


def test_run_canary_can_scope_filename_for_bisect_replay():
    scripted = _happy_scripted()
    wc.run_canary(
        "https://fake/mcp",
        5.0,
        post_fn=scripted,
        canary_filename="uptime-probe-bisect-run1",
    )

    write_args = scripted.calls[2]["payload"]["params"]["arguments"]
    read_args = scripted.calls[3]["payload"]["params"]["arguments"]
    # Gate probe is scoped; read always targets the shared persisted draft
    # (scoped drafts are never persisted post-gate).
    assert write_args["filename"] == "uptime-probe-bisect-run1"
    assert read_args["page"] == wc._CANARY_FILENAME


def test_gate_probe_uses_canonical_write_page_and_read_page():
    scripted = _happy_scripted()
    wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert scripted.calls[2]["payload"]["params"]["name"] == "write_page"
    assert scripted.calls[3]["payload"]["params"]["name"] == "read_page"
    # Full-page write shape: must hit the gate, never the dry-run patch
    # preview passthrough (no old_text/new_text, no kind, dry_run False).
    write_args = scripted.calls[2]["payload"]["params"]["arguments"]
    assert write_args["dry_run"] is False
    assert "old_text" not in write_args and "kind" not in write_args


def test_probe_id_sanitizes_to_scoped_filename():
    assert wc._filename_for_probe_id("bisect run: 42") == "uptime-probe-bisect-run-42"


def test_happy_path_run_probe_returns_zero(tmp_path):
    with patch("wiki_canary._append_log"):
        rc = wc.run_probe("https://fake/mcp", 5.0, post_fn=_happy_scripted())
    assert rc == 0


def test_happy_path_log_line_contains_green(tmp_path):
    logged: list[str] = []
    with patch("wiki_canary._append_log", side_effect=logged.append):
        wc.run_probe("https://fake/mcp", 5.0, post_fn=_happy_scripted())
    assert logged, "Expected at least one log line"
    assert "GREEN" in logged[0]
    assert "surface=wiki_gate" in logged[0]


def test_happy_path_log_line_not_red(tmp_path):
    logged: list[str] = []
    with patch("wiki_canary._append_log", side_effect=logged.append):
        wc.run_probe("https://fake/mcp", 5.0, post_fn=_happy_scripted())
    assert all("RED" not in line for line in logged)


# ---- handshake failures (exit 2) ------------------------------------------


def test_exit_2_on_initialize_network_error():
    scripted = ScriptedPost([ToolCanaryError(2, "unreachable")])
    with pytest.raises(ToolCanaryError) as ei:
        wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 2


def test_exit_2_on_initialize_missing_result():
    scripted = ScriptedPost([({"jsonrpc": "2.0", "id": 1}, "sess")])
    with pytest.raises(ToolCanaryError) as ei:
        wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 2


def test_exit_2_on_no_session_id():
    scripted = ScriptedPost([
        ({"jsonrpc": "2.0", "id": 1, "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "x"},
        }}, None),
    ])
    with pytest.raises(ToolCanaryError) as ei:
        wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 2


# ---- write-gate probe failures (exit 6) ------------------------------------


def test_exit_6_when_anonymous_write_is_accepted_gate_regression():
    """An anonymous write_page that persists is a #1441 gate regression."""
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        _wiki_write_accepted_resp(),
    ])
    with pytest.raises(ToolCanaryError) as ei:
        wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 6
    assert "regressed" in ei.value.msg


def test_exit_6_when_rejection_lacks_auth_required():
    body = json.dumps({"status": "rejected", "error": "nope"})
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        ({"jsonrpc": "2.0", "id": 2, "result": {
            "content": [{"type": "text", "text": body}],
            "isError": False,
        }}, "sess-wiki"),
    ])
    with pytest.raises(ToolCanaryError) as ei:
        wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 6
    assert "auth_required" in ei.value.msg


def test_exit_6_on_wiki_write_network_error():
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        ToolCanaryError(6, "HTTP 503 on wiki write"),
    ])
    with pytest.raises(ToolCanaryError) as ei:
        wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 6


def test_exit_6_on_wiki_write_iserror():
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        ({"jsonrpc": "2.0", "id": 2, "result": {
            "content": [{"type": "text", "text": "disk full"}],
            "isError": True,
        }}, "sess-wiki"),
    ])
    with pytest.raises(ToolCanaryError) as ei:
        wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 6
    assert "isError" in ei.value.msg


def test_exit_6_on_wiki_write_unexpected_status():
    bad_body = json.dumps({"status": "conflict", "filename": wc._CANARY_FILENAME})
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        ({"jsonrpc": "2.0", "id": 2, "result": {
            "content": [{"type": "text", "text": bad_body}],
            "isError": False,
        }}, "sess-wiki"),
    ])
    with pytest.raises(ToolCanaryError) as ei:
        wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 6
    assert "status" in ei.value.msg


def test_exit_6_on_wiki_write_no_result():
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        ({"jsonrpc": "2.0", "id": 2}, "sess-wiki"),
    ])
    with pytest.raises(ToolCanaryError) as ei:
        wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 6


def test_exit_6_on_wiki_write_no_text_content():
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        ({"jsonrpc": "2.0", "id": 2, "result": {
            "content": [], "isError": False,
        }}, "sess-wiki"),
    ])
    with pytest.raises(ToolCanaryError) as ei:
        wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 6


def test_exit_6_on_wiki_write_non_json_text():
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        ({"jsonrpc": "2.0", "id": 2, "result": {
            "content": [{"type": "text", "text": "not json"}],
            "isError": False,
        }}, "sess-wiki"),
    ])
    with pytest.raises(ToolCanaryError) as ei:
        wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 6


# ---- wiki read failures (exit 7) ------------------------------------------


def test_exit_7_on_wiki_read_network_error():
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(), _wiki_write_rejected_resp(),
        ToolCanaryError(7, "HTTP 503 on wiki read"),
    ])
    with pytest.raises(ToolCanaryError) as ei:
        wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 7


def test_exit_7_on_wiki_read_iserror():
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(), _wiki_write_rejected_resp(),
        ({"jsonrpc": "2.0", "id": 3, "result": {
            "content": [{"type": "text", "text": "not found"}],
            "isError": True,
        }}, "sess-wiki"),
    ])
    with pytest.raises(ToolCanaryError) as ei:
        wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 7
    assert "isError" in ei.value.msg


def test_exit_7_on_wiki_read_roundtrip_mismatch():
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(), _wiki_write_rejected_resp(),
        ({"jsonrpc": "2.0", "id": 3, "result": {
            "content": [{"type": "text", "text": "wrong content entirely"}],
            "isError": False,
        }}, "sess-wiki"),
    ])
    with pytest.raises(ToolCanaryError) as ei:
        wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 7
    assert "mismatch" in ei.value.msg


def test_exit_7_on_wiki_read_no_result():
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(), _wiki_write_rejected_resp(),
        ({"jsonrpc": "2.0", "id": 3}, "sess-wiki"),
    ])
    with pytest.raises(ToolCanaryError) as ei:
        wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 7


def test_exit_7_on_wiki_read_no_text_content():
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(), _wiki_write_rejected_resp(),
        ({"jsonrpc": "2.0", "id": 3, "result": {
            "content": [], "isError": False,
        }}, "sess-wiki"),
    ])
    with pytest.raises(ToolCanaryError) as ei:
        wc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 7


# ---- run_probe log line surface tag ----------------------------------------


def test_red_log_line_contains_surface_wiki_gate_on_exit_6():
    logged: list[str] = []
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        ToolCanaryError(6, "disk full"),
    ])
    with patch("wiki_canary._append_log", side_effect=logged.append):
        rc = wc.run_probe("https://fake/mcp", 5.0, post_fn=scripted)
    assert rc == 6
    assert logged
    assert "surface=wiki_gate" in logged[0]
    assert "RED" in logged[0]


def test_red_log_line_contains_surface_wiki_gate_on_exit_7():
    logged: list[str] = []
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(), _wiki_write_rejected_resp(),
        ToolCanaryError(7, "roundtrip mismatch"),
    ])
    with patch("wiki_canary._append_log", side_effect=logged.append):
        rc = wc.run_probe("https://fake/mcp", 5.0, post_fn=scripted)
    assert rc == 7
    assert logged
    assert "surface=wiki_gate" in logged[0]


def test_exit_99_on_unexpected_exception():
    def _explode(url, sid, payload, timeout, *, step_code):
        raise RuntimeError("surprise")

    logged: list[str] = []
    with patch("wiki_canary._append_log", side_effect=logged.append):
        rc = wc.run_probe("https://fake/mcp", 5.0, post_fn=_explode)
    assert rc == 99
    assert logged
    assert "unexpected" in logged[0]


# ---- main() propagates exit codes ------------------------------------------


@pytest.mark.parametrize("responses, expected_rc", [
    # exit 2: handshake fails
    ([ToolCanaryError(2, "boom")], 2),
    # exit 6: wiki write fails
    ([_init_resp(), _notif_resp(), ToolCanaryError(6, "write fail")], 6),
    # exit 7: wiki read roundtrip mismatch
    ([
        _init_resp(), _notif_resp(), _wiki_write_rejected_resp(),
        ({"jsonrpc": "2.0", "id": 3, "result": {
            "content": [{"type": "text", "text": "wrong"}],
            "isError": False,
        }}, "sess-wiki"),
    ], 7),
    # exit 0: all pass
    ([_init_resp(), _notif_resp(), _wiki_write_rejected_resp(), _wiki_read_ok_resp()], 0),
])
def test_main_propagates_exit_codes(monkeypatch, responses, expected_rc):
    scripted = ScriptedPost(responses)
    # Patch _post inside wiki_canary (the name it was imported under) so
    # run_probe → run_canary picks up the scripted responses without recursion.
    monkeypatch.setattr(wc, "_post", scripted)
    with patch("wiki_canary._append_log"):
        rc = wc.main(["--url", "https://fake/mcp"])
    assert rc == expected_rc
