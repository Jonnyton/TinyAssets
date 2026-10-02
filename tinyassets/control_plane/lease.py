"""The execution owner's lease, as the scheduler sees it (target design D11).

Every always-on duty runs under the execution owner's lease: exactly one owner,
holding a lease with a monotonic generation. The real lease (S8a,
``lane turn-handover``) is not landed, and today there is one serving process,
so the installed lease is :class:`SingleProcessLease`: generation 1, always
held. S8a replaces it by calling :func:`install_owner_lease` at owner start;
nothing that consumes the lease changes.

The contract a duty relies on:

* ``held()`` before a tick. A process that does not hold the lease does no
  scheduling at all -- a standby, or an owner that has started handing over.
* ``check()`` immediately before an effect (a fire). It raises
  :class:`LeaseLost` when the lease was lost since ``held()``, so a stalled
  owner fires nothing after its successor has taken over.
* ``generation`` is recorded on every fire row, so a successor can tell its
  own fires from an older owner's.
"""

from __future__ import annotations

import threading
from typing import Protocol, runtime_checkable


class LeaseLost(RuntimeError):
    """The owner lease is no longer held; the caller must not act."""


@runtime_checkable
class OwnerLease(Protocol):
    @property
    def generation(self) -> int: ...

    def held(self) -> bool: ...

    def check(self) -> None: ...


class SingleProcessLease:
    """Today's lease: one serving process is the only owner there is.

    Generation 1 forever. Correct only while exactly one process runs the
    control plane, which is today's deploy shape (``agent_turn_boot`` pins the
    same single-writer invariant); S8a's generation-fenced lease replaces it
    before any second owner can exist.
    """

    generation = 1

    def held(self) -> bool:
        return True

    def check(self) -> None:
        return None


_lock = threading.Lock()
_installed: OwnerLease = SingleProcessLease()


def owner_lease() -> OwnerLease:
    with _lock:
        return _installed


def install_owner_lease(lease: OwnerLease) -> OwnerLease:
    """Install ``lease`` as the process's owner lease; returns the previous one."""
    if not isinstance(lease, OwnerLease):
        raise TypeError("install_owner_lease needs an OwnerLease")
    global _installed
    with _lock:
        previous, _installed = _installed, lease
    return previous


__all__ = [
    "LeaseLost",
    "OwnerLease",
    "SingleProcessLease",
    "install_owner_lease",
    "owner_lease",
]
