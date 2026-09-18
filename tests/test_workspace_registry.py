"""Registry broker transport contract; local socket peers, never registry traffic."""

from __future__ import annotations

import array
import os
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from tinyassets import workspace_registry as registry


def budget(**overrides):
    options = dict(max_bytes=1024 * 1024, max_connections=16, max_active=4, timeout_s=3)
    options.update(overrides)
    return registry.TransferBudget(**options)


def request(host="pypi.org"):
    return f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n\r\n".encode()


def public_only(address):
    if address not in {"93.184.216.34", "2606:4700::1111"}:
        raise ValueError("private")
    return address


class ConnectParsingTests(unittest.TestCase):
    def test_exact_hosts_and_versions(self):
        for host in registry.REGISTRY_HOSTS:
            for version in (b"HTTP/1.0", b"HTTP/1.1"):
                with self.subTest(host=host, version=version):
                    self.assertEqual(registry.connect_host(
                        request(host).replace(b"HTTP/1.1", version)), host)

    def test_non_registry_and_ambiguous_requests_refuse(self):
        for raw in (
            b"GET https://pypi.org/simple HTTP/1.1\r\n\r\n",
            request().replace(b"CONNECT", b"connect"),
            request().replace(b":443", b":80"),
            request().replace(b":443", b":0443"),
            request().replace(b"pypi.org", b"PYPI.ORG"),
            request().replace(b"pypi.org", b"pypi.org."),
            request().replace(b"pypi.org", b"pypi.org.evil.example"),
            request().replace(b"pypi.org", b"evil@pypi.org"),
            request().replace(b"pypi.org", b"127.0.0.1"),
            request().replace(b"pypi.org", b"[::1]"),
            request().replace(b"CONNECT ", b"CONNECT  "),
            request().replace(b"HTTP/1.1", b"HTTP/2"),
            request().replace(b"Host: pypi.org", b"Host: evil.example"),
            request().replace(b"Host:", b" Host:"),
            request().replace(b"Host:", b"Host\x00:"),
            request().replace(b"\r\nHost:", b"\r\nProxy-Authorization:"),
            request().replace(b"\r\nHost:", b"\r\nAuthorization:"),
            request().replace(b"\r\nHost:", b"\r\nContent-Length:"),
            request().replace(b"\r\nHost:", b"\r\nTransfer-Encoding:"),
            request().replace(b"\r\n\r\n", b"\r\nHost: pypi.org:443\r\n\r\n"),
            request() + b"extra bytes",
            request() + request(),
            request().replace(b"\r\n", b"\n"),
            b"\xff\r\n\r\n",
            b"A" * 16384 + b"\r\n\r\n",
            request()[:-1],
        ):
            with self.subTest(raw=raw[:100]):
                with self.assertRaisesRegex(registry.RegistryRefused, "^bad_connect$"):
                    registry.connect_host(raw)

    def test_ordinary_non_auth_headers_are_not_forwarded(self):
        raw = request().replace(b"\r\n\r\n", b"\r\nUser-Agent: test\r\n\r\n")
        self.assertEqual(registry.connect_host(raw), "pypi.org")


