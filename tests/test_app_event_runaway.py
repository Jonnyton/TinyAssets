"""Wake chains stop at the owner's usage meter, and say so. No structural cap.

Change `in-platform-agent-systems`, lead requirement 2026-09-30. There are two ways
agents can wake each other without end:

* a self-loop on ``app_event``: an agent whose run emits the very event it is
  subscribed to;
* a ping-pong between two agents: A finishing wakes B, and B finishing wakes A
  (``run_completed``).

The founder's rule is usage limits only, never a depth or chain cap. So these
tests prove two things. First, where a loop cannot be built at all, it is because
no run has the capability, not because of a counter. Second, where it can be
built, the existing meter (``engine_admissions``: hourly write/total and
``RUN_DAY_LIMIT``) stops it, and the stop is a structured, visible refusal.

The meter's LIMITS are lowered here so the loop hits them in a few iterations.
Its mechanism is the real one; only the numbers are smaller.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

import tinyassets.automations as automations_module
from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401
from tests.test_automation_events import _consumer_with_inline_executor
from tests.test_automations import _FakeOutcome, _refusal_rows
from tests.test_in_platform_agent_systems import (  # noqa: F401 - fixtures
    OWNER,
    SCOUT,
    SCRIBE,
    UNIVERSE,
    _as,
    _emit,
    _pin_data_dir,
    _subscribe,
    _wakes,
    home,
)
from tinyassets.automations import AutomationStore, register_automation

pytestmark = pytest.mark.usefixtures("cloud_runtime")


def test_no_run_can_emit_an_app_event_so_a_self_loop_cannot_be_built(monkeypatch) -> None:
    """The self-loop needs a run that emits. None can, by capability:

    * a code node reaches MCP actions only through the alias map, which has no
      emit;
    * an agent node's served ``run_graph`` refuses the operation;
    * only the connector's ``run_graph``, as a signed-in person's own session
      (their app, or a UI they are looking at), emits.
    """
    from tinyassets import engine_mcp_server as engine
    from tinyassets import graph_compiler

    assert not [k for k in graph_compiler._NODE_MCP_ACTION_ALIASES if "emit" in k]
    monkeypatch.setattr(engine, "_binding_error", lambda: None)
    out = json.loads(engine.run_graph(operation="emit_event",
                                      inputs_json=json.dumps({"name": "x"})))
    assert "operation must be" in out.get("error", ""), out


class _PingPong:
    """The ``_execute`` seam. Each wake "runs", and its end goes through the
    REAL ``run_completed`` emitter, stamped with the owner, so the subscribed
    follower is woken exactly as a real finished run would wake it."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.ran: list[str] = []

    def __call__(self, base_path, automation, provider_call, branch, inputs,
                 on_run_started=None):
        from tinyassets.automation_events import emit_run_completed

        run_id = f"run_{len(self.ran)}"
        self.ran.append(automation.branch_def_id)
        if callable(on_run_started):
            on_run_started(run_id)
        emit_run_completed(
            self.base, run_id=run_id, branch_def_id=automation.branch_def_id,
            outcome="completed", actor=OWNER, queue_universe_id=UNIVERSE,
            cause_principal=OWNER,
        )
        return _FakeOutcome(run_id=run_id, status="completed")


def _ping_pong(base: Path) -> None:
    with _as(OWNER):
        for follows, wakes in ((SCOUT, SCRIBE), (SCRIBE, SCOUT)):
            register_automation(
                base, universe_id=UNIVERSE, owner_principal_id=OWNER,
                name=f"{wakes} follows {follows}", branch_def_id=wakes,
                event_type="run_completed", event_filter={"branch_def_id": follows},
                inputs={},
            )
        # The first push: one wake of the scout, as a click or a heartbeat would.
        register_automation(
            base, universe_id=UNIVERSE, owner_principal_id=OWNER, name="start",
            branch_def_id=SCOUT, not_before="2000-01-01T00:00:00+00:00", inputs={},
        )


def _drain(base: Path, polls: int = 60) -> None:
    for _ in range(polls):
        consumer, _inline = _consumer_with_inline_executor(base)
        try:
            submitted = consumer.poll_once()
        finally:
            consumer.stop()
        if not submitted:
            return


