"""Bounded native JSON-RPC metadata transport, never a writer or host session.

Only registered metadata methods are sent. The caller supplies an owned
credential snapshot environment and clean cwd, and retains authority checks.
No thread/turn, implicit inference, shell, stderr relay or partial catalogue.
"""

import asyncio
import json
import logging
import os
import signal
from dataclasses import dataclass
from datetime import datetime, timezone

from tinyassets.exceptions import ProviderError
from tinyassets.providers.native_catalogue import NativeCatalogue, NativeModel

_MAX_BYTES = 4 * 1024 * 1024
_MAX_MODELS = 4096
_MAX_PAGES = 64
_REAP_TIMEOUT = 1
_log = logging.getLogger(__name__)


async def _close_metadata_process(proc):
    """Release this invocation's pipes and process group, not just its launcher.

    POSIX launchers (including flock) can exit before their inherited-pipe
    children. The group created by start_new_session belongs to this invocation;
    target its original ID directly, never resolve a potentially recycled PID.
    Only ephemeral metadata credentials are supplied to these processes.
    """
    proc.stdin.close()
    try:
        if os.name == "posix":
            # Even a reaped launcher can leave a live group holding our pipes.
            os.killpg(proc.pid, signal.SIGKILL)
        elif proc.returncode is None:
            proc.kill()
    except ProcessLookupError:
        pass
    try:
        # wait() alone returns early when the launcher was already reaped.
        # Observe inherited-pipe EOF too, with the same byte/time ceilings.
        await asyncio.wait_for(
            asyncio.gather(proc.wait(), proc.stdout.read(_MAX_BYTES + 1)),
            timeout=_REAP_TIMEOUT,
        )
    except TimeoutError:
        # An executor that escapes its session must not wedge metadata reads.
        # Closing our pipe ends also releases transport references on the loop.
        _log.warning("native metadata process cleanup exceeded its bound")
    finally:
        # Also synchronous on a second cancellation during reaping.
        proc._transport.close()


@dataclass(frozen=True, slots=True)
class NativeJsonRpcProtocol:
    """Trusted executor metadata contract, not user-supplied executable authority."""

    list_method: str
    items_key: str
    model_key: str
    default_key: str
    modalities_key: str
    hidden_key: str
    cursor_key: str | None = None
    cursor_param: str | None = None
    initialize_method: str | None = None
    initialized_notification: str | None = None
    initialize_params_json: str = "{}"
    list_params_json: str = "{}"

    def __post_init__(self):
        required = (self.list_method, self.items_key, self.model_key, self.default_key,
                    self.modalities_key, self.hidden_key)
        optional = (self.cursor_key, self.cursor_param, self.initialize_method,
                    self.initialized_notification)
        if (any(type(key) is not str or not key or len(key) > 200 for key in required)
                or any(key is not None and (type(key) is not str or not key or len(key) > 200)
                       for key in optional)
                or (self.cursor_key is None) != (self.cursor_param is None)):
            raise ValueError("invalid native metadata protocol fields")
        for params in (self.initialize_params_json, self.list_params_json):
            if type(params) is not str or type(json.loads(params)) is not dict:
                raise ValueError("invalid native metadata protocol parameters")


def parse_model_page(result, protocol):
    if type(result) is not dict or type(result.get(protocol.items_key)) is not list:
        raise ValueError("invalid native model page")
    cursor = result.get(protocol.cursor_key) if protocol.cursor_key is not None else None
    if cursor is not None and (type(cursor) is not str or not cursor or len(cursor) > 4096):
        raise ValueError("invalid native model cursor")
    models, defaults = [], []
    for row in result[protocol.items_key]:
        if type(row) is not dict or type(row.get(protocol.default_key, False)) is not bool:
            raise ValueError("invalid native model entry")
        # Only the registered execution-ID field is used, never a display label.
        # Missing modalities remain unknown, not fabricated account evidence.
        modalities = row.get(protocol.modalities_key, [])
        if type(modalities) is not list or any(type(item) is not str for item in modalities):
            raise ValueError("invalid native input modalities")
        model = NativeModel(row.get(protocol.model_key), frozenset(modalities),
                            row.get(protocol.hidden_key, False))
        models.append(model)
        if row.get(protocol.default_key, False):
            defaults.append(model.model_id)
    return models, defaults, cursor


async def read_native_catalogue(argv, *, protocol, env, cwd, timeout=30, spawn_kwargs=None):
    """Read the complete bounded list or fail with sanitized fixed prose.

    Resource ceilings are transport guards, never silent list truncation. New
    optional fields and notifications are tolerated; invalid required facts,
    duplicate models, repeated cursors and upstream errors refuse the result.
    """
    proc = None
    try:
        if type(protocol) is not NativeJsonRpcProtocol:
            raise ValueError("native metadata requires a registered protocol")
        process_options = dict(spawn_kwargs or {})
        if os.name == "posix":
            # Transport-owned isolation cannot be disabled by an adapter.
            process_options["start_new_session"] = True
        async with asyncio.timeout(timeout):
            proc = await asyncio.create_subprocess_exec(
                *argv, env=env, cwd=cwd, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                limit=_MAX_BYTES, **process_options,
            )
            consumed = 0

            async def send(message):
                proc.stdin.write((json.dumps(message, separators=(",", ":")) + "\n").encode())
                await proc.stdin.drain()

            async def response(request_id):
                nonlocal consumed
                while True:
                    line = await proc.stdout.readline()
                    consumed += len(line)
                    if not line or consumed > _MAX_BYTES:
                        raise ValueError("native discovery incomplete or oversized")
                    message = json.loads(line)
                    if type(message) is not dict:
                        raise ValueError("invalid native discovery envelope")
                    if "id" not in message and type(message.get("method")) is str:
                        continue
                    if (type(message.get("id")) is not int or message["id"] != request_id
                            or "error" in message or type(message.get("result")) is not dict):
                        raise ValueError("unexpected native discovery response")
                    return message["result"]

            if protocol.initialize_method is not None:
                await send({"method": protocol.initialize_method, "id": 0,
                            "params": json.loads(protocol.initialize_params_json)})
                await response(0)
            if protocol.initialized_notification is not None:
                await send({"method": protocol.initialized_notification, "params": {}})
            models, defaults, cursors = [], [], set()
            cursor = None
            for request_id in range(1, _MAX_PAGES + 1):
                params = json.loads(protocol.list_params_json)
                if cursor is not None:
                    params[protocol.cursor_param] = cursor
                await send({"method": protocol.list_method, "id": request_id, "params": params})
                page, recommended, cursor = parse_model_page(await response(request_id), protocol)
                models.extend(page)
                defaults.extend(recommended)
                if len(models) > _MAX_MODELS or len(defaults) > 1:
                    raise ValueError("native catalogue limit or conflicting defaults")
                if cursor is None:
                    return NativeCatalogue(
                        tuple(models), defaults[0] if defaults else None,
                        datetime.now(timezone.utc),
                    )
                if cursor in cursors:
                    raise ValueError("native catalogue cursor repeated")
                cursors.add(cursor)
            raise ValueError("native catalogue page limit exceeded")
    except (OSError, ValueError, TimeoutError, asyncio.LimitOverrunError):
        # Never relay process output, errors, paths or account material.
        raise ProviderError("native model discovery unavailable") from None
    finally:
        if proc is not None:
            await _close_metadata_process(proc)
