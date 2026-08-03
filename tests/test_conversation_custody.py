from __future__ import annotations

import base64
import importlib
import multiprocessing
import os
import sqlite3
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import pytest


def _custody():
    return importlib.import_module("tinyassets.conversation_custody")


def _storage():
    return importlib.import_module("tinyassets.storage.conversation_custody")


def _scope(custody, *, universe_id: str = "universe_1"):
    return custody.ConversationCustodyScope(
        owner_user_id="owner_1",
        universe_id=universe_id,
        agent_binding_id="agent_binding_1",
    )


def _key(value: int) -> str:
    encoded = base64.urlsafe_b64encode(bytes([value]) * 32).decode("ascii").rstrip("=")
    return f"ik_{encoded}"


def _process_create_thread(args: tuple[str, str, str]) -> str:
    root_raw, universe_raw, key = args
    custody = _custody()
    storage = _storage()
    root = Path(root_raw)
    universe = Path(universe_raw)
    return storage.create_thread(
        _create_grant(
            custody,
            root,
            universe,
            interlocutor_ref="slack:user_1",
            key=key,
        ),
        scope=_scope(custody),
        idempotency_key=key,
        interlocutor_ref="slack:user_1",
        retention_until=None,
        now="2026-08-03T12:01:00.000000Z",
    ).conversation_id


def _process_append_reply(args: tuple[str, str, str, str, str, int]) -> tuple[int, str]:
    root_raw, universe_raw, conversation_id, reply_to_message_id, key, index = args
    custody = _custody()
    storage = _storage()
    root = Path(root_raw)
    universe = Path(universe_raw)
    payload = {"process": index}
    message = storage.append_message(
        _append_grant(
            custody,
            root,
            universe,
            conversation_id=conversation_id,
            key=key,
            payload=payload,
            reply_to_message_id=reply_to_message_id,
        ),
        scope=_scope(custody),
        idempotency_key=key,
        conversation_id=conversation_id,
        kind="text",
        participant_ref="slack:user_1",
        source_event_ref="slack:event_1",
        payload=payload,
        reply_to_message_id=reply_to_message_id,
        now="2026-08-03T12:01:02.000000Z",
    )
    return message.ordinal, message.reply_to_message_id


