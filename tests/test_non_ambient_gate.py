"""S5 — the non-ambient work gate in the cloud-worker supervisor.

The gate is FLAG-GATED and DEFAULT OFF. The load-bearing proof here is that with
the flag off the supervisor spawns exactly as it does today — even for an
unbound universe (a byte-for-byte no-op). With the flag on, an unbound universe
is not worked (idle-until-bound), a bound universe is worked, and a
DECLARED-but-broken binding fails the gate loudly instead of being silently
skipped.

Uses the same ``spawn_fn`` / ``sleep_fn`` injection seams as
``test_cloud_worker.py`` so the loop runs without subprocess I/O.
"""
from __future__ import annotations

import base64

import pytest

import tinyassets.cloud_worker as cw
from tinyassets.config import write_universe_config_fields
from tinyassets.credential_vault import write_credential_vault
from tinyassets.engine_binding import NON_AMBIENT_WORK_ENV


class _FakeProc:
    """Popen stand-in that exits clean immediately (mirrors test_cloud_worker)."""

    def __init__(self, returncode: int = 0):
        self._rc = returncode
        self.returncode: int | None = None

    def poll(self):
        self.returncode = self._rc
        return self._rc

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = self._rc
        return self.returncode


def _recorders():
    spawn_calls: list = []
    sleep_calls: list[float] = []

    def spawn(universe):
        spawn_calls.append(universe)
        return _FakeProc(returncode=0)

    def sleep(delay):
        sleep_calls.append(delay)

    return spawn_calls, sleep_calls, spawn, sleep


@pytest.fixture(autouse=True)
def _no_pinned_writer(monkeypatch):
    # Keep the pre-existing auth-quarantine gate inert so these tests exercise
    # only the non-ambient gate (no resolvable writer → auth gate returns None).
    monkeypatch.delenv("TINYASSETS_PIN_WRITER", raising=False)


def _unbound_universe(tmp_path):
    udir = tmp_path / "u-unbound"
    udir.mkdir()
    return udir


def _bound_universe(tmp_path):
    udir = tmp_path / "u-bound"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_api_key",
        "service": "anthropic",
        "secret_b64": base64.b64encode(b"sk-ant-test").decode("ascii"),
    }])
    write_universe_config_fields(udir, engine_source="byo_api_key")
    return udir


# ---- FLAG OFF (default) — byte-for-byte no-op -----------------------------


def test_flag_off_still_works_unbound_universe(tmp_path, monkeypatch):
    """DEFAULT OFF: an unbound universe that is worked today is STILL worked —
    the gate is completely inert. This is the no-op proof."""
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    udir = _unbound_universe(tmp_path)
    spawn_calls, _sleep_calls, spawn, sleep = _recorders()

    state = cw.run_supervisor(
        udir, idle_backoff=1.0, max_iterations=2, spawn_fn=spawn, sleep_fn=sleep,
    )
    assert len(spawn_calls) == 2, "flag off must spawn every iteration (no-op)"
    assert state.total_clean_exits == 2
    assert state.idle_until_bound_count == 0
    assert state.engine_misconfigured_count == 0


def test_flag_off_ignores_misconfigured_binding(tmp_path, monkeypatch):
    """Flag off = today's behavior: even a genuinely broken binding is NOT gated
    (today there is no binding check at all), so the universe is worked exactly
    as before."""
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    udir = tmp_path / "u-broken"
    udir.mkdir()
    # Declared byo_api_key with NO vault key = genuinely misconfigured.
    write_universe_config_fields(udir, engine_source="byo_api_key")
    spawn_calls, _sleep_calls, spawn, sleep = _recorders()

    state = cw.run_supervisor(
        udir, idle_backoff=1.0, max_iterations=1, spawn_fn=spawn, sleep_fn=sleep,
    )
    assert len(spawn_calls) == 1
    assert state.engine_misconfigured_count == 0


