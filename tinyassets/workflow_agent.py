"""Work-owned adapter for the shared agent loop; journals never grant authority."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import replace

from tinyassets.agent_turn_coordinator import AgentTurnCoordinator
from tinyassets.exceptions import AllProvidersExhaustedError, ProviderAuthorityHeldError
from tinyassets.providers.agent_capacity_boundary import capacity_boundary
from tinyassets.providers.base import UniverseContext
from tinyassets.providers.model_policy import ModelRef
from tinyassets.storage.agent_native_records import NativeInput
from tinyassets.storage.agent_turn_records import RoundInput, dump


class WorkAgentEffectHeld(ProviderAuthorityHeldError):
    """A new node attempt could replay recorded effects or unknown execution."""

    failure_class = "agent_effect_held"


class WorkAgentAdapter:
    def __init__(self, session, initial_launch, policy):
        self.session = session
        self.initial_launch = initial_launch
        self.initial_pending = True
        self.carrier = initial_launch[0]
        self.receipt = self.carrier._receipt
        self.policy = dict(policy or {})
        self.source_policy = dict(policy or {})
        self.candidates = getattr(session, "_work_candidates", None)
        self.has_candidate_order = self.candidates is not None
        self._staged_next = None
        selected = self.carrier.selected_model
        native = self.carrier.native_selection
        model = selected.model_id if selected is not None else (
            native.requested_model_id if native is not None else ""
        )
        self.selection = ModelRef(self.carrier.provider, model)
        # Resolve provider-default once for this turn. Subsequent HTTP rounds
        # refresh authority for that actual model without editing the Branch.
        self.policy["preferred"] = {"provider": self.carrier.provider, "model_id": model}

    def check(self, context, config):
        self._identity(context, config, self.selection)
        return self.session._check_agent_authority(self.carrier)

    def _identity(self, context, config, selection):
        """Pure prelude only; never substitute it for active invocation/tool authority."""
        if (context.universe_dir != self.session._universe_dir
                or context.provider_request is not None or context.provider_invocation is not None
                or context.served_provider is not None or context.agent_model_plan is not None
                or context.model_selection != selection
                or self.carrier._receipt != self.receipt
                or self.carrier._claim != self.initial_launch[0]._claim
                or not config.engine_mcp_enabled
                or config.engine_mcp_actor_id != self.receipt.principal_id
                or config.engine_mcp_graph_id != self.receipt.universe_id):
            raise ProviderAuthorityHeldError("workflow agent identity changed")

    def next_candidate(self, owner, universe, exhaustion):
        if (self.candidates is None or owner != self.receipt.principal_id
                or universe != self.receipt.universe_id):
            raise ProviderAuthorityHeldError("workflow candidate scope changed")
        self._staged_next = self.candidates.next_candidate(self.source_policy, exhaustion)
        return self._staged_next

    def engine_identity(self, context, config):
        if context.model_selection != self.selection and self._staged_next is not None:
            # Discovery is not a tool effect; actual engine admission still runs.
            # Fresh _authorize_attempt below is the only candidate launch gate.
            self._identity(context, config, self._staged_next)
        else:
            self.check(context, config)
        return self.receipt.principal_id, self.receipt.universe_id

    def create_turn(self, journal, *, owner, context, prompt, system, plan):
        if plan is not None or owner != self.receipt.principal_id:
            raise ProviderAuthorityHeldError("workflow agent progress scope changed")
        return journal.create(
            owner, self.receipt.universe_id, prompt=prompt, system=system,
            authority_kind="work_invocation", work_receipt_id=self.receipt.receipt_id,
        )

    async def infer(self, *, router, prompt, system, config, context, observer, kind):
        changing = context.model_selection != self.selection
        if changing:
            if self._staged_next is None or self.initial_pending:
                raise ProviderAuthorityHeldError("workflow candidate was not staged")
            self._identity(context, config, self._staged_next)
            if self.candidates.next_candidate(self.source_policy) != self._staged_next:
                raise ProviderAuthorityHeldError("workflow candidate was exhausted")
        else:
            self.check(context, config)
        if self.initial_pending:
            self.initial_pending = False
            return await self._infer_launch(
                self.initial_launch, router, prompt, system, config, context, observer, kind,
            )
        policy = dict(self.policy)
        if changing:
            policy["preferred"] = {"provider": self._staged_next.connection_id,
                                   "model_id": self._staged_next.model_id}
        with self.session._authorize_attempt(
            role="writer", prompt=prompt, system=system, policy=policy,
        ) as launch:
            if changing:
                self.selection = self._staged_next
                self.policy = policy
            return await self._infer_launch(
                launch, router, prompt, system, config, context, observer, kind,
            )

    async def _infer_launch(self, launch, router, prompt, system, config, context, observer, kind):
        self.carrier, snapshot_dir, provider = launch
        if provider != self.selection.connection_id:
            raise ProviderAuthorityHeldError("workflow agent source changed")
        self.check(context, config)
        return await router.call(
            "writer", prompt, system, replace(config, credential_snapshot_dir=snapshot_dir),
            operation=self.carrier.operation,
            universe_context=replace(context, provider_invocation=self.carrier),
            _agent_observer=observer, _agent_execution_kind=kind,
        )

    def round_input(self, authority, reservation, config, *, owner, context,
                    prompt, system, native_input, kind):
        if authority is not self.carrier or reservation is not None:
            raise ProviderAuthorityHeldError("workflow inference observer scope changed")
        if self.check(context, config) != owner:
            raise ProviderAuthorityHeldError("workflow inference owner changed")
        lineage = {"authority_kind": "work_invocation",
                   "work_receipt_id": self.receipt.receipt_id}
        if kind == "native_agent":
            if native_input is None or config.agent_request is not None:
                raise ProviderAuthorityHeldError("workflow native input changed")
            native_prompt, native_system = native_input
            body = dump({"prompt": native_prompt, "system": native_system})
            return NativeInput(
                authority.provider, self.selection.model_id, authority.binding_id,
                authority.reservation_id, authority.binding_generation, authority.binding_digest,
                "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest(), **lineage,
            )
        if kind != "engine_inference" or config.agent_request is None:
            raise ProviderAuthorityHeldError("workflow inference input changed")
        request = config.agent_request
        _, body = request.encode(
            prompt=prompt, system=system, selection=authority.selected_model,
            temperature=config.temperature, max_tokens=config.max_tokens,
        )
        return RoundInput(
            authority.provider, authority.selected_model.model_id,
            dump({"version": 1, "tools": request.tools()}), authority.binding_id,
            authority.reservation_id, authority.binding_generation, authority.binding_digest,
            "sha256:" + hashlib.sha256(json.dumps(body).encode("utf-8")).hexdigest(), **lineage,
        )


class WorkflowAgentTurn(AgentTurnCoordinator):
    async def run(self):
        try:
            return await super().run()
        except AllProvidersExhaustedError as exc:
            rounds = () if self.turn is None else self.turn.rounds
            effects = any(tool.state not in {"planned", "not_sent"}
                          for step in rounds for tool in step.tools)
            boundary = capacity_boundary(
                self.context.model_selection, exc.attempts, execution_kind=self.execution_kind,
                native_evidence=(getattr(exc, "native_evidence", ())
                                 if self.execution_kind == "native_agent" else ()),
            )
            # Before a durable inference round exists, the observer prevented
            # transport launch. Keep the existing known-unsent retry contract;
            # authentication/unknown transport failures have a recorded round.
            if effects or (rounds and boundary is None):
                raise WorkAgentEffectHeld(
                    "Workflow agent progress is held; "
                    "completed or uncertain actions were not replayed.",
                ) from exc
            raise


def call_foreground_work_agent(session, *, prompt, system, config, policy, response_observer=None,
                               metadata_observer=None):
    """Enter once from immutable work opt-in, never through a fake served request."""
    return _call_work_agent(
        session, prompt=prompt, system=system, config=config, policy=policy,
        principal_id=session._principal_id, universe_id=session._universe_id,
        response_observer=response_observer,
        metadata_observer=metadata_observer,
    )


def call_background_work_agent(session, *, prompt, system, config, policy):
    """Use the queue session's own per-round admission and between-step fence."""
    return _call_work_agent(
        session, prompt=prompt, system=system, config=config, policy=policy,
        principal_id=session._task.actor_id, universe_id=session._task.universe_id,
    )


