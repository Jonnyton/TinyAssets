"""Graph-handle adapter for a person's user-authored UI library and choice.

The row is keyed by the AUTHENTICATED caller and the universe, never by anything
the caller names: a request can only ever read or write its own row. Universe
access uses the same check as agent bindings (``_binding_access``), so who may
keep a UI in a universe is exactly who may keep an app experience there.
"""

from __future__ import annotations

from typing import Any

from tinyassets.api.custom_agents import (
    _authenticated_actor,
    _binding_access,
    _binding_universe,
    _payload,
)
from tinyassets.api.helpers import _base_path
from tinyassets.custom_agents import (
    AgentConflictError,
    AgentValidationError,
    get_app_ui,
    save_app_ui,
)


def read_app_ui(*, universe_id: str = "") -> dict[str, Any]:
    uid = _binding_universe(universe_id)
    denial = _binding_access(uid, write=False)
    if denial is not None:
        return denial
    actor = _authenticated_actor()
    if actor is None:
        return {"error": "authentication_required", "resource": "app_ui"}
    try:
        return {"app_ui": get_app_ui(_base_path(), owner_user_id=actor, universe_id=uid)}
    except AgentValidationError as exc:
        return {"error": "app_ui_validation_error", "detail": str(exc)}


def write_app_ui(
    *, universe_id: str = "", payload: Any = None, expected_revision: int = 0,
) -> dict[str, Any]:
    uid = _binding_universe(universe_id)
    denial = _binding_access(uid, write=True)
    if denial is not None:
        return denial
    actor = _authenticated_actor()
    if actor is None:
        return {"error": "authentication_required", "resource": "app_ui"}
    try:
        saved = save_app_ui(
            _base_path(),
            owner_user_id=actor,
            universe_id=uid,
            expected_revision=expected_revision,
            changes=_payload(payload),
        )
    except AgentConflictError as exc:
        return {"error": "app_ui_conflict", "detail": str(exc)}
    except AgentValidationError as exc:
        return {"error": "app_ui_validation_error", "detail": str(exc)}
    return {"status": "saved", "app_ui": saved}


__all__ = ["read_app_ui", "write_app_ui"]
