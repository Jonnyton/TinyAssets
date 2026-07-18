"""Live HTTP implementation of the GitHub-native surface — S4 / E4.

Implements :class:`tinyassets.github_native.GitHubApi` (the read side used by
setup verification + projection reconciliation) AND an executor that runs a
:class:`tinyassets.github_native.GitHubCall` (the write side: PR review submit,
merge with an expected head SHA, GraphQL ``enablePullRequestAutoMerge``).

Design rules:

- **Token selection per call.** Owner review submission
  (``submit_review_*``) uses the owner USER access token so GitHub attributes
  the review to the owner; everything else (merge / auto-merge / reads) uses the
  App INSTALLATION token. Tokens come from a
  :class:`tinyassets.github_auth.TokenProvider`; this module never stores or
  refreshes them.
- **Retry on 5xx only** (transient server errors) with bounded exponential
  backoff. A 4xx or a network/timeout error is surfaced immediately as a
  structured :class:`GitHubHttpError` — never a silent retry storm.
- **Tokens never leak.** No token appears in an exception, log line, or returned
  payload; :func:`_redact` scrubs any bearer/token-shaped substring from error
  detail defensively.
- **Injectable transport.** ``request_fn`` lets tests drive the client with
  recorded response-shape fixtures — no live network in the suite. A real live
  smoke lives in ``scripts/github_live_smoke.py`` (env-gated).

See ``docs/design-notes/2026-07-16-s4-github-native-redirect.md`` and
``docs/ops/github-app-setup.md``.
"""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

from tinyassets.github_auth import (
    PURPOSE_INSTALLATION,
    PURPOSE_RULESET_VERIFY,
    PURPOSE_USER_REVIEW,
    TokenProvider,
)
from tinyassets.github_native import GitHubCall

_API_BASE = "https://api.github.com"
_GRAPHQL_URL = "https://api.github.com/graphql"
_DEFAULT_TIMEOUT_S = 30.0
_MAX_RETRIES = 3  # total attempts on 5xx = _MAX_RETRIES
_ACCEPT = "application/vnd.github+json"
_API_VERSION = "2022-11-28"

#: Candidate CODEOWNERS paths, in GitHub's own precedence order.
_CODEOWNERS_PATHS = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")

#: Token-shaped substrings scrubbed from any error detail (defensive; our token
#: should never reach a response body, but never leak if GitHub echoes a header).
_TOKEN_RE = re.compile(
    r"(gh[posru]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|Bearer\s+[A-Za-z0-9._\-]+)"
)


def _redact(text: str) -> str:
    return _TOKEN_RE.sub("[REDACTED]", text or "")


class GitHubHttpError(Exception):
    """Structured GitHub HTTP failure. Carries a status + machine ``error_class``
    and a REDACTED detail; never a token."""

    def __init__(
        self, message: str, *, status: int | None = None,
        error_class: str = "github_http_error", detail: str = "",
    ) -> None:
        super().__init__(message)
        self.status = status
        self.error_class = error_class
        self.detail = _redact(detail)[:500]

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": _redact(str(self)),
            "error_class": self.error_class,
            "http_status": self.status,
            "detail": self.detail,
        }


def _default_request(
    *,
    method: str,
    url: str,
    token: str,
    body: dict[str, Any] | None,
    timeout: float,
    accept: str,
) -> tuple[int, Any]:
    """Perform one HTTP request. Returns ``(status, parsed_json_or_text)``.

    Raises :class:`GitHubHttpError` with ``error_class='network'`` on a
    connection/timeout failure (NOT retried). HTTP responses (including 4xx/5xx)
    return normally with their status so the caller decides retry policy.
    """
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Accept": accept,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "tinyassets-github-native/1.0",
            "X-GitHub-Api-Version": _API_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(detail) if detail.strip() else {}
        except (TypeError, ValueError):
            parsed = {"raw": detail}
        return exc.code, parsed
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise GitHubHttpError(
            f"GitHub request failed: {exc}", status=None, error_class="network",
            detail=str(exc),
        ) from exc


