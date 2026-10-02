"""Tests for scripts/queue_freshness.py and its workflow."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "queue_freshness", _REPO / "scripts" / "queue_freshness.py"
)
assert _spec and _spec.loader
qf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qf)

_WF = _REPO / ".github" / "workflows" / "queue-freshness.yml"


def _workflow() -> dict:
    return yaml.safe_load(_WF.read_text("utf-8"))


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
    many = [f"tests/t{i}.py" for i in range(qf.MAX_SHARED_TESTS + 1)]
    run, why = qf.probe_set(many, many)
    assert run is None and "cap" in why
    assert qf.probe_set(None, None)[0] is None


def test_only_a_failure_that_repeats_and_passes_on_main_is_blamed_on_the_pr():
    first = ["t::real", "t::flake", "t::main_broken"]
    assert qf.blame(first, {"t::real", "t::main_broken"}, {"t::main_broken"}) == ["t::real"]


def test_confirmation_reads_real_pytest_ids(tmp_path):
    """Codex on #4293: the confirmation run's default junit family dropped
    `file`, so every id read as "did not run" and blame() removed them all."""
    tree = tmp_path / "tree"
    (tree / "tests").mkdir(parents=True)
    (tree / "tests" / "test_x.py").write_text(
        "def test_ok():\n    pass\n\n\ndef test_bad():\n    assert False\n", encoding="utf-8"
    )
    ids = ["tests/test_x.py::test_ok", "tests/test_x.py::test_bad"]
    still = qf._still_failing(tree, ids, str(tmp_path), "t")
    assert still == {"tests/test_x.py::test_bad"}
    assert qf.blame(ids, still, set()) == ["tests/test_x.py::test_bad"]


def test_act_uses_the_trusted_number_and_head_never_the_artifacts():
    trusted = {"number": 5, "head": "h5"}
    forged = {"number": 9, "head": "h5", "verdict": "semantic-conflict", "why": "x"}
    assert qf.actionable(trusted, forged)["number"] == 5
    assert qf.actionable(trusted, {**forged, "head": "other"}) is None
    assert qf.actionable(trusted, {**forged, "verdict": "fresh"}) is None
    assert qf.actionable(trusted, None) is None


def test_the_comment_pings_the_author_and_is_marked_per_head_and_main():
    body = qf.render_comment(
        "dev1",
        {"head": "a" * 40, "verdict": "semantic-conflict", "why": "2 shared test file(s)",
         "failures": ["tests/x.py::test_y"]},
        "b" * 40,
    )
    assert body.startswith(qf.MARKER.format(head="a" * 40, main="b" * 40))
    assert "@dev1" in body and "`tests/x.py::test_y`" in body
    assert "Drain-Review-Diff" in body, "tell the builder their diff-key stamp survives a rebase"


def test_pr_code_runs_without_any_github_token(monkeypatch):
    for name in qf._SECRET_ENV:
        monkeypatch.setenv(name, "t0ken")
    code = "import os; print([os.environ.get(n) for n in %r])" % (qf._SECRET_ENV,)
    out = qf._run(sys.executable, "-c", code, untrusted=True)
    assert "t0ken" not in out.stdout


def test_selection_imports_conftests_without_tokens(monkeypatch, tmp_path):
    """Codex on #4293: the selector's conftest subprocess inherited GH_TOKEN."""
    monkeypatch.setenv("GH_TOKEN", "t0ken")
    seen = {}

    class _Fake:
        @staticmethod
        def select(files, root):
            seen["token"] = __import__("os").environ.get("GH_TOKEN")
            return ["tests/a.py"], []

    monkeypatch.setitem(sys.modules, "affected_tests", _Fake)
    assert qf._selection(["x.py"], tmp_path) == ["tests/a.py"]
    assert seen["token"] is None
    assert __import__("os").environ["GH_TOKEN"] == "t0ken", "restored for the trusted code"


