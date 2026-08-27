"""Guards for scripts/quarantine_oracle.py.

The oracle exists so the quarantine drain stops guessing at Linux behaviour.
That makes ONE failure mode unacceptable above all others: silently reporting
an entry as unmatched. A wrong "NOT RUN" looks like "CI didn't run it" rather
than "the parser broke", so it would quietly send the drain back to guessing —
which is the exact problem the tool was built to remove.

It happened during development: pytest emits `file=` only under
`junit_family=xunit1`. CI uses that, a plain local run uses xunit2, and against
xunit2 every single entry reported NOT RUN. These tests pin both shapes.
"""

from __future__ import annotations

import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "quarantine_oracle.py"


def _load():
    spec = importlib.util.spec_from_file_location("quarantine_oracle", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def oracle():
    return _load()


def _case(**attrs) -> ET.Element:
    el = ET.Element("testcase")
    for k, v in attrs.items():
        if v is not None:
            el.set(k, v)
    return el


# --- node id reconstruction -------------------------------------------------


def test_xunit1_shape_with_file_and_class(oracle):
    """CI's shape: `file` present, `classname` = dotted module + class."""
    nid = oracle.node_id(_case(
        file="tests/test_attribution_calc.py",
        classname="tests.test_attribution_calc.TestComputePayoutShares",
        name="test_distributable_remainder_after_fee",
    ))
    assert nid == (
        "tests/test_attribution_calc.py::TestComputePayoutShares"
        "::test_distributable_remainder_after_fee"
    )


def test_xunit1_shape_module_level_function(oracle):
    nid = oracle.node_id(_case(
        file="tests/test_wait_for_run.py",
        classname="tests.test_wait_for_run",
        name="test_wait_for_run_caps_max_wait_at_120s",
    ))
    assert nid == "tests/test_wait_for_run.py::test_wait_for_run_caps_max_wait_at_120s"


def test_xunit2_shape_without_file_attribute(oracle):
    """The regression: a plain local run emits NO `file` attribute.

    Before this was handled, every ledger entry came back NOT RUN — the tool
    reporting "CI didn't run it" when it had simply failed to parse.
    """
    nid = oracle.node_id(_case(
        classname="tests.test_wait_for_run",
        name="test_wait_for_run_caps_max_wait_at_120s",
    ))
    assert nid == "tests/test_wait_for_run.py::test_wait_for_run_caps_max_wait_at_120s"


def test_xunit2_shape_class_split_resolved_against_the_filesystem(oracle):
    """`tests.test_x.TestY` is ambiguous — TestY could be a class OR a package.

    Resolving it against real files is what makes the split correct; guessing
    "last segment is the class" would break on any nested test package.
    """
    nid = oracle.node_id(_case(
        classname="tests.test_attribution_calc.TestComputePayoutShares",
        name="test_distributable_remainder_after_fee",
    ))
    assert nid == (
        "tests/test_attribution_calc.py::TestComputePayoutShares"
        "::test_distributable_remainder_after_fee"
    )


def test_windows_separators_are_normalised(oracle):
    nid = oracle.node_id(_case(
        file=r"tests\test_wait_for_run.py",
        classname="tests.test_wait_for_run",
        name="test_x",
    ))
    assert nid == "tests/test_wait_for_run.py::test_x"


def test_unresolvable_classname_returns_none_rather_than_a_wrong_id(oracle):
    assert oracle.node_id(_case(classname="not.a.real.module", name="test_x")) is None


# --- status classification --------------------------------------------------


def test_parse_junit_classifies_all_three_outcomes(oracle, tmp_path):
    xml = tmp_path / "j.xml"
    xml.write_text(
        '<testsuites><testsuite>'
        '<testcase classname="tests.test_wait_for_run" name="t_pass"/>'
        '<testcase classname="tests.test_wait_for_run" name="t_fail">'
        '<failure message="boom"/></testcase>'
        '<testcase classname="tests.test_wait_for_run" name="t_skip">'
        '<skipped message="no privilege"/></testcase>'
        '<testcase classname="tests.test_wait_for_run" name="t_err">'
        '<error message="collection failure"/></testcase>'
        '</testsuite></testsuites>',
        encoding="utf-8",
    )
    got = oracle.parse_junit(xml)
    base = "tests/test_wait_for_run.py::"
    assert got[base + "t_pass"] == ("passed", "")
    assert got[base + "t_fail"] == ("failed", "boom")
    assert got[base + "t_skip"] == ("skipped", "no privilege")
    # An `error` (collection failure) must count as failing, not vanish.
    assert got[base + "t_err"][0] == "failed"


def test_a_passing_quarantined_test_is_reported_as_stale(oracle, tmp_path):
    """PASSED is the load-bearing status: `required-tests` fails the gate on a
    quarantined test that passes, so missing one hands main a red gate."""
    xml = tmp_path / "j.xml"
    xml.write_text(
        '<testsuites><testsuite>'
        '<testcase classname="tests.test_wait_for_run" name="t_now_passes"/>'
        '</testsuite></testsuites>',
        encoding="utf-8",
    )
    got = oracle.parse_junit(xml)
    assert got["tests/test_wait_for_run.py::t_now_passes"] == ("passed", "")


# --- failure reason extraction ----------------------------------------------


def test_reason_prefers_detail_over_a_bare_exception_header(oracle):
    """pytest writes `AssertionError:` alone in `message` and the real
    comparison in the body. Reporting the header made ten different
    host-installer failures render as ten identical `AssertionError:` lines —
    indistinguishable from having no detail at all."""
    reason = oracle.failure_reason(
        "AssertionError: \n  \nassert 1 == 0",
        "E       AssertionError: \nE         \nE       assert 1 == 0\n"
        "tests/test_host_uptime_installers.py:516: AssertionError\n",
    )
    assert reason == "assert 1 == 0"


def test_reason_falls_back_to_the_body_when_message_is_only_a_header(oracle):
    reason = oracle.failure_reason(
        "AssertionError:",
        "E       assert 'configured_ready' == 'partial_or_invalid'\n",
    )
    assert reason == "assert 'configured_ready' == 'partial_or_invalid'"


def test_reason_keeps_an_already_informative_message(oracle):
    reason = oracle.failure_reason("KeyError: 'branch_def_id'", "")
    assert reason == "KeyError: 'branch_def_id'"


def test_reason_never_returns_empty(oracle):
    assert oracle.failure_reason("", "") == "(no detail in junit)"


def test_location_points_at_the_failing_line(oracle):
    body = ("E       assert 1 == 0\n"
            "tests/test_host_uptime_installers.py:516: AssertionError\n")
    assert oracle.failure_location(body) == (
        "tests/test_host_uptime_installers.py:516: AssertionError"
    )


# --- NOT RUN direction: which artifact to look at next -----------------------


def _drive_main(oracle, monkeypatch, capsys, tmp_path, *, argv, ledger, heavy, xml):
    """Run main() over a synthetic ledger + junit and return the printed report."""
    import sys

    junit = tmp_path / "j.xml"
    junit.write_text(xml, encoding="utf-8")
    monkeypatch.setattr(oracle, "read_ledger", lambda: list(ledger))
    monkeypatch.setattr(oracle, "read_heavy", lambda: set(heavy))
    monkeypatch.setattr(oracle, "latest_run_id", lambda _artifact: "1")
    monkeypatch.setattr(oracle, "download", lambda _r, _d, _a: junit)
    monkeypatch.setattr(sys, "argv", ["quarantine_oracle.py", *argv])
    assert oracle.main() == 0
    return capsys.readouterr().out


_VACUOUS = "<testsuites><testsuite></testsuite></testsuites>"
_HEAVY_ENTRY = "tests/test_dispatcher_queue.py::t_x"


def test_a_vacuous_heavy_artifact_does_not_point_at_itself(
    oracle, monkeypatch, capsys, tmp_path
):
    """The direction must come from the artifact ASKED for, not from results.

    Inferring it from the parsed results looked fine until the heavy artifact
    came back empty -- a collection error, or every heavy file failing to
    collect. With no heavy path among the results the inference flipped to
    "required", and a heavy-listed entry was told to "look at
    junit-heavy-tests" while junit-heavy-tests was the artifact being read.
    Circular advice, and it reads as though the entry is fine somewhere else.
    Found by cross-family review 2026-08-27.
    """
    report = _drive_main(
        oracle, monkeypatch, capsys, tmp_path,
        argv=["--artifact", oracle.HEAVY_ARTIFACT],
        ledger=[_HEAVY_ENTRY],
        heavy={"tests/test_dispatcher_queue.py"},
        xml=_VACUOUS,
    )
    assert "NOT RUN" in report
    assert oracle.HEAVY_ARTIFACT not in report, (
        "a heavy artifact must never send the reader back to the heavy artifact"
    )
    assert "no matching testcase" in report


def test_a_required_artifact_still_points_at_the_heavy_one(
    oracle, monkeypatch, capsys, tmp_path
):
    """The useful direction still works -- this is the common case."""
    report = _drive_main(
        oracle, monkeypatch, capsys, tmp_path,
        argv=["--artifact", oracle.ARTIFACT],
        ledger=[_HEAVY_ENTRY],
        heavy={"tests/test_dispatcher_queue.py"},
        xml=_VACUOUS,
    )
    assert f"look at {oracle.HEAVY_ARTIFACT}" in report


def test_an_arbitrary_junit_reports_the_lane_as_unknown(
    oracle, monkeypatch, capsys, tmp_path
):
    """--junit could be either lane. Say so instead of asserting one.

    This is the case that most invites a wrong deletion: the reader sees a
    definitive-sounding reason and prunes a valid quarantine line.
    """
    junit = tmp_path / "given.xml"
    junit.write_text(_VACUOUS, encoding="utf-8")
    report = _drive_main(
        oracle, monkeypatch, capsys, tmp_path,
        argv=["--junit", str(junit)],
        ledger=[_HEAVY_ENTRY],
        heavy={"tests/test_dispatcher_queue.py"},
        xml=_VACUOUS,
    )
    assert "unknown under --run/--junit" in report
    assert "NOT evidence" in report
