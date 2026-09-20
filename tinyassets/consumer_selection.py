"""Read a receiver's explicit non-serving turn installation; never launch it.

Public components contain only source pins and field mappings. These helpers
consume an existing author transaction and do not open databases, grant provider
authority, mutate bindings, or deserialize a Branch snapshot. The caller still
checks source access and the immutable Branch pin before admission/execution.
"""

import json
import re

from tinyassets.storage.current_home import check_current_home

KIND = "tinyassets.turn-graph.v1"
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _object(value, fields):
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("unsupported turn consumer fields")
    return value


def _identifier(value):
    if (not isinstance(value, str) or not value or len(value) > 200
            or value != value.strip() or not value.isprintable()):
        raise ValueError("invalid turn consumer identifier")
    return value


def _hash(value):
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError("invalid turn consumer fingerprint")
    return value


def parse_component(value):
    doc = _object(value, {"kind", "version", "branch_version_id", "content_hash",
                          "input_map", "reply_key"})
    if doc["kind"] != KIND or type(doc["version"]) is not int or doc["version"] != 1:
        raise ValueError("unsupported turn consumer adapter")
    mapping = doc["input_map"]
    if (not isinstance(mapping, dict) or "message" not in mapping
            or set(mapping) - {"message", "history"}):
        raise ValueError("unsupported turn input mapping")
    values = [_identifier(value) for value in mapping.values()]
    if len(set(values)) != len(values):
        raise ValueError("turn input mappings must name distinct fields")
    return {"adapter": KIND, "branch_version_id": _identifier(doc["branch_version_id"]),
            "content_hash": _hash(doc["content_hash"]), "input_map": dict(mapping),
            "reply_key": _identifier(doc["reply_key"])}


def resolve_selection_in_transaction(conn, *, owner, universe):
    """Trusted transaction-local current selection, not standalone authentication."""
    check_current_home(conn, owner, universe)
    access = conn.execute("SELECT permission FROM universe_acl WHERE universe_id=? AND actor_id=?",
                          (universe, owner)).fetchone()
    if access is None or access[0] != "admin":
        raise PermissionError("consumer requires current owner admin")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_bindings'"
                    ).fetchone() is None:
        return None  # Existing homes without custom-agent schema keep default chat.
    rows = conn.execute("SELECT * FROM agent_bindings WHERE universe_id=? AND created_by=? "
                        "ORDER BY agent_binding_id LIMIT 101", (universe, owner)).fetchall()
    if len(rows) > 100:
        raise PermissionError("consumer installation list is ambiguous")
    active = []
    for row in rows:
        config = json.loads(row["configuration_json"])
        if not isinstance(config, dict):
            raise ValueError("invalid receiver installation configuration")
        if config.get("role") != "app_experience" or "turn_consumer" not in config:
            continue  # Layout import/application alone never selects execution.
        if (row["status"] != "configured" or row["updated_by"] != owner
                or "provider_ref" in config):
            raise PermissionError("consumer installation is not receiver-owned non-serving data")
        selection = config["turn_consumer"]
        if (not isinstance(selection, dict) or type(selection.get("version")) is not int
                or selection["version"] != 1):
            raise ValueError("unsupported consumer selection")
        if selection.get("state") == "disabled":
            _object(selection, {"version", "state"})
            continue  # Recovery must not require the old component to remain usable.
        _object(selection, {"version", "state", "component_key", "definition_fingerprint"})
        if selection["state"] != "active":
            raise ValueError("unsupported consumer selection state")
        active.append((row, selection))
    if len(active) > 1:
        raise PermissionError("consumer installation is ambiguous")
    if not active:
        return None
    binding, selection = active[0]
    definition = conn.execute("SELECT content_fingerprint,components_json FROM agent_definitions "
                              "WHERE agent_definition_id=?", (binding["agent_definition_id"],)
                              ).fetchone()
    if (definition is None
            or definition[0] != _hash(selection["definition_fingerprint"])):
        raise PermissionError("consumer definition fingerprint changed or is unavailable")
    components = json.loads(definition[1])
    key = _identifier(selection["component_key"])
    if not isinstance(components, dict) or key not in components:
        raise ValueError("selected turn component unavailable")
    component = parse_component(components[key])
    return {"version": 1, "binding_id": binding["agent_binding_id"],
            "binding_revision": binding["revision"],
            "definition_id": binding["agent_definition_id"],
            "definition_fingerprint": definition[0], "component_key": key, **component}