def _evidence(
    custody,
    root: Path,
    universe: Path,
    *,
    action: str = "read_thread",
    request_digest: str = "sha256:" + "a" * 64,
    key_digest: str | None = None,
    scope=None,
):
    selected_scope = scope or _scope(custody)
    return custody.ConversationCustodyGrantEvidence(
        action=action,
        request_digest=request_digest,
        idempotency_key_digest=key_digest,
        owner_user_id=selected_scope.owner_user_id,
        universe_id=selected_scope.universe_id,
        agent_binding_id=selected_scope.agent_binding_id,
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


def test_grant_cannot_be_consumed_before_its_issue_time(tmp_path: Path) -> None:
    custody = _custody()
    root = tmp_path / "platform"
    universe = root / "universes" / "u1"
    universe.mkdir(parents=True)
    evidence = _evidence(custody, root, universe)

    with pytest.raises(custody.ConversationCustodyAuthorizationError) as blocked:
        custody.consume_operation_grant(
            _grant(custody, evidence),
            expected_action=evidence.action,
            expected_request_digest=evidence.request_digest,
            expected_idempotency_key_digest=None,
            now="2026-08-03T11:59:59.999999Z",
        )
    assert blocked.value.code == "grant_not_yet_valid"
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


def test_existing_database_identity_is_stable_while_sidecars_may_transition(
    tmp_path: Path,
) -> None:
    custody = _custody()
    root = tmp_path / "platform"
    universe = root / "universes" / "u1"
    universe.mkdir(parents=True)
    evidence = _evidence(custody, root, universe)
    database = universe / ".tinyassets.db"
    database.write_bytes(b"first")

    initial = custody.validate_private_universe_location(evidence)
    assert initial.primary_identity is not None
    wal = universe / ".tinyassets.db-wal"
    wal.write_bytes(b"transient")
    custody.validate_private_universe_location(
        evidence,
        expected_primary_identity=initial.primary_identity,
    )
    wal.unlink()
    custody.validate_private_universe_location(
        evidence,
        expected_primary_identity=initial.primary_identity,
    )

    database.unlink()
    database.write_bytes(b"replacement")
    with pytest.raises(custody.ConversationCustodyAuthorizationError) as blocked:
        custody.validate_private_universe_location(
            evidence,
            expected_primary_identity=initial.primary_identity,
        )
    assert blocked.value.code == "storage_location_invalid"


def test_canonical_json_has_exact_bytes_and_preserves_unknown_members() -> None:
    custody = _custody()
    left = {"z": [True, None, -7], "a": {"unknown": "hello\nworld"}}
    right = {"a": {"unknown": "hello\nworld"}, "z": [True, None, -7]}
    expected = b'{"a":{"unknown":"hello\\nworld"},"z":[true,null,-7]}'

    assert custody.canonical_json_bytes(left) == expected
    assert custody.canonical_json_bytes(right) == expected
    assert custody.canonical_json_digest(left) == (
        "sha256:f43b6adc1f8bc1176ac226c62730f59de4d9ed29d68565c090c2735000f7cc9d"
    )


@pytest.mark.parametrize(
    "payload",
    [
        "raw-json-text",
        {"value": 1.5},
        {"value": 2**63},
        {"value": "e\u0301"},
        {"value": "\ud800"},
        {1: "non-string-key"},
        {"k" * 257: "too-long-key"},
        {"value": "x" * 32_769},
        {f"key_{index}": index for index in range(129)},
        {"items": list(range(257))},
        {"left": "x" * 32_768, "right": "y" * 32_768},
    ],
)
def test_canonical_json_rejects_ambiguous_or_oversized_values(payload: object) -> None:
    custody = _custody()

    with pytest.raises(custody.ConversationCustodyValidationError):
        custody.canonical_json_bytes(payload)


def test_canonical_json_depth_counts_root_at_zero() -> None:
    custody = _custody()
    accepted: object = "leaf"
    for _ in range(15):
        accepted = [accepted]
    custody.canonical_json_bytes({"value": accepted})

    rejected: object = [accepted]
    with pytest.raises(custody.ConversationCustodyValidationError):
        custody.canonical_json_bytes({"value": rejected})


def test_canonical_json_node_count_and_escape_boundaries_are_exact() -> None:
    custody = _custody()
    exact_4096 = [[0] * 255 for _ in range(15)] + [[0] * 253]
    custody.canonical_json_bytes({"batches": exact_4096})
    exact_4096[-1].append(0)
    with pytest.raises(custody.ConversationCustodyValidationError):
        custody.canonical_json_bytes({"batches": exact_4096})

    assert (
        custody.canonical_json_bytes({"controls": '"\\\b\t\n\f\r\x00\x1f/é'})
        == '{"controls":"\\"\\\\\\b\\t\\n\\f\\r\\u0000\\u001f/é"}'.encode()
    )


def test_canonical_json_rejects_custom_container_and_scalar_types() -> None:
    custody = _custody()

    class CustomMapping(dict):
        pass

    class CustomString(str):
        pass

    for payload in (CustomMapping(value=1), {"value": CustomString("text")}):
        with pytest.raises(custody.ConversationCustodyValidationError):
            custody.canonical_json_bytes(payload)


def test_idempotency_key_wire_and_digest_are_canonical() -> None:
    custody = _custody()
    key = "ik_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

    assert custody.idempotency_key_digest(key) == (
        "sha256:7c02713014568e7c6a23ccce8e98f0d6e165f7f779f274859610460060faf803"
    )
    for invalid in (
        "A" * 43,
        "ik_" + "A" * 42,
        "ik_" + "A" * 42 + "=",
        "ik_" + "A" * 42 + "+",
        "ik_" + "A" * 42 + "B",  # non-canonical trailing pad bits
    ):
        with pytest.raises(custody.ConversationCustodyValidationError):
            custody.idempotency_key_digest(invalid)


def test_operation_request_digest_vectors_match_contract() -> None:
    custody = _custody()
    scope = custody.ConversationCustodyScope(
        owner_user_id="owner_1",
        universe_id="universe_1",
        agent_binding_id="agent_binding_1",
    )

    assert (
        custody.create_thread_request_digest(
            scope,
            interlocutor_ref="interlocutor_1",
            retention_until="2030-01-02T03:04:05.000006Z",
        )
        == "sha256:2e16d89e186ea01130b06c77c544394f1bdc84159d7fd816419acd65826dd78f"
    )
    assert (
        custody.append_message_request_digest(
            scope,
            conversation_id="conversation_1",
            kind="text",
            participant_ref="participant_1",
            source_event_ref="event_1",
            payload={"text": "hello\nworld"},
            reply_to_message_id=None,
        )
        == "sha256:03d0dce3eba96d9efa1c8bf8ab383c90a2724c6c6e4a935201653649805fc3d5"
    )
    assert (
        custody.thread_request_digest("read_thread", scope, conversation_id="conversation_1")
        == "sha256:6b9114c5a4161548e7bca566a340d73f7ddab83c21527f53a375c2c47531b143"
    )
    assert (
        custody.thread_request_digest("export_thread", scope, conversation_id="conversation_1")
        == "sha256:f0d5c9697fbac581b93f42a4c52750388e1cb8c825fe653d52d2e91b902bef42"
    )
    assert custody.deleted_target_digest(scope, conversation_id="conversation_1") == (
        "sha256:1720128239c73ade4c587c137126e013dde5617751676294b5029815154cc1f5"
    )
    assert (
        custody.delete_thread_request_digest(
            scope,
            conversation_id="conversation_1",
            reason="owner_request",
        )
        == "sha256:a326ce1489645ec9083d739e9a27bfb2c88870a63cf7e833877b77a59acb00be"
    )


def test_request_digest_validation_rejects_noncanonical_metadata() -> None:
    custody = _custody()
    scope = custody.ConversationCustodyScope(
        owner_user_id="owner_1",
        universe_id="universe_1",
        agent_binding_id="agent_binding_1",
    )

    with pytest.raises(custody.ConversationCustodyValidationError):
        custody.create_thread_request_digest(
            scope,
            interlocutor_ref="bad ref",
            retention_until=None,
        )
    with pytest.raises(custody.ConversationCustodyValidationError):
        custody.append_message_request_digest(
            scope,
            conversation_id="conversation_1",
            kind="Text",
            participant_ref="participant_1",
            source_event_ref="event_1",
            payload={"text": "hello"},
            reply_to_message_id=None,
        )
    with pytest.raises(custody.ConversationCustodyValidationError):
        custody.delete_thread_request_digest(
            scope,
            conversation_id="conversation_1",
            reason="other",
        )


def test_metadata_ref_kind_and_timestamp_boundaries_are_exact() -> None:
    custody = _custody()
    scope = custody.ConversationCustodyScope(
        owner_user_id="o" + "x" * 255,
        universe_id="universe_1",
        agent_binding_id="agent_binding_1",
    )
    custody.create_thread_request_digest(
        scope,
        interlocutor_ref="i" + "x" * 255,
        retention_until="2030-01-02T03:04:05.000006Z",
    )
    custody.append_message_request_digest(
        scope,
        conversation_id="conversation_1",
        kind="a" + "x" * 63,
        participant_ref="participant_1",
        source_event_ref="event_1",
        payload={},
        reply_to_message_id=None,
    )

    with pytest.raises(custody.ConversationCustodyValidationError):
        custody.ConversationCustodyScope(
            owner_user_id="o" + "x" * 256,
            universe_id="universe_1",
            agent_binding_id="agent_binding_1",
        )
    with pytest.raises(custody.ConversationCustodyValidationError):
        custody.append_message_request_digest(
            scope,
            conversation_id="conversation_1",
            kind="a" + "x" * 64,
            participant_ref="participant_1",
            source_event_ref="event_1",
            payload={},
            reply_to_message_id=None,
        )
    for invalid_time in (
        "2030-01-02T03:04:05Z",
        "2030-01-02T03:04:05.00000Z",
        "2030-01-02T03:04:05.0000000Z",
        "2030-01-02T03:04:05.000006+00:00",
        "2030-01-02T03:04:60.000006Z",
        "2030-02-30T03:04:05.000006Z",
    ):
        with pytest.raises(custody.ConversationCustodyValidationError):
            custody.create_thread_request_digest(
                scope,
                interlocutor_ref="interlocutor_1",
                retention_until=invalid_time,
            )


def _thread(custody):
    return custody.ConversationThread(
        conversation_id="conversation_1",
        owner_user_id="owner_1",
        universe_id="universe_1",
        agent_binding_id="agent_binding_1",
        interlocutor_ref="slack:user_1",
        retention_until="2030-01-02T03:04:05.000006Z",
        created_at="2026-08-03T12:00:00.000001Z",
    )


def _message(custody, *, ordinal: int = 1, reply_to_message_id: str | None = None):
    return custody.ConversationMessage(
        conversation_id="conversation_1",
        message_id=f"message_{ordinal}",
        ordinal=ordinal,
        kind="text",
        participant_ref="slack:user_1" if ordinal == 1 else "agent:agent_binding_1",
        source_event_ref=f"slack:event_{ordinal}",
        payload={"text": "hello" if ordinal == 1 else "hi", "unknown": [1, True]},
        reply_to_message_id=reply_to_message_id,
        created_at=f"2026-08-03T12:00:0{ordinal}.00000{ordinal}Z",
    )


def test_thread_and_message_records_are_immutable_and_payload_is_detached() -> None:
    custody = _custody()
    payload = {"nested": {"items": [1, 2]}}
    message = custody.ConversationMessage(
        conversation_id="conversation_1",
        message_id="message_1",
        ordinal=1,
        kind="text",
        participant_ref="slack:user_1",
        source_event_ref="slack:event_1",
        payload=payload,
        reply_to_message_id=None,
        created_at="2026-08-03T12:00:01.000001Z",
    )
    payload["nested"]["items"].append(3)

    assert message.payload == {"nested": {"items": (1, 2)}}
    assert message.payload_digest == (
        "sha256:107bb99f37f332725c2b986d24cddf07e3c104989e28673e5132012eb651324a"
    )
    with pytest.raises((AttributeError, TypeError)):
        message.kind = "edited"
    with pytest.raises(TypeError):
        message.payload["nested"] = {}


@pytest.mark.parametrize(
    "factory",
    [
        lambda custody: custody.ConversationThread(
            conversation_id="bad ref",
            owner_user_id="owner_1",
            universe_id="universe_1",
            agent_binding_id="agent_binding_1",
            interlocutor_ref="slack:user_1",
            retention_until=None,
            created_at="2026-08-03T12:00:00.000001Z",
        ),
        lambda custody: custody.ConversationThread(
            conversation_id="conversation_1",
            owner_user_id="owner_1",
            universe_id="universe_1",
            agent_binding_id="agent_binding_1",
            interlocutor_ref="slack:user_1",
            retention_until=None,
            created_at="2026-08-03T12:00:00Z",
        ),
        lambda custody: custody.ConversationMessage(
            conversation_id="conversation_1",
            message_id="message_1",
            ordinal=True,
            kind="Text",
            participant_ref="slack:user_1",
            source_event_ref="slack:event_1",
            payload={},
            reply_to_message_id=None,
            created_at="2026-08-03T12:00:01.000001Z",
        ),
    ],
)
def test_records_reject_noncanonical_metadata(factory) -> None:
    custody = _custody()

    with pytest.raises(custody.ConversationCustodyValidationError):
        factory(custody)


def test_export_is_exact_deterministic_and_digest_is_separate() -> None:
    custody = _custody()
    thread = _thread(custody)
    messages = (
        _message(custody),
        _message(custody, ordinal=2, reply_to_message_id="message_1"),
    )

    first = custody.export_conversation(thread, messages)
    second = custody.export_conversation(thread, messages)

    expected = (
        b'{"canonical_json":"tinyassets-canonical-json/v1","custody_mode":"private_universe",'
        b'"messages":[{"created_at":"2026-08-03T12:00:01.000001Z","kind":"text",'
        b'"message_id":"message_1","ordinal":1,"participant_ref":"slack:user_1",'
        b'"payload":{"text":"hello","unknown":[1,true]},'
        b'"payload_digest":"sha256:4f2111c5f527321f6cc054e6c1058ee25cfebf12f7764b248463378e5d577adc",'
        b'"reply_to_message_id":null,"source_event_ref":"slack:event_1"},'
        b'{"created_at":"2026-08-03T12:00:02.000002Z","kind":"text",'
        b'"message_id":"message_2","ordinal":2,"participant_ref":"agent:agent_binding_1",'
        b'"payload":{"text":"hi","unknown":[1,true]},'
        b'"payload_digest":"sha256:9f6e57e293e2f28174b45a7891799e27a90aee41441ff44e7cc63b5945a496de",'
        b'"reply_to_message_id":"message_1","source_event_ref":"slack:event_2"}],'
        b'"schema":"conversation-custody/v1","thread":{"agent_binding_id":"agent_binding_1",'
        b'"conversation_id":"conversation_1","created_at":"2026-08-03T12:00:00.000001Z",'
        b'"interlocutor_ref":"slack:user_1","owner_user_id":"owner_1",'
        b'"retention_until":"2030-01-02T03:04:05.000006Z","universe_id":"universe_1"}}'
    )
    assert first.content == expected
    assert first == second
    assert first.digest == (
        "sha256:53085850ce0e6e7c2e68ed014d0a7a84de115226a00247fef8db0a953e7c1f91"
    )
    assert b'"digest"' not in first.content


@pytest.mark.parametrize(
    "messages",
    [
        (),
        ("wrong-thread",),
        ("gap",),
        ("reply-missing",),
        ("reply-forward",),
    ],
)
def test_export_refuses_incomplete_or_invalid_message_sequences(messages) -> None:
    custody = _custody()
    thread = _thread(custody)
    cases = {
        (): (_message(custody, ordinal=2),),
        ("wrong-thread",): (
            custody.ConversationMessage(
                conversation_id="conversation_2",
                message_id="message_1",
                ordinal=1,
                kind="text",
                participant_ref="slack:user_1",
                source_event_ref="slack:event_1",
                payload={},
                reply_to_message_id=None,
                created_at="2026-08-03T12:00:01.000001Z",
            ),
        ),
        ("gap",): (_message(custody), _message(custody, ordinal=3)),
        ("reply-missing",): (
            _message(custody),
            _message(custody, ordinal=2, reply_to_message_id="message_9"),
        ),
        ("reply-forward",): (
            _message(custody, reply_to_message_id="message_2"),
            _message(custody, ordinal=2),
        ),
    }

    with pytest.raises(custody.ConversationCustodyValidationError):
        custody.export_conversation(thread, cases[messages])


def _create_grant(
    custody,
    root: Path,
    universe: Path,
    *,
    interlocutor_ref: str,
    key: str,
    scope=None,
):
    selected_scope = scope or _scope(custody)
    request_digest = custody.create_thread_request_digest(
        selected_scope,
        interlocutor_ref=interlocutor_ref,
        retention_until=None,
    )
    return _grant(
        custody,
        _evidence(
            custody,
            root,
            universe,
            action="create_thread",
            request_digest=request_digest,
            key_digest=custody.idempotency_key_digest(key),
            scope=selected_scope,
        ),
    )


def _append_grant(
    custody,
    root: Path,
    universe: Path,
    *,
    conversation_id: str,
    key: str,
    payload: dict[str, object],
    reply_to_message_id: str | None = None,
    scope=None,
):
    selected_scope = scope or _scope(custody)
    request_digest = custody.append_message_request_digest(
        selected_scope,
        conversation_id=conversation_id,
        kind="text",
        participant_ref="slack:user_1",
        source_event_ref="slack:event_1",
        payload=payload,
        reply_to_message_id=reply_to_message_id,
    )
    return _grant(
        custody,
        _evidence(
            custody,
            root,
            universe,
            action="append_message",
            request_digest=request_digest,
            key_digest=custody.idempotency_key_digest(key),
            scope=selected_scope,
        ),
    )


def _read_grant(
    custody,
    root: Path,
    universe: Path,
    *,
    conversation_id: str,
    scope=None,
):
    selected_scope = scope or _scope(custody)
    request_digest = custody.thread_request_digest(
        "read_thread",
        selected_scope,
        conversation_id=conversation_id,
    )
    return _grant(
        custody,
        _evidence(
            custody,
            root,
            universe,
            action="read_thread",
            request_digest=request_digest,
            scope=selected_scope,
        ),
    )


def test_private_store_creates_replays_and_reads_exact_thread(tmp_path: Path) -> None:
    custody = _custody()
    storage = _storage()
    root = tmp_path / "platform"
    universe = root / "universes" / "u1"
    universe.mkdir(parents=True)
    key = "ik_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

    created = storage.create_thread(
        _create_grant(custody, root, universe, interlocutor_ref="slack:user_1", key=key),
        scope=_scope(custody),
        idempotency_key=key,
        interlocutor_ref="slack:user_1",
        retention_until=None,
        now="2026-08-03T12:01:00.000000Z",
    )
    replayed = storage.create_thread(
        _create_grant(custody, root, universe, interlocutor_ref="slack:user_1", key=key),
        scope=_scope(custody),
        idempotency_key=key,
        interlocutor_ref="slack:user_1",
        retention_until=None,
        now="2026-08-03T12:01:00.000000Z",
    )
    snapshot = storage.read_thread(
        _read_grant(custody, root, universe, conversation_id=created.conversation_id),
        scope=_scope(custody),
        conversation_id=created.conversation_id,
        now="2026-08-03T12:01:01.000000Z",
    )

    assert created == replayed == snapshot.thread
    assert created.conversation_id.startswith("conversation_")
    assert created.created_at == "2026-08-03T12:01:00.000000Z"
    assert snapshot.messages == ()
    assert (universe / ".tinyassets.db").is_file()
    assert not (root / ".tinyassets.db").exists()


def test_private_store_create_idempotency_conflict_preserves_original(tmp_path: Path) -> None:
    custody = _custody()
    storage = _storage()
    root = tmp_path / "platform"
    universe = root / "universes" / "u1"
    universe.mkdir(parents=True)
    key = "ik_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    original = storage.create_thread(
        _create_grant(custody, root, universe, interlocutor_ref="slack:user_1", key=key),
        scope=_scope(custody),
        idempotency_key=key,
        interlocutor_ref="slack:user_1",
        retention_until=None,
        now="2026-08-03T12:01:00.000000Z",
    )

    with pytest.raises(storage.ConversationCustodyConflict):
        storage.create_thread(
            _create_grant(
                custody,
                root,
                universe,
                interlocutor_ref="slack:user_2",
                key=key,
            ),
            scope=_scope(custody),
            idempotency_key=key,
            interlocutor_ref="slack:user_2",
            retention_until=None,
            now="2026-08-03T12:01:01.000000Z",
        )
    snapshot = storage.read_thread(
        _read_grant(custody, root, universe, conversation_id=original.conversation_id),
        scope=_scope(custody),
        conversation_id=original.conversation_id,
        now="2026-08-03T12:01:02.000000Z",
    )
    assert snapshot.thread == original


