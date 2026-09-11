"""Opt-in first-person Branch turns using the conversation harness.

The capability is declared in the immutable, owner-authored Branch, never in
run inputs. Provider admission and cancellation remain owned by the run session.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

SHARED_SELF_TOOL = "universe_self"


def shared_self_requested(snapshot: dict | None) -> bool:
    nodes = (snapshot or {}).get("node_defs", [])
    if isinstance(nodes, dict):
        nodes = list(nodes.values())
    marked = [n for n in nodes if SHARED_SELF_TOOL in (n.get("tools_allowed") or [])]
    if not marked:
        return False
    prompts = [n for n in nodes if str(n.get("prompt_template") or "").strip()]
    if len(marked) != 1 or len(prompts) != 1 or marked[0] is not prompts[0]:
        raise ValueError("universe_self_requires_one_prompt_node")
    if marked[0].get("model_hint") not in (None, "", "writer"):
        raise ValueError("universe_self_requires_writer")
    if marked[0].get("source_code"):
        raise ValueError("universe_self_requires_prompt_node")
    return True


def require_founder_home(base_path: Path, universe_id: str, principal_id: str) -> Path:
    """Recheck the stored owner against current home and admin before disclosure."""
    from tinyassets.daemon_server import get_founder_home, universe_access_permission
    from tinyassets.principals import has_named_principal

    base = Path(base_path).resolve()
    if not universe_id or Path(universe_id).name != universe_id or universe_id in {".", ".."}:
        raise PermissionError("shared_self_invalid_universe")
    root = base / universe_id
    if root.resolve() != root or not root.is_dir():
        raise PermissionError("shared_self_invalid_universe")
    if (
        not has_named_principal(principal_id)
        or get_founder_home(base, principal_id) != universe_id
        or universe_access_permission(base, universe_id=universe_id, actor_id=principal_id) != "admin"
    ):
        raise PermissionError("shared_self_requires_current_founder")
    return root


def prepare_shared_self_turn(base_path, universe_id, principal_id, prompt, config=None):
    """Use the SAME persona, memory formatter and tool config as converse.

    No learning extractor runs: a scheduled direction is not a new founder fact.
    History and run outputs remain evidence; this function does not record a
    synthetic founder message in the conversation.
    """
    from tinyassets.config import load_universe_config
    from tinyassets.conversation_store import load_recent_readonly
    from tinyassets.providers.base import UniverseContext
    from tinyassets import universe_intelligence as intelligence

    root = require_founder_home(Path(base_path), universe_id, principal_id)
    ctx = UniverseContext(universe_dir=root, config=load_universe_config(root))
    system = intelligence._build_persona_system_prompt(
        root, universe_id=universe_id, tier=intelligence.interlocutor.FOUNDER,
    )
    history = load_recent_readonly(root, f"principal:{principal_id}")
    history_block = intelligence._conversation_history_block(history)
    if history_block:
        system += "\n\n" + intelligence._CROSS_SURFACE_CONTINUITY
    system += "\n\n" + intelligence._turn_input_method_context("unknown")
    shared_config = intelligence._sandboxed_config(
        ctx, founder_principal=principal_id, universe_id=universe_id, granted=True,
    )
    if not shared_config.engine_mcp_enabled:
        raise PermissionError("shared_self_engine_tools_unavailable")
    if config is not None:
        shared_config = replace(
            shared_config, timeout=config.timeout,
            reasoning_effort=config.reasoning_effort, temperature=config.temperature,
        )
    return history_block + prompt, system, shared_config
