"""Per-universe LEARNED autonomy/trust policy (hardened per Codex 2026-08-09).

A proactive agent that acts on its OWN universe (self-patch draft PRs, internal
work) autonomously and asks only for what reaches the world; it LEARNS per
universe what it is trusted with. FAIL CLOSED (allowlist) + the store lives at
the data root, keyed by universe_id, outside the agent's writable workspace.
"""

from __future__ import annotations

from tinyassets import autonomy_policy as ap

U = "u-a"


def test_action_class_allowlist_fails_closed():
    # Safe sinks + pure-output runs are internal (trustable).
    assert ap.action_class("branch", "run", []) == "run.internal"
    assert ap.action_class("branch", "run", ["github_pull_request"]) == "run.internal"
    assert ap.action_class("branch", "run", ["chat_post"]) == "run.internal"
    # Anything reaching the world is high-stakes.
    assert ap.action_class("branch", "run", ["twitter_post"]) == "run.high_stakes"
    assert ap.action_class("branch", "run", ["github_merge"]) == "run.high_stakes"
    # FAIL CLOSED: an unknown/new/misspelled effect is high-stakes, not internal.
    assert ap.action_class("branch", "run", ["something_new"]) == "run.high_stakes"
    assert (
        ap.action_class("branch", "run", ["github_pull_request", "twitter_post"])
        == "run.high_stakes"
    )
    assert ap.action_class("scheduled_work", "run_now", []) == "automation.run"
    assert ap.action_class("effector", "grant", []) == "effector.grant"
    assert ap.action_class("chat_surface", "bind_channel", []) == "chat.bind"


def test_defaults_trust_own_machine_work_but_ask_outward(tmp_path):
    assert ap.is_trusted(tmp_path, U, "run.internal") is True
    assert ap.is_trusted(tmp_path, U, "automation.run") is True
    assert ap.is_trusted(tmp_path, U, "run.high_stakes") is False
    assert ap.is_trusted(tmp_path, U, "effector.grant") is False
    assert ap.is_trusted(tmp_path, U, "chat.bind") is False
    assert ap.is_trusted(tmp_path, U, "unknown.klass") is False


def test_learning_promotes_and_demotes(tmp_path):
    ap.set_trust(tmp_path, U, "run.high_stakes", ap.DECISION_TRUST, learned_from="founder")
    assert ap.is_trusted(tmp_path, U, "run.high_stakes") is True
    ap.set_trust(tmp_path, U, "run.internal", ap.DECISION_ASK, learned_from="founder")
    assert ap.is_trusted(tmp_path, U, "run.internal") is False


def test_policy_is_per_universe(tmp_path):
    # A trust rule for one universe must not leak to another (all-users UX).
    ap.set_trust(tmp_path, U, "run.high_stakes", ap.DECISION_TRUST, learned_from="founder")
    assert ap.is_trusted(tmp_path, U, "run.high_stakes") is True
    assert ap.is_trusted(tmp_path, "u-b", "run.high_stakes") is False


def test_learned_rule_persists(tmp_path):
    ap.set_trust(tmp_path, U, "effector.grant", ap.DECISION_TRUST, learned_from="founder")
    assert ap.decision_for(tmp_path, U, "effector.grant") == ap.DECISION_TRUST


def test_list_policy_shows_defaults_and_learned(tmp_path):
    ap.set_trust(tmp_path, U, "run.high_stakes", ap.DECISION_TRUST, learned_from="founder")
    pol = ap.list_policy(tmp_path, U)
    assert pol["run.internal"]["source"] == "default"
    assert pol["run.high_stakes"]["decision"] == "trust"
    assert pol["run.high_stakes"]["source"].startswith("learned")


def test_set_trust_rejects_bad_decision(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        ap.set_trust(tmp_path, U, "run.internal", "maybe")


def test_policy_read_failure_fails_safe_to_ask(tmp_path):
    bad = tmp_path / "nope"  # not created
    assert ap.is_trusted(bad, U, "run.high_stakes") is False
