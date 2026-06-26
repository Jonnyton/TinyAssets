"""validate_patch: a platform-trusted opaque node that deterministically
verifies a proposed patch packet APPLIES to the fetched current contents —
before a real PR is attempted and before an LLM review burns a guess.

The frontier gap it closes: every SOTA issue→PR system (Agentless, AutoCodeRover,
SWE-agent) validates patches with executable ground truth; our loop had none —
``review_gate`` only *guessed* (via an LLM) whether each search string matched.
The dominant patch-failure mode is a ``search`` string that does not occur
verbatim-and-unique in the live file, so the PR fails to apply. That is checkable
deterministically, in code, with NO LLM and NO network: the loop already fetched
the real file contents into ``current_contents_json`` (read_repo_files), and the
github_pull_request effector's ``_apply_edit_blocks`` is a pure exact-match apply.

Contract (opaque callable — ``fn(state) -> dict`` of state updates; never raises):

  reads from state:
    - ``pr_packet_draft`` (str|dict): the external_write_packet from
      propose_changes. We validate ``payload.edits_json`` ({path: [blocks]}).
    - ``current_contents_json`` (str): {path: contents|null} fetched by
      read_repo_files — the ground truth each edit must anchor on.
  writes to state:
    - ``patch_validity`` (str): exactly ``VALID`` or ``INVALID`` — a branch
      conditional-edges on this (``INVALID`` -> propose_changes for a retry,
      ``VALID`` -> review_gate).
    - ``patch_validity_detail`` (str): concrete, per-file reasons a propose
      retry can act on (which search text was not found / not unique).

Wiring (the user composes it via patch_branch): insert a ``validate_patch`` node
between propose_changes and review_gate, declare output_keys
[patch_validity, patch_validity_detail], and add a conditional edge from it.

Design parallels read_repo_files (opaque domain callable; user references it but
cannot supply its body) — see workflow/effectors/github_read.py.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

DOMAIN_ID = "workflow"
NODE_ID = "validate_patch"


def _invalid(detail: str) -> dict:
    return {"patch_validity": "INVALID", "patch_validity_detail": detail}


def _syntax_error(path: str, content: str) -> str:
    """Return a syntax-error description for a known language, else ''. Pure
    (no import/exec): ``compile(..., 'exec')`` only PARSES, and json.loads only
    parses — catches a patch that applies cleanly but breaks the file (the SWE
    "lint-guard"). Unknown extensions are skipped (no false positives).

    Scope (Codex review of #1410): the Python check uses the DAEMON's grammar,
    which is accurate when the target repo's Python <= the daemon's runtime
    (the patch-loop targets Jonnyton/Workflow on the same 3.11+ runtime). A repo
    using newer-than-daemon syntax could see a false INVALID on those constructs;
    Python's strong back-compat keeps that surface tiny. JSON parsing is
    version-independent."""
    lower = path.lower()
    if lower.endswith(".py") or lower.endswith(".pyi"):
        try:
            compile(content, path, "exec")
        except SyntaxError as exc:
            where = f" (line {exc.lineno})" if exc.lineno else ""
            return f"Python SyntaxError: {exc.msg}{where}"
        except (ValueError, TypeError) as exc:  # e.g. null bytes
            return f"Python source not compilable: {exc}"
    elif lower.endswith(".json"):
        try:
            json.loads(content)
        except (ValueError, TypeError) as exc:
            return f"invalid JSON: {exc}"
    return ""


def validate_patch(state: dict) -> dict:
    """Opaque-node body: a deterministic pre-flight. No LLM, no network. Never
    raises.

    Scope (honest — Codex review of #1409): this verifies the packet is a
    well-formed external_write_packet (reusing github_pr._parse_packet, the SAME
    shape gate the effector uses) and that its ``edits_json`` applies to the
    ALREADY-FETCHED ``current_contents_json`` — the same basis propose_changes
    edited against. It is NOT a full effector simulation: the github_pull_request
    effector re-fetches each path at ``payload.base_branch`` before applying, so
    base_branch divergence (and deletion-target presence) remain the effector's
    authority. What this reliably catches early is the dominant failure: a search
    string that isn't verbatim-and-unique in the fetched file, plus malformed
    packets / empty or conflicting change sets — feeding a concrete reason back
    for a propose retry instead of burning a review + a failed PR attempt.
    """
    if not isinstance(state, dict):
        return _invalid("no run state to validate.")
    # Reuse the effector's own pure helpers so verdicts match real behavior.
    from workflow.effectors.github_pr import _apply_edit_blocks, _parse_packet

    packet = _parse_packet(state.get("pr_packet_draft"))
    if packet is None:
        return _invalid(
            "pr_packet_draft is not a valid external_write_packet — it must be a "
            "JSON object starting with '{', carrying a 'sink', with no code fences "
            "or prose. Re-emit ONLY the raw JSON object."
        )
    payload = packet.get("payload")
    if not isinstance(payload, dict):
        return _invalid("packet.payload is missing or not a JSON object.")

    edits = payload.get("edits_json")
    changes = payload.get("changes_json")
    edit_paths: set[str] = set()
    change_paths: set[str] = set()

    # changes_json shape — mirror github_pr._materialize_branch's offline checks.
    if changes is not None:
        if not isinstance(changes, dict):
            return _invalid("packet.payload.changes_json must be an object or omitted.")
        for pk, cv in changes.items():
            if not isinstance(pk, str) or not pk.strip():
                return _invalid("changes_json keys must be non-empty repo-relative path strings.")
            if cv is not None and not isinstance(cv, str):
                return _invalid(
                    f"changes_json[{pk!r}] must be a string (new contents) or null (delete)."
                )
            if isinstance(cv, str):
                syn = _syntax_error(pk, cv)
                if syn:
                    return _invalid(
                        f"new-file {pk!r} would not parse — {syn}. Fix the file content."
                    )
            change_paths.add(pk)

    try:
        contents = json.loads(state.get("current_contents_json") or "{}")
        if not isinstance(contents, dict):
            contents = {}
    except (TypeError, ValueError):
        contents = {}

    errors: dict[str, str] = {}
    checked = 0
    if edits is not None:
        if not isinstance(edits, dict) or not edits:
            return _invalid(
                "packet.payload.edits_json must be a non-empty object of "
                "{path: [search/replace blocks]} (or omitted)."
            )
        for path, blocks in edits.items():
            edit_paths.add(path)
            current = contents.get(path)
            if not isinstance(current, str):
                errors[path] = (
                    "target file was not fetched present in current_contents "
                    "(an in-place edit needs the real file; use changes_json to "
                    "create a new file, or fix the path)"
                )
                continue
            new_content, err = _apply_edit_blocks(current, blocks)
            if err is not None:
                errors[path] = err.get("detail") or err.get("error_kind") or "edit did not apply"
            else:
                syn = _syntax_error(path, new_content or "")
                if syn:
                    errors[path] = f"edit applies but the patched file no longer parses — {syn}"
                else:
                    checked += 1

    if not edit_paths and not change_paths:
        return _invalid(
            "packet has no effective change set (no edits_json or changes_json entries)."
        )
    overlap = edit_paths & change_paths
    if overlap:
        return _invalid(
            "a path appears in BOTH edits_json and changes_json (use exactly one "
            f"per path): {', '.join(sorted(overlap))}."
        )

    if errors:
        detail = "; ".join(f"{p}: {e}" for p, e in sorted(errors.items()))
        return _invalid(
            "Patch does NOT apply to the fetched current contents — fix these and "
            f"re-propose: {detail}"
        )
    return {
        "patch_validity": "VALID",
        "patch_validity_detail": (
            f"All {checked} in-place-edited file(s) apply to the fetched current contents."
            if checked else
            "Change set is new-file/deletion only; apply deferred to the effector."
        ),
    }


def register_validate_patch() -> None:
    """Register the validate_patch opaque callable for the workflow domain.

    Idempotent. Called from workflow/effectors/__init__.py at import and lazily
    from the compiler's opaque-resolution path.
    """
    from workflow.domain_registry import register_domain_callable

    register_domain_callable(DOMAIN_ID, NODE_ID, validate_patch)


__all__ = ["validate_patch", "register_validate_patch", "DOMAIN_ID", "NODE_ID"]
