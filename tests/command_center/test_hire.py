"""Tests for the hire flow: provider discovery, preset writes, validation."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from command_center import collector


def _cfg(tmp_path: Path) -> collector.Config:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "scripts").mkdir()
    cfg = collector.Config(
        root=root,
        directory_url=None,
        inbox_dir=root / ".agents" / "village-inbox",
        claude_home=tmp_path / "c",
        codex_home=tmp_path / "x",
        kimi_home=tmp_path / "k",
        data_dirs=[tmp_path / "data"],
    )
    return cfg


def _universe(cfg: collector.Config, uid: str = "u-hire1") -> Path:
    udir = cfg.data_dirs[0] / uid
    udir.mkdir(parents=True, exist_ok=True)
    (udir / "soul.md").write_text("A quiet test universe about nothing much at all.\n",
                                  encoding="utf-8")
    return udir


def test_discover_providers_shape(tmp_path: Path):
    cfg = _cfg(tmp_path)
    providers = collector.discover_providers(cfg)
    by_id = {p["id"]: p for p in providers}
    assert "claude" in by_id and "market" in by_id and "hosted" in by_id
    assert by_id["market"]["available"] is False
    assert "coming" in by_id["market"]["note"]
    for p in providers:
        assert {"id", "label", "kind", "available", "dispatchable", "note"} <= set(p)


_FAKE_ENGINES = [
    {"id": "claude", "label": "Claude Code", "kind": "local-cli",
     "available": True, "dispatchable": True, "note": "/fake/claude"},
    {"id": "ollama", "label": "Ollama", "kind": "local-cli",
     "available": True, "dispatchable": False, "note": "/fake/ollama"},
    {"id": "market", "label": "Market capacity", "kind": "market",
     "available": False, "dispatchable": False, "note": "coming with the compute market"},
]


@pytest.fixture()
def fake_engines(monkeypatch):
    monkeypatch.setattr(
        collector, "discover_providers", lambda cfg: [dict(e) for e in _FAKE_ENGINES]
    )


def test_hire_preset_writes_config(tmp_path: Path, fake_engines):
    cfg = _cfg(tmp_path)
    udir = _universe(cfg)
    result = collector.hire(
        cfg, {"universe_id": "u-hire1", "provider": "claude", "preset": True}
    )
    assert result["ok"] is True, result
    assert result["mode"] == "preset"
    assert "preferred_writer: claude" in (udir / "config.yaml").read_text(encoding="utf-8")
    # a second preset replaces, not appends
    collector.hire(cfg, {"universe_id": "u-hire1", "provider": "ollama", "preset": True})
    text = (udir / "config.yaml").read_text(encoding="utf-8")
    assert "preferred_writer: ollama" in text
    assert text.count("preferred_writer") == 1


def test_hire_rejects_market_and_unknown(tmp_path: Path, fake_engines):
    cfg = _cfg(tmp_path)
    cfg.dispatch = True
    _universe(cfg)
    market = collector.hire(cfg, {"universe_id": "u-hire1", "provider": "market"})
    assert market["ok"] is False
    assert "coming" in market["error"]
    unknown = collector.hire(cfg, {"universe_id": "u-hire1", "provider": "wat"})
    assert unknown["ok"] is False
    missing = collector.hire(cfg, {"universe_id": "u-nope", "provider": "claude"})
    assert missing["ok"] is False


def test_hire_dispatch_needs_dispatchable_engine(tmp_path: Path, fake_engines):
    cfg = _cfg(tmp_path)
    cfg.dispatch = True
    _universe(cfg)
    result = collector.hire(cfg, {"universe_id": "u-hire1", "provider": "ollama"})
    assert result["ok"] is False
    assert "preset" in result["error"]


def _wait_until(predicate, *, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition did not become true before the test deadline")


def _dispatchable_engine() -> dict:
    return {
        "id": "claude",
        "label": "Claude Code",
        "kind": "local-cli",
        "available": True,
        "dispatchable": True,
        "note": "/fake/claude",
    }


def _local_universe(udir: Path) -> dict:
    return {
        "id": udir.name,
        "name": "Test Universe",
        "premise": "No real provider is ever invoked.",
        "source": "local",
        "path": str(udir),
    }


def _join_village_threads() -> None:
    for thread in list(threading.enumerate()):
        if thread.name.startswith(("village-dispatch-", "village-hire-")):
            thread.join(timeout=3)


def _dispatch_setup(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    cfg.dispatch = True
    udir = _universe(cfg)
    universe = _local_universe(udir)
    engine = _dispatchable_engine()
    (cfg.root / "scripts" / "peer_agent.py").write_text(
        "# fake only\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        collector,
        "_agent_by_id",
        lambda _cfg, ident: {
            "id": ident,
            "name": ident,
            "provider": "claude",
            "action": "testing",
        },
    )
    monkeypatch.setattr(collector, "discover_universes", lambda *_: [universe])
    monkeypatch.setattr(collector, "discover_providers", lambda *_: [engine])
    return cfg, udir


def test_dispatch_off_talk_is_inbox_only_and_never_starts_a_worker(
    tmp_path: Path, monkeypatch
):
    cfg = _cfg(tmp_path)
    cfg.dispatch = False
    monkeypatch.setattr(
        collector,
        "_agent_by_id",
        lambda _cfg, ident: {
            "id": ident,
            "name": "Fake Agent",
            "provider": "claude",
            "action": "testing",
        },
    )

    class ForbiddenThread:
        def __init__(self, *args, **kwargs):
            raise AssertionError("dispatch-off talk constructed a provider worker")

    monkeypatch.setattr(collector.threading, "Thread", ForbiddenThread)

    result = collector.talk(cfg, "agent:fake-1", "keep this local")

    assert result == {"ok": True, "mode": "inbox", "to": "Fake Agent"}
    assert "keep this local" in (
        cfg.inbox_dir / "fake-1.md"
    ).read_text(encoding="utf-8")


def test_dispatch_off_hire_rejects_before_discovery_lookup_writes_or_threads(
    tmp_path: Path, monkeypatch
):
    cfg = _cfg(tmp_path)
    cfg.dispatch = False

    def forbidden(*args, **kwargs):
        raise AssertionError("dispatch-off hire crossed a side-effect boundary")

    monkeypatch.setattr(collector, "discover_universes", forbidden)
    monkeypatch.setattr(collector, "discover_providers", forbidden)
    monkeypatch.setattr(collector, "_append_inbox", forbidden)
    monkeypatch.setattr(collector.threading, "Thread", forbidden)

    result = collector.hire(
        cfg,
        {
            "universe_id": "u-hire1",
            "provider": "claude",
            "count": 1,
            "task": "must not dispatch",
            "preset": False,
        },
    )

    assert result["ok"] is False
    assert "dispatch" in result["error"].lower()


def test_hire_dispatch_boundary_rechecks_process_level_gate(
    tmp_path: Path, monkeypatch
):
    cfg = _cfg(tmp_path)
    cfg.dispatch = False
    universe = _local_universe(_universe(cfg))
    (cfg.root / "scripts" / "peer_agent.py").write_text("# fake only\n", encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("_hire_dispatch crossed a side-effect boundary")

    monkeypatch.setattr(collector, "_append_inbox", forbidden)
    monkeypatch.setattr(collector.threading, "Thread", forbidden)

    result = collector._hire_dispatch(
        cfg, universe, _dispatchable_engine(), "must not dispatch", 1
    )

    assert result["ok"] is False
    assert "dispatch" in result["error"].lower()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("preset", "false"),
        ("preset", 0),
        ("count", True),
        ("count", "2"),
        ("count", 0),
        ("count", 9),
        ("task", 7),
        ("task", "x" * 2001),
        ("task", "nul\0task"),
        ("task", "surrogate\ud800task"),
    ],
)
def test_hire_rejects_type_confusion_and_unsafe_scalars_before_discovery(
    tmp_path: Path, monkeypatch, field: str, value
):
    cfg = _cfg(tmp_path)
    cfg.dispatch = True
    payload = {
        "universe_id": "u-hire1",
        "provider": "claude",
        "count": 1,
        "task": "safe",
        "preset": False,
    }
    payload[field] = value

    def forbidden(*args, **kwargs):
        raise AssertionError(f"invalid {field} crossed the collector boundary")

    monkeypatch.setattr(collector, "discover_universes", forbidden)
    monkeypatch.setattr(collector, "discover_providers", forbidden)

    result = collector.hire(cfg, payload)

    assert result["ok"] is False
    assert field in result["error"].lower()


def test_talk_and_hire_share_one_atomic_eight_process_tree_pool(
    tmp_path: Path, monkeypatch
):
    cfg, udir = _dispatch_setup(tmp_path, monkeypatch)

    release = threading.Event()
    eight_entered = threading.Event()
    lock = threading.Lock()
    entered = 0

    def fake_run_peer(cmd, *, cwd, timeout, env):
        nonlocal entered
        assert "--timeout" in cmd and cmd[cmd.index("--timeout") + 1] == "540"
        assert timeout == 600
        with lock:
            entered += 1
            if entered == 8:
                eight_entered.set()
        release.wait(timeout=3)
        return ""

    monkeypatch.setattr(collector, "_run_peer", fake_run_peer, raising=False)

    try:
        for index in range(4):
            assert collector.talk(
                cfg, f"agent:talk-{index}", f"message {index}"
            )["ok"]
        hire_result = collector.hire(
            cfg,
            {
                "universe_id": "u-hire1",
                "provider": "claude",
                "count": 4,
                "task": "fill remaining capacity",
                "preset": False,
            },
        )
        assert hire_result["ok"] is True
        assert eight_entered.wait(timeout=3), "eight fake process trees did not enter"

        chat_path = udir / "village-inbox.md"
        chat_before = (
            chat_path.read_text(encoding="utf-8") if chat_path.exists() else ""
        )
        over_hire = collector.hire(
            cfg,
            {
                "universe_id": "u-hire1",
                "provider": "claude",
                "count": 1,
                "task": "must be all-or-nothing",
                "preset": False,
            },
        )
        over_talk = collector.talk(
            cfg, "agent:over-cap", "this write must remain inbox-only"
        )
        time.sleep(0.1)

        assert over_hire["ok"] is False
        assert "capacity" in over_hire["error"].lower()
        assert (
            chat_path.read_text(encoding="utf-8") if chat_path.exists() else ""
        ) == chat_before
        assert over_talk["ok"] is True
        assert over_talk["mode"] == "inbox"
        assert "capacity" in over_talk.get("note", "").lower()
        assert "this write must remain inbox-only" in (
            cfg.inbox_dir / "over-cap.md"
        ).read_text(encoding="utf-8")
        with lock:
            assert entered == 8
    finally:
        release.set()
        _join_village_threads()


def test_hire_reservation_is_all_or_nothing_when_only_two_slots_are_free(
    tmp_path: Path, monkeypatch
):
    cfg, udir = _dispatch_setup(tmp_path, monkeypatch)

    release = threading.Event()
    six_entered = threading.Event()
    lock = threading.Lock()
    entered = 0

    def fake_run_peer(cmd, *, cwd, timeout, env):
        nonlocal entered
        with lock:
            entered += 1
            if entered == 6:
                six_entered.set()
        release.wait(timeout=3)
        return ""

    monkeypatch.setattr(collector, "_run_peer", fake_run_peer, raising=False)

    try:
        for index in range(6):
            collector.talk(cfg, f"agent:holder-{index}", "hold a fake slot")
        assert six_entered.wait(timeout=3)
        chat_path = udir / "village-inbox.md"

        result = collector.hire(
            cfg,
            {
                "universe_id": "u-hire1",
                "provider": "claude",
                "count": 3,
                "task": "three do not fit in two slots",
                "preset": False,
            },
        )
        time.sleep(0.1)

        assert result["ok"] is False
        assert "capacity" in result["error"].lower()
        assert not chat_path.exists(), "rejected hire wrote its chat/inbox record"
        with lock:
            assert entered == 6, "hire partially dispatched before rejecting"
    finally:
        release.set()
        _join_village_threads()


def test_talk_thread_start_failure_releases_reserved_slot(
    tmp_path: Path, monkeypatch
):
    cfg, _ = _dispatch_setup(tmp_path, monkeypatch)
    capacity = collector._DispatchCapacity()
    monkeypatch.setattr(collector, "_DISPATCH_CAPACITY", capacity)

    class StartFails:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("synthetic thread start failure")

    monkeypatch.setattr(collector.threading, "Thread", StartFails)

    with pytest.raises(RuntimeError, match="synthetic thread start failure"):
        collector.talk(cfg, "agent:start-fails", "do not leak this reservation")

    assert capacity.reserve(8), "talk leaked one shared capacity slot"
    capacity.release(8)


def test_hire_inbox_write_failure_releases_all_reserved_slots(
    tmp_path: Path, monkeypatch
):
    cfg, udir = _dispatch_setup(tmp_path, monkeypatch)
    capacity = collector._DispatchCapacity()
    monkeypatch.setattr(collector, "_DISPATCH_CAPACITY", capacity)

    def fail_inbox_write(*args, **kwargs):
        raise OSError("synthetic inbox write failure")

    monkeypatch.setattr(collector, "_append_inbox", fail_inbox_write)

    with pytest.raises(OSError, match="synthetic inbox write failure"):
        collector._hire_dispatch(
            cfg,
            _local_universe(udir),
            _dispatchable_engine(),
            "do not leak these reservations",
            3,
        )

    assert capacity.reserve(8), "hire inbox failure leaked reserved capacity"
    capacity.release(8)


def test_hire_thread_start_failure_releases_only_unstarted_reservations(
    tmp_path: Path, monkeypatch
):
    cfg, udir = _dispatch_setup(tmp_path, monkeypatch)
    capacity = collector._DispatchCapacity()
    monkeypatch.setattr(collector, "_DISPATCH_CAPACITY", capacity)

    worker_entered = threading.Event()
    worker_release = threading.Event()
    real_thread = threading.Thread
    started_threads: list[threading.Thread] = []
    start_calls = 0

    def fake_run_peer(cmd, *, cwd, timeout, env):
        worker_entered.set()
        worker_release.wait(timeout=3)
        return ""

    class SecondStartFails:
        def __init__(self, *args, **kwargs):
            self._thread = real_thread(*args, **kwargs)
            started_threads.append(self._thread)

        def start(self):
            nonlocal start_calls
            start_calls += 1
            if start_calls == 2:
                raise RuntimeError("synthetic second thread start failure")
            self._thread.start()

    monkeypatch.setattr(collector, "_run_peer", fake_run_peer, raising=False)
    monkeypatch.setattr(collector.threading, "Thread", SecondStartFails)

    try:
        with pytest.raises(RuntimeError, match="synthetic second thread start failure"):
            collector._hire_dispatch(
                cfg,
                _local_universe(udir),
                _dispatchable_engine(),
                "hold only the successfully started worker reservation",
                3,
            )

        assert worker_entered.wait(timeout=3)
        assert capacity.reserve(7), "hire leaked an unstarted worker reservation"
        assert not capacity.reserve(1), (
            "hire released the successfully started worker reservation too early"
        )
        capacity.release(7)
    finally:
        worker_release.set()
        for thread in started_threads:
            if thread.is_alive():
                thread.join(timeout=3)

    assert capacity.reserve(8), "started hire worker did not release in finally"
    capacity.release(8)


@pytest.mark.parametrize("worker_outcome", ["success", "failure"])
def test_dispatch_slot_releases_after_worker_finishes(
    tmp_path: Path, monkeypatch, worker_outcome: str
):
    cfg, _ = _dispatch_setup(tmp_path, monkeypatch)

    first_done = threading.Event()
    second_release = threading.Event()
    eight_entered = threading.Event()
    lock = threading.Lock()
    calls = 0
    second_wave = 0

    def fake_run_peer(cmd, *, cwd, timeout, env):
        nonlocal calls, second_wave
        with lock:
            calls += 1
            call = calls
            if call > 1:
                second_wave += 1
                if second_wave == 8:
                    eight_entered.set()
        if call == 1:
            first_done.set()
            if worker_outcome == "failure":
                raise RuntimeError("synthetic fake-peer failure")
            return ""
        second_release.wait(timeout=3)
        return ""

    monkeypatch.setattr(collector, "_run_peer", fake_run_peer, raising=False)

    try:
        collector.talk(cfg, "agent:first", "finish one reservation")
        assert first_done.wait(timeout=3)
        _wait_until(
            lambda: not any(
                t.name == "village-dispatch-first" for t in threading.enumerate()
            )
        )

        result = collector.hire(
            cfg,
            {
                "universe_id": "u-hire1",
                "provider": "claude",
                "count": 8,
                "task": "all eight slots should be reusable",
                "preset": False,
            },
        )

        assert result["ok"] is True
        assert eight_entered.wait(timeout=3), (
            f"slot leaked after fake-peer {worker_outcome}"
        )
    finally:
        second_release.set()
        _join_village_threads()


def test_village_wrapper_scrubs_its_bearers_preserves_provider_auth_and_nests_timeouts(
    tmp_path: Path, monkeypatch
):
    cfg, _ = _dispatch_setup(tmp_path, monkeypatch)
    monkeypatch.setenv("TINYASSETS_VILLAGE_TOKEN", "village-secret")
    monkeypatch.setenv("WORKFLOW_MCP_TOKEN", "mcp-secret")
    monkeypatch.setenv("FAKE_PROVIDER_SUBSCRIPTION_AUTH", "provider-auth-survives")

    captured: dict = {}
    finished = threading.Event()

    def fake_run_peer(cmd, *, cwd, timeout, env):
        captured.update(cmd=cmd, cwd=cwd, timeout=timeout, env=dict(env))
        finished.set()
        return ""

    monkeypatch.setattr(collector, "_run_peer", fake_run_peer, raising=False)

    collector.talk(cfg, "agent:env-probe", "inspect fake environment only")
    assert finished.wait(timeout=3)
    _join_village_threads()

    assert "TINYASSETS_VILLAGE_TOKEN" not in captured["env"]
    assert "WORKFLOW_MCP_TOKEN" not in captured["env"]
    assert (
        captured["env"]["FAKE_PROVIDER_SUBSCRIPTION_AUTH"]
        == "provider-auth-survives"
    )
    assert captured["timeout"] == 600
    inner_timeout = int(
        captured["cmd"][captured["cmd"].index("--timeout") + 1]
    )
    assert inner_timeout == 540
    assert inner_timeout < captured["timeout"]
