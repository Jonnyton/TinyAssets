"""Self-host migration smoke test — Row F.

Default mode probes the user-facing canonical URL, confirms the direct tunnel
URL is blocked by Cloudflare Access, and verifies the canonical daemon has an
LLM bound. Use ``--internal-parity`` only when ``--tunnel`` points at an
internal/service-token path that is expected to speak MCP.

Exit codes:
  0  Canonical URL healthy, direct tunnel gate healthy, and LLM bound.
  1  Canonical URL returned unexpected MCP content (protocol-level fail).
  2  Canonical URL or tunnel gate unreachable (network-level fail).
  3  Direct tunnel unexpectedly reachable, or internal parity mismatch.
  4  Invalid arguments.

Usage:
  python scripts/selfhost_smoke.py
  python scripts/selfhost_smoke.py \\
      --canonical https://tinyassets.io/mcp \\
      --tunnel    https://mcp.tinyassets.io/mcp \\
      --timeout   20
  python scripts/selfhost_smoke.py --internal-parity --tunnel http://127.0.0.1:8001/mcp

Designed to run at hour 1, hour 24, and hour 47 of the 48-hour offline
acceptance trial per the Row F spec.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _canary_common import canary_bearer_for  # noqa: E402

#: "Not specified" -- distinct from an explicit ``None``, which means "this
#: daemon is pre-cutover, send no bearer". Omitting the argument reads the
#: configured token WITHOUT a network call, so a direct caller (and every unit
#: test that drives a helper) behaves as it always did.
_FROM_ENV: Any = object()

from mcp_public_canary import CanaryError, probe_result  # noqa: E402
from verify_llm_binding import VerifyError, check_llm_binding  # noqa: E402

CANONICAL_URL = "https://tinyassets.io/mcp"
TUNNEL_URL = "https://mcp.tinyassets.io/mcp"
DEFAULT_TIMEOUT = 20.0
ACCESS_GATE_STATUS_CODES = {401, 403}

_INIT_PAYLOAD = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "selfhost-smoke", "version": "1.0"},
    },
}
_INITIALIZED_NOTIF = {"jsonrpc": "2.0", "method": "notifications/initialized"}
_TOOLS_LIST_PAYLOAD = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
_GET_STATUS_PAYLOAD = {
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {"name": "get_status", "arguments": {}},
}


class SmokeError(Exception):
    def __init__(self, code: int, msg: str) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg


def _post(
    url: str, sid: str | None, payload: dict, timeout: float, *, bearer_token: str
) -> tuple[dict | None, str | None]:
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "workflow-selfhost-smoke/1.0",
    }
    if sid:
        headers["mcp-session-id"] = sid
    if bearer_token:
        # Absent against a pre-cutover daemon, which refuses this bearer.
        headers["Authorization"] = f"Bearer {bearer_token}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            new_sid = resp.headers.get("mcp-session-id") or sid
            body = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
        raise SmokeError(2, f"network error on {url}: {exc}") from exc

    result = None
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            try:
                result = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                pass
        elif line.startswith("{"):
            try:
                result = json.loads(line)
            except json.JSONDecodeError:
                pass
    return result, new_sid


def _initialize(url: str, timeout: float, bearer_token: str) -> str | None:
    resp, sid = _post(
        url, None, _INIT_PAYLOAD, timeout, bearer_token=bearer_token,
    )
    if not resp or "result" not in resp:
        raise SmokeError(1, f"initialize failed on {url}: {resp!r}")
    _post(url, sid, _INITIALIZED_NOTIF, timeout, bearer_token=bearer_token)
    return sid


def _tools_list(
    url: str, sid: str | None, timeout: float, bearer_token: str,
) -> set[str]:
    resp, _ = _post(
        url, sid, _TOOLS_LIST_PAYLOAD, timeout, bearer_token=bearer_token,
    )
    if not resp or "result" not in resp:
        raise SmokeError(1, f"tools/list failed on {url}: {resp!r}")
    tools = resp["result"].get("tools") or []
    return {t["name"] for t in tools}


def _get_status(
    url: str, sid: str | None, timeout: float, bearer_token: str,
) -> dict[str, Any]:
    resp, _ = _post(
        url, sid, _GET_STATUS_PAYLOAD, timeout, bearer_token=bearer_token,
    )
    if not resp or "result" not in resp:
        raise SmokeError(1, f"get_status failed on {url}: {resp!r}")
    content = resp["result"].get("content") or []
    for item in content:
        if item.get("type") == "text":
            try:
                return json.loads(item["text"])
            except (json.JSONDecodeError, KeyError):
                return {"raw": item["text"]}
    raise SmokeError(1, f"get_status returned no text content on {url}")


def probe_url(
    url: str, timeout: float, label: str, bearer_token: str,
) -> tuple[set[str], dict[str, Any]]:
    print(f"[smoke] probing {label}: {url}")
    try:
        probe_result(url, timeout, bearer=bearer_token)
    except CanaryError as exc:
        raise SmokeError(exc.code, f"{label} canary failed: {exc.msg}") from exc
    sid = _initialize(url, timeout, bearer_token)
    tools = _tools_list(url, sid, timeout, bearer_token)
    status = _get_status(url, sid, timeout, bearer_token)
    print(f"[smoke] {label}: {len(tools)} tools, get_status OK")
    return tools, status


def assert_tunnel_access_blocked(
    url: str, timeout: float, bearer_token: str | None,
) -> int:
    print(f"[smoke] probing tunnel Access gate: {url}")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "workflow-selfhost-smoke/1.0",
    }
    if bearer_token:
        # Absent against a pre-cutover daemon, which refuses this bearer.
        headers["Authorization"] = f"Bearer {bearer_token}"
    req = urllib.request.Request(
        url,
        data=json.dumps(_INIT_PAYLOAD).encode(),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read(200).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code in ACCESS_GATE_STATUS_CODES:
            print(f"[smoke] tunnel Access gate PASS — HTTP {exc.code}")
            return exc.code
        raise SmokeError(
            3,
            f"tunnel Access gate returned HTTP {exc.code}; expected 401/403",
        ) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise SmokeError(2, f"tunnel Access gate network error on {url}: {exc}") from exc

    snippet = body.replace("\n", " ")[:120]
    raise SmokeError(
        3,
        f"tunnel direct access unexpectedly returned HTTP {status}; "
        f"expected 401/403. Body: {snippet!r}",
    )


def assert_parity(
    canonical_tools: set[str],
    tunnel_tools: set[str],
    canonical_status: dict,
    tunnel_status: dict,
) -> None:
    errors = []

    only_canonical = canonical_tools - tunnel_tools
    only_tunnel = tunnel_tools - canonical_tools
    if only_canonical:
        errors.append(f"tools only in canonical: {sorted(only_canonical)}")
    if only_tunnel:
        errors.append(f"tools only in tunnel: {sorted(only_tunnel)}")

    canonical_keys = set(canonical_status.keys()) if isinstance(canonical_status, dict) else set()
    tunnel_keys = set(tunnel_status.keys()) if isinstance(tunnel_status, dict) else set()
    key_diff = canonical_keys.symmetric_difference(tunnel_keys)
    if key_diff:
        errors.append(f"get_status top-level key mismatch: {sorted(key_diff)}")

    if errors:
        raise SmokeError(3, "parity failure:\n  " + "\n  ".join(errors))


def run(
    canonical: str,
    tunnel: str,
    timeout: float,
    *,
    internal_parity: bool = False,
    llm_check_fn=None,  # injection seam: (url, timeout) -> dict; raises VerifyError on fail
    # ``None`` means a PRE-CUTOVER daemon, which refuses this bearer; the
    # default keeps every existing caller (and test) working unchanged.
    bearer_token: str | None = None,
) -> int:
    try:
        canonical_tools, canonical_status = probe_url(
            canonical, timeout, "canonical", bearer_token,
        )
        if internal_parity:
            tunnel_tools, tunnel_status = probe_url(
                tunnel, timeout, "tunnel", bearer_token,
            )
            assert_parity(canonical_tools, tunnel_tools, canonical_status, tunnel_status)
            print(
                f"[smoke] PASS — {len(canonical_tools)} tools in parity, "
                f"get_status structure matches"
            )
        else:
            assert_tunnel_access_blocked(tunnel, timeout, bearer_token)
            print(
                f"[smoke] PASS — canonical has {len(canonical_tools)} tools; "
                "direct tunnel is Access-gated"
            )
    except SmokeError as exc:
        print(f"[smoke] FAIL (exit {exc.code}): {exc.msg}", file=sys.stderr)
        return exc.code

    # LLM-binding gate (HD-3): smoke fails if canonical daemon has no LLM bound.
    _llm_check = llm_check_fn or check_llm_binding
    try:
        _llm_check(canonical, timeout, bearer_token=bearer_token)
        print("[smoke] LLM binding check PASS")
    except VerifyError as exc:
        print(f"[smoke] LLM binding FAIL (exit {exc.code}): {exc.msg}", file=sys.stderr)
        return exc.code

    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Self-host migration smoke test (Row F).")
    ap.add_argument("--canonical", default=CANONICAL_URL, help="User-facing canonical URL")
    ap.add_argument("--tunnel", default=TUNNEL_URL, help="Direct tunnel URL")
    ap.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT,
        help=f"Per-request timeout seconds (default {DEFAULT_TIMEOUT})"
    )
    ap.add_argument(
        "--internal-parity",
        action="store_true",
        help=(
            "Probe --tunnel as an MCP endpoint and compare it with --canonical. "
            "Use only for an internal/service-token tunnel path; default expects "
            "the public direct tunnel URL to be Access-gated."
        ),
    )
    args = ap.parse_args(argv)
    # Which contract does THIS daemon keep? Asked once, after the URL is
    # known, so one run never mixes the pre- and post-cutover shapes.
    bearer = canary_bearer_for(args.canonical, "selfhost-smoke", args.timeout)
    return run(
        args.canonical,
        args.tunnel,
        args.timeout,
        internal_parity=args.internal_parity,
        bearer_token=bearer,
    )


if __name__ == "__main__":
    sys.exit(main())
