#!/usr/bin/env python3
"""Answer "is this commit actually in production?" — Hard Rule 14's gate.

*Merged is not deployed.* Merges performed by the Actions app via
``GITHUB_TOKEN`` raise no ``push`` event, so ``build-image`` / ``deploy-prod``
never fire. Five PRs landed on 2026-07-21 and none reached production. No
commit touched the broken surface, so only an out-of-band probe can catch this
class — the same shape as the 2026-04-19 tunnel outage.

This reads the sha production is *serving* from the live public ``/mcp/pulse``
receipt (``git_sha``, written to the host volume by
``deploy-prod.yml`` at deploy time) and compares it to git.

    # what is production serving, and how far behind origin/main is it?
    python scripts/deployed_sha.py

    # the gate: fail unless production contains this commit
    python scripts/deployed_sha.py --assert-contains HEAD
    python scripts/deployed_sha.py --assert-contains 8cbf9769

    python scripts/deployed_sha.py --json

**Known limit — it proves the RECEIPT, not the running binary.**
``release_state`` is a JSON file the deploy job writes to the host volume;
``tinyassets/api/status.py`` reads it back without comparing it to the revision
actually running. A manual rollback or an older-image restart that leaves the
receipt intact would make an older server report a newer sha, and
``--assert-contains`` would return 0 for code that is not running. Codex found
this reviewing the 2026-08-25 harness reset; closing it needs the public surface
to expose a runtime-derived revision, which is a product change, not a harness
one. Tracked at ``docs/concerns/2026-08-26-deployed-sha-proves-receipt-only.md``.

What this DOES check, so the gap is as small as it can be here: ``git_sha`` and
``image_tag`` must agree, and a receipt missing either is exit 2 rather than a
pass. That catches a partial or tampered receipt; it cannot catch a coherent
receipt describing a build that is no longer running.

**This is a post-deploy check, never a merge-required one.** A PR-required
check cannot demand that production already contain an unmerged head; wiring it
that way is circular and can never pass. Codex flagged exactly that in the
2026-08-25 harness-reset review. Run it *after* a deploy, or before claiming a
fix is shipped.

Exit codes: 0 pass, 1 assertion failed (commit not in production), 2 could not
determine (network, missing field, unknown sha). 2 is deliberately distinct
from 1 — "I could not tell" must never read as "yes, it shipped."
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_URL = "https://tinyassets.io/mcp"
#: Cloudflare answers the stdlib's default ``Python-urllib/3.x`` agent with a
#: managed-challenge 403 (measured against the live surface 2026-09-02), which
#: this gate would report as "cannot determine" forever. Every other probe in
#: scripts/ already names itself for the same reason.
PULSE_USER_AGENT = "tinyassets-deploy-gate/1.0"
DEFAULT_TIMEOUT = 30.0


class DeployedShaError(Exception):
    """Could not determine what production is serving."""


# Mirrors the `paths:` filter in .github/workflows/build-image.yml. A commit
# touching none of these cannot produce an image, so it cannot be "undeployed"
# in any actionable sense. Keep the two lists in step -- a test asserts it.
BUILD_PATHS = (
    "Dockerfile",
    ".dockerignore",
    "pyproject.toml",
    "PLAN.md",
    "tinyassets/",
    "domains/",
    "fantasy_daemon/",
    "data/world_rules.lp",
    "scripts/mcp_public_canary.py",
    "deploy/",
)


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        raise DeployedShaError(f"git {' '.join(args)}: {(proc.stderr or '').strip()}")
    return proc.stdout.strip()


def live_release_state(url: str, timeout: float) -> dict[str, Any]:
    """Read the unauthenticated release receipt from ``/mcp/pulse``."""
    pulse_url = f"{url.rstrip('/')}/pulse"
    request = urllib.request.Request(
        pulse_url,
        method="GET",
        headers={"Accept": "application/json", "User-Agent": PULSE_USER_AGENT},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise DeployedShaError(
                    f"non-200 status {response.status} from {pulse_url}"
                )
            body = response.read()
    except urllib.error.HTTPError as exc:
        raise DeployedShaError(
            f"non-200 status {exc.code} from {pulse_url}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DeployedShaError(f"probe failed against {pulse_url}: {exc}") from exc

    try:
        result = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeployedShaError(f"non-JSON response from {pulse_url}") from exc
    if not isinstance(result, dict):
        raise DeployedShaError(
            f"pulse response is not an object: {type(result).__name__}"
        )

    return result


def report(url: str, timeout: float) -> dict[str, Any]:
    release_state = live_release_state(url, timeout)
    deployed = (release_state.get("git_sha") or "").strip()
    if not deployed:
        raise DeployedShaError("release_state.git_sha is empty — cannot tell what is deployed")

    # Cross-check the two independent fields the receipt carries. They are
    # written together, so agreement does not prove the running binary -- but
    # DISagreement proves the receipt is untrustworthy, and an untrustworthy
    # receipt must be exit 2, never a pass.
    # Cross-check the receipt against itself. Written together, so agreement
    # does not prove the running binary -- but DISagreement proves the receipt
    # is untrustworthy, and an untrustworthy receipt must be exit 2, never a
    # pass. Hardened after a cross-family review found four holes: a missing
    # tag passed while the docstring claimed it would not; a one-character tag
    # sharing the sha's first character passed; valid OCI forms like
    # `release-<sha>` and uppercase hex were rejected; and a non-string tag
    # raised an uncaught AttributeError.
    raw_tag = release_state.get("image_tag")
    if raw_tag is not None and not isinstance(raw_tag, str):
        raise DeployedShaError(
            f"release_state.image_tag is {type(raw_tag).__name__}, not a string - "
            "refusing to interpret a malformed receipt"
        )
    image_tag = (raw_tag or "").strip()
    if not image_tag:
        raise DeployedShaError(
            "release_state carries git_sha but no image_tag - cannot corroborate "
            "the receipt, so the deploy state is unknown"
        )

    # Take the tag's reference part and pull the longest hex run out of it, so
    # `release-<sha>`, `v<sha>`, and bare `<sha>` all work. Case-insensitive.
    reference = image_tag.rsplit(":", 1)[-1].strip()
    hex_runs = re.findall(r"[0-9a-fA-F]{7,40}", reference)
    if not hex_runs:
        raise DeployedShaError(
            f"release_state.image_tag {image_tag!r} carries no sha-shaped reference - "
            "cannot corroborate git_sha"
        )
    tag_sha = max(hex_runs, key=len).lower()
    if not deployed.lower().startswith(tag_sha):
        raise DeployedShaError(
            f"release_state is inconsistent: git_sha {deployed[:12]} does not match "
            f"image_tag {image_tag!r} - refusing to report a deploy state from a "
            "receipt that disagrees with itself"
        )

    info: dict[str, Any] = {
        "deployed_sha": deployed,
        "url": url,
        "image_tag": image_tag or None,
        "image_digest": (release_state.get("image_digest") or "").strip() or None,
        "deployed_at": (release_state.get("deployed_at") or "").strip() or None,
        "proves": "receipt",  # not the running binary; see module docstring
    }
    try:
        _git("cat-file", "-e", f"{deployed}^{{commit}}")
        info["known_to_git"] = True
        info["deployed_subject"] = _git("log", "-1", "--format=%s", deployed)
        try:
            behind = _git("rev-list", "--count", f"{deployed}..origin/main")
            info["commits_on_main_not_deployed"] = int(behind)
            # A docs or CI commit CANNOT reach production: `build-image.yml`
            # is path-filtered, so nothing is built and nothing is deployed.
            # Counting those as drift makes the tool cry wolf permanently --
            # on 2026-08-27 it reported 9 undeployed commits, all of which
            # touched zero build paths. Split the count so a real gap is
            # distinguishable from "nothing to deploy".
            undeployed = _git(
                "rev-list", f"{deployed}..origin/main", "--", *BUILD_PATHS
            ).split()
            info["build_affecting_not_deployed"] = len(undeployed)
        except DeployedShaError:
            info["commits_on_main_not_deployed"] = None
            info["build_affecting_not_deployed"] = None
    except DeployedShaError:
        # Not an error by itself: a shallow clone or a build from another
        # remote can serve a commit this checkout has never fetched.
        info["known_to_git"] = False
    return info


def contains(deployed: str, commit: str) -> bool:
    """True when ``commit`` is an ancestor of (or equal to) what is deployed."""
    resolved = _git("rev-parse", f"{commit}^{{commit}}")
    if _git("rev-parse", f"{deployed}^{{commit}}") == resolved:
        return True
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", resolved, deployed],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--url", default=DEFAULT_URL,
        help=f"public MCP surface (default {DEFAULT_URL})",
    )
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    ap.add_argument(
        "--assert-contains",
        metavar="COMMIT",
        help="exit 1 unless production is serving a build containing COMMIT",
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    try:
        info = report(args.url, args.timeout)
    except DeployedShaError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"cannot determine deployed sha: {exc}", file=sys.stderr)
        return 2

    if args.assert_contains:
        if not info["known_to_git"]:
            msg = (
                f"production serves {info['deployed_sha'][:12]}, which this checkout does not "
                "have - fetch it, then re-run"
            )
            if args.json:
                print(json.dumps({"ok": False, "error": msg, **info}, indent=2))
            else:
                print(f"UNKNOWN: {msg}", file=sys.stderr)
            return 2
        try:
            ok = contains(info["deployed_sha"], args.assert_contains)
        except DeployedShaError as exc:
            print(f"cannot compare: {exc}", file=sys.stderr)
            return 2
        info["asserted"] = args.assert_contains
        info["contains"] = ok
        if args.json:
            print(json.dumps({"ok": ok, **info}, indent=2))
        elif ok:
            print(
                f"SHIPPED (per receipt): production reports {info['deployed_sha'][:12]}, "
                f"which contains {args.assert_contains}"
            )
        else:
            # Say WHICH kind of "not shipped" this is. A commit touching no
            # build path can never appear in production's sha, because
            # build-image.yml is path-filtered -- so "check the push event" is
            # the wrong advice and reads as a missed deploy. Measured
            # 2026-08-27: four merged PRs, zero build paths between them, and
            # this gate reported a deploy gap that did not exist.
            touches_build = None
            try:
                touches_build = bool(
                    _git(
                        "rev-list", "-1",
                        f"{info['deployed_sha']}..{args.assert_contains}",
                        "--", *BUILD_PATHS,
                    ).strip()
                )
            except DeployedShaError:
                pass
            info["asserted_touches_build_path"] = touches_build
            if touches_build is False:
                detail = (
                    "This commit touches NO build path, so no image was built "
                    "and none will be: build-image.yml is path-filtered. Nothing "
                    "is waiting to deploy -- the running image is correct. "
                    "Assert a commit that changes product code instead."
                )
            else:
                detail = (
                    "Merged is not deployed - check that the merge raised a push "
                    "event (docs/decisions/"
                    "ADR-004-merge-attribution-and-the-deploy-gap.md)."
                )
            print(
                f"NOT SHIPPED: production serves {info['deployed_sha'][:12]} "
                f"({info.get('deployed_subject', '')!r}), which does NOT "
                f"contain {args.assert_contains}.\n" + detail,
                file=sys.stderr,
            )
        return 0 if ok else 1

    if args.json:
        print(json.dumps({"ok": True, **info}, indent=2))
    else:
        print(f"production serves {info['deployed_sha']}")
        if info.get("deployed_subject"):
            print(f"  {info['deployed_subject']}")
        behind = info.get("commits_on_main_not_deployed")
        build_gap = info.get("build_affecting_not_deployed")
        if behind and build_gap:
            print(
                f"  {build_gap} of {behind} undeployed commit(s) touch build "
                f"paths -- production IS behind"
            )
        elif behind:
            print(
                f"  {behind} commit(s) on origin/main are not in production, but "
                f"NONE touch a build path -- nothing to deploy"
            )
        elif behind == 0:
            print("  up to date with origin/main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
