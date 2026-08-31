"""The census that makes a green local run declare what it did not cover.

Two halves are tested here. The CLASSIFIER is pure and gets a table, including
the cases a naive substring test gets wrong -- that matters because the whole
gate is built on the reason string, and a classifier that reads "windowsill" as
Windows would quietly file real holes under the wrong heading. The PLUGIN gets
a real pytest run against a synthetic file with a skip, an xfail and a pass, in
a subprocess, because the JSON shape is a contract with pytest's report objects
and a hand-built fake would only prove that this module agrees with itself.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_script():
    """`scripts/` is a package here, but load by path anyway: the census must
    keep working when it is invoked as a plain file, which is how a gate runs
    it."""
    path = _REPO_ROOT / "scripts" / "skip_census.py"
    spec = importlib.util.spec_from_file_location("skip_census_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered BEFORE execution: `@dataclass` resolves annotations through
    # `sys.modules[cls.__module__]`, which is None for a module that is only
    # half-imported.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sc = _load_script()


# ---------------------------------------------------------------------------
# 1. the classifier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        # -- platform: this host cannot run it, whoever installs what --------
        ("the real handles are POSIX-only", sc.CLASS_PLATFORM),
        ("Windows MAX_PATH: run with a shorter --basetemp", sc.CLASS_PLATFORM),
        ("needs bwrap, which is Linux-only", sc.CLASS_PLATFORM),
        ("os.name is not 'posix' here", sc.CLASS_PLATFORM),
        ("a real symlink needs a privilege this account lacks", sc.CLASS_PLATFORM),
        ("reads /proc/self/fd, which this kernel does not have", sc.CLASS_PLATFORM),
        ("dir_fd is unsupported on this platform", sc.CLASS_PLATFORM),
        ("only on nt", sc.CLASS_PLATFORM),
        # -- missing tool: a cross-platform binary that is simply absent -----
        ("the chain is git; there is none here", sc.CLASS_MISSING_TOOL),
        ("no node on PATH", sc.CLASS_MISSING_TOOL),
        ("actionlint is not installed", sc.CLASS_MISSING_TOOL),
        ("requires docker", sc.CLASS_MISSING_TOOL),
        # -- env: a credential or a network this box does not have -----------
        ("no ANTHROPIC_API_KEY in the environment", sc.CLASS_ENV),
        ("needs a live network", sc.CLASS_ENV),
        ("the vault is not reachable from here", sc.CLASS_ENV),
        ("runs only against the deployed droplet", sc.CLASS_ENV),
        # -- other: everything the reason does not explain -------------------
        ("unconditional skip", sc.CLASS_OTHER),
        ("flaky under load; tracked in a concern", sc.CLASS_OTHER),
        ("", sc.CLASS_OTHER),
        # -- the naive-substring traps ---------------------------------------
        # 'windows' inside a word, 'nt' inside a word, 'git' inside a word:
        # a substring classifier files all three as host holes they are not.
        ("the sun through the windowsill", sc.CLASS_OTHER),
        ("the count is off by one", sc.CLASS_OTHER),
        ("legitimate reason with no host in it", sc.CLASS_OTHER),
        ("digital signature mismatch", sc.CLASS_OTHER),
    ],
)
def test_the_classifier_reads_the_reason_not_a_substring(reason: str, expected: str) -> None:
    assert sc.classify_reason(reason) == expected


def test_an_installable_tool_beats_an_incidental_platform_word() -> None:
    """The precedence, and the case that decides it.

    Both reasons name a host and an absent thing. Only one of them is fixed by
    installing something HERE, and that one must not sit in the headline count
    a Linux run is supposed to answer for. Platform-first classified the git
    row as a hole another host covers, which is how a fixable local gap becomes
    permanent.
    """
    assert sc.classify_reason("no git on this Windows box") == sc.CLASS_MISSING_TOOL
    assert sc.classify_reason("no bwrap on this host") == sc.CLASS_PLATFORM
    # A platform word with no tool in it is untouched by the precedence.
    assert sc.classify_reason("no dir_fd on this host") == sc.CLASS_PLATFORM


def test_a_tool_name_alone_is_not_a_missing_tool() -> None:
    """Otherwise every skip in a git test file lands in the wrong class."""
    assert sc.classify_reason("the git history is rewritten by this test") == sc.CLASS_OTHER


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        # Every one of these is a reason THIS suite actually skips with, taken
        # from the tree. A classifier tuned only on invented strings is tuned
        # on the wrong distribution: "pyyaml not installed" names no tool this
        # or any list could enumerate, and "/bin/rm" names no platform word.
        ("the real handles are POSIX-only", sc.CLASS_PLATFORM),
        ("the no-follow helpers are POSIX-only", sc.CLASS_PLATFORM),
        ("POSIX SQLite lock semantics", sc.CLASS_PLATFORM),
        ("unix domain sockets", sc.CLASS_PLATFORM),
        ("chmod 000 permission denial not enforced on Windows", sc.CLASS_PLATFORM),
        (
            "shell helper is exercised on POSIX CI; Windows test stays structural",
            sc.CLASS_PLATFORM,
        ),
        ("the jail cascade needs Linux and bwrap", sc.CLASS_PLATFORM),
        ("the rm(1) wrapper needs /bin/rm", sc.CLASS_PLATFORM),
        ("the install(1) wrapper needs the real binary at /usr/bin/install", sc.CLASS_PLATFORM),
        ("pyyaml not installed", sc.CLASS_MISSING_TOOL),
        ("shellcheck not installed", sc.CLASS_MISSING_TOOL),
        ("git binary not available", sc.CLASS_MISSING_TOOL),
        ("bash not on PATH", sc.CLASS_MISSING_TOOL),
        ("pre-commit hook is a bash script; no bash on PATH", sc.CLASS_MISSING_TOOL),
        ("requires the installed Docker Compose CLI grammar", sc.CLASS_MISSING_TOOL),
        ("the chain is git; there is none here", sc.CLASS_MISSING_TOOL),
    ],
)
def test_the_classifier_on_reasons_this_suite_really_uses(reason: str, expected: str) -> None:
    assert sc.classify_reason(reason) == expected


# ---------------------------------------------------------------------------
# 2. reading a report
# ---------------------------------------------------------------------------


def _document(*entries: dict, host: dict | None = None, totals: dict | None = None) -> dict:
    return {
        "schema": sc.REPORT_SCHEMA,
        "host": host or {"os_name": "nt", "sys_platform": "win32"},
        "totals": totals or {"collected": 10, "passed": 7, "skipped": 3},
        "entries": list(entries),
    }


def _entry(nodeid: str, reason: str, *, kind: str = "skip", file: str | None = None) -> dict:
    return {
        "nodeid": nodeid,
        "file": file or nodeid.split("::", 1)[0],
        "line": 1,
        "kind": kind,
        "reason": reason,
        "when": "setup",
    }


def test_a_report_from_another_schema_is_refused_not_guessed(tmp_path: Path) -> None:
    path = tmp_path / "census.json"
    path.write_text(json.dumps({"schema": "skip-census/99", "entries": []}), encoding="utf-8")
    with pytest.raises(sc.CensusError, match="schema"):
        sc.load_report(path)


def test_a_report_without_entries_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "census.json"
    path.write_text(json.dumps({"schema": sc.REPORT_SCHEMA}), encoding="utf-8")
    with pytest.raises(sc.CensusError, match="entries"):
        sc.load_report(path)


def test_the_counts_group_by_class_and_by_file() -> None:
    census = sc.census_from_document(
        _document(
            _entry("tests/test_a.py::one", "POSIX-only"),
            _entry("tests/test_a.py::two", "the real handles are posix"),
            _entry("tests/test_b.py::three", "no git here"),
            _entry("tests/test_b.py::four", "flaky"),
        )
    )
    assert census.counts() == {
        sc.CLASS_PLATFORM: 2,
        sc.CLASS_MISSING_TOOL: 1,
        sc.CLASS_ENV: 0,
        sc.CLASS_OTHER: 1,
    }
    assert census.per_file(sc.CLASS_PLATFORM) == [("tests/test_a.py", 2)]


def test_the_headline_names_the_platform_count_and_what_covers_it() -> None:
    census = sc.census_from_document(
        _document(
            _entry("tests/test_a.py::one", "POSIX-only"),
            _entry("tests/test_a.py::two", "windows MAX_PATH"),
            _entry("tests/test_b.py::three", "flaky"),
        )
    )
    text = "\n".join(sc.render(census))
    assert "2 tests skipped for platform reasons on this host" in text
    assert "UNVERIFIED here" in text
    assert "the Linux oracle covers them" in text
    # The other classes are present but are NOT what the headline counts.
    assert "other (1)" in text


# ---------------------------------------------------------------------------
# 3. the baseline, both directions
# ---------------------------------------------------------------------------


def _baseline(*nodeids: str, os_name: str = "nt") -> dict:
    return {
        "schema": sc.BASELINE_SCHEMA,
        "host": {"os_name": os_name},
        "platform_skips": [
            {"nodeid": n, "file": n.split("::", 1)[0], "kind": "skip", "reason": "posix-only"}
            for n in nodeids
        ],
    }


def test_a_new_platform_skip_is_reported_as_added() -> None:
    census = sc.census_from_document(
        _document(
            _entry("tests/test_a.py::known", "POSIX-only"),
            _entry("tests/test_a.py::fresh", "POSIX-only"),
        )
    )
    diff = sc.compare_to_baseline(census, _baseline("tests/test_a.py::known"))
    assert [e.nodeid for e in diff.added] == ["tests/test_a.py::fresh"]
    assert diff.resolved == ()


def test_a_platform_skip_that_came_back_is_reported_as_resolved() -> None:
    """The other direction: a test that used to skip here now runs. Good news,
    so it is printed and does NOT fail the gate - a passing test must never be
    something a contributor has to silence."""
    census = sc.census_from_document(_document(_entry("tests/test_a.py::known", "POSIX-only")))
    diff = sc.compare_to_baseline(
        census, _baseline("tests/test_a.py::known", "tests/test_a.py::gone")
    )
    assert diff.added == ()
    assert diff.resolved == ("tests/test_a.py::gone",)


def test_a_baseline_from_another_kind_of_host_is_an_error() -> None:
    """A Windows baseline against a Linux report calls every entry resolved and
    every Linux-only skip new. That diff is 100% noise, so it is refused rather
    than printed."""
    census = sc.census_from_document(
        _document(_entry("tests/test_a.py::one", "POSIX-only"), host={"os_name": "posix"})
    )
    with pytest.raises(sc.CensusError, match="not comparable"):
        sc.compare_to_baseline(census, _baseline("tests/test_a.py::one", os_name="nt"))


def test_a_baseline_document_is_stable_and_carries_only_platform_skips() -> None:
    census = sc.census_from_document(
        _document(
            _entry("tests/test_b.py::two", "POSIX-only"),
            _entry("tests/test_a.py::one", "POSIX-only"),
            _entry("tests/test_a.py::tool", "no git here"),
        )
    )
    document = sc.baseline_document(census)
    assert [item["nodeid"] for item in document["platform_skips"]] == [
        "tests/test_a.py::one",
        "tests/test_b.py::two",
    ]
    # No timestamp, or the file changes on every run and nobody reviews it.
    assert "generated_at" not in document
    assert json.dumps(document) == json.dumps(sc.baseline_document(census))


# ---------------------------------------------------------------------------
# 4. exit codes
# ---------------------------------------------------------------------------


def _write_report(tmp_path: Path, *entries: dict) -> Path:
    path = tmp_path / "census.json"
    path.write_text(json.dumps(_document(*entries)), encoding="utf-8")
    return path


def _run_cli(*argv: str) -> tuple[int, str]:
    buffer = StringIO()
    code = sc.main(list(argv), out=buffer)
    return code, buffer.getvalue()


def test_the_gate_passes_at_the_limit_and_fails_above_it(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        _entry("tests/test_a.py::one", "POSIX-only"),
        _entry("tests/test_a.py::two", "POSIX-only"),
    )
    code, text = _run_cli(str(report), "--assert-max-platform-skips", "2")
    assert code == 0, text
    code, text = _run_cli(str(report), "--assert-max-platform-skips", "1")
    assert code == 1
    assert "exceed the agreed maximum of 1" in text


def test_a_new_platform_skip_fails_the_gate_by_name(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        _entry("tests/test_a.py::known", "POSIX-only"),
        _entry("tests/test_a.py::fresh", "POSIX-only"),
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(_baseline("tests/test_a.py::known")), encoding="utf-8")
    code, text = _run_cli(str(report), "--baseline", str(baseline))
    assert code == 1
    assert "tests/test_a.py::fresh" in text
    assert "tests/test_a.py::known" not in text.split("NEW platform skips")[1]


def test_an_unreadable_report_exits_two_not_one(tmp_path: Path) -> None:
    """Two so a gate can tell "the census says no" from "there is no census"."""
    code, text = _run_cli(str(tmp_path / "nope.json"))
    assert code == 2
    assert "cannot read" in text


def test_a_cross_host_baseline_exits_two(tmp_path: Path) -> None:
    report = tmp_path / "census.json"
    report.write_text(
        json.dumps(
            _document(_entry("tests/test_a.py::one", "POSIX-only"), host={"os_name": "posix"})
        ),
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps(_baseline("tests/test_a.py::one")), encoding="utf-8")
    code, text = _run_cli(str(report), "--baseline", str(baseline))
    assert code == 2
    assert "not comparable" in text


def test_write_baseline_round_trips_through_the_cli(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        _entry("tests/test_a.py::one", "POSIX-only"),
        _entry("tests/test_a.py::tool", "no git here"),
    )
    baseline = tmp_path / "generated" / "baseline.json"
    code, text = _run_cli(str(report), "--write-baseline", str(baseline))
    assert code == 0
    assert "wrote 1 platform skip(s)" in text
    # The baseline it just wrote must satisfy its own gate.
    code, _ = _run_cli(str(report), "--baseline", str(baseline))
    assert code == 0


def test_quiet_prints_the_headline_and_nothing_else(tmp_path: Path) -> None:
    report = _write_report(tmp_path, _entry("tests/test_a.py::one", "POSIX-only"))
    code, text = _run_cli(str(report), "--quiet")
    assert code == 0
    assert text.strip() == sc.HEADLINE.format(count=1)


# ---------------------------------------------------------------------------
# 5. the plugin, against a real pytest run
# ---------------------------------------------------------------------------


SYNTHETIC = '''
import pytest


def test_passes():
    assert True


@pytest.mark.skip(reason="the real handles are POSIX-only")
def test_platform_skip():
    raise AssertionError("must not run")


@pytest.mark.xfail(reason="a known hole")
def test_xfails():
    raise AssertionError("expected")


def test_runtime_skip():
    pytest.skip("the chain is git; there is none here")
'''


def _pytest_json(tmp_path: Path, body: str) -> dict:
    """Run pytest on a synthetic file with the plugin loaded, in a subprocess.

    A subprocess because the plugin's contract is with pytest's own report
    objects; re-entering pytest in-process would share this session's config
    and prove nothing about a real run.
    """
    source = tmp_path / "test_synthetic_census.py"
    source.write_text(body, encoding="utf-8")
    out = tmp_path / "census.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(source),
            "-p",
            "tests.skip_census_plugin",
            "--skip-census-out",
            str(out),
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(tmp_path / "bt"),
        ],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert out.exists(), completed.stdout + completed.stderr
    document = json.loads(out.read_text(encoding="utf-8"))
    document["_stdout"] = completed.stdout
    return document


@pytest.mark.skipif(
    not (_REPO_ROOT / "tests" / "skip_census_plugin.py").exists(),
    reason="the plugin module is missing",
)
def test_the_plugin_records_a_real_runs_skips_xfails_and_totals(tmp_path: Path) -> None:
    document = _pytest_json(tmp_path, SYNTHETIC)

    assert document["schema"] == sc.REPORT_SCHEMA
    assert document["host"]["os_name"] in {"nt", "posix"}
    assert document["totals"]["passed"] == 1
    assert document["totals"]["skipped"] == 2
    assert document["totals"]["xfailed"] == 1
    assert document["totals"]["collected"] == 4

    by_name = {e["nodeid"].split("::")[-1]: e for e in document["entries"]}
    assert set(by_name) == {"test_platform_skip", "test_xfails", "test_runtime_skip"}
    assert by_name["test_platform_skip"]["kind"] == "skip"
    assert by_name["test_platform_skip"]["reason"] == "the real handles are POSIX-only"
    assert by_name["test_xfails"]["kind"] == "xfail"
    assert by_name["test_xfails"]["reason"] == "a known hole"
    # A runtime skip is raised in the call phase, not collected from a marker.
    assert by_name["test_runtime_skip"]["when"] == "call"
    # The line number points at the test, one-based like an editor.
    assert by_name["test_platform_skip"]["line"] > 1

    # The run says so on the terminal too, or the census is a file nobody opens.
    assert "skip census: 3 test(s) did not execute" in document["_stdout"]

    # And the census reads it end to end: one platform hole, one missing tool.
    document.pop("_stdout")
    census = sc.census_from_document(document)
    assert census.counts()[sc.CLASS_PLATFORM] == 1
    assert census.counts()[sc.CLASS_MISSING_TOOL] == 1
    assert census.counts()[sc.CLASS_OTHER] == 1  # the xfail


def test_the_plugin_is_inert_without_the_flag(tmp_path: Path) -> None:
    """Loading it must not change a normal run: no recorder, no file, and the
    same outcome line. Otherwise nobody will leave it in a command."""
    source = tmp_path / "test_inert.py"
    source.write_text("def test_one():\n    assert True\n", encoding="utf-8")
    unwanted = tmp_path / "census.json"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(source),
            "-p",
            "tests.skip_census_plugin",
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(tmp_path / "bt"),
        ],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert not unwanted.exists()
    assert "skip census" not in completed.stdout


def test_a_module_level_skip_is_counted_as_a_whole_file(tmp_path: Path) -> None:
    """The largest hole a census can report: a file that never collects. It
    produces no test reports at all, so only the collect hook sees it."""
    document = _pytest_json(
        tmp_path,
        'import pytest\n\n'
        'pytest.skip("the real handles are POSIX-only", allow_module_level=True)\n\n\n'
        'def test_never_collected():\n    raise AssertionError\n',
    )
    entries = document["entries"]
    assert len(entries) == 1, entries
    assert entries[0]["kind"] == "collect-skip"
    assert entries[0]["reason"] == "the real handles are POSIX-only"
    assert sc.classify_reason(entries[0]["reason"]) == sc.CLASS_PLATFORM
