"""A request reaches its OWNER's devices, and nobody else's.

Driven through the real handlers and real stores: a request raised by the real
``request_from_user``, devices in the real registry, and -- for the transport
tests -- the real FCM transport built from a real (throwaway) service-account
key, with only the HTTP socket replaced. The fake is the network, never the
authority check, the composition or the idempotency.

The properties these exist to hold:

* a notification is routed by the OWNER of the universe holding the request,
  and by nothing a caller, a payload or the request's own content says;
* a handset that changes accounts stops receiving the old account's
  notifications;
* the identity line is the platform's and the body is the agent's, so no ask
  can be composed to look like it came from the platform or another person;
* nothing the owner typed into a request comes back out in a payload;
* one notification per request per device, and an unconfigured deployment says
  so instead of claiming a delivery.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tinyassets.api import visibility as vis
from tinyassets.daemon_server import (
    claim_founder_home,
    ensure_universe_registered,
    grant_universe_access,
    set_universe_display_name,
)
from tinyassets.notify import (
    OUTCOME_GONE,
    OUTCOME_NO_TRANSPORT,
    OUTCOME_SENT,
    Notification,
    TransportFailed,
    TransportGone,
)
from tinyassets.storage import owner_devices as devices

ALICE = "workos|alice-notify"
BOB = "workos|bob-notify"
A_UID = "u-alice-notify"
B_UID = "u-bob-notify"
A_NAME = "Alice's universe"


@pytest.fixture
def base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    monkeypatch.delenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", raising=False)
    for var in (
        "TINYASSETS_FCM_SERVICE_ACCOUNT_JSON",
        "TINYASSETS_WEBPUSH_VAPID_PRIVATE_KEY",
        "TINYASSETS_WEBPUSH_VAPID_SUBJECT",
    ):
        monkeypatch.delenv(var, raising=False)
    return root


def _home(base: Path, uid: str, owner: str, name: str = "") -> Path:
    udir = base / uid
    udir.mkdir(parents=True, exist_ok=True)
    (udir / "soul.md").write_text(f"# {uid}\n", encoding="utf-8")
    ensure_universe_registered(base, universe_id=uid, universe_path=udir)
    grant_universe_access(
        base, universe_id=uid, actor_id=owner, permission="admin", granted_by=owner,
    )
    claim_founder_home(base, owner, uid)
    vis.set_universe_visibility(uid, "private", source="default")
    if name:
        set_universe_display_name(base, universe_id=uid, display_name=name)
    return udir


class _Recorder:
    """A transport that records what it was handed. Never a network."""

    def __init__(self, raises: Exception | None = None) -> None:
        self.calls: list[tuple[dict, Notification]] = []
        self._raises = raises

    def __call__(self, device: dict, notification: Notification) -> str:
        self.calls.append((device, notification))
        if self._raises is not None:
            raise self._raises
        return OUTCOME_SENT


def _fake(raises: Exception | None = None) -> tuple[_Recorder, dict]:
    recorder = _Recorder(raises)
    return recorder, {"android": recorder, "web": recorder}


def _register(base: Path, owner: str, token: str, platform: str = "android") -> str:
    """Register one device. A web device needs a real subscription shape, so a
    bare label is turned into one keyed on itself."""
    if platform == "web" and isinstance(token, str):
        token = {
            "endpoint": f"https://push.example.com/{token}",
            "keys": {"p256dh": "k", "auth": "a"},
        }
    return devices.register_device(
        base, owner_user_id=owner, platform=platform, token=token,
    )["device_id"]


def _raise_request(base: Path, uid: str, owner: str, transports: dict, **overrides):
    """A request, then dispatch, as the seam does -- with the network replaced."""
    from tinyassets.auth.middleware import identity_context
    from tinyassets.auth.provider import Identity
    from tinyassets.owner_notifications import notify_request_raised

    document = {
        "kind": "TODO", "title": "Today", "body": "A few things.",
        "action": {"type": "answer"},
        "fields": [{"name": "note", "type": "text", "label": "Reply"}],
    }
    document.update(overrides)
    with identity_context(Identity(user_id=owner, username=owner)):
        from tinyassets.api.pending_requests import request_from_user

        row = request_from_user(universe_id=uid, payload=document)
        assert "error" not in row, row
        result = notify_request_raised(
            base, universe_id=uid, raised_by=owner, request=row,
            transports=transports,
        )
    return row, result


# --- the routing key ----------------------------------------------------------


def test_a_request_reaches_its_owners_devices(base):
    _home(base, A_UID, ALICE, A_NAME)
    device_id = _register(base, ALICE, "token-alice-phone")
    recorder, transports = _fake()

    row, result = _raise_request(base, A_UID, ALICE, transports)

    assert result["sent"] == 1
    [(device, notification)] = recorder.calls
    assert device["device_id"] == device_id
    assert notification.data["request_id"] == row["request_id"]
    assert notification.data["universe_id"] == A_UID


def test_another_users_devices_are_never_a_destination(base):
    """The one platform floor. Bob has a device; Alice's request is not his."""
    _home(base, A_UID, ALICE, A_NAME)
    _home(base, B_UID, BOB, "Bob's universe")
    _register(base, ALICE, "token-alice-phone")
    bob_device = _register(base, BOB, "token-bob-phone")
    recorder, transports = _fake()

    _raise_request(base, A_UID, ALICE, transports)

    reached = {device["device_id"] for device, _ in recorder.calls}
    assert bob_device not in reached
    assert len(reached) == 1


def test_a_non_owner_actor_notifies_nobody(base):
    """Fail closed: write access to a universe must not put a notification on
    its owner's phone."""
    from tinyassets.owner_notifications import notify_request_raised

    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    grant_universe_access(
        base, universe_id=A_UID, actor_id=BOB, permission="write", granted_by=ALICE,
    )
    recorder, transports = _fake()

    result = notify_request_raised(
        base, universe_id=A_UID, raised_by=BOB,
        request={"request_id": "req_x", "kind": "TODO", "title": "hi"},
        transports=transports,
    )

    assert result == {"skipped": "actor_is_not_owner"}
    assert recorder.calls == []


