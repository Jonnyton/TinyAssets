"""Branch evaluation and iteration hooks.

Covers judge_run / list_judgments / compare_runs / suggest_node_edit /
get_node_output against the acceptance criteria in
``docs/specs/community_branches_phase4.md``.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def p4_env(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    from tinyassets import universe_server as us

    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _call(us, action, **kwargs):
    return json.loads(us.extensions(action=action, **kwargs))


def _wait(run_id: str, timeout: float = 20.0) -> None:
    from tinyassets.runs import wait_for

    wait_for(run_id, timeout=timeout)


def _build_trivial_branch(us) -> str:
    """A single-node branch that always completes cleanly via mock provider.

    Keeps evaluation tests focused on eval surfaces rather than graph shape.
    """
    spec = {
        "name": "Trivial",
        "description": "Single-node test branch",
        "entry_point": "n",
        "node_defs": [
            {"node_id": "n", "display_name": "N",
             "prompt_template": "Handle: {x}", "output_keys": ["n_out"]},
        ],
        "edges": [
            {"from": "START", "to": "n"},
            {"from": "n", "to": "END"},
        ],
        "state_schema": [
            {"name": "x", "type": "str"},
            {"name": "n_out", "type": "str"},
        ],
    }
    return _call(us, "build_branch", spec_json=json.dumps(spec))["branch_def_id"]


def _run(us, bid: str, inputs: dict | None = None) -> str:
    result = _call(us, "run_branch", branch_def_id=bid,
                   inputs_json=json.dumps(inputs or {"x": "input"}))
    _wait(result["run_id"])
    return result["run_id"]


# ─────────────────────────────────────────────────────────────────────────────
# judge_run
# ─────────────────────────────────────────────────────────────────────────────


def test_judge_run_stores_judgment(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    rid = _run(us, bid)

    result = _call(us, "judge_run", run_id=rid,
                   judgment_text="Node missed the ingredient list",
                   node_id="n", tags="accuracy,prompt")
    assert result["status"] == "recorded"
    assert result["judgment_id"]
    assert result["tags"] == ["accuracy", "prompt"]


def test_judge_run_requires_run_id_and_text(p4_env):
    us, _ = p4_env
    r1 = _call(us, "judge_run", judgment_text="something")
    assert "error" in r1 and "run_id" in r1["error"]
    r2 = _call(us, "judge_run", run_id="abc")
    assert "error" in r2 and "judgment_text" in r2["error"]


def test_judge_run_rejects_missing_run(p4_env):
    us, _ = p4_env
    result = _call(us, "judge_run", run_id="deadbeef",
                   judgment_text="will not land")
    assert "error" in result


def test_judge_run_text_channel_preview(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    rid = _run(us, bid)
    result = _call(us, "judge_run", run_id=rid,
                   judgment_text="This is my judgment", node_id="n",
                   tags="tone")
    assert "text" in result
    assert "Judgment recorded" in result["text"]
    assert "node `n`" in result["text"]
    assert "tone" in result["text"]


def test_judge_run_supports_run_scoped_judgment(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    rid = _run(us, bid)
    result = _call(us, "judge_run", run_id=rid,
                   judgment_text="Whole-run complaint")
    assert result["status"] == "recorded"
    assert result["node_id"] is None
    assert "whole run" in result["text"].lower()


def test_judge_run_ledgers_the_write(p4_env):
    us, base = p4_env
    bid = _build_trivial_branch(us)
    rid = _run(us, bid)
    _call(us, "judge_run", run_id=rid,
          judgment_text="x", node_id="n")
    ledger = json.loads((Path(base) / "ledger.json").read_text("utf-8"))
    assert any(e["action"] == "judge_run" for e in ledger)


# ─────────────────────────────────────────────────────────────────────────────
# list_judgments
# ─────────────────────────────────────────────────────────────────────────────


def test_list_judgments_requires_a_filter(p4_env):
    us, _ = p4_env
    result = _call(us, "list_judgments")
    assert "error" in result


def test_list_judgments_by_run(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    rid = _run(us, bid)
    _call(us, "judge_run", run_id=rid, judgment_text="A", node_id="n")
    _call(us, "judge_run", run_id=rid, judgment_text="B")

    result = _call(us, "list_judgments", run_id=rid)
    assert result["count"] == 2
    assert "2 judgment(s)" in result["text"]


def test_list_judgments_by_node_scoped_across_runs(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    rid1 = _run(us, bid, {"x": "one"})
    rid2 = _run(us, bid, {"x": "two"})
    _call(us, "judge_run", run_id=rid1,
          judgment_text="same node, run 1", node_id="n")
    _call(us, "judge_run", run_id=rid2,
          judgment_text="same node, run 2", node_id="n")

    result = _call(us, "list_judgments", branch_def_id=bid, node_id="n")
    assert result["count"] == 2


def test_list_judgments_catalog_shape(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    rid = _run(us, bid)
    _call(us, "judge_run", run_id=rid, judgment_text="t", node_id="n",
          tags="accuracy")

    result = _call(us, "list_judgments", branch_def_id=bid)
    assert "- `" in result["text"]
    assert "accuracy" in result["text"]


# ─────────────────────────────────────────────────────────────────────────────
# compare_runs
# ─────────────────────────────────────────────────────────────────────────────


def test_compare_runs_requires_both_ids(p4_env):
    us, _ = p4_env
    r1 = _call(us, "compare_runs", run_a_id="x")
    assert "error" in r1
    r2 = _call(us, "compare_runs")
    assert "error" in r2


def test_compare_runs_detects_unchanged_outputs(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    rid1 = _run(us, bid, {"x": "alpha"})
    rid2 = _run(us, bid, {"x": "alpha"})  # same input, same output

    result = _call(us, "compare_runs", run_a_id=rid1, run_b_id=rid2)
    assert "differences" in result
    # "unchanged" entries or no real differences.
    changed = [d for d in result["differences"]
               if d["change_type"] != "unchanged"]
    assert changed == []
    assert "No field-level differences" in result["text"]


def test_compare_runs_detects_changed_field(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    rid1 = _run(us, bid, {"x": "alpha"})
    rid2 = _run(us, bid, {"x": "beta"})

    result = _call(us, "compare_runs", run_a_id=rid1, run_b_id=rid2)
    changed_fields = {d["node_id"] for d in result["differences"]
                      if d["change_type"] == "changed"}
    assert "x" in changed_fields


def test_compare_runs_flags_topology_change_after_update_node(p4_env):
    """AC: `compare_runs` exposes topology_changed when branch_version
    differs between the two runs."""
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    rid1 = _run(us, bid)

    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="Refined: {x}")
    rid2 = _run(us, bid)

    result = _call(us, "compare_runs", run_a_id=rid1, run_b_id=rid2)
    assert result["topology_changed"] is True
    assert "topology changed" in result["text"]


def test_compare_runs_narrows_on_single_field(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    rid1 = _run(us, bid, {"x": "alpha"})
    rid2 = _run(us, bid, {"x": "beta"})

    result = _call(us, "compare_runs",
                   run_a_id=rid1, run_b_id=rid2, field="x")
    assert len(result["differences"]) == 1
    assert result["differences"][0]["node_id"] == "x"


# ─────────────────────────────────────────────────────────────────────────────
# suggest_node_edit
# ─────────────────────────────────────────────────────────────────────────────


def test_suggest_node_edit_bundles_context(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    rid = _run(us, bid)
    _call(us, "judge_run", run_id=rid,
          judgment_text="Too vague", node_id="n", tags="tone")

    result = _call(us, "suggest_node_edit",
                   branch_def_id=bid, node_id="n",
                   context="user wants richer output")
    assert "node" in result
    assert len(result["judgments"]) == 1
    # The text block is the framed prompt Claude.ai can act on.
    assert "Current prompt_template" in result["text"]
    assert "Handle: {x}" in result["text"]
    assert "user wants richer output" in result["text"]
    assert "update_node" in result["text"]


def test_suggest_node_edit_rejects_missing_branch_or_node(p4_env):
    us, _ = p4_env
    r1 = _call(us, "suggest_node_edit", branch_def_id="nope", node_id="n")
    assert "error" in r1

    bid = _build_trivial_branch(us)
    r2 = _call(us, "suggest_node_edit", branch_def_id=bid,
               node_id="not-a-real-node")
    assert "error" in r2


def test_suggest_node_edit_does_not_call_llm(p4_env):
    """AC: `suggest_node_edit` assembles context; it does NOT delegate
    to the writer. If it did, the tests here would trigger the provider
    stub and the result['node'] vs the framed text block would diverge.
    Here we just assert the output shape matches "context bundle",
    nothing LLM-generated in it."""
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    result = _call(us, "suggest_node_edit",
                   branch_def_id=bid, node_id="n")
    # Exactly the input node's template is present — no LLM rewrite.
    assert result["node"]["prompt_template"] == "Handle: {x}"


# ─────────────────────────────────────────────────────────────────────────────
# get_node_output
# ─────────────────────────────────────────────────────────────────────────────


def test_get_node_output_returns_captured_event(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    rid = _run(us, bid)
    result = _call(us, "get_node_output", run_id=rid, node_id="n")
    assert "error" not in result
    assert result["node_id"] == "n"
    assert result["step_index"] >= 0
    assert "text" in result
    assert "n" in result["text"]


def test_get_node_output_errors_on_unknown_node(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    rid = _run(us, bid)
    result = _call(us, "get_node_output", run_id=rid,
                   node_id="does-not-exist")
    assert "error" in result


def test_get_node_output_requires_both_ids(p4_env):
    us, _ = p4_env
    r1 = _call(us, "get_node_output", run_id="abc")
    assert "error" in r1
    r2 = _call(us, "get_node_output", node_id="n")
    assert "error" in r2


# ─────────────────────────────────────────────────────────────────────────────
# Lineage + audit — wiring from other actions
# ─────────────────────────────────────────────────────────────────────────────


def test_run_branch_records_lineage(p4_env):
    """Every run writes a run_lineage row. Second run on the same
    branch + actor points at the first run as parent."""
    us, base = p4_env
    bid = _build_trivial_branch(us)
    rid1 = _run(us, bid)
    rid2 = _run(us, bid)

    from tinyassets.runs import get_lineage

    lin1 = get_lineage(base, rid1)
    lin2 = get_lineage(base, rid2)
    assert lin1 is not None and lin2 is not None
    assert lin1["parent_run_id"] is None
    assert lin2["parent_run_id"] == rid1
    assert lin1["branch_version"] == 1
    assert lin2["branch_version"] == 1


def test_run_branch_resume_from_records_explicit_source_run(p4_env):
    """resume_from chooses the source run even when it is not the latest run."""
    us, base = p4_env
    bid = _build_trivial_branch(us)
    source_run_id = _run(us, bid, {"x": "source"})
    latest_run_id = _run(us, bid, {"x": "latest"})

    resumed = _call(
        us,
        "run_branch",
        branch_def_id=bid,
        inputs_json=json.dumps({"x": "override"}),
        resume_from=source_run_id,
    )
    _wait(resumed["run_id"])

    from tinyassets.runs import get_lineage

    lineage = get_lineage(base, resumed["run_id"])
    assert lineage is not None
    assert lineage["parent_run_id"] == source_run_id
    assert lineage["parent_run_id"] != latest_run_id
    assert resumed["resume_from"] == source_run_id


def test_run_branch_resume_from_missing_source_returns_error(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)

    result = _call(
        us,
        "run_branch",
        branch_def_id=bid,
        resume_from="missing-run-id",
    )

    assert "error" in result
    assert "resume_from" in result["error"]
    assert result["failure_class"] == "resume_from_not_found"


def test_run_branch_resume_from_carries_source_inputs_when_absent(p4_env):
    us, base = p4_env
    bid = _build_trivial_branch(us)
    source_run_id = _run(us, bid, {"x": "source-input"})

    resumed = _call(
        us,
        "run_branch",
        branch_def_id=bid,
        resume_from=source_run_id,
    )
    _wait(resumed["run_id"])

    from tinyassets.runs import get_run

    run_record = get_run(base, resumed["run_id"])
    assert run_record is not None
    assert run_record["inputs"] == {"x": "source-input"}


def test_run_branch_resume_from_cross_actor_returns_error(p4_env, monkeypatch):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "bob")
    bob_run_id = _run(us, bid, {"x": "bob"})

    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    result = _call(
        us,
        "run_branch",
        branch_def_id=bid,
        resume_from=bob_run_id,
    )

    assert "error" in result
    assert "not visible" in result["error"]
    assert result["failure_class"] == "resume_from_forbidden"


def test_run_branch_resume_from_branch_mismatch_returns_error(p4_env):
    us, _ = p4_env
    source_bid = _build_trivial_branch(us)
    target_bid = _build_trivial_branch(us)
    source_run_id = _run(us, source_bid, {"x": "source"})

    result = _call(
        us,
        "run_branch",
        branch_def_id=target_bid,
        resume_from=source_run_id,
    )

    assert "error" in result
    assert "different workflow" in result["error"]
    assert result["failure_class"] == "resume_from_branch_mismatch"


def test_update_node_records_edit_audit(p4_env):
    """Every update_node emits a node_edit_audit row."""
    us, base = p4_env
    bid = _build_trivial_branch(us)
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="Refined: {x}")

    from tinyassets.runs import list_node_edit_audits

    audits = list_node_edit_audits(base, branch_def_id=bid)
    assert len(audits) == 1
    assert audits[0]["nodes_changed"] == ["n"]
    assert audits[0]["version_before"] == 1
    assert audits[0]["version_after"] == 2
    assert audits[0]["triggered_by_judgment_id"] is None


def test_update_node_carries_judgment_attribution(p4_env):
    """When a judgment triggers the edit, the audit row records it."""
    us, base = p4_env
    bid = _build_trivial_branch(us)
    rid = _run(us, bid)
    jr = _call(us, "judge_run", run_id=rid,
               judgment_text="bad", node_id="n")
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="Better: {x}",
          triggered_by_judgment_id=jr["judgment_id"])

    from tinyassets.runs import list_node_edit_audits

    audits = list_node_edit_audits(base, branch_def_id=bid)
    assert audits[0]["triggered_by_judgment_id"] == jr["judgment_id"]


def test_run_lineage_surfaces_edits_since_parent(p4_env):
    """After update_node between two runs, the second run's lineage
    records the changed node(s)."""
    us, base = p4_env
    bid = _build_trivial_branch(us)
    _run(us, bid)
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="Refined: {x}")
    rid2 = _run(us, bid)

    from tinyassets.runs import get_lineage

    lin2 = get_lineage(base, rid2)
    assert "n" in lin2["edits_since_parent"]
    assert lin2["branch_version"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# Catalog + cross-phase smoke
# ─────────────────────────────────────────────────────────────────────────────


def test_unknown_action_catalog_lists_phase4(p4_env):
    us, _ = p4_env
    result = _call(us, "not-a-real-action")
    avail = result.get("available_actions", [])
    for a in ("judge_run", "list_judgments", "compare_runs",
              "suggest_node_edit", "get_node_output"):
        assert a in avail


def test_mission5_loop_end_to_end(p4_env):
    """Mission 5 readiness: user builds → runs → judges → edits →
    reruns → compares. This test is the full round-trip proof that
    the surfaces connect.
    """
    us, base = p4_env
    bid = _build_trivial_branch(us)

    # Run once.
    rid1 = _run(us, bid, {"x": "first try"})

    # Judge the first run.
    judgment = _call(us, "judge_run", run_id=rid1,
                     judgment_text="Not specific enough",
                     node_id="n", tags="specificity")
    assert judgment["status"] == "recorded"

    # Get the bundle for an edit proposal.
    bundle = _call(us, "suggest_node_edit",
                   branch_def_id=bid, node_id="n",
                   context="want more specific answers")
    assert len(bundle["judgments"]) == 1

    # Apply the edit with attribution.
    edit = _call(us, "update_node", branch_def_id=bid, node_id="n",
                 prompt_template="Answer concretely: {x}",
                 triggered_by_judgment_id=judgment["judgment_id"])
    assert edit["status"] == "updated"
    assert edit["version_after"] == 2

    # Rerun.
    rid2 = _run(us, bid, {"x": "first try"})

    # Compare.
    cmp = _call(us, "compare_runs", run_a_id=rid1, run_b_id=rid2)
    assert cmp["topology_changed"] is True

    # Lineage shows rid2's parent as rid1 + the edit.
    from tinyassets.runs import get_lineage

    lin = get_lineage(base, rid2)
    assert lin["parent_run_id"] == rid1
    assert "n" in lin["edits_since_parent"]
    assert lin["branch_version"] == 2


def test_judgments_survive_module_reload(p4_env):
    """AC #7: judgments persist across sessions. Reloading the module
    simulates a server restart."""
    us, base = p4_env
    bid = _build_trivial_branch(us)
    rid = _run(us, bid)
    _call(us, "judge_run", run_id=rid,
          judgment_text="persistent judgment", node_id="n")

    # Simulate restart by reloading the module.
    import importlib

    from tinyassets import universe_server as us_mod

    importlib.reload(us_mod)

    result = _call(us_mod, "list_judgments", branch_def_id=bid)
    assert result["count"] == 1
    assert "persistent judgment" in result["judgments"][0]["text"]


# ─────────────────────────────────────────────────────────────────────────────
# #50: rollback_node + list_node_versions
# ─────────────────────────────────────────────────────────────────────────────


def test_update_node_snapshots_body_in_audit(p4_env):
    """AC #50: audit row captures full pre/post NodeDefinition bodies."""
    us, base = p4_env
    bid = _build_trivial_branch(us)
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="Improved: {x}")

    from tinyassets.runs import list_node_edit_audits

    audits = list_node_edit_audits(base, branch_def_id=bid, node_id="n")
    assert len(audits) == 1
    assert audits[0]["node_before"]["prompt_template"] == "Handle: {x}"
    assert audits[0]["node_after"]["prompt_template"] == "Improved: {x}"
    assert audits[0]["edit_kind"] == "update"