def test_flag_on_skips_config_only_host_daemon_as_idle(tmp_path, monkeypatch):
    """A bare `engine_source: host_daemon` value with NO summoned runtime is a
    CHOICE, not executable capacity — the gate must treat it as idle-until-bound
    (not spawned, not a loud misconfiguration)."""
    monkeypatch.setenv(NON_AMBIENT_WORK_ENV, "1")
    udir = tmp_path / "u-choice-only"
    udir.mkdir()
    write_universe_config_fields(udir, engine_source="host_daemon")
    spawn_calls, _sleep_calls, spawn, sleep = _recorders()

    state = cw.run_supervisor(
        udir, idle_backoff=1.0, max_iterations=2, spawn_fn=spawn, sleep_fn=sleep,
    )
    assert spawn_calls == [], "config-only host_daemon must NOT spawn under gate"
    assert state.idle_until_bound_count == 2
    assert state.engine_misconfigured_count == 0


# ---- FLAG ON — the gate is active -----------------------------------------


def test_flag_on_skips_unbound_universe(tmp_path, monkeypatch):
    monkeypatch.setenv(NON_AMBIENT_WORK_ENV, "1")
    udir = _unbound_universe(tmp_path)
    spawn_calls, sleep_calls, spawn, sleep = _recorders()

    state = cw.run_supervisor(
        udir, idle_backoff=2.0, max_iterations=2, spawn_fn=spawn, sleep_fn=sleep,
    )
    assert spawn_calls == [], "unbound universe must NOT be spawned when gate on"
    assert state.idle_until_bound_count == 2
    assert state.total_clean_exits == 0
    assert sleep_calls == [2.0, 2.0]


def test_flag_on_skips_paused_runtime_as_idle(tmp_path, monkeypatch):
    """A host_daemon whose only runtime instance is `paused` is NOT executable —
    the gate must treat it as idle-until-bound (not spawned)."""
    from tinyassets.daemon_server import (
        initialize_author_server,
        spawn_runtime_instance,
        update_runtime_instance_status,
    )

    monkeypatch.setenv(NON_AMBIENT_WORK_ENV, "1")
    uid = "u-paused"
    udir = tmp_path / uid
    udir.mkdir()
    write_universe_config_fields(udir, engine_source="host_daemon")
    initialize_author_server(tmp_path)
    inst = spawn_runtime_instance(
        tmp_path, universe_id=uid, author_id="a", provider_name="claude-code",
        model_name="claude", created_by="test",
    )
    update_runtime_instance_status(
        tmp_path, instance_id=inst["instance_id"], status="paused",
    )
    spawn_calls, _sleep_calls, spawn, sleep = _recorders()

    state = cw.run_supervisor(
        udir, idle_backoff=1.0, max_iterations=2, spawn_fn=spawn, sleep_fn=sleep,
    )
    assert spawn_calls == [], "paused runtime must NOT spawn under the gate"
    assert state.idle_until_bound_count == 2


def _codex_vault_universe(tmp_path, name="u-codexvault"):
    """Universe bound to a valid Codex subscription in the per-universe vault."""
    udir = tmp_path / name
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_subscription",
        "service": "codex",
        "auth_json_b64": base64.b64encode(b"{}").decode("ascii"),
    }])
    write_universe_config_fields(udir, engine_source="subscription")
    return udir


def test_flag_on_codex_pinned_worker_skips_anthropic_only_universe(tmp_path, monkeypatch):
    """FINDING 1: the gate is provider-level. An Anthropic-only bound universe
    must NOT let a Codex-pinned worker spawn (it would run on global Codex auth)."""
    monkeypatch.setenv(NON_AMBIENT_WORK_ENV, "1")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "no-codex-home"))  # no global auth
    udir = _bound_universe(tmp_path)  # anthropic BYO key → serves claude-code only
    spawn_calls, _sleep_calls, spawn, sleep = _recorders()

    state = cw.run_supervisor(
        udir, idle_backoff=1.0, max_iterations=2, spawn_fn=spawn, sleep_fn=sleep,
        daemon_args=["--provider", "codex"],
    )
    assert spawn_calls == [], "codex-pinned worker must not run a claude-only universe"
    assert state.idle_until_bound_count == 2
    assert state.engine_misconfigured_count == 0


