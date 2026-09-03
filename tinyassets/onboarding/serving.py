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

The founder's DEDICATED platform binding is used (created once; reset to
canonical content at an exact revision if a collaborator edited it — never an
arbitrary rediscovered binding), re-pointed to the newly deposited provider
(users switch Claude <-> OpenAI at will); any other serving binding the
founder created is disabled so exactly one serves. A CURRENT admin ACL is
re-checked before any mutation. All authority checks inside the serving module
still run — this composes the public primitives, it does not bypass them.
Claude serving stays behind the operator opt-in (``TINYASSETS_ALLOW_CLAUDE_SERVING``);
when that refuses, the result says so.
"""

from __future__ import annotations

import threading
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
#: Friendly ALIASES for the two subscription CLIs, not an allowlist. Anything
#: else is passed straight through as a compute-connection id, because
#: `bind_serving_provider` already resolves one and `_open_serving_context`
#: already refuses a grant the caller does not own. Gating here as well only
#: refused legitimate users: a universe could not be pointed at any LLM its
#: owner had registered (founder, 2026-09-03: "we shouldnt have a chatgpt
#: spacific path").
_SERVICE_TO_PROVIDER = {"codex": "codex", "claude": "claude-code"}

#: One gesture at a time per universe. `_platform_binding` is check-then-create
#: and `agent_bindings` has no uniqueness constraint, so two first-time calls
#: (two open tabs healing, a paste and a phone connect) both see no binding,
#: both create one, both go serving, and their quiesce passes disable each
#: other: zero serving, two bindings, and every later call refusing them as
#: ambiguous (Codex on #2760, S3). The route and the deposit both run in this
#: process, so a process lock keyed by universe closes it.
_GESTURE_LOCKS: dict[str, threading.Lock] = {}
_GESTURE_LOCKS_GUARD = threading.Lock()


def _gesture_lock(universe_id: str) -> threading.Lock:
    with _GESTURE_LOCKS_GUARD:
        lock = _GESTURE_LOCKS.get(universe_id)
        if lock is None:
            lock = _GESTURE_LOCKS[universe_id] = threading.Lock()
        return lock


def _platform_definition(base: Path) -> dict[str, Any]:
    from tinyassets.custom_agents import publish_definition

    return publish_definition(
        base,
        author_id=PLATFORM_DEFINITION_AUTHOR,
        payload=dict(_PLATFORM_DEFINITION),
        idempotency_key=PLATFORM_DEFINITION_KEY,
    )


def _require_current_admin(base: Path, *, universe_id: str, owner: str) -> None:
    """The owner must hold an explicit, CURRENT ``admin`` ACL row on the universe.

    Re-checked immediately before any mutation (Codex 2026-08-21 #1): a bearer
    whose founder-home mapping survived an ACL revocation must not be able to
    create or re-point serving. Same row ``connect_llm`` requires."""
    from tinyassets.daemon_server import list_universe_acl

    rows = [
        row
        for row in list_universe_acl(base, universe_id=universe_id)
        if row.get("actor_id") == owner and row.get("permission") == "admin"
    ]
    if not rows:
        raise PermissionError("a current admin ACL on the universe is required")


def _platform_binding(base: Path, *, universe_id: str, owner: str) -> dict[str, Any]:
    """The founder's DEDICATED platform binding — never an arbitrary rediscovered one.

    Codex 2026-08-21 #2 (confused deputy): a write collaborator may update a
    founder-created binding (definition, configuration); auto-selecting "the
    founder's current binding" would then bind the founder's credential under
    collaborator-chosen content. So: the binding must be founder-created AND
    on the platform definition; if its configuration has drifted from the
    canonical payload it is reset by the founder at an exact revision before
    use; otherwise a fresh one is created. Ambiguity (several candidates) is
    refused rather than guessed.
    """
    from tinyassets.custom_agents import create_binding, list_bindings, update_binding

    definition = _platform_definition(base)
    did = definition["agent_definition_id"]
    mine = [
        b
        for b in list_bindings(base, universe_id=universe_id, limit=100)
        if b.get("created_by") == owner and b.get("agent_definition_id") == did
    ]
    if len(mine) > 1:
        raise ValueError("ambiguous platform bindings; refusing to guess")
    if not mine:
        return create_binding(
            base,
            universe_id=universe_id,
            definition_id=did,
            created_by=owner,
            payload=dict(_BINDING_PAYLOAD),
        )
    binding = mine[0]
    config = binding.get("configuration") or {}
    canonical = {k: config.get(k) for k in _BINDING_PAYLOAD} == _BINDING_PAYLOAD
    extra = set(config) - set(_BINDING_PAYLOAD) - {"provider_ref"}
    if canonical and not extra:
        return binding
    # Drifted (possibly collaborator-edited): reset to canonical content at the
    # exact current revision; a concurrent edit makes this fail closed.
    return update_binding(
        base,
        universe_id=universe_id,
        binding_id=binding["agent_binding_id"],
        expected_revision=int(binding["revision"]),
        updated_by=owner,
        payload=dict(_BINDING_PAYLOAD),
        definition_id=did,
    )


def _quiesce_other_serving(
    base: Path, *, universe_dir: Path, universe_id: str, owner: str, keep: str
) -> None:
    """Exactly one founder serving binding may exist: the app's connect is the
    founder's choice of which one. Other founder-created serving bindings are
    disabled at their exact revision; anyone else's bindings are never touched."""
    from tinyassets.custom_agents import list_bindings
    from tinyassets.provider_serving_binding import set_serving

    for b in list_bindings(base, universe_id=universe_id, limit=100):
        if (
            b.get("created_by") == owner
            and b.get("status") == "serving"
            and b.get("agent_binding_id") != keep
        ):
            set_serving(
                base_path=base,
                universe_dir=universe_dir,
                owner_user_id=owner,
                universe_id=universe_id,
                agent_binding_id=b["agent_binding_id"],
                expected_revision=int(b["revision"]),
                enabled=False,
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
    asked = (service or "").strip()
    if not asked:
        return {"status": "held", "reason": "no_service_named"}
    # An alias resolves to its CLI provider; anything else is a compute
    # connection the owner registered, and the binding layer authorizes it.
    provider = _SERVICE_TO_PROVIDER.get(asked.lower(), asked)
    base = Path(base_path)
    owner = (owner_user_id or "").strip()
    uid = (universe_id or "").strip()
    if not owner or owner == "anonymous" or not uid:
        return {"status": "held", "reason": "authentication_required"}
    with _gesture_lock(uid):
        # `_ensure_founder_serving_locked` classifies and RETURNS; it does not
        # raise. The provider_not_yours / unknown_provider handlers that used to
        # sit here could never fire, because its own broad catches ran first.
        return _ensure_founder_serving_locked(
            base, universe_dir=universe_dir, owner=owner, uid=uid,
            provider=provider,
        )


def _ensure_founder_serving_locked(
    base: Path, *, universe_dir: str | Path, owner: str, uid: str, provider: str,
) -> dict[str, Any]:
    from tinyassets.provider_serving_binding import (
        ServingProviderNotOwned,
        UnknownServingProvider,
        bind_serving_provider,
        set_serving,
    )

    try:
        _require_current_admin(base, universe_id=uid, owner=owner)
        binding = _platform_binding(base, universe_id=uid, owner=owner)
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
        _quiesce_other_serving(
            base,
            universe_dir=Path(universe_dir),
            universe_id=uid,
            owner=owner,
            keep=final["agent_binding_id"],
        )
        return {
            "status": "serving",
            "provider": provider,
            "agent_binding_id": final["agent_binding_id"],
            "revision": int(final["revision"]),
        }
    except ServingProviderNotOwned as exc:
        # Classified BEFORE the broad catches below: they used to swallow both of
        # these into provider_authority_denied / binding_invalid, which made the
        # documented provider_not_yours + unknown_provider contract dead code.
        return {
            "status": "held", "reason": "provider_not_yours",
            "detail": str(exc), "provider": provider,
        }
    except UnknownServingProvider as exc:
        return {
            "status": "held", "reason": "unknown_provider",
            "detail": str(exc), "provider": provider,
        }
    except PermissionError as exc:
        return {"status": "held", "reason": "provider_authority_denied", "detail": str(exc)}
    except (ValueError, LookupError) as exc:
        return {"status": "held", "reason": "binding_invalid", "detail": str(exc)}
    except Exception as exc:  # noqa: BLE001 - never let serving setup mask a successful deposit
        return {"status": "held", "reason": "serving_setup_failed", "detail": type(exc).__name__}


__all__ = ["ensure_founder_serving", "PLATFORM_DEFINITION_AUTHOR", "PLATFORM_DEFINITION_KEY"]
