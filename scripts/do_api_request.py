#!/usr/bin/env python3
"""Make one bounded, credential-safe DigitalOcean API request."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable
from urllib import error, request
from urllib.parse import urlsplit

API_ORIGIN = "api.digitalocean.com"
API_PATH_PREFIX = "/v2/"
MAX_ERROR_BYTES = 4096
MAX_DIAGNOSTIC_CHARS = 300
REQUEST_TIMEOUT_SECONDS = 30
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]+")


class DigitalOceanRequestError(RuntimeError):
    def __init__(
        self,
        *,
        status: int | None,
        diagnostic: str,
        transport: str | None = None,
    ) -> None:
        self.status = status
        self.diagnostic = diagnostic
        self.transport = transport
        failure_class = f"HTTP {status}" if status is not None else transport
        super().__init__(f"{failure_class}: {diagnostic}")


def sanitize_failure_body(raw: bytes, token: str) -> str:
    bounded = raw[:MAX_ERROR_BYTES]
    decoded = bounded.decode("utf-8", errors="replace")
    try:
        payload = json.loads(decoded)
    except (json.JSONDecodeError, TypeError):
        text = decoded
    else:
        if isinstance(payload, dict):
            fields = []
            for name in ("id", "message"):
                value = payload.get(name)
                if isinstance(value, (str, int, float, bool)):
                    fields.append(f"{name}={value}")
            text = "; ".join(fields) if fields else "unstructured JSON error"
        else:
            text = "unstructured JSON error"

    text = _BEARER_PATTERN.sub("[REDACTED]", text)
    if token:
        text = text.replace(token, "[REDACTED]")
    text = _CONTROL_PATTERN.sub(" ", text)
    text = " ".join(text.split())
    if not text:
        text = "(empty response)"
    if len(text) > MAX_DIAGNOSTIC_CHARS:
        text = f"{text[: MAX_DIAGNOSTIC_CHARS - 3]}..."
    return text


def _validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != API_ORIGIN
        or not parsed.path.startswith(API_PATH_PREFIX)
        or parsed.username
        or parsed.password
    ):
        raise ValueError("request URL must target the DigitalOcean API v2 origin")


def api_request(
    *,
    method: str,
    url: str,
    token: str,
    data: bytes | None = None,
    opener: Callable = request.urlopen,
) -> bytes:
    _validate_url(url)
    normalized_method = method.upper()
    if normalized_method not in {"GET", "POST", "DELETE"}:
        raise ValueError(f"unsupported DigitalOcean API method: {method}")
    if not token:
        raise ValueError("DigitalOcean API token is empty")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    api_request_object = request.Request(
        url,
        data=data,
        headers=headers,
        method=normalized_method,
    )
    try:
        with opener(
            api_request_object,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as response:
            return response.read()
    except error.HTTPError as exc:
        raw = exc.read(MAX_ERROR_BYTES)
        raise DigitalOceanRequestError(
            status=exc.code,
            diagnostic=sanitize_failure_body(raw, token),
        ) from None
    except (error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        diagnostic = sanitize_failure_body(str(reason).encode(), token)
        raise DigitalOceanRequestError(
            status=None,
            transport=type(exc).__name__,
            diagnostic=diagnostic,
        ) from None


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", required=True, choices=("GET", "POST", "DELETE"))
    parser.add_argument("--url", required=True)
    parser.add_argument("--data")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    token = os.environ.get("DO_TOKEN", "")
    try:
        body = api_request(
            method=args.method,
            url=args.url,
            token=token,
            data=args.data.encode() if args.data is not None else None,
        )
    except (DigitalOceanRequestError, ValueError) as exc:
        path = urlsplit(args.url).path or "(invalid URL)"
        print(
            f"::error::DigitalOcean API {args.method} {path} failed: {exc}",
            file=sys.stderr,
        )
        return 1
    sys.stdout.buffer.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
