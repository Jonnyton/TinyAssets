"""Advisory daily request budgets from local evidence, never a remote quota probe."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from tinyassets.storage import DB_FILENAME

MIN_TURN_REQUESTS = 4
MAX_TURN_REQUESTS = 20
WRAP_UP_REMAINING = 2
LEARNING_MIN_REMAINING = 10


@dataclass(frozen=True)
class RequestBudget:
    used: int
    cap: int
    source_name: str
    reset_timezone: str

    @property
    def remaining(self):
        return self.cap - self.used

    @property
    def planned_requests(self):
        return max(MIN_TURN_REQUESTS, min(MAX_TURN_REQUESTS, self.remaining // 2))

    def prompt_line(self):
        line = (f"Today I have used {self.used} of about {self.cap} free requests on "
                f"{self.source_name} (resets 00:00 {self.reset_timezone}). ")
        if self.remaining <= 0:
            return line + "The allowance is spent."
        return line + (
            f"I plan this turn to finish one working slice within about {self.planned_requests} "
            "requests, including my final reply: I batch reads, save progress to "
            "notes/<project>-progress.md before the final request, and say what is left."
        )


def _read_only(path):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=1)


def requests_today(base_path, owner, source_ref, *, reset_timezone,
                   zero_priced_models=(), now=None):
    """Return (requests, latest successful request ordinal), or None if unreadable.

    Every free-model round counts, including failed and in-flight requests.
    Rounds have no timestamp: bucket by their turn's created_at, including turns
    spanning midnight. Source refs are the journal's opaque connection selectors.
    Price-zero IDs come from the captured catalogue; suffix :free needs no price.
    """
    try:
        current = now or datetime.now(timezone.utc)
        reset = current.astimezone(ZoneInfo(reset_timezone)).replace(
            hour=0, minute=0, second=0, microsecond=0,
        ).astimezone(timezone.utc)
        count = successful = 0
        with closing(_read_only(Path(base_path) / DB_FILENAME)) as conn:
            rows = conn.execute(
                "SELECT t.created_at, r.candidate_json, r.state, r.reply_json "
                "FROM agent_turns t JOIN agent_turn_rounds r "
                "ON (t.owner_user_id = r.owner_user_id AND t.universe_id = r.universe_id "
                "AND t.turn_id = r.turn_id) WHERE t.owner_user_id = ? "
                "AND julianday(t.created_at) >= julianday(?) "
                "AND julianday(t.created_at) <= julianday(?) "
                "ORDER BY t.created_at, t.turn_id, r.ordinal",
                (owner, reset.isoformat(), current.isoformat()),
            )
            for _, raw, state, reply in rows:
                candidate = json.loads(raw)
                if candidate.get("source_ref") != source_ref:
                    continue
                model = candidate.get("model", "")
                if not (model.endswith(":free") or model in zero_priced_models):
                    continue
                count += 1
                if reply is not None and state not in {"failed", "inference_started"}:
                    successful = count
        return count, successful
    except Exception:  # noqa: BLE001 - unavailable advisory evidence never breaks a turn
        return None


def request_budget(base_path, owner, source_ref, model, *, preset, zero_priced_models=(), now=None):
    """One data-driven cap policy; successful requests beyond a cap correct it."""
    try:
        cap = preset.get("free_daily_requests")
        if (type(cap) is not int or cap <= 0
                or not (model.endswith(":free") or model in zero_priced_models)):
            return None
        counts = requests_today(
            base_path, owner, source_ref, reset_timezone=preset["daily_reset_timezone"],
            zero_priced_models=zero_priced_models, now=now,
        )
        if counts is None:
            return None
        used, successful = counts
        if successful > cap:
            cap = preset.get("free_daily_requests_with_credit")
            if type(cap) is not int or cap < successful:
                return None
        return RequestBudget(
            used, cap, preset.get("display_name") or preset["name"],
            preset["daily_reset_timezone"],
        )
    except Exception:  # noqa: BLE001 - advisory only
        return None


def budget_for_context(context, *, owner=None):
    """Resolve installed source facts and captured prices locally, with no IO to a model."""
    try:
        from tinyassets.providers.definition import get_definition
        from tinyassets.providers.free_sources import source_for_host

        selection = context.model_selection
        if selection is None or not selection.connection_id.startswith("api_key_http:"):
            return None
        root = context.universe_dir
        definition = get_definition(
            root.name, selection.connection_id.removeprefix("api_key_http:"),
        )
        if definition is None or (owner is not None and definition.owner_user_id != owner):
            return None
        owner = definition.owner_user_id
        with closing(_read_only(root.parent / "outbound.db")) as conn:
            row = conn.execute(
                "SELECT c.allowed_endpoints_json FROM outbound_connections c "
                "JOIN outbound_connection_grants g ON c.connection_id = g.connection_id "
                "WHERE g.grant_id = ? AND g.owner_user_id = ? AND c.owner_user_id = ? "
                "AND g.universe_id = ? AND g.revoked_at IS NULL AND c.revoked_at IS NULL",
                (definition.ref, owner, owner, root.name),
            ).fetchone()
        if row is None:
            return None
        hosts = {ep["host"] for ep in json.loads(row[0])}
        if len(hosts) != 1:
            return None
        preset = source_for_host(hosts.pop())
        zero = set()
        plan = context.agent_model_plan
        if plan is not None and plan.catalog.owner_id == owner:
            for connection in plan.catalog.connections:
                if connection.connection_id == selection.connection_id:
                    for model in connection.models:
                        price = model.pricing
                        if (price.freshness == "fresh" and not price.unknown_components
                                and price.charges
                                and all(c.amount_micros == 0 for c in price.charges)):
                            zero.add(model.model_id)
        return request_budget(
            root.parent, owner, selection.connection_id, selection.model_id,
            preset=preset, zero_priced_models=zero,
        )
    except Exception:  # noqa: BLE001 - no prompt or guard on unknown budgets
        return None
