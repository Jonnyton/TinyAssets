"""Task #35 part B — inline permission-card dismiss.

Tests ``_dismiss_inline_permission_card`` gating + click behavior.
The detector runs ``page.evaluate`` on live Playwright state; we
fake the page with a tiny stub so the gate logic and notepad-log
wiring are unit-testable without a browser.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


@pytest.fixture
def chat_module(tmp_path, monkeypatch):
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    monkeypatch.syspath_prepend(str(scripts_dir))
    sys.modules.pop("claude_chat", None)
    module = importlib.import_module("claude_chat")
    module.NOTEPAD = tmp_path / "user_sim_session.md"
    return module


class _FakePage:
    """Minimal page stub — ``evaluate`` returns a scripted payload."""

    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    def evaluate(self, _script):
        self.calls += 1
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _notepad_text(module) -> str:
    path = Path(module.NOTEPAD)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def test_inline_dismiss_click_success_returns_1(chat_module):
    """Detector reports clicked=True → return 1 and log ok."""
    page = _FakePage({
        "found": True, "clicked": True, "label": "Always allow",
    })
    result = chat_module._dismiss_inline_permission_card(page)
    assert result == 1
    body = _notepad_text(chat_module)
    assert "SYSTEM DIALOG _dismiss_inline_permission_card" in body
    assert "auto-dismiss: ok" in body
    assert "Always allow" in body


def test_inline_dismiss_not_found_returns_0_no_log(chat_module):
    """No permission card on page → return 0, nothing logged."""
    page = _FakePage({"found": False, "reason": "no permission card text"})
    result = chat_module._dismiss_inline_permission_card(page)
    assert result == 0
    # Notepad untouched.
    assert _notepad_text(chat_module) == ""


def test_inline_dismiss_detected_but_click_failed_logs_failed(chat_module):
    """Found but click failed → return 0, log 'failed' so host sees it."""
    page = _FakePage({
        "found": True, "clicked": False, "label": "Always allow",
        "error": "node detached",
    })
    result = chat_module._dismiss_inline_permission_card(page)
    assert result == 0
    body = _notepad_text(chat_module)
    assert "auto-dismiss: failed" in body
    assert "Always allow" in body


def test_inline_dismiss_evaluate_raises_returns_0(chat_module):
    """page.evaluate raising is treated as a miss, never propagates."""
    page = _FakePage(RuntimeError("CDP dropped"))
    result = chat_module._dismiss_inline_permission_card(page)
    assert result == 0
    assert _notepad_text(chat_module) == ""


def test_inline_dismiss_empty_payload_returns_0(chat_module):
    """evaluate returning None/empty dict → treated as no-op."""
    page = _FakePage(None)
    assert chat_module._dismiss_inline_permission_card(page) == 0


def test_inline_dismiss_missing_label_falls_back_to_default(chat_module):
    """Missing label still logs a usable line (default 'Always allow')."""
    page = _FakePage({"found": True, "clicked": True})
    result = chat_module._dismiss_inline_permission_card(page)
    assert result == 1
    assert "Always allow" in _notepad_text(chat_module)


def test_inline_probe_script_gating_strings(chat_module):
    """The JS probe uses the exact gate strings team-lead specified —
    "Claude wants to use" AND a brand match (TinyAssets / TinyAssets Server /
    legacy Universe Server) AND a button whose text starts with "Always
    allow". Pin the contract."""
    probe = chat_module._INLINE_ALWAYS_ALLOW_PROBE
    assert "Claude wants to use" in probe
    # Brand gate covers the new "TinyAssets" connector name AND retains
    # the legacy "Universe Server" name so the probe still works for
    # connectors that haven't been reconnected yet.
    assert "TinyAssets" in probe
    assert "Universe Server" in probe
    # Case-insensitive exact-prefix match on Always allow.
    assert "^always allow" in probe.lower()