class HttpGitHubApi:
    """Live GitHub client implementing the read API + the call executor.

    ``token_provider`` supplies installation / user tokens. ``request_fn`` is the
    low-level transport (default :func:`_default_request`); tests inject a fake
    that replays recorded response shapes. ``sleep_fn`` gates retry backoff
    (default :func:`time.sleep`; tests pass a no-op).
    """

    def __init__(
        self,
        token_provider: TokenProvider,
        *,
        api_base: str = _API_BASE,
        graphql_url: str = _GRAPHQL_URL,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        max_retries: int = _MAX_RETRIES,
        request_fn: Callable[..., tuple[int, Any]] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        read_purpose: str = PURPOSE_INSTALLATION,
    ) -> None:
        self._tp = token_provider
        self._api = api_base.rstrip("/")
        self._graphql = graphql_url
        self._timeout = timeout_s
        self._max_retries = max(1, int(max_retries))
        self._request = request_fn or _default_request
        self._sleep = sleep_fn or time.sleep
        # Reads use PURPOSE_INSTALLATION by default. A dedicated VERIFIER client
        # (Codex r13 #3) sets read_purpose=PURPOSE_RULESET_VERIFY so the
        # ruleset/bypass reads use the owner's elevated ruleset-read token —
        # only autonomous merge needs this; manual never constructs a verifier.
        self._read_purpose = read_purpose

    # ── low-level with retry-on-5xx-only ─────────────────────────────────────

    def _call_http(
        self, *, method: str, url: str, purpose: str,
        body: dict[str, Any] | None = None, accept: str = _ACCEPT,
    ) -> tuple[int, Any]:
        token = self._tp.get_token(purpose=purpose)
        last_status = 0
        last_parsed: Any = None
        for attempt in range(self._max_retries):
            status, parsed = self._request(
                method=method, url=url, token=token, body=body,
                timeout=self._timeout, accept=accept,
            )
            if not (500 <= status <= 599):
                return status, parsed
            last_status, last_parsed = status, parsed
            if attempt < self._max_retries - 1:
                self._sleep(min(0.5 * (2 ** attempt), 4.0))
        # Exhausted retries on 5xx.
        raise GitHubHttpError(
            f"GitHub {method} {url} failed after {self._max_retries} attempts "
            f"(status {last_status})",
            status=last_status, error_class="server_error",
            detail=json.dumps(last_parsed)[:500] if last_parsed is not None else "",
        )

    def _get(self, path: str, *, purpose: str | None = None) -> tuple[int, Any]:
        return self._call_http(
            method="GET", url=f"{self._api}{path}",
            purpose=purpose or self._read_purpose,
        )

    # ── read API (implements tinyassets.github_native.GitHubApi) ─────────────

    def list_active_rulesets(
        self, *, destination: str, branch: str
    ) -> list[dict[str, Any]]:
        """Assemble the ruleset shape ``verify_review_gate_active`` expects.

        GitHub exposes the effective RULES for a branch flat
        (``GET /repos/{o}/{r}/rules/branches/{branch}``), each tagged with its
        ``ruleset_id``; the ``enforcement`` + ``bypass_actors`` live on the
        ruleset (``GET /repos/{o}/{r}/rulesets/{id}``). We group the rules by
        ruleset and fetch each ruleset once.
        """
        status, rules = self._get(
            f"/repos/{destination}/rules/branches/{branch}"
        )
        if status == 404:
            return []
        if status >= 400 or not isinstance(rules, list):
            raise GitHubHttpError(
                f"could not read branch rules for {destination}@{branch}",
                status=status, error_class="rules_read_failed",
                detail=json.dumps(rules)[:500],
            )
        by_ruleset: dict[Any, dict[str, Any]] = {}
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            rid = rule.get("ruleset_id")
            slot = by_ruleset.setdefault(rid, {"id": rid, "rules": []})
            slot["rules"].append(
                {"type": rule.get("type"), "parameters": rule.get("parameters") or {}}
            )
        assembled: list[dict[str, Any]] = []
        for rid, slot in by_ruleset.items():
            enforcement = "active"
            # Codex r12 #2: NEVER default bypass_actors to []. GitHub omits the
            # field unless the caller has ruleset-WRITE, so "not visible" must
            # not read as "confirmed empty". We only set slot['bypass_actors']
            # when the ruleset-detail response ACTUALLY carries it (and is a
            # list); otherwise the key is absent and verify_review_gate_active
            # fails closed on "bypass_actors_visible". A 403/failed/malformed
            # detail response also leaves the key absent.
            if rid is not None:
                try:
                    rs_status, ruleset = self._get(
                        f"/repos/{destination}/rulesets/{rid}"
                    )
                except GitHubHttpError:
                    # A failed detail GET (e.g. 5xx exhausted) ⇒ bypass config is
                    # NOT verifiable ⇒ leave the key absent (fail closed).
                    rs_status, ruleset = 599, {}
                if rs_status < 400 and isinstance(ruleset, dict):
                    enforcement = ruleset.get("enforcement", "active")
                    raw = ruleset.get("bypass_actors")
                    if isinstance(raw, list):
                        slot["bypass_actors"] = raw
            slot["enforcement"] = enforcement
            assembled.append(slot)
        return assembled

    def get_codeowners(self, *, destination: str, ref: str = "") -> str | None:
        """The repo's CODEOWNERS text at the PR's base ``ref`` (Codex r14 #6;
        first path that exists), or None. The base branch's CODEOWNERS governs."""
        query = f"?ref={ref}" if ref else ""
        for path in _CODEOWNERS_PATHS:
            status, payload = self._get(f"/repos/{destination}/contents/{path}{query}")
            if status == 404:
                continue
            if status >= 400 or not isinstance(payload, dict):
                continue
            content = payload.get("content")
            encoding = payload.get("encoding")
            if isinstance(content, str) and encoding == "base64":
                try:
                    return base64.b64decode(content).decode("utf-8", errors="replace")
                except (ValueError, TypeError):
                    continue
            if isinstance(content, str):
                return content
        return None

    def get_pull(self, *, destination: str, pr_number: int) -> dict[str, Any]:
        """Current GitHub PR state (REST). ``review_decision`` is GraphQL-only on
        GitHub, so it is left ``unknown`` here (the projection treats it as a
        hint, not authority)."""
        status, pr = self._get(f"/repos/{destination}/pulls/{pr_number}")
        if status >= 400 or not isinstance(pr, dict):
            raise GitHubHttpError(
                f"could not read {destination}#{pr_number}",
                status=status, error_class="pull_read_failed",
                detail=json.dumps(pr)[:500],
            )
        head = pr.get("head") or {}
        base = pr.get("base") or {}
        author = pr.get("user") or {}
        return {
            "state": "merged" if pr.get("merged") else (pr.get("state") or "unknown"),
            "merged": bool(pr.get("merged")),
            "mergeable_state": pr.get("mergeable_state") or "unknown",
            "review_decision": "unknown",
            "head_sha": head.get("sha") or "",
            "base_ref": base.get("ref") or "",
            "merge_commit_sha": pr.get("merge_commit_sha") or "",
            "node_id": pr.get("node_id") or "",
            "auto_merge_enabled": bool(pr.get("auto_merge")),
            # PR author identity (Codex r17 #4): App-installation-authored PRs have
            # ``user.type == "Bot"``; the owner-review gate rejects a PR authored by
            # the connected owner (self-approval is impossible).
            "author_login": (author.get("login") or ""),
            "author_type": (author.get("type") or ""),
        }

    def list_pull_reviews(
        self, *, destination: str, pr_number: int
    ) -> list[dict[str, Any]]:
        """ALL reviews for a PR, paginated (GitHub caps ``per_page`` at 100), each
        normalized to ``{"id", "commit_id", "state", "user_login"}`` with the
        reviewer login lower-cased. Follows pages until GitHub returns a short
        (or empty) page. A non-2xx / non-list page raises :class:`GitHubHttpError`
        (never a silent partial list that could hide an attacker's review).

        Ref: https://docs.github.com/en/rest/pulls/reviews"""
        per_page = 100
        reviews: list[dict[str, Any]] = []
        for page in range(1, 51):  # hard page cap (5000 reviews) — never unbounded
            status, payload = self._get(
                f"/repos/{destination}/pulls/{pr_number}/reviews"
                f"?per_page={per_page}&page={page}"
            )
            if status == 404 and page == 1:
                return []
            if status >= 400 or not isinstance(payload, list):
                raise GitHubHttpError(
                    f"could not list reviews for {destination}#{pr_number}",
                    status=status, error_class="reviews_read_failed",
                    detail=json.dumps(payload)[:500],
                )
            for rv in payload:
                if not isinstance(rv, dict):
                    continue
                user = rv.get("user")
                login = ""
                if isinstance(user, dict):
                    login = str(user.get("login") or "")
                reviews.append({
                    "id": rv.get("id"),
                    "commit_id": str(rv.get("commit_id") or ""),
                    "state": str(rv.get("state") or "").upper(),
                    "user_login": login.strip().lstrip("@").lower(),
                })
            if len(payload) < per_page:
                break
        return reviews

    # ── write side: execute a GitHubCall ─────────────────────────────────────

    def run_call(self, call: GitHubCall) -> dict[str, Any]:
        """Execute a :class:`GitHubCall`. Selects the owner USER token for review
        submission AND review dismissal (the owner is the authorized dismisser —
        the App's minimal installation scope cannot dismiss on a protected
        branch, Codex r15 #4), and the App INSTALLATION token for everything else
        (merge / auto-merge / reads). Returns ``{"ok": True, "kind", "status",
        "result"}`` or raises :class:`GitHubHttpError`."""
        user_token_kinds = {
            "submit_review_approve", "submit_review_request_changes",
            "dismiss_review",
        }
        purpose = PURPOSE_USER_REVIEW if call.kind in user_token_kinds else PURPOSE_INSTALLATION

        if call.transport == "graphql":
            return self._run_graphql(call)

        # REST: body is the call params (event/commit_id/body/sha/merge_method…).
        status, result = self._call_http(
            method=call.method, url=f"{self._api}{call.path}", purpose=purpose,
            body=dict(call.params),
        )
        if status >= 400:
            raise GitHubHttpError(
                f"{call.kind} failed ({status})", status=status,
                error_class=f"{call.kind}_failed", detail=json.dumps(result)[:500],
            )
        return {"ok": True, "kind": call.kind, "status": status, "result": result}

    def _run_graphql(self, call: GitHubCall) -> dict[str, Any]:
        """auto-merge mutations need the PR's GraphQL node id. Prefer the node id
        the recorded call already resolved (Codex r11 #4); fall back to a REST
        lookup only if it's absent. When an ``expected_head_oid`` is present the
        mutation is head-bound via ``expectedHeadOid``."""
        destination = call.params.get("destination", "")
        pr_number = call.params.get("pr_number")
        node_id = (call.params.get("pull_request_id") or "").strip()
        expected_head_oid = (call.params.get("expected_head_oid") or "").strip()
        if not node_id:
            pull = self.get_pull(destination=destination, pr_number=pr_number)
            node_id = pull.get("node_id")
        if not node_id:
            raise GitHubHttpError(
                f"could not resolve GraphQL node id for {destination}#{pr_number}",
                error_class="node_id_unresolved",
            )
        mutation = call.params.get("mutation")
        if mutation == "enablePullRequestAutoMerge":
            merge_method = str(call.params.get("merge_method") or "SQUASH").upper()
            if expected_head_oid:
                query = (
                    "mutation($pr:ID!,$m:PullRequestMergeMethod!,$oid:GitObjectID!){"
                    "enablePullRequestAutoMerge(input:{pullRequestId:$pr,"
                    "mergeMethod:$m,expectedHeadOid:$oid}){clientMutationId}}"
                )
                variables = {"pr": node_id, "m": merge_method, "oid": expected_head_oid}
            else:
                query = (
                    "mutation($pr:ID!,$m:PullRequestMergeMethod!){"
                    "enablePullRequestAutoMerge(input:{pullRequestId:$pr,mergeMethod:$m})"
                    "{clientMutationId}}"
                )
                variables = {"pr": node_id, "m": merge_method}
        elif mutation == "disablePullRequestAutoMerge":
            query = (
                "mutation($pr:ID!){"
                "disablePullRequestAutoMerge(input:{pullRequestId:$pr})"
                "{clientMutationId}}"
            )
            variables = {"pr": node_id}
        else:
            raise GitHubHttpError(
                f"unsupported GraphQL mutation {mutation!r}",
                error_class="unsupported_mutation",
            )
        status, result = self._call_http(
            method="POST", url=self._graphql, purpose=PURPOSE_INSTALLATION,
            body={"query": query, "variables": variables},
        )
        if status >= 400 or (isinstance(result, dict) and result.get("errors")):
            raise GitHubHttpError(
                f"{call.kind} GraphQL failed ({status})", status=status,
                error_class=f"{call.kind}_failed", detail=json.dumps(result)[:500],
            )
        return {"ok": True, "kind": call.kind, "status": status, "result": result}


