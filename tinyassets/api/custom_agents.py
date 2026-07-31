"""Graph-handle adapter for public agent definitions and private bindings."""

from __future__ import annotations

import json
from typing import Any

from tinyassets.api.helpers import _base_path, _request_universe
from tinyassets.custom_agents import (
    AgentConflictError,
    AgentNotFoundError,
    AgentValidationError,
    create_binding,
    get_binding,
    get_definition,
    import_definition,
    list_bindings,
    list_definitions,
    publish_definition,
    update_binding,
)


def _not_found(resource: str) -> dict[str, Any]:
    return {"error": "not_found", "resource": resource}


def _authenticated_actor() -> str | None:
    from tinyassets.api import permissions

    if not permissions.is_authenticated_request():
        return None
    actor = permissions.current_actor_id()
    return actor if actor and actor != "anonymous" else None


def _binding_universe(raw_universe_id: str) -> str:
    return _request_universe(raw_universe_id)


def _binding_access(
    universe_id: str,
    *,
    write: bool,
) -> dict[str, Any] | None:
    from tinyassets.api import permissions
    from tinyassets.daemon_server import list_universe_acl

    actor = (
        permissions.current_actor_id() if permissions.is_authenticated_request() else "anonymous"
    )
    permission = ""
    if actor != "anonymous":
        try:
            permission = next(
                (
                    str(row.get("permission") or "")
                    for row in list_universe_acl(
                        _base_path(),
                        universe_id=universe_id,
                    )
                    if row.get("actor_id") == actor
                ),
                "",
            )
        except Exception:
            permission = ""
    allowed = {"write", "admin"} if write else {"read", "write", "admin"}
    if permission in allowed:
        return None
    if not write:
        return _not_found("agent_binding")
    return permissions.universe_access_error(
        universe_id=universe_id,
        write=True,
        action="write_agent_binding",
        surface="custom_agents",
    )


def _tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise AgentValidationError(f"payload_json is invalid JSON: {exc}") from exc
        if isinstance(parsed, dict):
            return parsed
    raise AgentValidationError("payload must be a JSON object")


def custom_agents(
    *,
    action: str,
    definition_id: str = "",
    binding_id: str = "",
    universe_id: str = "",
    payload: Any = None,
    query: str = "",
    tags: Any = None,
    author_id: str = "",
    limit: int = 30,
    idempotency_key: str = "",
    expected_revision: int = 0,
) -> dict[str, Any]:
    """Execute one custom-agent operation and return a structured envelope."""

    normalized = (action or "").strip().lower()
    base = _base_path()
    try:
        if normalized == "list_agents":
            agents = list_definitions(
                base,
                query=query,
                tags=_tags(tags),
                author_id=author_id,
                limit=limit,
            )
            return {"agents": agents, "count": len(agents)}

        if normalized == "get_agent":
            agent = get_definition(base, definition_id)
            return {"agent": agent} if agent is not None else _not_found("agent_definition")

        if normalized in {"publish_agent", "import_agent"}:
            actor = _authenticated_actor()
            if actor is None:
                return {
                    "error": "authentication_required",
                    "resource": "agent_definition",
                }
            document = _payload(payload)
            if normalized == "import_agent":
                agent = import_definition(
                    base,
                    author_id=actor,
                    portable_definition=document,
                    idempotency_key=idempotency_key,
                )
            else:
                agent = publish_definition(
                    base,
                    author_id=actor,
                    payload=document,
                    idempotency_key=idempotency_key,
                )
            return {"status": "published", "agent": agent}

        if normalized in {
            "list_bindings",
            "get_binding",
            "create_binding",
            "update_binding",
        }:
            uid = _binding_universe(universe_id)
            write = normalized in {"create_binding", "update_binding"}
            denial = _binding_access(uid, write=write)
            if denial is not None:
                return denial

            if normalized == "list_bindings":
                bindings = list_bindings(base, universe_id=uid, limit=limit)
                return {
                    "universe_id": uid,
                    "bindings": bindings,
                    "count": len(bindings),
                }
            if normalized == "get_binding":
                binding = get_binding(
                    base,
                    universe_id=uid,
                    binding_id=binding_id,
                )
                return {"binding": binding} if binding is not None else _not_found("agent_binding")

            actor = _authenticated_actor()
            if actor is None:
                return {
                    "error": "authentication_required",
                    "resource": "agent_binding",
                }
            document = _payload(payload)
            if normalized == "create_binding":
                binding = create_binding(
                    base,
                    universe_id=uid,
                    definition_id=definition_id,
                    created_by=actor,
                    payload=document,
                )
                return {"status": "configured", "binding": binding}
            binding = update_binding(
                base,
                universe_id=uid,
                binding_id=binding_id,
                expected_revision=expected_revision,
                updated_by=actor,
                payload=document,
                definition_id=definition_id,
            )
            return {"status": "configured", "binding": binding}

        return {
            "error": "unknown_agent_action",
            "action": action,
            "allowed_actions": [
                "list_agents",
                "get_agent",
                "publish_agent",
                "import_agent",
                "list_bindings",
                "get_binding",
                "create_binding",
                "update_binding",
            ],
        }
    except AgentConflictError as exc:
        return {"error": "agent_conflict", "detail": str(exc)}
    except AgentNotFoundError:
        resource = "agent_binding" if "binding" in normalized else "agent_definition"
        return _not_found(resource)
    except AgentValidationError as exc:
        return {"error": "agent_validation_error", "detail": str(exc)}


__all__ = ["custom_agents"]
