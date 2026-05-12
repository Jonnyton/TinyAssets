"""Report drift between PLAN.md module-layout commitments and the code tree.

This is a default-branch, stdlib-only checker. It intentionally covers the
mechanical commitments that can be inspected without understanding product
semantics:

- canonical subpackages named in PLAN.md exist under ``workflow/``;
- concrete ``workflow/...`` Python files mentioned in PLAN.md exist;
- large root-level modules are called out when they are not in PLAN.md's
  correctly-flat allowlist.

Exit 0 means no drift found. Exit 1 means drift was reported. Use
``--no-fail`` when a human-readable inventory is wanted without failing a job.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError, OSError):
        pass


DEFAULT_ROOT_MODULE_LOC_THRESHOLD = 500
EXIT_CLEAN = 0
EXIT_DRIFT = 1


@dataclass(frozen=True)
class DriftIssue:
    code: str
    path: str
    message: str
    plan_reference: str


@dataclass(frozen=True)
class PlanCommitments:
    canonical_subpackages: tuple[str, ...]
    correctly_flat_modules: tuple[str, ...]
    mentioned_workflow_files: tuple[str, ...]


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / "PLAN.md").is_file() and (candidate / "workflow").is_dir():
            return candidate
    return Path.cwd().resolve()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_plan_commitments(plan_text: str) -> PlanCommitments:
    subpackages = sorted(
        {
            match.group(1).rstrip("/")
            for match in re.finditer(r"`workflow/([A-Za-z0-9_]+/)`", plan_text)
        }
    )

    correctly_flat_modules: set[str] = set()
    flat_match = re.search(
        r"Correctly-flat modules at root.*?(?=\n\n|\Z)",
        plan_text,
        flags=re.DOTALL,
    )
    if flat_match:
        correctly_flat_modules = {
            match.group(1)
            for match in re.finditer(r"`([A-Za-z0-9_]+\.py)`", flat_match.group(0))
        }

    mentioned_files: set[str] = {
        match.group(1)
        for match in re.finditer(
            r"`(workflow/[A-Za-z0-9_./-]+\.py)`",
            plan_text,
        )
    }
    for match in re.finditer(
        r"`((?:api|storage|runtime|bid|servers)/[A-Za-z0-9_./-]+\.py)`",
        plan_text,
    ):
        mentioned_files.add(f"workflow/{match.group(1)}")

    return PlanCommitments(
        canonical_subpackages=tuple(subpackages),
        correctly_flat_modules=tuple(sorted(correctly_flat_modules)),
        mentioned_workflow_files=tuple(sorted(mentioned_files)),
    )


def count_lines(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for _ in handle)
    except UnicodeDecodeError:
        return 0


def detect_plan_drift(
    root: Path,
    *,
    root_module_loc_threshold: int = DEFAULT_ROOT_MODULE_LOC_THRESHOLD,
) -> list[DriftIssue]:
    plan_path = root / "PLAN.md"
    workflow_dir = root / "workflow"
    issues: list[DriftIssue] = []

    if not plan_path.is_file():
        return [
            DriftIssue(
                code="missing-plan",
                path="PLAN.md",
                message="PLAN.md is missing; design truth cannot be checked.",
                plan_reference="AGENTS.md Three Living Files",
            )
        ]
    if not workflow_dir.is_dir():
        return [
            DriftIssue(
                code="missing-workflow-package",
                path="workflow/",
                message="workflow/ package is missing; implementation state cannot be checked.",
                plan_reference="PLAN.md Module Layout (target shape)",
            )
        ]

    commitments = parse_plan_commitments(read_text(plan_path))

    for subpackage in commitments.canonical_subpackages:
        rel = f"workflow/{subpackage}/"
        if not (root / rel).is_dir():
            issues.append(
                DriftIssue(
                    code="missing-canonical-subpackage",
                    path=rel,
                    message=(
                        f"PLAN.md names {rel} as a canonical engine subpackage, "
                        "but it is absent from the implementation tree."
                    ),
                    plan_reference="PLAN.md Module Layout (target shape)",
                )
            )

    for rel in commitments.mentioned_workflow_files:
        if not (root / rel).is_file():
            issues.append(
                DriftIssue(
                    code="missing-plan-mentioned-file",
                    path=rel,
                    message=f"PLAN.md mentions {rel}, but the file is absent.",
                    plan_reference="PLAN.md Module Layout (target shape)",
                )
            )

    flat_allowlist = set(commitments.correctly_flat_modules)
    for path in sorted(workflow_dir.glob("*.py")):
        if path.name.startswith("__"):
            continue
        line_count = count_lines(path)
        if line_count <= root_module_loc_threshold:
            continue
        if path.name in flat_allowlist:
            issues.append(
                DriftIssue(
                    code="oversized-correctly-flat-module",
                    path=f"workflow/{path.name}",
                    message=(
                        f"{path.name} is in PLAN.md's correctly-flat allowlist "
                        f"but is {line_count} LOC, above the "
                        f"~{root_module_loc_threshold} LOC migration threshold."
                    ),
                    plan_reference="PLAN.md Module Layout migration policy",
                )
            )
            continue
        issues.append(
            DriftIssue(
                code="oversized-root-module",
                path=f"workflow/{path.name}",
                message=(
                    f"{path.name} is {line_count} LOC at workflow/ root and is "
                    "not listed as correctly-flat in PLAN.md."
                ),
                plan_reference="PLAN.md Module Layout migration policy",
            )
        )

    return sorted(issues, key=lambda issue: (issue.code, issue.path))


def format_text_report(root: Path, issues: list[DriftIssue]) -> str:
    lines = [
        "PLAN.md drift report",
        f"Root: {root}",
        f"Issues: {len(issues)}",
    ]
    if not issues:
        lines.append("CLEAN: PLAN.md mechanical commitments match implementation state.")
        return "\n".join(lines)

    for issue in issues:
        lines.append("")
        lines.append(f"- {issue.code}: {issue.path}")
        lines.append(f"  {issue.message}")
        lines.append(f"  Plan reference: {issue.plan_reference}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check PLAN.md mechanical module-layout commitments against workflow/.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root to inspect. Defaults to auto-detecting from this script.",
    )
    parser.add_argument(
        "--root-module-loc-threshold",
        type=int,
        default=DEFAULT_ROOT_MODULE_LOC_THRESHOLD,
        help="LOC threshold for root workflow/*.py migration-policy drift.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of text.",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Always exit 0 after emitting the report.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = (args.root or find_repo_root(Path(__file__))).resolve()
    issues = detect_plan_drift(
        root,
        root_module_loc_threshold=args.root_module_loc_threshold,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(root),
                    "issue_count": len(issues),
                    "issues": [asdict(issue) for issue in issues],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(format_text_report(root, issues))

    if args.no_fail or not issues:
        return EXIT_CLEAN
    return EXIT_DRIFT


if __name__ == "__main__":
    raise SystemExit(main())
