"""Tests for scripts/refresh_test_durations.py (the shard-packing table)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "refresh_test_durations.py"
_spec = importlib.util.spec_from_file_location("refresh_test_durations", _SCRIPT)
assert _spec and _spec.loader
refresh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(refresh)


def _junit(path: Path, cases: list[tuple[str, float]]) -> Path:
    body = "".join(
        f'<testcase file="{f}" name="t{i}" time="{t}"/>' for i, (f, t) in enumerate(cases)
    )
    path.write_text(f"<testsuites><testsuite>{body}</testsuite></testsuites>", encoding="utf-8")
    return path


def test_per_file_seconds_sums_cases_and_ignores_non_test_paths(tmp_path):
    junit = _junit(
        tmp_path / "j.xml",
        [("tests/test_a.py", 1.5), ("tests\\test_a.py", 0.5), ("scripts/x.py", 9.0)],
    )
    assert refresh.per_file_seconds(junit) == {"tests/test_a.py": 2.0}


def test_median_table_takes_each_files_median_and_drops_deleted_files(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("", encoding="utf-8")
    runs = [{"tests/test_a.py": 1.0, "tests/test_gone.py": 5.0},
            {"tests/test_a.py": 9.0}, {"tests/test_a.py": 2.0}]
    # One noisy run (9.0) does not move the median.
    assert refresh.median_table(runs, tmp_path) == {"tests/test_a.py": 2.0}


def test_main_writes_a_sorted_table_from_given_reports(tmp_path):
    out = tmp_path / "d.json"
    junit = _junit(tmp_path / "j.xml", [("tests/test_ci_required_tests.py", 3.0)])
    assert refresh.main(["--junit", str(junit), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == {"tests/test_ci_required_tests.py": 3.0}
