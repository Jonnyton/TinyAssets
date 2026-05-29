"""read_repo_files: a platform-trusted opaque node that reads repo files into state.

The read counterpart to the github_pull_request write effector. It lets a
user-buildable loop EDIT existing files: a node named ``read_repo_files`` (in the
``workflow`` domain) fetches the current contents of caller-named paths from a
GitHub repository and writes them into run state, so a downstream
``propose_changes`` node can base a correct diff on the real file contents
instead of guessing.

Design note: docs/design-notes/2026-05-29-read-repo-files-primitive.md
(Option A — opaque domain callable; Cowork + Codex review, amendments folded).

Contract (opaque callable — ``fn(state) -> dict`` of state updates):

  reads from state:
    - ``read_destination`` (str): ``owner/repo`` to read from. The user's branch
      supplies this (e.g. a state-schema default); the platform never hardcodes a
      repo.
    - ``target_paths`` (str): repo-relative paths as a JSON array or a comma/
      semicolon list.
  writes to state:
    - ``current_contents_json`` (str): JSON object ``{path: contents|null}``.
      ``null`` means the path does not exist at the ref (a new-file create), NOT
      an error.
    - ``read_status_json`` (str): JSON object with per-path status
      (present|missing|denied|rejected|too_large|truncated|error), a ``_truncated``
      boolean, and an ``_errors`` map of path -> structured ``error_kind``.

Build decisions from review (design note §"Build decisions from review"):
  1. Read scope is SEPARATE from write scope — resolve a read token from
     ``WORKFLOW_GITHUB_READ_CAPABILITIES`` (NOT the write map). When no token is
     configured, fall back to an unauthenticated read, which works for public
     repos (rate-limited). A private repo without a read token returns
     ``denied`` per file rather than silently leaking the write token.
  2. The platform callable (not node config) enforces path safety + size caps.
  3. Missing file -> explicit ``null``.
  4. Distinct per-step ``error_kind``s; per-file status metadata.
  5. Platform-trusted opaque callable — the user references it but cannot supply
     its body.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_READ_CAPABILITIES_ENV = "WORKFLOW_GITHUB_READ_CAPABILITIES"
_READ_TIMEOUT_S = 30.0

_DEFAULT_MAX_FILES = 20
_DEFAULT_MAX_BYTES_PER_FILE = 100_000
_DEFAULT_MAX_TOTAL_BYTES = 400_000

DOMAIN_ID = "workflow"
NODE_ID = "read_repo_files"

_REPO_RE = re.compile(r"[\w.-]+/[\w.-]+")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
    except ValueError:
        return default
    return val if val > 0 else default


def _read_token(destination: str) -> str:
    """Resolve a READ-scoped token for ``destination`` (empty if none).

    Separate from the write capability map by design — a universe may be granted
    read-only without write. Empty string => unauthenticated read (public repos).
    """
    raw = os.environ.get(_READ_CAPABILITIES_ENV, "").strip()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning(
            "%s is set but not valid JSON; treating reads as unauthenticated",
            _READ_CAPABILITIES_ENV,
        )
        return ""
    if not isinstance(parsed, dict):
        return ""
    token = parsed.get(destination, "")
    return token.strip() if isinstance(token, str) else ""


def _parse_paths(raw: object) -> list[str]:
    """Parse target_paths from a JSON array or comma/semicolon list."""
    if isinstance(raw, list):
        items = raw
    else:
        text = str(raw or "").strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                items = parsed if isinstance(parsed, list) else [text]
            except (TypeError, ValueError):
                items = re.split(r"[,;]", text)
        else:
            items = re.split(r"[,;]", text)
    out: list[str] = []
    for it in items:
        s = str(it or "").strip()
        if s:
            out.append(s)
    return out


def _path_rejected(path: str) -> bool:
    """True when a path is unsafe or not a normalized repo-relative path."""
    if not path or path.startswith("/") or "\\" in path or _CONTROL_CHAR_RE.search(path):
        return True
    for part in path.split("/"):
        if part in {"", ".", ".."}:
            return True
        decoded = part
        for _ in range(3):
            unquoted = urllib.parse.unquote(decoded)
            if unquoted == decoded:
                break
            decoded = unquoted
        if (
            decoded in {".", ".."}
            or "/" in decoded
            or "\\" in decoded
            or _CONTROL_CHAR_RE.search(decoded)
        ):
            return True
    return False


def _quote_contents_path(path: str) -> str:
    return urllib.parse.quote(path, safe="/")


def _read_request(
    *, destination: str, path: str, token: str
) -> tuple[dict | None, dict | None]:
    """GET the contents API for one path. Returns ``(parsed, error)``.

    ``error`` is ``{"http_status": int|None, "detail": str}``; a 404 is returned
    as an error here and mapped to ``missing`` (null) by the caller.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "workflow-github-read/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    encoded_path = _quote_contents_path(path)
    req = urllib.request.Request(
        f"{_GITHUB_API}/repos/{destination}/contents/{encoded_path}",
        method="GET",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=_READ_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8")
            return (json.loads(raw) if raw.strip() else {}), None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        return None, {"http_status": exc.code, "detail": detail}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, {"http_status": None, "detail": str(exc)}
    except (TypeError, ValueError) as exc:
        return None, {"http_status": None, "detail": f"parse error: {exc}"}


def read_repo_files(state: dict) -> dict:
    """Opaque-node body: read caller-named repo files into state. Never raises."""
    destination = str(
        state.get("read_destination") or state.get("destination") or ""
    ).strip().strip("/")
    contents: dict[str, object] = {}
    status: dict[str, object] = {}
    errors: dict[str, str] = {}

    def _emit(truncated: bool = False) -> dict:
        status["_truncated"] = truncated
        status["_errors"] = errors
        return {
            "current_contents_json": json.dumps(contents, ensure_ascii=False),
            "read_status_json": json.dumps(status, ensure_ascii=False),
        }

    if not destination or not _REPO_RE.fullmatch(destination):
        errors["_destination"] = "read_destination_invalid"
        return _emit()

    paths = _parse_paths(state.get("target_paths"))
    if not paths:
        errors["_paths"] = "no_target_paths"
        return _emit()

    max_files = _int_env("WORKFLOW_GITHUB_READ_MAX_FILES", _DEFAULT_MAX_FILES)
    max_bytes_file = _int_env(
        "WORKFLOW_GITHUB_READ_MAX_BYTES_PER_FILE", _DEFAULT_MAX_BYTES_PER_FILE
    )
    max_total = _int_env(
        "WORKFLOW_GITHUB_READ_MAX_TOTAL_BYTES", _DEFAULT_MAX_TOTAL_BYTES
    )
    token = _read_token(destination)

    truncated = False
    if len(paths) > max_files:
        truncated = True
        for extra in paths[max_files:]:
            status[extra] = "truncated"
            errors[extra] = "read_truncated"
        paths = paths[:max_files]

    total = 0
    for path in paths:
        if _path_rejected(path):
            status[path] = "rejected"
            errors[path] = "read_path_rejected"
            continue
        parsed, err = _read_request(destination=destination, path=path, token=token)
        if err is not None:
            code = err.get("http_status")
            if code == 404:
                contents[path] = None  # missing => new-file create, not an error
                status[path] = "missing"
            elif code in (401, 403):
                status[path] = "denied"
                errors[path] = "read_contents_denied"
            else:
                status[path] = "error"
                errors[path] = "read_request_failed"
            continue
        node_type = (parsed or {}).get("type")
        if node_type != "file":
            status[path] = "rejected"
            errors[path] = "read_path_rejected"  # dir / symlink / submodule
            continue
        size = (parsed or {}).get("size")
        encoded = (parsed or {}).get("content")
        if (isinstance(size, int) and size > max_bytes_file) or not encoded:
            contents[path] = None
            status[path] = "too_large"
            errors[path] = "read_file_too_large"
            continue
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            status[path] = "error"
            errors[path] = "read_decode_failed"
            continue
        if len(decoded.encode("utf-8")) > max_bytes_file:
            contents[path] = None
            status[path] = "too_large"
            errors[path] = "read_file_too_large"
            continue
        if total + len(decoded.encode("utf-8")) > max_total:
            truncated = True
            status[path] = "truncated"
            errors[path] = "read_truncated"
            continue
        contents[path] = decoded
        status[path] = "present"
        total += len(decoded.encode("utf-8"))

    return _emit(truncated=truncated)


def register_read_repo_files() -> None:
    """Register the read_repo_files opaque callable for the workflow domain.

    Idempotent (register_domain_callable overwrites the same key with a debug
    log). Called from workflow/effectors/__init__.py at import and lazily from
    the compiler's opaque-resolution path so it is always present before a
    branch that uses it compiles.
    """
    from workflow.domain_registry import register_domain_callable

    register_domain_callable(DOMAIN_ID, NODE_ID, read_repo_files)


__all__ = ["read_repo_files", "register_read_repo_files", "DOMAIN_ID", "NODE_ID"]
