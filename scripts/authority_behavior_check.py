#!/usr/bin/env python3
"""Did an authority-path change alter BEHAVIOR, or only comments and docstrings?

`pr-scope-guard.yml` requires an exact-head cross-family review receipt for any
edit to the authority-critical paths. That rule is right, and it stays. What was
wrong is that it fired on a path REGEX, so it could not tell a real change from
one that cannot alter behavior at all.

PR #2561 was blocked for six review rounds. Its entire authority "change" was a
one-line docstring fix repointing a spec path after archiving, plus four DELETED
copies of authority files stored under `docs/audits/`. Neither can escalate a
privilege. An unbounded prose review was demanded for a comment edit.

This makes the question executable: parse both revisions, strip docstrings and
comments, and compare the ASTs. Identical tree means no behavior changed, and
the receipt requirement can stand down for that file.

Fails CLOSED in every ambiguous case -- an added file, a deleted file, a rename,
a syntax error, a non-Python path, or an unreadable blob all count as
behavioral. The gate is only relaxed when the code is provably the same.

Note the AST is compared, not the text: reformatting, reindenting, or moving a
line all still count as no-change, while a reordered argument or a flipped
comparison does not. `ast.parse` never executes the source.
"""

from __future__ import annotations

import argparse
import ast
import subprocess


def _blob(ref: str, path: str) -> str | None:
    proc = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    """Drop docstring expressions so a prose-only edit compares equal."""
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            # Keep the body non-empty: a function whose ONLY statement is a
            # docstring still needs a statement, or the parse shape changes.
            node.body = body[1:] or [ast.Pass()]
    return tree


def _normalized(source: str) -> str | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    return ast.dump(_strip_docstrings(tree), annotate_fields=True)


def is_behavioral(base_ref: str, head_ref: str, path: str) -> tuple[bool, str]:
    """(behavioral?, reason). Anything uncertain is behavioral."""
    if not path.endswith(".py"):
        return True, "not a Python file"
    base = _blob(base_ref, path)
    head = _blob(head_ref, path)
    if base is None and head is None:
        return True, "readable in neither revision"
    if base is None:
        return True, "added"
    if head is None:
        return True, "deleted"
    if base == head:
        return False, "byte-identical"
    base_ast = _normalized(base)
    head_ast = _normalized(head)
    if base_ast is None or head_ast is None:
        return True, "unparseable in at least one revision"
    if base_ast == head_ast:
        return False, "identical AST once docstrings are stripped"
    return True, "AST differs"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", required=True, help="Base ref/sha.")
    p.add_argument("--head", required=True, help="Head ref/sha.")
    p.add_argument("paths", nargs="+", help="Authority paths that the guard matched.")
    args = p.parse_args(argv)

    behavioral: list[str] = []
    for path in args.paths:
        changed, reason = is_behavioral(args.base, args.head, path)
        marker = "BEHAVIORAL" if changed else "no-op     "
        print(f"{marker}  {path}  ({reason})")
        if changed:
            behavioral.append(path)

    if behavioral:
        print(f"\n{len(behavioral)} authority path(s) changed behavior -- receipt required.")
        return 1
    print("\nNo authority path changed behavior -- receipt not required for these.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
