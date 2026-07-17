"""In-memory GitHub API fake for the S4 GitHub-native tests.

Implements :class:`tinyassets.github_native.GitHubApi` with no network. Tests
construct one with the ruleset / CODEOWNERS / PR state they want to assert the
setup-verification + projection-reconciliation logic against. (Not collected by
pytest — no ``test_`` prefix.)
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


class InMemoryGitHubApi:
    """Configurable fake GitHub read client."""

    def __init__(
        self,
        *,
        rulesets: list[dict[str, Any]] | None = None,
        codeowners: str | None = "* @owner\n.github/CODEOWNERS @owner\n",
        pulls: dict[int, dict[str, Any]] | None = None,
        raise_on_rulesets: bool = False,
        default_base_ref: str = "main",
    ) -> None:
        self._rulesets = rulesets if rulesets is not None else [fully_gated_ruleset()]
        self._codeowners = codeowners
        self._pulls = pulls or {}
        self._raise_on_rulesets = raise_on_rulesets
        self._default_base_ref = default_base_ref
        self.calls: list[tuple[str, dict[str, Any]]] = []

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
        }
        default.update(self._pulls.get(pr_number, {}))
        return default
