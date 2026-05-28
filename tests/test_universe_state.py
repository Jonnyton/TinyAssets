from __future__ import annotations


def test_domain_neutral_universe_state_excludes_fantasy_counters() -> None:
    from workflow.universe_state import (
        DOMAIN_NEUTRAL_UNIVERSE_STATE_FIELDS,
        FANTASY_DEFAULT_UNIVERSE_STATE_FIELDS,
    )

    assert {
        "universe_id",
        "universe_path",
        "domain_name",
        "progress",
        "metric_units",
        "health",
    } <= DOMAIN_NEUTRAL_UNIVERSE_STATE_FIELDS

    assert FANTASY_DEFAULT_UNIVERSE_STATE_FIELDS.isdisjoint(
        DOMAIN_NEUTRAL_UNIVERSE_STATE_FIELDS
    )


def test_project_domain_neutral_universe_state_drops_domain_fields() -> None:
    from workflow.universe_state import project_domain_neutral_universe_state

    projected = project_domain_neutral_universe_state(
        {
            "universe_id": "research-alpha",
            "universe_path": "/tmp/research-alpha",
            "domain_name": "research_probe",
            "progress": {"artifacts_reviewed": 3},
            "metric_units": {"artifacts_reviewed": "count"},
            "health": {"status": "running"},
            "total_words": 1500,
            "total_chapters": 2,
            "book_number": 1,
            "chapter_number": 4,
            "scene_number": 9,
        }
    )

    assert projected == {
        "universe_id": "research-alpha",
        "universe_path": "/tmp/research-alpha",
        "domain_name": "research_probe",
        "progress": {"artifacts_reviewed": 3},
        "metric_units": {"artifacts_reviewed": "count"},
        "health": {"status": "running"},
    }


def test_fantasy_universe_state_extends_domain_neutral_base() -> None:
    from domains.fantasy_daemon.state.universe_state import UniverseState
    from workflow.universe_state import DOMAIN_NEUTRAL_UNIVERSE_STATE_FIELDS

    fantasy_fields = frozenset(UniverseState.__annotations__)

    assert DOMAIN_NEUTRAL_UNIVERSE_STATE_FIELDS <= fantasy_fields
    assert {"total_words", "total_chapters"} <= fantasy_fields
