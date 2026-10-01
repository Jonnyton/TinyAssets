"""Tests for scripts/queue_attempts.py and the two workflows that call it."""

from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "scripts" / "queue_attempts.py"
_spec = importlib.util.spec_from_file_location("queue_attempts", _SCRIPT)
assert _spec and _spec.loader
qa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qa)


def _pr(commit_at: str, events: list[tuple[str, str, str | None]]) -> dict:
    nodes = []
    for kind, at, reason in events:
        if kind == "removed":
            nodes.append({"__typename": "RemovedFromMergeQueueEvent", "createdAt": at,
                          "reason": reason})
        elif kind == "unlabeled":
            nodes.append({"__typename": "UnlabeledEvent", "createdAt": at,
                          "label": {"name": reason}})
        else:
            nodes.append({"__typename": "HeadRefForcePushedEvent", "createdAt": at})
    return {
        "headRefOid": "a" * 40,
        "labels": {"nodes": []},
        "commits": {"nodes": [{"commit": {"committedDate": commit_at}}]},
        "timelineItems": {"nodes": nodes},
    }


def test_two_failed_removals_on_one_head_cap_it():
    pr = _pr("2026-10-01T01:00:00Z", [
        ("removed", "2026-10-01T01:10:00Z", "failed_checks"),
        ("removed", "2026-10-01T01:30:00Z", "failed_checks"),
    ])
    assert qa.is_capped(pr)


def test_one_failure_conflicts_and_manual_removals_do_not_cap():
    pr = _pr("2026-10-01T01:00:00Z", [
        ("removed", "2026-10-01T01:10:00Z", "failed_checks"),
        ("removed", "2026-10-01T01:20:00Z", "merge_conflict"),
        ("removed", "2026-10-01T01:30:00Z", "manual"),
    ])
    assert not qa.is_capped(pr)


def test_a_new_commit_or_force_push_resets_the_count():
    failures = [("removed", "2026-10-01T01:10:00Z", "failed_checks"),
                ("removed", "2026-10-01T01:30:00Z", "failed_checks")]
    assert not qa.is_capped(_pr("2026-10-01T02:00:00Z", failures))
    pushed = failures + [("pushed", "2026-10-01T02:00:00Z", None)]
    assert not qa.is_capped(_pr("2026-10-01T00:00:00Z", pushed))
    # Failures after the push count again.
    again = pushed + [("removed", "2026-10-01T02:10:00Z", "failed_checks"),
                      ("removed", "2026-10-01T02:40:00Z", "failed_checks")]
    assert qa.is_capped(_pr("2026-10-01T00:00:00Z", again))


def test_new_failures_reads_the_gate_summary_lines():
    log = ("**FAILED — this PR introduces test failures**\n"
           "- `tests/test_a.py::test_x`\n- `tests/test_a.py::test_x`\n"
           "- `tests/test_b.py::TestK::test_y[1]`\n- `not a test`\n")
    assert qa.new_failures(log) == ["tests/test_a.py::test_x", "tests/test_b.py::TestK::test_y[1]"]


def test_flaky_entries_are_only_the_flaky_lines():
    text = "tests/a.py::t  # broken\nflaky tests/b.py::u  # alternates\n# flaky tests/c.py::v\n"
    assert qa.flaky_entries(text) == {"tests/b.py::u"}


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"flaky": {"t"}}, "quarantined as flaky"),
        ({"on_pr_run": {"t"}}, "a defect in this PR"),
        ({"other_prs": Counter({"t": 3})}, "3 other PR(s)"),
        ({}, "batch interaction"),
    ],
)
def test_classify_names_the_most_likely_cause(kwargs, fragment):
    args = {"on_pr_run": set(), "other_prs": Counter(), "flaky": set(), **kwargs}
    assert fragment in qa.classify("t", **args)


def test_the_record_carries_a_per_head_marker_and_every_test():
    body = qa.render_record(7, "b" * 40, "2026-10-01T00:00:00Z", [(11, ["t1"]), (12, ["t2"])],
                            {"t1": "x", "t2": "y"})
    assert body.startswith(qa.MARKER.format(head="b" * 40, since="2026-10-01T00:00:00Z"))
    assert "| `t1` | x |" in body and "| `t2` | y |" in body
    assert "`11`, `12`" in body


# ---- the workflows -------------------------------------------------------------


def _workflow(name: str) -> dict:
    return yaml.safe_load((_REPO / ".github" / "workflows" / name).read_text(encoding="utf-8"))


def test_handoff_runs_on_dequeue_from_the_default_branch_and_never_pr_code():
    wf = _workflow("queue-handoff.yml")
    triggers = wf[True] if True in wf else wf["on"]
    assert triggers["pull_request_target"]["types"] == ["dequeued"]
    steps = wf["jobs"]["handoff"]["steps"]
    checkout = next(s for s in steps if "actions/checkout" in str(s.get("uses", "")))
    assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"
    assert checkout["with"]["persist-credentials"] is False
    run = next(s for s in steps if "run" in s)
    assert run["run"] == 'python scripts/queue_attempts.py handoff --repo "$REPO" --pr "$PR"'
    assert "${{" not in run["run"]


def test_enroll_asks_the_cap_before_arming_and_fails_open_on_errors():
    run = next(
        s for s in _workflow("auto-enroll-merge.yml")["jobs"]["enroll"]["steps"]
        if s.get("name") == "Enable auto-merge"
    )["run"]
    cap = run.index("python scripts/queue_attempts.py check")
    assert cap < run.index("gh pr merge \"$PR\" --repo \"$REPO\" --auto --squash")
    capped = run[cap:run.index("elif", cap)]
    assert '"$CAP_RC" -eq 3' in capped and "--disable-auto" in capped and "exit 0" in capped
    assert "::warning::queue-attempt cap check failed" in run


def test_removing_the_handoff_label_grants_a_fresh_count():
    """A person who read the record and saw a flake retries without a push."""
    failures = [("removed", "2026-10-01T01:10:00Z", "failed_checks"),
                ("removed", "2026-10-01T01:30:00Z", "failed_checks")]
    other = failures + [("unlabeled", "2026-10-01T01:40:00Z", "documentation")]
    assert qa.is_capped(_pr("2026-10-01T01:00:00Z", other))
    retried = failures + [("unlabeled", "2026-10-01T01:40:00Z", qa.LABEL)]
    assert not qa.is_capped(_pr("2026-10-01T01:00:00Z", retried))
