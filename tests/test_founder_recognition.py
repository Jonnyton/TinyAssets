"""Binary founder recognition on external chat surfaces.

The property under test, in the host's words: the agent must know *for a fact*
whether it is talking to the verified founder, and when it is not it must be
**programmatically unable** to do founder-only things.

So these tests are mostly about the negative direction. Anyone can write a test
that the founder is recognised; the ones that matter are the ones asserting
that everybody else is not, and that the failure is structural rather than a
convention someone can forget.
"""

from __future__ import annotations

import base64
import copy
import dataclasses
import hashlib
import hmac
import json
import pickle
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tinyassets.app_conversation_authority import (
    AppConversationAuthority,
    AppConversationAuthorityError,
)
from tinyassets.app_event_ingress import (
    SlackRequestVerifier,
    SlackSocketModeBoundary,
    is_admissible_principal_event,
    is_authenticated_app_event,
    is_socket_mode_app_event,
)
from tinyassets.app_principal_mapping import (
    AppPrincipalMappingService,
    AppPrincipalTarget,
)
from tinyassets.custom_agents import create_binding, publish_definition, update_binding
from tinyassets.daemon_server import (
    grant_universe_access,
    initialize_author_server,
    revoke_universe_access,
    set_founder_home,
)
from tinyassets.founder_grant import FounderGrant, FounderRecognizer, is_founder_grant
from tinyassets.storage.app_events import AppEventAdmissionStore

NOW = 1_900_000_000
SECRET = "founder-recognition-secret"
APP_ID = "A0123456789"
TEAM_ID = "T0123456789"
FOUNDER_ID = "U0FOUNDER01"
STRANGER_ID = "U0STRANGER1"
FOREIGN_TEAM = "T0FOREIGN01"
UNIVERSE = "u-founder"


# --- fixtures ---------------------------------------------------------------


def _payload(
    *,
    sender: str = FOUNDER_ID,
    event_id: str = "Ev0000000001",
    team: str = TEAM_ID,
    user_team: str | None = None,
    text: str = "remember that we launch on Friday",
) -> dict:
    inner: dict = {
        "type": "app_mention",
        "user": sender,
        "text": text,
        "channel": "C0123456789",
    }
    if user_team is not None:
        inner["user_team"] = user_team
    return {
        "type": "event_callback",
        "api_app_id": APP_ID,
        "team_id": team,
        "event_id": event_id,
        "event": inner,
    }


def _socket_event(base: Path, **kwargs):
    """Mint sealed Socket Mode evidence the only way it can be minted."""
    boundary = SlackSocketModeBoundary(
        expected_api_app_id=APP_ID,
        store=AppEventAdmissionStore(base),
        clock=lambda: NOW,
    )
    return boundary.admit(payload=_payload(**kwargs)).event


def _http_event(*, sender: str = FOUNDER_ID, event_id: str = "Ev0000000009"):
    """Mint HMAC-sealed evidence — the strictly stronger attestation."""
    body = json.dumps(
        _payload(sender=sender, event_id=event_id), separators=(",", ":")
    ).encode()
    timestamp = str(NOW)
    signature = "v0=" + hmac.new(
        SECRET.encode(), b"v0:" + timestamp.encode() + b":" + body, hashlib.sha256
    ).hexdigest()
    return SlackRequestVerifier(
        signing_secret=SECRET, expected_api_app_id=APP_ID, clock=lambda: NOW
    ).authenticate(
        raw_body=body,
        headers={
            "x-slack-request-timestamp": timestamp,
            "x-slack-signature": signature,
        },
    )


def _founder_universe(base: Path, *, subject: str = FOUNDER_ID, universe: str = UNIVERSE):
    initialize_author_server(base)
    grant_universe_access(
        base,
        universe_id=universe,
        actor_id=subject,
        permission="admin",
        granted_by=subject,
    )
    set_founder_home(base, founder_sub=subject, universe_id=universe)
    definition = publish_definition(
        base,
        author_id=subject,
        payload={
            "schema_version": 1,
            "name": "Tiny",
            "description": "A startup agent that thinks of itself as the startup",
            "tags": ["test"],
            "components": {
                "identity": {"kind": "soul", "config": {"instructions": "Be Tiny."}}
            },
        },
    )
    binding = create_binding(
        base,
        universe_id=universe,
        definition_id=definition["agent_definition_id"],
        created_by=subject,
        payload={"schema_version": 1, "name": "Tiny binding", "model": "test-model"},
    )
    # The universe directory must exist — a mapping can outlive its universe.
    (base / universe).mkdir(exist_ok=True)
    return AppPrincipalTarget(
        subject_id=subject,
        universe_id=universe,
        agent_binding_id=binding["agent_binding_id"],
        binding_revision=binding["revision"],
    )


