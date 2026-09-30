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
    assert notification.title == A_NAME
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


def test_an_unreadable_universe_name_falls_back_to_the_platform_name(base):
    """A record we cannot read must not promote agent text into the title."""
    from tinyassets.owner_notifications import _compose

    notification = _compose(
        base, "u-does-not-exist",
        {"request_id": "req_x", "kind": "TinyAssets", "title": "Official notice"},
    )

    assert notification.title == "TinyAssets"


def test_a_universe_named_after_its_own_id_is_not_a_name(base):
    from tinyassets.owner_notifications import _compose

    _home(base, A_UID, ALICE)  # no display name -> the row stores the id

    assert _compose(base, A_UID, {"request_id": "r"}).title == "TinyAssets"


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

    request = {"request_id": "req_retry", "kind": "TODO", "title": "Today"}
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
    from tinyassets.owner_notifications import clear_request

    clear_request(
        base, universe_id=A_UID, answered_by=ALICE, request_id="req_x",
        skip_device_id=answering, transports=transports,
    )

    assert [d["device_id"] for d, _ in recorder.calls] != [answering]
    assert len(recorder.calls) == 1


def test_an_item_answer_clears_only_that_item(base):
    _home(base, A_UID, ALICE, A_NAME)
    _register(base, ALICE, "phone")
    recorder, transports = _fake()
    from tinyassets.owner_notifications import clear_request

    clear_request(
        base, universe_id=A_UID, answered_by=ALICE, request_id="req_x",
        item_id="standup", transports=transports,
    )

    [(_device, notification)] = recorder.calls
    assert notification.data["item_id"] == "standup"


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
