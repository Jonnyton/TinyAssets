from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tinyassets.app_event_ingress import SlackRequestVerifier
from tinyassets.app_principal_mapping import AppPrincipalMappingService, AppPrincipalTarget
from tinyassets.app_reply_authority import (
    AppReplyAuthority,
    AppReplyAuthorityError,
    ReplyDestination,
)
from tinyassets.custom_agents import create_binding, publish_definition
from tinyassets.daemon_server import (
    grant_universe_access,
    initialize_author_server,
    set_founder_home,
)
from tinyassets.storage.app_principal_mappings import AppPrincipalMappingRecord

NOW = 1_900_000_000
SECRET = "reply-test-secret"
APP_ID = "A0123456789"
TEAM_ID = "T0123456789"
SENDER_ID = "U0123456789"


def _event():
    body = json.dumps(
        {
            "type": "event_callback",
            "api_app_id": APP_ID,
            "team_id": TEAM_ID,
            "event_id": "Ev0123456789",
            "event": {"type": "app_mention", "user": SENDER_ID, "text": "private text"},
        },
        separators=(",", ":"),
    ).encode()
    timestamp = str(NOW)
    signature = "v0=" + hmac.new(
        SECRET.encode(), b"v0:" + timestamp.encode() + b":" + body, hashlib.sha256
    ).hexdigest()
    return SlackRequestVerifier(
        signing_secret=SECRET, expected_api_app_id=APP_ID, clock=lambda: NOW
    ).authenticate(
        raw_body=body,
        headers={"x-slack-request-timestamp": timestamp, "x-slack-signature": signature},
    )


def _mapping(base: Path):
    initialize_author_server(base)
    grant_universe_access(
        base, universe_id="u-founder", actor_id=SENDER_ID, permission="admin", granted_by=SENDER_ID
    )
    set_founder_home(base, founder_sub=SENDER_ID, universe_id="u-founder")
    definition = publish_definition(
        base,
        author_id=SENDER_ID,
        payload={
            "schema_version": 1,
            "name": "Founder",
            "components": {"identity": {"kind": "soul", "config": {}}},
        },
    )
    binding = create_binding(
        base,
        universe_id="u-founder",
        definition_id=definition["agent_definition_id"],
        created_by=SENDER_ID,
        payload={"schema_version": 1, "name": "Binding", "model": "test-model"},
    )
    target = AppPrincipalTarget(
        subject_id=SENDER_ID,
        universe_id="u-founder",
        agent_binding_id=binding["agent_binding_id"],
        binding_revision=binding["revision"],
    )
    service = AppPrincipalMappingService(base)
    service.provision(_event(), resolve_target=lambda _key: target)
    return service, target


def _authority(base: Path, service, target):
    private = base / "private-universe"
    private.mkdir()
    key = Ed25519PrivateKey.generate()
    from tinyassets.app_conversation_authority import AppConversationAuthority

    return AppConversationAuthority(
        base,
        mapping=service,
        storage_resolver=lambda _record: (private, base),
        signing_key=key,
        authority_key_id="custody-authority-test",
        clock=time.time,
    )


def _handoff(base: Path):
    service, target = _mapping(base)
    custody = _authority(base, service, target)
    handoff = custody.issue(
        _event(),
        action="append_message",
        request_digest="sha256:" + "a" * 64,
        idempotency_key_digest="sha256:" + "b" * 64,
    )
    return service, target, custody, handoff


def test_authorize_verifies_handoff_and_returns_content_free_destination(tmp_path: Path):
    service, target, custody, handoff = _handoff(tmp_path)
    seen: list[AppPrincipalMappingRecord] = []
    authority = AppReplyAuthority(
        tmp_path,
        mapping=service,
        public_key=custody.signing_key.public_key(),
        authority_key_id="custody-authority-test",
        destination_resolver=lambda record: (
            seen.append(record) or ReplyDestination("slack", "conn-1", "C0123456789")
        ),
        clock=time.time,
    )
    result = authority.authorize(_event(), handoff, response_digest="sha256:" + "c" * 64)
    assert result.owner_user_id == target.subject_id
    assert result.destination.provider == "slack"
    assert result.authorization_digest.startswith("sha256:")
    assert seen and not hasattr(seen[0], "payload")
    assert "private text" not in repr(result)


def test_authorize_rejects_tampered_signature_and_stale_mapping(tmp_path: Path):
    service, _target, custody, handoff = _handoff(tmp_path)
    authority = AppReplyAuthority(
        tmp_path,
        mapping=service,
        public_key=custody.signing_key.public_key(),
        authority_key_id="custody-authority-test",
        destination_resolver=lambda _record: ReplyDestination("slack", "conn-1", "C0123456789"),
        clock=time.time,
    )
    tampered = type(handoff)(handoff.evidence, handoff.signature[:-1] + "A")
    with pytest.raises(AppReplyAuthorityError):
        authority.authorize(_event(), tampered, response_digest="sha256:" + "c" * 64)
    service.revoke(_event(), expected_generation=1)
    with pytest.raises(AppReplyAuthorityError):
        authority.authorize(_event(), handoff, response_digest="sha256:" + "c" * 64)


def test_authorize_rejects_invalid_destination_and_digest(tmp_path: Path):
    service, _target, custody, handoff = _handoff(tmp_path)
    authority = AppReplyAuthority(
        tmp_path,
        mapping=service,
        public_key=custody.signing_key.public_key(),
        authority_key_id="custody-authority-test",
        destination_resolver=lambda _record: ReplyDestination("slack", "conn-1", "C0123456789"),
        clock=time.time,
    )
    with pytest.raises(AppReplyAuthorityError):
        authority.authorize(_event(), handoff, response_digest="not-a-digest")
    bad_destination = AppReplyAuthority(
        tmp_path,
        mapping=service,
        public_key=custody.signing_key.public_key(),
        authority_key_id="custody-authority-test",
        destination_resolver=lambda _record: ReplyDestination("smtp", "conn-1", "dest"),
        clock=time.time,
    )
    with pytest.raises(AppReplyAuthorityError):
        bad_destination.authorize(_event(), handoff, response_digest="sha256:" + "c" * 64)
