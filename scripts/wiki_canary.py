"""Wiki write-roundtrip canary — Layer-1 extension.

Probes the wiki MCP surface with a write-then-read roundtrip against a
dedicated canary draft (``drafts/notes/uptime-probe.md``).  A working
``initialize`` handshake is necessary but not sufficient: this canary also
verifies that:

- ``wiki action=write`` persists a known content body without error.
- ``wiki action=read`` returns that content verbatim.

Wiki-write failure is P0 (Forever Rule: 24/7 uptime, auto-heal pipeline).
BUG-028 demonstrated that a slug-normalization bug could silently break bug
filing while the Layer-1 MCP handshake stayed green.  This canary closes
that gap.

Exit codes
----------
0  — all probe steps passed.
2  — MCP handshake failed (initialize / session).
6  — wiki write failed (isError or network error).
7  — wiki read failed or roundtrip content mismatch.
99 — unexpected error.

Usage
-----
    python scripts/wiki_canary.py
    python scripts/wiki_canary.py --url http://127.0.0.1:8001/mcp --verbose
    python scripts/wiki_canary.py --probe-id bisect-run-42
    python scripts/wiki_canary.py --once --format=gha   # GHA output mode

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from _canary_common import _INITIALIZED_NOTIF, _init_payload  # noqa: E402
from mcp_tool_canary import (  # noqa: E402
    ToolCanaryError,
    _extract_structured_tool_payload,
    _extract_tool_text,
    _post,
)
from uptime_canary import _append_log, _now_local_iso  # noqa: E402

DEFAULT_URL = "https://tinyassets.io/mcp"
DEFAULT_TIMEOUT = 20.0

_CANARY_FILENAME = "uptime-probe"
# `notes` is in _WIKI_CATEGORIES on the server (tinyassets/universe_server.py
# `_WIKI_CATEGORIES`); `canary` is not. The previous value silently failed
# the server's category validation, masking real wiki-write breakage.
_CANARY_CATEGORY = "notes"
# ASCII-only content. Server's JSON response wraps the read body with
# `json.dumps`, which (default ensure_ascii=True) escapes non-ASCII
# characters like em-dash to \uNNNN sequences. A substring check on the
# raw response text would then fail. Keep the canary content ASCII so
# the roundtrip check stays a simple substring match.
_CANARY_CONTENT = "TinyAssets wiki uptime canary - automated write-roundtrip probe."

_INIT_PAYLOAD = _init_payload("wiki-canary")
_PROBE_ID_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _filename_for_probe_id(probe_id: str | None) -> str:
    if not probe_id:
        return _CANARY_FILENAME
    suffix = _PROBE_ID_SAFE_RE.sub("-", probe_id.strip()).strip("._-")
    if not suffix:
        raise ValueError("probe_id must contain at least one filename-safe character")
    return f"{_CANARY_FILENAME}-{suffix[:80]}"


def _wiki_write_payload(call_id: int, *, filename: str = _CANARY_FILENAME) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": call_id,
        "method": "tools/call",
        "params": {
            "name": "wiki",
            "arguments": {
                "action": "write",
                "filename": filename,
                "category": _CANARY_CATEGORY,
                "content": _CANARY_CONTENT,
            },
        },
    }


def _wiki_read_payload(call_id: int, *, filename: str = _CANARY_FILENAME) -> dict:
    # `wiki action=read` takes a single `page=` arg (the slug); _resolve_page
    # locates it across pages/ + drafts/ subdirectories. No `category` /
    # `slug` kwargs — that mismatch was the 2026-04-26 canary RED root cause.
    return {
        "jsonrpc": "2.0",
        "id": call_id,
        "method": "tools/call",
        "params": {
            "name": "wiki",
            "arguments": {
                "action": "read",
                "page": filename,
            },
        },
    }


def _format_green(ts: str, url: str, rtt_ms: int) -> str:
    return f"{ts} GREEN layer=wiki url={url} surface=wiki_write rtt_ms={rtt_ms}"


def _format_red(ts: str, url: str, exit_code: int, reason: str, rtt_ms: int) -> str:
    reason_oneline = reason.replace("\n", " ").replace("\r", " ")
    return (
        f"{ts} RED   layer=wiki url={url} exit={exit_code} "
        f"surface=wiki_write rtt_ms={rtt_ms} reason={reason_oneline!r}"
    )


def _emit_gha_kv(key: str, value: str) -> None:
    if "\n" in value or "\r" in value:
        import uuid
        delimiter = f"EOF_{uuid.uuid4().hex}"
        print(f"{key}<<{delimiter}")
        print(value)
        print(delimiter)
    else:
        print(f"{key}={value}")


def run_canary(
    url: str,
    timeout: float,
    *,
    post_fn=None,
    verbose: bool = False,
    canary_filename: str = _CANARY_FILENAME,
) -> None:
    """Run the wiki write-roundtrip canary.

    ``post_fn`` is injectable for tests (same signature as ``mcp_tool_canary._post``).
    Raises ``ToolCanaryError`` on any failure with the appropriate exit code.
    """
    post = post_fn or _post

    # ---- Step 1: MCP handshake -------------------------------------------
    resp, sid = post(url, None, _INIT_PAYLOAD, timeout, step_code=2)
    if resp is None or "result" not in resp:
        raise ToolCanaryError(2, f"initialize returned no result: {resp!r}")
    if "error" in resp:
        raise ToolCanaryError(2, f"initialize returned MCP error: {resp['error']!r}")
    if not sid:
        raise ToolCanaryError(2, "initialize response did not include mcp-session-id header")
    post(url, sid, _INITIALIZED_NOTIF, timeout, step_code=2)
    if verbose:
        print(f"[wiki-canary] handshake OK sid={sid!r}")

    # ---- Step 2: wiki write ----------------------------------------------
    write_resp, _ = post(
        url,
        sid,
        _wiki_write_payload(2, filename=canary_filename),
        timeout,
        step_code=6,
    )
    if write_resp is None or "result" not in write_resp:
        raise ToolCanaryError(6, f"wiki write returned no result: {write_resp!r}")
    write_result = write_resp["result"]
    if write_result.get("isError"):
        text = _extract_tool_text(write_result)[:300]
        raise ToolCanaryError(6, f"wiki write isError=true: {text!r}")
    write_obj = _extract_structured_tool_payload(write_result)
    if write_obj is None:
        write_text = _extract_tool_text(write_result)
        if not write_text:
            raise ToolCanaryError(6, f"wiki write returned no text content: {write_result!r}")
        try:
            write_obj = json.loads(write_text)
        except json.JSONDecodeError as exc:
            raise ToolCanaryError(
                6, f"wiki write text not JSON: {exc}; preview={write_text[:200]!r}"
            ) from exc
    # Server returns "drafted" on first write of a new draft, "updated" on
    # any subsequent write to the same path. Both are healthy for the canary.
    if write_obj.get("status") not in (
        "ok", "written", "drafted", "updated", "filed",
    ):
        raise ToolCanaryError(6, f"wiki write unexpected status: {write_obj!r}")
    if verbose:
        print(f"[wiki-canary] wiki write OK: {write_obj.get('status')!r}")

    # ---- Step 3: wiki read roundtrip -------------------------------------
    read_resp, _ = post(
        url,
        sid,
        _wiki_read_payload(3, filename=canary_filename),
        timeout,
        step_code=7,
    )
    if read_resp is None or "result" not in read_resp:
        raise ToolCanaryError(7, f"wiki read returned no result: {read_resp!r}")
    read_result = read_resp["result"]
    if read_result.get("isError"):
        text = _extract_tool_text(read_result)[:300]
        raise ToolCanaryError(7, f"wiki read isError=true: {text!r}")
    read_obj = _extract_structured_tool_payload(read_result)
    if read_obj is not None:
        read_text = json.dumps(read_obj, default=str)
    else:
        read_text = _extract_tool_text(read_result)
        if not read_text:
            raise ToolCanaryError(7, f"wiki read returned no text content: {read_result!r}")
    if _CANARY_CONTENT not in read_text:
        raise ToolCanaryError(
            7,
            f"wiki roundtrip mismatch: expected content not found in read response. "
            f"preview={read_text[:300]!r}",
        )
    if verbose:
        print("[wiki-canary] wiki read roundtrip OK — content confirmed")


def run_probe(
    url: str,
    timeout: float,
    fmt: str = "log",
    *,
    post_fn=None,
    verbose: bool = False,
    probe_id: str | None = None,
) -> int:
    """Run one wiki roundtrip probe. Returns exit code (0=green, nonzero=red)."""
    ts = _now_local_iso()
    start = time.monotonic()
    canary_filename = _filename_for_probe_id(probe_id)
    try:
        run_canary(
            url,
            timeout,
            post_fn=post_fn,
            verbose=verbose,
            canary_filename=canary_filename,
        )
    except ToolCanaryError as exc:
        rtt_ms = int((time.monotonic() - start) * 1000)
        _append_log(_format_red(ts, url, exc.code, exc.msg, rtt_ms))
        if fmt == "gha":
            _emit_gha_kv("status", str(exc.code))
            _emit_gha_kv("msg", exc.msg)
        return exc.code
    except Exception as exc:
        rtt_ms = int((time.monotonic() - start) * 1000)
        msg = f"unexpected: {exc!r}"
        _append_log(_format_red(ts, url, 99, msg, rtt_ms))
        if fmt == "gha":
            _emit_gha_kv("status", "99")
            _emit_gha_kv("msg", msg)
        return 99
    rtt_ms = int((time.monotonic() - start) * 1000)
    _append_log(_format_green(ts, url, rtt_ms))
    if fmt == "gha":
        _emit_gha_kv("status", "0")
        _emit_gha_kv("msg", f"OK wiki roundtrip {url} rtt_ms={rtt_ms}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Wiki write-roundtrip uptime canary (P0 surface).",
    )
    ap.add_argument(
        "--url", default=DEFAULT_URL,
        help=f"MCP endpoint URL (default: {DEFAULT_URL})",
    )
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    ap.add_argument(
        "--once", action="store_true",
        help="Run a single probe and exit (default behavior; flag is a no-op).",
    )
    ap.add_argument(
        "--format", dest="fmt", choices=["log", "gha"], default="log",
        help="Output format: 'log' (default) or 'gha' ($GITHUB_OUTPUT).",
    )
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument(
        "--probe-id",
        help=(
            "Optional replay/run id; writes to uptime-probe-<probe-id> "
            "instead of the shared uptime-probe draft."
        ),
    )
    args = ap.parse_args(argv)
    return run_probe(
        args.url,
        args.timeout,
        fmt=args.fmt,
        verbose=args.verbose,
        probe_id=args.probe_id,
    )


if __name__ == "__main__":
    sys.exit(main())
