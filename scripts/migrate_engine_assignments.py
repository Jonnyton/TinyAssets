#!/usr/bin/env python3
"""Offline, reviewed migration for historical engine assignments.

This command intentionally does not use TinyAssets' runtime config or ledger
loaders.  Those loaders have compatibility/fail-soft behavior that is unsafe at
an offline migration fence.  Inventory parses the raw files strictly, binds its
decision manifest to their SHA-256 digests, and apply re-checks every decision
while holding all per-universe assignment locks before writing anything.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import errno
import hashlib
import json
import math
import os
import stat
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import yaml

SCHEMA_VERSION = 1
FENCE_VERSION = 1
MARKER_FILENAME = ".engine-assignment-migration-v1.json"
JOURNAL_FILENAME = ".engine-assignment-migration-transaction-v1.json"
LOCK_FILENAME = ".engine-assignment.lock"
ASSIGNMENT_FILES = (
    "config.yaml",
    ".credential-vault.json",
    "ledger.json",
)
UNIVERSE_ARTIFACT_FILENAMES = ASSIGNMENT_FILES + (
    "soul.md",
    "PROGRAM.md",
    "status.json",
)
TOP_LEVEL_OPERATIONAL_DIRS = frozenset({"lance", "output", "runs", "wiki"})
CANONICAL_PROVIDER_BY_SERVICE = {
    "anthropic": "claude-code",
    "openai": "codex",
}
INCOMPLETE_SOURCES = {
    "self_hosted_endpoint",
    "market_rented",
    "host_daemon",
}


class MigrationError(Exception):
    """A sanitized command error with a stable process exit status."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class StateProblem(Exception):
    """A sanitized per-universe raw-state failure."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class _NoDuplicateSafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _NoDuplicateSafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    if any(
        key_node.tag == "tag:yaml.org,2002:merge" or key_node.value == "<<"
        for key_node, _value_node in node.value
    ):
        raise StateProblem("config_merge_key")
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            if key in result:
                raise StateProblem("duplicate_config_key")
        except TypeError as exc:
            raise StateProblem("invalid_config_key") from exc
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_NoDuplicateSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _json_object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StateProblem("duplicate_json_key")
        result[key] = value
    return result


def _reject_json_constant(_value: str) -> None:
    raise StateProblem("non_finite_json_number")


def _parse_json(raw: bytes, reason_prefix: str) -> Any:
    try:
        text = raw.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=_json_object_without_duplicates,
            parse_constant=_reject_json_constant,
        )
    except StateProblem:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateProblem(f"invalid_{reason_prefix}_json") from exc


def _parse_config(raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
        for event in yaml.parse(text, Loader=yaml.SafeLoader):
            if isinstance(event, yaml.AliasEvent) or getattr(event, "anchor", None):
                raise StateProblem("config_anchor")
        value = yaml.load(text, Loader=_NoDuplicateSafeLoader)
    except StateProblem:
        raise
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise StateProblem("invalid_config_yaml") from exc
    if not isinstance(value, dict):
        raise StateProblem("invalid_config_root")
    if any(not isinstance(key, str) for key in value):
        raise StateProblem("invalid_config_key")
    return value


def _parse_vault(raw: bytes) -> list[dict[str, Any]]:
    value = _parse_json(raw, "vault")
    if isinstance(value, list):
        records = value
    elif isinstance(value, dict):
        if "schema_version" in value and value["schema_version"] != 1:
            raise StateProblem("unsupported_vault_schema")
        if "credentials" not in value:
            raise StateProblem("invalid_vault_records")
        records = value["credentials"]
    else:
        raise StateProblem("invalid_vault_root")
    if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
        raise StateProblem("invalid_vault_records")
    return records


def _parse_ledger(raw: bytes) -> list[dict[str, Any]]:
    value = _parse_json(raw, "ledger")
    if not isinstance(value, list) or any(not isinstance(record, dict) for record in value):
        raise StateProblem("invalid_ledger_root")
    return value


def _same_path(left: Path, right: Path) -> bool:
    left_value = os.path.normcase(os.path.normpath(str(left)))
    right_value = os.path.normcase(os.path.normpath(str(right)))
    return left_value == right_value


def _opened_file_metadata(fd: int) -> os.stat_result:
    return os.fstat(fd)


def _validated_data_dir(value: str | Path) -> Path:
    path = Path(value).absolute()
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise MigrationError("data directory is unavailable", 2) from exc
    if stat.S_ISLNK(metadata.st_mode):
        raise MigrationError("data directory may not be a symlink", 2)
    if not stat.S_ISDIR(metadata.st_mode):
        raise MigrationError("data directory is not a directory", 2)
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise MigrationError("data directory cannot be resolved", 2) from exc


def _validated_manifest_path(
    data_dir: Path,
    value: str | Path,
    *,
    exit_code: int,
) -> Path:
    path = Path(value).absolute()
    try:
        parent_metadata = path.parent.lstat()
        if not stat.S_ISDIR(parent_metadata.st_mode):
            raise MigrationError("manifest parent is not a directory", exit_code)
        parent = path.parent.resolve(strict=True)
    except MigrationError:
        raise
    except OSError as exc:
        raise MigrationError("manifest parent is unavailable", exit_code) from exc

    candidate = parent / path.name
    try:
        candidate.relative_to(data_dir)
    except ValueError:
        pass
    else:
        raise MigrationError("manifest must live outside the data directory", exit_code)

    try:
        metadata = candidate.lstat()
    except FileNotFoundError:
        return candidate
    except OSError as exc:
        raise MigrationError("manifest path is unavailable", exit_code) from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        raise MigrationError("manifest path must be one regular file", exit_code)
    return candidate


def _safe_read_optional(universe: Path, filename: str) -> bytes | None:
    path = universe / filename
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise StateProblem(f"unreadable_{_reason_name(filename)}") from exc

    reason_name = _reason_name(filename)
    if stat.S_ISLNK(metadata.st_mode):
        raise StateProblem(f"symlink_{reason_name}")
    if not stat.S_ISREG(metadata.st_mode):
        raise StateProblem(f"nonregular_{reason_name}")
    if metadata.st_nlink != 1:
        raise StateProblem(f"hardlink_{reason_name}")
    try:
        resolved = path.resolve(strict=True)
        universe_resolved = universe.resolve(strict=True)
    except OSError as exc:
        raise StateProblem(f"unresolvable_{reason_name}") from exc
    if not _same_path(resolved.parent, universe_resolved):
        raise StateProblem(f"path_escape_{reason_name}")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.EMLINK}:
            raise StateProblem(f"symlink_{reason_name}") from exc
        raise StateProblem(f"unreadable_{reason_name}") from exc
    try:
        opened = _opened_file_metadata(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise StateProblem(f"nonregular_{reason_name}")
        if opened.st_nlink != 1:
            raise StateProblem(f"hardlink_{reason_name}")
        if (metadata.st_dev, metadata.st_ino) != (opened.st_dev, opened.st_ino):
            raise StateProblem(f"raced_{reason_name}")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            return handle.read()
    except OSError as exc:
        raise StateProblem(f"unreadable_{reason_name}") from exc
    finally:
        if fd >= 0:
            os.close(fd)


def _reason_name(filename: str) -> str:
    return {
        "config.yaml": "config",
        ".credential-vault.json": "vault",
        "ledger.json": "ledger",
    }[filename]


def _raw_hash(raw: bytes | None) -> str | None:
    if raw is None:
        return None
    return hashlib.sha256(raw).hexdigest()


def _usable_secret(record: dict[str, Any]) -> bool:
    for key in ("api_key", "key", "token"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return True
    encoded = record.get("token_b64") or record.get("secret_b64")
    if not isinstance(encoded, str) or not encoded.strip():
        return False
    try:
        decoded = base64.b64decode(encoded.strip(), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    return bool(decoded.strip())


def _latest_successful_set_engine(
    ledger: list[dict[str, Any]],
) -> dict[str, Any] | None:
    successful: list[dict[str, Any]] = []
    for record in ledger:
        if record.get("action") != "set_engine":
            continue
        payload = record.get("payload")
        if isinstance(payload, dict) and payload.get("status") == "engine_set":
            successful.append(payload)
    return successful[-1] if successful else None


def _decision_for_candidate(
    config: dict[str, Any],
    vault: list[dict[str, Any]],
    ledger: list[dict[str, Any]],
) -> tuple[str, dict[str, Any], list[str]]:
    source = config.get("engine_source")
    reasons: list[str] = []

    if source in INCOMPLETE_SOURCES:
        reasons.append("incomplete_engine_source")
    elif source != "byo_api_key":
        reasons.append(
            "missing_explicit_engine_source" if source is None else "unsupported_engine_source"
        )

    key_records = [record for record in vault if record.get("credential_type") == "llm_api_key"]
    provider: str | None = None
    service: str | None = None
    if not key_records:
        reasons.append("missing_engine_credentials")
    else:
        services: list[str] = []
        providers: set[str] = set()
        for record in key_records:
            raw_service = record.get("service")
            if not isinstance(raw_service, str) or raw_service not in (
                CANONICAL_PROVIDER_BY_SERVICE
            ):
                reasons.append("noncanonical_key_service")
                continue
            services.append(raw_service)
            providers.add(CANONICAL_PROVIDER_BY_SERVICE[raw_service])
            if not _usable_secret(record):
                reasons.append("unusable_key_record")
        if len(providers) > 1:
            reasons.append("multiple_key_providers")
        if len(providers) == 1 and len(services) == len(key_records):
            provider = next(iter(providers))
            service = services[0]

    if provider is not None:
        if config.get("preferred_writer") != provider:
            reasons.append("preferred_writer_mismatch")
        latest = _latest_successful_set_engine(ledger)
        if latest is None:
            reasons.append("missing_set_engine_ledger")
        elif not (
            latest.get("engine_source") == "byo_api_key"
            and latest.get("service") == service
            and latest.get("preferred_writer") == provider
        ):
            reasons.append("ledger_mismatch")
    elif any(record.get("action") == "set_engine" for record in ledger):
        if _latest_successful_set_engine(ledger) is None:
            reasons.append("missing_set_engine_ledger")

    state_is_explicit = "engine_assignment_state" in config
    ceiling_is_explicit = "allowed_providers" in config
    if state_is_explicit or ceiling_is_explicit:
        state = config.get("engine_assignment_state")
        ceiling = config.get("allowed_providers")
        explicit_singleton_is_valid = (
            state == "ready" and provider is not None and ceiling == [provider]
        )
        if not explicit_singleton_is_valid and not reasons:
            # Use one stable reason for every explicit hold.  After apply,
            # invalid/pending state becomes ready+[]; that transition must not
            # change the reviewed decision or widen the empty ceiling.
            reasons.append("explicit_assignment_hold")

    reasons = sorted(set(reasons))
    confirmed = source == "byo_api_key" and provider is not None and not reasons
    if confirmed:
        return (
            "confirmed_byo",
            {
                "engine_assignment_state": "ready",
                "allowed_providers": [provider],
            },
            [],
        )
    return (
        "hold",
        {"engine_assignment_state": "ready", "allowed_providers": []},
        reasons,
    )


def _fatal_entry(
    universe_id: str,
    raw_by_name: dict[str, bytes | None],
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "universe_id": universe_id,
        "classification": "fatal",
        "target": None,
        "reason_codes": sorted(set(reasons)),
        "needs_migration": True,
        "raw_sha256": {name: _raw_hash(raw_by_name.get(name)) for name in ASSIGNMENT_FILES},
    }


def _inspect_universe(
    universe: Path,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    raw_by_name: dict[str, bytes | None] = {}
    reasons: list[str] = []
    for filename in ASSIGNMENT_FILES:
        try:
            raw_by_name[filename] = _safe_read_optional(universe, filename)
        except StateProblem as exc:
            raw_by_name[filename] = None
            reasons.append(exc.reason_code)

    config: dict[str, Any] = {}
    vault: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    if not reasons:
        try:
            if raw_by_name["config.yaml"] is not None:
                config = _parse_config(raw_by_name["config.yaml"] or b"")
            if raw_by_name[".credential-vault.json"] is not None:
                vault = _parse_vault(raw_by_name[".credential-vault.json"] or b"")
            if raw_by_name["ledger.json"] is not None:
                ledger = _parse_ledger(raw_by_name["ledger.json"] or b"")
        except StateProblem as exc:
            reasons.append(exc.reason_code)

    if reasons:
        return _fatal_entry(universe.name, raw_by_name, reasons), None

    key_records = [record for record in vault if record.get("credential_type") == "llm_api_key"]
    has_set_engine = any(record.get("action") == "set_engine" for record in ledger)
    has_explicit_state = any(key in config for key in ("engine_source", "engine_assignment_state"))
    if not (has_explicit_state or key_records or has_set_engine):
        return None, None

    classification, target, reason_codes = _decision_for_candidate(config, vault, ledger)
    needs_migration = not (
        config.get("engine_assignment_state") == target["engine_assignment_state"]
        and config.get("allowed_providers") == target["allowed_providers"]
    )
    entry = {
        "universe_id": universe.name,
        "classification": classification,
        "target": target,
        "reason_codes": reason_codes,
        "needs_migration": needs_migration,
        "raw_sha256": {name: _raw_hash(raw_by_name[name]) for name in ASSIGNMENT_FILES},
    }
    return entry, config


def _scan_data(data_dir: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    configs: dict[str, dict[str, Any]] = {}
    lock_universe_ids: list[str] = []
    try:
        children = sorted(data_dir.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise MigrationError("data directory cannot be listed", 2) from exc

    for child in children:
        if child.name.startswith(".") or child.name in TOP_LEVEL_OPERATIONAL_DIRS:
            continue
        try:
            metadata = child.lstat()
        except OSError:
            entries.append(_fatal_entry(child.name, {}, ["unreadable_universe_path"]))
            continue
        if stat.S_ISLNK(metadata.st_mode):
            entries.append(_fatal_entry(child.name, {}, ["symlink_universe_path"]))
            continue
        if not stat.S_ISDIR(metadata.st_mode):
            continue
        try:
            resolved = child.resolve(strict=True)
        except OSError:
            entries.append(_fatal_entry(child.name, {}, ["unresolvable_universe_path"]))
            continue
        if not _same_path(resolved.parent, data_dir):
            entries.append(_fatal_entry(child.name, {}, ["path_escape_universe_path"]))
            continue
        if not any(os.path.lexists(resolved / name) for name in UNIVERSE_ARTIFACT_FILENAMES):
            continue
        lock_universe_ids.append(child.name)
        entry, config = _inspect_universe(resolved)
        if entry is not None:
            entries.append(entry)
            if config is not None:
                configs[child.name] = config

    fatal_count = sum(entry["classification"] == "fatal" for entry in entries)
    needs_count = sum(
        entry["classification"] != "fatal" and entry["needs_migration"] for entry in entries
    )
    return {
        "entries": entries,
        "configs": configs,
        "lock_universe_ids": lock_universe_ids,
        "summary": {
            "candidate_count": len(entries),
            "fatal_count": fatal_count,
            "needs_migration_count": needs_count,
        },
    }


def _manifest_for_scan(scan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "fence_version": FENCE_VERSION,
        "review": {"approved": False, "reviewer": "", "reviewed_at": ""},
        "summary": scan["summary"],
        "universes": scan["entries"],
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        # Windows does not expose a portable directory fsync. os.replace is
        # still atomic; production fence execution is the Linux image.
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(directory, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_bytes_atomic(
    path: Path,
    content: bytes,
    *,
    prefix: str,
    suffix: str = ".tmp",
    mode: int | None = None,
    owner: tuple[int, int] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OSError("refusing to replace a symlink")
    fd, temporary_name = tempfile.mkstemp(dir=str(path.parent), prefix=prefix, suffix=suffix)
    temporary = Path(temporary_name)
    try:
        if owner is not None and os.name != "nt":
            os.fchown(fd, owner[0], owner[1])
        if mode is not None:
            if os.name == "nt":
                os.chmod(temporary, mode)
            else:
                os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if fd >= 0:
            os.close(fd)
        temporary.unlink(missing_ok=True)


def _write_json_atomic(path: Path, value: Any) -> None:
    _write_bytes_atomic(path, _json_bytes(value), prefix=f".{path.name}.")


def _config_bytes(data: dict[str, Any]) -> bytes:
    return yaml.safe_dump(
        data,
        default_flow_style=False,
        sort_keys=False,
    ).encode("utf-8")


def _write_config_atomic(path: Path, data: dict[str, Any]) -> None:
    """Durably replace one config while leaving no failed-write temp behind."""
    content = _config_bytes(data)
    mode = 0o600
    owner: tuple[int, int] | None = None
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        pass
    else:
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise OSError("refusing to replace a non-regular config")
        mode = stat.S_IMODE(metadata.st_mode)
        owner = (metadata.st_uid, metadata.st_gid)
    _write_bytes_atomic(
        path,
        content,
        prefix=".config.",
        mode=mode,
        owner=owner,
    )


def _config_snapshot(path: Path) -> tuple[bytes | None, int, tuple[int, int] | None]:
    raw = _safe_read_optional(path.parent, path.name)
    if raw is None:
        return None, 0o600, None
    metadata = path.lstat()
    return raw, stat.S_IMODE(metadata.st_mode), (metadata.st_uid, metadata.st_gid)


def _unlink_regular_file_durable(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        raise OSError("refusing to remove a non-regular or multiply-linked file")
    path.unlink()
    _fsync_directory(path.parent)


def _restore_config_snapshot(
    path: Path,
    snapshot: tuple[bytes | None, int, tuple[int, int] | None],
) -> None:
    raw, mode, owner = snapshot
    if raw is None:
        _unlink_regular_file_durable(path)
        return
    _write_bytes_atomic(
        path,
        raw,
        prefix=".config.rollback.",
        mode=mode,
        owner=owner,
    )


def _read_strict_json_file(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise MigrationError(f"{label} may not be a symlink", 4)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise MigrationError(f"{label} must be one regular unlinked file", 4)
        raw = path.read_bytes()
    except MigrationError:
        raise
    except OSError as exc:
        raise MigrationError(f"{label} is unavailable", 4) from exc
    try:
        value = _parse_json(raw, label.replace(" ", "_"))
    except StateProblem as exc:
        raise MigrationError(f"{label} is not strict JSON", 4) from exc
    if not isinstance(value, dict):
        raise MigrationError(f"{label} root must be an object", 4)
    return value, raw


def _validate_review(manifest: dict[str, Any]) -> None:
    review = manifest.get("review")
    if not isinstance(review, dict) or set(review) != {
        "approved",
        "reviewer",
        "reviewed_at",
    }:
        raise MigrationError("manifest review metadata is incomplete", 3)
    if review.get("approved") is not True:
        raise MigrationError("manifest review is not explicitly approved", 3)
    reviewer = review.get("reviewer")
    reviewed_at = review.get("reviewed_at")
    if (
        not isinstance(reviewer, str)
        or not reviewer.strip()
        or len(reviewer) > 200
        or not isinstance(reviewed_at, str)
        or not reviewed_at.strip()
        or len(reviewed_at) > 100
    ):
        raise MigrationError("manifest review metadata is incomplete", 3)
    try:
        parsed_reviewed_at = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MigrationError("manifest review timestamp is invalid", 3) from exc
    if parsed_reviewed_at.tzinfo is None:
        raise MigrationError("manifest review timestamp requires a timezone", 3)


def _validate_manifest_shape(manifest: dict[str, Any]) -> None:
    expected_keys = {
        "schema_version",
        "fence_version",
        "review",
        "summary",
        "universes",
    }
    if set(manifest) != expected_keys:
        raise MigrationError("manifest is incomplete or has unexpected fields", 4)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise MigrationError("manifest schema version is unsupported", 4)
    if manifest.get("fence_version") != FENCE_VERSION:
        raise MigrationError("manifest fence version is unsupported", 4)
    universes = manifest.get("universes")
    if not isinstance(universes, list) or any(not isinstance(entry, dict) for entry in universes):
        raise MigrationError("manifest universes are invalid", 4)
    ids = [entry.get("universe_id") for entry in universes]
    if any(not isinstance(universe_id, str) or not universe_id for universe_id in ids):
        raise MigrationError("manifest universe id is invalid", 4)
    if len(ids) != len(set(ids)):
        raise MigrationError("manifest contains duplicate universe entries", 4)


def _manifest_matches_scan(manifest: dict[str, Any], scan: dict[str, Any]) -> bool:
    return (
        manifest.get("summary") == scan["summary"] and manifest.get("universes") == scan["entries"]
    )


def _decisions(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "universe_id": entry["universe_id"],
            "classification": entry["classification"],
            "target": entry["target"],
            "reason_codes": entry["reason_codes"],
        }
        for entry in entries
    ]


def _marker_for_manifest(
    manifest: dict[str, Any], manifest_raw: bytes, scan: dict[str, Any]
) -> dict[str, Any]:
    review = manifest["review"]
    return {
        "schema_version": SCHEMA_VERSION,
        "fence_version": FENCE_VERSION,
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "review": {
            "reviewer": review["reviewer"],
            "reviewed_at": review["reviewed_at"],
        },
        "universes": _decisions(scan["entries"]),
    }


def _validate_marker(marker: dict[str, Any]) -> None:
    if set(marker) != {
        "schema_version",
        "fence_version",
        "manifest_sha256",
        "review",
        "universes",
    }:
        raise MigrationError("migration marker is invalid", 4)
    if (
        marker.get("schema_version") != SCHEMA_VERSION
        or marker.get("fence_version") != FENCE_VERSION
    ):
        raise MigrationError("migration marker version is invalid", 4)
    digest = marker.get("manifest_sha256")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise MigrationError("migration marker digest is invalid", 4)
    review = marker.get("review")
    if (
        not isinstance(review, dict)
        or set(review) != {"reviewer", "reviewed_at"}
        or not isinstance(review.get("reviewer"), str)
        or not review["reviewer"].strip()
        or not isinstance(review.get("reviewed_at"), str)
        or not review["reviewed_at"].strip()
    ):
        raise MigrationError("migration marker review is invalid", 4)
    try:
        marker_reviewed_at = datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise MigrationError("migration marker review is invalid", 4) from exc
    if marker_reviewed_at.tzinfo is None:
        raise MigrationError("migration marker review is invalid", 4)
    universes = marker.get("universes")
    if not isinstance(universes, list) or any(
        not isinstance(entry, dict)
        or set(entry) != {"universe_id", "classification", "target", "reason_codes"}
        for entry in universes
    ):
        raise MigrationError("migration marker decisions are invalid", 4)
    universe_ids = [entry["universe_id"] for entry in universes]
    if any(
        not isinstance(universe_id, str) or not universe_id for universe_id in universe_ids
    ) or len(universe_ids) != len(set(universe_ids)):
        raise MigrationError("migration marker decisions are invalid", 4)


def _marker_matches(marker: dict[str, Any], manifest_raw: bytes, scan: dict[str, Any]) -> bool:
    return (
        marker["manifest_sha256"] == hashlib.sha256(manifest_raw).hexdigest()
        and marker["universes"] == _decisions(scan["entries"])
        and scan["summary"]["fatal_count"] == 0
        and scan["summary"]["needs_migration_count"] == 0
    )


def _valid_sha256(value: Any, *, nullable: bool = False) -> bool:
    if nullable and value is None:
        return True
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _journal_for_transaction(
    manifest_raw: bytes,
    universe_ids: list[str],
    prepared: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "fence_version": FENCE_VERSION,
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "universe_ids": list(universe_ids),
        "configs": [
            {
                "universe_id": universe_id,
                "before_config_sha256": _raw_hash(prepared[universe_id]["snapshot"][0]),
                "after_config_sha256": prepared[universe_id]["after_sha256"],
            }
            for universe_id in sorted(prepared)
        ],
    }


def _validate_journal(journal: dict[str, Any]) -> None:
    if set(journal) != {
        "schema_version",
        "fence_version",
        "manifest_sha256",
        "universe_ids",
        "configs",
    }:
        raise MigrationError("transaction journal is invalid", 4)
    if (
        journal.get("schema_version") != SCHEMA_VERSION
        or journal.get("fence_version") != FENCE_VERSION
        or not _valid_sha256(journal.get("manifest_sha256"))
    ):
        raise MigrationError("transaction journal version or digest is invalid", 4)
    universe_ids = journal.get("universe_ids")
    if (
        not isinstance(universe_ids, list)
        or any(not isinstance(value, str) or not value for value in universe_ids)
        or universe_ids != sorted(universe_ids)
        or len(universe_ids) != len(set(universe_ids))
    ):
        raise MigrationError("transaction journal universe ids are invalid", 4)
    configs = journal.get("configs")
    if not isinstance(configs, list) or any(
        not isinstance(record, dict)
        or set(record)
        != {
            "universe_id",
            "before_config_sha256",
            "after_config_sha256",
        }
        for record in configs
    ):
        raise MigrationError("transaction journal config records are invalid", 4)
    config_ids = [record["universe_id"] for record in configs]
    if (
        any(universe_id not in universe_ids for universe_id in config_ids)
        or config_ids != sorted(config_ids)
        or len(config_ids) != len(set(config_ids))
        or any(
            not _valid_sha256(record["before_config_sha256"], nullable=True)
            or not _valid_sha256(record["after_config_sha256"])
            for record in configs
        )
    ):
        raise MigrationError("transaction journal config records are invalid", 4)


def _recovery_identity(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "universe_id": entry["universe_id"],
        "classification": entry["classification"],
        "target": entry["target"],
        "reason_codes": entry["reason_codes"],
        "vault_sha256": entry["raw_sha256"][".credential-vault.json"],
        "ledger_sha256": entry["raw_sha256"]["ledger.json"],
    }


def _scan_matches_recovery_transaction(
    manifest: dict[str, Any],
    scan: dict[str, Any],
    journal: dict[str, Any],
) -> bool:
    if scan["summary"]["fatal_count"] or scan["lock_universe_ids"] != journal["universe_ids"]:
        return False
    manifest_entries = {entry["universe_id"]: entry for entry in manifest["universes"]}
    current_entries = {entry["universe_id"]: entry for entry in scan["entries"]}
    if set(current_entries) != set(manifest_entries):
        return False
    journal_configs = {record["universe_id"]: record for record in journal["configs"]}
    for universe_id, manifest_entry in manifest_entries.items():
        current_entry = current_entries[universe_id]
        if _recovery_identity(current_entry) != _recovery_identity(manifest_entry):
            return False
        record = journal_configs.get(universe_id)
        if record is None:
            if current_entry != manifest_entry:
                return False
            continue
        current_hash = current_entry["raw_sha256"]["config.yaml"]
        if current_hash not in {
            record["before_config_sha256"],
            record["after_config_sha256"],
        }:
            return False
    return True


def _windows_file_lock_operation(
    fd: int,
    *,
    unlock: bool,
    blocking: bool = True,
) -> None:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_size_t),
            ("InternalHigh", ctypes.c_size_t),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    overlapped = Overlapped()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = wintypes.HANDLE(msvcrt.get_osfhandle(fd))
    if unlock:
        operation = kernel32.UnlockFileEx
        operation.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(Overlapped),
        ]
        arguments = (handle, 0, 1, 0, ctypes.byref(overlapped))
    else:
        operation = kernel32.LockFileEx
        operation.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(Overlapped),
        ]
        flags = 0x00000002 | (0 if blocking else 0x00000001)
        arguments = (handle, flags, 0, 1, 0, ctypes.byref(overlapped))
    operation.restype = wintypes.BOOL
    if not operation(*arguments):
        raise ctypes.WinError(ctypes.get_last_error())


@contextlib.contextmanager
def _exclusive_assignment_lock(universe: Path, *, timeout: float) -> Iterator[None]:
    path = universe / LOCK_FILENAME
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        metadata = None
    if metadata is not None and (
        stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode)
    ):
        raise MigrationError("assignment lock path is unsafe", 4)

    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o644)
    except OSError as exc:
        raise MigrationError("assignment lock cannot be opened", 4) from exc
    locked = False
    try:
        opened = _opened_file_metadata(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise MigrationError("assignment lock path is unsafe", 4)
        if opened.st_nlink != 1:
            raise MigrationError("assignment lock path is unsafe", 4)
        deadline = time.monotonic() + timeout
        while True:
            try:
                if sys.platform == "win32":
                    _windows_file_lock_operation(fd, unlock=False, blocking=False)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError as exc:
                is_contention = exc.errno in {
                    errno.EACCES,
                    errno.EAGAIN,
                    errno.EWOULDBLOCK,
                    errno.EDEADLK,
                } or getattr(exc, "winerror", None) in {32, 33, 36}
                if not is_contention:
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MigrationError(
                        "assignment lock timeout; no assignment state was changed",
                        5,
                    ) from exc
                time.sleep(min(0.05, remaining))
        yield
    finally:
        if locked:
            if sys.platform == "win32":
                _windows_file_lock_operation(fd, unlock=True)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _inventory(data_dir: Path, manifest_path: Path) -> int:
    manifest_path = _validated_manifest_path(data_dir, manifest_path, exit_code=2)
    scan = _scan_data(data_dir)
    try:
        _write_json_atomic(manifest_path, _manifest_for_scan(scan))
    except OSError as exc:
        raise MigrationError("manifest could not be written", 2) from exc
    print(json.dumps({"summary": scan["summary"]}, sort_keys=True))
    return 2 if scan["summary"]["fatal_count"] else 0


def _apply(data_dir: Path, manifest_path: Path, *, lock_timeout: float) -> int:
    manifest_path = _validated_manifest_path(data_dir, manifest_path, exit_code=4)
    manifest, manifest_raw = _read_strict_json_file(manifest_path, "manifest")
    _validate_manifest_shape(manifest)
    _validate_review(manifest)
    manifest_digest = hashlib.sha256(manifest_raw).hexdigest()

    marker_path = data_dir / MARKER_FILENAME
    journal_path = data_dir / JOURNAL_FILENAME
    existing_marker: dict[str, Any] | None = None
    existing_journal: dict[str, Any] | None = None
    if marker_path.exists() or marker_path.is_symlink():
        existing_marker, _marker_raw = _read_strict_json_file(marker_path, "migration marker")
        _validate_marker(existing_marker)
    if journal_path.exists() or journal_path.is_symlink():
        existing_journal, _journal_raw = _read_strict_json_file(journal_path, "transaction journal")
        _validate_journal(existing_journal)
        if existing_journal["manifest_sha256"] != manifest_digest:
            raise MigrationError("transaction journal belongs to another reviewed manifest", 4)

    scan = _scan_data(data_dir)
    if scan["summary"]["fatal_count"]:
        raise MigrationError("current assignment state contains fatal entries", 4)
    if existing_journal is not None:
        if not _scan_matches_recovery_transaction(manifest, scan, existing_journal):
            raise MigrationError("transaction journal does not match current state", 4)
        universe_ids = existing_journal["universe_ids"]
    else:
        universe_ids = scan["lock_universe_ids"]
        if existing_marker is not None:
            if not _marker_matches(existing_marker, manifest_raw, scan):
                raise MigrationError("migration marker is stale or belongs to another manifest", 4)
        elif not _manifest_matches_scan(manifest, scan):
            raise MigrationError("manifest is stale or incomplete", 4)

    with contextlib.ExitStack() as locks:
        for universe_id in universe_ids:
            locks.enter_context(
                _exclusive_assignment_lock(
                    data_dir / universe_id,
                    timeout=lock_timeout,
                )
            )

        locked_scan = _scan_data(data_dir)
        if locked_scan["lock_universe_ids"] != universe_ids:
            raise MigrationError("universe directory set changed under lock", 4)
        if locked_scan["summary"]["fatal_count"]:
            raise MigrationError("assignment state became fatal under lock", 4)

        if existing_journal is not None:
            locked_journal, _locked_journal_raw = _read_strict_json_file(
                journal_path, "transaction journal"
            )
            _validate_journal(locked_journal)
            if locked_journal != existing_journal or not (
                _scan_matches_recovery_transaction(manifest, locked_scan, locked_journal)
            ):
                raise MigrationError("transaction journal changed under lock", 4)
            if existing_marker is not None:
                locked_marker, _locked_marker_raw = _read_strict_json_file(
                    marker_path, "migration marker"
                )
                _validate_marker(locked_marker)
                if locked_marker != existing_marker or not _marker_matches(
                    locked_marker, manifest_raw, locked_scan
                ):
                    raise MigrationError("marker and transaction journal are not complete", 4)
                _unlink_regular_file_durable(journal_path)
                print(
                    json.dumps(
                        {
                            "status": "already_applied",
                            "summary": locked_scan["summary"],
                        }
                    )
                )
                return 0
        else:
            if existing_marker is not None:
                locked_marker, _locked_marker_raw = _read_strict_json_file(
                    marker_path, "migration marker"
                )
                _validate_marker(locked_marker)
                if locked_marker != existing_marker or not _marker_matches(
                    locked_marker, manifest_raw, locked_scan
                ):
                    raise MigrationError("migration marker changed under lock", 4)
                print(
                    json.dumps(
                        {
                            "status": "already_applied",
                            "summary": locked_scan["summary"],
                        }
                    )
                )
                return 0
            if marker_path.exists() or marker_path.is_symlink():
                raise MigrationError("migration marker appeared under lock", 4)
            if journal_path.exists() or journal_path.is_symlink():
                raise MigrationError("transaction journal appeared under lock", 4)
            if not _manifest_matches_scan(manifest, locked_scan):
                raise MigrationError("manifest became stale under assignment lock", 4)

        manifest_entries = {entry["universe_id"]: entry for entry in manifest["universes"]}
        if existing_journal is None:
            transaction_ids = [
                entry["universe_id"] for entry in locked_scan["entries"] if entry["needs_migration"]
            ]
            journal_records: dict[str, dict[str, Any]] = {}
        else:
            transaction_ids = [record["universe_id"] for record in existing_journal["configs"]]
            journal_records = {
                record["universe_id"]: record for record in existing_journal["configs"]
            }

        prepared: dict[str, dict[str, Any]] = {}
        for universe_id in transaction_ids:
            config_path = data_dir / universe_id / "config.yaml"
            snapshot = _config_snapshot(config_path)
            current_hash = _raw_hash(snapshot[0])
            config = dict(locked_scan["configs"][universe_id])
            target = manifest_entries[universe_id]["target"]
            config["engine_assignment_state"] = target["engine_assignment_state"]
            config["allowed_providers"] = target["allowed_providers"]
            after_hash = hashlib.sha256(_config_bytes(config)).hexdigest()
            record = journal_records.get(universe_id)
            if record is None:
                expected_before = manifest_entries[universe_id]["raw_sha256"]["config.yaml"]
                if current_hash != expected_before:
                    raise MigrationError("config changed during locked preflight", 4)
            elif after_hash != record["after_config_sha256"] or current_hash not in {
                record["before_config_sha256"],
                record["after_config_sha256"],
            }:
                raise MigrationError(
                    "config is neither exact before nor deterministic after state",
                    4,
                )
            prepared[universe_id] = {
                "path": config_path,
                "snapshot": snapshot,
                "current_sha256": current_hash,
                "after_sha256": after_hash,
                "after_config": config,
            }

        if existing_journal is None:
            journal = _journal_for_transaction(manifest_raw, universe_ids, prepared)
            try:
                _write_json_atomic(journal_path, journal)
            except OSError as exc:
                raise MigrationError("transaction journal could not be committed", 4) from exc
        else:
            journal = existing_journal

        attempted: list[str] = []
        failure_stage = "config write"
        try:
            for universe_id in transaction_ids:
                state = prepared[universe_id]
                if state["current_sha256"] == state["after_sha256"]:
                    continue
                attempted.append(universe_id)
                _write_config_atomic(state["path"], state["after_config"])

            failure_stage = "post-apply verification"
            post_scan = _scan_data(data_dir)
            post_entries = {entry["universe_id"]: entry for entry in post_scan["entries"]}
            if (
                not _scan_matches_recovery_transaction(manifest, post_scan, journal)
                or post_scan["summary"]["needs_migration_count"]
                or any(
                    post_entries[record["universe_id"]]["raw_sha256"]["config.yaml"]
                    != record["after_config_sha256"]
                    for record in journal["configs"]
                )
            ):
                raise MigrationError("post-apply verification found residual assignments", 4)
            marker = _marker_for_manifest(manifest, manifest_raw, post_scan)
            failure_stage = "marker write"
            _write_json_atomic(marker_path, marker)
        except Exception as apply_error:
            if existing_journal is not None:
                raise MigrationError(
                    f"{failure_stage} failed; transaction journal retained for retry",
                    4,
                ) from apply_error

            rollback_errors: list[Exception] = []
            try:
                _unlink_regular_file_durable(marker_path)
            except Exception as rollback_error:
                rollback_errors.append(rollback_error)
            for universe_id in reversed(attempted):
                try:
                    _restore_config_snapshot(
                        prepared[universe_id]["path"],
                        prepared[universe_id]["snapshot"],
                    )
                except Exception as rollback_error:
                    rollback_errors.append(rollback_error)
            if not rollback_errors:
                try:
                    _unlink_regular_file_durable(journal_path)
                except Exception as rollback_error:
                    rollback_errors.append(rollback_error)
            if rollback_errors:
                raise MigrationError(
                    f"{failure_stage} failed and config rollback was incomplete",
                    4,
                ) from apply_error
            raise MigrationError(
                f"{failure_stage} failed; all config bytes were restored",
                4,
            ) from apply_error

        try:
            _unlink_regular_file_durable(journal_path)
        except OSError as exc:
            raise MigrationError(
                "marker committed but transaction journal cleanup failed; retry apply",
                4,
            ) from exc

    print(json.dumps({"status": "applied", "summary": post_scan["summary"]}))
    return 0


def _verify(data_dir: Path) -> int:
    scan = _scan_data(data_dir)
    marker_path = data_dir / MARKER_FILENAME
    journal_path = data_dir / JOURNAL_FILENAME
    marker_status = "missing"
    transaction_status = "none"
    marker: dict[str, Any] | None = None
    if marker_path.exists() or marker_path.is_symlink():
        try:
            marker, _raw = _read_strict_json_file(marker_path, "migration marker")
            _validate_marker(marker)
            marker_status = "valid"
        except MigrationError:
            marker_status = "invalid"
    if journal_path.exists() or journal_path.is_symlink():
        try:
            journal, _raw = _read_strict_json_file(journal_path, "transaction journal")
            _validate_journal(journal)
            transaction_status = "incomplete"
        except MigrationError:
            transaction_status = "invalid"

    decisions_match = bool(
        marker is not None and marker.get("universes") == _decisions(scan["entries"])
    )
    output = {
        "fence_version": FENCE_VERSION,
        "marker_status": marker_status,
        "marker_decisions_match": decisions_match,
        "transaction_status": transaction_status,
        "summary": scan["summary"],
    }
    print(json.dumps(output, sort_keys=True))
    if (
        scan["summary"]["fatal_count"]
        or marker_status == "invalid"
        or transaction_status == "invalid"
    ):
        return 2
    if (
        scan["summary"]["needs_migration_count"]
        or marker_status != "valid"
        or transaction_status != "none"
    ):
        return 5
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    inventory = commands.add_parser("inventory")
    inventory.add_argument("--data-dir", required=True)
    inventory.add_argument("--manifest", required=True)

    apply_command = commands.add_parser("apply")
    apply_command.add_argument("--data-dir", required=True)
    apply_command.add_argument("--manifest", required=True)
    apply_command.add_argument("--lock-timeout", type=float, default=30.0)

    verify = commands.add_parser("verify")
    verify.add_argument("--data-dir", required=True)

    support = commands.add_parser("supports-fence-version")
    support.add_argument("version")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "supports-fence-version":
        return 0 if args.version == str(FENCE_VERSION) else 1

    data_dir = _validated_data_dir(args.data_dir)
    if args.command == "inventory":
        return _inventory(data_dir, Path(args.manifest).absolute())
    if args.command == "apply":
        if not math.isfinite(args.lock_timeout) or args.lock_timeout < 0:
            raise MigrationError("lock timeout must be a finite non-negative value", 4)
        return _apply(
            data_dir,
            Path(args.manifest).absolute(),
            lock_timeout=args.lock_timeout,
        )
    if args.command == "verify":
        return _verify(data_dir)
    raise AssertionError("unreachable command")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MigrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(exc.exit_code) from None
    except Exception as exc:  # fail closed without echoing raw state or secrets
        print(
            f"error: migration failed closed ({type(exc).__name__})",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
