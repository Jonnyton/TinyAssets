"""Say what a green run did not cover, and fail when that set grows silently.

A local Windows run of this suite skips every POSIX-only path and still prints
the same word a full run prints: green. Six CI rounds were spent on assertions
that could only ever fail on Linux, each one green here first -- an assertion
encoding a superseded contract survives exactly as long as nothing executes it.

So a run's skips are evidence, not noise. ``tests/skip_census_plugin.py``
records them; this reads that JSON and answers three questions:

1. **How much of this run was not run here?** Grouped by reason class, with the
   headline that a platform skip is UNVERIFIED on this host rather than passing.
2. **Is that within the agreed bound?** ``--assert-max-platform-skips N``.
3. **Did this change ADD a platform skip?** ``--baseline`` against the committed
   ``.github/platform-skip-baseline.json``. A new Windows-only skip then shows
   up in review, where it is a five-line conversation, instead of in CI three
   rounds later.

Usage::

    python -m pytest -p tests.skip_census_plugin --skip-census-out census.json
    python scripts/skip_census.py census.json --baseline .github/platform-skip-baseline.json

Exit codes: ``0`` clean, ``1`` a gate failed, ``2`` the report cannot be read
or was produced on a different kind of host than the baseline.

Classification is lexical, and deliberately so: the reason string is the only
thing a skip is required to carry. Order: platform, then missing tool, then
environment, then other. A reason naming a platform fact is host-shaped
whatever else it mentions, and the headline's claim -- that another host covers
these -- stays TRUE for it either way.

That order was measured, not assumed. Checking the tool first reads better in
the abstract ("no git on this Windows box" is fixed by installing git HERE),
but on this suite's real reasons it drops host-shaped holes out of the count:

    ws.bundle shells out to a BARE git, which resolves only through execvp's
    CS_PATH fallback; the sandbox child is given no PATH

names a tool and an absence, and git is already installed -- the hole is
Windows process creation, and Linux covers it. Tool-first moved three such
tests out of the headline. Platform-first's opposite error only ever moves a
test INTO a count another host really does cover, which is the safe direction.

The known limit is a reason using a platform word in an unrelated sense ("the
sliding windows overlap"); word boundaries stop the substring case
("windowsill"), and nothing stops the homonym case, so reasons are also printed
for review rather than only counted.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

REPORT_SCHEMA = "skip-census/1"
BASELINE_SCHEMA = "platform-skip-baseline/1"

CLASS_PLATFORM = "platform"
CLASS_MISSING_TOOL = "missing-tool"
CLASS_ENV = "env"
CLASS_OTHER = "other"
#: Checked and printed in this order; the first is what the headline counts.
CLASS_ORDER = (CLASS_PLATFORM, CLASS_MISSING_TOOL, CLASS_ENV, CLASS_OTHER)

#: Whole words. ``\b`` is what keeps "windowsill" and "point" out of the
#: platform class; a naive substring test classifies both.
_PLATFORM_WORDS = (
    "posix",
    "windows",
    "win32",
    "win64",
    "linux",
    "darwin",
    "macos",
    "unix",
    "nt",
    "wsl",
    "bwrap",
    "bubblewrap",
    "symlink",
    "symlinks",
    "symlinked",
    "junction",
    "junctions",
    "fifo",
    "mkfifo",
    "dir_fd",
    "o_nofollow",
    "max_path",
    "cygwin",
)
#: Not words -- they carry punctuation, so they are matched literally. Each is
#: unambiguous enough that a substring test is the right test. The absolute
#: POSIX paths are here because this suite skips on them by name ("the rm(1)
#: wrapper needs /bin/rm"), and no Windows path can contain them.
_PLATFORM_FRAGMENTS = (
    "os.name",
    "sys.platform",
    "/proc",
    "max path",
    "/bin/",
    "/usr/",
    "/dev/",
    # A case-insensitive filesystem is a property of the host, not of a tool:
    # this suite skips three case-coexistence tests on it.
    "case-insensitive",
    "case insensitive",
)

#: Tools that COULD be installed on any host. A Linux-only facility (bwrap,
#: /proc, dir_fd) is a platform fact instead: no amount of installing puts it
#: on a Windows box, so another host is what covers it.
_TOOL_WORDS = (
    "git",
    "node",
    "npm",
    "yarn",
    "docker",
    "gh",
    "curl",
    "bash",
    "shellcheck",
    "actionlint",
    "ffmpeg",
    "pandoc",
    "java",
    "sqlite3",
    "graphviz",
)
_ABSENCE_FRAGMENTS = (
    "no ",
    "not installed",
    "not available",
    "unavailable",
    "missing",
    "absent",
    "not found",
    "there is none",
    "none here",
    "requires ",
    "needs ",
    "could not find",
    "cannot find",
    "not on path",
    "is not on this",
)
#: Absence phrases that name an installable dependency on their own, because
#: the thing they name is open-ended: this suite skips on "pyyaml not
#: installed" and "shellcheck not installed", and a fixed list of tool names
#: can never cover every library a test imports.
_INSTALLABLE_FRAGMENTS = (
    "not installed",
    "not on path",
    "could not find",
    "cannot find",
    "not importable",
    "no such binary",
    "is missing",
    # pytest.importorskip's own words, and the shape every optional-dependency
    # skip in this suite takes.
    "could not import",
    "no module named",
)

_ENV_WORDS = (
    "credential",
    "credentials",
    "token",
    "secret",
    "secrets",
    "network",
    "offline",
    "internet",
    "vault",
    "dns",
    "deployed",
    "droplet",
    "dsn",
    "postgres",
)
_ENV_FRAGMENTS = (
    "api key",
    "api_key",
    "apikey",
    "_api_key",
    "env var",
    "environment variable",
    "live server",
    "live endpoint",
)


class CensusError(RuntimeError):
    """The report or baseline cannot be used. Never guessed around."""


def _word_pattern(words: Sequence[str]) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b")


#: A SCREAMING_SNAKE token in the ORIGINAL reason: the general form of "this
#: host was not configured for it". 22 skips in this suite say only
#: "TINYASSETS_TEST_POSTGRES_DSN is required", naming no word any list has.
#: Matched after platform, so MAX_PATH and O_NOFOLLOW are already spoken for.
_ENV_VAR_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")

_PLATFORM_RE = _word_pattern(_PLATFORM_WORDS)
_TOOL_RE = _word_pattern(_TOOL_WORDS)
_ENV_RE = _word_pattern(_ENV_WORDS)


def classify_reason(reason: str) -> str:
    """Which kind of hole this skip is.

    Platform first: a reason that names a platform fact is host-shaped even
    when it also names an absent tool, and the tests that proved it on this
    suite are the ones where the tool is INSTALLED and the platform is what
    breaks it (see the module docstring). A missing tool is then a tool name
    with an absence phrase, or a phrase that names an installable dependency on
    its own ("pyyaml not installed" names a library no list could enumerate).
    """
    text = (reason or "").lower()
    if _PLATFORM_RE.search(text) or any(f in text for f in _PLATFORM_FRAGMENTS):
        return CLASS_PLATFORM
    if any(f in text for f in _INSTALLABLE_FRAGMENTS) or (
        _TOOL_RE.search(text) and any(f in text for f in _ABSENCE_FRAGMENTS)
    ):
        return CLASS_MISSING_TOOL
    if (
        _ENV_RE.search(text)
        or any(f in text for f in _ENV_FRAGMENTS)
        or _ENV_VAR_RE.search(reason or "")
    ):
        return CLASS_ENV
    return CLASS_OTHER


@dataclass(frozen=True)
class Entry:
    nodeid: str
    file: str
    kind: str
    reason: str
    reason_class: str
    line: int | None = None

    @classmethod
    def from_json(cls, raw: Any) -> "Entry":
        if not isinstance(raw, dict):
            raise CensusError(f"entry is not an object: {raw!r}")
        try:
            nodeid = str(raw["nodeid"])
            reason = str(raw["reason"])
            kind = str(raw["kind"])
        except KeyError as exc:
            raise CensusError(f"entry is missing {exc.args[0]!r}: {raw!r}") from None
        file = str(raw.get("file") or nodeid.split("::", 1)[0])
        line = raw.get("line")
        return cls(
            nodeid=nodeid,
            file=file.replace("\\", "/"),
            kind=kind,
            reason=reason,
            reason_class=classify_reason(reason),
            line=line if isinstance(line, int) else None,
        )


@dataclass(frozen=True)
class Census:
    host: dict[str, Any]
    totals: dict[str, Any]
    entries: tuple[Entry, ...]
    source: str = "<memory>"

    def of_class(self, reason_class: str) -> tuple[Entry, ...]:
        return tuple(e for e in self.entries if e.reason_class == reason_class)

    def counts(self) -> dict[str, int]:
        counted = Counter(e.reason_class for e in self.entries)
        return {name: counted.get(name, 0) for name in CLASS_ORDER}

    def per_file(self, reason_class: str) -> list[tuple[str, int]]:
        counted = Counter(e.file for e in self.of_class(reason_class))
        # Biggest hole first, then by name so the output is stable.
        return sorted(counted.items(), key=lambda item: (-item[1], item[0]))

    @property
    def os_name(self) -> str:
        return str(self.host.get("os_name", "unknown"))


#: An absolute path anywhere in a reason. A skip that formats an OSError
#: carries pytest's per-run temp directory, which is different on every run.
_VOLATILE_PATH_RE = re.compile(
    r"(?:[A-Za-z]:[\\/]|/(?:tmp|var|home|mnt|private|Users)/)[^\s'\"]*"
)
_BASELINE_REASON_CHARS = 240


def normalize_reason(reason: str) -> str:
    """The reason with per-run paths removed, for storing in the baseline.

    Committed and diffed at review time, so it must be identical across two
    runs of an unchanged tree. Without this, seven entries carry
    ``...\\ta-pt\\cf\\test_x0\\target.tar.gz`` and the baseline is a new file
    every time anyone regenerates it -- which is how a review artifact becomes
    noise nobody reads. Classification always uses the FULL reason; only what
    is written here is normalized.
    """
    collapsed = " ".join(str(reason or "").split())
    replaced = _VOLATILE_PATH_RE.sub("<path>", collapsed)
    if len(replaced) > _BASELINE_REASON_CHARS:
        replaced = replaced[: _BASELINE_REASON_CHARS - 3].rstrip() + "..."
    return replaced


def load_report(path: Path) -> Census:
    """Read a plugin report. A shape this does not understand is an error."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CensusError(f"cannot read {path}: {exc}") from None
    except json.JSONDecodeError as exc:
        raise CensusError(f"{path} is not JSON: {exc}") from None
    return census_from_document(raw, source=str(path))


