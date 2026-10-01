"""Attach owner-scoped unread observations after the final tool-result bound."""
from __future__ import annotations

import asyncio
import json
from collections import OrderedDict

from fastmcp.server.middleware import Middleware
from mcp.types import TextContent

from tinyassets.conversation_attention import observe, reader_name, returned_page


class ConversationAttention(Middleware):
    def __init__(self):
        super().__init__()
        self._readers = OrderedDict()

    async def on_call_tool(self, context, call_next):
        from tinyassets import engine_mcp_server as server

        message = context.message
        arguments = getattr(message, "arguments", None) or {}
        reading = (
            getattr(message, "name", "") == "read_graph"
            and str(arguments.get("target", "")).strip().lower() == "conversation"
        )
        # Scope comes only from the verified server pins, never tool arguments.
        # Check before AND after the call so a revoked owner sees no count.
        if server._binding_error():
            return await call_next(context)
        try:
            ctx = context.fastmcp_context
            session = ctx.session_id if ctx is not None else None
        except (AttributeError, RuntimeError):
            session = None
        key = (server._ACTOR_ID, server._GRAPH_ID, session)
        selected = reader_name(arguments.get("query", "")) if reading else None
        if session:
            reader = selected or self._readers.get(key) or "session:" + session
            self._readers[key] = reader
            self._readers.move_to_end(key)
            while len(self._readers) > 1024:
                self._readers.popitem(last=False)
        else:
            reader = None

        result = await call_next(context)
        if server._binding_error():
            return result
        if reader is None:
            status = {"available": False, "unread_count": None, "reason": "session_unavailable"}
        else:
            try:
                from tinyassets.api.branches import _base_path
                from tinyassets.shared_self import require_founder_home

                root = require_founder_home(_base_path(), server._GRAPH_ID, server._ACTOR_ID)
                page = (
                    returned_page(list(result.content or ()))
                    if reading and not getattr(result, "is_error", False) else None
                )
                status = await asyncio.to_thread(
                    observe, root, f"principal:{server._ACTOR_ID}", reader, page=page,
                )
            except Exception:
                # Metadata failure must never replace a completed write with a
                # tool error that invites replay. Unknown is not a zero count.
                status = {"available": False, "unread_count": None, "reason": "read_failed"}
        # Preserve every original block and structured result byte-for-byte.
        # This small separate block is not part of the tool's output schema.
        result.content = list(result.content or ()) + [TextContent(
            type="text", text=json.dumps({"conversation_indicator": status}),
        )]
        return result
