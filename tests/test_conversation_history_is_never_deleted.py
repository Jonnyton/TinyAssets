"""The platform never deletes a user's transcript.

Founder, 2026-09-30: an account has exactly two limits -- the cloud bytes a
universe occupies, and how many agent runs it may have going at once. Stored
turns are bytes, charged to tier storage like anything else, so there is no
separate history ceiling. The 400-turn ``RETENTION_TURNS`` delete that used to
run inside every ``record_exchange`` is gone.

What a model is SENT stays bounded (``DEFAULT_LIMIT`` turns, character budget at
render time). Trimming a prompt and deleting a record are different decisions,
and only the user makes the second one.
"""

from __future__ import annotations

import sqlite3

from tinyassets import conversation_store as store
from tinyassets.conversation_memory import DEFAULT_LIMIT


def _stored_turn_count(universe_dir) -> int:
    conn = sqlite3.connect(universe_dir / ".conversation_memory.db")
    try:
        return int(conn.execute("SELECT COUNT(*) FROM conversation_turns").fetchone()[0])
    finally:
        conn.close()


def test_five_hundred_turns_keep_every_row(tmp_path):
    """Well past the old 400 ceiling, with the oldest turn still readable."""
    for i in range(500):
        assert store.record_exchange(tmp_path, "s", f"q{i}", f"a{i}")

    assert _stored_turn_count(tmp_path) == 1000, "500 exchanges = 1000 rows, none dropped"

    everything = store.load_recent_readonly(tmp_path, "s", limit=5000)
    assert len(everything) == 1000
    assert everything[0].text == "q0", "the very first turn survived turn 500"
    assert everything[-1].text == "a499"


def test_reading_is_still_bounded_by_default(tmp_path):
    """Storage is unbounded; what a turn RENDERS is not. Both, at once."""
    for i in range(30):
        assert store.record_exchange(tmp_path, "s", f"q{i}", f"a{i}")

    assert _stored_turn_count(tmp_path) == 60
    assert len(store.load_recent_readonly(tmp_path, "s")) == DEFAULT_LIMIT
    assert len(store.load_recent(tmp_path, "s")) == DEFAULT_LIMIT


def test_no_write_path_issues_a_delete(tmp_path):
    """Mutation guard against a retention delete creeping back in.

    A trigger that aborts any DELETE on the transcript. It has to run PAST the
    old 400-turn threshold to mean anything: a re-added
    ``DELETE ... turn_no <= max - RETENTION_TURNS`` matches zero rows below the
    threshold, so the trigger would never fire and the guard would pass against
    the very code it exists to catch (Codex refute, 2026-09-30).

    So: 250 exchanges = 500 rows, comfortably past 400, with the trigger armed
    from the first one.
    """
    store.record_exchange(tmp_path, "s", "first", "reply")
    conn = store._connect(tmp_path / ".conversation_memory.db")
    try:
        conn.execute(
            "CREATE TRIGGER refuse_delete BEFORE DELETE ON conversation_turns "
            "BEGIN SELECT RAISE(ABORT, 'the transcript is never deleted'); END"
        )
        conn.commit()
    finally:
        conn.close()

    for i in range(250):
        assert store.record_exchange(tmp_path, "s", f"q{i}", f"a{i}"), (
            f"a write path attempted a DELETE on conversation_turns at exchange {i}"
        )
    assert store.record_failure(tmp_path, "s", "bad", "unknown")
    assert _stored_turn_count(tmp_path) == 504
    # And the projection path, which had its own DELETE, is covered by source:
    # there is no DELETE on conversation_turns anywhere in either writer.
    import inspect

    from tinyassets.storage import conversation_run_admissions as cra

    for module in (store, cra):
        src = inspect.getsource(module)
        assert "DELETE FROM conversation_turns" not in src, (
            f"{module.__name__} deletes transcript rows"
        )
