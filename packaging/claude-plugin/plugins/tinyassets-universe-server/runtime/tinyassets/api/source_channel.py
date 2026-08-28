"""Owner self-serve source-channel approval + policy.

Host directive 2026-08-18: "what does and does not need host approval should be
user changeable", and the shape is GENERAL — ``approve_source_channel``, where a
*source channel* is ANY source/sink a user binds to a graph node. GitHub is one
channel type, not a special case.

Today a ``source_code`` node is gated fail-closed by
``graph_compiler._validate_source_code`` (``approved=True`` + matching
``approved_source_hash``). The only writer of that approval is
``extensions action=approve_source_code``, which needs the host-only
``tinyassets.extensions.admin`` scope and is not one of the advertised connector
handles — so a universe OWNER cannot approve their own graph's node and a run
fails ``node_not_approved``. This module is the owner self-serve path, reached
through ``write_graph target=source_channel`` (no new advertised handle).

Authorization (fail-closed, owner-scoped):

- The caller must be the authenticated ``admin``-ACL OWNER of the named
  universe. ``founder_grant.py`` names the ``admin`` ACL row as the canonical
  answer to "does this subject own THIS universe?"; a ``write``-ACL collaborator
  is NOT an owner. Anonymous, non-owner, ``write`` collaborator, or a caller
  naming a universe they do not own all get ``auth_failed``.
- A code-channel approval additionally requires the caller to be the branch
  ``author`` and the branch to be PRIVATE. Public/commons branches run for other
  principals, so self-approving them would affect the commons — those stay on
  the host operator surface.

This module ADDS the owner path; it does not weaken the host operator surface.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from tinyassets.storage.source_channel_policy import (
    MODE_AUTO,
    MODE_REQUIRE,
    VALID_MODES,
)
from tinyassets.storage.source_channel_policy import (
    get_policy as _store_get_policy,
)
from tinyassets.storage.source_channel_policy import (
    get_policy_mode as _store_get_policy_mode,
)
from tinyassets.storage.source_channel_policy import (
    set_policy as _store_set_policy,
)

CHANNEL_SOURCE_CODE = "source_code"


def _auth_failed(detail: str, **extra: Any) -> str:
    payload = {
        "error": "auth_failed",
        "failure_class": "auth_failed",
        "detail": detail,
        "actionable_by": "user",
    }
    payload.update(extra)
    return json.dumps(payload)


def _authenticated_actor() -> str | None:
    """Return the credential-validated request subject, or None if anonymous.

    Never an environment fallback: a ``UNIVERSE_SERVER_USER`` env value must not
    confer approval authority over a universe.
    """
    from tinyassets.api.permissions import current_request_actor_id

    actor = (current_request_actor_id() or "").strip()
    if not actor or actor == "anonymous":
        return None
    return actor


def universe_owner_actor(base_path: Any, universe_id: str, actor: str) -> bool:
    """True iff ``actor`` holds the ``admin`` ACL grant on ``universe_id``.

    The canonical per-universe ownership signal (``founder_grant.py``). Excludes
    ``read``/``write`` ACL holders and wrong-universe callers (admin on A is not
    admin on B). Fail-closed on any read error.
    """
    from tinyassets.daemon_server import universe_access_permission

    uid = (universe_id or "").strip()
    actor = (actor or "").strip()
    if not uid or not actor:
        return False
    try:
        permission = universe_access_permission(
            base_path, universe_id=uid, actor_id=actor
        )
    except Exception:  # noqa: BLE001 — fail closed on any storage error
        return False
    return permission == "admin"


def _payload_dict(payload: Any) -> dict[str, Any] | None:
    if payload is None or payload == "":
        return {}
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def source_channel(
    *,
    action: str,
    universe_id: str = "",
    branch_id: str = "",
    payload: Any = None,
) -> str:
    """Dispatch an owner source-channel operation.

    ``action`` ∈ {approve, set_policy, get_policy}. ``universe_id`` is the
    owner's universe (``graph_id`` from the connector). ``payload`` carries
    ``channel_type``/``node_id``/``reason``/``sink``/``destination``/``mode``.
    """
    from tinyassets.api.helpers import _base_path, _request_universe

    normalized = (action or "").strip().lower()
    fields = _payload_dict(payload)
    if fields is None:
        return json.dumps({
            "error": "payload_json must be a JSON object",
            "failure_class": "invalid_payload",
            "actionable_by": "chatbot",
        })

    actor = _authenticated_actor()
    if actor is None:
        return _auth_failed("authentication required")

    base = _base_path()
    uid = _request_universe(universe_id)
    if not uid:
        return json.dumps({
            "error": "universe_id is required",
            "failure_class": "missing_universe",
            "actionable_by": "chatbot",
        })

    # Single owner gate for every operation: only the admin-ACL owner of THIS
    # universe may approve or configure its channels.
    if not universe_owner_actor(base, uid, actor):
        return _auth_failed(
            "only the universe owner may approve or configure its source "
            "channels",
            universe_id=uid,
        )

    if normalized == "approve":
        return _approve(base, uid, actor, branch_id, fields)
    if normalized == "set_policy":
        return _set_policy(base, uid, actor, fields)
    if normalized == "get_policy":
        return _get_policy(base, uid, fields)
    return json.dumps({
        "error": "unknown_source_channel_operation",
        "operation": action,
        "allowed_operations": ["approve", "set_policy", "get_policy"],
        "actionable_by": "chatbot",
    })


#: Universe ids permitted to APPROVE source_code for in-process execution.
#:
#: Approving source is not an ordinary universe operation -- it is the authority to
#: run arbitrary Python inside the daemon. `graph_compiler` executes an approved node
#: with `exec()` and full builtins; the pattern denylist blocks a handful of substrings
#: and leaves `open`, `os.environ`, sockets and ordinary imports available. So an
#: approver can read every credential the process can read: the live Stripe key, the
#: webhook secret, the session-store digest key, every per-universe credential vault,
#: and every other user's refresh token. It can also write any database under the data
#: dir, including the one that decides who has paid.
#:
#: The owner gate below is per-universe, and EVERY user owns their own universe, so on
#: its own it authorises every user to do all of that (Codex, 2026-08-28, ranked the
#: top second-user blocker). Until user code runs in a real OS sandbox, the capability
#: is limited to an explicit allowlist.
#:
#: Empty = DARK, deliberately: a deployment that has not thought about this must not
#: hand out in-process execution. Mirrors `engine_mcp_http.run_graph_allowlist()`,
#: which exists for the same reason and was reviewed to the same conclusion.
_SOURCE_APPROVAL_VAR = "TINYASSETS_SOURCE_APPROVAL_UNIVERSES"


def source_approval_allowlist() -> frozenset[str]:
    """Universe ids allowed to approve source_code. Empty = nobody."""
    import os as _os

    raw = _os.environ.get(_SOURCE_APPROVAL_VAR, "")
    return frozenset(u.strip() for u in raw.split(",") if u.strip())


def source_approval_allowed(universe_id: str) -> bool:
    return bool(universe_id) and universe_id in source_approval_allowlist()


def source_approval_refusal(universe_id: str) -> dict:
    """The refusal body. Names the capability, so it does not read as a glitch."""
    return {
        "status": "rejected",
        "error": (
            "approving source_code runs arbitrary Python inside the daemon, and "
            "this deployment has not allowlisted this universe for that. It is "
            "off by default because an approver can read every credential the "
            "process holds, including other users'."
        ),
        "failure_class": "source_approval_not_allowlisted",
        "actionable_by": "host",
        "universe_id": universe_id,
        "remediation": (
            f"Set {_SOURCE_APPROVAL_VAR} to a comma-separated list of universe ids "
            "that may approve source. Until user code runs in an OS sandbox, keep "
            "it to vetted founders only."
        ),
    }


def _approve(
    base: Any,
    uid: str,
    actor: str,
    branch_id: str,
    fields: dict[str, Any],
) -> str:
    channel_type = (fields.get("channel_type") or "").strip()
    if not channel_type:
        return json.dumps({
            "error": "channel_type is required",
            "failure_class": "missing_channel_type",
            "actionable_by": "chatbot",
        })
    if channel_type == CHANNEL_SOURCE_CODE:
        return _approve_source_code(base, uid, actor, branch_id, fields)
    return _approve_sink(base, uid, actor, channel_type, fields)


def _approve_source_code(
    base: Any,
    uid: str,
    actor: str,
    branch_id: str,
    fields: dict[str, Any],
) -> str:
    from tinyassets.api.branches import (
        _resolve_readable_branch,
        _source_code_hash,
    )
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import save_branch_definition

    selector = (branch_id or fields.get("branch_def_id") or "").strip()
    node_id = (fields.get("node_id") or "").strip()
    reason = (fields.get("reason") or "").strip()
    if not selector or not node_id:
        return json.dumps({
            "error": "branch_id and node_id are required for a source_code "
            "channel",
            "failure_class": "missing_target",
            "actionable_by": "chatbot",
        })

    resolved = _resolve_readable_branch(selector, str(base))
    if resolved is None:
        return json.dumps({
            "error": f"Branch '{selector}' not found.",
            "failure_class": "branch_not_found",
            "actionable_by": "chatbot",
        })
    bid, source = resolved

    # You may only approve a branch you authored — a universe owner cannot
    # approve a branch authored by another principal.
    if (source.get("author") or "").strip() != actor:
        return _auth_failed(
            "only the branch author may approve its source_code channel",
            branch_def_id=bid,
        )

    # Commons safety (fail-closed allowlist): only a PRIVATE branch may be
    # self-approved. A public/commons/unlisted branch runs for other principals
    # too, so owner self-approval must not touch it — those stay on the host
    # operator surface. Allowlisting ``== "private"`` (not blocklisting
    # ``"public"``) means any non-private visibility value is refused.
    visibility = (source.get("visibility") or "public").strip().lower() or "public"
    if visibility != "private":
        return _auth_failed(
            "only a PRIVATE branch may be self-approved by its owner; "
            "public/commons branches require host operator approval",
            branch_def_id=bid,
            visibility=visibility,
        )

    staging = BranchDefinition.from_dict(source)
    target_node = next(
        (n for n in staging.node_defs if n.node_id == node_id), None
    )
    if target_node is None:
        return json.dumps({
            "status": "rejected",
            "error": f"Node '{node_id}' not found on branch '{bid}'.",
            "failure_class": "node_not_found",
            "actionable_by": "chatbot",
        })
    if not target_node.source_code:
        return json.dumps({
            "status": "rejected",
            "error": f"Node '{node_id}' has no source_code to approve.",
            "failure_class": "no_source_code",
            "actionable_by": "chatbot",
        })

    # Checked HERE, at the write that grants execution, not at the route edge:
    # this is the line that turns text into something the daemon will run.
    if not source_approval_allowed(uid):
        return json.dumps(source_approval_refusal(uid))

    source_hash = _source_code_hash(target_node.source_code)
    target_node.approved = True
    target_node.approved_by = actor
    target_node.approved_at = datetime.now(timezone.utc).isoformat()
    target_node.approved_source_hash = source_hash
    target_node.approval_reason = reason

    saved = save_branch_definition(base, branch_def=staging.to_dict())
    persisted = BranchDefinition.from_dict(saved)
    approved_node = next(
        (n for n in persisted.node_defs if n.node_id == node_id), target_node
    )
    return json.dumps({
        "status": "approved",
        "channel_type": CHANNEL_SOURCE_CODE,
        "universe_id": uid,
        "branch_def_id": bid,
        "node_id": node_id,
        "approved": approved_node.approved,
        "approved_by": approved_node.approved_by,
        "approved_at": approved_node.approved_at,
        "approved_source_hash": approved_node.approved_source_hash,
        "approval_reason": approved_node.approval_reason,
    }, default=str)


def _approve_sink(
    base: Any,
    uid: str,
    actor: str,
    channel_type: str,
    fields: dict[str, Any],
) -> str:
    """Approve a sink/effector channel via the shared effector-consent store.

    ``channel_type`` is the sink name (e.g. ``github_pull_request``), or the
    caller may pass ``sink`` explicitly. ``granted_by`` is the authenticated
    owner — stronger than the legacy ``grant_effector_consent`` which derived it
    from the ambient ``UNIVERSE_SERVER_USER`` env.
    """
    from tinyassets.api.helpers import _universe_dir
    from tinyassets.storage.effector_consents import grant_consent

    sink = (fields.get("sink") or channel_type or "").strip()
    destination = (fields.get("destination") or "").strip()
    if not sink:
        return json.dumps({
            "error": "sink (or channel_type) is required for a sink channel",
            "failure_class": "missing_sink",
            "actionable_by": "chatbot",
        })
    if not destination:
        return json.dumps({
            "error": "destination is required for a sink channel",
            "failure_class": "missing_destination",
            "actionable_by": "chatbot",
        })
    try:
        universe_dir = _universe_dir(uid)
    except ValueError:
        return json.dumps({
            "error": f"Invalid universe_id: {uid}",
            "failure_class": "invalid_universe",
            "actionable_by": "chatbot",
        })
    record = grant_consent(
        universe_dir,
        sink=sink,
        destination=destination,
        granted_by=actor,
    )
    return json.dumps({
        "status": "granted",
        "channel_type": sink,
        "universe_id": uid,
        "consent": record,
    })


def _set_policy(base: Any, uid: str, actor: str, fields: dict[str, Any]) -> str:
    channel_type = (fields.get("channel_type") or "").strip()
    mode = (fields.get("mode") or "").strip().lower()
    if not channel_type:
        return json.dumps({
            "error": "channel_type is required",
            "failure_class": "missing_channel_type",
            "actionable_by": "chatbot",
        })
    if mode not in VALID_MODES:
        return json.dumps({
            "error": f"mode must be one of {sorted(VALID_MODES)}",
            "failure_class": "invalid_mode",
            "actionable_by": "chatbot",
        })
    record = _store_set_policy(
        base,
        universe_id=uid,
        channel_type=channel_type,
        mode=mode,
        set_by=actor,
    )
    return json.dumps({
        "status": "policy_set",
        **record,
    })


def _get_policy(base: Any, uid: str, fields: dict[str, Any]) -> str:
    channel_type = (fields.get("channel_type") or "").strip()
    if not channel_type:
        return json.dumps({
            "error": "channel_type is required",
            "failure_class": "missing_channel_type",
            "actionable_by": "chatbot",
        })
    record = _store_get_policy(base, universe_id=uid, channel_type=channel_type)
    return json.dumps({
        "status": "policy",
        **record,
    })


def apply_auto_approval_policy(base: Any, branch: Any, universe_id: str) -> bool:
    """Run-time preflight: auto-approve the owner's own private source nodes.

    Called by ``run_branch`` after loading the branch. When the run universe's
    ``source_code`` policy is ``auto``, the branch is PRIVATE, and the branch
    ``author`` holds ``admin`` on the run universe (i.e. the branch is the
    universe owner's OWN node), this marks the branch's ``source_code`` nodes
    approved in-memory (hash-pinned) so the run proceeds without an explicit
    approve call.

    Scoped so it NEVER touches the commons or another user's nodes: a public
    branch, a branch authored by a non-owner of the run universe, or a policy of
    ``require`` all leave the branch unchanged. Returns True iff it changed the
    branch. Best-effort: any error leaves the branch unchanged (fail-closed —
    the compiler still enforces approval).
    """
    from tinyassets.api.branches import _source_code_hash

    uid = (universe_id or "").strip()
    if not uid:
        return False
    try:
        mode = _store_get_policy_mode(
            base, universe_id=uid, channel_type=CHANNEL_SOURCE_CODE
        )
        if mode != MODE_AUTO:
            return False
        visibility = (
            getattr(branch, "visibility", "public") or "public"
        ).strip().lower()
        if visibility != "private":  # fail-closed allowlist (never the commons)
            return False
        author = (getattr(branch, "author", "") or "").strip()
        if not author or not universe_owner_actor(base, uid, author):
            return False
        changed = False
        stamp = datetime.now(timezone.utc).isoformat()
        for node in getattr(branch, "node_defs", []) or []:
            src = getattr(node, "source_code", "") or ""
            if not src:
                continue
            expected = _source_code_hash(src)
            if node.approved and node.approved_source_hash == expected:
                continue
            node.approved = True
            node.approved_by = author
            node.approved_at = stamp
            node.approved_source_hash = expected
            node.approval_reason = "auto-approved by owner policy"
            changed = True
        return changed
    except Exception:  # noqa: BLE001 — never break a run on a policy read
        return False


__all__ = [
    "CHANNEL_SOURCE_CODE",
    "MODE_AUTO",
    "MODE_REQUIRE",
    "apply_auto_approval_policy",
    "source_channel",
    "universe_owner_actor",
]
