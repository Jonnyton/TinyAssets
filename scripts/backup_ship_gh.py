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
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

GH_API = "https://api.github.com"
GH_UPLOAD_API = "https://uploads.github.com"
DEFAULT_REPO = "Jonnyton/tinyassets-backups"
DEFAULT_RETAIN = 30


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
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
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
            return json.loads(resp.read().decode())
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
) -> None:
    _api(token, "DELETE", f"{GH_API}/repos/{repo}/releases/{release_id}",
         post_fn=post_fn)
    # Also delete the tag so the repo stays clean.
    try:
        _api(token, "DELETE", f"{GH_API}/repos/{repo}/git/refs/tags/{tag}",
             post_fn=post_fn)
    except RuntimeError:
        pass  # tag deletion is best-effort


def prune_releases(
    token: str,
    repo: str,
    keep: int,
    *,
    post_fn: Any = None,
) -> int:
    releases = list_releases(token, repo, post_fn=post_fn)
    # Sort oldest-first by created_at; keep the newest `keep`.
    releases.sort(key=lambda r: r.get("created_at", ""))
    victims = releases[:-keep] if len(releases) > keep else []
    for rel in victims:
        delete_release(token, repo, rel["id"], rel.get("tag_name", ""),
                       post_fn=post_fn)
        print(f"  pruned release: {rel.get('tag_name', rel['id'])}")
    return len(victims)


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

        pruned = prune_releases(token, repo, retain, post_fn=post_fn)
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
