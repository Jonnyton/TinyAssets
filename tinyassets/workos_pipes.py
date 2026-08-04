"""Secret-safe client for the WorkOS Pipes data-integration API."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

_BASE_URL = "https://api.workos.com"
_USER_ID = re.compile(r"user_[A-Za-z0-9]+\Z")
_GITHUB_SLUG = "github"


class WorkOSPipesError(RuntimeError):
    """A redacted WorkOS Pipes failure."""


@dataclass(frozen=True)
class ConnectedAccount:
    state: str
    account_id: str | None
    scopes: tuple[str, ...]


def _require_user_id(user_id: str) -> str:
    value = str(user_id or "").strip()
    if _USER_ID.fullmatch(value) is None:
        raise WorkOSPipesError("WorkOS user identity is invalid")
    return value


def _safe_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise WorkOSPipesError("WorkOS returned an invalid authorization URL")
    return url


def _json_object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkOSPipesError("WorkOS returned an invalid response")
    return value


class WorkOSPipesClient:
    """Small injectable API client; callers never receive bearer credentials."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = _BASE_URL,
        request: Callable[..., Any] | None = None,
    ) -> None:
        selected_key = api_key if api_key is not None else os.environ.get("WORKOS_API_KEY", "")
        self._api_key = selected_key.strip()
        self._base_url = base_url.rstrip("/")
        self._request = request or urllib.request.urlopen

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._api_key:
            raise WorkOSPipesError("WorkOS Pipes is not configured")
        payload = None
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": "tinyassets-workos-pipes/1.0",
        }
        if body is not None:
            payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            data=payload,
            headers=headers,
            method=method,
        )
        try:
            with self._request(request, timeout=20) as response:
                raw = response.read(256 * 1024)
            parsed = json.loads(raw.decode("utf-8"))
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            raise WorkOSPipesError("WorkOS Pipes request failed") from None
        return _json_object(parsed)

    def authorization_url(self, *, user_id: str, return_to: str) -> str:
        owner = _require_user_id(user_id)
        result = self._call(
            "POST",
            f"/data-integrations/{_GITHUB_SLUG}/authorize",
            {"user_id": owner, "return_to": _safe_url(return_to)},
        )
        return _safe_url(result.get("url"))

    def connected_account(self, *, user_id: str) -> ConnectedAccount:
        owner = _require_user_id(user_id)
        result = self._call(
            "GET",
            f"/user_management/users/{urllib.parse.quote(owner, safe='')}"
            f"/connected_accounts/{_GITHUB_SLUG}",
        )
        scopes = result.get("scopes", [])
        if not isinstance(scopes, list) or not all(isinstance(item, str) for item in scopes):
            raise WorkOSPipesError("WorkOS returned invalid connected-account scopes")
        account_id = result.get("id")
        if account_id is not None and not isinstance(account_id, str):
            raise WorkOSPipesError("WorkOS returned invalid connected-account identity")
        return ConnectedAccount(
            state=str(result.get("state") or ""),
            account_id=account_id,
            scopes=tuple(scopes),
        )

    def vend_credential(self, *, user_id: str) -> str:
        owner = _require_user_id(user_id)
        result = self._call(
            "POST",
            f"/data-integrations/{_GITHUB_SLUG}/credentials",
            {"user_id": owner},
        )
        if result.get("active") is not True:
            raise WorkOSPipesError("WorkOS connected account is not active")
        credential = _json_object(result.get("credential"))
        value = credential.get("value")
        if not isinstance(value, str) or not value.strip():
            raise WorkOSPipesError("WorkOS returned no usable credential")
        return value


__all__ = ["ConnectedAccount", "WorkOSPipesClient", "WorkOSPipesError"]
