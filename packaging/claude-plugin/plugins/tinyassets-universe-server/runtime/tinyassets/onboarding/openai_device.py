"""One-tap OpenAI (ChatGPT subscription) linking for the onboarding app.

Implements the OAuth *device-authorization* flow the Codex CLI itself uses
(``codex login --device-auth``), brokered by the daemon so a phone user never
generates, copies, or pastes a token:

1. ``start`` — the daemon asks OpenAI for a short user code. The app shows it and
   opens ``https://auth.openai.com/codex/device`` in an in-app tab; the user
   signs in (they are usually already signed in to ChatGPT) and approves.
2. ``poll`` — the app polls the daemon; the daemon polls OpenAI once per call.
   When OpenAI reports approval it hands back an authorization code *plus the
   PKCE verifier it generated*; the daemon exchanges that for tokens, builds the
   exact ``auth.json`` the Codex CLI reads, and deposits it through the landed
   ``connect_llm`` handler AS THE SIGNED-IN USER. The tokens never touch the
   browser, the chat, or a log line.

Flow constants are taken from the Codex CLI source
(``codex-rs/login/src/device_code_auth.rs`` + ``server.rs``, read 2026-08-21).
The client id is Codex's public OAuth client — OpenAI has not restricted
third-party use of it (unlike Anthropic, whose terms forbid it; the Claude path
therefore stays on Claude Code's own ``claude setup-token``).

The broker is stateless: ``device_auth_id`` + ``user_code`` round-trip through
the app between calls, exactly as the CLI keeps them in memory. Nothing from the
flow is persisted except the final vault record.
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
from typing import Any, Callable

import httpx

OPENAI_ISSUER = "https://auth.openai.com"
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"

_DEVICE_USERCODE_URL = f"{OPENAI_ISSUER}/api/accounts/deviceauth/usercode"
_DEVICE_TOKEN_URL = f"{OPENAI_ISSUER}/api/accounts/deviceauth/token"
_DEVICE_REDIRECT_URI = f"{OPENAI_ISSUER}/deviceauth/callback"
_OAUTH_TOKEN_URL = f"{OPENAI_ISSUER}/oauth/token"
VERIFICATION_URL = f"{OPENAI_ISSUER}/codex/device"

_TIMEOUT = 20.0

# Test seam: a factory returning an httpx.AsyncClient (tests pass a
# MockTransport). Production uses a plain client.
ClientFactory = Callable[[], httpx.AsyncClient]


def _default_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=_TIMEOUT)


class DeviceAuthError(Exception):
    """A secret-free, user-presentable failure of the device flow."""

    def __init__(self, code: str, status: int = 502) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def _opaque(value: Any, limit: int = 256) -> str:
    """A bounded string field from an untrusted JSON document, never the whole doc."""
    text = str(value or "").strip()
    if len(text) > limit:
        raise DeviceAuthError("device_response_invalid")
    return text


async def start_device_auth(client_factory: ClientFactory = _default_client) -> dict[str, Any]:
    """Request a user code. Returns public fields only (no secrets exist yet)."""
    try:
        async with client_factory() as client:
            resp = await client.post(
                _DEVICE_USERCODE_URL,
                json={"client_id": CODEX_CLIENT_ID},
                headers={"Content-Type": "application/json"},
            )
    except httpx.HTTPError:
        raise DeviceAuthError("openai_unreachable") from None
    if resp.status_code == 404:
        raise DeviceAuthError("device_login_unavailable", 503)
    if resp.status_code >= 400:
        raise DeviceAuthError("device_start_failed")
    try:
        doc = resp.json()
    except ValueError:
        raise DeviceAuthError("device_response_invalid") from None
    if not isinstance(doc, dict):
        raise DeviceAuthError("device_response_invalid")
    device_auth_id = _opaque(doc.get("device_auth_id"))
    user_code = _opaque(doc.get("user_code") or doc.get("usercode"), 64)
    if not device_auth_id or not user_code:
        raise DeviceAuthError("device_response_invalid")
    try:
        interval = int(doc.get("interval") or 5)
    except (TypeError, ValueError):
        interval = 5
    return {
        "device_auth_id": device_auth_id,
        "user_code": user_code,
        "verification_url": VERIFICATION_URL,
        "interval": max(2, min(interval, 30)),
    }


def _jwt_claim(token: str, claim: str) -> str:
    """Read one claim from an (unverified) JWT payload — the Codex CLI derives
    ``account_id`` from the id_token the same way. Returns "" on any problem."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        value = claims.get(claim, "")
        return value if isinstance(value, str) else ""
    except Exception:  # noqa: BLE001 - malformed token → no account id, never raise
        return ""


