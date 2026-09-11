"""The ``api_key_http`` compute executor — run inference on an open, user-registered
provider over the credential-blind outbound proxy.

A :class:`~tinyassets.providers.base.BaseProvider` so the existing node-execution /
serving / router machinery consumes it unchanged (an agent is just a node — host
decision 2026-08-22). It composes:

- a :class:`~tinyassets.providers.definition.ProviderDefinition` (``api_key_http``):
  ``protocol`` selects the encoder; ``model`` is the request model; ``ref`` is the
  ``grant_id`` of the ``ConnectionLedger`` connection the owner registered (the
  connection carries the endpoint allow-list + the vault ``credential_ref``);
- the protocol encoders (``openai_chat`` / ``anthropic_messages``) to build the
  request body + path and decode the response — **never a vendor SDK on an arbitrary
  ``base_url``** (that would bypass SSRF + the credential-blind proxy);
- the outbound substrate's ``resolve_exact_scoped_proxy`` +
  ``proxy.request`` — the SAME SSRF-hardened, credential-blind broker worker that
  ``authenticated_external_call`` uses. The secret is applied inside the worker; it
  never exists in this process.

**Authorization = the connection grant alone (host decision 2026-08-22).** Running
inference on the universe's own granted compute is its core function, so — unlike an
outbound *effect* — this path does NOT require the per-destination effector consent
or the ``TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED`` effects flag. It DOES keep
every credential/network guard: the grant-identity gate (``resolve_exact_scoped_proxy``
re-checks grant.universe / owner / connection / not-revoked), the endpoint allow-list,
and SSRF + credential-blindness inside the worker. The universe-isolation gate
(grant bound to the RUNNING universe) is enforced here up front AND by the resolver.
Fail loud — never fabricate an empty completion (Hard Rule #8).
"""

from __future__ import annotations

import asyncio
import contextvars
import functools
import json
import logging
import time
from pathlib import Path
from typing import Any

from tinyassets.exceptions import (
    ProviderOverloadedError,
    ProviderProtocolError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)
from tinyassets.providers.base import BaseProvider, ModelConfig, ProviderResponse
from tinyassets.providers.definition import ProviderDefinition
from tinyassets.providers.protocol_encoders import ENCODERS, ProtocolDecodeError, reported_model

_LOG = logging.getLogger(__name__)


def _single_host(view: Any) -> str:
    """The connection's single allowlisted host. A compute connection targets one
    provider endpoint; an ambiguous (multi-host) or hostless connection is refused
    rather than guessed."""
    hosts = {
        ep.host for ep in getattr(view, "allowed_endpoints", ()) or () if getattr(ep, "host", "")
    }
    if len(hosts) == 1:
        return next(iter(hosts))
    raise ProviderUnavailableError("compute connection must have exactly one allowlisted host")


def _declared_path(view: Any) -> str:
    """The connection's single concrete POST path, or "" if it declares none.

    The user's own endpoint URL is what they granted, so it is what we must call.
    Before this, the grant carried the user's path (``/custom/chat``) while the
    encoder called the protocol's canonical one (``/v1/chat/completions``), and
    the broker refused the mismatch — every endpoint whose path was not the
    canonical one was registerable but could never serve.

    Read-only catalogue/account paths are not inference destinations and must
    not make a custom POST path ambiguous. A template (one containing a ``{``
    placeholder) is not concrete, and several POST paths remain ambiguous; both
    fall back to the protocol path, which the broker must still authorize.
    """
    paths = {
        str(getattr(ep, "path_template", "") or "")
        for ep in getattr(view, "allowed_endpoints", ()) or ()
        if "POST" in (getattr(ep, "methods", ()) or ())
        and str(getattr(ep, "path_template", "") or "")
    }
    if len(paths) != 1:
        return ""
    path = next(iter(paths))
    return "" if "{" in path else path


def _coerce_status(value: Any) -> int | None:
    # A well-formed proxy envelope carries an INT status. Reject floats/bools/
    # non-digit strings (Codex review): int(200.9) == 200 would let a malformed
    # envelope pass as success. bool is an int subclass, so exclude it explicitly.
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


