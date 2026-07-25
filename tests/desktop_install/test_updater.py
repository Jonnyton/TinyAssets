from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _canonical(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _signed_manifest(
    private_key: Ed25519PrivateKey,
    artifact: bytes,
    **overrides: object,
) -> bytes:
    payload: dict[str, object] = {
        "schema_version": 1,
        "product": "TinyAssets",
        "version": "1.1.0",
        "channel": "stable",
        "platform": "win32",
        "architecture": "x86_64",
        "artifact_name": "TinyAssetsSetup.exe",
        "sha256": hashlib.sha256(artifact).hexdigest(),
        "artifact_signature": base64.b64encode(private_key.sign(artifact)).decode(),
        "source_commit": "a" * 40,
        "build_workflow": "desktop-release.yml",
        "rollout_percent": 100,
    }
    payload.update(overrides)
    envelope = {
        "signed": payload,
        "signature": base64.b64encode(private_key.sign(_canonical(payload))).decode(),
    }
    return _canonical(envelope)


@pytest.fixture
def updater(tmp_path: Path):
    if importlib.util.find_spec("tinyassets.desktop.updater") is None:
        pytest.skip("updater module does not exist until the production slice")
    from tinyassets.desktop import updater

    key = Ed25519PrivateKey.generate()
    public_key = key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    class Installer:
        def __init__(self) -> None:
            self.installed: list[Path] = []
            self.restored: list[Path] = []

        def install(self, artifact: Path) -> None:
            self.installed.append(artifact)

        def restore(self, artifact: Path) -> None:
            self.restored.append(artifact)

    installer = Installer()
    service = updater.UpdateService(
        install_root=tmp_path / "install",
        public_key_pem=public_key,
        product="TinyAssets",
        platform_name="win32",
        architecture="x86_64",
        channel="stable",
        installer=installer,
    )
    old_artifact = tmp_path / "TinyAssets-1.0.0.exe"
    old_artifact.write_bytes(b"old release")
    service.initialize_current(version="1.0.0", artifact=old_artifact)
    return updater, service, key, installer


def test_updater_module_exists() -> None:
    assert importlib.util.find_spec("tinyassets.desktop.updater") is not None


def test_signed_update_activates_after_health_check(updater, tmp_path: Path) -> None:
    module, service, key, installer = updater
    artifact = tmp_path / "TinyAssetsSetup.exe"
    artifact.write_bytes(b"new release")
    staged = service.stage_update(_signed_manifest(key, artifact.read_bytes()), artifact)

    result = service.apply_staged(staged, health_check=lambda path: path.exists())

    assert result.status == "activated"
    assert service.current_version() == "1.1.0"
    assert result.previous_version == "1.0.0"
    assert installer.installed == [
        service.install_root / "releases" / "1.1.0" / "TinyAssetsSetup.exe"
    ]


def test_tampered_artifact_is_rejected_before_activation(updater, tmp_path: Path) -> None:
    module, service, key, _ = updater
    artifact = tmp_path / "TinyAssetsSetup.exe"
    artifact.write_bytes(b"expected release")
    manifest = _signed_manifest(key, artifact.read_bytes())
    artifact.write_bytes(b"tampered release")

    with pytest.raises(module.UpdateVerificationError, match="checksum"):
        service.stage_update(manifest, artifact)

    assert service.current_version() == "1.0.0"


def test_staged_artifact_is_reverified_at_activation(updater, tmp_path: Path) -> None:
    module, service, key, _ = updater
    artifact = tmp_path / "TinyAssetsSetup.exe"
    artifact.write_bytes(b"expected release")
    staged = service.stage_update(_signed_manifest(key, artifact.read_bytes()), artifact)
    staged.artifact.write_bytes(b"tampered after staging")

    with pytest.raises(module.UpdateVerificationError, match="checksum"):
        service.apply_staged(staged, health_check=lambda _: True)

    assert service.current_version() == "1.0.0"


def test_failed_health_check_rolls_back_and_records_evidence(
    updater, tmp_path: Path
) -> None:
    _, service, key, installer = updater
    artifact = tmp_path / "TinyAssetsSetup.exe"
    artifact.write_bytes(b"bad release")
    staged = service.stage_update(_signed_manifest(key, artifact.read_bytes()), artifact)

    result = service.apply_staged(staged, health_check=lambda _: False)

    assert result.status == "rolled_back"
    assert service.current_version() == "1.0.0"
    evidence = json.loads((service.install_root / "rollback-evidence.json").read_text())
    assert evidence["failed_version"] == "1.1.0"
    assert evidence["restored_version"] == "1.0.0"
    assert installer.restored == [
        service.install_root / "releases" / "1.0.0" / "TinyAssets-1.0.0.exe"
    ]


def test_crash_after_activation_is_recovered_on_next_start(
    updater, tmp_path: Path
) -> None:
    _, service, key, _ = updater
    artifact = tmp_path / "TinyAssetsSetup.exe"
    artifact.write_bytes(b"crashing release")
    staged = service.stage_update(_signed_manifest(key, artifact.read_bytes()), artifact)

    class SimulatedProcessCrash(BaseException):
        pass

    with pytest.raises(SimulatedProcessCrash):
        service.apply_staged(
            staged,
            health_check=lambda _: (_ for _ in ()).throw(SimulatedProcessCrash()),
        )

    recovered = service.recover_incomplete_update()

    assert recovered is not None
    assert recovered.status == "rolled_back"
    assert service.current_version() == "1.0.0"


def test_prepared_transaction_rolls_back_conservatively(
    updater, tmp_path: Path
) -> None:
    _, service, key, _ = updater
    artifact = tmp_path / "TinyAssetsSetup.exe"
    artifact.write_bytes(b"candidate release")
    staged = service.stage_update(_signed_manifest(key, artifact.read_bytes()), artifact)
    current_path = service.install_root / "current.json"
    previous = json.loads(current_path.read_text())
    current_path.write_text(
        json.dumps({"version": "1.1.0", "artifact": str(staged.artifact)}),
        encoding="utf-8",
    )
    (service.install_root / "update-transaction.json").write_text(
        json.dumps(
            {
                "status": "prepared",
                "candidate_version": "1.1.0",
                "candidate_artifact": str(staged.artifact),
                "previous": previous,
            }
        ),
        encoding="utf-8",
    )

    recovered = service.recover_incomplete_update()

    assert recovered is not None
    assert recovered.status == "rolled_back"
    assert service.current_version() == "1.0.0"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"version": "0.9.0"}, "newer"),
        ({"platform": "darwin"}, "platform"),
        ({"architecture": "arm64"}, "architecture"),
        ({"channel": "prerelease"}, "channel"),
        ({"product": "OtherProduct"}, "product"),
    ],
)
def test_incompatible_or_downgrade_manifest_is_rejected(
    updater,
    tmp_path: Path,
    override: dict[str, object],
    message: str,
) -> None:
    module, service, key, _ = updater
    artifact = tmp_path / "TinyAssetsSetup.exe"
    artifact.write_bytes(b"new release")

    with pytest.raises(module.UpdateVerificationError, match=message):
        service.stage_update(
            _signed_manifest(key, artifact.read_bytes(), **override),
            artifact,
        )


