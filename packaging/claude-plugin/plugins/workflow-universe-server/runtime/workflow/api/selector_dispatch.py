"""User-buildable selector branch dispatch — DESIGN-008.

The architectural commitment from host's 2026-05-21 reframe: selection
logic is per-Goal user-buildable, NOT platform-coded. ``quality_leaderboard``
no longer applies an opinionated formula; instead it dispatches a
**selector branch** (a published Workflow branch bound to the Goal)
that consumes signal data and emits ranked entries.

This module owns:

* :func:`resolve_selector_branch_version_id` — return the selector
  branch_version_id for a Goal. If ``goal.selector_branch_version_id``
  is set, use it. Otherwise return the platform default selector's
  branch_version_id (lazily published on first call so the substrate
  works on a clean DB).
* :func:`dispatch_selector` — synchronously (with timeout) run a
  selector branch_version against the supplied candidate set, parse
  + validate the output shape, return ``ranked_entries`` or a
  structured error.
* :func:`ensure_default_selector_published` — idempotent helper that
  builds + publishes the platform default selector branch on first
  call. The default is a single prompt-template node that consumes
  the signal map and asks the LLM to rank — the "weights" are a
  prompt the chatbot can tune via fork, not Python constants.

Contract for selector branches (see also
``drafts/concepts/selector-branch-contract.md``):

Inputs (passed as the run's ``inputs`` dict)::

    {
        "goal_id": "<goal-id>",
        "candidate_branches": [
            {
                "branch_def_id": "...",
                "branch_version_id": "...",  # latest active version, or ""
                "name": "...",
                "author": "...",
                "signals": {
                    "completed_run_count": int,
                    "failed_run_count":    int,
                    "judgment_score_avg":  float | null,
                    "judgment_count":      int,
                    "fork_count":          int,
                    "last_successful_run_at": float,  # epoch
                    "has_gate_rung":       bool,
                    "gate_rung_top":       str | null,
                    "safe_to_publish":     bool,
                    "age_days_since_success": float | null,
                },
            },
            ...
        ],
    }

Outputs (read from the run's ``output`` dict)::

    {
        "ranked_entries": [
            {
                "branch_def_id":     "...",
                "branch_version_id": "...",
                "score":             <float>,
                "rationale":         "<human-readable why-ranked-here>",
            },
            ...  # ordered by rank, best first
        ],
    }

Round-1 design choices
----------------------

* **Sync dispatch with timeout.** The leaderboard caller blocks on the
  selector run via ``wait_for(run_id, timeout=SELECTOR_TIMEOUT_S)``. The
  selector pipeline cost is one LLM call per leaderboard build. A
  future caching slice can memoize results per Goal for N minutes.

* **Visibility is server-derived.** The candidate set passed to the
  selector is the public-or-author-owned view per PR-970's auth-
  boundary contract. The selector branch sees only branches the
  caller has visibility into; private branches authored by other
  actors are never even mentioned in the input.

* **Default selector is a published branch, not a code path.**
  ``ensure_default_selector_published`` builds the BranchDefinition
  in-Python on first call, calls ``save_branch_definition`` +
  ``publish_branch_version``, and stores the resulting
  ``branch_version_id`` for return. Subsequent calls find the
  existing definition and return its current active version.

* **Failure modes surface structured errors.** Selector missing /
  not published / timed out / invalid output shape all return
  ``{"ok": False, "error_kind": "..."}`` dicts that the leaderboard
  caller renders to the chatbot. The leaderboard never crashes;
  callers see a clear "selector misbehaved" signal rather than a
  Python traceback.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# How long the selector run is allowed to complete before the
# leaderboard caller gives up. One LLM call typically lands in <15s;
# 60s leaves headroom for slower providers + multiple-candidate
# prompts. Configurable via env so hosts can tune.
SELECTOR_TIMEOUT_S_DEFAULT = 60.0
SELECTOR_TIMEOUT_ENV = "WORKFLOW_SELECTOR_TIMEOUT_S"

# Deterministic branch_def_id for the platform default selector.
# Tests rely on this being stable across processes.
DEFAULT_SELECTOR_BRANCH_DEF_ID = "platform_default_selector_v1_20260521"
DEFAULT_SELECTOR_NAME = "Platform Default Selector v1"
DEFAULT_SELECTOR_AUTHOR = "platform"
DEFAULT_SELECTOR_PUBLISHER = "platform"


# ---------------------------------------------------------------------------
# Selector resolution
# ---------------------------------------------------------------------------


def resolve_selector_branch_version_id(
    base_path: str | Path,
    *,
    goal_id: str,
) -> dict[str, Any]:
    """Return the selector branch_version_id for the Goal.

    Resolution order:

      1. ``goal.selector_branch_version_id`` if set.
      2. Otherwise, the platform default selector's
         ``branch_version_id`` (published lazily by
         ``ensure_default_selector_published``).

    Returns ``{"ok": True, "branch_version_id": "...", "source":
    "goal_binding" | "platform_default"}`` on success or
    ``{"ok": False, "error_kind": "...", "error": "..."}`` on
    failure. Never raises.
    """
    try:
        from workflow.daemon_server import get_goal
        goal = get_goal(base_path, goal_id=goal_id)
    except KeyError:
        return {
            "ok": False,
            "error_kind": "goal_not_found",
            "error": f"Goal {goal_id!r} not found.",
        }
    except Exception as exc:  # pragma: no cover — defensive
        logger.exception("resolve_selector | get_goal crashed")
        return {
            "ok": False,
            "error_kind": "goal_load_failed",
            "error": str(exc),
        }

    explicit = (goal.get("selector_branch_version_id") or "").strip() or None
    # P1.C (DESIGN-008 round 4) — re-check the bound version's status
    # at READ/DISPATCH time. Bind-time enforces ``status='active'`` (see
    # ``set_selector_branch``), but the version can be rolled back AFTER
    # bind by a separate ``branch_versions.status`` flip or by a
    # rollback operation. Without this re-check, a rolled-back selector
    # keeps running on every leaderboard read — exactly the bug Codex
    # round 3 caught. Mirrors the round-2 P1.1 contract on
    # ``set_canonical_branch`` / ``_latest_published_version_id``.
    #
    # When the bound version is no longer active, fall back to the
    # platform default with a structured ``fellback_from`` diagnostic
    # so the chatbot / audit tools can flag the stale binding and the
    # operator can re-bind or unbind.
    fellback_from: dict[str, str] | None = None
    if explicit:
        try:
            from workflow.branch_versions import get_branch_version
            version = get_branch_version(base_path, explicit)
        except Exception:
            logger.exception(
                "resolve_selector | get_branch_version crashed for "
                "goal=%s explicit=%s", goal_id, explicit,
            )
            version = None
        if version is None:
            fellback_from = {
                "branch_version_id": explicit,
                "reason": "selector_version_not_found",
            }
            logger.warning(
                "selector binding for goal=%s points at "
                "branch_version_id=%r which is no longer in "
                "branch_versions; falling back to platform default",
                goal_id, explicit,
            )
            explicit = None
        else:
            status = getattr(version, "status", "active") or "active"
            if status != "active":
                fellback_from = {
                    "branch_version_id": explicit,
                    "reason": "selector_version_inactive",
                    "status": status,
                }
                logger.warning(
                    "selector binding for goal=%s points at "
                    "branch_version_id=%r with status=%r "
                    "(active-only required); falling back to "
                    "platform default. Operator: re-bind via "
                    "goals action=set_selector with an active "
                    "version, or unbind with branch_version_id=''",
                    goal_id, explicit, status,
                )
                explicit = None

    if explicit:
        return {
            "ok": True,
            "branch_version_id": explicit,
            "source": "goal_binding",
        }

    # Fall back to the platform default selector. This path is
    # reached for: no explicit binding, OR an explicit binding that
    # is no longer active (see fellback_from above).
    try:
        default_bvid = ensure_default_selector_published(base_path)
    except Exception as exc:
        logger.exception("resolve_selector | default-selector publish crashed")
        return {
            "ok": False,
            "error_kind": "default_selector_publish_failed",
            "error": str(exc),
        }
    if not default_bvid:
        return {
            "ok": False,
            "error_kind": "default_selector_unavailable",
            "error": (
                "Platform default selector branch could not be "
                "published; no fallback selector available."
            ),
        }
    result: dict[str, Any] = {
        "ok": True,
        "branch_version_id": default_bvid,
        "source": "platform_default",
    }
    if fellback_from is not None:
        # Distinguish "no binding" platform_default from "binding
        # invalidated by rollback" platform_default. Programmatic
        # consumers can spot stale bindings without scraping logs.
        result["fellback_from"] = fellback_from
    return result


# ---------------------------------------------------------------------------
# Default selector materialization
# ---------------------------------------------------------------------------


def ensure_default_selector_published(base_path: str | Path) -> str:
    """Ensure the platform default selector branch + active version exist.

    Returns the active ``branch_version_id``. Idempotent: if the
    branch_def already exists AND has an active published version,
    that version's id is returned without re-publishing.

    The branch is a single prompt-template node:

      * Input keys: ``goal_id``, ``candidate_branches`` (the signal
        bundle the leaderboard collects).
      * Output keys: ``ranked_entries`` (JSON array of
        ``{branch_def_id, branch_version_id, score, rationale}``).

    The prompt explicitly instructs the LLM to weight signals and
    emit valid JSON. Community forks of this branch tune the prompt
    rather than Python constants.
    """
    from workflow.branch_versions import (
        get_branch_version,
        list_branch_versions,
        publish_branch_version,
    )
    from workflow.daemon_server import (
        get_branch_definition,
        save_branch_definition,
    )

    # Step 1: ensure the branch_def exists.
    try:
        existing = get_branch_definition(
            base_path, branch_def_id=DEFAULT_SELECTOR_BRANCH_DEF_ID,
        )
    except KeyError:
        existing = None

    if existing is None:
        branch_dict = _build_default_selector_branch_dict()
        save_branch_definition(base_path, branch_def=branch_dict)

    # Step 2: find an active published version, else publish one.
    versions = list_branch_versions(
        base_path,
        branch_def_id=DEFAULT_SELECTOR_BRANCH_DEF_ID,
        limit=50,
    )
    for v in versions:
        if getattr(v, "status", "active") == "active":
            return v.branch_version_id

    # No active version — publish v1.
    #
    # P1 (DESIGN-008 round 5): ``publish_branch_version`` is deterministic
    # in ``(branch_def_id, content_hash)``. When an operator has rolled
    # back the platform default (every existing version's status flipped
    # to ``rolled_back``), the re-publish call returns the same existing
    # rolled-back row (workflow/branch_versions.py:267-273) rather than
    # minting a fresh active one. Without the post-publish status check
    # below, ``ensure_default_selector_published`` would silently hand
    # back a rolled-back branch_version_id, and ``dispatch_selector``
    # would execute it — defeating the rollback. Fail closed instead:
    # return empty so the caller (``resolve_selector_branch_version_id``)
    # surfaces ``default_selector_unavailable``.
    branch_dict = _build_default_selector_branch_dict()
    version = publish_branch_version(
        base_path,
        branch_dict=branch_dict,
        publisher=DEFAULT_SELECTOR_PUBLISHER,
        notes=(
            "Platform default selector v1 — single prompt-template "
            "node ranking candidate branches from collected signals. "
            "Community forks customize the prompt per domain."
        ),
    )
    # Sanity: re-read to confirm row landed + status.
    persisted = get_branch_version(base_path, version.branch_version_id)
    if persisted is None:
        raise RuntimeError(
            "publish_branch_version reported success but the row is "
            "not readable post-write."
        )
    status = getattr(persisted, "status", "active") or "active"
    if status != "active":
        logger.warning(
            "ensure_default_selector_published | publish_branch_version "
            "returned existing branch_version_id=%r with status=%r "
            "(deterministic re-publish hit a rolled-back row). Cannot "
            "dispatch a rolled-back default selector. Operator: "
            "republish the platform default branch with a content "
            "change (so a fresh content_hash mints a new active row), "
            "or bind a custom selector to the affected Goal via "
            "goals action=set_selector.",
            persisted.branch_version_id, status,
        )
        return ""
    return persisted.branch_version_id


def _build_default_selector_branch_dict() -> dict[str, Any]:
    """Construct the default selector's BranchDefinition dict.

    Kept as a function (not a constant) so each call returns a fresh
    dict the storage layer can mutate without aliasing.
    """
    prompt = _DEFAULT_SELECTOR_PROMPT
    node = {
        "node_id": "rank",
        "display_name": "Rank Candidates",
        "description": (
            "Read candidate_branches + their signals; emit "
            "ranked_entries JSON in score-desc order."
        ),
        "phase": "custom",
        "input_keys": ["goal_id", "candidate_branches"],
        "output_keys": ["ranked_entries"],
        "prompt_template": prompt,
        "model_hint": "writer",
        # The prompt-template node consumes ``candidate_branches`` —
        # a structured JSON-able list. The default prompt-template
        # renderer treats input_keys as a dict the template's
        # placeholders are formatted against; the strict_input_isolation
        # default (True) keeps the prompt from leaking state it
        # didn't declare.
    }
    return {
        "branch_def_id": DEFAULT_SELECTOR_BRANCH_DEF_ID,
        "name": DEFAULT_SELECTOR_NAME,
        "description": (
            "Platform default selector — ranks candidate branches "
            "for a Goal's leaderboard using LLM judgment over "
            "collected signals. Fork + tune the prompt for "
            "domain-specific selection."
        ),
        "author": DEFAULT_SELECTOR_AUTHOR,
        "domain_id": "workflow",
        "tags": ["selector", "platform-default", "leaderboard"],
        "version": 1,
        "skills": [],
        "entry_point": "rank",
        "graph_nodes": [
            {
                "id": "rank",
                "type": "prompt",
                "phase": "custom",
                "input_keys": ["goal_id", "candidate_branches"],
                "output_keys": ["ranked_entries"],
            },
        ],
        "edges": [
            {"from": "START", "to": "rank"},
            {"from": "rank", "to": "END"},
        ],
        "node_defs": [node],
        # state_schema types are intentionally all ``str``: the
        # ``ranked_entries`` output is emitted as a JSON-string by the
        # prompt-template node, then the substrate parses it via
        # ``_parse_ranked_entries`` (which tolerates JSON-string +
        # markdown-fence shapes). Declaring ``list`` here would force
        # the graph_compiler's JSON-contract code path on the response,
        # which assumes native structured-output and rejects any
        # provider that returns the JSON as a plain string. Selectors
        # talk to many providers (CLI-wrapped Claude / codex / ollama)
        # where structured-output isn't wirable.
        "state_schema": [
            {"name": "goal_id", "type": "str"},
            {"name": "candidate_branches", "type": "str"},
            {"name": "ranked_entries", "type": "str"},
        ],
        "published": True,
        "visibility": "public",
    }


# The default selector prompt. The "weights" are now words that any
# Goal owner can fork and rewrite for their domain (e.g. fantasy-
# writing might rank "novelty" higher; bug-investigation might
# weight "completed_run_count" + "judgment_score_avg" almost
# exclusively). See ``drafts/concepts/selector-branch-contract.md``
# for the full input/output spec.
_DEFAULT_SELECTOR_PROMPT = """\
You are the **platform default selector** for a Workflow Goal's
leaderboard. Your job is to rank candidate branches that are competing
on the same Goal and emit a JSON array describing the ranking.