def installation_token_exchange(
    *, api_base: str = _API_BASE, timeout_s: float = _DEFAULT_TIMEOUT_S,
    request_fn: Callable[..., tuple[int, Any]] | None = None,
) -> Callable[[str, str], tuple[str, float]]:
    """Build the App-JWT → installation-token exchange used by
    :class:`tinyassets.github_auth.GitHubAppTokenProvider`. Returns a callable
    ``(app_jwt, installation_id) -> (token, expires_at_epoch)``. Kept here (not
    in github_auth) so the auth module stays transport-free."""
    req = request_fn or _default_request

    def _exchange(app_jwt: str, installation_id: str) -> tuple[str, float]:
        status, payload = req(
            method="POST",
            url=f"{api_base.rstrip('/')}/app/installations/{installation_id}/access_tokens",
            token=app_jwt, body={}, timeout=timeout_s, accept=_ACCEPT,
        )
        if status >= 400 or not isinstance(payload, dict) or not payload.get("token"):
            raise GitHubHttpError(
                f"installation token exchange failed ({status})", status=status,
                error_class="installation_token_exchange_failed",
                detail=json.dumps(payload)[:300] if isinstance(payload, dict) else "",
            )
        expires_at = payload.get("expires_at")
        # GitHub returns an ISO8601 expiry; fall back to now+1h if unparseable.
        exp_epoch = time.time() + 3600.0
        if isinstance(expires_at, str):
            try:
                from datetime import datetime

                exp_epoch = datetime.fromisoformat(
                    expires_at.replace("Z", "+00:00")
                ).timestamp()
            except (ValueError, TypeError):
                pass
        return payload["token"], exp_epoch

    return _exchange


