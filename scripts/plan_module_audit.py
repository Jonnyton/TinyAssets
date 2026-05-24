"""PLAN.md module audit helper.

Lists the audit-stamp + substrate paths for each `## Module:` section in
PLAN.md. Flags stale modules (no audit stamp in N days) and drift candidates
(substrate paths that no longer exist on disk).

This is a reference tool for the `improve-codebase-architecture` and
`auto-iterate` skills. It does not gate commits or builds.

Usage:
    python scripts/plan_module_audit.py                 # show all modules
    python scripts/plan_module_audit.py --stale 30      # only modules unaudited >30 days
    python scripts/plan_module_audit.py --drift         # only modules with missing substrate paths
    python scripts/plan_module_audit.py --module Brain  # one module's full report

Exit code: 0 always. The script is informational, not a gate.
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PLAN_PATH = REPO_ROOT / "PLAN.md"

MODULE_HEADING_RE = re.compile(r"^## Module:\s*(?P<name>.+)$", re.MULTILINE)
STAMP_RE = re.compile(r"_Last audited:\s*(?P<date>\d{4}-\d{2}-\d{2})_")
SUBSTRATE_RE = re.compile(r"\*\*Substrate.*?\*\*\s*(?P<body>.*?)(?=\n\n\*\*|\n_Last audited|\n---)", re.DOTALL)
PATH_TOKEN_RE = re.compile(r"`([^`]+)`")


def parse_modules(plan_text: str) -> list[dict]:
    modules: list[dict] = []
    headings = list(MODULE_HEADING_RE.finditer(plan_text))
    for i, m in enumerate(headings):
        name = m.group("name").strip()
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else _next_h2_after(plan_text, start)
        body = plan_text[start:end]

        stamp_match = STAMP_RE.search(body)
        last_audited = stamp_match.group("date") if stamp_match else None

        substrate_match = SUBSTRATE_RE.search(body)
        substrate_paths: list[str] = []
        if substrate_match:
            for token in PATH_TOKEN_RE.findall(substrate_match.group("body")):
                if _looks_like_path(token):
                    substrate_paths.append(token)

        modules.append({
            "name": name,
            "last_audited": last_audited,
            "substrate_paths": substrate_paths,
        })
    return modules


def _next_h2_after(text: str, start: int) -> int:
    nxt = re.search(r"^## ", text[start:], re.MULTILINE)
    return start + nxt.start() if nxt else len(text)


def _looks_like_path(token: str) -> bool:
    if "/" in token or token.endswith(".py") or token.endswith(".md") or token.endswith(".yml"):
        return True
    return False


def staleness_days(module: dict, today: dt.date) -> int | None:
    if not module["last_audited"]:
        return None
    audited = dt.date.fromisoformat(module["last_audited"])
    return (today - audited).days


def missing_paths(module: dict) -> list[str]:
    missing: list[str] = []
    for path_token in module["substrate_paths"]:
        candidate = REPO_ROOT / path_token.rstrip("/")
        if not candidate.exists():
            missing.append(path_token)
    return missing


def format_module(module: dict, today: dt.date, *, verbose: bool = False) -> str:
    stamp = module["last_audited"] or "UNSTAMPED"
    age = staleness_days(module, today)
    age_str = f"{age}d" if age is not None else "n/a"
    missing = missing_paths(module)
    drift_str = f"  DRIFT: {', '.join(missing)}" if missing else ""

    if not verbose:
        return f"  {module['name']:36s}  audited={stamp}  age={age_str:>5s}{drift_str}"

    lines = [f"## {module['name']}", f"  last_audited: {stamp}", f"  age_days: {age_str}"]
    lines.append(f"  substrate_paths ({len(module['substrate_paths'])}):")
    for path in module["substrate_paths"]:
        marker = "  MISSING" if path in missing else ""
        lines.append(f"    - {path}{marker}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stale", type=int, default=None,
                        help="Only show modules unaudited for >N days.")
    parser.add_argument("--drift", action="store_true",
                        help="Only show modules with missing substrate paths.")
    parser.add_argument("--module", type=str, default=None,
                        help="Show full report for a single module by name (substring match).")
    args = parser.parse_args(argv)

    if not PLAN_PATH.exists():
        print(f"PLAN.md not found at {PLAN_PATH}", file=sys.stderr)
        return 0

    plan_text = PLAN_PATH.read_text(encoding="utf-8")
    modules = parse_modules(plan_text)
    today = dt.date.today()

    if args.module:
        needle = args.module.lower()
        for m in modules:
            if needle in m["name"].lower():
                print(format_module(m, today, verbose=True))
                print()
        return 0

    filtered = modules
    if args.stale is not None:
        filtered = [m for m in filtered
                    if (age := staleness_days(m, today)) is not None and age > args.stale]
    if args.drift:
        filtered = [m for m in filtered if missing_paths(m)]

    print(f"PLAN.md modules ({len(filtered)} / {len(modules)} shown, today={today.isoformat()})")
    if not filtered:
        print("  (no matches)")
    for m in filtered:
        print(format_module(m, today))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