def _recognized(base: Path, **event_kwargs):
    """Provision the founder mapping, then recognise a fresh event."""
    target = _founder_universe(base)
    service = AppPrincipalMappingService(base)
    service.provision(_socket_event(base), resolve_target=lambda _key: target)
    recognizer = FounderRecognizer(base, mapping=service)
    return recognizer, target, recognizer.recognize(_socket_event(base, **event_kwargs))


# --- the happy path, so the negatives mean something ------------------------


def test_the_verified_founder_is_recognized(tmp_path: Path) -> None:
    _, target, grant = _recognized(tmp_path, event_id="Ev0000000002")

    assert is_founder_grant(grant)
    assert grant.universe_id == target.universe_id
    assert grant.subject_id == FOUNDER_ID


# --- task 2.2: the weaker evidence stays out of the custody paths -----------


def test_socket_evidence_is_not_the_request_seal(tmp_path: Path) -> None:
    socket = _socket_event(tmp_path)
    http = _http_event()

    assert is_socket_mode_app_event(socket) and not is_authenticated_app_event(socket)
    assert is_authenticated_app_event(http) and not is_socket_mode_app_event(http)
    assert is_admissible_principal_event(socket) and is_admissible_principal_event(http)


def test_socket_evidence_cannot_mint_a_custody_grant(tmp_path: Path, monkeypatch) -> None:
    """The seal means "these exact request bytes were signed"; Socket Mode
    attests nothing about request bytes, and thread custody is issued on that
    fact. Widening the shared key helper for founder recognition must not
    widen this."""
    target = _founder_universe(tmp_path)
    service = AppPrincipalMappingService(tmp_path)
    service.provision(_socket_event(tmp_path), resolve_target=lambda _key: target)
    private = tmp_path / "private-universe"
    private.mkdir()
    monkeypatch.setenv("TINYASSETS_CUSTODY_AUTHORITY_KEY_ID", "custody-authority-test")
    authority = AppConversationAuthority(
        tmp_path,
        mapping=service,
        storage_resolver=lambda record: (private, tmp_path),
        signing_key=Ed25519PrivateKey.generate(),
        authority_key_id="custody-authority-test",
        clock=time.time,
    )

    with pytest.raises(AppConversationAuthorityError) as exc:
        authority.issue(
            _socket_event(tmp_path, event_id="Ev0000000003"),
            action="read_thread",
            request_digest="sha256:" + "a" * 64,
        )

    assert "request-signature" in str(exc.value)


def test_socket_evidence_cannot_authorize_a_reply(tmp_path: Path, monkeypatch) -> None:
    """The reply path verifies a signed handoff, so it needs the same evidence
    the handoff was minted from. Mint a real grant with HTTP evidence, then try
    to spend it with Socket Mode evidence."""
    from tinyassets.app_reply_authority import AppReplyAuthority, AppReplyAuthorityError

    target = _founder_universe(tmp_path)
    service = AppPrincipalMappingService(tmp_path)
    service.provision(_http_event(), resolve_target=lambda _key: target)
    private = tmp_path / "private-universe"
    private.mkdir()
    key = Ed25519PrivateKey.generate()
    public_wire = (
        base64.urlsafe_b64encode(key.public_key().public_bytes_raw()).decode().rstrip("=")
    )
    monkeypatch.setenv("TINYASSETS_CUSTODY_AUTHORITY_KEY_ID", "custody-authority-test")
    monkeypatch.setenv("TINYASSETS_CUSTODY_AUTHORITY_PUBLIC_KEY_B64U", public_wire)

    handoff = AppConversationAuthority(
        tmp_path,
        mapping=service,
        storage_resolver=lambda record: (private, tmp_path),
        signing_key=key,
        authority_key_id="custody-authority-test",
        clock=time.time,
    ).issue(
        _http_event(event_id="Ev00HTTP02"),
        action="append_message",
        request_digest="sha256:" + "a" * 64,
        idempotency_key_digest="sha256:" + "b" * 64,
    )

    reply_authority = AppReplyAuthority(
        tmp_path,
        mapping=service,
        destination_resolver=lambda record: (_ for _ in ()).throw(
            AssertionError("must fail before resolving a destination")
        ),
        public_key=key.public_key(),
        authority_key_id="custody-authority-test",
        clock=time.time,
    )

    with pytest.raises(AppReplyAuthorityError) as exc:
        reply_authority.authorize(
            _socket_event(tmp_path, event_id="Ev00SOCK03"),
            handoff,
            response_digest="sha256:" + "c" * 64,
        )

    assert "request-signature" in str(exc.value)


