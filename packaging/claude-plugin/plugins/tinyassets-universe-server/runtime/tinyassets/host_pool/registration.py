"""Host-pool registration — tray startup flow.

Wave 1 per Track D: on tray startup, create a ``host_pool`` row with
the daemon's declared capabilities + visibility. Returns the new
``host_id`` which the caller holds for the session (heartbeat +
deregistration target).

Idempotent. If a row already exists for (owner_user_id, capability_id)
— best-effort lookup first, else insert. Row version column handles
concurrent-startup conflicts in a race-aware but lenient way (not
load-bearing for Wave 1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from tinyassets.host_pool.client import HostPoolClient, HostPoolRow

logger = logging.getLogger(__name__)


@dataclass
class Registration:
    """What a caller gets back from ``register_daemon``.

    ``row`` is the authoritative row state (insertion OR pre-existing).
    ``created`` tells the caller whether this invocation inserted a new
    row (True) or reused an existing one (False). Useful for log lines.
    """

    row: HostPoolRow
    created: bool


def register_daemon(
    client: HostPoolClient,
    *,
    owner_user_id: str,
    provider: str,
    capability_id: str,
    visibility: str = "self",
    price_floor: float | None = None,
    max_concurrent: int = 1,
    always_active: bool = False,
    # Capability-row auto-provisioning (per Track A §7 OPEN resolution).
    capability_node_type: str | None = None,
    capability_llm_model: str | None = None,
    capability_description: str | None = None,
) -> Registration:
    """Ensure the daemon is registered. Return its host_pool row.

    Behavior:
        1. Ensure the capability row exists (insert-if-missing). If the
           caller didn't pass node_type + llm_model, we derive them by
           splitting ``capability_id`` on the first ``:`` — matches the
           shape ``<node_type>:<llm_model>`` Track A uses as canonical.
        2. Insert a new ``host_pool`` row. Returns it.

    We do NOT look up pre-existing rows by owner+capability then skip
    insert — schema has no unique on (owner, capability), so multiple
    rows per (user, capability) are legal (e.g. two daemons on the same
    box with different max_concurrent). Callers that want singleton
    semantics should track the host_id themselves between runs.
    """
    node_type = capability_node_type
    llm_model = capability_llm_model
    if node_type is None or llm_model is None:
        # Split ``node_type:llm_model`` — matches canonical capability_id
        # shape. Fall back to the whole capability_id as node_type if
        # there's no colon (defensive; callers should supply explicit
        # values when capability_id doesn't parse).
        if ":" in capability_id:
            default_node, default_llm = capability_id.split(":", 1)
        else:
            default_node, default_llm = capability_id, "unknown"
        node_type = node_type or default_node
        llm_model = llm_model or default_llm

    client.ensure_capability(
        capability_id,
        node_type=node_type,
        llm_model=llm_model,
        description=capability_description,
    )

    row = client.register(
        owner_user_id=owner_user_id,
        provider=provider,
        capability_id=capability_id,
        visibility=visibility,
        price_floor=price_floor,
        max_concurrent=max_concurrent,
        always_active=always_active,
    )
    logger.info(
        "host_pool: registered host_id=%s owner=%s capability=%s visibility=%s",
        row.host_id, owner_user_id, capability_id, visibility,
    )
    return Registration(row=row, created=True)
