"""Signed, atomic, rollback-capable updater for packaged desktop releases."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from tinyassets.singleton_lock import acquire_singleton_lock, release_singleton_lock

_SEMVER = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?P<suffix>-[0-9A-Za-z.-]+)?$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_CHANNELS = {"stable", "prerelease"}


class UpdateVerificationError(ValueError):
    """A manifest or artifact failed a fail-closed update check."""


class UpdateInProgress(RuntimeError):
    """Another updater owns the installation's update lock."""


class Installer(Protocol):
    """Platform installer used for both activation and last-known-good restore."""

    def install(self, artifact: Path) -> None: ...

    def restore(self, artifact: Path) -> None: ...


class WindowsInstaller:
    """Execute verified Inno Setup artifacts in unattended repair-safe mode."""

    def __init__(self, *, runner=subprocess.run) -> None:
        self._runner = runner

    def install(self, artifact: Path) -> None:
        if artifact.suffix.lower() != ".exe":
            raise UpdateVerificationError("Windows update artifact must be an installer")
        self._runner(
            [
                str(artifact),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
            ],
            check=True,
        )

    def restore(self, artifact: Path) -> None:
        self.install(artifact)


class UnsupportedPlatformInstaller:
    """Explicit fail-closed gate for native update adapters not built yet."""

    def __init__(self, platform_name: str) -> None:
        self._platform = platform_name

    def install(self, artifact: Path) -> None:
        del artifact
        raise UpdateVerificationError(
            f"native updater is not implemented yet for {self._platform}"
        )

    def restore(self, artifact: Path) -> None:
        self.install(artifact)


@dataclass(frozen=True)
class UpdateManifest:
    schema_version: int
    product: str
    version: str
    channel: str
    platform: str
    architecture: str
    artifact_name: str
    sha256: str
    artifact_signature: str
    source_commit: str
    build_workflow: str
    rollout_percent: int


@dataclass(frozen=True)
class StagedUpdate:
    manifest: UpdateManifest
    artifact: Path


@dataclass(frozen=True)
class UpdateResult:
    status: str
    version: str
    previous_version: str | None
    evidence_path: Path | None = None


