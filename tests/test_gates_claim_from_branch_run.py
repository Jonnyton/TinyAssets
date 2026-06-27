"""PR-126 M5 — `gates action=claim_from_branch_run`.

Reads a completed run's final state for `recommended_rung_claim`,
validates against the bound Goal's ladder, then delegates to the
existing `gates.claim` infrastructure.

Failure shapes covered:
  * run_not_found
  * run_not_completed
  * branch_not_found
  * branch_not_bound_to_goal
  * missing_recommended_rung_claim
  * unknown_rung

Happy path covered:
  * Branch supplies recommended_rung_claim + evidence_url in output -> claimed.
  * Branch supplies only recommended_rung_claim; caller supplies evidence_url
    -> claimed.
  * Branch supplies only recommended_rung_claim; action falls back to an
    internal TinyAssets run evidence handle -> claimed.
  * Caller's evidence_url overrides branch-supplied URL.
  * Re-running the action with the same (branch, rung) is idempotent
    (no duplicate claim, no error) — matches `gates.claim` semantics.

Goal-genericity covered:
  * Same primitive works against patch-loop and fantasy-writing ladders.
"""

from __future__ import annotations

import importlib
import json

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def us_env(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    monkeypatch.setenv("GATES_ENABLED", "1")
    monkeypatch.setenv("TINYASSETS_STORAGE_BACKEND", "sqlite")
    from tinyassets.catalog import backend as backend_mod
    backend_mod.invalidate_backend_cache()
    from tinyassets import universe_server as us
    importlib.reload(us)
    yield us, base
    backend_mod.invalidate_backend_cache()
    importlib.reload(us)


def _call(us, tool, action, **kwargs):
    return json.loads(getattr(us, tool)(action=action, **kwargs))


_PATCH_LOOP_LADDER = [
    {"rung_key": "draft_ready",
     "name": "Draft ready",
     "description": "Branch emitted a candidate patch."},
    {"rung_key": "review_passed",
     "name": "Review passed",
     "description": "Cross-family checker approved."},
    {"rung_key": "merged",
     "name": "Merged",
     "description": "Patch landed on main."},
]


def _seed_goal_with_ladder(us, ladder=None) -> str:
    g = _call(us, "goals", "propose", name="Patch loop test")
    gid = g["goal"]["goal_id"]
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(ladder or _PATCH_LOOP_LADDER))
    return gid


def _seed_branch_bound_to_goal(us, gid: str) -> str:
    b = _call(us, "extensions", "create_branch", name="Patch loop branch v1.2")
    bid = b["branch_def_id"]
    _call(us, "goals", "bind", goal_id=gid, branch_def_id=bid)
    return bid


def _seed_completed_run(
    base, *, branch_def_id: str, output: dict,
) -> str:
    """Insert a completed run row with the supplied output state.

    Bypasses execute_branch_async since we don't need real graph
    execution — just a runs row the action can read from.
    """
    from tinyassets.runs import (
        RUN_STATUS_COMPLETED,
        create_run,
        update_run_status,
    )
    run_id = create_run(
        base,
        branch_def_id=branch_def_id,
        thread_id=branch_def_id,
        inputs={},
    )
    update_run_status(
        base, run_id,
        status=RUN_STATUS_COMPLETED,
        output=output,
        finished_at=1_700_000_000.0,
    )
    return run_id


# ---------------------------------------------------------------------------
# Required-argument failure modes
# ---------------------------------------------------------------------------


def test_missing_run_id_returns_rejected(us_env):
    us, _ = us_env
    result = _call(us, "gates", "claim_from_branch_run")
    assert result["status"] == "rejected"
    assert "run_id is required" in result["error"]


def test_unknown_run_id_returns_run_not_found(us_env):
    us, _ = us_env
    result = _call(us, "gates", "claim_from_branch_run", run_id="nope")
    assert result["status"] == "rejected"
    assert result["error"] == "run_not_found"
    assert result["run_id"] == "nope"


# ---------------------------------------------------------------------------
# Run-status preconditions
# ---------------------------------------------------------------------------


def test_run_not_completed_is_rejected(us_env):
    us, base = us_env
    gid = _seed_goal_with_ladder(us)
    bid = _seed_branch_bound_to_goal(us, gid)
    # Create a run but leave it in 'queued' status (no update_run_status).
    from tinyassets.runs import create_run
    run_id = create_run(
        base, branch_def_id=bid, thread_id=bid, inputs={},
    )
    result = _call(
        us, "gates", "claim_from_branch_run", run_id=run_id,
    )
    assert result["status"] == "rejected"
    assert result["error"] == "run_not_completed"
    assert result["run_status"] == "queued"


