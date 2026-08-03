"""Validate the shared request/admission HMAC key without exposing it."""

from __future__ import annotations

import base64
import binascii
import os

ENV_NAME = "TINYASSETS_REQUEST_IDEMPOTENCY_HMAC_KEY"
MIN_KEY_BYTES = 32


def validate_secret(value: str) -> bytes:
    """Return decoded key bytes for one canonical single-line base64 value."""
    if not value or "\r" in value or "\n" in value:
        raise ValueError("secret must be non-empty single-line canonical base64")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("secret must be non-empty single-line canonical base64") from exc
    if base64.b64encode(decoded).decode("ascii") != value:
        raise ValueError("secret must use canonical standard base64 encoding")
    if len(decoded) < MIN_KEY_BYTES:
        raise ValueError(f"secret must decode to at least {MIN_KEY_BYTES} bytes")
    return decoded


def main() -> int:
    try:
        validate_secret(os.environ.get(ENV_NAME, ""))
    except ValueError as exc:
        print(f"::error::{ENV_NAME} {exc}")
        return 1
    print(f"{ENV_NAME} is valid canonical base64 with sufficient entropy length")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