def test_list_node_versions_returns_history(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="v2: {x}")
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="v3: {x}")

    result = _call(us, "list_node_versions",
                   branch_def_id=bid, node_id="n")
    assert result["current_version"] == 3
    versions = {v["version"] for v in result["versions"]}
    assert {1, 2, 3}.issubset(versions)
    assert "| Version" in result["text"]
    assert "← current" in result["text"]


def test_list_node_versions_requires_ids(p4_env):
    us, _ = p4_env
    r1 = _call(us, "list_node_versions", node_id="n")
    assert "error" in r1
    r2 = _call(us, "list_node_versions", branch_def_id="x")
    assert "error" in r2


def test_rollback_node_default_rewinds_one_step(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="improved: {x}")

    result = _call(us, "rollback_node",
                   branch_def_id=bid, node_id="n")
    assert result["status"] == "rolled_back"
    assert result["version_before"] == 2
    assert result["version_after"] == 3
    assert result["restored_from_version"] == 1

    got = _call(us, "get_branch", branch_def_id=bid)
    n = next(nd for nd in got["node_defs"] if nd["node_id"] == "n")
    assert n["prompt_template"] == "Handle: {x}"


def test_rollback_node_to_specific_version(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="v2: {x}")
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="v3: {x}")
    result = _call(us, "rollback_node", branch_def_id=bid, node_id="n",
                   to_version="2")
    assert result["status"] == "rolled_back"
    assert result["restored_from_version"] == 2

    got = _call(us, "get_branch", branch_def_id=bid)
    n = next(nd for nd in got["node_defs"] if nd["node_id"] == "n")
    assert n["prompt_template"] == "v2: {x}"


