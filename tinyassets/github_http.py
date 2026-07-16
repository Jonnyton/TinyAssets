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
from typing import Any, Callable

from tinyassets.github_auth import (
    PURPOSE_INSTALLATION,
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
    ) -> None:
        self._tp = token_provider
        self._api = api_base.rstrip("/")
        self._graphql = graphql_url
        self._timeout = timeout_s
        self._max_retries = max(1, int(max_retries))
        self._request = request_fn or _default_request
        self._sleep = sleep_fn or time.sleep

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

    def _get(self, path: str, *, purpose: str = PURPOSE_INSTALLATION) -> tuple[int, Any]:
        return self._call_http(method="GET", url=f"{self._api}{path}", purpose=purpose)

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
            bypass_actors: list[dict[str, Any]] = []
            if rid is not None:
                rs_status, ruleset = self._get(f"/repos/{destination}/rulesets/{rid}")
                if rs_status < 400 and isinstance(ruleset, dict):
                    enforcement = ruleset.get("enforcement", "active")
                    bypass_actors = ruleset.get("bypass_actors") or []
            slot["enforcement"] = enforcement
            slot["bypass_actors"] = bypass_actors
            assembled.append(slot)
        return assembled

    def get_codeowners(self, *, destination: str) -> str | None:
        """The repo's CODEOWNERS text (first path that exists), or None."""
        for path in _CODEOWNERS_PATHS:
            status, payload = self._get(f"/repos/{destination}/contents/{path}")
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
        return {
            "state": "merged" if pr.get("merged") else (pr.get("state") or "unknown"),
            "merged": bool(pr.get("merged")),
            "mergeable_state": pr.get("mergeable_state") or "unknown",
            "review_decision": "unknown",
            "head_sha": head.get("sha") or "",
            "merge_commit_sha": pr.get("merge_commit_sha") or "",
            "node_id": pr.get("node_id") or "",
        }

    # ── write side: execute a GitHubCall ─────────────────────────────────────

    def run_call(self, call: GitHubCall) -> dict[str, Any]:
        """Execute a :class:`GitHubCall`. Selects the owner USER token for review
        submission and the App INSTALLATION token for everything else. Returns
        ``{"ok": True, "kind", "status", "result"}`` or raises
        :class:`GitHubHttpError`."""
        review_kinds = {"submit_review_approve", "submit_review_request_changes"}
        purpose = PURPOSE_USER_REVIEW if call.kind in review_kinds else PURPOSE_INSTALLATION

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
        """auto-merge mutations need the PR's GraphQL node id — resolve it via
        REST, then run the mutation."""
        destination = call.params.get("destination", "")
        pr_number = call.params.get("pr_number")
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


__all__ = [
    "GitHubHttpError",
    "HttpGitHubApi",
    "installation_token_exchange",
]
