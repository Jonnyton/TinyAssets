"""Every goals WRITE action must leave an attributed ledger row.

This exists because the row silently stopped being written. `market.py` called
`_append_global_ledger(...)` without its required keyword-only `actor`, so every
goals write raised `TypeError`, hit the broad `except Exception` guarding the
ledger, and was logged as::

    WARNING  Ledger write failed for goals.propose:
             _append_global_ledger() missing 1 required keyword-only argument: 'actor'

The action itself still returned `{"status": "proposed"}`, so nothing user-facing
or test-facing went red — `ledger.json` simply never appeared. Attribution and
audit data for every goals write was lost with a warning nobody reads.

The swallow is deliberate (`_append_global_ledger` documents "Never raises:
failures are logged but don't roll back the mutation") and is NOT changed here:
a ledger failure should not roll back a completed mutation. That design is
exactly why the defect survived, so the guard has to be a test that reads the
ledger back rather than trust on the call site being right.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def goals_env(tmp_path, monkeypatch, authenticate_request):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    authenticate_request(
        "alice",
        capabilities=["tinyassets.goals.read", "tinyassets.goals.write"],
    )
    from tinyassets import universe_server as us

    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _ledger_rows(base: Path) -> list[dict]:
    path = base / "ledger.json"
    if not path.exists():
        return []
    return json.loads(path.read_text("utf-8"))


def test_goals_propose_writes_an_attributed_ledger_row(goals_env) -> None:
    us, base = goals_env

    result = json.loads(us.goals(action="propose", name="G", description="x"))
    assert result.get("status") == "proposed", result

    rows = _ledger_rows(base)
    assert rows, (
        "goals.propose wrote no ledger row at all. The mutation succeeded, so "
        "this is the silent-attribution-loss regression: check that "
        "_append_global_ledger is called with its required `actor` kwarg."
    )
    proposes = [r for r in rows if r.get("action") == "goals.propose"]
    assert len(proposes) == 1, [r.get("action") for r in rows]
    assert proposes[0].get("actor") == "alice", proposes[0]


def test_ledger_actor_is_the_credential_subject_not_the_env_user(
    goals_env, monkeypatch
) -> None:
    """The env var must not be able to forge the recorded actor.

    `UNIVERSE_SERVER_USER` is ambient; the credential subject is not. If the
    ledger ever falls back to the env var, an unauthenticated or differently
    authenticated caller would be attributed to whoever the environment names.
    """
    us, base = goals_env
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "mallory")

    json.loads(us.goals(action="propose", name="G2", description="x"))

    rows = [r for r in _ledger_rows(base) if r.get("action") == "goals.propose"]
    assert rows, "no ledger row written"
    assert rows[0].get("actor") == "alice", (
        f"ledger recorded {rows[0].get('actor')!r}; the credential subject is "
        f"'alice' and the env var was changed to 'mallory' to prove the env "
        f"cannot forge attribution"
    )


def test_unauthenticated_write_is_anonymous_not_the_env_user(
    tmp_path, monkeypatch
) -> None:
    """With NO credential, attribution must be `anonymous`, never the env user.

    This is the gap the first version of this fix left open, found in review.
    Passing `actor=""` looked harmless, but `_append_ledger` resolves a falsy
    actor via `actor or _current_actor()`, and `_current_actor()` reads
    `UNIVERSE_SERVER_USER`. So an unauthenticated write was attributed to
    whoever the environment happened to name — the ambient env forging an
    identity, which is precisely what `_request_branch_actor` exists to stop.

    Deliberately NOT asserting that the write is refused: production OAuth
    blocks anonymous writes at a different layer, and this test is about
    attribution honesty, not about relocating that gate.
    """
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "mallory")
    from tinyassets import universe_server as us

    importlib.reload(us)
    try:
        json.loads(us.goals(action="propose", name="G3", description="x"))
        rows = [
            r for r in _ledger_rows(base) if r.get("action") == "goals.propose"
        ]
        assert rows, "no ledger row written for an unauthenticated propose"
        assert rows[0].get("actor") == "anonymous", (
            f"unauthenticated write recorded actor "
            f"{rows[0].get('actor')!r}; the ambient UNIVERSE_SERVER_USER was "
            f"'mallory', so anything but 'anonymous' means the env forged an "
            f"identity into the audit trail"
        )
    finally:
        importlib.reload(us)