def test_rollback_records_audit_row_with_rollback_kind(p4_env):
    us, base = p4_env
    bid = _build_trivial_branch(us)
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="v2: {x}")
    _call(us, "rollback_node", branch_def_id=bid, node_id="n")

    from tinyassets.runs import list_node_edit_audits

    audits = list_node_edit_audits(base, branch_def_id=bid, node_id="n")
    kinds = [a["edit_kind"] for a in audits]
    assert "rollback" in kinds
    rb = next(a for a in audits if a["edit_kind"] == "rollback")
    assert rb["node_before"]["prompt_template"] == "v2: {x}"
    assert rb["node_after"]["prompt_template"] == "Handle: {x}"


def test_rollback_is_itself_an_edit_that_can_be_undone(p4_env):
    """Critical property — forward history survives rollback."""
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="v2: {x}")
    _call(us, "rollback_node", branch_def_id=bid, node_id="n")
    result = _call(us, "rollback_node", branch_def_id=bid, node_id="n")
    assert result["status"] == "rolled_back"

    got = _call(us, "get_branch", branch_def_id=bid)
    n = next(nd for nd in got["node_defs"] if nd["node_id"] == "n")
    assert n["prompt_template"] == "v2: {x}"


def test_rollback_rejects_when_no_history(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    result = _call(us, "rollback_node", branch_def_id=bid, node_id="n")
    assert result["status"] == "rejected"
    assert "nothing to roll back" in result["error"].lower()


def test_rollback_rejects_to_current_version(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="v2: {x}")
    result = _call(us, "rollback_node", branch_def_id=bid, node_id="n",
                   to_version="2")
    assert result["status"] == "rejected"
    assert "already at version" in result["error"].lower()


def test_rollback_rejects_unknown_version(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="v2: {x}")
    result = _call(us, "rollback_node", branch_def_id=bid, node_id="n",
                   to_version="999")
    assert result["status"] == "rejected"
    assert "no snapshot" in result["error"].lower()


def test_rollback_rejects_bad_to_version_string(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="v2: {x}")
    result = _call(us, "rollback_node", branch_def_id=bid, node_id="n",
                   to_version="not-a-number")
    assert result["status"] == "rejected"
    assert "integer" in result["error"].lower()


def test_rollback_preserves_judgments_on_runs(p4_env):
    """AC #50 carry-forward: judgments stay associated with the runs
    they targeted. Rolling back doesn't strip them."""
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    rid = _run(us, bid)
    jr = _call(us, "judge_run", run_id=rid,
               judgment_text="not quite right", node_id="n")
    assert jr["status"] == "recorded"

    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="v2: {x}")
    _call(us, "rollback_node", branch_def_id=bid, node_id="n")

    listing = _call(us, "list_judgments", run_id=rid)
    assert listing["count"] == 1
    assert "not quite right" in listing["judgments"][0]["text"]


