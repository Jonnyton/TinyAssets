"""Prove retired public MCP routes are ordinary absent-route responses."""

from __future__ import annotations

import argparse
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from typing import Protocol

METHODS = ("GET", "HEAD", "POST", "OPTIONS")
RETIRED_PATHS = (
    "/mcp-directory",
    "/mcp-directory/",
    "/mcp-directory/arbitrary",
    "/mcp-directory/catalog/2026-06-24-underscore-handles",
    "/mcp-directory?catalog=retired",
)


class _Opener(Protocol):
    def open(self, request: urllib.request.Request, timeout: float): ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _observe(
    opener: _Opener,
    *,
    method: str,
    url: str,
    timeout: float,
) -> tuple[int | None, object, bytes, str | None]:
    data = b'{"jsonrpc":"2.0","id":1,"method":"initialize"}' if method == "POST" else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-03-26",
        },
    )
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc
    except (urllib.error.URLError, OSError) as exc:
        return None, {}, b"", f"{type(exc).__name__}: {exc}"

    try:
        body = response.read()
    except (urllib.error.URLError, OSError) as exc:
        return None, {}, b"", f"{type(exc).__name__}: {exc}"
    return response.code, response.headers, body, None


def verify_retired_routes(
    *,
    base_url: str = "https://tinyassets.io",
    methods: Sequence[str] = METHODS,
    paths: Sequence[str] = RETIRED_PATHS,
    deadline_seconds: float = 60,
    request_timeout: float = 2,
    retry_delay: float = 5,
    opener: _Opener | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> list[str]:
    """Return an empty list only when the complete matrix is an ordinary 404."""
    if request_timeout <= 0:
        raise ValueError("request_timeout must be positive")
    if deadline_seconds < 0:
        raise ValueError("deadline_seconds must be non-negative")

    http = opener or urllib.request.build_opener(_NoRedirect)
    single_attempt = deadline_seconds == 0
    deadline = monotonic() + deadline_seconds

    while True:
        failures: list[str] = []
        for method in methods:
            for path in paths:
                remaining = deadline - monotonic()
                if not single_attempt and remaining <= 0:
                    failures.append("probe deadline exhausted before matrix completed")
                    return failures
                timeout = request_timeout if single_attempt else min(request_timeout, remaining)
                url = f"{base_url.rstrip('/')}{path}"
                status, headers, body, error = _observe(
                    http,
                    method=method,
                    url=url,
                    timeout=timeout,
                )
                if error is not None:
                    failures.append(f"{method} {url}: transport={error}")
                    continue
                if status != 404:
                    failures.append(f"{method} {url}: status={status}")
                location = headers.get("Location")
                if location is not None:
                    failures.append(f"{method} {url}: Location={location!r}")
                if method != "HEAD" and body != b"Not Found":
                    failures.append(f"{method} {url}: body={body[:120]!r}")

        if not failures or single_attempt:
            return failures
        remaining = deadline - monotonic()
        if remaining <= 0:
            return failures
        sleep(min(retry_delay, remaining))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://tinyassets.io")
    parser.add_argument("--deadline", type=float, default=60)
    parser.add_argument("--request-timeout", type=float, default=2)
    args = parser.parse_args(argv)

    failures = verify_retired_routes(
        base_url=args.base_url,
        deadline_seconds=args.deadline,
        request_timeout=args.request_timeout,
    )
    if failures:
        print("\n".join(failures))
        return 1
    print("retired-route matrix is an ordinary 404 at the edge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