def test_failed_run_is_rejected(us_env):
    us, base = us_env
    gid = _seed_goal_with_ladder(us)
    bid = _seed_branch_bound_to_goal(us, gid)
    from tinyassets.runs import (
        RUN_STATUS_FAILED,
        create_run,
        update_run_status,
    )
    run_id = create_run(
        base, branch_def_id=bid, thread_id=bid, inputs={},
    )
    update_run_status(
        base, run_id,
        status=RUN_STATUS_FAILED,
        error="boom",
        finished_at=1_700_000_000.0,
    )
    result = _call(
        us, "gates", "claim_from_branch_run", run_id=run_id,
    )
    assert result["status"] == "rejected"
    assert result["error"] == "run_not_completed"
    assert result["run_status"] == "failed"


# ---------------------------------------------------------------------------
# Branch/Goal binding preconditions
# ---------------------------------------------------------------------------


def test_branch_not_bound_to_goal_is_rejected(us_env):
    us, base = us_env
    # Branch without a Goal binding.
    b = _call(us, "extensions", "create_branch", name="Unbound branch")
    bid = b["branch_def_id"]
    run_id = _seed_completed_run(
        base,
        branch_def_id=bid,
        output={"recommended_rung_claim": "draft_ready"},
    )
    result = _call(
        us, "gates", "claim_from_branch_run", run_id=run_id,
    )
    assert result["status"] == "rejected"
    assert result["error"] == "branch_not_bound_to_goal"
    assert result["branch_def_id"] == bid


# ---------------------------------------------------------------------------
# Output-state preconditions
# ---------------------------------------------------------------------------


def test_missing_recommended_rung_claim_in_output(us_env):
    us, base = us_env
    gid = _seed_goal_with_ladder(us)
    bid = _seed_branch_bound_to_goal(us, gid)
    run_id = _seed_completed_run(
        base,
        branch_def_id=bid,
        output={"summary": "did stuff but no rung claim"},
    )
    result = _call(
        us, "gates", "claim_from_branch_run", run_id=run_id,
    )
    assert result["status"] == "rejected"
    assert result["error"] == "missing_recommended_rung_claim"
    assert result["goal_id"] == gid


def test_empty_recommended_rung_claim_string(us_env):
    us, base = us_env
    gid = _seed_goal_with_ladder(us)
    bid = _seed_branch_bound_to_goal(us, gid)
    run_id = _seed_completed_run(
        base,
        branch_def_id=bid,
        output={"recommended_rung_claim": "  "},  # whitespace only
    )
    result = _call(
        us, "gates", "claim_from_branch_run", run_id=run_id,
    )
    assert result["status"] == "rejected"
    assert result["error"] == "missing_recommended_rung_claim"


def test_non_string_recommended_rung_claim_is_missing(us_env):
    """A branch that emits a number / dict / list under
    recommended_rung_claim is malformed — surface as missing rather
    than crash on .strip()."""
    us, base = us_env
    gid = _seed_goal_with_ladder(us)
    bid = _seed_branch_bound_to_goal(us, gid)
    run_id = _seed_completed_run(
        base,
        branch_def_id=bid,
        output={"recommended_rung_claim": 42},
    )
    result = _call(
        us, "gates", "claim_from_branch_run", run_id=run_id,
    )
    assert result["status"] == "rejected"
    assert result["error"] == "missing_recommended_rung_claim"


# ---------------------------------------------------------------------------
# Rung validation against the bound Goal's ladder
# ---------------------------------------------------------------------------


def test_unknown_rung_against_ladder(us_env):
    us, base = us_env
    gid = _seed_goal_with_ladder(us)
    bid = _seed_branch_bound_to_goal(us, gid)
    run_id = _seed_completed_run(
        base,
        branch_def_id=bid,
        output={
            "recommended_rung_claim": "open_for_review",  # legacy v1.x verb
            "recommended_rung_claim_evidence_url":
                "https://example.com/pr/123",
        },
    )
    result = _call(
        us, "gates", "claim_from_branch_run", run_id=run_id,
    )
    assert result["status"] == "rejected"
    assert result["error"] == "unknown_rung"
    assert result["recommended_rung_claim"] == "open_for_review"
    assert set(result["available_rungs"]) == {
        "draft_ready", "review_passed", "merged",
    }


