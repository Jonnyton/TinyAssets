"""Tests for the `required-tests` gate's own decision logic.

The gate decides whether every other test result blocks a merge, so its logic
needs the same scrutiny as the code it guards — a bug here fails open silently.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
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


def test_vacuity_floor_fails_small_runs():
    # A mass skip/deselect/deletion must not produce a green gate.
    msg = gate.vacuity_failure(10)
    assert msg is not None and "vacuous" in msg


def test_vacuity_floor_passes_full_runs():
    assert gate.vacuity_failure(gate.MIN_RAN_FLOOR) is None


def test_vacuity_floor_is_meaningfully_high():
    # The floor only works if it sits far above any trivial subset run.
    assert gate.MIN_RAN_FLOOR >= 5000


def test_deselect_everything_attack_is_blocked(tmp_path):
    """The exact bypass shape: keep a few passing tests, drop the rest.

    Such a run yields zero new failures and zero stale entries — green under
    the pre-2026-08-02 logic. Only the ran-count floor catches it.
    """
    suite = ET.Element("testsuite")
    for i in range(5):
        suite.append(_tc(file="tests/test_x.py", classname="tests.test_x", name=f"test_{i}"))
    junit = tmp_path / "tiny.xml"
    ET.ElementTree(suite).write(junit, encoding="utf-8")

    failing, ran = gate.collect_outcomes(junit)
    assert failing == set()  # nothing failed...
    assert len(ran) == 5  # ...because almost nothing ran
    assert gate.vacuity_failure(len(ran)) is not None  # and that is the finding


def test_repo_quarantine_file_is_wellformed():
    """The committed list must always parse — a malformed line fails the gate."""
    _, _, problems = gate.parse_quarantine(gate.QUARANTINE)
    assert problems == [], f"malformed quarantine entries: {problems}"


@pytest.mark.parametrize("attr", ["QUARANTINE", "REPO_ROOT"])
def test_module_constants_exist(attr):
    assert getattr(gate, attr) is not None


def test_node_id_collection_error_has_no_double_colon():
    """A collection error records an empty classname; the id must stay clean."""
    el = _tc(file="tests/test_x.py", classname="", name="tests.test_x")
    assert gate.node_id(el) == "tests/test_x.py::tests.test_x"


def test_min_ran_below_floor_is_rejected_at_parse_time():
    """A low `--min-ran` must fail closed, not silently disable the floor.

    Cross-family review rated this BLOCKING: argparse honours the LAST
    occurrence of a repeated flag, so `--min-ran 10700 --min-ran 1` sets the
    real floor to 1 while any check scanning for the first match still reads
    10700 — and a mass-deselected suite then merges green. Validating only in
    the workflow-shape test would leave every other caller exposed, so the
    refusal lives here, at the point of enforcement.
    """
    with pytest.raises(argparse.ArgumentTypeError) as excinfo:
        gate._min_ran_arg(str(gate.MIN_RAN_FLOOR - 1))
    assert "MIN_RAN_FLOOR" in str(excinfo.value)


def test_min_ran_at_or_above_floor_is_accepted():
    """The escape hatch is lowering MIN_RAN_FLOOR itself, in the same PR."""
    assert gate._min_ran_arg(str(gate.MIN_RAN_FLOOR)) == gate.MIN_RAN_FLOOR
    assert gate._min_ran_arg("10700") == 10700


# ---- sharding: partition ---------------------------------------------------


def test_parse_shard_accepts_in_range_and_rejects_the_rest():
    assert gate.parse_shard("1/6") == (1, 6)
    assert gate.parse_shard("6/6") == (6, 6)
    for bad in ("0/6", "7/6", "3", "a/b", "1/0"):
        with pytest.raises(argparse.ArgumentTypeError):
            gate.parse_shard(bad)


def test_every_real_test_file_has_exactly_one_owner_and_every_shard_gets_work():
    """Complete and disjoint over the repo's ACTUAL test files, at the CI count."""
    files = sorted(
        p.relative_to(gate.REPO_ROOT).as_posix()
        for p in (gate.REPO_ROOT / "tests").rglob("test_*.py")
    )
    assert len(files) > 100
    owners = {f: gate.shard_of(f, 6) for f in files}
    assert set(owners.values()) == set(range(1, 7))
    # Stable across calls and separator styles: every shard job computes the
    # partition independently, so any nondeterminism would drop or double files.
    assert all(gate.shard_of(f, 6) == owners[f] for f in files)
    assert all(gate.shard_of(f.replace("/", "\\"), 6) == owners[f] for f in files)


