"""Provider auth status names the evidence class; status is not a live claim."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from tinyassets.providers import base


@pytest.fixture(autouse=True)
def _clean_probe_state(monkeypatch):
    base._reset_auth_probe_cache()
    monkeypatch.setenv("TINYASSETS_AUTH_VIABILITY_PROBE", "on")
    yield
    base._reset_auth_probe_cache()


def _write_codex_auth(path, *, age_seconds: float) -> None:
    stamp = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    (path / "auth.json").write_text(
        json.dumps({"last_refresh": stamp.isoformat()}),
        encoding="utf-8",
    )


def test_codex_fresh_timestamp_is_labeled_timestamp(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    _write_codex_auth(tmp_path, age_seconds=60)

    health = base.subscription_auth_health("codex", allow_probe=False)

    assert health["status"] == "ok"
    assert health["evidence"] == "timestamp"


def test_codex_deferred_and_cached_verdicts_are_distinguishable(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    _write_codex_auth(tmp_path, age_seconds=30 * 24 * 3600)
    monkeypatch.setattr(
        base,
        "_codex_live_auth_probe",
        lambda timeout_s: {"status": "ok", "detail": "live auth probe passed"},
    )

    deferred = base.subscription_auth_health("codex", allow_probe=False)
    assert deferred["evidence"] == "deferred"

    live = base.subscription_auth_health("codex", allow_probe=True)
    assert live["evidence"] == "live-probe"

    cached = base.subscription_auth_health("codex", allow_probe=False)
    assert cached["evidence"] == "cached"


def test_claude_populated_directory_is_labeled_config_present(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    (tmp_path / "settings.json").write_text("{}", encoding="utf-8")

    health = base.subscription_auth_health("claude-code", allow_probe=False)

    assert health["status"] == "ok"
    assert health["evidence"] == "config-present"


def test_get_status_provider_snapshot_preserves_evidence(monkeypatch) -> None:
    from tinyassets.api import status

    def health(name: str, *, allow_probe: bool):
        assert allow_probe is False
        return {
            "provider": name,
            "status": "ok",
            "detail": "not a live verification",
            "evidence": "cached" if name == "codex" else "config-present",
        }

    monkeypatch.setattr(base, "subscription_auth_health", health)

    snapshot = status._provider_auth_snapshot()

    assert snapshot["writers"]["codex"]["evidence"] == "cached"
    assert snapshot["writers"]["claude-code"]["evidence"] == "config-present"
