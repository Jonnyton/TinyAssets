"""Tests for the hire flow: provider discovery, preset writes, validation."""

from __future__ import annotations

import signal
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


def test_live_universe_auth_error_names_environment_input_not_removed_cli_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    cfg = _cfg(tmp_path)
    cfg.directory_url = "https://example.invalid"
    monkeypatch.setattr(
        collector,
        "discover_universes",
        lambda _cfg, _now: [
            {
                "id": "u-live",
                "name": "Live Proof",
                "source": "live",
            }
        ],
    )

    class RefusingClient:
        def __init__(self, _url: str, *, token: str | None):
            self.token = token

        def call_tool(self, _name: str, _arguments: dict) -> None:
            return None

    monkeypatch.setattr(collector, "McpClient", RefusingClient)

    result = collector.talk(cfg, "universe:u-live", "hello")

    assert result["ok"] is False
    assert "WORKFLOW_MCP_TOKEN" in result["error"]
    assert "--mcp-token" not in result["error"]


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


def test_post_spawn_communicate_oserror_cleans_up_before_it_is_surfaced(
    tmp_path: Path, monkeypatch
):
    cfg, _ = _dispatch_setup(tmp_path, monkeypatch)
    events: list[str] = []

    class BrokenPipeProcess:
        pid = 7101

        def communicate(self, timeout=None):
            events.append("communicate")
            raise OSError("synthetic pipe failure")

    process = BrokenPipeProcess()
    monkeypatch.setattr(collector.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(
        collector,
        "_kill_peer_tree",
        lambda proc: events.append("cleanup") if proc is process else None,
    )

    with pytest.raises(OSError, match="synthetic pipe failure"):
        collector._run_peer(
            ["fake-peer"],
            cwd=cfg.root,
            timeout=600,
            env={},
        )

    assert events == ["communicate", "cleanup"]


def test_peer_launch_oserror_is_operator_visible(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        collector.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError("synthetic launch failure")
        ),
    )

    with pytest.raises(OSError, match="synthetic launch failure"):
        collector._run_peer(
            ["missing-peer"],
            cwd=tmp_path,
            timeout=600,
            env={},
        )


def test_windows_taskkill_failure_is_not_treated_as_verified_cleanup(
    monkeypatch,
):
    events: list[tuple] = []

    class Process:
        pid = 7102

        def wait(self, timeout=None):
            events.append(("wait", timeout))
            return 0

    def fake_run(cmd, **kwargs):
        events.append(("taskkill", cmd))
        return collector.subprocess.CompletedProcess(cmd, 1, b"", b"access denied")

    monkeypatch.setattr(collector.os, "name", "nt")
    monkeypatch.setattr(collector.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="taskkill"):
        collector._kill_peer_tree(Process())

    assert events == [
        ("taskkill", ["taskkill", "/F", "/T", "/PID", "7102"]),
        ("wait", 10),
    ]


def test_windows_wrapper_wait_timeout_is_not_treated_as_verified_cleanup(
    monkeypatch,
):
    events: list[tuple] = []

    class Process:
        pid = 7103

        def wait(self, timeout=None):
            events.append(("wait", timeout))
            if len([event for event in events if event[0] == "wait"]) == 1:
                raise collector.subprocess.TimeoutExpired("fake-peer", timeout)
            return 0

        def kill(self):
            events.append(("kill",))

    def fake_run(cmd, **kwargs):
        events.append(("taskkill", cmd))
        return collector.subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(collector.os, "name", "nt")
    monkeypatch.setattr(collector.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="did not exit"):
        collector._kill_peer_tree(Process())

    assert events[:2] == [
        ("taskkill", ["taskkill", "/F", "/T", "/PID", "7103"]),
        ("wait", 10),
    ]


def test_windows_wrapper_fallback_kill_failure_is_dedicated_cleanup_failure(
    monkeypatch,
):
    class Process:
        pid = 7107

        def wait(self, timeout=None):
            raise collector.subprocess.TimeoutExpired("fake-peer", timeout)

        def kill(self):
            raise OSError("synthetic fallback kill failure")

    monkeypatch.setattr(collector.os, "name", "nt")
    monkeypatch.setattr(
        collector.subprocess,
        "run",
        lambda cmd, **kwargs: collector.subprocess.CompletedProcess(
            cmd, 0, b"", b""
        ),
    )

    with pytest.raises(
        collector._PeerCleanupError,
        match="fallback kill failure",
    ):
        collector._kill_peer_tree(Process())


