"""``/app/api/read`` and ``/app/api/status``: the owner's complete reads.

Both are POST with a JSON object of the domain read's own arguments, so the app
calls them exactly as it called ``read_graph`` / ``get_status`` over MCP, and the
arguments mean the same thing. What differs is only the door: nothing here bounds
the answer (see the package docstring).

A reply is the domain's own JSON document, exactly what the connector's dispatch
produced before any model-door projection, a refusal included
(``{"error": "not_found"}`` and the like). A domain document may carry an
``error`` field as DATA (a failed run's reason), so this door does not guess which
is which. Arguments this door cannot accept are a 4xx. A server failure is a 500
with no detail, never an empty document that reads as "nothing here".
"""

from __future__ import annotations

import inspect
import json
import logging
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, PlainTextResponse

_log = logging.getLogger(__name__)

_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}

#: Bytes an ARGUMENTS object may take. This bounds the request, never the reply:
#: a read's arguments are a handful of ids and numbers.
_MAX_ARGUMENT_BYTES = 16_384


def _allowed_arguments(fn) -> dict[str, tuple[type, ...]]:
    """The domain read's own parameters and the JSON types each accepts.

    Derived from the signature, so the owner door accepts exactly what the
    domain read takes and cannot drift into a second argument contract.
    """
    allowed: dict[str, tuple[type, ...]] = {}
    for name, param in inspect.signature(fn).parameters.items():
        default = param.default
        if isinstance(default, bool):
            allowed[name] = (bool,)
        elif isinstance(default, int):
            allowed[name] = (int,)
        elif isinstance(default, str):
            allowed[name] = (str,)
        elif default is None:
            # ``int | None`` parameters (a cursor, a page size the caller names).
            allowed[name] = (int, type(None))
        else:
            raise TypeError(f"owner door cannot type parameter {name!r}")
    return allowed


def _validated(document: object, allowed: dict[str, tuple[type, ...]]) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ValueError("the body must be a JSON object of read arguments")
    unknown = sorted(set(document) - set(allowed))
    if unknown:
        raise ValueError(f"unknown argument(s): {', '.join(unknown)}")
    for name, value in document.items():
        types = allowed[name]
        # bool is an int in Python; a JSON true is never a number here.
        if isinstance(value, bool) and bool not in types:
            raise ValueError(f"{name} has the wrong type")
        if not isinstance(value, types):
            raise ValueError(f"{name} has the wrong type")
    return dict(document)


async def _serve(request, read, allowed):
    from tinyassets import onboarding
    from tinyassets.auth.middleware import current_identity, identity_context

    if not onboarding.onboarding_enabled():
        return PlainTextResponse("Not Found", 404, headers=_HEADERS)
    denied = onboarding._app_identity_required()
    if denied is not None:
        denied.headers.update(_HEADERS)
        return denied
    ctype = str(request.headers.get("content-type", "")).split(";")[0].strip().lower()
    if ctype != "application/json":
        return JSONResponse({"error": "json_required"}, 415, headers=_HEADERS)
    raw = await onboarding._read_bounded_body(request, _MAX_ARGUMENT_BYTES)
    if raw is None:
        return JSONResponse({"error": "arguments_too_large"}, 413, headers=_HEADERS)
    try:
        arguments = _validated(json.loads(raw or b"{}"), allowed)
    except (ValueError, UnicodeError) as exc:
        return JSONResponse({"error": "invalid_arguments", "detail": str(exc)}, 400,
                            headers=_HEADERS)
    identity = current_identity()

    def run():
        with identity_context(identity):
            return read(**arguments)

    try:
        result = await run_in_threadpool(run)
    except Exception:  # noqa: BLE001 - no storage or credential detail in a reply
        _log.exception("owner door: %s failed", getattr(read, "__name__", "read"))
        return JSONResponse({"error": "owner_read_failed"}, 500, headers=_HEADERS)
    document = json.loads(result) if isinstance(result, str) else result
    if not isinstance(document, dict):
        document = {"result": document}
    return JSONResponse(document, 200, headers=_HEADERS)


def _graph_read():
    from tinyassets.api.graph_reads import read_graph

    return read_graph


def _status_read():
    from tinyassets.api.status import get_status

    return get_status


async def handle_read(request):
    """``read_graph`` for the owner: the same targets, the complete document."""
    read = _graph_read()
    return await _serve(request, read, _allowed_arguments(read))


async def handle_status(request):
    """``get_status`` for the owner, with the conversation page cursor."""
    read = _status_read()
    return await _serve(request, read, _allowed_arguments(read))


def owner_door_routes() -> list[Any]:
    from starlette.routing import Route

    return [
        Route("/app/api/read", handle_read, methods=["POST"]),
        Route("/app/api/status", handle_status, methods=["POST"]),
    ]
