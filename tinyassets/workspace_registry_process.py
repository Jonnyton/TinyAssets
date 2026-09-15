"""Process-owned registry broker with bounded, fixed-class transfer receipts.

Internal execution component, not permission to provision. The coordinator
must reserve the maximum charge before start, pass control only to the acquisition
jail, kill/reap that jail, and finish this broker before offline installation.
Unknown or interrupted transfer keeps the maximum reservation. No checkout,
credential reference, user command, caller-selected host or environment is sent
to this process. Its only network protocol is workspace_registry's CONNECT.
"""

from __future__ import annotations

import json
import os
import select
import socket
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from tinyassets.workspace_registry import TransferBudget, TransferSnapshot

_RECEIPT_CAP = 4096
_FAILURES = frozenset({
    "cancelled", "timeout", "byte_limit", "connection_limit", "bad_connect",
    "address_refused", "transport_failed",
})
_BOOTSTRAP = """
import json, resource, sys
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
sys.path.insert(0, sys.argv[1])
from tinyassets.workspace_registry_process import _broker_main
_broker_main(json.loads(sys.argv[2]))
"""


@dataclass(frozen=True)
class BrokerReceipt:
    """No paths or upstream text. A failure never earns a partial refund."""

    bytes_to_charge: int
    bytes_observed: int | None
    connections: int | None
    failure: str | None


def _receipt(raw: bytes, limits: dict) -> BrokerReceipt:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError
            value[key] = item
        return value

    try:
        if len(raw) > _RECEIPT_CAP:
            raise ValueError
        value = json.loads(raw, object_pairs_hook=unique)
        if type(value) is not dict or set(value) != {
            "bytes_transferred", "connections", "active", "failure",
        }:
            raise ValueError
        for key, ceiling in (("bytes_transferred", limits["max_bytes"]),
                             ("connections", limits["max_connections"]), ("active", 0)):
            if type(value[key]) is not int or not 0 <= value[key] <= ceiling:
                raise ValueError
        failure = value["failure"]
        if value["bytes_transferred"] and not value["connections"]:
            raise ValueError
        if failure is not None and (type(failure) is not str or failure not in _FAILURES):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        return BrokerReceipt(limits["max_bytes"], None, None, "invalid_receipt")
    measured = value["bytes_transferred"]
    return BrokerReceipt(limits["max_bytes"] if failure else measured,
                         measured, value["connections"], failure)


def _broker_main(settings: dict) -> None:
    """Trusted child entry point. Blocking DNS lives only in killable threads here."""
    from tinyassets.workspace_registry import RegistryRefused, receive_relay, serve_registry_tunnel

    budget = TransferBudget(**settings)
    control = socket.socket(fileno=0)
    workers: list[threading.Thread] = []
    try:
        while True:
            budget.check()
            if not select.select([control], [], [], min(0.05, budget.check()))[0]:
                continue
            relay = receive_relay(control)
            if relay is None:
                break
            workers = [worker for worker in workers if worker.is_alive()]
            if len(workers) >= settings["max_active"]:
                relay.close()
                budget.fail("connection_limit")
                break
            worker = threading.Thread(target=serve_registry_tunnel,
                                      args=(relay, budget), daemon=True)
            try:
                worker.start()
            except BaseException:
                relay.close()
                raise
            workers.append(worker)
    except RegistryRefused as error:
        budget.fail(str(error))
    except (OSError, ValueError, RuntimeError):
        budget.fail("transport_failed")
    finally:
        control.close()
        # EOF may arrive just before a relay finishes processing its own EOF.
        # One shared grace, never a fresh timeout per thread. Stuck DNS cannot
        # stop the process exit below or keep a host-network socket alive.
        grace = min(budget.deadline, time.monotonic() + 0.5)
        for worker in workers:
            worker.join(timeout=max(0, grace - time.monotonic()))
        snapshot = budget.snapshot()
        if any(worker.is_alive() for worker in workers) or snapshot.active:
            snapshot = TransferSnapshot(snapshot.bytes_transferred, snapshot.connections,
                                        snapshot.active, snapshot.failure or "cancelled")
        payload = json.dumps(asdict(snapshot), separators=(",", ":")).encode("ascii")
        try:
            os.write(1, payload)
        finally:
            # No Python shutdown/join can outlive this attempt. The OS closes
            # every upstream socket, even when a libc DNS call never returned.
            os._exit(0)


