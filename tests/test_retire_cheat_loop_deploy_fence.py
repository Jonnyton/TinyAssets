"""Focused tests for the transitional retire-cheat-loop task 2.1 deploy fence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

import scripts.retire_cheat_loop_deploy_fence as fence
from scripts.retire_cheat_loop_deploy_fence import (
    DAEMON_SERVICE,
    EXPECTED_CONTAINERS,
    RESTART_RACER_UNITS,
    FenceError,
    expire_recovery,
    fence_status,
    finalize_recovery,
    inventory_queue_risk,
    post_canary,
    preflight,
    prepare_deploy,
    prove,
    quiesce_unsafe,
    receipt_snapshot,
    recover_unsafe,
    refence_recovery,
    resolve_receipt_store,
    restore_if_safe,
    safe_fleet_matches,
)

RUN_ID = "test-run-1"


def _create_receipt_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE wiki_trigger_attempts (
                trigger_attempt_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                request_kind TEXT NOT NULL,
                request_page TEXT NOT NULL,
                status TEXT NOT NULL,
                attempted_at TEXT NOT NULL,
                goal_id TEXT,
                branch_def_id TEXT,
                queued_at TEXT,
                run_id TEXT,
                dispatcher_request_id TEXT,
                error_class TEXT,
                error_message TEXT
            );
            """
        )


def test_absent_receipt_snapshot_has_defined_read_only_shape(tmp_path: Path):
    assert receipt_snapshot(tmp_path / "missing.db") == {
        "exists": False,
        "quick_check": ["absent"],
        "schema": [],
        "row_count": 0,
        "status_counts": {},
        "max_attempted_at": None,
        "logical_digest": (
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855"
        ),
    }


