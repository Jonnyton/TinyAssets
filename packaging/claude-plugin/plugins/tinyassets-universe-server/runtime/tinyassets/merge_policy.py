"""Merge *preference* vocabulary for the reference patch loop — S4 (GitHub-native).

**Redirected 2026-07-16 (host decision):** S4 is GitHub-authoritative. GitHub
owns review state, rulesets, checks, mergeability, and the atomic merge. This
module is therefore NO LONGER a local eligibility evaluator (the old
``evaluate_merge_eligibility`` — with its local ``approved`` status, fresh-OAuth
token gate, and timer-elapsed decision — is deleted; GitHub decides all of it).

What survives is a small OFF-GitHub product preference: *how* the owner wants an
eligible PR to merge once GitHub's own gate (required PR + code-owner review +
required checks) is satisfied. The preference is a per-remix binding, not a
platform-global setting.

Three preferences:

- ``manual`` (default) — the owner explicitly triggers the merge from chat after
  approving (a merge API call with the expected head SHA).
- ``auto`` — TinyAssets enables GitHub auto-merge; GitHub merges the PR the
  moment its own required reviews/checks are satisfied.
- ``not_before`` — TinyAssets holds a single durable timer; when it fires,
  TinyAssets enables GitHub auto-merge. (GitHub has no PR-level "merge after T"
  primitive, so this one timer is the only genuinely off-GitHub piece.)

**Hard rule 8 (no policy merges a red PR) is enforced by GitHub**, not here: a
required-status-checks ruleset blocks the merge/auto-merge of a failing PR
atomically at merge time. TinyAssets additionally refuses to *record* an approve
intent or enable auto-merge on a locally-known-red verify verdict, as an honest
early guard — but GitHub is the authority.

See ``docs/design-notes/2026-07-16-s4-github-native-redirect.md``.
"""

from __future__ import annotations

from typing import Any

MERGE_PREFERENCE_MANUAL = "manual"
MERGE_PREFERENCE_AUTO = "auto"
MERGE_PREFERENCE_NOT_BEFORE = "not_before"

MERGE_PREFERENCES: frozenset[str] = frozenset(
    {MERGE_PREFERENCE_MANUAL, MERGE_PREFERENCE_AUTO, MERGE_PREFERENCE_NOT_BEFORE}
)

#: The default preference when a remix has not chosen one.
DEFAULT_MERGE_PREFERENCE = MERGE_PREFERENCE_MANUAL

#: The autonomous preferences — the ones that merge without a per-PR owner
#: action, and therefore REQUIRE a verified GitHub review gate (setup
#: verification fails closed for these; ``manual`` stays available with a
#: warning).
AUTONOMOUS_PREFERENCES: frozenset[str] = frozenset(
    {MERGE_PREFERENCE_AUTO, MERGE_PREFERENCE_NOT_BEFORE}
)

#: Loop-state field names a remix binds its preference under (state fields, not
#: platform-global settings).
MERGE_PREFERENCE_STATE_FIELD = "merge_preference"
NOT_BEFORE_DELAY_STATE_FIELD = "not_before_delay_s"

#: The only green verify verdict. Anything else (fail / unknown / empty) is red.
_VERIFY_GREEN = "pass"


def normalize_preference(value: Any) -> str:
    """Return the preference string lowercased/trimmed; empty/None → ``manual``.

    Does NOT raise on an unrecognized preference — callers that need to reject
    an unknown preference (the MCP setter) check membership in
    :data:`MERGE_PREFERENCES` explicitly and return a structured error.
    """
    if value is None:
        return DEFAULT_MERGE_PREFERENCE
    text = str(value).strip().lower()
    return text or DEFAULT_MERGE_PREFERENCE


def is_autonomous(preference: Any) -> bool:
    """True iff the preference merges without a per-PR owner action (``auto`` /
    ``not_before``) — the ones that require a verified GitHub review gate."""
    return normalize_preference(preference) in AUTONOMOUS_PREFERENCES


def verify_is_green(verify_verdict: Any) -> bool:
    """Return True iff the verify verdict is the green ``pass`` sentinel.

    Deliberately strict: ``fail``, ``unknown``, ``""``, ``None`` are all red.
    TinyAssets never records an approve/auto-merge intent it locally knows is
    red; GitHub's required checks are the authoritative gate on top of this.
    """
    return str(verify_verdict or "").strip().lower() == _VERIFY_GREEN


__all__ = [
    "MERGE_PREFERENCE_MANUAL",
    "MERGE_PREFERENCE_AUTO",
    "MERGE_PREFERENCE_NOT_BEFORE",
    "MERGE_PREFERENCES",
    "AUTONOMOUS_PREFERENCES",
    "DEFAULT_MERGE_PREFERENCE",
    "MERGE_PREFERENCE_STATE_FIELD",
    "NOT_BEFORE_DELAY_STATE_FIELD",
    "normalize_preference",
    "is_autonomous",
    "verify_is_green",
]
