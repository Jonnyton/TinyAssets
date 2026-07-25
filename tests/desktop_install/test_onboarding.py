from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tinyassets.desktop.credentials import DesktopCredentialManager


class MemorySecrets:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, reference: str, secret: str) -> None:
        self.values[reference] = secret

    def get(self, reference: str) -> str | None:
        return self.values.get(reference)

    def delete(self, reference: str) -> None:
        self.values.pop(reference, None)


class FakeOrigin:
    def __init__(self, onboarding, *, register_offline: bool = False) -> None:
        self.onboarding = onboarding
        self.register_offline = register_offline
        self.refreshed_token = "refresh-secret"
        self.expected_nonce = ""
        self.registrations: list[dict[str, object]] = []

    def exchange_code(self, *, code: str, code_verifier: str, redirect_uri: str):
        assert code == "authorization-code"
        assert code_verifier
        return self.onboarding.TokenSet(
            access_token="access-secret",
            refresh_token="refresh-secret",
            subject="acct-1",
            issuer="https://tinyassets.io",
            audience=("tinyassets-desktop",),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
            nonce=self.expected_nonce,
        )

    def refresh(self, refresh_token: str):
        assert refresh_token == "refresh-secret"
        return self.onboarding.TokenSet(
            access_token="refreshed-access",
            refresh_token=self.refreshed_token,
            subject="acct-1",
            issuer="https://tinyassets.io",
            audience=("tinyassets-desktop",),
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
            nonce=None,
        )

    def register_host(self, **kwargs):
        if self.register_offline:
            raise self.onboarding.OriginUnavailable("origin offline")
        self.registrations.append(kwargs)


def _onboarding_module():
    if importlib.util.find_spec("tinyassets.desktop.onboarding") is None:
        pytest.fail("tinyassets.desktop.onboarding has not been implemented")
    return importlib.import_module("tinyassets.desktop.onboarding")


def _service(onboarding, tmp_path: Path, *, register_offline: bool = False):
    config = onboarding.OAuthConfig(
        authorize_endpoint="https://tinyassets.io/authorize",
        client_id="tinyassets-desktop",
        issuer="https://tinyassets.io",
        audience="tinyassets-desktop",
        redirect_uri="http://127.0.0.1:43119/callback",
    )
    origin = FakeOrigin(onboarding, register_offline=register_offline)
    secrets = MemorySecrets()
    service = onboarding.OnboardingService(
        state_dir=tmp_path,
        oauth=config,
        origin=origin,
        credentials=DesktopCredentialManager(secrets),
    )
    return service, origin, secrets


def test_first_run_binds_existing_account_with_self_visibility(tmp_path: Path) -> None:
    onboarding = _onboarding_module()
    service, origin, secrets = _service(onboarding, tmp_path)
    attempt = service.begin_authorization()
    origin.expected_nonce = attempt.nonce

    result = service.complete_authorization(
        state=attempt.state,
        code="authorization-code",
        redirect_uri="http://127.0.0.1:43119/callback",
    )

    assert result.status == "online"
    assert result.account_id == "acct-1"
    assert origin.registrations == [
        {
            "access_token": "access-secret",
            "host_id": attempt.host_id,
            "capability_visibility": "self",
        }
    ]
    assert list(secrets.values.values()) == ["refresh-secret"]
    persisted = (tmp_path / "onboarding.json").read_text(encoding="utf-8")
    assert "refresh-secret" not in persisted
    assert "access-secret" not in persisted


def test_callback_state_mismatch_creates_no_registration(tmp_path: Path) -> None:
    onboarding = _onboarding_module()
    service, origin, secrets = _service(onboarding, tmp_path)
    service.begin_authorization()

    with pytest.raises(onboarding.AuthorizationValidationError, match="state"):
        service.complete_authorization(
            state="attacker-state",
            code="authorization-code",
            redirect_uri="http://127.0.0.1:43119/callback",
        )

    assert origin.registrations == []
    assert secrets.values == {}


