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
import re
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
#: Git scopes one ask may carry. A workspace job names the repositories it works
#: on; a list longer than this is a portfolio, not a job.
_MAX_REQUEST_GIT_SCOPES = 6

#: An unbroken run this long is a credential, not prose. Feedback is free text
#: stored in the clear, so it gets the same screen the resolver applies.
_ENTROPY_RUN_RE = re.compile(r"[A-Za-z0-9_\-]{16,}")


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
    )

    action = raw if isinstance(raw, dict) else {"type": "answer"}
    kind = str(action.get("type") or "answer").strip().lower()
    if kind == "answer":
        return {"type": "answer"}
    if kind == "grant_workspace_consent":
        return _validated_workspace_consent(action)
    if kind == "extend_http":
        # Widening a grant the user already funded. No secret is involved: the
        # vault keeps the one they deposited, and answering this request IS the
        # authorization. Endpoints are validated by the same allow-list.
        destination = str(action.get("destination") or "").strip().lower()
        if not _DESTINATION_RE.match(destination):
            raise ValueError(
                "destination must be 2-127 chars of [a-z0-9._:-] starting "
                "alphanumeric"
            )
        # A scope-only widening carries no endpoints: a git scope needs none,
        # and the served rail documents exactly that shape. The deposit
        # validates it against the endpoints the connection ALREADY has, which
        # is the only set that could vouch for the host anyway.
        raw_endpoints = action.get("endpoints")
        scope_only = (
            (not isinstance(raw_endpoints, list) or not raw_endpoints)
            and action.get("scopes")
            and not action.get("host")
        )
        endpoints = [] if scope_only else _validated_endpoint_list(action)
        return {
            "type": "extend_http",
            "destination": destination,
            "endpoints": endpoints,
            "scopes": _validated_git_scopes(action, endpoints, host_checked=not scope_only),
        }
    if kind != "connect_http":
        raise ValueError(
            "action type must be answer, connect_http, extend_http or "
            "grant_workspace_consent"
        )

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
    endpoints = _validated_endpoint_list(action)
    return {
        "type": "connect_http",
        "destination": destination,
        "auth_scheme": scheme,
        "endpoints": endpoints,
        "scopes": _validated_git_scopes(action, endpoints),
    }


def _validated_git_scopes(
    action: dict[str, Any],
    endpoints: list[dict[str, Any]],
    *,
    host_checked: bool = True,
) -> list[str]:
    """The git scopes an http ask may carry, validated the way the deposit will.

    A git scope is the one authority an endpoint list cannot express: which
    repository a credentialed clone or push may touch. It is checked against the
    SAME endpoint hosts here as at the deposit, so a tab can never promise a
    scope the deposit would then refuse - the user would have answered a
    question that grants nothing.
    """
    from tinyassets.storage.workspace_authority import (
        endpoints_allow_git_scopes,
        format_git_scope,
        is_git_scope,
        require_git_scope,
    )

    raw = action.get("scopes")
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("scopes must be a list of git scopes")
    if len(raw) > _MAX_REQUEST_GIT_SCOPES:
        raise ValueError(
            f"a request may cover at most {_MAX_REQUEST_GIT_SCOPES} git scopes"
        )
    scopes: list[str] = []
    for value in raw:
        if not is_git_scope(value):
            raise ValueError(
                "scopes accepts git scopes only (git_read:owner/name, "
                "git_write:owner/name); the HTTP methods come from the endpoints"
            )
        scopes.append(format_git_scope(*require_git_scope(value)))
    # ``host_checked=False`` is the scope-only widening: this ask names no
    # endpoints, so there is nothing here to check the host against and the
    # DEPOSIT checks the connection's stored set instead. Skipping it here
    # cannot widen anything - the ledger refuses the write either way.
    if host_checked and scopes and not endpoints_allow_git_scopes(
        [str(endpoint.get("host") or "") for endpoint in endpoints]
    ):
        raise ValueError(
            "a git scope needs every endpoint of the same ask to be on "
            "github.com; ask for the git scope on the github connection"
        )
    return sorted(set(scopes))


