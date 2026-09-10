"""Unpowered-safe settings ingress. Saving a choice does not authorize inference."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, PlainTextResponse

from tinyassets.providers.model_preferences import MAX_POLICY_BYTES, parse_preference_write
from tinyassets.storage.model_preferences import (
    ModelPreferenceStore,
    PreferenceConflict,
    PreferenceHomeChanged,
)

_LOG = logging.getLogger(__name__)
_NO_STORE = {"Cache-Control": "no-store"}


async def handle_model_preferences(request: Any) -> Any:
    from tinyassets import onboarding
    from tinyassets.auth.middleware import current_identity, identity_context

    if not onboarding.onboarding_enabled():
        return PlainTextResponse("Not Found", status_code=404, headers=_NO_STORE)
    denied = onboarding._app_identity_required()
    if denied is not None:
        denied.headers.update(_NO_STORE)
        return denied
    write = None
    if request.method == "POST":
        resource = str(onboarding.app_config().get("resource") or "")
        try:
            origin = urlsplit(request.headers.get("origin", ""))
            same_origin = (
                onboarding._same_origin_json(request, resource)
                and origin.scheme == urlsplit(resource or str(request.url)).scheme
                and not (origin.path or origin.query or origin.fragment)
            )
        except ValueError:
            same_origin = False
        if not same_origin:
            return JSONResponse({"error": "same_origin_json_required"}, 403, headers=_NO_STORE)
        raw = await onboarding._read_bounded_body(request, MAX_POLICY_BYTES)
        try:
            if raw is None:
                raise ValueError("oversized preferences")
            write = parse_preference_write(raw)
        except ValueError:
            return JSONResponse({"error": "invalid_model_preferences"}, 400, headers=_NO_STORE)
    identity = current_identity()

    def _access() -> tuple[dict, int]:
        from tinyassets.api.helpers import _base_path

        with identity_context(identity):
            home = onboarding._read_home(identity, raise_errors=True)
            if not home:
                return {"error": "no_home_universe"}, 409
            expected_home = request.query_params.get("universe_id")
            if expected_home is not None and expected_home != home:
                return {"error": "model_preference_home_changed"}, 409
            store = ModelPreferenceStore(_base_path())
            try:
                if write is None:
                    snapshot = store.get(identity.user_id, home, require_current_home=True)
                else:
                    snapshot = store.save(
                        identity.user_id,
                        home,
                        expected_generation=write[0],
                        policy=write[1],
                        require_current_home=True,
                    )
                return {"universe_id": home, **snapshot.document()}, 200
            except PreferenceConflict as exc:
                return {
                    "error": "model_preferences_conflict",
                    "universe_id": home,
                    **exc.current.document(),
                }, 409
            except PreferenceHomeChanged:
                return {"error": "model_preference_home_changed"}, 409

    try:
        doc, status = await run_in_threadpool(_access)
    except Exception:  # noqa: BLE001 - no raw database/user data in error bodies or logs
        _LOG.warning("Model preferences unavailable")
        return JSONResponse({"error": "model_preferences_unavailable"}, 503, headers=_NO_STORE)
    return JSONResponse(doc, status, headers=_NO_STORE)