## Goal context
goal_id: {goal_id}

## Candidates with collected signals
{candidate_branches}

## Ranking guidance (default — fork this branch to customize)

Consider, in roughly this order of importance:

1. **judgment_score_avg** — average of numeric judgment tags
   (quality/novelty/score). When non-null this is the strongest
   single signal. Treat as ~0-10.
2. **completed_run_count** — more completed runs = more evidence
   this branch actually works. Penalty for `failed_run_count`.
3. **fork_count** — community votes with their forks; high
   fork_count signals influence + endorsement.
4. **last_successful_run_at + age_days_since_success** — recency
   matters; a branch that succeeded yesterday outranks one that
   succeeded six months ago, all else equal.
5. **has_gate_rung / gate_rung_top** — branches that have climbed
   the Goal's gate ladder (real-world impact) outrank those that
   have not.
6. **safe_to_publish** — when present, a strong positive signal.

Branches with no completed runs and no judgments rank below
branches that have *any* signal. A branch with only one completed
run but high judgment_score_avg can still rank well.

## Output

Emit ONLY a JSON object (no markdown fence, no prose before or
after) with the following shape:

```
{{"ranked_entries":[
  {{
    "branch_def_id":"...",
    "branch_version_id":"...",
    "score":<float>,
    "rationale":"<one sentence>"
  }},
  ...
]}}
```

