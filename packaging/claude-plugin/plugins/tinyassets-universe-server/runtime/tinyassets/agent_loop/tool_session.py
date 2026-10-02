"""One turn's tools, routed by name to exactly one place.

Same surface as :class:`tinyassets.engine_tool_client.EngineToolSession`
(``tools`` plus ``call``), so :class:`AgentTurnCoordinator` journals intent,
dispatches and records outcomes exactly as it does for the engine route. The
difference is that ``call`` takes the journal position as ``op_id``
(``takes_op_id``), which the box needs to make a lost reply safe to ask about.

Routing, decided once when the session opens and never by the model:

* ``read``/``write``/``edit``/``bash`` -> the turn's bound box (:mod:`.box_tools`);
* ``history``/``activity`` -> the loop itself, read-only (:mod:`.owner_reads`);
* every other granted served tool -> the existing engine route, opened only if
  the grant names one. Its gates (owner rules, auto-review, effect consent)
  stay where they already are.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

from mcp.types import CallToolResult, TextContent, Tool

from tinyassets.agent_loop.box_tools import (
    BOX_ROOT,
    BOX_TOOLS,
    BoxOperationRefused,
    BoxTools,
    box_tool_definitions,
)
from tinyassets.agent_loop.owner_reads import OWNER_READ_TOOLS, OwnerReads, owner_read_definitions
from tinyassets.engine_tool_client import EngineToolError, open_engine_tools


def _text_result(text: str, *, is_error: bool = False) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=text)],
                          structuredContent=None, isError=is_error)


def _tool(name: str, definition: dict[str, Any]) -> Tool:
    return Tool(name=name, description=definition["description"],
                inputSchema=definition["inputSchema"])


class LoopToolSession:
    """Routes one turn's tool calls; constructed only by :func:`open_loop_tools`."""

    takes_op_id = True

    def __init__(self, *, tools: tuple[Tool, ...], box: BoxTools | None,
                 reads: OwnerReads | None, engine: Any | None) -> None:
        self._tools = tools
        self._box = box
        self._reads = reads
        self._engine = engine
        self._names = frozenset(tool.name for tool in tools)

    @property
    def tools(self) -> tuple[Tool, ...]:
        return tuple(tool.model_copy(deep=True) for tool in self._tools)

    async def call(self, name: str, arguments: dict[str, Any], *, op_id: str) -> CallToolResult:
        if name not in self._names or not isinstance(arguments, dict):
            raise EngineToolError("loop_tool_not_allowed")
        if name in BOX_TOOLS:
            try:
                return _text_result(await self._box.call(name, op_id, arguments))
            except BoxOperationRefused:
                # Refused before the operation existed: provably nothing ran.
                raise EngineToolError("box_operation_refused") from None
        if name in OWNER_READ_TOOLS:
            try:
                text = await asyncio.to_thread(self._reads.call, name, arguments)
            except Exception:  # noqa: BLE001 - a failed read has no effect to hold
                return _text_result(json.dumps({"error": f"{name}_read_failed"}),
                                    is_error=True)
            return _text_result(text)
        return await self._engine.call(name, arguments)


@asynccontextmanager
async def open_loop_tools(
    *,
    granted: Sequence[str],
    loop_reads: Sequence[str],
    bind_box: Callable[[], tuple[BoxTools, str]] | None,
    owner: str,
    universe_dir: Path,
    engine_identity: Callable[[], tuple[str, str]],
    timeout: float,
) -> AsyncIterator[LoopToolSession]:
    """Open the turn's tools. ``bind_box`` binds the handle once, here.

    ``granted`` is the turn's served-tool grant in canonical order;
    ``loop_reads`` the owner reads it may use. A granted box tool with no box
    to bind is refused loudly rather than silently dropped from the turn.
    """
    granted = tuple(granted)
    box_names = tuple(name for name in granted if name in BOX_TOOLS)
    engine_names = tuple(name for name in granted if name not in BOX_TOOLS)
    reads = tuple(name for name in OWNER_READ_TOOLS if name in tuple(loop_reads))
    if box_names and bind_box is None:
        raise EngineToolError("box_unavailable")
    async with AsyncExitStack() as stack:
        box, root = (None, BOX_ROOT)
        if box_names:
            box, root = await asyncio.to_thread(bind_box)
        engine = None
        engine_tools: dict[str, Tool] = {}
        if engine_names:
            actor_id, graph_id = engine_identity()
            engine = await stack.enter_async_context(open_engine_tools(
                actor_id=actor_id, graph_id=graph_id, enabled_tools=engine_names,
                timeout=timeout,
            ))
            engine_tools = {tool.name: tool for tool in engine.tools}
        box_definitions = box_tool_definitions(root)
        read_definitions = owner_read_definitions()
        tools = tuple(
            _tool(name, box_definitions[name]) if name in BOX_TOOLS else engine_tools[name]
            for name in granted
        ) + tuple(_tool(name, read_definitions[name]) for name in reads)
        if not tools:
            raise EngineToolError("loop_tools_empty")
        yield LoopToolSession(
            tools=tools, box=box,
            reads=OwnerReads(owner=owner, universe_dir=universe_dir) if reads else None,
            engine=engine,
        )