def test_private_store_append_replay_conflict_and_contiguous_reply(tmp_path: Path) -> None:
    custody = _custody()
    storage = _storage()
    root = tmp_path / "platform"
    universe = root / "universes" / "u1"
    universe.mkdir(parents=True)
    create_key = "ik_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    append_key = "ik_AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE"
    second_key = "ik_AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI"
    thread = storage.create_thread(
        _create_grant(
            custody,
            root,
            universe,
            interlocutor_ref="slack:user_1",
            key=create_key,
        ),
        scope=_scope(custody),
        idempotency_key=create_key,
        interlocutor_ref="slack:user_1",
        retention_until=None,
        now="2026-08-03T12:01:00.000000Z",
    )
    payload = {"text": "hello"}
    first = storage.append_message(
        _append_grant(
            custody,
            root,
            universe,
            conversation_id=thread.conversation_id,
            key=append_key,
            payload=payload,
        ),
        scope=_scope(custody),
        idempotency_key=append_key,
        conversation_id=thread.conversation_id,
        kind="text",
        participant_ref="slack:user_1",
        source_event_ref="slack:event_1",
        payload=payload,
        reply_to_message_id=None,
        now="2026-08-03T12:01:01.000000Z",
    )
    replay = storage.append_message(
        _append_grant(
            custody,
            root,
            universe,
            conversation_id=thread.conversation_id,
            key=append_key,
            payload=payload,
        ),
        scope=_scope(custody),
        idempotency_key=append_key,
        conversation_id=thread.conversation_id,
        kind="text",
        participant_ref="slack:user_1",
        source_event_ref="slack:event_1",
        payload=payload,
        reply_to_message_id=None,
        now="2026-08-03T12:01:02.000000Z",
    )
    assert replay == first

    changed = {"text": "changed"}
    with pytest.raises(storage.ConversationCustodyConflict):
        storage.append_message(
            _append_grant(
                custody,
                root,
                universe,
                conversation_id=thread.conversation_id,
                key=append_key,
                payload=changed,
            ),
            scope=_scope(custody),
            idempotency_key=append_key,
            conversation_id=thread.conversation_id,
            kind="text",
            participant_ref="slack:user_1",
            source_event_ref="slack:event_1",
            payload=changed,
            reply_to_message_id=None,
            now="2026-08-03T12:01:03.000000Z",
        )

    second_payload = {"text": "reply"}
    second = storage.append_message(
        _append_grant(
            custody,
            root,
            universe,
            conversation_id=thread.conversation_id,
            key=second_key,
            payload=second_payload,
            reply_to_message_id=first.message_id,
        ),
        scope=_scope(custody),
        idempotency_key=second_key,
        conversation_id=thread.conversation_id,
        kind="text",
        participant_ref="slack:user_1",
        source_event_ref="slack:event_1",
        payload=second_payload,
        reply_to_message_id=first.message_id,
        now="2026-08-03T12:01:04.000000Z",
    )
    assert second.ordinal == 2
    assert second.reply_to_message_id == first.message_id


