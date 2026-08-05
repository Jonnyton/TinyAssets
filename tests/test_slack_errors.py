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


def test_contains_secret_follows_both_cause_and_context():
    """`cause or context` short-circuited: an exception with an explicit cause
    never had its context inspected, so a token there read as clean.

    The cause is CONSTRUCTED, not raised, so it carries no chain of its own.
    That detail is the whole test: a first draft raised it, which gave it the
    secret-bearing exception as its own context — so the short-circuit walked
    cause -> its context and found the token anyway. The mutation survived and
    the test looked fine. The secret has to be reachable ONLY through the outer
    exception's context for this to distinguish anything.
    """
    innocuous = _Boom("innocuous")  # never raised: no __context__ of its own
    try:
        try:
            raise _Boom(f"Bearer {SECRET}")  # becomes the OUTER's __context__
        except _Boom:
            raise _Boom("outer") from innocuous
    except _Boom as exc:
        assert exc.__cause__ is innocuous
        assert exc.__cause__.__context__ is None, "the cause is a dead end"
        assert SECRET in str(exc.__context__), "the secret is only in the context"
        assert contains_secret(exc, SECRET) is True, "both branches must be walked"


# --- the vault loader: three more channels a reviewer walked out through -----


def _vault_leak_rendered(tmp_path, content: bytes) -> tuple[str, BaseException]:
    from tinyassets.credential_vault import credential_vault_path, load_credential_vault

    credential_vault_path(tmp_path).write_bytes(content)
    with pytest.raises(ValueError) as exc:
        load_credential_vault(tmp_path)
    rendered = "".join(
        traceback.format_exception(type(exc.value), exc.value, exc.value.__traceback__)
    )
    return rendered + repr(exc.value.__context__) + repr(exc.value.args), exc.value


def test_undecodable_bytes_do_not_expose_the_vault(tmp_path):
    """`UnicodeDecodeError.object` is the whole file — a second channel with the
    same consequence as JSONDecodeError.doc, found by trying invalid UTF-8
    rather than invalid JSON."""
    secret = "xoxb-UTF8-VAULT-SECRET"
    rendered, _ = _vault_leak_rendered(
        tmp_path, b'{"credentials":[{"bot_token":"' + secret.encode() + b'"}]}\xff\xfe'
    )

    assert secret not in rendered


def test_malformed_nested_codex_auth_does_not_expose_its_contents(tmp_path):
    """Valid outer JSON, malformed base64-decoded inner auth: the nested
    JSONDecodeError's `.doc` held the decoded credential blob."""
    import base64
    import json as _json

    secret = "xoxb-NESTED-CONTENT-SECRET"
    inner = base64.b64encode(f'{{"token":"{secret}" BROKEN'.encode()).decode()
    payload = _json.dumps(
        {
            "credentials": [
                {
                    "credential_type": "llm_subscription",
                    "service": "codex",
                    "auth_json_b64": inner,
                }
            ]
        }
    ).encode()
    rendered, _ = _vault_leak_rendered(tmp_path, payload)

    assert secret not in rendered


def test_a_secret_in_credential_type_is_not_echoed_back(tmp_path):
    """The rejected value is attacker- or typo-supplied vault content, and a
    reviewer put a live token in this field and read it out of the error."""
    import json as _json

    secret = "xoxb-CREDTYPE-SECRET"
    payload = _json.dumps({"credentials": [{"credential_type": secret}]}).encode()
    rendered, exc = _vault_leak_rendered(tmp_path, payload)

    assert secret not in rendered
    assert "expected one of" in str(exc), "the allowed set is still named"
