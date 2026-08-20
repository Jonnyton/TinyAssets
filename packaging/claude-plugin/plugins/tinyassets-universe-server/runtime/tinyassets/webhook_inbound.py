"""Universal inbound webhook receiver (channel-agnostic inbound, Floor 1).

A single public endpoint — ``POST /hooks/<token>`` — lets ANY channel that can fire an
HTTP webhook trigger a branch, with zero platform code per channel. The token is the
only authority: it was minted by a universe's founder for one of that universe's own
branches, so an inbound POST can only ever run THAT branch as THAT universe, using that
universe's own credentials. Nothing in the request selects identity.

Security posture:
- Unknown / revoked / malformed token -> 404, identical body (no enumeration signal).
- The run's actor is ``universe:<uid>`` from the token binding; no header/body redirects it.
- Body size-capped; per-token rate-limited; body + a filtered header subset are passed as
  run input verbatim (user data authoritative) but never interpreted as identity.
- Dark until the tunnel exposes ``/hooks/*`` (today ``/mcp`` only) — landing the code is safe.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)

#: Refuse anything larger unread — a webhook payload is a small JSON body, not a megabyte.
MAX_BODY_BYTES = 256 * 1024

#: Per-token rate limit: a channel that fires a webhook storm cannot enqueue unbounded runs.
_RATE_MAX = 60
_RATE_WINDOW_S = 60.0

#: Request headers never forwarded to the branch (generic transport auth / cookies). Channel
#: verification headers (e.g. X-Hub-Signature, X-GitHub-Event) ARE forwarded so a branch can
#: verify the sender itself — they are the channel's, not the universe's secrets.
_HEADER_DENYLIST = frozenset({"authorization", "cookie", "proxy-authorization", "set-cookie"})

_rate_lock = threading.Lock()
_rate_hits: dict[str, deque] = defaultdict(deque)


def _admit(token: str, *, now: float | None = None) -> bool:
    ts = time.time() if now is None else now
    with _rate_lock:
        hits = _rate_hits[token]
        while hits and hits[0] <= ts - _RATE_WINDOW_S:
            hits.popleft()
        if len(hits) >= _RATE_MAX:
            return False
        hits.append(ts)
        return True


def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in headers.items():
        if str(k).lower() in _HEADER_DENYLIST:
            continue
        out[str(k)] = str(v)
    return out


def _decode_body(body: bytes) -> Any:
    """The payload as parsed JSON when it is JSON, else the raw text (bounded)."""
    text = body.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001 - a non-JSON webhook body is fine; pass the text
        return text


def handle_hook(
    *,
    token: str,
    body: bytes,
    headers: Mapping[str, str],
    base_path: str | Path | None = None,
    enqueue: Callable[..., str] | None = None,
    now: float | None = None,
) -> tuple[int, dict[str, Any]]:
    """Authenticate a webhook by its token and enqueue the bound branch. Returns
    ``(status, payload)``. Transport-agnostic so the security decisions are testable
    without a server."""
    if len(body) > MAX_BODY_BYTES:
        return 413, {"error": "too_large"}

    from tinyassets.storage import webhook_hooks

    base = Path(base_path) if base_path is not None else _default_base()
    binding = webhook_hooks.resolve(base, token=token)
    if binding is None:
        # Unknown / revoked / malformed all answer identically — no enumeration.
        return 404, {"error": "not_found"}

    if not _admit(token, now=now):
        return 429, {"error": "rate_limited"}

    universe_id = str(binding["universe_id"])
    branch_def_id = str(binding["branch_def_id"])
    # Preserve the EXACT signed bytes (base64) alongside a parsed convenience value, so a
    # branch can verify a channel signature (GitHub X-Hub-Signature, Stripe, …) over the
    # original body — the forwarded verification headers are useless without them (Codex #4).
    inputs = {"webhook": {
        "payload": _decode_body(body),
        "raw_base64": base64.b64encode(body).decode("ascii"),
        "headers": _safe_headers(headers),
    }}

    try:
        run_id = (enqueue or _enqueue_branch_run)(
            base, universe_id=universe_id, branch_def_id=branch_def_id, inputs=inputs,
        )
    except Exception:  # noqa: BLE001 - never leak internal detail to a public caller
        logger.exception("webhook: enqueue failed for branch %s", branch_def_id)
        return 500, {"error": "enqueue_failed"}
    return 202, {"queued": True, "run_id": run_id}


def _default_base() -> Path:
    from tinyassets.storage import data_dir

    return Path(data_dir())


def _enqueue_branch_run(
    base_path: str | Path, *, universe_id: str, branch_def_id: str, inputs: dict[str, Any],
) -> str:
    """Enqueue a run of ``branch_def_id`` as ``universe:<universe_id>``.

    The token already proved this branch belongs to this universe (verified at mint time),
    so the run is enqueued directly as the universe — exactly the same background run path
    the MCP ``run_graph`` uses, with the same provider binding — never as a host identity.
    """
    from tinyassets.api.branches import _resolve_branch_id
    from tinyassets.api.permissions import branch_run_actor
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import get_branch_definition
    from tinyassets.runs import execute_branch_async

    bid = _resolve_branch_id(branch_def_id, str(base_path))
    branch = BranchDefinition.from_dict(get_branch_definition(base_path, branch_def_id=bid))
    errors = branch.validate()
    if errors:
        raise ValueError(f"branch {bid} failed validation: {errors}")

    provider_call: Any = None
    try:
        from tinyassets.api.runs import _bind_run_provider_call
        from tinyassets.providers.call import call_provider

        provider_call = _bind_run_provider_call(call_provider, universe_id)
    except ImportError:
        provider_call = None

    outcome = execute_branch_async(
        base_path,
        branch=branch,
        inputs=inputs,
        run_name="webhook",
        actor=branch_run_actor(universe_id),
        provider_call=provider_call,
        _enqueue_universe_id=universe_id,
    )
    return outcome.run_id
