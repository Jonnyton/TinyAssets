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

**The assertions are exact where behaviour is exact, and structural where a
stricter check would produce false positives.** Two rounds of cross-family
review found five vacuous assertions in earlier drafts of this very file —
including an "is there a non-PR trigger?" check that `workflow_dispatch` had
satisfied since before the bug existed, and a `--min-ran` check that accepted
`--min-ran 1`. A regression test for a silent-failure bug must not itself be
able to fail silently. Equally, it must not fail on a harmless reformat, so
expression comparisons canonicalize the optional `${{ }}` wrapper and cron
grammar is left to actionlint rather than re-implemented badly here.

PyYAML is imported hard, with no `skipif`. Sibling workflow tests skip when it
is absent; that is wrong for this file specifically, because skipping is how
these invariants would go quiet — the failure mode they exist to prevent.
PyYAML is declared in the `dev` extra so the import is guaranteed, not
transitive.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parent.parent
_WORKFLOW = _REPO / ".github" / "workflows" / "tests.yml"
_SCRIPT = _REPO / "scripts" / "ci_required_tests.py"

# Import the gate script so the floor asserted below cannot drift away from the
# floor the gate actually enforces.
_spec = importlib.util.spec_from_file_location("ci_required_tests", _SCRIPT)
assert _spec and _spec.loader
_ci = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ci)

# The one expression `full-tests` may use. Admits schedule, push and
# workflow_dispatch; excludes pull_request. Pinned exactly rather than by
# substring: `github.event_name != 'pull_request' && github.event_name ==
# 'push'` also contains "pull_request" and "!=" while excluding schedules
# entirely, which is the bug this file guards against.
_FULL_TESTS_IF = "github.event_name != 'pull_request'"

_CONCURRENCY_GROUP = (
    "tests-${{ github.event.pull_request.number || github.run_id }}"
)
_CANCEL_IN_PROGRESS = "github.event_name == 'pull_request'"


def _load() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _triggers(wf: dict) -> dict:
    # PyYAML parses a bare `on:` key as the boolean True.
    return wf[True] if True in wf else wf["on"]


def _expr(value: object) -> str:
    """Normalize whitespace and strip a whole-value `${{ }}` wrapper.

    `if: foo` and `if: ${{ foo }}` are the same expression to GitHub, so a test
    that accepts only one spelling is testing spelling, not behaviour. Only a
    wrapper spanning the ENTIRE value is stripped — `tests-${{ x }}` keeps its
    interpolation, since there the literal text is the thing being asserted.
    """
    text = re.sub(r"\s+", " ", str(value)).strip()
    m = re.fullmatch(r"\$\{\{(.*)\}\}", text)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else text


def test_full_suite_runs_on_an_in_repo_schedule() -> None:
    """The post-merge tripwire needs a trigger `push:` cannot provide.

    Regression guard for bug (2). `push: branches: [main]` may stay — it still
    catches the rare human-PAT merge — but it cannot carry the tripwire, and
    `workflow_dispatch` needs a human to press it.

    This deliberately requires an **in-repository `schedule`** rather than
    "any automatic trigger". A `repository_dispatch` driven by some external
    scheduler would also be automatic, and is even a documented GITHUB_TOKEN
    exception — but then the tripwire's liveness depends on infrastructure that
    is not in this repo and cannot be reviewed here. Requiring the schedule is
    a policy choice, named honestly rather than dressed up as a generic check.

    An empty `schedule:` or `schedule: []` parses cleanly and fires nothing, so
    presence of the key proves nothing on its own.
    """
    schedule = _triggers(_load()).get("schedule")
    assert isinstance(schedule, list) and schedule, (
        f"tests.yml needs a non-empty `schedule:` — got {schedule!r}. Without "
        f"it the full-tests tripwire never runs: `push: branches: [main]` does "
        f"NOT fire when auto-merge lands a PR via GITHUB_TOKEN, and "
        f"workflow_dispatch needs a human."
    )
    for entry in schedule:
        assert isinstance(entry, dict) and "cron" in entry, (
            f"each schedule entry needs a `cron:` key, got {entry!r}"
        )
        # Structural only. actionlint validates GitHub's cron grammar in CI;
        # re-implementing it here got day-of-week `7` and symbolic `SUN-SAT`
        # wrong in review, and a validator that rejects a VALID cron is a
        # false-positive gate — worse than delegating.
        fields = str(entry["cron"]).split()
        assert len(fields) == 5, (
            f"cron must have 5 fields, got {len(fields)}: {entry['cron']!r}"
        )


