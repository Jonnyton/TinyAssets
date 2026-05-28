"""Fantasy-domain TaskProducers (Phase C.4).

Three producers wrap existing universe-cycle logic so the daemon can
iterate them uniformly. Registration happens in
``domains/fantasy_daemon/__init__.py`` at import time:

    SeedProducer           — origin="seed"
    FantasyAuthorialProducer — origin="fantasy_authorial"
    UserRequestProducer    — origin="user_request"

Registration order IS dispatch order (spec §1.2). Later producers
overwrite earlier ones on target_id collision.
"""

from __future__ import annotations

import logging
from pathlib import Path

from workflow.universe_soul import premise_from_soul, read_legacy_premise
from workflow.work_targets import (
    WorkTarget,
    ensure_seed_targets,
    list_selectable_targets,
    materialize_pending_requests,
)

logger = logging.getLogger(__name__)


def _read_premise(universe_path: Path) -> str:
    """Read premise from compatibility file or soul.md purpose."""
    path = Path(universe_path)
    return read_legacy_premise(path) or premise_from_soul(path)


class SeedProducer:
    """Wraps ``ensure_seed_targets`` so first-boot seeds become a
    producer in the C.4 pipeline.

    Idempotent by construction — ``ensure_seed_targets`` no-ops when
    targets already exist. The cycle-time cost is trivial (one JSON
    read); no need for a ``first_run`` flag.
    """

    name = "seed"
    origin = "seed"

    def produce(
        self,
        universe_path: Path,
        *,
        config: dict | None = None,
    ) -> list[WorkTarget]:
        premise = _read_premise(universe_path)
        return ensure_seed_targets(universe_path, premise=premise)


class FantasyAuthorialProducer:
    """Emits candidate WorkTargets from the existing registry via
    ``list_selectable_targets``.

    Spec §5 draws the line: this producer wraps the *candidate-scoring
    pre-scoring step*, not the scoring itself. Scoring stays in
    ``choose_authorial_targets`` (C.5 wires the override).
    """

    name = "fantasy_authorial"
    origin = "fantasy_authorial"

    def produce(
        self,
        universe_path: Path,
        *,
        config: dict | None = None,
    ) -> list[WorkTarget]:
        return list_selectable_targets(universe_path)


class UserRequestProducer:
    """Wraps ``materialize_pending_requests`` so MCP `submit_request`
    entries flow through the producer pipeline.

    Produces one ROLE_NOTES target per pending request, tagged
    ``user-request``. Idempotent on ``request_id`` (target_id is
    ``request-<req_id>``, upsert-safe).
    """

    name = "user_request"
    origin = "user_request"

    def produce(
        self,
        universe_path: Path,
        *,
        config: dict | None = None,
    ) -> list[WorkTarget]:
        return materialize_pending_requests(universe_path)


def register_fantasy_producers() -> None:
    """Register the three fantasy producers in spec order.

    Idempotent: safe to call on module reload (re-register replaces
    by name). Called from ``domains/fantasy_daemon/__init__.py``.
    """
    from workflow.producers import register
    register(SeedProducer())
    register(FantasyAuthorialProducer())
    register(UserRequestProducer())
