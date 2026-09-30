"""Prove the Cloudflare Worker's public routes are bound — the edge's own contract.

`deploy-worker.yml` publishes the Worker script and its routes. That is the only
thing it controls, so it is the only thing it can honestly gate on.

Why this exists instead of an end-to-end probe there: the app-surface probe
(`scripts/probe_app_surface.py`) asserts that `https://tinyassets.io/app` SERVES
THE APP, which needs the edge route AND a daemon that mounts `/app`. Those ship
from two different workflows. On 2026-09-30, when both changed together,
`deploy-worker` published the route correctly and then went red because
`build-image` -> `deploy-prod` had not finished, so the old daemon was still
answering. A gate that fails during a correct rollout teaches people to ignore it.

So the split is by ownership:

  * here, in `deploy-worker`: the ROUTE BINDING, read from the Cloudflare API.
    Daemon-independent, and it is exactly what regresses if someone narrows
    `tinyassets.io/app*` to an exact path or deletes it.
  * `probe_app_surface.py` in `deploy-prod`: the end-to-end surface, run after
    the daemon is current, with rollback authority.

The adjudication itself is NOT reimplemented here. It reuses
`cloud_only_preflight.audit_public_worker_route`, which already knows the route
pattern grammar, most-specific-wins, scriptless-route suppression, and the
per-region shell+subtree coverage rule — and which refuses to guess rather than
guessing wrong.

    python scripts/verify_worker_routes.py --worker-name tinyassets-mcp-proxy

Needs `CLOUDFLARE_API_TOKEN` with `Zone:Workers Routes:Read` (the deploy token
already has Edit, which includes read) and `Zone:Zone:Read` to resolve the zone
id from the name. Exit 0 only on a `pass`; `unknown` is exit 2, because "the
checker cannot decide" is not evidence that the routes are right.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.cloud_only_preflight import (  # noqa: E402
    CF_API,
    PASS,
    UNKNOWN,
    audit_public_worker_route,
)

DEFAULT_ZONE = "tinyassets.io"
DEFAULT_WORKER = "tinyassets-mcp-proxy"


def resolve_zone_id(token: str, zone_name: str, timeout: float = 15) -> str | None:
    """Look the zone id up by name, so no id has to be stored in the workflow."""
    request = urllib.request.Request(
        f"{CF_API}/zones?name={urllib.request.quote(zone_name)}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if payload.get("success") is not True:
        return None
    result = payload.get("result") or []
    if not isinstance(result, list) or not result:
        return None
    zone_id = (result[0] or {}).get("id")
    return zone_id if isinstance(zone_id, str) and zone_id else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zone-name", default=DEFAULT_ZONE)
    parser.add_argument("--worker-name", default=DEFAULT_WORKER)
    parser.add_argument(
        "--zone-id",
        default=os.environ.get("CLOUDFLARE_ZONE_ID", "").strip() or None,
        help="Skip the name lookup when the id is already known.",
    )
    args = parser.parse_args(argv)

    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not token:
        print("CLOUDFLARE_API_TOKEN is required to read the zone's Worker routes")
        return 2

    zone_id = args.zone_id or resolve_zone_id(token, args.zone_name)
    if not zone_id:
        print(f"could not resolve a zone id for {args.zone_name}")
        return 2

    fact = audit_public_worker_route(token, zone_id, args.zone_name, args.worker_name)
    verdict = fact.get("verdict")
    # The fact carries no secret: verdict, reason, counts and path names only.
    print(json.dumps(fact, indent=2, sort_keys=True))

    if verdict == PASS:
        print(
            f"worker routes green: every canonical public path on {args.zone_name} "
            f"is bound to {args.worker_name}"
        )
        return 0
    if verdict == UNKNOWN:
        print(
            "UNDECIDED — this is not a pass. The route list could not be "
            "adjudicated; read it by hand before trusting the deploy."
        )
        return 2
    print(
        "FAILED — a canonical public path is not served by the expected Worker. "
        "The app or the connector is dark at the edge."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