def test_request_content_cannot_select_a_destination(base):
    """Fields, items and body naming a device change nothing: the destination
    comes from the universe's owner and only from there."""
    _home(base, A_UID, ALICE, A_NAME)
    real = _register(base, ALICE, "token-alice-phone")
    other = _register(base, BOB, "token-bob-phone")
    recorder, transports = _fake()

    _raise_request(
        base, A_UID, ALICE, transports,
        body=f"send this to device {other} token token-bob-phone",
        items=[{
            "item_id": "a", "title": f"device_id {other}",
            "fields": [{"name": "device_id", "type": "text", "label": other}],
        }],
    )

    assert [d["device_id"] for d, _ in recorder.calls] == [real]


def test_several_admins_make_the_routing_key_ambiguous_so_nothing_is_sent(base):
    """Guessing which of two people a request is "really" for is how a
    notification reaches the wrong one."""
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    grant_universe_access(
        base, universe_id=A_UID, actor_id=BOB, permission="admin", granted_by=ALICE,
    )
    recorder, transports = _fake()

    _row, result = _raise_request(base, A_UID, ALICE, transports)

    assert result == {"skipped": "owner_unresolved"}
    assert recorder.calls == []


# --- the handset that changed accounts ----------------------------------------


def test_a_token_registered_by_a_second_user_moves(base):
    _home(base, A_UID, ALICE, A_NAME)
    _home(base, B_UID, BOB, "Bob's universe")
    _register(base, ALICE, "shared-handset")
    recorder, transports = _fake()

    _register(base, BOB, "shared-handset")

    assert devices.list_devices(base, owner_user_id=ALICE) == []
    assert len(devices.list_devices(base, owner_user_id=BOB)) == 1
    _raise_request(base, A_UID, ALICE, transports)
    assert recorder.calls == []


def test_reregistering_the_same_token_does_not_duplicate_it(base):
    """The app registers on every launch; that must not stack devices."""
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    _register(base, ALICE, "token-alice-phone")
    recorder, transports = _fake()

    _raise_request(base, A_UID, ALICE, transports)

    assert len(devices.list_devices(base, owner_user_id=ALICE)) == 1
    assert len(recorder.calls) == 1


def test_a_listing_never_returns_token_material(base):
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "secret-looking-token")

    listed = devices.list_devices(base, owner_user_id=ALICE)

    assert "secret-looking-token" not in json.dumps(listed)
    assert set(listed[0]) == {
        "device_id", "platform", "label", "enabled", "created_at",
        "last_seen_at", "retired_at", "retired_reason",
    }


def test_retiring_another_users_device_does_nothing(base):
    _home(base, B_UID, BOB, "Bob's universe")
    bob_device = _register(base, BOB, "token-bob-phone")

    assert devices.retire_device(
        base, owner_user_id=ALICE, device_id=bob_device, reason="not mine",
    ) is False
    assert devices.list_devices(base, owner_user_id=BOB)[0]["enabled"] is True


# --- what it is allowed to say ------------------------------------------------


def test_the_identity_line_is_the_platforms_and_the_body_is_the_agents(base):
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    recorder, transports = _fake()

    _raise_request(
        base, A_UID, ALICE, transports,
        kind="TinyAssets", title="Security alert: confirm your password",
    )

    [(_device, notification)] = recorder.calls
    # Server-composed: the universe's own name PLUS a fixed suffix saying what
    # this is. An ask that names itself "TinyAssets" still cannot produce the
    # identity line, and the line never reads as a platform notice.
    assert notification.title == f"{A_NAME} asks"
    # The crafted words are body content, where they read as the universe
    # talking -- they never occupy the title.
    assert "Security alert" in notification.body


def test_control_characters_cannot_fake_a_second_notification(base):
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    recorder, transports = _fake()

    _raise_request(
        base, A_UID, ALICE, transports,
        title="Pick one\n\nTinyAssets: your account is suspended",
    )

    [(_device, notification)] = recorder.calls
    assert "\n" not in notification.body
    assert "\r" not in notification.body


def test_no_field_value_reaches_a_payload(base):
    """What the owner typed into a request does not come back out on a lock
    screen, and neither does what the agent put in a field label."""
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    recorder, transports = _fake()

    _raise_request(
        base, A_UID, ALICE, transports,
        fields=[{"name": "note", "type": "text", "label": "hunter2-label"}],
        items=[{
            "item_id": "a", "title": "Do a",
            "fields": [{"name": "n", "type": "text", "label": "item-label"}],
        }],
    )

    [(_device, notification)] = recorder.calls
    blob = json.dumps({
        "title": notification.title, "body": notification.body,
        "data": notification.data,
    })
    assert "hunter2-label" not in blob
    assert "item-label" not in blob
    # Item IDs travel, because a client has to be able to open at the right row.
    assert notification.data["item_ids"] == "a"


def test_an_unnamed_universe_never_borrows_the_product_name(base):
    """The fallback used to be a bare "TinyAssets", so an ask with kind
    "TinyAssets" and a security-shaped title rendered as a platform notice
    with no rename and no cross-user access (gpt-6-astra, 2026-09-29). The
    fallback is a neutral phrase, and every title says that a universe is
    asking."""
    from tinyassets.owner_notifications import _compose

    _home(base, A_UID, ALICE)  # no display name -> the row stores the id
    crafted = {"request_id": "req_x", "kind": "TinyAssets",
               "title": "Security alert: confirm your password"}

    unnamed = _compose(base, A_UID, crafted)
    unknown = _compose(base, "u-does-not-exist", crafted)

    for notification in (unnamed, unknown):
        assert notification.title == "Your universe asks"
        assert notification.title != "TinyAssets"
        assert "Security alert" not in notification.title