def census_from_document(raw: Any, *, source: str = "<memory>") -> Census:
    if not isinstance(raw, dict):
        raise CensusError(f"{source}: the report is not an object")
    schema = raw.get("schema")
    if schema != REPORT_SCHEMA:
        raise CensusError(
            f"{source}: schema is {schema!r}, expected {REPORT_SCHEMA!r} -- "
            "regenerate it with tests/skip_census_plugin.py"
        )
    entries = raw.get("entries")
    if not isinstance(entries, list):
        raise CensusError(f"{source}: 'entries' is missing or not a list")
    host = raw.get("host") if isinstance(raw.get("host"), dict) else {}
    totals = raw.get("totals") if isinstance(raw.get("totals"), dict) else {}
    return Census(
        host=dict(host),
        totals=dict(totals),
        entries=tuple(Entry.from_json(item) for item in entries),
        source=source,
    )


# ---------------------------------------------------------------------------
# baseline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BaselineDiff:
    added: tuple[Entry, ...]
    resolved: tuple[str, ...]


def baseline_document(census: Census) -> dict[str, Any]:
    """What gets committed: the platform skips only, sorted, no timestamp.

    Only the platform class, because that is the set another host has to cover.
    No timestamp, because a baseline that changes on every run is a baseline
    nobody reviews.
    """
    return {
        "schema": BASELINE_SCHEMA,
        "host": dict(census.host),
        "note": (
            "Platform skips accepted on this host. A NEW entry means a change "
            "added a test that does not execute here; either that is intended "
            "and the baseline moves in the same commit, or the test should not "
            "be host-conditional. Regenerate with: python -m pytest "
            "-p tests.skip_census_plugin --skip-census-out census.json && "
            "python scripts/skip_census.py census.json --write-baseline "
            ".github/platform-skip-baseline.json"
        ),
        "platform_skips": [
            {
                "nodeid": e.nodeid,
                "file": e.file,
                "kind": e.kind,
                "reason": normalize_reason(e.reason),
            }
            for e in sorted(census.of_class(CLASS_PLATFORM), key=lambda e: e.nodeid)
        ],
    }


