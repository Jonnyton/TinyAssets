"""Dedicated-machine operator-admission v2 load harness.

This script authors the canonical 400-v2/100-v1/300-second topology but does
not run from pytest or CI. It exercises only the production admission store,
SQLite locks, epoch-2 claim adapter, and legacy v1 file lock. It never invokes
a model, provider, credential, market, payment, or hardware adapter.

Example (dedicated machine only):

    python tests/load/operator_admission_v2.py \
      --base-path D:/tinyassets-load/operator-v2 \
      --events-dir D:/tinyassets-load/operator-v2-events \
      --confirm-dedicated-machine
"""

from __future__ import annotations

import argparse
import multiprocessing
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from queue import Empty

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from operator_admission_v2_fixture import (  # noqa: E402
    commit_v2_request,
    emit_raw_event,
    initialize_fixture,
    inject_invalid_v2_fixture,
    quarantine_maintenance_process,
    seed_v1_host_rows,
    status_reader_process,
    v1_worker_process,
    v2_worker_process,
)

from tinyassets.storage.request_admissions import (  # noqa: E402
    IdempotencyKeyBodyConflict,
)


@dataclass(frozen=True, slots=True)
class HarnessConfig:
    base_path: Path
    events_dir: Path
    seed: int
    warm_seconds: int
    measure_seconds: int
    v2_workers: int
    v1_workers: int
    operator_requests: int
    ordinary_requests: int
    directed_requests: int
    status_readers: int
    invalid_fixtures: int
    status_hz: float
    poll_seconds: float

    @property
    def expected_processes(self) -> int:
        return self.v2_workers + self.v1_workers + self.status_readers + 1

    @property
    def total_requests(self) -> int:
        return self.operator_requests + self.ordinary_requests + self.directed_requests


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-path", type=Path, required=True)
    parser.add_argument("--events-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260725)
    parser.add_argument("--warm-seconds", type=int, default=60)
    parser.add_argument("--measure-seconds", type=int, default=300)
    parser.add_argument("--v2-workers", type=int, default=400)
    parser.add_argument("--v1-workers", type=int, default=100)
    parser.add_argument("--operator-requests", type=int, default=500)
    parser.add_argument("--ordinary-requests", type=int, default=300)
    parser.add_argument("--directed-requests", type=int, default=200)
    parser.add_argument("--status-readers", type=int, default=100)
    parser.add_argument("--invalid-fixtures", type=int, default=10)
    parser.add_argument("--status-hz", type=float, default=1.0)
    parser.add_argument("--poll-seconds", type=float, default=0.05)
    parser.add_argument(
        "--confirm-dedicated-machine",
        action="store_true",
        help="Required acknowledgement; the canonical defaults spawn 600 processes.",
    )
    return parser.parse_args(argv)


def _config(args: argparse.Namespace) -> HarnessConfig:
    values = (
        args.warm_seconds,
        args.measure_seconds,
        args.v2_workers,
        args.v1_workers,
        args.operator_requests,
        args.ordinary_requests,
        args.directed_requests,
        args.status_readers,
        args.invalid_fixtures,
    )
    if any(value < 0 for value in values):
        raise ValueError("load counts and durations must be non-negative")
    if args.status_hz <= 0 or args.poll_seconds <= 0:
        raise ValueError("status_hz and poll_seconds must be positive")
    config = HarnessConfig(
        base_path=args.base_path.resolve(),
        events_dir=args.events_dir.resolve(),
        seed=args.seed,
        warm_seconds=args.warm_seconds,
        measure_seconds=args.measure_seconds,
        v2_workers=args.v2_workers,
        v1_workers=args.v1_workers,
        operator_requests=args.operator_requests,
        ordinary_requests=args.ordinary_requests,
        directed_requests=args.directed_requests,
        status_readers=args.status_readers,
        invalid_fixtures=args.invalid_fixtures,
        status_hz=args.status_hz,
        poll_seconds=args.poll_seconds,
    )
    if config.total_requests <= 0:
        raise ValueError("at least one request is required")
    return config


def _require_new_output_paths(config: HarnessConfig) -> None:
    for path in (config.base_path, config.events_dir):
        if path.exists() and any(path.iterdir()):
            raise RuntimeError(f"refusing non-empty load path {path}; use fresh directories")


def _spawn_processes(
    config: HarnessConfig,
    context: multiprocessing.context.BaseContext,
    stop_event,
    ready_queue,
    processes: list[multiprocessing.Process],
) -> list[str]:
    v2_worker_ids = [f"load-v2-{index:04d}" for index in range(config.v2_workers)]
    for index, worker_id in enumerate(v2_worker_ids):
        processes.append(
            context.Process(
                name=worker_id,
                target=v2_worker_process,
                args=(
                    str(config.base_path),
                    str(config.events_dir),
                    worker_id,
                    stop_event,
                    ready_queue,
                    config.poll_seconds,
                    config.seed + index,
                ),
            )
        )
    for index in range(config.v1_workers):
        worker_id = f"load-v1-{index:04d}"
        processes.append(
            context.Process(
                name=worker_id,
                target=v1_worker_process,
                args=(
                    str(config.base_path),
                    str(config.events_dir),
                    worker_id,
                    stop_event,
                    ready_queue,
                    config.poll_seconds,
                ),
            )
        )
    for index in range(config.status_readers):
        reader_id = f"status-{index:04d}"
        processes.append(
            context.Process(
                name=reader_id,
                target=status_reader_process,
                args=(
                    str(config.base_path),
                    str(config.events_dir),
                    reader_id,
                    stop_event,
                    ready_queue,
                    1.0 / config.status_hz,
                ),
            )
        )
    processes.append(
        context.Process(
            name="epoch2-quarantine-maintenance",
            target=quarantine_maintenance_process,
            args=(
                str(config.base_path),
                str(config.events_dir),
                stop_event,
                ready_queue,
                config.invalid_fixtures,
                1.0,
            ),
        )
    )
    for process in processes:
        if process.pid is None:
            process.start()
    return v2_worker_ids


def _wait_until_ready(
    config: HarnessConfig,
    processes: list[multiprocessing.Process],
    ready_queue,
) -> None:
    ready: set[int] = set()
    deadline = time.monotonic() + max(120, config.expected_processes)
    while len(ready) < config.expected_processes:
        _require_population(processes)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(
                f"only {len(ready)}/{config.expected_processes} processes became ready"
            )
        try:
            kind, identity, pid = ready_queue.get(timeout=min(1.0, remaining))
        except Empty:
            continue
        ready.add(int(pid))
        emit_raw_event(
            config.events_dir,
            "process_ready_observed",
            identity=identity,
            kind=kind,
            ready_count=len(ready),
        )


def _require_population(processes: list[multiprocessing.Process]) -> None:
    dead = [
        (process.name, process.pid, process.exitcode)
        for process in processes
        if not process.is_alive()
    ]
    if dead:
        raise RuntimeError(f"load population dropped: {dead[:10]}")


def _hold_population(
    config: HarnessConfig,
    processes: list[multiprocessing.Process],
    *,
    duration_seconds: float,
    phase: str,
) -> None:
    deadline = time.monotonic() + duration_seconds
    while time.monotonic() < deadline:
        _require_population(processes)
        emit_raw_event(
            config.events_dir,
            "population_sample",
            alive=sum(process.is_alive() for process in processes),
            expected=len(processes),
            phase=phase,
        )
        time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))


