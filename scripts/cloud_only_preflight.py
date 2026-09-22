#!/usr/bin/env python3
"""Bounded, read-only cloud-only deployment preflight.

Resolves the three deployment facts `openspec/changes/cloud-only-runtime-admission`
depends on and has never observed:

  A. Is the droplet metadata service reachable from *inside* the deployed daemon
     container? (decides whether the provenance resolver's primary evidence works)
  B. What droplet id should the resolver expect? (reported as a salted digest)
  C. Does any connector outside the droplet serve the public tunnel, and does the
     public hostname terminate at the tunnel? (counts and classes only)

Hard bounds — these are the design contract, not implementation detail:

  * READ-ONLY. Every provider call is a GET. No POST/PUT/PATCH/DELETE, no SSH
    mutation, no infrastructure change of any kind, ever.
  * NOT a remote command runner. The in-container metadata probe is one fixed
    argv built from a module-level literal; no caller string is interpolated into
    a shell, and no caller-supplied Python is executed.
  * SANITIZED OUTPUT. Emits typed verdicts and counts. Never raw API bodies,
    credentials, IP addresses, hostnames, connector ids, or user data. The
    droplet id appears only as a salted truncated digest.
  * MISSING PERMISSION IS `unknown`. An absent secret, an out-of-scope token or
    a non-2xx response is a typed unknown with a reason code -- never a pass.
  * HOSTED CI ONLY. Requires CI=true. Do not run this on a personal machine
    with production credentials.

Exit codes: 0 all facts resolved and clean; 1 a fact resolved to a refusal
(off-droplet connector, DNS not at the tunnel); 2 one or more facts unknown, or
not running on hosted CI.

This is OBSERVATION. It does not enforce anything and does not close the
cloud-only boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

# --- fixed literals -------------------------------------------------------
# The in-container probe argv is built from these. Nothing here is caller-supplied.
METADATA_URL = "http://169.254.169.254/metadata/v1/id"
_PROBE_SOURCE = (
    "import urllib.request,sys\n"
    "try:\n"
    "    v=urllib.request.urlopen(%r,timeout=2).read().decode().strip()\n"
    "except Exception as e:\n"
    "    print('UNREACHABLE:'+type(e).__name__); sys.exit(0)\n"
    "print('OK:'+v)\n" % (METADATA_URL,)
)
DO_DROPLETS_URL = "https://api.digitalocean.com/v2/droplets?per_page=200"
CF_API = "https://api.cloudflare.com/client/v4"

PASS = "pass"
REFUSE = "refuse"
UNKNOWN = "unknown"

_DIGEST_SALT = "tinyassets-cloud-only-preflight-v1"


def digest(value: str) -> str:
    """Stable, non-reversible short tag for an id. Never the id itself."""
    return hashlib.sha256((_DIGEST_SALT + value).encode()).hexdigest()[:12]


def fact(name: str, verdict: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {"fact": name, "verdict": verdict, "reason": reason, **extra}


def _get_json(url: str, headers: dict[str, str], timeout: float = 15.0) -> tuple[dict | None, str]:
    """Read-only GET. Returns (payload, reason_code); payload is None on failure.

    No response body ever reaches the caller's output -- only parsed fields the
    caller explicitly selects.
    """
    req = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None, f"http_{resp.status}"
            return json.loads(resp.read().decode("utf-8")), "ok"
    except urllib.error.HTTPError as exc:
        # 401/403 = missing or out-of-scope permission -> unknown, never pass.
        return None, f"http_{exc.code}"
    except urllib.error.URLError:
        return None, "unreachable"
    except (ValueError, TimeoutError):
        return None, "bad_response"


# --- fact A: container metadata reachability ------------------------------

def probe_container_metadata(
    service: str,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """Fixed read-only command inside the deployed container. No shell, no exec of input."""
    argv = ["docker", "exec", service, "python", "-c", _PROBE_SOURCE]
    try:
        completed = runner(argv, capture_output=True, text=True, timeout=30, check=False)
    except FileNotFoundError:
        return fact("container_metadata", UNKNOWN, "docker_unavailable")
    except subprocess.TimeoutExpired:
        return fact("container_metadata", UNKNOWN, "probe_timeout")
    if completed.returncode != 0:
        return fact("container_metadata", UNKNOWN, "probe_failed")
    out = (completed.stdout or "").strip()
    if out.startswith("OK:"):
        observed = out[3:].strip()
        if not observed:
            return fact("container_metadata", UNKNOWN, "empty_id")
        return fact(
            "container_metadata", PASS, "reachable", instance_digest=digest(observed)
        )
    if out.startswith("UNREACHABLE:"):
        return fact("container_metadata", REFUSE, "metadata_unreachable_in_container")
    return fact("container_metadata", UNKNOWN, "unparsed_probe_output")


# --- fact B: expected droplet identity ------------------------------------

def resolve_expected_droplet(token: str | None, host_hint: str | None) -> dict[str, Any]:
    if not token:
        return fact("expected_droplet", UNKNOWN, "missing_DO_API_TOKEN")
    payload, reason = _get_json(DO_DROPLETS_URL, {"Authorization": f"Bearer {token}"})
    if payload is None:
        return fact("expected_droplet", UNKNOWN, f"do_api_{reason}")
    droplets = payload.get("droplets") or []
    if not droplets:
        return fact("expected_droplet", UNKNOWN, "no_droplets_visible")
    addresses: set[str] = set()
    matched_id: str | None = None
    for droplet in droplets:
        ips = {
            entry.get("ip_address")
            for family in ("v4", "v6")
            for entry in (droplet.get("networks") or {}).get(family, [])
            if entry.get("ip_address")
        }
        if host_hint and host_hint in ips:
            matched_id = str(droplet.get("id"))
            addresses = ips
    if matched_id is None:
        if len(droplets) == 1:
            matched_id = str(droplets[0].get("id"))
            addresses = {
                entry.get("ip_address")
                for family in ("v4", "v6")
                for entry in (droplets[0].get("networks") or {}).get(family, [])
                if entry.get("ip_address")
            }
        else:
            return fact("expected_droplet", UNKNOWN, "host_hint_matched_no_droplet")
    return fact(
        "expected_droplet",
        PASS,
        "resolved",
        instance_digest=digest(matched_id),
        _addresses=sorted(a for a in addresses if a),  # internal; stripped before output
    )


# --- fact C: who serves the public tunnel ---------------------------------

def audit_tunnel_connectors(
    token: str | None,
    account_id: str | None,
    tunnel_id: str | None,
    droplet_addresses: set[str],
) -> dict[str, Any]:
    if not token:
        return fact("tunnel_connectors", UNKNOWN, "missing_CLOUDFLARE_API_TOKEN")
    if not account_id or not tunnel_id:
        return fact("tunnel_connectors", UNKNOWN, "missing_account_or_tunnel_id")
    if not droplet_addresses:
        return fact("tunnel_connectors", UNKNOWN, "no_droplet_address_set")
    url = f"{CF_API}/accounts/{account_id}/cfd_tunnel/{tunnel_id}/connections"
    payload, reason = _get_json(url, {"Authorization": f"Bearer {token}"})
    if payload is None:
        return fact("tunnel_connectors", UNKNOWN, f"cf_api_{reason}")
    if not payload.get("success", False):
        return fact("tunnel_connectors", UNKNOWN, "cf_api_unsuccessful")
    result = payload.get("result")
    if result is None:
        return fact("tunnel_connectors", UNKNOWN, "cf_api_no_result")
    in_set = out_of_set = 0
    for conn in result:
        origin = conn.get("origin_ip")
        if origin is None:
            return fact("tunnel_connectors", UNKNOWN, "connector_without_origin")
        if origin in droplet_addresses:
            in_set += 1
        else:
            out_of_set += 1
    verdict = REFUSE if out_of_set else PASS
    return fact(
        "tunnel_connectors",
        verdict,
        "off_droplet_connector_present" if out_of_set else "all_connectors_on_droplet",
        connectors_in_set=in_set,
        connectors_out_of_set=out_of_set,
    )


def audit_public_dns(token: str | None, zone_id: str | None, name: str) -> dict[str, Any]:
    if not token:
        return fact("public_dns", UNKNOWN, "missing_CLOUDFLARE_API_TOKEN")
    if not zone_id:
        return fact("public_dns", UNKNOWN, "missing_CLOUDFLARE_ZONE_ID")
    url = f"{CF_API}/zones/{zone_id}/dns_records?name={name}"
    payload, reason = _get_json(url, {"Authorization": f"Bearer {token}"})
    if payload is None:
        return fact("public_dns", UNKNOWN, f"cf_api_{reason}")
    records = payload.get("result")
    if not records:
        return fact("public_dns", UNKNOWN, "no_records")
    # Report a class, never the target value.
    tunnel_backed = sum(
        1
        for r in records
        if r.get("type") == "CNAME" and str(r.get("content", "")).endswith(".cfargotunnel.com")
    )
    proxied = sum(1 for r in records if r.get("proxied"))
    if tunnel_backed:
        return fact("public_dns", PASS, "terminates_at_tunnel", records=len(records))
    if proxied:
        return fact("public_dns", UNKNOWN, "proxied_but_not_tunnel_cname", records=len(records))
    return fact("public_dns", REFUSE, "unproxied_direct_target", records=len(records))


# --- entry point ----------------------------------------------------------

def sanitize(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip every internal key (leading underscore) before anything is printed."""
    return [{k: v for k, v in f.items() if not k.startswith("_")} for f in facts]


