"""The broker's owner fence: authorized by the lease, durable, linearized with writes."""

from __future__ import annotations

import threading
import time

import pytest

from tinyassets.broker.fence import Fence, Fenced


class Lease:
    """A lease authority that holds one generation with one proof at a time."""

    def __init__(self):
        self.generation, self.proof = 0, ""

    def acquire(self, generation):
        self.generation, self.proof = generation, f"proof-{generation}"
        return self.proof

    def verify(self, generation, proof):
        return (generation, proof) == (self.generation, self.proof)


@pytest.fixture
def lease():
    return Lease()


def fence(tmp_path, lease):
    return Fence(tmp_path / "fence.json", verify_lease_proof=lease.verify)


def test_a_barrier_with_the_leases_proof_issues_the_token_streams_carry(tmp_path, lease):
    f = fence(tmp_path, lease)
    generation, token = f.barrier(1, lease.acquire(1))
    assert generation == 1 and f.admits(1, token)
    assert not f.admits(1, "guessed") and not f.admits(2, token)


def test_an_old_owner_cannot_re_fence_with_a_higher_number(tmp_path, lease):
    f = fence(tmp_path, lease)
    old_proof = lease.acquire(8)
    f.barrier(8, old_proof)
    lease.acquire(9)  # the new owner holds 9
    with pytest.raises(Fenced):
        f.barrier(10, old_proof)
    with pytest.raises(Fenced):
        f.barrier(9, old_proof)


def test_a_lower_generation_is_refused_and_a_repeat_is_idempotent(tmp_path, lease):
    f = fence(tmp_path, lease)
    _, first = f.barrier(3, lease.acquire(3))
    assert f.barrier(3, lease.proof) == (3, first)  # a lost ACK, recovered
    lease.acquire(2)
    with pytest.raises(Fenced):
        f.barrier(2, lease.proof)


def test_the_fence_is_enforced_after_a_restart(tmp_path, lease):
    _, token = fence(tmp_path, lease).barrier(5, lease.acquire(5))
    reopened = fence(tmp_path, lease)
    assert reopened.admits(5, token)
    with pytest.raises(Fenced):
        with reopened.send(4, token):
            pass


def test_a_stale_stream_cannot_write_after_the_barrier(tmp_path, lease):
    f = fence(tmp_path, lease)
    _, old = f.barrier(1, lease.acquire(1))
    f.barrier(2, lease.acquire(2))
    with pytest.raises(Fenced):
        with f.send(1, old):
            pass


def test_the_barrier_waits_for_a_write_in_progress_and_stops_older_streams(tmp_path, lease):
    f = fence(tmp_path, lease)
    _, old = f.barrier(1, lease.acquire(1))
    inside, release = threading.Event(), threading.Event()
    stopped = []

    def writer():
        with f.send(1, old):
            inside.set()
            release.wait(5)

    thread = threading.Thread(target=writer)
    thread.start()
    assert inside.wait(5)
    done = []

    def barrier():
        done.append(f.barrier(2, lease.acquire(2), stop_older=stopped.append))

    advancing = threading.Thread(target=barrier)
    advancing.start()
    time.sleep(0.2)
    assert not done  # still waiting for the write in progress
    release.set()
    advancing.join(5)
    thread.join(5)
    assert done and stopped == [2]


def test_a_malformed_persisted_fence_refuses_to_serve(tmp_path, lease):
    (tmp_path / "fence.json").write_text('{"generation": "x", "token": 1}')
    with pytest.raises(ValueError):
        fence(tmp_path, lease)
