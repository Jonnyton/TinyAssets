"""A turn refused for not fitting the model says so, in those words.

Live 2026-09-26, turn ``8dc8ada56b8e4d1cbfd2e4f37a111e7d``: a 1,274,067-byte
``read_graph target="model_options"`` result pushed the request past the selected
free model's context window, the router refused it with the exact sentence
"selected model cannot fit this inference context", and the owner was told "we
could not identify why".

Nothing was unknown. We measured it ourselves, against the model's own published
window, before anything was sent. The refusal carries no provider attempt, which
is why every taxonomy downstream read it as unclassified -- so the classifier has
to recognise its OWN words before it consults them.
"""

from __future__ import annotations

import pytest

from tinyassets.exceptions import AllProvidersExhaustedError
from tinyassets.universe_server import (
    _served_failure_code,
    _served_failure_notice,
    _served_failure_record,
)

_ROUTER_WORDS = "selected model cannot fit this inference context"
_WORKFLOW_WORDS = "selected model cannot fit this workflow context"


@pytest.mark.parametrize("words", [_ROUTER_WORDS, _WORKFLOW_WORDS])
def test_the_routers_own_context_refusal_is_classified(words):
    assert _served_failure_code(PermissionError(words)) == "context_window_exceeded"


def test_a_wrapper_that_says_exhausted_does_not_bury_the_measurement():
    """The chain is read, not just the outermost message."""
    wrapper = AllProvidersExhaustedError(
        "Served provider 'openrouter' exhausted; universe authority forbids "
        "fallback widening.",
    )
    wrapper.__cause__ = PermissionError(_ROUTER_WORDS)
    assert _served_failure_code(wrapper) == "context_window_exceeded"


def test_the_notice_says_what_happened_and_what_fixes_it():
    notice = _served_failure_notice(PermissionError(_ROUTER_WORDS))
    lowered = notice.lower()

    assert "could not identify why" not in lowered
    # The two facts the owner needs: what got too big, and what to change.
    assert "context window" in lowered
    assert "tools" in lowered and "conversation" in lowered
    assert "larger context window" in lowered


def test_the_refusal_is_placed_before_the_send_not_at_the_provider():
    record = _served_failure_record(PermissionError(_ROUTER_WORDS))
    assert record.code == "context_window_exceeded"
    assert record.stage == "before_send"
    # Our own words are the detail; they name the cause exactly, which was true
    # on the live turn too -- the detail string was right while the notice was not.
    assert "cannot fit" in record.provider_detail
    assert record.ref


def test_an_unrelated_mention_of_context_stays_unclassified():
    """The sentence, not the keyword: a provider talking about context is not this."""
    for unrelated in (
        "the request context was rejected",
        "context deadline exceeded",
        "selected model is not available",
    ):
        assert _served_failure_code(PermissionError(unrelated)) != "context_window_exceeded"


def test_the_code_is_a_real_member_of_the_closed_set():
    from tinyassets.conversation_failure import (
        FAILURE_CODES,
        STAGE_OF_CLASS,
        turn_failure,
    )

    assert "context_window_exceeded" in FAILURE_CODES
    assert STAGE_OF_CLASS["context_window_exceeded"] == "before_send"
    # A code outside the set degrades to unknown; this one must not.
    assert turn_failure("context_window_exceeded").code == "context_window_exceeded"
