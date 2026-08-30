"""Usage budgets in place of graph-shape caps (change `run-usage-budgets`).

Founder 2026-08-30: no limit on how many nodes a user builds into a branch;
"we can limit them in other ways - if they want to run a big graph then that
uses up a lot". This is the other way: per-run and per-hour dispatch and
byte budgets, named in the refusal, tier-raisable, never a shape rule.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from tinyassets import effectors
from tinyassets.branches import NodeDefinition
from tinyassets.effectors import EffectChain, EffectFailedError, dispatch_node_effects

SINK = "authenticated_external_call"


def _packet(verb="GET"):
    return json.dumps({
        "sink": SINK, "connection_id": "c1", "grant_id": "g1", "verb": verb,
        "request": {"method": verb, "url": "https://api.example.test/x"},
    })


def _node(node_id):
    return NodeDefinition(
        node_id=node_id, display_name=node_id, prompt_template="p",
        output_keys=[f"{node_id}_packet"], effects=[SINK],
    )


def _adapter(result):
    def fake(**kw):
        return json.loads(json.dumps(result))
    return fake


_OK = {"delivered": True, "verb": "GET", "request_bytes": 100, "response_bytes": 900,
       "response": {"status": 200, "body": "{}"}}


def test_the_per_run_dispatch_budget_names_itself_and_stops_the_chain(monkeypatch):
    monkeypatch.setitem(effectors._EFFECTORS, SINK, _adapter(_OK))
    monkeypatch.setattr(effectors, "RUN_DISPATCHES_MAX", 3)
    chain = EffectChain(run_id="b1")
    for i in range(3):
        dispatch_node_effects(chain, _node(f"n{i}"), {f"n{i}_packet": _packet()})
    with pytest.raises(EffectFailedError) as exc:
        dispatch_node_effects(chain, _node("n3"), {"n3_packet": _packet()})
    assert exc.value.error_kind == "effect_budget_exhausted"
    assert "budget 3" in exc.value.error and "3 effect dispatches" in exc.value.error
    assert chain.dispatches == 3 and "n3" not in chain.evidence
    assert chain.bytes_out == 3 * 1000


def test_unknown_sizes_charge_the_per_call_caps(monkeypatch):
    unknown = {"delivered": True, "verb": "GET", "response": {"status": 200, "body": "{}"}}
    monkeypatch.setitem(effectors._EFFECTORS, SINK, _adapter(unknown))
    chain = EffectChain(run_id="b2")
    dispatch_node_effects(chain, _node("n0"), {"n0_packet": _packet()})
    assert chain.bytes_out == effectors._UNKNOWN_REQUEST_BYTES + effectors._UNKNOWN_RESPONSE_BYTES
    monkeypatch.setattr(effectors, "RUN_BYTES_MAX", chain.bytes_out)
    with pytest.raises(EffectFailedError, match="outbound bytes"):
        dispatch_node_effects(chain, _node("n1"), {"n1_packet": _packet()})


def test_the_hourly_ledger_charges_and_refuses(monkeypatch, tmp_path):
    from tinyassets import engine_admissions as ea

    db = tmp_path / "ledger.db"
    monkeypatch.setattr(ea, "ledger_path", lambda: db)
    assert ea.dispatch_window_usage("u-1") == (0, 0)          # no ledger yet: empty
    ea.charge_dispatch("u-1", dispatches=1, nbytes=1000)
    ea.charge_dispatch("u-1", dispatches=1, nbytes=24)
    assert ea.dispatch_window_usage("u-1") == (2, 1024)
    assert ea.dispatch_window_usage("u-2") == (0, 0)
    # rows outside the window are pruned on the next charge
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE dispatch_budget SET ts = ts - 7200")
    ea.charge_dispatch("u-1", dispatches=1, nbytes=1)
    assert ea.dispatch_window_usage("u-1") == (1, 1)
    # the chain consults it before firing
    monkeypatch.setitem(effectors._EFFECTORS, SINK, _adapter(_OK))
    monkeypatch.setattr(ea, "DISPATCHES_PER_HOUR", 1)
    chain = EffectChain(run_id="b3", universe_id="u-1")
    with pytest.raises(EffectFailedError, match="hourly budget exhausted"):
        dispatch_node_effects(chain, _node("n0"), {"n0_packet": _packet()})
    chain2 = EffectChain(run_id="b4", universe_id="u-9")
    dispatch_node_effects(chain2, _node("n0"), {"n0_packet": _packet()})   # fresh universe: fine
    assert ea.dispatch_window_usage("u-9") == (1, 1000)


def test_the_adapter_reports_the_bytes_it_moved(monkeypatch):
    """The real effector stamps request_bytes / response_bytes on a delivered
    result (structural pin on the return shape)."""
    import inspect

    from tinyassets.effectors import authenticated_external_call as aec

    src = inspect.getsource(aec)
    assert '"request_bytes": int(request_bytes)' in src
    assert '"response_bytes": int(response_bytes)' in src


def test_the_refusal_is_the_universes_to_act_on():
    from tinyassets.api.runs import _classify_run_outcome_error
    from tinyassets.runs import ACTIONABLE_BY

    cls, action = _classify_run_outcome_error(
        "external write failed - n/authenticated_external_call: run budget exhausted: "
        "500 effect dispatches in this run (budget 500) [effect_budget_exhausted]"
    )
    assert cls == "effect_budget_exhausted" and "budget" in action
    assert ACTIONABLE_BY["effect_budget_exhausted"] == "chatbot"