class RegistryBrokerProcess:
    """One bounded broker subprocess, never a daemon or a reusable network grant."""

    def __init__(self, *, max_bytes: int, max_connections: int = 64,
                 max_active: int = 8, timeout_s: float = 60):
        self._settings = dict(max_bytes=max_bytes, max_connections=max_connections,
                              max_active=max_active, timeout_s=timeout_s)
        TransferBudget(**self._settings)  # Validate before owning any resource.
        self.control: socket.socket | None = None
        self.process: subprocess.Popen | None = None
        self._drain = None
        self._drain_started = False
        self._breaches: list[str] = []
        self._deadline = 0.0
        self._started = self._closed = False
        self._result: BrokerReceipt | None = None

    def start(self) -> None:
        from tinyassets.node_sandbox import _BoundedDrain

        if os.name != "posix" or not hasattr(socket, "SCM_RIGHTS"):
            raise NotImplementedError("registry process requires POSIX Unix sockets")
        if self._started or self._closed:
            raise ValueError("registry process is single-use")
        self._started = True
        self._deadline = time.monotonic() + self._settings["timeout_s"]
        parent, self.control = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        try:
            self.process = subprocess.Popen(
                [sys.executable, "-I", "-B", "-c", _BOOTSTRAP,
                 str(Path(__file__).resolve().parent.parent), json.dumps(self._settings)],
                stdin=parent, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
                     "PYTHONDONTWRITEBYTECODE": "1"},
                cwd="/", close_fds=True, start_new_session=True,
            )
            self._drain = _BoundedDrain(self.process.stdout, _RECEIPT_CAP,
                                        "registry-receipt", self._breaches)
            self._drain.start()
            self._drain_started = True
        except BaseException:
            self.close()
            raise
        finally:
            parent.close()

    def release_control(self) -> None:
        """Close the parent's copy after passing it as the acquisition jail's stdin."""
        if self.control is not None:
            self.control.close()
            self.control = None

    def finish(self) -> BrokerReceipt:
        """Reap and verify the terminal receipt; unfinished attempts charge the maximum."""
        if self._result is not None:
            return self._result
        if self.process is None:
            raise ValueError("registry process was not started")
        self.release_control()
        failure = "cancelled" if self._closed else None
        try:
            while failure is None and self.process.poll() is None:
                remaining = self._deadline - time.monotonic()
                if self._breaches:
                    failure = "invalid_receipt"
                elif remaining <= 0:
                    failure = "timeout"
                else:
                    try:
                        self.process.wait(timeout=min(0.05, remaining))
                    except subprocess.TimeoutExpired:
                        continue
        finally:
            self.close()
        if failure is None and (self.process.returncode != 0 or self._breaches):
            failure = "invalid_receipt"
        self._result = (BrokerReceipt(self._settings["max_bytes"], None, None, failure)
                        if failure else _receipt(self._drain.data, self._settings))
        return self._result

    def close(self) -> None:
        """Revoke all network authority and verify exit, including stuck DNS cases."""
        from tinyassets.node_sandbox import _kill_process_tree

        self.release_control()
        self._closed = True
        if self.process is not None:
            if self.process.poll() is None:
                _kill_process_tree(self.process)
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                raise RuntimeError("registry termination unconfirmed") from None
        if self._drain_started:
            self._drain.join(timeout=1)
            if self._drain.is_alive():
                raise RuntimeError("registry receipt drain termination unconfirmed")
        if self.process is not None and self.process.stdout is not None:
            self.process.stdout.close()
