"""Bounded advisory memory for NEW plans; never authority or permission to replay."""

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from time import monotonic


@dataclass(frozen=True, slots=True)
class SourceKey:
    base: str
    owner: str
    universe: str
    provider: str
    reference: str
    generation: int
    digest: str


def source_key(base, owner, universe, member):
    """Only caller-validated assignment/served metadata, not secret material."""
    return SourceKey(
        str(Path(base).resolve()), owner, universe, member.provider,
        member.credential_reference_id, member.credential_reference_generation,
        member.credential_reference_digest,
    )


class SourceHealth:
    def __init__(self, *, clock=monotonic, ttl=300, capacity=4096):
        if ttl <= 0 or capacity < 1:
            raise ValueError("invalid source health bounds")
        self._clock, self._ttl, self._capacity = clock, ttl, capacity
        self._failed = OrderedDict()
        self._lock = Lock()

    def _prune(self, now):
        for key, expires in tuple(self._failed.items()):
            if expires <= now:
                del self._failed[key]

    def authentication_failed(self, key):
        if type(key) is not SourceKey:
            raise TypeError("source health requires exact custody scope")
        with self._lock:
            now = self._clock()
            self._prune(now)
            self._failed[key] = now + self._ttl
            self._failed.move_to_end(key)
            while len(self._failed) > self._capacity:
                self._failed.popitem(last=False)

    def succeeded(self, key):
        with self._lock:
            self._failed.pop(key, None)

    def needs_reconnect(self, key):
        with self._lock:
            self._prune(self._clock())
            return key in self._failed


SOURCE_HEALTH = SourceHealth()
