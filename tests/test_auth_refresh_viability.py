"""Tests for the codex refresh-viability probe layered onto
``subscription_auth_health`` (tinyassets/providers/base.py).

Live-proven gap 2026-07-14: a stale ``/data/.codex/auth.json`` stranded by
the Jun-27 volume migration passed BOTH the presence gate AND ``codex login
status``, yet 401'd at call time — the 2026-06-25 queue-poison class. The
ladder under test: presence → last_refresh freshness fast path (no
subprocess for busy workers) → TTL-cached live ``codex exec`` probe whose
DEAD signatures quarantine; inconclusive outcomes fail toward "ok".
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from tinyassets.providers import base


@pytest.fixture(autouse=True)
def _clean_probe_state(monkeypatch):
    base._reset_auth_probe_cache()
    monkeypatch.delenv("TINYASSETS_AUTH_VIABILITY_PROBE", raising=False)
    monkeypatch.delenv("TINYASSETS_CODEX_AUTH_FRESH_S", raising=False)
    monkeypatch.delenv("TINYASSETS_AUTH_PROBE_TTL_S", raising=False)
    monkeypatch.delenv("TINYASSETS_AUTH_PROBE_TIMEOUT_S", raising=False)
    yield
    base._reset_auth_probe_cache()


def _write_auth(tmp_path, *, last_refresh_age_s: float | None):
    payload: dict = {"tokens": {"access_token": "x", "refresh_token": "y"}}
    if last_refresh_age_s is not None:
        stamp = datetime.now(timezone.utc) - timedelta(seconds=last_refresh_age_s)
        payload["last_refresh"] = stamp.isoformat().replace("+00:00", "Z")
    (tmp_path / "auth.json").write_text(json.dumps(payload), encoding="utf-8")


def _explode_probe(*_a, **_k):
    raise AssertionError("live probe must not run on the fast path")


# ---- freshness fast path -----------------------------------------------------


def test_fresh_last_refresh_is_ok_without_probe(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    _write_auth(tmp_path, last_refresh_age_s=60)
    monkeypatch.setattr(base, "_codex_live_auth_probe", _explode_probe)
    health = base.subscription_auth_health("codex")
    assert health["status"] == "ok"
    assert "refresh-viable" in health["detail"]


def test_missing_last_refresh_falls_back_to_fresh_mtime(tmp_path, monkeypatch):
    """A just-written auth.json without the field (e.g. `codex login` output
    mid-write) reads fresh via mtime — no probe, no quarantine."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    _write_auth(tmp_path, last_refresh_age_s=None)
    monkeypatch.setattr(base, "_codex_live_auth_probe", _explode_probe)
    assert base.subscription_auth_health("codex")["status"] == "ok"


