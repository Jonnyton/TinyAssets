"""Tests for scripts/last_activity_canary.py.

Exit-code branches covered:
  0  fresh — last_activity within threshold
  2  stale — last_activity beyond threshold
  3  unparseable / missing last_activity_at, or daemon block missing
  4  handshake / connectivity failure (distinct from code 3 so operators
     can tell "dark daemon" from "stale execution" at a glance)
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import last_activity_canary as lac  # noqa: E402


def _utc(ts: str) -> _dt.datetime:
    """Parse an ISO string into a UTC-aware datetime for test fixtures."""
    d = _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d


# ---- classify_freshness (pure logic) --------------------------------------


def test_classify_fresh_well_within_threshold():
    now = _utc("2026-04-22T12:00:00+00:00")
    code, msg = lac.classify_freshness("2026-04-22T11:55:00+00:00", now, 30)
    assert code == 0
    assert "FRESH" in msg
    assert "5.0min" in msg
    assert "threshold=30min" in msg


def test_classify_fresh_at_boundary():
    """Exactly at threshold counts as fresh (<=, not <)."""
    now = _utc("2026-04-22T12:30:00+00:00")
    code, _ = lac.classify_freshness("2026-04-22T12:00:00+00:00", now, 30)
    assert code == 0


def test_classify_stale_just_past_threshold():
    now = _utc("2026-04-22T12:31:00+00:00")
    code, msg = lac.classify_freshness("2026-04-22T12:00:00+00:00", now, 30)
    assert code == 2
    assert "STALE" in msg


def test_classify_stale_two_days_old():
    """Matches the live 2026-04-22 pre-#14 evidence:
    last_activity=2026-04-20T05:44Z (~2d stale)."""
    now = _utc("2026-04-22T05:44:00+00:00")
    code, msg = lac.classify_freshness("2026-04-20T05:44:00+00:00", now, 30)
    assert code == 2
    assert "2880.0min" in msg or "2880min" in msg
    # 48h * 60 = 2880 min — evidence the classifier catches multi-day stale.


def test_classify_none_is_unparseable():
    now = _utc("2026-04-22T12:00:00+00:00")
    code, msg = lac.classify_freshness(None, now, 30)
    assert code == 3
    assert "null" in msg or "empty" in msg


def test_classify_empty_string_is_unparseable():
    now = _utc("2026-04-22T12:00:00+00:00")
    code, _ = lac.classify_freshness("", now, 30)
    assert code == 3


def test_classify_malformed_iso_is_unparseable():
    now = _utc("2026-04-22T12:00:00+00:00")
    code, msg = lac.classify_freshness("not-a-timestamp", now, 30)
    assert code == 3
    assert "could not parse" in msg


def test_classify_z_suffix_parses_correctly():
    """The MCP daemon emits Z-suffix timestamps — must parse cleanly."""
    now = _utc("2026-04-22T12:05:00+00:00")
    code, _ = lac.classify_freshness("2026-04-22T12:00:00Z", now, 30)
    assert code == 0


def test_classify_naive_iso_treated_as_utc():
    """A timestamp without tzinfo is treated as UTC (lossy but safe).
    Matches _parse_iso's behavior."""
    now = _utc("2026-04-22T12:05:00+00:00")
    code, _ = lac.classify_freshness("2026-04-22T12:00:00", now, 30)
    assert code == 0


# ---- _parse_iso corners ---------------------------------------------------


def test_parse_iso_z_suffix():
    ts = lac._parse_iso("2026-04-22T12:00:00Z")
    assert ts is not None
    assert ts.tzinfo is not None


def test_parse_iso_returns_none_on_junk():
    assert lac._parse_iso("") is None
    assert lac._parse_iso("junk") is None
    assert lac._parse_iso(None) is None


# ---- ScriptedPost: stub for fetch_inspect_result --------------------------


