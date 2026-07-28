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
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote

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
TASK_OWNER = "retire-cheat-loop task 2.1"
V1_RISK_STATUSES = frozenset({"pending", "running"})
V2_RISK_STATUSES = frozenset({"pending", "running", "cancel_requested"})
CANONICAL_IMAGE_RE = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]+)?"
    r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+"
    r"@sha256:[0-9a-f]{64}$"
)
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
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
                        "id": str(task.get("task_id") or task.get("id") or ""),
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
                placeholders = ",".join("?" for _ in V2_RISK_STATUSES)
                rows = connection.execute(
                    "SELECT bt.branch_task_id,bt.status "
                    "FROM branch_tasks_v2 AS bt "
                    "JOIN user_requests AS ur ON ur.request_id=bt.request_id "
                    "WHERE ur.request_type=? "
                    f"AND bt.status IN ({placeholders}) "
                    "ORDER BY bt.branch_task_id",
                    ("bug_investigation", *sorted(V2_RISK_STATUSES)),
                )
                for row in rows:
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
    ) -> str:
        result = subprocess.run(
            args,
            input=input_text,
            text=True,
            capture_output=True,
        )
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

    def unit_state(self, unit: str) -> dict[str, str]:
        return {
            "active": self.run(["systemctl", "is-active", unit], check=False),
            "enabled": self.run(["systemctl", "is-enabled", unit], check=False),
        }


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
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _load_state(path: Path) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FenceError("durable stop-writer fence state is unavailable") from exc
    if state.get("owner") != TASK_OWNER or state.get("schema_version") != 1:
        raise FenceError("durable stop-writer fence state is invalid")
    return state


def _exact_inspections(host: Host) -> dict[str, dict[str, Any]]:
    return {name: host.container_info(name) for name in EXPECTED_CONTAINERS}


def _stray_writer_processes(
    receipt_path: Path,
    excluded_pids: set[int],
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
                except OSError:
                    continue
                if target in receipt_related:
                    receipt_fd = True
                    break
            server_like = any(
                marker in cmdline
                for marker in (
                    "tinyassets.universe_server",
                    "tinyassets.daemon_server",
                    "claude-plugin",
                    "mcpb",
                )
            )
            if receipt_fd or server_like:
                risks.append(
                    {
                        "pid": pid,
                        "exe": exe,
                        "receipt_fd": receipt_fd,
                        "server_like": server_like,
                    }
                )
        except (FileNotFoundError, PermissionError, ProcessLookupError):
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
    state_path: Path,
) -> dict[str, Any]:
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
    if set(host.volume_container_names()) != set(EXPECTED_CONTAINERS):
        raise FenceError("stray container is attached to the production volume")
    old_image_ref, old_revision = _old_identity(host, inspections)
    old_ids = {name: str(info.get("Id", "")) for name, info in inspections.items()}
    old_pids = host.container_pids(EXPECTED_CONTAINERS)
    preliminary_risk = inventory_queue_risk(volume_dir)
    preliminary_processes = _stray_writer_processes(receipt.host_path, old_pids)
    preliminary_snapshot = receipt_snapshot(receipt.host_path)
    if preliminary_risk:
        raise FenceError("pre-mutation bug_investigation queue risk is nonzero")
    if preliminary_processes:
        raise FenceError("pre-mutation stray writer process risk is nonzero")

    state: dict[str, Any] = {
        "schema_version": 1,
        "owner": TASK_OWNER,
        "phase": "planned",
        "target_image_ref": image_ref,
        "target_revision": target_revision,
        "previous_image_ref": old_image_ref,
        "previous_revision": old_revision,
        "volume_mountpoint": str(volume_dir),
        "receipt_container_path": receipt.container_path,
        "receipt_host_path": str(receipt.host_path),
        "old_container_ids": old_ids,
        "restart_racer_state": {
            unit: host.unit_state(unit) for unit in RESTART_RACER_UNITS
        },
        "daemon_service_state": host.unit_state(DAEMON_SERVICE),
        "old_restart_policies": {
            name: str(info.get("HostConfig", {}).get("RestartPolicy", {}).get("Name", ""))
            for name, info in inspections.items()
        },
        "preliminary_receipt_snapshot": preliminary_snapshot,
    }
    _atomic_json(state_path, state)

    # Reboot-stable fence: disable timer activation persistently and make the
    # old containers restart=no before stopping the daemon unit. Runtime masks
    # additionally reject direct starts during the cutover.
    timer_units = [unit for unit in RESTART_RACER_UNITS if unit.endswith(".timer")]
    host.run(["systemctl", "disable", "--now", *timer_units], check=False)
    host.run(["systemctl", "stop", *RESTART_RACER_UNITS], check=False)
    host.run(["systemctl", "mask", "--runtime", *RESTART_RACER_UNITS])
    host.run(["systemctl", "disable", DAEMON_SERVICE], check=False)
    host.run(["systemctl", "mask", "--runtime", DAEMON_SERVICE])
    for name in EXPECTED_CONTAINERS:
        host.run(["docker", "update", "--restart=no", name])
    host.run(["systemctl", "stop", DAEMON_SERVICE], check=False)
    host.run(["docker", "stop", *EXPECTED_CONTAINERS], check=False)

    state["phase"] = "quiesced"
    _atomic_json(state_path, state)
    old_still_running = []
    for name, old_id in old_ids.items():
        running = host.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", old_id],
            check=False,
        )
        if running == "true":
            old_still_running.append({"container": name, "id": old_id})
    final_risk = inventory_queue_risk(volume_dir)
    final_processes = _stray_writer_processes(receipt.host_path, set())
    final_snapshot = receipt_snapshot(receipt.host_path)
    if old_still_running:
        raise FenceError("old container still running after quiescence")
    if final_risk:
        raise FenceError("post-quiesce bug_investigation queue risk is nonzero")
    if final_processes:
        raise FenceError("post-quiesce stray writer process risk is nonzero")
    if final_snapshot != preliminary_snapshot:
        raise FenceError("receipt snapshot changed during writer quiescence")
    state["receipt_snapshot"] = final_snapshot
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
    state_path: Path,
) -> dict[str, Any]:
    state = _load_state(state_path)
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
        if host.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", old_id],
            check=False,
        ) == "true":
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
    state_path: Path,
) -> dict[str, Any]:
    state = _load_state(state_path)
    if state.get("phase") not in {
        "target_installed",
        "safe_fleet",
        "post_canary_proved",
        "restored",
    }:
        raise FenceError("target was not prepared under the stop-writer fence")
    observation = observe_fleet(host, expected_image_ref=image_ref)
    old_ids = state.get("old_container_ids", {})
    old_running = []
    for name, old_id in old_ids.items():
        if host.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", old_id],
            check=False,
        ) == "true":
            old_running.append({"container": name, "id": old_id})
    observation["old_container_ids_running"] = old_running
    if not safe_fleet_matches(observation, image_ref, revision, old_ids):
        raise FenceError(
            "exactly five safe target containers were not independently proved"
        )
    if observation["receipt_snapshot"] != state.get("receipt_snapshot"):
        raise FenceError("post-deploy receipt snapshot mismatch")
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
    state_path: Path,
) -> dict[str, Any]:
    evidence = prove(
        host,
        image_ref=image_ref,
        revision=revision,
        state_path=state_path,
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
        if host.unit_state(unit)["enabled"] in {"masked", "masked-runtime"}
    ]


