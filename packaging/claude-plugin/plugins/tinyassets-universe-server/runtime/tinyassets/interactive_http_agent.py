"""Engine-owned HTTP agent execution: one admitted inference, then known effects.

Invoked only by the ordinary provider-call bridge on the capability-claiming
thread. A journal is progress, never authority or permission to replay actions.
Native CLI agents retain their native execution path.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import replace

from tinyassets.engine_tool_client import EngineToolError, open_engine_tools
from tinyassets.exceptions import (
    AllProvidersExhaustedError,
    ProviderAuthorityHeldError,
    ProviderProtocolError,
)
from tinyassets.provider_assignment import check_served_agent_tool_authority
from tinyassets.providers import agent_chat_codec as codec
from tinyassets.providers.agent_inference import AgentInferenceRequest
from tinyassets.providers.agent_model_plan import AgentModelPlan
from tinyassets.providers.model_capacity import CapacitySignal
from tinyassets.served_tools import SERVED_ENGINE_MCP_TOOLS
from tinyassets.storage.agent_turn_journal import AgentTurnJournal, JournalUnavailable
from tinyassets.storage.agent_turn_records import RoundInput, dump, load_result

_LOG = logging.getLogger(__name__)


class InteractiveHttpAgentTurn:
    """One in-process turn; no crash resurrection or automatic effect replay."""

    def __init__(self, *, router, prompt, system, universe_context, config):
        self.router = router
        self.prompt = prompt
        self.system = system
        self.context = universe_context
        self.config = config
        self.journal = None
        self.turn = None
        self.owner = None
        self.plan = universe_context.agent_model_plan
        if self.plan is not None and type(self.plan) is not AgentModelPlan:
            raise ValueError("invalid interactive candidate plan")
        self.exhaustion = ()
        self.retrying_capacity = False

    def _check_scope(self):
        owner = check_served_agent_tool_authority(self.context)
        if (
            not self.config.engine_mcp_enabled
            or self.config.engine_mcp_actor_id != owner
            or self.config.engine_mcp_graph_id != self.context.universe_dir.name
        ):
            raise ProviderAuthorityHeldError("interactive engine tool identity changed")
        if self.owner is not None and owner != self.owner:
            raise ProviderAuthorityHeldError("interactive agent owner changed")
        return owner

    def _accept(self, transition):
        if transition.status != "applied":
            raise JournalUnavailable("agent progress changed; action was not replayed")
        self.turn = transition.snapshot

    def _begin(self, authority, reservation, config):
        if (
            authority.owner_user_id != self.owner
            or authority.universe_id != self.context.universe_dir.name
        ):
            raise ProviderAuthorityHeldError("agent inference scope changed")
        request = config.agent_request
        _, body = request.encode(
            prompt=self.prompt,
            system=self.system,
            selection=authority.selected_model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        candidate = RoundInput(
            authority.provider,
            authority.selected_model.model_id,
            dump({"version": 1, "tools": request.tools()}),
            authority.binding_id,
            reservation.reservation_id,
            authority.binding_generation,
            authority.binding_digest,
            "sha256:" + hashlib.sha256(json.dumps(body).encode("utf-8")).hexdigest(),
        )
        self._accept(
            self.journal.begin_round(
                self.owner,
                authority.universe_id,
                self.turn.turn_id,
                expected_generation=self.turn.generation,
                candidate=candidate,
                after_failed_inference=self.retrying_capacity,
            )
        )
        self.retrying_capacity = False

    def _history(self):
        history = []
        for previous in self.turn.rounds:
            if previous.state == "failed":
                continue
            if (
                previous.reply is None
                or previous.reply.stop != "tool_requests"
                or any(
                    tool.state != "completed" or tool.content_kind != "text_only"
                    for tool in previous.tools
                )
            ):
                raise JournalUnavailable("agent continuation is incomplete")
            outcomes = tuple(
                codec.tool_outcome(
                    tool.request,
                    load_result(tool.result_json)[0],
                )
                for tool in previous.tools
            )
            history.append(
                codec.CapturedToolRound(
                    round=codec.ToolRound(previous.reply, outcomes),
                    tools=json.loads(previous.candidate.tools_json)["tools"],
                )
            )
        return tuple(history)

    async def run(self):
        try:
            return await self._run()
        except BaseException:
            # A later pre-intent failure has no uncertain action to preserve.
            # Keep zero-round roots ready for the writer's one all-skipped retry.
            if self.turn is not None and self.turn.state == "ready" and self.turn.rounds:
                try:
                    self.close_quiescent()
                except Exception:
                    _LOG.exception("could not close settled interactive agent progress")
            raise

    async def _run(self):
        self.owner = self._check_scope()
        uid = self.context.universe_dir.name
        if self.plan is not None:
            first = self.plan.next_candidate(self.owner, uid, self.exhaustion)
            if first is None:
                raise ProviderAuthorityHeldError("no eligible interactive model remains")
            self.context = replace(self.context, model_selection=first)
            self._check_scope()
        if self.turn is None:
            self.journal = AgentTurnJournal(self.context.universe_dir.parent)
            self.turn = self.journal.create(
                self.owner, uid, prompt=self.prompt, system=self.system,
                policy_generation=None if self.plan is None else self.plan.policy.generation,
            )
        elif self.turn.state != "ready" or self.turn.rounds:
            raise JournalUnavailable("agent turn cannot be replayed")

        timeout = self.config.stream_timeout_profile().absolute_cap_s
        async with asyncio.timeout(timeout):
            async with open_engine_tools(
                actor_id=self.owner,
                graph_id=uid,
                enabled_tools=SERVED_ENGINE_MCP_TOOLS,
                timeout=timeout,
            ) as engine:
                while True:
                    request = AgentInferenceRequest(
                        tools=codec.tool_definitions(engine.tools),
                        history=self._history(),
                    )
                    config = replace(self.config, agent_request=request)
                    try:
                        response = await self.router.call(
                            "writer",
                            self.prompt,
                            self.system,
                            config,
                            operation="converse",
                            universe_context=self.context,
                            _agent_observer=self._begin,
                        )
                    except BaseException as exc:
                        # No engine tool can start before a validated inference
                        # is committed. Preserve failure, never restart this turn.
                        if self.turn.state == "inference_started":
                            self._accept(
                                self.journal.finish_inference(
                                    self.owner,
                                    uid,
                                    self.turn.turn_id,
                                    expected_generation=self.turn.generation,
                                    ordinal=len(self.turn.rounds),
                                    reply=None,
                                )
                            )
                        if self._next_after_capacity(exc):
                            continue
                        raise
                    if response.agent_reply is None:
                        raise ProviderProtocolError("HTTP agent response lacks validated progress")
                    self._accept(
                        self.journal.finish_inference(
                            self.owner,
                            uid,
                            self.turn.turn_id,
                            expected_generation=self.turn.generation,
                            ordinal=len(self.turn.rounds),
                            reply=response.agent_reply,
                            cost_microusd=response.cost_microunits,
                        )
                    )
                    if self.turn.state == "completed":
                        return response
                    if self.turn.state != "tools_pending":
                        raise ProviderProtocolError(
                            "agent response requires attention: " + self.turn.state,
                        )
                    for call_ordinal, tool in enumerate(self.turn.rounds[-1].tools, 1):
                        self._check_scope()
                        self._accept(
                            self.journal.start_tool(
                                self.owner,
                                uid,
                                self.turn.turn_id,
                                expected_generation=self.turn.generation,
                                ordinal=len(self.turn.rounds),
                                call_ordinal=call_ordinal,
                            )
                        )
                        try:
                            result = await engine.call(tool.request.name, tool.request.arguments())
                        except BaseException as exc:
                            failure = (
                                "not_sent"
                                if (isinstance(exc, EngineToolError) and exc.outcome == "not_sent")
                                else "unknown"
                            )
                            self._accept(
                                self.journal.finish_tool(
                                    self.owner,
                                    uid,
                                    self.turn.turn_id,
                                    expected_generation=self.turn.generation,
                                    ordinal=len(self.turn.rounds),
                                    call_ordinal=call_ordinal,
                                    request=tool.request,
                                    failure=failure,
                                )
                            )
                            raise
                        self._accept(
                            self.journal.finish_tool(
                                self.owner,
                                uid,
                                self.turn.turn_id,
                                expected_generation=self.turn.generation,
                                ordinal=len(self.turn.rounds),
                                call_ordinal=call_ordinal,
                                request=tool.request,
                                result=result,
                            )
                        )
                        if self.turn.state not in {"ready", "tools_pending"}:
                            raise ProviderProtocolError("agent tool result requires attention")

    def _next_after_capacity(self, exc):
        if (
            self.plan is None or not isinstance(exc, AllProvidersExhaustedError)
            or exc.capacity_scope not in {"model", "account", "unknown"}
            or self.turn.state != "held_transport"
            or self.turn.rounds[-1].state != "failed"
            or self.turn.rounds[-1].tools
        ):
            return False
        signal = CapacitySignal(exc.capacity_scope, exc.failure_class, exc.retry_after)
        self.exhaustion += (signal.exhaustion(self.context.model_selection),)
        candidate = self.plan.next_candidate(
            self.owner, self.context.universe_dir.name, self.exhaustion,
        )
        if candidate is None:
            return False
        self.context = replace(self.context, model_selection=candidate)
        self.retrying_capacity = True
        return True

    def close_quiescent(self):
        if self.turn is not None and self.turn.state == "ready":
            self._accept(
                self.journal.abandon(
                    self.owner,
                    self.context.universe_dir.name,
                    self.turn.turn_id,
                    expected_generation=self.turn.generation,
                )
            )
