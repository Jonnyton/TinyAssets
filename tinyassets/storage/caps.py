"""Per-subsystem storage caps (BUG-023 Phase 3).

Primitives for soft/hard cap enforcement against the subsystem byte
counts reported by :func:`tinyassets.storage.inspect_storage_utilization`.

Design:
- Caps configured via env vars: ``TINYASSETS_CAP_CHECKPOINTS_BYTES``,
  ``TINYASSETS_CAP_LOGS_BYTES``, ``TINYASSETS_CAP_RUN_ARTIFACTS_BYTES``.
  Unset / zero / negative → cap disabled (status always ``ok``).
- Soft cap fires at ``SOFT_RATIO`` (default 0.80) of the hard cap.
- Hard cap = 1.0 of configured value. Hitting it triggers
  :class:`tinyassets.exceptions.StorageCapExceeded`.
- ``check_subsystem_cap`` is a pure observation — returns the status,
  never raises. Callers use it to decide if a write should proceed,
  emit a WARNING, or abort early.
- ``enforce_write_cap`` is the loud-refuse path: logs WARNING on soft,
  raises on hard. Use at write boundaries.

The caps primitive does NOT walk the filesystem itself — callers pass
``current_bytes`` in to keep the hot path cheap. ``storage_utilization``
already computes the per-subsystem bytes once per probe; callers can
reuse that number rather than re-walking.
"""
from __future__ import annotations

import logging
import os
from typing import Literal

from tinyassets.exceptions import StorageCapExceeded

logger = logging.getLogger(__name__)

#: Soft-cap threshold as a fraction of the configured hard cap.
SOFT_RATIO = 0.80

#: Subsystem → environment variable mapping. Unset / zero disables.
_SUBSYSTEM_CAP_ENV_VARS: dict[str, str] = {
    "checkpoints": "TINYASSETS_CAP_CHECKPOINTS_BYTES",
    "logs": "TINYASSETS_CAP_LOGS_BYTES",
    "run_artifacts": "TINYASSETS_CAP_RUN_ARTIFACTS_BYTES",
}


CapStatus = Literal["ok", "warn", "exceeded", "unbounded"]


def _read_cap_bytes(subsystem: str) -> int:
    """Return the hard-cap bytes for ``subsystem``, or 0 if disabled."""
    env_var = _SUBSYSTEM_CAP_ENV_VARS.get(subsystem)
    if not env_var:
        return 0
    raw = os.environ.get(env_var, "").strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "%s=%r is not an integer; cap disabled",
            env_var, raw,
        )
        return 0
    if value <= 0:
        return 0
    return value


def check_subsystem_cap(
    subsystem: str,
    current_bytes: int,
) -> CapStatus:
    """Classify a subsystem's usage against its configured cap.

    Returns one of:
      - ``"unbounded"``: no cap configured (env var unset / zero).
      - ``"ok"``:        below soft threshold.
      - ``"warn"``:      at or above soft, below hard.
      - ``"exceeded"``:  at or above hard.

    Pure function — never raises, never writes. Callers decide whether
    to honor the signal.
    """
    hard_cap = _read_cap_bytes(subsystem)
    if hard_cap <= 0:
        return "unbounded"

    if current_bytes >= hard_cap:
        return "exceeded"
    if current_bytes >= int(hard_cap * SOFT_RATIO):
        return "warn"
    return "ok"


def enforce_write_cap(
    subsystem: str,
    current_bytes: int,
    *,
    additional_bytes: int = 0,
) -> None:
    """Gate a pending write against the subsystem's cap.

    Call at write boundaries (e.g. before appending to a checkpoint or
    spilling a large run artifact). ``current_bytes`` + ``additional_bytes``
    represents the projected post-write size; the check runs against that.

    Raises
    ------
    StorageCapExceeded
        When projected usage >= the configured hard cap. Hard Rule #8:
        refuse loudly instead of silently letting the volume fill.

    Emits a WARNING log line when projected usage enters the soft band
    (80-99% of the cap). Unbounded subsystems are no-ops.
    """
    projected = max(0, current_bytes) + max(0, additional_bytes)
    status = check_subsystem_cap(subsystem, projected)

    if status == "exceeded":
        hard_cap = _read_cap_bytes(subsystem)
        raise StorageCapExceeded(
            f"subsystem {subsystem!r} at {projected} bytes would exceed "
            f"hard cap {hard_cap} (configured via "
            f"{_SUBSYSTEM_CAP_ENV_VARS.get(subsystem, '?')}). "
            "Rotate or prune older artifacts before retrying."
        )
    if status == "warn":
        hard_cap = _read_cap_bytes(subsystem)
        logger.warning(
            "storage cap soft-threshold crossed: %s at %d bytes "
            "(soft=%d, hard=%d). Rotate before hard cap hit.",
            subsystem, projected, int(hard_cap * SOFT_RATIO), hard_cap,
        )


def subsystem_cap_snapshot(
    per_subsystem_bytes: dict[str, int],
) -> dict[str, dict[str, object]]:
    """Build a cap-status block for :func:`inspect_storage_utilization`.

    Returns ``{subsystem: {status, hard_cap_bytes, soft_cap_bytes}}``
    for each cap-configurable subsystem. Subsystems whose current size
    is unknown (missing from ``per_subsystem_bytes``) are reported as
    ``current_bytes=0``.
    """
    snapshot: dict[str, dict[str, object]] = {}
    for subsystem in _SUBSYSTEM_CAP_ENV_VARS:
        hard_cap = _read_cap_bytes(subsystem)
        current = per_subsystem_bytes.get(subsystem, 0)
        snapshot[subsystem] = {
            "status": check_subsystem_cap(subsystem, current),
            "hard_cap_bytes": hard_cap,
            "soft_cap_bytes": int(hard_cap * SOFT_RATIO) if hard_cap else 0,
            "current_bytes": current,
        }
    return snapshot
