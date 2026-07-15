"""Isolated generated-id helpers for universe serials.

A universe id is ``u-`` followed by a 26-character lowercase ULID
(48-bit millisecond timestamp + 80 bits of randomness, Crockford base32).
The serial is opaque, immutable, and time-sortable. It is generated exactly
once at creation and is used as the universe directory name and operation key
(``openspec/changes/universe-creation`` D2).

Kept in its own module so the serial format has a single source of truth and
never gets re-derived from a display name or learned identity.
"""

from __future__ import annotations

import os
import re
import time

# Crockford base32, lowercase. Excludes i, l, o, u to avoid transcription
# ambiguity — the canonical ULID alphabet, lowercased.
_CROCKFORD = "0123456789abcdefghjkmnpqrstvwxyz"

UNIVERSE_ID_PREFIX = "u-"
ULID_LENGTH = 26
# 10 chars encode the 48-bit millisecond timestamp; 16 chars encode 80 bits
# of randomness (10 * 5 = 50 >= 48; 16 * 5 = 80).
_TIMESTAMP_CHARS = 10
_RANDOM_CHARS = 16
_TIMESTAMP_MASK = (1 << 48) - 1

# Matches ``u-`` + a 26-char lowercase Crockford ULID. Shared with the spec's
# acceptance scenario regex ``u-[0-9a-hjkmnp-tv-z]{26}``.
UNIVERSE_ID_RE = re.compile(r"^u-[0-9a-hjkmnp-tv-z]{26}$")


def _encode_crockford(value: int, length: int) -> str:
    chars: list[str] = []
    for _ in range(length):
        value, rem = divmod(value, 32)
        chars.append(_CROCKFORD[rem])
    return "".join(reversed(chars))


def new_ulid(*, timestamp_ms: int | None = None) -> str:
    """Return a 26-character lowercase Crockford base32 ULID."""
    ts = int(time.time() * 1000) if timestamp_ms is None else int(timestamp_ms)
    ts &= _TIMESTAMP_MASK
    randomness = int.from_bytes(os.urandom(10), "big")  # 80 bits
    return (
        _encode_crockford(ts, _TIMESTAMP_CHARS)
        + _encode_crockford(randomness, _RANDOM_CHARS)
    )


def new_universe_id(*, timestamp_ms: int | None = None) -> str:
    """Return a fresh opaque universe serial: ``u-`` + lowercase ULID."""
    return f"{UNIVERSE_ID_PREFIX}{new_ulid(timestamp_ms=timestamp_ms)}"


def is_universe_serial(value: str) -> bool:
    """Return True if ``value`` is a generated ``u-``+ULID universe serial."""
    return bool(UNIVERSE_ID_RE.match(value or ""))