Order entries best-first. Use the `branch_version_id` from each
candidate if non-empty, otherwise the empty string. `score` should
be on a 0.0-10.0 scale; ties are acceptable. `rationale` is a single
sentence naming the dominant signals (e.g. "highest judgment avg
(8.4) with 12 completed runs and 3 community forks").

If `candidate_branches` is empty, return `{{"ranked_entries":[]}}`.
"""


# ---------------------------------------------------------------------------
# Selector dispatch + result parsing
# ---------------------------------------------------------------------------


def dispatch_selector(
    base_path: str | Path,
    *,
    goal_id: str,
    candidate_branches: list[dict[str, Any]],
    actor: str = "anonymous",
    timeout_s: float | None = None,
    provider_call: Any = None,
) -> dict[str, Any]:
    """Run the selector branch synchronously + return its ``ranked_entries``.

    Resolves the selector via :func:`resolve_selector_branch_version_id`,
    dispatches an async run via ``execute_branch_version_async``, blocks
    on its background future for up to ``timeout_s`` seconds, reads the
    final ``runs.output_json``, validates the
    ``ranked_entries`` shape, and returns it.

    Returns one of:

    Success::

        {
            "ok": True,
            "branch_version_id": "...",
            "source": "goal_binding" | "platform_default",
            "run_id": "...",
            "ranked_entries": [...],  # validated shape
        }

    Failure (selector unresolvable, dispatch failed, timeout, or
    invalid output shape)::

        {
            "ok": False,
            "error_kind": "<one of: selector_not_published |
                            selector_dispatch_failed |
                            selector_timeout |
                            selector_run_failed |
                            selector_invalid_output>",
            "error": "<human-readable>",
            # Optional context fields per error_kind:
            "branch_version_id": "...",
            "run_id": "...",
        }

    Empty ``candidate_branches`` short-circuits to
    ``{ok: True, ranked_entries: []}`` without dispatching — no
    point burning an LLM call when there's nothing to rank.
    """
    # Short-circuit: no candidates means no work.
    if not candidate_branches:
        return {
            "ok": True,
            "branch_version_id": None,
            "source": "empty_candidate_set",
            "run_id": None,
            "ranked_entries": [],
        }

    resolution = resolve_selector_branch_version_id(
        base_path, goal_id=goal_id,
    )
    if not resolution.get("ok"):
        return {
            "ok": False,
            "error_kind": resolution.get(
                "error_kind", "selector_not_published",
            ),
            "error": resolution.get("error", ""),
        }
    bvid = resolution["branch_version_id"]
    source = resolution["source"]
    # P1.C (round 4) — when the bound version was found inactive at
    # resolve time and the substrate fell back to platform default,
    # propagate that diagnostic to the leaderboard caller so the
    # response shape carries it. Empty / None when not applicable.
    fellback_from = resolution.get("fellback_from")

    timeout = _resolve_timeout(timeout_s)

    # Build the selector's input dict. ``candidate_branches`` is
    # serialized as-is — the prompt template's placeholder will
    # render it via str() / JSON depending on the provider's stub.
    inputs: dict[str, Any] = {
        "goal_id": goal_id,
        "candidate_branches": candidate_branches,
    }

    # Reconstruct the selector branch from the immutable snapshot +
    # the live branch_definitions row's identity metadata.
    #
    # P1.1 fix (DESIGN-008 round 2): ``publish_branch_version`` ->
    # ``_canonical_snapshot`` deliberately strips name / description /
    # author from the immutable snapshot — only graph behavior fields
    # survive. Reconstructing via ``BranchDefinition.from_dict(snapshot)``
    # alone yields an empty name and ``validate()`` rejects with
    # "Branch name is required" before compile.
    #
    # We enrich here by reading the parent ``branch_definitions``
    # row (same branch_def_id) and merging name / description /
    # author / visibility back in. Effects + node graph + state
    # schema still come from the IMMUTABLE snapshot, so the
    # selector's actual behavior matches what was published — only
    # the identity/UI fields come from the mutable parent row.
    from workflow.branch_versions import get_branch_version
    from workflow.branches import BranchDefinition
    from workflow.daemon_server import get_branch_definition
    from workflow.runs import _execute_branch_core

    try:
        bv = get_branch_version(base_path, bvid)
    except Exception as exc:
        logger.exception(
            "selector dispatch | get_branch_version crashed | "
            "goal=%s bvid=%s", goal_id, bvid,
        )
        return {
            "ok": False,
            "error_kind": "selector_dispatch_failed",
            "error": str(exc),
            "branch_version_id": bvid,
        }
    if bv is None:
        return {
            "ok": False,
            "error_kind": "selector_not_published",
            "error": (
                f"selector branch_version_id {bvid!r} not found in "
                "branch_versions."
            ),
            "branch_version_id": bvid,
        }

    # P1 (DESIGN-008 round 5) — dispatch-time status guard. The
    # resolve-time check in ``resolve_selector_branch_version_id`` +
    # the fail-closed semantics in ``ensure_default_selector_published``
    # cover the normal lifecycle, but a final ``status='active'`` check
    # here closes any race between resolve and dispatch (TOCTOU) and
    # protects callers that thread their own ``branch_version_id``
    # straight in without going through ``resolve_selector_branch_version_id``.
    # Cheap (one already-loaded attribute read) and idempotent.
    bv_status = getattr(bv, "status", "active") or "active"
    if bv_status != "active":
        logger.warning(
            "selector dispatch | branch_version_id=%r resolved to "
            "status=%r at dispatch time (active-only required). "
            "Refusing to execute a rolled-back / superseded selector.",
            bvid, bv_status,
        )
        return {
            "ok": False,
            "error_kind": "selector_version_inactive_at_dispatch",
            "error": (
                f"selector branch_version_id {bvid!r} resolved to "
                f"status={bv_status!r} at dispatch time. The "
                "selector binding is stale or the platform default "
                "was rolled back without a fresh active replacement. "
                "Operator: bind a different active selector via "
                "goals action=set_selector, unbind to fall back to "
                "the platform default, or republish the platform "
                "default with new content so a fresh active version "
                "is minted."
            ),
            "branch_version_id": bvid,
            "status": bv_status,
        }

    snapshot = dict(bv.snapshot or {})
    parent_def_id = snapshot.get("branch_def_id") or ""
    parent_row: dict[str, Any] | None = None
    if parent_def_id:
        try:
            parent_row = get_branch_definition(
                base_path, branch_def_id=parent_def_id,
            )
        except KeyError:
            parent_row = None
        except Exception:
            logger.exception(
                "selector dispatch | parent branch_definitions read "
                "crashed | goal=%s bvid=%s parent=%s",
                goal_id, bvid, parent_def_id,
            )
            parent_row = None

    # Merge identity fields. Snapshot wins on graph fields; parent
    # row wins on identity fields (name/description/author). If the
    # parent row is missing (rare — could happen if the def was
    # purged but the version row remains), fall back to a synthetic
    # name derived from the branch_def_id so validate() passes and
    # the selector can still run.
    enriched: dict[str, Any] = dict(snapshot)
    if parent_row:
        for k in ("name", "description", "author", "visibility",
                  "domain_id", "tags"):
            if not enriched.get(k) and parent_row.get(k) is not None:
                enriched[k] = parent_row[k]
    if not enriched.get("name"):
        enriched["name"] = parent_def_id or f"selector_{bvid}"

    try:
        branch_def = BranchDefinition.from_dict(enriched)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        return {
            "ok": False,
            "error_kind": "selector_snapshot_drift",
            "error": (
                f"selector snapshot {bvid!r} cannot be reconstructed: "
                f"{exc}. Republish at the current schema version."
            ),
            "branch_version_id": bvid,
        }

    # Provider resolution: explicit ``provider_call`` kwarg wins
    # (tests inject a deterministic stub); otherwise fall back to
    # the fantasy-daemon provider stub, which routes to the
    # configured Workflow provider chain (Anthropic / Codex /
    # Ollama / etc.). Same fallback shape as
    # ``_action_run_branch_version``.
    if provider_call is None:
        try:
            from domains.fantasy_daemon.phases._provider_stub import (
                call_provider as _default_provider_call,
            )
            provider_call = _default_provider_call
        except ImportError:
            provider_call = None

    try:
        outcome = _execute_branch_core(
            base_path,
            branch=branch_def,
            inputs=inputs,
            run_name=f"selector_dispatch_for_{goal_id}",
            actor=actor,
            provider_call=provider_call,
            branch_version_id=bvid,
        )
    except Exception as exc:
        logger.exception(
            "selector dispatch failed for goal=%s bvid=%s",
            goal_id, bvid,
        )
        return {
            "ok": False,
            "error_kind": "selector_dispatch_failed",
            "error": str(exc),
            "branch_version_id": bvid,
        }

    run_id = outcome.run_id

    # Block on the background future. ``wait_for`` is a no-op when
    # ``_execute_branch_core`` completed inline (small graphs or test
    # paths where the executor pool ran synchronously); otherwise it
    # waits up to ``timeout`` for the worker to finish.
    from workflow.runs import get_run, wait_for
    try:
        wait_for(run_id, timeout=timeout)
    except Exception as exc:
        # TimeoutError from concurrent.futures or any other wait
        # failure collapses to a selector_timeout outcome — never
        # raise into the leaderboard caller.
        logger.warning(
            "selector run %s did not finish within %.1fs: %s",
            run_id, timeout, exc,
        )
        return {
            "ok": False,
            "error_kind": "selector_timeout",
            "error": (
                f"selector run {run_id!r} did not complete within "
                f"{timeout:.1f}s. The selector branch may be misconfigured "
                "or the provider is overloaded."
            ),
            "branch_version_id": bvid,
            "run_id": run_id,
        }

    # Re-read the run row to pick up the final output. ``outcome``
    # captures only the queued response; the actual graph output
    # lives in runs.output_json once the worker writes it.
    final = get_run(base_path, run_id)
    if final is None:
        return {
            "ok": False,
            "error_kind": "selector_run_failed",
            "error": (
                f"selector run {run_id!r} vanished from the runs DB "
                "after dispatch. Storage layer may have failed."
            ),
            "branch_version_id": bvid,
            "run_id": run_id,
        }
    status = final.get("status") or ""
    if status != "completed":
        return {
            "ok": False,
            "error_kind": "selector_run_failed",
            "error": (
                f"selector run {run_id!r} ended with status={status!r}: "
                f"{final.get('error') or '(no error message)'}"
            ),
            "branch_version_id": bvid,
            "run_id": run_id,
            "selector_status": status,
        }

    output = final.get("output") or {}
    if not isinstance(output, dict):
        return {
            "ok": False,
            "error_kind": "selector_invalid_output",
            "error": (
                f"selector run output was not a JSON object; got "
                f"{type(output).__name__}"
            ),
            "branch_version_id": bvid,
            "run_id": run_id,
        }

    parsed = _parse_ranked_entries(output)
    if parsed.get("ok"):
        result: dict[str, Any] = {
            "ok": True,
            "branch_version_id": bvid,
            "source": source,
            "run_id": run_id,
            "ranked_entries": parsed["ranked_entries"],
        }
        if fellback_from is not None:
            result["fellback_from"] = fellback_from
        return result
    return {
        "ok": False,
        "error_kind": parsed.get(
            "error_kind", "selector_invalid_output",
        ),
        "error": parsed.get("error", ""),
        "branch_version_id": bvid,
        "run_id": run_id,
    }


# ---------------------------------------------------------------------------
# Output parsing
# ---------------------------------------------------------------------------


_REQUIRED_ENTRY_KEYS = ("branch_def_id", "score")


def _parse_ranked_entries(output: dict[str, Any]) -> dict[str, Any]:
    """Pull ``ranked_entries`` out of the selector's run output.

    Accepts either:

      * ``output["ranked_entries"]`` as a list (the canonical shape).
      * ``output["ranked_entries"]`` as a JSON string that decodes to a list
        (LLM-emitted ``"[{...}]"`` from a prompt-template node that didn't
        post-process the string).

    Returns ``{ok: True, ranked_entries: [...]}`` on success or
    ``{ok: False, error_kind, error}`` on any malformation.
    """
    raw = output.get("ranked_entries")
    if raw is None:
        return {
            "ok": False,
            "error_kind": "selector_invalid_output",
            "error": (
                "selector output did not contain the required "
                "'ranked_entries' key."
            ),
        }
    entries = raw
    if isinstance(entries, str):
        # LLM-emitted JSON string — attempt to decode. Strip
        # markdown fence if present.
        candidate = entries.strip()
        if candidate.startswith("```"):
            # Strip a fenced block (```json ... ```).
            lines = candidate.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            candidate = "\n".join(lines).strip()
        try:
            decoded = json.loads(candidate)
        except (ValueError, TypeError) as exc:
            return {
                "ok": False,
                "error_kind": "selector_invalid_output",
                "error": (
                    "selector output 'ranked_entries' is a string but "
                    f"not parseable JSON: {exc}"
                ),
            }
        if isinstance(decoded, dict) and "ranked_entries" in decoded:
            # Whole JSON object was stuffed into the field. Unwrap.
            entries = decoded["ranked_entries"]
        elif isinstance(decoded, list):
            entries = decoded
        else:
            return {
                "ok": False,
                "error_kind": "selector_invalid_output",
                "error": (
                    "selector output 'ranked_entries' string decoded to "
                    f"{type(decoded).__name__}, expected list."
                ),
            }
    if not isinstance(entries, list):
        return {
            "ok": False,
            "error_kind": "selector_invalid_output",
            "error": (
                "selector output 'ranked_entries' must be a list; got "
                f"{type(entries).__name__}."
            ),
        }
    cleaned: list[dict[str, Any]] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            return {
                "ok": False,
                "error_kind": "selector_invalid_output",
                "error": (
                    f"ranked_entries[{idx}] must be an object; got "
                    f"{type(entry).__name__}."
                ),
            }
        for key in _REQUIRED_ENTRY_KEYS:
            if key not in entry:
                return {
                    "ok": False,
                    "error_kind": "selector_invalid_output",
                    "error": (
                        f"ranked_entries[{idx}] missing required key "
                        f"{key!r}. Entry keys: {sorted(entry.keys())}."
                    ),
                }
        # Normalize types so downstream consumers see consistent
        # shapes. Score is coerced to float; missing optional fields
        # become "" / None.
        try:
            score = float(entry["score"])
        except (TypeError, ValueError):
            return {
                "ok": False,
                "error_kind": "selector_invalid_output",
                "error": (
                    f"ranked_entries[{idx}].score is not coercible to "
                    f"float: {entry.get('score')!r}"
                ),
            }
        bdid = (entry.get("branch_def_id") or "").strip()
        if not bdid:
            return {
                "ok": False,
                "error_kind": "selector_invalid_output",
                "error": (
                    f"ranked_entries[{idx}].branch_def_id must be a "
                    "non-empty string."
                ),
            }
        cleaned.append({
            "branch_def_id": bdid,
            "branch_version_id": (
                entry.get("branch_version_id") or ""
            ),
            "score": round(score, 4),
            "rationale": str(entry.get("rationale") or ""),
        })
    return {"ok": True, "ranked_entries": cleaned}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_timeout(explicit: float | None) -> float:
    """Pick the selector dispatch timeout."""
    if explicit is not None:
        try:
            return max(1.0, float(explicit))
        except (TypeError, ValueError):
            pass
    import os
    raw = os.environ.get(SELECTOR_TIMEOUT_ENV, "").strip()
    if raw:
        try:
            return max(1.0, float(raw))
        except ValueError:
            pass
    return SELECTOR_TIMEOUT_S_DEFAULT


__all__ = [
    "DEFAULT_SELECTOR_BRANCH_DEF_ID",
    "DEFAULT_SELECTOR_NAME",
    "SELECTOR_TIMEOUT_S_DEFAULT",
    "SELECTOR_TIMEOUT_ENV",
    "resolve_selector_branch_version_id",
    "ensure_default_selector_published",
    "dispatch_selector",
]