def test_private_store_missing_reply_fails_without_consuming_ordinal(tmp_path: Path) -> None:
    custody = _custody()
    storage = _storage()
    root = tmp_path / "platform"
    universe = root / "universes" / "u1"
    universe.mkdir(parents=True)
    create_key = "ik_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    bad_key = "ik_AwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwM"
    good_key = "ik_BAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQ"
    thread = storage.create_thread(
        _create_grant(
            custody,
            root,
            universe,
            interlocutor_ref="slack:user_1",
            key=create_key,
        ),
        scope=_scope(custody),
        idempotency_key=create_key,
        interlocutor_ref="slack:user_1",
        retention_until=None,
        now="2026-08-03T12:01:00.000000Z",
    )
    payload = {"text": "hello"}
    with pytest.raises(storage.ConversationCustodyReplyError):
        storage.append_message(
            _append_grant(
                custody,
                root,
                universe,
                conversation_id=thread.conversation_id,
                key=bad_key,
                payload=payload,
                reply_to_message_id="message_missing",
            ),
            scope=_scope(custody),
            idempotency_key=bad_key,
            conversation_id=thread.conversation_id,
            kind="text",
            participant_ref="slack:user_1",
            source_event_ref="slack:event_1",
            payload=payload,
            reply_to_message_id="message_missing",
            now="2026-08-03T12:01:01.000000Z",
        )
    appended = storage.append_message(
        _append_grant(
            custody,
            root,
            universe,
            conversation_id=thread.conversation_id,
            key=good_key,
            payload=payload,
        ),
        scope=_scope(custody),
        idempotency_key=good_key,
        conversation_id=thread.conversation_id,
        kind="text",
        participant_ref="slack:user_1",
        source_event_ref="slack:event_1",
        payload=payload,
        reply_to_message_id=None,
        now="2026-08-03T12:01:02.000000Z",
    )
    assert appended.ordinal == 1


