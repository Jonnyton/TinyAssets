#!/usr/bin/env python3
"""The behavioural half of the `required-tests` branch-protection gate.

Runs the test suite, then decides pass/fail against a committed quarantine
list of already-broken tests (`.github/known-failing-tests.txt`).

Why a quarantine list instead of "the suite must be green"
----------------------------------------------------------
When this gate was first run against `main` it found 65 failures and 12 errors
that predate it. Requiring a fully green suite on day one would have blocked
every PR in the repo, so the gate would have been reverted within the hour and
`main` would still have no behavioural check at all.

So the gate enforces the property that actually matters for auto-merge:

    NO PR MAY INTRODUCE A TEST FAILURE THAT MAIN DID NOT ALREADY HAVE.

Every already-broken test is enumerated by node id, in the diff, with a reason.
The list may only shrink: an entry that stops failing is a hard error, so fixed
tests cannot rot in the file and quietly re-cover a regression later.

Honesty note (same spirit as pr-scope-guard.yml)
-----------------------------------------------
A contributor CAN add their own broken test to the quarantine file to get green.
This is a declaration control, not a security boundary. What it does buy: doing
so is an explicit, reviewable line in the diff on a `.github/` path — which also
trips the scope guard's `infra-change` declaration — instead of an invisible
regression riding in on a green check.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
QUARANTINE = REPO_ROOT / ".github" / "known-failing-tests.txt"

# The gate must never pass vacuously. Without a floor, a PR that mass-skips,
# mass-deselects, or deletes most of the suite goes green on nothing — pytest
# exits 0, no "new failures" exist, and only literal zero-collection trips
# exit 5 (Codex gate review 2026-08-02, finding 3). The suite ran 12,747
# tests on the 2026-08-02 baseline (run 30767266528); the floor sits far
# below natural variance and far above any vacuous run. Ratchet it upward
# as the suite grows.
MIN_RAN_FLOOR = 10000

# A heavy-only job runs ~2,235 tests, so it cannot meet the whole-suite floor --
# and LOWERING the global floor to fit it would disable the vacuity check for
# the gate too. Named profiles keep the property that matters: a floor is a
# reviewed constant here, never a number a caller can pick, and the
# workflow-shape test pins which profile each job uses.
MIN_RAN_FLOORS = {
    "full": MIN_RAN_FLOOR,   # every test under tests/
    "heavy": 2000,           # .github/heavy-test-files.txt only (~2,235 today)
}


def _min_ran_arg(raw: str) -> int:
    """Reject a `--min-ran` below the floor, at the point of enforcement.

    Validating this only in the workflow-shape test is not enough: argparse uses
    the LAST occurrence of a repeated flag, so `--min-ran 10700 --min-ran 1`
    reads as 1 while any check that scans for the first match still sees 10700.
    Found in cross-family review 2026-08-03 and rated BLOCKING, because it
    silently disables the vacuity floor and lets a mass-deselected suite merge.

    Refusing here closes it for every caller, including ones that never go
    through the workflow. Lowering the floor legitimately means editing
    MIN_RAN_FLOOR in the same reviewed change — which is the point.
    """
    value = int(raw)
    # Floor for the LOWEST profile: the exact profile is not known at
    # argparse time, so this rejects the obviously-disabling values and
    # `main` re-checks against the selected profile's floor.
    lowest = min(MIN_RAN_FLOORS.values())
    if value < lowest:
        raise argparse.ArgumentTypeError(
            f"--min-ran {value} is below the lowest profile floor ({lowest}); a "
            f"low floor disables the vacuity check as surely as omitting it. If "
            f"a suite legitimately shrank, lower the profile's entry in "
            f"MIN_RAN_FLOORS in the same PR and say why."
        )
    return value


def vacuity_failure(ran_count: int, floor: int = MIN_RAN_FLOOR) -> str | None:
    """Return a failure message if too few tests ran to trust a green result."""
    if ran_count < floor:
        return (
            f"only {ran_count} tests ran; the floor is {floor}. A run this "
            "small means mass skip/deselect/deletion or a collection collapse "
            "- the gate must not go green on a vacuous run. If the suite "
            "legitimately shrank, lower MIN_RAN_FLOOR in the same PR and say "
            "why."
        )
    return None


def parse_quarantine(path: Path) -> tuple[set[str], set[str], list[str]]:
    """Return (tolerated, flaky, problems).

    Line formats (blank lines and `#` comments ignored)::

        tests/test_x.py::test_y            # tolerated failure, ratcheted
        flaky tests/test_x.py::test_z      # tolerated in BOTH directions

    A plain entry is ratcheted: it must keep failing, or the line is stale and
    must be deleted. A `flaky` entry is exempt from that ratchet because it
    genuinely alternates run to run — without the escape hatch a flaky test
    would break unrelated PRs whichever way it landed. `flaky` is deliberately
    a separate, greppable keyword so the count stays visible and small.
    """
    if not path.exists():
        return set(), set(), []
    tolerated: set[str] = set()
    flaky: set[str] = set()
    problems: list[str] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        is_flaky = False
        if line.startswith("flaky "):
            is_flaky = True
            line = line[len("flaky ") :].strip()
        if "::" not in line:
            problems.append(f"{path.name}:{lineno}: not a pytest node id: {line!r}")
            continue
        (flaky if is_flaky else tolerated).add(line)
    return tolerated, flaky, problems


def node_id(testcase: ET.Element) -> str:
    """Rebuild the canonical pytest node id from an xunit1 <testcase>.

    xunit1 records `file` (path) and `classname` (dotted module [+ class]).
    The module prefix of `classname` is redundant with `file`; whatever remains
    after stripping it is the enclosing class, if any.
    """
    file_attr = (testcase.get("file") or "").replace("\\", "/")
    name = testcase.get("name") or ""
    classname = testcase.get("classname") or ""

    if not file_attr:
        # No `file` recorded — fall back to the dotted form so the entry is at
        # least identifiable. Never silently drop a failure.
        return f"{classname}::{name}"

    # A collection error records an empty classname; `file::name` keeps that
    # entry quarantinable instead of emitting a `file::::name` double colon.
    if not classname:
        return f"{file_attr}::{name}"

    module_dotted = file_attr[:-3].replace("/", ".") if file_attr.endswith(".py") else ""
    if classname == module_dotted or not module_dotted:
        return f"{file_attr}::{name}"
    if classname.startswith(module_dotted + "."):
        cls = classname[len(module_dotted) + 1 :]
        return f"{file_attr}::{cls}::{name}"
    return f"{file_attr}::{classname}::{name}"


def collect_outcomes(junit: Path) -> tuple[set[str], set[str]]:
    """Return (failing, ran) node id sets from a junit xml."""
    root = ET.parse(junit).getroot()
    failing: set[str] = set()
    ran: set[str] = set()
    for tc in root.iter("testcase"):
        nid = node_id(tc)
        # A skipped test did not execute — it can neither prove nor disprove a
        # quarantine entry, so it must not count as "ran".
        if tc.find("skipped") is not None:
            continue
        ran.add(nid)
        if tc.find("failure") is not None or tc.find("error") is not None:
            failing.add(nid)
    return failing, ran


def summarise(lines: list[str]) -> None:
    import os

    path = os.environ.get("GITHUB_STEP_SUMMARY")
    text = "\n".join(lines)
    print(text)
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--junit", default="junit.xml")
    ap.add_argument(
        "--pytest-arg",
        action="append",
        default=[],
        help="extra arg passed through to pytest (repeatable)",
    )
    ap.add_argument(
        "--exclude-from",
        metavar="FILE",
        help=(
            "File listing test paths to --ignore (blank lines and # comments "
            "skipped). Used by the fast REQUIRED gate to drop the handful of "
            "files that dominate its wall clock; `full-tests` omits this and "
            "runs everything."
        ),
    )
    ap.add_argument(
        "--include-from",
        metavar="FILE",
        help=(
            "File listing the ONLY test paths to run (blank lines and # "
            "comments skipped). The inverse of --exclude-from, for the "
            "`heavy-tests` job: it runs exactly the files the required gate "
            "excludes, so the two together cover the suite once instead of "
            "the old `full-tests` re-running the required 10,700 a second "
            "time. Directories are accepted, matching --exclude-from. A "
            "listed path that no longer exists is dropped with a WARNING "
            "rather than aborting the run."
        ),
    )
    ap.add_argument(
        "--profile",
        choices=sorted(MIN_RAN_FLOORS),
        default="full",
        help=(
            "Which vacuity floor applies. `full` is the whole suite; `heavy` "
            "is heavy-test-files.txt only. Named here rather than passed as a "
            "number so a job cannot quietly choose a floor it can meet."
        ),
    )
    ap.add_argument(
        "--min-ran",
        type=_min_ran_arg,
        default=MIN_RAN_FLOOR,
        help=(
            "Vacuity floor: fail if fewer than this many tests actually ran. "
            "Must be set per job — the fast gate and the full suite have "
            f"different honest totals (default {MIN_RAN_FLOOR}). Values below "
            f"MIN_RAN_FLOOR ({MIN_RAN_FLOOR}) are rejected outright."
        ),
    )
    ap.add_argument(
        "--emit-quarantine",
        metavar="JUNIT",
        help=(
            "Print the failing node ids from an EXISTING junit xml and exit. "
            "How .github/known-failing-tests.txt is generated — so the list is "
            "reproducible from a CI artifact, never hand-typed."
        ),
    )
    args = ap.parse_args()

    # BEFORE running anything. argparse can only check the LOWEST profile floor
    # (the profile is not known while parsing), so `--profile full --min-ran
    # 2000` slips past it. Checking here rather than beside the vacuity
    # assertion matters: the late check ran the whole suite for ten minutes
    # first and only then refused.
    profile_floor = MIN_RAN_FLOORS[args.profile]
    if args.min_ran < profile_floor:
        raise SystemExit(
            f"--min-ran {args.min_ran} is below the '{args.profile}' profile "
            f"floor ({profile_floor}). Lower MIN_RAN_FLOORS['{args.profile}'] "
            f"in the same reviewed change if the suite legitimately shrank."
        )

    if args.emit_quarantine:
        failing, _ = collect_outcomes(Path(args.emit_quarantine))
        for nid in sorted(failing):
            print(nid)
        return 0

    junit = Path(args.junit)
    if junit.exists():
        junit.unlink()

    # SERIAL ON PURPOSE — do not "optimise" this back to pytest-xdist.
    #
    # HISTORICAL, pre-#2199. Under `-n auto --dist loadfile` this suite was not
    # deterministic: a test leaked global state and poisoned every later test on
    # the same worker. One measured run had 70 of its 149 failures on gw2 alone,
    # against 5/11/6 on the other three, including a `git diff --cached` that
    # returned another test's PR URL.
    #
    # Which tests landed on the poisoned worker depended on the file list, so
    # simply ADDING a test file moved ~34 tests in and out of the failure set
    # between two runs of otherwise-identical code. A gate whose verdict depends
    # on scheduling cannot support a committed baseline, and would fail PRs for
    # sins they did not commit.
    #
    # That specific leak is FIXED (#2199: a `patch()` entered inside a thread
    # worker, which is process-global rather than thread-local). Do not read the
    # paragraphs above as evidence of a leak that still exists — they are the
    # reason this call went serial, not a current diagnosis. Whether any further
    # isolation problem remains is undiagnosed; see the measurement below, whose
    # run-to-run disagreements have no established cause.
    #
    # Serial remains the choice here because a gate needs a deterministic
    # verdict.
    #
    # The "~4x" this comment used to promise on the other side of that fix was a
    # HYPOTHESIS. It was never measured, and one measurement does not support it.
    #
    # Measured 2026-08-03, Windows, 20 logical CPUs, `-n auto --dist loadfile`,
    # same tree, on this gate's subset as the exclusion manifest stood that day:
    #
    #     serial        10:04   214 failing
    #     xdist run A   11:40   219 failing
    #     xdist run B    9:53   218 failing
    #
    # What that measurement supports, stated no more strongly than it earns:
    #
    # No REPEATABLE speedup. Run A was ~16% slower than serial; run B was 11
    # seconds (~1.8%) faster, and that was not repeated. "No speedup at all"
    # would be wrong — B did beat serial — but one run each cannot establish
    # timing variance, so 11 seconds is reported as the measured delta and NOT
    # classified as noise. The two parallel runs bracket serial.
    #
    # The failure SETS differ. Cardinalities alone (214 / 219 / 218) prove that
    # much without any node IDs. They do NOT settle what the gate would report,
    # and the intuition that a disagreement "inside the baseline is harmless" is
    # wrong here: a plain ledger entry is RATCHETED, so a quarantined test that
    # runs and PASSES is classified stale and fails the gate — the same
    # mechanism that deleted 30 entries in #2236. Only a `flaky` entry is
    # verdict-neutral, and even that shifts the reported count.
    #
    # Distinguishing new failures from stale-ratcheted from flaky needs the
    # node-ID and ran sets, which were not captured. So the claim here is only
    # that this configuration is not established as safe for a committed-baseline
    # gate — not that it is proven unsafe.
    #
    # Deliberately NOT claimed: any causal account of the disagreements. An
    # earlier version of this comment attributed them to resource contention and
    # enumerated causes that summed to six while calling them seven, with no
    # node-ID sets to back it. Absent those sets the honest statement is that the
    # runs disagree and the cause is undiagnosed. #2199 fixed one specific
    # threaded `patch()` leak; it does not prove the remainder is not isolation.
    #
    # Scope: this is "no win demonstrated for THIS configuration", not "xdist
    # cannot help". Fewer workers, another `--dist` scheduler, or a later suite
    # shape are all untested, as is the full suite post-#2199. Whether the files
    # in .github/heavy-test-files.txt (deliberately not a count here — the last
    # one drifted from 47 to 50 and made this comment wrong) are the best
    # remaining target is likewise unmeasured.
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        "not slow",
        "-q",
        "--no-header",
        "--durations=15",
        # Without this, ONE unimportable file aborts collection and the entire
        # suite reports "1 error, nothing run" — the gate would then be blind to
        # every real regression behind it. tests/test_tinyassets_tray.py does
        # exactly that on a headless runner (pystray -> Xlib DisplayNameError).
        # With it, the bad import is reported as an ordinary error against that
        # file and everything else still runs and still gates.
        "--continue-on-collection-errors",
        "-o",
        "junit_family=xunit1",
        f"--junitxml={junit}",
    ]
    if args.exclude_from:
        excluded = [
            line.strip()
            for line in Path(args.exclude_from).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if not excluded:
            # An empty list means the file was truncated or mis-parsed. Running
            # everything is the safe direction, but say so — silently widening
            # the gate is how a "fast" job quietly becomes a 37-minute one.
            print(f"WARNING: {args.exclude_from} listed no paths", flush=True)
        cmd += [f"--ignore={path}" for path in excluded]
    if args.include_from:
        listed = [
            line.strip()
            for line in Path(args.include_from).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        present = [p for p in listed if (REPO_ROOT / p).exists()]
        for missing in [p for p in listed if p not in present]:
            # A stale entry must not take the whole job down, but it must not
            # be silent either -- that is how coverage disappears unnoticed.
            print(f"WARNING: {args.include_from} lists a missing path: {missing}", flush=True)
        if not present:
            # Running EVERYTHING would be the wrong safe direction here: this
            # job exists to run a subset, and a silent full run would duplicate
            # the required gate again. Fail instead.
            raise SystemExit(
                f"{args.include_from} resolved to no existing paths; refusing to "
                f"run (an empty include list would silently run nothing)."
            )
        cmd += present
    cmd += [*args.pytest_arg]
    print("+ " + " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=REPO_ROOT)
    print(f"pytest exit code: {proc.returncode}", flush=True)

    # Exit 3 = INTERNALERROR (e.g. a crashed xdist worker). When that happens the
    # run is TRUNCATED: tests are silently dropped from the report, so a
    # failure-set comparison against it is meaningless. Fail loudly instead of
    # comparing garbage. This is not theoretical — it is exactly how three
    # os.name-faking tests silently stopped a whole file from running.
    if proc.returncode == 3:
        summarise(
            [
                "### Required tests — INTERNAL ERROR",
                "",
                "pytest exited 3 (INTERNALERROR). The run was truncated, so an",
                "unknown number of tests never executed. Treating this as failure:",
                "a partial run cannot prove the absence of a regression.",
            ]
        )
        return 1

    if not junit.exists():
        summarise(
            [
                "### Required tests — NO REPORT",
                "",
                f"pytest exited {proc.returncode} but wrote no junit xml. The gate",
                "cannot verify anything, so it fails closed.",
            ]
        )
        return 1

    tolerated, flaky, problems = parse_quarantine(QUARANTINE)
    known = tolerated | flaky
    failing, ran = collect_outcomes(junit)

    new_failures = sorted(failing - known)
    # An entry that ran and did NOT fail is fixed (or renamed/deleted). Either
    # way the line is stale and must go, or the list slowly stops meaning
    # anything. Entries that did not run at all are left alone — a
    # platform-skipped test is not evidence of anything. `flaky` entries are
    # exempt by definition.
    stale = sorted(n for n in tolerated if n in ran and n not in failing)

    lines = [
        "### Required tests",
        "",
        f"- ran: **{len(ran)}**",
        f"- failing: **{len(failing)}**",
        f"- known-broken on main: **{len(tolerated)}** (+{len(flaky)} flaky)",
        f"- NEW failures: **{len(new_failures)}**",
        f"- stale quarantine entries: **{len(stale)}**",
    ]

    if problems:
        lines += ["", "**Malformed quarantine file:**", ""]
        lines += [f"- `{p}`" for p in problems]

    if new_failures:
        lines += [
            "",
            "**FAILED — this PR introduces test failures that `main` does not have.**",
            "",
        ]
        lines += [f"- `{n}`" for n in new_failures[:50]]
        if len(new_failures) > 50:
            lines.append(f"- …and {len(new_failures) - 50} more")

    if stale:
        lines += [
            "",
            "**FAILED — quarantined tests are passing now. Delete these lines from",
            f"`{QUARANTINE.relative_to(REPO_ROOT).as_posix()}`:**",
            "",
        ]
        lines += [f"- `{n}`" for n in stale[:50]]
        if len(stale) > 50:
            lines.append(f"- …and {len(stale) - 50} more")

    if not new_failures and not stale and not problems:
        # ASCII only: this also runs on a Windows console (cp1252), where a
        # stray emoji raises UnicodeEncodeError and takes the gate down with it.
        lines += ["", "No new failures."]

    summarise(lines)

    if new_failures or stale or problems:
        return 1

    vacuous = vacuity_failure(len(ran), args.min_ran)
    if vacuous:
        summarise(["", f"**FAILED — {vacuous}**"])
        return 1

    # Guard the inverse of a green check: pytest failed for a reason the
    # comparison did not explain (collection error, usage error, no tests run).
    # Exit codes: 0 ok, 1 tests failed (already explained above), 2 interrupted,
    # 4 usage error, 5 no tests collected.
    if proc.returncode not in (0, 1):
        summarise(
            [
                "",
                f"**FAILED — pytest exited {proc.returncode} with no new test failures",
                "to explain it (usage error, interruption, or nothing collected).**",
            ]
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
