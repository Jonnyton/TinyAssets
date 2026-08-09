"""Per-universe LEARNED autonomy/trust policy.

Founder 2026-08-09: a proactive agent that acts on the vision + self-improves
WITHOUT asking each time, and LEARNS over time which action-classes it is trusted
to do autonomously vs. which to ask about first — per universe, works for all users.
"""

from __future__ import annotations

from tinyassets import autonomy_policy as ap


def test_action_class_maps_by_surface_and_effects():
    assert ap.action_class("branch", "run", []) == "run.internal"
    assert ap.action_class("branch", "run", ["github_pull_request"]) == "run.internal"
    assert ap.action_class("branch", "run", ["twitter_post"]) == "run.high_stakes"
    assert ap.action_class("branch", "run", ["github_merge"]) == "run.high_stakes"
    assert ap.action_class("scheduled_work", "run_now", []) == "automation.run"
    assert (
        ap.action_class("scheduled_work", "resume", ["twitter_post"])
        == "automation.high_stakes"
    )
    assert ap.action_class("effector", "grant", []) == "effector.grant"
    assert ap.action_class("chat_surface", "bind_channel", []) == "chat.bind"


def test_defaults_trust_self_improvement_but_ask_high_stakes(tmp_path):
    # Proactive out of the box: internal runs (self-patch drafts, github mgmt) +
    # the founder's own automations run without asking.
    assert ap.is_trusted(tmp_path, "run.internal") is True
    assert ap.is_trusted(tmp_path, "automation.run") is True
    # Ask-first: publishing/merging, granting effects, going live to others.
    assert ap.is_trusted(tmp_path, "run.high_stakes") is False
    assert ap.is_trusted(tmp_path, "effector.grant") is False
    assert ap.is_trusted(tmp_path, "chat.bind") is False
    # Unknown class fails safe → ask.
    assert ap.is_trusted(tmp_path, "something.new") is False


def test_learning_promotes_and_demotes(tmp_path):
    # The founder can teach it to trust a currently-ask class...
    ap.set_trust(tmp_path, "run.high_stakes", ap.DECISION_TRUST, learned_from="founder")
    assert ap.is_trusted(tmp_path, "run.high_stakes") is True
    # ...and to start asking again for a class it used to trust.
    ap.set_trust(tmp_path, "run.internal", ap.DECISION_ASK, learned_from="founder")
    assert ap.is_trusted(tmp_path, "run.internal") is False


def test_learned_rule_overrides_default_and_persists(tmp_path):
    ap.set_trust(tmp_path, "effector.grant", ap.DECISION_TRUST, learned_from="founder")
    # A fresh read (new call) still sees the learned rule.
    assert ap.decision_for(tmp_path, "effector.grant") == ap.DECISION_TRUST


def test_list_policy_shows_defaults_and_learned(tmp_path):
    ap.set_trust(tmp_path, "run.high_stakes", ap.DECISION_TRUST, learned_from="founder")
    pol = ap.list_policy(tmp_path)
    assert pol["run.internal"]["source"] == "default"
    assert pol["run.high_stakes"]["decision"] == "trust"
    assert pol["run.high_stakes"]["source"].startswith("learned")


def test_set_trust_rejects_bad_decision(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        ap.set_trust(tmp_path, "run.internal", "maybe")


def test_policy_read_failure_fails_safe_to_ask(tmp_path, monkeypatch):
    # If the policy store can't be read, an ASK-default class must NOT flip to
    # trusted (fail safe), and a would-be trusted class falls back to its default.
    bad = tmp_path / "nope"  # not created
    assert ap.is_trusted(bad, "run.high_stakes") is False
