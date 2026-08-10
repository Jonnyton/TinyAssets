"""Durable, session-anchored conversation store for the stateless universe turn.

The universe turn is rebuilt from scratch every call. The 2026-08-08 hotfix gave
the SLACK path a sliding window pulled from `conversations.history`, but the MCP
`converse` path had no memory at all and nothing was durable/surface-agnostic —
u-tiny's own diagnosis (Slack thread 1786225160): *"the sliding window injection
is built but not the session-anchored persistence layer."*

This is that layer: a SQLite store keyed by `(session_id, turn_no)`, per universe,
feeding the already-reviewed `conversation_memory.format_history` formatter.
Design: docs/design-notes/2026-08-09-persistent-conversation-memory.md.
"""

from __future__ import annotations

import threading

from tinyassets import conversation_store as cs
from tinyassets.conversation_memory import Msg


def test_record_then_load_roundtrips_oldest_first(tmp_path):
    cs.record_turn(tmp_path, "slack:C1", "founder", "post the update")
    cs.record_turn(tmp_path, "slack:C1", "universe", "on it")
    cs.record_turn(tmp_path, "slack:C1", "founder", "did it go out?")
    got = cs.load_recent(tmp_path, "slack:C1")
    assert [(m.speaker, m.text) for m in got] == [
        ("founder", "post the update"),
        ("universe", "on it"),
        ("founder", "did it go out?"),
    ]
    assert all(isinstance(m, Msg) for m in got)


def test_load_recent_is_empty_when_nothing_stored(tmp_path):
    assert cs.load_recent(tmp_path, "slack:never") == []


def test_sessions_are_isolated(tmp_path):
    cs.record_turn(tmp_path, "slack:A", "founder", "topic A")
    cs.record_turn(tmp_path, "slack:B", "founder", "topic B")
    a = cs.load_recent(tmp_path, "slack:A")
    b = cs.load_recent(tmp_path, "slack:B")
    assert [m.text for m in a] == ["topic A"]
    assert [m.text for m in b] == ["topic B"]


def test_universes_are_isolated(tmp_path):
    u1 = tmp_path / "u1"
    u2 = tmp_path / "u2"
    u1.mkdir()
    u2.mkdir()
    cs.record_turn(u1, "converse:u1", "founder", "secret for u1")
    got_u2 = cs.load_recent(u2, "converse:u1")
    # Same session-id string, different universe dir → no bleed.
    assert got_u2 == []
    assert [m.text for m in cs.load_recent(u1, "converse:u1")] == ["secret for u1"]


def test_turn_no_is_per_session_and_monotonic(tmp_path):
    t1 = cs.record_turn(tmp_path, "slack:A", "founder", "one")
    t2 = cs.record_turn(tmp_path, "slack:A", "universe", "two")
    other = cs.record_turn(tmp_path, "slack:B", "founder", "b-one")
    assert t1 == 1
    assert t2 == 2
    # A fresh session starts its own turn count at 1, not the global max.
    assert other == 1


def test_limit_keeps_only_the_most_recent_n(tmp_path):
    for i in range(30):
        cs.record_turn(tmp_path, "slack:A", "founder", f"m{i}")
    got = cs.load_recent(tmp_path, "slack:A", limit=5)
    assert [m.text for m in got] == ["m25", "m26", "m27", "m28", "m29"]


def test_empty_or_blank_text_is_not_recorded(tmp_path):
    cs.record_turn(tmp_path, "slack:A", "founder", "real")
    cs.record_turn(tmp_path, "slack:A", "founder", "")
    cs.record_turn(tmp_path, "slack:A", "founder", "   ")
    got = cs.load_recent(tmp_path, "slack:A")
    assert [m.text for m in got] == ["real"]


def test_load_recent_never_raises_on_bad_dir(tmp_path):
    # Best-effort: a store that cannot be opened returns [] (no memory this
    # turn), it never breaks the reply.
    bad = tmp_path / "does_not_exist"  # not created
    assert cs.load_recent(bad, "slack:A") == []


def test_concurrent_records_do_not_collide_on_turn_no(tmp_path):
    # Two turns racing on the same session must not both claim the same turn_no
    # and must not lose a write. SQLite is the single writer of record.
    session = "slack:race"
    n = 40
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            cs.record_turn(tmp_path, session, "founder", f"msg{i}")
        except Exception as exc:  # noqa: BLE001 - surface in assertion
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"record_turn raised under concurrency: {errors[:3]}"
    got = cs.load_recent(tmp_path, session, limit=1000)
    # No writes lost, and every message is present exactly once.
    assert len(got) == n
    assert sorted(m.text for m in got) == sorted(f"msg{i}" for i in range(n))


def test_feeds_the_formatter(tmp_path):
    from tinyassets.conversation_memory import format_history

    cs.record_turn(tmp_path, "slack:A", "founder", "my favorite topic is tide pools")
    cs.record_turn(tmp_path, "slack:A", "universe", "noted")
    block = format_history(cs.load_recent(tmp_path, "slack:A"))
    assert "tide pools" in block
    # The formatter's untrusted-not-consent fence is intact.
    assert "NOT consent" in block


