from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tinyassets.app_conversation_authority import (
    AppConversationAuthority,
    AppConversationAuthorityError,
    _grant_signing_bytes,
)
from tinyassets.app_event_ingress import SlackRequestVerifier
from tinyassets.app_principal_mapping import AppPrincipalMappingService, AppPrincipalTarget
from tinyassets.custom_agents import create_binding, publish_definition
from tinyassets.daemon_server import (
    grant_universe_access,
    initialize_author_server,
    set_founder_home,
)

NOW = 1_900_000_000
SECRET = "authority-test-secret"
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
        headers={
            "x-slack-request-timestamp": timestamp,
            "x-slack-signature": signature,
        },
    )


def _mapping(base: Path) -> tuple[AppPrincipalMappingService, AppPrincipalTarget]:
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


def _authority(base: Path, service: AppPrincipalMappingService, target: AppPrincipalTarget):
    private = base / "private-universe"
    private.mkdir()
    key = Ed25519PrivateKey.generate()
    public_wire = base64.urlsafe_b64encode(
        key.public_key().public_bytes_raw()
    ).decode().rstrip("=")
    return (
        AppConversationAuthority(
            base,
            mapping=service,
            storage_resolver=lambda record: (private, base),
            signing_key=key,
            authority_key_id="custody-authority-test",
            clock=time.time,
        ),
        public_wire,
    )


def test_issue_returns_signed_one_use_grant_without_payload_access(tmp_path: Path, monkeypatch):
    service, target = _mapping(tmp_path)
    authority, public_wire = _authority(tmp_path, service, target)
    monkeypatch.setenv("TINYASSETS_CUSTODY_AUTHORITY_KEY_ID", "custody-authority-test")
    monkeypatch.setenv("TINYASSETS_CUSTODY_AUTHORITY_PUBLIC_KEY_B64U", public_wire)
    request_digest = "sha256:" + "a" * 64
    key_digest = "sha256:" + "b" * 64

    grant = authority.issue(
        _event(),
        action="create_thread",
        request_digest=request_digest,
        idempotency_key_digest=key_digest,
    )
    public = authority.signing_key.public_key()
    public.verify(
        base64.urlsafe_b64decode(
            grant.signature + "=" * ((4 - len(grant.signature) % 4) % 4)
        ),
        _grant_signing_bytes(grant.evidence),
    )
    evidence = grant.evidence
    assert evidence.owner_user_id == SENDER_ID
    assert evidence.agent_binding_id == target.agent_binding_id
    assert evidence.selection_generation == 1
    assert grant.evidence.grant_id.startswith("cg_")


def test_stale_mapping_and_malformed_requests_fail_closed(tmp_path: Path):
    service, target = _mapping(tmp_path)
    authority, _public_wire = _authority(tmp_path, service, target)
    with pytest.raises(AppConversationAuthorityError, match="TTL"):
        authority.issue(
            _event(), action="read_thread", request_digest="sha256:" + "a" * 64, ttl_seconds=301
        )
    service.revoke(_event(), expected_generation=1)
    with pytest.raises(AppConversationAuthorityError):
        authority.issue(_event(), action="read_thread", request_digest="sha256:" + "a" * 64)


def test_storage_resolver_receives_mapping_only(tmp_path: Path):
    service, target = _mapping(tmp_path)
    seen = []
    private = tmp_path / "private"
    private.mkdir()
    authority = AppConversationAuthority(
        tmp_path,
        mapping=service,
        storage_resolver=lambda record: (seen.append(record) or (private, tmp_path)),
        signing_key=Ed25519PrivateKey.generate(),
        authority_key_id="custody-authority-test",
        clock=time.time,
    )
    authority.issue(_event(), action="read_thread", request_digest="sha256:" + "a" * 64)
    assert seen and not hasattr(seen[0], "payload")
