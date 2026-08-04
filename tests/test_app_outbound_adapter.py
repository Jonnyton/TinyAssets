from __future__ import annotations

import sqlite3
import threading

import pytest

from tinyassets.app_outbound_adapter import (
    AppOutboundAdapter,
    AppOutboundDeliveryError,
    AppTransportReceipt,
    body_digest,
)
from tinyassets.app_reply_authority import AppReplyAuthorization, ReplyDestination


def _authorization(body: str = "Hello from the universe") -> AppReplyAuthorization:
    return AppReplyAuthorization(
        owner_user_id="user:founder",
        universe_id="universe:demo",
        agent_binding_id="binding:demo",
        binding_revision=3,
        mapping_generation=4,
        destination=ReplyDestination(
            provider="slack",
            connection_id="connection:slack",
            address="C123456",
        ),
        response_digest=body_digest(body),
        authorization_digest="sha256:" + "a" * 64,
    )


def test_delivers_once_and_replays_redacted_receipt(tmp_path):
    calls: list[tuple[ReplyDestination, str]] = []

    def transport(destination, body):
        calls.append((destination, body))
        return AppTransportReceipt("slack-ts:1700000000.000001")

    adapter = AppOutboundAdapter(tmp_path, transport)
    authorization = _authorization()
    first = adapter.deliver(authorization, "Hello from the universe")
    replay = adapter.deliver(authorization, "Hello from the universe")

    assert len(calls) == 1
    assert calls[0][0] == authorization.destination
    assert calls[0][1] == "Hello from the universe"
    assert first.status == "succeeded"
    assert replay.replay is True
    assert replay.transport_receipt_digest == first.transport_receipt_digest
    assert not hasattr(first, "response")


def test_body_substitution_is_rejected_before_transport(tmp_path):
    calls = []
    adapter = AppOutboundAdapter(
        tmp_path,
        lambda destination, body: calls.append((destination, body))
        or AppTransportReceipt("receipt:1"),
    )

    with pytest.raises(AppOutboundDeliveryError, match="digest"):
        adapter.deliver(_authorization(), "tampered")
    assert calls == []
    with sqlite3.connect(tmp_path / "app_outbound_receipts.db") as db:
        assert db.execute("SELECT COUNT(*) FROM app_outbound_receipts").fetchone()[0] == 0


def test_malformed_authorization_digest_is_rejected_before_transport(tmp_path):
    calls = []
    adapter = AppOutboundAdapter(
        tmp_path,
        lambda destination, body: calls.append((destination, body))
        or AppTransportReceipt("receipt:1"),
    )
    authorization = AppReplyAuthorization(
        owner_user_id="user:founder",
        universe_id="universe:demo",
        agent_binding_id="binding:demo",
        binding_revision=3,
        mapping_generation=4,
        destination=ReplyDestination("slack", "connection:slack", "C123456"),
        response_digest=body_digest("Hello from the universe"),
        authorization_digest="forged",
    )
    with pytest.raises(AppOutboundDeliveryError, match="authorization digest"):
        adapter.deliver(authorization, "Hello from the universe")
    assert calls == []


def test_transport_failure_is_redacted_and_persisted(tmp_path):
    def transport(destination, body):
        raise RuntimeError("token=super-secret response=" + body)

    adapter = AppOutboundAdapter(tmp_path, transport)
    with pytest.raises(AppOutboundDeliveryError, match="delivery failed") as error:
        adapter.deliver(_authorization(), "Hello from the universe")
    assert "super-secret" not in str(error.value)
    with sqlite3.connect(tmp_path / "app_outbound_receipts.db") as db:
        row = db.execute(
            "SELECT status, failure_class, destination_json FROM app_outbound_receipts"
        ).fetchone()
    assert row == (
        "failed",
        "transport_failure",
        '{"address":"C123456","connection_id":"connection:slack",'
        '"provider":"slack"}',
    )
    assert "super-secret" not in row[2]


def test_threaded_replay_invokes_transport_once(tmp_path):
    calls = 0
    lock = threading.Lock()

    def transport(destination, body):
        nonlocal calls
        with lock:
            calls += 1
        return AppTransportReceipt("receipt:concurrent")

    adapter = AppOutboundAdapter(tmp_path, transport)
    authorization = _authorization()
    results = []

    def deliver():
        results.append(adapter.deliver(authorization, "Hello from the universe"))

    threads = [threading.Thread(target=deliver) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert calls == 1
    assert sum(not result.replay for result in results) == 1
