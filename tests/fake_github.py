"""In-memory GitHub API fake for the S4 GitHub-native tests.

Implements :class:`tinyassets.github_native.GitHubApi` with no network. Tests
construct one with the ruleset / CODEOWNERS / PR state they want to assert the
setup-verification + projection-reconciliation logic against. (Not collected by
pytest — no ``test_`` prefix.)
"""

from __future__ import annotations

from typing import Any


def code_owner_review_ruleset(
    *,
    enforcement: str = "active",
    dismiss_stale: bool = True,
    require_last_push: bool = True,
    bypass_actors: list[dict[str, Any]] | None = None,
    ruleset_id: int = 1,
) -> dict[str, Any]:
    """A ruleset that requires PR + code-owner review — the gate the autonomous
    preferences need. Tweak the args to build the not-configured variants."""
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
            }
        ],
    }


class InMemoryGitHubApi:
    """Configurable fake GitHub read client."""

    def __init__(
        self,
        *,
        rulesets: list[dict[str, Any]] | None = None,
        codeowners: str | None = "* @owner\n",
        pulls: dict[int, dict[str, Any]] | None = None,
        raise_on_rulesets: bool = False,
    ) -> None:
        self._rulesets = rulesets if rulesets is not None else [code_owner_review_ruleset()]
        self._codeowners = codeowners
        self._pulls = pulls or {}
        self._raise_on_rulesets = raise_on_rulesets
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def list_active_rulesets(self, *, destination: str, branch: str) -> list[dict[str, Any]]:
        self.calls.append(("list_active_rulesets", {"destination": destination, "branch": branch}))
        if self._raise_on_rulesets:
            raise RuntimeError("403 Forbidden (fake)")
        return list(self._rulesets)

    def get_codeowners(self, *, destination: str) -> str | None:
        self.calls.append(("get_codeowners", {"destination": destination}))
        return self._codeowners

    def get_pull(self, *, destination: str, pr_number: int) -> dict[str, Any]:
        self.calls.append(("get_pull", {"destination": destination, "pr_number": pr_number}))
        return dict(self._pulls.get(pr_number, {"state": "open", "merged": False}))