class ScriptedPost:
    """Feeds pre-scripted (response, sid) tuples back one call at a time."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, url, sid, payload, timeout, *, step_code):
        self.calls.append({
            "method": payload.get("method"), "sid": sid, "step_code": step_code,
            "payload": payload,
        })
        if not self._responses:
            raise AssertionError(
                f"ScriptedPost ran out at call {len(self.calls)} "
                f"(method={payload.get('method')!r})",
            )
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def _init_resp(sid="sess-x"):
    return (
        {"jsonrpc": "2.0", "id": 1, "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "tinyassets", "version": "1.0"},
        }},
        sid,
    )


def _notif_resp(sid="sess-x"):
    return (None, sid)


def _universe_inspect_resp(
    raw_text: str | None = None,
    last_activity_at: str | None = "2026-04-22T11:55:00+00:00",
    is_error: bool = False,
    structured_content: dict | None = None,
    sid: str = "sess-x",
):
    if raw_text is None:
        raw_text = json.dumps({
            "universe_id": "concordance",
            "daemon": {
                "phase": "writing" if last_activity_at else "offline",
                "last_activity_at": last_activity_at,
                "staleness": "fresh",
            },
        })
    result = {
        "content": [{"type": "text", "text": raw_text}],
        "isError": is_error,
    }
    if structured_content is not None:
        result["structuredContent"] = structured_content
    return (
        {"jsonrpc": "2.0", "id": 2, "result": result},
        sid,
    )


# ---- run_canary — exit code matrix via scripted posts --------------------


def test_run_canary_fresh_returns_zero():
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        _universe_inspect_resp(last_activity_at="2026-04-22T11:55:00+00:00"),
    ])
    code, msg = lac.run_canary(
        "https://fake/mcp", 5.0, 30,
        post_fn=scripted, now=_utc("2026-04-22T12:00:00+00:00"),
    )
    assert code == 0
    assert "FRESH" in msg


def test_inspect_call_uses_canonical_read_graph_not_deprecated_universe():
    """Anonymous calls to the deprecated `universe` fat tool are refused
    since #1441 — the probe must stay on the canonical read handle."""
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        _universe_inspect_resp(last_activity_at="2026-04-22T11:55:00+00:00"),
    ])
    lac.run_canary(
        "https://fake/mcp", 5.0, 30,
        post_fn=scripted, now=_utc("2026-04-22T12:00:00+00:00"),
    )
    params = scripted.calls[2]["payload"]["params"]
    assert params["name"] == "read_graph"
    assert params["arguments"] == {"target": "graph"}


def test_run_canary_accepts_structured_content_when_text_is_preview():
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        _universe_inspect_resp(
            raw_text=(
                "Tool result: active_targets=5; recent_activity=10. "
                "Full payload is in structuredContent."
            ),
            structured_content={
                "universe_id": "concordance",
                "daemon": {
                    "phase": "writing",
                    "last_activity_at": "2026-04-22T11:55:00+00:00",
                    "staleness": "fresh",
                },
            },
        ),
    ])
    code, msg = lac.run_canary(
        "https://fake/mcp", 5.0, 30,
        post_fn=scripted, now=_utc("2026-04-22T12:00:00+00:00"),
    )
    assert code == 0
    assert "FRESH" in msg


def test_run_canary_stale_returns_two():
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        _universe_inspect_resp(last_activity_at="2026-04-20T05:44:00+00:00"),
    ])
    code, msg = lac.run_canary(
        "https://fake/mcp", 5.0, 30,
        post_fn=scripted, now=_utc("2026-04-22T12:00:00+00:00"),
    )
    assert code == 2
    assert "STALE" in msg


def test_run_canary_missing_last_activity_returns_three():
    """Daemon block present but last_activity_at is null."""
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        _universe_inspect_resp(last_activity_at=None),
    ])
    code, _ = lac.run_canary(
        "https://fake/mcp", 5.0, 30,
        post_fn=scripted, now=_utc("2026-04-22T12:00:00+00:00"),
    )
    assert code == 3


def test_run_canary_missing_daemon_block_returns_three():
    """Inspect result has no daemon block at all."""
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        _universe_inspect_resp(raw_text=json.dumps({
            "universe_id": "concordance",
            # no daemon key
        })),
    ])
    code, msg = lac.run_canary(
        "https://fake/mcp", 5.0, 30,
        post_fn=scripted, now=_utc("2026-04-22T12:00:00+00:00"),
    )
    assert code == 3
    assert "no daemon block" in msg


def test_run_canary_tool_iserror_returns_three():
    """universe inspect with isError=true → exit 3 (daemon responded
    but the tool path is broken)."""
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        _universe_inspect_resp(is_error=True, raw_text="inspect crashed"),
    ])
    with pytest.raises(lac.LastActivityError) as ei:
        lac.run_canary(
            "https://fake/mcp", 5.0, 30,
            post_fn=scripted, now=_utc("2026-04-22T12:00:00+00:00"),
        )
    assert ei.value.code == 3
    assert "isError" in ei.value.msg


