"""The attribution logic behind the affected-only merge gate's miss rate.

`classify` is the part a wrong answer would mislead a merge-gate decision with,
so it is pure and tested here. The IO around it (the runs API, the junit
artifacts, the per-entry checkout) is exercised by running the script.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("miss_attr", _REPO / "scripts" / "miss_attr.py")
miss_attr = importlib.util.module_from_spec(_spec)
sys.modules["miss_attr"] = miss_attr
_spec.loader.exec_module(miss_attr)

Row = miss_attr.Row


def test_a_failure_in_the_selection_is_inside():
    rows = [Row(run_id=1, pr=10, selected_all=False,
                selected=frozenset({"tests/a.py"}), failures=("tests/a.py::t",))]
    att = miss_attr.classify(rows)
    assert (att.inside, att.outside) == (1, 0)


def test_an_all_run_has_nothing_outside():
    """ALL ran everything, so no failure of it can be a selection miss."""
    rows = [Row(run_id=1, pr=10, selected_all=True, failures=("tests/z.py::t",))]
    att = miss_attr.classify(rows)
    assert (att.inside, att.outside) == (1, 0)


def test_a_test_failing_under_unrelated_entries_is_carried_in():
    rows = [
        Row(run_id=i, pr=pr, selected_all=False, selected=frozenset({"tests/a.py"}),
            failures=("tests/ratchet.py::t",))
        for i, pr in enumerate((10, 11, 12), start=1)
    ]
    att = miss_attr.classify(rows)
    assert att.outside == 3
    assert att.clustered == 3
    assert att.unexplained == 0


def test_a_test_failing_under_one_entry_needs_attribution():
    """Not counted as carried in AND not counted as an escape -- it is named."""
    rows = [
        Row(run_id=1, pr=10, selected_all=False, selected=frozenset({"tests/a.py"}),
            failures=("tests/b.py::t",)),
        Row(run_id=2, pr=10, selected_all=False, selected=frozenset({"tests/a.py"}),
            failures=("tests/b.py::t",)),
    ]
    att = miss_attr.classify(rows)
    assert att.clustered == 0
    assert att.single_entry == {"tests/b.py::t": 2}, att.single_entry
    assert att.unexplained == 2


def test_repeated_runs_of_one_entry_are_not_several_entries():
    """The queue retries a head; two runs of pr-10 are still ONE entry.

    Counting runs instead of entries would make any retried failure look
    carried-in, which is the direction that would wrongly approve the gate.
    """
    rows = [
        Row(run_id=i, pr=10, selected_all=False, selected=frozenset(),
            failures=("tests/b.py::t",))
        for i in (1, 2, 3)
    ]
    att = miss_attr.classify(rows)
    assert att.per_test == {"tests/b.py::t": {10}}
    assert att.clustered == 0 and att.unexplained == 3


def test_the_queue_branch_pattern_yields_the_base_sha():
    base = "0" * 40
    match = miss_attr._QUEUE.match(f"gh-readonly-queue/main/pr-4162-{base}")
    assert match and match.group(1) == "4162" and match.group(2) == base


def test_a_non_queue_branch_is_not_parsed():
    assert miss_attr._QUEUE.match("gh-readonly-queue/main/pr-1-pr-2-deadbeef") is None
    assert miss_attr._QUEUE.match("main") is None
