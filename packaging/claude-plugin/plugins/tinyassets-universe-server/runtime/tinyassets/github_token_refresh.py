"""Vault-backed GitHub token lifecycle (S5 seam; consumed by S4's client).

Two flows, both driven by the FROZEN vault contract — this module never
stores, logs, or returns raw values outside :class:`SecretBytes` containers:

* **App JWT -> installation token** (:func:`mint_installation_token`): the
  non-expiring App private key (``GITHUB_APP_PRIVATE_KEY``, the crown jewel)
  stays in platform custody; a short-lived RS256 JWT mints a ~1h
  repository/permission-restricted installation token **in memory** — never
  persisted, never vaulted.
* **User-token refresh rotation** (:func:`refresh_user_token`): GitHub App
  user tokens expire in ~8h with ONE-USE ~6mo refresh tokens. Rotation drives
  the vault's ``begin_refresh``/``complete_refresh`` consume-before-mint pair
  so exactly one redemption can ever happen per stored refresh token — a
  replayed refresh would revoke the whole token family at GitHub.

The stored ``GITHUB_APP_USER_TOKEN`` value is a JSON bundle::

    {"access_token": ..., "refresh_token": ...,
     "expires_at": <epoch|null>, "refresh_token_expires_at": <epoch|null>}

The vault record's ``expires_at`` is the REFRESH token expiry (when the
record becomes unrecoverable and re-authorization is required); the access
token's shorter expiry lives inside the bundle.

Provider ``invalid_grant``-class rejections raise
``CredentialUnavailable(REAUTHORIZATION_REQUIRED)`` — no fallback, the user
must reconnect (design note, "Chat OAuth connect / disconnect" item 5).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, NoReturn

import jwt as pyjwt

from tinyassets.credentials import (
    CredentialUnavailable,
    PlatformVaultBackend,
    SecretBinding,
    SecretBytes,
    SecretDescriptor,
    SecretScope,
    VaultErrorCode,
)

GITHUB_API_BASE = "https://api.github.com"
GITHUB_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"

# GitHub caps App JWT lifetime at 10 minutes; 60s of iat backdating absorbs
# clock drift (both from the GitHub App auth docs).
APP_JWT_TTL_SECONDS = 540
APP_JWT_DRIFT_SECONDS = 60

_HTTP_TIMEOUT_SECONDS = 30.0

# OAuth error codes that mean the stored grant is dead: the user must
# re-authorize. Everything else is an exchange failure (retryable/operational).
_REAUTH_ERROR_CODES = frozenset(
    {"bad_refresh_token", "invalid_grant", "bad_verification_code"}
)

# (status, json_body) transports — injectable seams; defaults are real urllib.
JsonPost = Callable[[str, dict[str, str], dict[str, Any]], tuple[int, dict[str, Any]]]
FormPost = Callable[[str, dict[str, str]], tuple[int, dict[str, Any]]]


class GitHubTokenExchangeError(RuntimeError):
    """A token exchange failed operationally (non-auth-dead).

    Carries only the HTTP status and GitHub's machine ``error_code`` — never
    a token, JWT, or response body (bodies can echo request parameters).
    """

    def __init__(self, *, status: int, error_code: str = "") -> None:
        self.status = status
        self.error_code = error_code
        super().__init__(
            f"github token exchange failed [http {status}]"
            + (f" error={error_code}" if error_code else "")
        )


def _require_safe_url(url: str) -> None:
    """https only — plain http is allowed solely for loopback test servers."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1", "localhost"}:
        return
    raise GitHubTokenExchangeError(status=0, error_code="insecure_token_url")


def _read_response(resp: Any) -> tuple[int, dict[str, Any]]:
    raw = resp.read()
    try:
        body = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        body = {}
    return int(resp.status), body if isinstance(body, dict) else {}


def _http_post_json(
    url: str, headers: dict[str, str], payload: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    _require_safe_url(url)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS) as resp:
            return _read_response(resp)
    except urllib.error.HTTPError as exc:
        return _read_response(exc)