class VaultBackedTokenProvider:
    """Resolve and refresh destination-scoped GitHub credentials on demand.

    App installation tokens are minted from the vaulted private key and cached
    only in this process until shortly before expiry. User tokens are reread
    from the vault and atomically rotated through the refresh seam when stale.
    A PAT fallback is leased afresh for every call; no production factory
    snapshots a long-lived secret into :class:`StaticTokenProvider`.
    """

    _INSTALLATION_PERMISSIONS = {
        "contents": "write",
        "pull_requests": "write",
        "metadata": "read",
    }

    def __init__(
        self,
        universe_dir: Any,
        destination: str,
        *,
        base: str | Path | None = None,
        http_post_json: Callable[..., tuple[int, dict[str, Any]]] | None = None,
        http_post_form: Callable[..., tuple[int, dict[str, Any]]] | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._universe_id = Path(universe_dir).name
        self._destination = (destination or "").strip()
        self._base = base
        self._http_post_json = http_post_json
        self._http_post_form = http_post_form
        self._now = now
        self._installation_token: str | None = None
        self._installation_expires_at = 0.0

    def _binding(self, purpose: str) -> Any:
        from tinyassets.credential_broker import find_binding

        return find_binding(
            self._universe_id,
            "github",
            purpose,
            self._destination,
            base=self._base,
        )

    def _binding_or_none(self, purpose: str) -> Any:
        from tinyassets.credentials import CredentialUnavailable, VaultErrorCode

        try:
            return self._binding(purpose)
        except CredentialUnavailable as exc:
            if exc.code == VaultErrorCode.NOT_FOUND:
                return None
            raise

    def supports(self, purpose: str) -> bool:
        if purpose == PURPOSE_INSTALLATION:
            return (
                self._binding_or_none("app_auth") is not None
                or self._binding_or_none("external_write") is not None
            )
        if purpose == PURPOSE_USER_REVIEW:
            return self._binding_or_none("user_review") is not None
        if purpose == PURPOSE_RULESET_VERIFY:
            return self._binding_or_none("ruleset_verify") is not None
        return False

    def _lease_text(self, binding: Any) -> str:
        from tinyassets.credential_broker import platform_backend

        backend = platform_backend(self._base)
        with backend.get(binding, binding.scope) as lease:
            try:
                value = lease.reveal().decode("utf-8")
            except UnicodeDecodeError:
                from tinyassets.credentials import CredentialUnavailable, VaultErrorCode

                raise CredentialUnavailable(VaultErrorCode.CORRUPT_RECORD) from None
        if not value:
            from tinyassets.github_auth import TokenUnavailable

            raise TokenUnavailable("vaulted GitHub credential is empty")
        return value

    def _installation(self) -> str:
        if (
            self._installation_token
            and self._installation_expires_at - 60 > self._now()
        ):
            return self._installation_token

        app_binding = self._binding_or_none("app_auth")
        if app_binding is None:
            pat_binding = self._binding_or_none("external_write")
            if pat_binding is None:
                from tinyassets.github_auth import TokenUnavailable

                raise TokenUnavailable("no GitHub installation credential configured")
            return self._lease_text(pat_binding)

        from tinyassets.credential_broker import (
            github_connection_metadata,
            platform_backend,
        )
        from tinyassets.github_auth import TokenUnavailable
        from tinyassets.github_token_refresh import mint_installation_token

        metadata = github_connection_metadata(
            self._universe_id, self._destination, base=self._base
        )
        app_id = metadata.get("app_id", "")
        installation_id = metadata.get("installation_id", "")
        if not app_id or not installation_id:
            raise TokenUnavailable("GitHub App connection metadata is incomplete")
        repository = self._destination.rsplit("/", 1)[-1]
        minted = mint_installation_token(
            platform_backend(self._base),
            app_binding,
            app_binding.scope,
            app_id=app_id,
            installation_id=installation_id,
            repositories=[repository],
            permissions=self._INSTALLATION_PERMISSIONS,
            http_post_json=self._http_post_json,
        )
        try:
            token = minted.token.reveal().decode("utf-8")
        finally:
            minted.token.zero()
        self._installation_token = token
        self._installation_expires_at = minted.expires_at
        return token

    def _user_token(self, purpose: str) -> str:
        from tinyassets.credential_broker import (
            github_connection_metadata,
            platform_backend,
        )
        from tinyassets.credentials import SecretKind
        from tinyassets.github_auth import TokenUnavailable
        from tinyassets.github_token_refresh import (
            decode_user_token_bundle,
            refresh_user_token,
        )

        binding = self._binding(
            "user_review" if purpose == PURPOSE_USER_REVIEW else "ruleset_verify"
        )
        if binding.kind == SecretKind.GITHUB_PAT:
            return self._lease_text(binding)
        if binding.kind != SecretKind.GITHUB_APP_USER_TOKEN:
            raise TokenUnavailable("unsupported GitHub user credential kind")

        backend = platform_backend(self._base)
        with backend.get(binding, binding.scope) as lease:
            bundle = decode_user_token_bundle(lease.reveal())
        expires_at = bundle.get("expires_at")
        if isinstance(expires_at, (int, float)) and expires_at > self._now() + 60:
            return str(bundle["access_token"])

        metadata = github_connection_metadata(
            self._universe_id, self._destination, base=self._base
        )
        client_id = metadata.get("client_id", "")
        if not client_id:
            raise TokenUnavailable("GitHub user-token client metadata is incomplete")
        refresh_user_token(
            backend,
            binding,
            binding.scope,
            client_id=client_id,
            holder=f"s4:{uuid.uuid4().hex}",
            http_post_form=self._http_post_form,
            now=self._now(),
        )
        with backend.get(binding, binding.scope) as lease:
            refreshed = decode_user_token_bundle(lease.reveal())
        return str(refreshed["access_token"])

    def get_token(self, *, purpose: str) -> str:
        if purpose == PURPOSE_INSTALLATION:
            return self._installation()
        if purpose in {PURPOSE_USER_REVIEW, PURPOSE_RULESET_VERIFY}:
            return self._user_token(purpose)
        from tinyassets.github_auth import TokenUnavailable

        raise TokenUnavailable(f"unknown token purpose {purpose!r}")

    def __repr__(self) -> str:
        return "VaultBackedTokenProvider(destination=<redacted>)"


def github_client_from_vault(
    universe_dir: Any, destination: str, **kwargs: Any
) -> HttpGitHubApi | None:
    """Build the LIVE review/merge client for ``destination`` from the
    per-universe credential vault — the production wiring the daemon recovery
    workers use. Resolves the App INSTALLATION token (merge / auto-merge / reads
    / disable-auto-merge) and, when present, the owner USER token (review submit
    + dismissal) BY DESTINATION from the vault. Returns ``None`` (fail closed —
    the workers leave their queues intact) when no installation token is
    connected for the destination, so a universe with no GitHub connection never
    silently no-ops as if merged.

    This is the ONE place a live ``HttpGitHubApi`` is constructed for the S4
    recovery loop; the fake is a test-only drop-in for the same
    :class:`tinyassets.github_native.GitHubApi` shape."""
    dest = (destination or "").strip()
    if not dest:
        return None
    provider = VaultBackedTokenProvider(universe_dir, dest)
    if not provider.supports(PURPOSE_INSTALLATION):
        return None
    return HttpGitHubApi(provider, **kwargs)


def verifier_client_from_vault(
    universe_dir: Any, destination: str, **kwargs: Any
) -> HttpGitHubApi | None:
    """Build the per-destination VERIFIER client for the AUTONOMOUS-merge gate
    (Codex r17 #3) from the per-universe vault. Autonomous (``auto``/``not_before``)
    merge needs the owner's elevated ruleset-read token to positively see
    ``bypass_actors`` — a separate opt-in grant the App's minimal merge scope
    lacks. Returns ``None`` (fail closed — the timer stays due) when the
    ``ruleset_verify`` credential is not connected for the destination, so a
    universe that never opted into autonomous merge never enables it silently."""
    dest = (destination or "").strip()
    if not dest:
        return None
    provider = VaultBackedTokenProvider(universe_dir, dest)
    if not provider.supports(PURPOSE_RULESET_VERIFY):
        return None
    return HttpGitHubApi(
        provider, read_purpose=PURPOSE_RULESET_VERIFY, **kwargs
    )


__all__ = [
    "GitHubHttpError",
    "HttpGitHubApi",
    "VaultBackedTokenProvider",
    "installation_token_exchange",
    "github_client_from_vault",
    "verifier_client_from_vault",
]
