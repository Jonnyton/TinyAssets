#!/usr/bin/env python3
"""The behavioural half of the `required-tests` branch-protection gate.

Runs the test suite, then decides pass/fail against a committed quarantine
list of already-broken tests (`.github/known-failing-tests.txt`).

Why a quarantine list instead of "the suite must be green"
----------------------------------------------------------
When this gate was first run against `main` it found 65 failures and 12 errors
that predate it. Requiring a fully green suite on day one would have blocked
every PR in the repo, so the gate would have been reverted within the hour and
`main` would still have no behavioural check at all.

So the gate enforces the property that actually matters for auto-merge:

    NO PR MAY INTRODUCE A TEST FAILURE THAT MAIN DID NOT ALREADY HAVE.

Every already-broken test is enumerated by node id, in the diff, with a reason.
The list may only shrink: an entry that stops failing is a hard error, so fixed
tests cannot rot in the file and quietly re-cover a regression later.

Honesty note (same spirit as pr-scope-guard.yml)
-----------------------------------------------
A contributor CAN add their own broken test to the quarantine file to get green.
This is a declaration control, not a security boundary. What it does buy: doing
so is an explicit, reviewable line in the diff on a `.github/` path — which also
trips the scope guard's `infra-change` declaration — instead of an invisible
regression riding in on a green check.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
QUARANTINE = REPO_ROOT / ".github" / "known-failing-tests.txt"


def parse_quarantine(path: Path) -> tuple[set[str], set[str], list[str]]:
    """Return (tolerated, flaky, problems).

    Line formats (blank lines and `#` comments ignored)::

        tests/test_x.py::test_y            # tolerated failure, ratcheted
        flaky tests/test_x.py::test_z      # tolerated in BOTH directions

    A plain entry is ratcheted: it must keep failing, or the line is stale and
    must be deleted. A `flaky` entry is exempt from that ratchet because it
    genuinely alternates run to run — without the escape hatch a flaky test
    would break unrelated PRs whichever way it landed. `flaky` is deliberately
    a separate, greppable keyword so the count stays visible and small.
    """
    if not path.exists():
        return set(), set(), []
    tolerated: set[str] = set()
    flaky: set[str] = set()
    problems: list[str] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        is_flaky = False
        if line.startswith("flaky "):
            is_flaky = True
            line = line[len("flaky ") :].strip()
        if "::" not in line:
            problems.append(f"{path.name}:{lineno}: not a pytest node id: {line!r}")
            continue
        (flaky if is_flaky else tolerated).add(line)
    return tolerated, flaky, problems


def node_id(testcase: ET.Element) -> str:
    """Rebuild the canonical pytest node id from an xunit1 <testcase>.

    xunit1 records `file` (path) and `classname` (dotted module [+ class]).
    The module prefix of `classname` is redundant with `file`; whatever remains
    after stripping it is the enclosing class, if any.
    """
    file_attr = (testcase.get("file") or "").replace("\\", "/")
    name = testcase.get("name") or ""
    classname = testcase.get("classname") or ""

    if not file_attr:
        # No `file` recorded — fall back to the dotted form so the entry is at
        # least identifiable. Never silently drop a failure.
        return f"{classname}::{name}"

    module_dotted = file_attr[:-3].replace("/", ".") if file_attr.endswith(".py") else ""
    if classname == module_dotted or not module_dotted:
        return f"{file_attr}::{name}"
    if classname.startswith(module_dotted + "."):
        cls = classname[len(module_dotted) + 1 :]
        return f"{file_attr}::{cls}::{name}"
    return f"{file_attr}::{classname}::{name}"


def collect_outcomes(junit: Path) -> tuple[set[str], set[str]]:
    """Return (failing, ran) node id sets from a junit xml."""
    root = ET.parse(junit).getroot()
    failing: set[str] = set()
    ran: set[str] = set()
    for tc in root.iter("testcase"):
        nid = node_id(tc)
        # A skipped test did not execute — it can neither prove nor disprove a
        # quarantine entry, so it must not count as "ran".
        if tc.find("skipped") is not None:
            continue
        ran.add(nid)
        if tc.find("failure") is not None or tc.find("error") is not None:
            failing.add(nid)
    return failing, ran


def summarise(lines: list[str]) -> None:
    import os

    path = os.environ.get("GITHUB_STEP_SUMMARY")
    text = "\n".join(lines)
    print(text)
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--junit", default="junit.xml")
    ap.add_argument(
        "--pytest-arg",
        action="append",
        default=[],
        help="extra arg passed through to pytest (repeatable)",
    )
    ap.add_argument(
        "--emit-quarantine",
        metavar="JUNIT",
        help=(
            "Print the failing node ids from an EXISTING junit xml and exit. "
            "How .github/known-failing-tests.txt is generated — so the list is "
            "reproducible from a CI artifact, never hand-typed."
        ),
    )
    args = ap.parse_args()

    if args.emit_quarantine:
        failing, _ = collect_outcomes(Path(args.emit_quarantine))
        for nid in sorted(failing):
            print(nid)
        return 0

    junit = Path(args.junit)
    if junit.exists():
        junit.unlink()

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        "not slow",
        "-n",
        "auto",
        "--dist",
        "loadfile",
        "-q",
        "--no-header",
        "--durations=15",
        "-o",
        "junit_family=xunit1",
        f"--junitxml={junit}",
        *args.pytest_arg,
    ]
    print("+ " + " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=REPO_ROOT)
    print(f"pytest exit code: {proc.returncode}", flush=True)

    # Exit 3 = INTERNALERROR (e.g. a crashed xdist worker). When that happens the
    # run is TRUNCATED: tests are silently dropped from the report, so a
    # failure-set comparison against it is meaningless. Fail loudly instead of
    # comparing garbage. This is not theoretical — it is exactly how three
    # os.name-faking tests silently stopped a whole file from running.
    if proc.returncode == 3:
        summarise(
            [
                "### Required tests — INTERNAL ERROR",
                "",
                "pytest exited 3 (INTERNALERROR). The run was truncated, so an",
                "unknown number of tests never executed. Treating this as failure:",
                "a partial run cannot prove the absence of a regression.",
            ]
        )
        return 1

    if not junit.exists():
        summarise(
            [
                "### Required tests — NO REPORT",
                "",
                f"pytest exited {proc.returncode} but wrote no junit xml. The gate",
                "cannot verify anything, so it fails closed.",
            ]
        )
        return 1

    tolerated, flaky, problems = parse_quarantine(QUARANTINE)
    known = tolerated | flaky
    failing, ran = collect_outcomes(junit)

    new_failures = sorted(failing - known)
    # An entry that ran and did NOT fail is fixed (or renamed/deleted). Either
    # way the line is stale and must go, or the list slowly stops meaning
    # anything. Entries that did not run at all are left alone — a
    # platform-skipped test is not evidence of anything. `flaky` entries are
    # exempt by definition.
    stale = sorted(n for n in tolerated if n in ran and n not in failing)

    lines = [
        "### Required tests",
        "",
        f"- ran: **{len(ran)}**",
        f"- failing: **{len(failing)}**",
        f"- known-broken on main: **{len(tolerated)}** (+{len(flaky)} flaky)",
        f"- NEW failures: **{len(new_failures)}**",
        f"- stale quarantine entries: **{len(stale)}**",
    ]

    if problems:
        lines += ["", "**Malformed quarantine file:**", ""]
        lines += [f"- `{p}`" for p in problems]

    if new_failures:
        lines += [
            "",
            "**FAILED — this PR introduces test failures that `main` does not have.**",
            "",
        ]
        lines += [f"- `{n}`" for n in new_failures[:50]]
        if len(new_failures) > 50:
            lines.append(f"- …and {len(new_failures) - 50} more")

    if stale:
        lines += [
            "",
            "**FAILED — quarantined tests are passing now. Delete these lines from",
            f"`{QUARANTINE.relative_to(REPO_ROOT).as_posix()}`:**",
            "",
        ]
        lines += [f"- `{n}`" for n in stale[:50]]
        if len(stale) > 50:
            lines.append(f"- …and {len(stale) - 50} more")

    if not new_failures and not stale and not problems:
        # ASCII only: this also runs on a Windows console (cp1252), where a
        # stray emoji raises UnicodeEncodeError and takes the gate down with it.
        lines += ["", "No new failures."]

    summarise(lines)

    if new_failures or stale or problems:
        return 1

    # Guard the inverse of a green check: pytest failed for a reason the
    # comparison did not explain (collection error, usage error, no tests run).
    # Exit codes: 0 ok, 1 tests failed (already explained above), 2 interrupted,
    # 4 usage error, 5 no tests collected.
    if proc.returncode not in (0, 1):
        summarise(
            [
                "",
                f"**FAILED — pytest exited {proc.returncode} with no new test failures",
                "to explain it (usage error, interruption, or nothing collected).**",
            ]
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
