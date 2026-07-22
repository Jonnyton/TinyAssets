#!/usr/bin/env python3
"""Check that `docs/reference/environment-variables.md` documents every env var
the daemon runtime actually reads.

`AGENTS.md` § "Configuration — environment variables" makes a completeness claim
("every var, its purpose, and default") and then pointer-loads the catalog per
ADR-002. Pointer-loading means a reader is told not to look further, so a gap in
the catalog reads as "this var does not exist" — which is how behaviour-gating
and security-relevant vars (`TINYASSETS_EXTERNAL_WRITE_ENABLED`,
`TINYASSETS_GITHUB_PR_CAPABILITIES`, `TINYASSETS_SETTLEMENT_BACKEND`, the
`TINYASSETS_CAP_*` family) went undocumented for months.

Usage:
    python scripts/check_env_catalog.py            # exit 2 if the catalog is incomplete
    python scripts/check_env_catalog.py --list     # print the extracted var sets
    python scripts/check_env_catalog.py --json     # machine-readable report

Exit codes:
    0  catalog documents every scanned var
    2  one or more scanned vars are missing from the catalog
    3  the catalog or a scan root is missing / unreadable
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG = REPO_ROOT / "docs" / "reference" / "environment-variables.md"

# The daemon runtime. AGENTS.md's completeness claim is about "the daemon", so
# this is the gate-enforced scope. Tooling under scripts/ and CI under
# .github/workflows/ read env vars too; they are deliberately NOT enforced here
# (see --extra-root to audit them ad hoc) because a catalog that must track
# every one-off script rots faster than it helps.
SCAN_ROOTS = ("tinyassets", "fantasy_daemon")

# packaging/claude-plugin/plugins/**/runtime/tinyassets/ is a build artifact
# mirror of tinyassets/ (rebuilt by packaging/claude-plugin/build_plugin.py).
# Scanning it would double-count every var.
EXCLUDE_PARTS = ("packaging", ".git", "node_modules", "attic", "archive")

# Ambient vars owned by the OS, the shell, or a third-party CLI — read by this
# code but not configuration *of* this project, so not catalog material. Keep
# this list short and explicit: every entry is a documentation exemption.
AMBIENT = frozenset(
    {
        # OS / shell
        "APPDATA",
        "COMSPEC",
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "PROGRAMFILES",
        "PWD",
        "SESSIONNAME",
        "SHELL",
        "SYSTEMROOT",
        "TEMP",
        "TERM",
        "TMP",
        "TMPDIR",
        "USER",
        "USERNAME",
        "USERPROFILE",
        "WINDIR",
        # CI-injected (GitHub Actions)
        "CI",
        "container",
        "GITHUB_ACTIONS",
        "GITHUB_ENV",
        "GITHUB_EVENT_NAME",
        "GITHUB_OUTPUT",
        "GITHUB_REF",
        "GITHUB_REPOSITORY",
        "GITHUB_RUN_ID",
        "GITHUB_SHA",
        "GITHUB_STEP_SUMMARY",
        "GITHUB_WORKSPACE",
        "RUNNER_OS",
        # pytest / tooling
        "PYTEST_CURRENT_TEST",
        "PYTHONPATH",
        "PYTHONUNBUFFERED",
        "VIRTUAL_ENV",
    }
)

_ENV_CALLS = {"getenv", "get", "pop", "setdefault"}

# Many env names are bound indirectly, so a direct-read scan alone under-reports:
#     _ENABLE_ENV = "TINYASSETS_EXTERNAL_WRITE_ENABLED"     # module constant
#     _CAP_ENVS = {"logs": "TINYASSETS_CAP_LOGS_BYTES"}     # dict value
#     _int_env("TINYASSETS_GITHUB_READ_MAX_FILES", 40)      # helper arg
# So we also collect *standalone* string literals that look like a project env
# name. Matching the FULL literal (not a substring) is what keeps this precise:
# a docstring is one big Constant, so prose mentioning a var never matches, and
# `Path("/etc/tinyassets/env")` never matches. This is why
# `_TINYASSETS_ENV_PATH` / `_TINYASSETS_RUN_EVIDENCE_PREFIXES` — Python
# identifiers, not env vars — are correctly excluded where a bare
# `grep -oE 'TINYASSETS_[A-Z_]+'` reports them as undocumented vars.
_PROJECT_ENV_PREFIXES = ("TINYASSETS_", "UNIVERSE_SERVER_", "WORKOS_", "FANTASY_DAEMON_")
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")


def _looks_like_project_env(value: str) -> bool:
    # Reject a bare prefix or a trailing underscore: `"TINYASSETS_"` /
    # `"FANTASY_DAEMON_"` are prefix fragments, not var names. Without this the
    # scanner reports its own `_PROJECT_ENV_PREFIXES` tuple as undocumented vars
    # when scripts/ is added via --extra-root.
    if value.endswith("_") or not _ENV_NAME_RE.match(value):
        return False
    return any(
        value.startswith(prefix) and len(value) > len(prefix)
        for prefix in _PROJECT_ENV_PREFIXES
    )


def _is_environ(node: ast.AST) -> bool:
    """True for `os.environ` / `environ` attribute-or-name expressions."""
    if isinstance(node, ast.Attribute) and node.attr == "environ":
        return True
    return isinstance(node, ast.Name) and node.id == "environ"


def _is_getenv(node: ast.AST) -> bool:
    """True for `os.getenv` / bare imported `getenv`."""
    if isinstance(node, ast.Attribute) and node.attr == "getenv":
        return True
    return isinstance(node, ast.Name) and node.id == "getenv"


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _display(path: Path) -> str:
    """Repo-relative path for display, falling back to the absolute path.

    `--catalog` may legitimately point outside the repo (the test suite writes a
    deliberately-damaged copy to a tmp dir), so a bare `relative_to` would raise
    and turn a clean exit-2 report into a traceback.
    """
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _func_name(func: ast.AST) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def extract_from_source(source: str, filename: str = "<unknown>") -> set[str]:
    """Env var names read by `source`, via AST (not regex).

    Three detectors, unioned:

    1. **Direct reads** — `os.environ["X"]`, `os.environ.get("X")`,
       `os.getenv("X")`, `.pop`/`.setdefault`, and the
       `from os import environ, getenv` bare forms. Catches any name,
       including unprefixed ones (`GITHUB_TOKEN`, `SUPABASE_URL`).
    2. **Env-helper args** — first string arg of a call whose function name
       contains "env" (`_int_env("X", 40)`, `_env_truthy("X")`). Catches
       unprefixed names bound indirectly.
    3. **Project-prefixed literals** — standalone string constants matching a
       project env prefix, wherever they appear (module constant, dict value,
       tuple). Catches the dominant indirect-binding pattern in this codebase.

    Known limitation, stated rather than hidden: an *unprefixed* var bound
    indirectly through something other than an `*env*`-named helper is not
    detected. Add such a var to the catalog by hand.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return set()

    found: set[str] = set()
    for node in ast.walk(tree):
        # (1) os.environ["X"]
        if isinstance(node, ast.Subscript) and _is_environ(node.value):
            name = _const_str(node.slice)
            if name:
                found.add(name)
        elif isinstance(node, ast.Call):
            func = node.func
            # (1) os.getenv("X")
            if _is_getenv(func) and node.args:
                name = _const_str(node.args[0])
                if name:
                    found.add(name)
            # (1) os.environ.get("X") / .pop / .setdefault
            elif (
                isinstance(func, ast.Attribute)
                and func.attr in _ENV_CALLS
                and _is_environ(func.value)
                and node.args
            ):
                name = _const_str(node.args[0])
                if name:
                    found.add(name)
            # (2) _int_env("X", default) and friends
            elif "env" in _func_name(func).lower() and node.args:
                name = _const_str(node.args[0])
                if name and _ENV_NAME_RE.match(name):
                    found.add(name)
        # (3) any standalone project-prefixed literal
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _looks_like_project_env(node.value):
                found.add(node.value)

    return found


