"""GitHub-native primitives for the S4 owner review/merge surface (Phase-1 shape).

**Redirected 2026-07-16 (host decision):** GitHub is the source of truth for
review and merge state. This module holds:

1. :class:`GitHubCall` — a description of the EXACT GitHub API call a chat verb
   or the merge effector will make. Phase 1 RECORDS these (owner intent + the
   precise call to run); Phase 2 executes them against a live GitHub App. A
   ``GitHubCall`` is inert data — constructing one performs no network I/O.
2. Call builders (``review_approve``, ``review_request_changes``, ``merge_pr``,
   ``enable_auto_merge`` …) that map each chat action to its native call.
3. :class:`GitHubApi` — the injected read client used by setup verification and
   projection reconciliation. Phase 2 supplies a real GitHub App client; tests
   supply an in-memory fake (``tests/fake_github.py``). This module never
   constructs a network client itself.
4. :func:`verify_review_gate_active` — FAIL-CLOSED setup verification: before a
   repo is treated as review-gated (required for the autonomous ``auto`` /
   ``not_before`` preferences), the active ruleset must require PR + code-owner
   review, ``CODEOWNERS`` must be present, and the App must not be a ruleset
   bypass actor. Anything missing → not gated; the caller refuses autonomous
   merge and tells the owner exactly what to configure.

See ``docs/design-notes/2026-07-16-s4-github-native-redirect.md`` and the
prior-art basis ``docs/research/2026-07-16-github-native-review-merge-prior-art.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

#: Default merge method for the reference loop's merges. Squash keeps a clean
#: single-commit history on the owner's default branch.
DEFAULT_MERGE_METHOD = "squash"


@dataclass(frozen=True)
class GitHubCall:
    """The exact GitHub call a chat verb / effector will make.

    Phase 1 records this as owner intent; Phase 2 executes it. Constructing one
    is pure — no network. ``transport`` is ``rest`` or ``graphql``; ``method`` +
    ``path`` locate a REST endpoint (``path`` is ``graphql`` for GraphQL
    mutations, with the mutation named in ``params['mutation']``).
    """

    kind: str
    transport: str
    method: str
    path: str
    params: dict[str, Any] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "transport": self.transport,
            "method": self.method,
            "path": self.path,
            "params": dict(self.params),
            "summary": self.summary,
        }


def _repo_path(destination: str, suffix: str) -> str:
    return f"/repos/{destination}{suffix}"


def review_approve(*, destination: str, pr_number: int, head_sha: str) -> GitHubCall:
    """The owner's chat approval → a real GitHub PR review (event=APPROVE), bound
    to the exact reviewed head via ``commit_id`` so it can't apply to a re-pushed
    head. Authenticated (Phase 2) with the owner's GitHub App USER access token,
    so GitHub attributes the approval to the owner."""
    return GitHubCall(
        kind="submit_review_approve",
        transport="rest",
        method="POST",
        path=_repo_path(destination, f"/pulls/{pr_number}/reviews"),
        params={"event": "APPROVE", "commit_id": head_sha},
        summary=(
            f"POST a GitHub APPROVE review on {destination}#{pr_number} bound to "
            f"head {head_sha[:8] or '(none)'} (owner's user token)"
        ),
    )


def review_request_changes(
    *, destination: str, pr_number: int, head_sha: str, body: str
) -> GitHubCall:
    """Reshape / reject → a REQUEST_CHANGES review carrying the owner's notes."""
    return GitHubCall(
        kind="submit_review_request_changes",
        transport="rest",
        method="POST",
        path=_repo_path(destination, f"/pulls/{pr_number}/reviews"),
        params={"event": "REQUEST_CHANGES", "commit_id": head_sha, "body": body},
        summary=(
            f"POST a GitHub REQUEST_CHANGES review on {destination}#{pr_number} "
            f"with the owner's notes"
        ),
    )


