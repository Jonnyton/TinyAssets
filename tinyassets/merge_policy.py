"""Per-remix merge policy for the patch loop — S4 (G6).

A remixed patch loop binds a **merge policy** as loop state (never a
platform-global setting): it governs *when* a queued, owner-reviewable PR
actually merges.

Three policies:

- ``manual`` (default) — a PR merges only after the owner explicitly approves
  it on the review queue.
- ``auto`` — a PR merges as soon as the verify gate is green (no per-PR owner
  action). Still owner-scoped: only the owner's own loop, on the owner's bound
  repo, runs this.
- ``timer`` — a PR merges once the verify gate is green AND a delay has elapsed
  since it was queued, UNLESS the owner has held it (reshaped / rejected /
  explicit hold).

**Hard invariant (hard rule 8, reference design §7): NO policy merges a red
PR.** ``auto`` and ``timer`` require the verify gate green, and even ``manual``
approval cannot release a red PR — a red verify verdict blocks eligibility
under every policy. This module is the single place that invariant is decided.

Founder-OAuth-per-merge is an orthogonal flag layered on top of any policy:
when set, eligibility additionally requires a *fresh* founder approval token to
be present (minted by ``review_queue.approve_item``, consumed at merge). See
``tinyassets.storage.review_queue`` for the fresh-vs-standing distinction.

This module is pure (no IO): callers supply the resolved facts (verdict,
status, timer facts, whether a fresh approval is present) and receive an
eligibility decision. The effector (``effectors/github_merge.py``) wires it to
storage + the live PR head.
"""

from __future__ import annotations

import math
from typing import Any

MERGE_POLICY_MANUAL = "manual"
MERGE_POLICY_AUTO = "auto"
MERGE_POLICY_TIMER = "timer"

MERGE_POLICIES: frozenset[str] = frozenset(
    {MERGE_POLICY_MANUAL, MERGE_POLICY_AUTO, MERGE_POLICY_TIMER}
)

#: The default policy when a remix has not chosen one.
DEFAULT_MERGE_POLICY = MERGE_POLICY_MANUAL

#: Loop state field name the remix binds its policy under (a state field, not a
#: platform-global setting).
MERGE_POLICY_STATE_FIELD = "merge_policy"
FOUNDER_OAUTH_STATE_FIELD = "founder_oauth_per_merge"
TIMER_DELAY_STATE_FIELD = "merge_timer_delay_s"

#: The only green verify verdict. Anything else (fail / unknown / empty) blocks.
_VERIFY_GREEN = "pass"


def normalize_policy(value: Any) -> str:
    """Return a validated policy string.

    Empty / None resolves to the ``manual`` default. An unknown non-empty value
    is a contract violation — a remix that binds ``merge_policy="yolo"`` must
    fail loud (hard rule 8), not silently degrade to a permissive mode.
    """
    if value is None:
        return DEFAULT_MERGE_POLICY
    text = str(value).strip().lower()
    if not text:
        return DEFAULT_MERGE_POLICY
    if text not in MERGE_POLICIES:
        raise ValueError(
            f"unknown merge policy {value!r}; must be one of "
            f"{sorted(MERGE_POLICIES)}"
        )
    return text


def verify_is_green(verify_verdict: Any) -> bool:
    """Return True iff the verify verdict is the green ``pass`` sentinel.

    Deliberately strict: ``fail``, ``unknown``, ``""``, ``None`` are all red.
    A merge policy never treats an unknown verdict as safe.
    """
    return str(verify_verdict or "").strip().lower() == _VERIFY_GREEN


def _blocked(reason: str, **extra: Any) -> dict[str, Any]:
    return {"eligible": False, "reason": reason, **extra}


