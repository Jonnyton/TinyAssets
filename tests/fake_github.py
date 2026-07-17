"""In-memory GitHub API fake for the S4 GitHub-native tests.

Implements the FULL :class:`tinyassets.github_native.GitHubApi` read surface AND
the :class:`GitHubCall` executor (``run_call``) with no network. Tests construct
one with the ruleset / CODEOWNERS / PR / review state they want, and the fake
models GitHub's own state transitions (a merge marks the PR merged at its head; a
review submit appends an attributed review; a dismissal flips a review to
``DISMISSED``). This is a STATEFUL counterpart to the live ``HttpGitHubApi`` — the
shared contract test (``tests/test_github_api_contract.py``) runs the SAME
behavioural assertions against BOTH, so a production code path can never depend on
behaviour only the fake provides. (Not collected by pytest — no ``test_`` prefix.)
"""

from __future__ import annotations

from typing import Any


def fully_gated_ruleset(
    *,
    enforcement: str = "active",
    dismiss_stale: bool = True,
    require_last_push: bool = True,
    required_status_checks: list[dict[str, Any]] | None = None,
    bypass_actors: list[dict[str, Any]] | None = None,
    ruleset_id: int = 1,
) -> dict[str, Any]:
    """A ruleset satisfying EVERY hard precondition of the hardened gate: a
    pull_request rule (>=1 approval + code-owner review + stale-dismissal +
    latest-push approval) AND a required_status_checks rule with a check. Tweak
    the args to break one condition at a time. ``bypass_actors`` is present
    (empty) by default; delete the key on the returned dict to test the
    fail-closed-on-missing-bypass case."""
    checks = required_status_checks
    if checks is None:
        checks = [{"context": "ci/tests", "integration_id": None}]
    return {
        "id": ruleset_id,
        "enforcement": enforcement,
        "bypass_actors": bypass_actors or [],
        "rules": [
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 1,
                    "require_code_owner_review": True,
                    "dismiss_stale_reviews_on_push": dismiss_stale,
                    "require_last_push_approval": require_last_push,
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {"required_status_checks": checks},
            },
        ],
    }


# Back-compat alias for older test call sites.
code_owner_review_ruleset = fully_gated_ruleset


def _normalize_review(rv: dict[str, Any]) -> dict[str, Any]:
    """Normalize a review row to the shape the read API contract promises:
    ``{"id", "commit_id", "state", "user_login"}`` (login lower-cased)."""
    user = rv.get("user")
    login = rv.get("user_login")
    if not login and isinstance(user, dict):
        login = user.get("login")
    return {
        "id": rv.get("id"),
        "commit_id": str(rv.get("commit_id") or ""),
        "state": str(rv.get("state") or "").upper(),
        "user_login": str(login or "").strip().lstrip("@").lower(),
    }


