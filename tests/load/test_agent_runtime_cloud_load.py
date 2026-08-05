"""Production-shaped, explicitly non-production load proof for cloud agent execution.

This exercises the real SQLite authority/runtime owners with independent
processes and fresh service instances. The provider itself is a recording test
double, so this evidence is classified as shaped and never as a live-cloud pass.

Run directly with:
    python -m pytest tests/load/test_agent_runtime_cloud_load.py -q -s
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from tests.test_agent_runtime_invocation import NOW, _ProviderResolver, _request
from tests.test_agent_runtime_provider_call import _execution_service, _RecordingProvider
from tinyassets.providers.base import BaseProvider, ModelConfig, ProviderResponse
from tinyassets.providers.router import ProviderRouter
from tinyassets.storage import db_path

PROCESS_WORKERS = 8
PROCESS_REQUESTS = 64
THREAD_WORKERS = 64
_CONCURRENT_BLOCKERS = {
    "agent provider execution is owned by a concurrent launch",
    "agent provider launch requires uncertain-call reconciliation",
}


class _ProcessRecordingProvider(BaseProvider):
    name = "codex"
    family = "gpt"

    def __init__(self, marker_dir: Path, release_path: Path) -> None:
        self.marker_dir = marker_dir
        self.release_path = release_path

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        marker = self.marker_dir / f"{os.getpid()}-{time.time_ns()}.call"
        marker.write_text("provider boundary crossed", encoding="utf-8")
        deadline = time.monotonic() + 20
        while not self.release_path.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("load-test provider release was not observed")
            time.sleep(0.01)
        return ProviderResponse(
            text="approved patch",
            provider=self.name,
            model="gpt-load-test",
            family=self.family,
            latency_ms=10.0,
        )


def _prepare_in_fresh_process(
    base_path: str,
    invocation_id: str,
    observed_at: str,
) -> dict[str, object]:
    from tinyassets.agent_runtime_grants import (
        AccountCapabilityGrantSource,
        AgentRuntimeGrantResolver,
    )
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionService,
    )

    root = Path(base_path)
    now = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    service = AgentRuntimeProviderExecutionService(
        root,
        grant_resolver=AgentRuntimeGrantResolver(
            capability_source=AccountCapabilityGrantSource(root),
            clock=lambda: now.timestamp(),
        ),
        provider_binding_resolver=_ProviderResolver(),
        clock=lambda: now,
    )
    receipt = service.issue_receipt(invocation_id).record
    claim = service.claim(invocation_id).record
    reservation = service.reserve(invocation_id).record
    continuation = service.prepare_continuation(invocation_id).record
    assert receipt is not None
    assert claim is not None
    assert reservation is not None
    assert continuation is not None
    return {
        "receipt_id": receipt.receipt_id,
        "claim_id": claim.claim_id,
        "claim_generation": claim.generation,
        "reservation_id": reservation.reservation_id,
        "continuation_id": continuation.continuation_id,
        "continuation_generation": continuation.generation,
    }


def _launch_in_fresh_process(
    base_path: str,
    invocation_id: str,
    marker_dir: str,
    release_path: str,
) -> dict[str, str]:
    from tinyassets.agent_runtime_grants import (
        AccountCapabilityGrantSource,
        AgentRuntimeGrantResolver,
    )
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionBlocked,
        AgentRuntimeProviderExecutionService,
    )

    root = Path(base_path)
    service = AgentRuntimeProviderExecutionService(
        root,
        grant_resolver=AgentRuntimeGrantResolver(
            capability_source=AccountCapabilityGrantSource(root),
            clock=lambda: NOW.timestamp(),
        ),
        provider_binding_resolver=_ProviderResolver(),
        clock=lambda: NOW,
    )
    try:
        outcome = service.execute_provider_call(
            invocation_id,
            typed_input=_request().typed_input,
            router=ProviderRouter(
                {
                    "codex": _ProcessRecordingProvider(
                        Path(marker_dir),
                        Path(release_path),
                    )
                }
            ),
        )
    except AgentRuntimeProviderExecutionBlocked as exc:
        return {"kind": "blocked", "detail": str(exc)}
    return {"kind": "outcome", "detail": outcome.outcome_digest}


def _run_process_wave(
    base_path: Path,
    invocation_id: str,
    observed_at: datetime,
) -> tuple[list[dict[str, object]], float]:
    timestamp = observed_at.isoformat(timespec="microseconds").replace("+00:00", "Z")
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=PROCESS_WORKERS) as pool:
        results = list(
            pool.map(
                _prepare_in_fresh_process,
                [str(base_path)] * PROCESS_REQUESTS,
                [invocation_id] * PROCESS_REQUESTS,
                [timestamp] * PROCESS_REQUESTS,
            )
        )
    return results, time.perf_counter() - started


def _identity_count(results: list[dict[str, object]], field: str) -> int:
    return len({str(result[field]) for result in results})


def test_cross_process_prelaunch_and_expired_claim_recovery_converge(
    tmp_path, authenticate_request
) -> None:
    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    invocation_id = admitted.invocation.invocation_id

    initial, initial_seconds = _run_process_wave(tmp_path, invocation_id, NOW)
    recovered, recovery_seconds = _run_process_wave(
        tmp_path,
        invocation_id,
        NOW + timedelta(seconds=301),
    )

    for field in ("receipt_id", "claim_id", "reservation_id", "continuation_id"):
        assert _identity_count(initial, field) == 1
        assert _identity_count(recovered, field) == 1
        assert initial[0][field] == recovered[0][field]
    assert {result["claim_generation"] for result in initial} == {1}
    assert {result["continuation_generation"] for result in initial} == {1}
    assert {result["claim_generation"] for result in recovered} == {2}
    assert {result["continuation_generation"] for result in recovered} == {2}

    with sqlite3.connect(db_path(tmp_path)) as connection:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "provider_work_receipts",
                "provider_work_execution_claims",
                "provider_invocation_reservations",
                "cloud_execution_continuations",
            )
        }
        outcome_count = connection.execute(
            "SELECT COUNT(*) FROM agent_invocation_provider_outcomes"
        ).fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]

    evidence = {
        "classification": "shaped-local-sqlite",
        "fault": "worker processes replaced after claim expiry",
        "initial_process_requests": len(initial),
        "initial_wall_seconds": initial_seconds,
        "recovery_process_requests": len(recovered),
        "recovery_wall_seconds": recovery_seconds,
        "process_workers": PROCESS_WORKERS,
        "record_counts": counts,
    }
    print(json.dumps(evidence, sort_keys=True))

    assert counts == {
        "provider_work_receipts": 1,
        "provider_work_execution_claims": 1,
        "provider_invocation_reservations": 1,
        "cloud_execution_continuations": 1,
    }
    assert outcome_count == 0
    assert integrity == "ok"
    assert initial_seconds < 30
    assert recovery_seconds < 30
    assert service.get_provider_outcome(invocation_id) is None


def test_concurrent_launch_has_one_provider_call_then_exact_replay(
    tmp_path, authenticate_request
) -> None:
    from tinyassets.agent_runtime_provider_execution import (
        AgentRuntimeProviderExecutionBlocked,
        AgentRuntimeProviderExecutionService,
    )

    service, admitted, _universe_dir, _manifest = _execution_service(tmp_path, authenticate_request)
    invocation_id = admitted.invocation.invocation_id
    entered_provider = threading.Event()
    release_provider = threading.Event()
    launch_barrier = threading.Barrier(THREAD_WORKERS)

    def hold_provider() -> None:
        entered_provider.set()
        assert release_provider.wait(timeout=20)

    provider = _RecordingProvider(on_call=hold_provider)
    router = ProviderRouter({"codex": provider})

    def launch(_index: int):
        contender = AgentRuntimeProviderExecutionService(
            tmp_path,
            grant_resolver=service.grant_resolver,
            provider_binding_resolver=service.provider_binding_resolver,
            clock=lambda: NOW,
        )
        launch_barrier.wait(timeout=20)
        try:
            return contender.execute_provider_call(
                invocation_id,
                typed_input=_request().typed_input,
                router=router,
            )
        except AgentRuntimeProviderExecutionBlocked as exc:
            return str(exc)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=THREAD_WORKERS) as pool:
        futures = [pool.submit(launch, index) for index in range(THREAD_WORKERS)]
        assert entered_provider.wait(timeout=20)
        time.sleep(0.25)
        assert len(provider.calls) == 1
        release_provider.set()
        first_wave = [future.result(timeout=20) for future in futures]
    launch_seconds = time.perf_counter() - started

    blocked = [result for result in first_wave if isinstance(result, str)]
    visible_outcomes = [result for result in first_wave if not isinstance(result, str)]
    assert visible_outcomes
    assert blocked
    assert set(blocked) <= _CONCURRENT_BLOCKERS
    assert len({result.outcome_digest for result in visible_outcomes}) == 1
    outcome = visible_outcomes[0]

    def replay(_index: int):
        return AgentRuntimeProviderExecutionService(
            tmp_path,
            grant_resolver=service.grant_resolver,
            provider_binding_resolver=service.provider_binding_resolver,
            clock=lambda: NOW,
        ).execute_provider_call(
            invocation_id,
            typed_input=_request().typed_input,
            router=router,
        )

    replay_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=THREAD_WORKERS) as pool:
        replays = list(pool.map(replay, range(THREAD_WORKERS)))
    replay_seconds = time.perf_counter() - replay_started

    with sqlite3.connect(db_path(tmp_path)) as connection:
        outcome_count = connection.execute(
            "SELECT COUNT(*) FROM agent_invocation_provider_outcomes"
        ).fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]

    evidence = {
        "classification": "shaped-local-sqlite-with-provider-test-double",
        "blocked_during_uncertain_window": len(blocked),
        "launch_contenders": len(first_wave),
        "launch_wall_seconds": launch_seconds,
        "provider_calls": len(provider.calls),
        "replay_requests": len(replays),
        "replay_wall_seconds": replay_seconds,
    }
    print(json.dumps(evidence, sort_keys=True))

    assert all(replay == outcome for replay in replays)
    assert len(provider.calls) == 1
    assert outcome_count == 1
    assert integrity == "ok"
    assert launch_seconds < 30
    assert replay_seconds < 30


def test_cross_process_launch_has_one_provider_call_and_typed_losers(
    tmp_path, authenticate_request
) -> None:
    _service, admitted, _universe_dir, _manifest = _execution_service(
        tmp_path, authenticate_request
    )
    invocation_id = admitted.invocation.invocation_id
    marker_dir = tmp_path / "provider-call-markers"
    marker_dir.mkdir()
    release_path = tmp_path / "provider-call-release"

    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=PROCESS_WORKERS) as pool:
        futures = [
            pool.submit(
                _launch_in_fresh_process,
                str(tmp_path),
                invocation_id,
                str(marker_dir),
                str(release_path),
            )
            for _index in range(PROCESS_REQUESTS)
        ]
        # This deadline is a HANG GUARD, not the invariant under test — that is
        # the `== 1` assertion below, which is untouched. It waits on a freshly
        # spawned Python process to import and reach its first provider call,
        # and 20s was tight enough that a loaded CI runner blew it
        # (observed: 149.047 vs a 149.042 deadline, a 5ms miss). Widening the
        # patience cannot make a losing race pass; it only stops a slow runner
        # from reading as a concurrency failure.
        deadline = time.monotonic() + 120
        while not list(marker_dir.glob("*.call")):
            assert time.monotonic() < deadline, (
                "no subprocess reached its provider call within 120s — the "
                "launch never happened, rather than the race resolving wrongly"
            )
            time.sleep(0.01)
        time.sleep(0.25)
        assert len(list(marker_dir.glob("*.call"))) == 1
        release_path.touch()
        results = [future.result(timeout=30) for future in futures]
    wall_seconds = time.perf_counter() - started

    markers = list(marker_dir.glob("*.call"))
    blockers = [result["detail"] for result in results if result["kind"] == "blocked"]
    outcomes = [result["detail"] for result in results if result["kind"] == "outcome"]
    with sqlite3.connect(db_path(tmp_path)) as connection:
        outcome_count = connection.execute(
            "SELECT COUNT(*) FROM agent_invocation_provider_outcomes"
        ).fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]

    evidence = {
        "classification": "shaped-local-sqlite-with-provider-test-double",
        "blocked_during_uncertain_window": len(blockers),
        "process_requests": len(results),
        "process_workers": PROCESS_WORKERS,
        "provider_call_markers": len(markers),
        "terminal_replays": len(outcomes),
        "wall_seconds": wall_seconds,
    }
    print(json.dumps(evidence, sort_keys=True))

    assert len(markers) == 1
    assert blockers
    assert set(blockers) <= _CONCURRENT_BLOCKERS
    assert outcomes
    assert len(set(outcomes)) == 1
    assert outcome_count == 1
    assert integrity == "ok"
    assert wall_seconds < 30