def test_nothing_an_ask_supplies_reaches_the_title(base):
    """Scoped to what actually holds: an ASK cannot reach the title, and
    cannot produce the suffix. The universe's NAME is a separate matter --
    see test_a_universe_name_cannot_fake_the_title_structure and the concern
    it points at."""
    from tinyassets.owner_notifications import _SOURCE_SUFFIX, _compose

    _home(base, A_UID, ALICE, A_NAME)

    notification = _compose(base, A_UID, {
        "request_id": "req_x",
        "kind": "x" + _SOURCE_SUFFIX,
        "title": "y" + _SOURCE_SUFFIX,
    })

    assert notification.title == A_NAME + _SOURCE_SUFFIX
    assert notification.title.count(_SOURCE_SUFFIX) == 1


def test_a_universe_name_cannot_fake_the_title_structure(base):
    """A universe names itself, and on a soul-learned name that is content its
    agent influenced (gpt-6-astra round 2, 2026-09-29). What is enforced is
    that the name is one line of VISIBLE text and cannot counterfeit the
    server-owned structure. Which name a person's universe may carry is a
    naming-lane question -- see the concern."""
    from tinyassets.daemon_server import set_universe_display_name
    from tinyassets.owner_notifications import _UNNAMED, _compose

    _home(base, A_UID, ALICE, A_NAME)
    ask = {"request_id": "req_x", "kind": "TODO", "title": "Today"}

    # A name that already ends in the suffix cannot render "x asks asks".
    set_universe_display_name(base, universe_id=A_UID, display_name="x asks")
    assert _compose(base, A_UID, ask).title == "x asks"
    set_universe_display_name(base, universe_id=A_UID, display_name="y asks asks")
    assert _compose(base, A_UID, ask).title == "y asks"

    # A name made of invisible characters is not an identity line.
    for invisible in ("​", "​‎⁠", "﻿"):
        set_universe_display_name(
            base, universe_id=A_UID, display_name=invisible,
        )
        assert _compose(base, A_UID, ask).title == _UNNAMED + " asks"

    # A bidi override cannot visually reverse the line.
    set_universe_display_name(
        base, universe_id=A_UID, display_name="safe‮reversed",
    )
    assert "‮" not in _compose(base, A_UID, ask).title


def test_a_retirement_reason_is_a_code_never_transport_text(base):
    """`retired_reason` is the one string on this table a transport supplies,
    and it comes back out of `list_devices`. Injecting a bearer token through
    TransportGone returned that text verbatim (gpt-6-astra round 2,
    2026-09-29)."""
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    leaky = TransportGone("Bearer ya29.SUPER-SECRET-TOKEN is dead")
    _recorder, transports = _fake(raises=leaky)

    _raise_request(base, A_UID, ALICE, transports)

    [listed] = devices.list_devices(base, owner_user_id=ALICE)
    assert listed["retired_reason"] == "unknown"
    assert "SUPER-SECRET-TOKEN" not in json.dumps(listed)


def test_a_known_gone_code_is_still_recorded(base):
    """The allowlist must not erase the diagnostic it exists to protect."""
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    _recorder, transports = _fake(raises=TransportGone("UNREGISTERED"))

    _raise_request(base, A_UID, ALICE, transports)

    [listed] = devices.list_devices(base, owner_user_id=ALICE)
    assert listed["retired_reason"] == "UNREGISTERED"


def test_a_notification_of_accepted_input_always_fits_one_record(base):
    """A 55-emoji universe name, 24-emoji kind, 120-emoji title and twenty
    64-character item ids is accepted input, and composed to 4164 bytes
    against a 4079-byte record -- so the transport refused it and the owner
    got nothing (gpt-6-astra round 2, 2026-09-29). Composition fits the
    record now, so accepted input always delivers."""
    from tinyassets.daemon_server import set_universe_display_name
    from tinyassets.notify.webpush import payload_bytes, record_budget
    from tinyassets.owner_notifications import _compose

    _home(base, A_UID, ALICE, A_NAME)
    set_universe_display_name(
        base, universe_id=A_UID, display_name="\U0001f600" * 55,
    )
    request = {
        "request_id": "req_" + "a" * 24,
        "kind": "\U0001f600" * 24,
        "title": "\U0001f600" * 120,
        "items": [{"item_id": f"{n:02d}" + "a" * 62, "title": "Task"}
                  for n in range(20)],
    }

    notification = _compose(base, A_UID, request)

    assert len(payload_bytes(notification)) <= record_budget()
    # It is still a usable notification: the identity line and the ids survive.
    assert notification.title.endswith(" asks")
    assert notification.data["request_id"] == request["request_id"]


def test_that_oversized_notification_actually_sends(base):
    """The end of the same finding: not merely "fits", but delivers."""
    from tinyassets.daemon_server import set_universe_display_name

    _home(base, A_UID, ALICE, A_NAME)
    set_universe_display_name(
        base, universe_id=A_UID, display_name="\U0001f600" * 55,
    )
    _register(base, ALICE, "laptop", platform="web")
    recorder, transports = _fake()

    _row, result = _raise_request(
        base, A_UID, ALICE, transports,
        kind="\U0001f600" * 24, title="\U0001f600" * 120,
        items=[{"item_id": f"{n:02d}" + "a" * 62, "title": "Task"}
               for n in range(20)],
        fields=[],
    )

    assert result["sent"] == 1
    assert len(recorder.calls) == 1


# --- cost, without a meter ----------------------------------------------------


def test_a_deduplicated_ask_does_not_notify_again(base):
    """Only a genuinely new row is something to be told about."""
    from tinyassets.auth.middleware import identity_context
    from tinyassets.auth.provider import Identity

    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    recorder, transports = _fake()
    import tinyassets.owner_notifications as notifications

    sent: list[dict] = []

    def _capture(base_path, **kw):
        sent.append(kw)
        return notifications.notify_request_raised(
            base_path, transports=transports, **kw,
        )

    document = {
        "kind": "TODO", "title": "Today", "action": {"type": "answer"},
        "fields": [{"name": "note", "type": "text", "label": "Reply"}],
    }
    with identity_context(Identity(user_id=ALICE, username=ALICE)):
        from tinyassets.api import pending_requests as api

        original = api._notify_owner

        def _patched(uid, row):
            _capture(base, universe_id=uid, raised_by=ALICE, request=row)

        api._notify_owner = _patched
        try:
            first = api.request_from_user(universe_id=A_UID, payload=dict(document))
            second = api.request_from_user(universe_id=A_UID, payload=dict(document))
        finally:
            api._notify_owner = original

    assert first["request_id"] == second["request_id"]
    assert len(sent) == 1
    assert len(recorder.calls) == 1


