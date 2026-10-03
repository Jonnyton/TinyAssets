"""The thin loop for served chat, and the switch that selects it.

The owner's account setting ``agent_loop=thin`` routes an HTTP chat turn through the
thin loop: the same :class:`AgentTurnCoordinator` and journal, with its tools
opened by :func:`~.tool_session.open_loop_tools` -- box tools on a handle bound
at turn start, owner reads in the loop, the rest on the engine route. Accounts
default to ``engine``; unresolved owners keep today's path. Native (CLI) turns
are untouched either way:
command adapters and file-OAuth CLIs keep running as CLIs (D6).

The switch is a temporary rollout aid: once the thin loop is proven it becomes
the only path for HTTP turns and the switch is deleted (change
``control-plane-agent-loop`` task 3.4). It is opt-in and fails loudly: with
the thin loop selected and no box provider configured, a turn that is granted
a box tool is refused before anything runs, never quietly served by the tool
jail instead.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from tinyassets.agent_loop.box_tools import BOX_ROOT, BoxExecutor, BoxTools
from tinyassets.agent_loop.owner_reads import OWNER_READ_TOOLS
from tinyassets.agent_loop.tool_session import open_loop_tools
from tinyassets.exceptions import ProviderAuthorityHeldError
from tinyassets.interactive_http_agent import ServedChatAgentAdapter
from tinyassets.provider_assignment import check_served_agent_tool_authority
from tinyassets.served_tools import granted_tools
from tinyassets.storage.account_agent_loop import account_agent_loop

_LOG = logging.getLogger(__name__)


def thin_loop_selected(universe_context) -> bool:
    """Whether this turn takes the thin loop, per the owner's account setting.

    An owner we cannot resolve keeps the engine path -- the safe direction --
    but it is not the same as an owner who chose ``engine``, so it says so in
    the log rather than defaulting silently.
    """
    try:
        owner = check_served_agent_tool_authority(universe_context)
    except (PermissionError, ProviderAuthorityHeldError) as exc:
        _LOG.warning(
            "thin-loop switch: no served-agent tool authority for %s, keeping the "
            "engine path: %s: %s",
            getattr(universe_context, "universe_dir", "<no universe>"),
            type(exc).__name__, exc,
        )
        return False
    if not owner:
        _LOG.warning(
            "thin-loop switch: the owner of %s did not resolve to an account, "
            "keeping the engine path",
            getattr(universe_context, "universe_dir", "<no universe>"),
        )
        return False
    return account_agent_loop(
        universe_context.universe_dir.parent, owner_user_id=owner,
    ) == "thin"


_box_lock = threading.Lock()
_box_provider: Any = None


def configure_box_provider(provider: Any) -> None:
    """Install the process's ``BoxProvider`` (D2, :mod:`tinyassets.boxes`)."""
    global _box_provider
    with _box_lock:
        _box_provider = provider


def configured_box_provider() -> Any:
    with _box_lock:
        return _box_provider


def bind_turn_box(*, owner: str, command_center: str, turn_id: str) -> tuple[BoxTools, str]:
    """Bind the turn's box ONCE; every tool call of the turn uses this handle.

    Binding never wakes the box; its first execution does.
    """
    provider = configured_box_provider()
    if provider is None:
        raise LookupError("no box provider is configured")
    handle = provider.bind(command_center, account_id=owner, turn_id=turn_id)
    return BoxTools(BoxExecutor(provider, handle), root=BOX_ROOT), BOX_ROOT


class ThinLoopChatAdapter(ServedChatAgentAdapter):
    """Served chat on the thin loop; admission and identity are unchanged."""

    def open_tools(self, coordinator, *, timeout):
        owner = coordinator.owner
        universe_dir = coordinator.context.universe_dir
        turn_id = coordinator.turn.turn_id
        provider = configured_box_provider()
        return open_loop_tools(
            granted=granted_tools(coordinator.config),
            loop_reads=OWNER_READ_TOOLS,
            bind_box=None if provider is None else (
                lambda: bind_turn_box(owner=owner, command_center=universe_dir.name,
                                      turn_id=turn_id)
            ),
            owner=owner,
            universe_dir=universe_dir,
            engine_identity=lambda: self.engine_identity(coordinator.context,
                                                         coordinator.config),
            timeout=timeout,
            **coordinator.steering(),
        )