class RegistryTransportTests(unittest.TestCase):
    def pair(self):
        left, right = socket.socketpair()
        for stream in (left, right):
            stream.settimeout(2)
            self.addCleanup(stream.close)
        return left, right

    def start(self, relay, transfer, **kwargs):
        runner = threading.Thread(target=registry.serve_registry_tunnel,
                                  args=(relay, transfer), kwargs=kwargs, daemon=True)
        runner.start()
        self.addCleanup(transfer.cancel)
        return runner

    def finish(self, runner, transfer, failure=None):
        runner.join(2)
        self.assertFalse(runner.is_alive(), "relay did not terminate")
        result = transfer.snapshot()
        self.assertEqual(result.active, 0)
        self.assertEqual(result.failure, failure)
        return result

    def test_bad_connect_never_resolves(self):
        client, relay = self.pair()
        transfer = budget()
        resolver = Mock(side_effect=AssertionError("must not resolve"))
        runner = self.start(relay, transfer, resolver=resolver)
        client.sendall(request("localhost"))
        self.assertEqual(client.recv(1024), registry._REFUSED)
        self.finish(runner, transfer, "bad_connect")
        resolver.assert_not_called()

    def test_all_dns_answers_checked_before_any_connect(self):
        for addresses in (["93.184.216.34", "127.0.0.1"], ["10.0.0.2"], []):
            with self.subTest(addresses=addresses):
                client, relay = self.pair()
                transfer = budget()
                with patch.object(registry, "_connect_pinned") as connect:
                    runner = self.start(relay, transfer, resolver=lambda *_: addresses,
                                        classifier=public_only)
                    client.sendall(request())
                    self.assertEqual(client.recv(1024), registry._REFUSED)
                    self.finish(runner, transfer, "address_refused")
                    connect.assert_not_called()

    def test_bidirectional_bytes_half_close_and_accounting(self):
        client, relay = self.pair()
        upstream, server = self.pair()
        transfer = budget()
        with patch.object(registry, "_connect_pinned", return_value=upstream) as connect:
            runner = self.start(relay, transfer, resolver=lambda *_: ["93.184.216.34"],
                                classifier=public_only)
            client.sendall(request())
            self.assertEqual(client.recv(1024), registry._CONNECTED)
            client.sendall(b"opaque TLS client bytes")
            client.shutdown(socket.SHUT_WR)
            self.assertEqual(server.recv(1024), b"opaque TLS client bytes")
            self.assertEqual(server.recv(1024), b"")
            server.sendall(b"opaque TLS server bytes")
            server.shutdown(socket.SHUT_WR)
            self.assertEqual(client.recv(1024), b"opaque TLS server bytes")
            self.assertEqual(client.recv(1024), b"")
            result = self.finish(runner, transfer)
            self.assertEqual(result.bytes_transferred, 46)
            self.assertEqual(result.connections, 1)
            connect.assert_called_once_with(("93.184.216.34",), transfer)
            self.assertEqual(upstream.fileno(), -1)
            self.assertEqual(relay.fileno(), -1)

    def test_byte_limit_stops_transport_without_overreading(self):
        client, relay = self.pair()
        upstream, server = self.pair()
        transfer = budget(max_bytes=3)
        with patch.object(registry, "_connect_pinned", return_value=upstream):
            runner = self.start(relay, transfer, resolver=lambda *_: ["93.184.216.34"],
                                classifier=public_only)
            client.sendall(request())
            self.assertEqual(client.recv(1024), registry._CONNECTED)
            server.sendall(b"long response that is over the transfer limit")
            result = self.finish(runner, transfer, "byte_limit")
            self.assertEqual(result.bytes_transferred, 3)

    def test_cancel_revokes_an_established_tunnel(self):
        client, relay = self.pair()
        upstream, _server = self.pair()
        transfer = budget()
        with patch.object(registry, "_connect_pinned", return_value=upstream):
            runner = self.start(relay, transfer, resolver=lambda *_: ["93.184.216.34"],
                                classifier=public_only)
            client.sendall(request())
            self.assertEqual(client.recv(1024), registry._CONNECTED)
            transfer.cancel()
            self.finish(runner, transfer, "cancelled")
            self.assertEqual(client.recv(1024), b"")

    def test_deadline_applies_to_incomplete_headers(self):
        client, relay = self.pair()
        transfer = budget(timeout_s=0.05)
        runner = self.start(relay, transfer)
        client.sendall(b"CONNECT ")
        self.assertEqual(client.recv(1024), registry._REFUSED)
        self.finish(runner, transfer, "timeout")

    def test_dns_error_details_never_escape(self):
        client, relay = self.pair()
        transfer = budget()
        resolver = Mock(side_effect=OSError("secret internal-path private-address"))
        runner = self.start(relay, transfer, resolver=resolver)
        client.sendall(request())
        self.assertEqual(client.recv(1024), registry._REFUSED)
        self.finish(runner, transfer, "address_refused")

    def test_pinned_connect_uses_numeric_addresses_and_closes_failed_socket(self):
        failed, good = Mock(), Mock()
        failed.connect.side_effect = OSError("unreachable")
        transfer = budget()
        with patch.object(registry.socket, "socket", side_effect=[failed, good]) as factory:
            result = registry._connect_pinned(("93.184.216.34", "2606:4700::1111"), transfer)
        self.assertIs(result, good)
        self.assertEqual(factory.call_args_list[0].args, (socket.AF_INET, socket.SOCK_STREAM))
        self.assertEqual(factory.call_args_list[1].args, (socket.AF_INET6, socket.SOCK_STREAM))
        failed.connect.assert_called_once_with(("93.184.216.34", 443))
        good.connect.assert_called_once_with(("2606:4700::1111", 443))
        failed.close.assert_called_once()