class _FakeConfig:
    def __init__(self, root: Path, shard: str | None):
        self.rootpath = root
        self._shard = shard

    def getoption(self, name, default=None):
        assert name == "--ci-shard"
        return self._shard


def test_ignore_collect_skips_only_other_shards_test_files(tmp_path):
    f = tmp_path / "tests" / "test_x.py"
    f.parent.mkdir()
    f.write_text("", encoding="utf-8")
    owner = gate.shard_of("tests/test_x.py", 4)
    other = owner % 4 + 1
    assert gate.pytest_ignore_collect(f, _FakeConfig(tmp_path, f"{owner}/4")) is None
    assert gate.pytest_ignore_collect(f, _FakeConfig(tmp_path, f"{other}/4")) is True
    # Unsharded runs, directories and conftests are never filtered: a conftest
    # skipped in some shard would change fixtures under that shard's tests.
    assert gate.pytest_ignore_collect(f, _FakeConfig(tmp_path, None)) is None
    assert gate.pytest_ignore_collect(f.parent, _FakeConfig(tmp_path, f"{other}/4")) is None
    for name in ("conftest.py", "__init__.py"):
        special = f.parent / name
        special.write_text("", encoding="utf-8")
        for i in range(1, 5):
            assert gate.pytest_ignore_collect(special, _FakeConfig(tmp_path, f"{i}/4")) is None


def test_real_pytest_shards_cover_every_test_exactly_once(tmp_path):
    """Drive pytest itself with `-p ci_required_tests`, the way the gate does.

    The unit tests above prove the hook's answers; this proves pytest actually
    loads the module as a plugin and honours them, so the union of the shards
    is exactly the unsharded run.
    """
    proj = tmp_path / "proj"
    (proj / "tests" / "sub").mkdir(parents=True)
    (proj / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (proj / "tests" / "conftest.py").write_text("", encoding="utf-8")
    expected = set()
    for i in range(12):
        rel = f"tests/{'sub/' if i % 3 == 0 else ''}test_m{i}.py"
        (proj / rel).write_text(
            "def test_a():\n    pass\n\n\ndef test_b():\n    pass\n", encoding="utf-8"
        )
        expected |= {f"{rel}::test_a", f"{rel}::test_b"}

    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SCRIPT.parent)
    seen: dict[str, int] = {}
    for index in (1, 2, 3):
        junit = tmp_path / f"j{index}.xml"
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                "-p", "ci_required_tests", f"--ci-shard={index}/3",
                "-o", "junit_family=xunit1", f"--junitxml={junit}", "tests",
            ],
            cwd=proj, env=env, capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        _, ran = gate.collect_outcomes(junit)
        assert ran, f"shard {index} ran nothing; the split did not spread 12 files"
        for nid in ran:
            assert nid not in seen, f"{nid} ran in shards {seen[nid]} and {index}"
            seen[nid] = index
    assert set(seen) == expected


# ---- sharding: the aggregate -----------------------------------------------


def _shard(dir_: Path, index: int, total: int, body: str | None, exit_code: int = 0) -> None:
    (dir_ / f"junit-shard-{index}.json").write_text(
        json.dumps({"shard": index, "total": total, "pytest_exit": exit_code}), encoding="utf-8"
    )
    if body is not None:
        (dir_ / f"junit-shard-{index}.xml").write_text(
            f"<testsuites><testsuite>{body}</testsuite></testsuites>", encoding="utf-8"
        )


