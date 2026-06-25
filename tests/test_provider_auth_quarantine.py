"""Tests for the provider-auth health + worker self-quarantine feature.

Behind the 2026-06-25 loop-wedge: a worker whose writer-provider credentials
were missing kept claiming tasks and failing every one for ~3 weeks, poisoning
the queue, with no signal in get_status. This feature:

  1. ``subscription_auth_health`` — a presence-based auth probe (one source of
     truth shared by the worker gate + get_status).
  2. ``run_supervisor`` self-quarantine — a dead-auth worker skips spawning the
     claim subprocess entirely (no claim, no poison).
  3. ``_compute_supervisor_liveness`` provider_auth block — surfaces dead writer
     auth + an ``all_writers_unauthenticated`` roll-up warning.
"""

from __future__ import annotations

import sys
from pathlib import Path

_WORKFLOW = Path(__file__).resolve().parent.parent / "workflow"
if str(_WORKFLOW.parent) not in sys.path:
    sys.path.insert(0, str(_WORKFLOW.parent))

import workflow.cloud_worker as cw  # noqa: E402
from workflow.api.status import _compute_supervisor_liveness  # noqa: E402
from workflow.providers.base import subscription_auth_health  # noqa: E402

# ---- minimal Popen stand-in (never claims real subprocesses) --------------


class _FakeProc:
    def __init__(self, returncode: int = 0):
        self.returncode: int | None = None
        self._rc = returncode

    def poll(self):
        self.returncode = self._rc
        return self._rc

    def wait(self, timeout=None):
        self.returncode = self._rc
        return self._rc


def _sleep_recorder():
    calls: list[float] = []
    return calls, calls.append


# ---- subscription_auth_health: codex --------------------------------------


def test_codex_ok_when_auth_json_present(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "auth.json").write_text("{}", encoding="utf-8")
    health = subscription_auth_health("codex")
    assert health["status"] == "ok"
    assert health["provider"] == "codex"


def test_codex_not_logged_in_when_auth_json_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    assert subscription_auth_health("codex")["status"] == "not_logged_in"


# ---- subscription_auth_health: claude-code --------------------------------


def test_claude_ok_with_oauth_token(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    # Empty config dir — the token must win regardless.
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert subscription_auth_health("claude-code")["status"] == "ok"


def test_claude_ok_with_populated_config_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    (tmp_path / ".credentials.json").write_text("{}", encoding="utf-8")
    assert subscription_auth_health("claude-code")["status"] == "ok"


def test_claude_not_logged_in_when_no_token_and_empty_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "absent"))
    assert subscription_auth_health("claude-code")["status"] == "not_logged_in"


# ---- subscription_auth_health: unknown providers are never gated -----------


def test_unknown_provider_is_unknown():
    assert subscription_auth_health("gemini-free")["status"] == "unknown"


def test_empty_provider_is_unknown():
    assert subscription_auth_health("")["status"] == "unknown"


# ---- run_supervisor self-quarantine ---------------------------------------


def test_supervisor_quarantines_dead_auth_writer(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "no-creds"))
    spawn_calls: list[Path] = []

    def spawn(universe):
        spawn_calls.append(universe)
        return _FakeProc()

    sleep_calls, sleep_fn = _sleep_recorder()
    state = cw.run_supervisor(
        tmp_path,
        max_iterations=2,
        daemon_args=["--provider", "claude-code"],
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
        auth_quarantine_backoff=42.0,
    )
    # The dead-auth worker must NEVER claim — that is the whole point.
    assert spawn_calls == []
    assert state.auth_quarantine_count == 2
    assert sleep_calls == [42.0, 42.0]


