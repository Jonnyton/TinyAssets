"""Dark must actually mean dark.

This change lands with enforcement OFF, and every other test in the metering suites
opts explicitly INTO enforcement. That leaves the property the whole landing rests on
untested: with the flag unset, merging this must not be able to change whether any
effect happens.

It is not hypothetical. The metering branch's own history contains a commit titled
"round 3 — dark did not actually mean dark": the ledger was touched before the flag
was read, so a locked or unwritable ledger could refuse a real outbound write. That is
a failure mode created purely by merging, which is exactly what landing dark is meant
to avoid.

So these tests assert the negative: no refusal, no exception, no behaviour change --
while metering still records, because recording is the point of running dark.
"""

from __future__ import annotations

import pytest

from tinyassets.effectors.outbound_boundary import execute_replay_safe_effect
from tinyassets.storage.external_write_receipts import STATUS_SUCCEEDED
from tinyassets.storage.usage_ledger import usage_summary
from tinyassets.usage_policy import enforcement_enabled, reserve_effect_quota


@pytest.fixture(autouse=True)
def _flag_unset(monkeypatch):
    """The shipped default, stated explicitly rather than inherited."""
    monkeypatch.delenv("TINYASSETS_USAGE_ENFORCEMENT", raising=False)


def _fire(universe, key, calls, *, run_id="run-1"):
    def invoke():
        calls.append(key)
        return {"ok": True}

    return execute_replay_safe_effect(
        universe_dir=universe,
        effect_key=key,
        sink="test_sink",
        run_id=run_id,
        invoke=invoke,
    )


def test_enforcement_is_off_by_default():
    assert enforcement_enabled() is False


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "  ", "maybe"])
def test_only_an_explicit_truthy_value_enables_enforcement(value, monkeypatch):
    """A typo in the flag must fail SAFE — off — not silently enforce."""
    monkeypatch.setenv("TINYASSETS_USAGE_ENFORCEMENT", value)
    assert enforcement_enabled() is False


def test_an_exhausted_budget_still_lets_the_effect_through(tmp_path, monkeypatch):
    """The load-bearing negative: over quota, dark, and the write still happens."""
    monkeypatch.setenv("TINYASSETS_FREE_EFFECTS_PER_WINDOW", "1")
    universe = tmp_path / "universe"
    calls: list[str] = []

    assert _fire(universe, "e1", calls)["status"] == STATUS_SUCCEEDED
    over = _fire(universe, "e2", calls, run_id="run-2")

    assert over["status"] == STATUS_SUCCEEDED, "dark must not refuse"
    assert over.get("reason") != "usage_limit_reached"
    assert calls == ["e1", "e2"], "the destination must still be contacted"


def test_an_unusable_ledger_cannot_block_a_write(tmp_path, monkeypatch):
    """A failure mode that would exist ONLY because we merged this."""
    universe = tmp_path / "universe"
    universe.mkdir()
    from tinyassets.storage.usage_ledger import usage_ledger_path

    # A ledger that cannot be opened as a database at all.
    usage_ledger_path(universe).write_bytes(b"this is not a sqlite database")

    calls: list[str] = []
    result = _fire(universe, "e1", calls)

    assert result["status"] == STATUS_SUCCEEDED
    assert calls == ["e1"], "a broken meter must not stop the world"


def test_an_unusable_ledger_refuses_once_enforcement_is_on(tmp_path, monkeypatch):
    """The other half: enforcing, a meter we cannot read must fail CLOSED.

    Otherwise the cap is defeated by making the ledger unavailable.
    """
    monkeypatch.setenv("TINYASSETS_USAGE_ENFORCEMENT", "1")
    universe = tmp_path / "universe"
    universe.mkdir()
    from tinyassets.storage.usage_ledger import usage_ledger_path

    usage_ledger_path(universe).write_bytes(b"not a database")

    refusal = reserve_effect_quota(universe, sink="s", effect_key="k", tier="free")
    assert refusal is not None
    assert refusal.dimension == "effect"


def test_metering_still_records_while_dark(tmp_path):
    """Recording IS the point of dark: it is how we learn what real usage looks like
    before choosing a number to enforce."""
    universe = tmp_path / "universe"
    calls: list[str] = []

    _fire(universe, "a", calls)
    _fire(universe, "b", calls, run_id="run-2")

    summary = usage_summary(universe, window_seconds=86_400.0)
    assert summary["effects_committed"] == 2.0, "dark still meters"
