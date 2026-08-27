from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "validate_skills.py"
    spec = importlib.util.spec_from_file_location("validate_skills", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SKILL_TEMPLATE = """---
name: {name}
description: "Fixture skill {name}. Use when exercising the skill validator."
---

# {name}

Body text for {name}.
"""


def write_skill(root: Path, area: str, name: str, extra: str = "") -> Path:
    """Write one synthetic skill and return its path."""
    path = root / area / "skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SKILL_TEMPLATE.format(name=name) + extra, encoding="utf-8")
    return path


def make_skill_tree(tmp_path: Path, names=("alpha-skill", "beta-skill")) -> Path:
    """Build a synthetic canonical+mirror skill tree.

    Deliberately synthetic. These tests used to copy the repo's real skill tree
    and then mutate a skill by name -- so when `zoom-out` and `idea-refine` were
    deleted, the tests started failing with FileNotFoundError instead of testing
    anything. Two of them were already red on origin/main for that reason before
    the 2026-08-25 harness reset touched them. A test that cannot go red for the
    right reason is not a gate, so the fixtures now own their own data.
    """
    root = tmp_path / "repo"
    for name in names:
        write_skill(root, ".agents", name)
        write_skill(root, ".claude", name)
    return root


def test_current_skill_tree_is_valid() -> None:
    module = load_module()
    root = Path(__file__).resolve().parents[1]

    issues = module.validate_all(root)

    assert issues == []


def test_validator_catches_stale_imported_skill_text(tmp_path) -> None:
    module = load_module()
    root = make_skill_tree(tmp_path)
    assert module.validate_all(root) == [], "fixture must start clean"

    skill = root / ".agents" / "skills" / "alpha-skill" / "SKILL.md"
    skill.write_text(
        skill.read_text(encoding="utf-8") + "\nUse `AskUserQuestion` here.\n",
        encoding="utf-8",
    )

    issues = module.validate_all(root)

    assert any("AskUserQuestion" in issue.message for issue in issues)


def test_validator_catches_mirror_drift(tmp_path) -> None:
    module = load_module()
    root = make_skill_tree(tmp_path)
    assert module.validate_all(root) == [], "fixture must start clean"

    mirror = root / ".claude" / "skills" / "beta-skill" / "SKILL.md"
    mirror.write_text(mirror.read_text(encoding="utf-8") + "\nMirror drift.\n", encoding="utf-8")

    issues = module.validate_all(root)

    assert any("mirror differs" in issue.message for issue in issues)


def test_router_is_optional_when_absent(tmp_path) -> None:
    """No router is not a violation.

    The router was mandatory when the repo carried 34 skills. The harness reset
    cut that to 10 task-named ones and deleted `using-agent-skills`; see the
    docstring on `validate_router_coverage`.
    """
    module = load_module()
    root = make_skill_tree(tmp_path)

    issues = module.validate_all(root)

    assert issues == []
    assert not (root / ".agents" / "skills" / module.ROUTER_SKILL).exists()


def test_validator_catches_router_omission(tmp_path) -> None:
    """But a router that EXISTS must still list every skill."""
    module = load_module()
    root = make_skill_tree(tmp_path)
    router_body = "\n\nRouter mentions alpha-skill and beta-skill.\n"
    write_skill(root, ".agents", module.ROUTER_SKILL, router_body)
    write_skill(root, ".claude", module.ROUTER_SKILL, router_body)
    assert module.validate_all(root) == [], "fixture must start clean"

    for area in (".agents", ".claude"):
        router = root / area / "skills" / module.ROUTER_SKILL / "SKILL.md"
        router.write_text(
            router.read_text(encoding="utf-8").replace("beta-skill", "beta_removed"),
            encoding="utf-8",
        )

    issues = module.validate_all(root)

    assert any("router does not mention skill 'beta-skill'" in issue.message for issue in issues)