def test_posix_cleanup_targets_only_wrapper_owned_group(
    monkeypatch
):
    events: list[tuple] = []

    class Process:
        pid = 7104

        def wait(self, timeout=None):
            events.append(("wait", timeout))
            return 0

    def fake_killpg(pgid, sig):
        events.append(("killpg", pgid, sig))
        if sig == 0:
            raise ProcessLookupError(pgid)

    monkeypatch.setattr(collector.os, "name", "posix")
    monkeypatch.setattr(collector.os, "killpg", fake_killpg, raising=False)

    collector._kill_peer_tree(Process())

    kill_signal = getattr(signal, "SIGKILL", signal.SIGTERM)
    assert ("killpg", 7104, kill_signal) in events
    assert ("killpg", 7104, 0) in events
    assert ("wait", 10) in events


def test_posix_cleanup_fails_closed_while_process_group_still_exists(
    monkeypatch,
):
    class Process:
        pid = 7108

        def wait(self, timeout=None):
            return 0

    ticks = iter((0.0, 11.0))
    monkeypatch.setattr(collector.os, "name", "posix")
    monkeypatch.setattr(collector.os, "killpg", lambda pgid, sig: None, raising=False)
    monkeypatch.setattr(collector.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(collector.time, "sleep", lambda delay: None)

    with pytest.raises(collector._PeerCleanupError, match="still exists"):
        collector._kill_peer_tree(Process())


def test_posix_wrapper_wait_timeout_is_dedicated_cleanup_failure(
    monkeypatch,
):
    class Process:
        pid = 7105

        def wait(self, timeout=None):
            raise collector.subprocess.TimeoutExpired("fake-peer", timeout)

    monkeypatch.setattr(collector.os, "name", "posix")
    monkeypatch.setattr(
        collector.os,
        "killpg",
        lambda pgid, sig: (
            (_ for _ in ()).throw(ProcessLookupError(pgid))
            if sig == 0
            else None
        ),
        raising=False,
    )

    with pytest.raises(collector._PeerCleanupError, match="did not exit"):
        collector._kill_peer_tree(Process())


def test_outer_normal_exit_verifies_wrapper_group_absent(
    tmp_path: Path, monkeypatch
):
    class Process:
        pid = 7106
        returncode = 0

        def communicate(self, timeout=None):
            return b"done", b""

    process = Process()
    checks: list[tuple[int, int]] = []
    monkeypatch.setattr(collector.os, "name", "posix")
    monkeypatch.setattr(collector.subprocess, "Popen", lambda *args, **kwargs: process)

    def absent_group(pgid, sig):
        checks.append((pgid, sig))
        raise ProcessLookupError(pgid)

    monkeypatch.setattr(collector.os, "killpg", absent_group, raising=False)

    assert collector._run_peer(
        ["fake-peer"],
        cwd=tmp_path,
        timeout=600,
        env={},
    ) == "done"
    assert checks == [(process.pid, 0)]


def test_unverified_cleanup_keeps_talk_capacity_reserved(
    tmp_path: Path, monkeypatch
):
    cfg, _ = _dispatch_setup(tmp_path, monkeypatch)
    capacity = collector._DispatchCapacity()
    monkeypatch.setattr(collector, "_DISPATCH_CAPACITY", capacity)
    finished = threading.Event()

    def fail_cleanup(*args, **kwargs):
        try:
            raise collector._PeerCleanupError(
                "synthetic cleanup verification failure"
            )
        finally:
            finished.set()

    monkeypatch.setattr(collector, "_run_peer", fail_cleanup)

    collector.talk(cfg, "agent:cleanup-fails", "hold capacity fail closed")
    assert finished.wait(timeout=3)
    _join_village_threads()

    assert not capacity.reserve(8), (
        "unverified process-tree cleanup released shared dispatch capacity"
    )


def test_artifact_unlink_failure_is_reported_without_masking_primary_cleanup(
    tmp_path: Path, capsys
):
    class CleanupFails:
        def __str__(self):
            return str(tmp_path / "synthetic-artifact")

        def unlink(self, *, missing_ok=False):
            raise OSError("synthetic artifact unlink failure")

    with pytest.raises(collector._PeerCleanupError) as caught:
        try:
            raise collector._PeerCleanupError(
                "synthetic cleanup verification failure"
            )
        finally:
            collector._remove_dispatch_artifacts(CleanupFails())

    assert "cleanup verification failure" in str(caught.value)
    assert any(
        "artifact unlink failure" in note
        for note in getattr(caught.value, "__notes__", [])
    )
    assert "artifact unlink failure" in capsys.readouterr().err


def test_same_target_inbox_appends_are_serialized(
    tmp_path: Path, monkeypatch
):
    inbox = tmp_path / "same-target.md"
    real_open = Path.open
    first_opened = threading.Event()
    release_first = threading.Event()
    second_opened = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def controlled_open(path, *args, **kwargs):
        nonlocal calls
        if path == inbox:
            with calls_lock:
                calls += 1
                call = calls
            if call == 1:
                first_opened.set()
                assert release_first.wait(timeout=3)
            else:
                second_opened.set()
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", controlled_open)
    first = threading.Thread(
        target=collector._append_inbox,
        args=(inbox, "alpha", "first"),
    )
    second = threading.Thread(
        target=collector._append_inbox,
        args=(inbox, "beta", "second"),
    )
    first.start()
    assert first_opened.wait(timeout=3)
    second.start()
    try:
        serialized = not second_opened.wait(timeout=0.1)
    finally:
        release_first.set()
        first.join(timeout=3)
        second.join(timeout=3)

    assert serialized
    assert second_opened.is_set()
    assert not first.is_alive()
    assert not second.is_alive()


def test_unverified_cleanup_keeps_hire_capacity_reserved(
    tmp_path: Path, monkeypatch
):
    cfg, _ = _dispatch_setup(tmp_path, monkeypatch)
    capacity = collector._DispatchCapacity()
    monkeypatch.setattr(collector, "_DISPATCH_CAPACITY", capacity)
    finished = threading.Event()

    def fail_cleanup(*args, **kwargs):
        try:
            raise collector._PeerCleanupError(
                "synthetic cleanup verification failure"
            )
        finally:
            finished.set()

    monkeypatch.setattr(collector, "_run_peer", fail_cleanup)

    result = collector.hire(
        cfg,
        {
            "universe_id": "u-hire1",
            "provider": "claude",
            "count": 1,
            "task": "hold hire capacity fail closed",
            "preset": False,
        },
    )
    assert result["ok"] is True
    assert finished.wait(timeout=3)
    _join_village_threads()

    assert capacity.reserve(7)
    assert not capacity.reserve(1), (
        "unverified hire cleanup released its shared dispatch slot"
    )
    capacity.release(7)


def test_concurrent_same_target_talk_uses_unique_output_artifacts(
    tmp_path: Path, monkeypatch
):
    cfg, _ = _dispatch_setup(tmp_path, monkeypatch)
    both_wrote = threading.Barrier(2)
    out_paths: list[Path] = []
    lock = threading.Lock()

    def fake_run_peer(cmd, *, cwd, timeout, env):
        out_path = Path(cmd[cmd.index("--out") + 1])
        prompt = cmd[cmd.index("--prompt") + 1]
        reply = "reply-alpha" if "message alpha" in prompt else "reply-beta"
        with lock:
            out_paths.append(out_path)
        out_path.write_text(reply, encoding="utf-8")
        both_wrote.wait(timeout=3)
        return ""

    monkeypatch.setattr(collector, "_run_peer", fake_run_peer)

    collector.talk(cfg, "agent:same-target", "message alpha")
    collector.talk(cfg, "agent:same-target", "message beta")
    inbox_path = cfg.inbox_dir / "same-target.md"
    _wait_until(
        lambda: all(
            reply in inbox_path.read_text(encoding="utf-8")
            for reply in ("reply-alpha", "reply-beta")
        )
    )
    _join_village_threads()

    inbox_text = inbox_path.read_text(encoding="utf-8")
    assert len(set(out_paths)) == 2
    assert "reply-alpha" in inbox_text
    assert "reply-beta" in inbox_text


def test_concurrent_same_target_hires_use_unique_output_artifacts(
    tmp_path: Path, monkeypatch
):
    cfg, udir = _dispatch_setup(tmp_path, monkeypatch)
    both_wrote = threading.Barrier(2)
    out_paths: list[Path] = []
    lock = threading.Lock()

    def fake_run_peer(cmd, *, cwd, timeout, env):
        out_path = Path(cmd[cmd.index("--out") + 1])
        prompt = cmd[cmd.index("--prompt") + 1]
        reply = "hire-alpha" if "task alpha" in prompt else "hire-beta"
        with lock:
            out_paths.append(out_path)
        out_path.write_text(reply, encoding="utf-8")
        both_wrote.wait(timeout=3)
        return ""

    monkeypatch.setattr(collector, "_run_peer", fake_run_peer)

    for task in ("task alpha", "task beta"):
        result = collector.hire(
            cfg,
            {
                "universe_id": "u-hire1",
                "provider": "claude",
                "count": 1,
                "task": task,
                "preset": False,
            },
        )
        assert result["ok"] is True
    chat_path = udir / "village-inbox.md"
    _wait_until(
        lambda: all(
            reply in chat_path.read_text(encoding="utf-8")
            for reply in ("hire-alpha", "hire-beta")
        )
    )
    _join_village_threads()

    chat_text = chat_path.read_text(encoding="utf-8")
    assert len(set(out_paths)) == 2
    assert "hire-alpha" in chat_text
    assert "hire-beta" in chat_text
