"""Live, fail-closed authority resolution for immutable agent manifests.

Agent definitions and manifests contain references, never authority. A server
composition root installs authoritative sources once, and every privileged
transition calls ``resolve`` again against the complete immutable manifest.
This module does not activate agents or invoke providers.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from tinyassets.agent_runtime import (
    AgentRuntimeManifest,
    AgentRuntimeManifestInput,
)
from tinyassets.storage.accounts import list_capability_grant_history

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_REFERENCE_SOURCES = (
    ("capability", "capability_ids", "capability_source"),
    ("resource", "resource_ids", "resource_source"),
    ("provider_policy", "provider_policy_ids", "provider_policy_source"),
)
_BLOCKER_CODES = frozenset(
    {
        "grant_not_current",
        "source_evidence_invalid",
        "source_error",
        "source_unavailable",
    }
)


class AgentRuntimeGrantError(ValueError):
    """A runtime grant request violates the immutable resolver contract."""


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise AgentRuntimeGrantError(f"{name} must be canonical non-empty text")
    return value


def _finite_timestamp(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgentRuntimeGrantError(f"{name} must be a finite timestamp")
    result = float(value)
    if not math.isfinite(result):
        raise AgentRuntimeGrantError(f"{name} must be a finite timestamp")
    return result


@dataclass(frozen=True, slots=True)
class AgentRuntimeGrantEvidence:
    """Non-secret identity of one current authoritative grant generation."""

    reference_kind: str
    reference_id: str
    subject_id: str
    universe_id: str
    scope: str
    generation: int
    grant_digest: str
    expires_at: float | None

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        for name in (
            "reference_kind",
            "reference_id",
            "subject_id",
            "universe_id",
            "scope",
            "grant_digest",
        ):
            _text(getattr(self, name), name)
        if self.reference_kind not in {item[0] for item in _REFERENCE_SOURCES}:
            raise AgentRuntimeGrantError("reference_kind is unsupported")
        if type(self.generation) is not int or self.generation < 1:
            raise AgentRuntimeGrantError("generation must be an integer >= 1")
        if _SHA256.fullmatch(self.grant_digest) is None:
            raise AgentRuntimeGrantError("grant_digest must be canonical sha256")
        if self.expires_at is not None:
            _finite_timestamp(self.expires_at, "expires_at")

    def to_dict(self) -> dict[str, object]:
        return {
            "reference_kind": self.reference_kind,
            "reference_id": self.reference_id,
            "subject_id": self.subject_id,
            "universe_id": self.universe_id,
            "scope": self.scope,
            "generation": self.generation,
            "grant_digest": self.grant_digest,
            "expires_at": self.expires_at,
        }


class AgentRuntimeGrantSource(Protocol):
    """Server-owned live authority reader for one reference class."""

    def resolve_current(
        self,
        *,
        subject_id: str,
        universe_id: str,
        reference_id: str,
        evaluated_at: float,
    ) -> AgentRuntimeGrantEvidence | None: ...


@dataclass(frozen=True, slots=True)
class AgentRuntimeGrantBlocker:
    reference_kind: str
    reference_id: str
    code: str
    message: str

    def __post_init__(self) -> None:
        if self.reference_kind not in {item[0] for item in _REFERENCE_SOURCES}:
            raise AgentRuntimeGrantError("blocker reference_kind is unsupported")
        _text(self.reference_id, "blocker reference_id")
        if self.code not in _BLOCKER_CODES:
            raise AgentRuntimeGrantError("blocker code is unsupported")
        _text(self.message, "blocker message")


@dataclass(frozen=True, slots=True)
class AgentRuntimeGrantResolution:
    manifest_id: str
    manifest_digest: str
    evaluated_at: float
    evidence: tuple[AgentRuntimeGrantEvidence, ...]
    blockers: tuple[AgentRuntimeGrantBlocker, ...]
    evidence_set_digest: str

    @property
    def ready(self) -> bool:
        return not self.blockers


@dataclass(frozen=True, slots=True)
class AccountCapabilityGrantSource:
    """Live capability reader backed by the canonical author-server store."""

    base_path: str | Path

    def resolve_current(
        self,
        *,
        subject_id: str,
        universe_id: str,
        reference_id: str,
        evaluated_at: float,
    ) -> AgentRuntimeGrantEvidence | None:
        now = _finite_timestamp(evaluated_at, "evaluated_at")
        rows = list_capability_grant_history(
            self.base_path,
            subject_id=subject_id,
            capability=reference_id,
        )
        active = [
            row
            for row in rows
            if row["scope"] in {universe_id, "*"}
            and float(row["created_at"]) <= now
            and (row["expires_at"] is None or now < float(row["expires_at"]))
            and (row["revoked_at"] is None or now < float(row["revoked_at"]))
        ]
        if not active:
            return None
        row = min(
            active,
            key=lambda item: (
                item["scope"] != universe_id,
                -int(item["generation"]),
            ),
        )
        grant_digest = _digest(
            {
                "reference_kind": "capability",
                "reference_id": reference_id,
                "subject_id": subject_id,
                "universe_id": universe_id,
                "scope": row["scope"],
                "generation": row["generation"],
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
                "revoked_at": row["revoked_at"],
            }
        )
        return AgentRuntimeGrantEvidence(
            reference_kind="capability",
            reference_id=reference_id,
            subject_id=subject_id,
            universe_id=universe_id,
            scope=str(row["scope"]),
            generation=int(row["generation"]),
            grant_digest=grant_digest,
            expires_at=(None if row["expires_at"] is None else float(row["expires_at"])),
        )


class AgentRuntimeGrantResolver:
    """Resolve all immutable-manifest references against current authority."""

    def __init__(
        self,
        *,
        capability_source: AgentRuntimeGrantSource | None = None,
        resource_source: AgentRuntimeGrantSource | None = None,
        provider_policy_source: AgentRuntimeGrantSource | None = None,
    ) -> None:
        self._capability_source = capability_source
        self._resource_source = resource_source
        self._provider_policy_source = provider_policy_source

    def resolve(
        self,
        manifest: AgentRuntimeManifest,
        *,
        evaluated_at: float,
    ) -> AgentRuntimeGrantResolution:
        current_manifest = _validated_manifest(manifest)
        now = _finite_timestamp(evaluated_at, "evaluated_at")
        payload = current_manifest.to_dict()
        references = payload["requested_references"]
        subject_id = payload["owner_user_id"]
        universe_id = payload["universe_id"]
        evidence: list[AgentRuntimeGrantEvidence] = []
        blockers: list[AgentRuntimeGrantBlocker] = []

        for reference_kind, field, source_name in _REFERENCE_SOURCES:
            source = getattr(self, f"_{source_name}")
            for reference_id in references[field]:
                if source is None:
                    blockers.append(_blocker(reference_kind, reference_id, "source_unavailable"))
                    continue
                try:
                    item = source.resolve_current(
                        subject_id=subject_id,
                        universe_id=universe_id,
                        reference_id=reference_id,
                        evaluated_at=now,
                    )
                except Exception:
                    blockers.append(_blocker(reference_kind, reference_id, "source_error"))
                    continue
                if item is None:
                    blockers.append(_blocker(reference_kind, reference_id, "grant_not_current"))
                    continue
                if not _valid_evidence(
                    item,
                    reference_kind=reference_kind,
                    reference_id=reference_id,
                    subject_id=subject_id,
                    universe_id=universe_id,
                    evaluated_at=now,
                ):
                    blockers.append(
                        _blocker(reference_kind, reference_id, "source_evidence_invalid")
                    )
                    continue
                evidence.append(item)

        evidence_tuple = tuple(evidence)
        return AgentRuntimeGrantResolution(
            manifest_id=current_manifest.manifest_id,
            manifest_digest=current_manifest.manifest_digest,
            evaluated_at=now,
            evidence=evidence_tuple,
            blockers=tuple(blockers),
            evidence_set_digest=_digest(
                {
                    "manifest_digest": current_manifest.manifest_digest,
                    "evidence": [item.to_dict() for item in evidence_tuple],
                }
            ),
        )


def _validated_manifest(manifest: AgentRuntimeManifest) -> AgentRuntimeManifest:
    try:
        if not isinstance(manifest, AgentRuntimeManifest):
            raise TypeError
        manifest_input = AgentRuntimeManifestInput.from_dict(manifest.manifest_input.to_dict())
        return AgentRuntimeManifest(
            manifest_id=manifest.manifest_id,
            manifest_digest=manifest.manifest_digest,
            manifest_input=manifest_input,
            created_at=manifest.created_at,
        )
    except Exception:
        raise AgentRuntimeGrantError("manifest integrity validation failed") from None


def _valid_evidence(
    evidence: object,
    *,
    reference_kind: str,
    reference_id: str,
    subject_id: str,
    universe_id: str,
    evaluated_at: float,
) -> bool:
    try:
        if not isinstance(evidence, AgentRuntimeGrantEvidence):
            return False
        evidence._validate()
        return (
            evidence.reference_kind == reference_kind
            and evidence.reference_id == reference_id
            and evidence.subject_id == subject_id
            and evidence.universe_id == universe_id
            and (evidence.expires_at is None or evaluated_at < evidence.expires_at)
        )
    except AgentRuntimeGrantError:
        return False


def _blocker(
    reference_kind: str,
    reference_id: str,
    code: str,
) -> AgentRuntimeGrantBlocker:
    messages = {
        "grant_not_current": "no current authoritative grant exists",
        "source_evidence_invalid": "the authoritative source returned invalid evidence",
        "source_error": "the authoritative source could not be read",
        "source_unavailable": "no authoritative source is installed",
    }
    return AgentRuntimeGrantBlocker(
        reference_kind=reference_kind,
        reference_id=reference_id,
        code=code,
        message=messages[code],
    )


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


__all__ = [
    "AccountCapabilityGrantSource",
    "AgentRuntimeGrantBlocker",
    "AgentRuntimeGrantError",
    "AgentRuntimeGrantEvidence",
    "AgentRuntimeGrantResolution",
    "AgentRuntimeGrantResolver",
    "AgentRuntimeGrantSource",
]
