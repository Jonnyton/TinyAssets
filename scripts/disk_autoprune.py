"""Reclaim disposable host storage when root disk usage crosses a threshold.

BUG-023 Phase 4 — last-line-of-defense against the silent disk-fill
outage class (2026-04-23 P0: 18h dark before host noticed). Runs the
same disposable-host cleanup class as the P0 triage path when root-volume
usage is at or above ``DISK_AUTOPRUNE_PCT`` (default 85%). Logs the
action + outcome.

Composes with Phases 2 + 3:
- Phase 2 rotates old run transcripts to ``archived/``.
- Phase 3 refuses new writes in over-capped subsystems.
- Phase 4 (this) reclaims space from the Docker layer cache when the
  root volume itself is pressured, regardless of subsystem caps.

Design:
- Stdlib only — matches disk_watch.py so it can run in the stripped
  production container without extra deps.
- Injection seams (``disk_fn``, ``prune_fn``) so tests can exercise
  the decision logic deterministically.
- Exit codes aligned with disk_watch.py's pattern.

Environment:
    DISK_AUTOPRUNE_PCT   integer threshold, default 85
    DISK_WATCH_PATH      filesystem path to check, default /
    DRY_RUN              set to 1/true to print plan without pruning
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Callable

_DEFAULT_PATH = "/"
_DEFAULT_THRESHOLD = 85
_CLEANUP_COMMANDS: tuple[tuple[str, tuple[str, ...], bool], ...] = (
    (
        "docker system prune -af",
        ("docker", "system", "prune", "-af"),
        False,
    ),
    (
        "docker builder prune -af",
        ("docker", "builder", "prune", "-af"),
        False,
    ),
    (
        "journalctl --vacuum-time=3d",
        ("journalctl", "--vacuum-time=3d"),
        True,
    ),
)


def _disk_usage_pct(path: str) -> float:
    usage = shutil.disk_usage(path)
    return usage.used / usage.total * 100.0


def _host_disk_reclaim(timeout: float = 180.0) -> tuple[int, str, str]:
    """Run disposable host cleanup. Returns (rc, stdout, stderr).

    This intentionally does not pass ``--volumes`` to Docker. TinyAssets data
    lives in volumes/bind mounts and needs explicit retention policy, not a
    generic emergency prune.
    """
    rc = 0
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    for label, command, optional in _CLEANUP_COMMANDS:
        try:
            proc = subprocess.run(
                list(command),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            if optional:
                stderr_chunks.append(f"$ {label}\nSKIPPED: {exc}")
                continue
            raise

        if proc.stdout:
            stdout_chunks.append(f"$ {label}\n{proc.stdout.strip()}")
        if proc.stderr:
            stderr_chunks.append(f"$ {label}\n{proc.stderr.strip()}")
        if proc.returncode != 0 and rc == 0:
            rc = proc.returncode

    return rc, "\n".join(stdout_chunks), "\n".join(stderr_chunks)


def check(
    path: str = _DEFAULT_PATH,
    threshold: int = _DEFAULT_THRESHOLD,
    *,
    dry_run: bool = False,
    disk_fn: Callable[[str], float] | None = None,
    prune_fn: Callable[[], tuple[int, str, str]] | None = None,
) -> int:
    """Reclaim disposable host storage when disk usage crosses threshold.

    Returns
    -------
    int
        0 when below threshold OR prune completed (even with warnings).
        1 when threshold crossed AND dry_run (would-prune signal).
        2 when prune invocation errored (subprocess failure / timeout).
    """
    _disk = disk_fn or _disk_usage_pct
    _prune = prune_fn or _host_disk_reclaim

    try:
        pct = _disk(path)
    except (FileNotFoundError, PermissionError, OSError) as exc:
        print(
            f"[disk-autoprune] WARN: cannot stat {path!r}: {exc}",
            file=sys.stderr,
        )
        return 0  # non-fatal — do not mask the real problem

    print(
        f"[disk-autoprune] {path}: {pct:.1f}% used "
        f"(threshold {threshold}%)"
    )

    if pct < threshold:
        print("[disk-autoprune] OK — below threshold")
        return 0

    print(
        f"[disk-autoprune] TRIGGER: {path} at {pct:.1f}% — "
        "reclaiming disposable host storage"
    )

    if dry_run:
        print(
            "[disk-autoprune] DRY_RUN: would run Docker system/builder "
            "prune and journal vacuum"
        )
        return 1

    try:
        rc, stdout, stderr = _prune()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        print(
            f"[disk-autoprune] ERROR: prune invocation failed: {exc}",
            file=sys.stderr,
        )
        return 2

    if stdout:
        print(f"[disk-autoprune] stdout: {stdout.strip()}")
    if stderr:
        print(f"[disk-autoprune] stderr: {stderr.strip()}", file=sys.stderr)

    if rc != 0:
        print(
            f"[disk-autoprune] prune exit code {rc} (non-fatal, logged)",
            file=sys.stderr,
        )
        return 0  # logged but not masking the underlying disk event

    try:
        after_pct = _disk(path)
        print(
            f"[disk-autoprune] post-prune {path}: {after_pct:.1f}% "
            f"(delta {pct - after_pct:+.1f}pp)"
        )
    except OSError:
        pass

    return 0


def main() -> int:
    path = os.environ.get("DISK_WATCH_PATH", _DEFAULT_PATH)
    threshold = int(
        os.environ.get("DISK_AUTOPRUNE_PCT", str(_DEFAULT_THRESHOLD))
    )
    dry_run = os.environ.get("DRY_RUN", "").strip() in ("1", "true", "yes")
    return check(path, threshold, dry_run=dry_run)


if __name__ == "__main__":
    sys.exit(main())
