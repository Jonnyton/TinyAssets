"""Tests for the `required-tests` gate's own decision logic.

The gate decides whether every other test result blocks a merge, so its logic
needs the same scrutiny as the code it guards — a bug here fails open silently.
"""

from __future__ import annotations

import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ci_required_tests.py"
_spec = importlib.util.spec_from_file_location("ci_required_tests", _SCRIPT)
assert _spec and _spec.loader
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def _tc(**attrib) -> ET.Element:
    return ET.Element("testcase", attrib)


# ---- node id reconstruction ------------------------------------------------


def test_node_id_module_level_function():
    el = _tc(file="tests/test_x.py", classname="tests.test_x", name="test_y")
    assert gate.node_id(el) == "tests/test_x.py::test_y"


def test_node_id_inside_a_class():
    el = _tc(file="tests/test_x.py", classname="tests.test_x.TestThing", name="test_y")
    assert gate.node_id(el) == "tests/test_x.py::TestThing::test_y"


def test_node_id_normalises_windows_separators():
    el = _tc(file="tests\\smoke\\test_x.py", classname="tests.smoke.test_x", name="t")
    assert gate.node_id(el) == "tests/smoke/test_x.py::t"


def test_node_id_without_file_attribute_still_identifies_the_test():
    """A failure must never be dropped just because `file` is missing."""
    el = _tc(classname="tests.test_x.TestThing", name="test_y")
    assert gate.node_id(el) == "tests.test_x.TestThing::test_y"


# ---- quarantine file parsing -----------------------------------------------


def test_parse_quarantine_splits_tolerated_and_flaky(tmp_path):
    f = tmp_path / "q.txt"
    f.write_text(
        "# a comment\n"
        "\n"
        "tests/test_a.py::test_one\n"
        "flaky tests/test_b.py::test_two\n"
        "tests/test_c.py::test_three  # trailing comment\n",
        encoding="utf-8",
    )
    tolerated, flaky, problems = gate.parse_quarantine(f)
    assert tolerated == {"tests/test_a.py::test_one", "tests/test_c.py::test_three"}
    assert flaky == {"tests/test_b.py::test_two"}
    assert problems == []


def test_parse_quarantine_reports_malformed_lines(tmp_path):
    f = tmp_path / "q.txt"
    f.write_text("not-a-node-id\n", encoding="utf-8")
    tolerated, flaky, problems = gate.parse_quarantine(f)
    assert not tolerated and not flaky
    assert len(problems) == 1 and "not a pytest node id" in problems[0]


def test_parse_quarantine_missing_file_is_empty_not_an_error(tmp_path):
    assert gate.parse_quarantine(tmp_path / "nope.txt") == (set(), set(), [])


# ---- outcome collection ----------------------------------------------------


def _junit(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "junit.xml"
    p.write_text(f"<testsuites><testsuite>{body}</testsuite></testsuites>", encoding="utf-8")
    return p


def test_collect_outcomes_classifies_pass_fail_error(tmp_path):
    j = _junit(
        tmp_path,
        '<testcase file="tests/t.py" classname="tests.t" name="ok"/>'
        '<testcase file="tests/t.py" classname="tests.t" name="bad"><failure/></testcase>'
        '<testcase file="tests/t.py" classname="tests.t" name="boom"><error/></testcase>',
    )
    failing, ran = gate.collect_outcomes(j)
    assert failing == {"tests/t.py::bad", "tests/t.py::boom"}
    assert ran == {"tests/t.py::ok", "tests/t.py::bad", "tests/t.py::boom"}


def test_collect_outcomes_excludes_skipped_from_ran(tmp_path):
    """A skipped test proves nothing, so it must not mark a quarantine entry stale."""
    j = _junit(
        tmp_path,
        '<testcase file="tests/t.py" classname="tests.t" name="s"><skipped/></testcase>',
    )
    failing, ran = gate.collect_outcomes(j)
    assert failing == set()
    assert ran == set()


# ---- the repo's real quarantine file ---------------------------------------


def test_repo_quarantine_file_is_wellformed():
    """The committed list must always parse — a malformed line fails the gate."""
    _, _, problems = gate.parse_quarantine(gate.QUARANTINE)
    assert problems == [], f"malformed quarantine entries: {problems}"


@pytest.mark.parametrize("attr", ["QUARANTINE", "REPO_ROOT"])
def test_module_constants_exist(attr):
    assert getattr(gate, attr) is not None
