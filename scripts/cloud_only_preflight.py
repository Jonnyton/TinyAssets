#!/usr/bin/env python3
"""Bounded, read-only cloud-only deployment preflight.

Reports what can be *observed* about the facts
`openspec/changes/cloud-only-runtime-admission` depends on. Anything it cannot
observe is a typed `unknown` carrying the precise missing requirement. It never
composes an absence of evidence into a pass.

Facts, and what each one actually proves:

  A. `container_metadata` -- does the droplet metadata service answer from
     inside the *deployed* container? Only a probe that reaches the droplet over
     the existing SSH delivery path can answer this. A local `docker` daemon on
     whatever machine runs this script is NOT production and is never consulted.
  B. `expected_droplet` -- which droplet the DO inventory says is the deploy
     target, by exact match against `DO_DROPLET_HOST`. There is no
     single-droplet fallback: an unmatched host is `unknown`, never a pass.
  C. `cloud_identity_match` -- does A's observed identity equal B's expected
     identity? Reported as a boolean. Unknown on either side stays unknown.
  D. `tunnel_connectors` -- does any connector outside the droplet address set
     serve the selected tunnel? Counts only.
  E. `internal_origin_dns` -- does the internal origin hostname terminate at the
     *selected* tunnel (`<CLOUDFLARE_TUNNEL_ID>.cfargotunnel.com`), not merely
     at some tunnel.
  F. `public_worker_route` -- is the public hostname bound to the expected
     Worker route?
  G. `hosted_credential_custody` -- where this ran and who holds the secrets.
     Permanently `unknown` here; see below.

Hard bounds -- these are the design contract, not implementation detail:

  * READ-ONLY. Every provider call is a GET. No POST/PUT/PATCH/DELETE, no SSH
    mutation, no infrastructure change of any kind, ever.
  * NOT a remote command runner. The probe argv is assembled from module-level
    literals plus strictly-validated host/user/service identifiers. No caller
    string is interpolated into a shell and no caller-supplied Python is run.
  * NO REDIRECTS, NO PROXY INHERITANCE, BOUNDED READS. Authenticated requests
    refuse to follow redirects (a redirect would replay the Authorization
    header at an unvetted host) and ignore ambient proxy environment variables.
    Response bodies are read to a fixed byte ceiling; a longer body is
    `unknown`, not a truncated parse.
  * PAGINATION COMPLETENESS IS REQUIRED. A page that does not account for the
    provider's declared total is `unknown`. A partial inventory cannot clear an
    exhaustive check.
  * SANITIZED OUTPUT. Emits typed verdicts, booleans and counts. Identifiers,
    addresses, hostnames and credentials stay on internal (underscore-prefixed)
    keys that `sanitize()` strips before anything is printed.
  * MISSING PERMISSION IS `unknown`. An absent secret, an out-of-scope token, a
    non-2xx response or a malformed body is a typed unknown with a reason code
    and a `requirement` string -- never a pass.

Two honesty constraints that bound what this script may ever claim:

  * `CI=true` is an **accidental-use guard only**. It stops someone running this
    on a personal machine holding production credentials. It proves nothing
    about where the process actually ran or who holds the secrets -- the
    environment variable is trivially settable anywhere. Hosted workflow
    placement and credential custody are the real boundary and they remain
    **unverified** until the workflow is wired and deployed, so
    `hosted_credential_custody` is hard-coded `unknown`.
  * Identifiers are not anonymized. A fixed, public salt over a small numeric
    droplet id is enumerable in trivial time, so the digest is NOT a privacy
    control and no such claim is made. Identifiers are simply kept internal and
    compared internally; only booleans and counts are emitted.

Consequently this script cannot report an overall `pass` in its current state:
`hosted_credential_custody` is always unknown. That is the accurate result, not
a defect.

Exit codes: 0 all facts resolved and clean (unreachable today, by design);
1 a fact resolved to a refusal; 2 one or more facts unknown, or the
accidental-use guard tripped.

This is OBSERVATION. It does not enforce anything and does not close the
cloud-only boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

# --- fixed literals -------------------------------------------------------
# The probe argv is built from these. Nothing here is caller-supplied.
METADATA_URL = "http://169.254.169.254/metadata/v1/id"
_PROBE_SOURCE = (
    "import urllib.request,sys\n"
    # No proxy inheritance and no redirects: the metadata service is link-local
    # and must be read directly or not at all.
    "o=urllib.request.build_opener(urllib.request.ProxyHandler({}))\n"
    "try:\n"
    "    v=o.open(%r,timeout=2).read(256).decode('utf-8','replace').strip()\n"
    "except Exception as e:\n"
    "    print('UNREACHABLE:'+type(e).__name__); sys.exit(0)\n"
    "print('OK:'+v)\n" % (METADATA_URL,)
)
DO_DROPLETS_URL = "https://api.digitalocean.com/v2/droplets?per_page=200"
CF_API = "https://api.cloudflare.com/client/v4"

PASS = "pass"
REFUSE = "refuse"
UNKNOWN = "unknown"

# Bodies larger than this are unknown, never a truncated parse.
MAX_RESPONSE_BYTES = 2_000_000

# Correlation tag only. NOT anonymization -- see module docstring. Stays on
# internal keys and is never emitted.
_DIGEST_SALT = "tinyassets-cloud-only-preflight-v1"

_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,252}$")
_USER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_SERVICE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_INSTANCE_ID_RE = re.compile(r"^[0-9]{1,24}$")
_PROBE_REPORT_RE = re.compile(r"^(?:OK:[0-9]{1,24}|UNREACHABLE:[A-Za-z]{1,64})$")


def correlation_tag(value: str) -> str:
    """Short stable tag for comparing two ids *internally*.

    This is NOT a privacy control: the salt is a public constant in this file
    and droplet ids are small integers, so the mapping is enumerable. Callers
    must keep the result on an internal key and emit only booleans.
    """
    return hashlib.sha256((_DIGEST_SALT + value).encode()).hexdigest()[:12]


def fact(name: str, verdict: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {"fact": name, "verdict": verdict, "reason": reason, **extra}


def unknown(name: str, reason: str, requirement: str, **extra: Any) -> dict[str, Any]:
    """A typed unknown always states the precise thing that would resolve it."""
    return fact(name, UNKNOWN, reason, requirement=requirement, **extra)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect: following one replays Authorization at a new host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


# No ProxyHandler default => ambient http_proxy/https_proxy are ignored, so an
# authenticated request cannot be routed through an inherited intermediary.
_OPENER = urllib.request.build_opener(_NoRedirect, urllib.request.ProxyHandler({}))


def _get_json(url: str, headers: dict[str, str], timeout: float = 15.0) -> tuple[dict | None, str]:
    """Read-only, non-redirecting, proxy-free, byte-bounded GET.

    Returns (payload, reason_code); payload is None on any failure. No response
    body ever reaches the caller's output -- only fields the caller selects.
    """
    req = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None, f"http_{resp.status}"
            body = resp.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        # 401/403 = missing or out-of-scope permission -> unknown, never pass.
        # 3xx arrives here because redirects are refused above.
        if 300 <= exc.code < 400:
            return None, "redirect_refused"
        return None, f"http_{exc.code}"
    except urllib.error.URLError:
        return None, "unreachable"
    except (ValueError, TimeoutError):
        return None, "bad_response"
    if len(body) > MAX_RESPONSE_BYTES:
        return None, "response_too_large"
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None, "bad_response"
    if not isinstance(payload, dict):
        return None, "unexpected_payload_shape"
    return payload, "ok"


def _pagination_incomplete(total: Any, seen: int) -> bool:
    """True when the provider declares more records than this page returned.

    A non-integer or absent total is also incomplete: we cannot prove we saw
    everything, and an exhaustive check on a partial inventory is worthless.
    """
    if not isinstance(total, int) or isinstance(total, bool):
        return True
    return total != seen


# --- fact A: container metadata reachability (remote only) ----------------


class RemoteProbeTarget:
    """Validated coordinates for the existing SSH delivery path.

    Every field is validated against a strict character class before it can
    reach an argv, and the key path must already exist -- this script never
    creates, writes or prints a credential.
    """

    def __init__(self, host: str, user: str, key_path: str, known_hosts: str) -> None:
        self.host = host
        self.user = user
        self.key_path = key_path
        self.known_hosts = known_hosts


def resolve_remote_probe_target(
    env: dict[str, str], exists: Any = os.path.exists
) -> tuple[RemoteProbeTarget | None, str, str]:
    """Resolve the SSH probe path from *existing* deploy secrets, or say why not.

    Returns (target, reason_code, requirement). Introduces no new credential:
    it reuses `DO_DROPLET_HOST` / `DO_SSH_USER` and an already-provisioned key
    and known_hosts file. If either file is absent the path is simply not wired
    yet and the caller must report `unknown`.
    """
    host = (env.get("DO_DROPLET_HOST") or "").strip()
    user = (env.get("DO_SSH_USER") or "").strip()
    key_path = (env.get("DO_SSH_KEY_PATH") or "").strip()
    known_hosts = (env.get("DO_SSH_KNOWN_HOSTS") or "").strip()
    if not host or not user:
        return None, "missing_DO_DROPLET_HOST_or_DO_SSH_USER", (
            "set DO_DROPLET_HOST and DO_SSH_USER from the existing deploy secrets"
        )
    if not _HOST_RE.match(host) or not _USER_RE.match(user):
        return None, "malformed_ssh_target", (
            "DO_DROPLET_HOST and DO_SSH_USER must match the strict identifier "
            "character class; no shell metacharacters"
        )
    if not key_path or not exists(key_path):
        return None, "ssh_key_not_provisioned", (
            "point DO_SSH_KEY_PATH at the private key the deploy workflow "
            "already installs (it writes ~/.ssh/do_deploy from the DO_SSH_KEY "
            "secret); this script never writes or prints a key"
        )
    if not known_hosts or not exists(known_hosts):
        return None, "known_hosts_not_provisioned", (
            "point DO_SSH_KNOWN_HOSTS at a pre-populated known_hosts file; the "
            "probe runs with StrictHostKeyChecking=yes and will not "
            "trust-on-first-use its way onto an unverified host"
        )
    return RemoteProbeTarget(host, user, key_path, known_hosts), "ok", ""


def build_remote_probe_argv(target: RemoteProbeTarget, service: str) -> list[str]:
    """One fixed read-only argv. Every dynamic token is validated and quoted."""
    if not _SERVICE_RE.match(service):
        raise ValueError("container service name failed strict validation")
    remote = " ".join(
        shlex.quote(token)
        for token in ("docker", "exec", service, "python", "-c", _PROBE_SOURCE)
    )
    return [
        "ssh",
        "-i",
        target.key_path,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={target.known_hosts}",
        "-o",
        "ConnectTimeout=10",
        f"{target.user}@{target.host}",
        remote,
    ]


def _classify_probe_output(out: str) -> dict[str, Any]:
    if out.startswith("OK:"):
        observed = out[3:].strip()
        if not observed:
            return unknown(
                "container_metadata", "empty_id",
                "the metadata endpoint answered with an empty body",
            )
        if not _INSTANCE_ID_RE.match(observed):
            return unknown(
                "container_metadata", "malformed_instance_id",
                "the metadata endpoint must return a bare numeric droplet id",
            )
        return fact(
            "container_metadata", PASS, "reachable",
            _instance_tag=correlation_tag(observed),
        )
    if out.startswith("UNREACHABLE:"):
        return fact("container_metadata", REFUSE, "metadata_unreachable_in_container")
    return unknown(
        "container_metadata", "unparsed_probe_output",
        "the probe must emit exactly 'OK:<id>' or 'UNREACHABLE:<ExcName>'",
    )


def probe_container_metadata(
    service: str,
    target: RemoteProbeTarget | None,
    unwired_reason: str = "remote_probe_path_not_wired",
    unwired_requirement: str = "",
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """Fixed read-only probe **on the deployed droplet**, or a typed unknown.

    There is deliberately no local-Docker path. A hosted runner's Docker daemon
    is not the deployed container, so probing it could never prove production
    reachability -- and reporting it as if it could is the exact false positive
    this function exists to refuse.
    """
    if target is None:
        return unknown(
            "container_metadata",
            unwired_reason,
            unwired_requirement
            or (
                "no read-only path to the deployed droplet is wired; the local "
                "Docker daemon is not production and is never substituted"
            ),
        )
    try:
        argv = build_remote_probe_argv(target, service)
    except ValueError:
        return unknown(
            "container_metadata", "malformed_container_service",
            "--container-service must match the strict identifier character class",
        )
    try:
        completed = runner(argv, capture_output=True, text=True, timeout=45, check=False)
    except FileNotFoundError:
        return unknown(
            "container_metadata", "ssh_client_unavailable",
            "an ssh client must be present on the machine running this script",
        )
    except subprocess.TimeoutExpired:
        return unknown(
            "container_metadata", "probe_timeout",
            "the droplet did not answer the bounded read within 45s",
        )
    if completed.returncode != 0:
        # stderr may carry a hostname or key path; the reason code carries none.
        return unknown(
            "container_metadata", "probe_failed",
            "the fixed remote probe exited non-zero; check SSH reachability and "
            "that the deploy key may run `docker exec` read-only",
        )
    return _classify_probe_output((completed.stdout or "").strip())


def read_probe_report(path: str, opener: Any = open) -> dict[str, Any]:
    """Accept a report produced by the fixed remote probe, strictly validated.

    The only accepted content is the probe's own one-line output grammar. Any
    other content is `unknown` -- a free-form file would be an invented
    attestation, which is exactly what this must not become.
    """
    try:
        with opener(path, encoding="utf-8") as handle:
            raw = handle.read(512).strip()
    except OSError:
        return unknown(
            "container_metadata", "probe_report_unreadable",
            "the report path must name a readable file written by the fixed probe",
        )
    if not _PROBE_REPORT_RE.match(raw):
        return unknown(
            "container_metadata", "probe_report_malformed",
            "the report must be exactly one line of the fixed probe's own "
            "grammar: 'OK:<numeric id>' or 'UNREACHABLE:<ExcName>'",
        )
    result = _classify_probe_output(raw)
    result["evidence_source"] = "reported"
    return result


# --- fact B: expected droplet identity ------------------------------------

def _droplet_addresses(droplet: dict[str, Any]) -> set[str] | None:
    networks = droplet.get("networks")
    if not isinstance(networks, dict):
        return None
    addresses: set[str] = set()
    for family in ("v4", "v6"):
        entries = networks.get(family, [])
        if entries is None:
            continue
        if not isinstance(entries, list):
            return None
        for entry in entries:
            if not isinstance(entry, dict):
                return None
            address = entry.get("ip_address")
            if address is None:
                continue
            if not isinstance(address, str) or not address:
                return None
            addresses.add(address)
    return addresses


def resolve_expected_droplet(token: str | None, host_hint: str | None) -> dict[str, Any]:
    """Exact inventory match on `DO_DROPLET_HOST`. No single-droplet fallback.

    "It is the only droplet I can see" is not evidence that it is *the* droplet:
    token scope decides what is visible, so a one-element inventory proves
    nothing about which machine serves production.
    """
    if not token:
        return unknown(
            "expected_droplet", "missing_DO_API_TOKEN",
            "a read-scoped DigitalOcean API token",
        )
    if not host_hint:
        return unknown(
            "expected_droplet", "missing_DO_DROPLET_HOST",
            "DO_DROPLET_HOST must name the deploy target; there is no "
            "single-droplet fallback",
        )
    try:
        ipaddress.ip_address(host_hint)
    except ValueError:
        return unknown(
            "expected_droplet", "do_droplet_host_not_an_ip_literal",
            "DO_DROPLET_HOST must be an IP literal to match DO inventory "
            "addresses exactly; resolving a DNS name here would substitute "
            "name resolution for inventory truth",
        )
    payload, reason = _get_json(DO_DROPLETS_URL, {"Authorization": f"Bearer {token}"})
    if payload is None:
        return unknown(
            "expected_droplet", f"do_api_{reason}",
            "a successful, complete, well-formed read of GET /v2/droplets",
        )
    droplets = payload.get("droplets")
    if not isinstance(droplets, list):
        return unknown(
            "expected_droplet", "malformed_droplet_list",
            "GET /v2/droplets must return a `droplets` array",
        )
    if not droplets:
        return unknown(
            "expected_droplet", "no_droplets_visible",
            "the token must be able to see the deploy target droplet",
        )
    meta = payload.get("meta")
    total = meta.get("total") if isinstance(meta, dict) else None
    if _pagination_incomplete(total, len(droplets)):
        return unknown(
            "expected_droplet", "do_api_incomplete_page",
            "every droplet must be read before an exact match can be asserted; "
            "`meta.total` must equal the number of records received",
        )

    matches: list[tuple[str, set[str]]] = []
    for droplet in droplets:
        if not isinstance(droplet, dict):
            return unknown(
                "expected_droplet", "malformed_droplet_record",
                "each droplet record must be an object",
            )
        addresses = _droplet_addresses(droplet)
        if addresses is None:
            return unknown(
                "expected_droplet", "malformed_droplet_record",
                "each droplet's `networks.v4`/`networks.v6` must be arrays of "
                "objects with string `ip_address` values",
            )
        droplet_id = droplet.get("id")
        if not isinstance(droplet_id, int) or isinstance(droplet_id, bool):
            return unknown(
                "expected_droplet", "malformed_droplet_record",
                "each droplet record must carry an integer `id`",
            )
        if host_hint in addresses:
            matches.append((str(droplet_id), addresses))

    if not matches:
        return unknown(
            "expected_droplet", "host_hint_matched_no_droplet",
            "DO_DROPLET_HOST must appear in exactly one visible droplet's "
            "address set; an unmatched host is never resolved to whatever "
            "droplet happens to be visible",
        )
    if len(matches) > 1:
        return unknown(
            "expected_droplet", "host_hint_matched_multiple_droplets",
            "DO_DROPLET_HOST must identify exactly one droplet",
            matched_droplets=len(matches),
        )
    matched_id, addresses = matches[0]
    return fact(
        "expected_droplet", PASS, "resolved",
        _instance_tag=correlation_tag(matched_id),
        _addresses=sorted(addresses),  # internal; stripped before output
    )


# --- fact C: observed identity vs expected identity -----------------------

def compare_cloud_identity(
    observed: dict[str, Any], expected: dict[str, Any]
) -> dict[str, Any]:
    """Compare the two identities as a boolean. Unknown on either side stays unknown."""
    observed_tag = observed.get("_instance_tag")
    expected_tag = expected.get("_instance_tag")
    if observed.get("verdict") == REFUSE:
        return unknown(
            "cloud_identity_match", "no_observed_identity",
            "the container metadata probe must resolve an identity before it "
            "can be compared with the expected droplet",
        )
    if not observed_tag:
        return unknown(
            "cloud_identity_match", "container_identity_unknown",
            "resolve `container_metadata` first",
        )
    if not expected_tag:
        return unknown(
            "cloud_identity_match", "expected_identity_unknown",
            "resolve `expected_droplet` first",
        )
    if observed_tag == expected_tag:
        return fact(
            "cloud_identity_match", PASS,
            "container_identity_matches_expected_droplet", identity_match=True,
        )
    return fact(
        "cloud_identity_match", REFUSE,
        "container_identity_differs_from_expected_droplet", identity_match=False,
    )


# --- fact D: who serves the selected tunnel -------------------------------

def audit_tunnel_connectors(
    token: str | None,
    account_id: str | None,
    tunnel_id: str | None,
    droplet_addresses: set[str],
) -> dict[str, Any]:
    """Count connectors in/out of the droplet address set.

    Response shape per the Cloudflare API reference for
    GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/connections: `result` is an
    array of *client* objects, each carrying a nested `conns` array, and
    `origin_ip` lives on each entry of `conns` -- not on the client object.
    Reading `origin_ip` off the client object finds nothing on real data.
    """
    if not token:
        return unknown(
            "tunnel_connectors", "missing_CLOUDFLARE_API_TOKEN",
            "a Cloudflare token with Tunnel read scope",
        )
    if not account_id or not tunnel_id:
        return unknown(
            "tunnel_connectors", "missing_account_or_tunnel_id",
            "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_TUNNEL_ID",
        )
    if not droplet_addresses:
        return unknown(
            "tunnel_connectors", "no_droplet_address_set",
            "`expected_droplet` must resolve first; without the droplet's "
            "addresses every connector is unclassifiable",
        )
    url = f"{CF_API}/accounts/{account_id}/cfd_tunnel/{tunnel_id}/connections"
    payload, reason = _get_json(url, {"Authorization": f"Bearer {token}"})
    if payload is None:
        return unknown(
            "tunnel_connectors", f"cf_api_{reason}",
            "a successful, complete, well-formed read of the tunnel connections",
        )
    if payload.get("success") is not True:
        return unknown(
            "tunnel_connectors", "cf_api_unsuccessful",
            "the Cloudflare envelope must report success: true",
        )
    clients = payload.get("result")
    if not isinstance(clients, list):
        return unknown(
            "tunnel_connectors", "cf_api_no_result",
            "the response `result` must be an array of client objects",
        )
    if not clients:
        # Absence of serving evidence is not evidence of correct serving.
        return unknown(
            "tunnel_connectors", "no_connectors_reported",
            "at least one connector must be reported before 'no off-droplet "
            "connector' can mean anything; an empty list is unobserved, not clean",
        )
    info = payload.get("result_info")
    total = info.get("total_count") if isinstance(info, dict) else None
    if _pagination_incomplete(total, len(clients)):
        return unknown(
            "tunnel_connectors", "cf_api_incomplete_page",
            "`result_info.total_count` must equal the number of clients "
            "received; an off-droplet connector could sit on an unread page",
        )

    in_set = out_of_set = 0
    for client in clients:
        if not isinstance(client, dict):
            return unknown(
                "tunnel_connectors", "malformed_connector_record",
                "each `result` entry must be an object",
            )
        conns = client.get("conns")
        if not isinstance(conns, list):
            return unknown(
                "tunnel_connectors", "connector_without_conns",
                "each client object must carry a `conns` array; `origin_ip` is "
                "nested there, never on the client object itself",
            )
        for conn in conns:
            if not isinstance(conn, dict):
                return unknown(
                    "tunnel_connectors", "malformed_connection_record",
                    "each `conns` entry must be an object",
                )
            origin = conn.get("origin_ip")
            if not isinstance(origin, str) or not origin:
                return unknown(
                    "tunnel_connectors", "connection_without_origin",
                    "each connection must report a string `origin_ip`; an "
                    "unclassifiable connector cannot be counted as on-droplet",
                )
            if origin in droplet_addresses:
                in_set += 1
            else:
                out_of_set += 1

    if in_set == 0 and out_of_set == 0:
        return unknown(
            "tunnel_connectors", "no_active_connections_reported",
            "at least one active connection must be reported; clients with "
            "empty `conns` arrays are not serving evidence",
        )
    verdict = REFUSE if out_of_set else PASS
    return fact(
        "tunnel_connectors", verdict,
        "off_droplet_connector_present" if out_of_set else "all_connectors_on_droplet",
        connectors_in_set=in_set,
        connectors_out_of_set=out_of_set,
    )


# --- facts E/F: DNS bound to the selected tunnel, and the Worker route ------

def _dns_records(
    token: str, zone_id: str, name: str, fact_name: str
) -> tuple[list[dict[str, Any]] | None, dict[str, Any]]:
    url = f"{CF_API}/zones/{zone_id}/dns_records?name={name}"
    payload, reason = _get_json(url, {"Authorization": f"Bearer {token}"})
    if payload is None:
        return None, unknown(
            fact_name, f"cf_api_{reason}",
            "a successful, complete, well-formed read of the zone DNS records",
        )
    if payload.get("success") is not True:
        return None, unknown(
            fact_name, "cf_api_unsuccessful",
            "the Cloudflare envelope must report success: true",
        )
    records = payload.get("result")
    if not isinstance(records, list):
        return None, unknown(
            fact_name, "cf_api_no_result",
            "the response `result` must be an array of DNS records",
        )
    if not records:
        return None, unknown(
            fact_name, "no_records", f"a DNS record must exist for {fact_name}"
        )
    info = payload.get("result_info")
    total = info.get("total_count") if isinstance(info, dict) else None
    if _pagination_incomplete(total, len(records)):
        return None, unknown(
            fact_name, "cf_api_incomplete_page",
            "`result_info.total_count` must equal the number of records received",
        )
    for record in records:
        if not isinstance(record, dict):
            return None, unknown(
                fact_name, "malformed_dns_record", "each DNS record must be an object"
            )
    return records, {}


def audit_internal_origin_dns(
    token: str | None,
    zone_id: str | None,
    origin_name: str | None,
    tunnel_id: str | None,
) -> dict[str, Any]:
    """The internal origin must terminate at the **selected** tunnel.

    Accepting any `*.cfargotunnel.com` target would pass a hostname pointed at
    a different tunnel entirely, which is the routing gap the shape review
    named. The CNAME content must be `<CLOUDFLARE_TUNNEL_ID>.cfargotunnel.com`.
    """
    if not token:
        return unknown(
            "internal_origin_dns", "missing_CLOUDFLARE_API_TOKEN",
            "a Cloudflare token with DNS read scope",
        )
    if not zone_id:
        return unknown(
            "internal_origin_dns", "missing_CLOUDFLARE_ZONE_ID", "CLOUDFLARE_ZONE_ID"
        )
    if not origin_name:
        return unknown(
            "internal_origin_dns", "missing_internal_origin_name",
            "TINYASSETS_INTERNAL_ORIGIN_NAME must name the Access-gated internal "
            "origin hostname; the public apex is not a substitute for it",
        )
    if not tunnel_id:
        return unknown(
            "internal_origin_dns", "missing_CLOUDFLARE_TUNNEL_ID",
            "CLOUDFLARE_TUNNEL_ID must name the selected tunnel; 'some tunnel' "
            "is not the same fact as 'the tunnel this deployment serves'",
        )
    records, failure = _dns_records(token, zone_id, origin_name, "internal_origin_dns")
    if records is None:
        return failure
    expected_target = f"{tunnel_id}.cfargotunnel.com".lower()
    bound = sum(
        1
        for r in records
        if r.get("type") == "CNAME"
        and str(r.get("content", "")).strip().rstrip(".").lower() == expected_target
    )
    other_tunnel = sum(
        1
        for r in records
        if r.get("type") == "CNAME"
        and str(r.get("content", "")).strip().rstrip(".").lower().endswith(
            ".cfargotunnel.com"
        )
        and str(r.get("content", "")).strip().rstrip(".").lower() != expected_target
    )
    if other_tunnel:
        return fact(
            "internal_origin_dns", REFUSE, "bound_to_a_different_tunnel",
            records=len(records), bound_to_selected_tunnel=False,
        )
    if bound:
        return fact(
            "internal_origin_dns", PASS, "terminates_at_selected_tunnel",
            records=len(records), bound_to_selected_tunnel=True,
        )
    return fact(
        "internal_origin_dns", REFUSE, "not_a_tunnel_cname",
        records=len(records), bound_to_selected_tunnel=False,
    )


def audit_public_worker_route(
    token: str | None,
    zone_id: str | None,
    public_name: str | None,
    worker_name: str | None,
) -> dict[str, Any]:
    """The public hostname must be served by the expected Worker route.

    An apex CNAME alone does not establish that the public surface reaches the
    internal origin; the Worker route is the hop that does.
    """
    if not token:
        return unknown(
            "public_worker_route", "missing_CLOUDFLARE_API_TOKEN",
            "a Cloudflare token with Workers Routes read scope",
        )
    if not zone_id:
        return unknown(
            "public_worker_route", "missing_CLOUDFLARE_ZONE_ID", "CLOUDFLARE_ZONE_ID"
        )
    if not public_name:
        return unknown(
            "public_worker_route", "missing_public_name", "--public-name"
        )
    if not worker_name:
        return unknown(
            "public_worker_route", "missing_expected_worker_name",
            "TINYASSETS_WORKER_NAME must name the Worker script expected to "
            "serve the public hostname; 'a route exists' is not 'the right "
            "script is bound'",
        )
    url = f"{CF_API}/zones/{zone_id}/workers/routes"
    payload, reason = _get_json(url, {"Authorization": f"Bearer {token}"})
    if payload is None:
        return unknown(
            "public_worker_route", f"cf_api_{reason}",
            "a successful, complete, well-formed read of the zone Worker routes",
        )
    if payload.get("success") is not True:
        return unknown(
            "public_worker_route", "cf_api_unsuccessful",
            "the Cloudflare envelope must report success: true",
        )
    routes = payload.get("result")
    if not isinstance(routes, list):
        return unknown(
            "public_worker_route", "cf_api_no_result",
            "the response `result` must be an array of route objects",
        )
    if not routes:
        return unknown(
            "public_worker_route", "no_routes",
            "at least one Worker route must exist before route binding can be "
            "assessed",
        )
    matching = 0
    for route in routes:
        if not isinstance(route, dict):
            return unknown(
                "public_worker_route", "malformed_route_record",
                "each route entry must be an object",
            )
        pattern = route.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            return unknown(
                "public_worker_route", "route_without_pattern",
                "each route must report a string `pattern`",
            )
        host = pattern.split("/", 1)[0].lower()
        if host != public_name.lower():
            continue
        matching += 1
        if route.get("script") != worker_name:
            return fact(
                "public_worker_route", REFUSE, "route_bound_to_unexpected_script",
                routes_matching_public_name=matching, bound_to_expected_worker=False,
            )
    if not matching:
        return fact(
            "public_worker_route", REFUSE, "no_route_for_public_name",
            routes_matching_public_name=0, bound_to_expected_worker=False,
        )
    return fact(
        "public_worker_route", PASS, "bound_to_expected_worker",
        routes_matching_public_name=matching, bound_to_expected_worker=True,
    )


# --- fact G: hosted placement and credential custody ----------------------

def hosted_custody_fact() -> dict[str, Any]:
    """Permanently unknown until the workflow is wired and deployed.

    `CI=true` is settable by anyone anywhere; it is an accidental-use guard, not
    evidence of where this ran or who holds the secrets.
    """
    return unknown(
        "hosted_credential_custody", "workflow_placement_and_custody_unverified",
        "a deployed `.github/workflows/cloud-only-preflight.yml` "
        "(ubuntu-latest, permissions: contents: read, workflow_dispatch + "
        "schedule, never pull_request) plus a deployed sha proving the secrets "
        "are held only by that workflow. CI=true does not establish either.",
    )


# --- entry point ----------------------------------------------------------

def sanitize(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip every internal key (leading underscore) before anything is printed."""
    return [{k: v for k, v in f.items() if not k.startswith("_")} for f in facts]