def test_semver_prerelease_identifiers_compare_numerically(
    updater, tmp_path: Path
) -> None:
    module, service, key, _ = updater
    service.initialize_current(
        version="1.1.0-beta.10",
        artifact=tmp_path / "TinyAssets-1.0.0.exe",
    )
    artifact = tmp_path / "TinyAssetsSetup.exe"
    artifact.write_bytes(b"older prerelease")

    with pytest.raises(module.UpdateVerificationError, match="newer"):
        service.stage_update(
            _signed_manifest(
                key,
                artifact.read_bytes(),
                version="1.1.0-beta.2",
                channel="stable",
            ),
            artifact,
        )


def test_rollout_cohort_is_enforced_before_staging(updater, tmp_path: Path) -> None:
    module, service, key, _ = updater
    artifact = tmp_path / "TinyAssetsSetup.exe"
    artifact.write_bytes(b"limited release")

    with pytest.raises(module.UpdateVerificationError, match="rollout"):
        service.stage_update(
            _signed_manifest(key, artifact.read_bytes(), rollout_percent=0),
            artifact,
        )


def test_windows_installer_executes_verified_artifact_in_silent_mode(
    tmp_path: Path,
) -> None:
    from tinyassets.desktop.updater import WindowsInstaller

    calls: list[tuple[list[str], bool]] = []
    artifact = tmp_path / "TinyAssetsSetup.exe"
    artifact.write_bytes(b"signed installer")
    installer = WindowsInstaller(
        runner=lambda command, check: calls.append((command, check))
    )

    installer.install(artifact)

    assert calls == [
        (
            [
                str(artifact),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
            ],
            True,
        )
    ]
