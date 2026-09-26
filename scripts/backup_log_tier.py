"""Build the nightly log tier: recent journal history, redacted and compressed.

Third tier of deploy/backup.sh, alongside the brain and full tiers. The other
two carry state; this one carries evidence -- the container output that used to
exist only inside a container and died with it.

    python3 scripts/backup_log_tier.py \\
        --out /tmp/tinyassets-logs-2026-09-26T03-00-00Z.tar.gz \\
        --since '3 days ago'

Every line passes through scripts/redact_log_bundle.py before it is written,
because the bundle ships to GitHub release assets -- off the droplet.

Sources are journal queries, not files, and that is the point: the journal keeps
entries across container recreates, so `container:tinyassets-logs` reads back
through the deploys that used to erase this history. `tinyassets-logs` is the
Vector sidecar, which re-emits every forwarded daemon / tunnel / slack-agent
line on its own stdout (deploy/compose.yml, deploy/vector.yaml), so one query
covers all of them; the JSON on each line carries the originating `tag`.

Timestamps are `short-iso-precise` (microseconds). The investigation that
prompted this (2026-09-26, docs/ops/log-aggregation-runbook.md) needed per-attempt
latency, and second-granularity timestamps cannot supply it.

Exit codes
----------
0   bundle written (possibly with some sources empty -- see the manifest).
1   argument error, or the output path is unwritable.
3   journalctl is unavailable or refused every source. The caller treats this as
    a skipped tier, never as a failed backup: a log-collection problem must not
    starve the brain archive.

Stdlib only -- runs from the host-uptime runtime closure.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from redact_log_bundle import redact_line  # noqa: E402

DEFAULT_SOURCES = (
    "container:tinyassets-logs",
    "unit:tinyassets-daemon.service",
    "unit:tinyassets-backup.service",
)
DEFAULT_SINCE = "3 days ago"
MANIFEST_NAME = "manifest.tsv"
# Cap on the bytes written per source, so one runaway day cannot make the bundle
# unshippable as a GitHub release asset.
DEFAULT_MAX_BYTES = 64 * 1024 * 1024
# Cap on what journalctl EMITS, which is the one that bounds memory: the query is
# read into a string, so without this the process size is whatever the window
# happens to hold. `--lines` returns the most recent N entries, so the cap also
# picks the right end of the window (cross-family review,
# output/codex-log-durability-review.md §5 and its closing note).
DEFAULT_MAX_LINES = 50_000
# Wall-clock bound per source. `tinyassets-backup.service` has
# `TimeoutStartSec=30min` for the WHOLE unit, and this tier is the least valuable
# thing in it, so it must not be able to spend that budget: a hung journal would
# otherwise get the unit killed before the irreplaceable brain tier finishes
# shipping.
DEFAULT_TIMEOUT_SECONDS = 120


def _journalctl_argv(
    source: str, *, since: str, binary: str, max_lines: int
) -> list[str]:
    """Translate a `kind:name` source into a journalctl invocation."""
    kind, _, name = source.partition(":")
    if not name:
        raise ValueError(f"source {source!r} must be 'container:<name>' or 'unit:<name>'")
    common = [
        binary,
        "--no-pager",
        "--output=short-iso-precise",
        "--since",
        since,
        "--lines",
        str(max_lines),
    ]
    if kind == "container":
        # Docker's journald driver stamps CONTAINER_NAME per entry, so this match
        # spans every past generation of that container -- the whole reason the
        # journal is the durable home rather than the container's own log file.
        return [*common, f"CONTAINER_NAME={name}"]
    if kind == "unit":
        return [*common, "-u", name]
    raise ValueError(f"unknown source kind {kind!r} in {source!r}")


def _safe_file_name(source: str) -> str:
    kind, _, name = source.partition(":")
    return f"{kind}-{name}".replace("/", "_").replace(os.sep, "_") + ".log"


# journalctl writes its own status markers to STDOUT, framed in dashes, and exits
# 0 while doing it. `-- No entries --` is the one that matters: counted as data it
# makes an empty journal report as a healthy source, which is the failure this
# tier exists to remove -- a mechanism that ships nothing and looks fine. Found
# against a real journalctl; a stubbed one returns clean output and hides it.
_NO_ENTRIES = re.compile(r"^--\s*no entries\s*--$", re.IGNORECASE)
# The other markers (`-- Boot <id> --`, `-- Reboot --`) are real context and are
# kept in the file, but they are not evidence, so they do not count as data.
_JOURNAL_MARKER = re.compile(r"^--\s.*\s--$")


def collect_source(
    source: str,
    destination: Path,
    *,
    since: str,
    binary: str,
    max_bytes: int,
    max_lines: int = DEFAULT_MAX_LINES,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    runner=subprocess.run,
) -> tuple[int, str]:
    """Write one redacted journal query to ``destination``.

    Returns ``(lines_written, status)``. ``status`` is ``ok``, ``empty``,
    ``truncated``, or ``error:<detail>`` -- recorded in the manifest so a source
    that stopped producing is visible in the bundle instead of merely absent.

    Bounded three ways, because this is the least valuable thing in a unit with a
    30-minute timeout: ``max_lines`` caps what journalctl emits, ``timeout`` caps
    how long it may take, and ``max_bytes`` caps what is written.
    """
    argv = _journalctl_argv(source, since=since, binary=binary, max_lines=max_lines)
    try:
        completed = runner(
            argv, capture_output=True, text=True, errors="replace", timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return 0, f"error:timeout after {timeout}s"
    except (OSError, ValueError) as exc:
        return 0, f"error:{type(exc).__name__}"
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip().splitlines()
        # The stderr of a failed journalctl can name a unit or a match value;
        # redact it like any other line rather than trusting it.
        reason = redact_line(detail[-1])[:160] if detail else "rc%d" % completed.returncode
        return 0, f"error:{reason}"

    # Redact first, then select which lines fit. Keeping the NEWEST is the whole
    # point: journalctl emits oldest-first, so the original head-first budget
    # discarded the most recent evidence -- exactly the lines an incident needs
    # (cross-family review, output/codex-log-durability-review.md, closing note).
    kept: list[str] = []
    budget = max_bytes
    truncated = False
    data_lines = 0
    for raw in reversed((completed.stdout or "").splitlines()):
        stripped = raw.strip()
        if _NO_ENTRIES.match(stripped):
            continue
        line = redact_line(raw) + "\n"
        budget -= len(line.encode("utf-8", errors="replace"))
        if budget < 0:
            truncated = True
            break
        kept.append(line)
        if not _JOURNAL_MARKER.match(stripped):
            data_lines += 1
    kept.reverse()

    with destination.open("w", encoding="utf-8", errors="replace", newline="\n") as handle:
        if truncated:
            handle.write(
                f"[backup-log-tier] older lines dropped at {max_bytes} bytes; "
                "this file holds the most recent of the window\n"
            )
        handle.writelines(kept)

    if truncated:
        return data_lines, "truncated"
    return data_lines, "ok" if data_lines else "empty"


def build_bundle(
    out_path: Path,
    *,
    sources: tuple[str, ...] = DEFAULT_SOURCES,
    since: str = DEFAULT_SINCE,
    binary: str = "journalctl",
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_lines: int = DEFAULT_MAX_LINES,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    runner=subprocess.run,
) -> tuple[int, list[str]]:
    """Write the bundle. Returns ``(exit_code, report_lines)``."""
    report: list[str] = []
    if shutil.which(binary) is None and not Path(binary).exists():
        return 3, [f"journalctl not found ({binary}) — log tier skipped"]

    staging = Path(tempfile.mkdtemp(prefix="tinyassets-log-tier."))
    try:
        rows = [("source", "file", "lines", "status")]
        data_total = 0
        for source in sources:
            try:
                file_name = _safe_file_name(source)
                lines, status = collect_source(
                    source,
                    staging / file_name,
                    since=since,
                    binary=binary,
                    max_bytes=max_bytes,
                    max_lines=max_lines,
                    timeout=timeout,
                    runner=runner,
                )
            except ValueError as exc:
                return 1, [str(exc)]
            rows.append((source, file_name, str(lines), status))
            report.append(f"{source}: {lines} lines ({status})")
            data_total += lines
        if not data_total:
            # No source produced a single line. For a running daemon over a
            # multi-day window that is a broken pipeline, not a quiet night --
            # and shipping an empty tarball every night is indistinguishable
            # from success, which is precisely what the retired ship-logs timer
            # did in reverse. Skip loudly instead.
            return 3, [*report, "no log source produced any lines — log tier skipped"]

        manifest = staging / MANIFEST_NAME
        manifest.write_text(
            "".join("\t".join(row) + "\n" for row in rows),
            encoding="utf-8",
            newline="\n",
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(out_path, "w:gz") as archive:
                for entry in sorted(staging.iterdir()):
                    archive.add(entry, arcname=entry.name)
        except OSError as exc:
            return 1, [*report, f"cannot write {out_path}: {exc}"]
        report.append(f"wrote {out_path} ({out_path.stat().st_size} bytes)")
        return 0, report
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="output .tar.gz path")
    parser.add_argument("--since", default=DEFAULT_SINCE, help="journalctl --since window")
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        metavar="KIND:NAME",
        help="container:<name> or unit:<name>; repeatable (default: %s)"
        % ", ".join(DEFAULT_SOURCES),
    )
    parser.add_argument("--journalctl", default="journalctl", help="journalctl binary")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS,
        help="per-source wall-clock bound; the backup unit's own is 30 min",
    )
    args = parser.parse_args(argv)

    code, report = build_bundle(
        args.out,
        sources=tuple(args.sources or DEFAULT_SOURCES),
        since=args.since,
        binary=args.journalctl,
        max_bytes=args.max_bytes,
        max_lines=args.max_lines,
        timeout=args.timeout,
    )
    for line in report:
        print(f"[backup-log-tier] {line}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
