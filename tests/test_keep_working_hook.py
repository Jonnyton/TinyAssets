"""The Stop hook that refuses to end a turn on an outstanding dispatch.

A hook that cannot go red is decor; a hook that can wedge a session is worse
than the reflex it corrects. These pin both halves — it must fire on each of
the three states it exists for, and it must fail open on every path that could
trap a session.

The three states are not cosmetic. The first version of this hook watched only
for a running process, and would still have missed the case that prompted it:
a turn ending with a review that had already finished, unread.
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


class _Stdin:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> str:
        return self._text


def _ledger(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "ledger.jsonl"
    path.write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    return path


def _run(hook, monkeypatch, capsys, tmp_path, *, payload, ledger):
    monkeypatch.setattr(hook, "_ledger_path", lambda _p: ledger)
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps(payload)))
    assert hook.main() == 0
    out = capsys.readouterr().out.strip()
    return json.loads(out) if out else None


# --- the three states -------------------------------------------------------


def test_running_dispatch_blocks_and_says_take_another_lane(hook, tmp_path):
    rows = [{"event": "started", "out": "review.md", "pid": 1, "at": 1000.0}]
    got = hook.outstanding(rows, now=1010.0)
    assert got == [("running", "review.md")]


def test_finished_with_a_result_is_ready_not_running(hook, tmp_path):
    """The case that prompted the hook: a verdict sitting unread."""
    result = tmp_path / "review.md"
    result.write_text("VERDICT: ADAPT", encoding="utf-8")
    rows = [
        {"event": "started", "out": str(result), "pid": 1, "at": 1000.0},
        {"event": "finished", "out": str(result), "pid": 1, "at": 1050.0, "code": 0},
    ]
    assert hook.outstanding(rows, now=1060.0) == [("ready", str(result))]


def test_finished_with_no_result_file_is_vanished(hook, tmp_path):
    """peer_agent closes its row in a `finally`, so this means it died."""
    rows = [
        {"event": "started", "out": str(tmp_path / "gone.md"), "pid": 2, "at": 1000.0},
        {"event": "finished", "out": str(tmp_path / "gone.md"), "pid": 2, "at": 1001.0,
         "code": 2},
    ]
    assert hook.outstanding(rows, now=1010.0) == [("vanished", str(tmp_path / "gone.md"))]


def test_an_open_row_old_enough_is_vanished_not_running_forever(hook):
    """A killed process never writes its finish row. Do not wait on it forever."""
    rows = [{"event": "started", "out": "x.md", "pid": 3, "at": 0.0}]
    assert hook.outstanding(rows, now=hook._STALE_AFTER_S + 1.0) == [("vanished", "x.md")]


# --- hook behaviour ---------------------------------------------------------


def test_it_blocks_and_names_what_is_outstanding(hook, monkeypatch, capsys, tmp_path):
    ledger = _ledger(tmp_path, [
        {"event": "started", "out": "output/review.md", "pid": 1, "at": 1e9},
    ])
    got = _run(hook, monkeypatch, capsys, tmp_path,
               payload={"cwd": str(tmp_path), "session_id": "s1"}, ledger=ledger)
    assert got is not None and got["decision"] == "block"
    # "keep working" with no referent is the kind of nag that gets a hook deleted.
    assert "output/review.md" in got["reason"]


def test_each_item_is_surfaced_only_once(hook, monkeypatch, capsys, tmp_path):
    """Being told about the same verdict every turn is the pattern this breaks."""
    ledger = _ledger(tmp_path, [
        {"event": "started", "out": "output/review.md", "pid": 1, "at": 1e9},
    ])
    payload = {"cwd": str(tmp_path), "session_id": "s2"}
    first = _run(hook, monkeypatch, capsys, tmp_path, payload=payload, ledger=ledger)
    second = _run(hook, monkeypatch, capsys, tmp_path, payload=payload, ledger=ledger)
    assert first is not None
    assert second is None


def test_a_new_state_for_the_same_job_is_surfaced_again(
    hook, monkeypatch, capsys, tmp_path
):
    """running -> ready is new information, not a repeat."""
    result = tmp_path / "review.md"
    payload = {"cwd": str(tmp_path), "session_id": "s3"}
    running = _ledger(tmp_path, [
        {"event": "started", "out": str(result), "pid": 1, "at": 1e9},
    ])
    assert _run(hook, monkeypatch, capsys, tmp_path, payload=payload, ledger=running)

    result.write_text("VERDICT: APPROVE", encoding="utf-8")
    done = tmp_path / "l2.jsonl"
    done.write_text(
        json.dumps({"event": "started", "out": str(result), "pid": 1, "at": 1e9}) + "\n"
        + json.dumps({"event": "finished", "out": str(result), "pid": 1,
                      "at": 1e9 + 5, "code": 0}) + "\n",
        encoding="utf-8",
    )
    assert _run(hook, monkeypatch, capsys, tmp_path, payload=payload, ledger=done)


def test_it_never_chains_on_itself(hook, monkeypatch, capsys, tmp_path):
    ledger = _ledger(tmp_path, [
        {"event": "started", "out": "output/review.md", "pid": 1, "at": 1e9},
    ])
    got = _run(hook, monkeypatch, capsys, tmp_path,
               payload={"cwd": str(tmp_path), "session_id": "s4",
                        "stop_hook_active": True}, ledger=ledger)
    assert got is None


def test_it_stops_after_the_cap(hook, monkeypatch, capsys, tmp_path):
    """A hook that can nag forever is the ratchet it exists to prevent."""
    payload = {"cwd": str(tmp_path), "session_id": "s5"}
    seen = []
    for i in range(hook._MAX_BLOCKS + 2):
        ledger = _ledger(tmp_path, [
            {"event": "started", "out": f"output/r{i}.md", "pid": i, "at": 1e9 + i},
        ])
        seen.append(_run(hook, monkeypatch, capsys, tmp_path,
                         payload=payload, ledger=ledger))
    assert all(d is not None for d in seen[: hook._MAX_BLOCKS])
    assert all(d is None for d in seen[hook._MAX_BLOCKS :])


# --- fail-open paths --------------------------------------------------------


def test_a_malformed_payload_fails_open(hook, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", _Stdin("not json at all"))
    assert hook.main() == 0
    assert capsys.readouterr().out.strip() == ""


def test_a_missing_ledger_fails_open(hook, monkeypatch, capsys, tmp_path):
    got = _run(hook, monkeypatch, capsys, tmp_path,
               payload={"cwd": str(tmp_path), "session_id": "s6"},
               ledger=tmp_path / "absent.jsonl")
    assert got is None


def test_a_corrupt_ledger_line_is_skipped_not_fatal(hook, monkeypatch, capsys, tmp_path):
    path = tmp_path / "l.jsonl"
    path.write_text(
        "{not json\n"
        + json.dumps({"event": "started", "out": "output/r.md", "pid": 1, "at": 1e9})
        + "\n",
        encoding="utf-8",
    )
    got = _run(hook, monkeypatch, capsys, tmp_path,
               payload={"cwd": str(tmp_path), "session_id": "s7"}, ledger=path)
    assert got is not None
    assert "output/r.md" in got["reason"]


def test_a_session_id_with_path_characters_cannot_escape_the_state_dir(
    hook, monkeypatch, capsys, tmp_path
):
    """The session id reaches a filename. Keep it inside the state directory."""
    ledger = _ledger(tmp_path, [
        {"event": "started", "out": "output/r.md", "pid": 1, "at": 1e9},
    ])
    _run(hook, monkeypatch, capsys, tmp_path,
         payload={"cwd": str(tmp_path), "session_id": "../../evil/x"}, ledger=ledger)
    written = list((tmp_path / ".agents" / "supervisor").glob("keep-working-*.json"))
    assert len(written) == 1
    assert written[0].parent == tmp_path / ".agents" / "supervisor"
    assert not (tmp_path.parent / "evil").exists()
