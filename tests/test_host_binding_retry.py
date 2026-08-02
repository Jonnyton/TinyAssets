from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.xfail(
    strict=True,
    reason="RED contract: durable host-principal storage is OpenSpec task 3.2",
)

ISSUER = "https://example.authkit.app"
SUBJECT = "user_01HOSTOWNER"
OTHER_SUBJECT = "user_01OTHER"
KEY = "thumbprint:device-a"
BODY = "sha256:" + "ab" * 32


@dataclass
class _Clock:
    value: datetime = datetime(2026, 8, 1, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value


@pytest.fixture
def enrollment_module():
    try:
        return importlib.import_module("tinyassets.storage.host_principals")
    except ModuleNotFoundError:

        class _MissingEnrollmentModule:
            def __getattr__(self, _name: str):
                pytest.fail("durable host-principal storage is not implemented")

        return _MissingEnrollmentModule()


def _challenge(
    store,
    clock: _Clock,
    *,
    challenge_id: str,
    subject: str = SUBJECT,
    key_thumbprint: str = KEY,
    idempotency_key_hash: str = "hmac:idempotency-a",
    intent_digest: str = BODY,
) -> None:
    store.create_enrollment_challenge(
        issuer=ISSUER,
        subject=subject,
        challenge_id=challenge_id,
        key_thumbprint=key_thumbprint,
        idempotency_key_hash=idempotency_key_hash,
        intent_digest=intent_digest,
        expires_at=clock() + timedelta(minutes=5),
    )


def _commit(
    store,
    *,
    challenge_id: str,
    subject: str = SUBJECT,
    key_thumbprint: str = KEY,
    idempotency_key_hash: str = "hmac:idempotency-a",
    intent_digest: str = BODY,
    fault_hook=None,
):
    return store.commit_enrollment(
        issuer=ISSUER,
        subject=subject,
        challenge_id=challenge_id,
        key_thumbprint=key_thumbprint,
        idempotency_key_hash=idempotency_key_hash,
        intent_digest=intent_digest,
        fault_hook=fault_hook,
    )


def test_response_loss_retry_requires_fresh_challenge_and_returns_one_result(
    tmp_path,
    enrollment_module,
) -> None:
    clock = _Clock()
    store = enrollment_module.HostPrincipalStore(tmp_path, clock=clock)
    _challenge(store, clock, challenge_id="challenge-1")

    def lose_response(step: str) -> None:
        if step == "after_commit":
            raise ConnectionError("response lost")

    with pytest.raises(ConnectionError, match="response lost"):
        _commit(store, challenge_id="challenge-1", fault_hook=lose_response)

    _challenge(store, clock, challenge_id="challenge-2")
    recovered = _commit(store, challenge_id="challenge-2")
    assert recovered.idempotent_replay is True

    with pytest.raises(enrollment_module.HostBindingRefused):
        _commit(store, challenge_id="challenge-1")


def test_precommit_crash_consumes_neither_challenge_nor_principal(
    tmp_path,
    enrollment_module,
) -> None:
    clock = _Clock()
    store = enrollment_module.HostPrincipalStore(tmp_path, clock=clock)
    _challenge(store, clock, challenge_id="challenge-1")

    def crash_before_commit(step: str) -> None:
        if step == "before_commit":
            raise RuntimeError("database process crashed")

    with pytest.raises(RuntimeError, match="database process crashed"):
        _commit(store, challenge_id="challenge-1", fault_hook=crash_before_commit)

    committed = _commit(store, challenge_id="challenge-1")
    assert committed.host_principal_generation == 1
    assert committed.idempotent_replay is False


def test_same_idempotency_scope_with_changed_body_conflicts_without_mutation(
    tmp_path,
    enrollment_module,
) -> None:
    clock = _Clock()
    store = enrollment_module.HostPrincipalStore(tmp_path, clock=clock)
    _challenge(store, clock, challenge_id="challenge-1")
    committed = _commit(store, challenge_id="challenge-1")

    changed_body = "sha256:" + "cd" * 32
    _challenge(
        store,
        clock,
        challenge_id="challenge-2",
        intent_digest=changed_body,
    )
    with pytest.raises(enrollment_module.HostBindingConflict) as raised:
        _commit(store, challenge_id="challenge-2", intent_digest=changed_body)
    assert raised.value.status_code == 409

    _challenge(store, clock, challenge_id="challenge-3")
    replay = _commit(store, challenge_id="challenge-3")
    assert replay.host_principal_id == committed.host_principal_id
    assert replay.idempotent_replay is True


def test_idempotency_result_expires_after_24_hours_and_grants_no_authority(
    tmp_path,
    enrollment_module,
) -> None:
    clock = _Clock()
    store = enrollment_module.HostPrincipalStore(tmp_path, clock=clock)
    _challenge(store, clock, challenge_id="challenge-1")
    original = _commit(store, challenge_id="challenge-1")

    clock.value += timedelta(hours=24, seconds=1)
    store.purge_expired()
    _challenge(store, clock, challenge_id="challenge-2")
    after_expiry = _commit(store, challenge_id="challenge-2")

    assert after_expiry.host_principal_id == original.host_principal_id
    assert after_expiry.idempotent_replay is False


def test_server_instances_converge_on_one_same_subject_key_winner(
    tmp_path,
    enrollment_module,
) -> None:
    clock = _Clock()
    stores = [
        enrollment_module.HostPrincipalStore(tmp_path, clock=clock),
        enrollment_module.HostPrincipalStore(tmp_path, clock=clock),
    ]
    for index in range(8):
        _challenge(
            stores[index % 2],
            clock,
            challenge_id=f"challenge-{index}",
            idempotency_key_hash=f"hmac:idempotency-{index}",
        )

    def enroll(index: int):
        return _commit(
            stores[index % 2],
            challenge_id=f"challenge-{index}",
            idempotency_key_hash=f"hmac:idempotency-{index}",
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(enroll, range(8)))

    assert {result.host_principal_id for result in results} == {results[0].host_principal_id}
    assert {result.host_principal_generation for result in results} == {1}


def test_distinct_device_keys_create_distinct_principals_for_one_subject(
    tmp_path,
    enrollment_module,
) -> None:
    clock = _Clock()
    store = enrollment_module.HostPrincipalStore(tmp_path, clock=clock)
    results = []
    for index, key_thumbprint in enumerate(("thumbprint:device-a", "thumbprint:device-b")):
        _challenge(
            store,
            clock,
            challenge_id=f"challenge-{index}",
            key_thumbprint=key_thumbprint,
            idempotency_key_hash=f"hmac:idempotency-{index}",
        )
        results.append(
            _commit(
                store,
                challenge_id=f"challenge-{index}",
                key_thumbprint=key_thumbprint,
                idempotency_key_hash=f"hmac:idempotency-{index}",
            )
        )

    assert results[0].host_principal_id != results[1].host_principal_id
    assert {result.host_principal_generation for result in results} == {1}


def test_cross_subject_key_reuse_has_one_non_enumerating_refusal_shape(
    tmp_path,
    enrollment_module,
) -> None:
    clock = _Clock()
    store = enrollment_module.HostPrincipalStore(tmp_path, clock=clock)
    _challenge(store, clock, challenge_id="challenge-owner")
    _commit(store, challenge_id="challenge-owner")

    _challenge(
        store,
        clock,
        challenge_id="challenge-other",
        subject=OTHER_SUBJECT,
        idempotency_key_hash="hmac:idempotency-other",
    )
    with pytest.raises(enrollment_module.HostBindingRefused) as raised:
        _commit(
            store,
            challenge_id="challenge-other",
            subject=OTHER_SUBJECT,
            idempotency_key_hash="hmac:idempotency-other",
        )

    assert str(raised.value) == "host binding refused"
    assert raised.value.public_error == enrollment_module.HOST_BINDING_REFUSAL
    assert "user_" not in repr(raised.value.public_error)