def merge_pr(
    *, destination: str, pr_number: int, expected_head_sha: str,
    merge_method: str = DEFAULT_MERGE_METHOD,
) -> GitHubCall:
    """Manual merge → the merge API with the expected head SHA. GitHub atomically
    rechecks its own rules (required reviews/checks) and the head SHA."""
    return GitHubCall(
        kind="merge_pr",
        transport="rest",
        method="PUT",
        path=_repo_path(destination, f"/pulls/{pr_number}/merge"),
        params={"sha": expected_head_sha, "merge_method": merge_method},
        summary=(
            f"PUT merge {destination}#{pr_number} with expected head "
            f"{expected_head_sha[:8] or '(none)'} ({merge_method})"
        ),
    )


def enable_auto_merge(
    *, destination: str, pr_number: int, merge_method: str = "SQUASH"
) -> GitHubCall:
    """Auto / fired timer → GraphQL ``enablePullRequestAutoMerge``; GitHub merges
    once its own required reviews/checks are satisfied."""
    return GitHubCall(
        kind="enable_auto_merge",
        transport="graphql",
        method="POST",
        path="graphql",
        params={
            "mutation": "enablePullRequestAutoMerge",
            "destination": destination,
            "pr_number": pr_number,
            "merge_method": merge_method,
        },
        summary=(
            f"GraphQL enablePullRequestAutoMerge on {destination}#{pr_number} "
            f"({merge_method})"
        ),
    )


def disable_auto_merge(*, destination: str, pr_number: int) -> GitHubCall:
    """Preference tightening / hold → GraphQL ``disablePullRequestAutoMerge``."""
    return GitHubCall(
        kind="disable_auto_merge",
        transport="graphql",
        method="POST",
        path="graphql",
        params={
            "mutation": "disablePullRequestAutoMerge",
            "destination": destination,
            "pr_number": pr_number,
        },
        summary=f"GraphQL disablePullRequestAutoMerge on {destination}#{pr_number}",
    )


def dismiss_review(
    *, destination: str, pr_number: int, review_id: int, message: str
) -> GitHubCall:
    """Preference tightening requiring renewed consent → dismiss the prior
    approval so a fresh owner review is required."""
    return GitHubCall(
        kind="dismiss_review",
        transport="rest",
        method="PUT",
        path=_repo_path(
            destination, f"/pulls/{pr_number}/reviews/{review_id}/dismissals"
        ),
        params={"message": message, "event": "DISMISS"},
        summary=f"Dismiss review {review_id} on {destination}#{pr_number}",
    )


# ── Injected read client (Phase 2 real; tests fake) ─────────────────────────


@runtime_checkable
class GitHubApi(Protocol):
    """Read surface used by setup verification + projection reconciliation.

    Phase 2 implements this over a real GitHub App installation client. Tests
    implement it in-memory. Steady-state permissions are ``Contents: write`` +
    ``Pull requests: write`` for the acting calls; reading rulesets needs only
    ``Metadata: read`` — deliberately NOT ``Administration: read`` (that was the
    deleted classic-branch-protection path).
    """

    def list_active_rulesets(self, *, destination: str, branch: str) -> list[dict[str, Any]]:
        """Active rulesets applying to ``branch``. Each: ``{"id", "enforcement",
        "rules": [{"type", "parameters"}], "bypass_actors": [{"actor_id",
        "actor_type", "bypass_mode"}]}``."""
        ...

    def get_codeowners(self, *, destination: str) -> str | None:
        """The repo's CODEOWNERS file text, or None if absent."""
        ...

    def get_pull(self, *, destination: str, pr_number: int) -> dict[str, Any]:
        """Current GitHub PR state: ``{"state", "merged", "mergeable_state",
        "review_decision", "head_sha", "merge_commit_sha"}``."""
        ...


# ── Fail-closed setup verification ──────────────────────────────────────────


