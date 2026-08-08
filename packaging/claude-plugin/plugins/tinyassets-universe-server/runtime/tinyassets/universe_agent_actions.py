"""Platform actions for the universe agent, executed by the daemon.

Why the agent cannot just call the API
--------------------------------------
`api/cloud_automations.py` and `api/custom_agents.py` authorise from
request-scoped daemon state (`permissions.is_authenticated_request()` /
`current_actor_id()`, backed by an `auth.middleware` ContextVar). The agent's
tool server is spawned by the CLI, which is spawned by the daemon — a separate
process with none of that context. A direct call there returns
``authentication_required``, or resolves to ``anonymous`` and silently reads
nothing.

The fix is NOT to have the subprocess assert an identity from its environment.
That is a known dead end: four security tests once passed while running as the
resource OWNER because `UNIVERSE_SERVER_USER` never reached the
credential-derived checks. An env var naming an actor is a wish, not an
authorization.

So the tool server holds no authority at all. It presents a token the daemon
minted for exactly this turn, and the daemon binds that identity and calls the
ordinary API — which then authorises normally. Nothing here bypasses a
permission check; it re-establishes the context one was always meant to run in.

Token scope
-----------
The token carries ``universe_id`` and ``subject_id`` and expires. That matters:
the app-ingress HMAC key authorises "deliver an event as any sender" across every
universe, which is far too broad for a server bound to exactly one. A token that
leaks out of one turn's subprocess can act only as that founder, on that
universe, until it expires.
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import time
from hashlib import sha256
from typing import Any

logger = logging.getLogger(__name__)

#: Domain separation: this key is also used for the chat ingress, and a token
#: minted here must never verify there (or the reverse).
_PURPOSE = b"tinyassets-universe-agent-action-v1"

#: One turn. Long enough for a slow provider call, short enough that a leaked
#: token is not a standing credential.
DEFAULT_TTL_SECONDS = 1800

#: Actions the agent may ask the daemon to run. An allowlist, not a passthrough:
#: without it, a new API action becomes agent-reachable the moment it is added.
#: Every entry is scoped to the token's own universe by `_execute`.
AUTOMATION_ACTIONS = frozenset(
    {"list", "get", "create", "pause", "resume", "rebind", "bind_provider"}
)
AGENT_ACTIONS = frozenset(
    {"list_agents", "get_agent", "publish_agent", "list_bindings", "create_binding"}
)
#: Routing a chat channel to an agent, so a created agent can be TALKED TO
#: directly rather than only existing in a table. `unbind_channel` is included
#: deliberately: a founder who can point a channel at an agent must be able to
#: take it back without opening a support ticket.
CHAT_SURFACE_ACTIONS = frozenset({"describe", "bind_channel", "unbind_channel"})

#: Discovery. A repository automation needs an `accepted_spec_ref` and a
#: `branch_version_id`, and without a way to LIST them the agent can only be
#: handed them by its founder — observed live 2026-08-07: it refused to invent
#: them (correctly) and simply could not proceed. Read-only.
BRANCH_ACTIONS = frozenset(
    {"list_versions", "run", "build", "read", "templates", "template"}
)

#: Defining what a kind of automation work may spend. Bounded by
#: `DELEGABLE_SCOPES` at define time, so a self-declaration can only re-express
#: authority the founder already has.
OPERATION_SCOPE_ACTIONS = frozenset({"list", "define"})

#: Telling the founder what is happening WHILE it happens. The AI SDK streams
#: tool parts through `input-streaming -> input-available -> output-available`
#: so a user watches the agent work; ours was minutes of silence then a wall of
#: text. This is the same idea on a chat surface: short transient notes, sent as
#: the work happens rather than summarised after it.
PROGRESS_ACTIONS = frozenset({"note"})

#: Automations of ANY kind — schedule + branch + inputs + declared operations.
#: The repo-spec surface builds exactly one shape; this one builds whatever the
#: user composed a branch for. See `storage/scheduled_work.py`.
SCHEDULED_WORK_ACTIONS = frozenset(
    {"list", "create", "update_inputs", "pause", "resume", "run_now"}
)

#: Outbound connections — GitHub above all. An automation cannot be created
#: until requester-owned compute is enrolled AND a destination is authorized;
#: `list` reports both as `prerequisites`. Without these the agent can see that
#: it is blocked and do nothing about it, which is the exact complaint
#: `owner-operable-automation` was written about: "I can request state changes
#: but I can't spin one up myself — that's infrastructure on TinyAssets' side."
#:
#: This is also the "change his own GitHub, and thus himself" path: the GitHub
#: connection is what lets an automation open a pull request against the
#: platform. The agent never touches git — it authorizes a destination and asks
#: the platform to run the automation.
CONNECTION_ACTIONS = frozenset({"list", "connect", "reconcile"})


class AgentActionError(PermissionError):
    """The action was refused. Message reaches the model — keep it actionable."""


def _key() -> bytes:
    from tinyassets.app_ingress_http import load_key

    return load_key()


def _sign(payload: bytes, key: bytes) -> str:
    return hmac.new(key, _PURPOSE + b":" + payload, sha256).hexdigest()


def mint_turn_token(
    *, universe_id: str, subject_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> str:
    """Mint one turn's action token. Daemon-side only."""
    uid = (universe_id or "").strip()
    subject = (subject_id or "").strip()
    if not uid or not subject:
        # Fail closed. A token with no subject would authorise as nobody, and
        # "nobody" is exactly the anonymous actor we must never act as.
        raise AgentActionError("cannot mint an action token without a subject")
    expires = int((now if now is not None else time.time())) + int(ttl_seconds)
    payload = json.dumps(
        {"universe_id": uid, "subject_id": subject, "exp": expires},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    body = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"{body}.{_sign(payload, _key())}"


def verify_turn_token(token: str, *, now: float | None = None) -> tuple[str, str]:
    """Return ``(universe_id, subject_id)`` or raise.

    Every failure raises the SAME message. A caller that can tell "bad
    signature" from "expired" from "malformed" can probe the format.
    """
    refused = AgentActionError("action token is not valid")
    raw = (token or "").strip()
    if "." not in raw:
        raise refused
    body, _, signature = raw.partition(".")
    try:
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    except Exception as exc:  # noqa: BLE001
        raise refused from exc
    if not hmac.compare_digest(_sign(payload, _key()), signature):
        raise refused
    try:
        claims = json.loads(payload.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise refused from exc
    if not isinstance(claims, dict):
        raise refused
    if float(claims.get("exp") or 0) < (now if now is not None else time.time()):
        raise refused
    universe_id = str(claims.get("universe_id") or "")
    subject_id = str(claims.get("subject_id") or "")
    if not universe_id or not subject_id:
        raise refused
    return universe_id, subject_id


def execute_action(
    *, token: str, surface: str, action: str, payload: Any = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Run one agent-requested platform action under the token's identity.

    The universe is taken from the TOKEN, never from the caller's payload — the
    same rule that removed ``fallback_universe_id`` from `deliver_app_event`. A
    caller that can name the universe can aim an action at somebody else's.
    """
    universe_id, subject_id = verify_turn_token(token, now=now)
    normalized = (action or "").strip().lower()
    kind = (surface or "").strip().lower()
    if kind == "automation":
        if normalized not in AUTOMATION_ACTIONS:
            raise AgentActionError(f"unsupported automation action: {normalized}")
    elif kind == "agent":
        if normalized not in AGENT_ACTIONS:
            raise AgentActionError(f"unsupported agent action: {normalized}")
    elif kind == "chat_surface":
        if normalized not in CHAT_SURFACE_ACTIONS:
            raise AgentActionError(f"unsupported chat action: {normalized}")
    elif kind == "connection":
        if normalized not in CONNECTION_ACTIONS:
            raise AgentActionError(f"unsupported connection action: {normalized}")
    elif kind == "branch":
        if normalized not in BRANCH_ACTIONS:
            raise AgentActionError(f"unsupported branch action: {normalized}")
    elif kind == "progress":
        if normalized not in PROGRESS_ACTIONS:
            raise AgentActionError(f"unsupported progress action: {normalized}")
    elif kind == "operation_scope":
        if normalized not in OPERATION_SCOPE_ACTIONS:
            raise AgentActionError(f"unsupported operation-scope action: {normalized}")
    elif kind == "scheduled_work":
        if normalized not in SCHEDULED_WORK_ACTIONS:
            raise AgentActionError(f"unsupported automation action: {normalized}")
    else:
        raise AgentActionError(f"unsupported surface: {kind}")
    return _execute(
        surface=kind,
        action=normalized,
        universe_id=universe_id,
        subject_id=subject_id,
        payload=payload,
    )


def _list_branch_versions(subject_id: str) -> dict[str, Any]:
    """Branch versions THIS subject published, newest first.

    Filtered on `publisher`, taken from the token — never from the caller. A
    branch version is a remixable artifact, but which ones a given agent may
    build an automation from is an ownership question, and ownership here is
    "you published it".
    """
    import sqlite3

    from tinyassets.storage import data_dir

    versions: list[dict[str, Any]] = []
    try:
        con = sqlite3.connect(f"file:{data_dir()}/.runs.db?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT branch_version_id, branch_def_id, notes, status, published_at"
                " FROM branch_versions WHERE publisher = ?"
                " ORDER BY published_at DESC LIMIT 50",
                (subject_id,),
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        raise AgentActionError("could not read branch versions") from exc
    for row in rows:
        versions.append(
            {
                "branch_version_id": row[0],
                "branch_def_id": row[1],
                "notes": row[2] or "",
                "status": row[3] or "",
            }
        )
    return {"branch_versions": versions, "count": len(versions)}


#: What a declared automation OPERATION is allowed to spend.
#:
#: This is a translation table, NOT a policy one. The policy lives where the
#: user put it: `ProviderWorkBinding.allowed_operations`, declared when they (or
#: their agent) created the automation, and already enforced at
#: `storage/provider_work_authority.py:927` and `api/cloud_automations.py:103`.
#:
#: An earlier version of this mapped (surface, action) -> scope directly, which
#: made the platform decide what every automation may do. That is the wrong
#: shape: different automations do different work and must carry different
#: capabilities, chosen by whoever built them. Host correction 2026-08-07.
#: Operation -> scope now lives in `storage/operation_scopes.py`, per universe,
#: because users define their own operations too (host 2026-08-07: "seems users
#: should also be able to make operation scopes"). The shipped names are a
#: starting vocabulary, not policy.

#: Actions whose cost must be covered by a declared operation. Anything absent
#: needs no capability at all, so reads stay free.
_ACTIONS_REQUIRING_DECLARED_OPERATION = frozenset(
    {("branch", "run"), ("branch", "build"), ("scheduled_work", "run_now")}
)


def _scheduled_work(
    action: str, universe_id: str, subject_id: str, fields: dict
) -> dict[str, Any]:
    """Automations of any kind, composed from a branch the user already built."""
    from tinyassets.storage.scheduled_work import (
        ScheduledWorkError,
        ScheduledWorkStore,
    )

    store = ScheduledWorkStore(_base_path_for_scopes())
    try:
        if action == "list":
            return {
                "automations": [
                    item.as_dict() for item in store.list_for(universe_id=universe_id)
                ]
            }
        if action == "create":
            created = store.create(
                universe_id=universe_id,
                name=str(fields.get("name") or ""),
                kind=str(fields.get("kind") or ""),
                branch_def_id=str(fields.get("branch_def_id") or ""),
                inputs_json=str(fields.get("inputs_json") or ""),
                cadence_seconds=fields.get("cadence_seconds") or 3600,
                declared_operations=list(fields.get("declared_operations") or []),
                deliver_to=str(fields.get("deliver_to") or ""),
                owner_id=subject_id,
            )
            return created.as_dict()
        if action == "update_inputs":
            return store.update_inputs(
                universe_id=universe_id,
                work_id=str(fields.get("work_id") or ""),
                inputs_json=str(fields.get("inputs_json") or ""),
                expected_revision=int(fields.get("expected_revision") or 0),
            ).as_dict()
        if action in {"pause", "resume"}:
            updated = store.set_state(
                universe_id=universe_id,
                work_id=str(fields.get("work_id") or ""),
                state="paused" if action == "pause" else "active",
                expected_revision=int(fields.get("expected_revision") or 0),
            )
            return updated.as_dict()
    except ScheduledWorkError as exc:
        raise AgentActionError(str(exc)) from exc

    # run_now: execute the branch this automation was built around, right now,
    # with its own inputs. Same executor the schedule would use, so "does it
    # work" is answerable before waiting a cadence.
    item = store.get(
        universe_id=universe_id, work_id=str(fields.get("work_id") or "")
    )
    if item is None:
        raise AgentActionError("no such automation in this universe")
    from tinyassets.universe_server import run_graph

    raw = run_graph(
        branch_def_id=item.branch_def_id,
        graph_id=universe_id,
        inputs_json=item.inputs_json,
        run_name=f"{item.name} (manual)",
    )
    try:
        result = json.loads(raw)
    except (TypeError, ValueError):
        result = {"result": str(raw)[:2000]}
    run_id = str(result.get("run_id") or "")
    if run_id:
        store.record_run(
            universe_id=universe_id, work_id=item.work_id, run_id=run_id
        )
    return result


def _base_path_for_scopes():
    from tinyassets.api.helpers import _base_path

    return _base_path()


def _capabilities_for(
    surface: str, action: str, *, universe_id: str, subject_id: str,
    payload: Any = None,
) -> tuple[str, ...]:
    """Scopes this turn may use, derived from what the OWNER declared.

    Returns nothing unless the action needs a capability AND the subject holds a
    provider binding on this universe whose `allowed_operations` cover it. So an
    automation built for one kind of work cannot borrow another kind's authority,
    and a universe with no binding can run nothing — which is the same answer the
    ordinary API would give.
    """
    if (surface, action) not in _ACTIONS_REQUIRING_DECLARED_OPERATION:
        return ()

    # Running an AUTOMATION spends what THAT automation declared — not what the
    # universe's provider binding happens to allow. The declaration lives on the
    # work item because the user put it there when they built it, and two
    # automations in one universe may legitimately be allowed different things.
    #
    # Missing this is what silently broke execution: run_now got capabilities=[]
    # and every run was refused as unscoped while the tool reported a result.
    if surface == "scheduled_work":
        from tinyassets.storage.operation_scopes import OperationScopeStore
        from tinyassets.storage.scheduled_work import ScheduledWorkStore

        item = ScheduledWorkStore(_base_path_for_scopes()).get(
            universe_id=universe_id,
            work_id=str((payload or {}).get("work_id") or ""),
        )
        if item is None:
            return ()
        scope_store = OperationScopeStore(_base_path_for_scopes())
        granted: set[str] = set()
        for operation in item.declared_operations:
            granted.update(
                scope_store.scopes_for(universe_id=universe_id, operation=operation)
            )
        return tuple(sorted(granted))

    try:
        from tinyassets.api.helpers import _base_path
        from tinyassets.storage.provider_work_authority import (
            SQLiteProviderWorkAuthorityStore,
        )

        bindings = SQLiteProviderWorkAuthorityStore(_base_path()).list_bindings(
            owner_user_id=subject_id, universe_id=universe_id, active_only=True
        )
    except Exception:  # noqa: BLE001 - no binding readable means no capability
        logger.warning("universe agent: could not read declared operations")
        return ()
    from tinyassets.storage.operation_scopes import OperationScopeStore

    store = OperationScopeStore(_base_path())
    granted: set[str] = set()
    for binding in bindings:
        for operation in getattr(binding, "allowed_operations", ()) or ():
            granted.update(
                store.scopes_for(universe_id=universe_id, operation=operation)
            )
    return tuple(sorted(granted))


def _execute(
    *, surface: str, action: str, universe_id: str, subject_id: str, payload: Any
) -> dict[str, Any]:
    """Bind the founder's identity for exactly this call, then use the real API.

    Binding rather than bypassing is the point: `cloud_automations` still runs
    its own `permissions.universe_access_allows(uid, write=True)` check. If the
    subject does not actually own this universe, the API refuses — the token
    proves WHO is asking, never that the answer is yes.
    """
    from tinyassets.auth import middleware
    from tinyassets.auth.provider import Identity

    identity = Identity(
        user_id=subject_id, username=subject_id,
        capabilities=list(
            _capabilities_for(
                surface, action, universe_id=universe_id, subject_id=subject_id,
                payload=payload,
            )
        ),
    )
    reset = middleware._current_identity.set(identity)
    try:
        if surface == "automation":
            from tinyassets.api.cloud_automations import cloud_automations

            # `expected_revision` is optimistic concurrency control. Without
            # it a pause/resume/rebind returns a null envelope and changes
            # NOTHING — found live 2026-08-07: the automation stayed
            # `desired_state: active` and the call looked like it worked.
            fields = payload or {}
            try:
                expected_revision = int(fields.get("expected_revision") or 0)
            except (TypeError, ValueError):
                expected_revision = 0
            return cloud_automations(
                action=action,
                universe_id=universe_id,
                automation_id=str(fields.get("automation_id") or ""),
                expected_revision=expected_revision,
                payload=fields.get("payload"),
            )
        if surface == "progress":
            # No capability required and nothing durable written: this posts a
            # short note to a channel the universe is ALREADY bound to, which it
            # can reach anyway by replying. Deliberately not a general "post
            # anywhere" verb — the destination is the conversation in hand.
            from tinyassets.api.helpers import _universe_dir
            from tinyassets.app_reply_authority import ReplyDestination
            from tinyassets.effectors.slack_transport import build_slack_transport

            note = str((payload or {}).get("note") or "").strip()[:500]
            channel = str((payload or {}).get("channel_id") or "").strip()
            if not note or not channel:
                raise AgentActionError("progress needs a note and a channel")
            build_slack_transport(_universe_dir(universe_id))(
                ReplyDestination(
                    provider="slack", connection_id="slack-main", address=channel
                ),
                f"_{note}_",
                thread_ts=str((payload or {}).get("thread_ts") or ""),
            )
            return {"posted": True}

        if surface == "scheduled_work":
            return _scheduled_work(action, universe_id, subject_id, payload or {})

        if surface == "operation_scope":
            from tinyassets.storage.operation_scopes import (
                OperationScopeError,
                OperationScopeStore,
            )

            scope_store = OperationScopeStore(_base_path_for_scopes())
            if action == "list":
                return {
                    "operations": [
                        {
                            "operation": item.operation,
                            "scopes": list(item.scopes),
                            "defined_by": item.defined_by,
                        }
                        for item in scope_store.list_for(universe_id=universe_id)
                    ]
                }
            try:
                defined = scope_store.define(
                    universe_id=universe_id,
                    operation=str((payload or {}).get("operation") or ""),
                    scopes=list((payload or {}).get("scopes") or []),
                    defined_by=subject_id,
                )
            except OperationScopeError as exc:
                raise AgentActionError(str(exc)) from exc
            return {
                "operation": defined.operation,
                "scopes": list(defined.scopes),
                "defined_by": defined.defined_by,
            }

        if surface == "branch":
            if action == "list_versions":
                return _list_branch_versions(subject_id)
            if action == "templates":
                from tinyassets.branch_templates import list_templates

                return {"templates": list_templates()}
            if action == "template":
                from tinyassets.branch_templates import template_spec

                try:
                    return {"spec": template_spec(str((payload or {}).get("template") or ""))}
                except KeyError as exc:
                    raise AgentActionError(
                        f"no such template: {exc.args[0]!r}"
                    ) from exc
            if action == "read":
                # Learn the SHAPE by example. Every round of this build has hit
                # the same wall: the agent will not invent a structure it cannot
                # inspect, and it is right not to. It listed branches, could not
                # see inside one, and stopped.
                from tinyassets.universe_server import read_graph

                raw = read_graph(
                    target="branch",
                    graph_id=universe_id,
                    branch_id=str((payload or {}).get("branch_def_id") or ""),
                )
                try:
                    return json.loads(raw)
                except (TypeError, ValueError):
                    return {"result": str(raw)[:4000]}
            if action == "build":
                # Composing the WORK itself. Without this the agent can wrap a
                # branch in an automation but cannot create one, so "any kind of
                # automation" stops at whatever branches happen to exist —
                # observed live 2026-08-07: asked for a niche watcher, it listed
                # branches, found none that did the work, and correctly stopped.
                from tinyassets.universe_server import write_graph

                raw = write_graph(
                    target="branch",
                    operation="create",
                    graph_id=universe_id,
                    payload_json=str((payload or {}).get("spec_json") or "{}"),
                )
                try:
                    return json.loads(raw)
                except (TypeError, ValueError):
                    return {"result": str(raw)[:2000]}
            # `run`. A freshly created automation sits at
            # `blocker: awaiting_cloud_worker` with `next_action:
            # run_branch_version` — an operation the automation surface does NOT
            # accept, which is the `next_action`-names-a-fiction defect
            # `owner-operable-automation` records. The real verb is `run_graph`,
            # and it runs on the REQUESTER's own compute, which is the model the
            # platform is supposed to use anyway.
            from tinyassets.universe_server import run_graph

            raw = run_graph(
                branch_def_id=str((payload or {}).get("branch_def_id") or ""),
                graph_id=universe_id,
                run_name=str((payload or {}).get("run_name") or ""),
                # Branches declare `input_keys`; a node with
                # `strict_input_isolation` fails the COMPILE when a declared key
                # is missing, e.g. "prompt references declared input_keys
                # ['topic'] that are not present". Found live 2026-08-07 — the
                # run reached the executor and died there, which reads as a
                # broken branch rather than a missing argument.
                inputs_json=str((payload or {}).get("inputs_json") or ""),
            )
            try:
                return json.loads(raw)
            except (TypeError, ValueError):
                return {"result": str(raw)[:2000]}

        if surface == "connection":
            from tinyassets.api.cloud_connections import cloud_connections

            return cloud_connections(
                action=action,
                universe_id=universe_id,
                payload=(payload or {}).get("payload"),
            )

        if surface == "chat_surface":
            from tinyassets.api import chat_surface as chat

            fields = payload or {}
            if action == "describe":
                # `workspace_id` is REQUIRED, not optional — omitting it raised
                # TypeError, which the tool surfaced to the model as a bare
                # "refused". The agent then correctly reported that it could not
                # learn the channel id and bound workspace-wide instead, so a
                # missing kwarg quietly became a broader binding than the
                # founder asked for. Found live 2026-08-07.
                return chat.describe(
                    universe_id=universe_id,
                    workspace_id=str((payload or {}).get("workspace_id") or ""),
                )
            handler = chat.bind_channel if action == "bind_channel" else chat.unbind_channel
            return handler(
                universe_id=universe_id,
                workspace_id=str(fields.get("workspace_id") or ""),
                channel_id=str(fields.get("channel_id") or ""),
                agent_binding_id=str(fields.get("agent_binding_id") or ""),
            )

        from tinyassets.api.custom_agents import custom_agents

        return custom_agents(
            action=action,
            universe_id=universe_id,
            definition_id=str((payload or {}).get("definition_id") or ""),
            binding_id=str((payload or {}).get("binding_id") or ""),
            author_id=subject_id,
            payload=(payload or {}).get("payload"),
        )
    finally:
        # Always restore, even on error: a leaked identity would make the NEXT
        # request on this thread run as this founder.
        middleware._current_identity.reset(reset)


__all__ = [
    "AGENT_ACTIONS",
    "BRANCH_ACTIONS",
    "OPERATION_SCOPE_ACTIONS",
    "PROGRESS_ACTIONS",
    "SCHEDULED_WORK_ACTIONS",
    "CONNECTION_ACTIONS",
    "CHAT_SURFACE_ACTIONS",
    "AUTOMATION_ACTIONS",
    "AgentActionError",
    "DEFAULT_TTL_SECONDS",
    "execute_action",
    "mint_turn_token",
    "verify_turn_token",
]