def _stop_owned_processes(
    processes: list[multiprocessing.Process],
    stop_event,
) -> list[multiprocessing.Process]:
    stop_event.set()
    graceful_deadline = time.monotonic() + 30
    for process in processes:
        if process.pid is None:
            continue
        process.join(timeout=max(0.0, graceful_deadline - time.monotonic()))

    survivors = [process for process in processes if process.is_alive()]
    for process in survivors:
        process.terminate()
    terminate_deadline = time.monotonic() + 10
    for process in survivors:
        process.join(timeout=max(0.0, terminate_deadline - time.monotonic()))

    stubborn = [process for process in survivors if process.is_alive()]
    for process in stubborn:
        process.kill()
    kill_deadline = time.monotonic() + 5
    for process in stubborn:
        process.join(timeout=max(0.0, kill_deadline - time.monotonic()))
    return [process for process in stubborn if process.is_alive()]


def _request_schedule(config: HarnessConfig) -> list[str]:
    schedule = (
        ["operator"] * config.operator_requests
        + ["ordinary"] * config.ordinary_requests
        + ["directed"] * config.directed_requests
    )
    random.Random(config.seed).shuffle(schedule)
    return schedule


def _commit_with_optional_concurrent_replay(
    config: HarnessConfig,
    *,
    sequence: int,
    request_class: str,
    directed_daemon_id: str,
    executor: ThreadPoolExecutor,
) -> None:
    if sequence % 10:
        commit_v2_request(
            config.base_path,
            config.events_dir,
            sequence=sequence,
            request_class=request_class,
            directed_daemon_id=directed_daemon_id,
        )
        return

    start_barrier = threading.Barrier(2)

    def commit(replay: bool):
        start_barrier.wait()
        return commit_v2_request(
            config.base_path,
            config.events_dir,
            sequence=sequence,
            request_class=request_class,
            directed_daemon_id=directed_daemon_id,
            replay=replay,
        )

    first = executor.submit(commit, False)
    second = executor.submit(commit, True)
    results = (first.result(), second.result())
    if sorted(result["idempotent_replay"] for result in results) != [
        False,
        True,
    ]:
        raise RuntimeError("concurrent replay did not produce one original")
    if (
        len(
            {
                (
                    result["admission_id"],
                    result["request_id"],
                    result["branch_task_id"],
                )
                for result in results
            }
        )
        != 1
    ):
        raise RuntimeError("concurrent replay returned different durable IDs")