def test_a_retry_notifies_once(base):
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    recorder, transports = _fake()
    from tinyassets.owner_notifications import notify_request_raised

    request = {"request_id": "req_retry", "kind": "TODO", "title": "Today",
               "dedupe_key": '["TODO","Today"]'}
    first = notify_request_raised(
        base, universe_id=A_UID, raised_by=ALICE, request=request,
        transports=transports,
    )
    second = notify_request_raised(
        base, universe_id=A_UID, raised_by=ALICE, request=request,
        transports=transports,
    )

    assert first["sent"] == 1
    assert second["sent"] == 0
    # The delivery key catches it first: this exact notification was already
    # claimed. `replay` is decided BEFORE the latch is touched, so a refusal
    # leaves no state -- that ordering is what a phantom latch came from.
    assert list(second["outcomes"].values()) == ["replay"]
    assert len(recorder.calls) == 1


def test_notifications_off_sends_nothing(base):
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    devices.set_notifications_enabled(base, owner_user_id=ALICE, enabled=False)
    recorder, transports = _fake()

    row, result = _raise_request(base, A_UID, ALICE, transports)

    assert result["devices"] == 0
    assert recorder.calls == []
    # And the request is still there to be answered.
    from tinyassets.storage.pending_requests import get_request

    assert get_request(base / A_UID, row["request_id"])["status"] == "pending"


def test_one_owners_switch_does_not_silence_another(base):
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    devices.set_notifications_enabled(base, owner_user_id=BOB, enabled=False)
    recorder, transports = _fake()

    _raise_request(base, A_UID, ALICE, transports)

    assert len(recorder.calls) == 1
    assert devices.notifications_enabled(base, owner_user_id=ALICE) is True


def test_one_request_notifies_a_destination_once_whatever_happens_to_it(base):
    """The ledger's primary key is the whole dedupe rule. Re-dispatching the
    same request after it is answered, withdrawn or re-read still delivers
    nothing further to a destination that already got it."""
    from tinyassets.auth.middleware import identity_context
    from tinyassets.auth.provider import Identity
    from tinyassets.owner_notifications import notify_request_raised
    from tinyassets.storage.pending_requests import withdraw_request

    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "phone")
    recorder, transports = _fake()
    row, _ = _raise_request(base, A_UID, ALICE, transports)
    assert len(recorder.calls) == 1

    with identity_context(Identity(user_id=ALICE, username=ALICE)):
        withdraw_request(base / A_UID, row["request_id"], reason="never mind")
    for _ in range(5):
        again = notify_request_raised(
            base, universe_id=A_UID, raised_by=ALICE,
            request={"request_id": row["request_id"], "kind": "TODO",
                     "title": "Today"},
            transports=transports,
        )
        assert list(again["outcomes"].values()) == ["replay"]

    assert len(recorder.calls) == 1


def test_a_new_request_does_notify_and_that_is_the_accepted_cost(base):
    """Stated, not hidden: there is NO notification-specific bound, so an agent
    that raises genuinely new requests in a loop does notify per request. That
    is bounded where everything else is -- the run holds a concurrent seat
    while it works, and MAX_PENDING caps the unanswered pile -- and adding a
    second mechanism here would be a rate limiter, which account limits are
    explicitly not (founder, 2026-09-30)."""
    from tinyassets.storage.pending_requests import MAX_PENDING, list_pending

    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "phone")
    recorder, transports = _fake()

    for n in range(6):
        _raise_request(base, A_UID, ALICE, transports, title=f"Thing {n}")

    assert len(recorder.calls) == 6
    # And the pile itself is capped, so this cannot grow without limit.
    assert len(list_pending(base / A_UID, limit=MAX_PENDING * 2)) == 6
    assert MAX_PENDING == 50


# --- failure ------------------------------------------------------------------


def test_no_transport_says_so_and_never_claims_a_delivery(base):
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")

    row, result = _raise_request(base, A_UID, ALICE, {})

    assert result["sent"] == 0
    assert set(result["outcomes"].values()) == {OUTCOME_NO_TRANSPORT}
    # Nothing was claimed, so a later configured deployment still delivers it.
    assert devices.deliveries_for(base, request_id=row["request_id"]) == []
    from tinyassets.storage.pending_requests import get_request

    assert get_request(base / A_UID, row["request_id"])["status"] == "pending"


def test_a_transport_exception_carrying_a_secret_leaks_nothing(base):
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    leaky = RuntimeError("Bearer ya29.SUPER-SECRET-TOKEN failed")
    _recorder, transports = _fake(raises=leaky)

    row, result = _raise_request(base, A_UID, ALICE, transports)

    ledger = devices.deliveries_for(base, request_id=row["request_id"])
    blob = json.dumps([ledger, result])
    assert "SUPER-SECRET-TOKEN" not in blob
    assert [entry["outcome"] for entry in ledger] == ["unavailable"]


def test_a_bounded_failure_records_only_its_class(base):
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    _recorder, transports = _fake(raises=TransportFailed("refused"))

    row, _result = _raise_request(base, A_UID, ALICE, transports)

    ledger = devices.deliveries_for(base, request_id=row["request_id"])
    assert [entry["outcome"] for entry in ledger] == ["refused"]


def test_a_gone_device_is_retired_and_not_retried(base):
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    recorder, transports = _fake(raises=TransportGone("UNREGISTERED"))

    row, _result = _raise_request(base, A_UID, ALICE, transports)

    [listed] = devices.list_devices(base, owner_user_id=ALICE)
    assert listed["enabled"] is False
    assert listed["retired_reason"] == "UNREGISTERED"
    assert devices.delivery_targets(base, owner_user_id=ALICE) == []
    assert [e["outcome"] for e in devices.deliveries_for(
        base, request_id=row["request_id"],
    )] == [OUTCOME_GONE]
    # And it is not retried: a working transport now reaches nothing.
    recorder._raises = None
    _raise_request(base, A_UID, ALICE, transports)
    assert len(recorder.calls) == 1


