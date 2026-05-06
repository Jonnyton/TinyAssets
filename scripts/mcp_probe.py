"""Minimal MCP client over streamable-http — ops CLI for querying prod daemon state.

Stdlib only. Handles the streamable-http SSE-wrapped responses.

Subcommands (convenience):
    workflow-probe status               → get_status
    workflow-probe universes            → universe action=list
    workflow-probe universe <id>        → universe action=inspect universe_id=<id>
    workflow-probe wiki                 → wiki action=list
    workflow-probe tools                → tools/list (same as --list)
    workflow-probe latency              → time initialize + get_status

Raw call:
    workflow-probe --tool get_status
    workflow-probe --tool universe --args '{"action":"list"}'
    workflow-probe --list
    workflow-probe --tool universe --args '{"action":"inspect","universe_id":"x"}' --raw

All subcommands accept --url and --raw flags.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from typing import Any

DEFAULT_URL = "https://tinyassets.io/mcp"
MCP_PROTOCOL_VERSION = "2024-11-05"

# Set to True by --verbose at parse time; read by helpers.
_VERBOSE = False


def _vlog(msg: str) -> None:
    if _VERBOSE:
        print(f"[probe] {msg}", file=sys.stderr)


def _mcp_call(url: str, sid: str | None, payload: dict[str, Any]) -> tuple[dict | None, str | None]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "workflow-lead-probe/1.0",
    }
    if sid:
        headers["mcp-session-id"] = sid
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST", headers=headers
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        new_sid = resp.headers.get("mcp-session-id") or sid
        body = resp.read().decode()
    result = None
    for line in body.splitlines():
        if line.startswith("data:"):
            try:
                result = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                pass
    return result, new_sid


def _initialize(url: str) -> tuple[str | None, int]:
    """Run MCP initialize + notifications/initialized. Returns (sid, exit_code)."""
    _vlog(f"initialize → {url}")
    init_resp, sid = _mcp_call(
        url,
        None,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "clientInfo": {"name": "lead-probe", "version": "1"},
                "capabilities": {},
            },
        },
    )
    if not init_resp or "result" not in init_resp:
        print("initialize failed", file=sys.stderr)
        print(init_resp, file=sys.stderr)
        return None, 1
    _vlog(f"session-id: {sid}")
    _mcp_call(url, sid, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    _vlog("notifications/initialized sent")
    return sid, 0


def _tool_response_exit_code(resp: dict | None) -> int:
    if not resp or "error" in resp or "result" not in resp:
        return 1
    if resp["result"].get("isError"):
        return 1
    return 0


def _call_tool(url: str, sid: str | None, tool: str, tool_args: dict, *, raw: bool) -> int:
    _vlog(f"tools/call {tool} args={tool_args}")
    resp, _ = _mcp_call(
        url,
        sid,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": tool, "arguments": tool_args},
        },
    )
    if raw:
        print(json.dumps(resp, indent=2))
        return _tool_response_exit_code(resp)
    if resp and "result" in resp:
        for item in resp["result"].get("content", []):
            if item.get("type") == "text":
                print(item["text"])
        if resp["result"].get("isError"):
            return 1
        return 0
    print(json.dumps(resp, indent=2))
    return 1


def _cmd_status(url: str, raw: bool) -> int:
    sid, rc = _initialize(url)
    if rc:
        return rc
    return _call_tool(url, sid, "get_status", {}, raw=raw)


def _cmd_universes(url: str, raw: bool) -> int:
    sid, rc = _initialize(url)
    if rc:
        return rc
    return _call_tool(url, sid, "universe", {"action": "list"}, raw=raw)


def _cmd_universe(url: str, universe_id: str, raw: bool) -> int:
    sid, rc = _initialize(url)
    if rc:
        return rc
    return _call_tool(
        url, sid, "universe", {"action": "inspect", "universe_id": universe_id}, raw=raw
    )


def _cmd_wiki(url: str, raw: bool) -> int:
    sid, rc = _initialize(url)
    if rc:
        return rc
    return _call_tool(url, sid, "wiki", {"action": "list"}, raw=raw)


def _cmd_tools(url: str, raw: bool) -> int:
    sid, rc = _initialize(url)
    if rc:
        return rc
    resp, _ = _mcp_call(url, sid, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    if not resp or "result" not in resp:
        print(json.dumps(resp, indent=2))
        return 1
    if raw:
        print(json.dumps(resp, indent=2))
        return 0
    for t in resp["result"]["tools"]:
        print(f"{t['name']:<20} {t.get('description', '').splitlines()[0][:80]}")
    return 0


def _format_latency_line(result: dict[str, Any]) -> str:
    status = "ok" if result.get("ok") else "error"
    return (
        f"latency_ms={result['latency_ms']} "
        f"status={status} "
        f"stage={result['stage']} "
        f"url={result['url']}"
    )


def _cmd_latency(url: str, raw: bool) -> int:
    start = time.monotonic()
    sid, rc = _initialize(url)
    if rc:
        latency_ms = int((time.monotonic() - start) * 1000)
        result = {
            "ok": False,
            "url": url,
            "latency_ms": latency_ms,
            "stage": "initialize",
        }
        print(json.dumps(result, indent=2) if raw else _format_latency_line(result))
        return rc

    resp, _ = _mcp_call(
        url,
        sid,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_status", "arguments": {}},
        },
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    rc = _tool_response_exit_code(resp)
    result: dict[str, Any] = {
        "ok": rc == 0,
        "url": url,
        "latency_ms": latency_ms,
        "stage": "get_status",
    }
    if raw:
        result["response"] = resp
        print(json.dumps(result, indent=2))
    else:
        print(_format_latency_line(result))
    return rc


def _coerce_relaxed_value(value: str) -> Any:
    value = value.strip().strip("'\"")
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower == "null":
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _parse_relaxed_object(raw: str) -> dict[str, Any] | None:
    """Parse simple PowerShell-stripped JSON like {action:list,limit:5}.

    This is deliberately shallow. Nested JSON still needs valid JSON quoting.
    """
    text = raw.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    body = text[1:-1].strip()
    if not body:
        return {}

    result: dict[str, Any] = {}
    for part in body.split(","):
        key, sep, value = part.partition(":")
        if not sep:
            return None
        key = key.strip().strip("'\"")
        if not key:
            return None
        result[key] = _coerce_relaxed_value(value)
    return result


def _parse_tool_args(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        parsed = _parse_relaxed_object(raw)
        if parsed is None:
            raise ValueError(
                "--args must be a JSON object; simple PowerShell-stripped "
                "{action:list} objects are also accepted"
            ) from exc
    if not isinstance(parsed, dict):
        raise ValueError("--args must decode to an object")
    return parsed


def _add_subcommand_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--url", default=argparse.SUPPRESS, help="MCP endpoint URL")
    parser.add_argument(
        "--raw",
        action="store_true",
        default=argparse.SUPPRESS,
        help="print full JSON response",
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="workflow-probe",
        description="Query the Workflow MCP daemon from the command line.",
    )
    p.add_argument("--url", default=DEFAULT_URL, help="MCP endpoint URL")
    p.add_argument("--raw", action="store_true", help="print full JSON response")
    p.add_argument("--verbose", action="store_true",
                   help="log initialize/tool-call progress to stderr")

    sub = p.add_subparsers(dest="subcommand")

    status = sub.add_parser("status", help="call get_status")
    _add_subcommand_flags(status)

    universes = sub.add_parser("universes", help="list all universes")
    _add_subcommand_flags(universes)

    uni = sub.add_parser("universe", help="inspect a specific universe")
    uni.add_argument("universe_id", help="universe ID to inspect")
    _add_subcommand_flags(uni)

    wiki = sub.add_parser("wiki", help="list wiki pages")
    _add_subcommand_flags(wiki)

    tools = sub.add_parser("tools", help="list available MCP tools")
    _add_subcommand_flags(tools)

    latency = sub.add_parser("latency", help="time initialize + get_status")
    _add_subcommand_flags(latency)

    # Raw / legacy flags (no subcommand path)
    p.add_argument("--tool", help="tool name for raw call")
    p.add_argument("--args", default="{}", help="JSON args for raw tool call")
    p.add_argument("--list", action="store_true", help="list tools (legacy alias for 'tools')")

    return p


def main() -> int:
    global _VERBOSE
    p = _build_parser()
    args = p.parse_args()
    _VERBOSE = bool(args.verbose)
    url = args.url
    raw = args.raw

    if args.subcommand == "status":
        return _cmd_status(url, raw)
    if args.subcommand == "universes":
        return _cmd_universes(url, raw)
    if args.subcommand == "universe":
        return _cmd_universe(url, args.universe_id, raw)
    if args.subcommand == "wiki":
        return _cmd_wiki(url, raw)
    if args.subcommand == "tools":
        return _cmd_tools(url, raw)
    if args.subcommand == "latency":
        return _cmd_latency(url, raw)

    # Legacy / raw path
    if args.list:
        return _cmd_tools(url, raw)

    if not args.tool:
        print(
            "use a subcommand (status/universes/universe/wiki/tools/latency) "
            "or --tool <name>",
            file=sys.stderr,
        )
        return 2

    try:
        tool_args = _parse_tool_args(args.args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sid, rc = _initialize(url)
    if rc:
        return rc
    return _call_tool(url, sid, args.tool, tool_args, raw=raw)


if __name__ == "__main__":
    sys.exit(main())
