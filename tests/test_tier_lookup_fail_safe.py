"""A tier lookup must never be able to stop an outbound effect.

The quota gate resolves the tier as an ARGUMENT:

    reserve_effect_quota(..., tier=get_tier(universe_dir))

which means the lookup runs *outside* `reserve_effect_quota`'s own guard. That guard is
what makes metering harmless while dark -- it swallows a broken ledger so a failed meter
can never decide whether an effect happens. A lookup that raises before the call is made
slips straight past it.

`get_tier` caught only `sqlite3.Error`, but `_connect` first does
`path.parent.mkdir(...)`, which raises `OSError` on a read-only filesystem, a full disk,
or a permissions problem. So an environment where the universe directory cannot be
created turned every outbound effect into a crash -- dark or not, and only because
metering was merged.
"""

from __future__ import annotations

from unittest import mock

import pytest

from tinyassets.effectors.outbound_boundary import execute_replay_safe_effect
from tinyassets.storage import subscription_state as ss
from tinyassets.storage.external_write_receipts import STATUS_SUCCEEDED


@pytest.mark.parametrize(
    "boom",
    [PermissionError("read-only fs"), OSError("no space left on device")],
)
def test_an_unusable_universe_dir_reads_as_free_rather_than_raising(boom, tmp_path):
    with mock.patch.object(ss.Path, "mkdir", side_effect=boom):
        assert ss.get_tier(tmp_path / "u") == "free"


def test_an_unusable_universe_dir_never_grants_the_paid_tier(tmp_path):
    """The fail-safe direction. Unreadable must mean free, never paid."""
    with mock.patch.object(ss.Path, "mkdir", side_effect=PermissionError("x")):
        assert ss.get_tier(tmp_path / "u", default="free") == "free"


def test_an_unusable_universe_dir_does_not_stop_an_outbound_effect(tmp_path):
    """The property that actually matters, at the boundary that actually ships."""
    universe = tmp_path / "universe"
    universe.mkdir()
    calls: list[str] = []

    # Break ONLY the subscription-state connection. Patching Path.mkdir globally also
    # broke the receipt store, which this test is not about -- and a test that fails
    # for a second reason cannot show the first one was fixed.
    def _unusable(*_a, **_kw):
        raise PermissionError("read-only fs")

    with mock.patch.object(ss, "_connect", _unusable):
        result = execute_replay_safe_effect(
            universe_dir=universe,
            effect_key="e1",
            sink="test_sink",
            run_id="run-1",
            invoke=lambda: calls.append("e1") or {"ok": True},
        )

    assert result["status"] == STATUS_SUCCEEDED
    assert calls == ["e1"], "a broken tier lookup must not stop the world"