# --- task 3.2: replay admission survives a restart --------------------------


def test_a_redelivered_event_is_a_replay_across_a_restart(tmp_path: Path) -> None:
    """Slack redelivers an envelope that was not acked. In-memory dedupe loses
    its window on restart, and on the founder path "handled twice" means a
    second durable learning commit into the founder's own soul."""
    payload = _payload(event_id="Ev00REPLAY01")

    first = SlackSocketModeBoundary(
        expected_api_app_id=APP_ID,
        store=AppEventAdmissionStore(tmp_path),
        clock=lambda: NOW,
    ).admit(payload=payload)
    # A brand-new boundary AND a brand-new store object: the process restarted.
    second = SlackSocketModeBoundary(
        expected_api_app_id=APP_ID,
        store=AppEventAdmissionStore(tmp_path),
        clock=lambda: NOW,
    ).admit(payload=payload)

    assert first.replay is False
    assert second.replay is True
    assert second.receipt.admission_id == first.receipt.admission_id


# --- task 4.4: every failure mode, independently ----------------------------


def test_a_stranger_in_the_same_channel_is_not_the_founder(tmp_path: Path) -> None:
    _, _, grant = _recognized(tmp_path, sender=STRANGER_ID, event_id="Ev0000000004")

    assert grant is None


def test_a_connect_guest_with_a_colliding_user_id_keys_to_a_different_principal(
    tmp_path: Path,
) -> None:
    """Slack user ids are unique only *within* a workspace. A guest from
    another workspace can carry the founder's exact id, and under Slack Connect
    their message is delivered on our workspace's socket.

    The primary defence is the principal *key*: it is derived from the sender's
    own workspace, so the guest never reaches the founder's mapping at all.
    Asserted on the key itself — asserting only "no grant" passed even with the
    recognizer's guard disabled, because the lookup had already missed.
    """
    from tinyassets.app_principal_mapping import _external_key

    local = _external_key(_socket_event(tmp_path, sender=FOUNDER_ID, event_id="Ev00K1"))
    guest = _external_key(
        _socket_event(
            tmp_path,
            sender=FOUNDER_ID,       # the SAME id as the founder
            user_team=FOREIGN_TEAM,  # but their home workspace is not ours
            event_id="Ev00K2",
        )
    )

    assert local.workspace_id == TEAM_ID
    assert guest.workspace_id == FOREIGN_TEAM
    assert local != guest, "a Connect guest must not key to the founder's principal"

    _, _, grant = _recognized(
        tmp_path, sender=FOUNDER_ID, user_team=FOREIGN_TEAM, event_id="Ev0000000005"
    )
    assert grant is None


def test_a_connect_guest_holding_a_mapping_is_still_not_our_founder(
    tmp_path: Path,
) -> None:
    """Defence in depth, and the case the key alone does not cover.

    A founder installed this app in their *own* workspace, so a sender whose
    home workspace is not the installation's cannot be that founder — even if a
    mapping exists for them. Provision one deliberately to prove the recognizer
    refuses on its own, rather than inheriting a lookup miss.
    """
    target = _founder_universe(tmp_path)
    service = AppPrincipalMappingService(tmp_path)
    guest_event = _socket_event(
        tmp_path, sender=FOUNDER_ID, user_team=FOREIGN_TEAM, event_id="Ev00G1"
    )
    service.provision(guest_event, resolve_target=lambda _key: target)

    # The mapping resolves — the guest is a known principal.
    assert service.resolve(guest_event).universe_id == target.universe_id

    recognizer = FounderRecognizer(tmp_path, mapping=service)
    grant = recognizer.recognize(
        _socket_event(
            tmp_path, sender=FOUNDER_ID, user_team=FOREIGN_TEAM, event_id="Ev00G2"
        )
    )

    assert grant is None, "a foreign-workspace sender is never this app's founder"


