"""Out-of-GitHub-scheduler dead-man for release reconciliation.

The production host's systemd timer runs this probe every five minutes. A
Healthchecks-compatible external monitor receives the normal ping while the
newest successful scheduled reconcile run is fresh, or ``/fail`` otherwise.
If this process, its timer, the host, or the network stops, the monitor misses
the heartbeat and alerts independently.

Stdlib only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

DEFAULT_RUNS_URL = (
    "https://api.github.com/repos/Jonnyton/TinyAssets/actions/workflows/"
    "release-reconcile.yml/runs?event=schedule&status=success&per_page=20"
)
DEFAULT_THRESHOLD_MIN = 30.0
DEFAULT_TIMEOUT = 15.0

STALE_EXIT_CODE = 2
API_EXIT_CODE = 3
HEARTBEAT_EXIT_CODE = 4
CONFIG_EXIT_CODE = 5


class DeadmanError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _parse_timestamp(value: object) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise DeadmanError(API_EXIT_CODE, "run has no parseable created_at")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DeadmanError(
            API_EXIT_CODE, f"run has invalid created_at={value!r}",
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def classify_runs(
    payload: object,
    *,
    now: dt.datetime,
    threshold_min: float,
) -> tuple[int, str]:
    """Classify the newest successful scheduled run as fresh or stale."""
    if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
        raise DeadmanError(API_EXIT_CODE, "GitHub response has no workflow_runs list")

    successful_schedules: list[dict[str, Any]] = []
    for run in payload["workflow_runs"]:
        if not isinstance(run, dict):
            raise DeadmanError(API_EXIT_CODE, "GitHub workflow_runs entry is not an object")
        if not {"event", "conclusion", "created_at"}.issubset(run):
            raise DeadmanError(
                API_EXIT_CODE,
                "GitHub workflow_runs entry is missing required fields",
            )
        if run["event"] == "schedule" and run["conclusion"] == "success":
            successful_schedules.append(run)

    if not successful_schedules:
        return STALE_EXIT_CODE, "STALE: no successful event=schedule run exists"

    newest = max(successful_schedules, key=lambda run: _parse_timestamp(run["created_at"]))
    created_at = _parse_timestamp(newest["created_at"])
    current = now.astimezone(dt.timezone.utc)
    age_min = (current - created_at).total_seconds() / 60.0
    threshold_text = f"{threshold_min:g}"
    run_url = newest.get("html_url") or "unknown"
    if age_min <= threshold_min:
        return 0, (
            f"FRESH: newest successful event=schedule run age={age_min:.1f}min "
            f"threshold={threshold_text}min run={run_url}"
        )
    return STALE_EXIT_CODE, (
        f"STALE: newest successful event=schedule run age={age_min:.1f}min "
        f"> threshold={threshold_text}min run={run_url}"
    )


def _request_json(
    url: str,
    timeout: float,
    opener: Callable[..., Any],
) -> object:
    _validate_url(url, "runs", API_EXIT_CODE)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "tinyassets-release-reconcile-deadman/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with opener(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (
        OSError,
        TimeoutError,
        UnicodeDecodeError,
        urllib.error.URLError,
        json.JSONDecodeError,
    ) as exc:
        raise DeadmanError(API_EXIT_CODE, f"GitHub runs API failed: {exc}") from exc


def _validate_url(url: str, label: str, code: int) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DeadmanError(code, f"{label} URL must be absolute HTTP(S)")
    return parsed


def _failure_url(heartbeat_url: str) -> str:
    parsed = _validate_url(heartbeat_url, "heartbeat", HEARTBEAT_EXIT_CODE)
    path = parsed.path.rstrip("/") + "/fail"
    return urllib.parse.urlunsplit(parsed._replace(path=path))


def _ping(url: str, timeout: float, opener: Callable[..., Any]) -> None:
    _validate_url(url, "heartbeat", HEARTBEAT_EXIT_CODE)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "tinyassets-release-reconcile-deadman/1.0"},
    )
    try:
        with opener(request, timeout=timeout) as response:
            response.read()
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise DeadmanError(
            HEARTBEAT_EXIT_CODE, f"heartbeat delivery failed: {exc}",
        ) from exc


def run_check(
    runs_url: str,
    heartbeat_url: str,
    *,
    threshold_min: float,
    timeout: float,
    now: dt.datetime | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> tuple[int, str]:
    """Run one check and always signal the independent heartbeat monitor."""
    try:
        payload = _request_json(runs_url, timeout, opener)
        code, message = classify_runs(
            payload,
            now=now or dt.datetime.now(tz=dt.timezone.utc),
            threshold_min=threshold_min,
        )
    except DeadmanError as exc:
        code, message = exc.code, exc.message

    try:
        _ping(heartbeat_url if code == 0 else _failure_url(heartbeat_url), timeout, opener)
    except DeadmanError as exc:
        return HEARTBEAT_EXIT_CODE, f"{message}; {exc.message}"
    return code, message


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--runs-url",
        default=os.environ.get("TINYASSETS_RELEASE_RECONCILE_RUNS_URL", DEFAULT_RUNS_URL),
    )
    parser.add_argument(
        "--heartbeat-url",
        default=os.environ.get("TINYASSETS_RELEASE_DEADMAN_HEARTBEAT_URL"),
    )
    parser.add_argument("--threshold-min", type=float, default=DEFAULT_THRESHOLD_MIN)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)

    if not args.heartbeat_url:
        print("[release-deadman] FAIL: heartbeat URL is required", file=sys.stderr)
        return CONFIG_EXIT_CODE
    if args.threshold_min <= 0 or args.timeout <= 0:
        print("[release-deadman] FAIL: threshold and timeout must be positive", file=sys.stderr)
        return CONFIG_EXIT_CODE

    code, message = run_check(
        args.runs_url,
        args.heartbeat_url,
        threshold_min=args.threshold_min,
        timeout=args.timeout,
    )
    stream = sys.stdout if code == 0 else sys.stderr
    print(f"[release-deadman] {message}", file=stream)
    return code


if __name__ == "__main__":
    sys.exit(main())