def _call_work_agent(session, *, prompt, system, config, policy, principal_id, universe_id,
                     response_observer=None, metadata_observer=None):
    from tinyassets.config import load_universe_config
    from tinyassets.engine_mcp_http import engine_tools_authorized
    from tinyassets.provider_work_authority import ProviderInvocationReservationState
    from tinyassets.providers import call as bridge
    from tinyassets.providers.provider_resolver import register_universe_open_providers

    router = bridge.get_provider_router()
    if bridge.is_force_mock() or router is None:
        raise ProviderAuthorityHeldError("workflow agent requires its real provider router")
    if not engine_tools_authorized(
        actor_id=principal_id, graph_id=universe_id, root=session._base_path,
    ):
        raise ProviderAuthorityHeldError("engine_tools_unavailable")
    config = replace(config, engine_mcp_enabled=True, engine_mcp_actor_id=principal_id,
                     engine_mcp_graph_id=universe_id, credential_snapshot_dir=None)
    initial_policy = policy
    candidates = getattr(session, "_work_candidates", None)
    if candidates is not None:
        selected = candidates.next_candidate(policy)
        if selected is None:
            raise ProviderAuthorityHeldError("no eligible work model remains")
        initial_policy = {**(policy or {}), "preferred": {
            "provider": selected.connection_id, "model_id": selected.model_id,
        }}
    with session._authorize_attempt(
        role="writer", prompt=prompt, system=system, policy=initial_policy,
    ) as initial:
        adapter = None
        try:
            receipt = initial[0]._receipt
            if receipt.principal_id != principal_id or receipt.universe_id != universe_id:
                raise ProviderAuthorityHeldError("workflow agent admitted identity changed")
            adapter = WorkAgentAdapter(session, initial, policy)
            context = UniverseContext(
                universe_dir=session._universe_dir,
                config=load_universe_config(session._universe_dir),
                model_selection=adapter.selection,
            )
            register_universe_open_providers(router, receipt.universe_id)
            turn = WorkflowAgentTurn(adapter=adapter, router=router, prompt=prompt, system=system,
                                     universe_context=context, config=config)
            response = asyncio.run(turn.run())
            if metadata_observer is not None:
                metadata = router._call_meta(response, len(turn.turn.rounds))
                # Keep the selected request separate from answer telemetry.
                # Some HTTP adapters put the reported alias in response.model.
                metadata["model"] = adapter.selection.model_id
                metadata_observer(metadata)
            if response_observer is not None:
                try:
                    response_observer(response)
                except Exception:
                    logging.getLogger(__name__).warning("Work answer receipt unavailable")
            return response.text, response.provider
        finally:
            if adapter is None or adapter.initial_pending:
                # No inference was attempted (for example, engine discovery failed).
                initial[0].validate_for_call(role="writer", operation=initial[0].operation)
                initial[0].settle(ProviderInvocationReservationState.CANCELLED_BEFORE_LAUNCH,
                                  input_tokens=0, output_tokens=0, cost_microunits=0)
