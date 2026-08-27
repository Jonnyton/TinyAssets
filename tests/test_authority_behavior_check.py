r"""The authority receipt gate must relax ONLY for provably-unchanged code.

`pr-scope-guard.yml` demands an exact-head cross-family review receipt for edits
to authority-critical paths. That rule stays. What changed is that it used to
fire on a path REGEX alone, so it could not tell a privilege escalation from a
docstring fix -- and blocked PR #2561 for six review rounds over a comment.

These tests exist because relaxing a security gate is exactly where a plausible
implementation is not good enough. The load-bearing assertion is the NEGATIVE
one: a real behavioral change must still require the receipt.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "authority_behavior_check.py"
_SPEC = importlib.util.spec_from_file_location("authority_behavior_check", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
abc = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = abc
_SPEC.loader.exec_module(abc)

BASE_SRC = '''"""Original docstring."""


def resolve(uid, write_allowed):
    """Decide the tier."""
    if uid and write_allowed:
        return "T2"
    return "T1"
'''


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "t")
    (r / "auth.py").write_text(BASE_SRC, encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    monkeypatch.chdir(r)
    return r


def _head(repo: Path, source: str) -> None:
    (repo / "auth.py").write_text(source, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "head")


def test_docstring_only_change_is_not_behavioral(repo: Path) -> None:
    _head(repo, BASE_SRC.replace("Original docstring.", "Rewritten docstring."))
    changed, reason = abc.is_behavioral("HEAD~1", "HEAD", "auth.py")
    assert changed is False, reason


def test_comment_and_reformatting_are_not_behavioral(repo: Path) -> None:
    with_comment = BASE_SRC.replace(
        "    if uid and write_allowed:",
        "    # a note\n    if uid and write_allowed:",
    )
    _head(repo, with_comment)
    changed, reason = abc.is_behavioral("HEAD~1", "HEAD", "auth.py")
    assert changed is False, reason


def test_dropping_the_write_check_IS_behavioral(repo: Path) -> None:
    # The escalation shape the gate exists to catch.
    _head(repo, BASE_SRC.replace("if uid and write_allowed:", "if uid:"))
    changed, reason = abc.is_behavioral("HEAD~1", "HEAD", "auth.py")
    assert changed is True, reason


def test_flipped_comparison_IS_behavioral(repo: Path) -> None:
    _head(repo, BASE_SRC.replace('return "T2"', 'return "T1"'))
    changed, _ = abc.is_behavioral("HEAD~1", "HEAD", "auth.py")
    assert changed is True


@pytest.mark.parametrize(
    "mutate,why",
    [
        (lambda r: (r / "auth.py").unlink(), "deleted"),
        (lambda r: (r / "auth.py").write_text("def broken(:\n", encoding="utf-8"), "syntax error"),
    ],
)
def test_ambiguous_cases_fail_closed(repo: Path, mutate, why: str) -> None:
    mutate(repo)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "head")
    changed, reason = abc.is_behavioral("HEAD~1", "HEAD", "auth.py")
    assert changed is True, f"{why} must fail closed, got {reason!r}"


def test_added_file_fails_closed(repo: Path) -> None:
    (repo / "new_auth.py").write_text(BASE_SRC, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "head")
    changed, reason = abc.is_behavioral("HEAD~1", "HEAD", "new_auth.py")
    assert changed is True, reason


def test_non_python_path_fails_closed(repo: Path) -> None:
    changed, reason = abc.is_behavioral("HEAD", "HEAD", "auth.yaml")
    assert changed is True, reason


def test_exit_code_requires_receipt_when_any_file_is_behavioral(repo: Path) -> None:
    _head(repo, BASE_SRC.replace("if uid and write_allowed:", "if uid:"))
    assert abc.main(["--base", "HEAD~1", "--head", "HEAD", "auth.py"]) == 1


def test_exit_code_clears_when_every_file_is_a_no_op(repo: Path) -> None:
    _head(repo, BASE_SRC.replace("Original docstring.", "Rewritten."))
    assert abc.main(["--base", "HEAD~1", "--head", "HEAD", "auth.py"]) == 0
