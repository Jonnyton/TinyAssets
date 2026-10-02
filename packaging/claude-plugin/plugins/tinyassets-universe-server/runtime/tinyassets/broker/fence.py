"""The owner-generation fence (I14 decision 6, target architecture D5/D11).

Every owner-channel stream carries the generation and the token the broker's
last admitted barrier issued; a stream is admitted only if both equal the
persisted fence, and re-checked immediately before each write to the network.

The barrier is authorized by the LEASE, not by the caller's channel: an old
owner and a new one share an image and a uid, so channel identity cannot tell
them apart. ``FENCE{G, proof}`` is admitted only if the lease authority verifies
that ``proof`` is the secret minted for the acquisition that holds generation
G (``control_plane.lease.verify_lease_proof``, injected here).

* A barrier below the persisted generation is refused.
* A repeat of the persisted generation, with a valid proof, is idempotent: it
  returns the same token, which is how a lost acknowledgement is recovered.
* A higher generation is persisted durably with a fresh token BEFORE anything
  else; only then are older streams stopped and the barrier acknowledged.
* After a restart the persisted fence is enforced whether or not the
  acknowledgement was ever delivered.

Linearization: :meth:`Fence.send` is a read lock held across one network
write, and the barrier takes the write lock after persisting. When
:meth:`barrier` returns, no stream of an older generation is inside a write,
and none can start another (it re-checks under the read lock).
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path


class Fenced(PermissionError):
    """Below the fence, or a barrier without a valid lease proof."""


class Fence:
    def __init__(self, path: Path, *, verify_lease_proof: Callable[[int, str], bool]) -> None:
        self._path = Path(path)
        self._verify = verify_lease_proof
        self._state_lock = threading.Lock()
        self._rw = threading.Condition()
        self._readers = 0
        self._writer = False
        self.generation, self.token = self._load()

    def _load(self) -> tuple[int, str]:
        try:
            document = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return 0, ""
        generation, token = document["generation"], document["token"]
        if type(generation) is not int or generation < 0 or not isinstance(token, str):
            raise ValueError("the persisted fence is malformed; refusing to serve")
        return generation, token

    def _persist(self, generation: int, token: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=self._path.parent, prefix=".fence.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"generation": generation, "token": token}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self._path)
        except BaseException:
            Path(temp).unlink(missing_ok=True)
            raise
        if hasattr(os, "O_DIRECTORY"):
            directory = os.open(self._path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)

    def admits(self, generation: int, token: str) -> bool:
        with self._state_lock:
            return bool(self.token) and (generation, token) == (self.generation, self.token)

    def barrier(self, generation: int, proof: str,
                stop_older: Callable[[int], None] = lambda generation: None) -> tuple[int, str]:
        """Advance (or re-acknowledge) the fence; returns the persisted ``(G, token)``.

        ``stop_older(G)`` is called with the write lock held, after the new
        fence is durable: it must end every stream below G. On return no such
        stream is writing or can write again.
        """
        if type(generation) is not int or generation < 1 or not isinstance(proof, str):
            raise Fenced("a barrier needs a positive generation and a lease proof")
        if not self._verify(generation, proof):
            raise Fenced("the lease does not hold this generation with this proof")
        with self._state_lock:
            if generation < self.generation:
                raise Fenced("a newer generation already holds the fence")
            if generation == self.generation and self.token:
                return self.generation, self.token
            token = secrets.token_urlsafe(32)
            self._persist(generation, token)
            self.generation, self.token = generation, token
        with self._rw:
            self._writer = True
            try:
                while self._readers:
                    self._rw.wait()
                stop_older(generation)
            finally:
                self._writer = False
                self._rw.notify_all()
        return generation, token

    @contextmanager
    def send(self, generation: int, token: str) -> Iterator[None]:
        """Hold across ONE network write; refuses if the stream is below the fence."""
        with self._rw:
            while self._writer:
                self._rw.wait()
            if not self.admits(generation, token):
                raise Fenced("this stream's generation is below the fence")
            self._readers += 1
        try:
            yield
        finally:
            with self._rw:
                self._readers -= 1
                self._rw.notify_all()