def _http_post_form(url: str, data: dict[str, str]) -> tuple[int, dict[str, Any]]:
    _require_safe_url(url)
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT_SECONDS) as resp:
            return _read_response(resp)
    except urllib.error.HTTPError as exc:
        return _read_response(exc)


# ---------------------------------------------------------------------------
# App JWT -> installation token
# ---------------------------------------------------------------------------


def github_app_jwt(
    private_key_pem: bytes, app_id: str, *, now: float | None = None
) -> str:
    """Mint the short-lived RS256 App JWT (iss=app_id, <=10min lifetime)."""
    issued = int(now if now is not None else time.time())
    claims = {
        "iat": issued - APP_JWT_DRIFT_SECONDS,
        "exp": issued + APP_JWT_TTL_SECONDS,
        "iss": str(app_id),
    }
    return pyjwt.encode(claims, private_key_pem, algorithm="RS256")


class InstallationToken:
    """An in-memory ~1h installation token. Never persisted, never vaulted.

    The token bytes live in a non-observable :class:`SecretBytes`; repr/str
    show only the expiry.
    """

    __slots__ = ("token", "expires_at", "permissions")

    def __init__(
        self,
        *,
        token: SecretBytes,
        expires_at: float,
        permissions: dict[str, str] | None = None,
    ) -> None:
        self.token = token
        self.expires_at = expires_at
        self.permissions = dict(permissions or {})

    def __repr__(self) -> str:
        return f"InstallationToken(token=<redacted>, expires_at={self.expires_at})"

    __str__ = __repr__

    def _refuse(*_a: object, **_k: object) -> NoReturn:
        raise TypeError("InstallationToken cannot be copied/serialized")

    __reduce__ = _refuse
    __reduce_ex__ = _refuse
    __getstate__ = _refuse
    __copy__ = _refuse
    __deepcopy__ = _refuse


def _parse_github_timestamp(value: object) -> float:
    if not isinstance(value, str) or not value.strip():
        raise GitHubTokenExchangeError(status=0, error_code="missing_expires_at")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise GitHubTokenExchangeError(
            status=0, error_code="malformed_expires_at"
        ) from None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.timestamp()


def mint_installation_token(
    backend: PlatformVaultBackend,
    binding: SecretBinding,
    expected: SecretScope,
    *,
    app_id: str,
    installation_id: str,
    api_base: str = GITHUB_API_BASE,
    http_post_json: JsonPost | None = None,
) -> InstallationToken:
    """Exchange the vaulted App private key for an in-memory installation token.

    * 201 -> token + expiry (parsed, in memory only).
    * 401 -> the App key/JWT was rejected: the vaulted PEM is dead ->
      ``REAUTHORIZATION_REQUIRED`` (re-deposit a valid key), no retry.
    * anything else -> :class:`GitHubTokenExchangeError` (operational).
    """
    post = http_post_json if http_post_json is not None else _http_post_json
    with backend.get(binding, expected) as lease:
        token_jwt = github_app_jwt(bytes(lease.reveal()), app_id)
    url = (
        f"{api_base.rstrip('/')}/app/installations/"
        f"{urllib.parse.quote(str(installation_id))}/access_tokens"
    )
    status, body = post(
        url,
        {
            "Authorization": f"Bearer {token_jwt}",
            "Accept": "application/vnd.github+json",
        },
        {},
    )
    if status == 401:
        raise CredentialUnavailable(
            VaultErrorCode.REAUTHORIZATION_REQUIRED, binding.ref
        )
    if status != 201:
        raise GitHubTokenExchangeError(
            status=status, error_code=str(body.get("message") or "")[:120]
        )
    token = body.get("token")
    if not isinstance(token, str) or not token:
        raise GitHubTokenExchangeError(status=status, error_code="missing_token")
    permissions = body.get("permissions")
    return InstallationToken(
        token=SecretBytes(token.encode("utf-8")),
        expires_at=_parse_github_timestamp(body.get("expires_at")),
        permissions=permissions if isinstance(permissions, dict) else None,
    )


# ---------------------------------------------------------------------------
# User-token refresh rotation
# ---------------------------------------------------------------------------


