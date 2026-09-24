"""Require one named pytest case to be PRESENT and CLEAN in a JUnit report.

Used by `.github/workflows/linux-jail-proof.yml`. The case it guards is
`skipif`-gated on the presence of `bwrap`, so a green pytest exit code proves
nothing about it: pytest exits 0 when a test skips. This script is the part of
the job that refuses to read a skip as a pass.

Exit codes:
    0  the case is present at least once and every occurrence has no
       <skipped>, <failure> or <error> child.
    1  the case is absent, or any occurrence skipped / failed / errored.
    2  the JUnit file is missing or not parseable (the run never got that far).

Matching is by pytest's xunit1 attributes: ``name`` is the test function name
(with any ``[param]`` suffix) and ``classname`` is the dotted module, plus
``.Class`` for methods. The nodeid is split on ``::``; the last part is the
name, the first is the file, anything between is the class path.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _expected_classname(nodeid: str) -> tuple[str, str]:
    parts = nodeid.split("::")
    if len(parts) < 2 or not parts[0].endswith(".py"):
        raise SystemExit(f"nodeid must look like path/to/test.py::name, got {nodeid!r}")
    module = parts[0][: -len(".py")].replace("\\", "/").replace("/", ".")
    classes = parts[1:-1]
    return ".".join([module, *classes]), parts[-1]


def _state(testcase: ET.Element) -> str:
    for tag in ("error", "failure", "skipped"):
        node = testcase.find(tag)
        if node is not None:
            message = (node.get("message") or node.text or "").strip()
            return f"{tag}: {message}" if message else tag
    return "passed"


def check(junit: Path, nodeid: str) -> tuple[int, str]:
    if not junit.is_file():
        return 2, f"no JUnit report at {junit}"
    try:
        root = ET.parse(junit).getroot()
    except ET.ParseError as exc:
        return 2, f"JUnit report at {junit} is not parseable: {exc}"
    classname, name = _expected_classname(nodeid)
    states = [
        _state(tc)
        for tc in root.iter("testcase")
        if tc.get("name") == name and tc.get("classname") == classname
    ]
    if not states:
        return 1, f"{nodeid} is ABSENT from {junit} (not collected or never ran)"
    bad = [s for s in states if s != "passed"]
    if bad:
        return 1, f"{nodeid} did not pass: {'; '.join(bad)}"
    return 0, f"{nodeid} executed and passed ({len(states)} occurrence(s))"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--junit", required=True, type=Path)
    parser.add_argument("--nodeid", required=True)
    parser.add_argument("--summary", type=Path, default=None,
                        help="append a one-line markdown verdict here")
    ns = parser.parse_args(argv)
    code, message = check(ns.junit, ns.nodeid)
    verdict = "PASS" if code == 0 else "FAIL"
    line = f"linux-jail-proof {verdict}: {message}"
    print(line)
    if ns.summary is not None:
        with ns.summary.open("a", encoding="utf-8") as handle:
            handle.write(f"- **{verdict}** `{ns.nodeid}` — {message}\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
