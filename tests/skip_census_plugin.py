"""Record what a run did NOT execute, so "green" cannot be mistaken for "covered".

A Windows run of this suite skips every POSIX-only path -- descriptor handles,
``O_NOFOLLOW``, bwrap, real symlinks -- and reports the same word for it that a
full run reports: green. Six CI rounds were spent on assertions that could only
ever fail on Linux, each one green here first. The fix is not more Linux runs;
it is making a local run SAY what it left unverified.

This plugin records every skip, xfail and xpass with its reason and writes them
as JSON. ``scripts/skip_census.py`` classifies and gates that JSON.

Opt-in, and inert until asked::

    python -m pytest -p tests.skip_census_plugin --skip-census-out census.json

Loading the module registers one command-line flag and nothing else: without
``--skip-census-out`` no recorder is registered, no hook runs, and a normal run
is byte-for-byte what it was.

The report carries no timestamp on purpose. It is committed as a baseline and
diffed at review time, and a file that changes on every run is a file nobody
reads.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

#: Bumped when the JSON shape changes. `scripts/skip_census.py` refuses a
#: report it does not understand rather than guessing at missing keys.
SCHEMA = "skip-census/1"

#: The name the recorder registers under, so a second `-p` cannot double it.
RECORDER_NAME = "skip-census-recorder"

_SKIPPED_PREFIX = "Skipped: "
_XFAIL_PREFIX = "reason: "


def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup("skip census", "report what this run did not cover")
    group.addoption(
        "--skip-census-out",
        action="store",
        default=None,
        metavar="PATH",
        help=(
            "write a JSON census of skipped/xfailed tests to PATH "
            "(consumed by scripts/skip_census.py)"
        ),
    )


def pytest_configure(config: Any) -> None:
    """Register the recorder only when a destination was asked for."""
    destination = config.getoption("skip_census_out", default=None)
    if not destination:
        return
    if config.pluginmanager.hasplugin(RECORDER_NAME):
        return
    config.pluginmanager.register(SkipCensusRecorder(Path(destination)), RECORDER_NAME)


def _reason_from_longrepr(longrepr: Any) -> str:
    """The reason a skip carries, whatever shape pytest handed it over in.

    A skip's ``longrepr`` is ``(path, lineno, "Skipped: <reason>")``; a
    collect-time skip is the same tuple. Anything else is stringified rather
    than dropped -- an unexplained skip is exactly what this census is for, so
    it must appear in the report, not vanish from it.
    """
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        text = str(longrepr[2])
    elif longrepr is None:
        text = ""
    else:
        text = str(longrepr)
    if text.startswith(_SKIPPED_PREFIX):
        text = text[len(_SKIPPED_PREFIX) :]
    text = text.strip()
    return text or "unconditional skip (no reason given)"


def _reason_from_xfail(report: Any) -> str:
    text = str(getattr(report, "wasxfail", "") or "").strip()
    if text.startswith(_XFAIL_PREFIX):
        text = text[len(_XFAIL_PREFIX) :].strip()
    return text or "xfail (no reason given)"


def _file_of(report: Any) -> str:
    """The test's file, in forward slashes so a report compares across hosts."""
    location = getattr(report, "location", None)
    if isinstance(location, (tuple, list)) and location:
        return str(location[0]).replace(os.sep, "/").replace("\\", "/")
    nodeid = str(getattr(report, "nodeid", ""))
    return nodeid.split("::", 1)[0].replace("\\", "/")


def _line_of(report: Any) -> int | None:
    location = getattr(report, "location", None)
    if isinstance(location, (tuple, list)) and len(location) >= 2:
        line = location[1]
        if isinstance(line, int):
            # pytest counts from zero here; humans and editors do not.
            return line + 1
    return None


