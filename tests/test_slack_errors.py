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


def test_a_base64_credential_that_fails_to_decode_is_not_exposed(tmp_path):
    """Round 6: `_secret_value` chained the b64 decode failure, and a
    UnicodeDecodeError carries `.object` — the DECODED credential bytes. So
    chaining published the very token it was decoding."""
    import base64
    import json as _json

    from tinyassets.credential_vault import credential_vault_path
    from tinyassets.effectors.outbound_channel_adapter import resolve_slack_bot_token

    secret = b"xoxb-CHAIN-LEAK\xff"
    credential_vault_path(tmp_path).write_text(
        _json.dumps(
            {
                "credentials": [
                    {
                        "credential_type": "social",
                        "service": "slack",
                        "destination": "conn-1",
                        "token_b64": base64.b64encode(secret).decode(),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc:
        resolve_slack_bot_token(tmp_path, "conn-1")

    rendered = "".join(
        traceback.format_exception(type(exc.value), exc.value, exc.value.__traceback__)
    )
    assert "xoxb-CHAIN-LEAK" not in rendered + repr(exc.value.__context__)


def test_contains_secret_looks_inside_an_exception_group():
    """`ExceptionGroup.exceptions` is not part of the cause/context chain at
    all, so a token inside a grouped exception read as clean. asyncio's
    TaskGroup raises these routinely."""
    group = ExceptionGroup("outer", [ValueError(f"Bearer {SECRET}")])

    assert contains_secret(group, SECRET) is True


def test_a_service_name_holding_a_token_is_not_printed_back(tmp_path):
    """The deposit script prints this summary under the words 'nothing above
    contains a token'. `service` is arbitrary vault content — same class as the
    credential_type echo fixed a round earlier."""
    from tinyassets.credential_vault import write_credential_vault

    secret = "xoxb-SUMMARY-LEAK"
    summary = write_credential_vault(
        tmp_path,
        [
            {
                "credential_type": "social",
                "service": secret,
                "destination": "conn-1",
                "bot_token": "xoxb-EXAMPLE-NOT-A-REAL-TOKEN",
            }
        ],
    )

    import json as _json

    assert secret not in _json.dumps(summary)


def test_a_real_service_name_still_appears_in_the_summary(tmp_path):
    """The allow-list must not blank out the field it exists to report."""
    import json as _json

    from tinyassets.credential_vault import write_credential_vault

    summary = write_credential_vault(
        tmp_path,
        [
            {
                "credential_type": "social",
                "service": "slack",
                "destination": "conn-1",
                "bot_token": "xoxb-EXAMPLE-NOT-A-REAL-TOKEN",
            }
        ],
    )

    assert "slack" in _json.dumps(summary)


def test_a_single_record_write_upserts_and_cannot_delete(tmp_path):
    """Pins the semantics that burned this feature twice, in both directions.

    `write_credential_vault` treats a ONE-record payload as a read-modify-write
    upsert and a TWO-or-more payload as an exact replacement. Consequences:

    * Depositing one Slack connection replaced another, because the upsert key
      is (credential_type, service) and ignores `destination` — the depositor
      now merges by destination itself.
    * Filtering a record out and writing the remainder back does NOT delete it
      when the remainder is a single record. A revert that looked like it
      worked silently left the record in place.

    Neither behaviour is wrong on its own; the trap is that the same call means
    two different things depending on the length of the list.
    """
    from tinyassets.credential_vault import load_credential_vault, write_credential_vault

    write_credential_vault(
        tmp_path,
        [
            {"credential_type": "social", "service": "slack", "destination": "a",
             "bot_token": "xoxb-EXAMPLE-NOT-A-REAL-TOKEN"},
            {"credential_type": "llm_subscription", "service": "claude",
             "claude_config_dir": str(tmp_path / "cfg")},
        ],
    )
    assert len(load_credential_vault(tmp_path)) == 2

    # Try to "remove" the llm record by writing back only the other one.
    remaining = [
        r for r in load_credential_vault(tmp_path)
        if r.get("credential_type") != "llm_subscription"
    ]
    assert len(remaining) == 1
    write_credential_vault(tmp_path, remaining)

    kinds = {r.get("credential_type") for r in load_credential_vault(tmp_path)}
    assert kinds == {"social", "llm_subscription"}, (
        "a single-record write UPSERTS; it does not replace, so the filtered-out "
        "record survives"
    )

    # Two or more records DO replace exactly.
    write_credential_vault(
        tmp_path,
        [
            {"credential_type": "social", "service": "slack", "destination": "a",
             "bot_token": "xoxb-EXAMPLE-NOT-A-REAL-TOKEN"},
            {"credential_type": "social", "service": "slack", "destination": "b",
             "bot_token": "xoxb-EXAMPLE-NOT-A-REAL-TOKEN"},
        ],
    )
    assert {r.get("credential_type") for r in load_credential_vault(tmp_path)} == {"social"}
