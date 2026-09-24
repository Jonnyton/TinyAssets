"""OAuth 2.0 tokens for a connection: the vault encoding, the exchange, and refresh.

The vault keeps ONE opaque string per connection (``vault://http/<name>``). For
an ``oauth2`` connection that string is a JSON bundle::

    {"scheme": "oauth2", "v": 1, "access_token", "token_type", "expires_at",
     "refresh_token", "token_url", "client_id", "scope"}

The token URL and client id live in the bundle, not on the readable connection
row, because the refresh token is sent there: only the owner's completed
sign-in writes them, and nothing an agent can configure moves them.

Refresh is generic and happens inside the credential-blind broker, before the
access token is within :data:`REFRESH_SKEW_SECONDS` of expiry and again once
when the service answers 401. It is **single-flight per connection** across
threads and processes (a per-connection lock, and a re-read of the vault inside
it), so concurrent calls never spend a single-use refresh token twice. A rotated
refresh token is written back through the vault's atomic write before the new
access token is used. The vault's exclusive admission is taken BEFORE the
refresh token is spent, so a token the provider rotates can always be saved: if
the vault cannot be held, nothing is spent and the call fails retryably.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterator

from tinyassets.connection_oauth.transport import (
    OAuthError,
    request_json,
    server_error_detail,
    validate_https_url,
)

SCHEME = "oauth2"
REFRESH_SKEW_SECONDS = 60.0
#: How long a caller waits for another holder's refresh before failing loudly.
LOCK_WAIT_SECONDS = 45.0
_MAX_TOKEN_CHARS = 8192


@dataclass(frozen=True)
class TokenBundle:
    access_token: str
    token_url: str
    client_id: str
    refresh_token: str = ""
    expires_at: float | None = None
    scope: str = ""
    token_type: str = "Bearer"

    def expiring(self, now: float | None = None) -> bool:
        if self.expires_at is None:
            return False  # unknown lifetime: refresh only when the service says 401
        return (now if now is not None else time.time()) >= self.expires_at - REFRESH_SKEW_SECONDS

    def secret_values(self) -> tuple[str, ...]:
        return tuple(v for v in (self.access_token, self.refresh_token) if v)


def encode(bundle: TokenBundle) -> str:
    return json.dumps({
        "scheme": SCHEME, "v": 1, "access_token": bundle.access_token,
        "token_type": bundle.token_type, "expires_at": bundle.expires_at,
        "refresh_token": bundle.refresh_token, "token_url": bundle.token_url,
        "client_id": bundle.client_id, "scope": bundle.scope,
    }, sort_keys=True, separators=(",", ":"))


def looks_like_bundle(text: Any) -> bool:
    """True for the deposited oauth2 encoding. Never returns or logs values."""
    if not isinstance(text, str) or not text.lstrip().startswith("{"):
        return False
    try:
        doc = json.loads(text)
    except (TypeError, ValueError):
        return False
    return isinstance(doc, dict) and doc.get("scheme") == SCHEME


def _token(value: Any) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= _MAX_TOKEN_CHARS
            or any(ord(c) < 33 or ord(c) > 126 for c in value)):
        raise ValueError("token is not a printable single value")
    return value


def decode(text: str) -> TokenBundle:
    if not looks_like_bundle(text):
        raise ValueError("credential is not an oauth2 token bundle")
    doc = json.loads(text)
    expires = doc.get("expires_at")
    if expires is not None and (isinstance(expires, bool) or not isinstance(expires, (int, float))):
        raise ValueError("expires_at must be a number")
    refresh = doc.get("refresh_token") or ""
    return TokenBundle(
        access_token=_token(doc.get("access_token")),
        token_url=validate_https_url(doc.get("token_url")),
        client_id=_token(doc.get("client_id")),
        refresh_token=_token(refresh) if refresh else "",
        expires_at=float(expires) if expires is not None else None,
        scope=str(doc.get("scope") or ""),
        token_type=str(doc.get("token_type") or "Bearer"),
    )


def _token_response(status: int, doc: Any, *, secrets: tuple[str, ...]) -> dict[str, Any]:
    if status != 200 or not isinstance(doc, dict):
        raise OAuthError("token_request_failed", server_error_detail(status, doc, secrets),
                         status=status)
    try:
        _token(doc.get("access_token"))
    except ValueError:
        raise OAuthError("token_response_invalid", "no usable access_token") from None
    token_type = str(doc.get("token_type") or "Bearer")
    if token_type.lower() != "bearer":
        # A sender-constrained type (DPoP, MAC) needs proof the broker does not
        # build. Refused loudly rather than sent as something it is not.
        raise OAuthError("unsupported_token_type", f"token_type {token_type[:32]}")
    return doc


def _expires_at(doc: dict[str, Any], now: float) -> float | None:
    value = doc.get("expires_in")
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return now + float(value)


def exchange_code(*, token_url: str, client_id: str, code: str, verifier: str,
                  redirect_uri: str) -> TokenBundle:
    """RFC 6749 §4.1.3 with the RFC 7636 verifier; exactly one attempt."""
    now = time.time()
    status, doc = request_json("POST", token_url, form={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        "client_id": client_id, "code_verifier": verifier,
    }, secrets=(code, verifier))
    doc = _token_response(status, doc, secrets=(code, verifier))
    return TokenBundle(
        access_token=doc["access_token"], token_url=token_url, client_id=client_id,
        refresh_token=_token(doc["refresh_token"]) if doc.get("refresh_token") else "",
        expires_at=_expires_at(doc, now), scope=str(doc.get("scope") or ""),
    )


def refresh(bundle: TokenBundle) -> TokenBundle:
    """RFC 6749 §6. A server that rotates returns a new refresh token; one that
    does not leaves the old one valid, so it is kept."""
    now = time.time()
    secrets = bundle.secret_values()
    status, doc = request_json("POST", bundle.token_url, form={
        "grant_type": "refresh_token", "refresh_token": bundle.refresh_token,
        "client_id": bundle.client_id,
    }, secrets=secrets)
    doc = _token_response(status, doc, secrets=secrets)
    rotated = doc.get("refresh_token")
    return replace(
        bundle, access_token=doc["access_token"],
        refresh_token=_token(rotated) if rotated else bundle.refresh_token,
        expires_at=_expires_at(doc, now), scope=str(doc.get("scope") or bundle.scope),
    )


# --------------------------------------------------------------------------- #
# Single-flight refresh, inside the broker.
# --------------------------------------------------------------------------- #

_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _thread_lock(key: str) -> threading.Lock:
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.Lock())


@contextmanager
def _file_lock(path: Path, deadline: float) -> Iterator[None]:
    """An exclusive OS lock on ``path``, polled until ``deadline``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            while True:
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("connection refresh lock is busy") from None
                    time.sleep(0.02)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("connection refresh lock is busy") from None
                    time.sleep(0.02)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


