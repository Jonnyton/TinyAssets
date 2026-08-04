from __future__ import annotations

import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from tinyassets.api import cloud_automations, permissions
from tinyassets.provider_work_authority import ProviderWorkBindingRoot
from tinyassets.provider_work_enrollment import RequesterProviderEnrollmentResolver
from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore

NOW = datetime(2027, 1, 1, tzinfo=timezone.utc)


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def _entry(
    *, owner: str = "user_alice", universe: str = "universe_alice", provider: str = "codex"
) -> dict[str, object]:
    return {
        "owner_user_id": owner,
        "universe_id": universe,
        "provider": provider,
        "credential_reference_digest": _digest("credential"),
        "allowed_operations": ["repository_spec_delivery"],
        "allowed_roles": ["writer"],
        "assignment_generation": 1,
        "assignment_digest": _digest("assignment"),
        "max_invocations": 2,
        "max_tokens": 1000,
        "max_cost_microunits": 10,
        "expires_at": "2027-01-02T00:00:00Z",
    }


def test_resolver_requires_exact_nonexpired_entry(monkeypatch) -> None:
    monkeypatch.setenv("TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON", json.dumps([_entry()]))
    resolver = RequesterProviderEnrollmentResolver.from_environment(now=NOW)
    root = ProviderWorkBindingRoot("user_alice", "universe_alice", "codex")
    assert resolver.resolve(root) is not None
    assert resolver.resolve(ProviderWorkBindingRoot("user_bob", "universe_alice", "codex")) is None
    assert resolver.providers(
        owner_user_id="user_alice", universe_id="universe_alice"
    ) == ("codex",)


def test_fingerprint_entry_materializes_authenticated_subject(monkeypatch) -> None:
    key = "k" * 32
    subject = "user_not_visible_in_chat"
    monkeypatch.setenv("TINYASSETS_IDENTITY_FINGERPRINT_KEY", key)
    fingerprint = "v1:" + hmac.new(
        key.encode(),
        f"tinyassets:request-identity:v1\0{subject}".encode(),
        hashlib.sha256,
    ).hexdigest()
    monkeypatch.setenv(
        "TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON",
        json.dumps([_entry(owner=fingerprint)]),
    )
    resolver = RequesterProviderEnrollmentResolver.from_environment(now=NOW)
    seed = resolver.resolve(ProviderWorkBindingRoot(subject, "universe_alice", "codex"))
    assert seed is not None
    assert seed.owner_user_id == subject
    assert resolver.providers(owner_user_id=subject, universe_id="universe_alice") == ("codex",)


def test_invalid_or_duplicate_manifest_fails_closed(monkeypatch) -> None:
    invalid = _entry()
    invalid["unexpected"] = "nope"
    duplicate = [_entry(), _entry()]
    monkeypatch.setenv("TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON", json.dumps([invalid]))
    assert RequesterProviderEnrollmentResolver.from_environment(now=NOW).providers(
        owner_user_id="user_alice", universe_id="universe_alice"
    ) == ()
    monkeypatch.setenv("TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON", json.dumps(duplicate))
    assert RequesterProviderEnrollmentResolver.from_environment(now=NOW).resolve(
        ProviderWorkBindingRoot("user_alice", "universe_alice", "codex")
    ) is None


def test_phone_bind_uses_authenticated_actor_and_redacts_manifest(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON", json.dumps([_entry()]))
    monkeypatch.setattr(cloud_automations, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "user_alice")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda _uid, write: True)

    result = cloud_automations.cloud_automations(
        action="bind_provider",
        universe_id="universe_alice",
        payload={
            "provider": "codex",
            "owner_user_id": "user_attacker",
            "max_tokens": 999999999,
            "credential_reference": "raw-secret-never-accepted",
        },
    )
    assert result["status"] == "provider_bound"
    assert result["binding"]["provider"] == "codex"
    assert "credential_reference_digest" not in result["binding"]
    assert "raw-secret-never-accepted" not in json.dumps(result)

    binding_id = result["binding"]["binding_id"]
    binding = SQLiteProviderWorkAuthorityStore(tmp_path).get(binding_id)
    assert binding is not None
    assert binding.owner_user_id == "user_alice"
    replay = cloud_automations.cloud_automations(
        action="reconcile_provider",
        universe_id="universe_alice",
        payload={"provider": "codex"},
    )
    assert replay["binding"]["binding_id"] == binding_id
    assert replay["outcome"] == "replayed"


def test_phone_bind_without_enrollment_does_not_write(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON", raising=False)
    monkeypatch.setattr(cloud_automations, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "user_alice")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda _uid, write: True)
    result = cloud_automations.cloud_automations(
        action="bind_provider",
        universe_id="universe_alice",
        payload={"provider": "codex"},
    )
    assert result["error"] == "provider_binding_setup_required"
    assert SQLiteProviderWorkAuthorityStore(tmp_path).list_bindings(
        owner_user_id="user_alice", universe_id="universe_alice"
    ) == []


def test_concurrent_binders_converge_on_one_binding(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(
        "TINYASSETS_REQUESTER_PROVIDER_ENROLLMENTS_JSON", json.dumps([_entry()])
    )
    monkeypatch.setattr(cloud_automations, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "user_alice")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda _uid, write: True)

    def bind() -> dict[str, object]:
        return cloud_automations.cloud_automations(
            action="bind_provider",
            universe_id="universe_alice",
            payload={"provider": "codex"},
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _index: bind(), range(8)))
    assert len({result["binding"]["binding_id"] for result in results}) == 1
    assert len(
        SQLiteProviderWorkAuthorityStore(tmp_path).list_bindings(
            owner_user_id="user_alice", universe_id="universe_alice"
        )
    ) == 1
