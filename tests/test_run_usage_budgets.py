"""Usage budgets in place of graph-shape caps (change `run-usage-budgets`).

Founder 2026-08-30: no limit on how many nodes a user builds into a branch;
"we can limit them in other ways - if they want to run a big graph then that
uses up a lot". This is the other way: per-run and per-hour dispatch and
byte budgets, named in the refusal, tier-raisable, never a shape rule.
"""

from __future__ import annotations

import json

from tinyassets import effectors
from tinyassets.branches import NodeDefinition
from tinyassets.effectors import EffectChain, dispatch_node_effects

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


def test_there_is_no_per_run_dispatch_or_byte_budget(monkeypatch):
    """The per-run counts are gone; the chain still COUNTS what it did.

    ``RUN_DISPATCHES_MAX`` (5000) and ``RUN_BYTES_MAX`` (256 MiB) refused a run
    partway through and told the author to "split the work across runs" -- a
    structural cap on what one run may be (founder, 2026-09-30). The universe's
    rolling-hour ledger is a separate lane and is untouched here.
    """

    monkeypatch.setitem(effectors._EFFECTORS, SINK, _adapter(_OK))
    for gone in ("RUN_DISPATCHES_MAX", "RUN_BYTES_MAX", "RUN_RPC_CALLS_MAX"):
        assert not hasattr(effectors, gone), f"{gone} came back"
    assert not hasattr(effectors, "_budget_refusal"), "no dispatch budget of any kind"

    chain = EffectChain(run_id="b1")
    for i in range(12):
        dispatch_node_effects(chain, _node(f"n{i}"), {f"n{i}_packet": _packet()})
    assert chain.dispatches == 12 and "n11" in chain.evidence
    assert chain.bytes_out == 12 * 1000, "bytes are still observed, just not capped"


def test_unknown_sizes_are_still_charged_at_the_per_call_bounds(monkeypatch):
    """Per-CALL payload bounds stay: they validate one request, not an account."""
    unknown = {"delivered": True, "verb": "GET", "response": {"status": 200, "body": "{}"}}
    monkeypatch.setitem(effectors._EFFECTORS, SINK, _adapter(unknown))
    chain = EffectChain(run_id="b2")
    dispatch_node_effects(chain, _node("n0"), {"n0_packet": _packet()})
    assert chain.bytes_out == effectors._UNKNOWN_REQUEST_BYTES + effectors._UNKNOWN_RESPONSE_BYTES
    # Past the old 256 MiB run ceiling, and nothing refuses.
    for i in range(1, 22):
        dispatch_node_effects(chain, _node(f"n{i}"), {f"n{i}_packet": _packet()})
    assert chain.bytes_out > 256 * 1024 * 1024




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