def load_baseline(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CensusError(f"cannot read baseline {path}: {exc}") from None
    except json.JSONDecodeError as exc:
        raise CensusError(f"baseline {path} is not JSON: {exc}") from None
    if not isinstance(raw, dict) or raw.get("schema") != BASELINE_SCHEMA:
        raise CensusError(
            f"baseline {path}: schema is {raw.get('schema')!r} if it has one, "
            f"expected {BASELINE_SCHEMA!r}"
        )
    if not isinstance(raw.get("platform_skips"), list):
        raise CensusError(f"baseline {path}: 'platform_skips' is missing or not a list")
    return raw


def compare_to_baseline(census: Census, baseline: dict[str, Any]) -> BaselineDiff:
    """New and resolved platform skips, refusing a cross-host comparison.

    A Windows baseline against a Linux report would report every entry as
    resolved and every Linux-only skip as new -- a diff that is 100% noise and
    reads like a catastrophe. That is an error, not a warning.
    """
    baseline_host = baseline.get("host") if isinstance(baseline.get("host"), dict) else {}
    theirs = str(baseline_host.get("os_name", "unknown"))
    if theirs != census.os_name:
        raise CensusError(
            f"the baseline was taken on os.name={theirs!r} and this report is "
            f"os.name={census.os_name!r}; platform skips are not comparable "
            "across host kinds. Use a baseline from this kind of host."
        )
    known = {
        str(item.get("nodeid"))
        for item in baseline["platform_skips"]
        if isinstance(item, dict)
    }
    current = census.of_class(CLASS_PLATFORM)
    added = tuple(e for e in sorted(current, key=lambda e: e.nodeid) if e.nodeid not in known)
    live = {e.nodeid for e in current}
    resolved = tuple(sorted(nodeid for nodeid in known if nodeid not in live))
    return BaselineDiff(added=added, resolved=resolved)


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


HEADLINE = (
    "{count} tests skipped for platform reasons on this host - they are "
    "UNVERIFIED here; the Linux oracle covers them"
)


def render(census: Census, *, show_entries: bool = False) -> list[str]:
    counts = census.counts()
    totals = census.totals
    lines = [
        f"skip census: {census.source}",
        "host: "
        + " ".join(
            f"{key}={census.host.get(key)}"
            for key in ("os_name", "sys_platform", "python", "machine")
            if census.host.get(key) is not None
        ),
    ]
    if totals:
        lines.append(
            "run: "
            + " | ".join(
                f"{name} {totals.get(name)}"
                for name in (
                    "collected",
                    "passed",
                    "failed",
                    "errors",
                    "skipped",
                    "xfailed",
                    "xpassed",
                )
                if totals.get(name) is not None
            )
        )
    lines.append("")
    lines.append(HEADLINE.format(count=counts[CLASS_PLATFORM]))
    lines.append("")
    for reason_class in CLASS_ORDER:
        entries = census.of_class(reason_class)
        lines.append(f"{reason_class} ({len(entries)})")
        if not entries:
            continue
        for file, count in census.per_file(reason_class):
            lines.append(f"  {count:>4}  {file}")
        if show_entries:
            for entry in sorted(entries, key=lambda e: e.nodeid):
                lines.append(f"        {entry.nodeid}")
                lines.append(f"            [{entry.kind}] {entry.reason}")
    return lines


def render_diff(diff: BaselineDiff) -> list[str]:
    lines: list[str] = []
    if diff.added:
        lines.append("")
        lines.append(
            f"NEW platform skips not in the baseline ({len(diff.added)}) -- this "
            "change made tests stop executing on this host:"
        )
        for entry in diff.added:
            lines.append(f"  + {entry.nodeid}")
            lines.append(f"      {entry.reason}")
    if diff.resolved:
        lines.append("")
        lines.append(
            f"baseline entries no longer skipped ({len(diff.resolved)}) -- good "
            "news; refresh the baseline when convenient:"
        )
        for nodeid in diff.resolved:
            lines.append(f"  - {nodeid}")
    return lines


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skip_census.py",
        description="Classify and gate the skips a test run did not execute.",
    )
    parser.add_argument("report", type=Path, help="JSON written by --skip-census-out")
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="fail when a platform skip appears that this baseline does not have",
    )
    parser.add_argument(
        "--write-baseline",
        type=Path,
        default=None,
        metavar="PATH",
        help="write the current platform skips as a new baseline and exit",
    )
    parser.add_argument(
        "--assert-max-platform-skips",
        type=int,
        default=None,
        metavar="N",
        help="exit 1 when more than N tests skip for platform reasons",
    )
    parser.add_argument(
        "--show-entries",
        action="store_true",
        help="list every nodeid and reason, not just the per-file counts",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="print only the headline and any gate failures",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, out: Any = None) -> int:
    args = _build_parser().parse_args(argv)
    stream = out if out is not None else sys.stdout

    def emit(lines: Iterable[str]) -> None:
        for line in lines:
            print(line, file=stream)

    try:
        census = load_report(args.report)
    except CensusError as exc:
        print(f"skip census: {exc}", file=stream)
        return 2

    if args.write_baseline is not None:
        document = baseline_document(census)
        args.write_baseline.parent.mkdir(parents=True, exist_ok=True)
        args.write_baseline.write_text(
            json.dumps(document, indent=2) + "\n", encoding="utf-8"
        )
        emit(
            [
                f"wrote {len(document['platform_skips'])} platform skip(s) to "
                f"{args.write_baseline}"
            ]
        )
        return 0

    counts = census.counts()
    if args.quiet:
        emit([HEADLINE.format(count=counts[CLASS_PLATFORM])])
    else:
        emit(render(census, show_entries=args.show_entries))

    status = 0
    if args.baseline is not None:
        try:
            diff = compare_to_baseline(census, load_baseline(args.baseline))
        except CensusError as exc:
            print(f"skip census: {exc}", file=stream)
            return 2
        emit(render_diff(diff))
        if diff.added:
            emit(
                [
                    "",
                    f"FAIL: {len(diff.added)} platform skip(s) are new since the "
                    "baseline.",
                ]
            )
            status = 1

    limit = args.assert_max_platform_skips
    if limit is not None and counts[CLASS_PLATFORM] > limit:
        emit(
            [
                "",
                f"FAIL: {counts[CLASS_PLATFORM]} platform skips exceed the "
                f"agreed maximum of {limit}.",
            ]
        )
        status = 1
    return status


if __name__ == "__main__":  # pragma: no cover - exercised by the CLI tests
    raise SystemExit(main())
