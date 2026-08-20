"""User-facing mint/revoke/list of inbound webhook URLs (channel-agnostic inbound).

These are WRITE actions on the run surface: a universe's founder mints a stable
`https://<domain>/hooks/<token>` URL for one of THEIR OWN branches, revokes it, or lists
their hooks. Ownership is enforced two ways: the run surface already gates write actions
to a universe the caller can write (per-universe), and mint additionally resolves the
branch within that universe's graph — so a token can only ever be minted for a branch the
caller's own universe owns.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def _public_base_url() -> str:
    """The public origin webhooks are posted to. Canonical is tinyassets.io."""
    return (os.environ.get("TINYASSETS_PUBLIC_BASE_URL") or "https://tinyassets.io").rstrip("/")


def _uid(kwargs: dict[str, Any]) -> str:
    from tinyassets.api.runs import _request_universe

    return _request_universe(kwargs.get("universe_id") or "")


def _action_mint_webhook(kwargs: dict[str, Any]) -> str:
    from tinyassets.api.branches import _resolve_branch_id
    from tinyassets.api.helpers import _base_path
    from tinyassets.daemon_server import get_branch_definition
    from tinyassets.storage import webhook_hooks

    uid = _uid(kwargs)
    if not uid:
        return json.dumps({"error": "mint_webhook requires a universe_id (your own universe)."})
    branch_def_id = str(kwargs.get("branch_def_id", "")).strip()
    if not branch_def_id:
        return json.dumps({"error": "branch_def_id is required."})

    base = _base_path()
    bid = _resolve_branch_id(branch_def_id, base)
    try:
        # Resolving the definition confirms the branch exists and is reachable to this
        # (already write-authorized) universe — a branch the universe does not own is not
        # mintable, and the eventual run is author-gated identically to run_graph.
        get_branch_definition(base, branch_def_id=bid)
    except Exception:  # noqa: BLE001
        return json.dumps({"error": f"branch not found in your universe: {branch_def_id}"})

    token = webhook_hooks.mint(base, universe_id=uid, branch_def_id=bid)
    url = f"{_public_base_url()}/hooks/{token}"
    return json.dumps({
        "text": (
            "Inbound webhook URL created. Paste it into the channel's webhook settings "
            f"(GitHub, Stripe, or any tool that can POST a webhook):\n{url}\n"
            "Each POST to it runs this branch as your universe."
        ),
        "url": url,
        "token": token,
        "branch_def_id": bid,
    })


def _action_revoke_webhook(kwargs: dict[str, Any]) -> str:
    from tinyassets.api.helpers import _base_path
    from tinyassets.storage import webhook_hooks

    uid = _uid(kwargs)
    token = str(kwargs.get("token", "")).strip()
    if not uid or not token:
        return json.dumps({"error": "revoke_webhook requires a universe_id and a token."})
    base = _base_path()
    # Only revoke a token that belongs to THIS universe (never another's).
    binding = webhook_hooks.resolve(base, token=token)
    if binding is None or str(binding.get("universe_id")) != uid:
        # Indistinct: do not reveal whether the token exists for another universe.
        return json.dumps({"text": "No matching webhook to revoke.", "revoked": False})
    revoked = webhook_hooks.revoke(base, token=token)
    return json.dumps({"text": "Webhook revoked." if revoked else "Already revoked.",
                       "revoked": bool(revoked)})


def _action_list_webhooks(kwargs: dict[str, Any]) -> str:
    from tinyassets.api.helpers import _base_path
    from tinyassets.storage import webhook_hooks

    uid = _uid(kwargs)
    if not uid:
        return json.dumps({"error": "list_webhooks requires a universe_id (your own universe)."})
    base = _base_path()
    rows = webhook_hooks.list_for_universe(base, universe_id=uid)
    active = [r for r in rows if r.get("revoked_at") is None]
    base_url = _public_base_url()
    hooks = [{
        "branch_def_id": r["branch_def_id"],
        "url": f"{base_url}/hooks/{r['token']}",
        "created_at": r["created_at"],
    } for r in active]
    return json.dumps({
        "text": f"You have {len(hooks)} active inbound webhook(s).",
        "webhooks": hooks,
        "count": len(hooks),
    })