def run(argv: list[str] | None = None, env: dict[str, str] | None = None) -> int:
    env = dict(os.environ if env is None else env)
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--container-service", default="tinyassets-daemon")
    parser.add_argument("--public-name", default="tinyassets.io")
    parser.add_argument("--skip-container-probe", action="store_true")
    args = parser.parse_args(argv)

    if env.get("CI", "").lower() not in {"true", "1"}:
        print(
            json.dumps(
                {"status": UNKNOWN, "reason": "not_hosted_ci", "facts": [],
                 "enforcement": "none", "boundary_closed": False},
                indent=2,
            )
        )
        return 2

    facts: list[dict[str, Any]] = []
    if not args.skip_container_probe:
        facts.append(probe_container_metadata(args.container_service))

    droplet = resolve_expected_droplet(
        env.get("DO_API_TOKEN"), env.get("DO_DROPLET_HOST")
    )
    facts.append(droplet)
    addresses = set(droplet.get("_addresses") or [])

    facts.append(
        audit_tunnel_connectors(
            env.get("CLOUDFLARE_API_TOKEN"),
            env.get("CLOUDFLARE_ACCOUNT_ID"),
            env.get("CLOUDFLARE_TUNNEL_ID"),
            addresses,
        )
    )
    facts.append(
        audit_public_dns(
            env.get("CLOUDFLARE_API_TOKEN"),
            env.get("CLOUDFLARE_ZONE_ID"),
            args.public_name,
        )
    )

    clean = sanitize(facts)
    verdicts = {f["verdict"] for f in clean}
    if REFUSE in verdicts:
        status, code = REFUSE, 1
    elif UNKNOWN in verdicts:
        status, code = UNKNOWN, 2
    else:
        status, code = PASS, 0

    print(
        json.dumps(
            {
                "status": status,
                "facts": clean,
                "enforcement": "none",
                "boundary_closed": False,
                "note": "Observation only. This does not enforce cloud-only admission.",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run())