def test_a_transport_that_violates_its_contract_never_breaks_the_request(base):
    """Push is additive to a durable request: the ask survives a transport
    raising something outside the two classes it is allowed to raise."""
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    _recorder, transports = _fake(raises=TypeError("not part of the contract"))

    row, result = _raise_request(base, A_UID, ALICE, transports)

    assert result["sent"] == 0
    assert list(result["outcomes"].values()) == ["unavailable"]
    from tinyassets.storage.pending_requests import get_request

    assert get_request(base / A_UID, row["request_id"])["status"] == "pending"


def test_an_interrupt_is_not_swallowed(base):
    """A cancelled process must still cancel. ``except Exception`` is the right
    width here, and this is what keeps it from widening to BaseException."""
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    _recorder, transports = _fake(raises=KeyboardInterrupt())
    from tinyassets.owner_notifications import notify_request_raised

    with pytest.raises(KeyboardInterrupt):
        notify_request_raised(
            base, universe_id=A_UID, raised_by=ALICE,
            request={"request_id": "req_int", "kind": "TODO", "title": "x"},
            transports=transports,
        )


# --- answering here clears there ----------------------------------------------


def test_answering_clears_the_owners_other_devices(base):
    from tinyassets.auth.middleware import identity_context
    from tinyassets.auth.provider import Identity

    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "phone")
    _register(base, ALICE, "laptop", platform="web")
    recorder, transports = _fake()
    row, _ = _raise_request(base, A_UID, ALICE, transports)
    recorder.calls.clear()

    from tinyassets.owner_notifications import clear_request

    with identity_context(Identity(user_id=ALICE, username=ALICE)):
        cleared = clear_request(
            base, universe_id=A_UID, answered_by=ALICE,
            request_id=row["request_id"], transports=transports,
        )

    assert cleared["sent"] == 2
    for _device, notification in recorder.calls:
        assert notification.silent is True
        assert notification.title == ""
        assert notification.body == ""
        assert notification.data == {
            "kind": "clear", "request_id": row["request_id"],
            "universe_id": A_UID,
        }


def test_the_device_that_answered_is_not_cleared_again(base):
    _home(base, A_UID, ALICE, A_NAME)
    answering = _register(base, ALICE, "phone")
    _register(base, ALICE, "laptop", platform="web")
    recorder, transports = _fake()
    row, _ = _raise_request(base, A_UID, ALICE, transports)
    recorder.calls.clear()
    from tinyassets.owner_notifications import clear_request

    clear_request(
        base, universe_id=A_UID, answered_by=ALICE, request_id=row["request_id"],
        skip_device_id=answering, transports=transports,
    )

    assert [d["device_id"] for d, _ in recorder.calls] != [answering]
    assert len(recorder.calls) == 1


def test_a_device_that_never_got_the_alert_is_not_woken_to_clear_it(base):
    """A clear is for taking a notification down. A device with nothing up has
    nothing to take down, so waking it is pure cost."""
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "phone")
    recorder, transports = _fake()
    from tinyassets.owner_notifications import clear_request

    result = clear_request(
        base, universe_id=A_UID, answered_by=ALICE, request_id="req_never_sent",
        transports=transports,
    )

    assert result["skipped"] == "no_alert_outstanding"
    assert recorder.calls == []


def test_a_clear_goes_only_to_devices_the_notification_reached(base):
    """The clear reads the delivery ledger, so it wakes exactly the devices
    that received the notification. A device registered afterwards received
    nothing and has nothing to take down."""
    _home(base, A_UID, ALICE, A_NAME)
    holder = _register(base, ALICE, "phone")
    recorder, transports = _fake()
    row, _ = _raise_request(base, A_UID, ALICE, transports)
    assert devices.delivered_devices(
        base, owner_user_id=ALICE, request_id=row["request_id"],
    ) == [holder]
    # A second device arrives after the notification was already delivered.
    later = _register(base, ALICE, "laptop", platform="web")
    recorder.calls.clear()
    from tinyassets.owner_notifications import clear_request

    clear_request(
        base, universe_id=A_UID, answered_by=ALICE,
        request_id=row["request_id"], transports=transports,
    )

    assert [d["device_id"] for d, _ in recorder.calls] == [holder]
    assert later not in [d["device_id"] for d, _ in recorder.calls]


def test_every_device_the_owner_had_gets_the_notification(base):
    """Dedupe is per destination, so it never means only one of the owner's
    devices is told."""
    _home(base, A_UID, ALICE, A_NAME)
    phone = _register(base, ALICE, "phone")
    laptop = _register(base, ALICE, "laptop", platform="web")
    recorder, transports = _fake()

    _raise_request(base, A_UID, ALICE, transports)

    assert sorted(d["device_id"] for d, _ in recorder.calls) == sorted(
        [phone, laptop]
    )



def test_another_user_cannot_clear_this_owners_notifications(base):
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "phone")
    recorder, transports = _fake()
    from tinyassets.owner_notifications import clear_request

    result = clear_request(
        base, universe_id=A_UID, answered_by=BOB, request_id="req_x",
        transports=transports,
    )

    assert result == {"skipped": "actor_is_not_owner"}
    assert recorder.calls == []


