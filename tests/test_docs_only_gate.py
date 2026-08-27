r"""The docs-only fast path must never skip a PR that can change behaviour.

`required-tests` skips its install/pytest steps when every changed path is
provably inert documentation. That is a real cycle-time win -- 9 of the last 25
merged PRs changed zero executable files -- and a real risk surface, so the
inert pattern is pinned here.

Cross-family review REJECTED a broader pattern and named three escapes. Each is
a test below:

* a rename `scripts/foo.py` -> `docs/foo.md`, which plain `git diff --name-only`
  reports as the destination only,
* `.txt`, which would have exempted `.github/known-failing-tests.txt` and
  `.github/heavy-test-files.txt` -- the files that DEFINE the gate,
* a root markdown file, since `tests/smoke/test_plan_md_exists.py` asserts
  `AGENTS.md` and `PLAN.md` exist, so deleting one must still run that test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "tests.yml"


def _scope_step() -> dict:
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for step in wf["jobs"]["required-tests"]["steps"]:
        if step.get("id") == "scope":
            return step
    raise AssertionError("required-tests has no `scope` step")


def _inert_pattern() -> str:
    run = _scope_step()["run"]
    m = re.search(r"INERT='([^']+)'", run)
    assert m, f"no INERT='...' assignment in the scope step:\n{run}"
    return m.group(1)


def _is_inert(path: str) -> bool:
    # `re.search`, not `re.match`: the workflow uses `grep -E`, which is
    # UNANCHORED. Using match here would let an unanchored pattern like
    # `\.(md|txt)$` look non-inert to the test while grep treats it as inert --
    # the test would pass while the gate leaked.
    return re.search(_inert_pattern(), path) is not None


def test_the_gate_exists_and_is_pinnable() -> None:
    # Guards the guard: if the step is renamed away, every test below would
    # otherwise error rather than fail meaningfully.
    assert _inert_pattern()


def test_diff_uses_no_renames() -> None:
    run = _scope_step()["run"]
    assert "--no-renames" in run, (
        "git diff must use --no-renames. Without it a rename reports only its "
        "DESTINATION, so scripts/foo.py -> docs/foo.md reads as docs-only "
        "while executable code disappears."
    )


def test_the_job_itself_is_not_conditional() -> None:
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = wf["jobs"]["required-tests"]
    assert "if" not in job, (
        "required-tests must run unconditionally. A required check that does "
        "not report leaves every PR on 'Expected - waiting for status' forever."
    )


@pytest.mark.parametrize(
    "path",
    [
        ".github/known-failing-tests.txt",
        ".github/heavy-test-files.txt",
        ".github/workflows/tests.yml",
        "requirements.txt",
        "AGENTS.md",
        "PLAN.md",
        "README.md",
        "Dockerfile",
        ".gitignore",
        "tinyassets/api/permissions.py",
        "scripts/ci_required_tests.py",
        "docs/../tinyassets/x.py",
    ],
)
def test_these_must_never_be_treated_as_inert(path: str) -> None:
    assert not _is_inert(path), f"{path!r} must force a full test run"


@pytest.mark.parametrize(
    "path",
    ["docs/a.md", "docs/deep/nested/note.md", "docs/x.rst", "docs/img/shot.png"],
)
def test_genuine_documentation_is_inert(path: str) -> None:
    assert _is_inert(path), f"{path!r} should be skippable"