def _rule_requires_code_owner_review(rules: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
    """Scan a ruleset's rules for a ``pull_request`` rule requiring >=1 approval
    and code-owner review. Returns ``(ok, flags)`` where flags surfaces the
    stale-dismissal / last-push-approval quality signals."""
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("type") != "pull_request":
            continue
        params = rule.get("parameters") or {}
        approvals = params.get("required_approving_review_count") or 0
        code_owner = bool(params.get("require_code_owner_review"))
        if approvals >= 1 and code_owner:
            return True, {
                "required_approving_review_count": approvals,
                "require_code_owner_review": True,
                "dismiss_stale_reviews_on_push": bool(
                    params.get("dismiss_stale_reviews_on_push")
                ),
                "require_last_push_approval": bool(
                    params.get("require_last_push_approval")
                ),
            }
    return False, {}


def _app_is_bypass_actor(rulesets: list[dict[str, Any]], app_actor_id: Any) -> bool:
    if app_actor_id in (None, ""):
        return False
    for rs in rulesets:
        for actor in rs.get("bypass_actors") or []:
            if str(actor.get("actor_id")) == str(app_actor_id):
                return True
    return False


def verify_review_gate_active(
    api: GitHubApi, *, destination: str, branch: str, app_actor_id: Any = None
) -> tuple[bool, dict[str, Any]]:
    """FAIL-CLOSED: is ``destination``'s ``branch`` actually review-gated?

    Returns ``(gated, summary)``. ``gated`` is True ONLY when an active ruleset
    requires PR + code-owner review, ``CODEOWNERS`` is present, and the App is
    not a ruleset bypass actor. The ``summary`` names every missing precondition
    so the caller can tell the owner exactly what to configure. Any API failure
    is treated as "not verifiably gated" (fail closed), never as gated.
    """
    summary: dict[str, Any] = {
        "destination": destination,
        "branch": branch,
        "missing": [],
    }
    try:
        rulesets = api.list_active_rulesets(destination=destination, branch=branch)
    except Exception as exc:  # noqa: BLE001 — uninspectable ⇒ not verifiably gated
        summary["missing"].append("rulesets_uninspectable")
        summary["error"] = str(exc)
        return False, summary

    all_rules: list[dict[str, Any]] = []
    for rs in rulesets or []:
        if str(rs.get("enforcement", "active")).lower() != "active":
            continue
        all_rules.extend(rs.get("rules") or [])
    has_review_rule, flags = _rule_requires_code_owner_review(all_rules)
    if not has_review_rule:
        summary["missing"].append("required_code_owner_review_rule")
    else:
        summary["review_rule"] = flags
        # Quality signals — surfaced, not hard-required by this gate.
        if not flags.get("dismiss_stale_reviews_on_push"):
            summary["missing"].append("dismiss_stale_reviews_on_push")
        if not flags.get("require_last_push_approval"):
            summary["missing"].append("require_last_push_approval")

    try:
        codeowners = api.get_codeowners(destination=destination)
    except Exception as exc:  # noqa: BLE001
        codeowners = None
        summary["error_codeowners"] = str(exc)
    if not (codeowners or "").strip():
        summary["missing"].append("codeowners_present")
    else:
        summary["codeowners_present"] = True

    if _app_is_bypass_actor(rulesets or [], app_actor_id):
        summary["missing"].append("app_not_bypass_actor")

    # Hard preconditions: the required-review rule, CODEOWNERS, and no App bypass.
    # Stale/last-push are quality warnings that do not by themselves un-gate.
    hard_missing = {
        "required_code_owner_review_rule",
        "codeowners_present",
        "app_not_bypass_actor",
    } & set(summary["missing"])
    gated = not hard_missing
    summary["gated"] = gated
    return gated, summary


__all__ = [
    "DEFAULT_MERGE_METHOD",
    "GitHubCall",
    "GitHubApi",
    "review_approve",
    "review_request_changes",
    "merge_pr",
    "enable_auto_merge",
    "disable_auto_merge",
    "dismiss_review",
    "verify_review_gate_active",
]