def build_codex_auth_json(*, id_token: str, access_token: str, refresh_token: str) -> str:
    """The exact ``$CODEX_HOME/auth.json`` document the Codex CLI writes after
    a ChatGPT login (``AuthDotJson`` in ``codex-rs/login/src/auth/storage.rs``)."""
    tokens: dict[str, Any] = {
        "id_token": id_token,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }
    account_id = _jwt_claim(id_token, "chatgpt_account_id")
    if account_id:
        tokens["account_id"] = account_id
    doc = {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": None,
        "tokens": tokens,
        "last_refresh": _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return json.dumps(doc)


async def poll_device_auth(
    *,
    device_auth_id: str,
    user_code: str,
    client_factory: ClientFactory = _default_client,
) -> dict[str, Any] | None:
    """One poll. ``None`` while the user has not approved yet; on approval,
    exchanges the code and returns the ``auth.json`` text under ``auth_json``
    (the caller deposits it and must never return it to a client)."""
    device_auth_id = _opaque(device_auth_id)
    user_code = _opaque(user_code, 64)
    if not device_auth_id or not user_code:
        raise DeviceAuthError("missing_fields", 400)
    try:
        async with client_factory() as client:
            resp = await client.post(
                _DEVICE_TOKEN_URL,
                json={"device_auth_id": device_auth_id, "user_code": user_code},
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code in (403, 404):
                return None  # pending — the CLI treats these as "not yet"
            if resp.status_code >= 400:
                raise DeviceAuthError("device_poll_failed")
            try:
                doc = resp.json()
            except ValueError:
                raise DeviceAuthError("device_response_invalid") from None
            if not isinstance(doc, dict):
                raise DeviceAuthError("device_response_invalid")
            code = _opaque(doc.get("authorization_code"), 2048)
            verifier = _opaque(doc.get("code_verifier"), 512)
            if not code or not verifier:
                raise DeviceAuthError("device_response_invalid")
            # PKCE exchange — identical to the CLI's exchange_code_for_tokens.
            tok = await client.post(
                _OAUTH_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _DEVICE_REDIRECT_URI,
                    "client_id": CODEX_CLIENT_ID,
                    "code_verifier": verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.HTTPError:
        raise DeviceAuthError("openai_unreachable") from None
    if tok.status_code >= 400:
        raise DeviceAuthError("token_exchange_failed")
    try:
        tdoc = tok.json()
    except ValueError:
        raise DeviceAuthError("token_response_invalid") from None
    if not isinstance(tdoc, dict):
        raise DeviceAuthError("token_response_invalid")
    id_token = str(tdoc.get("id_token") or "")
    access_token = str(tdoc.get("access_token") or "")
    refresh_token = str(tdoc.get("refresh_token") or "")
    if not (id_token and access_token and refresh_token):
        raise DeviceAuthError("token_response_invalid")
    return {
        "auth_json": build_codex_auth_json(
            id_token=id_token, access_token=access_token, refresh_token=refresh_token
        )
    }


def deposit_codex_auth_json(auth_json: str, *, universe_id: str = "") -> dict[str, Any]:
    """Deposit through the landed ``connect_llm`` handler under the CURRENT
    request identity (set by the auth middleware from the app's bearer). Every
    gate inside ``connect_llm`` still runs — the universe admin ACL and the
    vault's owner binding — so a stranger's bearer cannot overwrite an owner's
    credential."""
    from tinyassets.api.llm_deposit import connect_llm

    material = base64.b64encode(auth_json.encode("utf-8")).decode("ascii")
    return connect_llm(
        universe_id=universe_id,
        payload={"service": "codex", "auth_material_b64": material},
    )


__all__ = [
    "CODEX_CLIENT_ID",
    "OPENAI_ISSUER",
    "VERIFICATION_URL",
    "DeviceAuthError",
    "start_device_auth",
    "poll_device_auth",
    "build_codex_auth_json",
    "deposit_codex_auth_json",
]
