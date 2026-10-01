"""Harness D1a: the owner's Custom Rules decide what the agent may do.

Design #4172 §4.8-4.10 (founder-approved 2026-10-01): dots' four behaviours,
seeded to reproduce dots, editable only by the owner, with the three hand-backs
on by default and loosened only after the owner confirms what that allows.
D1a enforces at the credential-blind effector, where rules can only tighten the
standing destination grants.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tinyassets import agent_rules
from tinyassets.agent_rules import ASK_FIRST, DO, DO_IF_PREAPPROVED, HAND_OFF


def _universe(tmp_path: Path) -> Path:
    path = tmp_path / "data" / "u-alpha"
    path.mkdir(parents=True)
    return path


# -- seed ----------------------------------------------------------------------


def test_a_new_universe_is_seeded_to_work_like_dots(tmp_path):
    rules = {r.action_class: r.behaviour for r in agent_rules.list_rules(_universe(tmp_path))}
    assert rules["workspace.files"] == DO and rules["app.read"] == DO
    assert rules["people.message"] == ASK_FIRST and rules["commons.publish"] == ASK_FIRST
    for handback in ("money.move", "security.change", "access.grant"):
        assert rules[handback] == HAND_OFF, handback
    assert set(rules) == set(agent_rules.ACTION_CLASSES), "every class has a visible rule"


def test_the_seed_is_written_once_and_never_over_an_owners_edit(tmp_path):
    universe = _universe(tmp_path)
    agent_rules.set_rule(universe, "people.message", DO)
    assert agent_rules.decide(universe, "people.message").behaviour == DO
    assert agent_rules.decide(universe, "people.message").behaviour == DO


def test_the_store_lives_outside_the_universe_folder(tmp_path):
    universe = _universe(tmp_path)
    agent_rules.list_rules(universe)
    assert not any(universe.rglob("rules.db"))
    assert (tmp_path / "data" / ".agent-sessions" / "u-alpha" / "rules.db").exists()


# -- decide ---------------------------------------------------------------------


def test_the_most_specific_rule_wins(tmp_path):
    universe = _universe(tmp_path)
    agent_rules.set_rule(universe, "app.write", ASK_FIRST, connection="github")
    agent_rules.set_rule(universe, "app.write", DO, connection="github", operation="post")
    assert agent_rules.decide(universe, "app.write", connection="github",
                              operation="POST").behaviour == DO
    assert agent_rules.decide(universe, "app.write", connection="github",
                              operation="DELETE").behaviour == ASK_FIRST
    assert agent_rules.decide(universe, "app.write", connection="slack").behaviour == DO


def test_equally_specific_rules_go_to_the_stricter(tmp_path):
    universe = _universe(tmp_path)
    agent_rules.set_rule(universe, "app.write", ASK_FIRST, connection="a")
    agent_rules.set_rule(universe, "app.write", HAND_OFF, operation="DELETE")
    decided = agent_rules.decide(universe, "app.write", connection="b", operation="DELETE")
    assert decided.behaviour == HAND_OFF


def test_a_class_no_rule_covers_asks_first(tmp_path):
    decided = agent_rules.decide(_universe(tmp_path), "not.a.class")
    assert decided.behaviour == ASK_FIRST and not decided.proceeds


# -- the owner's edits -----------------------------------------------------------


def test_loosening_a_handback_needs_the_owner_to_confirm_what_it_allows(tmp_path):
    universe = _universe(tmp_path)
    with pytest.raises(agent_rules.RuleRefused) as refused:
        agent_rules.set_rule(universe, "money.move", ASK_FIRST)
    assert "move money" in str(refused.value)
    assert agent_rules.decide(universe, "money.move").behaviour == HAND_OFF
    agent_rules.set_rule(universe, "money.move", ASK_FIRST, confirm_handback=True)
    assert agent_rules.decide(universe, "money.move").behaviour == ASK_FIRST


def test_unknown_classes_and_behaviours_are_refused(tmp_path):
    universe = _universe(tmp_path)
    with pytest.raises(agent_rules.RuleRefused):
        agent_rules.set_rule(universe, "everything", DO)
    with pytest.raises(agent_rules.RuleRefused):
        agent_rules.set_rule(universe, "app.write", "sometimes")


def test_only_narrowed_rules_can_be_removed(tmp_path):
    universe = _universe(tmp_path)
    narrowed = agent_rules.set_rule(universe, "app.write", HAND_OFF, connection="bank")
    class_wide = next(r for r in agent_rules.list_rules(universe)
                      if r.action_class == "app.write" and not r.connection)
    assert agent_rules.delete_rule(universe, class_wide.id) is False
    assert agent_rules.delete_rule(universe, narrowed.id) is True
    assert agent_rules.decide(universe, "app.write", connection="bank").behaviour == DO


# -- enforcement at the effector -------------------------------------------------


@pytest.mark.parametrize("behaviour, kind", [
    (ASK_FIRST, "rule_ask_first"), (HAND_OFF, "rule_hand_off"),
    (DO_IF_PREAPPROVED, "rule_ask_first"),
])
def test_a_rule_stops_a_call_its_grant_would_allow(tmp_path, behaviour, kind):
    from tinyassets.effectors.authenticated_external_call import _rule_refusal

    universe = _universe(tmp_path)
    agent_rules.set_rule(universe, "app.write", behaviour, connection="conn-1")
    refusal = _rule_refusal(universe, "conn-1", "POST")
    assert refusal is not None and refusal["error_kind"] == kind
    assert refusal["dry_run"] is True


def test_the_seed_lets_a_granted_write_proceed_to_its_grant_check(tmp_path):
    from tinyassets.effectors.authenticated_external_call import _rule_refusal

    assert _rule_refusal(_universe(tmp_path), "conn-1", "POST") is None


def test_an_unreadable_rule_store_refuses_the_call(tmp_path, monkeypatch):
    from tinyassets.effectors import authenticated_external_call as effector

    def broken(*_a, **_kw):
        raise OSError("disk")

    monkeypatch.setattr(agent_rules, "decide", broken)
    refusal = effector._rule_refusal(_universe(tmp_path), "conn-1", "POST")
    assert refusal["error_kind"] == "rules_unreadable"


def test_the_effector_checks_rules_before_the_standing_grant():
    """Order matters: a rule must stop a call even when a grant exists."""
    from tinyassets.effectors import authenticated_external_call as effector

    source = Path(effector.__file__).read_text(encoding="utf-8")
    run = source[source.index("def _run("):]
    assert run.index("_rule_refusal(") < run.index("_check_consent(universe_dir")


# -- the owner door ----------------------------------------------------------------


class _Request:
    def __init__(self, method: str, body: dict | None = None):
        self.method = method
        self._body = json.dumps(body or {}).encode("utf-8")
        self.headers = {"content-type": "application/json", "origin": "https://tinyassets.io",
                        "host": "tinyassets.io", "content-length": str(len(self._body))}

    async def stream(self):
        yield self._body


def test_the_owner_door_reads_and_edits_only_the_callers_own_home(monkeypatch, tmp_path):
    from tinyassets import onboarding
    from tinyassets.api import helpers
    from tinyassets.auth import middleware

    universe = _universe(tmp_path)
    monkeypatch.setattr(helpers, "_base_path", lambda: tmp_path / "data")
    monkeypatch.setattr(onboarding, "onboarding_enabled", lambda: True)
    monkeypatch.setattr(onboarding, "_app_identity_required", lambda: None)
    monkeypatch.setattr(onboarding, "app_config",
                        lambda: {"resource": "https://tinyassets.io"})
    monkeypatch.setattr(middleware, "current_identity",
                        lambda: SimpleNamespace(user_id="owner-1"))
    homes = {"owner-1": "u-alpha"}
    monkeypatch.setattr(onboarding, "_read_home",
                        lambda identity, **_kw: homes.get(identity.user_id, ""))

    def call(method, body=None):
        response = asyncio.run(onboarding._handle_rules(_Request(method, body)))
        return response.status_code, json.loads(response.body)

    status, listing = call("GET")
    assert status == 200 and listing["universe_id"] == "u-alpha"
    assert {r["action_class"] for r in listing["rules"]} == set(agent_rules.ACTION_CLASSES)

    status, refused = call("POST", {"action_class": "access.grant", "behaviour": "do"})
    assert status == 409 and "access" in refused["detail"]
    status, saved = call("POST", {"action_class": "app.write", "behaviour": "hand_off",
                                  "connection": "bank"})
    assert status == 200 and saved["saved"]["behaviour"] == "hand_off"
    assert agent_rules.decide(universe, "app.write", connection="bank").behaviour == HAND_OFF

    # A caller with no home of their own edits nothing.
    monkeypatch.setattr(middleware, "current_identity",
                        lambda: SimpleNamespace(user_id="stranger"))
    assert call("GET")[0] == 404


# -- gpt-6-astra on #4193 ------------------------------------------------------------


def test_overlapping_narrow_rules_go_to_the_stricter(tmp_path):
    """Connection does not outrank operation: DELETE on the bank hands off."""
    universe = _universe(tmp_path)
    agent_rules.set_rule(universe, "app.write", DO, connection="bank")
    agent_rules.set_rule(universe, "app.write", HAND_OFF, operation="DELETE")
    assert agent_rules.decide(universe, "app.write", connection="bank",
                              operation="DELETE").behaviour == HAND_OFF


def test_removing_a_handback_restriction_needs_confirmation(tmp_path):
    universe = _universe(tmp_path)
    agent_rules.set_rule(universe, "money.move", DO, confirm_handback=True)
    narrowed = agent_rules.set_rule(universe, "money.move", HAND_OFF, connection="bank")
    with pytest.raises(agent_rules.RuleRefused):
        agent_rules.delete_rule(universe, narrowed.id)
    assert agent_rules.decide(universe, "money.move", connection="bank").behaviour == HAND_OFF
    assert agent_rules.delete_rule(universe, narrowed.id, confirm_handback=True)


def test_removing_a_handback_rule_under_a_handback_default_needs_nothing(tmp_path):
    universe = _universe(tmp_path)
    narrowed = agent_rules.set_rule(universe, "money.move", HAND_OFF, connection="bank")
    assert agent_rules.delete_rule(universe, narrowed.id) is True


@pytest.mark.parametrize("bad", [15.9, True, "3", -1, 2 ** 70])
def test_the_owner_door_takes_only_a_rule_id_to_delete(monkeypatch, tmp_path, bad):
    from tinyassets import onboarding
    from tinyassets.api import helpers
    from tinyassets.auth import middleware

    _universe(tmp_path)
    monkeypatch.setattr(helpers, "_base_path", lambda: tmp_path / "data")
    monkeypatch.setattr(onboarding, "onboarding_enabled", lambda: True)
    monkeypatch.setattr(onboarding, "_app_identity_required", lambda: None)
    monkeypatch.setattr(onboarding, "app_config",
                        lambda: {"resource": "https://tinyassets.io"})
    monkeypatch.setattr(middleware, "current_identity",
                        lambda: SimpleNamespace(user_id="owner-1"))
    monkeypatch.setattr(onboarding, "_read_home", lambda identity, **_kw: "u-alpha")
    response = asyncio.run(onboarding._handle_rules(_Request("POST", {"delete": bad})))
    assert response.status_code == 400


@pytest.mark.parametrize("kind, failure_class", [
    ("rule_ask_first", "rule_requires_approval"),
    ("rule_hand_off", "rule_hand_off"),
    ("rules_unreadable", "rules_unreadable"),
])
def test_a_rule_refusal_gets_its_own_class_and_advice(kind, failure_class):
    from tinyassets import runs

    line = f"external write failed - authenticated_external_call [{kind}] refused"
    assert runs._classify_external_write(line.lower()) == failure_class
    advice = runs.external_write_suggested_action(failure_class)
    assert advice and "yours to fix" not in advice


# -- D1b: declared operation kinds -----------------------------------------------------


def test_an_undeclared_operation_is_a_write(tmp_path):
    assert agent_rules.classify(_universe(tmp_path), "stripe", "post", "/v1/charges") == (
        "app.write", "POST")


def test_a_declared_payment_is_handed_back_by_default(tmp_path):
    from tinyassets.effectors.authenticated_external_call import _rule_refusal

    universe = _universe(tmp_path)
    agent_rules.declare_kind(universe, "stripe", "payment", method="POST",
                             path_prefix="/v1/charges")
    assert agent_rules.classify(universe, "stripe", "POST", "/v1/charges/ch_1") == (
        "money.move", "POST")
    refusal = _rule_refusal(universe, "stripe", "POST", "/v1/charges")
    assert refusal["error_kind"] == "rule_hand_off"
    # The same connection's undeclared paths are ordinary writes.
    assert _rule_refusal(universe, "stripe", "POST", "/v1/customers") is None


def test_the_longest_prefix_and_a_specific_method_win(tmp_path):
    universe = _universe(tmp_path)
    agent_rules.declare_kind(universe, "gh", "read", path_prefix="/")
    agent_rules.declare_kind(universe, "gh", "write", method="POST", path_prefix="/repos")
    agent_rules.declare_kind(universe, "gh", "access", method="PUT",
                             path_prefix="/repos/o/r/collaborators")
    assert agent_rules.classify(universe, "gh", "GET", "/user")[0] == "app.read"
    assert agent_rules.classify(universe, "gh", "POST", "/repos/o/r/issues")[0] == "app.write"
    assert agent_rules.classify(universe, "gh", "PUT",
                                "/repos/o/r/collaborators/bob")[0] == "access.grant"
    assert agent_rules.classify(universe, "gh", "GET", "/repositories")[0] == "app.read", (
        "a prefix matches whole path segments")


def test_a_message_kind_asks_first_by_default(tmp_path):
    from tinyassets.effectors.authenticated_external_call import _rule_refusal

    universe = _universe(tmp_path)
    agent_rules.declare_kind(universe, "slack", "message", path_prefix="/api/chat.postMessage")
    assert _rule_refusal(universe, "slack", "POST",
                         "/api/chat.postMessage")["error_kind"] == "rule_ask_first"


@pytest.mark.parametrize("prefix", ["v1", "/v1?x=1", "/v1#f"])
def test_a_bad_prefix_or_kind_is_refused(tmp_path, prefix):
    universe = _universe(tmp_path)
    with pytest.raises(agent_rules.RuleRefused):
        agent_rules.declare_kind(universe, "c", "read", path_prefix=prefix)
    with pytest.raises(agent_rules.RuleRefused):
        agent_rules.declare_kind(universe, "c", "steal")


def test_the_request_path_is_read_from_a_url_or_a_path():
    from tinyassets.effectors.authenticated_external_call import _request_path

    assert _request_path({"url": "https://api.x.com/v1/a?b=1"}) == "/v1/a"
    assert _request_path({"path": "/v1/b?c=2"}) == "/v1/b"
    assert _request_path({}) == "/"
