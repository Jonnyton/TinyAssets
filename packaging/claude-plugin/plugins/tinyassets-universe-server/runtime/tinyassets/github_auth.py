"""GitHub auth strategies — a narrow ``TokenProvider`` protocol — S4 / E4.

This module supplies TOKENS to the GitHub client; it does NOT store or persist
them. Credential storage (App PEM at rest, owner user-token refresh) is a
parallel vault lane that will IMPLEMENT this protocol. Here we only:

- define the :class:`TokenProvider` contract + purposes;
- consume a token the vault supplies (:class:`StaticTokenProvider` — PAT
  fallback, or the owner user-access-token);
- mint short-lived App installation tokens from injected App credentials
  (:class:`GitHubAppTokenProvider`) — RS256 App JWT (≤10 min) → installation
  token (1h), cached IN MEMORY ONLY, never persisted or logged;
- route by purpose (:class:`CompositeTokenProvider`): App installation token for
  writes/reads, owner user token for review submission.

**Token values never appear in logs, errors, receipts, or ``repr``.** These
objects deliberately have no ``__repr__`` that prints the secret and raise
:class:`TokenUnavailable` (which carries no token) on failure.

See ``docs/ops/github-app-setup.md``.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Iterable, Protocol, runtime_checkable

#: The App installation token: App-authored PR create + merge + auto-merge +
#: ruleset/CODEOWNERS/PR reads (steady-state perms Contents:write +
#: Pull requests:write + Metadata:read).
PURPOSE_INSTALLATION = "installation"

#: The owner's USER access token: review submission, so GitHub attributes the
#: APPROVE / REQUEST_CHANGES to the owner (and the App-authored PR can't
#: self-approve).
PURPOSE_USER_REVIEW = "user_review"

VALID_PURPOSES = frozenset({PURPOSE_INSTALLATION, PURPOSE_USER_REVIEW})

#: Max App-JWT lifetime GitHub accepts is 10 minutes; we mint ≤9 min with a
#: 60s backdated iat for clock skew.
_APP_JWT_TTL_S = 540


class TokenUnavailable(Exception):
    """No token available for the requested purpose. Carries NO token value."""


@runtime_checkable
class TokenProvider(Protocol):
    """Return a bearer token for a purpose. Implementations must never log,
    persist, or embed the token in an exception."""

    def get_token(self, *, purpose: str) -> str: ...


class StaticTokenProvider:
    """Consumes a token the vault lane supplies for one or more purposes.

    Used for the fine-grained PAT fallback (``purpose=installation``) and for the
    owner user-access-token (``purpose=user_review``). Does NOT refresh — the
    vault lane owns the 8h user-token / PAT-expiry lifecycle; this just returns
    the current value. A missing/empty token raises :class:`TokenUnavailable`
    (fail closed — never an empty string that reads as a valid header)."""

    def __init__(self, token: str, *, purposes: Iterable[str]) -> None:
        self._token = token or ""
        self._purposes = frozenset(purposes)

    def get_token(self, *, purpose: str) -> str:
        if purpose not in self._purposes:
            raise TokenUnavailable(f"this provider does not serve purpose {purpose!r}")
        if not self._token:
            raise TokenUnavailable(f"no token configured for purpose {purpose!r}")
        return self._token

    def __repr__(self) -> str:  # never print the token
        return f"StaticTokenProvider(purposes={sorted(self._purposes)})"


class GitHubAppTokenProvider:
    """Mints App installation tokens from INJECTED App credentials.

    ``private_key_pem`` (the App's PKCS#1 RSA PEM) + ``app_id`` +
    ``installation_id`` are supplied by the caller (the vault lane at wiring
    time); this class never reads a vault. ``token_exchange`` performs the HTTP
    ``POST /app/installations/{id}/access_tokens`` (build it via
    ``tinyassets.github_http.installation_token_exchange`` in production; tests
    inject a fake). The minted installation token is cached IN MEMORY ONLY and
    re-minted before expiry; it is never persisted or logged.

    Only serves ``PURPOSE_INSTALLATION`` — the App cannot approve its own PR, so
    a review submission must use the owner user token (compose with
    :class:`CompositeTokenProvider`)."""

    def __init__(
        self,
        *,
        app_id: str,
        private_key_pem: str,
        installation_id: str,
        token_exchange: Callable[[str, str], tuple[str, float]],
        now: Callable[[], float] = time.time,
        jwt_ttl_s: int = _APP_JWT_TTL_S,
    ) -> None:
        self._app_id = str(app_id)
        self._pem = private_key_pem
        self._installation_id = str(installation_id)
        self._exchange = token_exchange
        self._now = now
        self._jwt_ttl_s = min(int(jwt_ttl_s), 600)
        self._cached_token: str | None = None
        self._cached_exp: float = 0.0

    def _mint_app_jwt(self) -> str:
        import jwt  # PyJWT, RS256 via cryptography

        now = int(self._now())
        payload = {
            "iat": now - 60,               # backdate for clock skew
            "exp": now + self._jwt_ttl_s,  # ≤10 min (GitHub hard cap)
            "iss": self._app_id,
        }
        token = jwt.encode(payload, self._pem, algorithm="RS256")
        return token if isinstance(token, str) else token.decode("utf-8")

    def get_token(self, *, purpose: str) -> str:
        if purpose != PURPOSE_INSTALLATION:
            raise TokenUnavailable(
                "the App token only serves installation writes/reads; owner "
                "review submission needs the owner user token"
            )
        # Re-mint 60s before expiry so an in-flight call never uses a stale token.
        if self._cached_token and (self._cached_exp - 60) > self._now():
            return self._cached_token
        app_jwt = self._mint_app_jwt()
        token, expires_at = self._exchange(app_jwt, self._installation_id)
        if not token:
            raise TokenUnavailable("installation token exchange returned no token")
        self._cached_token = token
        self._cached_exp = float(expires_at)
        return token

    def __repr__(self) -> str:  # never print the token / PEM
        return f"GitHubAppTokenProvider(app_id={self._app_id!r})"


class CompositeTokenProvider:
    """Route by purpose: installation writes/reads via ``installation``; owner
    review submission via ``user_review``. Missing route → fail closed."""

    def __init__(
        self, *, installation: TokenProvider, user_review: TokenProvider | None = None
    ) -> None:
        self._installation = installation
        self._user_review = user_review

    def get_token(self, *, purpose: str) -> str:
        if purpose == PURPOSE_USER_REVIEW:
            if self._user_review is None:
                raise TokenUnavailable(
                    "no owner user-token provider wired for review submission"
                )
            return self._user_review.get_token(purpose=purpose)
        if purpose == PURPOSE_INSTALLATION:
            return self._installation.get_token(purpose=purpose)
        raise TokenUnavailable(f"unknown token purpose {purpose!r}")

    def __repr__(self) -> str:
        return "CompositeTokenProvider(installation=…, user_review=%s)" % (
            "set" if self._user_review is not None else "none"
        )


def _assert_no_token_in(text: str, *tokens: str) -> None:
    """Test/debug helper: raise if any secret leaked into ``text``."""
    for t in tokens:
        if t and t in (text or ""):
            raise AssertionError("token value leaked into output")


__all__: list[str] = [
    "PURPOSE_INSTALLATION",
    "PURPOSE_USER_REVIEW",
    "VALID_PURPOSES",
    "TokenUnavailable",
    "TokenProvider",
    "StaticTokenProvider",
    "GitHubAppTokenProvider",
    "CompositeTokenProvider",
]


# Silence "unused" for the intentionally-exported debug helper.
_ = (Any, _assert_no_token_in)