class ApiKeyHttpProvider(BaseProvider):
    """Compute over a user-registered http provider, via the credential-blind proxy."""

    def __init__(
        self, definition: ProviderDefinition, *, proxy_override: Any | None = None
    ) -> None:
        if definition.access_method != "api_key_http":
            raise ValueError("ApiKeyHttpProvider requires an api_key_http definition")
        if definition.protocol not in ENCODERS:
            raise ValueError(f"unsupported api_key_http protocol: {definition.protocol}")
        self._definition = definition
        self._proxy_override = proxy_override
        self._encode, self._decode = ENCODERS[definition.protocol]
        # Instance-level identity (BaseProvider declares class attrs; set per-instance
        # so distinct registered providers are distinguishable in telemetry/diversity).
        self.name = f"api_key_http:{definition.id}"
        self.family = f"api:{definition.protocol}"
        self.model = definition.model

    @classmethod
    def is_available(cls) -> bool:
        # Availability is per-call (does the grant resolve?), not a binary probe.
        return True

    def _resolve_proxy(
        self,
        *,
        db_path: Path,
        universe_id: str,
        grant_id: str,
        connection_id: str,
        owner_user_id: str,
    ) -> Any:
        if self._proxy_override is not None:
            return self._proxy_override
        from tinyassets.storage.outbound_connections import ConnectionLedger

        ledger = ConnectionLedger(db_path, verify_authenticated_principal=lambda: owner_user_id)
        return ledger.resolve_exact_scoped_proxy(
            universe_id=universe_id, grant_id=grant_id, connection_id=connection_id
        )

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        # An executor Future (not a Task wrapping to_thread) survives the
        # cancel-all-Tasks phase of asyncio.run teardown. Shield alone would
        # not protect a to_thread Task from being cancelled directly there.
        context = contextvars.copy_context()
        operation = functools.partial(
            self._complete_sync,
            prompt,
            system,
            config,
            universe_dir=universe_dir,
        )
        worker = asyncio.get_running_loop().run_in_executor(None, context.run, operation)
        cancellation = None
        while True:
            try:
                response = await asyncio.shield(worker)
            except asyncio.CancelledError as exc:
                # Only this scope owns the Future; cancelling the calling task
                # never cancels the underlying synchronous request. Preserve the
                # caller's cancellation across success, failure and repeated cancels.
                cancellation = cancellation or exc
                if worker.cancelled():
                    raise cancellation
            except BaseException:
                if cancellation is not None:
                    raise cancellation from None
                raise
            else:
                if cancellation is not None:
                    raise cancellation
                return response

    def _complete_sync(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        if universe_dir is None:
            raise ProviderUnavailableError(
                "api_key_http compute requires a universe context (universe_dir)"
            )
        from tinyassets.storage.outbound_connections import (
            ConnectionLedger,
            GrantResolutionError,
        )

        universe_dir = Path(universe_dir)
        db_path = universe_dir.parent / "outbound.db"
        universe_id = universe_dir.name
        grant_id = self._definition.ref

        # Grant read + universe-isolation gate (belt; resolver re-checks it too).
        read_ledger = ConnectionLedger(db_path)
        grant = read_ledger.get_grant(grant_id)
        if grant is None or getattr(grant, "revoked_at", None) is not None:
            raise ProviderUnavailableError(f"compute grant {grant_id} is absent or revoked")
        if getattr(grant, "universe_id", "") != universe_id:
            raise ProviderUnavailableError("compute grant is not bound to the running universe")
        connection_id = grant.connection_id
        owner_user_id = grant.owner_user_id
        view = read_ledger.get_connection_view(connection_id)
        if view is None:
            raise ProviderUnavailableError("compute connection resource is absent")
        host = _single_host(view)

        selection = getattr(config, "selected_model", None)
        agent_request = getattr(config, "agent_request", None)
        if selection is not None:
            from tinyassets.providers.discovery_protocols import discovery_protocol

            contract = discovery_protocol(selection.discovery_protocol)
            if (
                selection.provider != self.name
                or contract.inference_protocol != self._definition.protocol
            ):
                raise ProviderUnavailableError("selected model does not match the compute source")
            if config.engine_mcp_enabled and agent_request is None:
                raise ProviderUnavailableError(
                    "selected HTTP agent tool execution is not implemented yet"
                )
        if agent_request is not None:
            from tinyassets.providers.agent_inference import AgentInferenceRequest
            from tinyassets.providers.protocol_encoders import agent_codec_for

            agent_codec = agent_codec_for(self._definition.protocol)
            if (type(agent_request) is not AgentInferenceRequest or selection is None
                    or not config.engine_mcp_enabled
                    or agent_codec is None):
                raise ProviderUnavailableError("HTTP agent inference requires admitted selection")
            protocol_path, body = agent_request.encode(
                prompt=prompt, system=system, selection=selection,
                temperature=config.temperature, max_tokens=config.max_tokens,
            )
        else:
            protocol_path, body = self._encode(
                prompt=prompt,
                system=system,
                model=self.model if selection is None else selection.model_id,
                temperature=getattr(config, "temperature", None),
                max_tokens=getattr(config, "max_tokens", None),
            )
            if selection is not None:
                body = contract.constrain_inference(body, selection.cost_caps)
        # The path the user granted wins over the protocol's canonical one: the
        # broker allowlists what they registered, so calling anything else is a
        # guaranteed refusal. The encoder still owns the BODY shape.
        path = _declared_path(view) or protocol_path
        # Protocol-static, credential-FREE headers (e.g. anthropic-version, required
        # by the Anthropic Messages API or it 400s). The api key is NOT here — the
        # broker applies it from the connection's auth_scheme (x-api-key for Claude).
        from tinyassets.providers.protocol_encoders import static_headers_for

        wire_request: dict[str, Any] = {"url": f"https://{host}{path}", "body": body}
        static_headers = static_headers_for(self._definition.protocol)
        if static_headers:
            wire_request["headers"] = static_headers

        started = time.monotonic()
        try:
            proxy = self._resolve_proxy(
                db_path=db_path,
                universe_id=universe_id,
                grant_id=grant_id,
                connection_id=connection_id,
                owner_user_id=owner_user_id,
            )
            try:
                result = proxy.request("POST", wire_request)
                # Inference latency excludes the owned worker's cleanup/join.
                latency_ms = (time.monotonic() - started) * 1000.0
            finally:
                if self._proxy_override is None:
                    try:
                        proxy.close()
                    except Exception:  # noqa: BLE001 - preserve result and secret-free diagnostics
                        _LOG.warning("HTTP inference proxy cleanup failed")
        except GrantResolutionError as exc:
            raise ProviderUnavailableError(
                f"compute grant resolution failed: {exc}"
            ) from exc

        if not isinstance(result, dict):
            if agent_request is not None:
                raise ProviderProtocolError("agent inference outcome is unknown")
            raise ProviderUnavailableError("compute proxy returned no response")
        status = _coerce_status(result.get("status"))
        if status is None:
            if agent_request is not None:
                # The proxy was called. No status does not prove no remote work;
                # hold the full reservation rather than report a free attempt.
                raise ProviderProtocolError("agent inference outcome is unknown")
            # A sanitized error envelope (no HTTP status) — the worker refused or
            # the network failed. Fail loud with the secret-free reason.
            reason = str(result.get("reason") or result.get("error") or "unknown")
            raise ProviderUnavailableError(f"compute call failed: {reason}")
        if agent_request is not None and contract.capacity_decoder is not None:
            from tinyassets.exceptions import SelectedModelCapacityError

            capacity = contract.capacity_decoder(status, result.get("headers"))
            if capacity is not None:
                raise SelectedModelCapacityError(capacity)
        if status == 429:
            raise ProviderRateLimitedError("compute provider rate limited (429)")
        if 500 <= status < 600:
            raise ProviderOverloadedError(f"compute provider error (HTTP {status})")
        if not (200 <= status < 300):
            raise ProviderProtocolError(f"compute provider returned HTTP {status}")

        body_str = result.get("body")
        if not isinstance(body_str, str) or not body_str:
            raise ProviderProtocolError("compute response had an empty body")
        try:
            if agent_request is not None:
                from tinyassets.providers.agent_chat_codec import _object

                parsed = _object(body_str)
            else:
                parsed = json.loads(body_str)
        except (TypeError, ValueError) as exc:
            raise ProviderProtocolError(f"compute response was not JSON: {exc}") from exc
        agent_reply = None
        cost = None
        try:
            if agent_request is not None:
                agent_reply = agent_codec.decode(
                    parsed, source_ref=selection.provider, requested_model=selection.model_id,
                    tool_names=frozenset(
                        item["function"]["name"] for item in agent_request.tools()
                    ),
                )
                text = agent_reply.text or ""
                in_tok, out_tok = agent_reply.input_tokens, agent_reply.output_tokens
                if contract.usage_decoder is not None:
                    cost = contract.usage_decoder(body_str)
            else:
                text, in_tok, out_tok = self._decode(parsed)
        except ProtocolDecodeError as exc:
            raise ProviderProtocolError(str(exc)) from exc

        return ProviderResponse(
            text=text,
            provider=self.name,
            model=reported_model(parsed),
            reported_model=reported_model(parsed),
            family=self.family,
            latency_ms=latency_ms,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_microunits=cost,
            agent_reply=agent_reply,
        )