def test_the_resolution_seam_clears_from_every_surface(base):
    """`resolve_request` is where every surface answers, so the clear rides it
    rather than being repeated per call site."""
    from tinyassets.auth.middleware import identity_context
    from tinyassets.auth.provider import Identity
    from tinyassets.storage.pending_requests import resolve_request

    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "phone")
    recorder, transports = _fake()
    row, _ = _raise_request(base, A_UID, ALICE, transports)
    recorder.calls.clear()
    # Substitute the transport LOOKUP -- the network -- and nothing else, so
    # the owner check, the composition and the idempotency on this path are
    # the real ones. Patching `clear_request` itself would have proved only
    # that the test's own stand-in was called.
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "tinyassets.owner_notifications.resolve_transports", lambda: transports,
    )
    try:
        with identity_context(Identity(user_id=ALICE, username=ALICE)):
            assert resolve_request(
                base / A_UID, row["request_id"], status="answered",
                answer={"note": "done"},
            )
    finally:
        monkeypatch.undo()

    [(device, notification)] = recorder.calls
    assert device["device_id"] == devices.list_devices(
        base, owner_user_id=ALICE,
    )[0]["device_id"]
    assert notification.silent is True
    assert notification.data == {
        "kind": "clear", "request_id": row["request_id"], "universe_id": A_UID,
    }


def test_a_background_resolver_with_nobody_bound_clears_nothing(base):
    """Nobody answered on a device, so there is nothing to take off one."""
    from tinyassets.storage.pending_requests import resolve_request

    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "phone")
    recorder, transports = _fake()
    row, _ = _raise_request(base, A_UID, ALICE, transports)
    recorder.calls.clear()

    assert resolve_request(base / A_UID, row["request_id"], status="dismissed")

    assert recorder.calls == []


# --- account deletion ---------------------------------------------------------


def test_deleting_an_owner_takes_their_devices_with_them(base):
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "phone")
    devices.set_notifications_enabled(base, owner_user_id=ALICE, enabled=False)

    assert devices.purge_owner(base, owner_user_id=ALICE) == 1

    assert devices.list_devices(base, owner_user_id=ALICE) == []
    assert devices.notifications_enabled(base, owner_user_id=ALICE) is True


def test_account_deletion_finds_every_notification_table_from_the_schema(base):
    """Deletion derives its sweep from the schema, so a table whose person
    column is not one of `PRINCIPAL_KEYS` is simply never found -- and these
    rows would outlive the person they are about. This is what pins the column
    names to the ones the sweep looks for."""
    import sqlite3

    from tinyassets.account_deletion import deletion_plan
    from tinyassets.storage.owner_devices import owner_devices_db_path

    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "phone")
    recorder, transports = _fake()
    _raise_request(base, A_UID, ALICE, transports)
    assert recorder.calls  # a delivery row exists to be found

    conn = sqlite3.connect(owner_devices_db_path(base))
    try:
        plan = deletion_plan(conn, principal=ALICE, home=A_UID)
    finally:
        conn.close()

    assert plan["owner_devices"] == [("owner_user_id", "principal")]
    assert plan["owner_notify_settings"] == [("owner_user_id", "principal")]
    assert plan["request_notifications"] == [("owner_user_id", "principal")]


def test_the_devices_store_is_swept_by_the_real_deletion_run(base):
    """Not just planned -- actually emptied, through the real root-store sweep."""
    import sqlite3

    from tinyassets.account_deletion import _delete_satellite_rows, _root_databases
    from tinyassets.storage.owner_devices import owner_devices_db_path

    _home(base, A_UID, ALICE, A_NAME)
    _home(base, B_UID, BOB, "Bob's universe")
    _register(base, ALICE, "alice-phone")
    _register(base, BOB, "bob-phone")

    # Discovery first: the sweep only reaches stores the directory registry
    # finds, and this one's name starts with a dot.
    assert owner_devices_db_path(base) in _root_databases(base)

    _delete_satellite_rows(
        owner_devices_db_path(base), principal=ALICE, home=A_UID,
        counts={}, label="owner_devices",
    )

    conn = sqlite3.connect(owner_devices_db_path(base))
    try:
        owners = {r[0] for r in conn.execute(
            "SELECT owner_user_id FROM owner_devices"
        )}
    finally:
        conn.close()
    assert owners == {BOB}


# --- registration arguments ---------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"owner_user_id": "", "platform": "android", "token": "t"}, "owner_user_id"),
        ({"owner_user_id": ALICE, "platform": "ios", "token": "t"}, "platform"),
        ({"owner_user_id": ALICE, "platform": "android", "token": ""}, "token"),
        ({"owner_user_id": ALICE, "platform": "android", "token": 7}, "token"),
        ({"owner_user_id": ALICE, "platform": "android",
          "token": "x" * (devices.MAX_TOKEN_CHARS + 1)}, "longer"),
    ],
)
def test_registration_refuses_a_bad_argument(base, kwargs, match):
    with pytest.raises(ValueError, match=match):
        devices.register_device(base, **kwargs)


def test_a_web_subscription_is_keyed_on_its_canonical_form(base):
    """Key order in the browser's JSON must not create a second device."""
    subscription = {
        "endpoint": "https://push.example.com/abc",
        "keys": {"p256dh": "k", "auth": "a"},
    }
    reordered = {
        "keys": {"auth": "a", "p256dh": "k"},
        "endpoint": "https://push.example.com/abc",
    }
    devices.register_device(
        base, owner_user_id=ALICE, platform="web", token=subscription,
    )
    devices.register_device(
        base, owner_user_id=ALICE, platform="web", token=reordered,
    )

    assert len(devices.list_devices(base, owner_user_id=ALICE)) == 1


_SUBSCRIPTION_ALIASES = [
    # Metadata the browser attaches and the transport never reads.
    {"endpoint": "https://push.example.com/abc",
     "keys": {"p256dh": "k", "auth": "a"}, "expirationTime": None},
    # A vendor extra.
    {"endpoint": "https://push.example.com/abc",
     "keys": {"p256dh": "k", "auth": "a"}, "vendorHint": "x"},
    # Whitespace in the surrounding JSON string.
    '{"endpoint": "https://push.example.com/abc",\n'
    ' "keys": {"p256dh": "k", "auth": "a"}}',
    # Rotated keys, same endpoint: the same browser re-subscribing.
    {"endpoint": "https://push.example.com/abc",
     "keys": {"p256dh": "k2", "auth": "a2"}},
]


