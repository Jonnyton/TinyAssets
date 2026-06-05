"""GitHub PR substrate effector — PR-122.

Reads ``external_write_packet`` shapes from a completed run's final state
for any node whose ``effects`` declaration includes
``"github_pull_request"``, and decides whether to fire a real
``gh pr create`` or return dry-run evidence.

Packet shape (convention — documented in
drafts/concepts/external-write-packet-shape.md):

.. code-block:: json

    {
      "sink": "github_pull_request",
      "destination": "Jonnyton/Workflow",       # Phase 2 — required for real writes
      "payload": {
        "title": "...",
        "body":  "...",
        "base_branch": "main",
        "head_branch": "auto/.../...",
        "labels": ["..."],
        "draft": true
      },
      "idempotency_hint": "<optional>",
      "expected_evidence_keys": ["pr_number", "pr_url"]
    }

Authority model (Phase 2)
-------------------------

A real write fires only when ALL THREE gates are open:

1. **Capability token (secrets-vended, daemon-side).** The shared
   auth provider resolves a destination-scoped GitHub ``push``
   credential from ``WORKFLOW_GITHUB_PUSH_CAPABILITIES`` (with
   ``WORKFLOW_GITHUB_PR_CAPABILITIES`` accepted as a legacy fallback)
   and returns the token to this effector at invocation time. The
   token is never echoed into branch-visible state.

2. **Per-destination consent grant.** A row in the per-universe
   ``effector_consents`` table with ``(sink, destination, revoked_at
   IS NULL)`` matching the packet exactly. The chatbot composes the
   ``extensions action=grant_effector_consent`` call; the daemon
   records the grant.

3. **Idempotency receipt — atomic reservation.** Round-2 fix for
   Codex P1.1: round-1's lookup → invoke → write sequence was
   non-atomic; two concurrent run threads could both observe "no
   receipt" and both invoke ``gh pr create``. Round-2 uses the
   ``try_reserve_receipt`` / ``finalize_receipt`` pair from
   ``workflow.storage.external_write_receipts`` — the reservation is
   atomic via SQLite's row-level lock, so a concurrent thread sees
   either ``duplicate`` (a terminal-succeeded row exists; dedup-hit)
   or ``in_flight`` (another worker has the pending reservation;
   this run dry-runs with ``reason=concurrent_in_flight``).
   ``database is locked`` errors are NOT silently treated as a miss
   — they surface as ``error_kind=receipt_store_locked`` evidence.

If any gate is closed AND the packet supplied a ``destination``, the
effector returns Phase-2-shaped dry-run evidence naming the closed
gate. If the packet has no ``destination`` (Phase 1 backward compat),
the effector returns Phase-1 dry-run evidence unchanged.

Errors are captured and returned in the evidence map; the function
never raises to the run-completion path. Hard-rule #8 (fail loudly) is
satisfied by structured ``error`` fields in the per-node evidence.

Design source: ``drafts/concepts/external-write-phase-2-authority.md``.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from workflow.auth.provider import vend_github_destination_secret
from workflow.effectors.authority import (
    DENIED as SOUL_AUTHORITY_DENIED,
)
from workflow.effectors.authority import (
    effect_authority_key,
    resolve_soul_effect_authority,
)

logger = logging.getLogger(__name__)


EXTERNAL_WRITE_SINK_GITHUB_PR = "github_pull_request"
_ENABLE_ENV = "WORKFLOW_EXTERNAL_WRITE_ENABLED"
# Round-3 P1 fix (Codex round-2 verdict on PR #969): this env is the
# **operator panic-button kill switch**. When truthy, the effector
# ALWAYS returns dry-run evidence regardless of capability / consent /
# idempotency-reservation state. The host can flip it on a live
# daemon to disable all real writes without going through consent
# revocation. Round-2 erroneously left this env recognized-but-ignored;
# Codex caught the documentation/behavior drift and asked for it to be
# restored as a documented override. Implementation:
# :func:`run_github_pr_effector` checks it before any gate, including
# Phase-1 backward-compat packets.
_DRY_RUN_ENV = "WORKFLOW_EXTERNAL_WRITE_DRY_RUN"
# GitHub write credentials now come through the shared auth/secrets
# provider as a destination-keyed ``push`` capability. The new canonical
# env map is ``WORKFLOW_GITHUB_PUSH_CAPABILITIES``; we still accept the
# older PR-specific map as a fallback so existing hosts keep working
# while they migrate.
_PUSH_CAPABILITIES_ENV = "WORKFLOW_GITHUB_PUSH_CAPABILITIES"
_LEGACY_CAPABILITIES_ENV = "WORKFLOW_GITHUB_PR_CAPABILITIES"
_GH_PR_TIMEOUT_S = 60.0
_GITHUB_API = "https://api.github.com"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_truthy(name: str) -> bool:
    val = os.environ.get(name, "")
    return val.strip().lower() in _TRUTHY


def _phase_1_mode() -> str:
    """Return the Phase 1 dry-run mode label for evidence records.

    Preserved verbatim from Phase 1 round 3 for backward compat. When
    a packet supplies no ``destination`` we still emit the Phase-1
    shape so existing Phase-1 dry-run consumers see no behavior change.
    """
    return "dry_run_phase_1" if _env_truthy(_ENABLE_ENV) else "dry_run_default"


def _parse_packet(value: Any) -> dict[str, Any] | None:
    """Parse an output value into an external_write_packet dict."""
    if isinstance(value, dict):
        packet = value
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped or not stripped.startswith("{"):
            return None
        try:
            packet = json.loads(stripped)
        except (ValueError, TypeError):
            return None
        if not isinstance(packet, dict):
            return None
    else:
        return None
    if "sink" not in packet:
        return None
    return packet


def _read_capability(destination: str) -> str:
    """Return the vendored GitHub push token for ``destination``.

    The shared auth provider resolves the destination-scoped credential
    and may fall back to the legacy PR-capability map during migration.
    The token is never echoed into branch-visible state or returned
    evidence.
    """
    if not destination:
        return ""
    vendored = vend_github_destination_secret(
        destination=destination,
        capability="push",
    )
    token = vendored.get("token")
    if not isinstance(token, str):
        return ""
    return token.strip()


def _resolve_universe_dir(base_path: str | Path | None) -> Path | None:
    """Return the per-universe directory or None.

    When the run completion path supplies ``base_path``, it's already
    the universe directory. When called without context (Phase 1
    backward-compat invocations from tests), we have no universe to
    bind to and the storage gates return their "not configured" answer.
    """
    if base_path is None:
        return None
    try:
        return Path(base_path)
    except (TypeError, ValueError):
        return None


def _check_consent(
    universe_dir: Path | None, destination: str,
) -> bool:
    """Return True iff an active consent row matches the destination."""
    if universe_dir is None or not destination:
        return False
    try:
        from workflow.storage.effector_consents import is_consent_active
    except Exception:  # pragma: no cover — defensive import guard
        logger.exception("failed to import effector_consents")
        return False
    try:
        return is_consent_active(
            universe_dir,
            sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
            destination=destination,
        )
    except Exception:  # pragma: no cover — gate failure is dry-run-safe
        logger.exception("consent lookup crashed for %s", destination)
        return False


def _is_lock_error(exc: BaseException) -> bool:
    """True iff ``exc`` looks like a SQLite "database is locked" class.

    SQLite raises :class:`sqlite3.OperationalError` for several
    distinct conditions (locked, busy, disk full, malformed schema).
    Round-2 P1.1 contract: locked/busy means "another writer is
    holding the file; we MUST NOT silently treat this as a miss." We
    surface it as a structured ``receipt_store_locked`` evidence record
    so the caller sees the lock state explicitly rather than firing a
    duplicate side-effect.

    Other ``OperationalError`` variants (disk full, malformed schema)
    also fall under "fail loudly" — we surface them the same way.
    """
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("locked", "busy", "deadlock", "timeout")
    )


def _try_reserve(
    universe_dir: Path | None,
    *,
    idempotency_hint: str,
    run_id: str,
) -> dict[str, Any]:
    """Atomically reserve a receipt slot, or report the collision shape.

    Returns the storage helper's verbatim payload (see
    :func:`workflow.storage.external_write_receipts.try_reserve_receipt`),
    or an ``{"status": "no_hint"}`` shape when the packet didn't supply
    a hint. Raises :class:`sqlite3.OperationalError` on lock timeout
    — the caller must surface it as a structured error rather than
    treating it as a miss.
    """
    if universe_dir is None or not idempotency_hint:
        return {"status": "no_hint"}
    from workflow.storage.external_write_receipts import try_reserve_receipt
    return try_reserve_receipt(
        universe_dir,
        idempotency_hint=idempotency_hint,
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id=run_id or "",
    )


def _finalize_receipt(
    universe_dir: Path | None,
    *,
    idempotency_hint: str,
    evidence: dict[str, Any],
    run_id: str,
) -> bool:
    """Mark the reserved row as ``succeeded`` with final evidence.

    Returns True when the update landed. Receipt finalization is
    best-effort AFTER the side-effect already ran — a crash here must
    NOT mask the successful PR. We log loudly per hard rule #8 and
    return False so the caller can include a ``receipt_finalize_failed``
    flag in the evidence for the operator.
    """
    if universe_dir is None or not idempotency_hint:
        return False
    try:
        from workflow.storage.external_write_receipts import finalize_receipt
        return finalize_receipt(
            universe_dir,
            idempotency_hint=idempotency_hint,
            sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
            evidence=evidence,
            run_id=run_id or "",
        )
    except Exception:
        logger.exception(
            "failed to finalize receipt for %s/%s",
            idempotency_hint, EXTERNAL_WRITE_SINK_GITHUB_PR,
        )
        return False


def _release_reservation(
    universe_dir: Path | None,
    *,
    idempotency_hint: str,
    run_id: str,
) -> None:
    """Mark a reserved row ``failed`` so a retry can re-reserve.

    Called after ``gh pr create`` returned an error. Best-effort —
    failure to release means the next retry under the same hint has
    to wait for the stale-pending threshold (default 10 min) before
    re-acquiring. Log loudly so the operator can spot stuck rows.
    """
    if universe_dir is None or not idempotency_hint:
        return
    try:
        from workflow.storage.external_write_receipts import (
            release_reservation,
        )
        release_reservation(
            universe_dir,
            idempotency_hint=idempotency_hint,
            sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
            run_id=run_id or "",
            mark_failed=True,
        )
    except Exception:
        logger.exception(
            "failed to release reservation for %s/%s",
            idempotency_hint, EXTERNAL_WRITE_SINK_GITHUB_PR,
        )


# ---------------------------------------------------------------------------
# Real-write invocation
# ---------------------------------------------------------------------------


_PR_URL_RE = re.compile(r"(https://github\.com/[\w.\-/]+/pull/(\d+))")


def _extract_pr_url_and_number(stdout: str) -> tuple[str, int | None]:
    """Pull the PR URL + number out of ``gh pr create`` stdout.

    ``gh pr create`` prints the URL as the last non-empty line on
    success. Be defensive: scan for any github.com/.../pull/N URL.
    """
    match = None
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        m = _PR_URL_RE.search(line)
        if m:
            match = m
            break
    if match is None:
        m = _PR_URL_RE.search(stdout)
        if m:
            match = m
    if match is None:
        return "", None
    url = match.group(1)
    try:
        number = int(match.group(2))
    except (TypeError, ValueError):
        number = None
    return url, number


def _validate_payload(payload: Any) -> str:
    """Return an error message if the payload is invalid; "" if OK."""
    if not isinstance(payload, dict):
        return "packet.payload must be a JSON object"
    title = payload.get("title", "")
    if not isinstance(title, str) or not title.strip():
        return "packet.payload.title is required and must be non-empty after strip"
    body = payload.get("body", "")
    if not isinstance(body, str):
        return "packet.payload.body must be a string (may be empty)"
    labels = payload.get("labels", [])
    if labels is not None and not isinstance(labels, list):
        return "packet.payload.labels must be a list of strings"
    if isinstance(labels, list) and not all(isinstance(x, str) for x in labels):
        return "packet.payload.labels must contain only strings"
    return ""


def _invoke_gh_pr_create(
    *,
    payload: dict[str, Any],
    destination: str,
    capability_token: str,
) -> dict[str, Any]:
    """Invoke ``gh pr create`` and return parsed evidence.

    Returns either a success record ``{"pr_url": ..., "pr_number": ...,
    "stdout": ...}`` or an error record
    ``{"error": ..., "error_kind": ...}``. Never raises.

    ``destination`` is passed via ``--repo`` so the call doesn't depend
    on the daemon's cwd being inside a clone of the target repo.
    """
    err = _validate_payload(payload)
    if err:
        return {"error": err, "error_kind": "invalid_payload"}

    title = payload["title"].strip()
    body = payload.get("body", "") or ""
    base_branch = payload.get("base_branch") or "main"
    head_branch = payload.get("head_branch") or ""
    labels = payload.get("labels") or []
    draft = bool(payload.get("draft", True))

    cmd: list[str] = [
        "gh", "pr", "create",
        "--repo", destination,
        "--title", title,
        "--body", body,
        "--base", base_branch,
    ]
    if head_branch:
        cmd.extend(["--head", head_branch])
    if draft:
        cmd.append("--draft")
    for label in labels:
        if isinstance(label, str) and label:
            cmd.extend(["--label", label])

    try:
        env = os.environ.copy()
        env["GH_TOKEN"] = capability_token
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_GH_PR_TIMEOUT_S,
            check=False,
            env=env,
        )
    except FileNotFoundError:
        return _invoke_github_api_pr_create(
            payload=payload,
            destination=destination,
            capability_token=capability_token,
        )
    except subprocess.TimeoutExpired:
        return {
            "error": f"gh pr create exceeded {_GH_PR_TIMEOUT_S}s timeout",
            "error_kind": "gh_invocation_failed",
        }
    except OSError as exc:
        return {
            "error": f"gh pr create OS error: {exc}",
            "error_kind": "gh_invocation_failed",
        }

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    if proc.returncode != 0:
        return {
            "error": (
                f"gh pr create exit {proc.returncode}: "
                f"{stderr.strip() or stdout.strip() or '(no output)'}"
            ),
            "error_kind": "gh_nonzero_exit",
            "stdout": stdout,
            "stderr": stderr,
        }

    pr_url, pr_number = _extract_pr_url_and_number(stdout)
    if not pr_url:
        return {
            "error": (
                "gh pr create returned zero exit but no parseable "
                "github.com/.../pull/N URL in stdout"
            ),
            "error_kind": "gh_nonzero_exit",
            "stdout": stdout,
            "stderr": stderr,
        }

    return {
        "pr_url": pr_url,
        "pr_number": pr_number,
        "invocation_mode": "gh",
        "stdout": stdout,
    }


def _github_api_request(
    *,
    path: str,
    capability_token: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{_GITHUB_API}{path}",
        data=data,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {capability_token}",
            "Content-Type": "application/json",
            "User-Agent": "workflow-github-pr-effector/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=_GH_PR_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _git_data_api(
    *,
    method: str,
    path: str,
    capability_token: str,
    body: dict[str, Any] | None = None,
) -> tuple[Any, dict[str, Any] | None]:
    """Call the GitHub Git Data / REST API. Returns ``(parsed, error)``.

    On success ``error`` is ``None`` and ``parsed`` is the decoded JSON
    (``{}`` for empty bodies). On failure ``parsed`` is ``None`` and
    ``error`` is ``{"http_status": int|None, "detail": str}`` so the
    caller can map it to a step-specific ``error_kind`` (BUG-111 review
    constraint 3: never collapse the materialize path into a single
    ``gh_nonzero_exit``). A 401/403/404 on a write step signals a token
    scope problem (constraint 1: Contents write must be present).
    """
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{_GITHUB_API}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {capability_token}",
            "Content-Type": "application/json",
            "User-Agent": "workflow-github-pr-effector/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_GH_PR_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8")
            return (json.loads(raw) if raw.strip() else {}), None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        return None, {"http_status": exc.code, "detail": detail}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, {"http_status": None, "detail": str(exc)}
    except (TypeError, ValueError) as exc:
        return None, {"http_status": None, "detail": f"parse error: {exc}"}


def _scope_or(error: dict[str, Any], step_kind: str) -> str:
    """Pick a step error_kind, upgrading auth/scope failures distinctly.

    BUG-111 review constraint 1: a 401/403/404 from a Git-Data write step
    is a capability/scope problem (the token lacks Contents write), not a
    generic step failure — surface it as ``github_contents_write_denied``
    so triage points the host at the token scope, not the code.
    """
    if (error or {}).get("http_status") in (401, 403, 404):
        return "github_contents_write_denied"
    return step_kind


_MAX_EDIT_BLOCKS_PER_FILE = 100


def _fetch_file_at_ref(
    *, owner_repo: str, path: str, ref: str, capability_token: str
) -> tuple[str | None, dict[str, Any] | None]:
    """Fetch a file's decoded text at ``ref`` via the Contents API.

    Returns ``(contents, None)`` on success or ``(None, error)`` where error is
    the ``_git_data_api`` error dict. A 404 means the path does not exist at the
    ref — edits cannot anchor on a missing file, so the caller maps that to
    ``edit_target_missing``.
    """
    encoded = urllib.parse.quote(path, safe="/")
    encoded_ref = urllib.parse.quote(ref, safe="")
    obj, err = _git_data_api(
        method="GET",
        path=f"/repos/{owner_repo}/contents/{encoded}?ref={encoded_ref}",
        capability_token=capability_token,
    )
    if err is not None:
        return None, err
    if not isinstance(obj, dict) or obj.get("type") != "file":
        return None, {"http_status": None, "detail": "path is not a file"}
    encoded_content = obj.get("content")
    if not isinstance(encoded_content, str) or not encoded_content:
        # Files >1MB return no inline content via the Contents API.
        return None, {"http_status": None, "detail": "no inline content (file too large?)"}
    try:
        return base64.b64decode(encoded_content).decode("utf-8"), None
    except (ValueError, UnicodeDecodeError) as exc:
        return None, {"http_status": None, "detail": f"decode failed: {exc}"}


def _apply_edit_blocks(
    contents: str, blocks: Any
) -> tuple[str | None, dict[str, Any] | None]:
    """Apply ordered search/replace blocks to ``contents`` (exact, unique).

    Each block is ``{"search": <str>, "replace": <str>}``. The ``search`` text
    must occur EXACTLY ONCE in the current contents (anchoring on real fetched
    text — read_repo_files gives the model that text). Zero matches or multiple
    matches fail closed so a bad edit never produces a corrupt commit. Blocks
    apply in order; a later block sees the result of earlier ones.
    """
    def _bad(kind: str, detail: str):
        return None, {"error_kind": kind, "detail": detail}

    if not isinstance(blocks, list) or not blocks:
        return _bad("invalid_edits", "edits must be a non-empty list of blocks")
    if len(blocks) > _MAX_EDIT_BLOCKS_PER_FILE:
        return _bad("invalid_edits", f"too many edit blocks (>{_MAX_EDIT_BLOCKS_PER_FILE})")
    out = contents
    for i, block in enumerate(blocks):
        if not isinstance(block, dict):
            return _bad("invalid_edits", f"block {i} is not an object")
        search = block.get("search")
        replace = block.get("replace")
        if not isinstance(search, str) or not search:
            return _bad("invalid_edits", f"block {i} has empty/non-string search")
        if not isinstance(replace, str):
            return _bad("invalid_edits", f"block {i} has non-string replace")
        count = out.count(search)
        if count == 0:
            return _bad("edit_search_not_found", f"block {i} search text not found")
        if count > 1:
            return _bad(
                "edit_search_not_unique",
                f"block {i} search matches {count}x (must be unique; add context)",
            )
        out = out.replace(search, replace, 1)
    return out, None


def _resolve_edits(
    *, edits_json: Any, destination: str, base_branch: str, capability_token: str
) -> tuple[dict[str, str], dict[str, Any] | None]:
    """Resolve ``edits_json`` ({path: [blocks]}) to ``{path: full_new_contents}``.

    Fetches each target file at ``base_branch`` and applies its blocks. Returns
    ``(resolved, None)`` or ``({}, error)`` with a distinct ``error_kind``. This
    is the large-file path: the model emits only the changed hunks, never the
    whole file, so it cannot truncate a big file into placeholders.
    """
    if not isinstance(edits_json, dict) or not edits_json:
        return {}, {"error": "edits_json must be a non-empty object", "error_kind": "invalid_edits"}
    resolved: dict[str, str] = {}
    for path_key, blocks in edits_json.items():
        if not isinstance(path_key, str) or not path_key.strip():
            return {}, {
                "error": "edits_json keys must be non-empty path strings",
                "error_kind": "invalid_edits",
            }
        current, err = _fetch_file_at_ref(
            owner_repo=destination, path=path_key, ref=base_branch,
            capability_token=capability_token,
        )
        if err is not None:
            if err.get("http_status") == 404:
                return {}, {
                    "error": (
                        f"edit target {path_key!r} does not exist at {base_branch} "
                        "(cannot edit a missing file; use changes_json to create it)"
                    ),
                    "error_kind": "edit_target_missing",
                }
            return {}, {
                "error": f"could not fetch {path_key!r} to apply edits: {err.get('detail')}",
                "error_kind": _scope_or(err, "edit_fetch_failed"),
            }
        new_contents, edit_err = _apply_edit_blocks(current, blocks)
        if edit_err is not None:
            return {}, {
                "error": f"edits for {path_key!r}: {edit_err['detail']}",
                "error_kind": edit_err["error_kind"],
            }
        resolved[path_key] = new_contents
    return resolved, None


# Plugin-mirror parity. The repo keeps a generated copy of the live ``workflow/``
# package at ``packaging/claude-plugin/.../runtime/workflow/`` (build_plugin.py is
# the generator) and CI rejects any commit where the two drift. A loop/effector
# PR only names the canonical file, so the effector mirrors each changed
# ``workflow/`` path to its runtime copy — otherwise every such PR fails the
# mirror-parity gate and needs a manual ``build_plugin.py`` sync.
_PLUGIN_MIRROR_PREFIX = (
    "packaging/claude-plugin/plugins/workflow-universe-server/runtime/"
)
_MIRRORED_SOURCE_ROOT = "workflow/"
# Match build_plugin.py's _TREE_EXCLUDES so we never stage a mirror file the
# generator would not produce (which would itself break parity).
_MIRROR_EXCLUDE_SUFFIXES = (".db", ".db-journal", ".log", ".pyc", ".tmp")
_MIRROR_EXCLUDE_PARTS = ("__pycache__", ".pytest_cache")


def _mirror_path_for(path: str) -> str | None:
    """Return the plugin-runtime mirror path for a canonical ``workflow/`` path.

    None when the path is outside ``workflow/`` (not mirrored) or matches a
    build_plugin.py exclude (so we don't add a file the generator omits).
    """
    if not path.startswith(_MIRRORED_SOURCE_ROOT):
        return None
    if any(path.endswith(suffix) for suffix in _MIRROR_EXCLUDE_SUFFIXES):
        return None
    if any(part in _MIRROR_EXCLUDE_PARTS for part in path.split("/")):
        return None
    return _PLUGIN_MIRROR_PREFIX + path


def _materialize_branch(
    *,
    changes_json: Any,
    destination: str,
    base_branch: str,
    head_branch: str,
    commit_message: str,
    capability_token: str,
    edits_json: Any = None,
) -> dict[str, Any]:
    """Build a remote head branch from ``changes_json`` via the Git Data API.

    BUG-111: the effector previously called ``gh pr create`` against a
    head branch nothing ever created, so GitHub rejected with "No commits
    between base and head". This builds the branch entirely through the
    GitHub Git Data API (blobs → tree → commit → ref) using the same
    capability token — no ``git`` binary, no local clone, no second
    credential (design note 2026-05-29, Option B; Codex checker key on
    PR #1144).

    ``changes_json`` is ``{path: full-new-contents}``; a value of ``None``
    deletes that path (tree entry sha=null). Returns ``{}`` on success
    (branch ready) or ``{"error": ..., "error_kind": ...}`` on failure.
    Every step has a distinct ``error_kind`` (constraint 3). Never raises.
    """
    owner_repo = destination.strip().strip("/")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", owner_repo):
        return {
            "error": f"invalid GitHub repository destination: {destination!r}",
            "error_kind": "invalid_destination",
        }
    if not head_branch:
        return {
            "error": "packet.payload.head_branch is required to materialize a branch",
            "error_kind": "missing_head_branch",
        }

    # Build the effective {path: full-new-contents|None} map from two sources:
    #   - changes_json: full-file replacements / creates / deletes (null).
    #   - edits_json:   {path: [search/replace blocks]} resolved server-side
    #                   against the file fetched at base_branch — the large-file
    #                   path, so the model never has to re-emit a whole big file.
    effective: dict[str, Any] = {}
    if changes_json is not None:
        if not isinstance(changes_json, dict):
            return {
                "error": "packet.payload.changes_json must be an object or omitted",
                "error_kind": "invalid_changes",
            }
        for path_key, contents in changes_json.items():
            if not isinstance(path_key, str) or not path_key.strip():
                return {
                    "error": "changes_json keys must be non-empty repo-relative path strings",
                    "error_kind": "invalid_changes",
                }
            if contents is not None and not isinstance(contents, str):
                return {
                    "error": f"changes_json[{path_key!r}] must be a string or null (delete)",
                    "error_kind": "invalid_changes",
                }
            effective[path_key] = contents
    if edits_json is not None:
        resolved, edit_err = _resolve_edits(
            edits_json=edits_json,
            destination=owner_repo,
            base_branch=base_branch,
            capability_token=capability_token,
        )
        if edit_err is not None:
            return edit_err
        for path_key, contents in resolved.items():
            if path_key in effective:
                return {
                    "error": (
                        f"{path_key!r} appears in both changes_json and "
                        "edits_json — supply only one per path"
                    ),
                    "error_kind": "invalid_edits",
                }
            effective[path_key] = contents
    if not effective:
        # Constraint: no silent empty-branch PR. A real-write packet must carry
        # the change set in changes_json (full files) and/or edits_json
        # (search/replace blocks); failing loudly beats opening an empty PR.
        return {
            "error": (
                "packet.payload must carry changes_json (object mapping "
                "repo-relative paths to full new file contents, null to delete) "
                "and/or edits_json (object mapping paths to a list of "
                "{search, replace} blocks)"
            ),
            "error_kind": "missing_changes",
        }

    # Plugin-mirror parity: mirror every changed canonical ``workflow/`` path to
    # its generated runtime copy so the commit keeps canonical+mirror in sync and
    # passes the mirror-parity CI gate. A path already named in the packet (an
    # explicit mirror edit) is never overwritten. Deletes (None) mirror as
    # deletes. Iterate a snapshot since we mutate ``effective``.
    for path_key in list(effective.keys()):
        mirror_key = _mirror_path_for(path_key)
        if mirror_key is not None and mirror_key not in effective:
            effective[mirror_key] = effective[path_key]

    # Step 1: base ref → base commit sha.
    ref_obj, err = _git_data_api(
        method="GET",
        path=f"/repos/{owner_repo}/git/ref/heads/{base_branch}",
        capability_token=capability_token,
    )
    if err is not None:
        return {
            "error": f"base ref lookup failed for heads/{base_branch}: {err['detail']}",
            "error_kind": _scope_or(err, "base_ref_lookup_failed"),
        }
    base_commit_sha = ((ref_obj or {}).get("object") or {}).get("sha")
    if not isinstance(base_commit_sha, str) or not base_commit_sha:
        return {
            "error": f"base ref heads/{base_branch} returned no commit sha",
            "error_kind": "base_ref_lookup_failed",
        }

    # Step 2: base commit → base tree sha (review correction: the ref
    # gives a COMMIT sha, not a tree sha; a commit lookup is required).
    commit_obj, err = _git_data_api(
        method="GET",
        path=f"/repos/{owner_repo}/git/commits/{base_commit_sha}",
        capability_token=capability_token,
    )
    if err is not None:
        return {
            "error": f"base commit lookup failed for {base_commit_sha}: {err['detail']}",
            "error_kind": _scope_or(err, "base_commit_lookup_failed"),
        }
    base_tree_sha = ((commit_obj or {}).get("tree") or {}).get("sha")
    if not isinstance(base_tree_sha, str) or not base_tree_sha:
        return {
            "error": f"base commit {base_commit_sha} returned no tree sha",
            "error_kind": "base_commit_lookup_failed",
        }

    # Step 3: one blob per modified/created path (deletions carry no blob).
    tree_entries: list[dict[str, Any]] = []
    for path_key, contents in effective.items():
        if contents is None:
            tree_entries.append(
                {"path": path_key, "mode": "100644", "type": "blob", "sha": None}
            )
            continue
        blob, err = _git_data_api(
            method="POST",
            path=f"/repos/{owner_repo}/git/blobs",
            capability_token=capability_token,
            body={"content": contents, "encoding": "utf-8"},
        )
        if err is not None:
            return {
                "error": f"blob create failed for {path_key}: {err['detail']}",
                "error_kind": _scope_or(err, "blob_create_failed"),
            }
        blob_sha = (blob or {}).get("sha")
        if not isinstance(blob_sha, str) or not blob_sha:
            return {
                "error": f"blob create for {path_key} returned no sha",
                "error_kind": "blob_create_failed",
            }
        tree_entries.append(
            {"path": path_key, "mode": "100644", "type": "blob", "sha": blob_sha}
        )

    # Step 4: new tree on top of the base tree.
    tree, err = _git_data_api(
        method="POST",
        path=f"/repos/{owner_repo}/git/trees",
        capability_token=capability_token,
        body={"base_tree": base_tree_sha, "tree": tree_entries},
    )
    if err is not None:
        return {
            "error": f"tree create failed: {err['detail']}",
            "error_kind": _scope_or(err, "tree_create_failed"),
        }
    new_tree_sha = (tree or {}).get("sha")
    if not isinstance(new_tree_sha, str) or not new_tree_sha:
        return {"error": "tree create returned no sha", "error_kind": "tree_create_failed"}

    # Step 5: commit pointing at the new tree, parented on the base commit.
    commit, err = _git_data_api(
        method="POST",
        path=f"/repos/{owner_repo}/git/commits",
        capability_token=capability_token,
        body={
            "message": commit_message,
            "tree": new_tree_sha,
            "parents": [base_commit_sha],
        },
    )
    if err is not None:
        return {
            "error": f"commit create failed: {err['detail']}",
            "error_kind": _scope_or(err, "commit_create_failed"),
        }
    new_commit_sha = (commit or {}).get("sha")
    if not isinstance(new_commit_sha, str) or not new_commit_sha:
        return {
            "error": "commit create returned no sha",
            "error_kind": "commit_create_failed",
        }

    # Step 6: create refs/heads/<head_branch>. If it already exists, this
    # is a retry — reuse ONLY when the existing branch points at a commit
    # whose tree matches what we just built (same materialized content);
    # otherwise fail closed rather than clobber another writer's branch
    # (review constraint 2).
    _ref, err = _git_data_api(
        method="POST",
        path=f"/repos/{owner_repo}/git/refs",
        capability_token=capability_token,
        body={"ref": f"refs/heads/{head_branch}", "sha": new_commit_sha},
    )
    if err is None:
        return {
            "materialized": True,
            "head_branch": head_branch,
            "commit_sha": new_commit_sha,
            "tree_sha": new_tree_sha,
        }
    if err.get("http_status") != 422:
        return {
            "error": f"ref create failed for refs/heads/{head_branch}: {err['detail']}",
            "error_kind": _scope_or(err, "ref_create_failed"),
        }

    # 422 → reference already exists. Inspect it for idempotent reuse.
    existing_ref, lookup_err = _git_data_api(
        method="GET",
        path=f"/repos/{owner_repo}/git/ref/heads/{head_branch}",
        capability_token=capability_token,
    )
    if lookup_err is not None:
        return {
            "error": (
                f"head ref refs/heads/{head_branch} already exists but could "
                f"not be inspected: {lookup_err['detail']}"
            ),
            "error_kind": "head_ref_conflict",
        }
    existing_commit_sha = ((existing_ref or {}).get("object") or {}).get("sha")
    existing_tree_sha = None
    if isinstance(existing_commit_sha, str) and existing_commit_sha:
        existing_commit, _e = _git_data_api(
            method="GET",
            path=f"/repos/{owner_repo}/git/commits/{existing_commit_sha}",
            capability_token=capability_token,
        )
        existing_tree_sha = ((existing_commit or {}).get("tree") or {}).get("sha")
    if existing_tree_sha == new_tree_sha:
        # Same materialized content already on the branch — idempotent
        # retry, safe to proceed to PR creation against it.
        return {
            "materialized": True,
            "head_branch": head_branch,
            "commit_sha": existing_commit_sha,
            "tree_sha": new_tree_sha,
            "head_ref_reused": True,
        }
    return {
        "error": (
            f"head ref refs/heads/{head_branch} already exists with different "
            f"content (existing tree {existing_tree_sha}, wanted {new_tree_sha}); "
            "refusing to force-update"
        ),
        "error_kind": "head_ref_conflict",
    }


def _invoke_github_api_pr_create(
    *,
    payload: dict[str, Any],
    destination: str,
    capability_token: str,
) -> dict[str, Any]:
    """Create a PR through GitHub's REST API when ``gh`` is unavailable."""
    owner_repo = destination.strip().strip("/")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", owner_repo):
        return {
            "error": f"invalid GitHub repository destination: {destination!r}",
            "error_kind": "invalid_destination",
        }

    title = payload["title"].strip()
    body = payload.get("body", "") or ""
    base_branch = payload.get("base_branch") or "main"
    head_branch = payload.get("head_branch") or ""
    labels = payload.get("labels") or []
    draft = bool(payload.get("draft", True))

    request_body = {
        "title": title,
        "body": body,
        "base": base_branch,
        "draft": draft,
    }
    if head_branch:
        request_body["head"] = head_branch

    try:
        created = _github_api_request(
            path=f"/repos/{owner_repo}/pulls",
            capability_token=capability_token,
            body=request_body,
        )
        pr_url = created.get("html_url") if isinstance(created, dict) else ""
        pr_number = created.get("number") if isinstance(created, dict) else None
        if not isinstance(pr_url, str) or not pr_url:
            return {
                "error": "GitHub API created PR response did not include html_url",
                "error_kind": "github_api_error",
            }
        if not isinstance(pr_number, int):
            pr_number = None
        label_error = ""
        if labels and pr_number is not None:
            try:
                _github_api_request(
                    path=f"/repos/{owner_repo}/issues/{pr_number}/labels",
                    capability_token=capability_token,
                    body={"labels": labels},
                )
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
                OSError,
                TypeError,
                ValueError,
            ) as exc:
                label_error = str(exc)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        return {
            "error": f"GitHub API HTTP {exc.code}: {detail}",
            "error_kind": "github_api_error",
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "error": f"GitHub API request failed: {exc}",
            "error_kind": "github_api_error",
        }
    except (TypeError, ValueError) as exc:
        return {
            "error": f"GitHub API response could not be parsed: {exc}",
            "error_kind": "github_api_error",
        }

    result: dict[str, Any] = {
        "pr_url": pr_url,
        "pr_number": pr_number,
        "invocation_mode": "github_api",
    }
    if label_error:
        result["label_error"] = label_error
    return result


# ---------------------------------------------------------------------------
# Main effector
# ---------------------------------------------------------------------------


def run_github_pr_effector(
    *,
    node_id: str,
    output_keys: list[str],
    run_state: dict[str, Any],
    base_path: str | Path | None = None,
    run_id: str = "",
    dry_run: bool = True,  # retained for signature compat — ignored
) -> dict[str, Any]:
    """Run the GitHub-PR effector for a single node.

    Phase 2 Slice 1 — gate-orchestrated. Returns one of:

    - ``{"dry_run": True, "phase": "phase_1", ...}`` when the packet
      has no ``destination`` field (Phase 1 backward compat — packets
      that pre-date Phase 2 still get the Phase-1 dry-run shape).
    - ``{"dry_run": True, "phase": "phase_2", "reason":
      "missing_capability"|"missing_consent", "destination": ...}``
      when the packet supplied ``destination`` but a gate is closed.
    - ``{"idempotency_dedup_hit": True, "phase": "phase_2",
      "evidence": <recorded>, "matched_output_key": ...}`` when a
      receipt already exists for ``(idempotency_hint, sink)``.
    - ``{"pr_url": ..., "pr_number": ..., "phase": "phase_2",
      "matched_output_key": ...}`` on a real successful invocation.
    - ``{"error": ..., "error_kind": ...}`` on any failure path.

    Per the PR-122 contract, this function never raises — all failure
    modes are returned as structured evidence.
    """
    del dry_run  # retained for signature compat; gate orchestration owns the decision

    matched_key: str | None = None
    packet: dict[str, Any] | None = None
    for key in output_keys or []:
        if not isinstance(key, str):
            continue
        if key not in run_state:
            continue
        candidate = _parse_packet(run_state.get(key))
        if candidate is None:
            continue
        if candidate.get("sink") != EXTERNAL_WRITE_SINK_GITHUB_PR:
            continue
        matched_key = key
        packet = candidate
        break
    if packet is None:
        return {
            "error": (
                f"node '{node_id}' declared effects=[github_pull_request] "
                "but no output_key held a parseable external_write_packet "
                "with sink='github_pull_request'"
            ),
            "error_kind": "no_matching_packet",
        }

    # ── Operator kill switch (round-3 P1 fix for Codex round-2) ────────
    # ``WORKFLOW_EXTERNAL_WRITE_DRY_RUN`` is a hard override. When
    # truthy, the effector ALWAYS returns dry-run evidence regardless
    # of capability / consent / idempotency-reservation state. This is
    # the documented panic-button path — host flips the env on a live
    # daemon to disable all real writes without revoking consent or
    # rotating capability tokens. Defense-in-depth control.
    if _env_truthy(_DRY_RUN_ENV):
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "operator_kill_switch_active",
            "kill_switch_env": _DRY_RUN_ENV,
            "intent": packet,
            "matched_output_key": matched_key,
            "hint": (
                f"{_DRY_RUN_ENV} is set on the daemon environment, "
                "which is the operator panic-button override. No real "
                "writes will fire for this sink until the env is "
                "unset (or set to a falsy value)."
            ),
        }

    destination_raw = packet.get("destination", "")
    destination = destination_raw.strip() if isinstance(destination_raw, str) else ""
    idempotency_hint = ""
    raw_hint = packet.get("idempotency_hint")
    if isinstance(raw_hint, str):
        idempotency_hint = raw_hint.strip()

    # ── Phase 1 backward-compat path ───────────────────────────────────
    # A packet without ``destination`` is a Phase 1 packet by definition
    # — Phase 2 made the field part of the canonical shape. Preserve the
    # Phase-1 dry-run evidence shape exactly so existing tests + consumers
    # don't observe a behavior change.
    if not destination:
        mode = _phase_1_mode()
        return {
            "dry_run": True,
            "mode": mode,
            "phase": "phase_1",
            "enabled_explicit": _env_truthy(_ENABLE_ENV),
            "intent": packet,
            "matched_output_key": matched_key,
            "reason": (
                "PR-122 Phase 2 introduced a 'destination' field on the "
                "external_write_packet. Packets that omit it stay on the "
                "Phase-1 dry-run-only path. See "
                "drafts/concepts/external-write-packet-shape.md."
            ),
        }

    universe_dir = _resolve_universe_dir(base_path)

    # ── Gate 0: soul-scoped effect-authority ───────────────────────────
    # The running universe's soul is the source of effect-authority (gap 1 of
    # the souled-universe self-maintenance model). A universe whose soul.md
    # declares effect_authority grants must include this sink:destination, or
    # the write fails closed here. A universe that declares NOTHING falls
    # through to the legacy env-capability + consent gates below — transitional
    # behavior the cutover removes once souls declare their grants. See
    # docs/design-notes/2026-05-28-souled-universe-effect-authority.md.
    soul_authority = resolve_soul_effect_authority(
        universe_dir, EXTERNAL_WRITE_SINK_GITHUB_PR, destination
    )
    if soul_authority == SOUL_AUTHORITY_DENIED:
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "soul_not_authorized",
            "destination": destination,
            "intent": packet,
            "matched_output_key": matched_key,
            "hint": (
                "This universe's soul declares effect_authority grants but "
                "none match "
                f'"{effect_authority_key(EXTERNAL_WRITE_SINK_GITHUB_PR, destination)}". '
                "Add that grant to the soul's '## Effect Authority' section to "
                "authorize this hand."
            ),
        }

    # ── Gate 1: capability env ─────────────────────────────────────────
    # Round-2 P1.2: lookup is by exact destination string against the
    # JSON map. The dry-run evidence names the destination the host
    # needs to add to the JSON map (the literal key) — never the
    # collision-prone uppercased suffix.
    capability = _read_capability(destination)
    if not capability:
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "missing_capability",
            "destination": destination,
            "capability_env_var": _PUSH_CAPABILITIES_ENV,
            "legacy_capability_env_var": _LEGACY_CAPABILITIES_ENV,
            "capability_lookup_failed_for": destination,
            "hint": (
                f"Add an entry to the {_PUSH_CAPABILITIES_ENV} JSON map "
                f'keyed by "{destination}" for a GitHub push-capable token. '
                f"Legacy hosts may continue using {_LEGACY_CAPABILITIES_ENV} "
                "during migration."
            ),
            "intent": packet,
            "matched_output_key": matched_key,
        }

    # ── Gate 2: consent grant ──────────────────────────────────────────
    if not _check_consent(universe_dir, destination):
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "missing_consent",
            "destination": destination,
            "intent": packet,
            "matched_output_key": matched_key,
            "hint": (
                "Call extensions action=grant_effector_consent "
                f"sink={EXTERNAL_WRITE_SINK_GITHUB_PR} "
                f"destination={destination} to authorize this universe."
            ),
        }

    # ── Gate 3: idempotency receipt (atomic reservation) ───────────────
    # Round-2 P1.1: the round-1 sequence (lookup → invoke → record)
    # was non-atomic. Two concurrent threads could both observe "no
    # receipt" and both invoke ``gh pr create``. We now reserve the
    # row BEFORE invoking, using SQLite's row-level lock on the unique
    # (idempotency_hint, sink) key. The reservation either succeeds
    # (proceed), finds a terminal succeeded row (dedup-hit), or finds
    # a pending row owned by another writer (dry-run with
    # concurrent_in_flight).
    try:
        reservation = _try_reserve(
            universe_dir,
            idempotency_hint=idempotency_hint,
            run_id=run_id,
        )
    except sqlite3.OperationalError as exc:
        # Lock / busy timeout or other SQLite error. Per P1.1 contract:
        # NEVER silently treat as a miss. Surface as a structured
        # error so the run output records exactly what happened.
        return {
            "error": (
                "receipt store unavailable; refusing to invoke "
                f"gh pr create to avoid duplicate writes: {exc}"
            ),
            "error_kind": (
                "receipt_store_locked"
                if _is_lock_error(exc) else "receipt_store_error"
            ),
            "phase": "phase_2",
            "destination": destination,
            "idempotency_hint": idempotency_hint,
            "matched_output_key": matched_key,
        }

    reservation_status = reservation.get("status")
    if reservation_status == "duplicate":
        # A terminal-succeeded row already exists — dedup hit. Return
        # the SAME evidence shape as round-1 so existing consumers
        # see no behavior change for the dedup path.
        recorded = reservation.get("row") or {}
        return {
            "idempotency_dedup_hit": True,
            "phase": "phase_2",
            "destination": destination,
            "matched_output_key": matched_key,
            "evidence": recorded.get("evidence") or {},
            "recorded_run_id": recorded.get("run_id"),
            "recorded_at": recorded.get("created_at"),
            "idempotency_hint": idempotency_hint,
        }
    if reservation_status == "in_flight":
        # Another writer holds a non-stale pending reservation. Dry
        # run rather than firing a duplicate side-effect. The caller
        # can retry later; once the in-flight writer finalizes the
        # row, our next attempt sees "duplicate" and returns the
        # recorded evidence.
        held = reservation.get("row") or {}
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "concurrent_in_flight",
            "destination": destination,
            "idempotency_hint": idempotency_hint,
            "matched_output_key": matched_key,
            "held_by_run_id": held.get("run_id"),
            "reservation_created_at": held.get("created_at"),
            "hint": (
                "Another worker is currently invoking gh pr create "
                "under the same idempotency_hint. Retry after it "
                "settles (or wait for the stale-pending threshold)."
            ),
            "intent": packet,
        }
    if reservation_status not in (
        "reserved", "reserved_after_stale",
        "reserved_after_failed", "no_hint",
    ):
        # Defensive — unknown reservation shape. Treat conservatively
        # as in-flight so we don't fire a duplicate.
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "reservation_unknown_state",
            "destination": destination,
            "idempotency_hint": idempotency_hint,
            "matched_output_key": matched_key,
            "reservation_status": str(reservation_status),
            "intent": packet,
        }

    # We hold the reservation (or there was no hint so we proceed
    # without one). Invoke the side-effect.

    # ── Real write ─────────────────────────────────────────────────────
    payload = packet.get("payload") or {}
    payload = payload if isinstance(payload, dict) else {}

    # BUG-111: materialize the change set into the remote head branch
    # BEFORE opening the PR. Without this the head ref has no commits and
    # `gh pr create` fails "No commits between base and head". Reuses the
    # capability token via the Git Data API (no git binary / clone).
    head_branch = payload.get("head_branch") or ""
    materialize = _materialize_branch(
        changes_json=payload.get("changes_json"),
        edits_json=payload.get("edits_json"),
        destination=destination,
        base_branch=payload.get("base_branch") or "main",
        head_branch=head_branch,
        commit_message=(payload.get("title") or f"Automated change for {head_branch}"),
        capability_token=capability,
    )
    if materialize.get("error"):
        _release_reservation(
            universe_dir,
            idempotency_hint=idempotency_hint,
            run_id=run_id,
        )
        materialize.setdefault("matched_output_key", matched_key)
        materialize.setdefault("destination", destination)
        materialize.setdefault("phase", "phase_2")
        if idempotency_hint:
            materialize.setdefault("idempotency_hint", idempotency_hint)
            materialize.setdefault("reservation_released", True)
        return materialize

    invocation = _invoke_gh_pr_create(
        payload=payload,
        destination=destination,
        capability_token=capability,
    )
    if "error" in invocation:
        # Release the reservation so a retry can re-acquire under the
        # same hint. Skipped when there was no hint (nothing to
        # release).
        _release_reservation(
            universe_dir,
            idempotency_hint=idempotency_hint,
            run_id=run_id,
        )
        invocation.setdefault("matched_output_key", matched_key)
        invocation.setdefault("destination", destination)
        invocation.setdefault("phase", "phase_2")
        if idempotency_hint:
            invocation.setdefault("idempotency_hint", idempotency_hint)
            invocation.setdefault("reservation_released", True)
        return invocation

    evidence: dict[str, Any] = {
        "phase": "phase_2",
        "destination": destination,
        "matched_output_key": matched_key,
        "pr_url": invocation["pr_url"],
        "pr_number": invocation.get("pr_number"),
        "invocation_mode": invocation.get("invocation_mode", "gh"),
        "stdout": invocation.get("stdout", ""),
        "head_branch": materialize.get("head_branch"),
        "commit_sha": materialize.get("commit_sha"),
        "recorded_at": time.time(),
    }
    if materialize.get("head_ref_reused"):
        evidence["head_ref_reused"] = True
    if invocation.get("label_error"):
        evidence["label_error"] = invocation["label_error"]
    if idempotency_hint:
        evidence["idempotency_hint"] = idempotency_hint
    # Reservation status is surfaced so a downstream auditor can see
    # whether this run reclaimed a stale row.
    if reservation_status in (
        "reserved_after_stale", "reserved_after_failed",
    ):
        evidence["reservation_origin"] = reservation_status
    if idempotency_hint:
        finalized = _finalize_receipt(
            universe_dir,
            idempotency_hint=idempotency_hint,
            evidence=evidence,
            run_id=run_id,
        )
        if not finalized:
            # The reservation row we held was rewritten by another
            # writer between our reserve and our finalize. The PR
            # already exists; flag the inconsistency so the operator
            # can spot it without us masking the successful write.
            evidence["receipt_finalize_failed"] = True
    return evidence


