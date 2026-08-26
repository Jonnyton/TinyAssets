"""TimestampLintRun for wiki/brain markdown pages.

Strictly checks typed coordination timestamp fields in frontmatter and YAML
state blocks. Prose body dates are intentionally ignored so source/canon
content keeps source fidelity.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

TIMESTAMP_KEYS = frozenset(
    {
        "applied_at",
        "applied_at_utc",
        "authored_at",
        "authored_at_utc",
        "created",
        "created_at",
        "created_at_utc",
        "expires_at",
        "expires_at_utc",
        "ingested_at",
        "ingested_at_utc",
        "refactor_pass_at",
        "refactor_pass_at_utc",
        "revoked_at",
        "revoked_at_utc",
        "source_observed_at",
        "source_observed_at_utc",
        "source_published_at",
        "source_published_at_utc",
        "updated",
        "updated_at",
        "updated_at_utc",
        "verified_at",
        "verified_at_utc",
    }
)

UNKNOWN_VALUES = frozenset({"", "null", "~", "unknown", "tbd", "n/a"})
UTC_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
KEY_VALUE_RE = re.compile(
    r"^(?P<indent>\s*)(?:-\s*)?(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*(?P<value>.*)$"
)
FENCE_RE = re.compile(r"^\s*```\s*(?P<lang>[A-Za-z0-9_-]*)\s*$")


@dataclass(frozen=True)
class TimestampViolation:
    path: str
    line: int
    field: str
    value: str
    reason: str


def parse_utc_z(raw: str) -> datetime | None:
    value = raw.strip().strip("'\"")
    if not UTC_Z_RE.match(value):
        return None
    return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)


def parse_write_time(raw: str) -> datetime:
    parsed = parse_utc_z(raw)
    if parsed is not None:
        return parsed
    try:
        value = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"write time must be ISO8601, got {raw!r}"
        ) from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("write time must include timezone")
    return parsed.astimezone(timezone.utc)


def markdown_yaml_segments(text: str) -> Iterable[tuple[int, list[str]]]:
    """Yield frontmatter and YAML fenced blocks as (start_line, lines)."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                yield 2, lines[1:index]
                break

    in_yaml = False
    start_line = 0
    block: list[str] = []
    for index, line in enumerate(lines, start=1):
        match = FENCE_RE.match(line)
        if match:
            if in_yaml:
                yield start_line, block
                in_yaml = False
                block = []
            elif match.group("lang").lower() in {"yaml", "yml"}:
                in_yaml = True
                start_line = index + 1
            continue
        if in_yaml:
            block.append(line)


def strip_inline_comment(value: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(value):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return value[:index].strip()
    return value.strip()


def lint_yaml_lines(
    *,
    path: Path,
    start_line: int,
    lines: list[str],
    write_time_utc: datetime,
    tolerance: timedelta,
) -> list[TimestampViolation]:
    violations: list[TimestampViolation] = []
    field_stack: list[tuple[int, str]] = []

    for offset, line in enumerate(lines):
        match = KEY_VALUE_RE.match(line)
        if not match:
            continue

        indent = len(match.group("indent"))
        key = match.group("key")
        value = strip_inline_comment(match.group("value")).strip().strip("'\"")
        while field_stack and field_stack[-1][0] >= indent:
            field_stack.pop()
        field_stack.append((indent, key))
        field_path = ".".join(part for _, part in field_stack)

        if key not in TIMESTAMP_KEYS:
            continue
        if value.lower() in UNKNOWN_VALUES:
            continue
        if not value:
            violations.append(
                TimestampViolation(
                    str(path),
                    start_line + offset,
                    field_path,
                    value,
                    "typed timestamp field must be scalar UTC ISO8601 with Z suffix",
                )
            )
            continue

        parsed = parse_utc_z(value)
        if parsed is None:
            violations.append(
                TimestampViolation(
                    str(path),
                    start_line + offset,
                    field_path,
                    value,
                    "typed timestamp field must use UTC ISO8601 Z suffix",
                )
            )
            continue
        if parsed > write_time_utc + tolerance:
            violations.append(
                TimestampViolation(
                    str(path),
                    start_line + offset,
                    field_path,
                    value,
                    "typed timestamp field is in the future of write_time_utc",
                )
            )

    return violations


def lint_markdown(
    path: Path,
    *,
    write_time_utc: datetime,
    tolerance: timedelta,
) -> list[TimestampViolation]:
    text = path.read_text(encoding="utf-8")
    violations: list[TimestampViolation] = []
    for start_line, lines in markdown_yaml_segments(text):
        violations.extend(
            lint_yaml_lines(
                path=path,
                start_line=start_line,
                lines=lines,
                write_time_utc=write_time_utc,
                tolerance=tolerance,
            )
        )
    return violations


def _format_violation(violation: TimestampViolation) -> str:
    return (
        f"{violation.path}:{violation.line}: {violation.field}: "
        f"{violation.reason} ({violation.value!r})"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--write-time",
        type=parse_write_time,
        default=datetime.now(timezone.utc),
        help="UTC write time to compare against; defaults to current time.",
    )
    parser.add_argument(
        "--tolerance-seconds",
        type=float,
        default=60.0,
        help="Allowed future skew before rejection.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON violations.")
    args = parser.parse_args(argv)

    violations: list[TimestampViolation] = []
    tolerance = timedelta(seconds=args.tolerance_seconds)
    for path in args.paths:
        violations.extend(
            lint_markdown(path, write_time_utc=args.write_time, tolerance=tolerance)
        )

    if args.json:
        print(json.dumps([asdict(item) for item in violations], indent=2))
    else:
        for violation in violations:
            print(_format_violation(violation), file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
