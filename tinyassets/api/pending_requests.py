"""The agent asks its user something; the app shows it as a tab; the user answers.

Founder, 2026-08-27:

    "pending-request should show up as tabs on the left side screen of the app,
    the hedder notates what it is like api in this case you tap/click them to
    expand and in this case paist in the api right there. the agent can
    construct these pending requests really how ever he likes so they can be
    used in clever ways by the agent. it should also have a way for it to be a
    notification on the phone and addressible from there also"

One primitive, not a credential feature
---------------------------------------
The agent composes ``kind`` (the tab header), ``title``, ``body`` and ``fields``,
so a kind nobody wrote code for still renders and still works. "I need an API
key" is simply the first kind.

Two actions exist, and the difference is where the answer goes:

* ``{"type": "connect_http", ...}`` — the answer is a credential. It goes
  straight to the vault through :func:`~tinyassets.api.http_connection.connect_http`
  under the endpoint policy stored ON THE REQUEST, so what the user was shown is
  exactly what gets granted. Nothing secret is recorded here.
* ``{"type": "answer"}`` — the answer is ordinary data the agent reads back.

Nothing is inferred anywhere in this flow. For a credential the agent already
knows the endpoint it is about to call, so it states it; there is no model
guessing a host from a pasted secret (contrast
:mod:`tinyassets.api.connection_inference`), and therefore nothing to fence
against a paste steering it.

The boundary that makes "however he likes" safe
-----------------------------------------------
A ``secret`` field is accepted ONLY on a ``connect_http`` request, and a secret
value is never stored. Without that, an agent — including one steered by
injected content — could compose a friendly-looking request that asks for a
password and lands it in readable storage. Generality is the feature; this is
what keeps it from being a harvesting primitive.

Addressable from any surface, including a phone, because the request lives
server-side and is read through the same ``read_graph`` every surface already
speaks. A phone *notification* additionally needs device registration, which
does not exist yet — see the concern filed alongside this module.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_MAX_KIND_CHARS = 24
_MAX_TITLE_CHARS = 120
_MAX_BODY_CHARS = 600
_MAX_FIELDS = 6
_MAX_ANSWER_CHARS = 2000
#: An agent-requested grant stays narrow; a broader one is a deliberate manual
#: deposit, chosen by a person in the explicit form.
_MAX_REQUEST_METHODS = 2
#: Enough for a real multi-call flow (a GitHub PR needs three) without
#: becoming a way to ask for a whole API in one go.
_MAX_REQUEST_ENDPOINTS = 6


def _payload(value: Any) -> dict[str, Any]:
    document = json.loads(value) if isinstance(value, str) else value
    if not isinstance(document, dict):
        raise ValueError("payload_json must be a JSON object")
    return document


def _bad(detail: str) -> dict[str, Any]:
    return {"error": "request_invalid", "detail": detail}


def _owner_gate(universe_id: str):
    """``(uid, udir, None)`` when the caller owns this universe, else an envelope.

    Mirrors ``connect_http``: an explicit ``admin`` ACL row for THIS actor, never
    the permissive ``universe_access_allows`` helper, and the same uniform
    absent-resource envelope so this surface cannot be used to probe existence.
    """
    from tinyassets.api import permissions
    from tinyassets.api.helpers import _base_path, _request_universe, _universe_dir
    from tinyassets.api.http_connection import _NOT_FOUND
    from tinyassets.daemon_server import list_universe_acl

    unauth = {"error": "authentication_required", "resource": "pending_request"}
    if not permissions.is_authenticated_request():
        return None, None, unauth
    actor = permissions.current_actor_id().strip()
    if not actor or actor == "anonymous":
        return None, None, unauth
    uid = _request_universe(universe_id)
    admin = [
        row
        for row in list_universe_acl(_base_path(), universe_id=uid)
        if row.get("actor_id") == actor and row.get("permission") == "admin"
    ]
    if not admin:
        return None, None, dict(_NOT_FOUND)
    udir = _universe_dir(uid)
    if not udir.is_dir():
        return None, None, dict(_NOT_FOUND)
    return uid, udir, None


def _validated_action(raw: Any) -> dict[str, Any]:
    """Normalize the action, validating a credential policy the same way the
    deposit will — so a request can never describe a grant the deposit refuses,
    and a user is never shown a tab that cannot be honoured."""
    from tinyassets.api.http_connection import (
        _DEPOSITABLE_AUTH_SCHEMES,
        _DESTINATION_RE,
        _parse_allowed_endpoints,
    )

    action = raw if isinstance(raw, dict) else {"type": "answer"}
    kind = str(action.get("type") or "answer").strip().lower()
    if kind == "answer":
        return {"type": "answer"}
    if kind != "connect_http":
        raise ValueError("action type must be answer or connect_http")

    destination = str(action.get("destination") or "").strip().lower()
    if not _DESTINATION_RE.match(destination):
        raise ValueError(
            "destination must be 2-127 chars of [a-z0-9._:-] starting alphanumeric"
        )
    scheme = str(action.get("auth_scheme") or "bearer").strip().lower()
    if scheme not in _DEPOSITABLE_AUTH_SCHEMES:
        raise ValueError(
            "auth_scheme must be one of " + ", ".join(sorted(_DEPOSITABLE_AUTH_SCHEMES))
        )
    # One request may cover SEVERAL exact endpoints. A GitHub pull request needs
    # three calls (create a ref, put contents, open the pull), and one path per
    # request would mean pasting the same key three times. A list of named exact
    # paths is still least privilege -- it is not a widening, and the user sees
    # every line before pasting once.
    raw_endpoints = action.get("endpoints")
    if not isinstance(raw_endpoints, list) or not raw_endpoints:
        raw_endpoints = [action]          # the single-endpoint shorthand
    if len(raw_endpoints) > _MAX_REQUEST_ENDPOINTS:
        raise ValueError(
            f"a request may cover at most {_MAX_REQUEST_ENDPOINTS} endpoints; "
            "ask for the calls you actually need"
        )
    endpoints = []
    for raw in raw_endpoints:
        if not isinstance(raw, dict):
            raise ValueError("each endpoint must be an object")
        methods = raw.get("methods")
        if not isinstance(methods, list) or not methods:
            methods = ["POST"]
        methods = sorted({str(m).strip().upper() for m in methods if str(m).strip()})
        if len(methods) > _MAX_REQUEST_METHODS:
            raise ValueError(
                f"an endpoint may cover at most {_MAX_REQUEST_METHODS} methods; "
                "ask for the one action you need on it"
            )
        endpoints.append({
            "host": str(raw.get("host") or action.get("host") or "").strip().lower(),
            "path_template": str(raw.get("path_template") or "").strip(),
            "methods": methods,
        })
    _parse_allowed_endpoints(endpoints)   # raises on anything the deposit refuses
    return {
        "type": "connect_http",
        "destination": destination,
        "auth_scheme": scheme,
        "endpoints": endpoints,
    }


def _validated_fields(raw: Any, action: dict[str, Any]) -> list[dict[str, Any]]:
    from tinyassets.storage.pending_requests import FIELD_TYPES

    fields = raw if isinstance(raw, list) else []
    if not fields:
        # A credential ask has an obvious single field; anything else must say
        # what it wants rather than presenting an empty tab.
        if action["type"] == "connect_http":
            fields = [{"name": "secret", "label": "Paste the key", "type": "secret"}]
        else:
            raise ValueError("a request needs at least one field")
    if len(fields) > _MAX_FIELDS:
        raise ValueError(f"a request may have at most {_MAX_FIELDS} fields")
    out: list[dict[str, Any]] = []
    for field in fields:
        if not isinstance(field, dict):
            raise ValueError("each field must be an object")
        name = str(field.get("name") or "").strip()
        if not name or len(name) > 40:
            raise ValueError("each field needs a name of at most 40 chars")
        ftype = str(field.get("type") or "text").strip().lower()
        if ftype not in FIELD_TYPES:
            raise ValueError("field type must be one of " + ", ".join(sorted(FIELD_TYPES)))
        if ftype == "secret" and action["type"] != "connect_http":
            # THE boundary. Without it, "compose requests however you like"
            # becomes a way to ask for a password and store it in the clear.
            raise ValueError(
                "a secret field is only allowed on a connect_http request, so the "
                "value goes to the vault instead of being recorded as an answer"
            )
        entry = {
            "name": name,
            "label": str(field.get("label") or name).strip()[:120],
            "type": ftype,
        }
        if ftype == "choice":
            options = [str(o).strip()[:60] for o in (field.get("options") or []) if str(o).strip()]
            if not options:
                raise ValueError("a choice field needs options")
            entry["options"] = options[:8]
        out.append(entry)
    if action["type"] == "connect_http" and not any(f["type"] == "secret" for f in out):
        raise ValueError("a connect_http request needs a secret field for the key")
    return out


def request_from_user(*, universe_id: str = "", payload: Any = None) -> dict[str, Any]:
    """The agent raises a tab. Writes no credential."""
    from tinyassets.storage.pending_requests import create_request

    _uid, udir, denied = _owner_gate(universe_id)
    if denied is not None:
        return denied
    try:
        document = _payload(payload)
    except ValueError as exc:
        return _bad(str(exc))

    kind = str(document.get("kind") or "").strip()[:_MAX_KIND_CHARS]
    title = str(document.get("title") or "").strip()[:_MAX_TITLE_CHARS]
    body = str(document.get("body") or "").strip()[:_MAX_BODY_CHARS]
    if not kind:
        return _bad("kind is the tab header (e.g. 'API'); it is required")
    if not title:
        return _bad("title is required; the user is being asked for something")
    try:
        action = _validated_action(document.get("action"))
        fields = _validated_fields(document.get("fields"), action)
    except ValueError as exc:
        return _bad(str(exc))
    except Exception as exc:  # noqa: BLE001 - endpoint validator
        return {"error": "endpoint_not_permitted", "detail": str(exc)}

    dedupe = json.dumps(
        [kind, title, action], sort_keys=True, separators=(",", ":")
    )
    row = create_request(
        udir, kind=kind, title=title, body=body, fields=fields,
        action=action, dedupe_key=dedupe,
    )
    if row is None:
        return {"error": "request_storage_unavailable"}
    if row.get("error"):
        return row
    return {**row, "grant_sentence": _grant_sentence(row)}


def _grant_sentence(row: dict[str, Any]) -> str:
    """For a credential ask, the exact grant in one line. Empty otherwise."""
    action = row.get("action") or {}
    if action.get("type") != "connect_http":
        return ""
    lines = [
        f"{'/'.join(e.get('methods') or [])} {e.get('host')}{e.get('path_template')}"
        for e in (action.get("endpoints") or [])
    ]
    if not lines:
        return ""
    if len(lines) == 1:
        return f"This key will be able to {lines[0]} - nothing else."
    return (
        "This key will be able to reach exactly these, and nothing else: "
        + "; ".join(lines)
        + "."
    )


def list_requests(*, universe_id: str = "", limit: int = 10) -> dict[str, Any]:
    """What the app's left rail renders, and what the phone reads too."""
    from tinyassets.storage.pending_requests import (
        list_pending,
        list_resolved,
        list_suppressions,
    )

    uid, udir, denied = _owner_gate(universe_id)
    if denied is not None:
        return denied
    rows = list_pending(udir, limit=limit)
    return {
        "universe_id": uid,
        "pending": [{**r, "grant_sentence": _grant_sentence(r)} for r in rows],
        "count": len(rows),
        "recently_answered": [
            {k: v for k, v in r.items() if k != "action"}
            for r in list_resolved(udir, limit=5)
        ],
        # Visible, so a standing "don't ask again" is undoable rather than a trap.
        "muted": list_suppressions(udir),
    }


