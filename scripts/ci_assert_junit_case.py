"""Require named pytest cases to be PRESENT and CLEAN in a JUnit report.

Used by `.github/workflows/linux-jail-proof.yml`. The cases it guards are
`skipif`-gated on the presence of `bwrap`, so a green pytest exit code proves
nothing about them: pytest exits 0 when a test skips. This script is the part of
the job that refuses to read a skip as a pass.

The cases are named ONE way: ``--marker real_jail`` derives them from the test
source, every test function carrying ``@pytest.mark.real_jail`` (directly or
through a module ``pytestmark``). There is no second list to keep in step --
the workflow and its shape test used to pin the same 23 node ids by hand, and
a case added to one and not the other was dropped three times.
``--list-files`` prints the files that hold them, for the pytest step.
``--nodeid`` (repeatable) still names cases explicitly. Every case is checked
on its own and the worst verdict is the exit code, so one clean case never
covers for another.

Exit codes:
    0  every case is present at least once and every occurrence has no
       <skipped>, <failure> or <error> child.
    1  some case is absent, or any occurrence skipped / failed / errored.
    2  the JUnit file is missing or not parseable (the run never got that far).

Matching is by pytest's xunit1 attributes: ``name`` is the test function name
(with any ``[param]`` suffix) and ``classname`` is the dotted module, plus
``.Class`` for methods. The nodeid is split on ``::``; the last part is the
name, the first is the file, anything between is the class path.
"""

from __future__ import annotations

import argparse
import ast
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


def _same_case(reported: str, name: str) -> bool:
    """`name` itself, or one of its parametrized cases (`name[...]`)."""
    return reported == name or (reported.startswith(name + "[") and reported.endswith("]"))


def _is_marker(node: ast.expr, marker: str) -> bool:
    """`pytest.mark.<marker>` or a call of it, e.g. `pytest.mark.<marker>(...)`."""
    if isinstance(node, ast.Call):
        node = node.func
    return (
        isinstance(node, ast.Attribute)
        and node.attr == marker
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "pytest"
    )


def _module_marked(tree: ast.Module, marker: str) -> bool:
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in stmt.targets
        ):
            values = stmt.value.elts if isinstance(stmt.value, (ast.List, ast.Tuple)) else [
                stmt.value
            ]
            if any(_is_marker(v, marker) for v in values):
                return True
    return False


def marked_cases(root: Path, marker: str, tests_dir: str = "tests") -> list[str]:
    """Node ids (without parameters) of every test carrying `pytest.mark.<marker>`.

    Read from the source, not from pytest collection, so deriving the list
    needs neither the test dependencies nor a jail. If the source and pytest
    ever disagree (a generated test, say), the case reads as ABSENT in the
    JUnit check and the job fails closed.
    """
    cases: list[str] = []
    for path in sorted((root / tests_dir).rglob("test_*.py")):
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        whole = _module_marked(tree, marker)
        for stmt in tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if stmt.name.startswith("test") and (
                    whole or any(_is_marker(d, marker) for d in stmt.decorator_list)
                ):
                    cases.append(f"{rel}::{stmt.name}")
            elif isinstance(stmt, ast.ClassDef) and stmt.name.startswith("Test"):
                in_class = whole or any(_is_marker(d, marker) for d in stmt.decorator_list)
                for item in stmt.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                        item.name.startswith("test")
                        and (in_class or any(_is_marker(d, marker) for d in item.decorator_list))
                    ):
                        cases.append(f"{rel}::{stmt.name}::{item.name}")
    return cases


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
        if _same_case(tc.get("name") or "", name) and tc.get("classname") == classname
    ]
    if not states:
        return 1, f"{nodeid} is ABSENT from {junit} (not collected or never ran)"
    bad = [s for s in states if s != "passed"]
    if bad:
        return 1, f"{nodeid} did not pass: {'; '.join(bad)}"
    return 0, f"{nodeid} executed and passed ({len(states)} occurrence(s))"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--junit", type=Path)
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--nodeid", action="append",
                       help="a case that must be present and clean; repeatable")
    which.add_argument("--marker",
                       help="every test carrying pytest.mark.<MARKER> must be present and clean")
    parser.add_argument("--list-files", action="store_true",
                        help="with --marker: print the test files holding the cases and exit")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--summary", type=Path, default=None,
                        help="append a one-line markdown verdict per case here")
    ns = parser.parse_args(argv)
    nodeids = ns.nodeid or marked_cases(ns.root, ns.marker)
    if not nodeids:
        # A marker nobody carries would make every run vacuously green.
        print(f"linux-jail-proof FAIL: no test carries pytest.mark.{ns.marker}",
              file=sys.stderr)
        return 2
    if ns.list_files:
        if not ns.marker:
            parser.error("--list-files needs --marker")
        for path in dict.fromkeys(n.split("::")[0] for n in nodeids):
            print(path)
        return 0
    if ns.junit is None:
        parser.error("--junit is required unless --list-files")
    worst = 0
    for nodeid in nodeids:
        code, message = check(ns.junit, nodeid)
        worst = max(worst, code)
        verdict = "PASS" if code == 0 else "FAIL"
        print(f"linux-jail-proof {verdict}: {message}")
        if ns.summary is not None:
            with ns.summary.open("a", encoding="utf-8") as handle:
                handle.write(f"- **{verdict}** `{nodeid}` — {message}\n")
    return worst


if __name__ == "__main__":
    sys.exit(main())