def test_rollback_bumps_branch_version(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="v2: {x}")
    before = _call(us, "get_branch", branch_def_id=bid)["version"]
    _call(us, "rollback_node", branch_def_id=bid, node_id="n")
    after = _call(us, "get_branch", branch_def_id=bid)["version"]
    assert after == before + 1


def test_rollback_writes_ledger(p4_env):
    us, base = p4_env
    bid = _build_trivial_branch(us)
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="v2: {x}")
    _call(us, "rollback_node", branch_def_id=bid, node_id="n")
    ledger = json.loads((Path(base) / "ledger.json").read_text("utf-8"))
    assert any(e["action"] == "rollback_node" for e in ledger)


def test_rollback_text_channel_mentions_version_transition(p4_env):
    us, _ = p4_env
    bid = _build_trivial_branch(us)
    _call(us, "update_node", branch_def_id=bid, node_id="n",
          prompt_template="v2: {x}")
    result = _call(us, "rollback_node", branch_def_id=bid, node_id="n")
    assert "Rolled back" in result["text"]
    assert "v1" in result["text"]
    assert "v3" in result["text"]


def test_unknown_action_catalog_lists_rollback_actions(p4_env):
    us, _ = p4_env
    result = _call(us, "not-a-real-action")
    avail = result.get("available_actions", [])
    assert "rollback_node" in avail
    assert "list_node_versions" in avail
