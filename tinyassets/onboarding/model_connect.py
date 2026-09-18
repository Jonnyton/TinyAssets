"""Authenticated same-origin ingress for hosted model connection, unpowered-safe."""

import json
from urllib.parse import urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, PlainTextResponse

from tinyassets.onboarding import hosted_model_auth as hosted

_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


async def handle_model_connect(request):
    from tinyassets import onboarding
    from tinyassets.api.helpers import _base_path, _universe_dir
    from tinyassets.auth.middleware import current_identity, identity_context
    from tinyassets.onboarding.model_bootstrap import complete_bootstrap
    from tinyassets.onboarding.model_setup import model_setup_state
    from tinyassets.shared_self import require_founder_home

    if not onboarding.onboarding_enabled():
        return PlainTextResponse("Not Found", 404, headers=_HEADERS)
    denied = onboarding._app_identity_required()
    if denied is not None:
        denied.headers.update(_HEADERS)
        return denied
    resource = str(onboarding.app_config().get("resource") or "")
    try:
        origin = urlsplit(request.headers.get("origin", ""))
        public = urlsplit(resource)
        allowed = (origin.scheme == public.scheme == "https" and origin.netloc == public.netloc
                   and origin.netloc and not (origin.path or origin.query or origin.fragment)
                   and not origin.username and not origin.password
                   and request.headers.get("content-type", "").split(";")[0].strip()
                   == "application/json")
    except ValueError:
        allowed = False
    if not allowed:
        return JSONResponse({"error": "same_origin_json_required"}, 403, headers=_HEADERS)
    operation = request.path_params.get("operation")
    fields = {"begin": {"preset_id", "code_challenge"},
              "exchange": {"flow", "code", "code_verifier"}, "resume": {"preset_id"},
              "deposit_key": {"preset_id", "key"}}
    if operation not in fields:
        return JSONResponse({"error": "not_found"}, 404, headers=_HEADERS)
    raw = await onboarding._read_bounded_body(request, 8192)
    try:
        data = json.loads(raw) if raw is not None else None
        if (not isinstance(data, dict) or set(data) != fields[operation]
                or any(not isinstance(v, str) or not v or len(v) > 2048 for v in data.values())):
            raise ValueError
    except (ValueError, UnicodeError, RecursionError):
        return JSONResponse({"error": "invalid_model_connection"}, 400, headers=_HEADERS)
    if operation == "begin" and not hosted._HANDLE.fullmatch(data["code_challenge"]):
        return JSONResponse({"error": "invalid_pkce_challenge"}, 400, headers=_HEADERS)
    if operation == "deposit_key" and any(not 33 <= ord(char) <= 126 for char in data["key"]):
        return JSONResponse({"error": "invalid_model_connection"}, 400, headers=_HEADERS)
    identity = current_identity()

    def scope(*, create=False, expected="", empty=False):
        home = onboarding._read_home(identity, raise_errors=True)
        if not home and create:
            home = onboarding._bootstrap_home(identity)
        if not home or (expected and expected != home):
            raise hosted.HostedAuthError("current_home_changed", 409)
        base = _base_path()
        require_founder_home(base, home, identity.user_id)
        if empty and model_setup_state(base, universe=_universe_dir(home), uid=home,
                                       owner=identity.user_id) != "empty":
            raise hosted.HostedAuthError("model_setup_changed", 409)
        return base, home

    def begin():
        with identity_context(identity):
            # Reject unknown data before creating even an inert home.
            hosted.load_preset(data["preset_id"])
            _, home = scope(create=True, empty=True)
            return hosted.begin_flow(owner=identity.user_id, universe_id=home,
                                     preset_id=data["preset_id"], challenge=data["code_challenge"],
                                     public_resource=resource)

    def take():
        with identity_context(identity):
            _, home = scope(empty=True)
            return hosted.take_flow(handle=data["flow"], owner=identity.user_id,
                                    universe_id=home, verifier=data["code_verifier"])

    def deposit_key():
        with identity_context(identity):
            # Only trusted installed data can opt in; validate before home creation.
            preset = hosted.load_preset(data["preset_id"], require_manual_key=True)
            base, home = scope(create=True, empty=True)
            return complete_bootstrap(base=base, uid=home, owner=identity.user_id,
                                      preset=preset, key=data["key"])

    def complete(preset, *, expected="", expected_digest="", key=None):
        with identity_context(identity):
            if expected_digest and preset.digest != expected_digest:
                raise hosted.HostedAuthError("model_connection_preset_changed", 409)
            base, home = scope(expected=expected)
            return complete_bootstrap(base=base, uid=home, owner=identity.user_id,
                                      preset=preset, key=key)

    try:
        if operation == "begin":
            result = await run_in_threadpool(begin)
        elif operation == "deposit_key":
            result = await run_in_threadpool(deposit_key)
        elif operation == "resume":
            result = await run_in_threadpool(complete, hosted.load_preset(data["preset_id"]))
        else:
            flow = await run_in_threadpool(take)
            key = await hosted.exchange_key(flow=flow, code=data["code"],
                                            verifier=data["code_verifier"])
            result = await run_in_threadpool(complete, hosted.load_preset(flow.preset_id),
                                             expected=flow.universe_id,
                                             expected_digest=flow.preset_digest, key=key)
        return JSONResponse(result, headers=_HEADERS)
    except hosted.HostedAuthError as exc:
        return JSONResponse({"error": exc.code}, exc.status, headers=_HEADERS)
    except PermissionError:
        return JSONResponse({"error": "model_connection_requires_recovery"}, 409, headers=_HEADERS)
    except Exception:  # noqa: BLE001 - credentials and upstream errors never enter logs or JSON
        return JSONResponse({"error": "model_connection_incomplete"}, 503, headers=_HEADERS)


async def handle_model_callback(request):
    """Public shell only; GET never redeems a code, deposits, grants or enables."""
    from tinyassets import onboarding

    if not hosted.is_callback_path(request.url.path):
        return PlainTextResponse("Not Found", 404, headers=_HEADERS)
    response = await onboarding._handle_app(request)
    response.headers.update(_HEADERS)
    return response