def test_supervisor_spawns_when_writer_auth_present(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    spawn_calls: list[Path] = []

    def spawn(universe):
        spawn_calls.append(universe)
        return _FakeProc(returncode=0)

    _, sleep_fn = _sleep_recorder()
    state = cw.run_supervisor(
        tmp_path,
        max_iterations=1,
        daemon_args=["--provider", "claude-code"],
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
    )
    assert len(spawn_calls) == 1
    assert state.auth_quarantine_count == 0


def test_supervisor_does_not_gate_generic_worker(tmp_path, monkeypatch):
    # No --provider and no pin → no resolvable writer → no gate (the worker may
    # legitimately route across the fallback chain), so it spawns normally.
    monkeypatch.delenv("WORKFLOW_PIN_WRITER", raising=False)
    spawn_calls: list[Path] = []

    def spawn(universe):
        spawn_calls.append(universe)
        return _FakeProc(returncode=0)

    _, sleep_fn = _sleep_recorder()
    state = cw.run_supervisor(
        tmp_path, max_iterations=1, spawn_fn=spawn, sleep_fn=sleep_fn,
    )
    assert len(spawn_calls) == 1
    assert state.auth_quarantine_count == 0


# ---- supervisor_liveness provider_auth block ------------------------------


def test_liveness_provider_auth_block_ok(tmp_path, monkeypatch):
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")

    out = _compute_supervisor_liveness(tmp_path)
    assert out["provider_auth"]["writers"]["codex"]["status"] == "ok"
    assert out["provider_auth"]["writers"]["claude-code"]["status"] == "ok"
    assert out["provider_auth"]["all_writers_unauthenticated"] is False
    assert not any("all_writers_unauthenticated" in w for w in out["warnings"])


def test_liveness_all_writers_unauthenticated_warns(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-absent"))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-absent"))

    out = _compute_supervisor_liveness(tmp_path)
    assert out["provider_auth"]["all_writers_unauthenticated"] is True
    assert any("all_writers_unauthenticated" in w for w in out["warnings"])


def test_liveness_partial_writer_warns(tmp_path, monkeypatch):
    # The exact 2026-06-25 shape: claude dead, codex alive. Must warn even
    # though the loop still produces (Codex review finding #1).
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-absent"))

    out = _compute_supervisor_liveness(tmp_path)
    assert out["provider_auth"]["all_writers_unauthenticated"] is False
    assert out["provider_auth"]["writers"]["claude-code"]["status"] == "not_logged_in"
    assert out["provider_auth"]["writers"]["codex"]["status"] == "ok"
    assert any("writer_unauthenticated" in w for w in out["warnings"])
    assert not any("all_writers_unauthenticated" in w for w in out["warnings"])


def test_supervisor_quarantines_via_pin_writer_env(tmp_path, monkeypatch):
    # No --provider; the writer comes from WORKFLOW_PIN_WRITER (Codex #9).
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "no-creds"))
    monkeypatch.setenv("WORKFLOW_PIN_WRITER", "claude-code")
    spawn_calls: list[Path] = []

    def spawn(universe):
        spawn_calls.append(universe)
        return _FakeProc()

    _, sleep_fn = _sleep_recorder()
    state = cw.run_supervisor(
        tmp_path, max_iterations=1, spawn_fn=spawn, sleep_fn=sleep_fn,
    )
    assert spawn_calls == []
    assert state.auth_quarantine_count == 1


def test_supervisor_resumes_after_reauth(tmp_path, monkeypatch):
    # Quarantined worker must resume claiming once creds are re-seeded — the
    # gate re-checks every tick, no restart needed (Codex #9).
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    config_dir = tmp_path / "claude"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    spawn_calls: list[Path] = []

    def spawn(universe):
        spawn_calls.append(universe)
        return _FakeProc(returncode=0)

    def sleep_fn(_delay):
        # Re-seed credentials mid-quarantine; the next iteration should spawn.
        config_dir.mkdir(exist_ok=True)
        (config_dir / ".credentials.json").write_text("{}", encoding="utf-8")

    state = cw.run_supervisor(
        tmp_path,
        max_iterations=2,
        daemon_args=["--provider", "claude-code"],
        spawn_fn=spawn,
        sleep_fn=sleep_fn,
    )
    assert state.auth_quarantine_count == 1  # only the first iteration
    assert len(spawn_calls) == 1             # second iteration claims
