"""Record every engine tool call for the owner's live view (harness S4).

``tinyassets.agent_activity`` owns the log. This middleware writes one row when
a call starts and completes it when the call ends, for whichever session the
launch named on its engine route (``engine_steering``). A call with no session
(stdio, an old launch) is not recorded. Recording never fails or delays the
call's own result beyond two small local writes.
"""
from __future__ import annotations

import asyncio
import logging

from fastmcp.server.middleware import Middleware

logger = logging.getLogger(__name__)


def _root():
    from tinyassets.engine_conversation_attention import _scope

    scope = _scope()
    return None if scope is None else scope[0]


def _start(session_key: str, tool: str, arguments) -> tuple | None:
    from tinyassets import agent_activity

    try:
        root = _root()
        if root is None:
            return None
        call_id = agent_activity.started(
            root, session_key, tool, agent_activity.summarize(tool, arguments))
        return root, call_id
    except Exception:  # noqa: BLE001 - the view is never worth a failed call
        logger.warning("tool activity could not be recorded", exc_info=True)
        return None


def _finish(handle, *, ok: bool, error: str = "") -> None:
    from tinyassets import agent_activity

    if handle is None:
        return
    try:
        agent_activity.finished(handle[0], handle[1], ok=ok, error=error)
    except Exception:  # noqa: BLE001
        logger.warning("tool activity could not be completed", exc_info=True)


def _error_text(result) -> str:
    """The first text block of an error result: its real cause."""
    for block in getattr(result, "content", None) or ():
        text = getattr(block, "text", None)
        if isinstance(text, str) and text.strip():
            return text
    return "the tool reported an error"


class ToolActivity(Middleware):
    async def on_call_tool(self, context, call_next):
        from tinyassets.engine_steering import _session_key

        session_key = _session_key()
        if not session_key:
            return await call_next(context)
        message = context.message
        tool = getattr(message, "name", "") or ""
        handle = await asyncio.to_thread(
            _start, session_key, tool, getattr(message, "arguments", None))
        try:
            result = await call_next(context)
        except Exception as exc:
            await asyncio.to_thread(_finish, handle, ok=False, error=str(exc))
            raise
        failed = bool(getattr(result, "is_error", False) or getattr(result, "isError", False))
        await asyncio.to_thread(
            _finish, handle, ok=not failed, error=_error_text(result) if failed else "")
        return result