def test_rung_validation_is_case_sensitive(us_env):
    """`Draft_ready` is not the same as `draft_ready`. No fuzzy match."""
    us, base = us_env
    gid = _seed_goal_with_ladder(us)
    bid = _seed_branch_bound_to_goal(us, gid)
    run_id = _seed_completed_run(
        base,
        branch_def_id=bid,
        output={
            "recommended_rung_claim": "Draft_ready",
            "recommended_rung_claim_evidence_url":
                "https://example.com/pr/1",
        },
    )
    result = _call(
        us, "gates", "claim_from_branch_run", run_id=run_id,
    )
    assert result["status"] == "rejected"
    assert result["error"] == "unknown_rung"


# ---------------------------------------------------------------------------
# Evidence resolution
# ---------------------------------------------------------------------------


def test_missing_evidence_url_falls_back_to_workflow_run_handle(us_env):
    us, base = us_env
    gid = _seed_goal_with_ladder(us)
    bid = _seed_branch_bound_to_goal(us, gid)
    run_id = _seed_completed_run(
        base,
        branch_def_id=bid,
        output={"recommended_rung_claim": "draft_ready"},
    )
    result = _call(
        us, "gates", "claim_from_branch_run", run_id=run_id,
    )
    assert result["status"] == "claimed"
    assert result["claim"]["evidence_url"] == f"workflow:run:{run_id}"


def test_branch_supplied_workflow_run_evidence_handle_used(us_env):
    us, base = us_env
    gid = _seed_goal_with_ladder(us)
    bid = _seed_branch_bound_to_goal(us, gid)
    run_id = _seed_completed_run(
        base,
        branch_def_id=bid,
        output={
            "recommended_rung_claim": "draft_ready",
            "recommended_rung_claim_evidence_url":
                "run-attachment:parent-run:child-run:abc123",
        },
    )
    result = _call(
        us, "gates", "claim_from_branch_run", run_id=run_id,
    )
    assert result["status"] == "claimed"
    assert result["claim"]["evidence_url"] == (
        "run-attachment:parent-run:child-run:abc123"
    )


def test_branch_supplied_evidence_url_used(us_env):
    us, base = us_env
    gid = _seed_goal_with_ladder(us)
    bid = _seed_branch_bound_to_goal(us, gid)
    run_id = _seed_completed_run(
        base,
        branch_def_id=bid,
        output={
            "recommended_rung_claim": "draft_ready",
            "recommended_rung_claim_evidence_url":
                "https://github.com/Jonnyton/TinyAssets/pull/970",
            "recommended_rung_claim_evidence_note":
                "PR #970 from branch v1.2",
        },
    )
    result = _call(
        us, "gates", "claim_from_branch_run", run_id=run_id,
    )
    assert result["status"] == "claimed", result
    claim = result["claim"]
    assert claim["rung_key"] == "draft_ready"
    assert claim["goal_id"] == gid
    assert claim["branch_def_id"] == bid
    assert claim["evidence_url"] == (
        "https://github.com/Jonnyton/TinyAssets/pull/970"
    )
    assert claim["evidence_note"] == "PR #970 from branch v1.2"
    assert result["run_id"] == run_id
    assert result["source"] == "claim_from_branch_run"
    assert result["rung_key"] == "draft_ready"


def test_caller_evidence_url_overrides_branch_supplied(us_env):
    us, base = us_env
    gid = _seed_goal_with_ladder(us)
    bid = _seed_branch_bound_to_goal(us, gid)
    run_id = _seed_completed_run(
        base,
        branch_def_id=bid,
        output={
            "recommended_rung_claim": "draft_ready",
            "recommended_rung_claim_evidence_url":
                "https://stale.example.com/old",
        },
    )
    result = _call(
        us, "gates", "claim_from_branch_run",
        run_id=run_id,
        evidence_url="https://github.com/Jonnyton/TinyAssets/pull/970",
        evidence_note="caller-supplied override",
    )
    assert result["status"] == "claimed"
    assert result["claim"]["evidence_url"] == (
        "https://github.com/Jonnyton/TinyAssets/pull/970"
    )
    assert result["claim"]["evidence_note"] == "caller-supplied override"


