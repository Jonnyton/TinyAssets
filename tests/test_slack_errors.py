"""Slack errors that cannot carry a credential.

The same two mistakes were made three times in three files in one sitting, and
a cross-family review reproduced a live token from each. These tests cover the
shared primitives; the per-module tests then prove each call site uses them.
"""

from __future__ import annotations

import traceback

import pytest

from tinyassets.effectors.slack_errors import (
    contains_secret,
    safe_error_code,
    scrubbed,
)

SECRET = "xoxb-VERY-SECRET-BOT"


class _Boom(Exception):
    pass


@pytest.mark.parametrize(
    "value,expected",
    [
        ("invalid_auth", "invalid_auth"),
        ("ratelimited", "ratelimited"),
        ("a", "a"),
        # Anything that is not a bare snake_case code is refused.
        ("invalid xoxb-VERY-SECRET-BOT", ""),
        ("Bearer xoxb-VERY-SECRET-BOT", ""),
        ("UPPER_CASE", ""),
        ("has-hyphens", ""),
        ("has spaces", ""),
        ("", ""),
        (None, ""),
        (42, ""),
        ({"error": "invalid_auth"}, ""),
        ("x" * 100, ""),
    ],
)
def test_only_real_slack_error_codes_pass_through(value, expected):
    assert safe_error_code(value) == expected


def test_a_default_is_used_when_the_code_is_refused():
    assert safe_error_code("invalid xoxb-LEAK", default="unknown_error") == (
        "unknown_error"
    )


def test_contains_secret_sees_through_a_cause():
    try:
        try:
            raise _Boom(f"Authorization: Bearer {SECRET}")
        except _Boom as inner:
            raise _Boom("wrapped") from inner
    except _Boom as exc:
        assert contains_secret(exc, SECRET) is True


def test_contains_secret_sees_through_a_context_too():
    """`from None` clears __cause__ but leaves __context__.

    Checking only the cause would miss a token that arrived by the other route
    — which is precisely the kind of near-miss that makes a scrub feel done
    while it is not.
    """
    try:
        try:
            raise _Boom(f"Authorization: Bearer {SECRET}")
        except _Boom:
            raise _Boom("wrapped") from None
    except _Boom as exc:
        assert exc.__cause__ is None
        assert contains_secret(exc, SECRET) is True


def test_contains_secret_is_false_for_a_clean_error():
    assert contains_secret(_Boom("http 503"), SECRET) is False


def test_contains_secret_with_no_secrets_is_false():
    """An empty token must not make everything look like a leak."""
    assert contains_secret(_Boom("anything"), "") is False
    assert contains_secret(_Boom("anything")) is False


def test_scrubbed_drops_a_diagnostic_that_carries_the_secret():
    try:
        raise _Boom(f"failed with Bearer {SECRET}")
    except _Boom as exc:
        result = scrubbed(exc, SECRET, fallback="unreachable", error_type=_Boom)

    assert str(result) == "unreachable"
    assert SECRET not in str(result)


def test_scrubbed_preserves_a_diagnostic_it_has_verified_is_clean():
    """The whole point of checking rather than blanket-replacing: keep the
    error someone actually needs to read."""
    try:
        raise _Boom("http 503 from slack")
    except _Boom as exc:
        result = scrubbed(exc, SECRET, fallback="unreachable", error_type=_Boom)

    assert "503" in str(result)


def test_scrubbed_result_carries_no_chain():
    """It is a fresh exception, so nothing rides along in __cause__."""
    try:
        raise _Boom(f"Bearer {SECRET}")
    except _Boom as exc:
        result = scrubbed(exc, SECRET, fallback="unreachable", error_type=_Boom)

    rendered = "".join(
        traceback.format_exception(type(result), result, result.__traceback__)
    )
    assert SECRET not in rendered