def test_revoking_admin_takes_effect_on_the_very_next_message(tmp_path: Path) -> None:
    recognizer, target, grant = _recognized(tmp_path, event_id="Ev0000000006")
    assert is_founder_grant(grant)

    revoke_universe_access(tmp_path, universe_id=target.universe_id, actor_id=FOUNDER_ID)

    assert recognizer.recognize(_socket_event(tmp_path, event_id="Ev0000000007")) is None


def test_a_co_admin_does_not_lock_the_founder_out(tmp_path: Path) -> None:
    """Cross-family review, availability: an "exactly one admin" rule would
    revoke the real founder's own recognition the moment they add a co-admin.
    A co-admin is not a rival claim to being the founder."""
    recognizer, target, grant = _recognized(tmp_path, event_id="Ev0000000008")
    assert is_founder_grant(grant)

    grant_universe_access(
        tmp_path,
        universe_id=target.universe_id,
        actor_id=STRANGER_ID,
        permission="admin",
        granted_by=FOUNDER_ID,
    )

    still = recognizer.recognize(_socket_event(tmp_path, event_id="Ev0000000010"))
    assert is_founder_grant(still), "adding a co-admin must not revoke the founder"


def test_the_founder_is_recognized_on_a_universe_that_is_not_their_home(
    tmp_path: Path,
) -> None:
    """Users keep several universes — work, personal, hobby. `founder_home`
    holds ONE row per subject, so requiring "this universe is your home" made a
    user the verified founder of exactly one of them and a stranger on the
    rest: their work agent would answer fluently and refuse to learn.

    Ownership is the per-universe admin ACL. This binds the Slack identity to
    the NON-home universe and asserts recognition still succeeds.
    """
    home = _founder_universe(tmp_path, universe="u-personal")
    work = _founder_universe(tmp_path, universe="u-work")
    # `set_founder_home` overwrites, so only the LAST one is home. Point it
    # deliberately away from the universe under test.
    set_founder_home(tmp_path, founder_sub=FOUNDER_ID, universe_id=home.universe_id)

    service = AppPrincipalMappingService(tmp_path)
    service.provision(_socket_event(tmp_path), resolve_target=lambda _key: work)
    recognizer = FounderRecognizer(tmp_path, mapping=service)

    grant = recognizer.recognize(_socket_event(tmp_path, event_id="Ev0000000018"))

    assert is_founder_grant(grant), "a second universe is still yours"
    assert grant.universe_id == "u-work"


def test_a_sender_who_does_not_own_the_universe_is_not_the_founder(
    tmp_path: Path,
) -> None:
    """The exclusion that replaces the cardinality rule: ownership is the admin
    ACL row on THIS universe, so losing it ends recognition regardless of what
    `founder_home` says."""
    recognizer, target, grant = _recognized(tmp_path, event_id="Ev0000000019")
    assert is_founder_grant(grant)

    # Hand ownership to someone else. The binding is still one the founder
    # created, and `founder_home` still points here — so the ONLY thing that
    # changed is who holds admin. Checking merely that *an* admin exists would
    # now find the stranger's row and mint a grant for the founder anyway.
    revoke_universe_access(tmp_path, universe_id=target.universe_id, actor_id=FOUNDER_ID)
    grant_universe_access(
        tmp_path,
        universe_id=target.universe_id,
        actor_id=STRANGER_ID,
        permission="admin",
        granted_by=STRANGER_ID,
    )
    set_founder_home(tmp_path, founder_sub=FOUNDER_ID, universe_id=target.universe_id)

    assert recognizer.recognize(_socket_event(tmp_path, event_id="Ev0000000020")) is None


def test_a_rotated_binding_revokes_recognition(tmp_path: Path) -> None:
    recognizer, target, grant = _recognized(tmp_path, event_id="Ev0000000011")
    assert is_founder_grant(grant)

    update_binding(
        tmp_path,
        universe_id=target.universe_id,
        binding_id=target.agent_binding_id,
        updated_by=FOUNDER_ID,
        expected_revision=target.binding_revision,
        payload={"schema_version": 1, "name": "Rotated", "model": "other-model"},
    )

    assert recognizer.recognize(_socket_event(tmp_path, event_id="Ev0000000012")) is None


