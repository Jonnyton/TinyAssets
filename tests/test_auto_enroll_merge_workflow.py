"""Guards for `.github/workflows/auto-enroll-merge.yml`.

This workflow enrolls every PR for auto-merge, so breaking it stops the whole
fleet from landing anything. It also cannot be exercised locally — it runs on
`pull_request_target`, from the base branch, with repository secrets. These
tests are therefore the only pre-merge check on its shape.

The specific thing being pinned is the merge-attribution token. A merge
attributed to the default `GITHUB_TOKEN` raises no `push` on main, so
`build-image` never fires and nothing deploys (hard rule 14), and with the
merge queue on, a PR it arms never enqueues. Enrollment therefore runs on a
user credential, refuses to run without one, and checks who it enrolled as.
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


def _steps(source: str) -> list[dict]:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(source)["jobs"]["enroll"]["steps"]


def test_enrollment_uses_the_attribution_token_with_no_fallback(source):
    """Enrollment must run as a user, never as the default token.

    The `|| github.token` fallback this replaced hid an empty secret on
    2026-09-27. Every PR was armed by github-actions, and with the merge queue
    on, a bot-armed auto-merge never enqueues.
    """
    gh_tokens = [
        ln.strip() for ln in source.splitlines() if ln.strip().startswith("GH_TOKEN:")
    ]
    assert gh_tokens == ["GH_TOKEN: ${{ secrets.%s }}" % _SECRET], gh_tokens


def test_an_empty_secret_fails_the_run(source):
    """An unset secret reads as the empty string. It must stop the run with
    an error, before anything is enrolled."""
    steps = _steps(source)
    names = [s.get("name") for s in steps]
    guard = names.index("Require the merge-attribution token")
    assert guard < names.index("Enable auto-merge")
    step = steps[guard]
    assert step["env"]["TOKEN_PRESENT"] == "${{ secrets.%s != '' }}" % _SECRET
    assert 'if [ "$TOKEN_PRESENT" != "true" ]' in step["run"]
    assert "exit 1" in step["run"]


def test_enrollment_is_checked_to_be_a_user(source):
    """A bot enroller is an error right after enrolling. A later event that
    finds a bot enrollment replaces it instead of keeping it."""
    run = next(s for s in _steps(source) if s.get("name") == "Enable auto-merge")["run"]
    # The queue entry's enqueuer counts: autoMergeRequest reads null once queued.
    assert "mergeQueueEntry{enqueuer{__typename login}}" in run
    # The second `STATE = yes` branch; the first is the review-gate deny path.
    already = run.index('if [ "$STATE" = "yes" ]; then', run.index("Idempotent"))
    block = run[already:run.index("fi\n", run.index("--disable-auto", already)) + 3]
    assert "who_enrolled" in block
    assert '== User:* ]]' in block and "exit 0" in block
    assert "--disable-auto" in block
    after = run[run.index('enrolled for auto-merge (squash)."'):]
    assert '!= User:* ]]' in after and "exit 1" in after


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
