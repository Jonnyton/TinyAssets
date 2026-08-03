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

**These assertions are deliberately exact, not substring checks.** A first draft
used `in` tests and cross-family review found three of them vacuous — most
notably an "is there a non-PR trigger?" assertion that `workflow_dispatch` had
already satisfied since before the bug existed, so it could never have failed.
A regression test for a silent-failure bug must not itself be able to fail
silently.

PyYAML is imported hard, with no `skipif`. Sibling workflow tests skip when it
is absent; that is wrong for this file specifically, because skipping is how
these invariants would go quiet — the failure mode they exist to prevent.
PyYAML is declared in the `dev` extra so the import is guaranteed, not
transitive.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parent.parent
_WORKFLOW = _REPO / ".github" / "workflows" / "tests.yml"

# The one expression `full-tests` may use. Admits schedule, push and
# workflow_dispatch; excludes pull_request. Pinned exactly rather than by
# substring: `github.event_name != 'pull_request' && github.event_name ==
# 'push'` also contains "pull_request" and "!=" while excluding schedules
# entirely, which is the bug this file guards against.
_FULL_TESTS_IF = "github.event_name != 'pull_request'"

_CONCURRENCY_GROUP = (
    "tests-${{ github.event.pull_request.number || github.run_id }}"
)
_CANCEL_IN_PROGRESS = "${{ github.event_name == 'pull_request' }}"

# Triggers that need a human to press them. A tripwire cannot be carried by
# these, so they do not count toward "fires automatically".
_MANUAL_TRIGGERS = {"workflow_dispatch", "repository_dispatch"}


def _load() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _triggers(wf: dict) -> dict:
    # PyYAML parses a bare `on:` key as the boolean True.
    return wf[True] if True in wf else wf["on"]


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _cron_field_ok(field: str, lo: int, hi: int) -> bool:
    """Accept `*`, `*/n`, `a`, `a-b`, and comma lists of those, within range."""
    for part in field.split(","):
        if not part:
            return False
        step = 1
        if "/" in part:
            part, _, step_s = part.partition("/")
            if not step_s.isdigit() or int(step_s) < 1:
                return False
            step = int(step_s)
        if part == "*":
            continue
        if "-" in part.lstrip("-"):
            a, _, b = part.partition("-")
            if not (a.isdigit() and b.isdigit()):
                return False
            if not (lo <= int(a) <= hi and lo <= int(b) <= hi and int(a) <= int(b)):
                return False
            continue
        if not part.isdigit() or not lo <= int(part) <= hi:
            return False
        _ = step
    return True


def _cron_is_valid(expr: str) -> bool:
    fields = expr.split()
    if len(fields) != 5:
        return False
    bounds = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
    return all(_cron_field_ok(f, lo, hi) for f, (lo, hi) in zip(fields, bounds))


def test_full_suite_has_an_automatic_trigger_that_survives_app_merges() -> None:
    """The post-merge tripwire needs a trigger `push:` cannot provide.

    Regression guard for bug (2). `push: branches: [main]` may stay — it still
    catches the rare human-PAT merge — but it must never be the only AUTOMATIC
    non-PR trigger, or the full suite reverts to never running.

    `workflow_dispatch` is excluded from the count on purpose: it is non-PR, but
    a human has to press it, so it cannot carry a tripwire. Counting it is what
    made the first version of this assertion unfailable.
    """
    triggers = _triggers(_load())
    automatic = set(triggers) - {"pull_request", "pull_request_target", "push"}
    automatic -= _MANUAL_TRIGGERS
    assert automatic, (
        "tests.yml has no AUTOMATIC trigger that fires on an app-performed "
        "merge. `push: branches: [main]` does NOT fire when auto-merge lands a "
        "PR via GITHUB_TOKEN, and workflow_dispatch needs a human, so the "
        "full-tests tripwire would never run on its own. Restore `schedule:`."
    )


def test_schedule_is_present_and_its_cron_is_valid() -> None:
    """A `schedule:` key that is empty or malformed fires nothing.

    `schedule:` with no entries, or `schedule: []`, both parse fine and both
    silently never run — so presence of the key proves nothing on its own.
    """
    schedule = _triggers(_load()).get("schedule")
    assert isinstance(schedule, list) and schedule, (
        f"`schedule:` must be a non-empty list, got {schedule!r} — an empty "
        f"schedule parses cleanly and fires nothing"
    )
    for entry in schedule:
        assert isinstance(entry, dict) and "cron" in entry, (
            f"each schedule entry needs a `cron:` key, got {entry!r}"
        )
        assert _cron_is_valid(entry["cron"]), (
            f"invalid 5-field cron expression: {entry['cron']!r}"
        )


def test_full_tests_runs_on_every_non_pr_event() -> None:
    """Pinned exactly — a narrower condition would re-strand the tripwire."""
    condition = _norm(_load()["jobs"]["full-tests"].get("if", ""))
    assert condition == _FULL_TESTS_IF, (
        f"full-tests `if:` must be exactly {_FULL_TESTS_IF!r} so that schedule, "
        f"push and workflow_dispatch all run it; got {condition!r}. Narrowing "
        f"it (e.g. adding `&& github.event_name == 'push'`) silently removes "
        f"the only automatic coverage of .github/heavy-test-files.txt."
    )


def test_non_pr_runs_never_cancel_or_queue_behind_each_other() -> None:
    """Regression guard for bug (1), pinned exactly.

    Substring checks passed here too: `cancel-in-progress:
    github.event_name != 'pull_request'` contains "pull_request" while meaning
    the exact opposite — cancel main runs, keep PR runs.
    """
    concurrency = _load()["concurrency"]
    assert _norm(concurrency["group"]) == _CONCURRENCY_GROUP, (
        f"concurrency group must be exactly {_CONCURRENCY_GROUP!r}; got "
        f"{_norm(concurrency['group'])!r}. Keying non-PR runs by ref lets each "
        f"push cancel the previous run; keying them by SHA still lets a newer "
        f"pending run replace a queued one on an unchanged main."
    )
    assert _norm(concurrency["cancel-in-progress"]) == _CANCEL_IN_PROGRESS, (
        f"cancel-in-progress must be exactly {_CANCEL_IN_PROGRESS!r}; got "
        f"{_norm(concurrency['cancel-in-progress'])!r}"
    )


def test_required_tests_job_name_matches_the_protection_context() -> None:
    """Renaming this job orphans the required context and blocks every PR.

    It does not fail open: the old context stays "Expected — waiting for
    status" forever.
    """
    assert _load()["jobs"]["required-tests"]["name"] == "required-tests"


def test_required_tests_is_not_path_filtered_or_conditional() -> None:
    """A required check that can decline to report hangs every PR.

    Both a `paths:` filter on the trigger and a job-level `if:` can produce
    "no status reported" rather than a failure, and branch protection waits on
    that forever.
    """
    wf = _load()
    triggers = _triggers(wf)
    assert "paths" not in (triggers.get("pull_request") or {}), (
        "a `paths:` filter on the required check's trigger hangs every PR "
        "outside those paths on 'Expected — waiting for status'"
    )
    assert "if" not in wf["jobs"]["required-tests"], (
        "the REQUIRED job must have no job-level `if:` — one that ever "
        "evaluates false on a pull_request strands the PR forever"
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
