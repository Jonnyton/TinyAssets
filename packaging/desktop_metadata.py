"""Generate reproducible metadata and SPDX SBOMs for desktop artifacts."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SIGNING_STATUSES = {"unsigned-ci", "signed", "signed-and-notarized"}
_CHANNELS = {"stable", "prerelease"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_metadata(
    *,
    artifact: Path,
    product_version: str,
    source_commit: str,
    build_workflow: str,
    target_platform: str,
    architecture: str,
    signing_status: str,
    signing_identity: str | None,
    sbom: Path,
    channel: str,
    rollout_percent: int,
    source_date_epoch: int,
) -> dict[str, object]:
    """Return path-independent artifact metadata for a reproducible build."""
    artifact = Path(artifact)
    sbom = Path(sbom)
    if not artifact.is_file():
        raise FileNotFoundError(artifact)
    if not sbom.is_file():
        raise FileNotFoundError(sbom)
    if not _COMMIT.fullmatch(source_commit):
        raise ValueError("source commit must be a full lowercase SHA")
    if signing_status not in _SIGNING_STATUSES:
        raise ValueError(f"unsupported signing status: {signing_status!r}")
    if signing_status != "unsigned-ci" and not signing_identity:
        raise ValueError("signed metadata requires a signing identity")
    if signing_status == "unsigned-ci" and signing_identity:
        raise ValueError("unsigned CI metadata cannot claim a signing identity")
    if channel not in _CHANNELS:
        raise ValueError(f"unsupported update channel: {channel!r}")
    if not 0 <= rollout_percent <= 100:
        raise ValueError("rollout percentage must be between 0 and 100")
    timestamp = datetime.fromtimestamp(source_date_epoch, tz=UTC).isoformat()
    return {
        "schema_version": 1,
        "product": "TinyAssets",
        "product_version": product_version,
        "source_commit": source_commit,
        "build_workflow": build_workflow,
        "target": {
            "platform": target_platform,
            "architecture": architecture,
        },
        "artifact": {
            "name": artifact.name,
            "sha256": _sha256(artifact),
            "size_bytes": artifact.stat().st_size,
        },
        "signing": {
            "status": signing_status,
            "identity": signing_identity,
        },
        "sbom": {
            "name": sbom.name,
            "sha256": _sha256(sbom),
        },
        "update": {
            "channel": channel,
            "rollout_percent": rollout_percent,
        },
        "source_date_epoch": source_date_epoch,
        "generated_at": timestamp,
    }


def installed_packages() -> list[str]:
    """Return stable ``name==version`` entries for the build environment."""
    packages = {
        f"{distribution.metadata['Name']}=={distribution.version}"
        for distribution in importlib.metadata.distributions()
        if distribution.metadata.get("Name")
    }
    return sorted(packages, key=str.casefold)


def build_spdx_sbom(
    *,
    artifact_name: str,
    packages: Iterable[str],
    source_date_epoch: int,
) -> dict[str, object]:
    """Create a minimal deterministic SPDX 2.3 package inventory."""
    package_list = sorted(set(packages), key=str.casefold)
    namespace_hash = hashlib.sha256(
        (artifact_name + "\n" + "\n".join(package_list)).encode()
    ).hexdigest()
    created = datetime.fromtimestamp(source_date_epoch, tz=UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{artifact_name}-sbom",
        "documentNamespace": f"https://tinyassets.io/spdx/{namespace_hash}",
        "creationInfo": {
            "created": created,
            "creators": ["Tool: packaging/desktop_metadata.py"],
        },
        "packages": [
            {
                "name": item.partition("==")[0],
                "versionInfo": item.partition("==")[2],
                "SPDXID": f"SPDXRef-Package-{index}",
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
            }
            for index, item in enumerate(package_list, start=1)
        ],
    }


def sign_update_manifest(
    *,
    artifact: Path,
    private_key_pem: bytes,
    product_version: str,
    source_commit: str,
    build_workflow: str,
    target_platform: str,
    architecture: str,
    channel: str,
    rollout_percent: int,
) -> dict[str, object]:
    """Sign the updater's manifest and artifact with a provisioned Ed25519 key."""
    artifact = Path(artifact)
    if not artifact.is_file():
        raise FileNotFoundError(artifact)
    if not _COMMIT.fullmatch(source_commit):
        raise ValueError("source commit must be a full lowercase SHA")
    if channel not in _CHANNELS:
        raise ValueError(f"unsupported update channel: {channel!r}")
    if not 0 <= rollout_percent <= 100:
        raise ValueError("rollout percentage must be between 0 and 100")
    key = load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("desktop update signing identity must be Ed25519")
    artifact_bytes = artifact.read_bytes()
    signed: dict[str, object] = {
        "schema_version": 1,
        "product": "TinyAssets",
        "version": product_version,
        "channel": channel,
        "platform": target_platform,
        "architecture": architecture,
        "artifact_name": artifact.name,
        "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
        "artifact_signature": base64.b64encode(key.sign(artifact_bytes)).decode(),
        "source_commit": source_commit,
        "build_workflow": build_workflow,
        "rollout_percent": rollout_percent,
    }
    signature = base64.b64encode(key.sign(_canonical_json(signed))).decode()
    return {"signed": signed, "signature": signature}


