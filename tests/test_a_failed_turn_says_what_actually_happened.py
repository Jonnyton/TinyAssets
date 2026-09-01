"""A failed turn must not tell the owner a confident wrong story.

Founder, 2026-09-01. His universe stopped answering and the app said:

    Your universe couldn't be reached right now: Served provider 'codex'
    exhausted; universe authority forbids fallback widening.

So he went and checked his codex usage. It was fine. The real error, sitting in
the run record the whole time, was:

    CompilerError: Provider call failed in node 'heartbeat':
    provider invocation carrier is already consumed

One failure, three stories: the app said quota, the run record said
`provider_unavailable` and advised checking ANTHROPIC/GROQ/GEMINI keys on a
universe with `api_key_providers_enabled=False`, and the truth was a platform
bug in neither category.

Two causes, both fixed here:

* `_TURN_ENDED_FAILURE_CLASSES` mapped two classes and fell through to the raw
  router exception -- and that exception says "exhausted" for EVERY
  all-attempts-failed reason.
* the run classifier matched the bare substring "provider", which swallowed our
  own invariant failures into "your keys are wrong".

The governing rule these tests encode: **a vague answer is a poor outcome, a
confident wrong one is worse**, because the owner acts on it.
"""
from __future__ import annotations

import pytest

from tinyassets.exceptions import AllProvidersExhaustedError
from tinyassets.universe_server import (
    _TURN_ENDED_FAILURE_CLASSES,
    _served_failure_notice,
)


class _Failure(Exception):
    """A router exception, which carries its class as an attribute."""

    def __init__(self, message: str, failure_class: str | None = None):
        super().__init__(message)
        self.failure_class = failure_class


# The exact text the founder was shown.
_THE_MESSAGE = (
    "Served provider 'codex' exhausted; universe authority forbids fallback widening."
)


def test_the_exact_sentence_the_founder_saw_can_never_reach_a_user_again():
    """The regression, pinned verbatim."""
    notice = _served_failure_notice(_Failure(_THE_MESSAGE, "provider_unavailable"))
    assert "exhausted" not in notice.lower(), notice
    assert "codex" not in notice.lower(), "the raw exception is still leaking"


def test_a_platform_bug_is_named_as_ours_not_as_the_owners_problem():
    """`provider invocation carrier is already consumed` is our invariant, not
    anything the owner configured. It must never be described as quota, keys or
    billing."""
    notice = _served_failure_notice(
        _Failure(
            "Provider call failed in node 'heartbeat': provider invocation "
            "carrier is already consumed",
            "provider_unavailable",
        )
    )
    lowered = notice.lower()
    assert "our side" in lowered
    # It DENIES those causes rather than avoiding the words -- a naive
    # substring check flagged the denial itself, which is the copy doing its
    # job. Assert the meaning.
    assert "not a problem with your account" in lowered
    assert "usage limits" in lowered and "not a problem" in lowered
    assert "exhausted" not in lowered, "the raw quota wording still leaks"


@pytest.mark.parametrize(
    "failure_class",
    ["provider_rate_limited", "provider_overloaded", "auth_invalid",
     "endpoint_unreachable", "platform_fault"],
)
def test_every_class_the_platform_distinguishes_has_its_own_sentence(failure_class):
    """`diagnostics.py` separates auth_invalid from endpoint_unreachable and
    calls that split "the main signal operators need" -- and then the notice
    layer threw it away. A distinction the platform computes and does not show
    is a distinction it does not have."""
    assert failure_class in _TURN_ENDED_FAILURE_CLASSES
    notice = _TURN_ENDED_FAILURE_CLASSES[failure_class]
    assert notice.strip() and notice[-1] in ".!"


def test_no_two_classes_share_a_sentence():
    """If two causes read identically the distinction is decorative."""
    sentences = list(_TURN_ENDED_FAILURE_CLASSES.values())
    assert len(set(sentences)) == len(sentences)


def test_only_OUR_misleading_wrapper_is_replaced_with_an_honest_unknown():
    """The rule is "honest vs misleading", not "classified vs unclassified".

    An earlier draft of mine suppressed EVERY unmapped exception. Two existing
    tests caught it, and they were right: `engine binding unreadable` is precise
    and the owner is better off reading it. Blanket suppression trades one wrong
    answer for another by destroying good information to hide bad.

    Only the router's synthetic wrapper actually lies -- it says "exhausted" for
    every all-attempts-failed reason there is.
    """
    lying = _served_failure_notice(_Failure(_THE_MESSAGE))
    assert "could not identify why" in lying.lower()
    assert "exhausted" not in lying.lower()
    assert "billing" in lying.lower(), "it should rule out the wrong guess"

    honest = _served_failure_notice(_Failure("engine binding unreadable"))
    assert "engine binding unreadable" in honest, (
        "a precise, non-misleading cause must still reach the owner"
    )


def test_the_auth_notice_does_not_promise_a_request_that_may_not_exist():
    """The rail synthesises the connect ask only when NO binding exists. A
    binding whose credential died leaves the owner bound, unserved and un-asked
    -- so promising "there is a request waiting" would be the same
    confident-wrong shape being fixed here."""
    notice = _TURN_ENDED_FAILURE_CLASSES["auth_invalid"]
    lowered = notice.lower()
    assert "reconnect" in lowered
    assert "request waiting" not in lowered
    assert "billing" in lowered or "usage" in lowered, (
        "it should say plainly that this is not a billing problem"
    )


