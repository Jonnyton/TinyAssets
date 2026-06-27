"""Pre-commit invariant: block new tinyassets.author_server imports.

The tinyassets.author_server module is a deprecated shim (author→daemon rename).
124 existing call sites are grandfathered. This invariant blocks new ones from
being introduced — it checks only ADDED lines in the staged diff, not the full
file content, so existing sites don't trigger false positives.

Patterns blocked (module-level or deferred):
- `from tinyassets.author_server import ...`
- `import tinyassets.author_server`

Exit codes:
  0 — no new forbidden imports in staged diff (or no Python files staged)
  2 — one or more new forbidden imports detected

Usage (called by pre-commit hook):
    python scripts/pre_commit_invariant_author_server.py

Or in tests, pass a unified-diff string directly:
    check_diff(diff_text)  -> list of (filename, lineno, line) hits
"""

from __future__ import annotations

import re
import subprocess
import sys

# Patterns that match the deprecated import forms (module-level or deferred).
_PATTERNS = [
    re.compile(r"from\s+tinyassets\.author_server\b"),
    re.compile(r"import\s+tinyassets\.author_server\b"),
]


def check_diff(diff: str) -> list[tuple[str, int, str]]:
    """Scan a unified diff for newly-added forbidden import lines.

    Returns a list of (filename, added_lineno, line_content) for each hit.
    Only added lines (prefix "+") in .py files are checked.
    The diff header lines ("+++ b/...") are excluded.
    """
    hits: list[tuple[str, int, str]] = []
    current_file = ""
    current_new_lineno = 0

    for raw_line in diff.splitlines():
        # Diff file header: +++ b/path/to/file.py
        if raw_line.startswith("+++ "):
            path = raw_line[4:]
            # Strip the b/ prefix git adds.
            if path.startswith("b/"):
                path = path[2:]
            current_file = path if path.endswith(".py") else ""
            current_new_lineno = 0
            continue

        # Hunk header: @@ -old_start,old_count +new_start,new_count @@
        if raw_line.startswith("@@"):
            m = re.search(r"\+(\d+)", raw_line)
            if m:
                current_new_lineno = int(m.group(1)) - 1
            continue

        if not current_file:
            continue

        if raw_line.startswith("+"):
            current_new_lineno += 1
            # Skip the +++ header line (already handled above).
            if raw_line.startswith("+++"):
                continue
            content = raw_line[1:]  # strip leading "+"
            stripped = content.lstrip()
            # Skip comment-only lines — they're not imports.
            if stripped.startswith("#"):
                continue
            for pat in _PATTERNS:
                if pat.match(stripped):
                    hits.append((current_file, current_new_lineno, content.rstrip()))
                    break
        elif not raw_line.startswith("-"):
            # Context line — advance new-file line counter.
            current_new_lineno += 1

    return hits


def _get_staged_diff() -> str:
    """Return the unified diff of all staged Python changes."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--unified=0", "--diff-filter=ACMR", "--", "*.py"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout or ""
    except (FileNotFoundError, UnicodeDecodeError):
        pass
    return ""


def main(argv: list[str] | None = None) -> int:
    diff = _get_staged_diff()
    if not diff.strip():
        return 0  # no staged Python changes

    hits = check_diff(diff)
    if not hits:
        print(
            "pre-commit [author_server]: no new tinyassets.author_server imports",
            file=sys.stderr,
        )
        return 0

    print("pre-commit [author_server]: INVARIANT VIOLATED", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "  New imports of the deprecated tinyassets.author_server shim detected:",
        file=sys.stderr,
    )
    for filename, lineno, line in hits:
        print(f"    {filename}:{lineno}: {line.strip()}", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "  tinyassets.author_server is a back-compat alias for tinyassets.daemon_server.",
        file=sys.stderr,
    )
    print(
        "  Use tinyassets.daemon_server directly in new code.",
        file=sys.stderr,
    )
    print(
        "  Existing 124 call sites are grandfathered until the bulk rename lands.",
        file=sys.stderr,
    )
    print("  Override with --no-verify if this is the bulk-rename commit itself.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
