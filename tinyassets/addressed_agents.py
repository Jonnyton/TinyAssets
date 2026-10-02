"""Which of the owner's agents a conversation turn addresses (harness §4.18).

A command center can hold many agents: the seeded main agent and any custom
agent the owner binds into it. The owner talks to whichever one they address.
``"main"`` (or nothing) is the seeded agent and keeps every existing key; any
other ``agent_id`` is one of the owner's own ``agent_bindings`` in that
universe, and its turn runs with that agent's own instructions on its own
thread while reading and writing the SAME brain.

The selector never stands in for ownership. The caller has already bound the
authenticated owner and the universe; this only resolves an id INSIDE that
scope, and an id that is not the owner's own agent there is refused by name,
never quietly answered by the main agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MAIN_AGENT = "main"

#: Configurations that are not agents a person talks to: the conversation-design
#: installation (the app's ``app_experience`` row) answers the MAIN thread.
_NOT_AN_AGENT_ROLES = frozenset({"app_experience"})
_AGENT_PREFIX = "agent:"
_MAX_ID = 128


class AgentNotAddressable(LookupError):
    """``agent_id`` names nothing this owner can talk to in this universe."""


@dataclass(frozen=True)
class AddressedAgent:
    """One custom agent a turn speaks as. ``main`` is never one of these."""

    agent_id: str
    name: str
    #: ``(component_key, kind, instructions)`` from the bound definition, in key order.
    instructions: tuple[tuple[str, str, str], ...]


def normalize_agent_id(agent_id: object) -> str:
    """``"main"`` for the seeded agent, else the trimmed id; refuses a malformed one."""
    if agent_id is None:
        return MAIN_AGENT
    if not isinstance(agent_id, str):
        raise AgentNotAddressable("agent_id must be a string")
    value = agent_id.strip()
    if not value or value == MAIN_AGENT:
        return MAIN_AGENT
    if len(value) > _MAX_ID or any(ch.isspace() or ch == ":" for ch in value):
        raise AgentNotAddressable(f"no agent of yours is {value[:_MAX_ID]!r}")
    return value


def memory_session(owner: str, agent_id: str = MAIN_AGENT) -> str:
    """The conversation-memory key of ``agent_id``'s thread with ``owner``.

    The main thread keeps ``principal:<owner>`` (no migration). Another agent's
    is ``agent:<agent_id>:principal:<owner>``; its native session and steering
    key is ``thread:`` plus this, exactly like the main thread's.
    """
    if agent_id == MAIN_AGENT:
        return f"principal:{owner}"
    return f"{_AGENT_PREFIX}{agent_id}:principal:{owner}"


def agent_of_session(session_id: str, owner: str) -> str | None:
    """The agent a memory session belongs to, for ``owner``; None if not theirs."""
    if session_id == f"principal:{owner}":
        return MAIN_AGENT
    suffix = f":principal:{owner}"
    if session_id.startswith(_AGENT_PREFIX) and session_id.endswith(suffix):
        agent_id = session_id[len(_AGENT_PREFIX):-len(suffix)]
        return agent_id or None
    return None


def is_conversable(binding: dict, *, owner: str, universe_id: str) -> bool:
    """A binding this owner can address as an agent in this universe.

    The serving binding is the main agent's provider binding, so it is ``main``,
    not a second agent. A conversation-design installation answers the main
    thread. Everything else the owner bound here is an agent.
    """
    configuration = binding.get("configuration")
    return bool(
        binding.get("created_by") == owner
        and binding.get("universe_id") == universe_id
        and binding.get("status") == "configured"
        and isinstance(configuration, dict)
        and configuration.get("role") not in _NOT_AN_AGENT_ROLES
        and "turn_consumer" not in configuration
    )


def agent_name(binding: dict, definition: dict | None) -> str:
    """The owner's own name for this agent (its binding), else its definition's."""
    configuration = binding.get("configuration") or {}
    for value in (
        configuration.get("name") if isinstance(configuration, dict) else None,
        (definition or {}).get("name"),
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Unnamed agent"


def _instructions(definition: dict) -> tuple[tuple[str, str, str], ...]:
    components = definition.get("components")
    if not isinstance(components, dict):
        return ()
    out = []
    for key in sorted(components):
        component = components[key]
        if not isinstance(component, dict):
            continue
        config = component.get("config")
        text = config.get("instructions") if isinstance(config, dict) else None
        if isinstance(text, str) and text.strip():
            out.append((str(key), str(component.get("kind") or ""), text.strip()))
    return tuple(out)


def resolve(
    base_path: str | Path, *, universe_id: str, owner: str, agent_id: object,
) -> AddressedAgent | None:
    """The agent ``agent_id`` addresses, or None for the main agent.

    Raises :class:`AgentNotAddressable` for anything that is not this owner's
    own agent in this universe: an unknown id, another account's binding, a
    binding in another universe, or a row that is not an agent at all. The
    message never says which, so a probe learns nothing about other accounts.
    """
    from tinyassets.custom_agents import get_binding, get_definition

    wanted = normalize_agent_id(agent_id)
    if wanted == MAIN_AGENT:
        return None
    refused = AgentNotAddressable(f"no agent of yours is {wanted!r} in this command center")
    binding = get_binding(base_path, universe_id=universe_id, binding_id=wanted)
    if binding is None or binding.get("created_by") != owner:
        raise refused
    if (binding.get("status") == "serving"
            and binding.get("universe_id") == universe_id):
        return None  # The main agent's own provider binding: the same agent.
    if not is_conversable(binding, owner=owner, universe_id=universe_id):
        raise refused
    definition = get_definition(base_path, binding["agent_definition_id"]) or {}
    return AddressedAgent(
        agent_id=wanted,
        name=agent_name(binding, definition),
        instructions=_instructions(definition),
    )


def roster(base_path: str | Path, *, universe_id: str, owner: str) -> list[dict]:
    """``[{agent_id, name}]`` of the owner's agents here, ``main`` first."""
    from tinyassets.custom_agents import list_bindings

    agents = [{"agent_id": MAIN_AGENT, "name": "Your agent"}]
    for binding in list_bindings(base_path, universe_id=universe_id, limit=None):
        if is_conversable(binding, owner=owner, universe_id=universe_id):
            agents.append({"agent_id": binding["agent_binding_id"],
                           "name": agent_name(binding, None)})
    return agents
