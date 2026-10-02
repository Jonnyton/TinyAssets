"""Tests for scripts/queue_freshness.py and its workflow."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "queue_freshness", _REPO / "scripts" / "queue_freshness.py"
)
assert _spec and _spec.loader
qf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qf)


def test_only_tests_both_sides_can_affect_are_run():
    run, why = qf.probe_set(["tests/a.py", "tests/b.py"], ["tests/b.py", "tests/c.py"])
    assert run == ["tests/b.py"]
    assert "1 shared" in why


def test_disjoint_selections_cannot_conflict_in_a_test():
    run, why = qf.probe_set(["tests/a.py"], ["tests/c.py"])
    assert run == []
    assert "no test" in why


def test_one_side_selecting_everything_runs_the_other_sides_tests():
    assert qf.probe_set(None, ["tests/c.py"])[0] == ["tests/c.py"]
    assert qf.probe_set(["tests/a.py"], None)[0] == ["tests/a.py"]


def test_a_probe_bigger_than_the_cap_is_left_to_the_queue():
    many = [f"tests/t{i}.py" for i in range(qf.MAX_CANDIDATES + 1)]
    run, why = qf.probe_set(many, many)
    assert run is None and "cap" in why
    assert qf.probe_set(None, None)[0] is None


def test_the_comment_pings_the_author_and_is_marked_per_head_and_main():
    body = qf.render_comment(
        {"author": "dev1"},
        {"head": "a" * 40, "verdict": "semantic-conflict", "why": "2 shared test file(s)",
         "failures": ["tests/x.py::test_y"]},
        "b" * 40,
    )
    assert body.startswith(qf.MARKER.format(head="a" * 40, main="b" * 40))
    assert "@dev1" in body and "`tests/x.py::test_y`" in body
    assert "Drain-Review-Diff" in body, "tell the builder their diff-key stamp survives a rebase"


def test_pr_code_runs_without_any_github_token(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "t0ken")
    monkeypatch.setenv("GITHUB_TOKEN", "t0ken")
    import sys

    out = qf._run(sys.executable, "-c",
                  "import os; print(os.environ.get('GH_TOKEN'), os.environ.get('GITHUB_TOKEN'))",
                  untrusted=True)
    assert out.stdout.split() == ["None", "None"]


def test_the_workflow_splits_running_pr_code_from_holding_write_access():
    wf = yaml.safe_load(
        (_REPO / ".github" / "workflows" / "queue-freshness.yml").read_text("utf-8")
    )
    triggers = wf[True] if True in wf else wf["on"]
    assert triggers["push"]["branches"] == ["main"]
    assert wf["permissions"] == {"contents": "read"}
    probe, act = wf["jobs"]["probe"], wf["jobs"]["act"]
    assert probe["permissions"] == {"contents": "read", "pull-requests": "read"}
    assert act["needs"] == "probe"
    assert "write" in act["permissions"].values()
    for job in (probe, act):
        checkout = next(s for s in job["steps"] if "actions/checkout" in str(s.get("uses", "")))
        assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"
        assert checkout["with"]["persist-credentials"] is False
    act_runs = "\n".join(s.get("run", "") for s in act["steps"])
    assert "pip install" not in act_runs and "pytest" not in act_runs, "act must not run PR code"
    assert "queue_freshness.py act" in act_runs


def test_only_a_failure_that_repeats_and_passes_on_main_is_blamed_on_the_pr():
    first = ["t::real", "t::flake", "t::main_broken"]
    merged_again = {"t::real", "t::main_broken"}
    main_alone = {"t::main_broken"}
    assert qf.blame(first, merged_again, main_alone) == ["t::real"]


def test_candidates_are_queued_prs_in_queue_order_then_armed_and_never_drafts(monkeypatch):
    def pr(n, *, armed=False, draft=False):
        return {"id": f"id{n}", "number": n, "isDraft": draft, "headRefOid": "h", "baseRefOid": "b",
                "mergeable": "MERGEABLE", "author": {"login": "u"},
                "autoMergeRequest": {"enabledAt": "t"} if armed else None}

    payload = {"data": {"repository": {
        "mergeQueue": {"entries": {"nodes": [{"pullRequest": {"number": 7}},
                                             {"pullRequest": {"number": 3}}]}},
        "pullRequests": {"nodes": [pr(1, armed=True), pr(3), pr(5), pr(7),
                                   pr(9, armed=True, draft=True)]},
    }}}
    import json

    monkeypatch.setattr(qf, "_gh", lambda *a: json.dumps(payload))
    assert [p["number"] for p in qf.candidates("o/r")] == [7, 3, 1]


def test_a_newer_push_never_cancels_a_running_probe():
    wf = yaml.safe_load(
        (_REPO / ".github" / "workflows" / "queue-freshness.yml").read_text("utf-8")
    )
    assert wf["concurrency"]["cancel-in-progress"] is False
