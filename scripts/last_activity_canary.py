"""last_activity_canary — prove node execution is 24/7, not just MCP surface.

Complements ``mcp_public_canary`` (handshake) and ``mcp_tool_canary``
(tools/list + universe inspect). Those catch "daemon is dark" and "tool
handler crashed" but NEITHER catches "MCP is green but node execution
is stalled" — which is exactly the state we saw live on 2026-04-22
before Task #14 landed the cloud-side worker.

This canary asserts the daemon has done *actual work* within N minutes
by reading ``daemon.last_activity_at`` from the ``universe action=
inspect`` tool result and comparing against ``now - threshold``.

Why ``universe inspect`` (not ``get_status``)
---------------------------------------------
The task spec said ``get_status.daemon.last_activity_at``, but the
actual ``get_status`` MCP tool doesn't expose a direct ``daemon``
block with that field — its surface is oriented toward privacy /
routing evidence (``active_host``, ``tier_routing_policy``,
``evidence.activity_log_tail``, etc.). The ``universe action=inspect``
tool IS the canonical surface for the ``daemon.last_activity_at``
field (see ``workflow/universe_server.py:1690``). This canary reads
that one.

Exit codes (task #15 spec)
--------------------------
  0  last_activity_at is within the threshold (FRESH)
  2  last_activity_at exceeds the threshold (STALE)
  3  daemon responded but no parseable last_activity_at field
     (tool returned an unexpected shape, or field is null/malformed)
  4  handshake / connectivity failure (overlaps with mcp_public_canary
     — this canary doesn't duplicate that path, just fails loudly
     with a distinct code so operators can tell stale-execution from
     dark-daemon at a glance)

Grace handling
--------------
Per task spec: daemon may legitimately be idle (no pending work).
Decision — page anyway. Rationale: "true 24/7 independence means
'always working on something' once there's work to do." If the queue
is empty, that's a product signal (nothing to do) that's still worth
noticing because the paid-market is supposed to be keeping daemons
fed. A persistent stale-but-queue-empty state IS a pageable condition
because it means the paid market isn't working either. Coupling to
``pending_requests > 0`` is flagged as a follow-up if the simpler
decision is noisy in prod.

Usage
-----
    python scripts/last_activity_canary.py
    python scripts/last_activity_canary.py --url http://127.0.0.1:8001/mcp
    python scripts/last_activity_canary.py --threshold-min 60 --verbose

Env overrides
-------------
    WORKFLOW_LAST_ACTIVITY_THRESHOLD_MIN   default threshold (min)

Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from functools import partial
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _canary_common import (  # noqa: E402
    _INITIALIZED_NOTIF,  # noqa: F401
    _extract_structured_tool_payload,
    _extract_tool_text,
    _init_payload,
)
from _canary_common import _post as _post_raw  # noqa: E402

DEFAULT_URL = "https://tinyassets.io/mcp"
DEFAULT_THRESHOLD_MIN = 30
DEFAULT_TIMEOUT = 20.0

_INIT_PAYLOAD = _init_payload("last-activity-canary")


class LastActivityError(Exception):
    """Raised by any step; carries the exit code so main() can exit with it."""

    def __init__(self, code: int, msg: str) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg


# `_post` is the shared HTTP+parse path from `_canary_common`, partially
# applied with this canary's exception constructor + User-Agent.
_post = partial(
    _post_raw,
    error_factory=LastActivityError,
    user_agent="workflow-last-activity-canary/1.0",
)


def _parse_iso(value: str) -> _dt.datetime | None:
    """Parse an ISO-8601 timestamp, returning timezone-aware UTC datetime."""
    if not value:
        return None
    try:
        # Accept both "Z" suffix and "+00:00" style.
        text = value.replace("Z", "+00:00") if value.endswith("Z") else value
        parsed = _dt.datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc)


def classify_freshness(
    last_activity_iso: str | None,
    now: _dt.datetime,
    threshold_min: int,
) -> tuple[int, str]:
    """Pure classification of last_activity_at against threshold.

    Returns (exit_code, human_message).
      - 0 when the timestamp is within the threshold.
      - 2 when stale.
      - 3 when unparseable / missing.

    Injection seam for tests — no network or subprocess.
    """
    if not last_activity_iso:
        return 3, "daemon returned null/empty last_activity_at"
    ts = _parse_iso(last_activity_iso)
    if ts is None:
        return 3, f"could not parse last_activity_at={last_activity_iso!r}"
    age = now - ts
    age_min = age.total_seconds() / 60.0
    if age_min <= threshold_min:
        return 0, (
            f"FRESH: last_activity_at={last_activity_iso} "
            f"age={age_min:.1f}min threshold={threshold_min}min"
        )
    return 2, (
        f"STALE: last_activity_at={last_activity_iso} "
        f"age={age_min:.1f}min > threshold={threshold_min}min"
    )


def fetch_inspect_result(
    url: str,
    timeout: float,
    *,
    post_fn=None,
) -> dict[str, Any]:
    """Full MCP handshake + universe inspect call.

    Returns the parsed inspect result as a dict (the top-level JSON
    emitted by ``_action_inspect_universe``). ``post_fn`` is an
    injection seam for tests.

    Raises LastActivityError on any failure — handshake failures get
    step_code=4, tool failures get step_code=3.
    """
    post = post_fn or _post

    # Step 1: initialize. Any failure => exit 4 (handshake).
    resp, sid = post(url, None, _INIT_PAYLOAD, timeout, step_code=4)
    if resp is None or "result" not in resp:
        raise LastActivityError(
            4, f"initialize returned no result: {resp!r}",
        )
    if "error" in resp:
        raise LastActivityError(
            4, f"initialize returned MCP error: {resp['error']!r}",
        )
    if not sid:
        raise LastActivityError(
            4, "initialize response missing mcp-session-id header",
        )

    # Notifications/initialized. Protocol-required but response-less.
    post(url, sid, _INITIALIZED_NOTIF, timeout, step_code=4)

    # Step 2: tools/call universe action=inspect. Failure => exit 3
    # (daemon responded but shape's off).
    call_payload = {
        "jsonrpc": "2.0", "id": 2,
        "method": "tools/call",
        "params": {"name": "universe", "arguments": {"action": "inspect"}},
    }
    resp, _ = post(url, sid, call_payload, timeout, step_code=3)
    if resp is None or "result" not in resp:
        raise LastActivityError(
            3, f"universe inspect returned no result: {resp!r}",
        )
    result = resp["result"]
    if result.get("isError"):
        text = _extract_tool_text(result)[:300]
        raise LastActivityError(
            3, f"universe inspect isError=true: {text!r}",
        )
    structured = _extract_structured_tool_payload(result)
    if structured is not None:
        return structured
    text = _extract_tool_text(result)
    if not text:
        raise LastActivityError(
            3, f"universe inspect returned no text content: {result!r}",
        )
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LastActivityError(
            3, f"universe inspect text not JSON: {exc}; preview={text[:200]!r}",
        ) from exc


def run_canary(
    url: str,
    timeout: float,
    threshold_min: int,
    *,
    post_fn=None,
    now: _dt.datetime | None = None,
    verbose: bool = False,
) -> tuple[int, str]:
    """Full canary flow. Returns (exit_code, human_message).

    ``now`` and ``post_fn`` are test seams — default to real time + real
    HTTP when unset.

    Paused-daemon exemption: when ``daemon.is_paused`` is True or
    ``daemon.staleness`` is ``'idle'``, the freshness check is skipped
    and FRESH is returned with a ``(paused)`` annotation. A daemon that
    is intentionally paused via the host's ``.pause`` signal is not
    stale — the MCP surface is live, node execution is intentionally
    suspended (host directive 2026-04-24). Only resume the freshness
    gate when the daemon is unpaused.
    """
    current_now = now or _dt.datetime.now(tz=_dt.timezone.utc)
    inspect = fetch_inspect_result(url, timeout, post_fn=post_fn)

    daemon = inspect.get("daemon")
    if not isinstance(daemon, dict):
        return 3, (
            "inspect result has no daemon block; "
            f"top-level keys: {sorted(inspect.keys())}"
        )

    staleness = daemon.get("staleness", "")
    is_paused = bool(daemon.get("is_paused", False))

    if verbose:
        print(f"[last-activity] universe_id={inspect.get('universe_id')} "
              f"phase={daemon.get('phase')} staleness={staleness} "
              f"is_paused={is_paused}")

    if is_paused or staleness == "idle":
        reason = "paused" if is_paused else "idle"
        return 0, (
            f"FRESH (paused/{reason}): daemon is intentionally "
            f"{'paused via .pause signal' if is_paused else 'idle — no active work queued'}; "
            f"last_activity_at={daemon.get('last_activity_at')!r} "
            f"(freshness gate suspended while {reason})"
        )

    # Worker-liveness preference (daemon-liveness-watchdog spec): the
    # supervisor heartbeat distinguishes the two states content-activity
    # mtimes conflate. A dead/stale beat is a wedge — page with that as
    # the reason instead of the vaguer "activity stale". A live beat
    # with no queued work is healthy idleness — don't page just because
    # nothing has needed doing lately. A live beat with work present
    # falls through to the freshness gate (the daemon should be making
    # progress, and last_activity measures exactly that).
    liveness = daemon.get("worker_liveness")
    if isinstance(liveness, dict) and liveness.get("present"):
        alive = liveness.get("alive")
        if alive is False:
            return 2, (
                "STALE (worker_wedged): supervisor heartbeat is "
                f"{liveness.get('beat_age_s')}s old "
                f"(phase={liveness.get('phase')!r}, "
                f"consec_crashes={liveness.get('consec_crashes')}); "
                "worker is wedged or dead — restart the worker container"
            )
        if alive is True and not daemon.get("has_work", False):
            return 0, (
                "FRESH (worker alive, no active work): supervisor beat "
                f"{liveness.get('beat_age_s')}s old; "
                f"last_activity_at={daemon.get('last_activity_at')!r} "
                "staleness reflects idleness, not a wedge"
            )

    last_activity_iso = daemon.get("last_activity_at")
    return classify_freshness(last_activity_iso, current_now, threshold_min)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Probe daemon.last_activity_at for 24/7 node-execution liveness.",
    )
    ap.add_argument("--url", default=DEFAULT_URL,
                    help=f"MCP endpoint URL (default: {DEFAULT_URL})")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                    help=f"Per-request timeout seconds (default: {DEFAULT_TIMEOUT})")
    default_threshold = int(os.environ.get(
        "WORKFLOW_LAST_ACTIVITY_THRESHOLD_MIN", DEFAULT_THRESHOLD_MIN,
    ))
    ap.add_argument("--threshold-min", type=int, default=default_threshold,
                    help=f"Stale threshold in minutes (default: {default_threshold}; "
                         f"env: WORKFLOW_LAST_ACTIVITY_THRESHOLD_MIN)")
    ap.add_argument("--verbose", action="store_true",
                    help="Print one-line summary + diagnostic fields.")
    args = ap.parse_args(argv)

    try:
        code, msg = run_canary(
            args.url, args.timeout, args.threshold_min,
            verbose=args.verbose,
        )
    except LastActivityError as exc:
        print(f"[last-activity] FAIL (exit {exc.code}): {exc.msg}",
              file=sys.stderr)
        return exc.code

    # 0/2/3 outcomes all print the human message; exit code carries the
    # RED/GREEN decision up to the workflow.
    if code == 0:
        print(f"[last-activity] {msg}")
    else:
        print(f"[last-activity] FAIL (exit {code}): {msg}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
