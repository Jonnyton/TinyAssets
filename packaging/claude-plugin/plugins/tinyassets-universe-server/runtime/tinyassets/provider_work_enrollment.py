"""Server-owned requester provider enrollment for cloud work.

The deployment manifest contains authority facts, never bearer credentials.
An absent or invalid manifest is deliberately equivalent to no enrollment.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from tinyassets.provider_work_authority import ProviderWorkBindingRoot, ProviderWorkBindingSeed

_ENV = "TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON"
_PROVIDERS = frozenset({"codex", "claude-code"})
_FIELDS = frozenset(
    {
        "owner_user_id",
        "universe_id",
        "provider",
        "credential_reference_digest",
        "allowed_operations",
        "allowed_roles",
        "assignment_generation",
        "assignment_digest",
        "max_invocations",
        "max_tokens",
        "max_cost_microunits",
        "expires_at",
    }
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _not_expired(value: str, *, now: datetime) -> bool:
    try:
        expiry = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except (TypeError, ValueError):
        return False
    return expiry.tzinfo is not None and expiry > now


class RequesterProviderEnrollmentResolver:
    """Resolve exactly one explicit deployment enrollment."""

    def __init__(
        self,
        entries: tuple[ProviderWorkBindingSeed, ...],
        *,
        now: datetime | None = None,
    ) -> None:
        self._entries = entries
        self._now = now or _now()

    @classmethod
    def from_environment(
        cls, *, now: datetime | None = None
    ) -> "RequesterProviderEnrollmentResolver":
        raw = os.environ.get(_ENV, "").strip()
        if not raw:
            return cls((), now=now)
        try:
            document = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return cls((), now=now)
        if not isinstance(document, list):
            return cls((), now=now)
        entries: list[ProviderWorkBindingSeed] = []
        for item in document:
            if not isinstance(item, dict) or set(item) != _FIELDS:
                continue
            try:
                owner = str(item["owner_user_id"]).strip()
                universe = str(item["universe_id"]).strip()
                provider = str(item["provider"]).strip()
                if not owner or owner == "*" or not universe or provider not in _PROVIDERS:
                    continue
                seed = ProviderWorkBindingSeed(
                    owner_user_id=owner,
                    universe_id=universe,
                    provider=provider,
                    credential_reference_digest=str(item["credential_reference_digest"]),
                    allowed_operations=tuple(item["allowed_operations"]),
                    allowed_roles=tuple(item["allowed_roles"]),
                    assignment_generation=int(item["assignment_generation"]),
                    assignment_digest=str(item["assignment_digest"]),
                    max_invocations=int(item["max_invocations"]),
                    max_tokens=int(item["max_tokens"]),
                    max_cost_microunits=int(item["max_cost_microunits"]),
                    expires_at=str(item["expires_at"]),
                )
            except (TypeError, ValueError, KeyError):
                continue
            if _not_expired(seed.expires_at, now=now or _now()):
                entries.append(seed)
        # Duplicate exact keys are ambiguous and therefore all held.
        keys = [(e.owner_user_id, e.universe_id, e.provider) for e in entries]
        if len(keys) != len(set(keys)):
            entries = []
        return cls(tuple(entries), now=now)

    def resolve(self, root: ProviderWorkBindingRoot) -> ProviderWorkBindingSeed | None:
        if not isinstance(root, ProviderWorkBindingRoot):
            raise ValueError("root must be a ProviderWorkBindingRoot")
        matches = tuple(
            entry
            for entry in self._entries
            if (
                entry.owner_user_id == root.owner_user_id
                and entry.universe_id == root.universe_id
                and entry.provider == root.provider
                and _not_expired(entry.expires_at, now=self._now)
            )
        )
        return matches[0] if len(matches) == 1 else None

    def providers(self, *, owner_user_id: str, universe_id: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    entry.provider
                    for entry in self._entries
                    if entry.owner_user_id == owner_user_id
                    and entry.universe_id == universe_id
                    and _not_expired(entry.expires_at, now=self._now)
                }
            )
        )


def enrollment_action(*, owner_user_id: str, universe_id: str) -> dict[str, Any]:
    resolver = RequesterProviderEnrollmentResolver.from_environment()
    providers = resolver.providers(owner_user_id=owner_user_id, universe_id=universe_id)
    return {
        "target": "automation",
        "operation": "bind_provider",
        "required_fields": ["provider"],
        "providers": list(providers),
        "next": (
            "bind one enrolled requester-owned provider, then retry automation create"
            if providers
            else "enroll requester-owned compute before retrying automation create"
        ),
    }


__all__ = ["RequesterProviderEnrollmentResolver", "enrollment_action"]
