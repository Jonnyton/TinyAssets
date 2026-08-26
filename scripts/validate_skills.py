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
    """Check the router lists every skill -- only if a router exists.

    The router was mandatory when this repo carried 34 skills and finding the
    right one was a real problem. The 2026-08-25 harness reset cut that to 10
    task-named skills, where a map costs more to maintain than it saves, so
    `using-agent-skills` was deleted. This check stays as coverage enforcement
    for a router that exists; it no longer demands one into being.
    """
    issues: list[SkillIssue] = []
    source_root = root / CANONICAL_ROOT
    router = source_root / ROUTER_SKILL / "SKILL.md"
    if not router.exists():
        return []
    router_text = router.read_text(encoding="utf-8")
    for path in _skill_files(source_root):
        skill_name = path.parent.name
        if skill_name == ROUTER_SKILL:
            continue
        if skill_name not in router_text:
            issues.append(SkillIssue(router, f"router does not mention skill {skill_name!r}"))
    return issues



# Paths a skill cites that must actually exist. Deliberately narrow: repo-rooted
# script/doc paths in backticks. Prose like `tests/` or a glob is not a claim
# that one exact file exists, so those are skipped.
# Two shapes of reference a skill can make:
#   repo-rooted   `scripts/foo.py`, `docs/bar.md`
#   skill-relative `references/checklist.md`, `workflow/providers/`
# The first version matched only the first shape under a narrow extension
# allowlist, so `references/security-checklist.md` and `workflow/providers/`
# both dangled while the validator reported green (cross-family review
# 2026-08-26). Directory references count: a skill pointing at a directory that
# does not exist is just as broken as one pointing at a missing file.
_ROOT_REF_RE = re.compile(
    r"`((?:scripts|docs|packaging|deploy|tinyassets|tests|openspec|\.agents|\.claude|\.github)"
    r"/[A-Za-z0-9_./-]+)`"
)
_REL_REF_RE = re.compile(r"`([A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)+/?)`")
_SKILL_REF_RE = re.compile(r"`([a-z][a-z0-9-]{3,})`")


def validate_referenced_paths(root: Path) -> list[SkillIssue]:
    """A skill citing a deleted script, doc, or sibling skill is a broken instruction.

    Checks EVERY markdown file under a skill directory, not just the top-level
    `SKILL.md` -- a dangling pointer in a bundled reference misleads exactly as
    much. Resolves skill-relative paths against the skill's own directory, which
    is how a reader would.
    """
    issues: list[SkillIssue] = []
    source_root = root / CANONICAL_ROOT
    known_skills = {path.parent.name for path in _skill_files(source_root)}

    for skill_dir in sorted(p for p in source_root.iterdir() if p.is_dir()):
        for md in sorted(skill_dir.rglob("*.md")):
            text = md.read_text(encoding="utf-8")
            for match in _ROOT_REF_RE.finditer(text):
                rel = match.group(1).rstrip("/")
                if not (root / rel).exists():
                    issues.append(SkillIssue(md, f"references missing path {rel!r}"))
            for match in _REL_REF_RE.finditer(text):
                rel = match.group(1)
                if _ROOT_REF_RE.fullmatch("`" + rel + "`"):
                    continue                       # already checked repo-rooted
                if rel.startswith(("http", "www.")) or " " in rel:
                    continue
                target = skill_dir / rel.rstrip("/")
                # Only flag a relative path that LOOKS like a bundled resource:
                # its first segment must be a real subdirectory of the skill, or
                # the whole path must be absent while its parent exists.
                first = rel.split("/", 1)[0]
                if (skill_dir / first).exists() and not target.exists():
                    issues.append(
                        SkillIssue(md, f"references missing skill resource {rel!r}")
                    )
            for match in _SKILL_REF_RE.finditer(text):
                name = match.group(1)
                if name in known_skills or "-" not in name:
                    continue
                if name in _DELETED_SKILLS:
                    issues.append(SkillIssue(md, f"references deleted skill {name!r}"))
    return issues


# Skills removed by the 2026-08-25 reset. Naming them explicitly keeps the check
# precise -- it flags a real dangling pointer without guessing that any
# hyphenated word is a skill name.
_DELETED_SKILLS = {
    "planning-and-task-breakdown", "incremental-implementation",
    "debugging-and-error-recovery", "code-simplification",
    "subagent-driven-development", "context-engineering",
    "documentation-and-adrs", "domain-model", "improve-codebase-architecture",
    "code-review-and-quality", "test-driven-development",
    "git-workflow-and-versioning", "skill-authoring", "using-agent-skills",
    "api-and-interface-design", "deprecation-and-migration",
    "frontend-ui-engineering", "performance-optimization",
    "conditional-edge-testing", "classic-game-design-test", "game-prototyping",
    "idea-refine", "spec-driven-development", "auto-iterate",
}

def validate_all(root: Path) -> list[SkillIssue]:
    return [
        *validate_metadata(root),
        *validate_forbidden_text(root),
        *validate_mirror(root),
        *validate_router_coverage(root),
        *validate_referenced_paths(root),
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
