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
# Compared LITERALLY, not through _expr(): in `concurrency`, unlike `if:`, the
# `${{ }}` wrapper is NOT optional — actionlint rejects a bare expression there.
# Normalizing it away would let an invalid workflow pass this test.
_CANCEL_IN_PROGRESS = "${{ github.event_name == 'pull_request' }}"


def _load() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _triggers(wf: dict) -> dict:
    # PyYAML parses a bare `on:` key as the boolean True.
    return wf[True] if True in wf else wf["on"]


def _norm(value: object) -> str:
    """Collapse whitespace only. Use where the literal text is the assertion."""
    return re.sub(r"\s+", " ", str(value)).strip()


def _expr(value: object) -> str:
    """Normalize whitespace and strip a whole-value `${{ }}` wrapper.

    Use ONLY for `if:`, where GitHub makes the wrapper optional. Do NOT use for
    `concurrency`, where the wrapper is mandatory — stripping it there would let
    a workflow actionlint rejects pass this suite.

    `if: foo` and `if: ${{ foo }}` are the same expression to GitHub, so a test
    that accepts only one spelling is testing spelling, not behaviour. Only a
    wrapper spanning the ENTIRE value is stripped — `tests-${{ x }}` keeps its
    interpolation, since there the literal text is the thing being asserted.

    The inner pattern is `[^{}]*`, not `.*`: greedy `.*` also matches a value
    made of TWO interpolations, e.g. `${{ a }}-${{ b }}`, mangling it to
    `a }}-${{ b`. That failed in the safe direction here (a mangled value just
    fails the exact comparison) but it is still wrong, and a future assertion
    might not be exact.
    """
    text = re.sub(r"\s+", " ", str(value)).strip()
    m = re.fullmatch(r"\$\{\{([^{}]*)\}\}", text)
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
        # Structure plus numeric ranges only. A full re-implementation of
        # GitHub's cron grammar got day-of-week `7` and symbolic `SUN-SAT`
        # wrong in review, and a validator that rejects a VALID cron is a
        # false-positive gate. But pure structure accepted `99 99 99 99 99`,
        # so numeric values are range-checked and anything containing letters
        # (`JAN-DEC`, `SUN-SAT`) is left to actionlint.
        fields = str(entry["cron"]).split()
        assert len(fields) == 5, (
            f"cron must have 5 fields, got {len(fields)}: {entry['cron']!r}"
        )
        bounds = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
        for field, (lo, hi) in zip(fields, bounds):
            if re.search(r"[A-Za-z]", field):
                continue  # symbolic form — actionlint owns it
            for number in re.findall(r"\d+", field.split("/")[0]):
                assert lo <= int(number) <= hi, (
                    f"cron field {field!r} has {number} outside {lo}-{hi} in "
                    f"{entry['cron']!r}"
                )


