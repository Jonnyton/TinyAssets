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
    APP_UI_ENTRY_OPERATIONS,
    AgentConflictError,
    AgentNotFoundError,
    AgentValidationError,
    app_ui_etag,
    app_ui_index,
    change_app_ui_entry,
    get_app_ui,
    save_app_ui,
)
from tinyassets.storage_accounting import StorageRefused

#: ``read_app_ui(ui_id=INDEX)`` is the row without any UI body.
INDEX = "index"
#: Chunk bound for one field of one UI, the unit a bounded model reads.
_MAX_FIELD_CHUNK = 32768


def read_app_ui(
    *, universe_id: str = "", ui_id: str = "", field_name: str = "",
    output_offset: int = 0, output_max_chars: int = 8192,
) -> dict[str, Any]:
    """The caller's own UI row: whole, as an index, one UI, or one field chunk.

    No ``ui_id`` is the whole row (the app's read). ``ui_id="index"`` is every
    UI's id, name, etag and field sizes with no bodies, plus the choice.
    Any other ``ui_id`` is that one UI; with ``field_name`` it is one chunk of
    that field, from ``output_offset``, with ``next_offset`` to continue.
    """

    uid = _binding_universe(universe_id)
    denial = _binding_access(uid, write=False)
    if denial is not None:
        return denial
    actor = _authenticated_actor()
    if actor is None:
        return {"error": "authentication_required", "resource": "app_ui"}
    try:
        document = get_app_ui(_base_path(), owner_user_id=actor, universe_id=uid)
    except AgentValidationError as exc:
        return {"error": "app_ui_validation_error", "detail": str(exc)}
    selector = (ui_id or "").strip()
    if not selector:
        return {"app_ui": document}
    if selector == INDEX:
        return {"app_ui": app_ui_index(document)}
    entry = next((e for e in document["ui_library"]
                  if isinstance(e, dict) and e.get("ui_id") == selector), None)
    if entry is None:
        return {"error": "app_ui_not_found", "ui_id": selector,
                "installed": [u["ui_id"] for u in app_ui_index(document)["uis"]]}
    field = (field_name or "").strip()
    if not field:
        return {"ui": entry, "etag": app_ui_etag(entry), "revision": document["revision"]}
    text = entry.get(field)
    if not isinstance(text, str):
        return {"error": "app_ui_field_not_found", "ui_id": selector, "field_name": field}
    start = max(0, int(output_offset or 0))
    size = max(1, min(int(output_max_chars or 8192), _MAX_FIELD_CHUNK))
    chunk = text[start:start + size]
    end = start + len(chunk)
    return {"ui_id": selector, "field_name": field, "etag": app_ui_etag(entry),
            "offset": start, "chunk": chunk, "total_chars": len(text),
            "next_offset": end if end < len(text) else None}


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
    except StorageRefused as refused:
        # At the account's storage quota: the visible refusal, with its inline
        # Upgrade link. Nothing was saved.
        return _visible_refusal(refused, actor)
    return {"status": "saved", "app_ui": saved}


def change_app_ui(
    *, universe_id: str = "", operation: str = "", payload: Any = None,
) -> dict[str, Any]:
    """One targeted change to the caller's own UI row; see ``change_app_ui_entry``."""

    op = (operation or "").strip().lower()
    if op not in APP_UI_ENTRY_OPERATIONS:
        return {"error": "unknown_app_ui_operation", "operation": operation,
                "allowed_operations": ["save", *APP_UI_ENTRY_OPERATIONS]}
    uid = _binding_universe(universe_id)
    denial = _binding_access(uid, write=True)
    if denial is not None:
        return denial
    actor = _authenticated_actor()
    if actor is None:
        return {"error": "authentication_required", "resource": "app_ui"}
    try:
        outcome = change_app_ui_entry(
            _base_path(), owner_user_id=actor, universe_id=uid,
            operation=op, payload=_payload(payload) if payload not in (None, "") else {},
        )
    except AgentNotFoundError as exc:
        return {"error": "app_ui_not_found", "detail": str(exc)}
    except AgentConflictError as exc:
        return {"error": "app_ui_conflict", "detail": str(exc)}
    except AgentValidationError as exc:
        return {"error": "app_ui_validation_error", "detail": str(exc)}
    return {"status": "saved", "operation": op, **outcome}


__all__ = ["INDEX", "change_app_ui", "read_app_ui", "write_app_ui"]


def _visible_refusal(refused, viewer=None):
    """The refusal the CALLER may see: the charged account's full record only
    if the caller is that account (storage_accounting.visible_record)."""
    from tinyassets.storage_accounting import visible_record

    return visible_record(refused, viewer)