# ------------------------------------------------------- the advice on runs


def test_a_subscription_only_universe_is_not_told_to_check_api_keys(monkeypatch):
    """The advice the founder actually received, on a deployment configured to
    ignore those variables entirely. Advice the reader cannot act on is worse
    than none: it sends them somewhere nothing they find can help."""
    from tinyassets.api.runs import _no_provider_advice

    monkeypatch.delenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", raising=False)
    advice = _no_provider_advice()
    for banned in ("ANTHROPIC", "GROQ", "GEMINI"):
        assert banned not in advice, f"still naming {banned} on a subscription universe"
    assert "connect" in advice.lower()


def test_a_deployment_that_allows_api_keys_still_hears_about_them(monkeypatch):
    """The advice follows the configuration rather than replacing one fixed
    answer with another."""
    from tinyassets.api.runs import _no_provider_advice

    monkeypatch.setenv("TINYASSETS_ALLOW_API_KEY_PROVIDERS", "1")
    assert "API key" in _no_provider_advice()


def test_the_run_classifier_calls_a_carrier_fault_ours(monkeypatch):
    """`"provider" in msg` swallowed our own invariants into "check your keys".
    Order matters: the platform-fault test has to run first."""
    from tinyassets.api.runs import _classify_run_outcome_error

    result = _classify_run_outcome_error(
        "CompilerError: Provider call failed in node 'heartbeat': provider "
        "invocation carrier is already consumed"
    )
    assert result is not None
    failure_class, advice = result
    assert failure_class == "platform_fault", failure_class
    assert "our side" in advice.lower()
    for banned in ("ANTHROPIC", "GROQ", "GEMINI"):
        assert banned not in advice


# ------------------------------ the promise the notice makes must be true


def test_the_details_the_notice_promises_are_actually_recorded(caplog):
    """"we have recorded the details" was a lie when I shipped it.

    `AllProvidersExhaustedError` has carried a structured `attempts` list since
    FEAT-006 -- provider, status, skip_class, failure_class, cooldown, detail --
    and a repo-wide grep found NO consumer. The router assembled the exact
    diagnosis on every failure and dropped it, which is how one outage could be
    reported as quota, then as missing API keys, and be neither.

    A promise in a user-facing sentence is a claim about behaviour, and it needs
    a test like any other claim.
    """
    import logging

    from tinyassets.providers.diagnostics import ProviderAttemptDiagnostic
    from tinyassets.universe_server import _record_served_failure

    exc = AllProvidersExhaustedError(
        "Served provider 'codex' exhausted; universe authority forbids fallback widening.",
        failure_class="provider_unavailable",
        attempts=[
            ProviderAttemptDiagnostic(
                provider="codex",
                status="failed",
                skip_class="auth_invalid",
                detail="launch credential rejected",
                failure_class="auth_invalid",
            )
        ],
    )

    with caplog.at_level(logging.WARNING):
        _record_served_failure("u-test", exc)

    written = caplog.text
    assert "codex" in written
    assert "auth_invalid" in written, "the per-provider class was not recorded"
    assert "launch credential rejected" in written
    assert "u-test" in written


def test_recording_never_breaks_the_failure_path(caplog):
    """It runs while a turn is already failing. A diagnostics bug must not
    replace the owner's error with a stack trace."""
    import logging

    from tinyassets.universe_server import _record_served_failure

    class _Hostile(Exception):
        @property
        def attempts(self):
            raise RuntimeError("boom")

    with caplog.at_level(logging.WARNING):
        _record_served_failure("u-test", _Hostile("x"))   # must not raise

    assert "u-test" in caplog.text


def test_a_secret_in_provider_detail_does_not_reach_the_log(caplog):
    """`detail` is provider text and may carry a token or a host path. It is
    scrubbed, and it never enters the owner's notice at all."""
    import logging

    from tinyassets.providers.diagnostics import ProviderAttemptDiagnostic
    from tinyassets.universe_server import _record_served_failure

    exc = AllProvidersExhaustedError(
        "exhausted",
        attempts=[
            ProviderAttemptDiagnostic(
                provider="codex", status="failed", skip_class="auth_invalid",
                detail="clone failed https://x-access-token:ghp_SECRETVALUE@github.com/o/r",
            )
        ],
    )
    with caplog.at_level(logging.WARNING):
        _record_served_failure("u-test", exc)

    assert "ghp_SECRETVALUE" not in caplog.text, "a credential reached the log"


def test_the_recorder_is_actually_WIRED_into_the_failure_path():
    """Testing the helper is not testing that anything calls it.

    The mutation check caught this: deleting the call from the served-failure
    handler left every test above green, because they all invoke
    `_record_served_failure` directly. That is the same shape as the defect
    this PR started from -- a capability that exists and is not reachable on the
    surface that needs it.

    Source-level on purpose: the handler needs a full served turn to drive, and
    a guard that only fires when someone deletes the wiring is worth more than
    no guard at all.
    """
    import inspect
    import re

    import tinyassets.universe_server as srv

    source = inspect.getsource(srv)
    # The notice and the recorder must appear in the same handler, with the
    # recording BEFORE the reply is built.
    pattern = (
        r"_record_served_failure\(uid, exc\)\s*\n\s*"
        r"return json\.dumps\(\s*\{\s*\"error\":\s*"
        r"_served_failure_notice\(exc\)"
    )
    m = re.search(pattern, source)
    assert m, (
        "the served-failure handler no longer records the details before "
        "telling the owner that it has"
    )