def test_full_tests_runs_on_every_non_pr_event() -> None:
    """Pinned exactly — a narrower condition would re-strand the tripwire."""
    condition = _expr(_load()["jobs"]["full-tests"].get("if", ""))
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
    assert _expr(concurrency["group"]) == _CONCURRENCY_GROUP, (
        f"concurrency group must be exactly {_CONCURRENCY_GROUP!r}; got "
        f"{_expr(concurrency['group'])!r}. Keying non-PR runs by ref lets each "
        f"push cancel the previous run; keying them by SHA still lets a newer "
        f"pending run replace a queued one on an unchanged main."
    )
    assert _expr(concurrency["cancel-in-progress"]) == _CANCEL_IN_PROGRESS, (
        f"cancel-in-progress must be exactly {_CANCEL_IN_PROGRESS!r}; got "
        f"{_expr(concurrency['cancel-in-progress'])!r}"
    )


def test_required_tests_job_name_matches_the_protection_context() -> None:
    """Renaming this job orphans the required context and blocks every PR.

    It does not fail open: the old context stays "Expected — waiting for
    status" forever.
    """
    assert _load()["jobs"]["required-tests"]["name"] == "required-tests"


def test_required_tests_cannot_decline_to_report() -> None:
    """The required check must always produce a real conclusion.

    Two different failure modes, and they fail in OPPOSITE directions:

    * A `paths:`/`paths-ignore:` filter on the trigger can stop the workflow
      from running at all. Then no check is ever reported and branch protection
      waits on "Expected — waiting for status" FOREVER — every PR wedged.
    * A job-level `if:` does NOT do that. A skipped job reports
      `conclusion=skipped`, which branch protection accepts as satisfied — so a
      mistaken condition FAILS OPEN and silently merges untested code. Verified
      empirically 2026-08-03: `full-tests` carries a job-level `if:` and
      reported `COMPLETED/SKIPPED` on PR #2197, not pending.

    Fail-open is the more dangerous of the two, which is why the required job
    gets neither.
    """
    wf = _load()
    pr_trigger = _triggers(wf).get("pull_request") or {}
    for key in ("paths", "paths-ignore"):
        assert key not in pr_trigger, (
            f"`{key}:` on the required check's trigger stops the workflow from "
            f"running on out-of-scope PRs, and the required context then hangs "
            f"on 'Expected — waiting for status' forever"
        )
    assert "if" not in wf["jobs"]["required-tests"], (
        "the REQUIRED job must have no job-level `if:` — a skipped job reports "
        "conclusion=skipped, which protection treats as SUCCESS, so a mistaken "
        "condition fails open and merges untested code"
    )


def test_required_tests_enforces_an_adequate_vacuity_floor() -> None:
    """The subset gate must assert a *meaningful* minimum test count.

    Without `--min-ran`, deselecting or erroring out of every test yields a
    green gate. But the flag alone is not enough: `--min-ran 1` is accepted by
    the script verbatim and disables the floor just as effectively, so this
    asserts the actual number.
    """
    steps = _load()["jobs"]["required-tests"]["steps"]
    run_block = " ".join(str(s.get("run", "")) for s in steps)
    match = re.search(r"--min-ran[\s=]+(\d+)", run_block)
    assert match, (
        "required-tests must pass --min-ran so a mass-deselect cannot pass"
    )
    floor = int(match.group(1))
    assert floor >= _ci.MIN_RAN_FLOOR, (
        f"--min-ran {floor} is below the script's own MIN_RAN_FLOOR "
        f"({_ci.MIN_RAN_FLOOR}); a low floor disables the vacuity check as "
        f"surely as omitting the flag. If the suite legitimately shrank, lower "
        f"MIN_RAN_FLOOR in the same PR and say why."
    )
