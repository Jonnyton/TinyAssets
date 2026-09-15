"""Authenticated current-home preferences; saving never changes provider authority."""

from __future__ import annotations

import logging

from tinyassets.providers.model_preferences import parse_preference_write
from tinyassets.storage.model_preferences import (
    ModelPreferenceStore,
    PreferenceConflict,
    PreferenceHomeChanged,
)

_LOG = logging.getLogger(__name__)


def save_model_preferences(*, universe_id: str, payload: str) -> dict:
    """Save a complete preference document with the existing generation CAS.

    Actor and current-home scope are server-derived. The pinned universe is a
    fence, not a caller-selected identity. References are advisory: execution
    independently checks accepted model access, custody and cost every time.
    """
    from tinyassets.api import permissions
    from tinyassets.api.helpers import _base_path
    from tinyassets.principals import named_principal
    from tinyassets.shared_self import require_founder_home

    if not permissions.is_authenticated_request():
        return {"error": "authentication_required", "resource": "model_preferences"}
    actor = named_principal(permissions.current_actor_id())
    if not actor:
        return {"error": "authentication_required", "resource": "model_preferences"}
    try:
        if not isinstance(payload, str):
            raise ValueError("invalid preference document")
        generation, policy = parse_preference_write(payload.encode("utf-8"))
    except (ValueError, TypeError, UnicodeError):
        return {"error": "invalid_model_preferences"}
    try:
        base = _base_path()
        require_founder_home(base, universe_id, actor)
        snapshot = ModelPreferenceStore(base).save(
            actor, universe_id, expected_generation=generation,
            policy=policy, require_current_home=True,
        )
        return {"universe_id": universe_id, **snapshot.document()}
    except PreferenceConflict as exc:
        return {"error": "model_preferences_conflict", "universe_id": universe_id,
                **exc.current.document()}
    except (PermissionError, PreferenceHomeChanged):
        return {"error": "model_preference_home_changed"}
    except Exception:  # noqa: BLE001 - do not expose private database details
        _LOG.warning("Model preferences unavailable")
        return {"error": "model_preferences_unavailable"}
