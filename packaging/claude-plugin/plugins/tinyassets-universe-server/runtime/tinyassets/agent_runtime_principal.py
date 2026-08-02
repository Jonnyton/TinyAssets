"""Dark, server-derived authority identity for one custom-agent invocation.

The immutable manifest and its references are requests, not authority. This
module composes current canonical activation state, a server-owned invocation
identity source, and freshly resolved non-secret grant generations into one
narrow principal. It does not admit work, invoke a provider, or perform an
effect. Trusted sinks must derive again before every privileged transition.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Protocol

from tinyassets.agent_runtime import AgentRuntimeManifest, AgentRuntimeManifestInput
from tinyassets.agent_runtime_grants import (
    AgentRuntimeGrantBlocker,
    AgentRuntimeGrantEvidence,
    AgentRuntimeGrantResolver,
)
from tinyassets.execution_subject import (
    ExecutionSubject,
    ExecutionSubjectKind,
    agent_binding_automation_id,
)
from tinyassets.storage.automation_activations import (
    AutomationActivation,
    AutomationActivationExecutor,
    AutomationActivationState,
    AutomationActivationStore,
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_BLOCKER_CODES = frozenset(
    {
        "activation_not_current",
        "activation_source_error",
        "activation_subject_mismatch",
        "grant_not_current",
        "grant_source_error",
        "invocation_evidence_invalid",
        "invocation_fence_mismatch",
        "invocation_identity_mismatch",
        "invocation_not_current",
        "invocation_source_error",
        "manifest_invalid",
    }
)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be canonical non-empty text")
    return value


def _positive_integer(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be an integer >= 1")
    return value


def _digest_value(value: object, name: str) -> str:
    value = _text(value, name)
    if _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a canonical sha256 digest")
    return value


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


@dataclass(frozen=True, slots=True)
class AgentInvocationAuthorityEvidence:
    """Non-bearer identity read from the future canonical invocation owner."""

    invocation_id: str
    invocation_generation: int
    authorizing_subject_id: str
    universe_id: str
    agent_binding_id: str
    binding_revision: int
    execution_subject: ExecutionSubject
    activation_automation_id: str
    activation_epoch: int
    executor_class: AutomationActivationExecutor
    lease_id: str
    typed_input_digest: str

    def __post_init__(self) -> None:
        _text(self.invocation_id, "invocation_id")
        if not self.invocation_id.startswith("agent_invocation_"):
            raise ValueError("invocation_id is not an agent invocation")
        _positive_integer(self.invocation_generation, "invocation_generation")
        for name in (
            "authorizing_subject_id",
            "universe_id",
            "agent_binding_id",
            "activation_automation_id",
            "lease_id",
        ):
            _text(getattr(self, name), name)
        _positive_integer(self.binding_revision, "binding_revision")
        _positive_integer(self.activation_epoch, "activation_epoch")
        if (
            not isinstance(self.execution_subject, ExecutionSubject)
            or self.execution_subject.kind is not ExecutionSubjectKind.AGENT_RUNTIME_MANIFEST
        ):
            raise ValueError("execution_subject must be an agent runtime manifest")
        if not isinstance(self.executor_class, AutomationActivationExecutor):
            raise ValueError("executor_class must be typed")
        _digest_value(self.typed_input_digest, "typed_input_digest")


class AgentInvocationAuthoritySource(Protocol):
    """Server-owned current invocation identity reader."""

    def resolve_current(
        self,
        *,
        invocation_id: str,
    ) -> AgentInvocationAuthorityEvidence | None: ...


class AgentRuntimePrincipalBlocked(RuntimeError):
    """A safe typed blocker prevented server-side principal derivation."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        grant_blockers: tuple[AgentRuntimeGrantBlocker, ...] = (),
    ) -> None:
        if code not in _BLOCKER_CODES:
            raise ValueError("principal blocker code is unsupported")
        self.code = code
        self.grant_blockers = tuple(grant_blockers)
        super().__init__(_text(message, "message"))


