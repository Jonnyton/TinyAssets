from __future__ import annotations

import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tinyassets.app_event_ingress import SlackRequestVerifier
from tinyassets.app_principal_mapping import (
    AppPrincipalEvidenceError,
    AppPrincipalMappingConflict,
    AppPrincipalMappingService,
    AppPrincipalStaleError,
    AppPrincipalTarget,
)
from tinyassets.custom_agents import create_binding, publish_definition, update_binding
from tinyassets.daemon_server import (
    grant_universe_access,
    initialize_author_server,
    revoke_universe_access,
    set_founder_home,
)
from tinyassets.storage.app_principal_mappings import AppPrincipalMappingIntegrityError

NOW = 1_900_000_000
SECRET = "mapping-test-secret"
APP_ID = "A0123456789"
TEAM_ID = "T0123456789"
SENDER_ID = "U0123456789"
EVENT_ID = "Ev0123456789"


def _event(*, text: str = "launch private workflow", event_id: str = EVENT_ID):
    body = json.dumps(
        {
            "type": "event_callback",
            "api_app_id": APP_ID,
            "team_id": TEAM_ID,
            "event_id": event_id,
            "event": {
                "type": "app_mention",
                "user": SENDER_ID,
                "text": text,
                "channel": "C0123456789",
            },
        },
        separators=(",", ":"),
    ).encode()
    timestamp = str(NOW)
    signature = "v0=" + hmac.new(
        SECRET.encode(),
        b"v0:" + timestamp.encode() + b":" + body,
        hashlib.sha256,
    ).hexdigest()
    return SlackRequestVerifier(
        signing_secret=SECRET,
        expected_api_app_id=APP_ID,
        clock=lambda: NOW,
    ).authenticate(
        raw_body=body,
        headers={
            "x-slack-request-timestamp": timestamp,
            "x-slack-signature": signature,
        },
    )


def _target_fixture(base: Path, *, subject: str = SENDER_ID, universe: str = "u-founder"):
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
            "name": "Founder agent",
            "description": "A private founder agent",
            "tags": ["test"],
            "components": {
                "identity": {
                    "kind": "soul",
                    "config": {"instructions": "Be useful."},
                }
            },
        },
    )
    binding = create_binding(
        base,
        universe_id=universe,
        definition_id=definition["agent_definition_id"],
        created_by=subject,
        payload={"schema_version": 1, "name": "Founder binding", "model": "test-model"},
    )
    return AppPrincipalTarget(
        subject_id=subject,
        universe_id=universe,
        agent_binding_id=binding["agent_binding_id"],
        binding_revision=binding["revision"],
    )


def test_provision_and_resolve_uses_exact_founder_binding(tmp_path: Path) -> None:
    target = _target_fixture(tmp_path)
    service = AppPrincipalMappingService(tmp_path)
    event = _event()

    created = service.provision(
        event,
        resolve_target=lambda key: target
        if (key.external_sender_id, key.workspace_id) == (SENDER_ID, TEAM_ID)
        else None,
    )
    resolved = service.resolve(event)

    assert created.replay is False
    assert resolved.mapping_id == created.mapping.mapping_id
    assert resolved.subject_id == SENDER_ID
    assert resolved.universe_id == "u-founder"
    assert resolved.agent_binding_id == target.agent_binding_id
    assert resolved.binding_revision == 1
    assert resolved.membership_generation
    assert "private workflow" not in created.mapping.record_json


def test_resolver_receives_only_external_key_not_message_payload(tmp_path: Path) -> None:
    target = _target_fixture(tmp_path)
    service = AppPrincipalMappingService(tmp_path)
    seen = []

    def resolver(key):
        seen.append(key)
        assert not hasattr(key, "payload")
        assert not hasattr(key, "text")
        return target

    service.provision(_event(text="choose the other universe"), resolve_target=resolver)
    assert seen[0].external_sender_id == SENDER_ID
    assert seen[0].installation_id == f"{APP_ID}:{TEAM_ID}"
    assert seen[0].workspace_id == TEAM_ID


