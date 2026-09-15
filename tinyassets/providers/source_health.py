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
    def __init__(self, *, clock=monotonic, capacity=4096):
        if capacity < 1:
            raise ValueError("invalid source health bounds")
        self._clock, self._capacity = clock, capacity
        self._failed = OrderedDict()
        self._lock = Lock()

    def _discard_older_generations(self, key):
        for previous in tuple(self._failed):
            if (previous.generation < key.generation
                    and previous.base == key.base
                    and previous.owner == key.owner
                    and previous.universe == key.universe
                    and previous.provider == key.provider
                    and previous.reference == key.reference):
                del self._failed[previous]

    def authentication_failed(self, key):
        if type(key) is not SourceKey:
            raise TypeError("source health requires exact custody scope")
        with self._lock:
            self._discard_older_generations(key)
            # Observation time is diagnostic metadata, never recovery evidence.
            # In particular, waiting cannot make an unchanged credential valid.
            self._failed[key] = self._clock()
            self._failed.move_to_end(key)
            while len(self._failed) > self._capacity:
                self._failed.popitem(last=False)

    def succeeded(self, key):
        with self._lock:
            self._discard_older_generations(key)
            self._failed.pop(key, None)

    def needs_reconnect(self, key):
        with self._lock:
            return key in self._failed


SOURCE_HEALTH = SourceHealth()