def test_schedule_declares_at_most_one_nominal_slot_per_hour() -> None:
    """Cadence policy: the schedule declares AT MOST one nominal slot per hour.

    "At most", not "one": `17 */3 * * *` declares one slot every three hours
    and is deliberately accepted. The test bounds the declared rate from
    above; it does not require any particular rate.

    `full-tests` takes 36-38 minutes (30858019064, 30875123887) and scheduled
    runs do NOT displace each other — the sibling concurrency test pins non-PR
    runs to a unique group with cancel-in-progress false, deliberately, so a
    queued tripwire run cannot be silently dropped. So a sub-hourly cron does
    not straightforwardly "run more often" — it declares more opportunities
    for a 38-minute job to overlap itself, and any overlap that is delivered
    runs concurrently rather than being cancelled.

    **This pins the DECLARED cadence, and nothing more.** GitHub documents that
    scheduled events may be delayed or dropped; it does not guarantee any
    minimum spacing between the starts it does deliver. The two runs cited
    above were dispatched 59 and 17 minutes late, so even one nominal slot per
    hour can produce starts minutes apart. Overlap is therefore tolerated (free
    runners, duplicated work, nothing corrupted), not prevented — do not read
    this test as proving runs cannot overlap. The declaration is the only part
    of the cadence the repo controls, so it is the only part testable here.

    Three deliberate conservatisms, all of which would otherwise make this
    vacuous or wrong:

    * The check is on the WHOLE schedule, not per entry. `17 * * * *` plus
      `47 * * * *` each satisfy "one fixed minute" while collectively declaring
      two slots an hour, so a per-entry check does not enforce its own headline
      — cross-family review caught exactly that.
    * ALL multi-entry schedules are rejected, not merely collectively
      sub-hourly ones. Disjoint weekday/weekend entries whose union never
      exceeds one slot per hour would be legitimate and are refused anyway.
    * A bare fixed minute is required, so legitimate once-per-hour forms like
      `59/5 * * * *` are rejected too. Evaluating real cron occurrences to
      admit either case would mean re-implementing GitHub's scheduler here,
      which an earlier version of this file got wrong; a conservative policy
      that is easy to read beats a clever one that is subtly wrong.

    If `full-tests` is ever made materially faster, relax this in the same
    commit that proves the new duration — do not delete it, because the
    behaviour it prevents is silent.
    """
    schedule = _triggers(_load())["schedule"]
    assert len(schedule) == 1, (
        f"expected exactly one schedule entry, got {len(schedule)}: "
        f"{[e.get('cron') for e in schedule]}. Multiple entries can each look "
        f"hourly while collectively declaring more slots, which is what this "
        f"test exists to prevent."
    )
    minute = str(schedule[0]["cron"]).split()[0]
    assert re.fullmatch(r"\d{1,2}", minute), (
        f"cron {schedule[0]['cron']!r} nominally starts more than once an hour "
        f"(minute field {minute!r}). `full-tests` runs 36-38 min and scheduled "
        f"runs use a unique concurrency group with cancel-in-progress false, so "
        f"they do not replace each other — they pile up. Use a single fixed "
        f"minute, or prove a shorter runtime first."
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
    group = _norm(concurrency["group"])
    cancel = _norm(concurrency["cancel-in-progress"])
    assert group == _CONCURRENCY_GROUP, (
        f"concurrency group must be exactly {_CONCURRENCY_GROUP!r}; got "
        f"{group!r}. Keying non-PR runs by ref lets each push cancel the "
        f"previous run; keying them by SHA still lets a newer pending run "
        f"replace a queued one on an unchanged main."
    )
    assert cancel == _CANCEL_IN_PROGRESS, (
        f"cancel-in-progress must be exactly {_CANCEL_IN_PROGRESS!r}; got "
        f"{cancel!r}. Compared literally on purpose — the `${{{{ }}}}` wrapper "
        f"is mandatory in `concurrency`, so accepting a bare expression here "
        f"would pass a workflow actionlint rejects."
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
    triggers = _triggers(wf)
    # Asserted separately: `.get("pull_request") or {}` treats a MISSING
    # pull_request trigger as an unfiltered one, so deleting the trigger
    # outright would have passed the filter checks below.
    assert "pull_request" in triggers, (
        "the required check must be triggered by `pull_request` at all — "
        "without it no check is ever reported and every PR hangs on "
        "'Expected — waiting for status'"
    )
    pr_trigger = triggers.get("pull_request") or {}
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
    values = [int(v) for v in re.findall(r"--min-ran[\s=]+(\d+)", run_block)]
    assert values, (
        "required-tests must pass --min-ran so a mass-deselect cannot pass"
    )
    # Exactly one, because argparse honours the LAST occurrence while a naive
    # scan reads the first: `--min-ran 10700 --min-ran 1` would look compliant
    # while setting the real floor to 1. Rated BLOCKING in review — it lets a
    # mass-deselected suite merge. The script now also rejects a low value
    # outright (ci_required_tests._min_ran_arg); this is the second lock.
    assert len(values) == 1, (
        f"--min-ran must appear exactly once, found {values}. argparse uses the "
        f"LAST value, so a repeated flag can silently lower the floor."
    )
    assert values[0] >= _ci.MIN_RAN_FLOOR, (
        f"--min-ran {values[0]} is below the script's own MIN_RAN_FLOOR "
        f"({_ci.MIN_RAN_FLOOR}); a low floor disables the vacuity check as "
        f"surely as omitting the flag. If the suite legitimately shrank, lower "
        f"MIN_RAN_FLOOR in the same PR and say why."
    )