def test_has_prior_turns_helper(tmp_path):
    # Used by the Slack cold-store backfill decision: does this session already
    # have durable history, or should we backfill from the Slack API once?
    assert cs.has_prior_turns(tmp_path, "slack:A") is False
    cs.record_turn(tmp_path, "slack:A", "founder", "hi")
    assert cs.has_prior_turns(tmp_path, "slack:A") is True


def test_backfill_once_imports_a_timeline(tmp_path):
    msgs = [
        {"speaker": "founder", "text": "older ask"},
        {"speaker": "universe", "text": "older reply"},
        {"speaker": "founder", "text": "", "extra": "blank dropped"},
    ]
    n = cs.backfill_once(tmp_path, "slack:A", msgs)
    assert n == 2  # the blank is not imported
    assert [(m.speaker, m.text) for m in cs.load_recent(tmp_path, "slack:A")] == [
        ("founder", "older ask"),
        ("universe", "older reply"),
    ]
    assert cs.is_backfilled(tmp_path, "slack:A") is True


def test_backfill_once_is_idempotent(tmp_path):
    msgs = [{"speaker": "founder", "text": "one"}]
    assert cs.backfill_once(tmp_path, "slack:A", msgs) == 1
    # A second import claims nothing and does NOT duplicate.
    assert cs.backfill_once(tmp_path, "slack:A", msgs) == 0
    assert [m.text for m in cs.load_recent(tmp_path, "slack:A")] == ["one"]


def test_backfill_once_marks_even_an_empty_timeline(tmp_path):
    # An empty timeline still claims the marker, so we do not re-hit Slack every
    # turn for a brand-new conversation.
    assert cs.backfill_once(tmp_path, "slack:new", []) == 0
    assert cs.is_backfilled(tmp_path, "slack:new") is True


def test_concurrent_backfill_imports_exactly_once(tmp_path):
    # The bug Codex flagged: two cold turns racing both run the backfill loop and
    # duplicate every imported message. The marker + single transaction makes
    # exactly one worker win.
    msgs = [{"speaker": "founder", "text": f"m{i}"} for i in range(10)]
    session = "slack:race"
    results: list[int] = []
    lock = threading.Lock()

    def worker() -> None:
        got = cs.backfill_once(tmp_path, session, msgs)
        with lock:
            results.append(got)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly one worker imported the 10 messages; the rest imported nothing.
    assert sorted(results) == [0, 0, 0, 0, 0, 0, 0, 10]
    # And the store holds each message exactly once — no duplication.
    got = cs.load_recent(tmp_path, session, limit=1000)
    assert sorted(m.text for m in got) == sorted(f"m{i}" for i in range(10))


def test_backfill_then_record_continues_turn_numbering(tmp_path):
    cs.backfill_once(tmp_path, "slack:A", [{"speaker": "founder", "text": "imported"}])
    t = cs.record_turn(tmp_path, "slack:A", "founder", "live turn")
    assert t == 2  # continues after the 1 imported turn, no collision
    assert [m.text for m in cs.load_recent(tmp_path, "slack:A")] == [
        "imported",
        "live turn",
    ]


# -- sync_tail: self-healing when a record_turn was dropped (silent drift) ----


def test_load_resyncs_a_tail_the_store_missed(tmp_path):
    """`backfill_once` runs exactly once, so a dropped `record_turn` leaves the
    store BEHIND the live thread forever — the exact silent drift that froze
    u-tiny's memory. `sync_tail` reconciles the missing trailing turns.

    Mutation-check: delete the `record_turn` inside `sync_tail`'s append loop and
    the store stays two turns behind — this assertion goes red.
    """
    session = "slack:C1"
    # The store has the older turns but MISSED the two most recent.
    cs.record_turn(tmp_path, session, "founder", "what's our plan?")
    cs.record_turn(tmp_path, session, "universe", "ship the memory fix")
    # The live Slack timeline is ahead by two turns.
    live = [
        {"speaker": "founder", "text": "what's our plan?"},
        {"speaker": "universe", "text": "ship the memory fix"},
        {"speaker": "founder", "text": "did the deploy go out?"},    # missed
        {"speaker": "universe", "text": "yes, sha abc123 is live"},  # missed
    ]
    appended = cs.sync_tail(tmp_path, session, live)
    assert appended == 2
    assert [m.text for m in cs.load_recent(tmp_path, session)] == [
        "what's our plan?",
        "ship the memory fix",
        "did the deploy go out?",
        "yes, sha abc123 is live",
    ]


def test_sync_tail_is_a_noop_when_the_store_is_current(tmp_path):
    session = "slack:C1"
    cs.record_turn(tmp_path, session, "founder", "hi")
    cs.record_turn(tmp_path, session, "universe", "hello")
    live = [
        {"speaker": "founder", "text": "hi"},
        {"speaker": "universe", "text": "hello"},
    ]
    assert cs.sync_tail(tmp_path, session, live) == 0
    assert [m.text for m in cs.load_recent(tmp_path, session)] == ["hi", "hello"]