def test_a_deleted_universe_revokes_recognition(tmp_path: Path) -> None:
    recognizer, target, grant = _recognized(tmp_path, event_id="Ev0000000013")
    assert is_founder_grant(grant)

    (tmp_path / target.universe_id).rmdir()

    assert recognizer.recognize(_socket_event(tmp_path, event_id="Ev0000000014")) is None


def test_unsealed_evidence_is_never_recognized(tmp_path: Path) -> None:
    """A plain object shaped like an event must not be recognisable."""
    _founder_universe(tmp_path)
    recognizer = FounderRecognizer(tmp_path)

    class _Forged:
        provider = "slack"
        installation_id = f"{APP_ID}:{TEAM_ID}"
        api_app_id = APP_ID
        team_id = TEAM_ID
        actor_team_id = TEAM_ID
        external_sender_id = FOUNDER_ID
        external_event_id = "Ev0000000015"
        event_type = "app_mention"

    assert recognizer.recognize(_Forged()) is None


# --- task 5.4: the grant cannot be forged or bypassed -----------------------


def test_a_founder_grant_cannot_be_constructed_by_a_caller() -> None:
    with pytest.raises(TypeError):
        FounderGrant(
            universe_id=UNIVERSE,
            subject_id=FOUNDER_ID,
            agent_binding_id="ab_forged",
            binding_revision=1,
            mapping_generation=1,
            provider="slack",
            workspace_id=TEAM_ID,
            external_sender_id=FOUNDER_ID,
            _seal=object(),
        )


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda g: dataclasses.replace(g, universe_id="u-someone-else"),
            id="dataclasses.replace",
        ),
        pytest.param(lambda g: copy.deepcopy(g), id="deepcopy"),
        pytest.param(lambda g: pickle.loads(pickle.dumps(g)), id="pickle"),
    ],
)
def test_a_grant_cannot_be_copied_into_a_different_authority(
    tmp_path: Path, mutate
) -> None:
    """Cross-family review, HIGH: `_seal` used to be a dataclass *field*, and
    `dataclasses.replace` passes every field straight back to the constructor.
    So a holder of one legitimate grant could mint one for ANOTHER universe —
    `replace(grant, universe_id=...)` — and it still passed `is_founder_grant`.
    """
    _, _, grant = _recognized(tmp_path, event_id="Ev00SEAL01")
    assert is_founder_grant(grant)

    try:
        forged = mutate(grant)
    except (TypeError, ValueError):
        return  # refused outright, which is the stronger outcome

    assert not is_founder_grant(forged)


def test_an_admitted_event_cannot_be_rewritten_to_another_sender(
    tmp_path: Path,
) -> None:
    """The same defect on the evidence itself, and worse: it also affected the
    pre-existing `AuthenticatedAppEvent`, so any holder of one admitted event
    could rewrite the sender to the founder's id and keep the seal."""
    event = _socket_event(tmp_path, sender=STRANGER_ID, event_id="Ev00SEAL02")
    assert is_socket_mode_app_event(event)

    with pytest.raises((TypeError, ValueError)):
        dataclasses.replace(event, external_sender_id=FOUNDER_ID)


def test_a_subclass_does_not_inherit_the_seal(tmp_path: Path) -> None:
    """Inheriting the check is not the same as passing it."""
    _, _, grant = _recognized(tmp_path, event_id="Ev00SEAL03")

    class Sneaky(FounderGrant):
        pass

    impostor = Sneaky.__new__(Sneaky)
    for name in (
        "universe_id", "subject_id", "agent_binding_id", "binding_revision",
        "mapping_generation", "provider", "workspace_id", "external_sender_id",
    ):
        object.__setattr__(impostor, name, getattr(grant, name))
    object.__setattr__(impostor, "_seal", getattr(grant, "_seal"))

    assert not is_founder_grant(impostor), "a subclass is a caller-defined type"


def test_a_forged_grant_is_downgraded_not_honoured(monkeypatch) -> None:
    """Fail-closed means the floor, not an exception: an attacker must not be
    able to tell "rejected" from "unknown"."""
    from tinyassets import universe_intelligence as ui

    class _Forged:
        universe_id = UNIVERSE

    assert ui._tier_from_grant(_Forged(), universe_id=UNIVERSE) == ui.EXTERNAL_SENDER_FLOOR


