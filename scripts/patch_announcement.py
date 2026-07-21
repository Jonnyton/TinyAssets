"""Compose GitHub-credit and social announcement text for landed patches.

GitHub attribution is primary: Workflow actors resolve through CONTRIBUTORS.md
to `Co-Authored-By:` trailers, and social posts consume the same contributor
set after the patch lands.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

COAUTHOR_RE = re.compile(r"^Co-authored-by:\s*(?P<name>.*?)\s*<(?P<email>[^<>]+)>\s*$", re.I)
NOREPLY_RE = re.compile(r"^(?P<handle>[^@<>]+)@users\.noreply\.github\.com$", re.I)
PATCH_MARKER_RE = re.compile(
    r"^(Patch-Id|Patch-Loop|Patch-Contributors|Source-Bug|Workflow-Patch):\s*.+$",
    re.I | re.M,
)
PATCH_CONTRIBUTORS_RE = re.compile(r"^Patch-Contributors:\s*(?P<actors>.+)$", re.I | re.M)


@dataclass(frozen=True)
class Contributor:
    actor_id: str
    github_handle: str
    display_name: str
    x_handle: str = ""
    social_opt_in: bool = False

    @property
    def github_email(self) -> str:
        return f"{self.github_handle}@users.noreply.github.com"

    @property
    def trailer(self) -> str:
        return f"Co-Authored-By: {self.display_name} <{self.github_email}>"

    @property
    def x_mention(self) -> str:
        if not self.social_opt_in or not self.x_handle:
            return ""
        return "@" + self.x_handle.lstrip("@")


@dataclass(frozen=True)
class CommitCredit:
    display_name: str
    email: str
    github_handle: str = ""

    @property
    def key(self) -> str:
        return self.email.lower()


def _norm_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _split_markdown_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on", "opt-in", "opt in"}


def load_contributors(path: Path) -> dict[str, Contributor]:
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        cells = _split_markdown_row(line)
        headers = [_norm_header(cell) for cell in cells]
        if "actor_id" not in headers or "github_handle" not in headers:
            continue
        if index + 1 >= len(lines) or "---" not in lines[index + 1]:
            continue
        contributors: dict[str, Contributor] = {}
        for row in lines[index + 2:]:
            if not row.strip().startswith("|"):
                break
            values = _split_markdown_row(row)
            if len(values) < len(headers):
                values += [""] * (len(headers) - len(values))
            record = dict(zip(headers, values, strict=False))
            actor_id = record.get("actor_id", "").strip()
            github_handle = record.get("github_handle", "").strip().lstrip("@")
            display_name = record.get("display_name", "").strip() or github_handle
            if not actor_id or not github_handle:
                continue
            contributors[actor_id] = Contributor(
                actor_id=actor_id,
                github_handle=github_handle,
                display_name=display_name,
                x_handle=(record.get("x_handle", "") or "").strip().lstrip("@"),
                social_opt_in=parse_bool(record.get("social_opt_in", "")),
            )
        return contributors
    raise ValueError(f"No contributor table found in {path}")


def actor_ids_from_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def actor_ids_from_json(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [str(item).strip() for item in data if str(item).strip()]
    if not isinstance(data, dict):
        raise ValueError("attribution JSON must be an object or list")
    raw = data.get("actor_ids") or data.get("actors") or data.get("contributors") or []
    if isinstance(raw, str):
        return actor_ids_from_csv(raw)
    if not isinstance(raw, list):
        raise ValueError("attribution JSON actor list must be a list or comma-separated string")
    actor_ids: list[str] = []
    for item in raw:
        if isinstance(item, str):
            actor_ids.append(item.strip())
        elif isinstance(item, dict):
            actor_ids.append(str(item.get("actor_id") or item.get("actor") or "").strip())
    return [actor_id for actor_id in actor_ids if actor_id]


def actor_ids_from_commit_message(message: str) -> list[str]:
    actor_ids: list[str] = []
    for match in PATCH_CONTRIBUTORS_RE.finditer(message):
        actor_ids.extend(actor_ids_from_csv(match.group("actors")))
    return actor_ids


def resolve_actors(
    actor_ids: Iterable[str],
    contributors: dict[str, Contributor],
) -> tuple[list[Contributor], list[str]]:
    resolved: list[Contributor] = []
    missing: list[str] = []
    seen: set[str] = set()
    for actor_id in actor_ids:
        if actor_id in seen:
            continue
        seen.add(actor_id)
        contributor = contributors.get(actor_id)
        if contributor is None:
            missing.append(actor_id)
            continue
        resolved.append(contributor)
    return resolved, missing


def run_git(repo: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def resolve_commit(repo: Path, commit: str) -> str:
    return run_git(repo, ["rev-parse", commit])


def commit_subject(repo: Path, commit: str) -> str:
    return run_git(repo, ["show", "-s", "--format=%s", commit])


def commit_body(repo: Path, commit: str) -> str:
    return run_git(repo, ["show", "-s", "--format=%B", commit])


def commit_author_credit(repo: Path, commit: str) -> CommitCredit:
    raw = run_git(repo, ["show", "-s", "--format=%an%n%ae", commit]).splitlines()
    name = raw[0] if raw else ""
    email = raw[1] if len(raw) > 1 else ""
    return CommitCredit(name, email, github_handle_from_email(email))


def github_handle_from_email(email: str) -> str:
    match = NOREPLY_RE.match(email.strip())
    return match.group("handle") if match else ""


def coauthors_from_message(message: str) -> list[CommitCredit]:
    credits: list[CommitCredit] = []
    seen: set[str] = set()
    for line in message.splitlines():
        match = COAUTHOR_RE.match(line.strip())
        if not match:
            continue
        email = match.group("email").strip()
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        credits.append(CommitCredit(
            display_name=match.group("name").strip(),
            email=email,
            github_handle=github_handle_from_email(email),
        ))
    return credits


def landed_credits(repo: Path, commit: str) -> list[CommitCredit]:
    credits = [commit_author_credit(repo, commit)]
    credits.extend(coauthors_from_message(commit_body(repo, commit)))
    unique: dict[str, CommitCredit] = {}
    for credit in credits:
        if credit.email:
            unique[credit.key] = credit
    return list(unique.values())


def missing_github_credit(
    contributors: Iterable[Contributor],
    credits: Iterable[CommitCredit],
) -> list[Contributor]:
    credited_emails = {credit.email.lower() for credit in credits}
    return [
        contributor
        for contributor in contributors
        if contributor.github_email.lower() not in credited_emails
    ]


def credited_contributors(
    contributors: Iterable[Contributor],
    credits: Iterable[CommitCredit],
) -> list[Contributor]:
    credited_emails = {credit.email.lower() for credit in credits}
    return [
        contributor
        for contributor in contributors
        if contributor.github_email.lower() in credited_emails
    ]


def _dedupe_names(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = value.strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def shorten(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


def is_patch_announcement_eligible(
    *,
    commit_message: str,
    actor_ids: Iterable[str],
    patch_title: str = "",
    source_url: str = "",
) -> bool:
    """Return true when a commit is intentionally marked for public announcement."""
    return bool(
        PATCH_MARKER_RE.search(commit_message)
        or list(actor_ids)
        or patch_title.strip()
        or source_url.strip()
    )


def compose_post_text(
    *,
    title: str,
    commit: str,
    repo_url: str,
    credits: Iterable[CommitCredit],
    contributors: Iterable[Contributor],
    source_url: str = "",
    max_chars: int = 280,
) -> str:
    title = shorten(title.strip().replace("\n", " "), 88)
    sha = commit[:7]
    x_mentions = _dedupe_names(
        contributor.x_mention for contributor in contributors if contributor.x_mention
    )
    github_names = _dedupe_names(
        credit.github_handle or credit.display_name
        for credit in credits
        if credit.github_handle or credit.display_name
    )

    lines = [f"Patch landed: {title}"]
    if x_mentions:
        lines.append("Contributors: " + ", ".join(x_mentions))
    elif github_names:
        lines.append("GitHub credit: " + ", ".join(github_names[:4]))
    lines.append(f"Verified on main: {sha}")
    lines.append(source_url or f"{repo_url.rstrip('/')}/commit/{commit}")

    text = "\n".join(lines)
    if len(text) <= max_chars:
        return text

    if github_names and not x_mentions:
        lines[1] = "GitHub credit: " + ", ".join(github_names[:2])
        text = "\n".join(lines)
    if len(text) <= max_chars:
        return text

    lines[0] = "Patch landed: " + shorten(title, 52)
    text = "\n".join(lines)
    return shorten(text, max_chars)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def command_trailers(args: argparse.Namespace) -> int:
    contributors = load_contributors(args.contributors)
    actor_ids = actor_ids_from_csv(args.actors)
    if args.attribution_json:
        actor_ids.extend(actor_ids_from_json(args.attribution_json))
    resolved, missing = resolve_actors(actor_ids, contributors)
    for contributor in resolved:
        print(contributor.trailer)
    if missing and args.json:
        print(json.dumps({"missing_actor_ids": missing}, sort_keys=True), file=sys.stderr)
    return 0


def command_guard(args: argparse.Namespace) -> int:
    contributors = load_contributors(args.contributors)
    actor_ids = actor_ids_from_csv(args.actors)
    if args.attribution_json:
        actor_ids.extend(actor_ids_from_json(args.attribution_json))
    commit = resolve_commit(args.repo, args.commit)
    resolved, missing = resolve_actors(actor_ids, contributors)
    missing_credit = missing_github_credit(resolved, landed_credits(args.repo, commit))
    payload = {
        "commit": commit,
        "resolved": [asdict(contributor) for contributor in resolved],
        "missing_actor_ids": missing,
        "missing_github_credit": [asdict(contributor) for contributor in missing_credit],
        "ok": not missing_credit,
    }
    if args.output:
        write_json(args.output, payload)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    if args.strict and missing_credit:
        return 2
    return 0


def command_compose(args: argparse.Namespace) -> int:
    contributors = load_contributors(args.contributors)
    actor_ids = actor_ids_from_csv(args.actors)
    if args.attribution_json:
        actor_ids.extend(actor_ids_from_json(args.attribution_json))
    commit = resolve_commit(args.repo, args.commit)
    message = commit_body(args.repo, commit)
    actor_ids.extend(actor_ids_from_commit_message(message))
    eligible = is_patch_announcement_eligible(
        commit_message=message,
        actor_ids=actor_ids,
        patch_title=args.patch_title,
        source_url=args.source_url,
    )
    resolved, missing = resolve_actors(actor_ids, contributors)
    credits = landed_credits(args.repo, commit)
    missing_credit = missing_github_credit(resolved, credits)
    credited = credited_contributors(resolved, credits)
    title = args.patch_title or commit_subject(args.repo, commit)
    text = ""
    skip_reason = ""
    if args.require_patch_marker and not eligible:
        skip_reason = "commit has no patch announcement marker"
    elif args.require_github_credit and missing_credit:
        skip_reason = "requested contributor is missing landed GitHub credit"
    else:
        text = compose_post_text(
            title=title,
            commit=commit,
            repo_url=args.repo_url,
            credits=credits,
            contributors=credited,
            source_url=args.source_url,
            max_chars=args.max_chars,
        )
    payload = {
        "commit": commit,
        "post_text": text,
        "dry_run_default": True,
        "eligible": eligible,
        "skip_reason": skip_reason,
        "github_credits": [asdict(credit) for credit in credits],
        "resolved_contributors": [asdict(contributor) for contributor in resolved],
        "missing_actor_ids": missing,
        "missing_github_credit": [asdict(contributor) for contributor in missing_credit],
    }
    if args.output:
        write_json(args.output, payload)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contributors", type=Path, default=Path("CONTRIBUTORS.md"))
    sub = parser.add_subparsers(dest="command", required=True)

    trailers = sub.add_parser("trailers", help="Print Co-Authored-By trailers for actor ids")
    trailers.add_argument("--actors", default="")
    trailers.add_argument("--attribution-json", type=Path)
    trailers.add_argument("--json", action="store_true")
    trailers.set_defaults(func=command_trailers)

    guard = sub.add_parser("guard", help="Check that resolved actors have GitHub commit credit")
    guard.add_argument("--repo", type=Path, default=Path("."))
    guard.add_argument("--commit", required=True)
    guard.add_argument("--actors", default="")
    guard.add_argument("--attribution-json", type=Path)
    guard.add_argument("--output", type=Path)
    guard.add_argument("--strict", action="store_true")
    guard.set_defaults(func=command_guard)

    compose = sub.add_parser("compose", help="Build social announcement JSON for a landed patch")
    compose.add_argument("--repo", type=Path, default=Path("."))
    compose.add_argument("--commit", required=True)
    compose.add_argument("--actors", default="")
    compose.add_argument("--attribution-json", type=Path)
    compose.add_argument("--patch-title", default="")
    compose.add_argument("--repo-url", default="https://github.com/Jonnyton/Workflow")
    compose.add_argument("--source-url", default="")
    compose.add_argument("--max-chars", type=int, default=280)
    compose.add_argument("--output", type=Path)
    compose.add_argument("--require-patch-marker", action="store_true")
    compose.add_argument("--require-github-credit", action="store_true")
    compose.set_defaults(func=command_compose)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"patch_announcement: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