def test_flag_on_codex_pinned_worker_runs_codex_eligible_universe(tmp_path, monkeypatch):
    """FINDING 1/2: a codex-eligible universe backed by per-universe VAULT auth
    spawns for a Codex-pinned worker even with NO global CODEX_HOME — the child
    materializes the vault auth, so the global-auth quarantine is skipped."""
    monkeypatch.setenv(NON_AMBIENT_WORK_ENV, "1")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "no-codex-home"))  # no global auth
    udir = _codex_vault_universe(tmp_path)
    spawn_calls, _sleep_calls, spawn, sleep = _recorders()

    state = cw.run_supervisor(
        udir, idle_backoff=1.0, max_iterations=2, spawn_fn=spawn, sleep_fn=sleep,
        daemon_args=["--provider", "codex"],
    )
    assert len(spawn_calls) == 2, "codex-eligible vault universe must spawn"
    assert state.auth_quarantine_count == 0, "vault auth must skip global quarantine"
    assert state.idle_until_bound_count == 0


def test_flag_off_codex_pinned_worker_still_quarantines_without_global_auth(
    tmp_path, monkeypatch,
):
    """Flag OFF is a no-op: the vault-aware quarantine skip is gated on the flag,
    so with the flag off a codex-pinned worker with no global CODEX_HOME
    quarantines exactly as today (never spawns on missing global auth)."""
    monkeypatch.delenv(NON_AMBIENT_WORK_ENV, raising=False)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "no-codex-home"))
    udir = _codex_vault_universe(tmp_path)
    spawn_calls, _sleep_calls, spawn, sleep = _recorders()

    state = cw.run_supervisor(
        udir, idle_backoff=1.0, max_iterations=2, spawn_fn=spawn, sleep_fn=sleep,
        auth_quarantine_backoff=1.0,
        daemon_args=["--provider", "codex"],
    )
    assert spawn_calls == [], "flag off must not change the global-auth quarantine"
    assert state.auth_quarantine_count == 2


def test_flag_on_works_bound_universe(tmp_path, monkeypatch):
    monkeypatch.setenv(NON_AMBIENT_WORK_ENV, "1")
    udir = _bound_universe(tmp_path)
    spawn_calls, _sleep_calls, spawn, sleep = _recorders()

    state = cw.run_supervisor(
        udir, idle_backoff=1.0, max_iterations=2, spawn_fn=spawn, sleep_fn=sleep,
    )
    assert len(spawn_calls) == 2, "a bound universe is worked normally"
    assert state.idle_until_bound_count == 0
    assert state.total_clean_exits == 2


def test_flag_on_fails_loud_on_misconfigured_binding(tmp_path, monkeypatch):
    """A DECLARED-but-broken binding is gated LOUDLY (Hard Rule #8): the
    universe is not spawned, and the misconfigured counter records it — it is
    NOT silently treated as unbound-and-skipped."""
    monkeypatch.setenv(NON_AMBIENT_WORK_ENV, "1")
    udir = tmp_path / "u-broken"
    udir.mkdir()
    # Declared byo_api_key (a vault-backed source) with NO vault key = a
    # genuinely broken binding (the bind act deposits the key atomically).
    write_universe_config_fields(udir, engine_source="byo_api_key")
    spawn_calls, _sleep_calls, spawn, sleep = _recorders()

    state = cw.run_supervisor(
        udir, idle_backoff=1.0, max_iterations=2, spawn_fn=spawn, sleep_fn=sleep,
    )
    assert spawn_calls == []
    assert state.engine_misconfigured_count == 2
    assert state.idle_until_bound_count == 0


def test_flag_on_heartbeat_reports_idle_until_bound(tmp_path, monkeypatch):
    """The honest liveness surface distinguishes idle-until-bound from wedged.

    Capture every phase written (the final post-loop 'stopped' beat overwrites
    the on-disk file, so record phases as they happen).
    """
    monkeypatch.setenv(NON_AMBIENT_WORK_ENV, "1")
    udir = _unbound_universe(tmp_path)
    _spawn_calls, _sleep_calls, spawn, sleep = _recorders()

    phases: list[str] = []
    real_beat = cw.write_supervisor_heartbeat

    def _record_beat(universe, state, *, phase, **kw):
        phases.append(phase)
        return real_beat(universe, state, phase=phase, **kw)

    monkeypatch.setattr(cw, "write_supervisor_heartbeat", _record_beat)

    cw.run_supervisor(
        udir, idle_backoff=1.0, max_iterations=1, spawn_fn=spawn, sleep_fn=sleep,
    )
    assert "idle_until_bound" in phases
