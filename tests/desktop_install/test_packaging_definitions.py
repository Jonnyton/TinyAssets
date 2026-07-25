from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from tinyassets.desktop.updater import ManifestVerifier

ROOT = Path(__file__).resolve().parents[2]
METADATA_MODULE = ROOT / "packaging" / "desktop_metadata.py"


def _load_metadata_module():
    assert METADATA_MODULE.is_file(), "desktop artifact metadata generator is missing"
    spec = importlib.util.spec_from_file_location("desktop_metadata", METADATA_MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_artifact_metadata_is_reproducible_and_complete(tmp_path: Path) -> None:
    metadata = _load_metadata_module()
    artifact = tmp_path / "TinyAssetsSetup.exe"
    sbom = tmp_path / "TinyAssetsSetup.exe.spdx.json"
    artifact.write_bytes(b"installer")
    sbom.write_text('{"spdxVersion":"SPDX-2.3"}\n', encoding="utf-8")
    kwargs = {
        "artifact": artifact,
        "product_version": "1.2.3",
        "source_commit": "a" * 40,
        "build_workflow": "desktop-release.yml",
        "target_platform": "windows",
        "architecture": "x86_64",
        "signing_status": "unsigned-ci",
        "signing_identity": None,
        "sbom": sbom,
        "channel": "prerelease",
        "rollout_percent": 10,
        "source_date_epoch": 1_700_000_000,
    }

    first = metadata.build_metadata(**kwargs)
    second = metadata.build_metadata(**kwargs)

    assert first == second
    assert first["artifact"]["name"] == "TinyAssetsSetup.exe"
    assert first["artifact"]["sha256"]
    assert first["source_commit"] == "a" * 40
    assert first["signing"] == {"status": "unsigned-ci", "identity": None}
    assert first["sbom"]["sha256"]
    assert first["update"] == {"channel": "prerelease", "rollout_percent": 10}


def test_signed_metadata_requires_a_real_identity(tmp_path: Path) -> None:
    metadata = _load_metadata_module()
    artifact = tmp_path / "artifact"
    sbom = tmp_path / "sbom.json"
    artifact.write_bytes(b"artifact")
    sbom.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="signing identity"):
        metadata.build_metadata(
            artifact=artifact,
            product_version="1.0.0",
            source_commit="b" * 40,
            build_workflow="desktop-release.yml",
            target_platform="linux",
            architecture="x86_64",
            signing_status="signed",
            signing_identity=None,
            sbom=sbom,
            channel="stable",
            rollout_percent=100,
            source_date_epoch=1_700_000_000,
        )


@pytest.mark.parametrize(
    ("platform", "required"),
    [
        (
            "windows",
            {
                "TinyAssets.spec",
                "TinyAssets.iss",
                "build.ps1",
                "sign.ps1",
                "entrypoint.py",
            },
        ),
        (
            "macos",
            {
                "TinyAssets.spec",
                "build.sh",
                "sign-and-notarize.sh",
                "entrypoint.py",
            },
        ),
        (
            "linux",
            {
                "TinyAssets.spec",
                "build.sh",
                "sign.sh",
                "entrypoint.py",
            },
        ),
    ],
)
def test_each_platform_has_native_build_and_signing_hooks(
    platform: str, required: set[str]
) -> None:
    platform_root = ROOT / "packaging" / platform

    assert {path.name for path in platform_root.iterdir()} >= required
    scripts = "\n".join(
        path.read_text(encoding="utf-8")
        for path in platform_root.iterdir()
        if path.suffix in {".ps1", ".sh"}
    )
    assert "signing identity not provisioned" in scripts
    assert "SOURCE_DATE_EPOCH" in scripts


def test_linux_build_defines_deb_and_portable_artifacts() -> None:
    build = (ROOT / "packaging" / "linux" / "build.sh").read_text(encoding="utf-8")

    assert "dpkg-deb" in build
    assert ".tar.gz" in build


def test_windows_installer_preserves_user_content_on_uninstall() -> None:
    installer = (ROOT / "packaging" / "windows" / "TinyAssets.iss").read_text(
        encoding="utf-8"
    )

    assert installer.count("{userappdata}\\TinyAssets") == 2
    assert '{userappdata}\\TinyAssets\\updates"' in installer
    assert "[UninstallDelete]" in installer
    assert "CompareText(" in installer


def test_metadata_json_round_trips_without_absolute_build_paths(
    tmp_path: Path,
) -> None:
    metadata = _load_metadata_module()
    artifact = tmp_path / "artifact.bin"
    sbom = tmp_path / "artifact.spdx.json"
    artifact.write_bytes(b"artifact")
    sbom.write_text("{}\n", encoding="utf-8")

    result = metadata.build_metadata(
        artifact=artifact,
        product_version="1.0.0",
        source_commit="c" * 40,
        build_workflow="desktop-release.yml",
        target_platform="linux",
        architecture="x86_64",
        signing_status="unsigned-ci",
        signing_identity=None,
        sbom=sbom,
        channel="stable",
        rollout_percent=100,
        source_date_epoch=1_700_000_000,
    )
    encoded = json.dumps(result, sort_keys=True)

    assert str(tmp_path) not in encoded


def test_update_manifest_uses_provisioned_ed25519_identity(tmp_path: Path) -> None:
    metadata = _load_metadata_module()
    artifact = tmp_path / "TinyAssetsSetup.exe"
    artifact.write_bytes(b"signed installer")
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        Encoding.PEM,
        PrivateFormat.PKCS8,
        NoEncryption(),
    )

    envelope = metadata.sign_update_manifest(
        artifact=artifact,
        private_key_pem=private_pem,
        product_version="1.2.3",
        source_commit="d" * 40,
        build_workflow="desktop-release.yml",
        target_platform="win32",
        architecture="x86_64",
        channel="stable",
        rollout_percent=25,
    )

    public_pem = private_key.public_key().public_bytes(
        Encoding.PEM,
        PublicFormat.SubjectPublicKeyInfo,
    )
    verified = ManifestVerifier(public_pem).verify_manifest(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
    )
    ManifestVerifier(public_pem).verify_artifact(verified, artifact.read_bytes())
    assert verified.version == "1.2.3"
    assert verified.rollout_percent == 25