@dataclass(frozen=True, slots=True)
class AgentRuntimePrincipal:
    """Immutable non-bearer authority identity for one exact invocation."""

    authorizing_subject_id: str
    universe_id: str
    agent_binding_id: str
    binding_revision: int
    execution_subject: ExecutionSubject
    activation_automation_id: str
    activation_epoch: int
    executor_class: AutomationActivationExecutor
    lease_id: str
    invocation_id: str
    invocation_generation: int
    typed_input_digest: str
    evaluated_at: float
    grant_evidence: tuple[AgentRuntimeGrantEvidence, ...]
    grant_evidence_set_digest: str
    principal_digest: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "authorizing_subject_id",
            "universe_id",
            "agent_binding_id",
            "activation_automation_id",
            "lease_id",
            "invocation_id",
        ):
            _text(getattr(self, name), name)
        _positive_integer(self.binding_revision, "binding_revision")
        _positive_integer(self.activation_epoch, "activation_epoch")
        _positive_integer(self.invocation_generation, "invocation_generation")
        if (
            not isinstance(self.execution_subject, ExecutionSubject)
            or self.execution_subject.kind is not ExecutionSubjectKind.AGENT_RUNTIME_MANIFEST
        ):
            raise ValueError("execution_subject must be an agent runtime manifest")
        if not isinstance(self.executor_class, AutomationActivationExecutor):
            raise ValueError("executor_class must be typed")
        _digest_value(self.typed_input_digest, "typed_input_digest")
        if isinstance(self.evaluated_at, bool) or not isinstance(self.evaluated_at, (int, float)):
            raise ValueError("evaluated_at must be a timestamp")
        if type(self.grant_evidence) is not tuple or any(
            type(item) is not AgentRuntimeGrantEvidence for item in self.grant_evidence
        ):
            raise ValueError("grant_evidence must be detached typed evidence")
        _digest_value(self.grant_evidence_set_digest, "grant_evidence_set_digest")
        object.__setattr__(self, "principal_digest", _digest(self._identity_dict()))

    def _identity_dict(self) -> dict[str, object]:
        return {
            "authorizing_subject_id": self.authorizing_subject_id,
            "universe_id": self.universe_id,
            "agent_binding_id": self.agent_binding_id,
            "binding_revision": self.binding_revision,
            "execution_subject": self.execution_subject.to_dict(),
            "activation_automation_id": self.activation_automation_id,
            "activation_epoch": self.activation_epoch,
            "executor_class": self.executor_class.value,
            "lease_id": self.lease_id,
            "invocation_id": self.invocation_id,
            "invocation_generation": self.invocation_generation,
            "typed_input_digest": self.typed_input_digest,
            "evaluated_at": self.evaluated_at,
            "grant_evidence": [item.to_dict() for item in self.grant_evidence],
            "grant_evidence_set_digest": self.grant_evidence_set_digest,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self._identity_dict(), "principal_digest": self.principal_digest}


@dataclass(frozen=True, slots=True)
class AgentRuntimePrincipalDeriver:
    """Trusted composition root for current, exact principal derivation."""

    activation_store: AutomationActivationStore
    invocation_source: AgentInvocationAuthoritySource
    grant_resolver: AgentRuntimeGrantResolver

    def derive(
        self,
        *,
        manifest: AgentRuntimeManifest,
        invocation_id: str,
    ) -> AgentRuntimePrincipal:
        current_manifest = _validated_manifest(manifest)
        invocation_id = _text(invocation_id, "invocation_id")
        manifest_content = current_manifest.manifest_input.to_dict()
        universe_id = str(manifest_content["universe_id"])
        agent_binding_id = str(manifest_content["agent_binding_id"])
        automation_id = agent_binding_automation_id(agent_binding_id)

        try:
            activation = self.activation_store.get(universe_id, automation_id)
        except Exception:
            raise _blocked("activation_source_error") from None
        if (
            type(activation) is not AutomationActivation
            or activation.state is not AutomationActivationState.ACTIVE
        ):
            raise _blocked("activation_not_current")
        expected_subject = ExecutionSubject(
            kind=ExecutionSubjectKind.AGENT_RUNTIME_MANIFEST,
            ref=current_manifest.manifest_id,
            digest=current_manifest.manifest_digest,
        )
        if activation.subject != expected_subject:
            raise _blocked("activation_subject_mismatch")
        assert activation.executor_class is not None
        assert activation.lease_id is not None

        try:
            evidence = self.invocation_source.resolve_current(invocation_id=invocation_id)
        except Exception:
            raise _blocked("invocation_source_error") from None
        if evidence is None:
            raise _blocked("invocation_not_current")
        invocation = _detached_invocation_evidence(evidence)
        if invocation is None or invocation.invocation_id != invocation_id:
            raise _blocked("invocation_evidence_invalid")
        identity_matches = (
            invocation.authorizing_subject_id == manifest_content["owner_user_id"],
            invocation.universe_id == universe_id,
            invocation.agent_binding_id == agent_binding_id,
            invocation.binding_revision == manifest_content["binding_revision"],
            invocation.execution_subject == expected_subject,
            invocation.activation_automation_id == automation_id,
        )
        if not all(identity_matches):
            raise _blocked("invocation_identity_mismatch")
        fence_matches = (
            invocation.activation_epoch == activation.epoch,
            invocation.executor_class is activation.executor_class,
            invocation.lease_id == activation.lease_id,
        )
        if not all(fence_matches):
            raise _blocked("invocation_fence_mismatch")

        try:
            grant_resolution = self.grant_resolver.resolve(current_manifest)
        except Exception:
            raise _blocked("grant_source_error") from None
        if not grant_resolution.ready:
            raise _blocked(
                "grant_not_current",
                grant_blockers=grant_resolution.blockers,
            )
        try:
            final_evidence = self.invocation_source.resolve_current(invocation_id=invocation_id)
        except Exception:
            raise _blocked("invocation_source_error") from None
        if final_evidence is None:
            raise _blocked("invocation_not_current")
        final_invocation = _detached_invocation_evidence(final_evidence)
        if final_invocation is None:
            raise _blocked("invocation_evidence_invalid")
        if final_invocation != invocation:
            raise _blocked("invocation_not_current")
        try:
            activation_is_current = self.activation_store.validate_claim(
                universe_id=universe_id,
                automation_id=automation_id,
                epoch=activation.epoch,
                executor_class=activation.executor_class,
                subject=expected_subject,
                lease_id=activation.lease_id,
            )
        except Exception:
            raise _blocked("activation_source_error") from None
        if not activation_is_current:
            raise _blocked("activation_not_current")
        grant_evidence = tuple(grant_resolution.evidence)
        return AgentRuntimePrincipal(
            authorizing_subject_id=invocation.authorizing_subject_id,
            universe_id=universe_id,
            agent_binding_id=agent_binding_id,
            binding_revision=invocation.binding_revision,
            execution_subject=expected_subject,
            activation_automation_id=automation_id,
            activation_epoch=activation.epoch,
            executor_class=activation.executor_class,
            lease_id=activation.lease_id,
            invocation_id=invocation.invocation_id,
            invocation_generation=invocation.invocation_generation,
            typed_input_digest=invocation.typed_input_digest,
            evaluated_at=grant_resolution.evaluated_at,
            grant_evidence=grant_evidence,
            grant_evidence_set_digest=grant_resolution.evidence_set_digest,
        )


