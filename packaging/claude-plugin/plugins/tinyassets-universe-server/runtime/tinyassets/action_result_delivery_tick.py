"""Production wiring for async action-result delivery (Slice 3).

Constructs the real ``get_run`` / ``authorize`` / ``adapter`` seams around the
governed :func:`tinyassets.action_result_delivery.deliver_pending_action_results`
core, and runs it on a periodic daemon thread (the established
``universe_server.main`` idiom, sibling to the served-budget lease loop).

The seams are module functions so the decision logic stays testable without a live
run queue or Slack transport; the loop is a thin scheduler over the core.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: How often the delivery tick runs. Follow-ups are not latency-critical; this keeps
#: the load trivial while still delivering within a minute of a run going terminal.
TICK_INTERVAL_S = 30.0

#: Only these run-output fields may become a user-facing public result reference, and
#: only if they ALSO pass the delivery core's strict allowlist. A deliberate, minimal
#: projection — never the whole ``output`` (which could carry internal detail).
_PUBLIC_REF_KEYS = ("public_result_ref", "result_url", "pr_url", "html_url")


def production_get_run(base_path: str | Path, run_id: str) -> dict[str, Any] | None:
    """The run row, with a DELIBERATE public-result-ref projection from ``output``.

    We never hand ``compose_summary`` the raw ``output`` dict (which may hold internal
    detail); we surface only a single known public reference key, and the core's
    allowlist still validates it before it can reach a user.
    """
    from tinyassets.runs import get_run

    run = get_run(Path(base_path), run_id)
    if not isinstance(run, dict):
        return None
    output = run.get("output")
    if isinstance(output, dict) and not run.get("public_result_ref"):
        for key in _PUBLIC_REF_KEYS:
            val = output.get(key)
            if isinstance(val, str) and val:
                run = {**run, "public_result_ref": val}
                break
    return run


def production_authorize(entry: dict[str, Any], summary: str) -> Any | None:
    """Re-resolve, FRESH, whether a follow-up may be posted to this conversation.

    Routes exactly as an inbound turn would, from server-side bindings only, and
    authorizes ONLY if the binding still resolves to the SAME universe the run belongs
    to. A binding that was changed or removed since the run was recorded yields None
    (HOLD) — we never post to a conversation the universe no longer owns.
    """
    from tinyassets.app_ingress import _route

    routed = _route(
        api_app_id=str(entry.get("app_binding_ref") or ""),
        workspace_id=str(entry.get("workspace_id") or ""),
        channel_id=str(entry.get("channel_id") or ""),
    )
    if routed is None or str(getattr(routed, "universe_id", "")) != str(
        entry.get("universe_id") or ""
    ):
        return None
    return (routed, entry)


class ProductionAdapter:
    """Posts the follow-up through the daemon's own governed outbound path.

    Reuses the server-side post (the same path a turn's reply takes), so a follow-up
    is NOT recorded as a universe utterance and carries no authority. HONORS the
    ``idempotency_key`` via a receipt store (Codex hardening #1): if this key was
    already posted (a crash between post and mark, then a reclaim + retry), it returns
    the cached receipt WITHOUT re-posting — closing the crash double-post the outbox
    claim/fencing alone cannot (Slack has no native idempotency).
    """

    def __init__(self, base_path: str | Path):
        self._base = base_path

    def deliver(self, authorization: Any, response: str, idempotency_key: str | None = None) -> str:
        from tinyassets.app_ingress import _post
        from tinyassets.storage import action_result_outbox as outbox

        if idempotency_key:
            prior = outbox.receipt_seen(self._base, idempotency_key=idempotency_key)
            if prior:
                return prior  # already delivered under this key — do not double-post

        routed, entry = authorization
        receipt = _post(
            routed=routed,
            channel_id=str(entry.get("channel_id") or ""),
            body=response,
            thread_ts=str(entry.get("thread_ts") or ""),
            transport=None,
        )
        if idempotency_key and receipt:
            outbox.record_receipt(self._base, idempotency_key=idempotency_key, receipt=receipt)
        return receipt


def run_delivery_tick(base_path: str | Path, *, now: float | None = None) -> dict[str, int]:
    """One delivery pass over the outbox with the production seams. Never raises."""
    from tinyassets.action_result_delivery import deliver_pending_action_results

    try:
        return deliver_pending_action_results(
            base_path,
            get_run=production_get_run,
            authorize=production_authorize,
            adapter=ProductionAdapter(base_path),
            now=now,
        )
    except Exception:  # noqa: BLE001 - a tick must never take the loop down
        logger.exception("action-result delivery tick failed")
        return {"delivered": 0, "skipped_running": 0, "held": 0}


def start_delivery_loop(base_path: str | Path) -> threading.Thread:
    """Start the periodic delivery tick on a daemon thread. Returns the thread."""
    import time as _time

    def _loop() -> None:
        while True:
            _time.sleep(TICK_INTERVAL_S)
            counts = run_delivery_tick(base_path)
            if counts.get("delivered"):
                logger.info(
                    "action-result: delivered %d follow-up(s)", counts["delivered"]
                )

    thread = threading.Thread(
        target=_loop, name="action-result-delivery", daemon=True,
    )
    thread.start()
    return thread