def test_unsealed_event_and_receipt_are_not_mapping_authority(tmp_path: Path) -> None:
    service = AppPrincipalMappingService(tmp_path)
    with pytest.raises((AppPrincipalEvidenceError, TypeError)):
        service.resolve(object())

    event = _event()
    with pytest.raises(TypeError):
        event.payload["user"] = "U-forged"  # type: ignore[index]


def test_acl_regrant_fences_old_mapping_and_new_generation(tmp_path: Path) -> None:
    target = _target_fixture(tmp_path)
    service = AppPrincipalMappingService(tmp_path)
    event = _event()
    created = service.provision(event, resolve_target=lambda _: target)

    assert revoke_universe_access(
        tmp_path,
        universe_id=target.universe_id,
        actor_id=target.subject_id,
    )
    with pytest.raises(AppPrincipalStaleError):
        service.resolve(event)

    grant_universe_access(
        tmp_path,
        universe_id=target.universe_id,
        actor_id=target.subject_id,
        permission="admin",
        granted_by=target.subject_id,
    )
    with pytest.raises(AppPrincipalStaleError):
        service.resolve(event)

    service.revoke(
        event,
        expected_generation=created.mapping.mapping_generation,
    )
    replacement = service.provision(event, resolve_target=lambda _: target)
    assert replacement.replay is False
    assert replacement.mapping.mapping_generation == created.mapping.mapping_generation + 1


def test_revoke_is_idempotent_for_same_generation(tmp_path: Path) -> None:
    target = _target_fixture(tmp_path)
    service = AppPrincipalMappingService(tmp_path)
    event = _event()
    created = service.provision(event, resolve_target=lambda _: target)

    first = service.revoke(
        event,
        expected_generation=created.mapping.mapping_generation,
    )
    second = service.revoke(
        event,
        expected_generation=created.mapping.mapping_generation,
    )
    assert first == second


def test_binding_revision_change_fences_mapping(tmp_path: Path) -> None:
    target = _target_fixture(tmp_path)
    service = AppPrincipalMappingService(tmp_path)
    event = _event()
    service.provision(event, resolve_target=lambda _: target)

    updated = update_binding(
        tmp_path,
        universe_id=target.universe_id,
        binding_id=target.agent_binding_id,
        expected_revision=target.binding_revision,
        updated_by=target.subject_id,
        payload={"schema_version": 1, "name": "Founder binding", "model": "new-model"},
    )
    assert updated["revision"] == target.binding_revision + 1
    with pytest.raises(AppPrincipalStaleError):
        service.resolve(event)


def test_conflicting_target_does_not_replace_active_mapping(tmp_path: Path) -> None:
    first = _target_fixture(tmp_path)
    second = _target_fixture(tmp_path, subject="U0987654321", universe="u-other")
    service = AppPrincipalMappingService(tmp_path)
    event = _event()
    service.provision(event, resolve_target=lambda _: first)

    with pytest.raises(AppPrincipalMappingConflict):
        service.provision(event, resolve_target=lambda _: second)
    assert service.resolve(event).universe_id == first.universe_id


def test_same_target_concurrent_provisioning_has_one_active_record(tmp_path: Path) -> None:
    target = _target_fixture(tmp_path)
    event = _event()

    def run_once():
        return AppPrincipalMappingService(tmp_path).provision(
            event,
            resolve_target=lambda _: target,
        ).mapping.mapping_id

    with ThreadPoolExecutor(max_workers=16) as pool:
        mapping_ids = list(pool.map(lambda _: run_once(), range(64)))
    assert len(set(mapping_ids)) == 1


def test_missing_target_fails_closed_without_mapping(tmp_path: Path) -> None:
    service = AppPrincipalMappingService(tmp_path)
    with pytest.raises(AppPrincipalEvidenceError):
        service.provision(_event(), resolve_target=lambda _: None)


def test_corrupt_mapping_record_cannot_be_resolved(tmp_path: Path) -> None:
    target = _target_fixture(tmp_path)
    service = AppPrincipalMappingService(tmp_path)
    event = _event()
    service.provision(event, resolve_target=lambda _: target)

    with service.store.connection() as conn:
        conn.execute(
            "UPDATE app_principal_mappings SET record_json = ?",
            ('{"status":"active"}',),
        )
    with pytest.raises(AppPrincipalMappingIntegrityError):
        service.resolve(event)