def encode_user_token_bundle(
    *,
    access_token: str,
    refresh_token: str,
    expires_at: float | None,
    refresh_token_expires_at: float | None,
) -> bytes:
    return json.dumps(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "refresh_token_expires_at": refresh_token_expires_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def decode_user_token_bundle(raw: bytes) -> dict[str, Any]:
    """Strict bundle decode — a malformed stored bundle is CORRUPT_RECORD."""
    try:
        bundle = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD) from None
    if not isinstance(bundle, dict):
        raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD)
    for field in ("access_token", "refresh_token"):
        value = bundle.get(field)
        if not isinstance(value, str) or not value:
            raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD)
    return bundle


def refresh_user_token(
    backend: PlatformVaultBackend,
    binding: SecretBinding,
    expected: SecretScope,
    *,
    client_id: str,
    client_secret: str = "",
    holder: str,
    token_url: str = GITHUB_OAUTH_TOKEN_URL,
    http_post_form: FormPost | None = None,
    now: float | None = None,
) -> SecretDescriptor | None:
    """Rotate the vaulted GitHub App user-token bundle (one redemption, ever).

    Serialized end to end: the coarse per-ref refresh lease reduces
    contention, and ``begin_refresh`` is the atomic consume-before-mint gate —
    only the sole winner reaches the provider. Returns ``None`` when another
    holder already advanced the record (caller re-reads the fresh bundle);
    the new descriptor on success.

    GitHub's OAuth token endpoint reports grant errors as an ``error`` field
    in a 200 JSON body (with ``Accept: application/json``) — status alone is
    NOT trusted. A dead grant (``bad_refresh_token``/``invalid_grant``) raises
    ``REAUTHORIZATION_REQUIRED``. A crash after ``begin_refresh`` but before
    completion is covered by the vault's wedge timeout, which also forces
    re-authorization — the honest answer once a one-use token MAY have been
    redeemed.
    """
    post = http_post_form if http_post_form is not None else _http_post_form
    with backend.refresh_lease(binding.ref, holder):
        with backend.get(binding, expected) as lease:
            bundle = decode_user_token_bundle(lease.reveal())
            version = lease.version
        ticket = backend.begin_refresh(binding, expected, holder, at_version=version)
        if ticket is None:
            return None  # version already advanced or claim in flight
        form = {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": bundle["refresh_token"],
        }
        if client_secret:
            form["client_secret"] = client_secret
        status, body = post(token_url, form)
        error_code = str(body.get("error") or "") if isinstance(body, dict) else ""
        if error_code in _REAUTH_ERROR_CODES:
            raise CredentialUnavailable(
                VaultErrorCode.REAUTHORIZATION_REQUIRED, binding.ref
            )
        if status != 200 or error_code:
            raise GitHubTokenExchangeError(status=status, error_code=error_code)
        access_token = body.get("access_token")
        new_refresh = body.get("refresh_token")
        if not isinstance(access_token, str) or not access_token:
            raise GitHubTokenExchangeError(status=status, error_code="missing_token")
        if not isinstance(new_refresh, str) or not new_refresh:
            # GitHub App user tokens ALWAYS rotate the refresh token; a reply
            # without one is not a usable rotation.
            raise GitHubTokenExchangeError(
                status=status, error_code="missing_refresh_token"
            )
        now_ts = now if now is not None else time.time()
        expires_in = body.get("expires_in")
        refresh_expires_in = body.get("refresh_token_expires_in")
        expires_at = (
            now_ts + float(expires_in)
            if isinstance(expires_in, (int, float))
            else None
        )
        refresh_token_expires_at = (
            now_ts + float(refresh_expires_in)
            if isinstance(refresh_expires_in, (int, float))
            else None
        )
        new_bundle = encode_user_token_bundle(
            access_token=access_token,
            refresh_token=new_refresh,
            expires_at=expires_at,
            refresh_token_expires_at=refresh_token_expires_at,
        )
        return backend.complete_refresh(
            binding,
            expected,
            ticket,
            SecretBytes(new_bundle),
            expires_at=refresh_token_expires_at,
        )
