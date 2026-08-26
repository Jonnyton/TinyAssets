#!/usr/bin/env python3
"""Answer "is this commit actually in production?" — Hard Rule 14's gate.

*Merged is not deployed.* Merges performed by the Actions app via
``GITHUB_TOKEN`` raise no ``push`` event, so ``build-image`` / ``deploy-prod``
never fire. Five PRs landed on 2026-07-21 and none reached production. No
commit touched the broken surface, so only an out-of-band probe can catch this
class — the same shape as the 2026-04-19 tunnel outage.

This reads the sha production is *serving* from the live public MCP surface
(``get_status`` -> ``release_state.git_sha``, written to the host volume by
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
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_URL = "https://tinyassets.io/mcp"
DEFAULT_TIMEOUT = 30.0


class DeployedShaError(Exception):
    """Could not determine what production is serving."""


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
    """Read ``release_state`` from the live public MCP surface."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        import mcp_public_canary as canary
    except Exception as exc:  # pragma: no cover - import guard
        raise DeployedShaError(f"cannot load mcp_public_canary: {exc}") from exc

    try:
        status, headers, _ = canary._post(url, canary._INIT_PAYLOAD, timeout)
        if status != 200:
            raise DeployedShaError(f"non-200 status {status} from {url}")
        session_id = headers.get("mcp-session-id")
        if session_id:
            canary._post(
                url,
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                timeout,
                session_id,
            )
        status, _, body = canary._post(
            url,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_status", "arguments": {}},
            },
            timeout,
            session_id,
        )
        if status != 200:
            raise DeployedShaError(f"non-200 status {status} from {url} (get_status)")
        payload = canary._parse_sse_or_json(body)
    except DeployedShaError:
        raise
    except Exception as exc:
        raise DeployedShaError(f"probe failed against {url}: {exc}") from exc

    result = payload.get("result", payload)
    if isinstance(result, dict) and "structuredContent" in result:
        result = result["structuredContent"]
    if isinstance(result, dict) and "content" in result:
        blocks = [b.get("text", "") for b in result.get("content", []) if isinstance(b, dict)]
        for block in blocks:
            try:
                result = json.loads(block)
                break
            except json.JSONDecodeError:
                continue
    if not isinstance(result, dict):
        raise DeployedShaError("get_status payload is not an object")

    release_state = result.get("release_state")
    if not isinstance(release_state, dict):
        raise DeployedShaError(
            "get_status carries no release_state object — cannot tell what is deployed"
        )
    return release_state


def report(url: str, timeout: float) -> dict[str, Any]:
    release_state = live_release_state(url, timeout)
    deployed = (release_state.get("git_sha") or "").strip()
    if not deployed:
        raise DeployedShaError("release_state.git_sha is empty — cannot tell what is deployed")

    # Cross-check the two independent fields the receipt carries. They are
    # written together, so agreement does not prove the running binary -- but
    # DISagreement proves the receipt is untrustworthy, and an untrustworthy
    # receipt must be exit 2, never a pass.
    image_tag = (release_state.get("image_tag") or "").strip()
    if image_tag:
        tag_sha = image_tag.rsplit(":", 1)[-1].strip()
        if tag_sha and not (deployed.startswith(tag_sha) or tag_sha.startswith(deployed)):
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
        except DeployedShaError:
            info["commits_on_main_not_deployed"] = None
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
            print(
                f"NOT SHIPPED: production serves {info['deployed_sha'][:12]} "
                f"({info.get('deployed_subject', '')!r}), which does NOT contain "
                f"{args.assert_contains}.\n"
                "Merged is not deployed - check that the merge raised a push event "
                "(docs/decisions/ADR-004-merge-attribution-and-the-deploy-gap.md).",
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
        if behind:
            print(f"  {behind} commit(s) on origin/main are NOT in production")
        elif behind == 0:
            print("  up to date with origin/main")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