def _cases(module: str, n: int, fail: int = 0) -> str:
    return "".join(
        f'<testcase file="tests/{module}.py" classname="tests.{module}" name="t{i}">'
        f"{'<failure/>' if i < fail else ''}</testcase>"
        for i in range(n)
    )


@pytest.fixture()
def shards(tmp_path):
    d = tmp_path / "shards"
    d.mkdir()
    return d


def _aggregate(shards: Path, expected: int = 3, min_ran: int = 1) -> int:
    return gate.aggregate(shards, expected, shards.parent / "junit.xml", min_ran)


def test_aggregate_passes_when_every_shard_is_present_and_clean(shards):
    for i in (1, 2, 3):
        _shard(shards, i, 3, _cases(f"test_s{i}", 4))
    assert _aggregate(shards) == 0
    # The union is written back as ONE junit, the shape --emit-quarantine reads.
    _, ran = gate.collect_outcomes(shards.parent / "junit.xml")
    assert len(ran) == 12


def test_aggregate_fails_on_a_missing_shard(shards, capsys):
    """The headline property: a lost shard can never read as green."""
    _shard(shards, 1, 3, _cases("test_s1", 4))
    _shard(shards, 3, 3, _cases("test_s3", 4))
    assert _aggregate(shards) == 1
    assert "missing shard(s) [2]" in capsys.readouterr().out


def test_aggregate_fails_when_a_shard_ran_a_different_split(shards):
    _shard(shards, 1, 3, _cases("test_s1", 4))
    _shard(shards, 2, 3, _cases("test_s2", 4))
    _shard(shards, 3, 4, _cases("test_s3", 4))
    assert _aggregate(shards) == 1


@pytest.mark.parametrize("exit_code", [2, 3, 4, 5])
def test_aggregate_fails_on_a_shard_exit_nothing_explains(shards, exit_code):
    _shard(shards, 1, 3, _cases("test_s1", 4))
    _shard(shards, 2, 3, _cases("test_s2", 4), exit_code=exit_code)
    _shard(shards, 3, 3, _cases("test_s3", 4))
    assert _aggregate(shards) == 1


def test_aggregate_fails_when_a_shard_wrote_no_junit(shards):
    _shard(shards, 1, 3, _cases("test_s1", 4))
    _shard(shards, 2, 3, None, exit_code=1)
    _shard(shards, 3, 3, _cases("test_s3", 4))
    assert _aggregate(shards) == 1


def test_aggregate_fails_when_a_shard_junit_is_corrupt(shards):
    for i in (1, 2, 3):
        _shard(shards, i, 3, _cases(f"test_s{i}", 4))
    (shards / "junit-shard-2.xml").write_text("<testsuites><testsu", encoding="utf-8")
    assert _aggregate(shards) == 1


def test_aggregate_fails_when_one_test_ran_in_two_shards(shards):
    _shard(shards, 1, 3, _cases("test_s1", 4))
    _shard(shards, 2, 3, _cases("test_s1", 1))
    _shard(shards, 3, 3, _cases("test_s3", 4))
    assert _aggregate(shards) == 1


def test_aggregate_fails_on_a_new_failure_in_any_shard(shards):
    _shard(shards, 1, 3, _cases("test_s1", 4))
    _shard(shards, 2, 3, _cases("test_s2", 4, fail=1), exit_code=1)
    _shard(shards, 3, 3, _cases("test_s3", 4))
    assert _aggregate(shards) == 1


def test_aggregate_applies_the_vacuity_floor_to_the_union(shards):
    for i in (1, 2, 3):
        _shard(shards, i, 3, _cases(f"test_s{i}", 4))
    assert _aggregate(shards, min_ran=13) == 1
    assert _aggregate(shards, min_ran=12) == 0


def test_shard_floor_sits_below_one_shard_of_the_full_floor():
    """A shard floor above ~1/6 of the suite would fail a healthy small shard."""
    assert 500 <= gate.MIN_RAN_FLOORS["shard"] < gate.MIN_RAN_FLOOR // 6
