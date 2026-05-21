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

Authority model (Phase 2 Slice 1)
---------------------------------

A real write fires only when ALL THREE gates are open:

1. **Capability token (env-sourced, daemon-side).** A per-destination
   env var is set on the daemon: ``WORKFLOW_GITHUB_PR_CAPABILITY_REPO_<OWNER>_<REPO>``.
   The token is read at invocation time and is never echoed into
   run state the branch can observe — a branch-authored "ack" string
   cannot mint authority. Per the design stub §1, this is Option A
   (env-sourced). Option B (per-run controller-minted) is a future
   migration target.

2. **Per-destination consent grant.** A row in the per-universe
   ``effector_consents`` table with ``(sink, destination, revoked_at
   IS NULL)`` matching the packet exactly. The chatbot composes the
   ``extensions action=grant_effector_consent`` call; the daemon
   records the grant.

3. **Idempotency receipt.** No prior ``external_write_receipts`` row
   for ``(idempotency_hint, sink)``. A receipt hit returns the recorded
   evidence with ``idempotency_dedup_hit=true`` instead of firing
   again. The store is per-universe SQLite; the receipt is
   system-authoritative.

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

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


EXTERNAL_WRITE_SINK_GITHUB_PR = "github_pull_request"
_ENABLE_ENV = "WORKFLOW_EXTERNAL_WRITE_ENABLED"
# Legacy env name retained only as recognized-input — has no effect on
# the gate-orchestrated path.
_DRY_RUN_ENV = "WORKFLOW_EXTERNAL_WRITE_DRY_RUN"
_CAPABILITY_ENV_PREFIX = "WORKFLOW_GITHUB_PR_CAPABILITY_REPO_"
_GH_PR_TIMEOUT_S = 60.0

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


def _capability_env_key(destination: str) -> str:
    """Return the env-var name a daemon sets to grant capability for ``destination``.

    Shape: ``WORKFLOW_GITHUB_PR_CAPABILITY_REPO_<OWNER>_<REPO>`` with
    every non-alphanumeric char in the destination collapsed to ``_``
    and uppercased. Example: ``Jonnyton/Workflow`` ->
    ``WORKFLOW_GITHUB_PR_CAPABILITY_REPO_JONNYTON_WORKFLOW``.

    The single env-key shape lets host configure multiple repos in
    one ``/etc/workflow/env`` file without a JSON map. Migrate to
    Option B (controller-minted scoped tokens) when paid-market /
    multi-tenant capacity grants make per-run scoping load-bearing.
    """
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", destination or "").strip("_")
    return _CAPABILITY_ENV_PREFIX + cleaned.upper()


def _read_capability(destination: str) -> str:
    """Return the capability token for ``destination`` (empty string if missing).

    Never echoed into branch-visible state. Callers must NOT include
    this value in returned evidence.
    """
    if not destination:
        return ""
    return os.environ.get(_capability_env_key(destination), "").strip()


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


def _lookup_idempotency(
    universe_dir: Path | None, idempotency_hint: str,
) -> dict[str, Any] | None:
    if universe_dir is None or not idempotency_hint:
        return None
    try:
        from workflow.storage.external_write_receipts import lookup_receipt
    except Exception:  # pragma: no cover
        logger.exception("failed to import external_write_receipts")
        return None
    try:
        return lookup_receipt(
            universe_dir,
            idempotency_hint=idempotency_hint,
            sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        )
    except Exception:  # pragma: no cover
        logger.exception("receipt lookup crashed for %s", idempotency_hint)
        return None


def _record_idempotency(
    universe_dir: Path | None,
    *,
    idempotency_hint: str,
    evidence: dict[str, Any],
    run_id: str,
) -> None:
    if universe_dir is None or not idempotency_hint:
        return
    try:
        from workflow.storage.external_write_receipts import record_receipt
    except Exception:  # pragma: no cover
        logger.exception("failed to import external_write_receipts")
        return
    try:
        record_receipt(
            universe_dir,
            idempotency_hint=idempotency_hint,
            sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
            evidence=evidence,
            run_id=run_id or "",
        )
    except Exception:
        # Receipt writes are best-effort during a run — a crash here
        # must NOT mask the real write that already succeeded. Log
        # loudly per hard rule #8 and continue.
        logger.exception(
            "failed to record receipt for %s/%s",
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
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_GH_PR_TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError:
        return {
            "error": "gh CLI not installed in the daemon environment",
            "error_kind": "gh_not_installed",
        }
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
        "stdout": stdout,
    }


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

    # ── Gate 1: capability env ─────────────────────────────────────────
    capability = _read_capability(destination)
    if not capability:
        return {
            "dry_run": True,
            "phase": "phase_2",
            "reason": "missing_capability",
            "destination": destination,
            "capability_env_key": _capability_env_key(destination),
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

    # ── Gate 3: idempotency receipt ────────────────────────────────────
    receipt = _lookup_idempotency(universe_dir, idempotency_hint)
    if receipt is not None:
        return {
            "idempotency_dedup_hit": True,
            "phase": "phase_2",
            "destination": destination,
            "matched_output_key": matched_key,
            "evidence": receipt.get("evidence") or {},
            "recorded_run_id": receipt.get("run_id"),
            "recorded_at": receipt.get("created_at"),
            "idempotency_hint": idempotency_hint,
        }

    # ── Real write ─────────────────────────────────────────────────────
    payload = packet.get("payload") or {}
    invocation = _invoke_gh_pr_create(
        payload=payload if isinstance(payload, dict) else {},
        destination=destination,
    )
    if "error" in invocation:
        # Don't record a receipt on failure; a future retry should be
        # allowed to attempt the write again.
        invocation.setdefault("matched_output_key", matched_key)
        invocation.setdefault("destination", destination)
        invocation.setdefault("phase", "phase_2")
        return invocation

    evidence: dict[str, Any] = {
        "phase": "phase_2",
        "destination": destination,
        "matched_output_key": matched_key,
        "pr_url": invocation["pr_url"],
        "pr_number": invocation.get("pr_number"),
        "stdout": invocation.get("stdout", ""),
        "recorded_at": time.time(),
    }
    if idempotency_hint:
        evidence["idempotency_hint"] = idempotency_hint
    _record_idempotency(
        universe_dir,
        idempotency_hint=idempotency_hint,
        evidence=evidence,
        run_id=run_id,
    )
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
            else:
                per_node[sink] = {
                    "error": f"unknown effect sink '{sink}'",
                    "error_kind": "unknown_sink",
                }
        if per_node:
            evidence_map[node_id] = per_node
    return evidence_map