def test_private_store_rejects_malformed_input_before_grant_consumption(tmp_path: Path) -> None:
    custody = _custody()
    storage = _storage()
    root = tmp_path / "platform"
    universe = root / "universes" / "u1"
    universe.mkdir(parents=True)
    key = _key(5)
    grant = _create_grant(
        custody,
        root,
        universe,
        interlocutor_ref="slack:user_1",
        key=key,
    )

    with pytest.raises(custody.ConversationCustodyValidationError):
        storage.create_thread(
            grant,
            scope=_scope(custody),
            idempotency_key=key,
            interlocutor_ref="slack:user_1",
            retention_until=None,
            now="not-a-time",
        )
    created = storage.create_thread(
        grant,
        scope=_scope(custody),
        idempotency_key=key,
        interlocutor_ref="slack:user_1",
        retention_until=None,
        now="2026-08-03T12:01:00.000000Z",
    )
    assert created.conversation_id.startswith("conversation_")


def test_private_store_same_key_is_independent_across_universes(tmp_path: Path) -> None:
    custody = _custody()
    storage = _storage()
    root = tmp_path / "platform"
    universe_1 = root / "universes" / "u1"
    universe_2 = root / "universes" / "u2"
    universe_1.mkdir(parents=True)
    universe_2.mkdir(parents=True)
    key = _key(6)

    created = []
    for universe_id, universe in (("universe_1", universe_1), ("universe_2", universe_2)):
        scope = _scope(custody, universe_id=universe_id)
        created.append(
            storage.create_thread(
                _create_grant(
                    custody,
                    root,
                    universe,
                    interlocutor_ref="slack:user_1",
                    key=key,
                    scope=scope,
                ),
                scope=scope,
                idempotency_key=key,
                interlocutor_ref="slack:user_1",
                retention_until=None,
                now="2026-08-03T12:01:00.000000Z",
            )
        )

    assert created[0].conversation_id != created[1].conversation_id
    assert created[0].universe_id == "universe_1"
    assert created[1].universe_id == "universe_2"