def _run_measurement(
    config: HarnessConfig,
    processes: list[multiprocessing.Process],
    v2_worker_ids: list[str],
) -> None:
    schedule = _request_schedule(config)
    if config.directed_requests and not v2_worker_ids:
        raise RuntimeError("directed requests require at least one v2 worker")
    interval = config.measure_seconds / len(schedule)
    started = time.monotonic()
    emit_raw_event(
        config.events_dir,
        "measurement_started",
        duration_seconds=config.measure_seconds,
        request_count=len(schedule),
    )
    with ThreadPoolExecutor(max_workers=8) as executor:
        for sequence, request_class in enumerate(schedule):
            target = started + sequence * interval
            while time.monotonic() < target:
                _require_population(processes)
                time.sleep(min(0.05, target - time.monotonic()))
            directed = (
                v2_worker_ids[sequence % len(v2_worker_ids)] if request_class == "directed" else ""
            )
            _commit_with_optional_concurrent_replay(
                config,
                sequence=sequence,
                request_class=request_class,
                directed_daemon_id=directed,
                executor=executor,
            )
            if sequence % 100:
                continue
            try:
                commit_v2_request(
                    config.base_path,
                    config.events_dir,
                    sequence=sequence,
                    request_class=request_class,
                    directed_daemon_id=directed,
                    conflict=True,
                )
            except IdempotencyKeyBodyConflict:
                emit_raw_event(
                    config.events_dir,
                    "expected_idempotency_conflict",
                    sequence=sequence,
                )
            else:
                raise RuntimeError("changed-body idempotency conflict was accepted")
            cross_scope = commit_v2_request(
                config.base_path / "_cross_scope_probe",
                config.events_dir,
                sequence=sequence,
                request_class=request_class,
                directed_daemon_id=directed,
            )
            second_scope = commit_v2_request(
                config.base_path / "_cross_scope_probe",
                config.events_dir,
                sequence=sequence,
                request_class=request_class,
                directed_daemon_id=directed,
                actor_id="load-actor-cross-scope",
            )
            if cross_scope["admission_id"] == second_scope["admission_id"]:
                raise RuntimeError("cross-scope key reused one admission")
            emit_raw_event(
                config.events_dir,
                "cross_scope_key_independent",
                admission_ids=[
                    cross_scope["admission_id"],
                    second_scope["admission_id"],
                ],
                sequence=sequence,
                store="separate_probe",
            )
    _hold_population(
        config,
        processes,
        duration_seconds=max(0.0, started + config.measure_seconds - time.monotonic()),
        phase="measurement_tail",
    )
    emit_raw_event(config.events_dir, "measurement_finished")


def run(config: HarnessConfig) -> int:
    _require_new_output_paths(config)
    config.base_path.mkdir(parents=True)
    config.events_dir.mkdir(parents=True)
    initialize_fixture(config.base_path, config.events_dir)
    initialize_fixture(
        config.base_path / "_cross_scope_probe",
        config.events_dir,
    )
    seed_v1_host_rows(
        config.base_path,
        config.events_dir,
        count=config.v1_workers,
    )
    for sequence in range(config.invalid_fixtures):
        inject_invalid_v2_fixture(
            config.base_path,
            config.events_dir,
            sequence=sequence,
        )

    context = multiprocessing.get_context("spawn")
    stop_event = context.Event()
    ready_queue = context.Queue()
    processes: list[multiprocessing.Process] = []
    try:
        v2_worker_ids = _spawn_processes(
            config,
            context,
            stop_event,
            ready_queue,
            processes,
        )
        _wait_until_ready(config, processes, ready_queue)
        _hold_population(
            config,
            processes,
            duration_seconds=config.warm_seconds,
            phase="warmup",
        )
        _run_measurement(config, processes, v2_worker_ids)
        return 0
    finally:
        survivors = _stop_owned_processes(processes, stop_event)
        emit_raw_event(
            config.events_dir,
            "harness_stopped",
            survivor_count=len(survivors),
        )
        if survivors:
            raise RuntimeError(
                "owned load processes survived kill: "
                + ", ".join(process.name for process in survivors[:10])
            )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.confirm_dedicated_machine:
        raise SystemExit(
            "--confirm-dedicated-machine is required; canonical defaults "
            "spawn 600 processes and run for 360 seconds"
        )
    return run(_config(args))


if __name__ == "__main__":
    raise SystemExit(main())