class InMemoryGitHubApi:
    """Configurable STATEFUL fake GitHub read+write client.

    ``reviews`` maps ``pr_number -> [review, ...]`` (each ``{"id", "commit_id",
    "state", "user_login"}``). ``actor_login`` is the login GitHub attributes a
    submitted review to (the connected owner's user token in production). Every
    ``run_call`` is recorded on ``self.run_calls`` and mutates the in-memory PR /
    review state the way GitHub would."""

    def __init__(
        self,
        *,
        rulesets: list[dict[str, Any]] | None = None,
        codeowners: str | None = "* @owner\n.github/CODEOWNERS @owner\n",
        pulls: dict[int, dict[str, Any]] | None = None,
        reviews: dict[int, list[dict[str, Any]]] | None = None,
        actor_login: str = "owner",
        raise_on_rulesets: bool = False,
        default_base_ref: str = "main",
    ) -> None:
        self._rulesets = rulesets if rulesets is not None else [fully_gated_ruleset()]
        self._codeowners = codeowners
        self._pulls = pulls or {}
        self._reviews: dict[int, list[dict[str, Any]]] = {
            pr: [_normalize_review(r) for r in rows]
            for pr, rows in (reviews or {}).items()
        }
        self._actor_login = actor_login.strip().lstrip("@").lower()
        self._raise_on_rulesets = raise_on_rulesets
        self._default_base_ref = default_base_ref
        self._next_review_id = 1000
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.run_calls: list[Any] = []

    # ── read API ──────────────────────────────────────────────────────────────

    def list_active_rulesets(self, *, destination: str, branch: str) -> list[dict[str, Any]]:
        self.calls.append(("list_active_rulesets", {"destination": destination, "branch": branch}))
        if self._raise_on_rulesets:
            raise RuntimeError("403 Forbidden (fake)")
        return list(self._rulesets)

    def get_codeowners(self, *, destination: str, ref: str = "") -> str | None:
        self.calls.append(("get_codeowners", {"destination": destination, "ref": ref}))
        return self._codeowners

    def get_pull(self, *, destination: str, pr_number: int) -> dict[str, Any]:
        self.calls.append(("get_pull", {"destination": destination, "pr_number": pr_number}))
        default = {
            "state": "open", "merged": False, "mergeable_state": "clean",
            "review_decision": "unknown", "head_sha": "a" * 40,
            "base_ref": self._default_base_ref, "merge_commit_sha": "",
            "node_id": f"PR_node_{pr_number}",
            # App-installation-authored by default (Codex r17 #4); override to
            # simulate a founder-PAT-authored PR.
            "author_login": "workflow-app[bot]", "author_type": "Bot",
        }
        default.update(self._pulls.get(pr_number, {}))
        return default

    def list_pull_reviews(
        self, *, destination: str, pr_number: int
    ) -> list[dict[str, Any]]:
        self.calls.append(
            ("list_pull_reviews", {"destination": destination, "pr_number": pr_number})
        )
        return [dict(r) for r in self._reviews.get(pr_number, [])]

    # ── write side: execute a GitHubCall (models GitHub's own transitions) ─────

    def run_call(self, call: Any) -> dict[str, Any]:
        self.run_calls.append(call)
        params = dict(getattr(call, "params", {}) or {})
        kind = getattr(call, "kind", "")
        pr_number = self._pr_from_path(getattr(call, "path", "") or "", params)
        if kind == "merge_pr":
            self._apply_merge(pr_number, params)
        elif kind in ("submit_review_approve", "submit_review_request_changes"):
            self._apply_review(pr_number, kind, params)
        elif kind == "dismiss_review":
            self._apply_dismiss(pr_number, params)
        # enable/disable auto-merge (graphql) + anything else: recorded, no-op state.
        return {"ok": True, "kind": kind, "status": 200, "result": {}}

    # ── in-memory GitHub state transitions ─────────────────────────────────────

    def _pr_from_path(self, path: str, params: dict[str, Any]) -> int:
        import re

        m = re.search(r"/pulls/(\d+)", path)
        if m:
            return int(m.group(1))
        raw = params.get("pr_number")
        return int(raw) if isinstance(raw, int) else 0

    def _apply_merge(self, pr_number: int, params: dict[str, Any]) -> None:
        pull = dict(self._pulls.get(pr_number, {}))
        head = (pull.get("head_sha") or "a" * 40)
        # GitHub enforces the expected head SHA; a mismatch would 409 (never here,
        # because execute_manual_merge head-guards before calling run_call).
        pull["merged"] = True
        pull["state"] = "merged"
        pull["merge_commit_sha"] = "m" * 40
        pull["head_sha"] = head
        self._pulls[pr_number] = pull

    def _apply_review(self, pr_number: int, kind: str, params: dict[str, Any]) -> None:
        state = "APPROVED" if kind == "submit_review_approve" else "CHANGES_REQUESTED"
        rid = self._next_review_id
        self._next_review_id += 1
        self._reviews.setdefault(pr_number, []).append({
            "id": rid,
            "commit_id": str(params.get("commit_id") or ""),
            "state": state,
            "user_login": self._actor_login,
        })

    def _apply_dismiss(self, pr_number: int, params: dict[str, Any]) -> None:
        target = params.get("review_id")
        for rv in self._reviews.get(pr_number, []):
            if rv.get("id") == target:
                rv["state"] = "DISMISSED"