class TransferBudgetTests(unittest.TestCase):
    def test_limits_are_shared_and_connections_do_not_reset_on_close(self):
        transfer = budget(max_active=1, max_connections=2)
        transfer.enter()
        transfer.leave()
        transfer.enter()
        transfer.leave()
        with self.assertRaisesRegex(registry.RegistryRefused, "connection_limit"):
            transfer.enter()
        self.assertEqual(transfer.snapshot().connections, 2)
        self.assertEqual(transfer.snapshot().active, 0)

    def test_concurrent_admission_does_not_oversubscribe(self):
        transfer = budget(max_active=1)
        barrier = threading.Barrier(8)
        accepted = []

        def enter():
            barrier.wait()
            try:
                transfer.enter()
                accepted.append(True)
            except registry.RegistryRefused:
                pass

        workers = [threading.Thread(target=enter) for _ in range(8)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(2)
            self.assertFalse(worker.is_alive())
        self.assertEqual(len(accepted), 1)
        self.assertEqual(transfer.snapshot().active, 1)
        transfer.leave()

    def test_invalid_limits_fail_before_work(self):
        for overrides in ({"max_bytes": True}, {"max_active": 0}, {"max_connections": 1.5},
                          {"timeout_s": float("inf")}, {"timeout_s": float("nan")},
                          {"timeout_s": -1}, {"timeout_s": True}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                budget(**overrides)


@unittest.skipUnless(sys.platform == "linux", "Linux descriptor handoff")
class RegistryDescriptorTests(unittest.TestCase):
    def setUp(self):
        self.child, self.parent = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        self.local, self.endpoint = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        for stream in (self.child, self.parent, self.local, self.endpoint):
            stream.settimeout(2)
            self.addCleanup(stream.close)

    def inject(self, payload, fds):
        self.child.sendmsg(
            [payload], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", fds))]
        )

    def assert_refused_without_leak(self):
        before = set(os.listdir("/proc/self/fd"))
        with self.assertRaisesRegex(registry.RegistryRefused, "^bad_connect$"):
            registry.receive_relay(self.parent)
        self.assertEqual(set(os.listdir("/proc/self/fd")), before)

    def test_connected_unix_relay_is_copied_noninheritable_and_bidirectional(self):
        registry.send_relay(self.child, self.endpoint)
        with registry.receive_relay(self.parent) as accepted:
            self.endpoint.close()
            self.assertFalse(os.get_inheritable(accepted.fileno()))
            self.assertEqual(accepted.family, socket.AF_UNIX)
            self.local.sendall(b"client TLS")
            self.assertEqual(accepted.recv(1024), b"client TLS")
            accepted.sendall(b"server TLS")
            self.assertEqual(self.local.recv(1024), b"server TLS")

    def test_eof_is_revocation_not_an_empty_relay(self):
        self.child.close()
        self.assertIsNone(registry.receive_relay(self.parent))

    def test_bad_control_message_closes_received_descriptor(self):
        self.inject(b"wrong", [self.endpoint.fileno()])
        self.assert_refused_without_leak()

    def test_truncated_message_closes_received_descriptor(self):
        self.inject(registry._RELAY_MESSAGE + b"extra", [self.endpoint.fileno()])
        self.assert_refused_without_leak()

    def test_multiple_or_truncated_descriptors_all_close(self):
        for count in (2, 20):
            with self.subTest(count=count):
                self.inject(registry._RELAY_MESSAGE, [self.endpoint.fileno()] * count)
                self.assert_refused_without_leak()

    def test_regular_file_descriptor_refuses_without_leak(self):
        with tempfile.TemporaryFile() as fixture:
            self.inject(registry._RELAY_MESSAGE, [fixture.fileno()])
            self.assert_refused_without_leak()

    def test_network_and_unconnected_sockets_refuse_without_leak(self):
        for family, kind in ((socket.AF_INET, socket.SOCK_STREAM),
                             (socket.AF_UNIX, socket.SOCK_STREAM),
                             (socket.AF_UNIX, socket.SOCK_DGRAM)):
            with self.subTest(family=family, kind=kind), socket.socket(family, kind) as wrong:
                self.inject(registry._RELAY_MESSAGE, [wrong.fileno()])
                self.assert_refused_without_leak()

    def test_sender_rejects_wrong_control_type(self):
        with self.assertRaisesRegex(ValueError, "private Unix packet"):
            registry.send_relay(self.local, self.endpoint)

    def test_missing_descriptor_refuses(self):
        self.child.send(registry._RELAY_MESSAGE)
        self.assert_refused_without_leak()


if __name__ == "__main__":
    unittest.main()
