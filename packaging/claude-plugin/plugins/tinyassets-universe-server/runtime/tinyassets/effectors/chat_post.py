"""Deliver a node's output to a chat destination.

Why this exists, and why it is this small
-----------------------------------------
A founder asked their agent "the niche watcher runs but I never see anything —
deliver it to me here". The agent did the right thing without being told how: it
DEFINED an operation scope called ``chat_post``, composed a two-node branch
(``scan`` -> ``deliver``) and declared ``effects: ["chat_post"]`` on the delivery
node, with a prompt telling it to post the brief "exactly as written".

That design was correct and nothing implemented the name. This is that
implementation — deliberately the effector and nothing else. Delivery is not a
platform feature with its own scheduling and destinations; it is an effect a
user's branch declares, exactly like ``github_merge``. The composition stays the
user's.

Where the destination comes from
--------------------------------
The RUN's inputs, because those are what the user's automation supplies. A
branch that delivers declares ``channel_id`` among its inputs and the automation
carries it, so the same branch can be pointed at a DM, a channel, or a different
workspace by changing the automation rather than the branch.

The bot token never appears here: `build_slack_transport` resolves it from the
universe's own vault, the same path `deliver_app_event` posts replies through.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: The sink name a node declares in ``effects``.
EXTERNAL_WRITE_SINK_CHAT_POST = "chat_post"

#: Run-state keys checked, in order, for where to deliver.
_DESTINATION_KEYS = ("channel_id", "chat_channel_id", "deliver_to")

#: Slack rejects an empty post, and a "delivered" receipt for nothing is worse
#: than a visible failure.
_MAX_CHARS = 39000


def _first_present(run_state: Any, keys: tuple[str, ...]) -> str:
    for key in keys:
        try:
            value = run_state.get(key)
        except AttributeError:
            return ""
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _body_from(run_state: Any, output_keys: list[str]) -> str:
    """The node's own output is the deliverable. First non-empty output key."""
    for key in output_keys:
        try:
            value = run_state.get(key)
        except AttributeError:
            return ""
        if isinstance(value, str):
            # Whitespace-only counts as nothing. Checking truthiness alone lets
            # "   " through the non-string branch below and "delivers" a blank
            # post — caught by test, not by reading.
            stripped = value.strip()
            if stripped:
                return stripped[:_MAX_CHARS]
            continue
        if value not in (None, "", [], {}):
            return str(value)[:_MAX_CHARS]
    return ""


def run_chat_post_effector(
    *,
    node_id: str,
    output_keys: list[str],
    run_state: Any,
    base_path: str | Path | None = None,
    run_id: str = "",
    dry_run: bool = False,
    universe_id: str = "",
    transport: Any = None,
) -> dict[str, Any]:
    """Post one node's output to chat. Returns evidence, never raises.

    Never raising is deliberate and matches `github_merge`: this runs on the
    completion path, and a delivery failure must be recorded as evidence rather
    than take down a run whose actual work already succeeded.
    """
    body = _body_from(run_state, list(output_keys or []))
    if not body:
        return {
            "error": (
                f"node '{node_id}' declared effects=[chat_post] but produced no "
                "text in any output key — nothing to deliver"
            ),
            "error_kind": "nothing_to_deliver",
        }

    destination = _first_present(run_state, _DESTINATION_KEYS)
    if not destination:
        return {
            "error": (
                f"node '{node_id}' declared effects=[chat_post] but the run has "
                f"no destination — supply one of {', '.join(_DESTINATION_KEYS)} "
                "in the automation's inputs"
            ),
            "error_kind": "no_destination",
        }

    if dry_run:
        return {
            "dry_run": True,
            "destination": destination,
            "characters": len(body),
        }

    uid = (universe_id or "").strip() or _first_present(run_state, ("universe_id",))
    if not uid:
        return {
            "error": "chat_post could not resolve which universe is delivering",
            "error_kind": "no_universe",
        }

    try:
        if transport is None:
            from tinyassets.api.helpers import _universe_dir
            from tinyassets.effectors.slack_transport import build_slack_transport

            transport = build_slack_transport(_universe_dir(uid))
        from tinyassets.app_reply_authority import ReplyDestination

        receipt = transport(
            ReplyDestination(
                provider="slack", connection_id="slack-main", address=destination
            ),
            body,
            thread_ts="",
        )
    except Exception as exc:  # noqa: BLE001 - evidence, never a raised run failure
        logger.warning("chat_post: delivery failed for node %s", node_id)
        return {
            "error": f"delivery failed: {type(exc).__name__}",
            "error_kind": "delivery_failed",
        }

    return {
        "delivered": True,
        "destination": destination,
        "characters": len(body),
        "provider_receipt_ref": str(
            getattr(receipt, "provider_receipt_ref", "") or ""
        ),
        "run_id": run_id,
    }


__all__ = ["EXTERNAL_WRITE_SINK_CHAT_POST", "run_chat_post_effector"]
