"""Tests for scripts/mcp_tool_canary.py.

Exercises each exit-code branch (0/2/3/4/5) with a scripted post_fn that
feeds stage-by-stage responses, so no network is touched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import mcp_tool_canary as tc  # noqa: E402

# ---- helpers --------------------------------------------------------------


def _init_resp(sid: str = "sess-123") -> tuple[dict, str]:
    return (
        {"jsonrpc": "2.0", "id": 1, "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "workflow", "version": "1.0"},
            "capabilities": {},
        }},
        sid,
    )


def _initialized_notif_resp(sid: str = "sess-123") -> tuple[None, str]:
    # notifications/initialized has no response body typically.
    return (None, sid)


def _tools_list_resp(
    tools: list[dict] | None = None, sid: str = "sess-123",
) -> tuple[dict, str]:
    if tools is None:
        tools = [
            {"name": "universe", "description": "..."},
            {"name": "get_status", "description": "..."},
        ]
    return (
        {"jsonrpc": "2.0", "id": 2, "result": {"tools": tools}},
        sid,
    )


def _universe_inspect_resp(
    universe_id: str = "demo-universe",
    is_error: bool = False,
    raw_text: str | None = None,
    structured_content: dict | None = None,
    sid: str = "sess-123",
) -> tuple[dict, str]:
    if raw_text is None:
        raw_text = json.dumps({
            "universe_id": universe_id,
            "daemon": {"phase": "idle"},
        })
    result = {
        "content": [{"type": "text", "text": raw_text}],
        "isError": is_error,
    }
    if structured_content is not None:
        result["structuredContent"] = structured_content
    return (
        {"jsonrpc": "2.0", "id": 3, "result": result},
        sid,
    )


def _workflow_status_resp(
    schema_version: int = 1,
    is_error: bool = False,
    raw_text: str | None = None,
    structured_content: dict | None = None,
    sid: str = "sess-123",
) -> tuple[dict, str]:
    if raw_text is None:
        raw_text = json.dumps({
            "schema_version": schema_version,
            "universe_id": "demo-universe",
            "active_host": {"host_id": "host"},
        })
    result = {
        "content": [{"type": "text", "text": raw_text}],
        "isError": is_error,
    }
    if structured_content is not None:
        result["structuredContent"] = structured_content
    return (
        {"jsonrpc": "2.0", "id": 3, "result": result},
        sid,
    )


class ScriptedPost:
    """Feeds pre-scripted (response, sid) tuples back one call at a time.

    If a tuple is an Exception, raises it instead (to simulate HTTP/network
    failures at any step).
    """

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, url, sid, payload, timeout, *, step_code):
        self.calls.append({
            "url": url, "sid": sid, "method": payload.get("method"),
            "step_code": step_code, "payload": payload,
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


# ---- happy path -----------------------------------------------------------


def test_happy_path_returns_inspect_dict():
    scripted = ScriptedPost([
        _init_resp(),
        _initialized_notif_resp(),
        _tools_list_resp(),
        _universe_inspect_resp(universe_id="my-uni"),
    ])
    result = tc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert result["universe_id"] == "my-uni"
    # Verify each call was tagged with the right step_code.
    assert scripted.calls[0]["step_code"] == 2  # initialize
    assert scripted.calls[1]["step_code"] == 3  # notifications/initialized
    assert scripted.calls[2]["step_code"] == 4  # tools/list
    assert scripted.calls[3]["step_code"] == 5  # tools/call


def test_happy_path_accepts_structured_content_when_text_is_preview():
    scripted = ScriptedPost([
        _init_resp(),
        _initialized_notif_resp(),
        _tools_list_resp(),
        _universe_inspect_resp(
            raw_text=(
                "Tool result: active_targets=5; recent_activity=10. "
                "Full payload is in structuredContent."
            ),
            structured_content={
                "universe_id": "structured-uni",
                "daemon": {"phase": "idle"},
            },
        ),
    ])
    result = tc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert result["universe_id"] == "structured-uni"


def test_directory_tool_set_uses_workflow_status_probe():
    scripted = ScriptedPost([
        _init_resp(),
        _initialized_notif_resp(),
        _tools_list_resp(tools=[
            {"name": "read_graph", "description": "..."},
            {"name": "read_page", "description": "..."},
        ]),
        _workflow_status_resp(schema_version=1),
    ])
    result = tc.run_canary("https://fake/mcp-directory", 5.0, post_fn=scripted)
    assert result["schema_version"] == 1
    assert result["universe_id"] == "demo-universe"
    assert scripted.calls[3]["payload"]["params"] == {
        "name": "read_graph",
        "arguments": {"target": "status"},
    }


def test_directory_probe_accepts_nested_structured_content_result():
    scripted = ScriptedPost([
        _init_resp(),
        _initialized_notif_resp(),
        _tools_list_resp(tools=[
            {"name": "read_graph", "description": "..."},
        ]),
        _workflow_status_resp(
            raw_text="Tool result available in structuredContent.",
            structured_content={
                "result": {
                    "schema_version": 1,
                    "universe_id": "directory-uni",
                },
            },
        ),
    ])
    result = tc.run_canary("https://fake/mcp-directory", 5.0, post_fn=scripted)
    assert result["schema_version"] == 1
    assert result["universe_id"] == "directory-uni"


def test_main_exit_zero_on_happy_path(monkeypatch, capsys):
    scripted = ScriptedPost([
        _init_resp(), _initialized_notif_resp(),
        _tools_list_resp(), _universe_inspect_resp(),
    ])
    monkeypatch.setattr(tc, "_post", scripted)
    rc = tc.main(["--url", "https://fake/mcp", "--verbose"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "PASS" in out


# ---- exit 2 — handshake failures -----------------------------------------


def test_exit_2_on_network_error_at_initialize():
    scripted = ScriptedPost([
        tc.ToolCanaryError(2, "unreachable"),
    ])
    with pytest.raises(tc.ToolCanaryError) as ei:
        tc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 2


def test_exit_2_on_initialize_mcp_error():
    scripted = ScriptedPost([
        ({"jsonrpc": "2.0", "id": 1,
          "error": {"code": -32000, "message": "boom"}}, "sess"),
    ])
    with pytest.raises(tc.ToolCanaryError) as ei:
        tc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 2
    assert "initialize" in ei.value.msg.lower()


def test_exit_2_on_initialize_missing_result():
    scripted = ScriptedPost([
        ({"jsonrpc": "2.0", "id": 1}, "sess"),  # no result, no error
    ])
    with pytest.raises(tc.ToolCanaryError) as ei:
        tc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 2


# ---- exit 3 — session failures -------------------------------------------


def test_exit_3_when_no_session_id_header():
    scripted = ScriptedPost([
        ({"jsonrpc": "2.0", "id": 1, "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "x"},
        }}, None),
    ])
    with pytest.raises(tc.ToolCanaryError) as ei:
        tc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 3
    assert "mcp-session-id" in ei.value.msg


def test_exit_3_on_notifications_initialized_network_error():
    scripted = ScriptedPost([
        _init_resp(),
        tc.ToolCanaryError(3, "network blip on notif"),
    ])
    with pytest.raises(tc.ToolCanaryError) as ei:
        tc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 3


# ---- exit 4 — tools/list failures ----------------------------------------


def test_exit_4_when_tools_list_returns_empty():
    scripted = ScriptedPost([
        _init_resp(), _initialized_notif_resp(),
        _tools_list_resp(tools=[]),
    ])
    with pytest.raises(tc.ToolCanaryError) as ei:
        tc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 4
    assert "empty" in ei.value.msg.lower() or "non-list" in ei.value.msg.lower()


def test_exit_4_when_tools_list_has_no_result():
    scripted = ScriptedPost([
        _init_resp(), _initialized_notif_resp(),
        ({"jsonrpc": "2.0", "id": 2}, "sess-123"),
    ])
    with pytest.raises(tc.ToolCanaryError) as ei:
        tc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 4


def test_exit_4_on_tools_list_network_error():
    scripted = ScriptedPost([
        _init_resp(), _initialized_notif_resp(),
        tc.ToolCanaryError(4, "HTTP 503 on tools/list"),
    ])
    with pytest.raises(tc.ToolCanaryError) as ei:
        tc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 4


# ---- exit 5 — tools/call failures ----------------------------------------


def test_exit_5_when_universe_inspect_iserror():
    scripted = ScriptedPost([
        _init_resp(), _initialized_notif_resp(), _tools_list_resp(),
        _universe_inspect_resp(is_error=True, raw_text="tool crashed inside"),
    ])
    with pytest.raises(tc.ToolCanaryError) as ei:
        tc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 5
    assert "isError" in ei.value.msg


def test_exit_5_when_universe_inspect_missing_universe_id():
    scripted = ScriptedPost([
        _init_resp(), _initialized_notif_resp(), _tools_list_resp(),
        _universe_inspect_resp(raw_text=json.dumps({"daemon": {"phase": "idle"}})),
    ])
    with pytest.raises(tc.ToolCanaryError) as ei:
        tc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 5
    assert "universe_id" in ei.value.msg


def test_exit_5_when_universe_inspect_text_not_json():
    scripted = ScriptedPost([
        _init_resp(), _initialized_notif_resp(), _tools_list_resp(),
        _universe_inspect_resp(raw_text="not json at all"),
    ])
    with pytest.raises(tc.ToolCanaryError) as ei:
        tc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 5


def test_exit_5_when_universe_inspect_no_text_content():
    scripted = ScriptedPost([
        _init_resp(), _initialized_notif_resp(), _tools_list_resp(),
        ({"jsonrpc": "2.0", "id": 3, "result": {"content": [], "isError": False}},
         "sess-123"),
    ])
    with pytest.raises(tc.ToolCanaryError) as ei:
        tc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 5


def test_exit_5_on_universe_inspect_network_error():
    scripted = ScriptedPost([
        _init_resp(), _initialized_notif_resp(), _tools_list_resp(),
        tc.ToolCanaryError(5, "HTTP 500 on tools/call"),
    ])
    with pytest.raises(tc.ToolCanaryError) as ei:
        tc.run_canary("https://fake/mcp", 5.0, post_fn=scripted)
    assert ei.value.code == 5


def test_exit_5_when_no_supported_probe_tool_advertised():
    scripted = ScriptedPost([
        _init_resp(),
        _initialized_notif_resp(),
        _tools_list_resp(tools=[
            {"name": "read_page", "description": "..."},
        ]),
    ])
    with pytest.raises(tc.ToolCanaryError) as ei:
        tc.run_canary("https://fake/mcp-directory", 5.0, post_fn=scripted)
    assert ei.value.code == 5
    assert "supported read-only probe" in ei.value.msg


def test_exit_5_when_workflow_status_missing_schema_version():
    scripted = ScriptedPost([
        _init_resp(),
        _initialized_notif_resp(),
        _tools_list_resp(tools=[{"name": "read_graph"}]),
        _workflow_status_resp(raw_text=json.dumps({"universe_id": "demo"})),
    ])
    with pytest.raises(tc.ToolCanaryError) as ei:
        tc.run_canary("https://fake/mcp-directory", 5.0, post_fn=scripted)
    assert ei.value.code == 5
    assert "schema_version" in ei.value.msg


# ---- main() exit-code propagation ----------------------------------------


@pytest.mark.parametrize("scripted_responses, expected_code", [
    # exit 2: handshake fails
    ([tc.ToolCanaryError(2, "boom")], 2),
    # exit 3: no session id
    ([({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "x",
                                              "serverInfo": {"name": "n"}}},
        None)], 3),
    # exit 4: tools/list empty
    ([_init_resp(), _initialized_notif_resp(), _tools_list_resp(tools=[])], 4),
    # exit 5: universe inspect missing id
    ([_init_resp(), _initialized_notif_resp(), _tools_list_resp(),
      _universe_inspect_resp(raw_text=json.dumps({}))], 5),
])
def test_main_propagates_failure_codes(monkeypatch, scripted_responses, expected_code):
    scripted = ScriptedPost(scripted_responses)
    monkeypatch.setattr(tc, "_post", scripted)
    rc = tc.main(["--url", "https://fake/mcp"])
    assert rc == expected_code


# ---- _extract_tool_text helper -------------------------------------------


def test_extract_tool_text_concatenates_text_items():
    result = {"content": [
        {"type": "text", "text": "hello "},
        {"type": "image", "data": "ignored"},
        {"type": "text", "text": "world"},
    ]}
    assert tc._extract_tool_text(result) == "hello world"


def test_extract_tool_text_empty_on_no_text():
    assert tc._extract_tool_text({"content": []}) == ""
    assert tc._extract_tool_text({}) == ""
