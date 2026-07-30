#!/usr/bin/env python3
"""Transitional production writer fence for retire-cheat-loop task 2.1.

This helper exists only for the filing-only cutover. Task 2.5 owns the locked
receipt/queue migration and removal of this product-specific deployment guard.
It never mutates receipt or queue data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote

try:
    import fcntl
except ImportError:  # pragma: no cover - production helper runs on Linux.
    fcntl = None

EXPECTED_CONTAINERS = (
    "tinyassets-daemon",
    "tinyassets-worker",
    "tinyassets-worker-codex-2",
    "tinyassets-worker-claude-1",
    "tinyassets-worker-claude-2",
)
RESTART_RACER_UNITS = (
    "daemon-watchdog.timer",
    "daemon-watchdog.service",
    "tinyassets-watchdog.timer",
    "tinyassets-watchdog.service",
    "tinyassets-autoheal.timer",
    "tinyassets-autoheal.service",
)
DAEMON_SERVICE = "tinyassets-daemon.service"
VOLUME_NAME = "tinyassets-data"
DEFAULT_RECEIPT_PATH = "/data/wiki_trigger_attempts.db"
DEFAULT_STATE_PATH = Path(
    "/var/lib/tinyassets-deploy/retire-cheat-loop-task-2-1-fence.json"
)
DEFAULT_LOCK_PATH = Path("/run/lock/tinyassets-deploy-fence.lock")
HOST_COMMAND_TIMEOUT_SECONDS = 45
LOCK_TIMEOUT_SECONDS = 60
UNIT_RESTORE_TIMEOUT_SECONDS = 120
RECOVERY_LEASE_SECONDS = 600
RECOVERY_COMPOSE_PATH = Path("/opt/tinyassets/compose.yml")
RECOVERY_COMPOSE_OVERRIDE_PATH = Path(
    "/opt/tinyassets/deploy/recovery-restart-no.yml"
)
RECOVERY_SCRIPT_PATH = Path(
    "/opt/tinyassets/deploy/retire-cheat-loop-deploy-fence.py"
)
RECOVERY_RECONCILE_SERVICE = "tinyassets-recovery-reconcile.service"
TASK_OWNER = "retire-cheat-loop task 2.1"
V1_RISK_STATUSES = frozenset({"pending", "running"})
V2_RISK_STATUSES = frozenset({"pending", "running", "cancel_requested"})
CANONICAL_IMAGE_RE = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]+)?"
    r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+"
    r"@sha256:[0-9a-f]{64}$"
)
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
WRITER_PROCESS_MARKERS = (
    "tinyassets.universe_server",
    "tinyassets.daemon_server",
    "tinyassets.cloud_worker",
    "claude-plugin",
    "mcpb",
)
RECEIPT_COLUMNS = (
    "trigger_attempt_id",
    "request_id",
    "request_kind",
    "request_page",
    "status",
    "attempted_at",
    "goal_id",
    "branch_def_id",
    "queued_at",
    "run_id",
    "dispatcher_request_id",
    "error_class",
    "error_message",
)


class FenceError(RuntimeError):
    """Fail-closed deployment fence error."""


@dataclass(frozen=True)
class ReceiptStore:
    container_path: str
    host_path: Path


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _read_only_connection(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(path.resolve()))}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def receipt_snapshot(path: Path) -> dict[str, Any]:
    """Return a deterministic logical snapshot without creating the store."""

    empty_digest = hashlib.sha256(b"").hexdigest()
    if not path.is_file():
        return {
            "exists": False,
            "quick_check": ["absent"],
            "schema": [],
            "row_count": 0,
            "status_counts": {},
            "max_attempted_at": None,
            "logical_digest": empty_digest,
        }
    try:
        with _read_only_connection(path) as connection:
            quick_check = [
                str(row[0]) for row in connection.execute("PRAGMA quick_check")
            ]
            if quick_check != ["ok"]:
                raise FenceError(
                    f"receipt sqlite quick_check failed: {quick_check!r}"
                )
            table = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='wiki_trigger_attempts'"
            ).fetchone()
            if table is None:
                raise FenceError("receipt sqlite lacks exact receipt schema")
            columns = tuple(
                str(row["name"])
                for row in connection.execute(
                    "PRAGMA table_info(wiki_trigger_attempts)"
                )
            )
            if columns != RECEIPT_COLUMNS:
                raise FenceError("receipt sqlite lacks exact receipt schema")
            schema = [
                {
                    "type": str(row["type"]),
                    "name": str(row["name"]),
                    "table": str(row["tbl_name"]),
                    "sql": str(row["sql"] or ""),
                }
                for row in connection.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master "
                    "ORDER BY type,name"
                )
            ]
            quoted_columns = ",".join(f'"{column}"' for column in columns)
            rows = [
                list(row)
                for row in connection.execute(
                    f"SELECT {quoted_columns} FROM wiki_trigger_attempts "
                    "ORDER BY trigger_attempt_id"
                )
            ]
            status_counts = {
                str(row[0]): int(row[1])
                for row in connection.execute(
                    "SELECT status,COUNT(*) FROM wiki_trigger_attempts "
                    "GROUP BY status ORDER BY status"
                )
            }
            max_attempted_at = connection.execute(
                "SELECT MAX(attempted_at) FROM wiki_trigger_attempts"
            ).fetchone()[0]
    except FenceError:
        raise
    except (OSError, sqlite3.DatabaseError) as exc:
        raise FenceError(
            f"receipt sqlite unreadable: {type(exc).__name__}"
        ) from exc

    logical_rows = b"".join(_json_bytes(row) + b"\n" for row in rows)
    return {
        "exists": True,
        "quick_check": quick_check,
        "schema": schema,
        "row_count": len(rows),
        "status_counts": status_counts,
        "max_attempted_at": max_attempted_at,
        "logical_digest": hashlib.sha256(logical_rows).hexdigest(),
    }


def _v1_tasks(raw: Any) -> list[dict[str, Any]]:
    tasks = raw if isinstance(raw, list) else raw.get("tasks") if isinstance(raw, dict) else None
    if not isinstance(tasks, list) or any(not isinstance(task, dict) for task in tasks):
        raise FenceError("v1 queue unreadable: unexpected shape")
    return tasks


def inventory_queue_risk(volume_dir: Path) -> list[dict[str, str]]:
    """Inventory every executable retired v1/v2 queue row, read-only."""

    risks: list[dict[str, str]] = []
    for path in sorted(volume_dir.rglob("branch_tasks.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            tasks = _v1_tasks(raw)
        except FenceError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise FenceError(
                f"v1 queue unreadable: {path.relative_to(volume_dir)}"
            ) from exc
        for task in tasks:
            status = str(task.get("status", "")).lower()
            if (
                task.get("request_type") == "bug_investigation"
                and status in V1_RISK_STATUSES
            ):
                risks.append(
                    {
                        "id": str(task.get("branch_task_id") or ""),
                        "status": status,
                        "store": path.relative_to(volume_dir).as_posix(),
                        "version": "v1",
                    }
                )

    for path in sorted(volume_dir.rglob(".tinyassets.db")):
        try:
            with _read_only_connection(path) as connection:
                tables = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                if "branch_tasks_v2" not in tables:
                    continue
                if "user_requests" not in tables:
                    raise FenceError("v2 queue schema incomplete: user_requests")
                task_columns = {
                    str(row["name"])
                    for row in connection.execute(
                        "PRAGMA table_info(branch_tasks_v2)"
                    )
                }
                request_columns = {
                    str(row["name"])
                    for row in connection.execute(
                        "PRAGMA table_info(user_requests)"
                    )
                }
                if not {"branch_task_id", "request_id", "status"} <= task_columns:
                    raise FenceError("v2 queue schema incomplete: branch_tasks_v2")
                if not {"request_id", "request_type"} <= request_columns:
                    raise FenceError("v2 queue schema incomplete: user_requests")
                foreign_key_failures = list(
                    connection.execute("PRAGMA foreign_key_check")
                )
                if foreign_key_failures:
                    raise FenceError("v2 queue foreign key check failed")
                placeholders = ",".join("?" for _ in V2_RISK_STATUSES)
                rows = connection.execute(
                    "SELECT bt.branch_task_id,bt.status,ur.request_type "
                    "FROM branch_tasks_v2 AS bt "
                    "LEFT JOIN user_requests AS ur ON ur.request_id=bt.request_id "
                    f"WHERE bt.status IN ({placeholders}) "
                    "ORDER BY bt.branch_task_id",
                    tuple(sorted(V2_RISK_STATUSES)),
                )
                for row in rows:
                    request_type = row[2]
                    if not isinstance(request_type, str) or not request_type.strip():
                        raise FenceError(
                            "v2 live task missing authoritative request type"
                        )
                    if request_type == "bug_investigation":
                        risks.append(
                            {
                                "id": str(row[0]),
                                "status": str(row[1]),
                                "store": path.relative_to(volume_dir).as_posix(),
                                "version": "v2",
                            }
                        )
        except FenceError:
            raise
        except (OSError, sqlite3.DatabaseError) as exc:
            raise FenceError(
                f"v2 queue unreadable: {path.relative_to(volume_dir)}"
            ) from exc
    return sorted(
        risks,
        key=lambda row: (row["version"], row["store"], row["id"], row["status"]),
    )


def _env_map(info: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in info.get("Config", {}).get("Env", []) or []:
        key, separator, value = str(item).partition("=")
        if separator:
            result[key] = value
    return result


def resolve_receipt_store(
    inspections: Mapping[str, Mapping[str, Any]],
    volume_dir: Path,
) -> ReceiptStore:
    """Resolve one controlled /data store shared by the exact writer fleet."""

    resolved_volume = volume_dir.resolve()
    selected_paths: set[str] = set()
    for name in EXPECTED_CONTAINERS:
        info = inspections.get(name)
        if info is None:
            raise FenceError(f"missing expected container: {name}")
        mounts = [
            mount
            for mount in info.get("Mounts", []) or []
            if mount.get("Destination") == "/data"
        ]
        if len(mounts) != 1:
            raise FenceError(f"{name} does not have exactly one /data mount")
        mount = mounts[0]
        if (
            mount.get("Name") != VOLUME_NAME
            or Path(str(mount.get("Source", ""))).resolve() != resolved_volume
        ):
            raise FenceError(f"{name} does not share {VOLUME_NAME}")
        selected = _env_map(info).get(
            "TINYASSETS_TRIGGER_RECEIPTS_DB",
            DEFAULT_RECEIPT_PATH,
        )
        normalized = posixpath.normpath(selected)
        if not normalized.startswith("/data/"):
            raise FenceError(f"{name} receipt path is outside /data")
        selected_paths.add(normalized)
    if len(selected_paths) != 1:
        raise FenceError("receipt path differs across the five-container fleet")
    container_path = next(iter(selected_paths))
    host_path = (
        resolved_volume / container_path.removeprefix("/data/")
    ).resolve()
    if resolved_volume not in host_path.parents:
        raise FenceError("receipt path is outside /data")
    return ReceiptStore(container_path=container_path, host_path=host_path)


def safe_fleet_matches(
    observation: Mapping[str, Any],
    image_ref: str,
    revision: str,
    old_ids: Mapping[str, str],
) -> bool:
    if not CANONICAL_IMAGE_RE.fullmatch(image_ref):
        return False
    if not REVISION_RE.fullmatch(revision):
        return False
    containers = observation.get("containers")
    if not isinstance(containers, dict) or set(containers) != set(EXPECTED_CONTAINERS):
        return False
    if set(observation.get("volume_container_names", [])) != set(
        EXPECTED_CONTAINERS
    ):
        return False
    if observation.get("stray_writer_processes") or observation.get("queue_risk"):
        return False
    for name in EXPECTED_CONTAINERS:
        item = containers.get(name, {})
        if (
            item.get("running") is not True
            or item.get("image_ref") != image_ref
            or item.get("revision") != revision
            or not item.get("id")
            or item.get("id") == old_ids.get(name)
        ):
            return False
    return not observation.get("old_container_ids_running")


class Host:
    """Small subprocess boundary, replaceable in focused tests."""

    def run(
        self,
        args: Sequence[str],
        *,
        check: bool = True,
        input_text: str | None = None,
        timeout_seconds: int = HOST_COMMAND_TIMEOUT_SECONDS,
    ) -> str:
        try:
            result = subprocess.run(
                args,
                input=input_text,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise FenceError(
                f"host command timed out after {timeout_seconds}s: "
                f"{args[0]} {args[1] if len(args) > 1 else ''}"
            ) from exc
        if check and result.returncode:
            detail = result.stderr.strip().splitlines()
            bounded = detail[-1][:240] if detail else f"exit {result.returncode}"
            raise FenceError(f"{args[0]} {args[1] if len(args) > 1 else ''}: {bounded}")
        return result.stdout.strip()

    def container_info(self, name: str) -> dict[str, Any]:
        try:
            payload = json.loads(self.run(["docker", "inspect", name]))
            info = payload[0]
        except (IndexError, TypeError, json.JSONDecodeError) as exc:
            raise FenceError(f"invalid docker inspection for {name}") from exc
        if not isinstance(info, dict):
            raise FenceError(f"invalid docker inspection for {name}")
        return info

    def image_identity(self, image: str, expected_repository: str) -> tuple[str, str]:
        try:
            payload = json.loads(self.run(["docker", "image", "inspect", image]))
            info = payload[0]
        except (IndexError, TypeError, json.JSONDecodeError) as exc:
            raise FenceError("invalid docker image inspection") from exc
        repo_digests = [
            value
            for value in info.get("RepoDigests", []) or []
            if isinstance(value, str) and value.startswith(f"{expected_repository}@")
        ]
        if len(repo_digests) != 1 or not CANONICAL_IMAGE_RE.fullmatch(repo_digests[0]):
            raise FenceError("image does not resolve to one exact repository digest")
        revision = str(
            (info.get("Config", {}).get("Labels") or {}).get(
                "org.opencontainers.image.revision", ""
            )
        )
        if not REVISION_RE.fullmatch(revision):
            raise FenceError("image has no canonical source revision")
        return repo_digests[0], revision

    def volume_dir(self) -> Path:
        raw = self.run(
            [
                "docker",
                "volume",
                "inspect",
                VOLUME_NAME,
                "--format",
                "{{ .Mountpoint }}",
            ]
        )
        path = Path(raw).resolve()
        if not path.is_dir():
            raise FenceError("shared volume mountpoint is unavailable")
        return path

    def volume_container_names(self) -> list[str]:
        raw = self.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"volume={VOLUME_NAME}",
                "--format",
                "{{.Names}}",
            ]
        )
        return sorted(filter(None, raw.splitlines()))

    def container_pids(self, names: Iterable[str]) -> set[int]:
        pids: set[int] = set()
        for name in names:
            raw = self.run(
                ["docker", "top", name, "-eo", "pid"],
                check=False,
            )
            for line in raw.splitlines()[1:]:
                try:
                    pids.add(int(line.strip().split()[0]))
                except (IndexError, ValueError):
                    continue
        return pids

    def container_restart_policy(self, identity: str) -> str:
        policy = self.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.HostConfig.RestartPolicy.Name}}",
                identity,
            ]
        )
        if policy not in {"no", "always", "unless-stopped", "on-failure"}:
            raise FenceError(
                f"container restart policy is not authoritative: {identity}"
            )
        return policy

    def unit_state(self, unit: str) -> dict[str, str]:
        return {
            "active": self.run(["systemctl", "is-active", unit], check=False),
            "enabled": self.run(["systemctl", "is-enabled", unit], check=False),
        }

    def unit_present(self, unit: str) -> bool:
        state = self.unit_load_state(unit)
        return state != "not-found"

    def unit_load_state(self, unit: str) -> str:
        state = self.run(
            ["systemctl", "show", "--property", "LoadState", "--value", unit]
        )
        if state not in {"loaded", "masked", "not-found"}:
            raise FenceError(f"unit load state is not authoritative: {unit}={state!r}")
        return state

    def unit_active_state(self, unit: str) -> str:
        state = self.run(
            ["systemctl", "show", "--property", "ActiveState", "--value", unit]
        )
        if state not in {
            "active",
            "reloading",
            "inactive",
            "failed",
            "activating",
            "deactivating",
        }:
            raise FenceError(f"unit active state is not authoritative: {unit}={state!r}")
        return state


def _configured_image() -> str:
    try:
        for line in Path("/etc/tinyassets/env").read_text(
            encoding="utf-8"
        ).splitlines():
            if line.startswith("TINYASSETS_IMAGE="):
                return line.partition("=")[2]
    except OSError as exc:
        raise FenceError("cannot read configured production image") from exc
    raise FenceError("configured production image is missing")


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        _fsync_parent(path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _fsync_parent(path: Path) -> None:
    if os.name != "posix":
        return
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _load_state(path: Path) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FenceError("durable stop-writer fence state is unavailable") from exc
    if state.get("owner") != TASK_OWNER or state.get("schema_version") != 1:
        raise FenceError("durable stop-writer fence state is invalid")
    return state


def _require_run_id(run_id: str) -> None:
    if not RUN_ID_RE.fullmatch(run_id):
        raise FenceError("deploy fence run identity is invalid")


def _require_state_run(state: Mapping[str, Any], run_id: str) -> None:
    _require_run_id(run_id)
    if state.get("run_id") != run_id:
        raise FenceError("durable stop-writer fence belongs to another deploy run")


def _exact_inspections(host: Host) -> dict[str, dict[str, Any]]:
    return {name: host.container_info(name) for name in EXPECTED_CONTAINERS}


def _container_running_exact(host: Host, identity: str) -> bool:
    """Prove an old container ID is absent or has one authoritative state."""

    output = host.run(
        [
            "docker",
            "ps",
            "-a",
            "--no-trunc",
            "--filter",
            f"id={identity}",
            "--format",
            "{{.ID}}|{{.State}}",
        ]
    )
    if not output:
        return False
    rows = output.splitlines()
    if len(rows) != 1:
        raise FenceError(f"container state is not authoritative: {identity}")
    container_id, separator, state = rows[0].partition("|")
    if separator != "|" or container_id != identity:
        raise FenceError(f"container state is not authoritative: {identity}")
    if state in {"running", "restarting", "paused"}:
        return True
    if state in {"created", "exited", "dead"}:
        return False
    raise FenceError(f"container state is not authoritative: {identity}={state!r}")


def _named_container_running(host: Host, name: str) -> bool:
    output = host.run(
        [
            "docker",
            "ps",
            "--filter",
            f"name=^/{name}$",
            "--format",
            "{{.Names}}",
        ]
    )
    if not output:
        return False
    if output != name:
        raise FenceError(f"named container state is not authoritative: {name}")
    return True


def _wait_units_quiesced(
    host: Host,
    units: Sequence[str],
    *,
    attempts: int = 20,
    delay_seconds: float = 0.5,
) -> None:
    remaining: dict[str, str] = {}
    for attempt in range(attempts):
        remaining = {
            unit: state
            for unit in units
            if (state := host.unit_active_state(unit)) not in {"inactive", "failed"}
        }
        if not remaining:
            return
        if attempt + 1 < attempts:
            time.sleep(delay_seconds)
    raise FenceError(f"restart racer remains active after checked stop: {remaining}")


def _wait_units_restored(
    host: Host,
    expected_states: Mapping[str, Mapping[str, str]],
    *,
    timeout_seconds: float = UNIT_RESTORE_TIMEOUT_SECONDS,
    delay_seconds: float = 1.0,
) -> dict[str, dict[str, str]]:
    """Wait through transient systemd states, then require exact saved state."""

    actual: dict[str, dict[str, str]] = {}
    attempts = max(1, int(timeout_seconds / delay_seconds) + 1)
    for attempt in range(attempts):
        actual = {
            unit: _validated_unit_state(host, unit)
            for unit in expected_states
        }
        mismatches = {
            unit: {
                "expected": dict(expected_states[unit]),
                "actual": actual[unit],
            }
            for unit in expected_states
            if actual[unit] != expected_states[unit]
        }
        if not mismatches:
            return actual
        if attempt + 1 < attempts:
            time.sleep(delay_seconds)
    raise FenceError(
        f"unit restoration proof failed after {timeout_seconds:g}s timeout: "
        f"mismatches={mismatches}"
    )


def _set_restart_no(
    host: Host,
    consumers: Mapping[str, Mapping[str, Any]],
) -> dict[str, str]:
    proved: dict[str, str] = {}
    for name, info in consumers.items():
        identity = str(info.get("Id", ""))
        if not identity:
            raise FenceError(f"container identity is unavailable: {name}")
        host.run(["docker", "update", "--restart=no", identity])
        policy = host.container_restart_policy(identity)
        if policy != "no":
            raise FenceError(
                f"container restart fence did not persist: {name}={policy}"
            )
        proved[name] = policy
    return proved


def _apply_boot_fence(host: Host, present_racers: Sequence[str]) -> None:
    for unit in present_racers:
        if unit.endswith(".timer"):
            host.run(["systemctl", "disable", "--now", unit])
    host.run(["systemctl", "disable", DAEMON_SERVICE])


def _stop_and_mask_writer_units(
    host: Host,
    *,
    boot_fence_applied: bool = False,
) -> tuple[str, ...]:
    present_racers = tuple(
        unit for unit in RESTART_RACER_UNITS if host.unit_present(unit)
    )
    if not host.unit_present(DAEMON_SERVICE):
        raise FenceError(f"required production unit is missing: {DAEMON_SERVICE}")
    if not boot_fence_applied:
        _apply_boot_fence(host, present_racers)
    for unit in (*present_racers, DAEMON_SERVICE):
        host.run(["systemctl", "stop", unit])
    if present_racers:
        host.run(["systemctl", "mask", "--runtime", *present_racers])
    host.run(["systemctl", "mask", "--runtime", DAEMON_SERVICE])
    _wait_units_quiesced(host, (*present_racers, DAEMON_SERVICE))
    return present_racers


def _looks_like_writer_command(cmdline: str) -> bool:
    return any(marker in cmdline.lower() for marker in WRITER_PROCESS_MARKERS)


def _stray_writer_processes(
    receipt_path: Path,
    excluded_pids: set[int],
    volume_dir: Path | None = None,
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    receipt_related = {
        receipt_path.resolve(),
        Path(f"{receipt_path}-wal").resolve(),
        Path(f"{receipt_path}-shm").resolve(),
    }
    for proc in sorted(Path("/proc").glob("[0-9]*")):
        try:
            pid = int(proc.name)
            if pid == os.getpid() or pid in excluded_pids:
                continue
            exe = Path(os.readlink(proc / "exe")).name
            cmdline = (
                (proc / "cmdline")
                .read_bytes()
                .replace(b"\0", b" ")
                .decode("utf-8", "replace")
                .lower()
            )
            receipt_fd = False
            for descriptor in (proc / "fd").iterdir():
                try:
                    target = Path(os.path.realpath(descriptor)).resolve()
                except PermissionError as exc:
                    raise FenceError(
                        f"process scan permission denied: pid={pid}"
                    ) from exc
                except OSError:
                    continue
                if target in receipt_related:
                    receipt_fd = True
                    break
            server_like = _looks_like_writer_command(cmdline)
            controlled_path_env_keys: list[str] = []
            controlled_mount_namespace = False
            same_host_mount_namespace = False
            mount_namespace = ""
            if volume_dir is not None:
                resolved_volume = volume_dir.resolve()
                environ = (proc / "environ").read_bytes().split(b"\0")
                for item in environ:
                    key_raw, separator, value_raw = item.partition(b"=")
                    if not separator:
                        continue
                    value = value_raw.decode("utf-8", "replace")
                    if not value.startswith("/"):
                        continue
                    try:
                        candidate = Path(value).resolve()
                    except OSError:
                        continue
                    if candidate == resolved_volume or resolved_volume in candidate.parents:
                        controlled_path_env_keys.append(
                            key_raw.decode("utf-8", "replace")
                        )
                mountinfo = (proc / "mountinfo").read_text(
                    encoding="utf-8",
                    errors="replace",
                )
                try:
                    mount_namespace = os.readlink(proc / "ns" / "mnt")
                    own_mount_namespace = os.readlink("/proc/self/ns/mnt")
                    same_host_mount_namespace = (
                        mount_namespace == own_mount_namespace
                    )
                except OSError as exc:
                    raise FenceError(
                        f"process mount namespace unreadable: pid={pid}"
                    ) from exc
                controlled_mount_namespace = (
                    str(resolved_volume) in mountinfo
                    and not same_host_mount_namespace
                )
            if (
                receipt_fd
                or server_like
                or controlled_path_env_keys
                or controlled_mount_namespace
            ):
                risks.append(
                    {
                        "pid": pid,
                        "exe": exe,
                        "receipt_fd": receipt_fd,
                        "server_like": server_like,
                        "controlled_path_env_keys": sorted(
                            set(controlled_path_env_keys)
                        ),
                        "controlled_mount_namespace": controlled_mount_namespace,
                        "same_host_mount_namespace": same_host_mount_namespace,
                        "mount_namespace": mount_namespace,
                    }
                )
        except PermissionError as exc:
            raise FenceError(f"process scan permission denied: pid={pid}") from exc
        except (FileNotFoundError, ProcessLookupError):
            continue
    return risks[:100]


def observe_fleet(
    host: Host,
    *,
    expected_image_ref: str | None = None,
) -> dict[str, Any]:
    inspections = _exact_inspections(host)
    volume_dir = host.volume_dir()
    receipt = resolve_receipt_store(inspections, volume_dir)
    configured = expected_image_ref or _configured_image()
    if not CANONICAL_IMAGE_RE.fullmatch(configured):
        raise FenceError("configured image is not an immutable digest")
    repository = configured.partition("@")[0]
    containers: dict[str, dict[str, Any]] = {}
    for name, info in inspections.items():
        image_ref, revision = host.image_identity(
            str(info.get("Image", "")),
            repository,
        )
        containers[name] = {
            "id": str(info.get("Id", "")),
            "running": bool(info.get("State", {}).get("Running")),
            "pid": int(info.get("State", {}).get("Pid") or 0),
            "image_ref": image_ref,
            "revision": revision,
        }
    excluded_pids = host.container_pids(EXPECTED_CONTAINERS)
    return {
        "containers": containers,
        "volume_container_names": host.volume_container_names(),
        "receipt_container_path": receipt.container_path,
        "receipt_host_path": str(receipt.host_path),
        "receipt_snapshot": receipt_snapshot(receipt.host_path),
        "queue_risk": inventory_queue_risk(volume_dir),
        "stray_writer_processes": _stray_writer_processes(
            receipt.host_path,
            excluded_pids,
            volume_dir,
        ),
    }


def _old_identity(
    host: Host,
    inspections: Mapping[str, Mapping[str, Any]],
) -> tuple[str, str]:
    configured = _configured_image()
    if not CANONICAL_IMAGE_RE.fullmatch(configured):
        raise FenceError("previous configured image is not an immutable digest")
    repository = configured.partition("@")[0]
    identities = {
        host.image_identity(str(info.get("Image", "")), repository)
        for info in inspections.values()
    }
    if len(identities) != 1:
        raise FenceError("old five-container fleet does not share one exact image")
    image_ref, revision = next(iter(identities))
    if image_ref != configured:
        raise FenceError("old configured and running image digests disagree")
    return image_ref, revision


def preflight(
    host: Host,
    *,
    image_ref: str,
    target_revision: str,
    run_id: str,
    state_path: Path,
) -> dict[str, Any]:
    _require_run_id(run_id)
    if state_path.is_file():
        existing = _load_state(state_path)
        if existing.get("phase") != "restored" or _masked_units(host):
            raise FenceError("an earlier stop-writer fence requires reconciliation")
    if not CANONICAL_IMAGE_RE.fullmatch(image_ref):
        raise FenceError("target image is not an immutable digest")
    if not REVISION_RE.fullmatch(target_revision):
        raise FenceError("target revision is not canonical")
    repository = image_ref.partition("@")[0]
    pulled_ref, pulled_revision = host.image_identity(image_ref, repository)
    if (pulled_ref, pulled_revision) != (image_ref, target_revision):
        raise FenceError("pulled target image identity disagrees")

    inspections = _exact_inspections(host)
    for name, info in inspections.items():
        if not info.get("State", {}).get("Running"):
            raise FenceError(f"old expected container is not running: {name}")
    volume_dir = host.volume_dir()
    receipt = resolve_receipt_store(inspections, volume_dir)
    volume_names = set(host.volume_container_names())
    if not set(EXPECTED_CONTAINERS) <= volume_names:
        raise FenceError("expected container is absent from the production volume")
    extra_names = tuple(sorted(volume_names - set(EXPECTED_CONTAINERS)))
    extra_inspections = {
        name: host.container_info(name) for name in extra_names
    }
    extra_consumers = {
        name: {
            "id": str(info.get("Id", "")),
            "running": bool(info.get("State", {}).get("Running")),
            "restart_policy": str(
                info.get("HostConfig", {}).get("RestartPolicy", {}).get("Name", "")
            ),
        }
        for name, info in extra_inspections.items()
    }
    old_image_ref, old_revision = _old_identity(host, inspections)
    old_ids = {name: str(info.get("Id", "")) for name, info in inspections.items()}
    controlled_pids = host.container_pids((*EXPECTED_CONTAINERS, *extra_names))
    preliminary_risk = inventory_queue_risk(volume_dir)
    preliminary_processes = _stray_writer_processes(
        receipt.host_path,
        controlled_pids,
        volume_dir,
    )
    preliminary_snapshot = receipt_snapshot(receipt.host_path)
    if preliminary_risk:
        raise FenceError("pre-mutation bug_investigation queue risk is nonzero")
    if preliminary_processes:
        raise FenceError("pre-mutation stray writer process risk is nonzero")
    present_racers = tuple(
        unit for unit in RESTART_RACER_UNITS if host.unit_present(unit)
    )
    if not host.unit_present(DAEMON_SERVICE):
        raise FenceError(f"required production unit is missing: {DAEMON_SERVICE}")

    state: dict[str, Any] = {
        "schema_version": 1,
        "owner": TASK_OWNER,
        "run_id": run_id,
        "phase": "fencing_planned",
        "target_image_ref": image_ref,
        "target_revision": target_revision,
        "previous_image_ref": old_image_ref,
        "previous_revision": old_revision,
        "volume_mountpoint": str(volume_dir),
        "receipt_container_path": receipt.container_path,
        "receipt_host_path": str(receipt.host_path),
        "old_container_ids": old_ids,
        "restart_racer_state": {
            unit: host.unit_state(unit) for unit in present_racers
        },
        "daemon_service_state": host.unit_state(DAEMON_SERVICE),
        "old_restart_policies": {
            name: str(info.get("HostConfig", {}).get("RestartPolicy", {}).get("Name", ""))
            for name, info in inspections.items()
        },
        "preliminary_receipt_snapshot": preliminary_snapshot,
        "present_restart_racer_units": present_racers,
        "extra_volume_consumers": extra_consumers,
        "fence_progress": {
            "restart_policy_proved": False,
            "boot_activators_disabled": False,
        },
    }

    # Write-ahead invariant: canonical current-run state is durable before the
    # first mutation. Every later failure is therefore visible to guards and
    # cleanup. The host operation lock keeps cleanup behind this full command.
    _atomic_json(state_path, state)
    consumers = {**inspections, **extra_inspections}
    state["restart_policy_proof"] = _set_restart_no(host, consumers)
    state["fence_progress"]["restart_policy_proved"] = True
    _atomic_json(state_path, state)
    _apply_boot_fence(host, present_racers)
    state["fence_progress"]["boot_activators_disabled"] = True
    state["phase"] = "fencing"
    _atomic_json(state_path, state)

    stopped_racers = _stop_and_mask_writer_units(
        host,
        boot_fence_applied=True,
    )
    if stopped_racers != present_racers:
        raise FenceError("restart racer inventory changed during quiescence")
    host.run(
        ["docker", "stop", *EXPECTED_CONTAINERS, *extra_names],
        check=False,
    )

    state["phase"] = "quiesced"
    _atomic_json(state_path, state)
    old_still_running = []
    for name, old_id in old_ids.items():
        if _container_running_exact(host, old_id):
            old_still_running.append({"container": name, "id": old_id})
    final_risk = inventory_queue_risk(volume_dir)
    extra_still_running = [
        name for name in extra_names if _named_container_running(host, name)
    ]
    final_processes = _stray_writer_processes(receipt.host_path, set(), volume_dir)
    final_snapshot = receipt_snapshot(receipt.host_path)
    if old_still_running:
        raise FenceError("old container still running after quiescence")
    if extra_still_running:
        raise FenceError("extra production-volume consumer survived quiescence")
    if final_risk:
        raise FenceError("post-quiesce bug_investigation queue risk is nonzero")
    if final_processes:
        raise FenceError("post-quiesce stray writer process risk is nonzero")
    if final_snapshot != preliminary_snapshot:
        raise FenceError("receipt snapshot changed during writer quiescence")
    state["receipt_snapshot"] = final_snapshot
    if extra_consumers:
        state["phase"] = "unsafe_fenced"
        _atomic_json(state_path, state)
        raise FenceError(
            "extra production-volume consumer was fenced; refusing deployment"
        )
    state["phase"] = "preflight_proved"
    _atomic_json(state_path, state)
    return {
        "schema_version": 1,
        "owner": TASK_OWNER,
        "phase": state["phase"],
        "safe": True,
        "target_image_ref": image_ref,
        "target_revision": target_revision,
        "previous_image_ref": old_image_ref,
        "previous_revision": old_revision,
        "old_container_ids": old_ids,
        "receipt_container_path": receipt.container_path,
        "receipt_host_path": str(receipt.host_path),
        "preliminary_queue_risk": preliminary_risk,
        "final_queue_risk": final_risk,
        "stray_writer_processes": final_processes,
        "receipt_snapshot": final_snapshot,
        "restart_racer_state": state["restart_racer_state"],
    }


def prepare_deploy(
    host: Host,
    *,
    image_ref: str,
    run_id: str,
    state_path: Path,
) -> dict[str, Any]:
    state = _load_state(state_path)
    _require_state_run(state, run_id)
    if state.get("phase") != "preflight_proved":
        raise FenceError("stop-writer preflight is not proved")
    if image_ref != state.get("target_image_ref") or _configured_image() != image_ref:
        raise FenceError("atomically installed target image does not match fence")
    volume_dir = Path(str(state["volume_mountpoint"]))
    if inventory_queue_risk(volume_dir):
        raise FenceError("queue risk appeared before target start")
    receipt_path = Path(str(state["receipt_host_path"]))
    if receipt_snapshot(receipt_path) != state.get("receipt_snapshot"):
        raise FenceError("receipt snapshot changed before target start")
    for old_id in state["old_container_ids"].values():
        if _container_running_exact(host, old_id):
            raise FenceError("old container restarted before target start")
    host.run(["systemctl", "unmask", "--runtime", DAEMON_SERVICE])
    state["phase"] = "target_installed"
    _atomic_json(state_path, state)
    return {"owner": TASK_OWNER, "phase": state["phase"], "safe": True}


def prove(
    host: Host,
    *,
    image_ref: str,
    revision: str,
    run_id: str,
    state_path: Path,
) -> dict[str, Any]:
    state = _load_state(state_path)
    _require_state_run(state, run_id)
    if state.get("phase") not in {
        "target_installed",
        "safe_fleet",
        "post_canary_proved",
        "recovery_pending_canary",
        "canary_accepted",
        "finalizing",
        "restored",
    }:
        raise FenceError("target was not prepared under the stop-writer fence")
    admitted_identities = {
        (
            str(state.get("target_image_ref", "")),
            str(state.get("target_revision", "")),
        ),
        (
            str(state.get("previous_image_ref", "")),
            str(state.get("previous_revision", "")),
        ),
    }
    if (image_ref, revision) not in admitted_identities:
        raise FenceError("active image identity is not admitted by durable fence state")
    observation = observe_fleet(host, expected_image_ref=image_ref)
    old_ids = state.get("old_container_ids", {})
    old_running = []
    for name, old_id in old_ids.items():
        if _container_running_exact(host, old_id):
            old_running.append({"container": name, "id": old_id})
    observation["old_container_ids_running"] = old_running
    if not safe_fleet_matches(observation, image_ref, revision, old_ids):
        state["last_failed_observation"] = observation
        _atomic_json(state_path, state)
        raise FenceError(
            "exactly five safe target containers were not independently proved"
        )
    if observation["receipt_snapshot"] != state.get("receipt_snapshot"):
        raise FenceError("post-deploy receipt snapshot mismatch")
    if state.get("phase") not in {
        "recovery_pending_canary",
        "canary_accepted",
        "finalizing",
    }:
        state["phase"] = "safe_fleet"
    _atomic_json(state_path, state)
    return {
        "schema_version": 1,
        "owner": TASK_OWNER,
        "phase": state["phase"],
        "safe": True,
        "target_image_ref": image_ref,
        "target_revision": revision,
        "old_container_ids": old_ids,
        "observation": observation,
    }


def post_canary(
    host: Host,
    *,
    image_ref: str,
    revision: str,
    run_id: str,
    state_path: Path,
) -> dict[str, Any]:
    evidence: dict[str, Any] | None = None
    last_error = ""
    for attempt in range(10):
        try:
            evidence = prove(
                host,
                image_ref=image_ref,
                revision=revision,
                run_id=run_id,
                state_path=state_path,
            )
            break
        except FenceError as exc:
            last_error = str(exc)
            if attempt < 9:
                time.sleep(2)
    if evidence is None:
        state = _load_state(state_path)
        diagnostic = state.get("last_failed_observation", {})
        raise FenceError(
            "post-canary exact fleet proof did not converge: "
            f"{last_error}; diagnostic={json.dumps(diagnostic, sort_keys=True)}"
        )
    evidence["phase"] = "post_canary_proved"
    state = _load_state(state_path)
    state["phase"] = "post_canary_proved"
    _atomic_json(state_path, state)
    return evidence


def _masked_units(host: Host) -> list[str]:
    units = (*RESTART_RACER_UNITS, DAEMON_SERVICE)
    return [
        unit
        for unit in units
        if host.unit_present(unit)
        and (
            host.unit_state(unit)["enabled"] in {"masked", "masked-runtime"}
            or host.unit_load_state(unit) == "masked"
        )
    ]


def fence_status(
    host: Host,
    *,
    run_id: str,
    state_path: Path,
) -> dict[str, Any]:
    _require_run_id(run_id)
    state: dict[str, Any] | None = None
    state_error = ""
    if state_path.is_file():
        try:
            state = _load_state(state_path)
        except FenceError as exc:
            state_error = str(exc)
    return {
        "owner": TASK_OWNER,
        "state_exists": state_path.is_file(),
        "state_phase": state.get("phase") if state else None,
        "state_run_id": state.get("run_id") if state else None,
        "current_run_matches": bool(state and state.get("run_id") == run_id),
        "current_run_cutover_started": bool(
            state
            and state.get("run_id") == run_id
            and state.get("phase") not in {"restored"}
        ),
        "state_error": state_error,
        "masked_units": _masked_units(host),
    }


def guard_host_mutation(host: Host, *, state_path: Path) -> dict[str, Any]:
    """Reject host mutation when canonical state or fence residue is unsafe."""

    if state_path.exists():
        state = _load_state(state_path)
        if state.get("phase") != "restored":
            raise FenceError(
                f"production cutover fence is {state.get('phase')!r}"
            )
        return {
            "owner": TASK_OWNER,
            "guard": "restored_state",
            "safe": True,
        }

    residue: list[dict[str, str]] = []
    for unit in (*RESTART_RACER_UNITS, DAEMON_SERVICE):
        if not host.unit_present(unit):
            continue
        state = _validated_unit_state(host, unit)
        enabled = state["enabled"]
        if enabled in {"masked", "masked-runtime"} or (
            enabled == "disabled"
            and (unit == DAEMON_SERVICE or unit.endswith(".timer"))
        ):
            residue.append(
                {"kind": "unit", "name": unit, "value": enabled}
            )
    for name in host.volume_container_names():
        info = host.container_info(name)
        identity = str(info.get("Id", ""))
        policy = host.container_restart_policy(identity)
        if policy == "no":
            residue.append(
                {"kind": "container", "name": name, "value": "restart=no"}
            )
    if residue:
        raise FenceError(f"stop-writer fence residue is present: {residue}")
    return {"owner": TASK_OWNER, "guard": "clean_absence", "safe": True}


def _archive_corrupt_state(state_path: Path) -> Path | None:
    if not state_path.exists():
        return None
    archive = state_path.with_name(
        f"{state_path.name}.corrupt-{time.time_ns()}"
    )
    shutil.copyfile(state_path, archive)
    os.chmod(archive, 0o600)
    with archive.open("r+b") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_parent(state_path)
    return archive


def quiesce_unsafe(
    host: Host,
    *,
    run_id: str,
    state_path: Path,
) -> dict[str, Any]:
    """Idempotently stop every controlled writer while leaving the fence closed."""

    _require_run_id(run_id)
    state_error = ""
    state_valid = True
    try:
        state = _load_state(state_path)
    except FenceError as exc:
        state_error = str(exc)
        state_valid = False
        state = {
            "schema_version": 1,
            "owner": TASK_OWNER,
            "run_id": run_id,
            "phase": "emergency_fencing",
            "old_container_ids": {},
            "extra_volume_consumers": {},
        }

    volume_dir = host.volume_dir()
    current_volume_names = set(host.volume_container_names())
    current_inspections = {
        name: host.container_info(name) for name in sorted(current_volume_names)
    }
    receipt_resolution_error = ""
    receipt: ReceiptStore | None = None
    if state.get("receipt_host_path") and state.get("volume_mountpoint"):
        receipt = ReceiptStore(
            container_path=str(state.get("receipt_container_path", "")),
            host_path=Path(str(state["receipt_host_path"])),
        )
        volume_dir = Path(str(state["volume_mountpoint"]))
    else:
        try:
            expected_inspections = {
                name: current_inspections[name] for name in EXPECTED_CONTAINERS
            }
            receipt = resolve_receipt_store(expected_inspections, volume_dir)
            state["receipt_container_path"] = receipt.container_path
            state["receipt_host_path"] = str(receipt.host_path)
            state["volume_mountpoint"] = str(volume_dir)
        except (FenceError, KeyError) as exc:
            receipt_resolution_error = (
                str(exc)
                if isinstance(exc, FenceError)
                else "expected writer is unavailable for receipt resolution"
            )

    recorded_extras = dict(state.get("extra_volume_consumers", {}))
    extra_names = tuple(
        sorted(
            (current_volume_names - set(EXPECTED_CONTAINERS))
            | set(recorded_extras)
        )
    )
    for name in extra_names:
        info = current_inspections.get(name)
        if info is not None:
            recorded_extras[name] = {
                "id": str(info.get("Id", "")),
                "running": bool(info.get("State", {}).get("Running")),
                "restart_policy": str(
                    info.get("HostConfig", {})
                    .get("RestartPolicy", {})
                    .get("Name", "")
                ),
            }
        elif name not in recorded_extras:
            recorded_extras[name] = {"inspection_error": True}
    state["extra_volume_consumers"] = recorded_extras
    state["source_run_id"] = state.get("source_run_id") or state.get("run_id")
    state["run_id"] = run_id
    state["recovery_run_id"] = run_id
    state["phase"] = "emergency_fencing_planned"
    state["emergency_fence_progress"] = {
        "restart_policy_proved": False,
        "boot_activators_disabled": False,
    }
    archived_state = None
    if not state_valid:
        archived_state = _archive_corrupt_state(state_path)
    state["archived_corrupt_state"] = (
        str(archived_state) if archived_state else ""
    )
    _atomic_json(state_path, state)

    restart_policy_proof = _set_restart_no(host, current_inspections)
    state["restart_policy_proof"] = restart_policy_proof
    state["emergency_fence_progress"]["restart_policy_proved"] = True
    _atomic_json(state_path, state)
    present_racers = tuple(
        unit for unit in RESTART_RACER_UNITS if host.unit_present(unit)
    )
    if not host.unit_present(DAEMON_SERVICE):
        raise FenceError(f"required production unit is missing: {DAEMON_SERVICE}")
    _apply_boot_fence(host, present_racers)
    state["emergency_fence_progress"]["boot_activators_disabled"] = True
    state["phase"] = "emergency_fencing"
    _atomic_json(state_path, state)

    stopped_racers = _stop_and_mask_writer_units(
        host,
        boot_fence_applied=True,
    )
    if stopped_racers != present_racers:
        raise FenceError("restart racer inventory changed during emergency fence")
    controlled_names = tuple(sorted(current_volume_names | set(recorded_extras)))
    host.run(["docker", "stop", *controlled_names], check=False)

    names_still_running = [
        name for name in controlled_names if _named_container_running(host, name)
    ]
    old_running = [
        {"container": name, "id": old_id}
        for name, old_id in state.get("old_container_ids", {}).items()
        if _container_running_exact(host, old_id)
    ]
    process_risk: list[dict[str, Any]] = []
    process_error = ""
    if receipt is not None:
        try:
            process_risk = _stray_writer_processes(
                receipt.host_path,
                set(),
                volume_dir,
            )
        except FenceError as exc:
            process_error = str(exc)
    if (
        names_still_running
        or old_running
        or process_risk
        or receipt_resolution_error
        or process_error
    ):
        state["phase"] = "unsafe_fence_unproved"
        state["receipt_resolution_error"] = receipt_resolution_error
        state["process_scan_error"] = process_error
        _atomic_json(state_path, state)
        raise FenceError(
            "unsafe writer cleanup could not prove all controlled writers stopped"
        )
    state["phase"] = "unsafe_fenced"
    _atomic_json(state_path, state)
    return {
        "schema_version": 1,
        "owner": TASK_OWNER,
        "phase": "unsafe_fenced",
        "safe": False,
        "writers_fenced": True,
        "present_restart_racer_units": present_racers,
        "named_containers_running": names_still_running,
        "old_container_ids_running": old_running,
        "stray_writer_processes": process_risk,
        "restart_policy_proof": restart_policy_proof,
        "masked_units": _masked_units(host),
        "source_state_error": state_error,
        "archived_corrupt_state": str(archived_state) if archived_state else "",
        "durable_state_path": str(state_path),
    }


def _validated_unit_state(host: Host, unit: str) -> dict[str, str]:
    state = host.unit_state(unit)
    if state.get("active") not in {
        "active",
        "reloading",
        "inactive",
        "failed",
        "activating",
        "deactivating",
    }:
        raise FenceError(f"unit active state is not authoritative: {unit}")
    if state.get("enabled") not in {
        "enabled",
        "enabled-runtime",
        "linked",
        "linked-runtime",
        "static",
        "disabled",
        "indirect",
        "generated",
        "transient",
        "masked",
        "masked-runtime",
    }:
        raise FenceError(f"unit enablement is not authoritative: {unit}")
    return state


def restore_if_safe(
    host: Host,
    *,
    image_ref: str,
    revision: str,
    run_id: str,
    state_path: Path,
) -> dict[str, Any]:
    _require_run_id(run_id)
    masked_before = _masked_units(host)
    if not state_path.is_file():
        if masked_before:
            raise FenceError(
                "fence state missing while restart units remain masked; "
                "leaving restart racers fenced"
            )
        return {
            "owner": TASK_OWNER,
            "phase": "not_applicable",
            "safe": True,
            "masked_units": [],
        }
    state = _load_state(state_path)
    _require_state_run(state, run_id)
    evidence = prove(
        host,
        image_ref=image_ref,
        revision=revision,
        run_id=run_id,
        state_path=state_path,
    )
    racer_state = state.get("restart_racer_state", {})
    saved_racers = tuple(
        state.get("present_restart_racer_units") or racer_state.keys()
    )
    saved_units = (*saved_racers, DAEMON_SERVICE)
    if any(not host.unit_present(unit) for unit in saved_units):
        raise FenceError("unit restoration proof failed: saved unit is missing")
    host.run(["systemctl", "unmask", "--runtime", *saved_units])
    for unit in saved_racers:
        prior = racer_state.get(unit, {})
        if prior.get("enabled") == "enabled":
            host.run(["systemctl", "enable", unit])
        if prior.get("active") == "active":
            host.run(["systemctl", "start", unit])
    daemon_state = state.get("daemon_service_state", {})
    if daemon_state.get("enabled") == "enabled":
        host.run(["systemctl", "enable", DAEMON_SERVICE])
    if daemon_state.get("active") == "active":
        host.run(["systemctl", "start", DAEMON_SERVICE])

    expected_states = {**racer_state, DAEMON_SERVICE: daemon_state}
    actual_states = _wait_units_restored(host, expected_states)
    masks_after = _masked_units(host)
    if masks_after:
        raise FenceError(
            "unit restoration proof failed: "
            f"masked={masks_after}"
        )
    state["phase"] = "restored"
    _atomic_json(state_path, state)
    evidence.update(
        {
            "phase": "restored",
            "masked_units_before": masked_before,
            "masked_units_after": masks_after,
            "restored_unit_states": actual_states,
        }
    )
    return evidence


def _validate_unsafe_recovery_source(
    host: Host,
    *,
    source_run_id: str,
    image_ref: str,
    revision: str,
    state_path: Path,
) -> tuple[dict[str, Any], str, str]:
    """Validate an immutable unsafe-fence generation before any mutation."""

    _require_run_id(source_run_id)
    state = _load_state(state_path)
    if state.get("phase") != "unsafe_fenced":
        raise FenceError("canonical state is not an authoritatively unsafe fence")
    if (state.get("source_run_id") or state.get("run_id")) != source_run_id:
        raise FenceError("unsafe fence belongs to another source run")
    required = (
        "target_image_ref",
        "target_revision",
        "previous_image_ref",
        "previous_revision",
        "volume_mountpoint",
        "receipt_host_path",
        "receipt_snapshot",
        "old_container_ids",
        "restart_racer_state",
        "daemon_service_state",
        "present_restart_racer_units",
        "extra_volume_consumers",
    )
    if any(key not in state for key in required):
        raise FenceError("unsafe fence lacks complete inherited preflight state")
    if state.get("extra_volume_consumers"):
        raise FenceError("unsafe fence recorded extra production-volume consumers")
    if not CANONICAL_IMAGE_RE.fullmatch(image_ref):
        raise FenceError("runner-bound recovery image is not immutable")
    if not REVISION_RE.fullmatch(revision):
        raise FenceError("runner-bound recovery revision is not canonical")
    configured = _configured_image()
    if configured != image_ref:
        raise FenceError("runner-bound recovery image disagrees with configured image")
    recorded = {
        (
            str(state["target_image_ref"]),
            str(state["target_revision"]),
        ),
        (
            str(state["previous_image_ref"]),
            str(state["previous_revision"]),
        ),
    }
    if (image_ref, revision) not in recorded:
        raise FenceError("runner-bound recovery identity is not recorded")
    repository = image_ref.partition("@")[0]
    if host.image_identity(image_ref, repository) != (image_ref, revision):
        raise FenceError("local recovery image identity disagrees with runner binding")
    policies = state.get("old_restart_policies")
    if not isinstance(policies, dict) or set(policies) != set(EXPECTED_CONTAINERS):
        raise FenceError("saved restart policy keys are incomplete")
    if any(
        policy not in {"always", "unless-stopped", "on-failure", "no"}
        for policy in policies.values()
    ):
        raise FenceError("saved restart policy is invalid")
    names = set(host.volume_container_names())
    if names not in (set(), set(EXPECTED_CONTAINERS)):
        raise FenceError("fenced volume has partial or extra writer containers")
    if names:
        inspections = _exact_inspections(host)
        for name, info in inspections.items():
            if info.get("State", {}).get("Running"):
                raise FenceError(f"fenced writer is still running: {name}")
            identity = host.image_identity(str(info.get("Image", "")), repository)
            if identity != (image_ref, revision):
                raise FenceError(
                    "fenced fleet identity disagrees with runner binding"
                )
            container_id = str(info.get("Id", ""))
            if host.container_restart_policy(container_id) != "no":
                raise FenceError("fenced writer restart policy is not no")
    volume_dir = Path(str(state["volume_mountpoint"]))
    if volume_dir.resolve() != host.volume_dir().resolve():
        raise FenceError("fenced volume mountpoint changed")
    if inventory_queue_risk(volume_dir):
        raise FenceError("bug_investigation queue risk appeared while fenced")
    receipt_path = Path(str(state["receipt_host_path"]))
    if receipt_snapshot(receipt_path) != state["receipt_snapshot"]:
        raise FenceError("receipt snapshot changed while fenced")
    for old_id in state["old_container_ids"].values():
        if _container_running_exact(host, str(old_id)):
            raise FenceError("old writer container restarted while fenced")
    if _stray_writer_processes(receipt_path, set(), volume_dir):
        raise FenceError("stray writer process exists while fenced")
    expected_units = (
        *tuple(state["present_restart_racer_units"]),
        DAEMON_SERVICE,
    )
    for unit in expected_units:
        if not host.unit_present(unit):
            raise FenceError(f"saved production unit is missing: {unit}")
        unit_state = _validated_unit_state(host, unit)
        load_state = host.unit_load_state(unit)
        permitted_enabled = {"masked", "masked-runtime", "disabled"}
        if unit.endswith(".service") and unit != DAEMON_SERVICE:
            permitted_enabled.add("static")
        if unit_state["enabled"] not in permitted_enabled:
            raise FenceError(f"fenced unit can still boot-start: {unit}")
        if load_state not in {"loaded", "masked"}:
            raise FenceError(f"fenced unit load state is not authoritative: {unit}")
        if unit_state["active"] not in {"inactive", "failed"}:
            raise FenceError(f"fenced unit is not inactive: {unit}")
    return state, image_ref, revision


def _recovery_unit_name(run_id: str) -> str:
    suffix = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16]
    return f"tinyassets-recovery-expiry-{suffix}"


def _prove_recovery_entrypoint() -> str:
    """Prove the expiry timer will invoke this exact installed script."""

    try:
        running_path = Path(__file__).resolve(strict=True)
        timer_path = RECOVERY_SCRIPT_PATH.resolve(strict=True)
    except OSError as exc:
        raise FenceError(
            f"recovery timer entrypoint is unavailable: {exc}"
        ) from exc
    if not running_path.samefile(timer_path):
        raise FenceError(
            "recovery timer entrypoint does not match the running script"
        )
    if not os.access(timer_path, os.X_OK):
        raise FenceError("recovery timer entrypoint is not executable")
    return hashlib.sha256(timer_path.read_bytes()).hexdigest()


def _arm_recovery_expiry(
    host: Host,
    *,
    source_run_id: str,
    run_id: str,
    state_path: Path,
) -> str:
    unit = _recovery_unit_name(run_id)
    host.run(
        [
            "systemd-run",
            "--quiet",
            "--collect",
            f"--unit={unit}",
            f"--on-active={RECOVERY_LEASE_SECONDS}s",
            "--timer-property=AccuracySec=1s",
            "/usr/bin/python3",
            str(RECOVERY_SCRIPT_PATH),
            "--state-path",
            str(state_path),
            "expire-recovery",
            "--source-run-id",
            source_run_id,
            "--run-id",
            run_id,
        ]
    )
    return unit


def _cancel_recovery_expiry(host: Host, unit: str) -> None:
    if unit:
        host.run(
            ["systemctl", "stop", f"{unit}.timer", f"{unit}.service"],
            check=False,
        )


def _prove_recovery_fences(
    host: Host,
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """Require every temporary recovery fence immediately before restore."""

    inspections = _exact_inspections(host)
    policies = {
        name: host.container_restart_policy(str(info.get("Id", "")))
        for name, info in inspections.items()
    }
    if set(policies.values()) != {"no"}:
        raise FenceError(
            f"recovery restart fence drifted before finalization: {policies}"
        )
    unit_proof: dict[str, dict[str, str]] = {}
    for unit in (
        *tuple(state.get("present_restart_racer_units") or ()),
        DAEMON_SERVICE,
    ):
        unit_state = _validated_unit_state(host, unit)
        if unit_state["active"] not in {"inactive", "failed"}:
            raise FenceError(f"recovery boot fence became active: {unit}")
        permitted = {"disabled", "masked", "masked-runtime"}
        if unit.endswith(".service") and unit != DAEMON_SERVICE:
            permitted.add("static")
        if unit_state["enabled"] not in permitted:
            raise FenceError(f"recovery boot fence became enabled: {unit}")
        unit_proof[unit] = unit_state
    expiry = str(state.get("recovery_expiry_unit", ""))
    if not expiry:
        raise FenceError("recovery expiry ownership is missing")
    timer = f"{expiry}.timer"
    timer_state = _validated_unit_state(host, timer)
    if (
        timer_state["active"] != "active"
        or timer_state["enabled"] not in {"transient", "enabled-runtime"}
    ):
        raise FenceError(
            f"recovery expiry timer is not armed: {timer}={timer_state}"
        )
    reconciler_state = _validated_unit_state(
        host,
        RECOVERY_RECONCILE_SERVICE,
    )
    if reconciler_state["enabled"] != "enabled":
        raise FenceError("boot recovery reconciler is not enabled")
    return {
        "restart_policies": policies,
        "boot_units": unit_proof,
        "expiry_timer": {timer: timer_state},
        "boot_reconciler": {
            RECOVERY_RECONCILE_SERVICE: reconciler_state,
        },
    }


def _require_recovery_owner(
    state: Mapping[str, Any],
    *,
    source_run_id: str,
    run_id: str,
) -> None:
    if not (
        state.get("source_run_id") == source_run_id
        and state.get("run_id") == run_id
        and state.get("recovery_run_id") == run_id
        and run_id in (state.get("recovery_attempts") or [])
    ):
        raise FenceError("canonical fence is not owned by this recovery attempt")


def _reconcile_orphaned_recovery(
    host: Host,
    *,
    source_run_id: str,
    run_id: str,
    state_path: Path,
) -> None:
    state = _load_state(state_path)
    if state.get("phase") == "unsafe_fenced":
        return
    if state.get("source_run_id") != source_run_id:
        raise FenceError("unsafe fence belongs to another source run")
    if state.get("phase") == "restored":
        raise FenceError("restored recovery cannot be replaced")
    deadline = float(state.get("recovery_deadline_epoch") or 0)
    controlled_running = any(
        bool(host.container_info(name).get("State", {}).get("Running"))
        for name in host.volume_container_names()
    )
    if time.time() < deadline and (
        controlled_running
        or state.get("phase") in {"canary_accepted", "finalizing"}
    ):
        raise FenceError("another recovery attempt still owns an active lease")
    quiesce_unsafe(host, run_id=run_id, state_path=state_path)


def recover_unsafe(
    host: Host,
    *,
    source_run_id: str,
    run_id: str,
    image_ref: str,
    revision: str,
    state_path: Path,
    recovery_script_sha256: str = "",
) -> dict[str, Any]:
    """Start one exact admitted fleet in a restart-fenced canary phase."""

    _require_run_id(run_id)
    _reconcile_orphaned_recovery(
        host,
        source_run_id=source_run_id,
        run_id=run_id,
        state_path=state_path,
    )
    state, image_ref, revision = _validate_unsafe_recovery_source(
        host,
        source_run_id=source_run_id,
        image_ref=image_ref,
        revision=revision,
        state_path=state_path,
    )
    attempts = list(state.get("recovery_attempts") or [])
    if run_id in attempts:
        raise FenceError("recovery attempt identity was already used")
    attempts.append(run_id)
    state["source_run_id"] = source_run_id
    state["run_id"] = run_id
    state["recovery_run_id"] = run_id
    state["recovery_attempts"] = attempts
    state["recovery_deadline_epoch"] = time.time() + RECOVERY_LEASE_SECONDS
    if recovery_script_sha256:
        state["recovery_script_sha256"] = recovery_script_sha256
    state["phase"] = "recovery_planned"
    _atomic_json(state_path, state)
    try:
        expiry_unit = _arm_recovery_expiry(
            host,
            source_run_id=source_run_id,
            run_id=run_id,
            state_path=state_path,
        )
        state["recovery_expiry_unit"] = expiry_unit
        state["phase"] = "recovery_starting"
        _atomic_json(state_path, state)
        host.run(
            [
                "docker",
                "compose",
                "--env-file",
                "/etc/tinyassets/env",
                "-f",
                str(RECOVERY_COMPOSE_PATH),
                "-f",
                str(RECOVERY_COMPOSE_OVERRIDE_PATH),
                "up",
                "-d",
            ]
        )
        inspections = _exact_inspections(host)
        state["recovery_restart_policy_proof"] = _set_restart_no(
            host,
            inspections,
        )
        state["phase"] = "recovery_pending_canary"
        _atomic_json(state_path, state)
        evidence: dict[str, Any] | None = None
        last_error = ""
        for attempt in range(30):
            try:
                evidence = prove(
                    host,
                    image_ref=image_ref,
                    revision=revision,
                    run_id=run_id,
                    state_path=state_path,
                )
                break
            except FenceError as exc:
                last_error = str(exc)
                if attempt < 29:
                    time.sleep(2)
        if evidence is None:
            raise FenceError(f"exact fleet did not converge: {last_error}")
        evidence.update(
            {
                "phase": "recovery_pending_canary",
                "source_run_id": source_run_id,
                "recovery_run_id": run_id,
                "recovery_deadline_epoch": state["recovery_deadline_epoch"],
                "restart_policy_proof": state[
                    "recovery_restart_policy_proof"
                ],
            }
        )
        return evidence
    except (FenceError, OSError) as recovery_error:
        try:
            quiesce_unsafe(host, run_id=run_id, state_path=state_path)
        except (FenceError, OSError) as refence_error:
            raise FenceError(
                f"recovery failed: {recovery_error}; "
                f"re-fence also failed: {refence_error}"
            ) from recovery_error
        raise FenceError(
            f"recovery failed and was re-fenced: {recovery_error}"
        ) from recovery_error


def _restore_restart_policies(
    host: Host,
    state: dict[str, Any],
    *,
    state_path: Path,
) -> dict[str, str]:
    proof = dict(state.get("restart_policy_restore_proof") or {})
    for name, policy in state["old_restart_policies"].items():
        info = host.container_info(name)
        identity = str(info.get("Id", ""))
        if not identity:
            raise FenceError(f"container identity is unavailable: {name}")
        host.run(["docker", "update", f"--restart={policy}", identity])
        actual = host.container_restart_policy(identity)
        if actual != policy:
            raise FenceError(
                f"restart policy restoration did not persist: "
                f"{name}={actual}, expected={policy}"
            )
        proof[name] = actual
        state["restart_policy_restore_proof"] = proof
        _atomic_json(state_path, state)
    return proof


def finalize_recovery(
    host: Host,
    *,
    source_run_id: str,
    run_id: str,
    image_ref: str,
    revision: str,
    state_path: Path,
) -> dict[str, Any]:
    """Commit a canary-accepted recovery and restore its saved boot posture."""

    state = _load_state(state_path)
    _require_recovery_owner(
        state,
        source_run_id=source_run_id,
        run_id=run_id,
    )
    if state.get("phase") == "restored":
        return prove(
            host,
            image_ref=image_ref,
            revision=revision,
            run_id=run_id,
            state_path=state_path,
        )
    if state.get("phase") not in {
        "recovery_pending_canary",
        "canary_accepted",
        "finalizing",
    }:
        raise FenceError("recovery is not ready for canary finalization")
    try:
        evidence = prove(
            host,
            image_ref=image_ref,
            revision=revision,
            run_id=run_id,
            state_path=state_path,
        )
        state = _load_state(state_path)
        fence_proof = _prove_recovery_fences(host, state)
        state["pre_finalize_fence_proof"] = fence_proof
        _atomic_json(state_path, state)
        state["canary_accepted_epoch"] = state.get(
            "canary_accepted_epoch"
        ) or time.time()
        state["phase"] = "canary_accepted"
        _atomic_json(state_path, state)
        state["phase"] = "finalizing"
        _atomic_json(state_path, state)
        restart_proof = _restore_restart_policies(
            host,
            state,
            state_path=state_path,
        )
        restored = restore_if_safe(
            host,
            image_ref=image_ref,
            revision=revision,
            run_id=run_id,
            state_path=state_path,
        )
        _cancel_recovery_expiry(
            host,
            str(state.get("recovery_expiry_unit", "")),
        )
        restored.update(
            {
                "source_run_id": source_run_id,
                "recovery_run_id": run_id,
                "canary_accepted_epoch": state["canary_accepted_epoch"],
                "restart_policy_restore_proof": restart_proof,
                "pre_finalize_evidence": evidence,
                "pre_finalize_fence_proof": fence_proof,
            }
        )
        return restored
    except (FenceError, OSError) as finalize_error:
        try:
            quiesce_unsafe(host, run_id=run_id, state_path=state_path)
        except (FenceError, OSError) as refence_error:
            raise FenceError(
                f"recovery finalization failed: {finalize_error}; "
                f"re-fence also failed: {refence_error}"
            ) from finalize_error
        raise FenceError(
            f"recovery finalization failed and was re-fenced: {finalize_error}"
        ) from finalize_error


def refence_recovery(
    host: Host,
    *,
    source_run_id: str,
    run_id: str,
    state_path: Path,
) -> dict[str, Any]:
    """Re-fence only a generation durably owned by this recovery attempt."""

    _require_run_id(source_run_id)
    _require_run_id(run_id)
    state = _load_state(state_path)
    _require_recovery_owner(
        state,
        source_run_id=source_run_id,
        run_id=run_id,
    )
    if state.get("phase") == "restored":
        raise FenceError("restored recovery cannot be re-fenced")
    return quiesce_unsafe(host, run_id=run_id, state_path=state_path)


def reconcile_recovery_on_boot(
    host: Host,
    *,
    state_path: Path,
) -> dict[str, Any]:
    """Automatically close an interrupted recovery after a host reboot."""

    if not state_path.is_file():
        return {"phase": "not_applicable", "safe": True}
    state = _load_state(state_path)
    phase = str(state.get("phase", ""))
    if phase in {"restored", "unsafe_fenced"}:
        return {
            "phase": phase,
            "safe": phase == "restored",
            "writers_fenced": phase == "unsafe_fenced",
        }
    source_run_id = str(state.get("source_run_id", ""))
    run_id = str(state.get("recovery_run_id") or state.get("run_id") or "")
    _require_recovery_owner(
        state,
        source_run_id=source_run_id,
        run_id=run_id,
    )
    return quiesce_unsafe(host, run_id=run_id, state_path=state_path)


def expire_recovery(
    host: Host,
    *,
    source_run_id: str,
    run_id: str,
    state_path: Path,
) -> dict[str, Any]:
    """Re-fence an unaccepted recovery after its durable lease expires."""

    state = _load_state(state_path)
    _require_recovery_owner(
        state,
        source_run_id=source_run_id,
        run_id=run_id,
    )
    if state.get("phase") == "restored":
        return {
            "owner": TASK_OWNER,
            "phase": state.get("phase"),
            "expired": False,
            "safe": True,
        }
    deadline = float(state.get("recovery_deadline_epoch") or 0)
    if time.time() < deadline:
        raise FenceError("recovery lease has not expired")
    evidence = refence_recovery(
        host,
        source_run_id=source_run_id,
        run_id=run_id,
        state_path=state_path,
    )
    evidence["expired"] = True
    return evidence


def _write_optional(path: str | None, payload: Mapping[str, Any]) -> None:
    if path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_json_bytes(payload) + b"\n")


@contextmanager
def _operation_lock(
    path: Path,
    *,
    timeout_seconds: float = LOCK_TIMEOUT_SECONDS,
) -> Iterable[None]:
    """Serialize every host-side fence observation and mutation."""

    if fcntl is None:
        raise FenceError("host operation lock primitive is unavailable")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError as exc:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise FenceError(
                        f"host operation lock timed out after {timeout_seconds:g}s"
                    ) from exc
                time.sleep(min(0.1, remaining))
        yield
    finally:
        if acquired:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--lock-path", type=Path, default=DEFAULT_LOCK_PATH)
    parser.add_argument("--evidence")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "prove", "post-canary", "restore-if-safe"):
        command = subparsers.add_parser(name)
        command.add_argument("--image-ref", required=True)
        command.add_argument("--revision", required=True)
        command.add_argument("--run-id", required=True)
    prepare = subparsers.add_parser("prepare-deploy")
    prepare.add_argument("--image-ref", required=True)
    prepare.add_argument("--run-id", required=True)
    observe = subparsers.add_parser("observe")
    observe.add_argument("--image-ref")
    status = subparsers.add_parser("status")
    status.add_argument("--run-id", required=True)
    quiesce = subparsers.add_parser("quiesce-unsafe")
    quiesce.add_argument("--run-id", required=True)
    recover = subparsers.add_parser("recover-unsafe")
    recover.add_argument("--source-run-id", required=True)
    recover.add_argument("--run-id", required=True)
    recover.add_argument("--image-ref", required=True)
    recover.add_argument("--revision", required=True)
    finalize = subparsers.add_parser("finalize-recovery")
    finalize.add_argument("--source-run-id", required=True)
    finalize.add_argument("--run-id", required=True)
    finalize.add_argument("--image-ref", required=True)
    finalize.add_argument("--revision", required=True)
    refence = subparsers.add_parser("refence-recovery")
    refence.add_argument("--source-run-id", required=True)
    refence.add_argument("--run-id", required=True)
    expire = subparsers.add_parser("expire-recovery")
    expire.add_argument("--source-run-id", required=True)
    expire.add_argument("--run-id", required=True)
    subparsers.add_parser("reconcile-recovery-on-boot")
    guard = subparsers.add_parser("guard-host-mutation")
    guard.add_argument(
        "--command-timeout",
        type=int,
        default=HOST_COMMAND_TIMEOUT_SECONDS,
    )
    guard.add_argument("mutation_argv", nargs=argparse.REMAINDER)
    return parser


def _execute(args: argparse.Namespace, host: Host) -> dict[str, Any]:
    if args.command == "preflight":
        return preflight(
            host,
            image_ref=args.image_ref,
            target_revision=args.revision,
            run_id=args.run_id,
            state_path=args.state_path,
        )
    if args.command == "prepare-deploy":
        return prepare_deploy(
            host,
            image_ref=args.image_ref,
            run_id=args.run_id,
            state_path=args.state_path,
        )
    if args.command == "prove":
        return prove(
            host,
            image_ref=args.image_ref,
            revision=args.revision,
            run_id=args.run_id,
            state_path=args.state_path,
        )
    if args.command == "post-canary":
        return post_canary(
            host,
            image_ref=args.image_ref,
            revision=args.revision,
            run_id=args.run_id,
            state_path=args.state_path,
        )
    if args.command == "restore-if-safe":
        return restore_if_safe(
            host,
            image_ref=args.image_ref,
            revision=args.revision,
            run_id=args.run_id,
            state_path=args.state_path,
        )
    if args.command == "observe":
        return observe_fleet(host, expected_image_ref=args.image_ref)
    if args.command == "quiesce-unsafe":
        return quiesce_unsafe(
            host,
            run_id=args.run_id,
            state_path=args.state_path,
        )
    if args.command == "recover-unsafe":
        recovery_script_sha256 = _prove_recovery_entrypoint()
        return recover_unsafe(
            host,
            source_run_id=args.source_run_id,
            run_id=args.run_id,
            image_ref=args.image_ref,
            revision=args.revision,
            state_path=args.state_path,
            recovery_script_sha256=recovery_script_sha256,
        )
    if args.command == "finalize-recovery":
        return finalize_recovery(
            host,
            source_run_id=args.source_run_id,
            run_id=args.run_id,
            image_ref=args.image_ref,
            revision=args.revision,
            state_path=args.state_path,
        )
    if args.command == "refence-recovery":
        return refence_recovery(
            host,
            source_run_id=args.source_run_id,
            run_id=args.run_id,
            state_path=args.state_path,
        )
    if args.command == "expire-recovery":
        return expire_recovery(
            host,
            source_run_id=args.source_run_id,
            run_id=args.run_id,
            state_path=args.state_path,
        )
    if args.command == "reconcile-recovery-on-boot":
        return reconcile_recovery_on_boot(
            host,
            state_path=args.state_path,
        )
    if args.command == "guard-host-mutation":
        mutation_argv = list(args.mutation_argv)
        separator_present = mutation_argv[:1] == ["--"]
        if separator_present:
            mutation_argv.pop(0)
        if (
            (separator_present and not mutation_argv)
            or args.command_timeout < 1
            or args.command_timeout > 300
        ):
            raise FenceError("guarded host mutation command is invalid")
        guard_evidence = guard_host_mutation(host, state_path=args.state_path)
        if not mutation_argv:
            return {**guard_evidence, "mutation_completed": False}
        output = host.run(
            [
                "timeout",
                "--kill-after=2s",
                f"{args.command_timeout}s",
                *mutation_argv,
            ],
            timeout_seconds=args.command_timeout + 5,
        )
        return {
            **guard_evidence,
            "mutation_completed": True,
            "output_present": bool(output),
        }
    return fence_status(
        host,
        run_id=args.run_id,
        state_path=args.state_path,
    )


def main(argv: Sequence[str] | None = None, *, host: Host | None = None) -> int:
    args = _parser().parse_args(argv)
    host = host or Host()
    try:
        with _operation_lock(args.lock_path):
            result = _execute(args, host)
        _write_optional(args.evidence, result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except FenceError as exc:
        failure = {
            "schema_version": 1,
            "owner": TASK_OWNER,
            "safe": False,
            "error": str(exc),
        }
        if args.state_path.is_file():
            try:
                state = _load_state(args.state_path)
                command_run_id = getattr(args, "run_id", "")
                if state.get("run_id") == command_run_id:
                    failure.update(
                        {
                            "phase": state.get("phase"),
                            "cutover_started": state.get("phase") != "restored",
                            "previous_image_ref": state.get(
                                "previous_image_ref", ""
                            ),
                            "previous_revision": state.get(
                                "previous_revision", ""
                            ),
                            "old_container_ids": state.get(
                                "old_container_ids", {}
                            ),
                        }
                    )
                else:
                    failure["stale_state_ignored"] = True
            except FenceError:
                failure["state_error"] = "durable fence state unreadable"
        _write_optional(args.evidence, failure)
        print(json.dumps(failure, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
