"""Atomic handoff from an admitted custom-agent invocation to provider work."""

from __future__ import annotations

import json
import os
import secrets
import sqlite3
import threading
import weakref
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Literal, Mapping

from tinyassets.agent_invocation_authority import AgentInvocationEventState
from tinyassets.agent_runtime_grants import AgentRuntimeGrantResolver
from tinyassets.agent_runtime_health import (
    AgentRuntimeHealthState,
    AgentRuntimeNoProgressAlarm,
    AgentRuntimeUsefulProgressHealth,
    agent_runtime_alarm_id,
)
from tinyassets.agent_runtime_invocation import (
    AGENT_INVOCATION_OPERATION,
    AGENT_INVOCATION_ROLE,
    canonical_agent_invocation_input,
)
from tinyassets.agent_runtime_principal import AgentRuntimePrincipal
from tinyassets.agent_runtime_provider_outcome import (
    MAX_AGENT_PROVIDER_OUTPUT_BYTES,
    AgentInvocationProviderOutcome,
    AgentProviderOutcomeState,
)
from tinyassets.cloud_automation_continuation import (
    AgentInvocationCloudContinuation,
    CloudContinuationState,
    CloudContinuationWriteResult,
)
from tinyassets.config import load_universe_config
from tinyassets.provider_work_authority import (
    ProviderInvocationCarrier,
    ProviderInvocationReservation,
    ProviderInvocationReservationState,
    ProviderInvocationReservationWriteResult,
    ProviderUniverseWorkAuthority,
    ProviderUniverseWorkRoot,
    ProviderWorkBindingRoot,
    ProviderWorkBindingSeed,
    ProviderWorkBindingState,
    ProviderWorkExecutionClaimWriteResult,
    ProviderWorkReceiptWriteResult,
    ProviderWorkTransactionalBindingResolver,
    _mint_provider_invocation_carrier,
)
from tinyassets.providers.base import ModelConfig, UniverseContext
from tinyassets.providers.router import ProviderRouter
from tinyassets.storage.agent_runtime import AgentRuntimeManifestStore
from tinyassets.storage.agent_runtime_health import SQLiteAgentRuntimeHealthStore
from tinyassets.storage.agent_runtime_invocation import (
    SQLiteAgentInvocationExternalAuthorityFenceSource,
    SQLiteAgentRuntimeInvocationStore,
)
from tinyassets.storage.agent_runtime_provider_outcome import (
    SQLiteAgentRuntimeProviderOutcomeStore,
)
from tinyassets.storage.automation_activations import AutomationActivationStore
from tinyassets.storage.automation_activations import _record as _activation_record
from tinyassets.storage.cloud_automation_continuation import (
    SQLiteCloudAutomationContinuationStore,
    _agent_record,
)
from tinyassets.storage.provider_work_authority import (
    SQLiteProviderWorkAuthorityStore,
    _claim_record,
    _receipt_record,
    _reservation_record,
)


class AgentRuntimeProviderExecutionBlocked(PermissionError):
    """Raised when admitted work no longer has exact current authority."""


class _AgentProviderReceiptStoreGrant:
    """One-shot, process-local proof that the agent authority fence passed."""

    __slots__ = ("_grant_id", "_issuer_pid", "__weakref__")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("agent provider receipt grants are service-issued")

    def __setattr__(self, _name: str, _value: object) -> None:
        raise AttributeError("agent provider receipt grants are immutable")

    def __reduce__(self):
        raise TypeError("agent provider receipt grants are non-serializable")

    def _resolve(self, *, consume: bool) -> ProviderUniverseWorkAuthority:
        if type(self) is not _AgentProviderReceiptStoreGrant:
            raise PermissionError("agent provider receipt grant is not service-issued")
        current_pid = os.getpid()
        if self._issuer_pid != current_pid:
            raise PermissionError("agent provider receipt grant belongs to another process")
        with _RECEIPT_GRANT_LOCK:
            entry = _ACTIVE_RECEIPT_GRANTS.get(self._grant_id)
            if entry is None or entry[0]() is not self or entry[2] != current_pid:
                raise PermissionError("agent provider receipt grant is invalid or consumed")
            if consume:
                del _ACTIVE_RECEIPT_GRANTS[self._grant_id]
        return entry[1]

    def _peek(self) -> ProviderUniverseWorkAuthority:
        return self._resolve(consume=False)

    def _consume(self) -> ProviderUniverseWorkAuthority:
        return self._resolve(consume=True)

    def _discard(self) -> None:
        if type(self) is not _AgentProviderReceiptStoreGrant:
            raise PermissionError("agent provider receipt grant is not service-issued")
        _discard_receipt_grant(self._grant_id, self._issuer_pid)


_RECEIPT_GRANT_LOCK = threading.Lock()
_ACTIVE_RECEIPT_GRANTS: dict[
    str,
    tuple[
        weakref.ReferenceType[_AgentProviderReceiptStoreGrant],
        ProviderUniverseWorkAuthority,
        int,
    ],
] = {}


def _reset_receipt_grants_after_fork() -> None:
    global _RECEIPT_GRANT_LOCK
    global _ACTIVE_RECEIPT_GRANTS
    _RECEIPT_GRANT_LOCK = threading.Lock()
    _ACTIVE_RECEIPT_GRANTS = {}


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_receipt_grants_after_fork)


def _discard_receipt_grant(grant_id: str, issuer_pid: int) -> None:
    if issuer_pid != os.getpid():
        return
    with _RECEIPT_GRANT_LOCK:
        _ACTIVE_RECEIPT_GRANTS.pop(grant_id, None)