def _validated_workspace_consent(action: dict[str, Any]) -> dict[str, Any]:
    """``grant_workspace_consent``: the typed yes for one repository.

    The scope says the credential MAY reach the repository; this says the owner
    agreed to this kind of work on it. Separate on purpose - a key deposited for
    an API call is not a standing agreement to check the repository out, run its
    code and push to it.
    """
    from tinyassets.storage.workspace_authority import (
        WORKSPACE_CONSENTS,
        normalize_repo,
    )

    connection_id = str(action.get("connection_id") or "").strip()
    if not connection_id or len(connection_id) > 200:
        raise ValueError(
            "grant_workspace_consent needs the connection_id the key was "
            "deposited under"
        )
    repo = normalize_repo(action.get("repo"))
    raw = action.get("consents")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        raise ValueError(
            "consents must name at least one of " + ", ".join(WORKSPACE_CONSENTS)
        )
    consents = sorted({str(value).strip().lower() for value in raw})
    unknown = [value for value in consents if value not in WORKSPACE_CONSENTS]
    if unknown:
        raise ValueError(
            "unknown consent(s) " + ", ".join(unknown) + "; expected "
            + ", ".join(WORKSPACE_CONSENTS)
        )
    return {
        "type": "grant_workspace_consent",
        "connection_id": connection_id,
        "repo": repo,
        "consents": consents,
    }


def _validated_endpoint_list(action: dict[str, Any]) -> list[dict[str, Any]]:
    """Shared endpoint validation for connect_http and extend_http."""
    from tinyassets.api.http_connection import _parse_allowed_endpoints

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
        endpoint = {
            "host": str(raw.get("host") or action.get("host") or "").strip().lower(),
            "path_template": str(raw.get("path_template") or "").strip(),
            "methods": methods,
        }
        # Carry the pattern keys through. This rebuild used to keep only the
        # three fields above, which silently stripped ``param_patterns`` - and
        # a ``{name}`` / ``{name+}`` placeholder WITHOUT its pattern is refused
        # by the deposit parser ("must declare exactly the path placeholders").
        # So the exact job-scoped ask the agent is taught to raise
        # (``contents/{path+}``) was rejected at ask time, and the agent was told
        # its correctly shaped request was invalid (found 2026-08-29, before it
        # reached a live test). The parser below still validates every one of
        # these; nothing is trusted here, only forwarded.
        for key in ("param_patterns", "allowed_query", "query_patterns", "required_query"):
            if raw.get(key) is not None:
                endpoint[key] = raw[key]
        endpoints.append(endpoint)
    _parse_allowed_endpoints(endpoints)   # raises on anything the deposit refuses
    return endpoints


def _validated_fields(raw: Any, action: dict[str, Any]) -> list[dict[str, Any]]:
    from tinyassets.storage.pending_requests import FIELD_TYPES

    fields = raw if isinstance(raw, list) else []
    if not fields:
        # A credential ask has an obvious single field; anything else must say
        # what it wants rather than presenting an empty tab.
        if action["type"] == "connect_http":
            fields = [{"name": "secret", "label": "Paste the key", "type": "secret"}]
        elif action["type"] in ("extend_http", "grant_workspace_consent"):
            # Nothing to type. The key is already in the vault; this is a yes/no.
            return []
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
        if any(existing["name"] == name for existing in out):
            # Duplicate names collide as DOM ids: the browser clears the first
            # control twice and leaves the second holding its value, which for a
            # secret field means a credential left in the page (Codex 2026-08-27,
            # reproduced headless).
            raise ValueError("field names must be unique within a request")
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

    # Include body AND fields. With only (kind, title, action), muting "Approve
    # this?" about a harmless draft also silenced "Approve this?" about deleting
    # production data — the `answer` action normalizes to a bare {"type":"answer"},
    # so those two asks shared a key (Codex 2026-08-27, reproduced).
    dedupe = json.dumps(
        [kind, title, body, fields, action], sort_keys=True, separators=(",", ":")
    )
    row = create_request(
        udir, kind=kind, title=title, body=body, fields=fields,
        action=action, dedupe_key=dedupe,
    )
    if row is None:
        return {"error": "request_storage_unavailable"}
    if row.get("error"):
        return row
    if row.get("settled"):
        # Already decided in a past interaction. This is the "it might know from
        # past interaction what it is allowed" case: a standing ALLOW means go
        # ahead, a standing decline means do not, and neither costs the user a
        # second answer.
        return {
            "status": "settled",
            "decision": row["decision"],
            "may_proceed": row["decision"] == "allowed",
            "answer": row.get("answer"),
            "feedback": row.get("feedback", ""),
            "note": (
                "You already asked this and they settled it. Act on the standing "
                "decision rather than asking again."
            ),
        }
    return {**row, "grant_sentence": _grant_sentence(row)}