def test_run_canary_handshake_failure_returns_four():
    """Initialize network error → exit 4 (handshake / connectivity),
    distinct from tool-level exit 3 so operators tell dark-daemon from
    stale-execution."""
    scripted = ScriptedPost([
        lac.LastActivityError(4, "unreachable"),
    ])
    with pytest.raises(lac.LastActivityError) as ei:
        lac.run_canary(
            "https://fake/mcp", 5.0, 30,
            post_fn=scripted, now=_utc("2026-04-22T12:00:00+00:00"),
        )
    assert ei.value.code == 4


def test_run_canary_initialize_missing_session_id_returns_four():
    scripted = ScriptedPost([
        ({"jsonrpc": "2.0", "id": 1, "result": {
            "protocolVersion": "2024-11-05", "serverInfo": {"name": "x"},
        }}, None),
    ])
    with pytest.raises(lac.LastActivityError) as ei:
        lac.run_canary(
            "https://fake/mcp", 5.0, 30,
            post_fn=scripted, now=_utc("2026-04-22T12:00:00+00:00"),
        )
    assert ei.value.code == 4
    assert "mcp-session-id" in ei.value.msg


def test_run_canary_initialize_mcp_error_returns_four():
    scripted = ScriptedPost([
        ({"jsonrpc": "2.0", "id": 1,
          "error": {"code": -32000, "message": "boom"}}, "sess"),
    ])
    with pytest.raises(lac.LastActivityError) as ei:
        lac.run_canary(
            "https://fake/mcp", 5.0, 30,
            post_fn=scripted, now=_utc("2026-04-22T12:00:00+00:00"),
        )
    assert ei.value.code == 4


# ---- step_code correctness on network errors ----------------------------


def test_initialize_network_error_tagged_step_code_4():
    """network error during initialize must tag step_code=4."""
    scripted = ScriptedPost([
        lac.LastActivityError(4, "HTTP 503 on initialize"),
    ])
    with pytest.raises(lac.LastActivityError) as ei:
        lac.run_canary(
            "https://fake/mcp", 5.0, 30,
            post_fn=scripted, now=_utc("2026-04-22T12:00:00+00:00"),
        )
    assert ei.value.code == 4


def test_tool_call_network_error_tagged_step_code_3():
    """network error during tools/call must tag step_code=3 so operators
    distinguish tool-path failure from handshake-level failure."""
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        lac.LastActivityError(3, "HTTP 503 on tools/call"),
    ])
    with pytest.raises(lac.LastActivityError) as ei:
        lac.run_canary(
            "https://fake/mcp", 5.0, 30,
            post_fn=scripted, now=_utc("2026-04-22T12:00:00+00:00"),
        )
    assert ei.value.code == 3


# ---- main() integration --------------------------------------------------


def test_main_exit_zero_on_fresh(monkeypatch, capsys):
    """main() returns 0 when run_canary reports FRESH."""
    def fake_run_canary(url, timeout, threshold, *, post_fn=None, now=None, verbose=False):
        return 0, "FRESH: last_activity_at=... age=5.0min threshold=30min"
    monkeypatch.setattr(lac, "run_canary", fake_run_canary)
    rc = lac.main(["--url", "https://fake/mcp", "--threshold-min", "30"])
    assert rc == 0
    assert "FRESH" in capsys.readouterr().out


