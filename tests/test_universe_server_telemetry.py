"""Tests for Universe Server daemon telemetry legibility.

Covers the cluster of bugs where `inspect`, `list`, and `control_daemon
status` returned stale or misleading daemon state:
- #8 raw phase was "unknown" because status.json uses `current_phase`
  but readers looked for `phase`.
- #10 `inspect` silently omitted the premise field when PROGRAM.md was
  missing, making "no premise" indistinguishable from "premise was empty".
- #14/#16 dormant daemons reported as alive because no reader checked
  activity freshness.
- #17 `accept_rate=0.0` was read from a stale status.json field that
  nothing updates at runtime.

The fix centralizes liveness in `_daemon_liveness()` and is consumed by
list, inspect, and control_daemon status.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import tinyassets.api.universe as us


@pytest.fixture
def universe_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    return base


def _make_universe(
    base: Path, uid: str, *,
    premise: str | None = None,
    work_targets: list[dict] | None = None,
    status: dict | None = None,
    activity_age_hours: float | None = None,
    scene_history: list[tuple[str, str]] | None = None,
    paused: bool = False,
) -> Path:
    """Build a universe on disk with controllable liveness signals."""
    udir = base / uid
    udir.mkdir()
    if premise is not None:
        (udir / "PROGRAM.md").write_text(premise, encoding="utf-8")
    if work_targets is not None:
        (udir / "work_targets.json").write_text(
            json.dumps(work_targets), encoding="utf-8",
        )
    if status is not None:
        (udir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    if activity_age_hours is not None:
        log = udir / "activity.log"
        log.write_text("[run] sample\n", encoding="utf-8")
        target = time.time() - activity_age_hours * 3600
        os.utime(log, (target, target))
    if paused:
        (udir / ".pause").write_text("paused", encoding="utf-8")
    if scene_history is not None:
        db = udir / "story.db"
        conn = sqlite3.connect(str(db))
        try:
            conn.execute(
                "CREATE TABLE scene_history (scene_id TEXT, verdict TEXT)"
            )
            conn.executemany(
                "INSERT INTO scene_history (scene_id, verdict) VALUES (?, ?)",
                scene_history,
            )
            conn.commit()
        finally:
            conn.close()
    return udir


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def test_staleness_buckets_cover_fresh_idle_dormant_never() -> None:
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(minutes=30)).isoformat()
    idle = (now - timedelta(hours=6)).isoformat()
    dormant = (now - timedelta(days=3)).isoformat()

    assert us._staleness_bucket(fresh) == "fresh"
    assert us._staleness_bucket(idle) == "idle"
    assert us._staleness_bucket(dormant) == "dormant"
    assert us._staleness_bucket(None) == "never"
    assert us._staleness_bucket("not-a-timestamp") == "never"


def test_phase_human_paused_wins_over_everything() -> None:
    assert us._phase_human(
        "dispatch_execution", has_premise=True, has_work=True,
        is_paused=True, staleness="fresh",
    ) == "paused"


def test_phase_human_dormant_paths() -> None:
    assert us._phase_human(
        "dispatch_execution", has_premise=False, has_work=False,
        is_paused=False, staleness="dormant",
    ) == "dormant-no-premise"
    assert us._phase_human(
        "dispatch_execution", has_premise=True, has_work=False,
        is_paused=False, staleness="dormant",
    ) == "dormant-starved"
    assert us._phase_human(
        "dispatch_execution", has_premise=True, has_work=True,
        is_paused=False, staleness="dormant",
    ) == "dormant"


def test_phase_human_starved_paths_for_fresh_daemon() -> None:
    assert us._phase_human(
        "unknown", has_premise=False, has_work=False,
        is_paused=False, staleness="fresh",
    ) == "idle-no-premise"
    assert us._phase_human(
        "unknown", has_premise=True, has_work=False,
        is_paused=False, staleness="fresh",
    ) == "starved"


def test_phase_human_returns_raw_phase_when_running_and_ready() -> None:
    assert us._phase_human(
        "dispatch_execution", has_premise=True, has_work=True,
        is_paused=False, staleness="fresh",
    ) == "dispatch_execution"


def test_phase_human_falls_back_to_idle_when_raw_phase_blank() -> None:
    assert us._phase_human(
        "", has_premise=True, has_work=True,
        is_paused=False, staleness="fresh",
    ) == "idle"
    assert us._phase_human(
        None, has_premise=True, has_work=True,
        is_paused=False, staleness="fresh",
    ) == "idle"


def test_last_activity_prefers_activity_log_mtime(universe_base: Path) -> None:
    udir = _make_universe(
        universe_base, "u",
        status={"current_phase": "x", "last_updated": "2026-04-01T00:00:00+00:00"},
        activity_age_hours=0.5,  # 30 minutes ago
    )
    got = us._last_activity_at(udir, json.loads((udir / "status.json").read_text()))
    assert got is not None
    ts = datetime.fromisoformat(got)
    age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
    # Activity log wins over status.last_updated; should be ~30min, not 2026-04-01.
    assert age_seconds < 60 * 60


def test_last_activity_falls_back_to_status_last_updated(
    universe_base: Path,
) -> None:
    status = {"current_phase": "x", "last_updated": "2026-04-05T12:00:00+00:00"}
    udir = _make_universe(universe_base, "u", status=status)
    got = us._last_activity_at(udir, status)
    assert got == "2026-04-05T12:00:00+00:00"


def test_last_activity_uses_runtime_status_heartbeat(
    universe_base: Path,
) -> None:
    udir = _make_universe(
        universe_base, "u",
        status={"current_phase": "x", "last_updated": "2026-04-01T00:00:00+00:00"},
        activity_age_hours=2,
    )
    runtime_status = udir / ".runtime_status.json"
    runtime_status.write_text("{}", encoding="utf-8")

    got = us._last_activity_at(
        udir, json.loads((udir / "status.json").read_text()),
    )
    assert got is not None
    ts = datetime.fromisoformat(got)
    age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
    assert age_seconds < 60


def test_last_activity_returns_none_for_untouched_universe(
    universe_base: Path,
) -> None:
    udir = universe_base / "fresh"
    udir.mkdir()
    assert us._last_activity_at(udir, None) is None


# ---------------------------------------------------------------------------
# accept_rate from scene_history
# ---------------------------------------------------------------------------


def test_accept_rate_returns_none_without_db(universe_base: Path) -> None:
    udir = _make_universe(universe_base, "u")
    rate, sample = us._compute_accept_rate_from_db(udir)
    assert rate is None
    assert sample["source"] == "none"


def test_accept_rate_ignores_pending_verdicts(universe_base: Path) -> None:
    """#17: status.json cached `accept_rate: 0.0` confused readers when
    really no scenes had been evaluated yet. The fix: pending scenes do
    NOT count as rejects. `None` means "no evaluated sample", not 0%.
    """
    udir = _make_universe(
        universe_base, "u",
        scene_history=[("s1", "pending"), ("s2", "pending")],
    )
    rate, sample = us._compute_accept_rate_from_db(udir)
    assert rate is None
    assert sample == {"accepted": 0, "evaluated": 0, "source": "scene_history"}


def test_accept_rate_computes_when_scenes_evaluated(universe_base: Path) -> None:
    udir = _make_universe(
        universe_base, "u",
        scene_history=[
            ("s1", "accept"),
            ("s2", "second_draft"),
            ("s3", "reject"),
            ("s4", "pending"),  # excluded from both numerator and denominator
        ],
    )
    rate, sample = us._compute_accept_rate_from_db(udir)
    assert rate == pytest.approx(2 / 3)
    assert sample == {"accepted": 2, "evaluated": 3, "source": "scene_history"}


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------


def test_inspect_surfaces_has_premise_false_when_missing(
    universe_base: Path,
) -> None:
    """#10: has_premise must be an explicit boolean in the inspect response."""
    _make_universe(universe_base, "u")  # no premise
    out = json.loads(us._action_inspect_universe(universe_id="u"))
    assert out["has_premise"] is False
    assert "premise" not in out