class ConnectionTokens:
    """Current access token for one universe's oauth2 connections.

    Built inside the broker child from its own config: the universe directory
    whose vault holds the bundle and the owner the vault records it under. A
    refresh that fails raises
    :class:`~tinyassets.storage.outbound_connections.ConnectionAuthorizationError`,
    an ordinary connection failure (stage ``connection``, class ``auth``) with
    the token endpoint's own words as its detail.
    """

    def __init__(self, *, universe_dir: str | Path, owner_user_id: str) -> None:
        self._universe_dir = Path(universe_dir)
        self._owner = str(owner_user_id)

    # The vault seam: read and write the ONE record, by its destination.
    def _read(self, destination: str) -> str:
        from tinyassets.credential_vault import load_credential_vault

        for record in load_credential_vault(self._universe_dir):
            if (str(record.get("credential_type") or "").lower() == "http"
                    and str(record.get("destination") or "").strip() == destination):
                value = record.get("token")
                if isinstance(value, str) and value.strip():
                    return value.strip()
        raise LookupError("credential reference is unavailable")

    def _write(self, destination: str, bundle: TokenBundle) -> None:
        from tinyassets.credential_vault import write_credential_vault

        write_credential_vault(
            self._universe_dir,
            [{"credential_type": "http", "service": destination,
              "destination": destination, "token": encode(bundle)}],
            owner_user_id=self._owner, universe_id=self._universe_dir.name,
        )

    def _lock_path(self, destination: str) -> Path:
        digest = hashlib.sha256(destination.encode("utf-8")).hexdigest()[:32]
        return self._universe_dir / ".oauth-refresh" / f"{digest}.lock"

    @staticmethod
    def _failed(detail: str):
        from tinyassets.storage.outbound_connections import ConnectionAuthorizationError

        return ConnectionAuthorizationError(detail)

    def current(self, destination: str, credential: str, *, rejected: str = "") -> TokenBundle:
        """The bundle whose access token to send now.

        ``rejected`` is an access token the service just answered 401 to; the
        stored one is refreshed unless another holder already replaced it.
        """
        try:
            bundle = decode(credential)
        except ValueError:
            raise self._failed("the stored authorization is unreadable; reconnect") from None
        if not rejected and not bundle.expiring():
            return bundle
        key = f"{self._universe_dir.resolve()}::{destination}"
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        locked = False
        with _thread_lock(key):
            try:
                with _file_lock(self._lock_path(destination), deadline):
                    locked = True
                    return self._refresh_locked(destination, rejected, deadline)
            except TimeoutError:
                if locked:
                    raise
                raise self._failed("another refresh of this connection did not finish") from None

    def _hold_vault(self, deadline: float) -> tuple[ExitStack, Any]:
        """The vault's exclusive admission, retried until ``deadline``.

        Held BEFORE the refresh token is spent. The cross-process admission is
        a bounded lock (on Windows it gives up after about a second), so a
        refresh that took it only to WRITE could rotate the token at the
        provider and then fail to save it, losing the connection.
        """
        from tinyassets.credential_vault import exclusive_credential_vault

        while True:
            stack = ExitStack()
            try:
                write = stack.enter_context(exclusive_credential_vault(self._universe_dir))
                return stack, write
            except (TimeoutError, OSError):
                stack.close()
                if time.monotonic() >= deadline:
                    raise self._failed(
                        "this connection's vault stayed busy; nothing was spent, try again"
                    ) from None
                time.sleep(0.05)

    def _refresh_locked(self, destination: str, rejected: str, deadline: float) -> TokenBundle:
        stack, write = self._hold_vault(deadline)
        with stack:
            # Re-read INSIDE the locks: the holder before us may have rotated it.
            try:
                current = decode(self._read(destination))
            except (LookupError, ValueError):
                raise self._failed("the stored authorization is unreadable; reconnect") from None
            now = time.time()
            # Another holder already refreshed: use theirs, never spend the
            # (possibly single-use) refresh token a second time.
            if not current.expiring(now) and (not rejected or current.access_token != rejected):
                return current
            if not current.refresh_token:
                raise self._failed(
                    "the provider issued no refresh token; reconnect to sign in again")
            try:
                fresh = refresh(current)
            except OAuthError as exc:
                raise self._failed(exc.detail or exc.code) from None
            record = [{"credential_type": "http", "service": destination,
                       "destination": destination, "token": encode(fresh)}]
            # Still holding the vault: only a storage fault can stop this write,
            # so it is retried until the deadline rather than given up once.
            while True:
                try:
                    write(record, owner_user_id=self._owner,
                          universe_id=self._universe_dir.name)
                    return fresh
                except Exception:  # noqa: BLE001 - a rotated token that is not saved is lost
                    if time.monotonic() >= deadline:
                        raise self._failed(
                            "the refreshed authorization could not be saved; reconnect"
                        ) from None
                    time.sleep(0.05)