def _canonical_json(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    sbom = subparsers.add_parser("sbom")
    sbom.add_argument("--artifact-name", required=True)
    sbom.add_argument("--output", type=Path, required=True)
    metadata = subparsers.add_parser("metadata")
    metadata.add_argument("--artifact", type=Path, required=True)
    metadata.add_argument("--output", type=Path, required=True)
    metadata.add_argument("--version", required=True)
    metadata.add_argument("--source-commit", required=True)
    metadata.add_argument("--workflow", required=True)
    metadata.add_argument("--platform", required=True)
    metadata.add_argument("--architecture", required=True)
    metadata.add_argument("--signing-status", required=True)
    metadata.add_argument("--signing-identity")
    metadata.add_argument("--sbom", type=Path, required=True)
    metadata.add_argument("--channel", required=True)
    metadata.add_argument("--rollout-percent", type=int, required=True)
    manifest = subparsers.add_parser("sign-update-manifest")
    manifest.add_argument("--artifact", type=Path, required=True)
    manifest.add_argument("--output", type=Path, required=True)
    manifest.add_argument("--version", required=True)
    manifest.add_argument("--source-commit", required=True)
    manifest.add_argument("--workflow", required=True)
    manifest.add_argument("--platform", required=True)
    manifest.add_argument("--architecture", required=True)
    manifest.add_argument("--channel", required=True)
    manifest.add_argument("--rollout-percent", type=int, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        source_date_epoch = int(os.environ["SOURCE_DATE_EPOCH"])
    except (KeyError, ValueError) as exc:
        raise SystemExit("SOURCE_DATE_EPOCH must be provisioned for reproducible builds") from exc
    if args.command == "sbom":
        _write_json(
            args.output,
            build_spdx_sbom(
                artifact_name=args.artifact_name,
                packages=installed_packages(),
                source_date_epoch=source_date_epoch,
            ),
        )
        return 0
    if args.command == "sign-update-manifest":
        encoded_key = os.environ.get("DESKTOP_UPDATE_SIGNING_KEY_BASE64", "")
        if not encoded_key:
            raise SystemExit(
                "signing identity not provisioned: desktop update manifest key"
            )
        try:
            private_key_pem = base64.b64decode(encoded_key, validate=True)
        except ValueError as exc:
            raise SystemExit("desktop update signing key is not valid base64") from exc
        _write_json(
            args.output,
            sign_update_manifest(
                artifact=args.artifact,
                private_key_pem=private_key_pem,
                product_version=args.version,
                source_commit=args.source_commit,
                build_workflow=args.workflow,
                target_platform=args.platform,
                architecture=args.architecture,
                channel=args.channel,
                rollout_percent=args.rollout_percent,
            ),
        )
        return 0
    _write_json(
        args.output,
        build_metadata(
            artifact=args.artifact,
            product_version=args.version,
            source_commit=args.source_commit,
            build_workflow=args.workflow,
            target_platform=args.platform,
            architecture=args.architecture,
            signing_status=args.signing_status,
            signing_identity=args.signing_identity,
            sbom=args.sbom,
            channel=args.channel,
            rollout_percent=args.rollout_percent,
            source_date_epoch=source_date_epoch,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