def test_inspect_surfaces_has_premise_true_with_text(
    universe_base: Path,
) -> None:
    _make_universe(universe_base, "u", premise="A tower of bones.")
    out = json.loads(us._action_inspect_universe(universe_id="u"))
    assert out["has_premise"] is True
    assert out["premise"] == "A tower of bones."


def test_inspect_translates_current_phase_from_status_json(
    universe_base: Path,
) -> None:
    """#8: status.json uses `current_phase`; inspect previously read `phase`
    and reported 'unknown'. Fix: we read current_phase with phase as fallback.
    """
    _make_universe(
        universe_base, "u",
        premise="x",
        status={"current_phase": "dispatch_execution", "word_count": 1000},
        activity_age_hours=0.1,
    )
    out = json.loads(us._action_inspect_universe(universe_id="u"))
    assert out["daemon"]["phase"] == "dispatch_execution"
    assert out["daemon"]["phase_human"] != "unknown"


def test_inspect_reports_dormant_for_stale_daemon(universe_base: Path) -> None:
    """#14/#16: a status.json that claims 'running' must not be trusted
    as a liveness signal. Activity log age drives staleness.
    """
    _make_universe(
        universe_base, "u",
        premise="x",
        work_targets=[{"lifecycle": "active", "target_id": "t1"}],
        status={"current_phase": "dispatch_execution", "daemon_state": "running"},
        activity_age_hours=48,  # 2 days stale
    )
    out = json.loads(us._action_inspect_universe(universe_id="u"))
    d = out["daemon"]
    assert d["staleness"] == "dormant"
    assert d["phase_human"] == "dormant"


