"""Advisory diff check for direct mutable reads at authority-shaped sites.

This deliberately does not claim to prove the authority invariant. It only
finds added literal SELECT/PRAGMA calls inside lexically authority-like Python
functions. Indirect reads, dynamic SQL, and semantic data flow remain review
work; legitimate reads that only narrow or reject may still be reported.
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_AUTHORITY_NAME = re.compile(
    r"(?:^|_)(?:accept|approve|authorize|claim|complete|eligible|fence|finalize|"
    r"grant|issue|lease|permit|validate|verify)(?:_|$)"
)
_SQL_READ = re.compile(r"\b(?:SELECT|PRAGMA)\b", re.IGNORECASE)
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    function: str
    sql: str


def _literal_sql(call: ast.Call) -> str | None:
    method = call.func.attr if isinstance(call.func, ast.Attribute) else ""
    if method not in {"execute", "executemany", "executescript"}:
        return None
    text = " ".join(
        node.value
        for argument in call.args
        for node in ast.walk(argument)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )
    return text if _SQL_READ.search(text) else None


def _find_findings(source: str, added_lines: set[int], path: str) -> list[Finding]:
    tree = ast.parse(source, filename=path)
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    findings: list[Finding] = []
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        sql = _literal_sql(call)
        end_line = getattr(call, "end_lineno", call.lineno)
        if sql is None or not any(call.lineno <= line <= end_line for line in added_lines):
            continue
        owners = [
            function
            for function in functions
            if function.lineno <= call.lineno <= getattr(function, "end_lineno", call.lineno)
        ]
        if not owners:
            continue
        owner = min(owners, key=lambda node: getattr(node, "end_lineno", node.lineno) - node.lineno)
        if _AUTHORITY_NAME.search(owner.name):
            findings.append(Finding(path, call.lineno, owner.name, " ".join(sql.split())[:120]))
    return findings


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout


def _diff_args(base: str, head: str | None) -> list[str]:
    return [base, head] if head else [base]


def _changed_python_paths(base: str, head: str | None) -> list[str]:
    output = _git(
        "diff", "--name-only", "--diff-filter=ACMR", *_diff_args(base, head), "--", "tinyassets"
    )
    return [path for path in output.splitlines() if path.endswith(".py")]


def _added_lines(base: str, head: str | None, path: str) -> set[int]:
    output = _git("diff", "--unified=0", *_diff_args(base, head), "--", path)
    lines: set[int] = set()
    for text in output.splitlines():
        match = _HUNK.match(text)
        if match:
            start, count = int(match.group(1)), int(match.group(2) or "1")
            lines.update(range(start, start + count))
    return lines


def _source_at(path: str, head: str | None) -> str:
    return _git("show", f"{head}:{path}") if head else Path(path).read_text(encoding="utf-8")


def _self_test() -> None:
    suspicious = """\
def grant_lease(connection):
    return connection.execute("SELECT status FROM jobs").fetchone()
"""
    assert _find_findings(suspicious, {2}, "tinyassets/example.py")
    assert not _find_findings(suspicious, {1}, "tinyassets/example.py")
    assert not _find_findings(
        suspicious.replace("grant_lease", "list_jobs"), {2}, "tinyassets/example.py"
    )
    assert not _find_findings(
        suspicious.replace("SELECT status", "INSERT INTO audit"),
        {2},
        "tinyassets/example.py",
    )
    print("authority-site advisory self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="base commit; omit only with --self-test")
    parser.add_argument("--head", help="head commit; omit to inspect the working tree")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        _self_test()
        return 0
    if not args.base:
        parser.error("--base is required unless --self-test is used")

    findings: list[Finding] = []
    for path in _changed_python_paths(args.base, args.head):
        findings.extend(
            _find_findings(
                _source_at(path, args.head),
                _added_lines(args.base, args.head, path),
                path,
            )
        )

    print(
        "ADVISORY LIMITS: direct literal SQL plus lexical function names only; "
        "no interprocedural or authority data-flow proof."
    )
    if not findings:
        print("No newly added direct mutable reads found at authority-shaped sites.")
        return 0
    for finding in findings:
        print(
            f"::warning file={finding.path},line={finding.line},title=Authority read review::"
            f"{finding.function} adds a direct mutable read: {finding.sql}"
        )
    print(
        f"Review {len(findings)} advisory finding(s); "
        "legitimate narrowing/rejection reads may remain."
    )
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError, SyntaxError) as exc:
        print(f"authority-site advisory could not complete: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
