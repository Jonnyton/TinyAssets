"""The platform-routed research session restricts tools, never a model argument."""
from __future__ import annotations

import json

READ_GRAPH_TARGETS = frozenset({
    "status", "graph", "branches", "branch", "runs", "run", "run_output",
    "automations", "automation", "conversation", "model_options",
})
# activities/activity join this audited list when #4221 supplies their handlers.
# pending_requests is deliberately absent: rail_entry can create requests.
ALLOWED = [
    "read", *(f"read_graph:{target}" for target in sorted(READ_GRAPH_TARGETS)),
    "write_graph:proposal:propose",
]


def is_research_session(session_key: str) -> bool:
    # Reserve the whole prefix, including malformed keys, so a broken platform
    # launch cannot accidentally gain ordinary write authority.
    return isinstance(session_key, str) and session_key.startswith("research:")


def research_refusal(tool: str, arguments: dict | None = None) -> str | None:
    from tinyassets.engine_steering import _session_key

    if not is_research_session(_session_key()):
        return None
    arguments = arguments or {}
    target = str(arguments.get("target", "status")).strip().lower()
    operation = str(arguments.get("operation", "")).strip().lower()
    if tool == "read" or (tool == "read_graph" and target in READ_GRAPH_TARGETS):
        return None
    if tool == "write_graph" and target == "proposal" and operation == "propose":
        return None
    return json.dumps({"error": "research_is_read_only", "allowed": ALLOWED})
