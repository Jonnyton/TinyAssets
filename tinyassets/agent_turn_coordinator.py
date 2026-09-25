"""Shared agent progress; the injected adapter owns admission and identity.

A journal is progress, never authority or permission to replay actions.
Selected native agents and engine-managed inference share one finite coordinator.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AsyncExitStack
from dataclasses import replace

from tinyassets.engine_tool_client import EngineToolError, open_engine_tools
from tinyassets.exceptions import (
    AllProvidersExhaustedError,
    ProviderAuthorityHeldError,
    ProviderProtocolError,
)
from tinyassets.providers import agent_chat_codec as codec
from tinyassets.providers.agent_capacity_boundary import capacity_boundary
from tinyassets.providers.agent_inference import AgentInferenceRequest
from tinyassets.providers.agent_model_plan import AgentModelPlan
from tinyassets.providers.native_agent_input import render_native_input
from tinyassets.served_tools import SERVED_ENGINE_MCP_TOOLS
from tinyassets.storage.agent_native_records import NativeInput, NativeTerminal
from tinyassets.storage.agent_turn_journal import AgentTurnJournal, JournalUnavailable
from tinyassets.storage.agent_turn_records import load_result

_LOG = logging.getLogger(__name__)


class AgentTurnCoordinator:
    """One in-process turn; no crash resurrection or automatic effect replay."""

    def __init__(self, *, adapter, router, prompt, system, universe_context, config):
        self.adapter = adapter
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
        self.visited = set()
        self.execution_kind = None
        self.native_input = None
        # Narrowed sibling retries used so far, and the diagnostics of the
        # rounds they replaced -- a turn that tried four models must not report
        # one attempt (live 2026-09-25 read "attempts=1" for a dead end).
        self.free_sibling_retries = 0
        self.spent_attempts = []

    def _check_scope(self):
        owner = self.adapter.check(self.context, self.config)
        if self.owner is not None and owner != self.owner:
            raise ProviderAuthorityHeldError("interactive agent owner changed")
        return owner

    def _has_candidate_order(self):
        return self.plan is not None or bool(getattr(self.adapter, "has_candidate_order", False))

    def _next_candidate(self):
        if getattr(self.adapter, "has_candidate_order", False):
            return self.adapter.next_candidate(
                self.owner, self.context.universe_dir.name, self.exhaustion,
            )
        return self.plan.next_candidate(self.owner, self.context.universe_dir.name, self.exhaustion)

    def _accept(self, transition):
        if transition.status != "applied":
            raise JournalUnavailable("agent progress changed; action was not replayed")
        self.turn = transition.snapshot

    def _begin(self, authority, reservation, config):
        candidate = self.adapter.round_input(
            authority, reservation, config, owner=self.owner, context=self.context,
            prompt=self.prompt, system=self.system, native_input=None, kind="engine_inference",
        )
        self._accept(
            self.journal.begin_round(
                self.owner,
                self.context.universe_dir.name,
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
            if type(previous.candidate) is NativeInput:
                if (type(previous.reply) is NativeTerminal
                        and previous.reply.status == "capacity_no_effects"):
                    continue
                raise JournalUnavailable("native continuation is incomplete")
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

    def _begin_native(self, authority, reservation, config):
        candidate = self.adapter.round_input(
            authority, reservation, config, owner=self.owner, context=self.context,
            prompt=self.prompt, system=self.system, native_input=self.native_input,
            kind="native_agent",
        )
        self._accept(self.journal.begin_round(
            self.owner, self.context.universe_dir.name, self.turn.turn_id,
            expected_generation=self.turn.generation, candidate=candidate,
            after_failed_inference=self.retrying_capacity,
        ))
        self.retrying_capacity = False

    def _finish_native_failure(self, exc):
        terminal = NativeTerminal("indeterminate")
        if isinstance(exc, AllProvidersExhaustedError):
            proofs = getattr(exc, "native_evidence", ())
            boundary = capacity_boundary(
                self.context.model_selection, exc.attempts,
                execution_kind="native_agent", native_evidence=proofs,
            )
            # One claimed native intent corresponds to exactly one executed
            # provider attempt. Never compress several unknown launches to one proof.
            if boundary is not None and boundary.attempted and len(proofs) == 1:
                terminal = NativeTerminal(
                    "capacity_no_effects", evidence=proofs[0],
                    failure_class=boundary.failure_class,
                    capacity_scope=boundary.exhaustion.scope,
                    retry_after_s=boundary.retry_after_s,
                )
        self._accept(self.journal.finish_native(
            self.owner, self.context.universe_dir.name, self.turn.turn_id,
            expected_generation=self.turn.generation, ordinal=len(self.turn.rounds),
            terminal=terminal,
        ))

    def effects_evidence(self):
        """What this turn's own ledger proves ran: ``(effects, stage, ref)``.

        ``none`` only when no tool started and no native agent launched;
        ``some`` once any tool completed; ``unknown`` for anything in flight or
        indeterminate. ``stage`` is ``tool`` only when the last recorded step
        was a tool that did not complete. Read from the journal, never guessed.
        """
        if self.turn is None:
            return "none", None, None
        effects, stage = "none", None
        for position, previous in enumerate(self.turn.rounds):
            last = position == len(self.turn.rounds) - 1
            if type(previous.candidate) is NativeInput:
                if not (type(previous.reply) is NativeTerminal
                        and previous.reply.status == "capacity_no_effects"):
                    effects = "some" if effects == "some" else "unknown"
                continue
            for tool in previous.tools:
                if tool.state == "completed":
                    effects = "some"
                elif tool.state in {"started", "unknown"} and effects == "none":
                    effects = "unknown"
                if last and tool.state in {"started", "unknown", "not_sent"}:
                    stage = "tool"
        return effects, stage, self.turn.turn_id

    async def run(self):
        try:
            return await self._run()
        except BaseException as exc:
            try:
                exc.turn_effects, exc.turn_stage, exc.turn_ref = self.effects_evidence()
                self._carry_spent_attempts(exc)
            except Exception:  # noqa: BLE001 - evidence never replaces the failure
                _LOG.warning("agent turn effects evidence unavailable")
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
        if self._has_candidate_order():
            first = self._next_candidate()
            if first is None:
                raise ProviderAuthorityHeldError("no eligible interactive model remains")
            if self.context.model_selection != first:
                raise ProviderAuthorityHeldError("interactive selection contradicts its plan")
            self._check_scope()
        if self.turn is None:
            self.journal = AgentTurnJournal(self.context.universe_dir.parent)
            self.turn = self.adapter.create_turn(
                self.journal, owner=self.owner, context=self.context,
                prompt=self.prompt, system=self.system, plan=self.plan,
            )
        elif self.turn.state != "ready" or self.turn.rounds:
            raise JournalUnavailable("agent turn cannot be replayed")

        timeout = self.config.stream_timeout_profile().absolute_cap_s
        async with asyncio.timeout(timeout):
            async with AsyncExitStack() as stack:
                engine = None
                while True:
                    self.execution_kind = self.router.selected_agent_execution_kind(
                        self.context.model_selection,
                    )
                    if self.execution_kind == "engine_inference":
                        if engine is None:
                            actor_id, graph_id = self.adapter.engine_identity(
                                self.context, self.config,
                            )
                            engine = await stack.enter_async_context(open_engine_tools(
                                actor_id=actor_id, graph_id=graph_id,
                                enabled_tools=SERVED_ENGINE_MCP_TOOLS, timeout=timeout,
                            ))
                        config = replace(self.config, agent_request=AgentInferenceRequest(
                            tools=codec.tool_definitions(engine.tools), history=self._history(),
                        ))
                        prompt, system, observer = self.prompt, self.system, self._begin
                    else:
                        self.native_input = render_native_input(
                            self.prompt, self.system, self._history(),
                        )
                        prompt, system = self.native_input
                        config = replace(self.config, agent_request=None, selected_model=None)
                        observer = self._begin_native
                    try:
                        response = await self.adapter.infer(
                            router=self.router, prompt=prompt, system=system, config=config,
                            context=self.context, observer=observer, kind=self.execution_kind,
                        )
                    except BaseException as exc:
                        # No engine tool can start before a validated inference
                        # is committed. Preserve failure, never restart this turn.
                        if self.turn.state == "native_started":
                            self._finish_native_failure(exc)
                        elif self.turn.state == "inference_started":
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
                    if self.execution_kind == "native_agent":
                        try:
                            if response.provider != self.context.model_selection.connection_id:
                                raise ProviderProtocolError("native response source changed")
                            terminal = NativeTerminal(
                                "completed", evidence=response.native_evidence,
                                text=response.text, configured_model=response.model,
                                reported_model=response.reported_model or None,
                                input_tokens=response.input_tokens,
                                output_tokens=response.output_tokens,
                            )
                            self._accept(self.journal.finish_native(
                                self.owner, uid, self.turn.turn_id,
                                expected_generation=self.turn.generation,
                                ordinal=len(self.turn.rounds), terminal=terminal,
                                cost_microusd=response.cost_microunits,
                            ))
                        except BaseException as exc:
                            if self.turn.state == "native_started":
                                self._finish_native_failure(exc)
                            raise
                        return response
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

    #: How many times one turn may narrow an UNPROVEN account exhaustion to the
    #: model that actually failed. Small on purpose: the narrowing is a policy
    #: bet that the source's window was per-model, and a bet re-taken without
    #: limit is just hammering. Three covers the live case (a busy free model
    #: with eligible siblings) without turning one message into a sweep.
    MAX_FREE_SIBLING_RETRIES = 3

    def _narrowed(self, boundary):
        """Exclude only the failed MODEL when excluding the account is a guess.

        A source that reported the account, a class that is not a passing
        window, or any source that can spend keeps the conservative exhaustion.
        Only a zero-cost source with an ``unknown`` scope is narrowed, and only
        a bounded number of times per turn. The replacement comes from the SAME
        order under the SAME ceilings, so this can never reach a paid model.

        Returns ``(exhaustion, narrowed)``; ``narrowed`` tells the caller its
        next candidate rests on a guess and must stay inside the same grant.
        """
        from tinyassets.providers.model_capacity import free_sibling_retry

        if self.plan is None or self.free_sibling_retries >= self.MAX_FREE_SIBLING_RETRIES:
            return boundary.exhaustion, False
        if not free_sibling_retry(
            scope=boundary.observed_scope, failure_class=boundary.failure_class,
            cost_caps=self.plan.source_cost_caps(self.context.model_selection.connection_id),
        ):
            return boundary.exhaustion, False
        self.free_sibling_retries += 1
        return replace(boundary.exhaustion, scope="model"), True

    def _next_after_capacity(self, exc):
        if (
            not self._has_candidate_order() or not isinstance(exc, AllProvidersExhaustedError)
            or self.turn.state not in {"ready", "held_transport", "held_native_capacity"}
        ):
            return False
        boundary = capacity_boundary(
            self.context.model_selection, exc.attempts, execution_kind=self.execution_kind,
            native_evidence=(getattr(exc, "native_evidence", ())
                             if self.execution_kind == "native_agent" else ()),
        )
        if boundary is None:
            return False
        failed = self.context.model_selection
        self.visited.add(failed)
        exhaustion, narrowed = self._narrowed(boundary)
        self.exhaustion += (exhaustion,)
        candidate = self._next_candidate()
        if candidate is None or candidate in self.visited:
            return False
        # A narrowed exhaustion is a guess about ONE source's window, never
        # evidence that a different connection sharing its scope is healthy.
        # The conservative account exclusion is what normally proves that, and
        # narrowing removed it, so the retry stays inside the same grant.
        if narrowed and candidate.connection_id != failed.connection_id:
            return False
        # Only engine-inference rounds. A native round's diagnostics are paired
        # positionally with its own ``native_evidence``, and carrying them onto
        # a later exception would leave the two lists mismatched, which
        # ``capacity_boundary`` correctly refuses to read.
        if self.execution_kind == "engine_inference":
            self.spent_attempts += list(exc.attempts or ())
        self.context = replace(self.context, model_selection=candidate)
        self.retrying_capacity = self.turn.state != "ready"
        return True

    def _carry_spent_attempts(self, exc):
        """Prepend the replaced rounds' diagnostics to the failure that escapes.

        Only the last round's exception propagates, so without this a turn that
        tried four models reports one attempt -- and the owner's failure record
        and the server log both describe a dead end that never happened.
        """
        if not self.spent_attempts or not isinstance(exc, AllProvidersExhaustedError):
            return
        attempts = list(exc.attempts or ())
        evidence = getattr(exc, "native_evidence", ())
        # ``native_evidence`` is positional against ``attempts``; a pairing this
        # hop does not recognize is left alone rather than repaired blind.
        if type(evidence) is not tuple or len(evidence) != len(attempts):
            return
        # Every carried round was engine inference, which has no native proof.
        exc.attempts = self.spent_attempts + attempts
        exc.native_evidence = (None,) * len(self.spent_attempts) + evidence

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
