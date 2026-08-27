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


def a_real_skill(root: Path) -> str:
    """Name a skill that actually exists, so mutation fixtures cannot rot.

    These tests used to hardcode `zoom-out`, deleted in a55f8362. Both mutation
    tests then silently stopped mutating anything and asserted against an issue
    that could never be raised — so the two guards enforcing mirror parity and
    router completeness were dead for months, including through the 2026-08-07
    change that made an identical cross-provider skill set a hard invariant.
    """
    names = sorted(
        p.name for p in (root / ".agents" / "skills").iterdir() if (p / "SKILL.md").is_file()
    )
    assert names, "no skills found — fixture cannot mutate anything"
    # Skip the router itself; mutating it would confound the router test.
    return next(n for n in names if n != "using-agent-skills")


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
    victim = a_real_skill(root)
    mirror = root / ".claude" / "skills" / victim / "SKILL.md"
    before = mirror.read_text(encoding="utf-8")
    mirror.write_text(before + "\nMirror drift.\n", encoding="utf-8")
    assert mirror.read_text(encoding="utf-8") != before, "fixture did not mutate"

    issues = module.validate_all(root)

    assert any("mirror differs" in issue.message for issue in issues)


def test_validator_catches_router_omission(tmp_path) -> None:
    module = load_module()
    root = copy_skill_tree(tmp_path)
    victim = a_real_skill(root)
    router = root / ".agents" / "skills" / "using-agent-skills" / "SKILL.md"
    before = router.read_text(encoding="utf-8")
    assert victim in before, f"router never mentioned {victim} — nothing to remove"
    # The placeholder must NOT contain `victim`: the validator looks for the
    # skill name as a substring, so `<victim>_removed` would still match and the
    # mutation would be a no-op.
    mutated = before.replace(victim, "placeholder-skill")
    assert victim not in mutated, "fixture left the name behind; mutation is a no-op"
    router.write_text(mutated, encoding="utf-8")

    issues = module.validate_all(root)

    assert any(
        f"router does not mention skill '{victim}'" in issue.message for issue in issues
    )