def test_receipt_snapshot_records_schema_counts_max_and_logical_digest(tmp_path: Path):
    path = tmp_path / "wiki_trigger_attempts.db"
    _create_receipt_db(path)
    with sqlite3.connect(path) as connection:
        connection.executemany(
            """
            INSERT INTO wiki_trigger_attempts (
                trigger_attempt_id, request_id, request_kind, request_page,
                status, attempted_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("attempt-2", "BUG-2", "bug", "pages/bugs/two.md", "queued", "2026-02-02"),
                ("attempt-1", "BUG-1", "bug", "pages/bugs/one.md", "pending", "2026-01-01"),
            ],
        )

    first = receipt_snapshot(path)
    second = receipt_snapshot(path)

    assert first == second
    assert first["quick_check"] == ["ok"]
    assert first["row_count"] == 2
    assert first["status_counts"] == {"pending": 1, "queued": 1}
    assert first["max_attempted_at"] == "2026-02-02"
    assert first["schema"]
    assert len(first["logical_digest"]) == 64


def test_receipt_snapshot_rejects_corrupt_or_unexpected_schema(tmp_path: Path):
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not sqlite")
    with pytest.raises(FenceError, match="receipt sqlite unreadable"):
        receipt_snapshot(corrupt)

    wrong = tmp_path / "wrong.db"
    with sqlite3.connect(wrong) as connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
    with pytest.raises(FenceError, match="exact receipt schema"):
        receipt_snapshot(wrong)


def test_queue_inventory_finds_v1_pending_and_running_only(tmp_path: Path):
    universe = tmp_path / "universes" / "one"
    universe.mkdir(parents=True)
    (universe / "branch_tasks.json").write_text(
        json.dumps(
            [
                {
                    "branch_task_id": "pending",
                    "request_type": "bug_investigation",
                    "status": "pending",
                },
                {
                    "branch_task_id": "running",
                    "request_type": "bug_investigation",
                    "status": "running",
                },
                {
                    "branch_task_id": "done",
                    "request_type": "bug_investigation",
                    "status": "succeeded",
                },
                {
                    "branch_task_id": "generic",
                    "request_type": "branch_run",
                    "status": "pending",
                },
            ]
        ),
        encoding="utf-8",
    )

    assert inventory_queue_risk(tmp_path) == [
        {
            "id": "pending",
            "status": "pending",
            "store": "universes/one/branch_tasks.json",
            "version": "v1",
        },
        {
            "id": "running",
            "status": "running",
            "store": "universes/one/branch_tasks.json",
            "version": "v1",
        },
    ]


def test_queue_inventory_v2_joins_authoritative_user_request_type(tmp_path: Path):
    universe = tmp_path / "universes" / "two"
    universe.mkdir(parents=True)
    db = universe / ".tinyassets.db"
    with sqlite3.connect(db) as connection:
        connection.executescript(
            """
            CREATE TABLE user_requests (
                request_id TEXT PRIMARY KEY,
                request_type TEXT NOT NULL
            );
            CREATE TABLE branch_tasks_v2 (
                branch_task_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                status TEXT NOT NULL
            );
            """
        )
        connection.executemany(
            "INSERT INTO user_requests VALUES (?, ?)",
            [
                ("req-p", "bug_investigation"),
                ("req-r", "bug_investigation"),
                ("req-c", "bug_investigation"),
                ("req-g", "branch_run"),
            ],
        )
        connection.executemany(
            "INSERT INTO branch_tasks_v2 VALUES (?, ?, ?)",
            [
                ("task-p", "req-p", "pending"),
                ("task-r", "req-r", "running"),
                ("task-c", "req-c", "cancel_requested"),
                ("task-g", "req-g", "pending"),
            ],
        )

    risks = inventory_queue_risk(tmp_path)
    assert [(row["id"], row["status"]) for row in risks] == [
        ("task-c", "cancel_requested"),
        ("task-p", "pending"),
        ("task-r", "running"),
    ]
    assert all(row["version"] == "v2" for row in risks)


def test_queue_inventory_v2_fails_closed_on_live_orphan_request(tmp_path: Path):
    db = tmp_path / ".tinyassets.db"
    with sqlite3.connect(db) as connection:
        connection.executescript(
            """
            CREATE TABLE user_requests (
                request_id TEXT PRIMARY KEY,
                request_type TEXT NOT NULL
            );
            CREATE TABLE branch_tasks_v2 (
                branch_task_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                status TEXT NOT NULL
            );
            INSERT INTO branch_tasks_v2 VALUES ('orphan', 'missing', 'running');
            """
        )

    with pytest.raises(FenceError, match="missing authoritative request type"):
        inventory_queue_risk(tmp_path)


def test_queue_inventory_v2_runs_foreign_key_check(tmp_path: Path):
    db = tmp_path / ".tinyassets.db"
    with sqlite3.connect(db) as connection:
        connection.executescript(
            """
            CREATE TABLE user_requests (
                request_id TEXT PRIMARY KEY,
                request_type TEXT NOT NULL
            );
            CREATE TABLE branch_tasks_v2 (
                branch_task_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL
                    REFERENCES user_requests(request_id),
                status TEXT NOT NULL
            );
            INSERT INTO branch_tasks_v2 VALUES ('orphan', 'missing', 'running');
            """
        )

    with pytest.raises(FenceError, match="foreign key check failed"):
        inventory_queue_risk(tmp_path)


def test_queue_inventory_fails_closed_on_unreadable_or_partial_store(tmp_path: Path):
    (tmp_path / "branch_tasks.json").write_text("{", encoding="utf-8")
    with pytest.raises(FenceError, match="v1 queue unreadable"):
        inventory_queue_risk(tmp_path)

    (tmp_path / "branch_tasks.json").unlink()
    with sqlite3.connect(tmp_path / ".tinyassets.db") as connection:
        connection.execute("CREATE TABLE branch_tasks_v2 (branch_task_id TEXT)")
    with pytest.raises(FenceError, match="v2 queue schema incomplete"):
        inventory_queue_risk(tmp_path)


def test_receipt_store_requires_one_shared_volume_and_data_relative_override(tmp_path: Path):
    inspections = {
        name: {
            "Id": f"id-{index}",
            "State": {"Running": True, "Pid": 100 + index},
            "Config": {"Env": ["TINYASSETS_TRIGGER_RECEIPTS_DB=/data/receipts.db"]},
            "Mounts": [
                {
                    "Destination": "/data",
                    "Name": "tinyassets-data",
                    "Source": str(tmp_path),
                }
            ],
        }
        for index, name in enumerate(EXPECTED_CONTAINERS)
    }
    selected = resolve_receipt_store(inspections, tmp_path)
    assert selected.container_path == "/data/receipts.db"
    assert selected.host_path == tmp_path / "receipts.db"

    inspections["tinyassets-worker"]["Config"]["Env"] = [
        "TINYASSETS_TRIGGER_RECEIPTS_DB=/tmp/escape.db"
    ]
    with pytest.raises(FenceError, match="outside /data"):
        resolve_receipt_store(inspections, tmp_path)


def test_restart_racer_inventory_includes_all_three_watchdog_families():
    assert set(RESTART_RACER_UNITS) == {
        "daemon-watchdog.timer",
        "daemon-watchdog.service",
        "tinyassets-watchdog.timer",
        "tinyassets-watchdog.service",
        "tinyassets-autoheal.timer",
        "tinyassets-autoheal.service",
    }
    assert DAEMON_SERVICE == "tinyassets-daemon.service"


def test_volume_consumer_inventory_includes_stopped_containers():
    class CaptureHost(fence.Host):
        def __init__(self) -> None:
            self.args: list[str] = []

        def run(
            self,
            args: Any,
            *,
            check: bool = True,
            input_text: str | None = None,
        ) -> str:
            del check, input_text
            self.args = list(args)
            return "tinyassets-daemon\nstopped-extra"

    host = CaptureHost()
    assert host.volume_container_names() == ["stopped-extra", "tinyassets-daemon"]
    assert "-a" in host.args


def test_safe_fleet_requires_exact_five_exact_digest_revision_and_no_old_ids():
    image_ref = "ghcr.io/jonnyton/tinyassets-daemon@sha256:" + "a" * 64
    revision = "b" * 40
    observation = {
        "containers": {
            name: {
                "id": f"new-{index}",
                "running": True,
                "image_ref": image_ref,
                "revision": revision,
            }
            for index, name in enumerate(EXPECTED_CONTAINERS)
        },
        "volume_container_names": list(EXPECTED_CONTAINERS),
        "stray_writer_processes": [],
        "queue_risk": [],
    }
    old_ids = {name: f"old-{index}" for index, name in enumerate(EXPECTED_CONTAINERS)}
    assert safe_fleet_matches(observation, image_ref, revision, old_ids)

    observation["containers"]["tinyassets-worker"]["revision"] = "c" * 40
    assert not safe_fleet_matches(observation, image_ref, revision, old_ids)


class LifecycleHost:
    def __init__(self, volume_dir: Path) -> None:
        self.volume = volume_dir
        self.old_image_ref = "ghcr.io/jonnyton/tinyassets-daemon@sha256:" + "a" * 64
        self.old_revision = "a" * 40
        self.target_image_ref = (
            "ghcr.io/jonnyton/tinyassets-daemon@sha256:" + "b" * 64
        )
        self.target_revision = "b" * 40
        self.image_identities = {
            "sha256:old": (self.old_image_ref, self.old_revision),
            self.old_image_ref: (self.old_image_ref, self.old_revision),
            self.target_image_ref: (self.target_image_ref, self.target_revision),
            "sha256:target": (self.target_image_ref, self.target_revision),
        }
        self.containers = self._containers("old", "sha256:old", running=True)
        self.units = {
            unit: {
                "active": "active" if unit.endswith(".timer") else "inactive",
                "enabled": "enabled" if unit.endswith(".timer") else "static",
                "load": "loaded",
            }
            for unit in RESTART_RACER_UNITS
        }
        self.units[DAEMON_SERVICE] = {
            "active": "active",
            "enabled": "enabled",
            "load": "loaded",
        }
        self.units[fence.RECOVERY_RECONCILE_SERVICE] = {
            "active": "inactive",
            "enabled": "enabled",
            "load": "loaded",
        }
        self.calls: list[tuple[str, ...]] = []
        self.stubborn_unit: str | None = None
        self.unmask_noop = False
        self.unmask_error = False
        self.container_state_error = False
        self.container_state_override: str | None = None
        self.restart_policy_override: str | None = None
        self.start_installs_target = False

    def _containers(
        self,
        prefix: str,
        image: str,
        *,
        running: bool,
    ) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "Id": f"{prefix}-{index}",
                "Image": image,
                "State": {"Running": running, "Pid": 1000 + index if running else 0},
                "HostConfig": {"RestartPolicy": {"Name": "always"}},
                "Config": {"Env": [], "Labels": {}},
                "Mounts": [
                    {
                        "Destination": "/data",
                        "Name": "tinyassets-data",
                        "Source": str(self.volume),
                    }
                ],
            }
            for index, name in enumerate(EXPECTED_CONTAINERS)
        }

    def install_target_fleet(self) -> None:
        self.containers = self._containers(
            "target",
            "sha256:target",
            running=True,
        )
        self.units[DAEMON_SERVICE]["active"] = "active"

    def container_info(self, name: str) -> dict[str, Any]:
        return json.loads(json.dumps(self.containers[name]))

    def image_identity(self, image: str, expected_repository: str) -> tuple[str, str]:
        del expected_repository
        return self.image_identities[image]

    def volume_dir(self) -> Path:
        return self.volume

    def volume_container_names(self) -> list[str]:
        return sorted(self.containers)

    def container_pids(self, names: Any) -> set[int]:
        return {
            int(self.containers[name]["State"]["Pid"])
            for name in names
            if self.containers[name]["State"]["Running"]
        }

    def container_restart_policy(self, identity: str) -> str:
        if self.restart_policy_override is not None:
            return self.restart_policy_override
        for info in self.containers.values():
            if identity == info["Id"]:
                return str(info["HostConfig"]["RestartPolicy"]["Name"])
        raise FenceError("container restart policy unavailable")

    def unit_present(self, unit: str) -> bool:
        return unit in self.units

    def unit_load_state(self, unit: str) -> str:
        return self.units[unit]["load"] if unit in self.units else "not-found"

    def unit_state(self, unit: str) -> dict[str, str]:
        state = self.units[unit]
        return {"active": state["active"], "enabled": state["enabled"]}

    def unit_active_state(self, unit: str) -> str:
        return self.units[unit]["active"]

    def run(
        self,
        args: list[str] | tuple[str, ...],
        *,
        check: bool = True,
        input_text: str | None = None,
    ) -> str:
        del check, input_text
        command = tuple(args)
        self.calls.append(command)
        if command[0] == "systemctl":
            action = command[1]
            units = [
                value
                for value in command[2:]
                if value not in {"--now", "--runtime"}
            ]
            if action == "disable":
                for unit in units:
                    self.units[unit]["enabled"] = "disabled"
                    if "--now" in command and unit != self.stubborn_unit:
                        self.units[unit]["active"] = "inactive"
            elif action == "stop":
                for unit in units:
                    if unit in self.units and unit != self.stubborn_unit:
                        self.units[unit]["active"] = "inactive"
            elif action == "mask":
                for unit in units:
                    self.units[unit]["enabled"] = "masked-runtime"
                    self.units[unit]["load"] = "masked"
            elif action == "unmask" and self.unmask_error:
                raise FenceError("systemctl unmask failed")
            elif action == "unmask" and not self.unmask_noop:
                for unit in units:
                    self.units[unit]["enabled"] = (
                        "static" if unit.endswith(".service") else "disabled"
                    )
                    self.units[unit]["load"] = "loaded"
            elif action == "enable":
                for unit in units:
                    self.units[unit]["enabled"] = "enabled"
            elif action == "start":
                for unit in units:
                    self.units[unit]["active"] = "active"
                if (
                    DAEMON_SERVICE in units
                    and self.start_installs_target
                    and not self.containers
                ):
                    configured = fence._configured_image()
                    image = (
                        "sha256:target"
                        if configured == self.target_image_ref
                        else "sha256:old"
                    )
                    self.containers = self._containers(
                        "recovered",
                        image,
                        running=True,
                    )
                    for info in self.containers.values():
                        info["HostConfig"]["RestartPolicy"]["Name"] = "no"
            return ""
        if command[0] == "systemd-run":
            unit = next(
                value.partition("=")[2]
                for value in command
                if value.startswith("--unit=")
            )
            self.units[f"{unit}.timer"] = {
                "active": "active",
                "enabled": "transient",
                "load": "loaded",
            }
            self.units[f"{unit}.service"] = {
                "active": "inactive",
                "enabled": "transient",
                "load": "loaded",
            }
            return ""
        if command[:2] == ("docker", "compose"):
            if self.start_installs_target:
                configured = fence._configured_image()
                image = (
                    "sha256:target"
                    if configured == self.target_image_ref
                    else "sha256:old"
                )
                self.containers = self._containers(
                    "recovered",
                    image,
                    running=True,
                )
                project = command[command.index("--project-name") + 1]
                for info in self.containers.values():
                    info["HostConfig"]["RestartPolicy"]["Name"] = "no"
                    info["Config"]["Labels"][
                        "com.docker.compose.project"
                    ] = project
            return ""
        if command[:2] == ("docker", "update"):
            policy = next(
                value.partition("=")[2]
                for value in command
                if value.startswith("--restart=")
            )
            identity = command[-1]
            for name, info in self.containers.items():
                if identity in {name, info["Id"]}:
                    info["HostConfig"]["RestartPolicy"]["Name"] = policy
                    break
            else:
                raise FenceError("docker update failed")
            return ""
        if command[:2] == ("docker", "stop"):
            for identity in command[2:]:
                for name, info in self.containers.items():
                    if identity in {info["Id"], name}:
                        info["State"]["Running"] = False
                        info["State"]["Pid"] = 0
            return ""
        if command[:2] == ("docker", "ps") and "-a" in command:
            if self.container_state_error:
                raise FenceError("docker ps failed")
            if self.container_state_override is not None:
                return self.container_state_override
            identity = next(
                value.removeprefix("id=")
                for value in command
                if value.startswith("id=")
            )
            for name, info in self.containers.items():
                del name
                if identity == info["Id"]:
                    state = "running" if info["State"]["Running"] else "exited"
                    return f"{identity}|{state}"
            return ""
        if command[:2] == ("docker", "ps"):
            selected = next(
                value.removeprefix("name=^/").removesuffix("$")
                for value in command
                if value.startswith("name=^/")
            )
            info = self.containers.get(selected)
            return selected if info and info["State"]["Running"] else ""
        if command[:3] == ("docker", "inspect", "--format"):
            identity = command[-1]
            for name, info in self.containers.items():
                if identity in {name, info["Id"]}:
                    return str(info["State"]["Running"]).lower()
            return ""
        raise AssertionError(f"unexpected command: {command}")


def _patch_lifecycle_runtime(
    monkeypatch: pytest.MonkeyPatch,
    configured_ref: list[str],
) -> None:
    monkeypatch.setattr(fence, "_configured_image", lambda: configured_ref[0])
    monkeypatch.setattr(fence, "_stray_writer_processes", lambda *_args: [])
    monkeypatch.setattr(fence.time, "sleep", lambda _seconds: None)

    @contextmanager
    def test_lock(_path: Path):
        yield

    monkeypatch.setattr(fence, "_operation_lock", test_lock)


def test_full_lifecycle_executes_every_command_and_restores_exact_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    host = LifecycleHost(tmp_path)
    configured_ref = [host.old_image_ref]
    _patch_lifecycle_runtime(monkeypatch, configured_ref)
    state_path = tmp_path / "fence-state.json"

    preflight_result = preflight(
        host,
        image_ref=host.target_image_ref,
        target_revision=host.target_revision,
        run_id=RUN_ID,
        state_path=state_path,
    )
    assert preflight_result["phase"] == "preflight_proved"

    configured_ref[0] = host.target_image_ref
    assert prepare_deploy(
        host,
        image_ref=host.target_image_ref,
        run_id=RUN_ID,
        state_path=state_path,
    )["phase"] == "target_installed"
    host.install_target_fleet()
    assert prove(
        host,
        image_ref=host.target_image_ref,
        revision=host.target_revision,
        run_id=RUN_ID,
        state_path=state_path,
    )["phase"] == "safe_fleet"
    assert post_canary(
        host,
        image_ref=host.target_image_ref,
        revision=host.target_revision,
        run_id=RUN_ID,
        state_path=state_path,
    )["phase"] == "post_canary_proved"
    assert fence_status(host, run_id=RUN_ID, state_path=state_path)["state_phase"] == (
        "post_canary_proved"
    )
    restored = restore_if_safe(
        host,
        image_ref=host.target_image_ref,
        revision=host.target_revision,
        run_id=RUN_ID,
        state_path=state_path,
    )
    assert restored["phase"] == "restored"
    assert restored["masked_units_after"] == []
    for unit in (*RESTART_RACER_UNITS, DAEMON_SERVICE):
        assert host.unit_state(unit)["enabled"] != "masked-runtime"
    for unit in RESTART_RACER_UNITS:
        if unit.endswith(".timer"):
            assert host.unit_state(unit) == {
                "active": "active",
                "enabled": "enabled",
            }
    assert host.unit_state(DAEMON_SERVICE) == {
        "active": "active",
        "enabled": "enabled",
    }
    second_run = fence.main(
        [
            "--state-path",
            str(state_path),
            "preflight",
            "--image-ref",
            "not-an-immutable-digest",
            "--revision",
            host.target_revision,
            "--run-id",
            "test-run-2",
        ],
        host=host,
    )
    second_failure = json.loads(capsys.readouterr().out)
    assert second_run == 2
    assert second_failure["stale_state_ignored"] is True
    assert not second_failure.get("cutover_started", False)


def test_new_run_preflight_failure_ignores_stale_restored_generation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "fence-state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "owner": "retire-cheat-loop task 2.1",
                "run_id": "prior-run-1",
                "phase": "restored",
            }
        ),
        encoding="utf-8",
    )

    return_code = fence.main(
        [
            "--state-path",
            str(state_path),
            "preflight",
            "--image-ref",
            "not-an-immutable-digest",
            "--revision",
            host.target_revision,
            "--run-id",
            "current-run-2",
        ],
        host=host,
    )

    failure = json.loads(capsys.readouterr().out)
    assert return_code == 2
    assert failure["stale_state_ignored"] is True
    assert not failure.get("cutover_started", False)
    status = fence_status(
        host,
        run_id="current-run-2",
        state_path=state_path,
    )
    assert status["current_run_matches"] is False
    assert status["current_run_cutover_started"] is False


def test_operation_lock_blocks_status_until_inflight_command_finishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    first_started = threading.Event()
    release_first = threading.Event()
    status_executed = threading.Event()

    class FakeFcntl:
        LOCK_EX = 1
        LOCK_NB = 2
        LOCK_UN = 4

        def __init__(self) -> None:
            self.mutex = threading.Lock()

        def flock(self, _descriptor: int, operation: int) -> None:
            if operation & self.LOCK_EX:
                self.mutex.acquire()
            else:
                self.mutex.release()

    def execute(args: Any, _host: Any) -> dict[str, Any]:
        if args.command == "observe" and args.image_ref == "first":
            first_started.set()
            assert release_first.wait(timeout=2)
        else:
            status_executed.set()
        return {"command": args.command}

    monkeypatch.setattr(fence, "fcntl", FakeFcntl())
    monkeypatch.setattr(fence, "_execute", execute)
    lock_path = tmp_path / "host-operation.lock"
    first = threading.Thread(
        target=fence.main,
        args=(
            [
                "--lock-path",
                str(lock_path),
                "observe",
                "--image-ref",
                "first",
            ],
        ),
    )
    second = threading.Thread(
        target=fence.main,
        args=(
            [
                "--lock-path",
                str(lock_path),
                "status",
                "--run-id",
                RUN_ID,
            ],
        ),
    )

    first.start()
    assert first_started.wait(timeout=2)
    second.start()
    time.sleep(0.05)
    assert not status_executed.is_set()
    release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)
    assert status_executed.is_set()
    assert not first.is_alive()
    assert not second.is_alive()


def test_operation_lock_fails_closed_without_flock_primitive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(fence, "fcntl", None)
    with pytest.raises(FenceError, match="lock primitive is unavailable"):
        with fence._operation_lock(tmp_path / "host-operation.lock"):
            pytest.fail("lock body must not execute")


def test_operation_lock_timeout_is_bounded_and_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    class BusyFcntl:
        LOCK_EX = 1
        LOCK_NB = 2
        LOCK_UN = 4

        @staticmethod
        def flock(_descriptor: int, operation: int) -> None:
            if operation & BusyFcntl.LOCK_EX:
                raise BlockingIOError("busy")

    monkeypatch.setattr(fence, "fcntl", BusyFcntl())
    with pytest.raises(FenceError, match="lock timed out after 0s"):
        with fence._operation_lock(
            tmp_path / "host-operation.lock",
            timeout_seconds=0,
        ):
            pytest.fail("timed-out lock body must not execute")


def test_host_command_timeout_becomes_fence_error(
    monkeypatch: pytest.MonkeyPatch,
):
    observed: dict[str, Any] = {}

    def timeout_run(args: Any, **kwargs: Any) -> Any:
        observed.update(kwargs)
        raise fence.subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(fence.subprocess, "run", timeout_run)
    with pytest.raises(FenceError, match="host command timed out after 45s"):
        fence.Host().run(["docker", "ps"])
    assert observed["timeout"] == fence.HOST_COMMAND_TIMEOUT_SECONDS


def test_guarded_mutation_strips_separator_before_invoking_command(
    tmp_path: Path,
):
    class GuardHost:
        def __init__(self) -> None:
            self.command: list[str] | None = None
            self.timeout_seconds: int | None = None

        def unit_present(self, _unit: str) -> bool:
            return False

        def volume_container_names(self) -> list[str]:
            return []

        def run(
            self,
            args: Any,
            *,
            timeout_seconds: int,
        ) -> str:
            self.command = list(args)
            self.timeout_seconds = timeout_seconds
            return ""

    host = GuardHost()
    args = fence._parser().parse_args(
        [
            "--state-path",
            str(tmp_path / "missing-state.json"),
            "guard-host-mutation",
            "--command-timeout",
            "120",
            "--",
            "/bin/bash",
            "-lc",
            "systemctl restart tinyassets-daemon.service",
        ]
    )

    evidence = fence._execute(args, host)

    assert host.command == [
        "timeout",
        "--kill-after=2s",
        "120s",
        "/bin/bash",
        "-lc",
        "systemctl restart tinyassets-daemon.service",
    ]
    assert host.timeout_seconds == 125
    assert evidence["mutation_completed"] is True


def test_guard_command_can_check_without_running_a_mutation(tmp_path: Path):
    class GuardOnlyHost:
        def unit_present(self, _unit: str) -> bool:
            return False

        def volume_container_names(self) -> list[str]:
            return []

        def run(self, _args: Any, **_kwargs: Any) -> str:
            pytest.fail("guard-only command must not invoke a mutation")

    args = fence._parser().parse_args(
        [
            "--state-path",
            str(tmp_path / "missing-state.json"),
            "guard-host-mutation",
        ]
    )

    evidence = fence._execute(args, GuardOnlyHost())

    assert evidence["mutation_completed"] is False


def test_guard_command_rejects_empty_mutation_after_separator(tmp_path: Path):
    args = fence._parser().parse_args(
        [
            "--state-path",
            str(tmp_path / "missing-state.json"),
            "guard-host-mutation",
            "--",
        ]
    )

    with pytest.raises(FenceError, match="guarded host mutation command is invalid"):
        fence._execute(args, object())


@pytest.mark.parametrize(
    ("unit", "enabled"),
    (
        (DAEMON_SERVICE, "masked"),
        ("daemon-watchdog.timer", "disabled"),
    ),
)
def test_guarded_mutation_rejects_missing_state_with_unit_residue(
    tmp_path: Path,
    unit: str,
    enabled: str,
):
    host = LifecycleHost(tmp_path)
    host.units[unit]["enabled"] = enabled

    with pytest.raises(FenceError, match="stop-writer fence residue"):
        fence.guard_host_mutation(
            host,
            state_path=tmp_path / "missing-state.json",
        )


def test_guarded_mutation_rejects_missing_state_with_restart_no_residue(
    tmp_path: Path,
):
    host = LifecycleHost(tmp_path)
    next(iter(host.containers.values()))["HostConfig"]["RestartPolicy"][
        "Name"
    ] = "no"

    with pytest.raises(FenceError, match="restart=no"):
        fence.guard_host_mutation(
            host,
            state_path=tmp_path / "missing-state.json",
        )


def test_guarded_mutation_rejects_nonterminal_canonical_state(tmp_path: Path):
    state_path = tmp_path / "fence-state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "owner": "retire-cheat-loop task 2.1",
                "run_id": RUN_ID,
                "phase": "fencing_planned",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(FenceError, match="fencing_planned"):
        fence.guard_host_mutation(
            LifecycleHost(tmp_path),
            state_path=state_path,
        )


def test_preflight_fails_if_checked_stop_leaves_active_racer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    host = LifecycleHost(tmp_path)
    host.stubborn_unit = "tinyassets-autoheal.service"
    host.units[host.stubborn_unit]["active"] = "active"
    configured_ref = [host.old_image_ref]
    _patch_lifecycle_runtime(monkeypatch, configured_ref)

    with pytest.raises(FenceError, match="restart racer remains active"):
        preflight(
            host,
            image_ref=host.target_image_ref,
            target_revision=host.target_revision,
            run_id=RUN_ID,
            state_path=tmp_path / "fence-state.json",
        )


def test_preflight_records_and_fences_stopped_extra_volume_consumer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    host = LifecycleHost(tmp_path)
    extra = host._containers("extra", "sha256:old", running=False)[
        "tinyassets-daemon"
    ]
    extra["Id"] = "extra-volume-writer"
    extra["HostConfig"]["RestartPolicy"]["Name"] = "always"
    host.containers["forgotten-writer"] = extra
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "fence-state.json"

    with pytest.raises(FenceError, match="consumer was fenced"):
        preflight(
            host,
            image_ref=host.target_image_ref,
            target_revision=host.target_revision,
            run_id=RUN_ID,
            state_path=state_path,
        )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["phase"] == "unsafe_fenced"
    assert state["extra_volume_consumers"]["forgotten-writer"] == {
        "id": "extra-volume-writer",
        "restart_policy": "always",
        "running": False,
    }
    assert (
        host.containers["forgotten-writer"]["HostConfig"]["RestartPolicy"]["Name"]
        == "no"
    )


def test_preflight_wal_is_canonical_before_first_host_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    real_atomic_json = fence._atomic_json
    publications: list[str] = []

    def assert_durable_before_publish(path: Path, payload: dict[str, Any]) -> None:
        first_publication = not publications
        publications.append(str(payload["phase"]))
        if first_publication:
            assert payload["phase"] == "fencing_planned"
            assert all(
                info["HostConfig"]["RestartPolicy"]["Name"] == "always"
                for info in host.containers.values()
            )
            assert host.units[DAEMON_SERVICE]["enabled"] == "enabled"
        real_atomic_json(path, payload)

    monkeypatch.setattr(fence, "_atomic_json", assert_durable_before_publish)
    preflight(
        host,
        image_ref=host.target_image_ref,
        target_revision=host.target_revision,
        run_id=RUN_ID,
        state_path=tmp_path / "fence-state.json",
    )

    assert publications[:3] == [
        "fencing_planned",
        "fencing_planned",
        "fencing",
    ]


def test_preflight_refuses_unproved_restart_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    host = LifecycleHost(tmp_path)
    host.restart_policy_override = "always"
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "fence-state.json"

    with pytest.raises(FenceError, match="restart fence did not persist"):
        preflight(
            host,
            image_ref=host.target_image_ref,
            target_revision=host.target_revision,
            run_id=RUN_ID,
            state_path=state_path,
        )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["run_id"] == RUN_ID
    assert state["phase"] == "fencing_planned"
    assert state["fence_progress"] == {
        "boot_activators_disabled": False,
        "restart_policy_proved": False,
    }


@pytest.mark.parametrize("failure", ["noop", "error"])
def test_restore_rejects_unmask_noop_or_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
):
    host = LifecycleHost(tmp_path)
    host.unmask_noop = failure == "noop"
    host.unmask_error = failure == "error"
    monkeypatch.setattr(fence.time, "sleep", lambda _seconds: None)
    state_path = tmp_path / "fence-state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "owner": "retire-cheat-loop task 2.1",
                "run_id": RUN_ID,
                "phase": "safe_fleet",
                "old_container_ids": {},
                "restart_racer_state": {
                    unit: host.unit_state(unit) for unit in RESTART_RACER_UNITS
                },
                "daemon_service_state": host.unit_state(DAEMON_SERVICE),
            }
        ),
        encoding="utf-8",
    )
    for unit in (*RESTART_RACER_UNITS, DAEMON_SERVICE):
        host.units[unit]["enabled"] = "masked-runtime"
    monkeypatch.setattr(
        fence,
        "prove",
        lambda *_args, **_kwargs: {"safe": True, "phase": "safe_fleet"},
    )

    with pytest.raises(FenceError, match="unit restoration proof failed|unmask failed"):
        restore_if_safe(
            host,
            image_ref=host.target_image_ref,
            revision=host.target_revision,
            run_id=RUN_ID,
            state_path=state_path,
        )
    assert json.loads(state_path.read_text(encoding="utf-8"))["phase"] == (
        "safe_fleet"
    )


@pytest.mark.parametrize("failure", ["command", "malformed"])
def test_old_container_state_errors_fail_closed(
    tmp_path: Path,
    failure: str,
):
    host = LifecycleHost(tmp_path)
    if failure == "command":
        host.container_state_error = True
    else:
        host.container_state_override = "not-an-exact-container-state"
    with pytest.raises(FenceError, match="docker ps failed|not authoritative"):
        fence._container_running_exact(host, "old-0")


def test_prove_rejects_image_identity_not_recorded_in_fence_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    host = LifecycleHost(tmp_path)
    state_path = tmp_path / "fence-state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "owner": "retire-cheat-loop task 2.1",
                "run_id": RUN_ID,
                "phase": "target_installed",
                "target_image_ref": host.target_image_ref,
                "target_revision": host.target_revision,
                "previous_image_ref": host.old_image_ref,
                "previous_revision": host.old_revision,
                "old_container_ids": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        fence,
        "observe_fleet",
        lambda *_args, **_kwargs: pytest.fail("identity must fail before observation"),
    )
    arbitrary_image = "ghcr.io/jonnyton/tinyassets-daemon@sha256:" + "c" * 64
    with pytest.raises(FenceError, match="not admitted by durable fence state"):
        prove(
            host,
            image_ref=arbitrary_image,
            revision="c" * 40,
            run_id=RUN_ID,
            state_path=state_path,
        )


def test_unsafe_cleanup_stops_all_writers_and_proves_old_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "fence-state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "owner": "retire-cheat-loop task 2.1",
                "phase": "quiesced",
                "receipt_host_path": str(tmp_path / "wiki_trigger_attempts.db"),
                "old_container_ids": {
                    name: f"pre-cutover-{index}"
                    for index, name in enumerate(EXPECTED_CONTAINERS)
                },
                "old_restart_policies": {
                    name: "always" for name in EXPECTED_CONTAINERS
                },
            }
        ),
        encoding="utf-8",
    )

    evidence = quiesce_unsafe(host, run_id=RUN_ID, state_path=state_path)

    assert evidence["phase"] == "unsafe_fenced"
    assert evidence["old_container_ids_running"] == []
    assert not any(
        info["State"]["Running"] for info in host.containers.values()
    )
    assert host.unit_state(DAEMON_SERVICE)["enabled"] == "masked-runtime"


def test_unsafe_cleanup_fences_newly_attached_volume_consumer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    host = LifecycleHost(tmp_path)
    extra = host._containers("late", "sha256:old", running=True)[
        "tinyassets-daemon"
    ]
    extra["Id"] = "late-volume-writer"
    host.containers["late-volume-writer"] = extra
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "fence-state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "owner": "retire-cheat-loop task 2.1",
                "phase": "quiesced",
                "old_container_ids": {},
            }
        ),
        encoding="utf-8",
    )

    evidence = quiesce_unsafe(host, run_id=RUN_ID, state_path=state_path)

    assert evidence["writers_fenced"] is True
    assert host.containers["late-volume-writer"]["State"]["Running"] is False
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert "late-volume-writer" in state["extra_volume_consumers"]


def test_unsafe_cleanup_still_fences_when_durable_state_is_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "fence-state.json"
    state_path.write_text("{", encoding="utf-8")

    evidence = quiesce_unsafe(host, run_id=RUN_ID, state_path=state_path)

    assert evidence["writers_fenced"] is True
    assert evidence["source_state_error"]
    assert not any(
        info["State"]["Running"] for info in host.containers.values()
    )
    assert Path(evidence["durable_state_path"]) == state_path
    canonical = json.loads(state_path.read_text(encoding="utf-8"))
    assert canonical["phase"] == "unsafe_fenced"
    archived = Path(evidence["archived_corrupt_state"])
    assert archived.is_file()
    assert archived.read_text(encoding="utf-8") == "{"


def test_corrupt_state_replacement_failure_keeps_canonical_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "fence-state.json"
    state_path.write_text("{", encoding="utf-8")
    monkeypatch.setattr(
        fence,
        "_atomic_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("injected atomic replacement failure")
        ),
    )

    with pytest.raises(OSError, match="injected atomic replacement failure"):
        quiesce_unsafe(host, run_id=RUN_ID, state_path=state_path)

    assert state_path.read_text(encoding="utf-8") == "{"
    archives = list(tmp_path.glob("fence-state.json.corrupt-*"))
    assert len(archives) == 1
    assert archives[0].read_text(encoding="utf-8") == "{"
    assert all(
        info["HostConfig"]["RestartPolicy"]["Name"] == "always"
        for info in host.containers.values()
    )
    assert host.units[DAEMON_SERVICE]["enabled"] == "enabled"


def test_missing_state_wal_failure_precedes_every_emergency_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "missing-state.json"
    monkeypatch.setattr(
        fence,
        "_atomic_json",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("injected emergency WAL failure")
        ),
    )

    with pytest.raises(OSError, match="injected emergency WAL failure"):
        quiesce_unsafe(host, run_id=RUN_ID, state_path=state_path)

    assert not state_path.exists()
    assert all(
        info["HostConfig"]["RestartPolicy"]["Name"] == "always"
        for info in host.containers.values()
    )
    assert host.units[DAEMON_SERVICE]["enabled"] == "enabled"
    mutation_calls = [
        call
        for call in host.calls
        if call[:2]
        in {
            ("docker", "update"),
            ("docker", "stop"),
            ("systemctl", "disable"),
            ("systemctl", "stop"),
            ("systemctl", "mask"),
        }
    ]
    assert mutation_calls == []


def test_unsafe_cleanup_without_receipt_resolution_never_claims_fenced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    host = LifecycleHost(tmp_path)
    del host.containers["tinyassets-worker"]
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "missing-state.json"

    with pytest.raises(FenceError, match="could not prove"):
        quiesce_unsafe(host, run_id=RUN_ID, state_path=state_path)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["phase"] == "unsafe_fence_unproved"
    assert state["receipt_resolution_error"]
    assert not any(
        info["State"]["Running"] for info in host.containers.values()
    )


def test_process_scan_permission_error_is_uncertainty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    proc_root = tmp_path / "proc"
    proc = proc_root / "123"
    (proc / "fd").mkdir(parents=True)
    (proc / "cmdline").write_bytes(b"python\0worker")
    (proc / "environ").write_bytes(b"")
    (proc / "mountinfo").write_text("", encoding="utf-8")
    monkeypatch.setattr(fence.os, "getpid", lambda: 999)
    monkeypatch.setattr(fence.os, "readlink", lambda _path: "/usr/bin/python")
    original_read_bytes = Path.read_bytes

    def deny_environ(path: Path) -> bytes:
        if path.name == "environ":
            raise PermissionError("denied")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", deny_environ)
    monkeypatch.setattr(
        fence.Path,
        "glob",
        lambda _self, _pattern: [proc],
    )

    with pytest.raises(FenceError, match="process scan permission denied"):
        fence._stray_writer_processes(
            tmp_path / "receipt.db",
            set(),
            tmp_path,
        )


@pytest.mark.parametrize(
    ("process_namespace", "expected_risk"),
    (("mnt:[1]", False), ("mnt:[2]", True)),
)
def test_mountinfo_only_flags_foreign_not_same_host_namespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    process_namespace: str,
    expected_risk: bool,
):
    proc = tmp_path / "proc" / "123"
    (proc / "fd").mkdir(parents=True)
    (proc / "ns").mkdir()
    (proc / "cmdline").write_bytes(b"python\0idle")
    (proc / "environ").write_bytes(b"")
    (proc / "mountinfo").write_text(str(tmp_path), encoding="utf-8")
    monkeypatch.setattr(fence.os, "getpid", lambda: 999)

    def readlink(path: Any) -> str:
        value = str(path)
        if value.endswith("/exe") or value.endswith("\\exe"):
            return "/usr/bin/python"
        if value == "/proc/self/ns/mnt":
            return "mnt:[1]"
        return process_namespace

    monkeypatch.setattr(fence.os, "readlink", readlink)
    monkeypatch.setattr(fence.Path, "glob", lambda _self, _pattern: [proc])

    risks = fence._stray_writer_processes(tmp_path / "receipt.db", set(), tmp_path)
    assert bool(risks) is expected_risk
    if risks:
        assert risks[0]["same_host_mount_namespace"] is False
        assert risks[0]["mount_namespace"] == "mnt:[2]"


def test_post_canary_failure_includes_final_observation_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "owner": "retire-cheat-loop task 2.1",
                "run_id": RUN_ID,
                "phase": "safe_fleet",
                "last_failed_observation": {
                    "volume_container_names": ["tinyassets-daemon"]
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        fence,
        "prove",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FenceError("exact-five transient")
        ),
    )
    monkeypatch.setattr(fence.time, "sleep", lambda _seconds: None)
    with pytest.raises(FenceError, match="volume_container_names"):
        post_canary(
            object(),
            image_ref="ghcr.io/jonnyton/tinyassets-daemon@sha256:" + "b" * 64,
            revision="b" * 40,
            run_id=RUN_ID,
            state_path=state_path,
        )


def test_writer_command_classifier_covers_idle_cloud_worker():
    assert fence._looks_like_writer_command(
        "python -m tinyassets.cloud_worker --poll-seconds 5"
    )


def _unsafe_recovery_state(host: LifecycleHost, state_path: Path) -> None:
    _create_receipt_db(host.volume / "wiki_trigger_attempts.db")
    snapshot = receipt_snapshot(host.volume / "wiki_trigger_attempts.db")
    for info in host.containers.values():
        info["State"] = {"Running": False, "Pid": 0}
        info["HostConfig"]["RestartPolicy"]["Name"] = "no"
    for unit in (*RESTART_RACER_UNITS, DAEMON_SERVICE):
        host.units[unit]["enabled"] = "masked-runtime"
        host.units[unit]["active"] = "inactive"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "owner": "retire-cheat-loop task 2.1",
                "run_id": "source-run-1",
                "source_run_id": "source-run-1",
                "phase": "unsafe_fenced",
                "target_image_ref": host.target_image_ref,
                "target_revision": host.target_revision,
                "previous_image_ref": host.old_image_ref,
                "previous_revision": host.old_revision,
                "volume_mountpoint": str(host.volume),
                "receipt_container_path": "/data/wiki_trigger_attempts.db",
                "receipt_host_path": str(host.volume / "wiki_trigger_attempts.db"),
                "receipt_snapshot": snapshot,
                "preliminary_receipt_snapshot": snapshot,
                "old_container_ids": {
                    name: f"pre-cutover-{index}"
                    for index, name in enumerate(EXPECTED_CONTAINERS)
                },
                "old_restart_policies": {
                    name: "always" for name in EXPECTED_CONTAINERS
                },
                "restart_racer_state": {
                    unit: {
                        "active": "active" if unit.endswith(".timer") else "inactive",
                        "enabled": "enabled" if unit.endswith(".timer") else "static",
                    }
                    for unit in RESTART_RACER_UNITS
                },
                "daemon_service_state": {"active": "active", "enabled": "enabled"},
                "present_restart_racer_units": list(RESTART_RACER_UNITS),
                "extra_volume_consumers": {},
            }
        ),
        encoding="utf-8",
    )


def test_recover_unsafe_refuses_wrong_source_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)

    with pytest.raises(FenceError, match="source run"):
        recover_unsafe(
            host,
            source_run_id="wrong-run",
            run_id="recovery-1",
            image_ref=host.old_image_ref,
            revision=host.old_revision,
            state_path=state_path,
        )
    assert not any(call[:2] == ("systemctl", "unmask") for call in host.calls)


def test_recover_unsafe_starts_restart_fenced_then_finalizes_exact_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    configured = [host.old_image_ref]
    _patch_lifecycle_runtime(monkeypatch, configured)
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.start_installs_target = True

    evidence = recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id="recovery-1",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )

    assert evidence["phase"] == "recovery_pending_canary"
    assert evidence["source_run_id"] == "source-run-1"
    assert ("systemctl", "start", DAEMON_SERVICE) not in host.calls
    compose = next(call for call in host.calls if call[:2] == ("docker", "compose"))
    assert str(fence.RECOVERY_COMPOSE_OVERRIDE_PATH) in compose
    assert all(
        info["HostConfig"]["RestartPolicy"]["Name"] == "no"
        for info in host.containers.values()
    )
    assert all(
        host.units[unit]["enabled"] == "masked-runtime"
        and host.units[unit]["active"] == "inactive"
        for unit in (*RESTART_RACER_UNITS, DAEMON_SERVICE)
    )
    assert all(
        info["Id"].startswith("recovered-") for info in host.containers.values()
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["source_run_id"] == "source-run-1"
    assert state["recovery_attempts"] == ["recovery-1"]
    assert state["phase"] == "recovery_pending_canary"

    finalized = finalize_recovery(
        host,
        source_run_id="source-run-1",
        run_id="recovery-1",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )

    assert finalized["phase"] == "restored"
    assert ("systemctl", "start", DAEMON_SERVICE) in host.calls
    assert all(
        info["HostConfig"]["RestartPolicy"]["Name"] == "always"
        for info in host.containers.values()
    )


def test_recover_unsafe_accepts_compose_down_zero_container_fence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.containers = {}
    host.start_installs_target = True

    evidence = recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id="recovery-zero",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )

    assert evidence["phase"] == "recovery_pending_canary"
    assert set(host.containers) == set(EXPECTED_CONTAINERS)
    assert all(
        info["HostConfig"]["RestartPolicy"]["Name"] == "no"
        for info in host.containers.values()
    )


def test_recovery_arms_expiry_before_starting_any_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.containers = {}
    host.start_installs_target = True

    recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id="recovery-timer-order",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )

    timer_index = next(
        index
        for index, call in enumerate(host.calls)
        if call[:1] == ("systemd-run",)
    )
    compose_index = next(
        index
        for index, call in enumerate(host.calls)
        if call[:2] == ("docker", "compose")
    )
    assert timer_index < compose_index
    timer_call = host.calls[timer_index]
    assert str(fence.RECOVERY_SCRIPT_PATH) in timer_call


def test_recovery_entrypoint_proof_binds_timer_to_running_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    installed = tmp_path / "retire-cheat-loop-deploy-fence.py"
    installed.write_bytes(Path(fence.__file__).read_bytes())
    installed.chmod(0o755)
    monkeypatch.setattr(fence, "RECOVERY_SCRIPT_PATH", installed)
    monkeypatch.setattr(fence, "__file__", str(installed))

    digest = hashlib.sha256(installed.read_bytes()).hexdigest()
    assert fence._prove_recovery_entrypoint(digest) == digest


def test_recovery_entrypoint_proof_rejects_different_timer_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    running = tmp_path / "running.py"
    timer = tmp_path / "timer.py"
    running.write_text("print('running')\n", encoding="utf-8")
    timer.write_text("print('timer')\n", encoding="utf-8")
    timer.chmod(0o755)
    monkeypatch.setattr(fence, "RECOVERY_SCRIPT_PATH", timer)
    monkeypatch.setattr(fence, "__file__", str(running))

    with pytest.raises(
        FenceError,
        match="does not match the running script",
    ):
        fence._prove_recovery_entrypoint("a" * 64)


def test_finalize_refences_when_restart_policies_drift_after_canary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.start_installs_target = True
    recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id="recovery-policy-drift",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )
    for info in host.containers.values():
        info["HostConfig"]["RestartPolicy"]["Name"] = "always"

    with pytest.raises(FenceError, match="re-fenced"):
        finalize_recovery(
            host,
            source_run_id="source-run-1",
            run_id="recovery-policy-drift",
            image_ref=host.old_image_ref,
            revision=host.old_revision,
            state_path=state_path,
        )

    assert json.loads(state_path.read_text(encoding="utf-8"))["phase"] == (
        "unsafe_fenced"
    )


def test_finalize_refences_when_boot_fence_drifts_after_canary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.start_installs_target = True
    recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id="recovery-unit-drift",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )
    host.units[DAEMON_SERVICE].update(active="active", enabled="enabled")

    with pytest.raises(FenceError, match="re-fenced"):
        finalize_recovery(
            host,
            source_run_id="source-run-1",
            run_id="recovery-unit-drift",
            image_ref=host.old_image_ref,
            revision=host.old_revision,
            state_path=state_path,
        )

    assert json.loads(state_path.read_text(encoding="utf-8"))["phase"] == (
        "unsafe_fenced"
    )


def test_finalize_refences_when_expiry_timer_disappears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.start_installs_target = True
    recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id="recovery-timer-drift",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    host.units[f"{state['recovery_expiry_unit']}.timer"]["active"] = "inactive"

    with pytest.raises(FenceError, match="re-fenced"):
        finalize_recovery(
            host,
            source_run_id="source-run-1",
            run_id="recovery-timer-drift",
            image_ref=host.old_image_ref,
            revision=host.old_revision,
            state_path=state_path,
        )

    assert json.loads(state_path.read_text(encoding="utf-8"))["phase"] == (
        "unsafe_fenced"
    )


def test_refence_rejects_replaced_container_generation_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.start_installs_target = True
    recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id="recovery-owned-generation",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )
    for index, info in enumerate(host.containers.values()):
        info["Id"] = f"replacement-{index}"
    calls_before = len(host.calls)

    with pytest.raises(FenceError, match="identities changed"):
        refence_recovery(
            host,
            source_run_id="source-run-1",
            run_id="recovery-owned-generation",
            state_path=state_path,
        )

    assert len(host.calls) == calls_before
    assert all(info["State"]["Running"] for info in host.containers.values())


def test_recovery_failure_rejects_foreign_labels_without_cleanup_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.start_installs_target = True
    original_run = host.run

    def install_foreign_generation(
        command: list[str] | tuple[str, ...],
        **kwargs: Any,
    ) -> str:
        result = original_run(command, **kwargs)
        if tuple(command)[:2] == ("docker", "compose"):
            for info in host.containers.values():
                info["Config"]["Labels"][
                    "com.docker.compose.project"
                ] = "another-generation"
        return result

    monkeypatch.setattr(host, "run", install_foreign_generation)

    with pytest.raises(FenceError, match="re-fence also failed"):
        recover_unsafe(
            host,
            source_run_id="source-run-1",
            run_id="recovery-foreign-label",
            image_ref=host.old_image_ref,
            revision=host.old_revision,
            state_path=state_path,
        )

    compose_index = next(
        index
        for index, call in enumerate(host.calls)
        if call[:2] == ("docker", "compose")
    )
    assert not any(
        call[:2] in {("docker", "update"), ("docker", "stop")}
        for call in host.calls[compose_index + 1 :]
    )


def test_finalize_refences_new_writer_activator_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    missing = "tinyassets-autoheal.timer"
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.units.pop(missing)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["present_restart_racer_units"].remove(missing)
    state["restart_racer_state"].pop(missing)
    state_path.write_text(json.dumps(state), encoding="utf-8")
    host.start_installs_target = True
    recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id="recovery-new-activator",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )
    host.units[missing] = {
        "active": "active",
        "enabled": "enabled",
        "load": "loaded",
    }

    with pytest.raises(FenceError, match="re-fenced"):
        finalize_recovery(
            host,
            source_run_id="source-run-1",
            run_id="recovery-new-activator",
            image_ref=host.old_image_ref,
            revision=host.old_revision,
            state_path=state_path,
        )

    assert json.loads(state_path.read_text(encoding="utf-8"))["phase"] == (
        "unsafe_fenced"
    )


def test_boot_reconciler_refences_interrupted_recovery_after_timer_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.start_installs_target = True
    recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id="recovery-reboot",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    host.units.pop(f"{state['recovery_expiry_unit']}.timer")
    host.units.pop(f"{state['recovery_expiry_unit']}.service")
    for info in host.containers.values():
        info["State"].update(Running=False, Pid=0)
    for unit in (*RESTART_RACER_UNITS, DAEMON_SERVICE):
        host.units[unit].update(
            active="inactive",
            enabled="disabled",
            load="loaded",
        )

    evidence = fence.reconcile_recovery_on_boot(
        host,
        state_path=state_path,
    )

    assert evidence["phase"] == "unsafe_fenced"
    assert json.loads(state_path.read_text(encoding="utf-8"))["phase"] == (
        "unsafe_fenced"
    )


def test_cli_recovery_persists_installed_script_digest_before_compose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.start_installs_target = True
    digest = "c" * 64
    monkeypatch.setattr(
        fence,
        "_prove_recovery_entrypoint",
        lambda expected: digest if expected == digest else "",
    )
    original_run = host.run

    def run_with_digest_check(
        command: list[str] | tuple[str, ...],
        **kwargs: Any,
    ) -> str:
        if tuple(command)[:2] == ("docker", "compose"):
            pre_compose = json.loads(state_path.read_text(encoding="utf-8"))
            assert pre_compose["recovery_script_sha256"] == digest
            assert pre_compose["phase"] == "recovery_starting"
        return original_run(command, **kwargs)

    monkeypatch.setattr(host, "run", run_with_digest_check)
    args = fence._parser().parse_args(
        [
            "--state-path",
            str(state_path),
            "recover-unsafe",
            "--source-run-id",
            "source-run-1",
            "--run-id",
            "recovery-cli",
            "--image-ref",
            host.old_image_ref,
            "--revision",
            host.old_revision,
            "--expected-script-sha256",
            digest,
        ]
    )

    fence._execute(args, host)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["recovery_script_sha256"] == digest
    compose_index = next(
        index
        for index, call in enumerate(host.calls)
        if call[:2] == ("docker", "compose")
    )
    assert state["phase"] == "recovery_pending_canary"
    assert compose_index > 0


def test_expired_recovery_refences_orphaned_runner_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.containers = {}
    host.start_installs_target = True
    recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id="recovery-expired",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["recovery_deadline_epoch"] = 0
    state_path.write_text(json.dumps(state), encoding="utf-8")

    evidence = expire_recovery(
        host,
        source_run_id="source-run-1",
        run_id="recovery-expired",
        state_path=state_path,
    )

    assert evidence["expired"] is True
    assert json.loads(state_path.read_text(encoding="utf-8"))["phase"] == "unsafe_fenced"
    assert not any(info["State"]["Running"] for info in host.containers.values())


def test_unexpired_recovery_lease_cannot_be_stolen_or_expired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.containers = {}
    host.start_installs_target = True
    recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id="recovery-live",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )

    with pytest.raises(FenceError, match="has not expired"):
        expire_recovery(
            host,
            source_run_id="source-run-1",
            run_id="recovery-live",
            state_path=state_path,
        )
    with pytest.raises(FenceError, match="active lease"):
        recover_unsafe(
            host,
            source_run_id="source-run-1",
            run_id="recovery-steal",
            image_ref=host.old_image_ref,
            revision=host.old_revision,
            state_path=state_path,
        )
    assert all(info["State"]["Running"] for info in host.containers.values())


def test_expired_pending_recovery_is_reconciled_before_new_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.containers = {}
    host.start_installs_target = True
    recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id="recovery-old",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["recovery_deadline_epoch"] = 0
    state_path.write_text(json.dumps(state), encoding="utf-8")

    evidence = recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id="recovery-new",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )

    assert evidence["phase"] == "recovery_pending_canary"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["recovery_attempts"] == ["recovery-old", "recovery-new"]
    assert state["recovery_run_id"] == "recovery-new"


@pytest.mark.parametrize(
    "phase",
    [
        "recovery_planned",
        "recovery_starting",
        "recovery_pending_canary",
        "safe_fleet",
    ],
)
def test_expired_intermediate_recovery_phase_replays_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(
        {
            "phase": phase,
            "run_id": "interrupted-run",
            "recovery_run_id": "interrupted-run",
            "recovery_attempts": ["interrupted-run"],
            "recovery_deadline_epoch": 0,
        }
    )
    state_path.write_text(json.dumps(state), encoding="utf-8")
    host.containers = {}
    host.start_installs_target = True

    evidence = recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id=f"replay-{phase}",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )

    assert evidence["phase"] == "recovery_pending_canary"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["recovery_attempts"] == [
        "interrupted-run",
        f"replay-{phase}",
    ]
    assert all(
        info["HostConfig"]["RestartPolicy"]["Name"] == "no"
        for info in host.containers.values()
    )


def test_finalize_recovery_refences_silent_restart_policy_misapplication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.containers = {}
    host.start_installs_target = True
    recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id="recovery-policy",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )
    host.restart_policy_override = "no"

    with pytest.raises(FenceError, match="re-fenced"):
        finalize_recovery(
            host,
            source_run_id="source-run-1",
            run_id="recovery-policy",
            image_ref=host.old_image_ref,
            revision=host.old_revision,
            state_path=state_path,
        )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["phase"] == "unsafe_fenced"
    assert not any(info["State"]["Running"] for info in host.containers.values())


@pytest.mark.parametrize("phase", ["canary_accepted", "finalizing"])
def test_expiry_refences_interrupted_finalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.containers = {}
    host.start_installs_target = True
    recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id="recovery-finalize-loss",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["phase"] = phase
    state["recovery_deadline_epoch"] = 0
    state_path.write_text(json.dumps(state), encoding="utf-8")

    evidence = expire_recovery(
        host,
        source_run_id="source-run-1",
        run_id="recovery-finalize-loss",
        state_path=state_path,
    )

    assert evidence["expired"] is True
    assert json.loads(state_path.read_text(encoding="utf-8"))["phase"] == "unsafe_fenced"
    assert not any(info["State"]["Running"] for info in host.containers.values())


def test_recover_unsafe_requires_exact_runner_bound_identity_before_wal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    before = state_path.read_bytes()

    with pytest.raises(FenceError, match="runner-bound|recorded"):
        recover_unsafe(
            host,
            source_run_id="source-run-1",
            run_id="recovery-wrong-image",
            image_ref=host.target_image_ref,
            revision=host.target_revision,
            state_path=state_path,
        )

    assert state_path.read_bytes() == before
    assert host.calls == []


def test_recover_unsafe_requires_complete_saved_restart_policies_before_wal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["old_restart_policies"].pop("tinyassets-worker")
    state_path.write_text(json.dumps(state), encoding="utf-8")
    before = state_path.read_bytes()

    with pytest.raises(FenceError, match="restart polic"):
        recover_unsafe(
            host,
            source_run_id="source-run-1",
            run_id="recovery-policy-gap",
            image_ref=host.old_image_ref,
            revision=host.old_revision,
            state_path=state_path,
        )
    assert state_path.read_bytes() == before
    assert host.calls == []


def test_recovery_refence_wrong_source_does_not_mutate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)

    with pytest.raises(FenceError, match="not owned"):
        refence_recovery(
            host,
            source_run_id="wrong-source",
            run_id="unrelated-run",
            state_path=state_path,
        )
    assert host.calls == []


def test_recovery_refence_canary_failure_stops_current_recovered_fleet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    host.start_installs_target = True
    recover_unsafe(
        host,
        source_run_id="source-run-1",
        run_id="recovery-canary",
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        state_path=state_path,
    )

    evidence = refence_recovery(
        host,
        source_run_id="source-run-1",
        run_id="recovery-canary",
        state_path=state_path,
    )

    assert evidence["phase"] == "unsafe_fenced"
    assert not any(info["State"]["Running"] for info in host.containers.values())


def test_restore_handles_active_timer_requiring_static_service_to_settle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    state_path = tmp_path / "state.json"
    state = {
        "schema_version": 1,
        "owner": "retire-cheat-loop task 2.1",
        "run_id": RUN_ID,
        "phase": "safe_fleet",
        "old_container_ids": {},
        "restart_racer_state": {
            unit: host.unit_state(unit) for unit in RESTART_RACER_UNITS
        },
        "daemon_service_state": host.unit_state(DAEMON_SERVICE),
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    for unit in (*RESTART_RACER_UNITS, DAEMON_SERVICE):
        host.units[unit]["enabled"] = "masked-runtime"
        host.units[unit]["load"] = "masked"
    original_run = host.run
    original_state = host.unit_state
    service_reads = {"count": 0}

    def timer_requires_service(args: Any, **kwargs: Any) -> str:
        result = original_run(args, **kwargs)
        if tuple(args) == ("systemctl", "start", "daemon-watchdog.timer"):
            host.units["daemon-watchdog.service"]["active"] = "activating"
        return result

    def settling_state(unit: str) -> dict[str, str]:
        value = original_state(unit)
        if (
            unit == "daemon-watchdog.service"
            and value["active"] == "activating"
        ):
            service_reads["count"] += 1
            if service_reads["count"] >= 2:
                host.units[unit]["active"] = "inactive"
                value["active"] = "inactive"
        return value

    monkeypatch.setattr(host, "run", timer_requires_service)
    monkeypatch.setattr(host, "unit_state", settling_state)
    monkeypatch.setattr(fence.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        fence,
        "prove",
        lambda *_args, **_kwargs: {"safe": True, "phase": "safe_fleet"},
    )

    evidence = restore_if_safe(
        host,
        image_ref=host.old_image_ref,
        revision=host.old_revision,
        run_id=RUN_ID,
        state_path=state_path,
    )

    assert evidence["phase"] == "restored"
    assert service_reads["count"] >= 2


def test_recover_unsafe_refences_after_mutation_os_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    original_run = host.run

    def fail_start(args: Any, **kwargs: Any) -> str:
        if tuple(args)[:2] == ("docker", "compose"):
            raise OSError("injected start I/O failure")
        return original_run(args, **kwargs)

    monkeypatch.setattr(host, "run", fail_start)
    with pytest.raises(FenceError, match="re-fenced"):
        recover_unsafe(
            host,
            source_run_id="source-run-1",
            run_id="recovery-1",
            image_ref=host.old_image_ref,
            revision=host.old_revision,
            state_path=state_path,
        )
    assert json.loads(state_path.read_text(encoding="utf-8"))["phase"] == "unsafe_fenced"


@pytest.mark.parametrize("fault", ["extra", "queue", "receipt"])
def test_recover_unsafe_refuses_unproved_fenced_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
):
    host = LifecycleHost(tmp_path)
    _patch_lifecycle_runtime(monkeypatch, [host.old_image_ref])
    state_path = tmp_path / "state.json"
    _unsafe_recovery_state(host, state_path)
    if fault == "extra":
        host.containers["extra"] = host._containers("extra", "sha256:old", running=False)[
            "tinyassets-daemon"
        ]
    elif fault == "queue":
        (tmp_path / "branch_tasks.json").write_text(
            json.dumps(
                [
                    {
                        "branch_task_id": "x",
                        "request_type": "bug_investigation",
                        "status": "pending",
                    }
                ]
            ),
            encoding="utf-8",
        )
    else:
        with sqlite3.connect(tmp_path / "wiki_trigger_attempts.db") as connection:
            connection.execute(
                "INSERT INTO wiki_trigger_attempts "
                "(trigger_attempt_id,request_id,request_kind,request_page,status,attempted_at) "
                "VALUES ('x','x','bug','x','queued','now')"
            )

    with pytest.raises(FenceError):
        recover_unsafe(
            host,
            source_run_id="source-run-1",
            run_id="recovery-1",
            image_ref=host.old_image_ref,
            revision=host.old_revision,
            state_path=state_path,
        )
    assert json.loads(state_path.read_text(encoding="utf-8"))["phase"] == "unsafe_fenced"


def test_restore_waits_for_activating_unit_then_exact_inactive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    states = iter(["activating", "inactive"])
    host.units["daemon-watchdog.service"]["active"] = "activating"
    original = host.unit_state

    def settling(unit: str) -> dict[str, str]:
        value = original(unit)
        if unit == "daemon-watchdog.service":
            value["active"] = next(states, "inactive")
        return value

    monkeypatch.setattr(host, "unit_state", settling)
    monkeypatch.setattr(fence.time, "sleep", lambda _seconds: None)
    actual = fence._wait_units_restored(
        host,
        {"daemon-watchdog.service": {"active": "inactive", "enabled": "static"}},
        timeout_seconds=91,
        delay_seconds=1,
    )
    assert actual["daemon-watchdog.service"]["active"] == "inactive"


def test_restore_timeout_reports_last_transient_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    host = LifecycleHost(tmp_path)
    host.units["daemon-watchdog.service"]["active"] = "activating"
    monkeypatch.setattr(fence.time, "sleep", lambda _seconds: None)
    with pytest.raises(FenceError, match="activating"):
        fence._wait_units_restored(
            host,
            {"daemon-watchdog.service": {"active": "inactive", "enabled": "static"}},
            timeout_seconds=91,
            delay_seconds=100,
        )


def test_parent_directory_fsync_is_attempted_on_posix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[tuple[str, int | Path]] = []
    monkeypatch.setattr(fence.os, "name", "posix")
    monkeypatch.setattr(
        fence.os,
        "open",
        lambda path, _flags: calls.append(("open", path)) or 91,
    )
    monkeypatch.setattr(
        fence.os,
        "fsync",
        lambda descriptor: calls.append(("fsync", descriptor)),
    )
    monkeypatch.setattr(
        fence.os,
        "close",
        lambda descriptor: calls.append(("close", descriptor)),
    )

    fence._fsync_parent(tmp_path / "state.json")

    assert calls == [
        ("open", tmp_path),
        ("fsync", 91),
        ("close", 91),
    ]
