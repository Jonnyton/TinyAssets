"""Real subprocess lifetime and fixed receipt contracts, without public traffic."""

import json
import os
import socket
import time

import pytest

from tinyassets import workspace_registry as registry
from tinyassets import workspace_registry_process as process

LIMITS = dict(max_bytes=4096, max_connections=4, max_active=2, timeout_s=3)
POSIX = pytest.mark.skipif(os.name != "posix", reason="real broker uses Unix sockets")


@pytest.mark.parametrize("field,value", [
    ("max_bytes", 0), ("max_bytes", True), ("max_connections", -1),
    ("max_active", "2"), ("timeout_s", float("nan")), ("timeout_s", 0),
])
def test_invalid_limits_do_not_start_a_process(field, value):
    with pytest.raises(ValueError):
        process.RegistryBrokerProcess(**{**LIMITS, field: value})


@pytest.mark.parametrize("value", [
    {}, [], None, {"bytes_transferred": 0},
    dict(bytes_transferred=-1, connections=1, active=0, failure=None),
    dict(bytes_transferred=True, connections=1, active=0, failure=None),
    dict(bytes_transferred=5000, connections=1, active=0, failure=None),
    dict(bytes_transferred=1, connections=9, active=0, failure=None),
    dict(bytes_transferred=1, connections=0, active=0, failure=None),
    dict(bytes_transferred=1, connections=1, active=1, failure=None),
    dict(bytes_transferred=1, connections=1, active=0, failure="private-error-text"),
])
def test_bad_or_incomplete_receipt_preserves_full_reservation(value):
    result = process._receipt(json.dumps(value).encode(), LIMITS)
    assert result == process.BrokerReceipt(4096, None, None, "invalid_receipt")


@pytest.mark.parametrize("failure", [None, "timeout", "cancelled", "address_refused"])
def test_only_complete_success_can_reduce_reservation(failure):
    result = process._receipt(json.dumps(dict(bytes_transferred=12, connections=1,
                                               active=0, failure=failure)).encode(), LIMITS)
    assert result.bytes_to_charge == (12 if failure is None else 4096)
    assert result.bytes_observed == 12
    assert result.failure == failure


@pytest.mark.parametrize("raw", [
    b'{"bytes_transferred":1,"bytes_transferred":0,"connections":0,"active":0,"failure":null}',
    b"{}" * 3000, b"\xff", b'{"bytes_transferred":NaN}',
])
def test_malformed_receipt_bytes_never_claim_success(raw):
    assert process._receipt(raw, LIMITS).failure == "invalid_receipt"


def assert_reaped(broker):
    assert broker.process.poll() is not None
    assert not broker._drain.is_alive()
    assert broker.process.stdout.closed
    assert broker.control is None


@POSIX
def test_empty_broker_finishes_and_is_not_reusable():
    broker = process.RegistryBrokerProcess(**LIMITS)
    broker.start()
    try:
        result = broker.finish()
        assert result == process.BrokerReceipt(0, 0, 0, None)
        assert broker.finish() is result
        assert_reaped(broker)
        with pytest.raises(ValueError, match="single-use"):
            broker.start()
    finally:
        broker.close()


@POSIX
def test_real_subprocess_refuses_private_connect_without_network():
    broker = process.RegistryBrokerProcess(**LIMITS)
    broker.start()
    caller, relay = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        registry.send_relay(broker.control, relay)
        relay.close()
        caller.settimeout(2)
        caller.sendall(b"CONNECT 127.0.0.1:443 HTTP/1.1\r\n\r\n")
        assert caller.recv(100).startswith(b"HTTP/1.1 502")
        caller.close()
        receipt = broker.finish()
        assert receipt.failure == "bad_connect"
        assert receipt.bytes_to_charge == 4096
        assert receipt.bytes_observed == 0
        assert_reaped(broker)
    finally:
        caller.close()
        relay.close()
        broker.close()


