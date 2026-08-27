"""§14 authoring proof — concurrent author sessions, sequential cross-account
isolation, and lost-event / cross-bleed bounds.

Requirement source: ``openspec/changes/archive/2026-08-26-complete-independent-full-platform-targets/
specs/node-authoring-and-autoresearch/spec.md`` — "Authoring completion includes
adversarial isolation and concurrent optimization proof" (task 4.6, authoring
half). The optimization half (candidate leases, duplicate-candidate suppression,
budget-stop races, evaluator-cache fan-out) belongs to task 4.4 / the
`tinyassets/autoresearch/` package, which this lane does not build.

Measured bounds are asserted *and* reported in the assertion payload so a
failure shows the numbers, not just a boolean.
"""

from __future__ import annotations

import statistics
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

CONCURRENT_SESSIONS = 100
SEQUENTIAL_SESSIONS = 1000


@pytest.fixture
def env(tmp_path, monkeypatch):
    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "loadtest")
    return base


@pytest.fixture
def service(env):
    from tinyassets.authoring import service as svc
    from tinyassets.authoring.store import AuthoringStore

    AuthoringStore().initialize()
    return svc


def _one_session(service, actor: str, label: str) -> tuple[str, float]:
    start = time.perf_counter()
    session = service.start_session(
        actor_id=actor, artifact_kind="node", sketch=f"sketch for {label}"
    )
    session_id = session["session_id"]
    service.apply_edit_batch(
        actor_id=actor,
        session_id=session_id,
        operations=[{"op": "set", "path": "name", "value": label}],
    )
    service.run_test(actor_id=actor, session_id=session_id)
    return session_id, time.perf_counter() - start


def test_concurrent_author_sessions_stay_owner_bound(service):
    """100 concurrent sessions across 100 accounts: no cross-user bleed."""
    latencies: dict[str, float] = {}
    session_ids: dict[str, str] = {}
    errors: list[str] = []

    def work(index: int) -> None:
        actor = f"user_{index:03d}"
        label = f"node_{index:03d}"
        try:
            session_id, elapsed = _one_session(service, actor, label)
        except Exception as exc:  # noqa: BLE001 — the harness reports, never hides
            errors.append(f"{actor}: {type(exc).__name__}: {exc}")
            return
        latencies[actor] = elapsed
        session_ids[actor] = session_id

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(work, range(CONCURRENT_SESSIONS)))
    wall = time.perf_counter() - started

    ordered = sorted(latencies.values())
    report = {
        "sessions": len(session_ids),
        "errors": errors[:5],
        "wall_seconds": round(wall, 3),
        "p50_seconds": round(statistics.median(ordered), 4) if ordered else None,
        "p95_seconds": round(ordered[int(len(ordered) * 0.95) - 1], 4) if ordered else None,
        "max_seconds": round(ordered[-1], 4) if ordered else None,
    }
    assert not errors, report
    assert len(session_ids) == CONCURRENT_SESSIONS, report
    assert len(set(session_ids.values())) == CONCURRENT_SESSIONS, report

    # Every event is bound to its own owner and session; nothing bleeds.
    for index in range(CONCURRENT_SESSIONS):
        actor = f"user_{index:03d}"
        view = service.inspect_session(actor_id=actor, session_id=session_ids[actor])
        assert view["owner_id"] == actor, report
        assert view["definition"]["name"] == f"node_{index:03d}", report
        assert view["definition"]["sketch"] == f"sketch for node_{index:03d}", report
        listed = service.list_sessions(actor_id=actor)
        assert [s["session_id"] for s in listed] == [session_ids[actor]], report

    # Reported bound: no session took absurdly long under contention.
    assert report["max_seconds"] < 30.0, report


def test_concurrent_edits_to_one_session_lose_no_committed_event(service):
    """Contention on a single draft: every commit that reports success is durable."""
    from tinyassets.authoring.models import AuthoringConflictError

    session = service.start_session(
        actor_id="racer", artifact_kind="node", sketch="contended"
    )
    session_id = session["session_id"]
    committed: list[int] = []
    conflicts = 0

    def edit(index: int) -> None:
        nonlocal conflicts
        try:
            result = service.apply_edit_batch(
                actor_id="racer",
                session_id=session_id,
                operations=[{"op": "set", "path": "name", "value": f"name_{index}"}],
            )
        except AuthoringConflictError:
            conflicts += 1
            return
        committed.append(result["draft_version"])

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(edit, range(40)))

    events = service.inspect_session(
        actor_id="racer", session_id=session_id, view="history"
    )["events"]
    edit_events = [e for e in events if e["event_type"] == "edit"]
    report = {
        "committed": len(committed),
        "conflicts": conflicts,
        "edit_events": len(edit_events),
        "seqs": [e["seq"] for e in events],
    }
    assert len(committed) == len(edit_events), report
    assert len(set(committed)) == len(committed), report  # one version per commit
    # Event sequence numbers are contiguous: no lost or duplicated event.
    assert report["seqs"] == sorted(report["seqs"]), report
    assert report["seqs"] == list(range(1, len(events) + 1)), report


@pytest.mark.slow
def test_sequential_cross_account_sessions_never_bleed(service):
    """1,000 isolated sequential sessions across 1,000 accounts."""
    from tinyassets.authoring.models import AuthoringAccessError

    ids: list[tuple[str, str]] = []
    started = time.perf_counter()
    for index in range(SEQUENTIAL_SESSIONS):
        actor = f"seq_{index:04d}"
        session = service.start_session(
            actor_id=actor, artifact_kind="node", sketch=f"seq {index}"
        )
        ids.append((actor, session["session_id"]))
    wall = time.perf_counter() - started
    report = {
        "sessions": len(ids),
        "wall_seconds": round(wall, 2),
        "per_session_ms": round(wall / max(len(ids), 1) * 1000, 3),
    }

    assert len({session_id for _, session_id in ids}) == SEQUENTIAL_SESSIONS, report

    # Spot-check isolation across the range, including neighbours.
    for index in (0, 1, 499, 500, SEQUENTIAL_SESSIONS - 1):
        actor, session_id = ids[index]
        assert service.inspect_session(actor_id=actor, session_id=session_id)[
            "owner_id"
        ] == actor, report
        neighbour, neighbour_session = ids[(index + 1) % SEQUENTIAL_SESSIONS]
        with pytest.raises(AuthoringAccessError):
            service.inspect_session(actor_id=actor, session_id=neighbour_session)
        assert len(service.list_sessions(actor_id=neighbour)) == 1, report

    assert report["per_session_ms"] < 200.0, report
