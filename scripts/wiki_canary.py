"""Wiki gate + read canary — Layer-1 extension.

Probes the wiki MCP surface anonymously against a dedicated canary draft
(``drafts/notes/uptime-probe.md``). A working ``initialize`` handshake is
necessary but not sufficient: this canary also verifies that:

- ``write_page`` REJECTS an anonymous full-page write with the
  ``status=rejected`` / ``auth_required=true`` envelope. Since the
  server-side anonymous-write gate (#1441) an unauthenticated write
  succeeding is a SECURITY REGRESSION, so silent-accept is red.
- ``read_page`` returns the persisted canary draft content verbatim
  (reads stay open to anonymous callers by design).

History: this was a write-then-read roundtrip via the ``wiki`` fat tool
(BUG-028 class: slug normalization silently broke bug filing while the
handshake stayed green). #1441 gated all anonymous writes AND all
anonymous calls to the deprecated fat tools, so the anonymous roundtrip
is impossible by design. The canary draft content it reads was persisted
by the last pre-gate green run; authenticated write-path coverage is a
tracked follow-up (STATUS.md — canary needs a service credential).

Exit codes
----------
0  — all probe steps passed.
2  — MCP handshake failed (initialize / session).
6  — write gate probe failed (anonymous write ACCEPTED = gate regression,
     isError, or network error).
7  — wiki read failed or canary draft content mismatch.
99 — unexpected error.

Scope: auth-gated deployments only. Production runs
``UNIVERSE_SERVER_AUTH=optional`` (anonymous resolves, writes gated). A
dev-mode server (``UNIVERSE_SERVER_AUTH=false``) leaves anonymous writes
OPEN by design (D1 sign-off), so the gate step reds with exit 6 there —
that red means "server is not auth-gated", not "wiki is down". Don't
point this canary at a dev server and expect green.

Usage
-----
    python scripts/wiki_canary.py
    python scripts/wiki_canary.py --url https://tinyassets.io/mcp --verbose
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
    # Canonical `write_page` full-page write (no old_text/new_text, no kind)
    # so it always hits the anonymous-write gate — never the dry-run patch
    # preview passthrough. dry_run=False is explicit: if the gate ever
    # regressed, the mutation would land on the dedicated canary draft only.
    return {
        "jsonrpc": "2.0",
        "id": call_id,
        "method": "tools/call",
        "params": {
            "name": "write_page",
            "arguments": {
                "filename": filename,
                "category": _CANARY_CATEGORY,
                "content": _CANARY_CONTENT,
                "dry_run": False,
            },
        },
    }


def _wiki_read_payload(call_id: int, *, filename: str = _CANARY_FILENAME) -> dict:
    # Canonical `read_page` takes a single `page=` arg (the slug);
    # _resolve_page locates it across pages/ + drafts/ subdirectories. No
    # `category` / `slug` kwargs — that mismatch was the 2026-04-26 canary
    # RED root cause.
    return {
        "jsonrpc": "2.0",
        "id": call_id,
        "method": "tools/call",
        "params": {
            "name": "read_page",
            "arguments": {
                "page": filename,
            },
        },
    }


def _format_green(ts: str, url: str, rtt_ms: int) -> str:
    return f"{ts} GREEN layer=wiki url={url} surface=wiki_gate rtt_ms={rtt_ms}"


def _format_red(ts: str, url: str, exit_code: int, reason: str, rtt_ms: int) -> str:
    reason_oneline = reason.replace("\n", " ").replace("\r", " ")
    return (
        f"{ts} RED   layer=wiki url={url} exit={exit_code} "
        f"surface=wiki_gate rtt_ms={rtt_ms} reason={reason_oneline!r}"
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
    """Run the wiki gate + read canary.

    ``post_fn`` is injectable for tests (same signature as ``mcp_tool_canary._post``).
    Raises ``ToolCanaryError`` on any failure with the appropriate exit code.

    ``canary_filename`` scopes the WRITE-GATE probe target (bisect replay);
    the READ step always targets the shared ``uptime-probe`` draft because
    scoped drafts were never persisted — anonymous writes are rejected, so
    only the shared draft (persisted pre-gate) exists to read back.
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

    # ---- Step 2: anonymous write-gate probe -------------------------------
    # Anonymous write_page MUST come back with the rejection envelope
    # (status=rejected, auth_required=true). An ACCEPTED anonymous write is
    # a #1441 gate regression — the security failure this step exists to
    # catch. Tool errors / unparseable shapes are red too (write surface
    # itself is broken).
    write_resp, _ = post(
        url,
        sid,
        _wiki_write_payload(2, filename=canary_filename),
        timeout,
        step_code=6,
    )
    if write_resp is None or "result" not in write_resp:
        raise ToolCanaryError(6, f"write_page returned no result: {write_resp!r}")
    write_result = write_resp["result"]
    if write_result.get("isError"):
        text = _extract_tool_text(write_result)[:300]
        raise ToolCanaryError(6, f"write_page isError=true: {text!r}")
    write_obj = _extract_structured_tool_payload(write_result)
    if write_obj is None:
        write_text = _extract_tool_text(write_result)
        if not write_text:
            raise ToolCanaryError(6, f"write_page returned no text content: {write_result!r}")
        try:
            write_obj = json.loads(write_text)
        except json.JSONDecodeError as exc:
            raise ToolCanaryError(
                6, f"write_page text not JSON: {exc}; preview={write_text[:200]!r}"
            ) from exc
    if write_obj.get("status") in ("ok", "written", "drafted", "updated", "filed"):
        raise ToolCanaryError(
            6,
            "anonymous write_page was ACCEPTED — the anonymous-write gate "
            "(#1441) has regressed. (If this is a dev-mode server with "
            "UNIVERSE_SERVER_AUTH=false, anonymous writes are open by design "
            "and this probe does not apply — it targets auth-gated "
            f"deployments.) Response: {write_obj!r}",
        )
    if write_obj.get("status") != "rejected" or not write_obj.get("auth_required"):
        raise ToolCanaryError(
            6,
            "write_page did not return the expected anonymous rejection "
            f"envelope (status=rejected, auth_required=true): {write_obj!r}",
        )
    if verbose:
        print("[wiki-canary] anonymous write-gate OK: rejected with auth_required=true")

    # ---- Step 3: wiki read (persisted canary draft) ------------------------
    # Always read the SHARED draft — scoped bisect filenames were never
    # persisted post-gate (see run_canary docstring).
    read_resp, _ = post(
        url,
        sid,
        _wiki_read_payload(3, filename=_CANARY_FILENAME),
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
            f"wiki read mismatch: persisted canary draft content not found. "
            f"preview={read_text[:300]!r}",
        )
    if verbose:
        print("[wiki-canary] wiki read OK — persisted canary draft content confirmed")


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
        _emit_gha_kv("msg", f"OK wiki gate+read {url} rtt_ms={rtt_ms}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Wiki gate + read uptime canary (P0 surface).",
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
