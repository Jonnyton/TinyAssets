"""Wiki write-roundtrip or gate + read canary — Layer-1 extension.

Probes the wiki MCP surface against the reserved canary draft
(``drafts/notes/uptime-probe.md``). With
``TINYASSETS_WIKI_CANARY_TOKEN`` present, it writes the draft with that scoped
non-OAuth bearer and reads the content back anonymously. Without the token it
keeps the post-#1441 policy assertion:

- ``write_page`` returns the canonical pre-dispatch HTTP 401 with a non-empty
  ``WWW-Authenticate`` OAuth challenge. Any dispatched JSON result (including
  the retired rejection envelope) is red because it cannot launch OAuth.
- ``read_page`` returns the persisted canary draft content verbatim
  (reads stay open to anonymous callers by design).

History: this was originally a write-then-read roundtrip via the ``wiki`` fat
tool (BUG-028 class: slug normalization silently broke bug filing while the
handshake stayed green). #1441 correctly gated anonymous writes. The scoped
service token restores the persisted roundtrip without becoming an OAuth
identity or authorizing any other page or action.

Exit codes
----------
0  — all probe steps passed.
2  — MCP handshake failed (initialize / session).
6  — scoped write or anonymous write-gate probe failed.
7  — wiki read failed or canary draft content mismatch.
99 — unexpected error.

Scope: production uses the scoped token. The no-token fallback is for
auth-gated deployments only: a dev server intentionally leaves anonymous writes
open, so its fallback gate assertion is red.

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
import os
import re
import sys
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError

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
_CANARY_RELATIVE_PATH = "drafts/notes/uptime-probe.md"
_CANARY_TOKEN_ENV = "TINYASSETS_WIKI_CANARY_TOKEN"

_INIT_PAYLOAD = _init_payload("wiki-canary")
_PROBE_ID_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _filename_for_probe_id(probe_id: str | None) -> str:
    if not probe_id:
        return _CANARY_FILENAME
    suffix = _PROBE_ID_SAFE_RE.sub("-", probe_id.strip()).strip("._-")
    if not suffix:
        raise ValueError("probe_id must contain at least one filename-safe character")
    return f"{_CANARY_FILENAME}-{suffix[:80]}"


def _wiki_write_payload(
    call_id: int,
    *,
    filename: str = _CANARY_FILENAME,
    content: str = _CANARY_CONTENT,
) -> dict:
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
                "content": content,
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
        delimiter = f"EOF_{uuid.uuid4().hex}"
        print(f"{key}<<{delimiter}")
        print(value)
        print(delimiter)
    else:
        print(f"{key}={value}")


def _is_oauth_challenge(exc: ToolCanaryError) -> bool:
    """Return whether a write-call HTTP failure is the canonical OAuth gate."""
    cause = exc.__cause__
    if not isinstance(cause, HTTPError) or cause.code != 401:
        return False
    try:
        challenge = cause.headers.get("WWW-Authenticate")
    except Exception:
        return False
    return isinstance(challenge, str) and bool(challenge.strip())


def _fresh_canary_content() -> str:
    """Return a unique marker so each credentialed read proves this write."""
    return f"{_CANARY_CONTENT} run={uuid.uuid4().hex}"


def _validate_write_response(resp: dict | None) -> None:
    """Require a successful write response for the exact reserved path."""
    if resp is None or "result" not in resp:
        raise ToolCanaryError(6, f"wiki write returned no result: {resp!r}")
    result = resp["result"]
    if result.get("isError"):
        text = _extract_tool_text(result)[:300]
        raise ToolCanaryError(6, f"wiki write isError=true: {text!r}")
    obj = _extract_structured_tool_payload(result)
    if obj is None:
        text = _extract_tool_text(result)
        if not text:
            raise ToolCanaryError(6, f"wiki write returned no text content: {result!r}")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ToolCanaryError(
                6,
                f"wiki write text not JSON: {exc}; preview={text[:200]!r}",
            ) from exc
    if not isinstance(obj, dict):
        raise ToolCanaryError(6, f"wiki write JSON was not an object: {obj!r}")
    if (
        obj.get("path") != _CANARY_RELATIVE_PATH
        or obj.get("status") not in {"drafted", "updated"}
    ):
        raise ToolCanaryError(
            6,
            "wiki write did not confirm the reserved path "
            f"{_CANARY_RELATIVE_PATH!r}: {obj!r}",
        )


def run_canary(
    url: str,
    timeout: float,
    *,
    post_fn=None,
    verbose: bool = False,
    canary_filename: str = _CANARY_FILENAME,
    service_token: str | None = None,
    canary_content: str = _CANARY_CONTENT,
) -> None:
    """Run the credentialed roundtrip or anonymous gate + read canary.

    ``post_fn`` is injectable for tests (same signature as ``mcp_tool_canary._post``).
    Raises ``ToolCanaryError`` on any failure with the appropriate exit code.

    ``canary_filename`` scopes only the anonymous WRITE-GATE probe target for
    bisect replay. Credentialed mode refuses any non-reserved filename. The
    READ step always targets the shared ``uptime-probe`` draft.
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

    # ---- Step 2: credentialed write OR anonymous write-gate probe ----------
    if service_token:
        if canary_filename != _CANARY_FILENAME:
            raise ToolCanaryError(
                6,
                "scoped service token can write only the reserved filename "
                f"{_CANARY_FILENAME!r}",
            )
        write_resp, _ = post(
            url,
            sid,
            _wiki_write_payload(2, content=canary_content),
            timeout,
            step_code=6,
            bearer_token=service_token,
        )
        _validate_write_response(write_resp)
        if verbose:
            print("[wiki-canary] scoped write OK - reserved draft confirmed")
    else:
        # Canonical write auth is an HTTP 401 before MCP dispatch. Only the
        # direct HTTPError cause with a usable challenge proves a client can
        # begin OAuth; any returned tool JSON is a protocol regression.
        try:
            post(
                url,
                sid,
                _wiki_write_payload(
                    2,
                    filename=canary_filename,
                    content=canary_content,
                ),
                timeout,
                step_code=6,
            )
        except ToolCanaryError as exc:
            if not _is_oauth_challenge(exc):
                cause = exc.__cause__
                if isinstance(cause, HTTPError) and cause.code == 401:
                    raise ToolCanaryError(
                        6,
                        "write_page HTTP 401 lacks a non-empty WWW-Authenticate "
                        f"challenge: {exc.msg}",
                    ) from exc
                raise
        else:
            raise ToolCanaryError(
                6,
                "write_page returned a dispatched JSON result; expected HTTP 401 "
                "with a non-empty WWW-Authenticate challenge pre-dispatch",
            )
        if verbose:
            print(
                "[wiki-canary] anonymous write-gate OK: HTTP 401 with "
                "WWW-Authenticate present",
            )

    # ---- Step 3: anonymous read of the shared canary draft -----------------
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
    read_path = None
    if read_obj is not None:
        read_path = read_obj.get("path")
        read_text = json.dumps(read_obj, default=str)
    else:
        read_text = _extract_tool_text(read_result)
        if not read_text:
            raise ToolCanaryError(7, f"wiki read returned no text content: {read_result!r}")
        try:
            parsed_read = json.loads(read_text)
        except json.JSONDecodeError:
            parsed_read = None
        if isinstance(parsed_read, dict):
            read_path = parsed_read.get("path")
    if canary_content not in read_text:
        raise ToolCanaryError(
            7,
            f"wiki read mismatch: persisted canary draft content not found. "
            f"preview={read_text[:300]!r}",
        )
    if read_path != _CANARY_RELATIVE_PATH:
        raise ToolCanaryError(
            7,
            "wiki read did not confirm the reserved path "
            f"{_CANARY_RELATIVE_PATH!r}: path={read_path!r}",
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
    service_token = os.environ.get(_CANARY_TOKEN_ENV) or None
    canary_content = _fresh_canary_content() if service_token else _CANARY_CONTENT
    try:
        run_canary(
            url,
            timeout,
            post_fn=post_fn,
            verbose=verbose,
            canary_filename=canary_filename,
            service_token=service_token,
            canary_content=canary_content,
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
        mode = "write+read" if service_token else "gate+read"
        _emit_gha_kv("msg", f"OK wiki {mode} {url} rtt_ms={rtt_ms}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Wiki write-roundtrip or gate + read uptime canary.",
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
            "Optional anonymous-fallback replay id; the scoped-token mode "
            "rejects non-reserved filenames."
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