def _iter_py(root: Path):
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
        if any(part in EXCLUDE_PARTS for part in rel.parts):
            continue
        yield path


def scan_code(roots: tuple[str, ...]) -> dict[str, list[str]]:
    """Map var name -> sorted repo-relative files that read it."""
    hits: dict[str, set[str]] = {}
    for root_name in roots:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            raise FileNotFoundError(f"scan root not found: {root}")
        for path in _iter_py(root):
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for name in extract_from_source(source, str(path)):
                hits.setdefault(name, set()).add(path.relative_to(REPO_ROOT).as_posix())
    return {name: sorted(files) for name, files in sorted(hits.items())}


# A var counts as documented only when it has a table ROW — i.e. it is backticked
# in the row's FIRST cell. Anything looser over-counts: the catalog's prose
# legitimately backticks Python identifiers (`SOFT_RATIO`, `DEFAULT_WORKER_MODELS`)
# and cross-references other vars inside purpose cells, and neither carries the
# "purpose + default" AGENTS.md promises. One row may cover several names
# (`GITHUB_TOKEN` / `GH_TOKEN`), so all backticked names in the first cell count.
_TABLE_ROW = re.compile(r"^\|([^|]+)\|")
_BACKTICKED = re.compile(r"`([A-Z][A-Z0-9_]{2,})`")


