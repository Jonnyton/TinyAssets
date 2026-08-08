"""Run scheduled automations and deliver what they produce.

Why this exists
---------------
`storage/scheduled_work.py` stores `cadence_seconds` and `deliver_to`, the
agent builds automations around them, and until this module NOTHING read
either field. Verified live 2026-08-08 (run `25b32388ab12425a`): the run
completed, its output sat in the checkpoint DB, `deliver_to` was a stored
string nobody posted to, and no process existed that would ever fire the
daily cadence. The agent told its founder "first briefing arrives tomorrow
morning" — a promise the platform could not keep. Build is not run.

Shape
-----
One sweep, two jobs, both idempotent:

1. FIRE — every active automation whose cadence has elapsed (or that has
   never run) gets its branch executed through the same `run_graph` path
   `run_automation_now` uses, and the run recorded.
2. DELIVER — every automation whose latest recorded run is finished and not
   yet delivered gets that run's produced output posted to its `deliver_to`
   destination, exactly once (`delivered_run_id` is the marker). A FAILED run
   is delivered too, as a failure notice — silence is the one output a
   founder must never receive (hard rule: fail loudly).

Run-now runs are picked up by the same delivery sweep because
`run_automation_now` records the run id the sweep keys on. Delivery is a
consequence of a run existing, not of who started it.

The sweep runs on a daemon thread started by `universe_server.main()`.
`TINYASSETS_DISABLE_SCHEDULED_WORK=1` is the kill switch; the default is ON
because a workflow gate must have an autonomous default.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: Seconds between sweeps. Cadence floor is 60s, so half that keeps worst-case
#: schedule drift under one sweep without busy-looping.
DEFAULT_INTERVAL_SECONDS = 30.0

DISABLE_ENV = "TINYASSETS_DISABLE_SCHEDULED_WORK"


def _default_run(item: Any) -> str:
    """Execute the automation's branch — the same path run_now uses."""
    from tinyassets.universe_server import run_graph

    return run_graph(
        branch_def_id=item.branch_def_id,
        graph_id=item.universe_id,
        inputs_json=item.inputs_json,
        run_name=f"{item.name} (scheduled)",
    )


def _default_get_run(base_path: Path, run_id: str) -> dict | None:
    from tinyassets.runs import get_run

    return get_run(base_path, run_id)


def _default_post(universe_id: str, address: str, body: str) -> None:
    from tinyassets.api.helpers import _universe_dir
    from tinyassets.app_reply_authority import ReplyDestination
    from tinyassets.effectors.slack_transport import build_slack_transport

    build_slack_transport(_universe_dir(universe_id))(
        ReplyDestination(
            provider="slack", connection_id="slack-main", address=address
        ),
        body,
        thread_ts="",
    )


def _slack_address(deliver_to: str) -> str:
    """`slack:TEAM:ADDRESS` or a bare channel/user id -> the address, else ''."""
    value = (deliver_to or "").strip()
    if not value:
        return ""
    if value.startswith("slack:"):
        return value.rsplit(":", 1)[-1].strip()
    # A bare Slack id (D…/C…/U…) is accepted as-is; anything else is a
    # destination this executor does not know how to reach.
    if value[:1] in {"C", "D", "U"} and value.isalnum():
        return value
    return ""


def _delivery_body(item: Any, record: dict) -> str:
    """What the founder receives: the produced text, or an honest failure."""
    status = str(record.get("status") or "")
    run_id = str(record.get("run_id") or item.last_run_id)
    if status == "failed":
        error = str(record.get("error") or "no error recorded")[:400]
        return (
            f"*{item.name}* run `{run_id}` FAILED: {error}\n"
            "Ask me to look into it and I will."
        )
    output = record.get("output")
    if not isinstance(output, dict):
        output = {}
    inputs = record.get("inputs")
    input_keys = set(inputs.keys()) if isinstance(inputs, dict) else set()
    produced = {
        key: str(value).strip()
        for key, value in output.items()
        if key not in input_keys and str(value or "").strip()
    }
    if not produced:
        return (
            f"*{item.name}* run `{run_id}` finished but produced no output — "
            "that is a bug worth telling me about."
        )
    if len(produced) == 1:
        text = next(iter(produced.values()))
        return f"*{item.name}*:\n{text[:3500]}"
    sections = "\n\n".join(
        f"*{key}*:\n{value[:1500]}" for key, value in produced.items()
    )
    return f"*{item.name}*:\n{sections}"[:3900]


