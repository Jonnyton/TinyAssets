"""Narrow control-plane actions for the result-bound GitHub PR effect."""

from __future__ import annotations

from datetime import datetime

from tinyassets.runtime.effect_authorization import (
    EffectReceipt,
    GitHubEffectAuthorization,
    GitHubEffectService,
)


def create_github_pr_authorization(
    service: GitHubEffectService,
    *,
    job_id: str,
    grant_id: str,
    review_record_id: str,
    authenticated_owner_id: str,
    expires_at: datetime,
) -> GitHubEffectAuthorization:
    """Create one authorization; repository and result come from authority state."""
    return service.authorize(
        job_id=job_id,
        grant_id=grant_id,
        review_record_id=review_record_id,
        authenticated_owner_id=authenticated_owner_id,
        expires_at=expires_at,
    )


def apply_github_pr_authorization(
    service: GitHubEffectService,
    *,
    authorization_id: str,
    idempotency_key: str,
) -> EffectReceipt:
    """Apply by authorization ID only; transport identity never defines effect ID."""
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ValueError("Idempotency-Key is required")
    return service.apply(authorization_id=authorization_id)


__all__ = [
    "apply_github_pr_authorization",
    "create_github_pr_authorization",
]