@pytest.mark.parametrize("alias", _SUBSCRIPTION_ALIASES)
def test_a_web_subscription_alias_cannot_retain_the_previous_owner(base, alias):
    """Hashing the whole document let two representations of ONE destination
    each keep a live row, so the previous owner's private notifications still
    reached a browser that had changed accounts (gpt-6-astra, 2026-09-29).
    Destination identity is the endpoint -- exactly what the transport
    addresses."""
    from tinyassets.notify.webpush import _subscription

    canonical = {
        "endpoint": "https://push.example.com/abc",
        "keys": {"p256dh": "k", "auth": "a"},
    }
    devices.register_device(
        base, owner_user_id=ALICE, platform="web", token=canonical,
    )
    if isinstance(alias, str):
        import json as _json

        assert _subscription({"token": alias})["endpoint"] == canonical["endpoint"]
        _json.loads(alias)  # the alias really is the same subscription

    devices.register_device(
        base, owner_user_id=BOB, platform="web", token=alias,
    )

    assert devices.list_devices(base, owner_user_id=ALICE) == []
    assert len(devices.list_devices(base, owner_user_id=BOB)) == 1


def test_stored_web_subscriptions_are_narrowed_to_what_the_transport_reads(base):
    """Extra fields are dropped rather than stored, so there is nothing left
    for a later alias to differ by."""
    import json as _json

    devices.register_device(
        base, owner_user_id=ALICE, platform="web",
        token={"endpoint": "https://push.example.com/abc",
               "keys": {"p256dh": "k", "auth": "a", "extra": "z"},
               "expirationTime": None, "vendorHint": "x"},
    )

    [target] = devices.delivery_targets(base, owner_user_id=ALICE)
    stored = _json.loads(target["token"])
    assert stored == {
        "endpoint": "https://push.example.com/abc",
        "keys": {"p256dh": "k", "auth": "a"},
    }


_URL_ALIASES = [
    # A fragment never leaves the client: urllib sends host + selector only.
    "https://push.example.com/abc#bob",
    "https://push.example.com/abc#",
    # Host case is not significant.
    "https://PUSH.EXAMPLE.COM/abc",
    "https://Push.Example.Com/abc",
    # The default https port is the same port.
    "https://push.example.com:443/abc",
]


@pytest.mark.parametrize("alias", _URL_ALIASES)
def test_a_url_alias_of_one_endpoint_cannot_retain_the_previous_owner(base, alias):
    """These all address the same host and selector on the wire, so they are
    one destination. Hashing the URL verbatim let each owner keep a live row
    (gpt-6-astra round 2, 2026-09-29)."""
    import urllib.request

    canonical = "https://push.example.com/abc"
    keys = {"p256dh": "k", "auth": "a"}
    # What the transport would actually address, for both.
    for url in (canonical, alias):
        request = urllib.request.Request(url)
        assert request.host.lower().removesuffix(":443") == "push.example.com"
        assert request.selector.split("#")[0] == "/abc"
    devices.register_device(
        base, owner_user_id=ALICE, platform="web",
        token={"endpoint": canonical, "keys": keys},
    )

    devices.register_device(
        base, owner_user_id=BOB, platform="web",
        token={"endpoint": alias, "keys": keys},
    )

    assert devices.list_devices(base, owner_user_id=ALICE) == []
    assert len(devices.list_devices(base, owner_user_id=BOB)) == 1


def test_a_genuinely_different_path_is_a_different_destination(base):
    """The canonicalisation is narrow on purpose: merging two real
    destinations would silently drop someone's device."""
    keys = {"p256dh": "k", "auth": "a"}
    for path in ("/abc", "/ABC", "/abc/", "/abc?x=1"):
        devices.register_device(
            base, owner_user_id=ALICE, platform="web",
            token={"endpoint": f"https://push.example.com{path}", "keys": keys},
        )

    assert len(devices.list_devices(base, owner_user_id=ALICE)) == 4


def test_an_android_token_cannot_delete_a_web_device_that_spells_the_same(base):
    """One string, two protocols, two destinations. Sharing the digest
    namespace let an FCM token whose characters equalled a web endpoint delete
    that web device and its latch (gpt-6-astra round 2, 2026-09-29)."""
    endpoint = "https://push.example.com/abc"
    _home(base, A_UID, ALICE, A_NAME)
    web = devices.register_device(
        base, owner_user_id=ALICE, platform="web",
        token={"endpoint": endpoint, "keys": {"p256dh": "k", "auth": "a"}},
    )["device_id"]

    devices.register_device(
        base, owner_user_id=BOB, platform="android", token=endpoint,
    )

    assert [d["device_id"] for d in devices.list_devices(
        base, owner_user_id=ALICE,
    )] == [web]
    assert len(devices.list_devices(base, owner_user_id=BOB)) == 1


@pytest.mark.parametrize("bad", [
    {"keys": {"p256dh": "k", "auth": "a"}},
    {"endpoint": "http://push.example.com/abc", "keys": {"p256dh": "k", "auth": "a"}},
    {"endpoint": "https://push.example.com/abc"},
    {"endpoint": "https://push.example.com/abc", "keys": {"p256dh": "k"}},
    {"endpoint": "https://push.example.com/abc", "keys": "nope"},
])
def test_registration_refuses_a_subscription_it_could_not_address(base, bad):
    with pytest.raises(ValueError):
        devices.register_device(
            base, owner_user_id=ALICE, platform="web", token=bad,
        )


# --- the destination is re-verified at claim time -----------------------------


