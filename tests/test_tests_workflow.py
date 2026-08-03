"""Trigger-shape invariants for the Tests workflow.

These exist because a trigger that never fires is indistinguishable from
coverage until you go looking. Two such bugs were found in this workflow on
2026-08-03, both of which read as "the full suite guards main" while guarding
nothing:

  1. `concurrency` grouped main runs by ref, so each push killed the previous
     main run and the post-merge job almost never finished.
  2. `push: branches: [main]` does not fire at all on the normal merge path.
     auto-enroll-merge.yml enrols PRs with the repo's GITHUB_TOKEN, so GitHub
     performs the merge as `app/github-actions`, and events raised by
     GITHUB_TOKEN never start a workflow run (AGENTS.md hard rule 14). Of the
     last 6 merges, the 5 app-performed ones produced ZERO push runs; only the
     one merged by a human PAT produced a run.

So the assertions below are not style checks. Each one pins a property whose
absence silently converts a gate into decoration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import yaml

    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

_REPO = Path(__file__).resolve().parent.parent
_WORKFLOW = _REPO / ".github" / "workflows" / "tests.yml"

pytestmark = pytest.mark.skipif(
    not _YAML_AVAILABLE, reason="pyyaml not installed"
)


def _load() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _triggers(wf: dict) -> dict:
    # PyYAML parses a bare `on:` key as the boolean True.
    return wf[True] if True in wf else wf["on"]


def test_full_suite_has_a_trigger_that_fires_on_app_merges() -> None:
    """The post-merge tripwire needs a trigger `push:` cannot provide.

    Regression guard for bug (2) above. `push: branches: [main]` is allowed to
    stay — it still catches the rare human-PAT merge — but it must never be the
    ONLY non-PR trigger, or the full suite reverts to never running.
    """
    triggers = _triggers(_load())
    non_pr = set(triggers) - {"pull_request", "pull_request_target", "push"}
    assert non_pr, (
        "tests.yml has no trigger that fires on an app-performed merge. "
        "`push: branches: [main]` does NOT fire when auto-merge lands a PR "
        "via GITHUB_TOKEN, so the full-tests tripwire would never run. "
        "Add `schedule:` (or another non-push trigger) back."
    )
    assert "schedule" in triggers, (
        "expected `schedule:` specifically — it is the trigger empirically "
        "proven to fire on this repo"
    )


def test_full_tests_job_runs_on_the_scheduled_trigger() -> None:
    """A schedule trigger is useless if the job's `if:` excludes it."""
    job = _load()["jobs"]["full-tests"]
    condition = str(job.get("if", ""))
    assert "pull_request" in condition, (
        "full-tests should be gated on event name, not run everywhere"
    )
    # The guard must EXCLUDE pull_request, not require it — `== 'pull_request'`
    # would flip the meaning and strand the tripwire again.
    assert "!=" in condition, (
        f"full-tests `if:` must exclude pull_request, got: {condition!r}"
    )


def test_main_runs_are_not_cancelled_by_later_pushes() -> None:
    """Regression guard for bug (1): per-SHA grouping, no cancel off PRs."""
    concurrency = _load()["concurrency"]
    assert "github.sha" in concurrency["group"], (
        "main runs must be keyed per-SHA; grouping by ref lets each push "
        "cancel the previous main run"
    )
    assert "pull_request" in str(concurrency["cancel-in-progress"]), (
        "cancel-in-progress must be conditional on the event being a "
        "pull_request; `true` would cancel main runs too"
    )


def test_required_tests_job_name_matches_the_protection_context() -> None:
    """Renaming this job orphans the required context and blocks every PR.

    It does not fail open: the old context stays "Expected — waiting for
    status" forever.
    """
    assert _load()["jobs"]["required-tests"]["name"] == "required-tests"


def test_required_tests_is_not_path_filtered() -> None:
    """A path-filtered REQUIRED check never reports on out-of-path PRs."""
    triggers = _triggers(_load())
    assert "paths" not in (triggers.get("pull_request") or {}), (
        "a `paths:` filter on the required check's trigger hangs every PR "
        "outside those paths on 'Expected — waiting for status'"
    )


def test_required_tests_enforces_a_vacuity_floor() -> None:
    """The subset gate must assert a minimum test count.

    Without `--min-ran`, deselecting or erroring out of every test yields a
    green gate.
    """
    steps = _load()["jobs"]["required-tests"]["steps"]
    run_block = " ".join(str(s.get("run", "")) for s in steps)
    assert "--min-ran" in run_block, (
        "required-tests must pass --min-ran so a mass-deselect cannot pass"
    )