def _grant_sentence(row: dict[str, Any]) -> str:
    """For a credential ask, the exact grant in one line. Empty otherwise."""
    action = row.get("action") or {}
    if action.get("type") == "grant_workspace_consent":
        from tinyassets.storage.workspace_authority import (
            CONSENT_OPERATIONS,
            GIT_SCOPE_HOST,
        )

        operations = [
            CONSENT_OPERATIONS.get(consent, consent)
            for consent in (action.get("consents") or [])
        ]
        return (
            "Let this universe " + ", ".join(operations) + " "
            f"{GIT_SCOPE_HOST}/{action.get('repo')} with the key you already "
            "gave. Nothing to paste; this is the yes."
        )
    if action.get("type") == "extend_http":
        lines = [
            f"{'/'.join(e.get('methods') or [])} {e.get('host')}{e.get('path_template')}"
            for e in (action.get("endpoints") or [])
        ]
        return (
            f'Also let the key you already gave as "{action.get("destination")}" '
            "reach " + "; ".join(lines) + ". You do not need to paste it again."
        )
    if action.get("type") != "connect_http":
        return ""
    lines = [
        f"{'/'.join(e.get('methods') or [])} {e.get('host')}{e.get('path_template')}"
        for e in (action.get("endpoints") or [])
    ]
    if not lines:
        return ""
    # Name the connection. Two asks can differ ONLY by destination — the agent
    # re-raised the same endpoint under a new name when the first would have
    # conflicted — and with the destination hidden both tabs read identically,
    # so a user cannot tell the one that works from the one that fails
    # (observed live, 2026-08-28).
    where = f' as "{action.get("destination")}"' if action.get("destination") else ""
    if len(lines) == 1:
        return f"This key{where} will be able to {lines[0]} - nothing else."
    return (
        f"This key{where} will be able to reach exactly these, and nothing "
        "else: " + "; ".join(lines) + "."
    )


#: The one ask the platform raises itself. Everything else comes from the agent —
#: but the agent cannot ask for the thing it needs in order to think at all, so
#: this one is synthesized (founder, 2026-08-27).
_LLM_REQUEST_ID = "sys_connect_llm"


def _serving_llm_bound(base_path, universe_id: str, actor: str) -> bool:
    """Whether anything is currently serving this universe's turns."""
    from tinyassets.provider_serving_binding import resolve_serving_agent_binding

    try:
        selected = resolve_serving_agent_binding(
            base_path, universe_id=universe_id, owner_user_id=actor
        )
    except Exception:  # noqa: BLE001 - "cannot resolve one" IS "none is bound"
        return False
    return bool(selected and selected.get("agent_binding_id"))


def _connect_llm_request() -> dict[str, object]:
    """The sticky tab shown while no model is connected.

    ``sticky`` means the rail renders it expanded and offers no dismiss: this is
    a precondition, not a request the user can decline and still have a working
    universe. It disappears by being satisfied, which is the only honest way for
    a blocking ask to go away.
    """
    return {
        "request_id": _LLM_REQUEST_ID,
        "kind": "LLM",
        "title": "Connect the model your universe runs on",
        "body": (
            "Your universe thinks on your own Claude or OpenAI subscription - it "
            "never runs on anyone else's account. Connect one and it starts "
            "speaking on the very next turn."
        ),
        "fields": [],
        "action": {"type": "connect_llm"},
        "status": "pending",
        "sticky": True,
        "created_at": 0.0,
        "resolved_at": None,
        "answer": None,
        "feedback": None,
        "dedupe_key": _LLM_REQUEST_ID,
        "grant_sentence": "",
    }