def test_sync_tail_leaves_a_cold_store_to_backfill(tmp_path):
    # A cold store (nothing recorded) is `backfill_once`'s job, not sync_tail's;
    # it must not append a whole window here and race the backfill.
    live = [{"speaker": "founder", "text": "brand new"}]
    assert cs.sync_tail(tmp_path, "slack:new", live) == 0
    assert cs.load_recent(tmp_path, "slack:new") == []


def test_sync_tail_skips_when_there_is_no_overlap(tmp_path):
    # If the live window shares nothing with the store, appending a whole window
    # blind risks duplication — leave it to normal recording.
    session = "slack:C1"
    cs.record_turn(tmp_path, session, "founder", "old thing")
    live = [{"speaker": "founder", "text": "totally different"}]
    assert cs.sync_tail(tmp_path, session, live) == 0
    assert [m.text for m in cs.load_recent(tmp_path, session)] == ["old thing"]


def test_sync_tail_never_duplicates_a_repeated_phrase_at_the_seam(tmp_path):
    # "yes" appears in both stored tail and the missing tail; sync_tail must not
    # re-append the already-stored one.
    session = "slack:C1"
    cs.record_turn(tmp_path, session, "founder", "go ahead?")
    cs.record_turn(tmp_path, session, "founder", "yes")
    live = [
        {"speaker": "founder", "text": "go ahead?"},
        {"speaker": "founder", "text": "yes"},
        {"speaker": "universe", "text": "done"},  # the only genuinely new one
    ]
    assert cs.sync_tail(tmp_path, session, live) == 1
    assert [m.text for m in cs.load_recent(tmp_path, session)] == [
        "go ahead?",
        "yes",
        "done",
    ]


def test_sync_tail_never_raises(tmp_path):
    # Best-effort: bad input degrades to 0, never breaks the turn.
    assert cs.sync_tail(tmp_path, "slack:C1", None) == 0
    assert cs.sync_tail(tmp_path, "", [{"speaker": "founder", "text": "x"}]) == 0


# -- hardening: bad-ts never-raise + stable-id dedup + no phantom resync -------


def test_record_turn_survives_a_bad_ts(tmp_path):
    # A malformed ts must degrade to "now", never raise into the turn (this runs
    # OUTSIDE record_turn's retry try, so an un-coerced float() would escape).
    n = cs.record_turn(tmp_path, "slack:C1", "founder", "hi", ts="not-a-ts")
    assert n == 1
    got = cs.load_recent(tmp_path, "slack:C1")
    assert [m.text for m in got] == ["hi"]
    assert got[0].ts is None or got[0].ts > 0  # a real "when", not a crash


def test_sync_tail_dedups_by_stable_id_keeps_a_repeated_message(tmp_path):
    # A legitimately REPEATED message (same text, DIFFERENT Slack ts) must not be
    # lost: id-based dedup keeps both, where a pure text set would drop the second.
    session = "slack:C1"
    cs.record_turn(tmp_path, session, "founder", "ping", ts=100.0001, ext_id="100.0001")
    live = [
        {"speaker": "founder", "text": "ping", "ts": "100.0001"},  # already stored (id)
        {"speaker": "founder", "text": "ping", "ts": "100.0002"},  # NEW: same text, new id
    ]
    assert cs.sync_tail(tmp_path, session, live) == 1
    assert [m.text for m in cs.load_recent(tmp_path, session)] == ["ping", "ping"]


def test_sync_tail_never_re_appends_the_same_id(tmp_path):
    # The same Slack message (same id) is never appended twice, even across calls.
    session = "slack:C1"
    cs.backfill_once(tmp_path, session, [{"speaker": "founder", "text": "a", "ts": "1.1"}])
    live = [
        {"speaker": "founder", "text": "a", "ts": "1.1"},   # known by id
        {"speaker": "universe", "text": "b", "ts": "1.2"},  # new
    ]
    assert cs.sync_tail(tmp_path, session, live) == 1
    assert cs.sync_tail(tmp_path, session, live) == 0  # b now known by id
    assert [m.text for m in cs.load_recent(tmp_path, session)] == ["a", "b"]


def test_sync_tail_does_not_count_a_failed_write(tmp_path, monkeypatch):
    # A dropped record_turn (returns 0) must NOT be counted as a resync — logging
    # a phantom resync hides the very drift this guards against.
    session = "slack:C1"
    cs.record_turn(tmp_path, session, "founder", "anchor", ts=1.0, ext_id="1.0")
    live = [
        {"speaker": "founder", "text": "anchor", "ts": "1.0"},
        {"speaker": "universe", "text": "new one", "ts": "2.0"},
    ]
    monkeypatch.setattr(cs, "record_turn", lambda *a, **k: 0)  # every write "drops"
    assert cs.sync_tail(tmp_path, session, live) == 0