@pytest.mark.parametrize("meter", ["hourly", "daily"])
def test_a_ping_pong_stops_at_the_meter_with_a_visible_refusal(
    home: Path, monkeypatch, meter: str,  # noqa: F811 - the imported fixture
) -> None:
    from tinyassets import engine_admissions as ea
    from tinyassets import engine_mcp_server as ems
    from tinyassets.api.automations import automations as automations_api

    budget = 6
    if meter == "hourly":
        # The pump admits through engine_mcp_server's copy of the limit; the
        # owner's notice reads engine_admissions'. Production sets both from one
        # constant, so the test lowers both.
        monkeypatch.setattr(ems, "_RUN_GRAPH_RATE_MAX", budget)
        monkeypatch.setattr(ea, "RUN_WRITE_LIMIT", budget)
    else:
        monkeypatch.setattr(ea, "RUN_DAY_LIMIT", budget)
    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.list_serving_universes",
        lambda _base: [UNIVERSE],
    )
    seam = _PingPong(home)
    monkeypatch.setattr(automations_module, "_execute", seam)

    _ping_pong(home)
    _drain(home)

    # It ran, alternating, until the meter said no, and then stopped.
    assert 2 <= len(seam.ran) <= budget, seam.ran
    assert seam.ran[:2] == [SCOUT, SCRIBE]
    ran = len(seam.ran)
    _drain(home)
    assert len(seam.ran) == ran, "nothing runs past the meter"

    # The refusal is recorded against the wake that was turned away, in words
    # an owner's read carries, and the subscriptions themselves stay active:
    # a meter refills, and a full one is not a reason to delete work.
    reasons = _refusal_rows(home)
    assert "run_rate_limited" in reasons.values(), reasons
    with _as(OWNER):
        listed = automations_api(action="list", universe_id=UNIVERSE, payload="{}")
    rows = {row["name"]: row for row in listed["automations"]}
    assert rows[f"{SCRIBE} follows {SCOUT}"]["desired_state"] == "active"
    assert rows[f"{SCOUT} follows {SCRIBE}"]["desired_state"] == "active"
    refused = [row for row in listed["automations"]
               if "run_rate_limited" in (row.get("recent_reason"), row.get("last_reason"))]
    assert refused, listed
    assert all("usage_notice" in row for row in refused), refused
    assert "usage limit" in refused[0]["usage_notice"]["message"]


def test_a_screen_emitting_in_a_loop_stops_at_the_meter(home: Path, monkeypatch) -> None:  # noqa: F811
    """The one place an emit loop CAN be written: UI code on the owner's own
    screen calling emit again and again. Each emit is metered before a wake
    exists; the refusal is structured and names the limit."""
    from tinyassets import engine_admissions as ea

    budget = 5
    monkeypatch.setattr(ea, "RUN_TOTAL_LIMIT", budget)
    _subscribe(home, "x")
    replies = [_emit("x") for _ in range(budget + 3)]
    admitted = [r for r in replies if r.get("emitted")]
    refused = [r for r in replies if r.get("error")]
    assert 1 <= len(admitted) < budget + 3
    assert refused and all(r["error"] == "usage_limit" and r["limit"] for r in refused), refused
    assert "usage limit" in refused[0]["detail"]
    # Every stored wake was paid for; no wake exists past the refusal.
    assert len(_wakes(home)) == len(admitted)


def test_how_fast_the_real_meter_fills(home: Path, capsys) -> None:  # noqa: F811
    """Measurement, not a gate: at the real limits, how long does a tight emit
    loop take to spend the hourly total? Printed for the lead's decision."""
    from tinyassets import engine_admissions as ea

    _subscribe(home, "x")
    n = 40
    started = time.perf_counter()
    for _ in range(n):
        assert _emit("x").get("emitted"), "the real meter must admit a short burst"
    per_emit = (time.perf_counter() - started) / n
    with capsys.disabled():
        print(f"\n[meter] {per_emit * 1000:.1f} ms per emit locally; the hourly total "
              f"({ea.RUN_TOTAL_LIMIT}) fills in ~{per_emit * ea.RUN_TOTAL_LIMIT:.0f}s, "
              f"the daily limit ({ea.RUN_DAY_LIMIT}) needs "
              f"{ea.RUN_DAY_LIMIT / ea.RUN_TOTAL_LIMIT:.1f} hourly windows")
    assert len(AutomationStore(home).list(universe_id=UNIVERSE)) >= n
