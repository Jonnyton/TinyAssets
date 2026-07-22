"""Provider auth status names evidence and never invents authentication."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from tinyassets.providers import base


@pytest.fixture(autouse=True)
def _clean_probe_state(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_codex_deferred_live_and_cached_evidence_are_distinct(
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
    live = base.subscription_auth_health("codex", allow_probe=True)
    cached = base.subscription_auth_health("codex", allow_probe=False)

    assert deferred["evidence"] == "deferred"
    assert live["evidence"] == "live-probe"
    assert cached["evidence"] == "cached"


def test_inconclusive_live_probe_is_not_authentication(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    _write_codex_auth(tmp_path, age_seconds=30 * 24 * 3600)
    monkeypatch.setattr(
        base,
        "_codex_live_auth_probe",
        lambda timeout_s: {
            "status": "inconclusive",
            "detail": "probe transport timed out",
        },
    )

    health = base.subscription_auth_health("codex", allow_probe=True)

    assert health["status"] == "ok"
    assert health["evidence"] == "live-probe-inconclusive"


def test_populated_claude_config_is_not_called_authenticated(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.api import status

    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    (tmp_path / "settings.json").write_text("{}", encoding="utf-8")

    health = base.subscription_auth_health("claude-code", allow_probe=False)
    snapshot = status._provider_auth_snapshot()

    assert health["status"] == "ok"
    assert health["evidence"] == "config-present"
    assert snapshot["writers"]["claude-code"]["evidence"] == "config-present"
    assert snapshot["writers"]["claude-code"]["authenticated"] is None
    assert snapshot["live_probe_performed"] is False


def test_public_snapshot_marks_only_live_success_as_authenticated(monkeypatch) -> None:
    from tinyassets.api import status

    def health(name: str, *, allow_probe: bool) -> dict[str, str]:
        assert allow_probe is False
        if name == "codex":
            return {
                "provider": name,
                "status": "ok",
                "detail": "cached worker verdict",
                "evidence": "cached",
            }
        return {
            "provider": name,
            "status": "not_logged_in",
            "detail": "config absent",
            "evidence": "absent",
        }

    monkeypatch.setattr(base, "subscription_auth_health", health)

    snapshot = status._provider_auth_snapshot()

    assert snapshot["writers"]["codex"]["authenticated"] is None
    assert snapshot["writers"]["codex"]["evidence"] == "cached"
    assert snapshot["writers"]["claude-code"]["authenticated"] is False
    assert snapshot["writers"]["claude-code"]["evidence"] == "absent"
    assert snapshot["live_probe_performed"] is False


def test_public_snapshot_does_not_authenticate_inconclusive_probe(monkeypatch) -> None:
    from tinyassets.api import status

    monkeypatch.setattr(
        base,
        "subscription_auth_health",
        lambda name, *, allow_probe: {
            "provider": name,
            "status": "ok",
            "detail": "probe transport timed out",
            "evidence": "live-probe-inconclusive",
        },
    )

    snapshot = status._provider_auth_snapshot()

    assert snapshot["writers"]["codex"]["authenticated"] is None
    assert snapshot["writers"]["claude-code"]["authenticated"] is None
    assert snapshot["live_probe_performed"] is False