def test_candidates_paginate_filter_base_and_order_by_queue(monkeypatch):
    def pr(n, *, armed=False, draft=False, base="main"):
        return {"id": f"id{n}", "number": n, "isDraft": draft, "headRefOid": f"h{n}",
                "baseRefName": base, "author": {"login": "u"},
                "autoMergeRequest": {"enabledAt": "t"} if armed else None}

    queue = {"entries": {"nodes": [{"pullRequest": {"number": 7}},
                                   {"pullRequest": {"number": 3}}]}}
    pages = [
        {"mergeQueue": queue, "pullRequests": {
            "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
            "nodes": [pr(1, armed=True), pr(5), pr(9, armed=True, draft=True)]}},
        {"mergeQueue": queue, "pullRequests": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [pr(3), pr(7), pr(11, armed=True, base="release")]}},
    ]
    calls = []

    def fake_graphql(query, **variables):
        calls.append(variables.get("after"))
        return {"repository": pages[len(calls) - 1]}

    monkeypatch.setattr(qf, "_graphql", fake_graphql)
    assert [p["number"] for p in qf.candidates("o/r")] == [7, 3, 1]
    assert calls == [None, "c1"]


def test_act_re_derives_a_conflict_against_current_main_without_pr_code(tmp_path):
    """A textual-conflict verdict is checked by a trusted merge-tree, not believed."""
    repo = tmp_path / "r"
    repo.mkdir()

    def git(*a):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a],
                              cwd=repo, capture_output=True, text=True, check=True).stdout.strip()

    git("init", "-q", "-b", "main")
    (repo / "f").write_text("base\n", encoding="utf-8")
    git("add", "f")
    git("commit", "-qm", "base")
    git("checkout", "-qb", "pr")
    (repo / "f").write_text("pr\n", encoding="utf-8")
    git("commit", "-qam", "pr")
    head = git("rev-parse", "HEAD")
    git("checkout", "-q", "main")
    (repo / "f").write_text("main\n", encoding="utf-8")
    git("commit", "-qam", "main")
    main = git("rev-parse", "HEAD")
    out = subprocess.run(["git", "merge-tree", "--write-tree", main, head], cwd=repo,
                         capture_output=True, text=True)
    assert out.returncode == 1, "the act job's conflict test relies on this exit code"


def test_the_workflow_gives_pr_code_no_token_and_names_artifacts_from_the_matrix():
    wf = _workflow()
    triggers = wf[True] if True in wf else wf["on"]
    assert triggers["push"]["branches"] == ["main"]
    assert wf["permissions"] == {}
    assert wf["concurrency"]["cancel-in-progress"] is False
    jobs = wf["jobs"]
    probe, act = jobs["probe"], jobs["act"]
    assert probe["permissions"] == {"contents": "read"}
    probe_env = {k for s in probe["steps"] for k in (s.get("env") or {})}
    assert not probe_env & {"GH_TOKEN", "GITHUB_TOKEN"}
    upload = next(s for s in probe["steps"] if "upload-artifact" in str(s.get("uses", "")))
    assert upload["with"]["name"] == "verdict-${{ matrix.pr.number }}"
    assert act["needs"] == ["list", "probe"]
    for job in jobs.values():
        checkout = next(s for s in job["steps"] if "actions/checkout" in str(s.get("uses", "")))
        assert checkout["with"]["persist-credentials"] is False
        assert "pull_request" not in str(checkout["with"]["ref"])
    act_runs = "\n".join(s.get("run", "") for s in act["steps"])
    assert "pip install" not in act_runs and "pytest" not in act_runs, "act must not run PR code"
    assert "queue_freshness.py act" in act_runs


def test_list_output_is_capped_json(monkeypatch, capsys):
    many = [{"number": i, "head": f"h{i}", "author": ""} for i in range(20)]
    monkeypatch.setattr(qf, "candidates", lambda repo: many)
    monkeypatch.setattr(sys, "argv", ["qf", "list", "--repo", "o/r"])
    assert qf.main() == 0
    assert len(json.loads(capsys.readouterr().out)) == qf.MAX_PROBES
