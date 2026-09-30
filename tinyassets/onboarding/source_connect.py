"""Connect-card composition: owned key, granted /models, explicit model consent."""

from urllib.parse import urlsplit

from tinyassets.onboarding.hosted_model_auth import HostedAuthError


def connect_source(*, base, uid, owner, preset, key):
    from tinyassets.api.connection_uses import apply_connection_uses
    from tinyassets.api.http_connection import connect_http
    from tinyassets.api.pending_requests import request_from_user
    from tinyassets.custom_agents import list_bindings
    from tinyassets.onboarding.model_bootstrap_binding import ensure_bootstrap_binding
    from tinyassets.onboarding.serving import _gesture_lock
    from tinyassets.provider_assignment import load_provider_assignment
    from tinyassets.provider_assignment_manifest import ModelAccess
    from tinyassets.providers.discovery_http import read_granted_discovery_document
    from tinyassets.providers.free_sources import discovered_agent_models
    from tinyassets.shared_self import require_founder_home

    with _gesture_lock(uid):
        require_founder_home(base, uid, owner)
        urls = [(preset["base_url"] + "/chat/completions", "POST"),
                (preset["base_url"] + "/models", "GET")]
        endpoints = [{"host": urlsplit(url).netloc, "path_template": urlsplit(url).path,
                      "methods": [method]} for url, method in urls]
        # This is the same deposit/authority path as every connect card. No
        # bearer token ever enters a provider definition or a browser response.
        deposit = connect_http(universe_id=uid, payload={
            "destination": "model-" + preset["id"], "secret": key,
            "auth_scheme": "bearer", "allowed_endpoints": endpoints, "access": "exact",
        })
        if deposit.get("status") != "provisioned":
            raise HostedAuthError("model_connection_deposit_incomplete", 409)
        payload = read_granted_discovery_document(
            db_path=base / "outbound.db", grant_id=deposit["grant_id"],
            owner_user_id=owner, universe_id=uid, url=urls[1][0],
        )
        models = discovered_agent_models(preset, payload)
        require_founder_home(base, uid, owner)
        applied = apply_connection_uses(
            base=base, uid=uid, actor=owner, grant_id=deposit["grant_id"],
            uses={"model": {"wire": preset["wire"], "billing": "free", "models": models}},
            constant_headers={}, owner_confirmed=True,
        )
        if applied.get("error") or not applied.get("provider"):
            raise HostedAuthError("model_connection_requires_recovery", 409)
        assignment = load_provider_assignment(base, universe_id=uid)
        if assignment is not None and assignment.owner_user_id != owner:
            raise PermissionError("owned assignment required")
        if assignment is not None:
            matches = [b for b in list_bindings(base, universe_id=uid, limit=100)
                       if b["created_by"] == owner
                       and b["configuration"].get("provider_ref") == assignment.binding_id]
            if len(matches) != 1:
                raise PermissionError("one owned serving agent required")
            binding = matches[0]
        else:
            binding = ensure_bootstrap_binding(base, uid=uid, owner=owner)
        if binding is None or binding["created_by"] != owner:
            raise PermissionError("owned agent required")
        access = ({m.provider.removeprefix("api_key_http:"): m.access.document()
                   for m in assignment.candidates}
                  if assignment is not None else {})
        access[applied["definition_id"]] = ModelAccess(
            "explicit", tuple(m["id"] for m in models), None,
        ).document()
        root = (assignment.provider.removeprefix("api_key_http:") if assignment is not None
                else applied["definition_id"])
        result = request_from_user(universe_id=uid, origin="platform", payload={
            "kind": "LLM", "title": "Use your " + preset["name"] + " models",
            "body": preset["offer"] + " Use a free/trial account with paid usage disabled. "
                    "TinyAssets cannot enforce the provider's billing settings. "
                    "Your other accepted sources and spending ceilings stay the same.",
            "fields": [], "action": {
                "type": "bind_model_access", "agent_binding_id": binding["agent_binding_id"],
                "expected_revision": binding["revision"], "provider": root,
                "model_access": access,
            },
        })
        if not result.get("request_id") or result.get("error"):
            raise HostedAuthError("model_confirmation_requires_review", 409)
        return {"status": "confirmation_required", "request_id": result["request_id"],
                "request": result, "universe_id": uid}