def test_a_handset_reassigned_mid_dispatch_does_not_get_the_old_owners_alert(base):
    """Dispatch used to snapshot every destination and then send to the cached
    tokens, so a registration that moved a handset to another account during
    the send still received the previous owner's private title (gpt-6-astra,
    2026-09-29). The token now comes from the claim, in the same transaction
    that verifies ownership."""
    _home(base, A_UID, ALICE, A_NAME)
    _home(base, B_UID, BOB, "Bob's universe")
    _register(base, ALICE, "first-phone")
    _register(base, ALICE, "shared-phone")
    seen: list[dict] = []

    def _reassigning(device, notification):
        seen.append({"token": device["token"], "title": notification.title})
        if len(seen) == 1:
            # The interleaving: while the first send is in flight, the shared
            # handset is registered by Bob.
            devices.register_device(
                base, owner_user_id=BOB, platform="android", token="shared-phone",
            )
        return OUTCOME_SENT

    _raise_request(base, A_UID, ALICE, {"android": _reassigning})

    assert "shared-phone" not in [entry["token"] for entry in seen]
    assert len(devices.list_devices(base, owner_user_id=BOB)) == 1


def test_the_token_sent_with_is_the_one_verified_at_claim_time(base):
    """A re-subscription rotates the keys on the same endpoint, so the same
    device's token CHANGES in place. Sending the token read before the loop
    would use a stale one; the claim hands back the current row's."""
    endpoint = "https://push.example.com/alice-laptop"
    _home(base, A_UID, ALICE, A_NAME)
    # Order matters: devices are dispatched to oldest first, so the phone has
    # to be sent to BEFORE the laptop's subscription rotates.
    _register(base, ALICE, "first-phone")
    devices.register_device(
        base, owner_user_id=ALICE, platform="web",
        token={"endpoint": endpoint, "keys": {"p256dh": "old", "auth": "old"}},
    )
    seen: list[str] = []

    def _rotating(device, notification):
        seen.append(device["token"])
        if len(seen) == 1:
            # Between the snapshot and the second send, the browser
            # re-subscribes: same endpoint, new keys, same device row.
            devices.register_device(
                base, owner_user_id=ALICE, platform="web",
                token={"endpoint": endpoint,
                       "keys": {"p256dh": "new", "auth": "new"}},
            )
        return OUTCOME_SENT

    _raise_request(base, A_UID, ALICE, {"android": _rotating, "web": _rotating})

    web_tokens = [t for t in seen if endpoint in t]
    assert web_tokens, seen
    assert '"p256dh":"new"' in web_tokens[0]
    assert "old" not in web_tokens[0]


def test_relaunching_the_app_keeps_the_devices_identity(base):
    """The app registers on every launch. A new device_id each time would churn
    ids and re-notify for requests already delivered, because the delivery
    ledger is keyed on the device."""
    _home(base, A_UID, ALICE, A_NAME)
    first = _register(base, ALICE, "phone")
    recorder, transports = _fake()
    row, _ = _raise_request(base, A_UID, ALICE, transports)

    again = _register(base, ALICE, "phone")
    recorder.calls.clear()
    from tinyassets.owner_notifications import notify_request_raised

    repeat = notify_request_raised(
        base, universe_id=A_UID, raised_by=ALICE,
        request={"request_id": row["request_id"], "kind": "TODO", "title": "x"},
        transports=transports,
    )

    assert again == first
    assert list(repeat["outcomes"].values()) == ["replay"]
    assert recorder.calls == []


def test_a_device_retired_mid_dispatch_is_not_sent_to(base):
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "first-phone")
    second = _register(base, ALICE, "second-phone")
    seen: list[str] = []

    def _retiring(device, notification):
        seen.append(device["token"])
        if len(seen) == 1:
            devices.retire_device(
                base, owner_user_id=ALICE, device_id=second, reason="user",
            )
        return OUTCOME_SENT

    _row, result = _raise_request(base, A_UID, ALICE, {"android": _retiring})

    assert seen == ["first-phone"]
    assert result["outcomes"][second] == "moved"


# --- one outstanding alert per device -----------------------------------------




def test_a_fifty_item_note_costs_two_pushes_not_fifty_one(base):
    """Answering each item used to push a silent clear per item: one visible
    alert plus 49 item clears plus a final clear (gpt-6-astra, 2026-09-29). A
    notification is per REQUEST, so only the close clears it."""
    from tinyassets.auth.middleware import identity_context
    from tinyassets.auth.provider import Identity

    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "phone")
    recorder, transports = _fake()
    item_ids = [f"i{n}" for n in range(50)]
    import tinyassets.owner_notifications as notifications

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(notifications, "resolve_transports", lambda: transports)
    try:
        with identity_context(Identity(user_id=ALICE, username=ALICE)):
            from tinyassets.api.pending_requests import (
                answer_request,
                request_from_user,
            )

            row = request_from_user(universe_id=A_UID, payload={
                "kind": "TODO", "title": "Today", "action": {"type": "answer"},
                "fields": [],
                "items": [
                    {"item_id": i, "title": f"Do {i}",
                     "fields": [{"name": "note", "type": "text", "label": "Reply"}]}
                    for i in item_ids
                ],
            })
            assert row.get("request_id"), row
            for item_id in item_ids:
                answer_request(universe_id=A_UID, payload={
                    "request_id": row["request_id"], "item_id": item_id,
                    "values": {"note": "done"},
                })
    finally:
        monkeypatch.undo()

    kinds = [n.silent for _d, n in recorder.calls]
    assert kinds == [False, True], f"{len(kinds)} pushes: {kinds}"


# --- the exception boundary ---------------------------------------------------


def test_a_transport_exception_does_not_reach_the_log_either(base, caplog):
    """The ledger and the return value were checked; the LOG was not, and
    exc_info=True put the bearer token from a raising transport into the
    traceback while the test still passed (gpt-6-astra, 2026-09-29)."""
    import logging

    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "token-alice-phone")
    leaky = RuntimeError("Bearer ya29.SUPER-SECRET-TOKEN failed")
    _recorder, transports = _fake(raises=leaky)

    with caplog.at_level(logging.DEBUG):
        row, result = _raise_request(base, A_UID, ALICE, transports)

    assert "SUPER-SECRET-TOKEN" not in caplog.text
    assert "ya29" not in caplog.text
    # It still says enough to diagnose: the class, the platform, the device.
    assert "RuntimeError" in caplog.text
    ledger = devices.deliveries_for(base, request_id=row["request_id"])
    assert "SUPER-SECRET-TOKEN" not in json.dumps([ledger, result])
