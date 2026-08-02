"""Dark, generic admission for requester-owned custom-agent invocations.

This module owns no public route and performs no provider call or external
effect.  It turns one authenticated, process-local draft into durable,
non-bearer provenance that later runtime stages can revalidate.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import weakref
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, ContextManager, Mapping, Protocol, runtime_checkable

from tinyassets.agent_runtime import AgentRuntimeManifest, AgentRuntimeManifestInput
from tinyassets.agent_runtime_grants import (
    AgentRuntimeGrantResolution,
    AgentRuntimeGrantResolver,
)
from tinyassets.auth.middleware import current_bearer_present, current_identity
from tinyassets.execution_subject import (
    ExecutionSubject,
    ExecutionSubjectKind,
    agent_binding_automation_id,
)
from tinyassets.provider_work_authority import (
    ProviderWorkBinding,
    ProviderWorkBindingResolver,
    ProviderWorkBindingRoot,
    ProviderWorkBindingSeed,
)
from tinyassets.storage.automation_activations import (
    AutomationActivation,
    AutomationActivationExecutor,
    AutomationActivationState,
    AutomationActivationStore,
)

AGENT_INVOCATION_OPERATION = "agent_invocation"
AGENT_INVOCATION_ROLE = "agent_runtime"
_MAX_INPUT_BYTES = 256 * 1024


def _text(value: object, name: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if len(value) > maximum:
        raise ValueError(f"{name} is too long")
    return value


def _integer(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
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


def _digest_value(value: object, name: str) -> str:
    text = _text(value, name)
    if len(text) != 71 or not text.startswith("sha256:"):
        raise ValueError(f"{name} must be a sha256 digest")
    try:
        int(text[7:], 16)
    except ValueError as exc:
        raise ValueError(f"{name} must be a sha256 digest") from exc
    return text


def _canonical_input(value: Mapping[str, object]) -> tuple[dict[str, Any], str]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("typed_input must be a non-empty object")
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        detached = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError("typed_input must be canonical JSON data") from exc
    if len(encoded) > _MAX_INPUT_BYTES:
        raise ValueError(f"typed_input exceeds {_MAX_INPUT_BYTES} bytes")
    return detached, f"sha256:{hashlib.sha256(encoded).hexdigest()}"


class AgentInvocationAdmissionOutcome(str, Enum):
    APPLIED = "applied"
    REPLAYED = "replayed"


class AgentInvocationState(str, Enum):
    ADMITTED = "admitted"


class AgentInvocationConflict(RuntimeError):
    """An idempotency key was reused for different canonical intent."""


class AgentInvocationAdmissionBlocked(PermissionError):
    """A typed, fail-closed admission boundary refused the request."""

    def __init__(self, code: str, message: str) -> None:
        self.code = _text(code, "code")
        super().__init__(_text(message, "message", maximum=512))


@dataclass(frozen=True, slots=True)
class AgentInvocationTarget:
    """Current server-resolved target; never accepted from request JSON."""

    manifest: AgentRuntimeManifest
    provider: str

    def __post_init__(self) -> None:
        _validated_manifest(self.manifest)
        _text(self.provider, "provider")


@runtime_checkable
class AgentInvocationTargetResolver(Protocol):
    def resolve_current(
        self,
        *,
        owner_user_id: str,
        agent_binding_id: str,
    ) -> AgentInvocationTarget | None: ...


@dataclass(frozen=True, slots=True)
class AgentInvocationExternalAuthoritySnapshot:
    """Exact non-secret generations held stable through admission commit."""

    owner_user_id: str
    universe_id: str
    agent_binding_id: str
    manifest_id: str
    manifest_digest: str
    grant_evidence_set_digest: str
    provider: str
    assignment_generation: int
    assignment_digest: str
    credential_reference_digest: str

    def __post_init__(self) -> None:
        for name in (
            "owner_user_id",
            "universe_id",
            "agent_binding_id",
            "manifest_id",
            "provider",
        ):
            _text(getattr(self, name), name)
        for name in (
            "manifest_digest",
            "grant_evidence_set_digest",
            "assignment_digest",
            "credential_reference_digest",
        ):
            _digest_value(getattr(self, name), name)
        _integer(self.assignment_generation, "assignment_generation", minimum=1)


@runtime_checkable
class AgentInvocationExternalAuthorityFenceSource(Protocol):
    """Linearize external authority with the admission commit.

    The trusted owner validates the exact snapshot on entry and prevents every
    covered manifest/grant/provider-assignment mutation until context exit.
    Implementations unable to provide that guarantee must yield ``False``.
    """

    def hold_current(
        self,
        snapshot: AgentInvocationExternalAuthoritySnapshot,
    ) -> ContextManager[bool]: ...


@dataclass(frozen=True, slots=True)
class AgentInvocationAdmissionRequest:
    """Caller intent only; it contains no actor, target, or provider authority."""

    typed_input: Mapping[str, object]
    idempotency_key: str
    max_tokens: int
    max_cost_microunits: int
    typed_input_digest: str = field(init=False)

    def __post_init__(self) -> None:
        detached, digest = _canonical_input(self.typed_input)
        object.__setattr__(self, "typed_input", detached)
        object.__setattr__(self, "typed_input_digest", digest)
        _text(self.idempotency_key, "idempotency_key", maximum=128)
        _integer(self.max_tokens, "max_tokens")
        _integer(self.max_cost_microunits, "max_cost_microunits")


@dataclass(frozen=True, slots=True)
class AgentInvocationCommand:
    schema_version: int
    command_id: str
    command_digest: str
    invocation_id: str
    invocation_generation: int
    authorizing_subject_id: str
    authorizing_principal_digest: str
    grant_evidence_set_digest: str
    grant_evaluated_at: float
    universe_id: str
    agent_binding_id: str
    binding_revision: int
    execution_subject: ExecutionSubject
    activation_automation_id: str
    activation_epoch: int
    executor_class: AutomationActivationExecutor
    lease_id: str
    typed_input_digest: str
    provider_work_binding_id: str
    provider_work_binding_generation: int
    provider_work_binding_digest: str
    provider: str
    max_tokens: int
    max_cost_microunits: int
    idempotency_key_digest: str
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported command schema_version")
        for name in (
            "command_id",
            "invocation_id",
            "authorizing_subject_id",
            "universe_id",
            "agent_binding_id",
            "activation_automation_id",
            "lease_id",
            "provider_work_binding_id",
            "provider",
            "created_at",
        ):
            _text(getattr(self, name), name)
        if not self.command_id.startswith("agent_invocation_command_"):
            raise ValueError("command_id is invalid")
        if not self.invocation_id.startswith("agent_invocation_"):
            raise ValueError("invocation_id is invalid")
        for name in (
            "command_digest",
            "authorizing_principal_digest",
            "grant_evidence_set_digest",
            "typed_input_digest",
            "provider_work_binding_digest",
            "idempotency_key_digest",
        ):
            _digest_value(getattr(self, name), name)
        _integer(self.invocation_generation, "invocation_generation", minimum=1)
        _integer(self.binding_revision, "binding_revision", minimum=1)
        _integer(self.activation_epoch, "activation_epoch", minimum=1)
        _integer(
            self.provider_work_binding_generation,
            "provider_work_binding_generation",
            minimum=1,
        )
        _integer(self.max_tokens, "max_tokens")
        _integer(self.max_cost_microunits, "max_cost_microunits")
        if not isinstance(self.grant_evaluated_at, (int, float)) or isinstance(
            self.grant_evaluated_at, bool
        ):
            raise ValueError("grant_evaluated_at must be a timestamp")
        if (
            not isinstance(self.execution_subject, ExecutionSubject)
            or self.execution_subject.kind is not ExecutionSubjectKind.AGENT_RUNTIME_MANIFEST
        ):
            raise ValueError("execution_subject must be an agent runtime manifest")
        if not isinstance(self.executor_class, AutomationActivationExecutor):
            raise ValueError("executor_class must be typed")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "command_id": self.command_id,
            "command_digest": self.command_digest,
            "invocation_id": self.invocation_id,
            "invocation_generation": self.invocation_generation,
            "authorizing_subject_id": self.authorizing_subject_id,
            "authorizing_principal_digest": self.authorizing_principal_digest,
            "grant_evidence_set_digest": self.grant_evidence_set_digest,
            "grant_evaluated_at": self.grant_evaluated_at,
            "universe_id": self.universe_id,
            "agent_binding_id": self.agent_binding_id,
            "binding_revision": self.binding_revision,
            "execution_subject": self.execution_subject.to_dict(),
            "activation_automation_id": self.activation_automation_id,
            "activation_epoch": self.activation_epoch,
            "executor_class": self.executor_class.value,
            "lease_id": self.lease_id,
            "typed_input_digest": self.typed_input_digest,
            "provider_work_binding_id": self.provider_work_binding_id,
            "provider_work_binding_generation": self.provider_work_binding_generation,
            "provider_work_binding_digest": self.provider_work_binding_digest,
            "provider": self.provider,
            "max_tokens": self.max_tokens,
            "max_cost_microunits": self.max_cost_microunits,
            "idempotency_key_digest": self.idempotency_key_digest,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AgentInvocationCommand:
        values = dict(payload)
        values["execution_subject"] = ExecutionSubject.from_dict(
            values["execution_subject"]  # type: ignore[arg-type]
        )
        values["executor_class"] = AutomationActivationExecutor(values["executor_class"])
        return cls(**values)  # type: ignore[arg-type]

    def expected_digest(self) -> str:
        payload = self.to_dict()
        del payload["command_digest"]
        return _digest(payload)


@dataclass(frozen=True, slots=True)
class AgentInvocation:
    schema_version: int
    invocation_id: str
    invocation_digest: str
    generation: int
    state: AgentInvocationState
    command_id: str
    command_digest: str
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported invocation schema_version")
        for name in ("invocation_id", "command_id", "created_at"):
            _text(getattr(self, name), name)
        if not self.invocation_id.startswith("agent_invocation_"):
            raise ValueError("invocation_id is invalid")
        if not self.command_id.startswith("agent_invocation_command_"):
            raise ValueError("command_id is invalid")
        _digest_value(self.invocation_digest, "invocation_digest")
        _digest_value(self.command_digest, "command_digest")
        _integer(self.generation, "generation", minimum=1)
        if not isinstance(self.state, AgentInvocationState):
            raise ValueError("state must be typed")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "invocation_id": self.invocation_id,
            "invocation_digest": self.invocation_digest,
            "generation": self.generation,
            "state": self.state.value,
            "command_id": self.command_id,
            "command_digest": self.command_digest,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AgentInvocation:
        values = dict(payload)
        values["state"] = AgentInvocationState(values["state"])
        return cls(**values)  # type: ignore[arg-type]

    def expected_digest(self) -> str:
        payload = self.to_dict()
        del payload["invocation_digest"]
        return _digest(payload)


@dataclass(frozen=True, slots=True)
class AgentInvocationAdmissionResult:
    outcome: AgentInvocationAdmissionOutcome
    binding: ProviderWorkBinding
    command: AgentInvocationCommand
    invocation: AgentInvocation

    def to_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "binding": self.binding.to_dict(),
            "command": self.command.to_dict(),
            "invocation": self.invocation.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class _DraftPayload:
    service_id: str
    owner_user_id: str
    agent_binding_id: str
    target: AgentInvocationTarget
    activation: AutomationActivation
    grants: AgentRuntimeGrantResolution
    provider_seed: ProviderWorkBindingSeed


class LiveProviderWorkBindingDraft:
    """One-use in-process proof that authenticated intent is still live."""

    __slots__ = ("_draft_id", "_seal", "__weakref__")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("LiveProviderWorkBindingDraft must be request-boundary minted")

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("LiveProviderWorkBindingDraft is immutable")

    def __reduce__(self):
        raise TypeError("LiveProviderWorkBindingDraft is non-serializable")


@dataclass(frozen=True, slots=True)
class _StoreAdmissionPayload:
    owner_user_id: str
    manifest: AgentRuntimeManifest
    activation: AutomationActivation
    grants: AgentRuntimeGrantResolution
    provider_seed: ProviderWorkBindingSeed
    typed_input_digest: str
    idempotency_key: str
    max_tokens: int
    max_cost_microunits: int
    hold_external_authority: Callable[[], ContextManager[bool]] = field(
        repr=False,
        compare=False,
    )


class _AgentInvocationStoreGrant:
    __slots__ = ("_grant_id", "_seal", "__weakref__")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("agent invocation store grants are admission-issued")


_CAPABILITY_KEY = secrets.token_bytes(32)
_CAPABILITY_LOCK = threading.Lock()
_DRAFTS: dict[
    str,
    tuple[weakref.ReferenceType[LiveProviderWorkBindingDraft], _DraftPayload],
] = {}
_STORE_GRANTS: dict[
    str,
    tuple[weakref.ReferenceType[_AgentInvocationStoreGrant], _StoreAdmissionPayload],
] = {}


def _seal(kind: str, identifier: str) -> bytes:
    return hmac.digest(_CAPABILITY_KEY, f"{kind}\0{identifier}".encode(), "sha256")


def _discard_draft(identifier: str) -> None:
    with _CAPABILITY_LOCK:
        _DRAFTS.pop(identifier, None)


def _discard_store_grant(identifier: str) -> None:
    with _CAPABILITY_LOCK:
        _STORE_GRANTS.pop(identifier, None)


def _mint_draft(payload: _DraftPayload) -> LiveProviderWorkBindingDraft:
    identifier = secrets.token_hex(32)
    draft = object.__new__(LiveProviderWorkBindingDraft)
    object.__setattr__(draft, "_draft_id", identifier)
    object.__setattr__(draft, "_seal", _seal("draft", identifier))
    with _CAPABILITY_LOCK:
        _DRAFTS[identifier] = (weakref.ref(draft), payload)
    weakref.finalize(draft, _discard_draft, identifier)
    return draft


def _consume_draft(
    draft: LiveProviderWorkBindingDraft,
    *,
    service_id: str,
) -> _DraftPayload:
    try:
        exact = type(draft) is LiveProviderWorkBindingDraft and hmac.compare_digest(
            draft._seal, _seal("draft", draft._draft_id)
        )
    except (AttributeError, TypeError):
        exact = False
    if not exact:
        raise AgentInvocationAdmissionBlocked(
            "draft_invalid",
            "the live provider binding draft is not server-issued",
        )
    with _CAPABILITY_LOCK:
        entry = _DRAFTS.get(draft._draft_id)
        if entry is not None and entry[0]() is draft and entry[1].service_id == service_id:
            _DRAFTS.pop(draft._draft_id, None)
        else:
            entry = None
    if entry is None:
        raise AgentInvocationAdmissionBlocked(
            "draft_consumed",
            "the live provider binding draft was already consumed",
        )
    payload = entry[1]
    return payload


def _issue_store_grant(payload: _StoreAdmissionPayload) -> _AgentInvocationStoreGrant:
    identifier = secrets.token_hex(32)
    grant = object.__new__(_AgentInvocationStoreGrant)
    object.__setattr__(grant, "_grant_id", identifier)
    object.__setattr__(grant, "_seal", _seal("store", identifier))
    with _CAPABILITY_LOCK:
        _STORE_GRANTS[identifier] = (weakref.ref(grant), payload)
    weakref.finalize(grant, _discard_store_grant, identifier)
    return grant


def _consume_store_grant(grant: _AgentInvocationStoreGrant) -> _StoreAdmissionPayload:
    try:
        exact = type(grant) is _AgentInvocationStoreGrant and hmac.compare_digest(
            grant._seal, _seal("store", grant._grant_id)
        )
    except (AttributeError, TypeError):
        exact = False
    if not exact:
        raise AgentInvocationAdmissionBlocked(
            "store_grant_invalid",
            "agent invocation persistence requires an admission-issued grant",
        )
    with _CAPABILITY_LOCK:
        entry = _STORE_GRANTS.get(grant._grant_id)
        if entry is not None and entry[0]() is grant:
            _STORE_GRANTS.pop(grant._grant_id, None)
        else:
            entry = None
    if entry is None:
        raise AgentInvocationAdmissionBlocked(
            "store_grant_consumed",
            "agent invocation persistence grant was already consumed",
        )
    return entry[1]


def _validated_manifest(manifest: object) -> AgentRuntimeManifest:
    try:
        if type(manifest) is not AgentRuntimeManifest:
            raise TypeError
        detached_input = AgentRuntimeManifestInput.from_dict(manifest.manifest_input.to_dict())
        detached = AgentRuntimeManifest(
            manifest_id=manifest.manifest_id,
            manifest_digest=manifest.manifest_digest,
            manifest_input=detached_input,
            created_at=manifest.created_at,
        )
        if detached != manifest:
            raise ValueError
        return detached
    except Exception:
        raise AgentInvocationAdmissionBlocked(
            "manifest_invalid",
            "the current agent manifest is invalid",
        ) from None


def _target_parts(target: AgentInvocationTarget, *, owner: str, binding: str) -> dict[str, Any]:
    if type(target) is not AgentInvocationTarget:
        raise AgentInvocationAdmissionBlocked(
            "target_unavailable",
            "the current agent target is unavailable",
        )
    manifest = _validated_manifest(target.manifest)
    content = manifest.manifest_input.to_dict()
    exact = (
        content["owner_user_id"] == owner,
        content["agent_binding_id"] == binding,
        bool(target.provider.strip()),
    )
    if not all(exact):
        raise AgentInvocationAdmissionBlocked(
            "target_mismatch",
            "the current agent target does not match authenticated intent",
        )
    return content


def _same_grants(left: AgentRuntimeGrantResolution, right: AgentRuntimeGrantResolution) -> bool:
    return (
        left.manifest_id == right.manifest_id
        and left.manifest_digest == right.manifest_digest
        and left.evidence == right.evidence
        and left.blockers == right.blockers
        and left.evidence_set_digest == right.evidence_set_digest
    )


class AgentInvocationAdmissionService:
    """Trusted composition root for live-boundary invocation admission."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        target_resolver: AgentInvocationTargetResolver,
        grant_resolver: AgentRuntimeGrantResolver,
        provider_binding_resolver: ProviderWorkBindingResolver,
        external_authority_fence_source: AgentInvocationExternalAuthorityFenceSource,
        clock: Callable[[], datetime] | None = None,
        busy_timeout_ms: int = 30_000,
    ) -> None:
        if not isinstance(target_resolver, AgentInvocationTargetResolver):
            raise ValueError("target_resolver must be server-owned")
        if not isinstance(grant_resolver, AgentRuntimeGrantResolver):
            raise ValueError("grant_resolver must be server-owned")
        if not isinstance(provider_binding_resolver, ProviderWorkBindingResolver):
            raise ValueError("provider_binding_resolver must be server-owned")
        if not isinstance(
            external_authority_fence_source,
            AgentInvocationExternalAuthorityFenceSource,
        ):
            raise ValueError("external_authority_fence_source must be server-owned")
        from tinyassets.storage.agent_runtime_invocation import (
            SQLiteAgentRuntimeInvocationStore,
        )

        self._service_id = secrets.token_hex(32)
        self._target_resolver = target_resolver
        self._grant_resolver = grant_resolver
        self._provider_binding_resolver = provider_binding_resolver
        self._external_authority_fence_source = external_authority_fence_source
        self._activation_store = AutomationActivationStore(
            base_path,
            busy_timeout_ms=busy_timeout_ms,
            clock=clock,
        )
        self.store = SQLiteAgentRuntimeInvocationStore(
            base_path,
            busy_timeout_ms=busy_timeout_ms,
            clock=clock,
        )

    def _resolve_external(
        self,
        *,
        owner: str,
        binding: str,
    ) -> tuple[
        AgentInvocationTarget,
        AgentRuntimeGrantResolution,
        ProviderWorkBindingSeed,
    ]:
        target = self._target_resolver.resolve_current(
            owner_user_id=owner,
            agent_binding_id=binding,
        )
        content = _target_parts(target, owner=owner, binding=binding)  # type: ignore[arg-type]
        assert target is not None
        grants = self._grant_resolver.resolve(target.manifest)
        if not grants.ready:
            raise AgentInvocationAdmissionBlocked(
                "grant_not_current",
                "one or more requested grants are not current",
            )
        root = ProviderWorkBindingRoot(
            owner_user_id=owner,
            universe_id=str(content["universe_id"]),
            provider=target.provider,
        )
        provider_seed = self._provider_binding_resolver.resolve(root)
        if type(provider_seed) is not ProviderWorkBindingSeed:
            raise AgentInvocationAdmissionBlocked(
                "provider_assignment_unavailable",
                "the requester-owned provider assignment is unavailable",
            )
        exact_seed = (
            provider_seed.owner_user_id == root.owner_user_id,
            provider_seed.universe_id == root.universe_id,
            provider_seed.provider == root.provider,
            AGENT_INVOCATION_OPERATION in provider_seed.allowed_operations,
            AGENT_INVOCATION_ROLE in provider_seed.allowed_roles,
        )
        if not all(exact_seed):
            raise AgentInvocationAdmissionBlocked(
                "provider_assignment_mismatch",
                "the requester-owned provider assignment does not admit agent invocation",
            )
        return target, grants, provider_seed

    def _resolve(self, *, owner: str, binding: str) -> _DraftPayload:
        target, grants, provider_seed = self._resolve_external(
            owner=owner,
            binding=binding,
        )
        content = target.manifest.manifest_input.to_dict()
        automation_id = agent_binding_automation_id(binding)
        activation = self._activation_store.get(str(content["universe_id"]), automation_id)
        expected_subject = ExecutionSubject(
            kind=ExecutionSubjectKind.AGENT_RUNTIME_MANIFEST,
            ref=target.manifest.manifest_id,
            digest=target.manifest.manifest_digest,
        )
        if (
            type(activation) is not AutomationActivation
            or activation.state is not AutomationActivationState.ACTIVE
            or activation.subject != expected_subject
            or activation.executor_class is not AutomationActivationExecutor.CLOUD
        ):
            raise AgentInvocationAdmissionBlocked(
                "activation_not_current",
                "the exact cloud agent activation is not current",
            )
        return _DraftPayload(
            service_id=self._service_id,
            owner_user_id=owner,
            agent_binding_id=binding,
            target=target,
            activation=activation,
            grants=grants,
            provider_seed=provider_seed,
        )

    def capture_live_provider_binding_draft(
        self,
        *,
        agent_binding_id: str,
    ) -> LiveProviderWorkBindingDraft:
        binding = _text(agent_binding_id, "agent_binding_id")
        identity = current_identity()
        owner = (getattr(identity, "user_id", "") or "").strip()
        if not current_bearer_present() or not owner or owner == "anonymous":
            raise AgentInvocationAdmissionBlocked(
                "authentication_required",
                "a live authenticated request is required",
            )
        return _mint_draft(self._resolve(owner=owner, binding=binding))

    def admit(
        self,
        draft: LiveProviderWorkBindingDraft,
        request: AgentInvocationAdmissionRequest,
    ) -> AgentInvocationAdmissionResult:
        if type(request) is not AgentInvocationAdmissionRequest:
            raise ValueError("request must be an AgentInvocationAdmissionRequest")
        payload = _consume_draft(draft, service_id=self._service_id)
        identity = current_identity()
        current_owner = (getattr(identity, "user_id", "") or "").strip()
        if not current_bearer_present() or current_owner != payload.owner_user_id:
            raise AgentInvocationAdmissionBlocked(
                "live_request_ended",
                "the live request boundary ended before admission",
            )
        current = self._resolve(
            owner=payload.owner_user_id,
            binding=payload.agent_binding_id,
        )
        unchanged = (
            current.target == payload.target,
            current.activation == payload.activation,
            _same_grants(current.grants, payload.grants),
            current.provider_seed == payload.provider_seed,
        )
        if not all(unchanged):
            raise AgentInvocationAdmissionBlocked(
                "authority_changed",
                "agent invocation authority changed during the live request",
            )
        manifest_budgets = current.target.manifest.manifest_input.to_dict()["budgets"]
        assert isinstance(manifest_budgets, dict)
        allowed = (
            request.max_tokens <= int(manifest_budgets.get("max_tokens", 0)),
            request.max_cost_microunits <= int(manifest_budgets.get("max_cost_microunits", 0)),
            request.max_tokens <= current.provider_seed.max_tokens,
            request.max_cost_microunits <= current.provider_seed.max_cost_microunits,
        )
        if not all(allowed):
            raise AgentInvocationAdmissionBlocked(
                "budget_exceeded",
                "the requested invocation budget exceeds a current budget envelope",
            )
        grant = _issue_store_grant(
            _StoreAdmissionPayload(
                owner_user_id=payload.owner_user_id,
                manifest=current.target.manifest,
                activation=current.activation,
                grants=current.grants,
                provider_seed=current.provider_seed,
                typed_input_digest=request.typed_input_digest,
                idempotency_key=request.idempotency_key,
                max_tokens=request.max_tokens,
                max_cost_microunits=request.max_cost_microunits,
                hold_external_authority=lambda: self._external_authority_fence_source.hold_current(
                    _external_authority_snapshot(current)
                ),
            )
        )
        return self.store.admit(grant)


