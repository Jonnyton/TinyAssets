"""The sentence a failed served turn shows the user names the TRUE failure class.

2026-08-29, live: a healthy multi-step GitHub job ended on the idle watchdog and
the app said "Served provider 'codex' exhausted; universe authority forbids
fallback widening." -- which reads as quota. The provider-routing spec
("the user notice reflects the true failure class, never mislabeling a timeout
as capacity") forbids exactly that.
"""

from __future__ import annotations

from tinyassets.exceptions import AllProvidersExhaustedError
from tinyassets.universe_server import _served_failure_notice


def _exhausted(failure_class: str | None) -> AllProvidersExhaustedError:
    return AllProvidersExhaustedError(
        "Served provider 'codex' exhausted; universe authority forbids fallback widening.",
        failure_class=failure_class,
    )


def test_an_idle_timeout_is_described_as_the_turn_ending_not_capacity():
    notice = _served_failure_notice(_exhausted("provider_idle_timeout"))
    assert "went quiet" in notice
    # A resend repeats the whole instruction, and the turn may already have
    # acted (Codex round 1, P1 concern): the sentence must say so.
    assert "repeats" in notice
    assert "continue" in notice
    for mislabel in ("exhausted", "fallback", "capacity", "quota"):
        assert mislabel not in notice.lower()


def test_an_interactive_deadline_is_described_honestly():
    notice = _served_failure_notice(_exhausted("interactive_deadline"))
    assert "time limit" in notice
    assert "repeats" in notice
    assert "exhausted" not in notice


def test_a_real_outage_still_surfaces_verbatim():
    """A credentialed universe whose provider is genuinely down keeps the
    exception text: hiding a real outage behind a soft sentence would be a
    silent failure (Hard Rule 8)."""
    exc = _exhausted("provider_rate_limited")
    notice = _served_failure_notice(exc)
    assert notice == f"Your universe couldn't be reached right now: {exc}"


def test_an_exception_without_a_failure_class_is_unchanged():
    exc = RuntimeError("engine binding unreadable")
    assert _served_failure_notice(exc) == (
        "Your universe couldn't be reached right now: engine binding unreadable"
    )
