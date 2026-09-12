"""Native terminal evidence and mixed durable history, without executing providers."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from tests.test_agent_turn_journal import (
    begin,
    candidate,
    finish,
    journal,
    new,
    receive,
    reply,
    result,
    start,
)
from tinyassets.providers.agent_capacity_boundary import NativeCompletionEvidence
from tinyassets.storage.agent_native_records import NativeInput, NativeTerminal
from tinyassets.storage.agent_turn_journal import JournalUnavailable, reset_blockers
from tinyassets.storage.current_home import CurrentHomeChanged

__all__ = ["journal"]  # Reuse the real owner/home journal fixture.


def native_candidate(source="native:future", model=""):
    old = candidate(source, model)
    return NativeInput(**{
        key: getattr(old, key) for key in NativeInput.__dataclass_fields__
    })


def proof(**changes):
    return replace(NativeCompletionEvidence("native:future", True, True, "none"), **changes)


def safe_capacity(**changes):
    return replace(NativeTerminal(
        "capacity_no_effects", evidence=proof(), failure_class="provider_rate_limited",
        capacity_scope="account", retry_after_s=12,
    ), **changes)


def completed(**changes):
    return replace(NativeTerminal(
        "completed", evidence=proof(side_effect_state="committed"),
        text="exact native answer\n🪐", configured_model="provider-default",
    ), **changes)


def begin_native(journal, turn, *, retry=False):
    return journal.begin_round(
        "owner", "home", turn.turn_id, expected_generation=turn.generation,
        candidate=native_candidate(), after_failed_inference=retry,
    )


def end_native(journal, turn, terminal, **kwargs):
    return journal.finish_native(
        "owner", "home", turn.turn_id, expected_generation=turn.generation,
        ordinal=len(turn.rounds), terminal=terminal, **kwargs,
    )


def blockers(journal):
    with journal._ledger.connection() as conn:
        return reset_blockers(conn, "owner", "home")


@pytest.mark.parametrize("model", ["", "a-future-release"])
def test_native_candidate_round_trip_keeps_provider_default(model):
    value = native_candidate(model=model)
    raw = value.canonical_json()
    assert NativeInput.from_json(raw) == value
    assert json.loads(raw)["version"] == 2
    assert json.loads(raw)["kind"] == "native_agent"
    assert json.loads(raw)["model"] == model
    assert "tools_json" not in json.loads(raw)


@pytest.mark.parametrize("changes", [
    {"model": None}, {"model": " "}, {"model": "x\n"}, {"source_ref": ""},
    {"binding_id": ""}, {"reservation_id": ""}, {"binding_generation": True},
    {"binding_generation": 0}, {"binding_digest": "sha256:a"}, {"request_digest": None},
])
def test_native_candidate_rejects_malformed(changes):
    with pytest.raises(ValueError):
        replace(native_candidate(), **changes).canonical_json()


@pytest.mark.parametrize("terminal", [
    completed(), completed(reported_model="actual-remote-model", input_tokens=0, output_tokens=4),
    safe_capacity(), NativeTerminal("indeterminate"),
    NativeTerminal("indeterminate", evidence=proof(protocol_complete=False, process_reaped=False)),
])
def test_terminal_round_trip_is_explicit(terminal):
    raw = terminal.canonical_json(native_candidate())
    assert NativeTerminal.from_json(raw, native_candidate()) == terminal
    assert json.loads(raw)["accounting"] == "executor_accounting"
    assert "requested_model" not in json.loads(raw)  # It belongs to the exact input record.


@pytest.mark.parametrize("terminal", [
    safe_capacity(evidence=None), safe_capacity(evidence=proof(provider="another")),
    safe_capacity(evidence=proof(protocol_complete=False)),
    safe_capacity(evidence=proof(process_reaped=False)),
    safe_capacity(evidence=proof(protocol_complete=1)),
    safe_capacity(evidence=proof(side_effect_state="possible")),
    safe_capacity(evidence=proof(side_effect_state="committed")),
    safe_capacity(evidence=proof(side_effect_state="unknown")),
    safe_capacity(failure_class="timeout"), safe_capacity(failure_class=None),
    safe_capacity(capacity_scope="new"), safe_capacity(retry_after_s=float("inf")),
    safe_capacity(text="not a failed empty attempt"),
    completed(evidence=None), completed(evidence=proof(process_reaped=False)),
    completed(text=None), completed(configured_model=None), completed(reported_model=""),
    completed(input_tokens=True), completed(failure_class="provider_rate_limited"),
    NativeTerminal("indeterminate", retry_after_s=1), NativeTerminal("unknown-kind"),
])
def test_terminal_never_promotes_missing_or_contradictory_evidence(terminal):
    with pytest.raises(ValueError):
        terminal.canonical_json(native_candidate())


def test_native_success_receipt_is_not_a_fabricated_http_reply(journal):
    turn = begin_native(journal, new(journal)).snapshot
    assert turn.state == "native_started" and blockers(journal)
    done = end_native(journal, turn, completed(), cost_microusd=27).snapshot
    assert done.state == "completed" and not blockers(journal)
    assert done.rounds[0].candidate.model == ""
    assert done.rounds[0].reply.reported_model is None
    assert done.rounds[0].cost_microusd == 27
    assert not done.rounds[0].tools
    assert journal.get("owner", "home", turn.turn_id) == done
    assert "answer" not in repr(done.rounds[0].reply)
    assert begin_native(journal, done, retry=True).status == "conflict"


def test_reaped_success_with_incomplete_effects_ends_turn_but_never_allows_retry(journal):
    turn = begin_native(journal, new(journal)).snapshot
    terminal = completed(evidence=proof(protocol_complete=False, side_effect_state="unknown"))
    turn = end_native(journal, turn, terminal).snapshot
    assert turn.state == "completed" and not blockers(journal)
    assert begin_native(journal, turn, retry=True).status == "conflict"
    assert journal.get("owner", "home", turn.turn_id) == turn


@pytest.mark.parametrize("terminal", [None, NativeTerminal("indeterminate")])
def test_native_started_and_unknown_block_reset_and_cannot_retry(journal, terminal):
    turn = begin_native(journal, new(journal)).snapshot
    if terminal is not None:
        turn = end_native(journal, turn, terminal).snapshot
        assert turn.state == "held_native_unknown"
    assert blockers(journal)
    assert begin_native(journal, turn, retry=True).status == "conflict"
    assert begin_native(journal, turn).status == "conflict"
    assert journal.abandon(
        "owner", "home", turn.turn_id, expected_generation=turn.generation,
    ).status == "conflict"
    assert journal.get("owner", "home", turn.turn_id) == turn


def test_explicit_native_capacity_can_precede_http_or_native(journal):
    turn = begin_native(journal, new(journal)).snapshot
    turn = end_native(journal, turn, safe_capacity()).snapshot
    assert turn.state == "held_native_capacity" and not blockers(journal)
    assert begin_native(journal, turn).status == "conflict"
    turn = begin_native(journal, turn, retry=True).snapshot
    turn = end_native(journal, turn, safe_capacity()).snapshot
    turn = journal.begin_round(
        "owner", "home", turn.turn_id, expected_generation=turn.generation,
        candidate=candidate(), after_failed_inference=True,
    ).snapshot
    turn = receive(journal, turn, reply(count=0, text="HTTP finished"))
    assert turn.state == "completed" and len(turn.rounds) == 3
    assert journal.get("owner", "home", turn.turn_id) == turn


def test_mixed_history_preserves_exact_http_bytes_without_rewriting(journal):
    turn = receive(journal, begin(journal, new(journal)))
    turn = start(journal, turn).snapshot
    turn = finish(journal, turn, result=result()).snapshot
    with journal._ledger.connection() as conn:
        original = tuple(conn.execute(
            "SELECT candidate_json, reply_json FROM agent_turn_rounds WHERE ordinal=1",
        ).fetchone())
    old_round = turn.rounds[0]
    turn = begin_native(journal, turn).snapshot
    turn = end_native(journal, turn, safe_capacity()).snapshot
    turn = journal.begin_round(
        "owner", "home", turn.turn_id, expected_generation=turn.generation,
        candidate=candidate(), after_failed_inference=True,
    ).snapshot
    turn = receive(journal, turn, reply(count=0, text="finished"))
    assert turn.rounds[0] == old_round
    with journal._ledger.connection() as conn:
        assert tuple(conn.execute(
            "SELECT candidate_json, reply_json FROM agent_turn_rounds WHERE ordinal=1",
        ).fetchone()) == original
    assert journal.get("owner", "home", turn.turn_id) == turn


def test_one_native_start_winner_and_exact_terminal_idempotency(journal):
    initial = new(journal)
    with ThreadPoolExecutor(max_workers=2) as pool:
        starts = list(pool.map(lambda _: begin_native(journal, initial), range(2)))
    assert sorted(item.status for item in starts) == ["applied", "conflict"]
    turn = journal.get("owner", "home", initial.turn_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        ends = list(pool.map(lambda _: end_native(journal, turn, completed()), range(2)))
    assert sorted(item.status for item in ends) == ["already_applied", "applied"]
    assert end_native(journal, turn, completed(text="different")).status == "conflict"


def test_wrong_kind_finalizers_cannot_overwrite_progress(journal):
    native = begin_native(journal, new(journal)).snapshot
    for response in (None, reply()):
        assert journal.finish_inference(
            "owner", "home", native.turn_id, expected_generation=native.generation,
            ordinal=1, reply=response,
        ).status == "conflict"
    http = begin(journal, new(journal))
    assert end_native(journal, http, completed()).status == "conflict"
    assert journal.get("owner", "home", native.turn_id) == native
    assert journal.get("owner", "home", http.turn_id) == http


@pytest.mark.parametrize("changes", [
    {"version": 1}, {"version": True}, {"kind": "engine_inference"},
    {"accounting": "provider_reported"}, {"extra": "discard me"},
    {"evidence": None}, {"evidence": {"provider": "native:future"}},
    {"status": "completed"},
])
def test_corrupt_native_terminal_is_unreadable_and_reset_blocking(journal, changes):
    turn = begin_native(journal, new(journal)).snapshot
    turn = end_native(journal, turn, safe_capacity()).snapshot
    value = json.loads(safe_capacity().canonical_json(native_candidate())) | changes
    with journal._ledger.connection() as conn:
        conn.execute("UPDATE agent_turn_rounds SET reply_json = ?", (
            json.dumps(value, separators=(",", ":")),
        ))
    with pytest.raises(JournalUnavailable):
        journal.get("owner", "home", turn.turn_id)
    assert blockers(journal)


@pytest.mark.parametrize("status", ["completed", "indeterminate"])
def test_corrupt_native_prefix_cannot_hide_previous_completion_or_uncertainty(journal, status):
    turn = begin_native(journal, new(journal)).snapshot
    turn = end_native(journal, turn, safe_capacity()).snapshot
    turn = begin_native(journal, turn, retry=True).snapshot
    wrong = completed() if status == "completed" else NativeTerminal("indeterminate")
    with journal._ledger.connection() as conn:
        conn.execute("UPDATE agent_turn_rounds SET reply_json=? WHERE ordinal=1", (
            wrong.canonical_json(native_candidate()),
        ))
    with pytest.raises(JournalUnavailable):
        journal.get("owner", "home", turn.turn_id)
    assert blockers(journal)


def test_native_cannot_acquire_fake_http_tools(journal):
    turn = begin_native(journal, new(journal)).snapshot
    with journal._ledger.connection() as conn:
        conn.execute(
            "INSERT INTO agent_turn_tools VALUES ('owner','home',?,1,1,1,"
            "'call','tool','{}','planned',NULL,NULL,NULL)", (turn.turn_id,),
        )
    with pytest.raises(JournalUnavailable):
        journal.get("owner", "home", turn.turn_id)
    assert blockers(journal)


def test_scope_and_stale_finish_stay_fenced(journal):
    turn = begin_native(journal, new(journal)).snapshot
    assert journal.get("other", "home", turn.turn_id) is None
    assert journal.get("owner", "other", turn.turn_id) is None
    with pytest.raises(CurrentHomeChanged):
        journal.finish_native(
            "other", "home", turn.turn_id, expected_generation=turn.generation,
            ordinal=1, terminal=completed(),
        )
    assert journal.finish_native(
        "owner", "home", turn.turn_id, expected_generation=turn.generation - 1,
        ordinal=1, terminal=completed(),
    ).status == "conflict"


@pytest.mark.parametrize("change", ["removed", "rebound", "deleted"])
@pytest.mark.parametrize("operation", ["begin", "finish"])
def test_native_mutations_recheck_current_home(journal, change, operation):
    from tinyassets.account_deletion import principal_digest

    turn = new(journal)
    if operation == "finish":
        turn = begin_native(journal, turn).snapshot
    with journal._ledger.connection() as conn:
        if change == "removed":
            conn.execute("DELETE FROM founder_home WHERE founder_sub='owner'")
        elif change == "rebound":
            conn.execute("UPDATE founder_home SET universe_id='new-home' WHERE founder_sub='owner'")
        else:
            conn.execute(
                "INSERT INTO deleted_principals (founder_sub, deleted_at) VALUES (?, 'now')",
                (principal_digest("owner"),),
            )
    with pytest.raises(CurrentHomeChanged):
        if operation == "begin":
            begin_native(journal, turn)
        else:
            end_native(journal, turn, completed())
    assert journal.get("owner", "home", turn.turn_id) == turn


@pytest.mark.parametrize("changes", [
    {"version": 1}, {"version": True}, {"version": 3}, {"kind": "engine_inference"},
    {"model": None}, {"tools_json": '{}'}, {"request_digest": "unknown"},
])
def test_corrupt_native_candidate_is_never_an_http_fallback(journal, changes):
    turn = begin_native(journal, new(journal)).snapshot
    value = json.loads(native_candidate().canonical_json()) | changes
    with journal._ledger.connection() as conn:
        conn.execute("UPDATE agent_turn_rounds SET candidate_json=?", (
            json.dumps(value, separators=(",", ":")),
        ))
    with pytest.raises(JournalUnavailable):
        journal.get("owner", "home", turn.turn_id)
    assert blockers(journal)
