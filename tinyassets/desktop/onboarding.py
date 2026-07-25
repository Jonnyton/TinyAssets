"""Packaged-tray account binding and recoverable first-run state.

OAuth attempt secrets live only in memory. Durable onboarding state is
deliberately non-secret; reusable refresh credentials are referenced through
``DesktopCredentialManager`` and remain in the operating-system secret store.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import plistlib
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode

from tinyassets.desktop.credentials import DesktopCredentialManager


class OriginUnavailable(RuntimeError):
    """The platform origin could not be reached."""


class AuthorizationRejected(RuntimeError):
    """The origin rejected a credential refresh or registration."""


class AuthorizationValidationError(ValueError):
    """An OAuth callback or token response failed local validation."""


@dataclass(frozen=True)
class OAuthConfig:
    authorize_endpoint: str
    client_id: str
    issuer: str
    audience: str
    redirect_uri: str


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str
    subject: str
    issuer: str
    audience: tuple[str, ...]
    expires_at: datetime
    nonce: str | None


@dataclass(frozen=True)
class AuthorizationAttempt:
    authorization_url: str
    state: str
    nonce: str
    host_id: str


@dataclass(frozen=True)
class OnboardingResult:
    status: str
    host_id: str
    account_id: str | None
    advertise_online: bool
    retry_count: int = 0
    next_retry_at: str | None = None


class OriginClient(Protocol):
    def exchange_code(
        self, *, code: str, code_verifier: str, redirect_uri: str
    ) -> TokenSet: ...

    def refresh(self, refresh_token: str) -> TokenSet: ...

    def register_host(
        self,
        *,
        access_token: str,
        host_id: str,
        capability_visibility: str,
    ) -> None: ...


@dataclass(frozen=True)
class _AttemptSecret:
    nonce: str
    code_verifier: str
    host_id: str


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


class OnboardingService:
    """Bind one installed host to an existing TinyAssets account."""

    def __init__(
        self,
        *,
        state_dir: Path,
        oauth: OAuthConfig,
        origin: OriginClient,
        credentials: DesktopCredentialManager | None = None,
        clock=_utc_now,
    ) -> None:
        self._state_dir = Path(state_dir)
        self._state_path = self._state_dir / "onboarding.json"
        self._host_path = self._state_dir / "host.json"
        self._oauth = oauth
        self._origin = origin
        self._credentials = credentials or DesktopCredentialManager()
        self._clock = clock
        self._attempts: dict[str, _AttemptSecret] = {}

    def begin_authorization(self) -> AuthorizationAttempt:
        host_id = self._host_id()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        self._attempts[state] = _AttemptSecret(
            nonce=nonce,
            code_verifier=verifier,
            host_id=host_id,
        )
        self._write_state(
            status="authorization_pending",
            host_id=host_id,
            attempt_id=uuid.uuid4().hex,
            account_id=None,
            credential_reference=None,
            retry_count=0,
            next_retry_at=None,
        )
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._oauth.client_id,
                "redirect_uri": self._oauth.redirect_uri,
                "scope": "openid offline_access",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return AuthorizationAttempt(
            authorization_url=f"{self._oauth.authorize_endpoint}?{query}",
            state=state,
            nonce=nonce,
            host_id=host_id,
        )

    def complete_authorization(
        self,
        *,
        state: str,
        code: str,
        redirect_uri: str,
    ) -> OnboardingResult:
        attempt = self._attempts.get(state)
        if attempt is None:
            raise AuthorizationValidationError("authorization state does not match")
        if redirect_uri != self._oauth.redirect_uri:
            raise AuthorizationValidationError("authorization redirect binding does not match")
        tokens = self._origin.exchange_code(
            code=code,
            code_verifier=attempt.code_verifier,
            redirect_uri=redirect_uri,
        )
        self._validate_tokens(tokens, expected_nonce=attempt.nonce)
        reference = self._credentials.save_refresh_token(
            account_id=tokens.subject,
            host_id=attempt.host_id,
            refresh_token=tokens.refresh_token,
        )
        del self._attempts[state]
        return self._register_or_defer(
            tokens=tokens,
            host_id=attempt.host_id,
            credential_reference=reference,
            retry_count=0,
        )

    def recover_pending_registration(self) -> OnboardingResult:
        state = self._read_state()
        if not state:
            return OnboardingResult(
                status="authorization_required",
                host_id=self._host_id(),
                account_id=None,
                advertise_online=False,
            )
        status = str(state["status"])
        if status == "online":
            return self._result_from_state(state)
        if status != "pending_registration":
            return self._result_from_state(state)
        reference = str(state["credential_reference"])
        refresh_token = self._credentials.load_refresh_token(reference)
        if not refresh_token:
            self._write_state(
                **(state | {
                    "status": "authorization_required",
                    "credential_reference": None,
                })
            )
            return self._result_from_state(self._read_state())
        try:
            tokens = self._origin.refresh(refresh_token)
        except OriginUnavailable:
            return self._defer_retry(state)
        except AuthorizationRejected:
            self._write_state(**(state | {"status": "authorization_required"}))
            return self._result_from_state(self._read_state())
        self._validate_tokens(tokens, expected_nonce=None)
        if tokens.subject != state["account_id"]:
            raise AuthorizationValidationError(
                "refreshed token account does not match pending registration"
            )
        if tokens.refresh_token != refresh_token:
            self._credentials.save_refresh_token(
                account_id=tokens.subject,
                host_id=str(state["host_id"]),
                refresh_token=tokens.refresh_token,
            )
        return self._register_or_defer(
            tokens=tokens,
            host_id=str(state["host_id"]),
            credential_reference=reference,
            retry_count=int(state["retry_count"]),
        )

    def _register_or_defer(
        self,
        *,
        tokens: TokenSet,
        host_id: str,
        credential_reference: str,
        retry_count: int,
    ) -> OnboardingResult:
        state = {
            "status": "pending_registration",
            "host_id": host_id,
            "attempt_id": None,
            "account_id": tokens.subject,
            "credential_reference": credential_reference,
            "retry_count": retry_count,
            "next_retry_at": None,
        }
        try:
            self._origin.register_host(
                access_token=tokens.access_token,
                host_id=host_id,
                capability_visibility="self",
            )
        except OriginUnavailable:
            return self._defer_retry(state)
        self._write_state(**(state | {"status": "online", "next_retry_at": None}))
        return self._result_from_state(self._read_state())

    def _defer_retry(self, state: dict[str, object]) -> OnboardingResult:
        retry_count = int(state.get("retry_count", 0)) + 1
        delay = min(300, 2 ** min(retry_count, 8))
        next_retry = (self._clock() + timedelta(seconds=delay)).isoformat()
        self._write_state(
            **(
                state
                | {
                    "status": "pending_registration",
                    "retry_count": retry_count,
                    "next_retry_at": next_retry,
                }
            )
        )
        return self._result_from_state(self._read_state())

    def _validate_tokens(
        self, tokens: TokenSet, *, expected_nonce: str | None
    ) -> None:
        if tokens.issuer != self._oauth.issuer:
            raise AuthorizationValidationError("token issuer does not match")
        if self._oauth.audience not in tokens.audience:
            raise AuthorizationValidationError("token audience does not match")
        expiry = tokens.expires_at
        if expiry.tzinfo is None:
            raise AuthorizationValidationError("token expiry must be timezone-aware")
        if expiry <= self._clock():
            raise AuthorizationValidationError("token is expired")
        if expected_nonce is not None and tokens.nonce != expected_nonce:
            raise AuthorizationValidationError("token nonce does not match")
        if not tokens.subject or not tokens.access_token or not tokens.refresh_token:
            raise AuthorizationValidationError("token response is incomplete")

    def _host_id(self) -> str:
        try:
            payload = json.loads(self._host_path.read_text(encoding="utf-8"))
            host_id = payload["host_id"]
            if isinstance(host_id, str) and host_id:
                return host_id
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            pass
        host_id = f"host-{uuid.uuid4().hex}"
        _atomic_json(self._host_path, {"host_id": host_id})
        return host_id

    def _read_state(self) -> dict[str, object]:
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_state(self, **state: object) -> None:
        allowed = {
            "account_id",
            "attempt_id",
            "credential_reference",
            "host_id",
            "next_retry_at",
            "retry_count",
            "status",
        }
        unknown = set(state) - allowed
        if unknown:
            raise ValueError(f"secret or unknown onboarding state fields: {sorted(unknown)}")
        _atomic_json(self._state_path, state)

    @staticmethod
    def _result_from_state(state: dict[str, object]) -> OnboardingResult:
        return OnboardingResult(
            status=str(state["status"]),
            host_id=str(state["host_id"]),
            account_id=(
                str(state["account_id"]) if state.get("account_id") is not None else None
            ),
            advertise_online=state["status"] == "online",
            retry_count=int(state.get("retry_count", 0)),
            next_retry_at=(
                str(state["next_retry_at"])
                if state.get("next_retry_at") is not None
                else None
            ),
        )


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


class AutostartManager:
    """Own exactly one per-user native autostart entry for the tray."""

    _WINDOWS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    _WINDOWS_VALUE = "TinyAssets"
    _MAC_LABEL = "io.tinyassets.tray"

    def __init__(
        self,
        *,
        command: list[str],
        platform_name: str | None = None,
        config_home: Path | None = None,
    ) -> None:
        if not command or any(not item for item in command):
            raise ValueError("autostart command must contain non-empty arguments")
        self._command = list(command)
        self._platform = platform_name or sys.platform
        if config_home is not None:
            self._config_home = Path(config_home)
        elif self._platform == "darwin":
            self._config_home = Path.home() / "Library" / "LaunchAgents"
        else:
            self._config_home = Path(
                os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
            )

    def enable(self) -> Path:
        if self._platform == "win32":
            return self._enable_windows()
        if self._platform == "darwin":
            return self._enable_macos()
        if self._platform.startswith("linux"):
            return self._enable_linux()
        raise NotImplementedError(
            f"autostart is not implemented for platform {self._platform!r}"
        )

    def disable(self) -> None:
        if self._platform == "win32":
            self._disable_windows()
            return
        path = self._entry_path()
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def _entry_path(self) -> Path:
        if self._platform == "darwin":
            return self._config_home / f"{self._MAC_LABEL}.plist"
        if self._platform.startswith("linux"):
            return self._config_home / "autostart" / "tinyassets.desktop"
        return Path("HKCU") / self._WINDOWS_KEY / self._WINDOWS_VALUE

    def _enable_windows(self) -> Path:
        import winreg

        command = subprocess.list2cmdline(self._command)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self._WINDOWS_KEY) as key:
            winreg.SetValueEx(
                key,
                self._WINDOWS_VALUE,
                0,
                winreg.REG_SZ,
                command,
            )
        return self._entry_path()

    def _disable_windows(self) -> None:
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self._WINDOWS_KEY,
                0,
                winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, self._WINDOWS_VALUE)
        except FileNotFoundError:
            pass

    def _enable_macos(self) -> Path:
        path = self._entry_path()
        payload = {
            "Label": self._MAC_LABEL,
            "ProgramArguments": self._command,
            "RunAtLoad": True,
            "KeepAlive": False,
        }
        _atomic_bytes(path, plistlib.dumps(payload, sort_keys=True))
        return path

    def _enable_linux(self) -> Path:
        path = self._entry_path()
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=TinyAssets\n"
            f"Exec={shlex.join(self._command)}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n"
        )
        _atomic_bytes(path, content.encode("utf-8"))
        return path


@dataclass(frozen=True)
class UninstallResult:
    program_removed: bool
    autostart_removed: bool
    user_content_preserved: bool
    user_content_path: Path


class ContentPreservingUninstaller:
    """Remove packaged application files while refusing to delete user data."""

    def __init__(
        self,
        *,
        install_root: Path,
        data_root: Path,
        autostart: AutostartManager,
    ) -> None:
        self._install_root = Path(install_root).resolve()
        self._data_root = Path(data_root).resolve()
        self._autostart = autostart

    def uninstall(self) -> UninstallResult:
        if self._install_root.parent == self._install_root:
            raise ValueError("refusing to uninstall a filesystem root")
        if self._install_root == Path.home().resolve():
            raise ValueError("refusing to uninstall the user home directory")
        if self._data_root.is_relative_to(self._install_root):
            raise ValueError(
                "user content is inside the install root; move or export it "
                "before uninstalling"
            )
        self._autostart.disable()
        if self._install_root.exists():
            shutil.rmtree(self._install_root)
        return UninstallResult(
            program_removed=not self._install_root.exists(),
            autostart_removed=True,
            user_content_preserved=self._data_root.exists(),
            user_content_path=self._data_root,
        )


__all__ = [
    "AuthorizationAttempt",
    "AuthorizationRejected",
    "AuthorizationValidationError",
    "AutostartManager",
    "ContentPreservingUninstaller",
    "OAuthConfig",
    "OnboardingResult",
    "OnboardingService",
    "OriginClient",
    "OriginUnavailable",
    "TokenSet",
    "UninstallResult",
]