class SkipCensusRecorder:
    """Collects one entry per non-executed test and writes them at the end."""

    def __init__(self, out_path: Path) -> None:
        self.out_path = out_path
        #: nodeid -> entry. A test reports per phase (setup/call/teardown) and
        #: a skip in setup must not be counted twice if teardown also reports.
        self.entries: dict[str, dict[str, Any]] = {}
        self.totals: dict[str, int] = {
            "collected": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "xfailed": 0,
            "xpassed": 0,
        }

    # -- collection ------------------------------------------------------

    def pytest_collectreport(self, report: Any) -> None:
        """A whole module refused to import or skipped itself.

        ``pytest.skip(allow_module_level=True)`` and ``importorskip`` never
        reach a test function, so nothing else in this plugin would see them --
        and a module that skips wholesale is the largest hole a census can
        report.
        """
        if report.outcome != "skipped":
            return
        nodeid = str(report.nodeid)
        if not nodeid:
            return
        self._record(
            nodeid=nodeid,
            file=nodeid.split("::", 1)[0].replace("\\", "/"),
            line=None,
            kind="collect-skip",
            reason=_reason_from_longrepr(getattr(report, "longrepr", None)),
            when="collect",
        )
        self.totals["skipped"] += 1

    # -- execution -------------------------------------------------------

    def pytest_runtest_logreport(self, report: Any) -> None:
        wasxfail = hasattr(report, "wasxfail")
        if report.outcome == "skipped":
            if wasxfail:
                self._record(
                    nodeid=str(report.nodeid),
                    file=_file_of(report),
                    line=_line_of(report),
                    kind="xfail",
                    reason=_reason_from_xfail(report),
                    when=str(report.when),
                )
                self.totals["xfailed"] += 1
            else:
                self._record(
                    nodeid=str(report.nodeid),
                    file=_file_of(report),
                    line=_line_of(report),
                    kind="skip",
                    reason=_reason_from_longrepr(getattr(report, "longrepr", None)),
                    when=str(report.when),
                )
                self.totals["skipped"] += 1
        elif report.outcome == "passed" and wasxfail:
            self._record(
                nodeid=str(report.nodeid),
                file=_file_of(report),
                line=_line_of(report),
                kind="xpass",
                reason=_reason_from_xfail(report),
                when=str(report.when),
            )
            self.totals["xpassed"] += 1
        elif report.when == "call":
            if report.outcome == "passed":
                self.totals["passed"] += 1
            elif report.outcome == "failed":
                self.totals["failed"] += 1
        elif report.outcome == "failed":
            # setup/teardown failure: an error, not a test result.
            self.totals["errors"] += 1

    def _record(
        self,
        *,
        nodeid: str,
        file: str,
        line: int | None,
        kind: str,
        reason: str,
        when: str,
    ) -> None:
        if nodeid in self.entries:
            return
        self.entries[nodeid] = {
            "nodeid": nodeid,
            "file": file,
            "line": line,
            "kind": kind,
            "reason": reason,
            "when": when,
        }

    # -- output ----------------------------------------------------------

    def document(self) -> dict[str, Any]:
        self.totals["collected"] = (
            self.totals["passed"]
            + self.totals["failed"]
            + self.totals["skipped"]
            + self.totals["xfailed"]
            + self.totals["xpassed"]
        )
        return {
            "schema": SCHEMA,
            "host": host_facts(),
            "totals": dict(self.totals),
            "entries": [self.entries[key] for key in sorted(self.entries)],
        }

    def pytest_sessionfinish(self, session: Any, exitstatus: Any) -> None:
        document = self.document()
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        # LF explicitly: this file is diffed against one committed from another
        # host, and text-mode translation would make every Windows run of an
        # unchanged tree look like a rewrite.
        self.out_path.write_text(
            json.dumps(document, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def pytest_terminal_summary(self, terminalreporter: Any, *args: Any) -> None:
        not_run = (
            self.totals["skipped"] + self.totals["xfailed"] + self.totals["xpassed"]
        )
        terminalreporter.write_line(
            f"skip census: {not_run} test(s) did not execute; "
            f"written to {self.out_path}"
        )


def host_facts() -> dict[str, Any]:
    """What decides a platform skip. Recorded so a census cannot be read as if
    it came from the host the reader is standing on."""
    return {
        "os_name": os.name,
        "sys_platform": sys.platform,
        "python": platform.python_version(),
        "machine": platform.machine(),
    }
