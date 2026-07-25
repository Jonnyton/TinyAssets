from __future__ import annotations

import importlib
import importlib.util
import tomllib
from pathlib import Path

import pytest


def _credentials_module():
    if importlib.util.find_spec("tinyassets.desktop.credentials") is None:
        pytest.fail("tinyassets.desktop.credentials has not been implemented")
    return importlib.import_module("tinyassets.desktop.credentials")


class FakeKeyring:
    def __init__(
        self,
        *,
        priority: float = 1,
        backend_module: str = "keyring.backends.Windows",
        backend_name: str = "WinVaultKeyring",
        fail_operations: bool = False,
    ) -> None:
        self._values: dict[tuple[str, str], str] = {}
        backend_type = type(backend_name, (), {"priority": priority})
        backend_type.__module__ = backend_module
        self._backend = backend_type()
        self._fail_operations = fail_operations

    def get_keyring(self):
        return self._backend

    def set_password(self, service: str, username: str, secret: str) -> None:
        if self._fail_operations:
            raise RuntimeError("backend locked")
        self._values[(service, username)] = secret

    def get_password(self, service: str, username: str) -> str | None:
        if self._fail_operations:
            raise RuntimeError("backend locked")
        return self._values.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self._values.pop((service, username), None)


def test_refresh_token_round_trips_through_native_store() -> None:
    credentials = _credentials_module()
    keyring = FakeKeyring()
    store = credentials.NativeCredentialStore(keyring_module=keyring)
    manager = credentials.DesktopCredentialManager(store)

    reference = manager.save_refresh_token(
        account_id="acct-1",
        host_id="host-1",
        refresh_token="refresh-secret",
    )

    assert reference == "tinyassets-desktop:acct-1:host-1"
    assert manager.load_refresh_token(reference) == "refresh-secret"
    assert "refresh-secret" not in reference


def test_unavailable_native_backend_fails_closed() -> None:
    credentials = _credentials_module()
    store = credentials.NativeCredentialStore(keyring_module=FakeKeyring(priority=0))

    with pytest.raises(
        credentials.SecretStoreUnavailable,
        match="native operating-system secret store is unavailable",
    ):
        store.set("account", "secret")


def test_positive_priority_plaintext_backend_fails_closed() -> None:
    credentials = _credentials_module()
    store = credentials.NativeCredentialStore(
        keyring_module=FakeKeyring(
            backend_module="keyrings.alt.file",
            backend_name="PlaintextKeyring",
        )
    )

    with pytest.raises(credentials.SecretStoreUnavailable, match="native operating-system"):
        store.set("account", "secret")


def test_native_backend_operational_failure_is_fail_closed() -> None:
    credentials = _credentials_module()
    store = credentials.NativeCredentialStore(
        keyring_module=FakeKeyring(fail_operations=True)
    )

    with pytest.raises(credentials.SecretStoreUnavailable, match="native operating-system"):
        store.get("account")


def test_refresh_token_is_never_accepted_as_empty() -> None:
    credentials = _credentials_module()
    manager = credentials.DesktopCredentialManager(
        credentials.NativeCredentialStore(keyring_module=FakeKeyring())
    )

    with pytest.raises(ValueError, match="refresh token must not be empty"):
        manager.save_refresh_token(
            account_id="acct-1",
            host_id="host-1",
            refresh_token="",
        )


def test_delete_removes_native_secret() -> None:
    credentials = _credentials_module()
    manager = credentials.DesktopCredentialManager(
        credentials.NativeCredentialStore(keyring_module=FakeKeyring())
    )
    reference = manager.save_refresh_token(
        account_id="acct-1",
        host_id="host-1",
        refresh_token="refresh-secret",
    )

    manager.delete(reference)

    assert manager.load_refresh_token(reference) is None


def test_desktop_install_declares_native_keyring_dependency() -> None:
    project = Path(__file__).resolve().parents[2]
    config = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))

    desktop_dependencies = config["project"]["optional-dependencies"]["desktop"]

    assert any(item.startswith("keyring") for item in desktop_dependencies)
