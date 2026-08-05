from __future__ import annotations

import importlib.util
import shutil
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


def copy_skill_tree(tmp_path: Path) -> Path:
    root = Path(__file__).resolve().parents[1]
    dst = tmp_path / "repo"
    shutil.copytree(root / ".agents" / "skills", dst / ".agents" / "skills")
    shutil.copytree(root / ".claude" / "skills", dst / ".claude" / "skills")
    return dst


def a_mirrored_skill(root: Path) -> str:
    """Name a skill that ACTUALLY exists in both trees and in the router.

    These tests used to hardcode `zoom-out`, which was later deleted — after
    which the mirror-drift test died on FileNotFoundError and the router test
    asserted a message about a skill that no longer existed. Picking the name
    from the tree means a future skill rename cannot rot them the same way.
    """
    router_text = (root / ".agents" / "skills" / "using-agent-skills" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    for path in sorted((root / ".agents" / "skills").iterdir()):
        name = path.name
        if not (path / "SKILL.md").is_file():
            continue
        if not (root / ".claude" / "skills" / name / "SKILL.md").is_file():
            continue
        if name == "using-agent-skills" or name not in router_text:
            continue
        return name
    raise AssertionError("no mirrored skill is referenced by the router")


def test_current_skill_tree_is_valid() -> None:
    module = load_module()
    root = Path(__file__).resolve().parents[1]

    issues = module.validate_all(root)

    assert issues == []


def test_validator_catches_stale_imported_skill_text(tmp_path) -> None:
    module = load_module()
    root = copy_skill_tree(tmp_path)
    skill = root / ".agents" / "skills" / "idea-refine" / "SKILL.md"
    skill.write_text(
        skill.read_text(encoding="utf-8") + "\nUse `AskUserQuestion` here.\n",
        encoding="utf-8",
    )

    issues = module.validate_all(root)

    assert any("AskUserQuestion" in issue.message for issue in issues)


def test_validator_catches_mirror_drift(tmp_path) -> None:
    module = load_module()
    root = copy_skill_tree(tmp_path)
    skill_name = a_mirrored_skill(root)
    mirror = root / ".claude" / "skills" / skill_name / "SKILL.md"
    mirror.write_text(mirror.read_text(encoding="utf-8") + "\nMirror drift.\n", encoding="utf-8")

    issues = module.validate_all(root)

    assert any("mirror differs" in issue.message for issue in issues)


def test_validator_catches_router_omission(tmp_path) -> None:
    module = load_module()
    root = copy_skill_tree(tmp_path)
    skill_name = a_mirrored_skill(root)
    router = root / ".agents" / "skills" / "using-agent-skills" / "SKILL.md"
    router.write_text(
        router.read_text(encoding="utf-8").replace(skill_name, "skill_removed_from_router"),
        encoding="utf-8",
    )

    issues = module.validate_all(root)

    assert any(
        f"router does not mention skill '{skill_name}'" in issue.message for issue in issues
    )