def scan_catalog(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"catalog not readable: {path} ({exc})") from exc

    documented: set[str] = set()
    for line in text.splitlines():
        row = _TABLE_ROW.match(line.strip())
        if row:
            documented.update(_BACKTICKED.findall(row.group(1)))
    return documented


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog", type=Path, default=CATALOG, help="path to the env-var catalog"
    )
    parser.add_argument(
        "--extra-root",
        action="append",
        default=[],
        metavar="DIR",
        help="additional dir to scan (repo-relative). Advisory audit use; not the enforced scope.",
    )
    parser.add_argument("--list", action="store_true", help="print both extracted sets")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    args = parser.parse_args(argv)

    roots = SCAN_ROOTS + tuple(args.extra_root)
    try:
        code = scan_code(roots)
        documented = scan_catalog(args.catalog)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3

    scanned = {name: files for name, files in code.items() if name not in AMBIENT}
    missing = {name: files for name, files in scanned.items() if name not in documented}
    # Catalog entries no code under `roots` reads. Advisory only: deploy-side and
    # CI-side vars legitimately live here with no daemon read site.
    catalog_only = sorted(documented - set(code) - AMBIENT)

    if args.json:
        print(
            json.dumps(
                {
                    "roots": list(roots),
                    "catalog": _display(args.catalog),
                    "scanned_count": len(scanned),
                    "documented_count": len(documented),
                    "missing": {k: v for k, v in missing.items()},
                    "catalog_only": catalog_only,
                },
                indent=2,
            )
        )
        return 2 if missing else 0

    if args.list:
        print(f"# env vars read under {', '.join(roots)} ({len(scanned)})")
        for name, files in scanned.items():
            print(f"{name}\t{files[0]}")
        print(f"\n# documented in {args.catalog.name} ({len(documented)})")
        for name in sorted(documented):
            print(name)
        print()

    if catalog_only:
        print(
            f"NOTE: {len(catalog_only)} catalog entr{'y' if len(catalog_only) == 1 else 'ies'} "
            f"not read under {', '.join(roots)} "
            "(expected for deploy/CI-side vars; verify before deleting):"
        )
        for name in catalog_only:
            print(f"  - {name}")
        print()

    if not missing:
        print(
            f"OK: all {len(scanned)} env vars read under {', '.join(roots)} "
            f"are documented in {_display(args.catalog)}."
        )
        return 0

    print(
        f"FAIL: {len(missing)} env var(s) read by code are missing from "
        f"{_display(args.catalog)}:\n",
        file=sys.stderr,
    )
    for name, files in missing.items():
        shown = ", ".join(files[:3])
        more = f" (+{len(files) - 3} more)" if len(files) > 3 else ""
        print(f"  {name}\n      read at: {shown}{more}", file=sys.stderr)
    print(
        "\nDocument each with purpose + default sourced from the call site "
        "(`git grep -n '<VAR>'` shows the os.environ.get default), or add it to "
        "AMBIENT in this script if it is an OS/CI-owned var rather than project "
        "configuration.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
