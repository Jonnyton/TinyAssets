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

A, B = "a" * 40, "b" * 40


# ---- the ledger: attempts are keyed by head SHA --------------------------------


def test_the_ledger_round_trips_and_is_idempotent_per_removal():
    ledger = {A: {"2026-10-01T01:10:00Z", "2026-10-01T01:30:00Z"}, B: {"2026-10-01T02:00:00Z"}}
    body = qa.render_ledger(ledger)
    assert body.startswith(qa.LEDGER_MARKER)
    assert qa.parse_ledger(body) == ledger
    again = qa.parse_ledger(body)
    again[A].add("2026-10-01T01:10:00Z")  # the same removal delivered twice
    assert len(again[A]) == 2


def test_a_new_head_starts_from_zero_whatever_the_old_head_did():
    ledger = qa.parse_ledger(qa.render_ledger({A: {"t1", "t2"}}))
    assert len(ledger.get(B, set())) == 0


# ---- capped: the record for THIS head and the label, both ----------------------


def test_capped_needs_the_record_for_the_current_head_and_the_label():
    record = qa.render_record(A, [], {})
    assert qa.is_capped(A, {qa.LABEL}, ["other", record])
    assert not qa.is_capped(A, set(), [record]), "removing the label retries the head"
    assert not qa.is_capped(B, {qa.LABEL}, [record]), "a new head is never capped"
    assert not qa.is_capped(A, {qa.LABEL}, ["no record was delivered"])


# ---- reading failures ----------------------------------------------------------


def test_new_failures_reads_only_the_new_failures_section():
    log = (
        "required-tests shard 1/6\tStep\t2026Z - ran: **5**\n"
        "required-tests shard 1/6\tStep\t2026Z **FAILED — this PR introduces test failures"
        " that `main` does not have.**\n"
        "required-tests shard 1/6\tStep\t2026Z \n"
        "required-tests shard 1/6\tStep\t2026Z - `tests/test_a.py::test_x`\n"
        "required-tests shard 1/6\tStep\t2026Z - `tests/test_b.py::TestK::test_y[1]`\n"
        "required-tests shard 1/6\tStep\t2026Z \n"
        "required-tests shard 1/6\tStep\t2026Z **FAILED — quarantined tests are passing now.**\n"
        "required-tests shard 1/6\tStep\t2026Z - `tests/test_stale.py::test_passes`\n"
    )
    assert qa.new_failures(log) == [
        "tests/test_a.py::test_x", "tests/test_b.py::TestK::test_y[1]"
    ]


def test_flaky_entries_are_only_the_flaky_lines():
    text = "tests/a.py::t  # broken\nflaky tests/b.py::u  # alternates\n# flaky tests/c.py::v\n"
    assert qa.flaky_entries(text) == {"tests/b.py::u"}


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"flaky": {"t"}}, "quarantined as flaky"),
        ({"pr_run": {"t"}}, "most likely this PR"),
        ({"other_prs": Counter({"t": 3})}, "3 other PR(s)"),
        ({"pr_run": None}, "no usable evidence"),
        ({}, "may not have been selected"),
    ],
)
def test_classify_reports_evidence_and_says_when_there_is_none(kwargs, fragment):
    args = {"pr_run": set(), "other_prs": Counter(), "flaky": set(), **kwargs}
    assert fragment in qa.classify("t", **args)


def test_the_record_names_unreadable_logs_instead_of_inventing_a_cause():
    body = qa.render_record(B, [(11, ["t1"]), (12, None)], {"t1": "x"})
    assert body.startswith(qa.RECORD_MARKER.format(head=B))
    assert "| `t1` | x |" in body
    assert "Logs unreadable for: `12`" in body


def test_handoff_refuses_a_head_that_is_not_a_sha(capsys):
    with pytest.raises(SystemExit):
        qa.main(["handoff", "--repo", "o/r", "--pr", "1", "--head", "main"])


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
    assert "${{" not in run["run"]
    assert '--head "$HEAD_SHA"' in run["run"]
    assert run["env"]["HEAD_SHA"] == "${{ github.event.pull_request.head.sha || inputs.head }}"


def test_enroll_asks_the_cap_before_arming_and_fails_open_on_errors():
    run = next(
        s for s in _workflow("auto-enroll-merge.yml")["jobs"]["enroll"]["steps"]
        if s.get("name") == "Enable auto-merge"
    )["run"]
    cap = run.index("python scripts/queue_attempts.py check")
    assert cap < run.index("gh pr merge \"$PR\" --repo \"$REPO\" --auto --squash")
    capped = run[cap:run.index("elif", cap)]
    assert '"$CAP_RC" -eq 3' in capped and "exit 0" in capped
    assert '--disable-auto || true' in capped, "the capped path must not fail the job"
    assert "::warning::queue-attempt cap check failed" in run
