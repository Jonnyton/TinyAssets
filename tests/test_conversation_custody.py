from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest


def _custody():
    return importlib.import_module("tinyassets.conversation_custody")


def _evidence(
    custody,
    root: Path,
    universe: Path,
    *,
    action: str = "read_thread",
    request_digest: str = "sha256:" + "a" * 64,
    key_digest: str | None = None,
):
    return custody.ConversationCustodyGrantEvidence(
        action=action,
        request_digest=request_digest,
        idempotency_key_digest=key_digest,
        owner_user_id="owner_1",
        universe_id="universe_1",
        agent_binding_id="agent_binding_1",
        custody_mode="private_universe",
        selection_generation=1,
        registered_universe_path=str(universe.resolve()),
        platform_data_root=str(root.resolve()),
        issued_at="2026-08-03T12:00:00.000000Z",
        expires_at="2026-08-03T12:05:00.000000Z",
    )


def _grant(custody, evidence, *, current: bool = True):
    return custody._issue_operation_grant(  # noqa: SLF001 - explicit dark test issuer
        evidence,
        live_check=lambda observed: current and observed == evidence,
    )


def test_operation_grant_is_exact_and_single_use(tmp_path: Path) -> None:
    custody = _custody()
    root = tmp_path / "data"
    universe = root / "universe_1"
    universe.mkdir(parents=True)
    evidence = _evidence(custody, root, universe)
    grant = _grant(custody, evidence)

    consumed = custody.consume_operation_grant(
        grant,
        expected_action="read_thread",
        expected_request_digest="sha256:" + "a" * 64,
        expected_idempotency_key_digest=None,
        now="2026-08-03T12:01:00.000000Z",
    )

    assert consumed == evidence
    with pytest.raises(custody.ConversationCustodyAuthorizationError) as replay:
        custody.consume_operation_grant(
            grant,
            expected_action="read_thread",
            expected_request_digest="sha256:" + "a" * 64,
            expected_idempotency_key_digest=None,
            now="2026-08-03T12:01:01.000000Z",
        )
    assert replay.value.code == "grant_consumed"


def test_mismatched_grant_is_consumed_without_opening_storage(tmp_path: Path) -> None:
    custody = _custody()
    root = tmp_path / "data"
    universe = root / "universe_1"
    universe.mkdir(parents=True)
    evidence = _evidence(custody, root, universe)
    grant = _grant(custody, evidence)

    with pytest.raises(custody.ConversationCustodyAuthorizationError) as mismatch:
        custody.consume_operation_grant(
            grant,
            expected_action="export_thread",
            expected_request_digest=evidence.request_digest,
            expected_idempotency_key_digest=None,
            now="2026-08-03T12:01:00.000000Z",
        )
    assert mismatch.value.code == "grant_mismatch"
    assert not (universe / ".tinyassets.db").exists()

    with pytest.raises(custody.ConversationCustodyAuthorizationError) as replay:
        custody.consume_operation_grant(
            grant,
            expected_action="read_thread",
            expected_request_digest=evidence.request_digest,
            expected_idempotency_key_digest=None,
            now="2026-08-03T12:01:01.000000Z",
        )
    assert replay.value.code == "grant_consumed"


@pytest.mark.parametrize(
    ("now", "current", "expected_code"),
    [
        ("2026-08-03T12:05:00.000001Z", True, "grant_expired"),
        ("2026-08-03T12:01:00.000000Z", False, "grant_revoked"),
    ],
)
def test_expired_or_revoked_grant_fails_closed(
    tmp_path: Path,
    now: str,
    current: bool,
    expected_code: str,
) -> None:
    custody = _custody()
    root = tmp_path / "data"
    universe = root / "universe_1"
    universe.mkdir(parents=True)
    evidence = _evidence(custody, root, universe)

    with pytest.raises(custody.ConversationCustodyAuthorizationError) as blocked:
        custody.consume_operation_grant(
            _grant(custody, evidence, current=current),
            expected_action=evidence.action,
            expected_request_digest=evidence.request_digest,
            expected_idempotency_key_digest=None,
            now=now,
        )
    assert blocked.value.code == expected_code
    assert not (universe / ".tinyassets.db").exists()


def test_read_grant_requires_null_key_and_mutation_requires_digest(tmp_path: Path) -> None:
    custody = _custody()
    root = tmp_path / "data"
    universe = root / "universe_1"
    universe.mkdir(parents=True)

    with pytest.raises(custody.ConversationCustodyValidationError):
        _evidence(
            custody,
            root,
            universe,
            action="read_thread",
            key_digest="sha256:" + "b" * 64,
        )
    with pytest.raises(custody.ConversationCustodyValidationError):
        _evidence(custody, root, universe, action="create_thread", key_digest=None)


def test_registered_universe_allows_missing_sqlite_files(tmp_path: Path) -> None:
    custody = _custody()
    root = tmp_path / "data"
    universe = root / "universe_1"
    universe.mkdir(parents=True)
    evidence = _evidence(custody, root, universe)

    consumed = custody.consume_operation_grant(
        _grant(custody, evidence),
        expected_action=evidence.action,
        expected_request_digest=evidence.request_digest,
        expected_idempotency_key_digest=None,
        now="2026-08-03T12:01:00.000000Z",
    )

    assert consumed.registered_universe_path == str(universe.resolve())
    assert not (universe / ".tinyassets.db").exists()


def test_platform_root_or_missing_universe_is_refused(tmp_path: Path) -> None:
    custody = _custody()
    root = tmp_path / "data"
    root.mkdir()

    for universe in (root, root / "missing"):
        evidence = _evidence(custody, root, universe)
        with pytest.raises(custody.ConversationCustodyAuthorizationError) as blocked:
            custody.consume_operation_grant(
                _grant(custody, evidence),
                expected_action=evidence.action,
                expected_request_digest=evidence.request_digest,
                expected_idempotency_key_digest=None,
                now="2026-08-03T12:01:00.000000Z",
            )
        assert blocked.value.code == "storage_location_invalid"


def test_hard_linked_database_is_refused(tmp_path: Path) -> None:
    custody = _custody()
    root = tmp_path / "data"
    universe = root / "universe_1"
    universe.mkdir(parents=True)
    outside = tmp_path / "outside.db"
    outside.write_bytes(b"not a custody database")
    try:
        os.link(outside, universe / ".tinyassets.db")
    except OSError as exc:  # pragma: no cover - unsupported filesystem
        pytest.skip(f"hard links unavailable: {exc}")
    evidence = _evidence(custody, root, universe)

    with pytest.raises(custody.ConversationCustodyAuthorizationError) as blocked:
        custody.consume_operation_grant(
            _grant(custody, evidence),
            expected_action=evidence.action,
            expected_request_digest=evidence.request_digest,
            expected_idempotency_key_digest=None,
            now="2026-08-03T12:01:00.000000Z",
        )
    assert blocked.value.code == "storage_location_invalid"