def test_a_grant_for_another_universe_is_downgraded(tmp_path: Path) -> None:
    from tinyassets import universe_intelligence as ui

    _, _, grant = _recognized(tmp_path, event_id="Ev0000000016")

    assert is_founder_grant(grant)
    assert ui._tier_from_grant(grant, universe_id="u-someone-else") == (
        ui.EXTERNAL_SENDER_FLOOR
    )


# --- task 5.2: the transport is actually wired to recognition ---------------


def _slack_config(tmp_path: Path):
    from tinyassets.effectors.slack_agent_service import SlackAgentConfig

    return SlackAgentConfig(
        universe_id=UNIVERSE,
        connection_id="slack-main",
        team_id=TEAM_ID,
        bot_user_id="U08BOT0001",
        api_app_id=APP_ID,
    )


def _inner_event(sender: str = FOUNDER_ID) -> dict:
    """What `event_of` hands the resolver: the inner event with the
    authenticated fields normalised onto it."""
    return {
        "type": "app_mention",
        "user": sender,
        "text": "<@U08BOT0001> hello",
        "channel": "C0123456789",
        "team_id": TEAM_ID,
        "api_app_id": APP_ID,
        "event_id": "Ev00WIRE01",
        "actor_team_id": TEAM_ID,
    }


def test_the_resolver_puts_the_grant_on_the_binding(tmp_path: Path, monkeypatch) -> None:
    """Recognition with no call site is dead code. This is the call site."""
    from tinyassets.effectors.slack_agent_service import build_resolver

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    sentinel = object()
    seen = []

    resolve = build_resolver(
        _slack_config(tmp_path),
        recognize=lambda event, routed=None: seen.append(event) or sentinel,
    )
    binding = resolve(_inner_event())

    assert binding is not None
    assert binding.founder_grant is sentinel
    assert seen, "the resolver must consult recognition for every event"


def test_an_unrecognized_sender_gets_a_binding_with_no_grant(
    tmp_path: Path, monkeypatch
) -> None:
    """Not the founder still gets an answer — just no founder capability."""
    from tinyassets.effectors.slack_agent_service import build_resolver

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))

    resolve = build_resolver(_slack_config(tmp_path), recognize=lambda _e, _r=None: None)
    binding = resolve(_inner_event(sender=STRANGER_ID))

    assert binding is not None, "a stranger is answered, not ignored"
    assert binding.founder_grant is None


def test_recognition_failing_degrades_the_founder_instead_of_the_agent(
    tmp_path: Path, monkeypatch
) -> None:
    """A recognition outage must not take the workspace's agent down."""
    from tinyassets.effectors import slack_agent_service as svc

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        svc,
        "_recognize_founder",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("db down")),
    )

    resolve = svc.build_resolver(_slack_config(tmp_path))

    with pytest.raises(RuntimeError):
        # The injected default is what swallows; prove the raising version is
        # genuinely reached, so the next assertion is not vacuous.
        svc._recognize_founder(_slack_config(tmp_path), _inner_event())

    binding = resolve(_inner_event())
    assert binding is not None
    assert binding.founder_grant is None


def test_a_replayed_event_never_mints_founder_authority_twice(
    tmp_path: Path, monkeypatch
) -> None:
    """The second delivery of one founder event must not re-authorise a
    learning commit, even though the first one legitimately did."""
    from tinyassets.effectors.slack_agent_service import _recognize_founder

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    target = _founder_universe(tmp_path)
    service = AppPrincipalMappingService(tmp_path)
    service.provision(_socket_event(tmp_path), resolve_target=lambda _key: target)

    config = _slack_config(tmp_path)
    event = _inner_event()

    first = _recognize_founder(config, event)
    second = _recognize_founder(config, event)

    assert is_founder_grant(first), "the founder is recognised the first time"
    assert second is None, "a redelivery must not mint founder authority again"


def test_converse_refuses_two_sources_of_authority(tmp_path: Path, monkeypatch) -> None:
    """Passing both a grant and a tier is never a legitimate call."""
    from tinyassets import universe_intelligence as ui

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    (tmp_path / UNIVERSE).mkdir(parents=True, exist_ok=True)
    _, _, grant = _recognized(tmp_path, event_id="Ev0000000017")

    with pytest.raises(ValueError, match="never both"):
        ui.converse(UNIVERSE, "hello", tier="T2", founder_grant=grant)