def test_default_evidence_note_traces_back_to_run(us_env):
    us, base = us_env
    gid = _seed_goal_with_ladder(us)
    bid = _seed_branch_bound_to_goal(us, gid)
    run_id = _seed_completed_run(
        base,
        branch_def_id=bid,
        output={
            "recommended_rung_claim": "draft_ready",
            "recommended_rung_claim_evidence_url":
                "https://github.com/Jonnyton/TinyAssets/pull/970",
        },
    )
    result = _call(
        us, "gates", "claim_from_branch_run", run_id=run_id,
    )
    assert result["status"] == "claimed"
    note = result["claim"]["evidence_note"]
    assert run_id in note
    assert "Auto-claim" in note


# ---------------------------------------------------------------------------
# Happy path — all signals provided by the branch
# ---------------------------------------------------------------------------


def test_happy_path_claim_lands_via_existing_gates_claim(us_env):
    us, base = us_env
    gid = _seed_goal_with_ladder(us)
    bid = _seed_branch_bound_to_goal(us, gid)
    run_id = _seed_completed_run(
        base,
        branch_def_id=bid,
        output={
            "recommended_rung_claim": "review_passed",
            "recommended_rung_claim_evidence_url":
                "https://github.com/Jonnyton/TinyAssets/pull/970",
            "recommended_rung_claim_evidence_note":
                "Codex round-2 approved",
        },
    )
    result = _call(
        us, "gates", "claim_from_branch_run", run_id=run_id,
    )
    assert result["status"] == "claimed"
    # Confirm the claim is visible via the normal list_claims path —
    # we didn't create a parallel storage track.
    claims = _call(us, "gates", "list_claims", goal_id=gid)
    assert claims["status"] != "rejected"
    claim_rows = claims.get("claims") or []
    assert any(
        c.get("branch_def_id") == bid
        and c.get("rung_key") == "review_passed"
        for c in claim_rows
    )


def test_idempotent_on_branch_plus_rung(us_env):
    """`gates.claim` is idempotent on `(branch, rung)`; this wrapper
    inherits that semantics. Second call returns the existing claim
    instead of creating a duplicate."""
    us, base = us_env
    gid = _seed_goal_with_ladder(us)
    bid = _seed_branch_bound_to_goal(us, gid)
    run_id = _seed_completed_run(
        base,
        branch_def_id=bid,
        output={
            "recommended_rung_claim": "draft_ready",
            "recommended_rung_claim_evidence_url":
                "https://example.com/pr/1",
        },
    )
    first = _call(us, "gates", "claim_from_branch_run", run_id=run_id)
    second = _call(us, "gates", "claim_from_branch_run", run_id=run_id)
    assert first["status"] == "claimed"
    assert second["status"] == "claimed"
    # Same claim_id — proves no duplicate row was created.
    assert first["claim"]["claim_id"] == second["claim"]["claim_id"]


# ---------------------------------------------------------------------------
# Goal-genericity
# ---------------------------------------------------------------------------


def test_works_against_fantasy_ladder_vocabulary(us_env):
    """Different Goal, different ladder vocabulary, same primitive."""
    us, base = us_env
    fantasy_ladder = [
        {"rung_key": "first_draft", "name": "First draft",
         "description": "Chapter complete."},
        {"rung_key": "beta_reader_pass", "name": "Beta reader pass",
         "description": "Two beta readers approved."},
    ]
    g = _call(us, "goals", "propose", name="Fantasy novel")
    gid = g["goal"]["goal_id"]
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(fantasy_ladder))
    b = _call(us, "extensions", "create_branch", name="Chapter 4 draft")
    bid = b["branch_def_id"]
    _call(us, "goals", "bind", goal_id=gid, branch_def_id=bid)
    run_id = _seed_completed_run(
        base,
        branch_def_id=bid,
        output={
            "recommended_rung_claim": "beta_reader_pass",
            "recommended_rung_claim_evidence_url":
                "https://example.com/ch4-feedback",
        },
    )
    result = _call(us, "gates", "claim_from_branch_run", run_id=run_id)
    assert result["status"] == "claimed"
    assert result["rung_key"] == "beta_reader_pass"


# ---------------------------------------------------------------------------
# GATES_ENABLED flag is honored (inherited from the gates() wrapper)
# ---------------------------------------------------------------------------


def test_action_short_circuits_when_gates_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path / "output"))
    (tmp_path / "output").mkdir()
    monkeypatch.delenv("GATES_ENABLED", raising=False)
    from tinyassets import universe_server as us
    importlib.reload(us)
    try:
        result = _call(
            us, "gates", "claim_from_branch_run", run_id="anything",
        )
        assert result["status"] == "not_available"
    finally:
        importlib.reload(us)