def list_requests(*, universe_id: str = "", limit: int = 10) -> dict[str, Any]:
    """What the app's rail renders, and what the phone reads too.

    Carries the agent's asks, plus the one the platform raises for itself: while
    no model is connected the universe cannot ask for anything, so that request
    is synthesized rather than stored.
    """
    from tinyassets.api import permissions
    from tinyassets.api.helpers import _base_path
    from tinyassets.storage.pending_requests import (
        list_pending,
        list_resolved,
        list_suppressions,
        list_unmutes,
    )

    uid, udir, denied = _owner_gate(universe_id)
    if denied is not None:
        return denied
    rows = list_pending(udir, limit=limit)
    # Prepended, not stored: it is derived from whether a model is bound, so it
    # cannot go stale, cannot be dismissed into a state where the universe is
    # mute with no way back, and needs no migration.
    if not _serving_llm_bound(_base_path(), uid, permissions.current_actor_id().strip()):
        rows = [_connect_llm_request(), *rows]
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
        # …and lifts are visible too, because the agent shares the user's
        # principal and can lift one itself.
        "mutes_lifted": list_unmutes(udir),
    }


def unmute_request(*, universe_id: str = "", payload: Any = None) -> dict[str, Any]:
    """Lift a "don't ask again". A standing refusal a user cannot undo is a trap."""
    from tinyassets.storage.pending_requests import record_unmute, unsuppress

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
    lifted = unsuppress(udir, key)
    if lifted:
        # The agent runs as the user's own principal, so nothing at this gate can
        # tell "the user lifted a mute" from "the universe lifted the mute the
        # user set" — Codex reproduced mute -> agent reads key -> agent unmutes.
        # A distinction the auth model cannot make must not be faked here; record
        # it so the lift is visible in the rail rather than silent.
        record_unmute(udir, key)
    return {"status": "unmuted" if lifted else "not_muted"}


