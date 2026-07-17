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
    *, destination: str, pr_number: int, merge_method: str = "SQUASH",
    expected_head_sha: str = "", pull_request_id: str = "",
) -> GitHubCall:
    """Auto / fired timer → GraphQL ``enablePullRequestAutoMerge``; GitHub merges
    once its own required reviews/checks are satisfied.

    GitHub's mutation requires the PR's GraphQL ``pullRequestId`` (node id) and
    supports ``expectedHeadOid`` for head-binding (Codex r11 #4). ``kind`` is
    ``enable_auto_merge`` only when the node id AND expected head are BOTH
    resolved — otherwise it is honestly named ``enable_auto_merge_intent`` (an
    unresolved intent, not an exact call), so a caller never mistakes an
    unbound record for a ready-to-run call."""
    head = (expected_head_sha or "").strip()
    node_id = (pull_request_id or "").strip()
    resolved = bool(head and node_id)
    return GitHubCall(
        kind="enable_auto_merge" if resolved else "enable_auto_merge_intent",
        transport="graphql",
        method="POST",
        path="graphql",
        params={
            "mutation": "enablePullRequestAutoMerge",
            "destination": destination,
            "pr_number": pr_number,
            "merge_method": merge_method,
            "pull_request_id": node_id,
            "expected_head_oid": head,
            "resolved": resolved,
        },
        summary=(
            f"GraphQL enablePullRequestAutoMerge on {destination}#{pr_number} "
            f"({merge_method}); head {head[:8] or '(unresolved)'} "
            f"node {node_id or '(unresolved)'}"
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

    def get_codeowners(self, *, destination: str, ref: str = "") -> str | None:
        """The repo's CODEOWNERS text at the PR's base ``ref`` (Codex r14 #6), or
        None if absent."""
        ...

    def get_pull(self, *, destination: str, pr_number: int) -> dict[str, Any]:
        """Current GitHub PR state: ``{"state", "merged", "mergeable_state",
        "review_decision", "head_sha", "base_ref", "merge_commit_sha",
        "node_id"}``. ``base_ref`` is authoritative — the gate verifies against
        the PR's ACTUAL base branch, never a packet-supplied ref (Codex r11
        #1)."""
        ...


# ── Fail-closed setup verification ──────────────────────────────────────────


def _find_review_rule(rules: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the parameters of a ``pull_request`` rule requiring >=1 approval +
    code-owner review, or None."""
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("type") != "pull_request":
            continue
        params = rule.get("parameters") or {}
        if (params.get("required_approving_review_count") or 0) >= 1 and bool(
            params.get("require_code_owner_review")
        ):
            return params
    return None


def _has_required_status_checks(rules: list[dict[str, Any]]) -> bool:
    """True iff an active ``required_status_checks`` rule lists >=1 check."""
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("type") != "required_status_checks":
            continue
        params = rule.get("parameters") or {}
        checks = params.get("required_status_checks") or []
        if isinstance(checks, list) and len(checks) >= 1:
            return True
    return False


#: Representative paths whose EFFECTIVE (last-matching) owner must be the
#: founder for the gate to pass: a root code path (the merge path) AND the
#: CODEOWNERS file itself (so it can't be changed without founder review).
_CODEOWNERS_PROBE_PATHS = (
    "src/main.py", "README.md", ".github/CODEOWNERS", "CODEOWNERS",
)


def _codeowners_pattern_matches(pattern: str, path: str) -> bool:
    """Approximate GitHub CODEOWNERS path matching for the gate's probe paths."""
    import fnmatch

    pat = pattern.strip()
    p = path.lstrip("/")
    if pat == "*":
        return True
    anchored = pat.startswith("/")
    pat = pat.lstrip("/")
    if pat.endswith("/"):  # directory → matches anything under it
        return p == pat.rstrip("/") or p.startswith(pat)
    # Anchored patterns match from repo root; unanchored match any path segment.
    if anchored:
        return fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(p, pat + "/*") or p == pat
    return (
        fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(p, "*/" + pat)
        or p.endswith("/" + pat) or p == pat
    )


def _codeowners_effective_owners(text: str, path: str) -> list[str]:
    """Return the owners of the LAST CODEOWNERS rule matching ``path`` — GitHub's
    last-match-wins semantics (Codex r14 #6). A `* @founder` catch-all overridden
    by a LATER pattern yields the later owners, not the founder."""
    owners: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        if _codeowners_pattern_matches(parts[0], path):
            owners = [o.strip().lstrip("@").lower() for o in parts[1:]]
    return owners


def _codeowners_founder_owns_merge_path(text: str, expected_owner: str) -> bool:
    """True iff the founder is the EFFECTIVE (last-matching) owner of BOTH a root
    code path AND the CODEOWNERS file itself, for every probe path — so no later
    pattern can override the founder's ownership of the merge path or leave
    CODEOWNERS itself unprotected (Codex r14 #6)."""
    want = (expected_owner or "").strip().lstrip("@").lower()
    if not want:
        return False
    for probe in _CODEOWNERS_PROBE_PATHS:
        owners = _codeowners_effective_owners(text, probe)
        if want not in owners:
            return False
    return True


def _get_codeowners_at_ref(api: Any, *, destination: str, ref: str) -> str | None:
    """Fetch CODEOWNERS at the PR's actual base ``ref`` (Codex r14 #6). Tolerates
    a client whose ``get_codeowners`` doesn't yet accept ``ref``."""
    try:
        return api.get_codeowners(destination=destination, ref=ref)
    except TypeError:
        return api.get_codeowners(destination=destination)


def verify_review_gate_active(
    api: GitHubApi, *, destination: str, branch: str, app_actor_id: Any = None,
    expected_owner: str = "",
) -> tuple[bool, dict[str, Any]]:
    """FAIL-CLOSED: is ``destination``'s ``branch`` actually review-gated?

    Returns ``(gated, summary)``. Every precondition below is HARD — ``gated`` is
    True only when ALL hold; anything missing or uninspectable un-gates (Codex
    r11 #1). ``summary['missing']`` names each gap so the owner is told exactly
    what to configure. The caller MUST pass the PR's ACTUAL base branch (read
    from GitHub), not a packet-supplied ref.

    Hard preconditions:

    - an active ``pull_request`` rule requiring >=1 approval + code-owner review;
    - ``dismiss_stale_reviews_on_push`` AND ``require_last_push_approval`` on it
      (stale/newly-pushed commits can't ride a prior approval);
    - an active ``required_status_checks`` rule with >=1 check (no red merge);
    - ``CODEOWNERS`` with a ``*`` catch-all owned by the EXPECTED founder;
    - a KNOWN App identity (``app_actor_id``) AND positively-visible bypass
      config on every active ruleset — GitHub omits ``bypass_actors`` unless the
      caller has ruleset-read, so MISSING bypass data fails closed (not assumed
      empty), and the App must not be in any bypass list.
    """
    summary: dict[str, Any] = {
        "destination": destination, "branch": branch, "missing": [],
    }
    missing: list[str] = summary["missing"]
    try:
        rulesets = api.list_active_rulesets(destination=destination, branch=branch)
    except Exception as exc:  # noqa: BLE001 — uninspectable ⇒ not verifiably gated
        missing.append("rulesets_uninspectable")
        summary["error"] = str(exc)
        return False, summary

    active = [
        rs for rs in (rulesets or [])
        if str(rs.get("enforcement", "active")).lower() == "active"
    ]
    all_rules: list[dict[str, Any]] = []
    for rs in active:
        all_rules.extend(rs.get("rules") or [])

    review = _find_review_rule(all_rules)
    if review is None:
        missing.append("required_code_owner_review_rule")
    else:
        summary["review_rule"] = {
            "required_approving_review_count": review.get("required_approving_review_count"),
            "require_code_owner_review": True,
        }
        if not review.get("dismiss_stale_reviews_on_push"):
            missing.append("dismiss_stale_reviews_on_push")
        if not review.get("require_last_push_approval"):
            missing.append("require_last_push_approval")

    if not _has_required_status_checks(all_rules):
        missing.append("required_status_checks")

    # App identity + POSITIVELY visible bypass config (fail closed on either gap).
    if app_actor_id in (None, ""):
        missing.append("app_identity_known")
    if not active:
        # No active ruleset at all → bypass config not verifiable.
        missing.append("bypass_actors_visible")
    else:
        for rs in active:
            if "bypass_actors" not in rs:
                missing.append("bypass_actors_visible")
                break
        if app_actor_id not in (None, ""):
            for rs in active:
                for actor in rs.get("bypass_actors") or []:
                    if str(actor.get("actor_id")) == str(app_actor_id):
                        missing.append("app_not_bypass_actor")
                        break

    # CODEOWNERS at the PR's ACTUAL base ref (Codex r14 #6) — the base branch's
    # CODEOWNERS governs review requests. Effective (last-match-wins) ownership of
    # the merge path AND of CODEOWNERS itself must be the founder.
    try:
        codeowners = _get_codeowners_at_ref(api, destination=destination, ref=branch)
    except Exception as exc:  # noqa: BLE001
        codeowners = None
        summary["error_codeowners"] = str(exc)
    if not (expected_owner or "").strip():
        missing.append("expected_owner_unknown")
    elif not _codeowners_founder_owns_merge_path(codeowners or "", expected_owner):
        missing.append("codeowners_founder_effective_owner")
    else:
        summary["codeowners_founder_effective_owner"] = expected_owner.strip().lstrip("@")

    # De-dup while preserving order.
    seen: set[str] = set()
    summary["missing"] = [m for m in missing if not (m in seen or seen.add(m))]
    gated = not summary["missing"]
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