def test_inspect_reports_idle_no_premise_for_empty_universe(
    universe_base: Path,
) -> None:
    """#8 broader: missing premise should surface as `idle-no-premise`,
    not fall through to `unknown`.
    """
    _make_universe(universe_base, "u")  # no premise, no work, no activity
    out = json.loads(us._action_inspect_universe(universe_id="u"))
    d = out["daemon"]
    assert d["has_premise"] is False
    assert d["phase_human"] == "idle-no-premise"
    assert d["staleness"] == "never"


def test_inspect_accept_rate_is_null_not_zero(universe_base: Path) -> None:
    """#17: returning accept_rate=0.0 when nothing has been evaluated is
    misleading. Callers should see null + the sample counts."""
    _make_universe(universe_base, "u", premise="x")
    out = json.loads(us._action_inspect_universe(universe_id="u"))
    assert out["daemon"]["accept_rate"] is None
    assert out["daemon"]["accept_rate_sample"]["evaluated"] == 0


# ---------------------------------------------------------------------------
# control_daemon status
# ---------------------------------------------------------------------------


def test_control_daemon_status_includes_liveness_fields(
    universe_base: Path,
) -> None:
    """#14: status must expose last_activity_at + staleness so readers
    can tell a dormant daemon from an alive one.
    """
    _make_universe(
        universe_base, "u",
        premise="x",
        work_targets=[{"lifecycle": "active", "target_id": "t1"}],
        status={"current_phase": "dispatch_execution"},
        activity_age_hours=72,  # 3 days stale
    )
    out = json.loads(us._action_control_daemon(universe_id="u", text="status"))
    assert out["action"] == "status"
    assert out["phase_human"] == "dormant"
    assert out["staleness"] == "dormant"
    assert out["last_activity_at"] is not None
    assert out["has_premise"] is True
    assert "accept_rate" in out
    assert "accept_rate_sample" in out


def test_control_daemon_status_reports_paused_state(universe_base: Path) -> None:
    _make_universe(
        universe_base, "u",
        premise="x",
        work_targets=[{"lifecycle": "active", "target_id": "t1"}],
        status={"current_phase": "dispatch_execution"},
        activity_age_hours=0.1,
        paused=True,
    )
    out = json.loads(us._action_control_daemon(universe_id="u", text="status"))
    assert out["is_paused"] is True
    assert out["phase_human"] == "paused"


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_surfaces_telemetry_for_every_universe(universe_base: Path) -> None:
    _make_universe(
        universe_base, "alive",
        premise="x",
        work_targets=[{"lifecycle": "active", "target_id": "t1"}],
        status={"current_phase": "draft"},
        activity_age_hours=0.1,
    )
    _make_universe(universe_base, "empty")  # no premise
    out = json.loads(us._action_list_universes())
    by_id = {u["id"]: u for u in out["universes"]}

    alive = by_id["alive"]
    assert alive["has_premise"] is True
    assert alive["staleness"] == "fresh"
    assert alive["phase_human"] == "draft"

    empty = by_id["empty"]
    assert empty["has_premise"] is False
    assert empty["phase_human"] == "idle-no-premise"
    assert empty["staleness"] == "never"
    assert empty["last_activity_at"] is None