@POSIX
def test_child_has_no_ambient_secrets_or_extra_descriptors(monkeypatch, tmp_path):
    monkeypatch.setenv("REGISTRY_TEST_SECRET", "must-not-reach-broker")
    proof = """
import os, resource
assert 'REGISTRY_TEST_SECRET' not in os.environ
assert sys.flags.isolated and sys.dont_write_bytecode
assert resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)
for name in os.listdir('/proc/self/fd'):
    if int(name) <= 2: continue
    try: os.fstat(int(name))
    except OSError: continue
    raise AssertionError('unexpected inherited descriptor')
"""
    monkeypatch.setattr(process, "_BOOTSTRAP", process._BOOTSTRAP.replace(
        "_broker_main(json.loads(sys.argv[2]))", proof + "\n_broker_main(json.loads(sys.argv[2]))"))
    path = tmp_path / "unrelated"
    path.write_bytes(b"not a broker input")
    with path.open("rb") as extra:
        os.set_inheritable(extra.fileno(), True)
        broker = process.RegistryBrokerProcess(**LIMITS)
        broker.start()
        try:
            assert broker.finish().failure is None
            assert_reaped(broker)
        finally:
            broker.close()


@POSIX
@pytest.mark.parametrize("source,reason", [
    ("import time; time.sleep(60)", "timeout"),
    ("import os; os.write(1,b'x'*1000000)", "invalid_receipt"),
    ("raise SystemExit(17)", "invalid_receipt"),
])
def test_hung_or_malformed_broker_is_reaped_without_refund(monkeypatch, source, reason):
    monkeypatch.setattr(process, "_BOOTSTRAP", source)
    broker = process.RegistryBrokerProcess(**{**LIMITS, "timeout_s": 0.5})
    broker.start()
    try:
        receipt = broker.finish()
        assert receipt.failure == reason
        assert receipt.bytes_to_charge == 4096
        assert receipt.bytes_observed is None
        assert_reaped(broker)
    finally:
        broker.close()


@POSIX
def test_spawn_failure_closes_both_socket_endpoints(monkeypatch):
    opened = []
    original = socket.socketpair

    def socketpair(*args):
        pair = original(*args)
        opened.extend(pair)
        return pair

    def fail(*args, **kwargs):
        raise OSError("spawn failed")

    monkeypatch.setattr(process.socket, "socketpair", socketpair)
    monkeypatch.setattr(process.subprocess, "Popen", fail)
    broker = process.RegistryBrokerProcess(**LIMITS)
    with pytest.raises(OSError, match="spawn failed"):
        broker.start()
    assert all(stream.fileno() == -1 for stream in opened)
    broker.close()


@POSIX
@pytest.mark.parametrize("termination", ["cancel", "deadline"])
def test_actual_blocked_dns_thread_dies_when_broker_is_closed(monkeypatch, tmp_path, termination):
    marker = tmp_path / "dns-entered"
    injection = f"""
import time
from pathlib import Path
from tinyassets import workspace_registry as registry
def stuck_dns(*args, **kwargs):
    Path({str(marker)!r}).write_text('entered')
    time.sleep(60)
registry.pin_address = stuck_dns
_broker_main(json.loads(sys.argv[2]))
"""
    monkeypatch.setattr(process, "_BOOTSTRAP", process._BOOTSTRAP.replace(
        "_broker_main(json.loads(sys.argv[2]))", injection))
    broker = process.RegistryBrokerProcess(**LIMITS)
    broker.start()
    caller, relay = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        registry.send_relay(broker.control, relay)
        relay.close()
        caller.sendall(b"CONNECT pypi.org:443 HTTP/1.1\r\n\r\n")
        deadline = time.monotonic() + 2
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.read_text() == "entered"
        if termination == "cancel":
            broker.close()
            assert broker.finish().failure == "cancelled"
        else:
            receipt = broker.finish()
            assert receipt.failure is not None
            assert receipt.bytes_to_charge == 4096
        assert_reaped(broker)
        caller.settimeout(1)
        assert caller.recv(1) == b""
    finally:
        caller.close()
        relay.close()
        broker.close()
