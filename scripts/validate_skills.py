"""Validate project-local agent skills.

This catches the repo-specific skill hygiene problems that are easy to miss in
manual audits: stale copied-skill paths, weak trigger metadata, mirror drift,
and router entries that forget newly added skills.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ROOT = Path(".agents/skills")
MIRROR_ROOT = Path(".claude/skills")
ROUTER_SKILL = "using-agent-skills"

FORBIDDEN_TEXT = {
    "/mnt/skills": "external skill path copied into project skill",
    "AskUserQuestion": "tool name from another harness; use plain project workflow",
    "docs/ideas": "ideas belong under ideas/, not docs/ideas/",
    "user_invocable": "frontmatter must be limited to name and description",
    "disable-model-invocation": "frontmatter must be limited to name and description",
}


@dataclass(frozen=True)
class SkillIssue:
    path: Path
    message: str

    def format(self) -> str:
        return f"{self.path.as_posix()}: {self.message}"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frontmatter(path: Path) -> tuple[dict[str, str], list[str]]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, ["missing opening frontmatter fence"]
    try:
        raw = text.split("---", 2)[1]
    except IndexError:
        return {}, ["missing closing frontmatter fence"]

    data: dict[str, str] = {}
    errors: list[str] = []
    for line in raw.strip().splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            errors.append(f"invalid frontmatter line: {line!r}")
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        data[key] = value
    return data, errors


def _skill_files(skills_root: Path) -> list[Path]:
    return sorted(path for path in skills_root.glob("*/SKILL.md") if path.is_file())


def validate_metadata(root: Path) -> list[SkillIssue]:
    issues: list[SkillIssue] = []
    skills_root = root / CANONICAL_ROOT
    for path in _skill_files(skills_root):
        skill_name = path.parent.name
        data, errors = _frontmatter(path)
        for error in errors:
            issues.append(SkillIssue(path, error))
        extra = sorted(set(data) - {"name", "description"})
        if extra:
            issues.append(SkillIssue(path, f"unexpected frontmatter keys: {', '.join(extra)}"))
        if data.get("name") != skill_name:
            issues.append(SkillIssue(path, f"name must match folder: {skill_name!r}"))
        description = data.get("description", "")
        if not description:
            issues.append(SkillIssue(path, "missing description"))
        elif len(description) > 1024:
            issues.append(SkillIssue(path, "description exceeds 1024 characters"))
        elif not re.search(r"\bUse (when|for)\b|Use \"", description):
            issues.append(
                SkillIssue(path, 'description must include "Use when" or equivalent trigger')
            )
    return issues


def validate_forbidden_text(root: Path) -> list[SkillIssue]:
    issues: list[SkillIssue] = []
    for path in _skill_files(root / CANONICAL_ROOT):
        text = path.read_text(encoding="utf-8")
        for needle, reason in FORBIDDEN_TEXT.items():
            if needle in text:
                issues.append(SkillIssue(path, f"forbidden text {needle!r}: {reason}"))
    return issues


def validate_mirror(root: Path) -> list[SkillIssue]:
    issues: list[SkillIssue] = []
    source_root = root / CANONICAL_ROOT
    mirror_root = root / MIRROR_ROOT
    for source in _skill_files(source_root):
        rel = source.relative_to(source_root)
        mirror = mirror_root / rel
        if not mirror.exists():
            issues.append(SkillIssue(mirror, "missing mirror skill file"))
        elif _sha256(source) != _sha256(mirror):
            issues.append(SkillIssue(mirror, f"mirror differs from {source.as_posix()}"))
    for mirror in _skill_files(mirror_root):
        rel = mirror.relative_to(mirror_root)
        source = source_root / rel
        if not source.exists():
            issues.append(SkillIssue(mirror, "mirror has no canonical source"))
    return issues


def validate_router_coverage(root: Path) -> list[SkillIssue]:
    issues: list[SkillIssue] = []
    source_root = root / CANONICAL_ROOT
    router = source_root / ROUTER_SKILL / "SKILL.md"
    if not router.exists():
        return [SkillIssue(router, "router skill is missing")]
    router_text = router.read_text(encoding="utf-8")
    for path in _skill_files(source_root):
        skill_name = path.parent.name
        if skill_name == ROUTER_SKILL:
            continue
        if skill_name not in router_text:
            issues.append(SkillIssue(router, f"router does not mention skill {skill_name!r}"))
    return issues


def validate_all(root: Path) -> list[SkillIssue]:
    return [
        *validate_metadata(root),
        *validate_forbidden_text(root),
        *validate_mirror(root),
        *validate_router_coverage(root),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate TinyAssets project skills.")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    args = parser.parse_args(argv)

    issues = validate_all(args.root.resolve())
    if issues:
        for issue in issues:
            print(issue.format(), file=sys.stderr)
        return 1
    print("Skill validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