class AgentRuntimeProviderExecutionService:
    """Mint one replay-safe provider receipt under one SQLite authority fence."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        grant_resolver: AgentRuntimeGrantResolver,
        provider_binding_resolver: ProviderWorkTransactionalBindingResolver,
        clock: Callable[[], datetime] | None = None,
        busy_timeout_ms: int = 30_000,
    ) -> None:
        if not isinstance(grant_resolver, AgentRuntimeGrantResolver):
            raise ValueError("grant_resolver must be server-owned")
        if not isinstance(
            provider_binding_resolver,
            ProviderWorkTransactionalBindingResolver,
        ):
            raise ValueError("provider_binding_resolver must be transactional")
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.grant_resolver = grant_resolver
        self.provider_binding_resolver = provider_binding_resolver
        self.provider_store = SQLiteProviderWorkAuthorityStore(
            base_path,
            busy_timeout_ms=busy_timeout_ms,
            clock=self._clock,
        )
        external_authority_fence_source = SQLiteAgentInvocationExternalAuthorityFenceSource(
            base_path,
            grant_resolver=grant_resolver,
            clock=self._clock,
        )
        self.invocation_store = SQLiteAgentRuntimeInvocationStore(
            base_path,
            external_authority_fence_source=external_authority_fence_source,
            busy_timeout_ms=busy_timeout_ms,
            clock=self._clock,
        )
        self.continuation_store = SQLiteCloudAutomationContinuationStore(
            base_path,
            busy_timeout_ms=busy_timeout_ms,
            clock=self._clock,
        )
        with self.continuation_store.connection():
            pass
        with self.invocation_store.connection() as conn:
            SQLiteAgentRuntimeProviderOutcomeStore.ensure_schema(conn)
            SQLiteAgentRuntimeHealthStore.ensure_schema(conn)

    def issue_receipt(self, invocation_id: str) -> ProviderWorkReceiptWriteResult:
        result = self._transition(invocation_id, transition="receipt")
        assert isinstance(result, ProviderWorkReceiptWriteResult)
        return result

    def claim(self, invocation_id: str) -> ProviderWorkExecutionClaimWriteResult:
        result = self._transition(invocation_id, transition="claim")
        assert isinstance(result, ProviderWorkExecutionClaimWriteResult)
        return result

    def reserve(self, invocation_id: str) -> ProviderInvocationReservationWriteResult:
        result = self._transition(invocation_id, transition="reserve")
        assert isinstance(result, ProviderInvocationReservationWriteResult)
        return result

    def get_continuation(
        self,
        invocation_id: str,
    ) -> AgentInvocationCloudContinuation | None:
        return self.continuation_store.get_agent(invocation_id)

    def get_provider_outcome(
        self,
        invocation_id: str,
    ) -> AgentInvocationProviderOutcome | None:
        with self.invocation_store.connection() as conn:
            SQLiteAgentRuntimeProviderOutcomeStore.ensure_schema(conn)
            return SQLiteAgentRuntimeProviderOutcomeStore.get_in_transaction(
                conn,
                invocation_id=invocation_id,
            )

    def project_useful_progress(
        self,
        invocation_id: str,
        *,
        no_progress_after_seconds: int,
    ) -> AgentRuntimeUsefulProgressHealth:
        """Project health only from canonical useful transitions, never heartbeats."""

        if (
            isinstance(no_progress_after_seconds, bool)
            or not isinstance(no_progress_after_seconds, int)
            or no_progress_after_seconds < 1
        ):
            raise ValueError("no_progress_after_seconds must be an integer >= 1")
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise AgentRuntimeProviderExecutionBlocked("server clock is unavailable")
        now = now.astimezone(timezone.utc)
        observed_at = now.isoformat(timespec="microseconds").replace("+00:00", "Z")
        with self.invocation_store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                aggregate = self.invocation_store.get_in_transaction(
                    conn,
                    invocation_id=invocation_id,
                )
                if aggregate is None:
                    raise AgentRuntimeProviderExecutionBlocked("agent invocation is not current")
                command, invocation, event = aggregate
                if event.state is not AgentInvocationEventState.ADMITTED:
                    raise AgentRuntimeProviderExecutionBlocked("agent invocation is not admitted")
                manifest = AgentRuntimeManifestStore.resolve_current_in_transaction(
                    conn,
                    owner_user_id=command.authorizing_subject_id,
                    manifest_id=command.execution_subject.ref,
                    manifest_digest=command.execution_subject.digest,
                )
                if manifest is None:
                    raise AgentRuntimeProviderExecutionBlocked("agent manifest is not current")
                milestone = "invocation_admitted"
                record_digest = invocation.root_digest
                progress_at = invocation.created_at
                continuation_row = conn.execute(
                    "SELECT * FROM cloud_execution_continuations WHERE work_item_id = ?",
                    (invocation_id,),
                ).fetchone()
                continuation = (
                    _agent_record(continuation_row) if continuation_row is not None else None
                )
                outcome = SQLiteAgentRuntimeProviderOutcomeStore.get_in_transaction(
                    conn,
                    invocation_id=invocation_id,
                )
                if continuation is not None:
                    if (
                        continuation.command_id != command.command_id
                        or continuation.command_digest != command.command_digest
                        or continuation.invocation_digest != invocation.root_digest
                        or continuation.invocation_generation != event.generation
                        or continuation.universe_id != command.universe_id
                        or continuation.automation_id != command.activation_automation_id
                        or continuation.activation_epoch != command.activation_epoch
                        or continuation.activation_lease_id != command.lease_id
                        or continuation.execution_subject != command.execution_subject
                        or continuation.provider_binding_id != command.provider_work_binding_id
                        or continuation.provider_binding_generation
                        != command.provider_work_binding_generation
                        or continuation.provider_binding_digest
                        != command.provider_work_binding_digest
                        or continuation.typed_input_digest != command.typed_input_digest
                        or continuation.max_tokens != command.budget.max_tokens
                        or continuation.max_cost_microunits != command.budget.max_cost_microunits
                    ):
                        raise AgentRuntimeProviderExecutionBlocked(
                            "agent health continuation lineage is not exact"
                        )
                    receipt_row = conn.execute(
                        "SELECT * FROM provider_work_receipts WHERE receipt_id = ?",
                        (continuation.receipt_id,),
                    ).fetchone()
                    claim_row = conn.execute(
                        "SELECT * FROM provider_work_execution_claims WHERE claim_id = ?",
                        (continuation.claim_id,),
                    ).fetchone()
                    reservation_row = conn.execute(
                        "SELECT * FROM provider_invocation_reservations WHERE reservation_id = ?",
                        (continuation.reservation_id,),
                    ).fetchone()
                    if receipt_row is None or claim_row is None or reservation_row is None:
                        raise AgentRuntimeProviderExecutionBlocked(
                            "agent health continuation authority is incomplete"
                        )
                    receipt = _receipt_record(receipt_row)
                    claim = _claim_record(claim_row)
                    reservation = _reservation_record(reservation_row)
                    lineage_exact = (
                        receipt.work_item_kind == "agent_invocation",
                        receipt.work_item_id == invocation.invocation_id,
                        receipt.binding_id == continuation.provider_binding_id,
                        receipt.binding_generation == continuation.provider_binding_generation,
                        receipt.binding_digest == continuation.provider_binding_digest,
                        receipt.agent_invocation_command_id == command.command_id,
                        receipt.agent_invocation_command_digest == command.command_digest,
                        receipt.agent_invocation_generation == continuation.invocation_generation,
                        receipt.receipt_id == continuation.receipt_id,
                        receipt.receipt_digest == continuation.receipt_digest,
                        receipt.actor_id == continuation.activation_lease_id,
                        receipt.universe_id == continuation.universe_id,
                        receipt.execution_subject == continuation.execution_subject,
                        receipt.max_tokens >= continuation.max_tokens,
                        receipt.max_cost_microunits >= continuation.max_cost_microunits,
                        claim.receipt_id == receipt.receipt_id,
                        claim.receipt_digest == receipt.receipt_digest,
                        claim.claim_id == continuation.claim_id,
                        claim.generation == continuation.claim_generation,
                        claim.claim_digest == continuation.claim_digest,
                        reservation.receipt_id == receipt.receipt_id,
                        reservation.receipt_digest == receipt.receipt_digest,
                        reservation.claim_id == claim.claim_id,
                        reservation.claim_generation == claim.generation,
                        reservation.claim_digest == claim.claim_digest,
                        reservation.reservation_id == continuation.reservation_id,
                        (
                            reservation.reservation_digest == continuation.reservation_digest
                            if outcome is None
                            else outcome.reservation_id == reservation.reservation_id
                            and outcome.terminal_reservation_digest
                            == reservation.reservation_digest
                            and outcome.continuation_id == continuation.continuation_id
                            and outcome.continuation_digest == continuation.continuation_digest
                        ),
                        reservation.invocation_key == invocation.invocation_id,
                        reservation.max_tokens == continuation.max_tokens,
                        reservation.max_cost_microunits == continuation.max_cost_microunits,
                    )
                    if not all(lineage_exact):
                        raise AgentRuntimeProviderExecutionBlocked(
                            "agent health continuation lineage is not exact"
                        )
                    milestone = "continuation_prepared"
                    record_digest = continuation.continuation_digest
                    progress_at = continuation.created_at
                if outcome is not None:
                    if continuation is None or (
                        outcome.continuation_id != continuation.continuation_id
                        or outcome.continuation_digest != continuation.continuation_digest
                    ):
                        raise AgentRuntimeProviderExecutionBlocked(
                            "agent health outcome lineage is not exact"
                        )
                    milestone = "provider_outcome_recorded"
                    record_digest = outcome.outcome_digest
                    progress_at = outcome.created_at
                try:
                    self._validated_authority(
                        conn,
                        invocation_id=invocation_id,
                        evaluated_at=now.timestamp(),
                    )
                except AgentRuntimeProviderExecutionBlocked:
                    authority_current = False
                else:
                    authority_current = True
                progress_time = datetime.fromisoformat(progress_at.removesuffix("Z") + "+00:00")
                if progress_time > now:
                    raise AgentRuntimeProviderExecutionBlocked(
                        "agent useful progress timestamp is in the future"
                    )
                no_progress_seconds = max(
                    0,
                    int((now - progress_time).total_seconds()),
                )
                if outcome is not None:
                    state = AgentRuntimeHealthState.TERMINAL
                elif not authority_current:
                    state = AgentRuntimeHealthState.BLOCKED
                elif no_progress_seconds >= no_progress_after_seconds:
                    state = AgentRuntimeHealthState.STALLED
                else:
                    state = AgentRuntimeHealthState.ACTIVE
                health = AgentRuntimeUsefulProgressHealth.build(
                    invocation_id=invocation_id,
                    state=state,
                    useful_milestone=milestone,
                    useful_record_digest=record_digest,
                    useful_progress_at=progress_at,
                    observed_at=observed_at,
                    no_progress_seconds=no_progress_seconds,
                    authority_current=authority_current,
                    terminal_outcome_state=(outcome.state.value if outcome is not None else None),
                    alarm=None,
                )
                if state is AgentRuntimeHealthState.STALLED:
                    alarm = SQLiteAgentRuntimeHealthStore._raise_alarm_in_transaction(
                        conn,
                        AgentRuntimeNoProgressAlarm(
                            alarm_id=agent_runtime_alarm_id(
                                invocation_id,
                                health.useful_progress_digest,
                                no_progress_after_seconds,
                            ),
                            invocation_id=invocation_id,
                            useful_progress_digest=health.useful_progress_digest,
                            useful_milestone=milestone,
                            useful_progress_at=progress_at,
                            threshold_seconds=no_progress_after_seconds,
                            raised_at=(progress_time + timedelta(seconds=no_progress_after_seconds))
                            .isoformat(timespec="microseconds")
                            .replace("+00:00", "Z"),
                        ),
                    )
                    health = AgentRuntimeUsefulProgressHealth.build(
                        invocation_id=invocation_id,
                        state=state,
                        useful_milestone=milestone,
                        useful_record_digest=record_digest,
                        useful_progress_at=progress_at,
                        observed_at=observed_at,
                        no_progress_seconds=no_progress_seconds,
                        authority_current=authority_current,
                        terminal_outcome_state=None,
                        alarm=alarm,
                    )
                conn.commit()
                return health
            except Exception:
                conn.rollback()
                raise

    def reconcile_uncertain_provider_call(
        self,
        invocation_id: str,
    ) -> AgentInvocationProviderOutcome:
        """Fence a lost post-launch call after its original claim window ends."""

        with self.invocation_store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                existing = SQLiteAgentRuntimeProviderOutcomeStore.get_in_transaction(
                    conn,
                    invocation_id=invocation_id,
                )
                if existing is not None:
                    conn.commit()
                    return existing
                continuation_row = conn.execute(
                    "SELECT * FROM cloud_execution_continuations WHERE work_item_id = ?",
                    (invocation_id,),
                ).fetchone()
                if continuation_row is None:
                    raise AgentRuntimeProviderExecutionBlocked(
                        "agent provider continuation is missing"
                    )
                continuation = _agent_record(continuation_row)
                reservation_row = conn.execute(
                    "SELECT * FROM provider_invocation_reservations WHERE reservation_id = ?",
                    (continuation.reservation_id,),
                ).fetchone()
                claim_row = conn.execute(
                    "SELECT * FROM provider_work_execution_claims WHERE claim_id = ?",
                    (continuation.claim_id,),
                ).fetchone()
                receipt_row = conn.execute(
                    "SELECT * FROM provider_work_receipts WHERE receipt_id = ?",
                    (continuation.receipt_id,),
                ).fetchone()
                if reservation_row is None or claim_row is None or receipt_row is None:
                    raise AgentRuntimeProviderExecutionBlocked(
                        "agent provider launch lineage is incomplete"
                    )
                reservation = _reservation_record(reservation_row)
                claim = _claim_record(claim_row)
                receipt = _receipt_record(receipt_row)
                exact = (
                    reservation.invocation_key == invocation_id,
                    reservation.receipt_id == continuation.receipt_id,
                    reservation.claim_id == continuation.claim_id,
                    reservation.claim_digest == continuation.claim_digest,
                    reservation.claim_generation == continuation.claim_generation,
                    claim.claim_id == continuation.claim_id,
                    claim.claim_digest == continuation.claim_digest,
                    claim.generation == continuation.claim_generation,
                    receipt.receipt_id == continuation.receipt_id,
                    receipt.receipt_digest == continuation.receipt_digest,
                    receipt.work_item_kind == "agent_invocation",
                    receipt.work_item_id == invocation_id,
                )
                if not all(exact):
                    raise AgentRuntimeProviderExecutionBlocked(
                        "agent provider launch lineage is not exact"
                    )
                if reservation.state is ProviderInvocationReservationState.RESERVED:
                    raise AgentRuntimeProviderExecutionBlocked(
                        "agent provider call has not launched and is safe to resume"
                    )
                if reservation.state is not ProviderInvocationReservationState.LAUNCH_STARTED:
                    raise AgentRuntimeProviderExecutionBlocked(
                        "agent provider terminal reservation has no outcome"
                    )
                now = self._clock()
                if now.tzinfo is None or now.utcoffset() is None:
                    raise AgentRuntimeProviderExecutionBlocked("server clock is unavailable")
                claim_expires = datetime.fromisoformat(
                    claim.lease_expires_at.removesuffix("Z") + "+00:00"
                )
                if claim_expires > now.astimezone(timezone.utc):
                    raise AgentRuntimeProviderExecutionBlocked(
                        "agent provider call may still be active"
                    )
                outcome = SQLiteAgentRuntimeProviderOutcomeStore.finalize_in_transaction(
                    conn,
                    continuation=continuation,
                    launched_reservation=reservation,
                    state=AgentProviderOutcomeState.INDETERMINATE,
                    provider=receipt.provider,
                    model="",
                    family="",
                    latency_ms=None,
                    typed_output=None,
                    blocker_code="provider_call_lost_after_launch",
                    blocker_detail=("worker recovery found an expired claim after provider launch"),
                    created_at=now,
                )
                conn.commit()
                return outcome
            except Exception:
                conn.rollback()
                raise

    def execute_provider_call(
        self,
        invocation_id: str,
        *,
        typed_input: Mapping[str, object],
        router: ProviderRouter,
    ) -> AgentInvocationProviderOutcome:
        """Execute one bounded governed turn under the already-admitted identity."""

        if type(router) is not ProviderRouter:
            raise ValueError("router must be the canonical ProviderRouter")
        detached_input, input_digest = canonical_agent_invocation_input(typed_input)
        system, prompt, universe_dir = self._resolve_provider_call_material(
            invocation_id,
            typed_input=detached_input,
            typed_input_digest=input_digest,
        )
        existing = self.get_provider_outcome(invocation_id)
        if existing is not None:
            return existing
        existing_continuation = self.get_continuation(invocation_id)
        if existing_continuation is not None:
            existing_reservation = self.provider_store.get_reservation(
                existing_continuation.reservation_id
            )
            if (
                existing_reservation is not None
                and existing_reservation.state is ProviderInvocationReservationState.LAUNCH_STARTED
            ):
                raise AgentRuntimeProviderExecutionBlocked(
                    "agent provider launch requires uncertain-call reconciliation"
                )
        try:
            self.issue_receipt(invocation_id)
            self.claim(invocation_id)
            self.reserve(invocation_id)
            prepared = self.prepare_continuation(invocation_id).record
            if type(prepared) is not AgentInvocationCloudContinuation:
                raise AgentRuntimeProviderExecutionBlocked(
                    "agent provider continuation is not current"
                )
            carrier = self.arm_launch(invocation_id)
        except AgentRuntimeProviderExecutionBlocked:
            concurrent_outcome = self._current_provider_outcome_after_transition(invocation_id)
            if concurrent_outcome is not None:
                return concurrent_outcome
            raise
        except PermissionError as exc:
            concurrent_outcome = self._current_provider_outcome_after_transition(invocation_id)
            if concurrent_outcome is not None:
                return concurrent_outcome
            raise AgentRuntimeProviderExecutionBlocked(
                "agent provider execution is owned by a concurrent launch"
            ) from exc
        launched = self.provider_store.get_reservation(prepared.reservation_id)
        if (
            launched is None
            or launched.state is not ProviderInvocationReservationState.LAUNCH_STARTED
        ):
            raise AgentRuntimeProviderExecutionBlocked(
                "agent provider launch reservation is not current"
            )
        universe_config = load_universe_config(universe_dir)
        config = ModelConfig(
            timeout=universe_config.timeout,
            max_tokens=prepared.max_tokens,
            temperature=universe_config.temperature,
            sandbox_workspace=True,
            allowed_tools=("WebFetch", "WebSearch"),
            disallowed_tools=("Bash", "Write", "Edit", "NotebookEdit"),
        )
        try:
            response = router.call_sync(
                AGENT_INVOCATION_ROLE,
                prompt,
                system,
                config,
                operation=AGENT_INVOCATION_OPERATION,
                universe_context=UniverseContext(
                    universe_dir=universe_dir,
                    config=universe_config,
                    provider_invocation=carrier,
                ),
            )
        except Exception:
            return self._finalize_provider_outcome(
                prepared,
                launched,
                state=AgentProviderOutcomeState.INDETERMINATE,
                provider=carrier.provider,
                model="",
                family="",
                latency_ms=None,
                typed_output=None,
                blocker_code="provider_call_indeterminate",
                blocker_detail="provider call did not return a confirmed result",
            )

        typed_output: dict[str, object] = {
            "kind": "provider_text",
            "text": response.text,
        }
        encoded_output = json.dumps(
            typed_output,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if response.provider != carrier.provider:
            return self._finalize_provider_outcome(
                prepared,
                launched,
                state=AgentProviderOutcomeState.FAILED,
                provider=carrier.provider,
                model="",
                family="",
                latency_ms=None,
                typed_output=None,
                blocker_code="provider_identity_mismatch",
                blocker_detail="provider response did not match the armed provider",
            )
        if len(encoded_output) > MAX_AGENT_PROVIDER_OUTPUT_BYTES:
            return self._finalize_provider_outcome(
                prepared,
                launched,
                state=AgentProviderOutcomeState.FAILED,
                provider=carrier.provider,
                model="",
                family="",
                latency_ms=None,
                typed_output=None,
                blocker_code="provider_output_too_large",
                blocker_detail="provider output exceeded the bounded result size",
            )
        return self._finalize_provider_outcome(
            prepared,
            launched,
            state=AgentProviderOutcomeState.SUCCEEDED,
            provider=carrier.provider,
            model=response.model,
            family=response.family,
            latency_ms=response.latency_ms,
            typed_output=typed_output,
            blocker_code=None,
            blocker_detail=None,
        )

    def _current_provider_outcome_after_transition(
        self,
        invocation_id: str,
    ) -> AgentInvocationProviderOutcome | None:
        """Replay a race winner only while its invocation authority is current."""

        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise AgentRuntimeProviderExecutionBlocked("server clock is unavailable")
        with self.invocation_store.connection() as conn:
            conn.execute("BEGIN")
            try:
                self._validated_authority(
                    conn,
                    invocation_id=invocation_id,
                    evaluated_at=now.astimezone(timezone.utc).timestamp(),
                )
                outcome = SQLiteAgentRuntimeProviderOutcomeStore.get_in_transaction(
                    conn,
                    invocation_id=invocation_id,
                )
                conn.commit()
                return outcome
            except Exception:
                conn.rollback()
                raise

    def _resolve_provider_call_material(
        self,
        invocation_id: str,
        *,
        typed_input: dict[str, object],
        typed_input_digest: str,
    ) -> tuple[str, str, Path]:
        with self.invocation_store.connection() as conn:
            conn.execute("BEGIN")
            aggregate = self.invocation_store.get_in_transaction(
                conn,
                invocation_id=invocation_id,
            )
            if aggregate is None:
                raise AgentRuntimeProviderExecutionBlocked("agent invocation is not current")
            command, invocation, event = aggregate
            if (
                event.state is not AgentInvocationEventState.ADMITTED
                or command.typed_input_digest != typed_input_digest
            ):
                raise AgentRuntimeProviderExecutionBlocked(
                    "agent typed input does not match admission"
                )
            manifest = AgentRuntimeManifestStore.resolve_current_in_transaction(
                conn,
                owner_user_id=command.authorizing_subject_id,
                manifest_id=command.execution_subject.ref,
                manifest_digest=command.execution_subject.digest,
            )
            universe_row = conn.execute(
                "SELECT host_path FROM universes WHERE universe_id = ?",
                (command.universe_id,),
            ).fetchone()
            conn.commit()
        if manifest is None or universe_row is None:
            raise AgentRuntimeProviderExecutionBlocked(
                "agent manifest or registered universe is unavailable"
            )
        registered_universe_dir = Path(str(universe_row["host_path"])).expanduser()
        if not registered_universe_dir.is_absolute():
            raise AgentRuntimeProviderExecutionBlocked(
                "registered universe directory must be absolute"
            )
        universe_dir = registered_universe_dir.resolve(strict=False)
        if not universe_dir.is_dir():
            raise AgentRuntimeProviderExecutionBlocked(
                "registered universe directory is unavailable"
            )
        content = manifest.manifest_input.to_dict()
        plan = content["execution_plan"]
        plan_adapter = content["plan_adapter"]
        if (
            not isinstance(plan, dict)
            or not isinstance(plan_adapter, dict)
            or plan.get("plan_class") != "single_provider_turn"
            or plan_adapter.get("adapter_ref") != "builtin:single-provider-turn"
        ):
            raise AgentRuntimeProviderExecutionBlocked(
                "agent plan adapter is not executable by this runtime"
            )
        component_key = plan.get("entry_component")
        components = content["components"]
        component = components.get(component_key) if isinstance(components, dict) else None
        if not isinstance(component, dict) or component.get("runtime_mode") != "execute":
            raise AgentRuntimeProviderExecutionBlocked("agent entry component is not executable")
        adapter = component.get("adapter")
        configuration = component.get("configuration")
        instructions = (
            configuration.get("instructions") if isinstance(configuration, dict) else None
        )
        if (
            not isinstance(adapter, dict)
            or adapter.get("adapter_ref") != "builtin:prompt-component"
            or not isinstance(instructions, str)
            or not instructions.strip()
        ):
            raise AgentRuntimeProviderExecutionBlocked("agent prompt component is not executable")
        prompt = json.dumps(
            typed_input,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return instructions, prompt, universe_dir

    def _finalize_provider_outcome(
        self,
        continuation: AgentInvocationCloudContinuation,
        launched_reservation: ProviderInvocationReservation,
        *,
        state: AgentProviderOutcomeState,
        provider: str,
        model: str,
        family: str,
        latency_ms: float | None,
        typed_output: dict[str, object] | None,
        blocker_code: str | None,
        blocker_detail: str | None,
    ) -> AgentInvocationProviderOutcome:
        with self.invocation_store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if state is AgentProviderOutcomeState.SUCCEEDED:
                    try:
                        grant = self._validated_store_grant(
                            conn,
                            invocation_id=continuation.invocation_id,
                            evaluated_at=self._clock().timestamp(),
                        )
                    except AgentRuntimeProviderExecutionBlocked:
                        state = AgentProviderOutcomeState.INDETERMINATE
                        model = ""
                        family = ""
                        latency_ms = None
                        typed_output = None
                        blocker_code = "provider_authority_lost_after_call"
                        blocker_detail = (
                            "current provider authority was lost before output finalization"
                        )
                    else:
                        grant._discard()
                row = conn.execute(
                    "SELECT * FROM provider_invocation_reservations WHERE reservation_id = ?",
                    (continuation.reservation_id,),
                ).fetchone()
                current = _reservation_record(row) if row is not None else None
                if current != launched_reservation:
                    raise AgentRuntimeProviderExecutionBlocked(
                        "agent provider finalization lost its reservation fence"
                    )
                outcome = SQLiteAgentRuntimeProviderOutcomeStore.finalize_in_transaction(
                    conn,
                    continuation=continuation,
                    launched_reservation=current,
                    state=state,
                    provider=provider,
                    model=model,
                    family=family,
                    latency_ms=latency_ms,
                    typed_output=typed_output,
                    blocker_code=blocker_code,
                    blocker_detail=blocker_detail,
                    created_at=self._clock(),
                )
                conn.commit()
                return outcome
            except Exception:
                conn.rollback()
                raise

    def prepare_continuation(
        self,
        invocation_id: str,
    ) -> CloudContinuationWriteResult:
        with self.invocation_store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                now = self._clock()
                if now.tzinfo is None or now.utcoffset() is None:
                    raise AgentRuntimeProviderExecutionBlocked("server clock is unavailable")
                now = now.astimezone(timezone.utc)
                store_grant = self._validated_store_grant(
                    conn,
                    invocation_id=invocation_id,
                    evaluated_at=now.timestamp(),
                )
                reservation_result = self.provider_store._reserve_agent_in_transaction(
                    conn,
                    store_grant,
                )
                reservation = reservation_result.record
                if reservation is None:
                    raise AgentRuntimeProviderExecutionBlocked(
                        "agent provider reservation is not current"
                    )
                aggregate = self.invocation_store.get_in_transaction(
                    conn,
                    invocation_id=invocation_id,
                )
                if aggregate is None:
                    raise AgentRuntimeProviderExecutionBlocked("agent invocation is not current")
                command, invocation, event = aggregate
                if event.state is not AgentInvocationEventState.ADMITTED:
                    raise AgentRuntimeProviderExecutionBlocked("agent invocation is not admitted")
                receipt_row = conn.execute(
                    "SELECT * FROM provider_work_receipts WHERE receipt_id = ?",
                    (reservation.receipt_id,),
                ).fetchone()
                claim_row = conn.execute(
                    "SELECT * FROM provider_work_execution_claims WHERE claim_id = ?",
                    (reservation.claim_id,),
                ).fetchone()
                activation_row = conn.execute(
                    """
                    SELECT * FROM automation_activations
                    WHERE universe_id = ? AND automation_id = ?
                    """,
                    (command.universe_id, command.activation_automation_id),
                ).fetchone()
                if receipt_row is None or claim_row is None or activation_row is None:
                    raise AgentRuntimeProviderExecutionBlocked(
                        "agent continuation authority is not current"
                    )
                receipt = _receipt_record(receipt_row)
                claim = _claim_record(claim_row)
                activation = _activation_record(activation_row)
                timestamp = now.isoformat(timespec="microseconds").replace("+00:00", "Z")
                record = AgentInvocationCloudContinuation.build(
                    schema_version=1,
                    work_item_kind="agent_invocation",
                    continuation_id=f"agent_continuation_{invocation_id}",
                    generation=1,
                    state=CloudContinuationState.PREPARED,
                    principal_id=command.authorizing_subject_id,
                    universe_id=command.universe_id,
                    automation_id=command.activation_automation_id,
                    activation_epoch=command.activation_epoch,
                    activation_lease_id=command.lease_id,
                    execution_subject=command.execution_subject,
                    command_id=command.command_id,
                    command_digest=command.command_digest,
                    invocation_id=invocation.invocation_id,
                    invocation_generation=event.generation,
                    invocation_digest=invocation.root_digest,
                    provider_binding_id=command.provider_work_binding_id,
                    provider_binding_generation=(command.provider_work_binding_generation),
                    provider_binding_digest=command.provider_work_binding_digest,
                    receipt_id=receipt.receipt_id,
                    receipt_digest=receipt.receipt_digest,
                    claim_id=claim.claim_id,
                    claim_generation=claim.generation,
                    claim_digest=claim.claim_digest,
                    reservation_id=reservation.reservation_id,
                    reservation_digest=reservation.reservation_digest,
                    typed_input_digest=command.typed_input_digest,
                    max_tokens=reservation.max_tokens,
                    max_cost_microunits=reservation.max_cost_microunits,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                result = self.continuation_store._prepare_agent_in_transaction(
                    conn,
                    record,
                    expected_activation=activation,
                    expected_command=command,
                    expected_invocation=invocation,
                    expected_receipt=receipt,
                    expected_claim=claim,
                    expected_reservation=reservation,
                )
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise

    def arm_launch(self, invocation_id: str) -> ProviderInvocationCarrier:
        result = self._transition(invocation_id, transition="launch")
        assert isinstance(result, ProviderInvocationReservationWriteResult)
        if result.outcome.value == "replayed":
            raise PermissionError("provider invocation reservation is already armed")
        if (
            result.outcome.value != "applied"
            or result.record is None
            or result.receipt is None
            or result.claim is None
            or result.mint_proof is None
        ):
            raise PermissionError("provider invocation reservation could not be armed")
        return _mint_provider_invocation_carrier(
            result.receipt,
            result.claim,
            result.record,
            result.mint_proof,
        )

    def _transition(
        self,
        invocation_id: str,
        *,
        transition: Literal["receipt", "claim", "reserve", "launch"],
    ) -> object:
        with self.invocation_store.connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                now = self._clock()
                if now.tzinfo is None or now.utcoffset() is None:
                    raise AgentRuntimeProviderExecutionBlocked("server clock is unavailable")
                now = now.astimezone(timezone.utc)
                store_grant = self._validated_store_grant(
                    conn,
                    invocation_id=invocation_id,
                    evaluated_at=now.timestamp(),
                )
                if transition == "receipt":
                    result = self.provider_store._issue_universe_receipt_in_transaction(
                        conn,
                        store_grant,
                    )
                elif transition == "claim":
                    result = self.provider_store._claim_agent_in_transaction(
                        conn,
                        store_grant,
                    )
                elif transition == "reserve":
                    result = self.provider_store._reserve_agent_in_transaction(
                        conn,
                        store_grant,
                    )
                else:
                    result = self.provider_store._arm_agent_launch_in_transaction(
                        conn,
                        store_grant,
                    )
                conn.commit()
                return result
            except Exception:
                conn.rollback()
                raise

    def _validated_authority(
        self,
        conn: sqlite3.Connection,
        *,
        invocation_id: str,
        evaluated_at: float,
    ) -> ProviderUniverseWorkAuthority:
        try:
            aggregate = self.invocation_store.get_in_transaction(
                conn,
                invocation_id=invocation_id,
            )
        except (TypeError, ValueError):
            raise AgentRuntimeProviderExecutionBlocked(
                "agent invocation integrity validation failed"
            ) from None
        if aggregate is None:
            raise AgentRuntimeProviderExecutionBlocked("agent invocation is not current")
        command, invocation, event = aggregate
        if event.state is not AgentInvocationEventState.ADMITTED:
            raise AgentRuntimeProviderExecutionBlocked("agent invocation is not admitted")

        manifest = AgentRuntimeManifestStore.resolve_current_in_transaction(
            conn,
            owner_user_id=command.authorizing_subject_id,
            manifest_id=command.execution_subject.ref,
            manifest_digest=command.execution_subject.digest,
        )
        if manifest is None:
            raise AgentRuntimeProviderExecutionBlocked("agent manifest is not current")
        if not AutomationActivationStore.validate_claim_in_transaction(
            conn,
            universe_id=command.universe_id,
            automation_id=command.activation_automation_id,
            epoch=command.activation_epoch,
            executor_class=command.executor_class,
            subject=command.execution_subject,
            lease_id=command.lease_id,
        ):
            raise AgentRuntimeProviderExecutionBlocked("agent activation is not current")

        grants = self.grant_resolver.resolve_in_transaction(
            manifest,
            conn,
            evaluated_at=evaluated_at,
        )
        if not grants.ready:
            raise AgentRuntimeProviderExecutionBlocked("agent grant is not current")
        admitted_at = datetime.fromisoformat(
            command.created_at.removesuffix("Z") + "+00:00"
        ).timestamp()
        principal = AgentRuntimePrincipal(
            authorizing_subject_id=command.authorizing_subject_id,
            universe_id=command.universe_id,
            agent_binding_id=command.agent_binding_id,
            binding_revision=command.binding_revision,
            execution_subject=command.execution_subject,
            activation_automation_id=command.activation_automation_id,
            activation_epoch=command.activation_epoch,
            executor_class=command.executor_class,
            lease_id=command.lease_id,
            invocation_id=invocation.invocation_id,
            invocation_generation=event.generation,
            typed_input_digest=command.typed_input_digest,
            # Principal identity is stable across restart while grant authority
            # itself is still resolved against `evaluated_at` above.
            evaluated_at=admitted_at,
            grant_evidence=tuple(grants.evidence),
            grant_evidence_set_digest=grants.evidence_set_digest,
        )
        binding = self.provider_store.get_binding_in_transaction(
            conn,
            binding_id=command.provider_work_binding_id,
        )
        if binding is None:
            raise AgentRuntimeProviderExecutionBlocked("provider binding is not current")
        assignment_root = ProviderWorkBindingRoot(
            owner_user_id=command.authorizing_subject_id,
            universe_id=command.universe_id,
            provider=binding.provider,
        )
        try:
            assignment = self.provider_binding_resolver.resolve_current_in_transaction(
                conn,
                assignment_root,
            )
        except Exception:
            raise AgentRuntimeProviderExecutionBlocked(
                "provider assignment source is unavailable"
            ) from None
        if type(assignment) is not ProviderWorkBindingSeed:
            raise AgentRuntimeProviderExecutionBlocked("provider assignment is not current")
        binding_matches = (
            binding.state is ProviderWorkBindingState.ACTIVE,
            binding.generation == command.provider_work_binding_generation,
            binding.binding_digest == command.provider_work_binding_digest,
            binding.owner_user_id == command.authorizing_subject_id,
            binding.universe_id == command.universe_id,
            "agent_invocation" in binding.allowed_operations,
            "agent_runtime" in binding.allowed_roles,
            binding.max_invocations >= 1,
            binding.max_tokens >= command.budget.max_tokens,
            binding.max_cost_microunits >= command.budget.max_cost_microunits,
            assignment.owner_user_id == binding.owner_user_id,
            assignment.universe_id == binding.universe_id,
            assignment.provider == binding.provider,
            assignment.credential_reference_digest == binding.credential_reference_digest,
            assignment.allowed_operations == binding.allowed_operations,
            assignment.allowed_roles == binding.allowed_roles,
            assignment.assignment_generation == binding.assignment_generation,
            assignment.assignment_digest == binding.assignment_digest,
            assignment.max_invocations == binding.max_invocations,
            assignment.max_tokens == binding.max_tokens,
            assignment.max_cost_microunits == binding.max_cost_microunits,
            assignment.expires_at == binding.expires_at,
        )
        if not all(binding_matches):
            raise AgentRuntimeProviderExecutionBlocked("provider binding is not current")

        authority = ProviderUniverseWorkAuthority(
            root=ProviderUniverseWorkRoot(
                work_item_kind="agent_invocation",
                work_item_id=invocation.invocation_id,
            ),
            binding=binding,
            principal_id=principal.principal_digest,
            actor_id=command.lease_id,
            operation="agent_invocation",
            role="agent_runtime",
            executor_class="cloud",
            max_invocations=1,
            max_tokens=command.budget.max_tokens,
            max_cost_microunits=command.budget.max_cost_microunits,
            expires_at=binding.expires_at,
            execution_subject=command.execution_subject,
            agent_invocation_command_id=command.command_id,
            agent_invocation_command_digest=command.command_digest,
            agent_invocation_generation=event.generation,
        )
        return authority

    def _validated_store_grant(
        self,
        conn: sqlite3.Connection,
        *,
        invocation_id: str,
        evaluated_at: float,
    ) -> _AgentProviderReceiptStoreGrant:
        authority = self._validated_authority(
            conn,
            invocation_id=invocation_id,
            evaluated_at=evaluated_at,
        )
        # Keep minting inline after every authority check. A module-level or
        # store-level mint helper would let a lower-level caller launder a
        # fabricated authority object around this sole issuance owner.
        grant_id = secrets.token_hex(32)
        issuer_pid = os.getpid()
        store_grant = object.__new__(_AgentProviderReceiptStoreGrant)
        object.__setattr__(store_grant, "_grant_id", grant_id)
        object.__setattr__(store_grant, "_issuer_pid", issuer_pid)
        with _RECEIPT_GRANT_LOCK:
            _ACTIVE_RECEIPT_GRANTS[grant_id] = (
                weakref.ref(store_grant),
                authority,
                issuer_pid,
            )
        weakref.finalize(
            store_grant,
            _discard_receipt_grant,
            grant_id,
            issuer_pid,
        )
        return store_grant


__all__ = [
    "AgentInvocationProviderOutcome",
    "AgentProviderOutcomeState",
    "AgentRuntimeProviderExecutionBlocked",
    "AgentRuntimeProviderExecutionService",
]
