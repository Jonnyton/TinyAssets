"""Public MCP uptime canary — stdlib-only end-to-end probe.

POSTs an ``initialize`` JSON-RPC request against a configurable MCP
endpoint (default ``https://tinyassets.io/mcp``) and validates the
response carries a well-formed MCP ``serverInfo`` + ``protocolVersion``.

Intended for continuous uptime monitoring per the 24/7 forever rule.
Tray wires this on a timer; on nonzero exit, tray surfaces an alert.

Exit codes
----------
0   Endpoint is healthy — full MCP initialize round-trip succeeded.
1   Endpoint is reachable but did not return a valid MCP initialize
    response (wrong content-type, missing fields, protocol mismatch).
2   Endpoint is unreachable (DNS failure, TCP refused, TLS failure,
    HTTP non-2xx).
3   Response parsed but MCP-level error returned (``jsonrpc`` error
    field present).
4   ``--assert-handles`` drift: the live ``tools/list`` does not advertise
    exactly the canonical handle set (``read_graph`` / ``write_graph`` /
    ``run_graph`` / ``read_page`` / ``write_page`` / ``converse`` /
    ``get_status`` — see ``CANONICAL_HANDLES`` below and
    ``openspec/specs/live-mcp-connector-surface/spec.md``). This is the
    PR-178 drift guard required by Hard Rule #11 after any
    DNS/tunnel/Worker/connector change.
5   ``--assert-handles`` status failure: ``tools/call get_status`` failed or
    omitted the uptime-critical ``active_host`` / ``release_state`` fields.

Usage
-----
    python scripts/mcp_public_canary.py
    python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp
    python scripts/mcp_public_canary.py --timeout 15
    python scripts/mcp_public_canary.py --assert-handles   # Hard Rule #11

All output on failure goes to stderr so tray can stream it. stdout
stays silent unless ``--verbose`` is passed so the canary is cheap to
tail.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_URL = "https://tinyassets.io/mcp"
DEFAULT_TIMEOUT = 10.0

_INIT_PAYLOAD = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "mcp-public-canary", "version": "1.0"},
    },
}

# PR-178 + 2026-07-24 canonical convergence: the live user-facing surface is
# exactly these seven handles. The canary asserts the deployed tools/list
# advertises all seven and nothing beyond them. Legacy fat tools are
# dual-registered but hidden from tools/list, so they must NOT appear here.
# `converse` is the relay handle (chatbot -> universe intelligence); the handle
# shape is provisional pending host ratification of the design-note open-Q.
CANONICAL_HANDLES = frozenset({
    "read_graph",
    "write_graph",
    "run_graph",
    "read_page",
    "write_page",
    "converse",
    "get_status",
})
_ALLOWED_ADVERTISED = CANONICAL_HANDLES


def _die(code: int, msg: str) -> None:
    print(f"[canary] {msg}", file=sys.stderr)
    sys.exit(code)


class CanaryError(Exception):
    """Probe failed. Carries the same (exit_code, message) shape as ``_die``."""

    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code
        self.msg = msg


def _parse_sse_or_json(body: bytes) -> dict[str, Any]:
    """MCP streamable-http returns either JSON or SSE ``event: message``
    frames. Accept both."""
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        raise ValueError("empty body")
    if text.startswith("{"):
        return json.loads(text)
    # SSE: find the first ``data: {...}`` line.
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload:
                return json.loads(payload)
    raise ValueError("no JSON or SSE data frame in response body")


def _post(
    url: str,
    payload: dict[str, Any],
    timeout: float,
    session_id: str | None = None,
) -> tuple[int, dict[str, str], bytes]:
    """POST one JSON-RPC frame. Return (status, headers, body). Raise on I/O.

    Factored out (and module-level) so unit tests can monkeypatch it to drive
    the handshake offline without a network.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "tinyassets-mcp-canary/1.0",
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as exc:
        raise CanaryError(2, f"HTTP {exc.code} from {url}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise CanaryError(2, f"unreachable {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise CanaryError(2, f"timeout after {timeout}s: {url}") from exc
    except ssl.SSLError as exc:
        raise CanaryError(2, f"TLS error {url}: {exc}") from exc
    except OSError as exc:
        raise CanaryError(2, f"socket error {url}: {exc}") from exc


def advertised_tool_names(url: str, timeout: float) -> set[str]:
    """Full MCP handshake → tools/list; return the advertised tool name set."""
    status, headers, _ = _post(url, _INIT_PAYLOAD, timeout)
    if status != 200:
        raise CanaryError(2, f"non-200 status {status} from {url}")
    session_id = headers.get("mcp-session-id")
    if session_id:
        # Streamable-HTTP requires the initialized notification before reads.
        _post(
            url,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            timeout,
            session_id,
        )
    status, _, body = _post(
        url,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        timeout,
        session_id,
    )
    if status != 200:
        raise CanaryError(2, f"non-200 status {status} from {url} (tools/list)")
    try:
        payload = _parse_sse_or_json(body)
    except (ValueError, json.JSONDecodeError) as exc:
        raise CanaryError(1, f"non-MCP tools/list body from {url}: {exc}") from exc
    if "error" in payload:
        raise CanaryError(3, f"MCP error on tools/list from {url}: {payload['error']}")
    tools = (payload.get("result") or {}).get("tools") or []
    if not isinstance(tools, list):
        raise CanaryError(1, f"malformed tools/list from {url}: {tools!r}")
    return {t.get("name") for t in tools if isinstance(t, dict) and t.get("name")}


def assert_canonical_handles(url: str, timeout: float) -> None:
    """Raise ``CanaryError(4)`` unless tools/list is exactly the canonical set."""
    names = advertised_tool_names(url, timeout)
    missing = CANONICAL_HANDLES - names
    extra = names - _ALLOWED_ADVERTISED
    if missing or extra:
        raise CanaryError(
            4,
            f"handle drift on {url}: missing={sorted(missing)} "
            f"extra={sorted(extra)} advertised={sorted(names)}",
        )


def assert_status_surface(url: str, timeout: float) -> str:
    """Call ``get_status`` and verify its uptime-critical response fields.

    Return a compact identity-evidence state so verbose canary output makes
    fingerprint configuration degradation visible without treating it as a
    status-surface outage.
    """
    status, headers, _ = _post(url, _INIT_PAYLOAD, timeout)
    if status != 200:
        raise CanaryError(2, f"non-200 status {status} from {url}")
    session_id = headers.get("mcp-session-id")
    if session_id:
        _post(
            url,
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            timeout,
            session_id,
        )
    status, _, body = _post(
        url,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_status", "arguments": {}},
        },
        timeout,
        session_id,
    )
    if status != 200:
        raise CanaryError(5, f"non-200 status {status} from {url} (get_status)")
    try:
        rpc_payload = _parse_sse_or_json(body)
    except (ValueError, json.JSONDecodeError) as exc:
        raise CanaryError(5, f"non-MCP get_status body from {url}: {exc}") from exc
    if "error" in rpc_payload:
        raise CanaryError(
            5,
            f"MCP error on get_status from {url}: {rpc_payload['error']}",
        )
    result = rpc_payload.get("result") or {}
    if result.get("isError"):
        raise CanaryError(5, f"get_status returned a tool error from {url}")
    payload = result.get("structuredContent")
    if not isinstance(payload, dict):
        content = result.get("content") or []
        text_blocks = [
            item.get("text")
            for item in content
            if isinstance(item, dict)
            and item.get("type") == "text"
            and isinstance(item.get("text"), str)
        ]
        if not text_blocks:
            raise CanaryError(5, f"get_status returned no text payload from {url}")
        try:
            payload = json.loads(text_blocks[0])
        except json.JSONDecodeError as exc:
            raise CanaryError(
                5,
                f"get_status returned non-JSON text from {url}",
            ) from exc
    if not isinstance(payload, dict):
        raise CanaryError(5, f"get_status payload is not an object from {url}")
    missing = [
        field for field in ("active_host", "release_state") if field not in payload
    ]
    if missing:
        raise CanaryError(
            5,
            f"get_status uptime fields missing from {url}: {missing}",
        )

    identity_evidence = payload.get("identity_evidence")
    if not isinstance(identity_evidence, dict):
        return "unknown"
    identity_status = identity_evidence.get("status")
    if identity_status == "unavailable":
        reason = identity_evidence.get("reason")
        return f"unavailable:{reason}" if isinstance(reason, str) else "unavailable"
    return str(identity_status or "unknown")


def assert_canonical_handles_with_retry(
    url: str,
    timeout: float,
    retries: int = 5,
    delay: float = 3.0,
    _sleep=time.sleep,
) -> str:
    """Assert canonical handles and status surface, retrying transient blips.

    Return the compact identity-evidence state reported by ``get_status``.

    Wired into the post-deploy gate, where a single transient ``tools/list``
    failure would otherwise trip a rollback of an otherwise-healthy daemon
    (a fresh image can briefly serve before the surface fully settles). The
    last attempt's ``CanaryError`` propagates so a genuine regression still
    fails the deploy.
    """
    attempts = max(1, retries)
    for attempt in range(1, attempts + 1):
        try:
            assert_canonical_handles(url, timeout)
            return assert_status_surface(url, timeout)
        except CanaryError as exc:
            if attempt >= attempts:
                raise
            print(
                f"[canary] handle assertion attempt {attempt}/{attempts} "
                f"failed ({exc.msg}); retrying in {delay}s",
                file=sys.stderr,
            )
            _sleep(delay)


def probe_result(
    url: str,
    timeout: float,
    expected_name: str | None = None,
) -> None:
    """Run the probe. Return None on success; raise ``CanaryError`` on failure.

    Importable by layered canary wrappers that need to log outcomes without
    exiting the process. ``probe()`` is the CLI-shaped thin adapter.
    """
    req = urllib.request.Request(
        url,
        data=json.dumps(_INIT_PAYLOAD).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "tinyassets-mcp-canary/1.0",
        },
    )
    ctx = ssl.create_default_context()

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            status = resp.status
            body = resp.read()
    except urllib.error.HTTPError as exc:
        raise CanaryError(2, f"HTTP {exc.code} from {url}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise CanaryError(2, f"unreachable {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise CanaryError(2, f"timeout after {timeout}s: {url}") from exc
    except ssl.SSLError as exc:
        raise CanaryError(2, f"TLS error {url}: {exc}") from exc
    except OSError as exc:
        raise CanaryError(2, f"socket error {url}: {exc}") from exc

    if status != 200:
        raise CanaryError(2, f"non-200 status {status} from {url}")

    try:
        payload = _parse_sse_or_json(body)
    except (ValueError, json.JSONDecodeError) as exc:
        preview = body[:200].decode("utf-8", errors="replace")
        raise CanaryError(1, f"non-MCP body from {url}: {exc}; preview={preview!r}") from exc

    if "error" in payload:
        raise CanaryError(3, f"MCP error response from {url}: {payload['error']}")

    result = payload.get("result") or {}
    if not isinstance(result, dict):
        raise CanaryError(1, f"malformed result (not a dict) from {url}: {result!r}")
    if not result.get("protocolVersion"):
        raise CanaryError(1, f"missing protocolVersion in result from {url}: {result!r}")
    server_info = result.get("serverInfo") or {}
    if not server_info.get("name"):
        raise CanaryError(1, f"missing serverInfo.name in result from {url}: {result!r}")
    if expected_name is not None and server_info["name"] != expected_name:
        raise CanaryError(
            1,
            f"serverInfo.name drift from {url}: expected {expected_name!r}, "
            f"got {server_info['name']!r}",
        )


def probe(
    url: str,
    timeout: float,
    expected_name: str | None = None,
) -> None:
    """CLI-shaped adapter — calls ``probe_result`` and ``_die``s on failure."""
    try:
        probe_result(url, timeout, expected_name=expected_name)
    except CanaryError as exc:
        _die(exc.code, exc.msg)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Probe a public MCP endpoint.")
    ap.add_argument("--url", default=DEFAULT_URL, help=f"MCP endpoint URL (default {DEFAULT_URL})")
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                    help=f"request timeout seconds (default {DEFAULT_TIMEOUT})")
    ap.add_argument("--verbose", action="store_true",
                    help="print success line to stdout")
    ap.add_argument("--assert-name",
                    help="require an exact MCP serverInfo.name value")
    ap.add_argument("--assert-handles", action="store_true",
                    help="also assert tools/list advertises exactly the "
                         "canonical handle set incl. converse (PR-178 drift "
                         "guard, Hard Rule #11)")
    ap.add_argument("--assert-handles-retries", type=int, default=5,
                    help="retry the handle assertion N times before failing "
                         "(default 5) — absorbs transient post-deploy blips")
    ap.add_argument("--assert-handles-retry-delay", type=float, default=3.0,
                    help="seconds between handle-assertion retries (default 3)")
    args = ap.parse_args(argv)

    probe(args.url, args.timeout, expected_name=args.assert_name)

    if args.assert_handles:
        try:
            identity_state = assert_canonical_handles_with_retry(
                args.url,
                args.timeout,
                retries=args.assert_handles_retries,
                delay=args.assert_handles_retry_delay,
            )
        except CanaryError as exc:
            _die(exc.code, exc.msg)

    if args.verbose:
        suffix = (
            " (canonical handle set advertised; get_status uptime fields present; "
            f"identity_evidence={identity_state})"
            if args.assert_handles
            else ""
        )
        print(f"[canary] OK {args.url}{suffix}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