def _validated_manifest(manifest: object) -> AgentRuntimeManifest:
    try:
        if type(manifest) is not AgentRuntimeManifest:
            raise TypeError
        manifest_input = AgentRuntimeManifestInput.from_dict(manifest.manifest_input.to_dict())
        detached = AgentRuntimeManifest(
            manifest_id=manifest.manifest_id,
            manifest_digest=manifest.manifest_digest,
            manifest_input=manifest_input,
            created_at=manifest.created_at,
        )
        if detached != manifest:
            raise ValueError
        return detached
    except Exception:
        raise _blocked("manifest_invalid") from None


def _detached_invocation_evidence(
    evidence: object,
) -> AgentInvocationAuthorityEvidence | None:
    try:
        if type(evidence) is not AgentInvocationAuthorityEvidence:
            return None
        return AgentInvocationAuthorityEvidence(
            invocation_id=evidence.invocation_id,
            invocation_generation=evidence.invocation_generation,
            authorizing_subject_id=evidence.authorizing_subject_id,
            universe_id=evidence.universe_id,
            agent_binding_id=evidence.agent_binding_id,
            binding_revision=evidence.binding_revision,
            execution_subject=evidence.execution_subject,
            activation_automation_id=evidence.activation_automation_id,
            activation_epoch=evidence.activation_epoch,
            executor_class=evidence.executor_class,
            lease_id=evidence.lease_id,
            typed_input_digest=evidence.typed_input_digest,
        )
    except (AttributeError, TypeError, ValueError):
        return None


def _blocked(
    code: str,
    *,
    grant_blockers: tuple[AgentRuntimeGrantBlocker, ...] = (),
) -> AgentRuntimePrincipalBlocked:
    messages = {
        "activation_not_current": "the exact agent activation is not current",
        "activation_source_error": "the activation authority could not be read",
        "activation_subject_mismatch": "the activation does not own this manifest",
        "grant_not_current": "one or more requested grants are not current",
        "grant_source_error": "the grant authority could not be read",
        "invocation_evidence_invalid": "the invocation authority returned invalid evidence",
        "invocation_fence_mismatch": "the invocation activation fence is stale",
        "invocation_identity_mismatch": "the invocation identity does not match the manifest",
        "invocation_not_current": "the invocation is not current",
        "invocation_source_error": "the invocation authority could not be read",
        "manifest_invalid": "the runtime manifest failed integrity validation",
    }
    return AgentRuntimePrincipalBlocked(
        code,
        messages[code],
        grant_blockers=grant_blockers,
    )


__all__ = [
    "AgentInvocationAuthorityEvidence",
    "AgentInvocationAuthoritySource",
    "AgentRuntimePrincipal",
    "AgentRuntimePrincipalBlocked",
    "AgentRuntimePrincipalDeriver",
]
