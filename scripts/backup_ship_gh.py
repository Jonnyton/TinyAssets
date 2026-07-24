"""backup_ship_gh.py — upload a tinyassets-data tarball to GitHub release assets.

Offsite backup for task #59: after the local rclone upload succeeds, ship
the same tarball to a private GitHub repo (Jonnyton/tinyassets-backups) as a
release asset.  No new secrets — uses GH_TOKEN (same credential already
cached for GHA workflows).

Exit codes
----------
0   Upload succeeded (or DRY_RUN=1).
1   GH_TOKEN not set.
2   tarball path not found / unreadable.
3   GitHub API error (create repo / release / asset).
4   Retention prune of old releases failed (non-fatal on success path).

Usage
-----
    python3 scripts/backup_ship_gh.py /tmp/tinyassets-data-2026-04-20T02-00-00Z.tar.gz
    GH_TOKEN=ghp_... python3 scripts/backup_ship_gh.py /path/to/backup.tar.gz
    DRY_RUN=1 python3 scripts/backup_ship_gh.py /path/to/backup.tar.gz

Environment
-----------
    GH_TOKEN              GitHub token with repo scope (required).
    BACKUP_GH_REPO        target repo (default: Jonnyton/tinyassets-backups).
    BACKUP_GH_RETAIN      number of releases to keep (default: 30).
    DRY_RUN               set to "1" to skip mutations.

Stdlib only — no third-party deps.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

GH_API = "https://api.github.com"
GH_UPLOAD_API = "https://uploads.github.com"
DEFAULT_REPO = "Jonnyton/tinyassets-backups"
DEFAULT_RETAIN = 30
PRUNE_RECONCILE_ATTEMPTS = 6
PRUNE_RECONCILE_DELAY_SECONDS = 2


class GitHubAPIError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _token() -> str:
    t = os.environ.get("GH_TOKEN", "").strip()
    if not t:
        print("ERROR: GH_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    return t


def _headers(token: str, accept: str = "application/vnd.github+json") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "tinyassets-backup-ship/1.0",
    }


def _api(
    token: str,
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    *,
    post_fn: Any = None,
) -> dict[str, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            **_headers(token),
            **({"Content-Type": "application/json"} if data else {}),
        },
    )
    if post_fn:
        return post_fn(req)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            # Some endpoints (DELETE release → 204) return an empty body —
            # json.loads("") raised here and failed every nightly ship once
            # the repo crossed BACKUP_GH_RETAIN releases (live-hit
            # 2026-07-15 on the first post-rename ship: the renamed repo
            # carried 30+ pre-rename releases).
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise GitHubAPIError(
            exc.code,
            f"GitHub API {method} {url} → {exc.code}: {body_text}"
        ) from exc


def _upload_asset(
    token: str,
    upload_url: str,
    name: str,
    path: Path,
    *,
    post_fn: Any = None,
) -> dict[str, Any]:
    # upload_url from GH API is a URI template: strip {?name,label} suffix.
    base = upload_url.split("{")[0]
    url = f"{base}?name={urllib.request.quote(name)}"
    data = path.read_bytes()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            **_headers(token),
            "Content-Type": "application/gzip",
            "Content-Length": str(len(data)),
        },
    )
    if post_fn:
        return post_fn(req)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            # Asset uploads return 201 with a JSON body; the empty-body
            # tolerance here is defensive only (the load-bearing case is
            # _api's DELETE-release 204 — see comment there).
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHub asset upload {url} → {exc.code}: {body_text}"
        ) from exc


def ensure_repo(token: str, repo: str, *, post_fn: Any = None) -> None:
    owner, name = repo.split("/", 1)
    url = f"{GH_API}/repos/{owner}/{name}"
    try:
        _api(token, "GET", url, post_fn=post_fn)
        return
    except RuntimeError as exc:
        if "404" not in str(exc):
            raise
    # Repo missing — create it private.
    create_url = f"{GH_API}/user/repos"
    _api(
        token,
        "POST",
        create_url,
        {"name": name, "private": True, "auto_init": True,
         "description": "TinyAssets daemon offsite backup archives"},
        post_fn=post_fn,
    )
    print(f"created private repo {repo}")


def create_release(
    token: str,
    repo: str,
    tag: str,
    *,
    post_fn: Any = None,
) -> dict[str, Any]:
    url = f"{GH_API}/repos/{repo}/releases"
    return _api(
        token,
        "POST",
        url,
        {
            "tag_name": tag,
            "name": f"backup {tag}",
            "body": "Automated tinyassets-data backup archive.",
            "draft": False,
            "prerelease": False,
        },
        post_fn=post_fn,
    )


def list_releases(
    token: str,
    repo: str,
    *,
    post_fn: Any = None,
) -> list[dict[str, Any]]:
    url = f"{GH_API}/repos/{repo}/releases?per_page=100"
    return _api(token, "GET", url, post_fn=post_fn)  # type: ignore[return-value]


def delete_release(
    token: str,
    repo: str,
    release_id: int,
    tag: str,
    *,
    post_fn: Any = None,
) -> bool:
    try:
        _api(token, "DELETE", f"{GH_API}/repos/{repo}/releases/{release_id}",
             post_fn=post_fn)
    except GitHubAPIError as exc:
        if exc.status == 404:
            return False
        raise
    # Also delete the tag so the repo stays clean.
    try:
        _api(token, "DELETE", f"{GH_API}/repos/{repo}/git/refs/tags/{tag}",
             post_fn=post_fn)
    except RuntimeError:
        pass  # tag deletion is best-effort
    return True


# Only releases carrying these tag prefixes are subject to retention
# pruning. Anything else in the repo (e.g. the one-off
# workflow-data-content-archive-* from the 2026-07-15 volume audit) is a
# permanent artifact — before this scoping, prune deleted the OLDEST
# releases regardless of name, so a parked archive would have been
# silently destroyed within days of landing.
PRUNABLE_TAG_PREFIXES: tuple[str, ...] = (
    "tinyassets-brain-", "tinyassets-data-",
    "workflow-brain-", "workflow-data-2",
)


def _release_age_key(rel: dict[str, Any]) -> str:
    """Age key for retention ordering. GitHub sets a release's
    ``created_at`` to the TARGET COMMIT's date, not the release time —
    the live backup repo has 31 releases sharing one ``created_at``, so
    it cannot order backups (Codex review 2026-07-15, live-reproduced:
    the old sort deleted whichever release the list order put first).
    Order by ``published_at``, falling back to the timestamp embedded in
    the tag (normalized to ISO so both sources compare), then
    ``created_at`` as a last resort.
    """
    published = str(rel.get("published_at") or "")
    if published:
        return published
    m = re.search(
        r"(\d{4}-\d{2}-\d{2})T(\d{2})[-:](\d{2})[-:](\d{2})",
        str(rel.get("tag_name", "")),
    )
    if m:
        return f"{m.group(1)}T{m.group(2)}:{m.group(3)}:{m.group(4)}Z"
    return str(rel.get("created_at") or "")


def prune_releases(
    token: str,
    repo: str,
    keep: int,
    *,
    include_release: dict[str, Any] | None = None,
    post_fn: Any = None,
    sleep_fn: Any = time.sleep,
) -> int:
    pruned = 0
    for attempt in range(PRUNE_RECONCILE_ATTEMPTS):
        listed = list_releases(token, repo, post_fn=post_fn)
        if include_release is not None:
            listed_ids = {release.get("id") for release in listed}
            if include_release.get("id") not in listed_ids:
                if attempt + 1 == PRUNE_RECONCILE_ATTEMPTS:
                    raise RuntimeError(
                        "GitHub release list did not converge on the "
                        "just-created backup release"
                    )
                sleep_fn(PRUNE_RECONCILE_DELAY_SECONDS)
                continue
        releases = [
            release for release in listed
            if str(release.get("tag_name", "")).startswith(
                PRUNABLE_TAG_PREFIXES
            )
        ]
        releases.sort(key=_release_age_key)
        victims = releases[:-keep] if len(releases) > keep else []
        stale_victim = False
        for release in victims:
            deleted = delete_release(
                token,
                repo,
                release["id"],
                release.get("tag_name", ""),
                post_fn=post_fn,
            )
            if deleted is False:
                stale_victim = True
                break
            pruned += 1
            print(
                f"  pruned release: "
                f"{release.get('tag_name', release['id'])}"
            )
        if not stale_victim:
            return pruned
        if attempt + 1 < PRUNE_RECONCILE_ATTEMPTS:
            sleep_fn(PRUNE_RECONCILE_DELAY_SECONDS)
    raise RuntimeError("GitHub release retention view did not converge")


def ship(
    tarball: Path,
    *,
    repo: str = DEFAULT_REPO,
    retain: int = DEFAULT_RETAIN,
    dry_run: bool = False,
    post_fn: Any = None,
) -> None:
    token = _token()

    if not tarball.is_file():
        print(f"ERROR: tarball not found: {tarball}", file=sys.stderr)
        sys.exit(2)

    size = tarball.stat().st_size
    # Derive a tag from the filename stem (strip .tar.gz).
    stem = tarball.name
    for suffix in (".tar.gz", ".tgz"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    tag = stem  # e.g. "tinyassets-data-2026-04-20T02-00-00Z"

    print(f"[backup-ship] tarball: {tarball} ({size} bytes)")
    print(f"[backup-ship] target:  {repo} release {tag!r}")

    if dry_run:
        print("[backup-ship] DRY_RUN=1 — no mutations")
        return

    try:
        ensure_repo(token, repo, post_fn=post_fn)
        release = create_release(token, repo, tag, post_fn=post_fn)
        upload_url = release["upload_url"]
        asset = _upload_asset(token, upload_url, tarball.name, tarball,
                              post_fn=post_fn)
        print(f"[backup-ship] uploaded: {asset.get('browser_download_url', asset.get('name'))}")

        release_for_retention = {**release, "tag_name": tag}
        pruned = prune_releases(
            token,
            repo,
            retain,
            include_release=release_for_retention,
            post_fn=post_fn,
        )
        if pruned:
            print(f"[backup-ship] pruned {pruned} old release(s) (keep={retain})")
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(3)

    print("[backup-ship] done.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ship a workflow backup tarball to GitHub release assets."
    )
    parser.add_argument("tarball", help="Path to the .tar.gz archive to upload")
    parser.add_argument(
        "--repo",
        default=os.environ.get("BACKUP_GH_REPO", DEFAULT_REPO),
        help=f"GitHub repo (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--retain",
        type=int,
        default=int(os.environ.get("BACKUP_GH_RETAIN", DEFAULT_RETAIN)),
        help=f"Releases to keep (default: {DEFAULT_RETAIN})",
    )
    args = parser.parse_args()

    dry_run = os.environ.get("DRY_RUN", "0").strip() == "1"
    ship(Path(args.tarball), repo=args.repo, retain=args.retain, dry_run=dry_run)


if __name__ == "__main__":
    main()