def test_offline_registration_recovers_once_without_reinstall(tmp_path: Path) -> None:
    onboarding = _onboarding_module()
    service, origin, _ = _service(onboarding, tmp_path, register_offline=True)
    attempt = service.begin_authorization()
    origin.expected_nonce = attempt.nonce

    pending = service.complete_authorization(
        state=attempt.state,
        code="authorization-code",
        redirect_uri="http://127.0.0.1:43119/callback",
    )

    assert pending.status == "pending_registration"
    assert pending.advertise_online is False

    origin.register_offline = False
    recovered = service.recover_pending_registration()

    assert recovered.status == "online"
    assert len(origin.registrations) == 1
    assert service.recover_pending_registration().status == "online"
    assert len(origin.registrations) == 1


def test_expired_or_rejected_refresh_stops_online_advertising(tmp_path: Path) -> None:
    onboarding = _onboarding_module()
    service, origin, _ = _service(onboarding, tmp_path, register_offline=True)
    attempt = service.begin_authorization()
    origin.expected_nonce = attempt.nonce
    service.complete_authorization(
        state=attempt.state,
        code="authorization-code",
        redirect_uri="http://127.0.0.1:43119/callback",
    )

    def reject_refresh(_refresh_token: str):
        raise onboarding.AuthorizationRejected("refresh expired")

    origin.refresh = reject_refresh
    result = service.recover_pending_registration()

    assert result.status == "authorization_required"
    assert result.advertise_online is False
    assert json.loads((tmp_path / "onboarding.json").read_text())["host_id"] == (
        attempt.host_id
    )


def test_recovery_persists_a_rotated_refresh_token(tmp_path: Path) -> None:
    onboarding = _onboarding_module()
    service, origin, secrets = _service(onboarding, tmp_path, register_offline=True)
    attempt = service.begin_authorization()
    origin.expected_nonce = attempt.nonce
    service.complete_authorization(
        state=attempt.state,
        code="authorization-code",
        redirect_uri="http://127.0.0.1:43119/callback",
    )

    origin.register_offline = False
    origin.refreshed_token = "rotated-refresh-secret"
    result = service.recover_pending_registration()

    assert result.status == "online"
    assert list(secrets.values.values()) == ["rotated-refresh-secret"]


def test_each_clean_machine_gets_a_distinct_host_identity(tmp_path: Path) -> None:
    onboarding = _onboarding_module()
    first, _, _ = _service(onboarding, tmp_path / "first")
    second, _, _ = _service(onboarding, tmp_path / "second")

    assert first.begin_authorization().host_id != second.begin_authorization().host_id


def test_linux_autostart_is_idempotent_and_removable(tmp_path: Path) -> None:
    onboarding = _onboarding_module()
    manager = onboarding.AutostartManager(
        command=["/opt/tinyassets/TinyAssets", "--tray"],
        platform_name="linux",
        config_home=tmp_path,
    )

    first = manager.enable()
    second = manager.enable()

    assert first == second
    assert first.read_text(encoding="utf-8").count("Exec=") == 1
    manager.disable()
    assert not first.exists()


def test_uninstall_removes_program_but_preserves_user_content(tmp_path: Path) -> None:
    onboarding = _onboarding_module()
    install_root = tmp_path / "program"
    data_root = tmp_path / "user-content"
    install_root.mkdir()
    data_root.mkdir()
    (install_root / "TinyAssets.exe").write_bytes(b"program")
    (data_root / "universe.db").write_bytes(b"user data")
    manager = onboarding.AutostartManager(
        command=[sys.executable],
        platform_name="linux",
        config_home=tmp_path / "config",
    )
    manager.enable()

    result = onboarding.ContentPreservingUninstaller(
        install_root=install_root,
        data_root=data_root,
        autostart=manager,
    ).uninstall()

    assert result.program_removed is True
    assert result.user_content_preserved is True
    assert not install_root.exists()
    assert (data_root / "universe.db").read_bytes() == b"user data"


def test_pending_state_file_contains_only_non_secret_fields(tmp_path: Path) -> None:
    onboarding = _onboarding_module()
    service, _, _ = _service(onboarding, tmp_path)
    service.begin_authorization()

    state = json.loads((tmp_path / "onboarding.json").read_text(encoding="utf-8"))

    assert set(state) <= {
        "account_id",
        "attempt_id",
        "credential_reference",
        "host_id",
        "next_retry_at",
        "retry_count",
        "status",
    }
