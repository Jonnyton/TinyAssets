# ruff: noqa: F811  (imported fixtures are re-named by the tests that request them)
"""An Android (FCM) device, registered through /app/devices and delivered to.

The phone app POSTs its FCM token to the same route the browser uses, as
platform ``fcm``. What these pin, at the boundaries the change touches:

* the device belongs to the AUTHENTICATED subject -- a body that names an owner
  changes nothing;
* a token re-registered under another subject MOVES, so a handset that changes
  accounts cannot keep delivering the previous owner's requests (the floor:
  no cross-user delivery);
* the request the owner raised reaches the registered device through the REAL
  FCM transport, with only ``urlopen`` faked.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.test_app_notification_routes import (  # noqa: F401  (fixture + harness)
    ALICE,
    BOB,
    _as,
    _call,
    app_env,
)
from tests.test_notify_transports import (  # noqa: F401  (fixtures + harness)
    SEND_URL,
    _Response,
    service_account,
    wire,
)

PHONE_TOKEN = "fcm-registration-token-alice-pixel"


def _register(owner: str, token: str = PHONE_TOKEN, **extra):
    from tinyassets.onboarding.notifications import handle_devices

    with _as(owner):
        return _call(handle_devices, "POST", {
            "platform": "fcm", "token": token, "label": "This phone", **extra,
        })


def _targets(owner: str):
    from tinyassets.api.helpers import _base_path
    from tinyassets.storage import owner_devices as devices

    return devices.delivery_targets(_base_path(), owner_user_id=owner)


def test_an_fcm_device_registers_under_the_authenticated_owner(app_env):
    status, created, _ = _register(ALICE)

    assert status == 200, created
    assert created["device_id"].startswith("dev_")
    # Filed under the platform the FCM transport is resolved by.
    assert created["platform"] == "android"
    [target] = _targets(ALICE)
    assert target["platform"] == "android" and target["token"] == PHONE_TOKEN
    assert _targets(BOB) == []


def test_registration_returns_the_callers_own_recipient_tag_and_no_one_elses(app_env):
    from tinyassets.storage.owner_devices import recipient_tag

    alice = _register(ALICE)[1]
    bob = _register(BOB, token="bobs-phone", owner_user_id=ALICE)[1]

    assert alice["recipient"] == recipient_tag(ALICE)
    assert bob["recipient"] == recipient_tag(BOB) != alice["recipient"]
    assert ALICE not in alice["recipient"]        # opaque, not the subject


def test_a_body_cannot_name_the_owner_of_an_fcm_device(app_env):
    status, _created, _ = _register(
        ALICE, owner_user_id=BOB, owner_sub=BOB, user_id=BOB, device_id="dev_forged",
    )

    assert status == 200
    assert len(_targets(ALICE)) == 1
    assert _targets(BOB) == []


def test_registering_an_fcm_device_needs_an_identity(app_env, nobody):
    from tinyassets.onboarding.notifications import handle_devices

    status, payload, _ = _call(handle_devices, "POST", {
        "platform": "fcm", "token": PHONE_TOKEN,
    })

    assert status == 401
    assert payload["error"] == "authentication_required"


def test_the_token_is_never_returned_by_a_read(app_env):
    from tinyassets.onboarding.notifications import handle_devices

    _register(ALICE)
    with _as(ALICE):
        _status, listed, _ = _call(handle_devices, "GET")

    assert PHONE_TOKEN not in json.dumps(listed)
    assert listed["devices"][0]["platform"] == "android"


def test_the_same_phone_relaunching_keeps_its_device_id(app_env):
    first = _register(ALICE)[1]["device_id"]
    second = _register(ALICE)[1]["device_id"]

    assert first == second
    assert len(_targets(ALICE)) == 1


def test_a_refreshed_token_is_a_second_row_for_the_same_owner_never_another_owners(
    app_env,
):
    """FCM rotates a token; the app posts the new one. The owner has the new
    row, and nobody else gains anything."""
    _register(ALICE, token="old-token")
    _register(ALICE, token="new-token")

    assert {t["token"] for t in _targets(ALICE)} == {"old-token", "new-token"}
    assert _targets(BOB) == []


def test_a_handset_that_changes_accounts_stops_delivering_to_the_old_owner(app_env):
    _register(ALICE)
    assert len(_targets(ALICE)) == 1

    status, _moved, _ = _register(BOB)   # same handset, same FCM token, new login

    assert status == 200
    assert _targets(ALICE) == []
    assert [t["token"] for t in _targets(BOB)] == [PHONE_TOKEN]


def test_fcm_is_an_alias_not_a_second_platform_with_its_own_identity_rule(app_env):
    """`fcm` and `android` name one destination: registering the token under
    either name, for two owners, leaves exactly one live row."""
    from tinyassets.onboarding.notifications import handle_devices

    _register(ALICE)
    with _as(BOB):
        _call(handle_devices, "POST", {"platform": "android", "token": PHONE_TOKEN})

    assert _targets(ALICE) == []
    assert len(_targets(BOB)) == 1


def test_a_request_reaches_the_registered_fcm_device_through_the_real_transport(
    app_env, monkeypatch, service_account, wire,
):
    """The end of the chain: registered through the route, raised by the owner's
    universe, delivered by the real transport. Only the socket is faked."""
    from tinyassets.api import visibility as vis
    from tinyassets.api.helpers import _base_path
    from tinyassets.daemon_server import (
        claim_founder_home,
        ensure_universe_registered,
        grant_universe_access,
        set_universe_display_name,
    )
    from tinyassets.owner_notifications import notify_request_raised

    base = _base_path()
    uid = "u-alice-fcm"
    udir = Path(base) / uid
    udir.mkdir(parents=True)
    ensure_universe_registered(base, universe_id=uid, universe_path=udir)
    grant_universe_access(
        base, universe_id=uid, actor_id=ALICE, permission="admin", granted_by=ALICE,
    )
    claim_founder_home(base, ALICE, uid)
    vis.set_universe_visibility(uid, "private", source="default")
    set_universe_display_name(base, universe_id=uid, display_name="Alice's universe")

    _register(ALICE)
    _register(BOB, token="fcm-registration-token-bob")

    result = notify_request_raised(
        base, universe_id=uid, raised_by=ALICE,
        request={"request_id": "req_fcm", "kind": "TODO", "title": "Today",
                 "items": [{"item_id": "one"}]},
    )

    assert result["sent"] == 1
    [sent] = wire.sent_to(SEND_URL)
    assert sent.get_header("Authorization") == "Bearer ya29.test"
    message = json.loads(sent.data.decode("utf-8"))["message"]
    # Alice's phone, and only Alice's.
    assert message["token"] == PHONE_TOKEN
    assert "notification" not in message            # data only: the app draws it
    assert message["data"]["title"] == "Alice's universe asks"
    assert message["data"]["body"] == "TODO: Today"
    assert message["data"]["request_id"] == "req_fcm"
    assert message["data"]["item_ids"] == "one"
    assert message["android"]["priority"] == "high"
    assert "fcm-registration-token-bob" not in json.dumps(message)
    # Whose message it is, so a phone armed for someone else drops it.
    from tinyassets.storage.owner_devices import recipient_tag

    assert message["data"]["recipient"] == recipient_tag(ALICE) != recipient_tag(BOB)