def _external_authority_snapshot(
    payload: _DraftPayload,
) -> AgentInvocationExternalAuthoritySnapshot:
    content = payload.target.manifest.manifest_input.to_dict()
    seed = payload.provider_seed
    return AgentInvocationExternalAuthoritySnapshot(
        owner_user_id=payload.owner_user_id,
        universe_id=str(content["universe_id"]),
        agent_binding_id=payload.agent_binding_id,
        manifest_id=payload.target.manifest.manifest_id,
        manifest_digest=payload.target.manifest.manifest_digest,
        grant_evidence_set_digest=payload.grants.evidence_set_digest,
        provider=seed.provider,
        assignment_generation=seed.assignment_generation,
        assignment_digest=seed.assignment_digest,
        credential_reference_digest=seed.credential_reference_digest,
    )


__all__ = [
    "AGENT_INVOCATION_OPERATION",
    "AGENT_INVOCATION_ROLE",
    "AgentInvocation",
    "AgentInvocationAdmissionBlocked",
    "AgentInvocationAdmissionOutcome",
    "AgentInvocationAdmissionRequest",
    "AgentInvocationAdmissionResult",
    "AgentInvocationAdmissionService",
    "AgentInvocationCommand",
    "AgentInvocationConflict",
    "AgentInvocationExternalAuthorityFenceSource",
    "AgentInvocationExternalAuthoritySnapshot",
    "AgentInvocationState",
    "AgentInvocationTarget",
    "AgentInvocationTargetResolver",
    "LiveProviderWorkBindingDraft",
]
