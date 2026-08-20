"""Server-side delivery of one external chat event.

The properties under test are the ones that let the Slack agent stop mounting
the production volume: the daemon decides the universe, the daemon holds the
credential, and the transport gets back nothing it could forge or leak.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest

from tinyassets import app_ingress
from tinyassets.custom_agents import create_binding, publish_definition
from tinyassets.daemon_server import (
    grant_universe_access,
    initialize_author_server,
)
from tinyassets.storage.app_channel_bindings import AppChannelBindingStore

APP = "A0INGRESS01"
TEAM = "T0INGRESS01"
CHANNEL = "C0INGRESS01"
SENDER = "U0INGRESSFO"
OWNER = "U0INGRESSFO"


class _Receipt:
    def __init__(self, ref: str) -> None:
        self.provider_receipt_ref = ref


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    initialize_author_server(str(tmp_path))
    return tmp_path


def _make_universe(base, universe_id: str, owner: str = OWNER) -> str:
    grant_universe_access(
        str(base),
        universe_id=universe_id,
        actor_id=owner,
        permission="admin",
        granted_by=owner,
    )
    definition = publish_definition(
        str(base),
        author_id=owner,
        payload={
            "schema_version": 1,
            "name": f"agent for {universe_id}",
            "description": "ingress test",
            "tags": ["t"],
            "components": {
                "identity": {"kind": "soul", "config": {"instructions": "hi"}}
            },
        },
    )
    binding = create_binding(
        str(base),
        universe_id=universe_id,
        definition_id=definition["agent_definition_id"],
        created_by=owner,
        payload={"schema_version": 1, "name": "b", "model": "test"},
    )
    (base / universe_id).mkdir(exist_ok=True)
    return binding["agent_binding_id"]


def _bind(base, universe_id: str, agent_binding_id: str, channel_id: str = "") -> None:
    AppChannelBindingStore(base).bind(
        provider="slack",
        installation_id=f"{APP}:{TEAM}",
        workspace_id=TEAM,
        channel_id=channel_id,
        universe_id=universe_id,
        agent_binding_id=agent_binding_id,
        binding_revision=1,
        bound_by=OWNER,
    )


def _deliver(**overrides):
    calls: dict = {"converse": [], "post": []}

    def _converse(universe_id, prompt, *, actor_id="", founder_grant=None,
                  conversation_history=None):
        calls["converse"].append(
            {
                "universe_id": universe_id,
                "prompt": prompt,
                "actor_id": actor_id,
                "founder_grant": founder_grant,
                "conversation_history": conversation_history,
            }
        )
        return "the universe answers"

    def _transport(destination, body, *, thread_ts=""):
        calls["post"].append(
            {"destination": destination, "body": body, "thread_ts": thread_ts}
        )
        return _Receipt(f"slack:{destination.address}:1700000000.000200")

    kwargs = {
        "provider": "slack",
        "api_app_id": APP,
        "workspace_id": TEAM,
        "actor_team_id": TEAM,
        "external_sender_id": SENDER,
        "channel_id": CHANNEL,
        "event_id": "Ev-ingress-1",
        "event_type": "app_mention",
        "text": "<@U0BOT> what do you know?",
        "converse": _converse,
        "transport": _transport,
    }
    kwargs.update(overrides)
    result = app_ingress.deliver_app_event(**kwargs)
    return result, calls


def test_a_bound_workspace_is_answered(base):
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    result, calls = _deliver()

    assert result.handled is True
    assert calls["converse"][0]["universe_id"] == "u-ingress-a"
    assert calls["post"][0]["body"] == "the universe answers"


def test_an_unbound_installation_is_silent(base):
    """No binding must mean silence, not a guessed universe."""
    _make_universe(base, "u-ingress-a")  # exists, but nothing routes to it

    result, calls = _deliver()

    assert result.handled is False
    assert calls["converse"] == []
    assert calls["post"] == []


def test_the_caller_cannot_name_the_universe(base):
    """The transport used to pass its own configured universe as a fallback.

    That made "which brain answers" a caller-supplied value. `deliver_app_event`
    takes no such parameter, so a caller trying to smuggle one in is a
    TypeError rather than a universe it was never entitled to.
    """
    binding = _make_universe(base, "u-ingress-a")
    _make_universe(base, "u-ingress-victim", owner="U0STRANGER1")
    _bind(base, "u-ingress-a", binding)

    with pytest.raises(TypeError):
        _deliver(fallback_universe_id="u-ingress-victim")

    # And the routed answer is still the bound one.
    result, calls = _deliver()
    assert result.handled is True
    assert calls["converse"][0]["universe_id"] == "u-ingress-a"


def test_the_channel_binding_wins_over_the_workspace_default(base):
    work = _make_universe(base, "u-ingress-work")
    hobby = _make_universe(base, "u-ingress-hobby")
    _bind(base, "u-ingress-work", work)  # workspace-wide
    _bind(base, "u-ingress-hobby", hobby, channel_id=CHANNEL)

    result, calls = _deliver()

    assert result.handled is True
    assert calls["converse"][0]["universe_id"] == "u-ingress-hobby"


def test_the_receipt_carries_no_reply_text_and_no_authority(base):
    """A transport that never sees the reply cannot log it elsewhere."""
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    result, _ = _deliver()

    rendered = repr(result)
    assert "the universe answers" not in rendered
    assert not hasattr(result, "founder_grant")
    assert not hasattr(result, "universe_id")
    assert not hasattr(result, "universe_dir")
    assert result.provider_receipt_ref == f"slack:{CHANNEL}:1700000000.000200"


def test_an_empty_prompt_costs_no_provider_call(base):
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    result, calls = _deliver(text="<@U0BOT>   ")

    assert result.handled is False
    assert calls["converse"] == []


def test_an_unsupported_provider_is_silent(base):
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    result, calls = _deliver(provider="discord")

    assert result.handled is False
    assert calls["converse"] == []


def test_the_actor_id_is_workspace_namespaced(base):
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    _, calls = _deliver()

    assert calls["converse"][0]["actor_id"] == f"slack:{TEAM}:{SENDER}"


def test_signed_founder_slack_turn_carries_exact_server_request_authority(
    base,
    monkeypatch,
):
    from tinyassets import app_ingress_http
    from tinyassets.auth.middleware import provider_request_capability

    binding = _make_universe(base, "u-ingress-authority")
    _bind(base, "u-ingress-authority", binding)
    grant = SimpleNamespace(
        subject_id=OWNER,
        agent_binding_id=binding,
        binding_revision=1,
    )
    monkeypatch.setattr(app_ingress, "_recognize", lambda **_kwargs: grant)
    seen: dict[str, object] = {}

    def _converse(universe_id, prompt, **kwargs):
        capability = provider_request_capability()
        assert capability is not None
        seen.update(
            universe_id=universe_id,
            prompt=prompt,
            principal=capability.principal_id,
            mechanism=capability.mechanism,
            issuer=capability.issuer,
            tool_name=capability.tool_name,
            **kwargs,
        )
        return "served"

    monkeypatch.setattr(
        "tinyassets.universe_intelligence.converse_as_external_sender",
        _converse,
    )
    monkeypatch.setattr(
        app_ingress,
        "_post",
        lambda **_kwargs: "slack:C0INGRESS01:1700000000.000200",
    )
    key = b"k" * 32
    now = 1_700_000_000
    body = json.dumps(
        {
            "provider": "slack",
            "api_app_id": APP,
            "workspace_id": TEAM,
            "actor_team_id": TEAM,
            "external_sender_id": SENDER,
            "channel_id": CHANNEL,
            "event_id": "Ev-authority-1",
            "event_type": "app_mention",
            "text": "<@U0BOT> prove authority",
            "thread_ts": "",
        }
    ).encode()
    timestamp = str(now)
    status, payload = app_ingress_http.handle_request(
        body=body,
        headers={
            app_ingress_http.SIGNATURE_HEADER: app_ingress_http.sign(
                body,
                timestamp,
                key,
            ),
            app_ingress_http.TIMESTAMP_HEADER: timestamp,
        },
        env={
            app_ingress_http.HMAC_ENV: base64.b64encode(key).decode("ascii"),
        },
        now=now,
    )

    assert status == 200
    assert payload["handled"] is True
    assert seen["principal"] == OWNER
    assert seen["mechanism"] == "tinyassets.authenticated-app-event.v1"
    assert seen["issuer"] == "tinyassets.app_ingress_http"
    assert seen["tool_name"] == "slack_event"
    # deliver_app_event no longer passes the routed PERSONA binding to converse:
    # converse resolves the SERVING binding itself (2026-08-19 Slack fix — the
    # persona binding is not the serving binding, and passing it made converse's
    # status=="serving" gate reject every turn). The server request authority
    # above is what must be carried; the serving binding is resolved downstream.
    assert "agent_binding_id" not in seen
    assert "binding_revision" not in seen


def test_a_replayed_event_mints_no_second_grant(base, monkeypatch):
    """Answer again, but never grant founder authority twice for one event.

    A recogniser that always grants is what makes this bite. Asserting only
    "the replay got None" passes with the replay guard DELETED, because with no
    founder mapping in the fixture the grant is None on both deliveries — the
    test would be measuring the absent mapping, not the guard.
    """
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    sentinel = object()
    monkeypatch.setattr(
        "tinyassets.founder_grant.FounderRecognizer.recognize",
        lambda self, event, **kwargs: sentinel,
        raising=True,
    )

    _, first = _deliver()
    _, second = _deliver()

    assert first["converse"][0]["founder_grant"] is sentinel
    assert second["converse"][0]["founder_grant"] is None
    assert first["converse"][0]["prompt"] == second["converse"][0]["prompt"]


def test_an_unattributable_sender_gets_no_turn(base):
    """A sender with no id must not reach the universe at all.

    Without the identity guard this still routes — routing does not depend on
    the sender — and `converse` runs with an actor id of ``slack:<team>:``,
    which is an unattributable turn wearing a well-formed name.
    """
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    result, calls = _deliver(external_sender_id="")

    assert result.handled is False
    assert calls["converse"] == []
    assert calls["post"] == []


def test_recognition_failure_degrades_instead_of_killing_the_turn(base, monkeypatch):
    """A broken recogniser must cost authority, not the whole workspace."""
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    def _boom(*a, **k):
        raise RuntimeError("recogniser is down")

    monkeypatch.setattr(
        "tinyassets.founder_grant.FounderRecognizer.recognize",
        _boom,
        raising=True,
    )
    result, calls = _deliver()

    # `handled is True` is the load-bearing assertion, and it is not vacuous:
    # without the except-branch in `_recognize` the RuntimeError propagates and
    # this call raises instead of returning. (Do NOT call `monkeypatch.undo()`
    # here — the fixture set TINYASSETS_DATA_DIR through the same object, so
    # undoing reverts the data dir too and every later lookup silently misses.)
    assert result.handled is True
    assert calls["converse"][0]["founder_grant"] is None


def test_an_empty_reply_tells_the_founder_instead_of_going_silent(base):
    # An empty reply is still a fault — but the founder must HEAR it, not be left
    # in silence. (Was: raise into silence; a persistent agent never goes dark.)
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    result, calls = _deliver(converse=lambda *a, **k: "   ")
    assert result.handled is True
    # The last post is an honest notice, not silence and not a fake success.
    last = calls["post"][-1]["body"].lower()
    assert "empty" in last or "again" in last


def test_a_failed_turn_posts_an_honest_notice_not_silence(base):
    # The live 2026-08-09 outage: the writer turn raised and the founder got only
    # silence for minutes. Now the daemon posts an honest notice and stays
    # handled. An UNCLASSIFIED exhaustion (no failure_class) must NOT be
    # mislabeled "capacity"/"rate limit" — that guess was the exact bug the
    # stream-and-classify change removes; a real rate-limit now arrives WITH its
    # class (see the classified case below).
    binding = _make_universe(base, "u-ingress-a")
    _bind(base, "u-ingress-a", binding)

    def _boom(*a, **k):
        from tinyassets.exceptions import AllProvidersExhaustedError

        raise AllProvidersExhaustedError("All providers exhausted for role=writer")

    result, calls = _deliver(converse=_boom)
    assert result.handled is True
    body = calls["post"][-1]["body"].lower()
    # Not silence: a notice was posted.
    assert body.strip()
    # Honest: an unclassified failure is a generic error, never a fabricated
    # "capacity" story.
    assert "capacity" not in body
    assert "rate limit" not in body
    assert "error finishing that turn" in body


def test_a_classified_rate_limit_turn_names_the_real_cause(base):
    # A turn that fails with a REAL classified rate-limit surfaces the true cause
    # (and retry-after) — the honest path a genuine limit takes.
    binding = _make_universe(base, "u-ingress-rl")
    _bind(base, "u-ingress-rl", binding)

    def _boom(*a, **k):
        from tinyassets.exceptions import AllProvidersExhaustedError

        raise AllProvidersExhaustedError(
            "Served provider exhausted",
            failure_class="provider_rate_limited",
            retry_after=30,
        )

    result, calls = _deliver(converse=_boom)
    assert result.handled is True
    body = calls["post"][-1]["body"].lower()
    assert "rate-limited" in body


#: A 1:1 DM channel id (Slack DM ids start with "D"). Durable memory is only
#: enabled here — the fail-closed multi-principal guard.
_DM = "D0INGRESSDM"


def _grant_founder(monkeypatch):
    """Make the ingress recognize the sender as the founder (a non-None grant)."""
    monkeypatch.setattr(
        "tinyassets.founder_grant.FounderRecognizer.recognize",
        lambda self, event, **kwargs: object(),
        raising=True,
    )


def test_memory_persists_across_turns(base, monkeypatch):
    """The durable store makes a stateless turn remember the last one.

    This is the whole point: u-tiny forgot everything between turns because the
    turn is a fresh `claude -p`. Turn 1 is recorded; turn 2 gets turn 1 fed back
    as PRIOR conversation, without the current message being double-shown. Runs
    only in a founder-authorized 1:1 DM (the fail-closed guard).
    """
    binding = _make_universe(base, "u-ingress-mem")
    _bind(base, "u-ingress-mem", binding)
    _grant_founder(monkeypatch)

    import tinyassets.effectors.slack_agent_turn as sat

    live = [
        {
            "speaker": "founder",
            "text": "my favorite topic is tide pools",
            "ts": "1700000000.000100",
        }
    ]
    monkeypatch.setattr(sat, "load_thread_history", lambda **_kwargs: list(live))

    # Turn 1: the live timeline supplies the current founder message id, but the
    # current message is excluded from its own prior-history block.
    _, calls1 = _deliver(
        channel_id=_DM,
        text="<@U0BOT> my favorite topic is tide pools",
        event_id="Ev-mem-1",
    )
    first_history = calls1["converse"][0]["conversation_history"] or []
    assert all("tide pools" not in m.text for m in first_history)

    # Turn 2: the durable store feeds turn 1 back in as prior context.
    live[:] = [
        *live,
        {
            "speaker": "universe",
            "text": "the universe answers",
            "ts": "1700000000.000200",
        },
        {
            "speaker": "founder",
            "text": "what did I say my favorite topic was?",
            "ts": "1700000000.000300",
        },
    ]
    _, calls2 = _deliver(
        channel_id=_DM,
        text="<@U0BOT> what did I say my favorite topic was?",
        event_id="Ev-mem-2",
    )
    history = calls2["converse"][0]["conversation_history"]
    texts = [m.text for m in history]
    assert "my favorite topic is tide pools" in texts  # founder's earlier turn
    assert "the universe answers" in texts  # the universe's own earlier reply
    assert texts.count("the universe answers") == 1
    # The current turn's own prompt is not shown inside its own memory block.
    assert "what did I say my favorite topic was?" not in texts


def test_current_founder_turn_uses_the_live_timeline_ts(base, monkeypatch):
    """Ingress derives the current message id daemon-side, without agent fields."""
    binding = _make_universe(base, "u-ingress-founder-id")
    _bind(base, "u-ingress-founder-id", binding)
    _grant_founder(monkeypatch)

    import tinyassets.conversation_store as cs
    import tinyassets.effectors.slack_agent_turn as sat
    from tinyassets.api.helpers import _universe_dir

    founder_ts = "1700000000.000111"
    calls = []

    def _timeline(**kwargs):
        calls.append(kwargs)
        return [{"speaker": "founder", "text": "hello", "ts": founder_ts}]

    monkeypatch.setattr(sat, "load_thread_history", _timeline)
    _, delivered = _deliver(
        channel_id=_DM,
        text="<@U0BOT> hello",
        event_id="Ev-founder-id-1",
    )

    conv_dir = _universe_dir("u-ingress-founder-id")
    identities = cs._recent_identities(conv_dir, f"slack:{_DM}", limit=10)
    founders = [row for row in identities if row[0] == "founder"]
    assert founders == [("founder", "hello", founder_ts)]
    assert delivered["converse"][0]["conversation_history"] == []
    assert calls and not calls[0].get("exclude_text")


def test_a_dropped_record_is_re_synced_from_the_live_timeline(base, monkeypatch):
    """HARDENING: `backfill_once` runs exactly once, so a dropped `record_turn`
    leaves the store BEHIND the live thread forever. The load path reconciles the
    tail from the live timeline so recent context is never lost.

    Mutation-check: remove the `sync_tail` call in `deliver_app_event` and the
    missed universe reply never reaches the next turn — this test goes red.
    """
    binding = _make_universe(base, "u-ingress-drift")
    _bind(base, "u-ingress-drift", binding)
    _grant_founder(monkeypatch)

    import tinyassets.conversation_store as cs
    import tinyassets.effectors.slack_agent_turn as sat
    from tinyassets.api.helpers import _universe_dir

    conv_dir = _universe_dir("u-ingress-drift")
    session = f"slack:{_DM}"
    # Store already backfilled (marker set) but then MISSED recording a later
    # reply — the exact silent-drift regression.
    cs.backfill_once(
        conv_dir,
        session,
        [{"speaker": "founder", "text": "start the plan", "ts": "1.0"}],
    )
    cs.record_turn(
        conv_dir, session, "universe", "starting now", ts=2.0, ext_id="2.0"
    )

    # The live Slack timeline is AHEAD: it also holds the turns the store missed.
    live = [
        {"speaker": "founder", "text": "start the plan", "ts": "1.0"},
        {"speaker": "universe", "text": "starting now", "ts": "2.0"},
        {"speaker": "founder", "text": "any update?", "ts": "3.0"},
        {"speaker": "universe", "text": "shipped part one", "ts": "4.0"},
    ]
    monkeypatch.setattr(sat, "load_thread_history", lambda **k: live)

    _, calls = _deliver(
        channel_id=_DM, text="<@U0BOT> what did you ship?", event_id="Ev-drift-1"
    )
    history = calls["converse"][0]["conversation_history"]
    texts = [m.text for m in history]
    assert "any update?" in texts
    assert "shipped part one" in texts  # the missed tail is reconciled in


def test_memory_is_off_in_a_shared_channel(base, monkeypatch):
    """Fail-closed multi-principal guard (Codex REJECT 2026-08-09): even a
    recognized founder gets NO durable memory outside a 1:1 DM. A shared channel
    is multi-principal and the session is channel-keyed, so loading its history
    could inject another person's words into a founder turn.

    Mutation-check: drop the `startswith("D")` half of `memory_on` and the seeded
    shared-channel history rides into the turn — this goes red.
    """
    binding = _make_universe(base, "u-ingress-share")
    _bind(base, "u-ingress-share", binding)
    _grant_founder(monkeypatch)

    import tinyassets.conversation_store as cs
    from tinyassets.api.helpers import _universe_dir

    conv_dir = _universe_dir("u-ingress-share")
    shared = "C0SHAREDXX"
    # Seed a store for this channel so an empty history can ONLY be the guard.
    cs.record_turn(conv_dir, f"slack:{shared}", "founder", "prior shared secret")

    _, calls = _deliver(channel_id=shared, text="<@U0BOT> hi", event_id="Ev-share-1")
    history = calls["converse"][0]["conversation_history"] or []
    assert history == []  # nothing loaded or injected in a shared channel


def test_the_reply_is_recorded_only_after_it_is_posted(base, monkeypatch):
    """POST-THEN-RECORD (Codex REJECT 2026-08-09): history must never claim a
    reply the founder never received. If delivery fails, the universe reply is
    NOT in the store (the founder's own message, recorded before converse, is).

    Mutation-check: record the reply BEFORE `_post` and this goes red.
    """
    binding = _make_universe(base, "u-ingress-por")
    _bind(base, "u-ingress-por", binding)
    _grant_founder(monkeypatch)

    import tinyassets.conversation_store as cs
    import tinyassets.effectors.slack_agent_turn as sat
    from tinyassets.api.helpers import _universe_dir

    conv_dir = _universe_dir("u-ingress-por")
    session = f"slack:{_DM}"
    monkeypatch.setattr(
        sat,
        "load_thread_history",
        lambda **_kwargs: [
            {"speaker": "founder", "text": "hello there", "ts": "1700000000.000100"}
        ],
    )

    def _post_boom(destination, body, *, thread_ts=""):
        raise RuntimeError("slack post 500")

    # A failed reply post no longer PROPAGATES (Codex #3: propagating made the
    # caller post a second message, risking a double-post against an ambiguous
    # commit). It returns handled=False and records nothing — the undelivered
    # reply must never enter history.
    result, _calls = _deliver(
        channel_id=_DM, transport=_post_boom,
        text="<@U0BOT> hello there", event_id="Ev-por-1",
    )
    assert result.handled is False

    stored = [m.text for m in cs.load_recent(conv_dir, session)]
    assert "the universe answers" not in stored  # undelivered reply not recorded
    assert "hello there" in stored  # the founder's message WAS recorded pre-converse


def test_a_reply_post_that_commits_then_raises_never_double_posts(base, monkeypatch):
    """Codex #3: if the reply post commits to Slack and THEN raises (e.g. the
    response is lost while reading the receipt), deliver must NOT attempt a second
    (notice) post — a double-post is worse than silence and we cannot know the
    commit happened. It posts exactly once and returns handled=False."""
    binding = _make_universe(base, "u-ingress-dp")
    _bind(base, "u-ingress-dp", binding)
    _grant_founder(monkeypatch)

    posts: list[str] = []

    def _commit_then_raise(destination, body, *, thread_ts=""):
        posts.append(body)  # Slack accepted (committed) ...
        raise RuntimeError("lost the response reading the receipt")  # ... then raised

    result, _calls = _deliver(
        channel_id=_DM, transport=_commit_then_raise,
        text="<@U0BOT> hello", event_id="Ev-dp-1",
    )
    assert result.handled is False       # not claimed as delivered
    assert posts == ["the universe answers"]  # posted ONCE — no second notice


def test_a_reply_record_failure_after_post_never_escapes(base, monkeypatch):
    """Once Slack accepted the reply, memory bookkeeping cannot fail delivery."""
    binding = _make_universe(base, "u-ingress-post-safe")
    _bind(base, "u-ingress-post-safe", binding)
    _grant_founder(monkeypatch)

    import tinyassets.conversation_store as cs

    def _boom(*_args, **_kwargs):
        raise RuntimeError("path coercion exploded")

    monkeypatch.setattr(cs, "record_turn", _boom)
    result, calls = _deliver(
        channel_id=_DM,
        text="<@U0BOT> hello",
        event_id="Ev-post-safe-1",
    )

    assert result.handled is True
    assert result.provider_receipt_ref == f"slack:{_DM}:1700000000.000200"
    assert calls["post"][-1]["body"] == "the universe answers"


def test_memory_load_never_raises_into_the_turn(base, monkeypatch):
    """Best-effort: if the memory load path blows up (vault error, store bug), the
    turn still answers — memory degrades to empty, never drops the reply.

    Mutation-check: remove the try/except around the memory block and this raises.
    """
    binding = _make_universe(base, "u-ingress-safe")
    _bind(base, "u-ingress-safe", binding)
    _grant_founder(monkeypatch)

    import tinyassets.conversation_store as cs

    def _boom(*a, **k):
        raise RuntimeError("vault down")

    monkeypatch.setattr(cs, "load_recent", _boom)

    result, calls = _deliver(channel_id=_DM, text="<@U0BOT> hi", event_id="Ev-safe-1")
    assert result.handled is True
    assert calls["post"][-1]["body"] == "the universe answers"
    assert calls["converse"][0]["conversation_history"] == []


def test_composite_transport_receipt_does_not_duplicate_the_reply(base, monkeypatch):
    """FIX2 (Codex 2026-08-10): the REAL Slack transport returns a COMPOSITE
    receipt ``slack:<channel>:<ts>``, but sync_tail dedups on the RAW ts from the
    live timeline. Storing the composite as ext_id meant the reply never matched
    on re-sync and was re-recorded as a duplicate every turn. The reply must be
    stored under its RAW ts and survive a re-sync without duplicating.

    Note: this uses a transport with the PROD receipt shape — the round-2 test
    double returned a raw ts, which is exactly why this bug slipped through.

    Mutation-check: drop the rsplit normalization in ``_record_universe`` (store
    the composite) and the re-sync below re-appends the reply — this goes red.
    """
    binding = _make_universe(base, "u-ingress-fix2")
    _bind(base, "u-ingress-fix2", binding)
    _grant_founder(monkeypatch)

    import tinyassets.conversation_store as cs
    import tinyassets.effectors.slack_agent_turn as sat
    from tinyassets.api.helpers import _universe_dir

    conv_dir = _universe_dir("u-ingress-fix2")
    session = f"slack:{_DM}"
    reply_ts = "1700000000.000200"

    def _composite_transport(destination, body, *, thread_ts=""):
        # Exactly what tinyassets/effectors/slack_transport.py returns.
        return _Receipt(f"slack:{_DM}:{reply_ts}")

    # Turn 1: the reply is recorded from the COMPOSITE receipt.
    _deliver(
        channel_id=_DM, transport=_composite_transport,
        text="<@U0BOT> hello", event_id="Ev-fix2-1",
    )
    ids = {ext for _sp, _tx, ext in cs._recent_identities(conv_dir, session, limit=50)}
    assert reply_ts in ids, "reply must be stored under its RAW ts"
    assert f"slack:{_DM}:{reply_ts}" not in ids, "composite must never become an ext_id"

    # Turn 2: the live timeline reports the reply at its RAW ts; sync_tail must
    # recognize it and NOT re-append.
    live = [
        {"speaker": "founder", "text": "hello", "ts": "1700000000.000100"},
        {"speaker": "universe", "text": "the universe answers", "ts": reply_ts},
    ]
    monkeypatch.setattr(sat, "load_thread_history", lambda **k: live)
    _deliver(
        channel_id=_DM, transport=_composite_transport,
        text="<@U0BOT> still there?", event_id="Ev-fix2-2",
    )
    replies = [
        m.text for m in cs.load_recent(conv_dir, session, limit=100)
        if m.text == "the universe answers"
    ]
    assert replies == ["the universe answers"], f"reply duplicated {len(replies)}x"


def test_a_non_founder_dm_gets_no_founder_history(base, monkeypatch):
    """FIX5 (Codex 2026-08-10): the guard is BOTH halves — 1:1 DM AND a founder
    grant. A DM sender the recognizer does NOT grant must get NO durable memory,
    or one visitor's DM could read the founder's history.

    Mutation-check: drop the ``grant is not None`` half of ``memory_on`` and the
    seeded history rides into the ungranted DM turn — this goes red.
    """
    binding = _make_universe(base, "u-ingress-nofdr")
    _bind(base, "u-ingress-nofdr", binding)
    # NOTE: deliberately do NOT grant founder — recognize returns None by default.

    import tinyassets.conversation_store as cs
    from tinyassets.api.helpers import _universe_dir

    conv_dir = _universe_dir("u-ingress-nofdr")
    # Seed the DM session so an empty history can ONLY be the guard, not emptiness.
    cs.record_turn(conv_dir, f"slack:{_DM}", "founder", "prior founder-only secret")

    _, calls = _deliver(channel_id=_DM, text="<@U0BOT> hi", event_id="Ev-nofdr-1")
    history = calls["converse"][0]["conversation_history"] or []
    assert history == [], "an ungranted DM must load no history"


def test_a_failure_notice_is_not_recorded_as_a_completed_universe_message(
    base, monkeypatch
):
    """Blocker H (fail-closed): a failure NOTICE is not a terminal provider
    result, so it must NEVER be recorded as a completed universe utterance. The
    founder HEARS it (it is posted), but the durable store must not gain a
    fabricated "the universe said X" row that would ride into the next turn's
    conversation history.

    Mutation-check: restore ``_record_universe(notice, receipt)`` in the failure
    path of ``deliver_app_event`` and this goes red.
    """
    binding = _make_universe(base, "u-ingress-hnotice")
    _bind(base, "u-ingress-hnotice", binding)
    _grant_founder(monkeypatch)

    import tinyassets.conversation_store as cs
    import tinyassets.effectors.slack_agent_turn as sat
    from tinyassets.api.helpers import _universe_dir
    from tinyassets.exceptions import ProviderIdleTimeoutError

    conv_dir = _universe_dir("u-ingress-hnotice")
    session = f"slack:{_DM}"
    monkeypatch.setattr(
        sat, "load_thread_history",
        lambda **_kwargs: [
            {"speaker": "founder", "text": "do the thing",
             "ts": "1700000000.000100"}
        ],
    )

    def _idle(*_a, **_k):
        # An idle-timeout turn: a real classified failure, not silence.
        raise ProviderIdleTimeoutError("idle watchdog fired")

    result, calls = _deliver(
        channel_id=_DM, converse=_idle,
        text="<@U0BOT> do the thing", event_id="Ev-hnotice-1",
    )
    assert result.handled is True
    # The notice was posted (the founder is not left in silence)...
    body = calls["post"][-1]["body"].lower()
    assert "progress" in body  # the honest idle-timeout wording

    # ...but the store recorded NO universe turn — only the founder's message.
    stored = cs.load_recent(conv_dir, session, limit=50)
    speakers = [m.speaker for m in stored]
    assert "universe" not in speakers, "a failure notice must not be a universe turn"
    assert "founder" in speakers, "the founder's own message is still recorded"


def test_an_empty_reply_notice_is_not_recorded_as_a_universe_message(
    base, monkeypatch
):
    """Same fail-closed rule for the empty-reply path (blocker H): an empty turn
    produced no terminal result, so its notice is posted but never stored as the
    universe's completed reply."""
    binding = _make_universe(base, "u-ingress-empty")
    _bind(base, "u-ingress-empty", binding)
    _grant_founder(monkeypatch)

    import tinyassets.conversation_store as cs
    import tinyassets.effectors.slack_agent_turn as sat
    from tinyassets.api.helpers import _universe_dir

    conv_dir = _universe_dir("u-ingress-empty")
    session = f"slack:{_DM}"
    monkeypatch.setattr(
        sat, "load_thread_history",
        lambda **_kwargs: [
            {"speaker": "founder", "text": "say something",
             "ts": "1700000000.000100"}
        ],
    )

    result, _ = _deliver(
        channel_id=_DM, converse=lambda *a, **k: "   ",
        text="<@U0BOT> say something", event_id="Ev-empty-1",
    )
    assert result.handled is True
    stored = cs.load_recent(conv_dir, session, limit=50)
    assert "universe" not in [m.speaker for m in stored]