def _grant_workspace_consent(
    *,
    udir: Any,
    row: dict[str, Any],
    action: dict[str, Any],
    request_id: str,
    answer: dict[str, Any],
    feedback: str,
    dont_ask_again: bool,
) -> dict[str, Any]:
    """Write the typed workspace consents the owner just agreed to.

    One row per operation under the ``workspace`` sink, at the destination
    :func:`workspace_consent_destination` spells - the same string the sink
    checks, from the same function, so the two cannot drift apart.

    The named connection must exist, belong to this owner and not be revoked:
    consent to check out a repository through a connection that is not theirs is
    not a thing the owner can give. It is also IN the key, so a second key
    deposited under another destination label starts with no consent of its own.

    It does NOT require the git scope to exist
    yet - the scope ask and the consent ask are two tabs and the owner may
    answer them in either order, and a consent with no scope behind it grants
    nothing, because the sink requires both.
    """
    from pathlib import Path

    from tinyassets.api import permissions
    from tinyassets.api.helpers import _base_path
    from tinyassets.storage.effector_consents import grant_consent
    from tinyassets.storage.outbound_connections import ConnectionLedger
    from tinyassets.storage.pending_requests import resolve_request
    from tinyassets.storage.workspace_authority import (
        WORKSPACE_SINK,
        workspace_consent_destination,
    )

    actor = permissions.current_actor_id().strip()
    connection_id = action["connection_id"]
    ledger = ConnectionLedger(
        Path(_base_path()) / "outbound.db",
        verify_authenticated_principal=lambda: actor,
    )
    connection = ledger.get_connection(connection_id)
    if (
        connection is None
        or connection.owner_user_id != actor
        or connection.revoked_at is not None
    ):
        # Leave the request PENDING, exactly as a failed deposit does: the answer
        # did not land, and closing the tab would lose the ask with nothing
        # written. Uniform envelope so this cannot probe which ids exist.
        return {"error": "not_found", "resource": "connection"}

    repo = action["repo"]
    destinations = [
        workspace_consent_destination(consent, repo, connection_id=connection_id)
        for consent in action["consents"]
    ]
    for destination in destinations:
        grant_consent(
            udir,
            sink=WORKSPACE_SINK,
            destination=destination,
            granted_by=actor,
        )
    resolve_request(
        udir,
        request_id,
        status="answered",
        answer=answer,
        feedback=feedback,
        dont_ask_again=dont_ask_again,
        decision="allowed",
    )
    return {
        "status": "answered",
        "request_id": request_id,
        "connection_id": connection_id,
        "repo": repo,
        "consents": list(action["consents"]),
        "destinations": destinations,
        "receipt": _grant_sentence(row),
        "secret_reused": True,
    }


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
    if request_id == _LLM_REQUEST_ID:
        # Synthesized, not stored. It is satisfied by connecting a model, and it
        # disappears because the check that raises it stops being true — there is
        # nothing here to answer or dismiss.
        return {
            "error": "not_answerable",
            "detail": (
                "connect a model to clear this; it is not a question with an "
                "answer, it is the thing your universe needs in order to think"
            ),
        }
    row = get_request(udir, request_id) if request_id else None
    if row is None:
        return {"error": "not_found", "resource": "pending_request"}
    if row["status"] != "pending":
        return {"error": "already_resolved", "status": row["status"]}

    if document.get("dismiss") is True:
        fb = str(document.get("feedback") or "").strip()[:_MAX_ANSWER_CHARS]
        if fb and _ENTROPY_RUN_RE.search(fb):
            return _bad(
                "that feedback looks like it contains a credential; it is stored "
                "in the clear, so say it in words instead"
            )
        again = document.get("dont_ask_again") is True
        resolve_request(udir, request_id, status="dismissed", feedback=fb,
                        dont_ask_again=again, decision="declined")
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
    # Record ONLY values for fields the request actually declared as non-secret.
    # Excluding known secret names was not enough: Codex (2026-08-27) submitted
    # the credential under an UNDECLARED key and it was persisted verbatim. An
    # allow-list of declared names has nowhere for an extra key to land.
    recordable = {
        f["name"] for f in row["fields"] if f["type"] != "secret"
    }
    answer = {
        str(k): str(v)[:_MAX_ANSWER_CHARS]
        for k, v in values.items()
        if str(k) in recordable
    }
    # Feedback is free text the user types, so it can hold anything — including a
    # credential pasted into the wrong box. Same entropy screen the resolver uses.
    if feedback and _ENTROPY_RUN_RE.search(feedback):
        return _bad(
            "that feedback looks like it contains a credential; it is stored in "
            "the clear, so say it in words instead"
        )

    if action.get("type") == "grant_workspace_consent":
        return _grant_workspace_consent(
            udir=udir,
            row=row,
            action=action,
            request_id=request_id,
            answer=answer,
            feedback=feedback,
            dont_ask_again=dont_ask_again,
        )
    if action.get("type") == "extend_http":
        from tinyassets.api.http_connection import extend_http

        widened = extend_http(
            universe_id=universe_id,
            payload=json.dumps({
                "destination": action["destination"],
                "endpoints": action["endpoints"],
                "scopes": action.get("scopes") or [],
            }),
        )
        if widened.get("error"):
            return widened
        resolve_request(udir, request_id, status="answered", answer=answer,
                        feedback=feedback, dont_ask_again=dont_ask_again)
        return {
            "status": "answered",
            "request_id": request_id,
            "destination": action["destination"],
            "receipt": _grant_sentence(row),
            "secret_reused": True,
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
                    "scopes": action.get("scopes") or [],
                }
            ),
        )
        if deposited.get("error"):
            # Leave it PENDING: the answer did not land, and closing the tab
            # here would lose the ask with nothing deposited.
            return deposited
        resolve_request(udir, request_id, status="answered", answer=answer,
                        feedback=feedback, dont_ask_again=dont_ask_again,
                        decision="allowed")
        return {
            "status": "answered",
            "request_id": request_id,
            "suppressed": dont_ask_again,
            "destination": action["destination"],
            "receipt": _grant_sentence(row).replace("will be able to", "may"),
            "connection_id": deposited.get("connection_id"),
        }

    # For a plain answer the user's own words decide it: an explicit decline
    # field, else answering at all is a yes.
    # Send means allowed, Not now means declined — that is all the surface knows,
    # and it must not try to read intent out of a field value. A caller that DOES
    # know (a choice field it defined) can say so outright.
    stated = str(document.get("decision") or "").strip().lower()
    if stated in {"allowed", "declined"}:
        decided = stated
    else:
        decided = "declined" if document.get("decline") is True else "allowed"
    resolve_request(udir, request_id, status="answered", answer=answer,
                    feedback=feedback, dont_ask_again=dont_ask_again,
                    decision=decided)
    return {
        "status": "answered",
        "decision": decided,
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
