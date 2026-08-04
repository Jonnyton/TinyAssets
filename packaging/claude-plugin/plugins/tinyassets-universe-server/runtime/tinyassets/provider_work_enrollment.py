"""Server-owned requester provider enrollment for cloud work.

The deployment manifest contains authority facts, never bearer credentials.
An absent or invalid manifest is deliberately equivalent to no enrollment.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from tinyassets.provider_work_authority import ProviderWorkBindingRoot, ProviderWorkBindingSeed

_ENV = "TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON"
_PROVIDERS = frozenset({"codex", "claude-code"})
_FINGERPRINT_RE = r"v[0-9]+:[0-9a-f]{64}"
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


def _principal_fingerprint(owner_user_id: str) -> str | None:
    """Derive the same token-free identity fingerprint exposed by status."""
    key = os.environ.get("TINYASSETS_IDENTITY_FINGERPRINT_KEY", "")
    version = os.environ.get("TINYASSETS_IDENTITY_FINGERPRINT_VERSION", "v1")
    if not isinstance(key, str) or len(key.encode()) < 32:
        return None
    if not isinstance(version, str) or not version.strip():
        return None
    version = version.strip()
    if re.fullmatch(r"[A-Za-z0-9._-]+", version) is None:
        return None
    message = f"tinyassets:request-identity:{version}\0{owner_user_id}".encode()
    digest = hmac.new(key.encode(), message, hashlib.sha256).hexdigest()
    return f"{version}:{digest}"


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
                owner = item["owner_user_id"]
                universe = item["universe_id"]
                provider = item["provider"]
                credential_digest = item["credential_reference_digest"]
                operations = item["allowed_operations"]
                roles = item["allowed_roles"]
                assignment_generation = item["assignment_generation"]
                assignment_digest = item["assignment_digest"]
                max_invocations = item["max_invocations"]
                max_tokens = item["max_tokens"]
                max_cost = item["max_cost_microunits"]
                expires_at = item["expires_at"]
                if not all(
                    isinstance(value, str)
                    for value in (
                        owner,
                        universe,
                        provider,
                        credential_digest,
                        assignment_digest,
                        expires_at,
                    )
                ):
                    continue
                if not all(
                    isinstance(value, list)
                    and all(isinstance(item_value, str) for item_value in value)
                    for value in (operations, roles)
                ):
                    continue
                if any(
                    isinstance(value, bool) or not isinstance(value, int)
                    for value in (
                        assignment_generation,
                        max_invocations,
                        max_tokens,
                        max_cost,
                    )
                ):
                    continue
                owner = owner.strip()
                universe = universe.strip()
                provider = provider.strip()
                if not owner or owner == "*" or not universe or provider not in _PROVIDERS:
                    continue
                seed = ProviderWorkBindingSeed(
                    owner_user_id=owner,
                    universe_id=universe,
                    provider=provider,
                    credential_reference_digest=credential_digest,
                    allowed_operations=tuple(operations),
                    allowed_roles=tuple(roles),
                    assignment_generation=assignment_generation,
                    assignment_digest=assignment_digest,
                    max_invocations=max_invocations,
                    max_tokens=max_tokens,
                    max_cost_microunits=max_cost,
                    expires_at=expires_at,
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
        fingerprint = _principal_fingerprint(root.owner_user_id)
        matches = tuple(
            entry
            for entry in self._entries
            if (
                entry.universe_id == root.universe_id
                and entry.provider == root.provider
                and _not_expired(entry.expires_at, now=self._now)
                and (
                    entry.owner_user_id == root.owner_user_id
                    or (
                        fingerprint is not None
                        and entry.owner_user_id == fingerprint
                    )
                )
            )
        )
        if len(matches) != 1:
            return None
        matched = matches[0]
        if matched.owner_user_id == root.owner_user_id:
            return matched
        return replace(matched, owner_user_id=root.owner_user_id)

    def providers(self, *, owner_user_id: str, universe_id: str) -> tuple[str, ...]:
        fingerprint = _principal_fingerprint(owner_user_id)
        return tuple(
            sorted(
                {
                    entry.provider
                    for entry in self._entries
                    if entry.owner_user_id in {owner_user_id, fingerprint}
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
