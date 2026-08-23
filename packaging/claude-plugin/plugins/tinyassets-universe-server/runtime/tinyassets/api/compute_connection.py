"""Owner-scoped registration of an open COMPUTE provider for a universe.

``write_graph target=connection operation=connect_compute`` — the user-facing keystone
of the compute-agnostic provider system, the sibling of ``connect_llm`` /
``connect_http``. It lets a universe owner register ANY compute provider (Kimi,
OpenRouter, any OpenAI-compatible endpoint, or a CLI subscription) as a
:class:`~tinyassets.providers.definition.ProviderDefinition` — no per-provider code,
no allowlist.

**Registration only — never a secret (custody boundary).** Unlike ``connect_llm`` /
``connect_http``, this handler accepts NO credential material. Per
``retire-mcp-provider-secret-deposit``, an LLM API key must never cross the
chatbot/MCP/control-plane boundary. So for ``api_key_http`` the credential is
deposited OUT OF BAND — the owner first creates an http connection (endpoint +
credential) and grants it to the universe (via the secure WorkOS browser deposit
form / ``connect_http``), then passes that grant's id here as ``ref``. This handler
only validates the grant is real, bound to THIS universe, and owned by the caller,
then records the compute descriptor on top of it. For ``subscription_cli`` the ``ref``
is the vendor CLI provider name (``codex`` / ``claude-code``); the subscription is
deposited via ``connect_llm``.

Registration creates a CANDIDATE only (design §1): it does not enroll, select, or make
the provider routable — the owner selects it for automations via per-node
``llm_policy`` and the router bridge. Owner-gated exactly like ``connect_http`` (an
explicit ``admin`` ACL row; anonymous/non-admin/unknown-universe get the uniform
``not_found`` envelope). Never echoes a secret (there is none to echo).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tinyassets.api.helpers import _base_path, _request_universe

# Uniform absent-resource envelope (existence-probe safe) — mirrors connect_http.
_NOT_FOUND: dict[str, Any] = {"error": "not_found", "resource": "connection"}

# subscription_cli refs we can run in-daemon (CLI subprocess). Everything else is
# api_key_http (open). Kept in lockstep with provider_resolver._CLI_PROVIDER_CLASSES.
_CLI_REFS = ("codex", "claude-code")


def _payload(value: Any) -> dict[str, Any]:
    document = json.loads(value) if isinstance(value, str) else value
    if not isinstance(document, dict):
        raise ValueError("payload_json must be a JSON object")
    return document


def _project(definition: Any) -> dict[str, Any]:
    """Redacted projection — there is no secret in a definition; ``ref`` is a
    grant_id / provider name, not credential material."""
    return {
        "status": "registered",
        "definition_id": definition.id,
        "access_method": definition.access_method,
        "protocol": definition.protocol,
        "model": definition.model,
        "visibility": definition.visibility,
        "next": [
            "select this provider for an automation via write_graph target=branch "
            "with an llm_policy preferred_provider = this definition_id",
            "the interactive tool-using agent currently runs on CLI-subscription "
            "providers (codex/claude); api_key_http serves workflow nodes",
        ],
    }


def _validate_http_grant(
    *, base: Path, universe_id: str, actor: str, grant_id: str
) -> dict[str, Any] | None:
    """Confirm ``grant_id`` names a real http connection grant bound to THIS universe
    and owned by the caller. Returns an error envelope, or None on success.

    Isolation: a grant for another universe/owner returns the uniform ``not_found``
    (never confirm a foreign grant's existence). The credential itself is never
    touched here — only the grant's binding metadata (a plain read)."""
    if not grant_id:
        return {
            "error": "connection_setup_invalid",
            "detail": (
                "api_key_http requires ref = the grant_id of an http connection "
                "already granted to this universe (deposit the credential via the "
                "secure browser form / connect_http first)"
            ),
        }
    from tinyassets.storage.outbound_connections import ConnectionLedger

    ledger = ConnectionLedger(base / "outbound.db")
    grant = ledger.get_grant(grant_id)
    if grant is None or getattr(grant, "revoked_at", None) is not None:
        return {
            "error": "connection_setup_invalid",
            "detail": "referenced grant is absent or revoked",
        }
    if getattr(grant, "universe_id", "") != universe_id:
        return dict(_NOT_FOUND)
    if getattr(grant, "owner_user_id", "") != actor:
        return dict(_NOT_FOUND)
    return None


def connect_compute(*, universe_id: str = "", payload: Any = None) -> dict[str, Any]:
    """Register an open compute provider for the owner's universe (no secret).

    Returns a redacted projection on success, a sanitized error otherwise. Every
    refusal happens before any write.
    """
    from tinyassets.api import permissions
    from tinyassets.daemon_server import list_universe_acl
    from tinyassets.providers import definition as pd

    # 1. Server-derived authenticated principal (no env fallback).
    if not permissions.is_authenticated_request():
        return {"error": "authentication_required", "resource": "connection"}
    actor = permissions.current_actor_id().strip()
    if not actor or actor == "anonymous":
        return {"error": "authentication_required", "resource": "connection"}

    # 2. Require an explicit admin ACL row for THIS actor on THIS universe.
    uid = _request_universe(universe_id)
    base = _base_path()
    admin = [
        row
        for row in list_universe_acl(base, universe_id=uid)
        if row.get("actor_id") == actor and row.get("permission") == "admin"
    ]
    if not admin:
        return dict(_NOT_FOUND)

    # 3. Parse + read the descriptor fields (validation done by register_definition).
    try:
        document = _payload(payload)
    except ValueError as exc:
        return {"error": "connection_setup_invalid", "detail": str(exc)}
    access_method = str(document.get("access_method") or "").strip()
    protocol = str(document.get("protocol") or "").strip()
    model = str(document.get("model") or "").strip()
    ref = str(document.get("ref") or "").strip()
    visibility = str(document.get("visibility") or "private").strip()

    # 4. Access-method-specific ref validation (BEFORE any write).
    if access_method == "api_key_http":
        gate = _validate_http_grant(
            base=Path(base), universe_id=uid, actor=actor, grant_id=ref
        )
        if gate is not None:
            return gate
    elif access_method == "subscription_cli":
        if ref not in _CLI_REFS:
            return {
                "error": "connection_setup_invalid",
                "detail": f"subscription_cli ref must be one of {list(_CLI_REFS)}",
            }
    # An unknown access_method falls through to register_definition, which rejects it.

    # 5. Register the descriptor (candidate only; no secret, no authority side-effect).
    try:
        definition = pd.register_definition(
            universe_id=uid,
            owner_user_id=actor,
            access_method=access_method,
            protocol=protocol,
            model=model,
            ref=ref,
            visibility=visibility,
        )
    except pd.ProviderDefinitionError as exc:
        return {"error": "connection_setup_invalid", "detail": str(exc)}
    return _project(definition)
