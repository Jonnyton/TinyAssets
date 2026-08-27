"""The Stop hook that refuses to end a turn while dispatched work is running.

A hook that cannot go red is decor, and a hook that can wedge a session is
worse than the reflex it corrects. These pin both halves: it must fire on the
case it exists for, and it must fail open on every path that could trap a
session -- malformed payload, unreadable process list, already-continuing turn,
and past its own cap.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "keep_working_while_waiting.py"


def _load():
    spec = importlib.util.spec_from_file_location("keep_working_while_waiting", _HOOK)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def hook():
    return _load()


def _run(hook, monkeypatch, capsys, tmp_path, *, payload, commands):
    monkeypatch.setattr(hook, "_running_commands", lambda: commands)
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps(payload)))
    assert hook.main() == 0
    out = capsys.readouterr().out.strip()
    return json.loads(out) if out else None


class _Stdin:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text


_RUNNING = ["python scripts/peer_agent.py codex --out output/review.md --cwd ."]


def test_it_blocks_while_a_dispatched_job_is_running(hook, monkeypatch, capsys, tmp_path):
    """The whole point: a running peer dispatch is not a reason to stop."""
    got = _run(hook, monkeypatch, capsys, tmp_path,
               payload={"cwd": str(tmp_path), "session_id": "s1"}, commands=_RUNNING)
    assert got is not None
    assert got["decision"] == "block"
    # The reason must name WHAT is running -- "keep working" with no referent
    # is the kind of nag that gets a hook deleted.
    assert "output/review.md" in got["reason"]


def test_it_is_silent_when_nothing_is_running(hook, monkeypatch, capsys, tmp_path):
    got = _run(hook, monkeypatch, capsys, tmp_path,
               payload={"cwd": str(tmp_path), "session_id": "s2"},
               commands=["python -m pytest tests/"])
    assert got is None


def test_it_never_chains_on_itself(hook, monkeypatch, capsys, tmp_path):
    """stop_hook_active means the turn is ALREADY continuing because of a hook.

    Without this the hook re-blocks its own continuation forever.
    """
    got = _run(hook, monkeypatch, capsys, tmp_path,
               payload={"cwd": str(tmp_path), "session_id": "s3", "stop_hook_active": True},
               commands=_RUNNING)
    assert got is None


def test_it_stops_after_the_cap(hook, monkeypatch, capsys, tmp_path):
    """A hook that can nag forever is the ratchet it exists to prevent."""
    payload = {"cwd": str(tmp_path), "session_id": "s4"}
    decisions = [
        _run(hook, monkeypatch, capsys, tmp_path, payload=payload, commands=_RUNNING)
        for _ in range(hook._MAX_BLOCKS + 2)
    ]
    assert all(d is not None for d in decisions[: hook._MAX_BLOCKS])
    assert all(d is None for d in decisions[hook._MAX_BLOCKS :])
    state = tmp_path / ".agents" / "supervisor" / "keep-working-s4.json"
    assert json.loads(state.read_text(encoding="utf-8"))["blocks"] == hook._MAX_BLOCKS


def test_a_malformed_payload_fails_open(hook, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", _Stdin("not json at all"))
    assert hook.main() == 0
    assert capsys.readouterr().out.strip() == ""


def test_an_unreadable_process_list_fails_open(hook, monkeypatch, capsys, tmp_path):
    """No evidence is not evidence of work. Never block on a failed probe."""
    got = _run(hook, monkeypatch, capsys, tmp_path,
               payload={"cwd": str(tmp_path), "session_id": "s5"}, commands=[])
    assert got is None


def test_a_session_id_with_path_characters_cannot_escape_the_state_dir(
    hook, monkeypatch, capsys, tmp_path
):
    """The session id reaches a filename. Keep it inside the state directory."""
    _run(hook, monkeypatch, capsys, tmp_path,
         payload={"cwd": str(tmp_path), "session_id": "../../evil/x"}, commands=_RUNNING)
    written = list((tmp_path / ".agents" / "supervisor").glob("keep-working-*.json"))
    assert len(written) == 1
    assert written[0].parent == tmp_path / ".agents" / "supervisor"
    assert not (tmp_path.parent / "evil").exists()
