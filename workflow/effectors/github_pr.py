"""GitHub PR substrate effector — PR-122 Phase 1 milestone M1 (round 3).

Reads ``external_write_packet`` shapes from a completed run's final state
for any node whose ``effects`` declaration includes
``"github_pull_request"``, and returns **dry-run evidence** describing
what *would* have been done.

Packet shape (convention — documented in
drafts/concepts/external-write-packet-shape.md):

.. code-block:: json

    {
      "sink": "github_pull_request",
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

Phase 1 scope — round 3 cut
---------------------------

Phase 1's goal is to land the **effects vocabulary** and an **effector
entry point**: a place in the run-completion path that walks
``NodeDefinition.effects`` and resolves matching outputs to a typed
"intent" record. Phase 1 deliberately ships **no real-write
authority**.

Per Codex round-2 review of PR #955 (verdict 2026-05-20T06:46Z):

- A public static "idempotency_ack" string in the branch-authored packet
  was self-mintable authority, not real authority.
- Phase 1 also lacks any idempotency store, so the previous "ack to
  acknowledge duplicate-PR risk" path could fire ``gh pr create`` twice
  with the same packet on retry.

Round-3 response: Phase 1 is **dry-run-only at the code level**. The
effector never invokes ``gh``. The ``WORKFLOW_EXTERNAL_WRITE_ENABLED``
env is preserved as a hook for Phase 2 — when truthy the evidence
records ``mode="dry_run_phase_1"`` instead of ``"dry_run_default"`` so
operators can see the future-enabled signal, but no subprocess fires.

Real-write authority is deferred to Phase 2, which must ship:
capability-token isolation (daemon-side, never branch-author-mintable),
an idempotency store keyed by ``idempotency_hint`` + existing-remote
branch lookup, and a per-destination consent surface. See
``drafts/concepts/external-write-phase-2-authority.md``.

Errors are captured and returned in the evidence map; the function
never raises to the run-completion path. Hard-rule #8 (fail loudly)
is satisfied by structured ``error`` fields in the per-node evidence.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess  # noqa: F401 — kept importable so tests can patch and assert never-called
from typing import Any

logger = logging.getLogger(__name__)


EXTERNAL_WRITE_SINK_GITHUB_PR = "github_pull_request"
_ENABLE_ENV = "WORKFLOW_EXTERNAL_WRITE_ENABLED"
# Legacy env name retained only as recognized-input — has no effect in
# Phase 1 round 3 since the code path is dry-run-only regardless.
_DRY_RUN_ENV = "WORKFLOW_EXTERNAL_WRITE_DRY_RUN"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_truthy(name: str) -> bool:
    val = os.environ.get(name, "")
    return val.strip().lower() in _TRUTHY


def _phase_1_mode() -> str:
    """Return the Phase 1 dry-run mode label for evidence records.

    - ``"dry_run_phase_1"`` when ``WORKFLOW_EXTERNAL_WRITE_ENABLED`` is
      truthy. The env var is preserved as a Phase-2 hook — operators
      who set it are signalling "I want real writes once they're safe".
      Phase 1 still emits dry-run evidence.
    - ``"dry_run_default"`` otherwise.
    """
    return "dry_run_phase_1" if _env_truthy(_ENABLE_ENV) else "dry_run_default"


def _parse_packet(value: Any) -> dict[str, Any] | None:
    """Parse an output value into an external_write_packet dict.

    Accepts an already-dict shape OR a JSON-string shape. Returns
    ``None`` when the value isn't packet-shaped (missing ``sink``).
    """
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


def run_github_pr_effector(
    *,
    node_id: str,
    output_keys: list[str],
    run_state: dict[str, Any],
    dry_run: bool = True,  # retained for signature compat — ignored
) -> dict[str, Any]:
    """Run the GitHub-PR effector for a single node (Phase 1: dry-run).

    Scans ``output_keys`` for a value that parses as an
    ``external_write_packet`` with ``sink == "github_pull_request"``.
    The first matching key wins; non-matching keys are skipped silently
    (they are normal output fields, not packets).

    Phase 1 always returns a dry-run evidence record — the effector
    never invokes ``gh``. The ``dry_run`` parameter is retained for
    signature compatibility but is no-op in Phase 1.

    Returns one of:

    - ``{"dry_run": True, "mode": "dry_run_default"|"dry_run_phase_1",
       "intent": <packet>, "matched_output_key": <key>}`` when a packet
       was found and parsed.
    - ``{"error": "...", "error_kind": "no_matching_packet"}`` when no
      output key held a packet-shaped value.

    Per the PR-122 contract, this function never raises — all failure
    modes are returned as structured evidence and surfaced into the run
    record's ``external_write_errors`` metadata so authors can debug
    without crashing the run.
    """
    del dry_run  # retained for signature compat; Phase 1 is dry-run-only
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
    mode = _phase_1_mode()
    return {
        "dry_run": True,
        "mode": mode,
        "phase": "phase_1",
        "enabled_explicit": _env_truthy(_ENABLE_ENV),
        "intent": packet,
        "matched_output_key": matched_key,
        "reason": (
            "PR-122 Phase 1 is dry-run-only at the code level. Real-write "
            "authority is deferred to Phase 2 (capability tokens + "
            "idempotency store + per-destination consent). See "
            "drafts/concepts/external-write-phase-2-authority.md."
        ),
    }


def run_effects_for_branch(
    *,
    branch: Any,
    run_state: dict[str, Any],
    dry_run: bool | None = None,
) -> dict[str, Any]:
    """Walk every node on ``branch`` with a declared effect, dispatch.

    Returns a dict keyed by ``node_id`` for every node that declared at
    least one effect. Each value is the evidence dict from the matching
    effector (one currently — github_pull_request). Nodes without
    ``effects`` are skipped entirely.

    ``dry_run`` is accepted for signature compatibility but ignored —
    Phase 1 round 3 is dry-run-only at the code level.

    Never raises. Errors are folded into the per-node evidence so the
    caller can log them as ``external_write_errors`` and otherwise
    complete the run normally.
    """
    del dry_run  # retained for signature compat; Phase 1 is dry-run-only
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
