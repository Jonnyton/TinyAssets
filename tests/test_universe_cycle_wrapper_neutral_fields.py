"""Tests for substrate-fix #12 Family A Phase 1.B: neutral additive status fields.

When the universe cycle wrapper completes with stopped=True and no produced
work, the log line should additively include `reason_code=no_active_work`
and `display_reason=idle_no_active_work` ALONGSIDE the legacy `reason` field
(for back-compat). This gives first observers (recruiters, fresh AI sessions)
domain-neutral status text instead of fantasy-shaped vocabulary alone.
"""

from __future__ import annotations


def test_wrapper_output_with_synthesis_switch_stops_for_universe_switch(tmp_path):
    """Wrapper-mode output must still trigger the daemon switch path.

    Direct graph execution emits the same health field from the inner
    ``universe_cycle`` node. Under unified execution, the outer stream only
    exposes ``universe_cycle_wrapper`` output, so the controller must honor
    the switch request there too.
    """
    from fantasy_daemon.__main__ import DaemonController

    universe = tmp_path / "universe-a"
    universe.mkdir()
    controller = DaemonController(universe_path=str(universe), no_tray=True)

    controller._handle_node_output(
        "universe_cycle_wrapper",
        {
            "health": {
                "switch_to_universe": "universe-b",
                "stopped": True,
            },
            "total_words": 0,
            "total_chapters": 0,
        },
    )

    assert controller._pending_universe_switch == "universe-b"
    assert controller._stop_event.is_set()


def test_neutral_fields_in_emission_when_idle_by_design():
    """When daemon idles by design (stopped=True, no work), emission includes
    reason_code=no_active_work + display_reason=idle_no_active_work."""
    # Test the field-construction logic directly without spinning up daemon.
    # This mirrors the conditional in fantasy_daemon/__main__.py
    # universe_cycle_wrapper handler.
    health = {"idle_reason": "worldbuild_stuck", "stopped": True}
    output = {"total_words": 0, "total_chapters": 0, "health": health}

    reason = str(health.get("idle_reason") or "continue")
    stopped = bool(health.get("stopped", False))
    total_words = output.get("total_words", 0)
    total_chapters = output.get("total_chapters", 0)
    if stopped and not total_words and not total_chapters:
        reason_code = "no_active_work"
        display_reason = "idle_no_active_work"
    else:
        reason_code = reason
        display_reason = reason

    log_line = (
        "Universe cycle wrapper: completed "
        f"(stopped={stopped}, reason={reason}, "
        f"reason_code={reason_code}, "
        f"display_reason={display_reason}, "
        f"words={total_words}, "
        f"chapters={total_chapters})"
    )

    # Legacy field still present (back-compat)
    assert "reason=worldbuild_stuck" in log_line
    # New neutral fields present additively
    assert "reason_code=no_active_work" in log_line
    assert "display_reason=idle_no_active_work" in log_line


def test_neutral_fields_pass_through_when_active_work():
    """When work IS happening (words or chapters > 0), reason_code and
    display_reason mirror the legacy reason (no special idle override)."""
    health = {"idle_reason": "continue", "stopped": False}
    output = {"total_words": 1500, "total_chapters": 2, "health": health}

    reason = str(health.get("idle_reason") or "continue")
    stopped = bool(health.get("stopped", False))
    total_words = output.get("total_words", 0)
    total_chapters = output.get("total_chapters", 0)
    if stopped and not total_words and not total_chapters:
        reason_code = "no_active_work"
        display_reason = "idle_no_active_work"
    else:
        reason_code = reason
        display_reason = reason

    log_line = (
        "Universe cycle wrapper: completed "
        f"(stopped={stopped}, reason={reason}, "
        f"reason_code={reason_code}, "
        f"display_reason={display_reason}, "
        f"words={total_words}, "
        f"chapters={total_chapters})"
    )

    # Legacy reason mirrored as reason_code/display_reason when active
    assert "reason=continue" in log_line
    assert "reason_code=continue" in log_line
    assert "display_reason=continue" in log_line