class ScheduledWorkExecutor:
    """Fires due automations and delivers finished runs. One instance per daemon."""

    def __init__(
        self,
        base_path: str | Path,
        *,
        interval: float = DEFAULT_INTERVAL_SECONDS,
        run: Callable[[Any], str] | None = None,
        get_run: Callable[[Path, str], dict | None] | None = None,
        post: Callable[[str, str, str], None] | None = None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.base_path = Path(base_path)
        self.interval = float(interval)
        self._run = run or _default_run
        self._get_run = get_run or (
            lambda base, rid: _default_get_run(base, rid)
        )
        self._post = post or _default_post
        self._now = now
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- one sweep -----------------------------------------------------------

    def sweep(self) -> dict[str, int]:
        """Fire due automations, deliver finished runs. Returns counts."""
        from tinyassets.storage.scheduled_work import ScheduledWorkStore

        store = ScheduledWorkStore(self.base_path)
        fired = self._fire_due(store)
        delivered = self._deliver_finished(store)
        return {"fired": fired, "delivered": delivered}

    def _fire_due(self, store: Any) -> int:
        count = 0
        for item in store.list_due(now=self._now()):
            raw = ""
            try:
                raw = self._run(item)
            except Exception:  # noqa: BLE001 - one bad automation must not stop the rest
                logger.exception(
                    "scheduled run failed to start: %s/%s",
                    item.universe_id, item.work_id,
                )
            run_id = ""
            try:
                run_id = str((json.loads(raw) or {}).get("run_id") or "")
            except (TypeError, ValueError):
                pass
            # Record even a failed hand-off attempt so a broken automation
            # retries next CADENCE, not every sweep (a 30s retry loop against
            # a broken branch is a spend leak, not persistence).
            store.record_run(
                universe_id=item.universe_id,
                work_id=item.work_id,
                run_id=run_id or f"unstarted_{int(self._now())}",
            )
            if run_id:
                count += 1
                logger.info(
                    "scheduled_work fired %s/%s run=%s",
                    item.universe_id, item.name, run_id,
                )
        return count

    def _deliver_finished(self, store: Any) -> int:
        count = 0
        for item in store.list_undelivered():
            run_id = item.last_run_id
            if run_id.startswith("unstarted_"):
                # Nothing ever ran; there is no result to deliver.
                store.record_delivery(
                    universe_id=item.universe_id,
                    work_id=item.work_id,
                    run_id=run_id,
                )
                continue
            try:
                record = self._get_run(self.base_path, run_id)
            except Exception:  # noqa: BLE001
                logger.exception("could not read run %s", run_id)
                continue
            if not record or str(record.get("status") or "") not in (
                "completed", "failed",
            ):
                continue  # still running — next sweep will look again
            address = _slack_address(item.deliver_to)
            if not address:
                # Nowhere to deliver. Mark delivered so this is not retried
                # forever, but say so loudly in the log.
                logger.warning(
                    "scheduled_work %s/%s finished run %s but deliver_to=%r "
                    "is not a deliverable destination",
                    item.universe_id, item.name, run_id, item.deliver_to,
                )
                store.record_delivery(
                    universe_id=item.universe_id,
                    work_id=item.work_id,
                    run_id=run_id,
                )
                continue
            body = _delivery_body(item, record)
            try:
                self._post(item.universe_id, address, body)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "delivery failed for %s/%s run %s — will retry next sweep",
                    item.universe_id, item.name, run_id,
                )
                continue
            store.record_delivery(
                universe_id=item.universe_id,
                work_id=item.work_id,
                run_id=run_id,
            )
            count += 1
            logger.info(
                "scheduled_work delivered %s/%s run=%s to %s",
                item.universe_id, item.name, run_id, address,
            )
        return count

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return

        def _loop() -> None:
            while not self._stop.wait(self.interval):
                try:
                    self.sweep()
                except Exception:  # noqa: BLE001 - the loop must survive any sweep
                    logger.exception("scheduled_work sweep failed")

        self._thread = threading.Thread(
            target=_loop, name="scheduled-work-executor", daemon=True
        )
        self._thread.start()
        logger.info(
            "scheduled_work executor started (interval=%.0fs)", self.interval
        )

    def stop(self) -> None:
        self._stop.set()


def start_default_executor() -> ScheduledWorkExecutor | None:
    """Start the executor for the daemon process, unless disabled by env."""
    if (os.environ.get(DISABLE_ENV) or "").strip().lower() in {"1", "true", "yes"}:
        logger.info("scheduled_work executor disabled by %s", DISABLE_ENV)
        return None
    from tinyassets.api.helpers import _base_path

    executor = ScheduledWorkExecutor(_base_path())
    executor.start()
    return executor


__all__ = [
    "DEFAULT_INTERVAL_SECONDS",
    "DISABLE_ENV",
    "ScheduledWorkExecutor",
    "start_default_executor",
]