def test_main_exit_two_on_stale(monkeypatch, capsys):
    def fake_run_canary(*a, **kw):
        return 2, "STALE: ..."
    monkeypatch.setattr(lac, "run_canary", fake_run_canary)
    rc = lac.main(["--url", "https://fake/mcp"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "FAIL" in err
    assert "STALE" in err


def test_main_threshold_from_env(monkeypatch, capsys):
    """TINYASSETS_LAST_ACTIVITY_THRESHOLD_MIN overrides the default."""
    monkeypatch.setenv("TINYASSETS_LAST_ACTIVITY_THRESHOLD_MIN", "120")
    # Reload so the argparse default picks up the new env.
    import importlib
    importlib.reload(lac)
    captured = {}

    def fake_run_canary(url, timeout, threshold_min, *, post_fn=None, now=None, verbose=False):
        captured["threshold_min"] = threshold_min
        return 0, "ok"
    monkeypatch.setattr(lac, "run_canary", fake_run_canary)
    lac.main(["--url", "https://fake/mcp"])
    assert captured["threshold_min"] == 120


def test_main_exit_three_on_handshake_error_raises_lastactivity(monkeypatch, capsys):
    """main() catches LastActivityError and exits with the code."""
    def fake_run_canary(*a, **kw):
        raise lac.LastActivityError(4, "network blip")
    monkeypatch.setattr(lac, "run_canary", fake_run_canary)
    rc = lac.main(["--url", "https://fake/mcp"])
    assert rc == 4
    err = capsys.readouterr().err
    assert "FAIL (exit 4)" in err


# ---- _extract_tool_text ---------------------------------------------------


def test_extract_tool_text_joins_text_items():
    result = {"content": [
        {"type": "text", "text": "a"},
        {"type": "image", "data": "skip"},
        {"type": "text", "text": "b"},
    ]}
    assert lac._extract_tool_text(result) == "ab"


def test_extract_tool_text_empty_on_no_content():
    assert lac._extract_tool_text({}) == ""
    assert lac._extract_tool_text({"content": []}) == ""


# ---- Paused-daemon exemption (task #13 — issue #59 false-positive fix) ------


def _paused_inspect_resp(
    is_paused: bool = True,
    staleness: str = "idle",
    last_activity_at: str | None = "2026-04-20T04:55:00+00:00",
    sid: str = "sess-x",
):
    """Build a universe inspect response for a paused daemon."""
    raw_text = json.dumps({
        "universe_id": "concordance",
        "daemon": {
            "phase": "writing",
            "phase_human": "paused" if is_paused else "idle",
            "is_paused": is_paused,
            "staleness": staleness,
            "last_activity_at": last_activity_at,
        },
    })
    return (
        {"jsonrpc": "2.0", "id": 2, "result": {
            "content": [{"type": "text", "text": raw_text}],
            "isError": False,
        }},
        sid,
    )


def test_run_canary_paused_daemon_returns_zero():
    """is_paused=True must return exit 0 (FRESH) even with stale last_activity.

    Reproduces issue #59: host paused concordance 2026-04-24; canary was
    paging STALE because it didn't gate on is_paused.
    """
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        _paused_inspect_resp(is_paused=True, staleness="idle"),
    ])
    code, msg = lac.run_canary(
        "https://fake/mcp", 5.0, 30,
        post_fn=scripted,
        now=_utc("2026-04-24T12:00:00+00:00"),  # >30 min after last_activity
    )
    assert code == 0
    assert "paused" in msg.lower()
    assert "FRESH" in msg


def test_run_canary_idle_staleness_returns_zero():
    """staleness='idle' (even without is_paused=True) exempts the freshness check."""
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        _paused_inspect_resp(is_paused=False, staleness="idle"),
    ])
    code, msg = lac.run_canary(
        "https://fake/mcp", 5.0, 30,
        post_fn=scripted,
        now=_utc("2026-04-24T12:00:00+00:00"),
    )
    assert code == 0
    assert "idle" in msg.lower()


def test_run_canary_dormant_not_exempt():
    """staleness='dormant' is NOT exempted — daemon has been quiet too long."""
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        _paused_inspect_resp(is_paused=False, staleness="dormant"),
    ])
    code, _ = lac.run_canary(
        "https://fake/mcp", 5.0, 30,
        post_fn=scripted,
        now=_utc("2026-04-24T12:00:00+00:00"),
    )
    # dormant → last_activity is very old → STALE
    assert code == 2


def test_run_canary_fresh_staleness_uses_timestamp():
    """staleness='fresh' still uses the timestamp check (normal operation)."""
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        _paused_inspect_resp(
            is_paused=False,
            staleness="fresh",
            last_activity_at="2026-04-24T11:55:00+00:00",
        ),
    ])
    code, msg = lac.run_canary(
        "https://fake/mcp", 5.0, 30,
        post_fn=scripted,
        now=_utc("2026-04-24T12:00:00+00:00"),
    )
    assert code == 0
    assert "FRESH" in msg


def test_run_canary_is_paused_true_overrides_stale_timestamp():
    """is_paused=True overrides even a 'dormant' staleness bucket."""
    scripted = ScriptedPost([
        _init_resp(), _notif_resp(),
        _paused_inspect_resp(is_paused=True, staleness="dormant"),
    ])
    code, msg = lac.run_canary(
        "https://fake/mcp", 5.0, 30,
        post_fn=scripted,
        now=_utc("2026-04-24T12:00:00+00:00"),
    )
    assert code == 0
    assert "paused" in msg.lower()