def test_absent_auth_json_still_not_logged_in(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    health = base.subscription_auth_health("codex")
    assert health["status"] == "not_logged_in"
    assert "no auth.json" in health["detail"]


# ---- stale creds trigger the live probe --------------------------------------


def _make_stale(tmp_path, monkeypatch, age_s: float = 26 * 24 * 3600):
    """The live incident shape: last_refresh ~26 days old (Jun 18 → Jul 14)."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    _write_auth(tmp_path, last_refresh_age_s=age_s)


def test_stale_plus_dead_probe_quarantines(tmp_path, monkeypatch):
    _make_stale(tmp_path, monkeypatch)
    monkeypatch.setattr(
        base, "_codex_live_auth_probe",
        lambda timeout_s: {"status": "not_logged_in",
                           "detail": "refresh-viability probe FAILED"},
    )
    health = base.subscription_auth_health("codex")
    assert health["status"] == "not_logged_in"
    assert "probe FAILED" in health["detail"]


def test_stale_plus_alive_probe_is_ok(tmp_path, monkeypatch):
    _make_stale(tmp_path, monkeypatch)
    monkeypatch.setattr(
        base, "_codex_live_auth_probe",
        lambda timeout_s: {"status": "ok", "detail": "live auth probe passed"},
    )
    assert base.subscription_auth_health("codex")["status"] == "ok"


def test_stale_plus_inconclusive_probe_fails_toward_ok(tmp_path, monkeypatch):
    """Only a POSITIVE dead signature quarantines; transport trouble must
    not quarantine a healthy worker (false ok still trips loop_stalled)."""
    _make_stale(tmp_path, monkeypatch)
    monkeypatch.setattr(
        base, "_codex_live_auth_probe",
        lambda timeout_s: {"status": "inconclusive", "detail": "timed out"},
    )
    health = base.subscription_auth_health("codex")
    assert health["status"] == "ok"
    assert "timed out" in health["detail"]


def test_probe_disabled_env_reads_presence_only(tmp_path, monkeypatch):
    _make_stale(tmp_path, monkeypatch)
    monkeypatch.setenv("TINYASSETS_AUTH_VIABILITY_PROBE", "off")
    monkeypatch.setattr(base, "_codex_live_auth_probe", _explode_probe)
    assert base.subscription_auth_health("codex")["status"] == "ok"


# ---- allow_probe=False (get_status latency guard) -----------------------------


def test_allow_probe_false_never_spawns_probe_on_stale(tmp_path, monkeypatch):
    """get_status is an MCP request path: stale creds must NOT block on a
    probe subprocess — deferred detail instead."""
    _make_stale(tmp_path, monkeypatch)
    monkeypatch.setattr(base, "_codex_live_auth_probe", _explode_probe)
    health = base.subscription_auth_health("codex", allow_probe=False)
    assert health["status"] == "ok"
    assert "deferred" in health["detail"]


def test_allow_probe_false_still_serves_cached_dead_verdict(tmp_path, monkeypatch):
    """Once a probing caller (worker gate) cached a dead verdict in this
    process, non-probing callers see it too."""
    _make_stale(tmp_path, monkeypatch)
    monkeypatch.setattr(
        base, "_codex_live_auth_probe",
        lambda timeout_s: {"status": "not_logged_in",
                           "detail": "refresh-viability probe FAILED"},
    )
    assert base.subscription_auth_health("codex")["status"] == "not_logged_in"
    monkeypatch.setattr(base, "_codex_live_auth_probe", _explode_probe)
    cached = base.subscription_auth_health("codex", allow_probe=False)
    assert cached["status"] == "not_logged_in"


# ---- probe verdicts are TTL-cached -------------------------------------------


def test_probe_result_cached_within_ttl(tmp_path, monkeypatch):
    _make_stale(tmp_path, monkeypatch)
    calls = []

    def counting_probe(timeout_s):
        calls.append(timeout_s)
        return {"status": "not_logged_in", "detail": "dead"}

    monkeypatch.setattr(base, "_codex_live_auth_probe", counting_probe)
    first = base.subscription_auth_health("codex")
    second = base.subscription_auth_health("codex")
    assert first["status"] == second["status"] == "not_logged_in"
    assert len(calls) == 1  # supervisor ticks must not spawn a probe each


def test_probe_reruns_after_ttl_expiry(tmp_path, monkeypatch):
    _make_stale(tmp_path, monkeypatch)
    monkeypatch.setenv("TINYASSETS_AUTH_PROBE_TTL_S", "1")
    calls = []

    def counting_probe(timeout_s):
        calls.append(timeout_s)
        return {"status": "ok", "detail": "alive"}

    monkeypatch.setattr(base, "_codex_live_auth_probe", counting_probe)
    base.subscription_auth_health("codex")
    # Age BOTH cache layers into the past instead of sleeping.
    key = next(iter(base._auth_probe_cache))
    checked_at, verdict = base._auth_probe_cache[key]
    base._auth_probe_cache[key] = (checked_at - 10.0, verdict)
    base._write_probe_cache_file(tmp_path, checked_at - 10.0, verdict)
    base.subscription_auth_health("codex")
    assert len(calls) == 2


def test_dead_verdict_visible_across_processes_via_disk(tmp_path, monkeypatch):
    """Codex-critical regression: daemon and workers are separate
    containers sharing CODEX_HOME. A worker's dead verdict must be visible
    to a FRESH process's non-probing get_status call — simulated here by
    clearing the in-memory layer after the probing call."""
    _make_stale(tmp_path, monkeypatch)
    monkeypatch.setattr(
        base, "_codex_live_auth_probe",
        lambda timeout_s: {"status": "not_logged_in",
                           "detail": "refresh-viability probe FAILED"},
    )
    assert base.subscription_auth_health("codex")["status"] == "not_logged_in"
    base._reset_auth_probe_cache()  # "new process": memory gone, disk remains
    monkeypatch.setattr(base, "_codex_live_auth_probe", _explode_probe)
    health = base.subscription_auth_health("codex", allow_probe=False)
    assert health["status"] == "not_logged_in"
    assert (tmp_path / base.PROBE_CACHE_FILENAME).is_file()


# ---- _codex_live_auth_probe output parsing ------------------------------------


class _Proc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


@pytest.mark.parametrize("signature", list(base._CODEX_AUTH_FAILURE_PATTERNS))
def test_live_probe_detects_each_dead_signature(monkeypatch, signature):
    # The probe does a function-local `import subprocess`, so patching the
    # module attribute is seen by it.
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: _Proc(stderr=f"ERROR: {signature}", returncode=0),
    )
    verdict = base._codex_live_auth_probe(5.0)
    assert verdict["status"] == "not_logged_in"
    assert "codex login" in verdict["detail"]


def test_live_probe_clean_output_is_ok(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(stdout="OK"))
    assert base._codex_live_auth_probe(5.0)["status"] == "ok"


def test_live_probe_matches_signatures_case_insensitively(monkeypatch):
    """Codex review: 'codex login status' casing is not a contract."""
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: _Proc(stdout="x", stderr="401 UNAUTHORIZED", returncode=0),
    )
    assert base._codex_live_auth_probe(5.0)["status"] == "not_logged_in"


def test_live_probe_silent_auth_mirror_empty_stdout(monkeypatch):
    """CodexProvider's silent-auth heuristic: empty stdout + broad auth
    signal in stderr = dead (v0.122+ exits 0 and prints nothing)."""
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: _Proc(stdout="", stderr="Reconnecting to auth...",
                              returncode=0),
    )
    assert base._codex_live_auth_probe(5.0)["status"] == "not_logged_in"


def test_live_probe_broad_signals_never_match_model_text(monkeypatch):
    """Broad signals are only trusted on EMPTY stdout — a model reply that
    happens to mention auth must not quarantine."""
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: _Proc(stdout="OK (auth systems are fascinating)",
                              stderr="Reconnecting", returncode=0),
    )
    assert base._codex_live_auth_probe(5.0)["status"] == "ok"


def test_live_probe_empty_output_without_signal_is_inconclusive(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _Proc(stdout="", stderr="", returncode=0),
    )
    assert base._codex_live_auth_probe(5.0)["status"] == "inconclusive"


def test_live_probe_nonzero_exit_without_signature_is_inconclusive(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _Proc(stderr="boom", returncode=2),
    )
    assert base._codex_live_auth_probe(5.0)["status"] == "inconclusive"


def test_live_probe_timeout_is_inconclusive(monkeypatch):
    def raise_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="codex", timeout=5.0)

    monkeypatch.setattr(subprocess, "run", raise_timeout)
    assert base._codex_live_auth_probe(5.0)["status"] == "inconclusive"


def test_live_probe_missing_binary_is_inconclusive(monkeypatch):
    def raise_missing(*a, **k):
        raise FileNotFoundError("codex")

    monkeypatch.setattr(subprocess, "run", raise_missing)
    assert base._codex_live_auth_probe(5.0)["status"] == "inconclusive"


# ---- env + parsing hardening ---------------------------------------------------


@pytest.mark.parametrize("bad", ["junk", "-5", "0", "inf", "nan", "1e999"])
def test_env_seconds_reject_non_finite_and_non_positive(monkeypatch, bad):
    monkeypatch.setenv("TINYASSETS_CODEX_AUTH_FRESH_S", bad)
    assert base._finite_positive_env_s(
        "TINYASSETS_CODEX_AUTH_FRESH_S", 123.0,
    ) == 123.0


def test_last_refresh_z_suffix_parses(tmp_path):
    _write_auth(tmp_path, last_refresh_age_s=3600)
    age = base._codex_last_refresh_age_s(tmp_path)
    assert age is not None
    assert 3500 < age < 3700


@pytest.mark.parametrize("corrupt", ["not json", "[]", '"str"'])
def test_corrupt_auth_json_is_suspicious_not_mtime_fresh(tmp_path, corrupt):
    """Codex review: a freshly-written file containing garbage must NOT
    read viable via mtime — it escalates to the probe instead."""
    (tmp_path / "auth.json").write_text(corrupt, encoding="utf-8")
    assert base._codex_last_refresh_age_s(tmp_path) is None


def test_corrupt_auth_json_with_dead_probe_quarantines(tmp_path, monkeypatch):
    """The claim-and-poison closure: corrupt file → probe → dead → gate."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "auth.json").write_text("not json", encoding="utf-8")
    monkeypatch.setattr(
        base, "_codex_live_auth_probe",
        lambda timeout_s: {"status": "not_logged_in",
                           "detail": "refresh-viability probe FAILED"},
    )
    assert base.subscription_auth_health("codex")["status"] == "not_logged_in"


def test_valid_json_without_last_refresh_uses_mtime(tmp_path):
    """Only a VALID JSON object missing the field gets the mtime fallback
    (mid-write `codex login` shape)."""
    (tmp_path / "auth.json").write_text("{}", encoding="utf-8")
    age = base._codex_last_refresh_age_s(tmp_path)
    assert age is not None
    assert age < 60  # just written


def test_unparseable_last_refresh_field_is_suspicious(tmp_path):
    (tmp_path / "auth.json").write_text(
        json.dumps({"last_refresh": "not-a-date"}), encoding="utf-8",
    )
    assert base._codex_last_refresh_age_s(tmp_path) is None


def test_unreadable_auth_json_returns_none(tmp_path):
    assert base._codex_last_refresh_age_s(tmp_path / "nope") is None


# ---- supervisor wiring ----------------------------------------------------------


def test_dead_probe_verdict_flows_into_worker_quarantine(tmp_path, monkeypatch):
    """cloud_worker gates on subscription_auth_health; a present-but-dead
    token must now read not_logged_in end-to-end (the 2026-06-25 class)."""
    import tinyassets.cloud_worker as cw

    _make_stale(tmp_path, monkeypatch)
    monkeypatch.setattr(
        base, "_codex_live_auth_probe",
        lambda timeout_s: {"status": "not_logged_in",
                           "detail": "refresh-viability probe FAILED"},
    )
    health = cw._worker_auth_health(["--provider", "codex"])
    assert health is not None
    assert health["status"] == "not_logged_in"