def _canonical(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UpdateVerificationError(f"update state is unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise UpdateVerificationError(f"update state is not an object: {path}")
    return payload


def _version_key(
    version: str,
) -> tuple[int, int, int, int, tuple[tuple[int, int | str], ...]]:
    match = _SEMVER.fullmatch(version)
    if match is None:
        raise UpdateVerificationError(f"version is not supported SemVer: {version!r}")
    suffix = match.group("suffix")
    prerelease: tuple[tuple[int, int | str], ...] = ()
    if suffix:
        prerelease = tuple(
            (0, int(part)) if part.isdigit() else (1, part)
            for part in suffix[1:].split(".")
        )
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
        0 if suffix else 1,
        prerelease,
    )


class ManifestVerifier:
    """Verify an Ed25519-signed manifest envelope and detached artifact."""

    def __init__(self, public_key_pem: bytes) -> None:
        try:
            key = load_pem_public_key(public_key_pem)
        except (TypeError, ValueError) as exc:
            raise UpdateVerificationError("update public key is invalid") from exc
        if not isinstance(key, Ed25519PublicKey):
            raise UpdateVerificationError("update public key must be Ed25519")
        self._key = key

    def verify_manifest(self, document: bytes) -> UpdateManifest:
        try:
            envelope = json.loads(document)
            signed = envelope["signed"]
            signature = base64.b64decode(envelope["signature"], validate=True)
        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise UpdateVerificationError("signed update manifest is malformed") from exc
        if not isinstance(signed, dict):
            raise UpdateVerificationError("signed update manifest payload must be an object")
        try:
            self._key.verify(signature, _canonical(signed))
        except InvalidSignature as exc:
            raise UpdateVerificationError("manifest signature verification failed") from exc
        manifest = self._parse_manifest(signed)
        return manifest

    def verify_artifact(self, manifest: UpdateManifest, artifact: bytes) -> None:
        checksum = hashlib.sha256(artifact).hexdigest()
        if checksum != manifest.sha256:
            raise UpdateVerificationError("artifact checksum verification failed")
        try:
            signature = base64.b64decode(manifest.artifact_signature, validate=True)
            self._key.verify(signature, artifact)
        except (ValueError, InvalidSignature) as exc:
            raise UpdateVerificationError("artifact signature verification failed") from exc

    @staticmethod
    def _parse_manifest(payload: dict[str, object]) -> UpdateManifest:
        required = set(UpdateManifest.__dataclass_fields__)
        missing = required - set(payload)
        if missing:
            raise UpdateVerificationError(
                f"signed update manifest is missing fields: {sorted(missing)}"
            )
        try:
            manifest = UpdateManifest(
                schema_version=int(payload["schema_version"]),
                product=str(payload["product"]),
                version=str(payload["version"]),
                channel=str(payload["channel"]),
                platform=str(payload["platform"]),
                architecture=str(payload["architecture"]),
                artifact_name=str(payload["artifact_name"]),
                sha256=str(payload["sha256"]),
                artifact_signature=str(payload["artifact_signature"]),
                source_commit=str(payload["source_commit"]),
                build_workflow=str(payload["build_workflow"]),
                rollout_percent=int(payload["rollout_percent"]),
            )
        except (TypeError, ValueError) as exc:
            raise UpdateVerificationError("signed update manifest field type is invalid") from exc
        if manifest.schema_version != 1:
            raise UpdateVerificationError("unsupported update manifest schema version")
        _version_key(manifest.version)
        if manifest.channel not in _CHANNELS:
            raise UpdateVerificationError("update channel is invalid")
        if not 0 <= manifest.rollout_percent <= 100:
            raise UpdateVerificationError("rollout percentage must be between 0 and 100")
        if not _SHA256.fullmatch(manifest.sha256):
            raise UpdateVerificationError("artifact checksum must be lowercase SHA-256")
        if not _COMMIT.fullmatch(manifest.source_commit):
            raise UpdateVerificationError("source commit must be a full lowercase SHA")
        if (
            not manifest.artifact_name
            or Path(manifest.artifact_name).name != manifest.artifact_name
        ):
            raise UpdateVerificationError("artifact name must not contain a path")
        return manifest


class UpdateService:
    """Stage and atomically activate verified releases under one install root."""

    def __init__(
        self,
        *,
        install_root: Path,
        public_key_pem: bytes,
        product: str,
        platform_name: str,
        architecture: str,
        channel: str,
        cohort_id: str | None = None,
        installer: Installer | None = None,
    ) -> None:
        if channel not in _CHANNELS:
            raise ValueError(f"unsupported update channel: {channel!r}")
        self.install_root = Path(install_root).resolve()
        self._verifier = ManifestVerifier(public_key_pem)
        self._product = product
        self._platform = platform_name
        self._architecture = architecture
        self._channel = channel
        self._cohort_id = cohort_id
        self._installer = installer or UnsupportedPlatformInstaller(platform_name)
        self._current_path = self.install_root / "current.json"
        self._transaction_path = self.install_root / "update-transaction.json"
        self._evidence_path = self.install_root / "rollback-evidence.json"
        self._lock_path = self.install_root / "update.lock"

    def initialize_current(self, *, version: str, artifact: Path) -> None:
        _version_key(version)
        source = Path(artifact)
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = self._release_artifact(version, source.name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source, destination)
        _atomic_json(
            self._current_path,
            {
                "version": version,
                "artifact": str(destination.relative_to(self.install_root)),
            },
        )

    def current_version(self) -> str | None:
        if not self._current_path.exists():
            return None
        current = _read_json(self._current_path)
        value = current.get("version")
        return str(value) if value is not None else None

    def stage_update(self, manifest_document: bytes, artifact: Path) -> StagedUpdate:
        manifest = self._verifier.verify_manifest(manifest_document)
        self._verify_compatibility(manifest)
        self._verify_rollout(manifest)
        source = Path(artifact)
        if source.name != manifest.artifact_name or not source.is_file():
            raise UpdateVerificationError("artifact does not match the manifest name")
        artifact_bytes = source.read_bytes()
        self._verifier.verify_artifact(manifest, artifact_bytes)
        destination = (
            self.install_root
            / "staging"
            / manifest.version
            / manifest.artifact_name
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".partial")
        temporary.write_bytes(artifact_bytes)
        os.replace(temporary, destination)
        return StagedUpdate(manifest=manifest, artifact=destination)

    def apply_staged(
        self,
        staged: StagedUpdate,
        *,
        health_check: Callable[[Path], bool],
    ) -> UpdateResult:
        lock = acquire_singleton_lock(self._lock_path)
        if not lock.acquired:
            raise UpdateInProgress("another desktop update is already in progress")
        try:
            if staged.artifact.name != staged.manifest.artifact_name:
                raise UpdateVerificationError("staged artifact name does not match")
            self._verifier.verify_artifact(
                staged.manifest,
                staged.artifact.read_bytes(),
            )
            previous = _read_json(self._current_path) if self._current_path.exists() else None
            release_artifact = self._release_artifact(
                staged.manifest.version, staged.manifest.artifact_name
            )
            release_artifact.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staged.artifact, release_artifact)
            transaction = {
                "status": "prepared",
                "candidate_version": staged.manifest.version,
                "candidate_artifact": str(
                    release_artifact.relative_to(self.install_root)
                ),
                "previous": previous,
            }
            _atomic_json(self._transaction_path, transaction)
            try:
                self._installer.install(release_artifact)
            except Exception as exc:
                return self._rollback(
                    transaction,
                    reason=f"native installer failed: {exc}",
                )
            _atomic_json(
                self._current_path,
                {
                    "version": staged.manifest.version,
                    "artifact": transaction["candidate_artifact"],
                },
            )
            transaction["status"] = "activated"
            _atomic_json(self._transaction_path, transaction)
            try:
                healthy = health_check(release_artifact)
            except Exception as exc:
                return self._rollback(transaction, reason=f"health check raised: {exc}")
            if not healthy:
                return self._rollback(transaction, reason="health check returned false")
            self._transaction_path.unlink(missing_ok=True)
            return UpdateResult(
                status="activated",
                version=staged.manifest.version,
                previous_version=(
                    str(previous["version"]) if previous is not None else None
                ),
            )
        finally:
            release_singleton_lock(lock)

    def recover_incomplete_update(self) -> UpdateResult | None:
        if not self._transaction_path.exists():
            return None
        lock = acquire_singleton_lock(self._lock_path)
        if not lock.acquired:
            raise UpdateInProgress("another desktop update is already in progress")
        try:
            transaction = _read_json(self._transaction_path)
            return self._rollback(
                transaction,
                reason="recovered interrupted update transaction",
            )
        finally:
            release_singleton_lock(lock)

    def _verify_compatibility(self, manifest: UpdateManifest) -> None:
        if manifest.product != self._product:
            raise UpdateVerificationError("update product does not match")
        if manifest.platform != self._platform:
            raise UpdateVerificationError("update platform does not match")
        if manifest.architecture != self._architecture:
            raise UpdateVerificationError("update architecture does not match")
        if manifest.channel != self._channel:
            raise UpdateVerificationError("update channel does not match")
        current = self.current_version()
        if current is not None and _version_key(manifest.version) <= _version_key(current):
            raise UpdateVerificationError("update version must be newer than current")

    def _verify_rollout(self, manifest: UpdateManifest) -> None:
        if manifest.rollout_percent == 100:
            return
        if not self._cohort_id:
            raise UpdateVerificationError(
                "update rollout cannot be enforced without a stable host cohort"
            )
        bucket = int.from_bytes(
            hashlib.sha256(self._cohort_id.encode("utf-8")).digest()[:8],
            "big",
        ) % 100
        if bucket >= manifest.rollout_percent:
            raise UpdateVerificationError("host is not included in this update rollout")

    def _rollback(
        self, transaction: dict[str, object], *, reason: str
    ) -> UpdateResult:
        previous = transaction.get("previous")
        if not isinstance(previous, dict):
            raise UpdateVerificationError(
                "update failed and no last known-good release is available"
            )
        previous_artifact = self.install_root / str(previous.get("artifact", ""))
        if (
            not previous_artifact.is_file()
            or self.install_root not in previous_artifact.resolve().parents
        ):
            raise UpdateVerificationError(
                "last known-good installer is unavailable for rollback"
            )
        try:
            self._installer.restore(previous_artifact)
        except Exception as exc:
            raise UpdateVerificationError(
                f"last known-good installer restore failed: {exc}"
            ) from exc
        _atomic_json(self._current_path, previous)
        failed_version = str(transaction["candidate_version"])
        restored_version = str(previous["version"])
        evidence = {
            "status": "rolled_back",
            "failed_version": failed_version,
            "restored_version": restored_version,
            "reason": reason,
        }
        _atomic_json(self._evidence_path, evidence)
        self._transaction_path.unlink(missing_ok=True)
        return UpdateResult(
            status="rolled_back",
            version=failed_version,
            previous_version=restored_version,
            evidence_path=self._evidence_path,
        )

    def _release_artifact(self, version: str, artifact_name: str) -> Path:
        return self.install_root / "releases" / version / artifact_name


__all__ = [
    "ManifestVerifier",
    "Installer",
    "StagedUpdate",
    "UpdateInProgress",
    "UpdateManifest",
    "UpdateResult",
    "UpdateService",
    "UpdateVerificationError",
    "UnsupportedPlatformInstaller",
    "WindowsInstaller",
]
