"""Container healthcheck asserting the daemon is ALIVE, not just running.

docs/specs/daemon-liveness-watchdog.md §1: the stock ``docker inspect``
healthcheck is a false positive — it reports "container alive" when the
condition that matters is "container alive AND the supervisor is beating
AND pickable work is actually being picked up". The 2026-06 dormancy
(worker wedged June 3-10, container "healthy" throughout) is the failure
class this closes: with ``restart: unless-stopped`` plus this check, a
wedged worker self-heals via container restart instead of waiting for a
human to notice.

Exit codes:
    0  healthy (supervisor beating; no stuck pickable work).
    1  unhealthy — one-line reason on stderr.

Wire-up (deploy/compose.yml ``worker`` service):

    healthcheck:
      test: ["CMD", "python", "-m", "workflow.cloud_worker_healthcheck"]
      interval: 60s
      timeout: 15s
      retries: 3
      start_period: 120s

Stdlib only; read-only against the universe dir.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Beat older than this is always unhealthy, regardless of planned sleep
# floor — matches the spec's "no supervisor heartbeat for >5min" rule.
STALE_FLOOR_S = 300.0
# Grace added on top of the supervisor's own declared backoff sleep.
PLANNED_SLEEP_GRACE_S = 120.0
# With pickable work present the supervisor must beat at least this often
# (it polls at sub-second granularity while a subprocess runs, and a fresh
# spawn beats immediately). Catches "work arrived mid-backoff and the
# supervisor is sleeping through it" as well as a wedged supervisor.
PICKABLE_STALE_S = 180.0


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc,
        )
    except (TypeError, ValueError):
        return None


def check(universe: Path, *, now: datetime | None = None) -> tuple[bool, str]:
    """Return (healthy, reason). Pure logic — testable without a container."""
    from workflow.cloud_worker import SUPERVISOR_HEARTBEAT_FILENAME

    now = now or datetime.now(timezone.utc)
    beat_path = universe / SUPERVISOR_HEARTBEAT_FILENAME
    if not beat_path.exists():
        return False, f"no supervisor heartbeat at {beat_path}"
    try:
        beat = json.loads(beat_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, f"unreadable supervisor heartbeat: {exc}"

    ts = _parse_ts(str(beat.get("ts", "")))
    if ts is None:
        return False, f"heartbeat has no parseable ts: {beat.get('ts')!r}"
    age_s = (now - ts).total_seconds()

    planned_sleep = float(beat.get("planned_sleep_s") or 0.0)
    allowed = max(STALE_FLOOR_S, planned_sleep + PLANNED_SLEEP_GRACE_S)
    if age_s > allowed:
        return False, (
            f"supervisor beat stale: age={age_s:.0f}s allowed={allowed:.0f}s "
            f"phase={beat.get('phase')}"
        )

    try:
        from workflow.cloud_worker import _has_pickable_branch_task

        pickable = _has_pickable_branch_task(universe)
    except Exception as exc:  # noqa: BLE001 — probe must report, not crash
        return False, f"queue probe failed: {exc}"
    if pickable and age_s > PICKABLE_STALE_S:
        return False, (
            f"pickable work waiting but supervisor beat is {age_s:.0f}s old "
            f"(phase={beat.get('phase')})"
        )

    return True, (
        f"ok: beat age={age_s:.0f}s phase={beat.get('phase')} "
        f"pickable={pickable}"
    )


def main(argv: list[str] | None = None) -> int:
    from workflow.cloud_worker import _resolve_universe_path

    universe = _resolve_universe_path()
    healthy, reason = check(universe)
    if healthy:
        print(reason)
        return 0
    print(reason, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
