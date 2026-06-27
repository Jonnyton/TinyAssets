"""Multi-provider claim helper for STATUS.md Work table.

Cross-provider session-start ritual. Any provider (Claude Code, Codex, Cursor,
future) runs this from a fresh checkout to discover what's safe to claim
without announcement.

Usage
-----
    python scripts/claim_check.py
    python scripts/claim_check.py --provider codex
    python scripts/claim_check.py --provider codex-gpt5-desktop
    python scripts/claim_check.py --provider codex-gpt5-desktop --check-files scripts/claim_check.py
    python scripts/claim_check.py --provider codex-gpt5-desktop \
        --check-files "tinyassets/api/runs.py, tests/"
    python scripts/claim_check.py --provider codex-gpt5-desktop --json
    python scripts/claim_check.py --provider cursor --reap
    python scripts/claim_check.py --provider cursor-gpt55 --reap

Output sections
---------------
- PROSPECTIVE FILE CHECK: optional `--check-files` report showing whether
  a proposed Files cell overlaps another provider's active claim.
- CLAIMABLE: rows where status=pending, all Depends are done, and Files
  write-set does not overlap any in-flight or claimed row.
- BLOCKED: pending rows whose Depends are not yet done.
- STALE-CLAIMS: rows with status=claimed:* whose Files have seen no commits
  in the last 24h and whose row has no fresh active-date heartbeat
  (candidates for reaping).
- IN-FLIGHT: rows actively claimed; their Files are off-limits to others.

Reads STATUS.md as authoritative. Uses `git log --since=24.hours -- <file>`
to detect landed activity. A Work row can also include an explicit heartbeat
such as `ACTIVE 2026-04-28`; this prevents active uncommitted work in a
shared checkout from being misclassified as stale. Stdlib-only.

Conventions parsed
------------------
The STATUS.md Work-table row schema is:

| Task | Files | Depends | Status |

- Files: comma- or semicolon-separated paths, possibly with a leading "..."
  prefix. Globs and natural-language hints ("plugin mirror") are tolerated;
  matching falls back to substring overlap.
- Depends: comma-separated list of task IDs (e.g. "#18, #23"), the literal
  "-" (none), or task names. Resolves status of each dependency in the same
  table.
- Status: one of {pending, claimed:<provider>, in-flight, dev-ready,
  host-action, host-decision, host-review, monitoring, done}. Anything
  matching `claimed:*` or `in-flight` is treated as a claim.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Force UTF-8 stdout so em-dashes / non-ASCII identifiers in STATUS.md
# render correctly on Windows consoles (cp1252 default mojibakes them).
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError, OSError):
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
STATUS_PATH = REPO_ROOT / "STATUS.md"
STALE_THRESHOLD_S = 24 * 60 * 60  # 24h

CLAIMED_RE = re.compile(r"^claimed:(\S+)", re.IGNORECASE)
TASK_ID_RE = re.compile(r"#(\d+)")


@dataclass
class Row:
    raw_task: str
    files: list[str]
    depends_raw: str
    status: str
    line_no: int

    @property
    def task_label(self) -> str:
        # First bolded chunk or first 80 chars.
        m = re.search(r"\*\*(.+?)\*\*", self.raw_task)
        return (m.group(1) if m else self.raw_task)[:80]

    @property
    def task_ids(self) -> list[str]:
        return TASK_ID_RE.findall(self.raw_task)

    @property
    def depends_ids(self) -> list[str]:
        return TASK_ID_RE.findall(self.depends_raw)

    @property
    def claimer(self) -> str | None:
        m = CLAIMED_RE.match(self.status.strip())
        return m.group(1) if m else None

    @property
    def is_claimed(self) -> bool:
        return self.claimer is not None or self.status.strip().lower() == "in-flight"

    @property
    def is_pending(self) -> bool:
        s = self.status.strip().lower()
        return s in {"pending", "dev-ready", "dev", "nav-then-dev"} or s.startswith("dev")

    @property
    def file_globs(self) -> list[str]:
        return self.files


def parse_status() -> list[Row]:
    """Extract Work-table rows from STATUS.md."""
    rows: list[Row] = []
    in_work = False
    in_table = False
    for i, line in enumerate(STATUS_PATH.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if s.startswith("## Work"):
            in_work = True
            continue
        if in_work and s.startswith("## "):
            break  # left the section
        if not in_work:
            continue
        if s.startswith("|") and "---" in s:
            in_table = True
            continue
        if not in_table or not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 4:
            continue
        if cells[0].lower().startswith("task"):  # header
            continue
        task, files_raw, depends_raw, status = cells[:4]
        # Split Files on comma or semicolon, respecting markdown backticks.
        files = _split_files(files_raw)
        rows.append(
            Row(
                raw_task=task,
                files=files,
                depends_raw=depends_raw,
                status=status,
                line_no=i,
            )
        )
    return rows


def _split_files(raw: str) -> list[str]:
    """Split a Files cell into atoms, stripping markdown noise."""
    # Strip backticks; they're decoration in the table, not part of paths.
    cleaned = raw.replace("`", "")
    parts = re.split(r"[,;]", cleaned)
    return [p.strip() for p in parts if p.strip() and p.strip() != "-"]


def split_cli_files(raw_parts: list[str] | None) -> list[str] | None:
    """Split one or more CLI --check-files arguments into Files-cell atoms."""
    if raw_parts is None:
        return None
    atoms: list[str] = []
    for raw in raw_parts:
        atoms.extend(_split_files(raw))
    return atoms


def files_overlap(a: list[str], b: list[str]) -> list[str]:
    """Return atoms from a that appear to overlap b. Substring on either side."""
    hits: list[str] = []
    for x in a:
        if not x or x in {"-", "..."}:
            continue
        for y in b:
            if not y or y in {"-", "..."}:
                continue
            # Direct substring either direction = overlap candidate.
            if x in y or y in x:
                hits.append(x)
                break
    return hits


def find_stale_claims(rows: list[Row]) -> list[tuple[Row, str]]:
    """Return (row, reason) for claims with no commit activity in 24h.

    Skips rows whose Files atoms don't include any real-looking path
    (meta-rows like "user-sim" or "~53 test files" can't be checked
    against git history; treat as not-stale rather than false-positive).
    Also skips rows with a fresh `ACTIVE YYYY-MM-DD` heartbeat so concurrent
    providers can keep a claim alive while building and testing before commit.
    """
    stale: list[tuple[Row, str]] = []
    cutoff = time.time() - STALE_THRESHOLD_S
    iso_cutoff = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(cutoff))
    for row in rows:
        if not row.is_claimed:
            continue
        if _has_fresh_activity_marker(row, cutoff):
            continue
        real_paths = [f.split()[0] for f in row.files if _looks_like_path(f)]
        if not real_paths:
            continue  # No checkable paths; assume not stale.
        active = False
        for path in real_paths:
            try:
                out = subprocess.run(
                    [
                        "git",
                        "log",
                        f"--since={iso_cutoff}",
                        "--pretty=oneline",
                        "--",
                        path,
                    ],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if out.stdout.strip():
                    active = True
                    break
            except (subprocess.TimeoutExpired, OSError):
                # Be conservative: don't flag stale on git errors.
                active = True
                break
        if not active:
            stale.append((row, f"no commits touching {', '.join(real_paths)} since {iso_cutoff}"))
    return stale


def _has_fresh_activity_marker(row: Row, cutoff_epoch: float) -> bool:
    """Return true when a row contains a fresh active-date heartbeat.

    Accepted forms are intentionally simple and human-editable:
    `ACTIVE 2026-04-28` or `active:2026-04-28` anywhere in the task/status
    text. A date-only marker stays fresh through the end of that local day.
    """
    text = f"{row.raw_task} {row.status}"
    for match in re.finditer(r"\bactive[:\s]+(\d{4}-\d{2}-\d{2})\b", text, re.IGNORECASE):
        try:
            marker = time.strptime(match.group(1), "%Y-%m-%d")
        except ValueError:
            continue
        end_of_day = time.mktime(
            (
                marker.tm_year,
                marker.tm_mon,
                marker.tm_mday,
                23,
                59,
                59,
                marker.tm_wday,
                marker.tm_yday,
                marker.tm_isdst,
            )
        )
        if end_of_day >= cutoff_epoch:
            return True
    return False


def _looks_like_path(s: str) -> bool:
    """Heuristic: does this Files atom look like a real file/dir path?"""
    head = s.split()[0] if s else ""
    if not head:
        return False
    # Reject natural-language hints.
    if " " in s and "/" not in head and "." not in head:
        return False
    # Accept anything with a separator or extension.
    return "/" in head or "." in head or head.endswith("py") or "_" in head


def classify(
    rows: list[Row], provider: str
) -> tuple[list[Row], list[tuple[Row, list[str]]], list[Row], list[Row]]:
    """Return (claimable, blocked, in_flight, host_owned)."""
    in_flight = [r for r in rows if r.is_claimed]
    in_flight_files: list[str] = []
    for r in in_flight:
        in_flight_files.extend(r.files)

    done_ids: set[str] = set()
    for r in rows:
        if r.status.strip().lower() in {"done", "completed", "landed", "shipped"}:
            done_ids.update(r.task_ids)

    claimable: list[Row] = []
    blocked: list[tuple[Row, list[str]]] = []
    host_owned: list[Row] = []

    for r in rows:
        s = r.status.strip().lower()
        if r.is_claimed:
            continue
        # Host-owned: explicit tags + any status mentioning "host" or "host-only".
        if (
            s in {"host-decision", "host-action", "host-review", "monitoring"}
            or "host" in s
            or "manual" in s
        ):
            host_owned.append(r)
            continue
        if s in {"done", "completed", "landed", "shipped"}:
            continue
        # Dep-check on numeric IDs (#NN).
        unmet_ids = [f"#{d}" for d in r.depends_ids if d not in done_ids]
        # Also check non-numeric depends like "Arc C" or "host" — those count as unmet.
        depends_lower = r.depends_raw.lower().strip()
        unmet_words: list[str] = []
        if depends_lower and depends_lower != "-":
            non_numeric = re.sub(r"#\d+", "", depends_lower).strip(" ,")
            if non_numeric and non_numeric not in {"none", ""}:
                unmet_words.append(non_numeric)
        # File-overlap check against in-flight rows.
        overlap = files_overlap(r.files, in_flight_files)
        reasons = unmet_ids + unmet_words
        if overlap:
            reasons.append("files-overlap:" + ",".join(overlap))
        if reasons:
            blocked.append((r, reasons))
            continue
        claimable.append(r)

    return claimable, blocked, in_flight, host_owned


def prospective_conflicts(
    proposed_files: list[str],
    in_flight: list[Row],
    provider: str,
) -> tuple[list[tuple[Row, list[str]]], list[tuple[Row, list[str]]]]:
    """Return (other_provider_conflicts, own_claim_overlaps)."""
    conflicts: list[tuple[Row, list[str]]] = []
    own_overlaps: list[tuple[Row, list[str]]] = []
    for row in in_flight:
        overlap = files_overlap(proposed_files, row.files)
        if not overlap:
            continue
        if row.claimer == provider:
            own_overlaps.append((row, overlap))
        else:
            conflicts.append((row, overlap))
    return conflicts, own_overlaps


def render(
    provider: str,
    claimable: list[Row],
    blocked: list[tuple[Row, list[str]]],
    in_flight: list[Row],
    host_owned: list[Row],
    stale: list[tuple[Row, str]],
    show_reap: bool,
    prospective_files: list[str] | None = None,
) -> str:
    out: list[str] = []
    out.append(f"# claim_check — provider: {provider}")
    out.append("")
    if prospective_files is not None:
        out.extend(render_prospective_check(provider, prospective_files, in_flight))
        out.append("")
    out.append(f"## CLAIMABLE ({len(claimable)})")
    if not claimable:
        out.append("- (none — see BLOCKED below or wait for in-flight to land)")
    for r in claimable:
        out.append(f"- L{r.line_no}: {r.task_label}")
        out.append(f"    Files: {', '.join(r.files) or '(none listed)'}")
        out.append(f"    Status currently: {r.status}")
    out.append("")
    out.append(f"## BLOCKED ({len(blocked)})")
    if not blocked:
        out.append("- (none)")
    for r, reasons in blocked:
        out.append(f"- L{r.line_no}: {r.task_label}")
        out.append(f"    Blocked by: {', '.join(reasons)}")
    out.append("")
    out.append(f"## IN-FLIGHT ({len(in_flight)})  — files off-limits")
    for r in in_flight:
        claim_label = r.claimer or "in-flight"
        out.append(f"- L{r.line_no}: claimed:{claim_label} — {r.task_label}")
        out.append(f"    Files: {', '.join(r.files) or '(none listed)'}")
    out.append("")
    out.append(f"## HOST-OWNED ({len(host_owned)})  — wait for host")
    for r in host_owned:
        out.append(f"- L{r.line_no}: {r.status} — {r.task_label}")
    out.append("")
    out.append(f"## STALE-CLAIM CANDIDATES ({len(stale)})")
    if not stale:
        out.append("- (none — all in-flight rows have recent commits)")
    for r, reason in stale:
        out.append(f"- L{r.line_no}: claimed:{r.claimer or '?'} — {r.task_label}")
        out.append(f"    Reason: {reason}")
        if show_reap:
            out.append(
                f"    Suggested edit: change Status cell on L{r.line_no} → "
                f"reaped:{provider}:no-activity-24h"
            )
    out.append("")
    out.append(
        "Claim by editing STATUS.md: change the row's Status cell "
        f"to `claimed:{provider}`. Then work in a worktree/branch. "
        "On land, change Status to `done` and delete the row in the same commit."
    )
    return "\n".join(out)


def render_prospective_check(
    provider: str, proposed_files: list[str], in_flight: list[Row]
) -> list[str]:
    out: list[str] = []
    out.append("## PROSPECTIVE FILE CHECK")
    if not proposed_files:
        out.append(
            "- No proposed files parsed. Pass comma-separated Files atoms after --check-files."
        )
        return out

    out.append(f"- Proposed Files: {', '.join(proposed_files)}")
    conflicts, own_overlaps = prospective_conflicts(proposed_files, in_flight, provider)
    if not conflicts:
        out.append("- CLEAR: no overlap with another provider's claimed/in-flight Files.")
    else:
        out.append("- BLOCKED: overlaps another provider's claimed/in-flight Files.")
        for row, hits in conflicts:
            claim_label = row.claimer or "in-flight"
            out.append(f"    L{row.line_no}: claimed:{claim_label} overlaps {', '.join(hits)}")
            out.append(f"    Task: {row.task_label}")

    if own_overlaps:
        out.append("- Own active claim overlap:")
        for row, hits in own_overlaps:
            out.append(f"    L{row.line_no}: {', '.join(hits)} ({row.task_label})")
    return out


def row_payload(row: Row) -> dict[str, object]:
    return {
        "line_no": row.line_no,
        "task": row.raw_task,
        "task_label": row.task_label,
        "files": row.files,
        "depends": row.depends_raw,
        "status": row.status,
        "claimer": row.claimer,
        "task_ids": row.task_ids,
        "depends_ids": row.depends_ids,
    }


def build_payload(
    provider: str,
    claimable: list[Row],
    blocked: list[tuple[Row, list[str]]],
    in_flight: list[Row],
    host_owned: list[Row],
    stale: list[tuple[Row, str]],
    show_reap: bool,
    prospective_files: list[str] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "provider": provider,
        "counts": {
            "claimable": len(claimable),
            "blocked": len(blocked),
            "in_flight": len(in_flight),
            "host_owned": len(host_owned),
            "stale": len(stale),
        },
        "claimable": [row_payload(row) for row in claimable],
        "blocked": [
            {"row": row_payload(row), "reasons": reasons} for row, reasons in blocked
        ],
        "in_flight": [row_payload(row) for row in in_flight],
        "host_owned": [row_payload(row) for row in host_owned],
        "stale": [
            {
                "row": row_payload(row),
                "reason": reason,
                "suggested_reap_status": (
                    f"reaped:{provider}:no-activity-24h" if show_reap else None
                ),
            }
            for row, reason in stale
        ],
    }
    if prospective_files is not None:
        conflicts, own_overlaps = prospective_conflicts(
            prospective_files, in_flight, provider
        )
        payload["prospective_file_check"] = {
            "files": prospective_files,
            "clear": not conflicts,
            "conflicts": [
                {"row": row_payload(row), "overlap": hits} for row, hits in conflicts
            ],
            "own_overlaps": [
                {"row": row_payload(row), "overlap": hits}
                for row, hits in own_overlaps
            ],
        }
    return payload


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Multi-provider claim helper for STATUS.md.")
    ap.add_argument(
        "--provider",
        default="unknown",
        help="Your provider name (claude-code, codex, cursor, ...). Used for claim labels.",
    )
    ap.add_argument(
        "--reap",
        action="store_true",
        help="Show suggested STATUS.md edits to reap stale claims.",
    )
    ap.add_argument(
        "--check-files",
        nargs="+",
        help=(
            "Prospective Files-cell atoms to check against active claims. "
            "Accepts one or more arguments; each may be comma- or semicolon-separated."
        ),
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report instead of the human text report.",
    )
    args = ap.parse_args(argv)

    if not STATUS_PATH.exists():
        print(f"STATUS.md not found at {STATUS_PATH}", file=sys.stderr)
        return 2

    rows = parse_status()
    claimable, blocked, in_flight, host_owned = classify(rows, args.provider)
    stale = find_stale_claims(rows)
    prospective_files = split_cli_files(args.check_files)
    if args.json:
        payload = build_payload(
            args.provider,
            claimable,
            blocked,
            in_flight,
            host_owned,
            stale,
            args.reap,
            prospective_files,
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print(
        render(
            args.provider,
            claimable,
            blocked,
            in_flight,
            host_owned,
            stale,
            args.reap,
            prospective_files,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
