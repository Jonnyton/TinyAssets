"""Classify and optionally clean up stale git branches (Layer 1).

Part of the branch lifecycle automation; see
``docs/design-notes/2026-06-24-branch-lifecycle-automation.md``.

Report-first by design. The default mode only classifies and prints (and can
write a rolling tracking issue with ``--issue``). ``--apply`` is the only mode
that deletes anything, and even then hard guardrails protect important
branches.

Categories
----------
PROTECTED    main/master/production/release/* — never touched.
MERGED       already merged into the base ref (ancestor *or* squash-merged) —
             its changes are all on main, so deleting the branch loses nothing.
             Swept in --apply (or --only-merged).
STALE_FLAG   unmerged, no open PR, no commit in STALE_DAYS — reported only.
STALE_DELETE flagged and still untouched past GRACE_DAYS — deleted in --apply.
ACTIVE       has an open PR, or a commit younger than RECENT_DAYS, or simply
             not yet stale — never touched.

Guardrails (hard, always on)
----------------------------
* Never delete a protected branch.
* Never delete a branch with an open PR.
* Never delete a branch with a commit younger than RECENT_DAYS, regardless of
  total age.
* If open-PR data cannot be fetched, unmerged deletion is disabled for the run
  (only provably-merged branches may be swept).
"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from git_squash_merge import is_merged_into  # noqa: E402  (sibling-script import)

PROTECTED_EXACT = {"main", "master", "production", "develop", "HEAD"}
PROTECTED_PREFIXES = ("release/", "hotfix/")
RECENT_DAYS = 7
STALE_DAYS = 7
GRACE_DAYS = 14
ISSUE_MARKER = "<!-- branch-janitor -->"
ISSUE_TITLE = "🧹 Branch janitor report"

CATEGORIES = ("PROTECTED", "ACTIVE", "MERGED", "STALE_FLAG", "STALE_DELETE")
LIVENESS_CATEGORIES = ("OPEN-PR", "MERGED", "CONTAINED", "STRANDED", "UNDETERMINED")


def _force_utf8_stdio() -> None:
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        enc = (getattr(stream, "encoding", None) or "").lower().replace("_", "-")
        if enc == "utf-8":
            continue
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
                continue
            except (AttributeError, ValueError, OSError):
                pass
        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            try:
                wrapped = io.TextIOWrapper(
                    buffer, encoding="utf-8", errors="replace", line_buffering=True
                )
                setattr(sys, name, wrapped)
            except (AttributeError, ValueError, OSError):
                pass


def _run(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, capture_output=True, text=True, check=check, encoding="utf-8", errors="replace"
    )


@dataclass
class BranchVerdict:
    name: str
    category: str
    age_days: int
    reason: str
    last_commit_unix: int


@dataclass(frozen=True)
class PullRequestIndex:
    open_by_branch: dict[str, int]
    all_by_branch: dict[str, int]


@dataclass(frozen=True)
class LivenessVerdict:
    name: str
    category: str
    reason: str
    pr_number: int | None = None
    contained_by: str | None = None


def remote_branches(remote: str, now: int) -> list[tuple[str, int]]:
    """Return (short-name-without-remote-prefix, last-commit-unix) per branch."""
    fmt = "%(refname:short)%09%(committerdate:unix)"
    proc = _run(["git", "for-each-ref", f"--format={fmt}", f"refs/remotes/{remote}"])
    out: list[tuple[str, int]] = []
    prefix = f"{remote}/"
    for line in proc.stdout.splitlines():
        if "\t" not in line:
            continue
        ref, _, ts = line.partition("\t")
        if not ref.startswith(prefix):
            continue
        name = ref[len(prefix):]
        if name in ("HEAD", ""):
            continue
        try:
            out.append((name, int(ts)))
        except ValueError:
            continue
    return out


def open_pr_branches() -> set[str] | None:
    """Head-ref names of open PRs, or None if gh is unavailable/unauthed."""
    proc = _run(["gh", "pr", "list", "--state", "open", "--limit", "1000", "--json", "headRefName"])
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None
    return {row.get("headRefName", "") for row in data if row.get("headRefName")}


def pull_request_index() -> tuple[PullRequestIndex | None, str | None]:
    """Return open/all PR numbers by head branch, or an explicit failure."""
    command = [
        "gh",
        "pr",
        "list",
        "--state",
        "all",
        "--limit",
        "1000",
        "--json",
        "headRefName,number,state",
    ]
    try:
        proc = _run(command)
    except OSError as exc:
        return None, f"gh pr list failed: {exc}"
    if proc.returncode != 0:
        return None, _command_failure("gh pr list", proc)
    try:
        rows = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return None, "gh pr list returned invalid JSON"
    if not isinstance(rows, list):
        return None, "gh pr list returned a non-list JSON value"
    if len(rows) >= 1000:
        return None, "gh pr list reached its 1000-row limit; completeness is unknown"

    open_by_branch: dict[str, int] = {}
    all_by_branch: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            return None, "gh pr list returned a non-object row"
        branch = row.get("headRefName")
        number = row.get("number")
        state = row.get("state")
        if not isinstance(branch, str) or not branch:
            return None, "gh pr list returned a row without headRefName"
        if not isinstance(number, int) or isinstance(number, bool):
            return None, "gh pr list returned a row with an invalid PR number"
        if state not in {"OPEN", "CLOSED", "MERGED"}:
            return None, "gh pr list returned a row with an invalid PR state"
        all_by_branch.setdefault(branch, number)
        if state == "OPEN":
            open_by_branch.setdefault(branch, number)
    return PullRequestIndex(open_by_branch, all_by_branch), None


def is_protected(name: str) -> bool:
    return name in PROTECTED_EXACT or name.startswith(PROTECTED_PREFIXES)


def is_merged(remote: str, name: str, base_ref: str) -> bool:
    # Squash-aware: PRs here squash-merge, so --is-ancestor alone would miss the
    # default merge style and leave merged branches lingering until STALE_DELETE.
    return is_merged_into(_run, f"refs/remotes/{remote}/{name}", base_ref)


def liveness_branches(remote: str) -> tuple[list[str] | None, str | None]:
    """Return remote branch names, preserving git-enumeration failures."""
    command = ["git", "for-each-ref", "--format=%(refname:short)", f"refs/remotes/{remote}"]
    try:
        proc = _run(command)
    except OSError as exc:
        return None, f"git for-each-ref failed: {exc}"
    if proc.returncode != 0:
        return None, _command_failure("git for-each-ref", proc)
    prefix = f"{remote}/"
    branches = [
        ref[len(prefix):]
        for ref in (line.strip() for line in proc.stdout.splitlines())
        if ref.startswith(prefix) and ref != f"{remote}/HEAD"
    ]
    return branches, None


def _command_failure(command: str, proc: subprocess.CompletedProcess[str]) -> str:
    detail = (proc.stderr or proc.stdout or "no error output").strip().splitlines()[0]
    return f"{command} failed (exit {proc.returncode}): {detail}"


def merge_status(ref: str, base_ref: str) -> tuple[bool | None, str | None]:
    """Tri-state wrapper around ``is_merged_into`` for reporting.

    The shared primitive intentionally maps git errors to ``False`` for safe
    deletion. Reporting needs the inverse safety property, so this runner
    records ambiguity without duplicating the primitive's squash algorithm.
    """
    issue: str | None = None

    def diagnostic_run(command: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal issue
        try:
            proc = _run(command)
        except OSError as exc:
            proc = subprocess.CompletedProcess(command, 127, "", str(exc))
        operation = command[1] if len(command) > 1 else "git"
        ancestor_probe = operation == "merge-base" and "--is-ancestor" in command
        if proc.returncode != 0 and not (ancestor_probe and proc.returncode == 1):
            issue = issue or _command_failure(" ".join(command), proc)
        elif (
            proc.returncode == 0
            and not ancestor_probe
            and operation in {"merge-base", "rev-parse", "commit-tree"}
        ):
            if not proc.stdout.strip():
                issue = issue or f"{' '.join(command)} returned empty output"
        elif proc.returncode == 0 and operation == "cherry":
            lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            if any(not line.startswith(("+", "-")) for line in lines):
                issue = issue or "git cherry returned malformed output"
        return proc

    merged = is_merged_into(diagnostic_run, ref, base_ref)
    return (None, issue) if issue else (merged, None)


def ancestry_container(
    remote: str,
    name: str,
    base_ref: str,
) -> tuple[str | None, str | None]:
    """Return a remote ref that contains the branch tip, using one git query."""
    ref = f"refs/remotes/{remote}/{name}"
    command = [
        "git",
        "for-each-ref",
        f"--contains={ref}",
        "--format=%(refname:short)",
        f"refs/remotes/{remote}",
    ]
    try:
        proc = _run(command)
    except OSError as exc:
        return None, f"git for-each-ref --contains failed: {exc}"
    if proc.returncode != 0:
        return None, _command_failure("git for-each-ref --contains", proc)
    excluded = {f"{remote}/{name}", f"{remote}/HEAD", base_ref}
    container = next(
        (line.strip() for line in proc.stdout.splitlines() if line.strip() not in excluded),
        None,
    )
    return container, None


def classify_liveness(
    remote: str,
    base_ref: str,
    branches: list[str],
    *,
    pr_index: PullRequestIndex | None,
    pr_error: str | None = None,
) -> list[LivenessVerdict]:
    """Classify each non-protected remote branch into one liveness bucket."""
    verdicts: list[LivenessVerdict] = []
    subjects = [name for name in branches if not is_protected(name)]
    for name in subjects:
        if pr_index and name in pr_index.open_by_branch:
            verdicts.append(
                LivenessVerdict(
                    name,
                    "OPEN-PR",
                    "has an open PR",
                    pr_number=pr_index.open_by_branch[name],
                )
            )
            continue

        ref = f"refs/remotes/{remote}/{name}"
        merged, error = merge_status(ref, base_ref)
        if merged is None:
            verdicts.append(LivenessVerdict(name, "UNDETERMINED", error or "git ambiguity"))
            continue
        pr_number = pr_index.all_by_branch.get(name) if pr_index else None
        if merged:
            verdicts.append(
                LivenessVerdict(
                    name,
                    "MERGED",
                    "cumulative change is present on the base ref",
                    pr_number=pr_number,
                )
            )
            continue

        if pr_index is None:
            contained_by, contain_error = ancestry_container(remote, name, base_ref)
            if contained_by:
                verdicts.append(
                    LivenessVerdict(
                        name,
                        "CONTAINED",
                        "branch tip is an ancestor of another remote ref",
                        contained_by=contained_by,
                    )
                )
            elif contain_error:
                verdicts.append(LivenessVerdict(name, "UNDETERMINED", contain_error))
            else:
                detail = pr_error or "unknown gh failure"
                verdicts.append(
                    LivenessVerdict(
                        name,
                        "UNDETERMINED",
                        f"PR attribution unavailable: {detail}",
                    )
                )
            continue

        containment_errors: list[str] = []
        contained_by = None
        for absorber in branches:
            absorber_short_ref = f"{remote}/{absorber}"
            if absorber == name or absorber_short_ref == base_ref:
                continue
            contained, contain_error = merge_status(
                ref, f"refs/remotes/{remote}/{absorber}"
            )
            if contained:
                contained_by = absorber_short_ref
                break
            if contained is None:
                containment_errors.append(
                    contain_error or f"could not inspect {absorber_short_ref}"
                )
        if contained_by:
            verdicts.append(
                LivenessVerdict(
                    name,
                    "CONTAINED",
                    "cumulative change is present on another remote ref",
                    pr_number=pr_number,
                    contained_by=contained_by,
                )
            )
        elif containment_errors:
            verdicts.append(
                LivenessVerdict(name, "UNDETERMINED", containment_errors[0], pr_number=pr_number)
            )
        else:
            verdicts.append(
                LivenessVerdict(
                    name,
                    "STRANDED",
                    "not merged, contained, or covered by an open PR",
                    pr_number=pr_number,
                )
            )
    verdicts.sort(key=lambda verdict: (LIVENESS_CATEGORIES.index(verdict.category), verdict.name))
    return verdicts


def render_liveness_report(
    verdicts: list[LivenessVerdict],
    *,
    pr_error: str | None = None,
    report_errors: list[str] | None = None,
) -> str:
    counts = {category: 0 for category in LIVENESS_CATEGORIES}
    for verdict in verdicts:
        counts[verdict.category] += 1
    lines = [
        "# Branch liveness",
        (
            f"PR attribution: unavailable — {pr_error}"
            if pr_error
            else "PR attribution: available"
        ),
        " · ".join(f"{category}: {counts[category]}" for category in LIVENESS_CATEGORIES),
    ]
    if pr_error:
        lines.append("Git-derived MERGED/CONTAINED results remain authoritative; "
                     "unsafe STRANDED claims are suppressed.")
    for error in report_errors or []:
        lines.append(f"UNDETERMINED: {error}")
    lines += [
        "",
        "| Branch | Bucket | PR | Contained by | Reason |",
        "|---|---|---:|---|---|",
    ]
    for verdict in verdicts:
        pr = f"#{verdict.pr_number}" if verdict.pr_number else "—"
        contained_by = verdict.contained_by or "—"
        reason = verdict.reason.replace("|", "\\|")
        lines.append(
            f"| `{verdict.name}` | {verdict.category} | {pr} | `{contained_by}` | {reason} |"
        )
    return "\n".join(lines)


def liveness_payload(
    verdicts: list[LivenessVerdict],
    *,
    pr_error: str | None,
    report_errors: list[str],
) -> dict[str, object]:
    return {
        "pr_attribution": {"available": pr_error is None, "error": pr_error},
        "errors": report_errors,
        "branches": [asdict(verdict) for verdict in verdicts],
    }


def liveness_exit_code(
    verdicts: list[LivenessVerdict],
    *,
    exit_on_stranded: bool,
    report_errors: list[str] | None = None,
) -> int:
    if report_errors or any(verdict.category == "UNDETERMINED" for verdict in verdicts):
        return 2
    if exit_on_stranded and any(verdict.category == "STRANDED" for verdict in verdicts):
        return 1
    return 0


def classify(
    remote: str,
    base_ref: str,
    now: int,
    *,
    open_prs: set[str] | None,
) -> list[BranchVerdict]:
    verdicts: list[BranchVerdict] = []
    pr_lookup_failed = open_prs is None
    prs = open_prs or set()
    for name, ts in remote_branches(remote, now):
        age_days = max(0, (now - ts) // 86400)
        if is_protected(name):
            verdicts.append(BranchVerdict(name, "PROTECTED", age_days, "protected branch", ts))
            continue
        if is_merged(remote, name, base_ref):
            verdicts.append(
                BranchVerdict(name, "MERGED", age_days, "already merged into base ref", ts)
            )
            continue
        if name in prs:
            verdicts.append(BranchVerdict(name, "ACTIVE", age_days, "has an open PR", ts))
            continue
        if age_days < RECENT_DAYS:
            verdicts.append(
                BranchVerdict(name, "ACTIVE", age_days, f"commit younger than {RECENT_DAYS}d", ts)
            )
            continue
        if age_days < STALE_DAYS:
            verdicts.append(BranchVerdict(name, "ACTIVE", age_days, "not yet stale", ts))
            continue
        if age_days >= GRACE_DAYS and not pr_lookup_failed:
            verdicts.append(
                BranchVerdict(name, "STALE_DELETE", age_days, f"stale > {GRACE_DAYS}d, no PR", ts)
            )
        else:
            note = (
                "stale, awaiting grace"
                if not pr_lookup_failed
                else "stale (PR lookup failed; delete disabled)"
            )
            verdicts.append(BranchVerdict(name, "STALE_FLAG", age_days, note, ts))
    verdicts.sort(key=lambda v: (CATEGORIES.index(v.category), -v.age_days))
    return verdicts


def delete_branch(remote: str, name: str, *, dry_run: bool) -> str:
    cmd = ["git", "push", remote, "--delete", name]
    if dry_run:
        return "DRY-RUN: " + " ".join(cmd)
    proc = _run(cmd)
    return ("deleted " + name) if proc.returncode == 0 else f"FAILED {name}: {proc.stderr.strip()}"


def render_report(verdicts: list[BranchVerdict], *, now: int) -> str:
    counts = {c: 0 for c in CATEGORIES}
    for v in verdicts:
        counts[v.category] += 1
    stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(now))
    lines = [
        ISSUE_MARKER,
        f"## Branch janitor — {stamp}",
        "",
        f"**{len(verdicts)} branches** · "
        + " · ".join(f"{c}: {counts[c]}" for c in CATEGORIES),
        "",
        "| Branch | Category | Age (d) | Reason |",
        "|---|---|---|---|",
    ]
    shown = [v for v in verdicts if v.category != "ACTIVE"]
    for v in shown[:200]:
        lines.append(f"| `{v.name}` | {v.category} | {v.age_days} | {v.reason} |")
    if len(shown) > 200:
        lines.append(f"| … | … | … | +{len(shown) - 200} more |")
    lines += [
        "",
        f"_Guardrails: protects main/release, open-PR branches, and commits < {RECENT_DAYS}d._",
        "_This run deletes nothing unless invoked with `--apply`; the scheduled "
        "workflow runs `apply-all`._",
    ]
    return "\n".join(lines)


def upsert_issue(body: str) -> str:
    """Create or update the rolling tracking issue. Best-effort via gh."""
    find = _run(
        ["gh", "issue", "list", "--state", "open", "--search", ISSUE_TITLE,
         "--limit", "5", "--json", "number,title"]
    )
    number = None
    if find.returncode == 0:
        try:
            for row in json.loads(find.stdout or "[]"):
                if row.get("title") == ISSUE_TITLE:
                    number = row.get("number")
                    break
        except json.JSONDecodeError:
            pass
    if number is None:
        proc = _run(["gh", "issue", "create", "--title", ISSUE_TITLE, "--body", body])
        return f"created issue: {proc.stdout.strip() or proc.stderr.strip()}"
    proc = _run(["gh", "issue", "edit", str(number), "--body", body])
    return f"updated issue #{number}: {'ok' if proc.returncode == 0 else proc.stderr.strip()}"


def main(argv: list[str]) -> int:
    _force_utf8_stdio()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete MERGED + STALE_DELETE branches. Without this, report only.",
    )
    parser.add_argument(
        "--only-merged",
        action="store_true",
        help="With --apply, delete only MERGED branches (provably safe).",
    )
    parser.add_argument(
        "--issue", action="store_true", help="Write/update the rolling tracking issue via gh."
    )
    parser.add_argument(
        "--liveness",
        action="store_true",
        help="Report OPEN-PR/MERGED/CONTAINED/STRANDED branch liveness.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of the table.")
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="With --liveness, exit 1 when STRANDED is non-empty.",
    )
    parser.add_argument(
        "--fetch", action="store_true", help="git fetch --prune before classifying."
    )
    args = parser.parse_args(argv)

    if args.exit_code and not args.liveness:
        parser.error("--exit-code requires --liveness")
    if args.liveness and (args.apply or args.only_merged or args.issue):
        parser.error("--liveness cannot be combined with deletion or issue modes")

    report_errors: list[str] = []
    if args.fetch:
        fetched = _run(["git", "fetch", "--prune", args.remote])
        if args.liveness and fetched.returncode != 0:
            report_errors.append(_command_failure("git fetch --prune", fetched))

    if args.liveness:
        branches, branch_error = liveness_branches(args.remote)
        if branch_error:
            report_errors.append(branch_error)
            branches = []
        prs, pr_error = pull_request_index()
        verdicts = classify_liveness(
            args.remote,
            args.base_ref,
            branches or [],
            pr_index=prs,
            pr_error=pr_error,
        )
        if args.json:
            print(
                json.dumps(
                    liveness_payload(
                        verdicts,
                        pr_error=pr_error,
                        report_errors=report_errors,
                    ),
                    indent=2,
                )
            )
        else:
            print(
                render_liveness_report(
                    verdicts,
                    pr_error=pr_error,
                    report_errors=report_errors,
                )
            )
        return liveness_exit_code(
            verdicts,
            exit_on_stranded=args.exit_code,
            report_errors=report_errors,
        )

    now = int(time.time())
    open_prs = open_pr_branches()
    verdicts = classify(args.remote, args.base_ref, now, open_prs=open_prs)

    if args.json:
        print(json.dumps([asdict(v) for v in verdicts], indent=2))
    else:
        print(render_report(verdicts, now=now))

    if args.issue:
        print("\n" + upsert_issue(render_report(verdicts, now=now)))

    if args.apply:
        targets = [v for v in verdicts if v.category == "MERGED"]
        if not args.only_merged:
            targets += [v for v in verdicts if v.category == "STALE_DELETE"]
        print(f"\n# Applying deletions: {len(targets)} branch(es)")
        for v in targets:
            print(delete_branch(args.remote, v.name, dry_run=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
