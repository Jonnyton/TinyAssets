"""Tests for the production seams of the async action-result delivery tick (Slice 3).

The seams route/post through the real server-side path in production; here they are
exercised with the run store, router, and transport monkeypatched, so the projection
safety, the fresh-authorization gate, and the tick's never-raise contract are asserted
without a live Slack.
"""

from __future__ import annotations

import tinyassets.action_result_delivery_tick as tick


def _entry(**over):
    e = dict(
        run_id="r1", universe_id="u-tiny", workspace_id="T1", channel_id="C1",
        thread_ts="1700.1", app_binding_ref="A1", origin_event_id="Ev1",
    )
    e.update(over)
    return e


def test_get_run_projects_only_a_known_public_ref_never_raw_output(monkeypatch):
    # The raw output dict may hold internal detail; only a KNOWN public ref key is
    # surfaced (and the delivery core's allowlist still validates it).
    run = {
        "status": "completed",
        "output": {"pr_url": "https://github.com/x/y/pull/7", "secret": "xoxb-nope"},
    }
    monkeypatch.setattr("tinyassets.runs.get_run", lambda b, rid: run)
    got = tick.production_get_run("/base", "r1")
    assert got["public_result_ref"] == "https://github.com/x/y/pull/7"
    assert "secret" not in got  # only the ref was lifted, not the whole output


def test_get_run_does_not_override_an_explicit_public_ref(monkeypatch):
    run = {"status": "completed", "public_result_ref": "PR #9", "output": {"pr_url": "u"}}
    monkeypatch.setattr("tinyassets.runs.get_run", lambda b, rid: run)
    assert tick.production_get_run("/base", "r1")["public_result_ref"] == "PR #9"


def test_get_run_returns_none_for_a_missing_run(monkeypatch):
    monkeypatch.setattr("tinyassets.runs.get_run", lambda b, rid: None)
    assert tick.production_get_run("/base", "r1") is None


def test_authorize_holds_when_the_binding_no_longer_routes(monkeypatch):
    monkeypatch.setattr("tinyassets.app_ingress._route", lambda **k: None)
    assert tick.production_authorize(_entry(), "summary") is None


def test_authorize_holds_when_the_route_resolves_to_a_different_universe(monkeypatch):
    class _Routed:
        universe_id = "someone-else"

    monkeypatch.setattr("tinyassets.app_ingress._route", lambda **k: _Routed())
    assert tick.production_authorize(_entry(universe_id="u-tiny"), "summary") is None


def test_authorize_returns_the_route_when_it_still_owns_the_conversation(monkeypatch):
    class _Routed:
        universe_id = "u-tiny"

    routed = _Routed()
    monkeypatch.setattr("tinyassets.app_ingress._route", lambda **k: routed)
    auth = tick.production_authorize(_entry(universe_id="u-tiny"), "summary")
    assert auth is not None
    got_routed, entry = auth
    assert got_routed is routed and entry["channel_id"] == "C1"


def test_adapter_posts_the_summary_through_the_server_side_path(monkeypatch, tmp_path):
    posts = []

    def _spy_post(*, routed, channel_id, body, thread_ts, transport):
        posts.append({"channel_id": channel_id, "body": body, "thread_ts": thread_ts})
        return "slack:C1:1700.9"

    monkeypatch.setattr("tinyassets.app_ingress._post", _spy_post)

    class _Routed:
        universe_id = "u-tiny"

    receipt = tick.ProductionAdapter(tmp_path).deliver(
        (_Routed(), _entry()), "Done — the job finished.", idempotency_key="k",
    )
    assert receipt == "slack:C1:1700.9"
    assert posts[0]["channel_id"] == "C1" and "Done" in posts[0]["body"]


def test_adapter_is_idempotent_across_a_crash_retry(monkeypatch, tmp_path):
    # A second deliver with the SAME idempotency_key returns the cached receipt and
    # does NOT re-post (crash between post and mark, then reclaim + retry).
    posts = []

    def _spy_post(*, routed, channel_id, body, thread_ts, transport):
        posts.append(1)
        return "slack:C1:1700.9"

    monkeypatch.setattr("tinyassets.app_ingress._post", _spy_post)

    class _Routed:
        universe_id = "u-tiny"

    adapter = tick.ProductionAdapter(tmp_path)
    r1 = adapter.deliver((_Routed(), _entry()), "Done.", idempotency_key="action-result:r1:7")
    r2 = adapter.deliver((_Routed(), _entry()), "Done.", idempotency_key="action-result:r1:7")
    assert r1 == r2 == "slack:C1:1700.9"
    assert len(posts) == 1   # posted ONCE despite two deliver calls with the same key


def test_run_delivery_tick_never_raises(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("core exploded")

    monkeypatch.setattr(
        "tinyassets.action_result_delivery.deliver_pending_action_results", _boom,
    )
    counts = tick.run_delivery_tick("/base")   # must swallow + return zero counts
    assert counts == {"delivered": 0, "skipped_running": 0, "held": 0}