def run_effects_for_branch(
    *,
    branch: Any,
    run_state: dict[str, Any],
    base_path: str | Path | None = None,
    run_id: str = "",
    dry_run: bool | None = None,
) -> dict[str, Any]:
    """Walk every node on ``branch`` with a declared effect, dispatch.

    Returns a dict keyed by ``node_id`` for every node that declared at
    least one effect. Each value is the evidence dict from the matching
    effector. Nodes without ``effects`` are skipped entirely.

    ``base_path`` + ``run_id`` are Phase 2 additions; when omitted the
    storage-backed gates (consent, idempotency) treat the universe as
    "not configured" and the effector falls back to dry-run for any
    Phase-2-shaped packet. Phase-1-shaped packets (no destination) keep
    their Phase-1 evidence shape regardless.

    ``dry_run`` is accepted for signature compatibility but ignored —
    gate orchestration owns the dry-run-vs-real decision.

    Never raises. Errors are folded into the per-node evidence so the
    caller can log them as ``external_write_errors`` and otherwise
    complete the run normally.
    """
    del dry_run  # retained for signature compat
    evidence_map: dict[str, Any] = {}
    node_defs = getattr(branch, "node_defs", None) or []
    for node in node_defs:
        effects = getattr(node, "effects", None) or []
        if not effects:
            continue
        node_id = getattr(node, "node_id", "")
        output_keys = list(getattr(node, "output_keys", None) or [])
        per_node: dict[str, Any] = {}
        for sink in effects:
            if sink == EXTERNAL_WRITE_SINK_GITHUB_PR:
                try:
                    result = run_github_pr_effector(
                        node_id=node_id,
                        output_keys=output_keys,
                        run_state=run_state,
                        base_path=base_path,
                        run_id=run_id,
                    )
                except Exception as exc:  # defensive — never raise
                    logger.exception(
                        "github_pr effector crashed for node %s",
                        node_id,
                    )
                    result = {
                        "error": f"effector crashed: {exc}",
                        "error_kind": "effector_crashed",
                    }
                per_node[sink] = result
            elif sink == "host_local.windows_desktop.install_classic_game":
                try:
                    from workflow.effectors.windows_desktop import (
                        run_windows_desktop_effector,
                    )

                    result = run_windows_desktop_effector(
                        node_id=node_id,
                        output_keys=output_keys,
                        run_state=run_state,
                        base_path=base_path,
                        run_id=run_id,
                    )
                except Exception as exc:  # defensive — never raise
                    logger.exception(
                        "windows_desktop effector crashed for node %s",
                        node_id,
                    )
                    result = {
                        "error": f"effector crashed: {exc}",
                        "error_kind": "effector_crashed",
                    }
                per_node[sink] = result
            elif sink == "wiki_write_back":
                try:
                    from workflow.effectors.wiki_write_back import (
                        run_wiki_write_back_effector,
                    )

                    result = run_wiki_write_back_effector(
                        node_id=node_id,
                        output_keys=output_keys,
                        run_state=run_state,
                        base_path=base_path,
                        run_id=run_id,
                    )
                except Exception as exc:  # defensive — never raise
                    logger.exception(
                        "wiki_write_back effector crashed for node %s",
                        node_id,
                    )
                    result = {
                        "error": f"effector crashed: {exc}",
                        "error_kind": "effector_crashed",
                    }
                per_node[sink] = result
            else:
                per_node[sink] = {
                    "error": f"unknown effect sink '{sink}'",
                    "error_kind": "unknown_sink",
                }
        if per_node:
            evidence_map[node_id] = per_node
    return evidence_map