def evaluate_merge_eligibility(
    *,
    policy: Any,
    verify_verdict: Any,
    item_status: str = "",
    founder_oauth_required: bool = False,
    fresh_approval_present: bool = False,
    created_at: float | None = None,
    now: float | None = None,
    timer_delay_s: float = 0.0,
    held: bool = False,
) -> dict[str, Any]:
    """Decide whether a queued PR may merge under its bound policy.

    Returns ``{"eligible": bool, "reason": str, "policy": str, ...}``.

    Order of gates (each is fail-closed):

    1. **Red-verify guard (universal).** A non-green verify verdict blocks every
       policy — including ``manual`` approval. No policy merges a red PR.
    2. **Policy gate.** ``manual`` needs owner ``approved`` status; ``auto`` is
       released by green verify alone; ``timer`` needs green verify + elapsed
       delay + not held.
    3. **Founder-OAuth gate.** When required, a fresh approval token must be
       present regardless of policy.
    """
    resolved_policy = normalize_policy(policy)

    if not verify_is_green(verify_verdict):
        return _blocked(
            "verify_not_green",
            policy=resolved_policy,
            verify_verdict=str(verify_verdict or "").strip().lower() or "unknown",
        )

    status = (item_status or "").strip().lower()

    # An already-merged item is terminal under EVERY policy — never re-merge it.
    # (Without this guard, `auto` would re-evaluate a merged item as eligible.)
    if status == "merged":
        return _blocked(
            "already_merged",
            policy=resolved_policy,
            item_status=status,
        )

    if resolved_policy == MERGE_POLICY_MANUAL:
        if status != "approved":
            return _blocked(
                "manual_policy_awaiting_owner_approval",
                policy=resolved_policy,
                item_status=status or "pending",
            )
    elif resolved_policy == MERGE_POLICY_TIMER:
        if held or status in {"reshaped", "rejected"}:
            return _blocked(
                "timer_policy_held_by_owner",
                policy=resolved_policy,
                item_status=status,
            )
        if created_at is None or now is None:
            return _blocked(
                "timer_policy_missing_clock",
                policy=resolved_policy,
            )
        # Fail closed on a malformed delay (Codex R5 REQUIRED 2). A negative /
        # NaN / inf delay must never read as "eligible now" — the effector
        # boundary rejects these with a structured error, and this is the
        # defense-in-depth guard so the pure evaluator can't fail open either.
        if not isinstance(timer_delay_s, (int, float)) or not math.isfinite(
            timer_delay_s
        ) or timer_delay_s < 0:
            return _blocked(
                "timer_delay_invalid",
                policy=resolved_policy,
                timer_delay_s=timer_delay_s,
            )
        elapsed = now - created_at
        if elapsed < timer_delay_s:
            return _blocked(
                "timer_policy_delay_not_elapsed",
                policy=resolved_policy,
                elapsed_s=round(elapsed, 3),
                timer_delay_s=timer_delay_s,
            )
    elif resolved_policy == MERGE_POLICY_AUTO:
        if status in {"reshaped", "rejected"}:
            return _blocked(
                "auto_policy_held_by_owner",
                policy=resolved_policy,
                item_status=status,
            )
    # (normalize_policy guarantees resolved_policy is one of the three.)

    if founder_oauth_required and not fresh_approval_present:
        return _blocked(
            "founder_oauth_required",
            policy=resolved_policy,
            hint=(
                "this merge requires a fresh founder-authenticated approval "
                "bound to the exact PR head; a standing consent does not "
                "satisfy it"
            ),
        )

    return {
        "eligible": True,
        "reason": "eligible",
        "policy": resolved_policy,
        "founder_oauth_required": founder_oauth_required,
    }


__all__ = [
    "MERGE_POLICY_MANUAL",
    "MERGE_POLICY_AUTO",
    "MERGE_POLICY_TIMER",
    "MERGE_POLICIES",
    "DEFAULT_MERGE_POLICY",
    "MERGE_POLICY_STATE_FIELD",
    "FOUNDER_OAUTH_STATE_FIELD",
    "TIMER_DELAY_STATE_FIELD",
    "normalize_policy",
    "verify_is_green",
    "evaluate_merge_eligibility",
]