def _overall(clean: list[dict[str, Any]]) -> tuple[str, int]:
    verdicts = {f["verdict"] for f in clean}
    if REFUSE in verdicts:
        return REFUSE, 1
    if UNKNOWN in verdicts:
        return UNKNOWN, 2
    return PASS, 0


def run(argv: list[str] | None = None, env: dict[str, str] | None = None) -> int:
    env = dict(os.environ if env is None else env)
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--container-service", default="tinyassets-daemon")
    parser.add_argument("--public-name", default="tinyassets.io")
    parser.add_argument(
        "--container-probe-report",
        default=None,
        help="Path to a strictly-validated report line from the fixed remote probe.",
    )
    parser.add_argument(
        "--skip-container-probe",
        action="store_true",
        help=(
            "Do not attempt the probe. The fact is still reported, as a typed "
            "unknown -- a required fact is never skipped out of the result set."
        ),
    )
    args = parser.parse_args(argv)

    if env.get("CI", "").lower() not in {"true", "1"}:
        print(
            json.dumps(
                {
                    "status": UNKNOWN,
                    "reason": "not_hosted_ci",
                    "facts": [],
                    "enforcement": "none",
                    "boundary_closed": False,
                    "hosted_trust": "unverified",
                    "note": (
                        "CI=true is an accidental-use guard against running this "
                        "with production credentials on a personal machine. It is "
                        "not evidence of hosted execution or credential custody."
                    ),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    facts: list[dict[str, Any]] = []

    # A. container metadata -- always reported, never omitted.
    if args.skip_container_probe:
        container = unknown(
            "container_metadata", "container_probe_skipped_by_operator",
            "run without --skip-container-probe; a skipped required fact stays "
            "unknown and can never contribute to an overall pass",
        )
    elif args.container_probe_report:
        container = read_probe_report(args.container_probe_report)
    else:
        target, reason, requirement = resolve_remote_probe_target(env)
        container = probe_container_metadata(
            args.container_service, target, reason, requirement
        )
    facts.append(container)

    # B. expected droplet.
    droplet = resolve_expected_droplet(
        env.get("DO_API_TOKEN"), env.get("DO_DROPLET_HOST")
    )
    facts.append(droplet)
    addresses = set(droplet.get("_addresses") or [])

    # C. the comparison the design actually depends on.
    facts.append(compare_cloud_identity(container, droplet))

    # D-F.
    facts.append(
        audit_tunnel_connectors(
            env.get("CLOUDFLARE_API_TOKEN"),
            env.get("CLOUDFLARE_ACCOUNT_ID"),
            env.get("CLOUDFLARE_TUNNEL_ID"),
            addresses,
        )
    )
    facts.append(
        audit_internal_origin_dns(
            env.get("CLOUDFLARE_API_TOKEN"),
            env.get("CLOUDFLARE_ZONE_ID"),
            env.get("TINYASSETS_INTERNAL_ORIGIN_NAME"),
            env.get("CLOUDFLARE_TUNNEL_ID"),
        )
    )
    facts.append(
        audit_public_worker_route(
            env.get("CLOUDFLARE_API_TOKEN"),
            env.get("CLOUDFLARE_ZONE_ID"),
            args.public_name,
            env.get("TINYASSETS_WORKER_NAME"),
        )
    )

    # G. always unknown -- so an overall pass is unreachable, correctly.
    facts.append(hosted_custody_fact())

    clean = sanitize(facts)
    status, code = _overall(clean)

    print(
        json.dumps(
            {
                "status": status,
                "facts": clean,
                "enforcement": "none",
                "boundary_closed": False,
                "hosted_trust": "unverified",
                "note": (
                    "Observation only. This does not enforce cloud-only "
                    "admission. Hosted placement and credential custody are "
                    "unverified, so an overall pass is not reachable here."
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run())
