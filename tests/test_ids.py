"""Tests for the isolated universe-serial id helper (universe-creation D2)."""

from __future__ import annotations

import re

from tinyassets.ids import (
    UNIVERSE_ID_RE,
    is_universe_serial,
    new_ulid,
    new_universe_id,
)

# The spec's acceptance regex for a generated universe id.
_SPEC_RE = re.compile(r"^u-[0-9a-hjkmnp-tv-z]{26}$")


def test_new_universe_id_matches_spec_format():
    uid = new_universe_id()
    assert _SPEC_RE.match(uid), uid
    assert UNIVERSE_ID_RE.match(uid)
    assert is_universe_serial(uid)


def test_ulid_is_26_lowercase_crockford_chars():
    ulid = new_ulid()
    assert len(ulid) == 26
    # Crockford lowercase excludes i, l, o, u.
    assert re.fullmatch(r"[0-9a-hjkmnp-tv-z]{26}", ulid), ulid


def test_ids_are_unique_across_a_batch():
    ids = {new_universe_id() for _ in range(500)}
    assert len(ids) == 500


def test_ids_are_time_sortable():
    early = new_universe_id(timestamp_ms=1_000_000_000_000)
    later = new_universe_id(timestamp_ms=2_000_000_000_000)
    # ULID timestamp prefix makes later ids sort after earlier ones.
    assert early < later


def test_provided_text_cannot_masquerade_as_serial():
    assert not is_universe_serial("my-cool-universe")
    assert not is_universe_serial("")
    assert not is_universe_serial("u-TOOSHORT")
    # Uppercase / ambiguous chars are not valid lowercase Crockford serials.
    assert not is_universe_serial("u-" + "I" * 26)
    assert not is_universe_serial("u-" + "l" * 26)


def test_timestamp_prefix_reflects_supplied_time():
    a = new_ulid(timestamp_ms=0)
    b = new_ulid(timestamp_ms=0)
    # Same timestamp -> identical first 10 (timestamp) chars, random suffix differs.
    assert a[:10] == b[:10]
