"""Guards for `.github/workflows/auto-enroll-merge.yml`.

This workflow enrolls every PR for auto-merge, so breaking it stops the whole
fleet from landing anything. It also cannot be exercised locally — it runs on
`pull_request_target`, from the base branch, with repository secrets. These
tests are therefore the only pre-merge check on its shape.

The specific thing being pinned is the merge-attribution token. A merge
attributed to the default `GITHUB_TOKEN` raises no `push` on main, so
`build-image` never fires and nothing deploys (hard rule 14). Pointing
enrollment at a non-default credential is what closes that, and the `||`
fallback is what makes the change safe to land before the credential exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github" / "workflows" / "auto-enroll-merge.yml"
)

#: Must match the name the host sets. Changing one without the other silently
#: reverts to the default token and re-opens the deploy gap with no failure.
_SECRET = "MERGE_ATTRIBUTION_TOKEN"


@pytest.fixture(scope="module")
def source() -> str:
    return _WORKFLOW.read_text("utf-8")


def test_workflow_is_parseable_yaml(source):
    """A syntax error here would break enrollment for every open PR."""
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(source)
    assert isinstance(doc, dict), type(doc)
    # `on` is parsed as the boolean True by YAML 1.1 — check both spellings
    # rather than asserting the one that happens to win.
    assert "jobs" in doc
    assert ("on" in doc) or (True in doc), sorted(map(str, doc))


def test_enrollment_prefers_the_attribution_token(source):
    """The whole point: enrollment must not hard-code the default token."""
    assert f"secrets.{_SECRET}" in source, (
        f"enrollment no longer references secrets.{_SECRET}; a merge "
        f"attributed to the default GITHUB_TOKEN raises no push on main, so "
        f"build-image never fires and nothing deploys (hard rule 14)"
    )
    assert "GH_TOKEN: ${{ secrets.%s || github.token }}" % _SECRET in source, (
        "the GH_TOKEN expression is not the expected "
        "`secrets.<token> || github.token` form"
    )


def test_fallback_is_present_so_an_absent_secret_is_a_no_op(source):
    """Without the `||` this change would break enrollment until the host
    creates the credential — which is the opposite of safe to land early."""
    line = next(
        ln for ln in source.splitlines() if ln.strip().startswith("GH_TOKEN:")
    )
    assert "||" in line, line
    assert "github.token" in line, line


def test_default_token_is_not_used_unconditionally(source):
    """A bare `GH_TOKEN: ${{ github.token }}` anywhere would reintroduce the
    gap even with the new expression present elsewhere."""
    bare = [
        ln.strip() for ln in source.splitlines()
        if ln.strip() == "GH_TOKEN: ${{ github.token }}"
    ]
    assert not bare, bare


def test_still_runs_on_pull_request_target(source):
    """`pull_request_target` is what gives this workflow the trusted base
    checkout AND access to repository secrets. On plain `pull_request` the
    secret would be unavailable for fork PRs and the fallback would silently
    take over — reopening the gap without any failure."""
    assert "pull_request_target:" in source