def fence_status(host: Host, *, state_path: Path) -> dict[str, Any]:
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
        "state_error": state_error,
        "masked_units": _masked_units(host),
    }


def restore_if_safe(
    host: Host,
    *,
    image_ref: str,
    revision: str,
    state_path: Path,
) -> dict[str, Any]:
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
    evidence = prove(
        host,
        image_ref=image_ref,
        revision=revision,
        state_path=state_path,
    )
    host.run(
        [
            "systemctl",
            "unmask",
            "--runtime",
            *RESTART_RACER_UNITS,
            DAEMON_SERVICE,
        ],
        check=False,
    )
    racer_state = state.get("restart_racer_state", {})
    for unit in RESTART_RACER_UNITS:
        prior = racer_state.get(unit, {})
        if prior.get("enabled") == "enabled":
            host.run(["systemctl", "enable", unit], check=False)
        if unit.endswith(".timer") and prior.get("active") == "active":
            host.run(["systemctl", "start", unit])
    daemon_state = state.get("daemon_service_state", {})
    if daemon_state.get("enabled") == "enabled":
        host.run(["systemctl", "enable", DAEMON_SERVICE], check=False)
    state["phase"] = "restored"
    _atomic_json(state_path, state)
    evidence.update(
        {
            "phase": "restored",
            "masked_units_before": masked_before,
            "masked_units_after": _masked_units(host),
        }
    )
    return evidence


def _write_optional(path: str | None, payload: Mapping[str, Any]) -> None:
    if path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(_json_bytes(payload) + b"\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-path", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--evidence")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "prove", "post-canary", "restore-if-safe"):
        command = subparsers.add_parser(name)
        command.add_argument("--image-ref", required=True)
        command.add_argument("--revision", required=True)
    prepare = subparsers.add_parser("prepare-deploy")
    prepare.add_argument("--image-ref", required=True)
    observe = subparsers.add_parser("observe")
    observe.add_argument("--image-ref")
    subparsers.add_parser("status")
    return parser


def main(argv: Sequence[str] | None = None, *, host: Host | None = None) -> int:
    args = _parser().parse_args(argv)
    host = host or Host()
    try:
        if args.command == "preflight":
            result = preflight(
                host,
                image_ref=args.image_ref,
                target_revision=args.revision,
                state_path=args.state_path,
            )
        elif args.command == "prepare-deploy":
            result = prepare_deploy(
                host,
                image_ref=args.image_ref,
                state_path=args.state_path,
            )
        elif args.command == "prove":
            result = prove(
                host,
                image_ref=args.image_ref,
                revision=args.revision,
                state_path=args.state_path,
            )
        elif args.command == "post-canary":
            result = post_canary(
                host,
                image_ref=args.image_ref,
                revision=args.revision,
                state_path=args.state_path,
            )
        elif args.command == "restore-if-safe":
            result = restore_if_safe(
                host,
                image_ref=args.image_ref,
                revision=args.revision,
                state_path=args.state_path,
            )
        elif args.command == "observe":
            result = observe_fleet(host, expected_image_ref=args.image_ref)
        else:
            result = fence_status(host, state_path=args.state_path)
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
                failure.update(
                    {
                        "phase": state.get("phase"),
                        "cutover_started": state.get("phase")
                        in {
                            "planned",
                            "quiesced",
                            "preflight_proved",
                            "target_installed",
                            "safe_fleet",
                            "post_canary_proved",
                            "restored",
                        },
                        "previous_image_ref": state.get("previous_image_ref", ""),
                        "previous_revision": state.get("previous_revision", ""),
                        "old_container_ids": state.get("old_container_ids", {}),
                    }
                )
            except FenceError:
                failure["state_error"] = "durable fence state unreadable"
        _write_optional(args.evidence, failure)
        print(json.dumps(failure, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