def unmute_request(*, universe_id: str = "", payload: Any = None) -> dict[str, Any]:
    """Lift a "don't ask again". A standing refusal a user cannot undo is a trap."""
    from tinyassets.storage.pending_requests import unsuppress

    _uid, udir, denied = _owner_gate(universe_id)
    if denied is not None:
        return denied
    try:
        document = _payload(payload)
    except ValueError as exc:
        return _bad(str(exc))
    key = str(document.get("dedupe_key") or "")
    if not key:
        return _bad("dedupe_key is required; read it from the muted list")
    return {"status": "unmuted" if unsuppress(udir, key) else "not_muted"}


def answer_request(*, universe_id: str = "", payload: Any = None) -> dict[str, Any]:
    """The user's answer.

    ``{"request_id": ..., "values": {...}}`` submits; ``"dismiss": true`` closes
    the tab with nothing written. For a ``connect_http`` request the secret value
    is deposited under the policy stored ON THE REQUEST — never one supplied
    here — so the tab's promise is what gets granted.
    """
    from tinyassets.api.http_connection import connect_http
    from tinyassets.storage.pending_requests import get_request, resolve_request

    _uid, udir, denied = _owner_gate(universe_id)
    if denied is not None:
        return denied
    try:
        document = _payload(payload)
    except ValueError as exc:
        return _bad(str(exc))

    request_id = str(document.get("request_id") or "").strip()
    row = get_request(udir, request_id) if request_id else None
    if row is None:
        return {"error": "not_found", "resource": "pending_request"}
    if row["status"] != "pending":
        return {"error": "already_resolved", "status": row["status"]}

    if document.get("dismiss") is True:
        fb = str(document.get("feedback") or "").strip()[:_MAX_ANSWER_CHARS]
        again = document.get("dont_ask_again") is True
        resolve_request(udir, request_id, status="dismissed", feedback=fb,
                        dont_ask_again=again)
        return {
            "status": "dismissed",
            "request_id": request_id,
            "feedback": fb,
            "suppressed": again,
        }

    # An approval the user disagrees with is worth more than a silent no, and a
    # user who never wants this ask again should not have to keep declining it
    # (founder 2026-08-27). Both ride the answer rather than being a separate
    # surface, because the moment of answering is when the user has the opinion.
    feedback = str(document.get("feedback") or "").strip()[:_MAX_ANSWER_CHARS]
    dont_ask_again = document.get("dont_ask_again") is True

    values = document.get("values")
    if not isinstance(values, dict):
        return _bad("values must be an object of field name -> value")

    action = row["action"]
    secret_names = {f["name"] for f in row["fields"] if f["type"] == "secret"}
    # Only NON-secret answers are ever recorded.
    answer = {
        str(k): str(v)[:_MAX_ANSWER_CHARS]
        for k, v in values.items()
        if str(k) not in secret_names
    }

    if action.get("type") == "connect_http":
        secret = next(
            (str(values.get(n) or "") for n in secret_names if values.get(n)), ""
        )
        if not secret.strip():
            return _bad("the key is required")
        deposited = connect_http(
            universe_id=universe_id,
            payload=json.dumps(
                {
                    "destination": action["destination"],
                    "secret": secret,
                    "auth_scheme": action["auth_scheme"],
                    "allowed_endpoints": action["endpoints"],
                }
            ),
        )
        if deposited.get("error"):
            # Leave it PENDING: the answer did not land, and closing the tab
            # here would lose the ask with nothing deposited.
            return deposited
        resolve_request(udir, request_id, status="answered", answer=answer,
                        feedback=feedback, dont_ask_again=dont_ask_again)
        return {
            "status": "answered",
            "request_id": request_id,
            "suppressed": dont_ask_again,
            "destination": action["destination"],
            "receipt": _grant_sentence(row).replace("will be able to", "may"),
            "connection_id": deposited.get("connection_id"),
        }

    resolve_request(udir, request_id, status="answered", answer=answer,
                    feedback=feedback, dont_ask_again=dont_ask_again)
    return {
        "status": "answered",
        "request_id": request_id,
        "answer": answer,
        "feedback": feedback,
        "suppressed": dont_ask_again,
    }


__all__ = [
    "answer_request",
    "list_requests",
    "request_from_user",
    "unmute_request",
]
