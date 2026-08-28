"""A universe is born from a signup or a subscription, and nothing else.

Founder rule, 2026-08-28: no universe should exist that is not bound to a WorkOS user.
Two legitimate births follow from it -- the free one a signup gets, and the extra ones a
subscription pays for -- and every other path is refused.

Enforced on the public surface rather than in `_action_create_universe`, which is a
shared primitive that fixtures, migrations and internal seeding call with no
authenticated subject. Gating it there refused 23 legitimate internal callers; that was
the signal the rule is about PEOPLE and belongs where a person asks.
"""

from __future__ import annotations

import pytest

from tinyassets import universe_server as us


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    return tmp_path


def _actor(monkeypatch, actor_id):
    from tinyassets.api import permissions

    monkeypatch.setattr(permissions, "current_request_actor_id", lambda: actor_id)


def _home(monkeypatch, value):
    import tinyassets.daemon_server as ds

    monkeypatch.setattr(ds, "get_founder_home", lambda *_a, **_kw: value)


def test_anonymous_cannot_birth_a_universe(monkeypatch):
    _actor(monkeypatch, "anonymous")
    out = us._universe_birth_refusal()
    assert out is not None
    assert out["failure_class"] == "universe_requires_authenticated_subject"


def test_an_empty_actor_cannot_birth_a_universe(monkeypatch):
    _actor(monkeypatch, "")
    assert us._universe_birth_refusal() is not None


def test_a_signup_with_no_home_gets_one_free(monkeypatch):
    _actor(monkeypatch, "user_01SIGNUP")
    _home(monkeypatch, "")
    assert us._universe_birth_refusal() is None


def test_a_second_universe_requires_a_subscription(monkeypatch):
    _actor(monkeypatch, "user_01ALREADY")
    _home(monkeypatch, "u-existing")
    out = us._universe_birth_refusal()
    assert out is not None
    assert out["failure_class"] == "additional_universe_requires_subscription"
    assert out["existing_universe_id"] == "u-existing"
    assert "subscribe" in out["error"].lower(), "say how to proceed, not just no"


def test_a_paid_subject_may_have_more_than_one(monkeypatch, tmp_path):
    from tinyassets.storage.subscription_state import apply_tier_event

    _actor(monkeypatch, "user_01PAID")
    _home(monkeypatch, "u-existing")
    udir = tmp_path / "u-existing"
    udir.mkdir(parents=True, exist_ok=True)
    apply_tier_event(udir, tier="paid", event_created=1000.0)
    assert us._universe_birth_refusal() is None


def test_an_unreadable_binding_fails_closed(monkeypatch):
    """If we cannot tell whether they already have one, we do not create one."""
    import tinyassets.daemon_server as ds

    _actor(monkeypatch, "user_01BROKEN")

    def _boom(*_a, **_kw):
        raise OSError("binding store unavailable")

    monkeypatch.setattr(ds, "get_founder_home", _boom)
    out = us._universe_birth_refusal()
    assert out is not None
    assert out["failure_class"] == "universe_binding_unreadable"


def test_an_unreadable_tier_does_not_grant_the_extra_universe(monkeypatch):
    """Fail-closed the other way too: unknown tier is not paid."""
    from tinyassets.storage import subscription_state

    _actor(monkeypatch, "user_01ODD")
    _home(monkeypatch, "u-existing")

    def _boom(*_a, **_kw):
        raise OSError("tier unreadable")

    monkeypatch.setattr(subscription_state, "get_tier", _boom)
    out = us._universe_birth_refusal()
    assert out is not None
    assert out["failure_class"] == "additional_universe_requires_subscription"


def test_the_birth_route_consults_the_gate_before_creating():
    """Asserted against the source: the check must precede the create call."""
    import pathlib

    src = pathlib.Path(us.__file__).read_text(encoding="utf-8")
    # Narrow window, not "anywhere before". The first version split on the whole file
    # and matched the function DEFINITION, which of course precedes the call site --
    # so deleting the actual call left it green. Mutation testing caught it.
    call_at = src.index('action="create_universe"')
    window = src[max(0, call_at - 700):call_at]
    assert "_universe_birth_refusal()" in window, (
        "the birth route must CALL the gate immediately before create_universe; "
        "defining it elsewhere is not enforcement"
    )
    # And it must act on the answer, not merely compute it.
    assert "_json.dumps(_refused)" in window