def test_private_store_concurrent_identical_create_has_one_result(tmp_path: Path) -> None:
    custody = _custody()
    storage = _storage()
    root = tmp_path / "platform"
    universe = root / "universes" / "u1"
    universe.mkdir(parents=True)
    key = _key(7)
    grants = [
        _create_grant(
            custody,
            root,
            universe,
            interlocutor_ref="slack:user_1",
            key=key,
        )
        for _ in range(8)
    ]

    def create(grant):
        return storage.create_thread(
            grant,
            scope=_scope(custody),
            idempotency_key=key,
            interlocutor_ref="slack:user_1",
            retention_until=None,
            now="2026-08-03T12:01:00.000000Z",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = tuple(executor.map(create, grants))

    assert len({result.conversation_id for result in results}) == 1
    with sqlite3.connect(universe / ".tinyassets.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM conversation_custody_threads").fetchone()[0] == 1
        assert (
            conn.execute("SELECT COUNT(*) FROM conversation_custody_idempotency").fetchone()[0] == 1
        )


def test_private_store_concurrent_distinct_appends_are_contiguous(tmp_path: Path) -> None:
    custody = _custody()
    storage = _storage()
    root = tmp_path / "platform"
    universe = root / "universes" / "u1"
    universe.mkdir(parents=True)
    create_key = _key(8)
    thread = storage.create_thread(
        _create_grant(
            custody,
            root,
            universe,
            interlocutor_ref="slack:user_1",
            key=create_key,
        ),
        scope=_scope(custody),
        idempotency_key=create_key,
        interlocutor_ref="slack:user_1",
        retention_until=None,
        now="2026-08-03T12:01:00.000000Z",
    )
    calls = []
    for index in range(9, 17):
        payload = {"index": index}
        key = _key(index)
        calls.append(
            (
                _append_grant(
                    custody,
                    root,
                    universe,
                    conversation_id=thread.conversation_id,
                    key=key,
                    payload=payload,
                ),
                key,
                payload,
            )
        )

    def append(call):
        grant, key, payload = call
        return storage.append_message(
            grant,
            scope=_scope(custody),
            idempotency_key=key,
            conversation_id=thread.conversation_id,
            kind="text",
            participant_ref="slack:user_1",
            source_event_ref="slack:event_1",
            payload=payload,
            reply_to_message_id=None,
            now="2026-08-03T12:01:01.000000Z",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = tuple(executor.map(append, calls))

    assert sorted(result.ordinal for result in results) == list(range(1, 9))
    snapshot = storage.read_thread(
        _read_grant(custody, root, universe, conversation_id=thread.conversation_id),
        scope=_scope(custody),
        conversation_id=thread.conversation_id,
        now="2026-08-03T12:01:02.000000Z",
    )
    assert tuple(message.ordinal for message in snapshot.messages) == tuple(range(1, 9))


def test_private_store_concurrent_identical_append_has_one_result(tmp_path: Path) -> None:
    custody = _custody()
    storage = _storage()
    root = tmp_path / "platform"
    universe = root / "universes" / "u1"
    universe.mkdir(parents=True)
    create_key = _key(28)
    append_key = _key(29)
    thread = storage.create_thread(
        _create_grant(
            custody,
            root,
            universe,
            interlocutor_ref="slack:user_1",
            key=create_key,
        ),
        scope=_scope(custody),
        idempotency_key=create_key,
        interlocutor_ref="slack:user_1",
        retention_until=None,
        now="2026-08-03T12:01:00.000000Z",
    )
    payload = {"same": True}
    grants = [
        _append_grant(
            custody,
            root,
            universe,
            conversation_id=thread.conversation_id,
            key=append_key,
            payload=payload,
        )
        for _ in range(8)
    ]

    def append(grant):
        return storage.append_message(
            grant,
            scope=_scope(custody),
            idempotency_key=append_key,
            conversation_id=thread.conversation_id,
            kind="text",
            participant_ref="slack:user_1",
            source_event_ref="slack:event_1",
            payload=payload,
            reply_to_message_id=None,
            now="2026-08-03T12:01:01.000000Z",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = tuple(executor.map(append, grants))
    assert len({result.message_id for result in results}) == 1
    assert {result.ordinal for result in results} == {1}


def test_private_store_cross_thread_reply_fails_without_ordinal(tmp_path: Path) -> None:
    custody = _custody()
    storage = _storage()
    root = tmp_path / "platform"
    universe = root / "universes" / "u1"
    universe.mkdir(parents=True)
    threads = []
    for index in (30, 31):
        key = _key(index)
        threads.append(
            storage.create_thread(
                _create_grant(
                    custody,
                    root,
                    universe,
                    interlocutor_ref=f"slack:user_{index}",
                    key=key,
                ),
                scope=_scope(custody),
                idempotency_key=key,
                interlocutor_ref=f"slack:user_{index}",
                retention_until=None,
                now="2026-08-03T12:01:00.000000Z",
            )
        )
    first_payload = {"thread": 1}
    first = storage.append_message(
        _append_grant(
            custody,
            root,
            universe,
            conversation_id=threads[0].conversation_id,
            key=_key(32),
            payload=first_payload,
        ),
        scope=_scope(custody),
        idempotency_key=_key(32),
        conversation_id=threads[0].conversation_id,
        kind="text",
        participant_ref="slack:user_1",
        source_event_ref="slack:event_1",
        payload=first_payload,
        reply_to_message_id=None,
        now="2026-08-03T12:01:01.000000Z",
    )
    reply_payload = {"thread": 2}
    with pytest.raises(storage.ConversationCustodyReplyError):
        storage.append_message(
            _append_grant(
                custody,
                root,
                universe,
                conversation_id=threads[1].conversation_id,
                key=_key(33),
                payload=reply_payload,
                reply_to_message_id=first.message_id,
            ),
            scope=_scope(custody),
            idempotency_key=_key(33),
            conversation_id=threads[1].conversation_id,
            kind="text",
            participant_ref="slack:user_1",
            source_event_ref="slack:event_1",
            payload=reply_payload,
            reply_to_message_id=first.message_id,
            now="2026-08-03T12:01:02.000000Z",
        )
    appended = storage.append_message(
        _append_grant(
            custody,
            root,
            universe,
            conversation_id=threads[1].conversation_id,
            key=_key(34),
            payload=reply_payload,
        ),
        scope=_scope(custody),
        idempotency_key=_key(34),
        conversation_id=threads[1].conversation_id,
        kind="text",
        participant_ref="slack:user_1",
        source_event_ref="slack:event_1",
        payload=reply_payload,
        reply_to_message_id=None,
        now="2026-08-03T12:01:03.000000Z",
    )
    assert appended.ordinal == 1


def test_private_store_cross_process_create_append_and_reply_races(tmp_path: Path) -> None:
    custody = _custody()
    storage = _storage()
    root = tmp_path / "platform"
    universe = root / "universes" / "u1"
    universe.mkdir(parents=True)
    create_key = _key(20)
    context = multiprocessing.get_context("spawn")
    create_args = (str(root), str(universe), create_key)
    with ProcessPoolExecutor(max_workers=4, mp_context=context) as executor:
        conversation_ids = tuple(executor.map(_process_create_thread, (create_args,) * 6))
    assert len(set(conversation_ids)) == 1
    conversation_id = conversation_ids[0]

    first_key = _key(21)
    first_payload = {"seed": True}
    first = storage.append_message(
        _append_grant(
            custody,
            root,
            universe,
            conversation_id=conversation_id,
            key=first_key,
            payload=first_payload,
        ),
        scope=_scope(custody),
        idempotency_key=first_key,
        conversation_id=conversation_id,
        kind="text",
        participant_ref="slack:user_1",
        source_event_ref="slack:event_1",
        payload=first_payload,
        reply_to_message_id=None,
        now="2026-08-03T12:01:01.000000Z",
    )
    append_args = tuple(
        (
            str(root),
            str(universe),
            conversation_id,
            first.message_id,
            _key(index),
            index,
        )
        for index in range(22, 28)
    )
    with ProcessPoolExecutor(max_workers=4, mp_context=context) as executor:
        replies = tuple(executor.map(_process_append_reply, append_args))

    assert sorted(ordinal for ordinal, _reply in replies) == list(range(2, 8))
    assert {reply for _ordinal, reply in replies} == {first.message_id}


def test_private_store_detects_indexed_and_payload_tampering(tmp_path: Path) -> None:
    custody = _custody()
    storage = _storage()
    root = tmp_path / "platform"
    universe = root / "universes" / "u1"
    universe.mkdir(parents=True)
    create_key = _key(17)
    append_key = _key(18)
    thread = storage.create_thread(
        _create_grant(
            custody,
            root,
            universe,
            interlocutor_ref="slack:user_1",
            key=create_key,
        ),
        scope=_scope(custody),
        idempotency_key=create_key,
        interlocutor_ref="slack:user_1",
        retention_until=None,
        now="2026-08-03T12:01:00.000000Z",
    )
    payload = {"private_sentinel": "do-not-leak"}
    storage.append_message(
        _append_grant(
            custody,
            root,
            universe,
            conversation_id=thread.conversation_id,
            key=append_key,
            payload=payload,
        ),
        scope=_scope(custody),
        idempotency_key=append_key,
        conversation_id=thread.conversation_id,
        kind="text",
        participant_ref="slack:user_1",
        source_event_ref="slack:event_1",
        payload=payload,
        reply_to_message_id=None,
        now="2026-08-03T12:01:01.000000Z",
    )
    with sqlite3.connect(universe / ".tinyassets.db") as conn:
        conn.execute(
            "UPDATE conversation_custody_messages SET payload_digest = ?",
            ("sha256:" + "0" * 64,),
        )

    with pytest.raises(storage.ConversationCustodyIntegrityError):
        storage.read_thread(
            _read_grant(custody, root, universe, conversation_id=thread.conversation_id),
            scope=_scope(custody),
            conversation_id=thread.conversation_id,
            now="2026-08-03T12:01:02.000000Z",
        )


def test_private_store_is_not_exported_and_uses_required_sqlite_mode(tmp_path: Path) -> None:
    custody = _custody()
    storage_package = importlib.import_module("tinyassets.storage")
    root = tmp_path / "platform"
    universe = root / "universes" / "u1"
    universe.mkdir(parents=True)
    key = _key(19)
    _storage().create_thread(
        _create_grant(
            custody,
            root,
            universe,
            interlocutor_ref="slack:user_1",
            key=key,
        ),
        scope=_scope(custody),
        idempotency_key=key,
        interlocutor_ref="slack:user_1",
        retention_until=None,
        now="2026-08-03T12:01:00.000000Z",
    )

    assert not hasattr(storage_package, "create_thread")
    with sqlite3.connect(universe / ".tinyassets.db") as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        foreign_keys = conn.execute(
            "PRAGMA foreign_key_list(conversation_custody_messages)"
        ).fetchall()
        assert any(row[2] == "conversation_custody_threads" for row in foreign_keys)
