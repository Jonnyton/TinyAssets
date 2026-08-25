"""Every consumer reason a user can see carries a next step they can act on."""

from __future__ import annotations

import pytest

from tinyassets.consumer_reason_actions import consumer_next_action


def test_provider_mismatch_names_both_providers_and_both_remedies():
    """The cold desktop test 2026-08-25 relayed this reason with no remedy."""
    action = consumer_next_action("provider_mismatch:automation=claude-code,serving=codex")
    assert "claude-code" in action and "codex" in action
    assert "rebind" in action.lower()
    assert "serving provider" in action
    assert "will not switch providers for you" in action


@pytest.mark.parametrize(
    "reason",
    [
        "no_due_trigger",
        "production_declined",
        "no_prepared_continuation",
        "provider_binding_missing",
        "no_daemon_for_principal",
        "no_serving_runtime",
        "not_an_automation_task",
        "consumer_not_applicable:assigned_cloud_automation",
        "consumer_not_applicable:automation_branch_version_missing",
        "refusal_unexplained",
        "requires_executor_class:tray",
        "reconcile_error:PermissionError:cloud background attempt is unavailable",
        "activate_error:CloudContinuationActivationError:assignment mismatched",
        "produce_error:PermissionError:x",
        "prepare_error:PermissionError:x",
        "claim_error:RuntimeError:x",
        "explain_error:RuntimeError:x",
        "binding_runtime_missing",
        "attempt_not_reserved",
    ],
)
def test_every_known_reason_has_an_actionable_step(reason):
    action = consumer_next_action(reason)
    assert action, reason
    assert len(action) > 40, reason


def test_unknown_and_empty_reasons_are_blank_not_invented():
    assert consumer_next_action("") == ""
    assert consumer_next_action("something_new_we_have_not_seen") == ""
    assert consumer_next_action(None) == ""  # type: ignore[arg-type]


def test_requires_executor_class_names_the_executor():
    assert "tray" in consumer_next_action("requires_executor_class:tray")


def test_served_deposit_guidance_matches_the_shipped_form():
    """Cold desktop test 2026-08-25: the universe told the founder to paste the four
    OAuth keys 'one per line' (the form has had four labelled boxes since #2536) and
    named an older button label it had learned. Served guidance is the UI copy the
    agent relays, so it must match the shipped form exactly."""
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "tinyassets" / "engine_mcp_server.py"
    text = source.read_text(encoding="utf-8")
    assert "one per line" not in text
    assert "FOUR\n    LABELLED BOXES" in text or "FOUR LABELLED BOXES" in text
    assert "that is the button's CURRENT label" in text
    app = source.parent / "onboarding" / "app.html"
    label = "Connect / add API connection"
    assert label in app.read_text(encoding="utf-8")
    assert label in text
