"""Make a deposited subscription actually SERVE the founder's own universe.

``connect_llm`` is deliberately write-only (the chatbot path re-points serving
with explicit ``bind_serving_provider`` / ``set_serving`` calls). The phone
app's "Connect" must be the whole gesture: live test 2026-08-21 showed an
OpenAI credential landing in the vault while every turn still failed with
"exactly one founder serving binding is required", because nothing created
the agent binding the serving authority hangs off.

This provisions the minimal chain for the founder's OWN universe, exactly as
the served-router tests do:

    platform definition (published once, idempotent)
      -> one agent binding created by the founder ("Your universe", writer)
        -> bind_serving_provider(provider of the deposited service)
          -> set_serving(enabled=True)

Existing founder bindings are reused (and re-pointed to the newly deposited
provider: users switch Claude <-> OpenAI at will). All authority checks inside
the serving module still run — this composes the public primitives, it does
not bypass them. Claude serving stays behind the operator opt-in
(``TINYASSETS_ALLOW_CLAUDE_SERVING``); when that refuses, the result says so.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

PLATFORM_DEFINITION_AUTHOR = "platform:universe-default"
PLATFORM_DEFINITION_KEY = "universe-default-v1"
_PLATFORM_DEFINITION = {
    "schema_version": 1,
    "name": "Your universe",
    "description": (
        "The default voice of a founder's own universe: it speaks on the "
        "subscription the founder connected. Published once by the platform; "
        "every founder's home binds to it."
    ),
    "tags": ["platform", "default"],
    "components": {"identity": {"kind": "soul", "config": {}}},
}
_BINDING_PAYLOAD = {"schema_version": 1, "name": "Your universe", "role": "writer"}
_SERVICE_TO_PROVIDER = {"codex": "codex", "claude": "claude-code"}


def _platform_definition(base: Path) -> dict[str, Any]:
    from tinyassets.custom_agents import publish_definition

    return publish_definition(
        base,
        author_id=PLATFORM_DEFINITION_AUTHOR,
        payload=dict(_PLATFORM_DEFINITION),
        idempotency_key=PLATFORM_DEFINITION_KEY,
    )


def _founder_binding(base: Path, *, universe_id: str, owner: str) -> dict[str, Any]:
    """The founder's existing binding in this universe (a serving one wins), or a new one."""
    from tinyassets.custom_agents import create_binding, list_bindings

    mine = [
        b
        for b in list_bindings(base, universe_id=universe_id, limit=100)
        if b.get("created_by") == owner
    ]
    serving = [b for b in mine if b.get("status") == "serving"]
    if serving:
        return serving[0]
    if mine:
        return mine[0]
    definition = _platform_definition(base)
    return create_binding(
        base,
        universe_id=universe_id,
        definition_id=definition["agent_definition_id"],
        created_by=owner,
        payload=dict(_BINDING_PAYLOAD),
    )


def ensure_founder_serving(
    *,
    base_path: str | Path,
    universe_dir: str | Path,
    owner_user_id: str,
    universe_id: str,
    service: str,
) -> dict[str, Any]:
    """Point the founder's universe at the just-deposited ``service`` and enable it.

    Returns a non-secret projection: ``{"status": "serving", "provider", "agent_binding_id",
    "revision"}`` on success, or ``{"status": "held", "reason": ...}`` when the
    serving module refuses (e.g. claude serving not opted in) — never raises for
    an authority refusal, so a deposit's success is reported honestly alongside
    the serving outcome.
    """
    from tinyassets.provider_serving_binding import bind_serving_provider, set_serving

    provider = _SERVICE_TO_PROVIDER.get((service or "").strip().lower())
    if provider is None:
        return {"status": "held", "reason": "unsupported_service"}
    base = Path(base_path)
    owner = (owner_user_id or "").strip()
    uid = (universe_id or "").strip()
    if not owner or owner == "anonymous" or not uid:
        return {"status": "held", "reason": "authentication_required"}
    try:
        binding = _founder_binding(base, universe_id=uid, owner=owner)
        bound = bind_serving_provider(
            base_path=base,
            universe_dir=universe_dir,
            owner_user_id=owner,
            universe_id=uid,
            agent_binding_id=binding["agent_binding_id"],
            expected_revision=int(binding["revision"]),
            provider=provider,
        )
        after_bind = bound.get("agent_binding") or binding
        enabled = set_serving(
            base_path=base,
            universe_dir=universe_dir,
            owner_user_id=owner,
            universe_id=uid,
            agent_binding_id=after_bind["agent_binding_id"],
            expected_revision=int(after_bind["revision"]),
            enabled=True,
        )
        final = enabled.get("agent_binding") or after_bind
        return {
            "status": "serving",
            "provider": provider,
            "agent_binding_id": final["agent_binding_id"],
            "revision": int(final["revision"]),
        }
    except PermissionError as exc:
        return {"status": "held", "reason": "provider_authority_denied", "detail": str(exc)}
    except (ValueError, LookupError) as exc:
        return {"status": "held", "reason": "binding_invalid", "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001 - never let serving setup mask a successful deposit
        return {"status": "held", "reason": "serving_setup_failed", "detail": type(exc).__name__}


__all__ = ["ensure_founder_serving", "PLATFORM_DEFINITION_AUTHOR", "PLATFORM_DEFINITION_KEY"]
