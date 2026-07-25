"""Generate reproducible metadata and SPDX SBOMs for desktop artifacts."""

from __future__ import annotations

import argparse
import ast
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
_BUNDLE_ENTRY_TYPES = {
    "BINARY",
    "DATA",
    "EXTENSION",
    "PYMODULE",
    "PYSOURCE",
}


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


def _bundle_entries(value: object) -> Iterable[tuple[str, str]]:
    if (
        isinstance(value, tuple)
        and len(value) == 3
        and isinstance(value[0], str)
        and isinstance(value[1], str)
        and value[2] in _BUNDLE_ENTRY_TYPES
    ):
        yield value[0], value[1]
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _bundle_entries(item)


def packages_from_pyinstaller_analysis(
    analysis: Path,
    *,
    project_name: str,
    project_version: str,
) -> list[str]:
    """Return distributions whose modules or files are in a PyInstaller bundle."""
    analysis = Path(analysis)
    try:
        bundle_graph = ast.literal_eval(analysis.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError) as exc:
        raise ValueError(f"unreadable PyInstaller analysis: {analysis}") from exc

    package_distributions = importlib.metadata.packages_distributions()
    roots = {
        name.casefold(): distributions for name, distributions in package_distributions.items()
    }
    distribution_names: set[str] = set()
    project_is_bundled = False
    for bundled_name, source_path in _bundle_entries(bundle_graph):
        module_root = bundled_name.replace("\\", "/").split("/", 1)[0].split(".", 1)[0]
        source_parts = source_path.replace("\\", "/").split("/")
        source_root = next(
            (
                source_parts[index + 1]
                for index, part in enumerate(source_parts[:-1])
                if part.casefold() in {"site-packages", "dist-packages"}
            ),
            "",
        )
        candidates = {module_root, source_root}
        for candidate in candidates:
            distribution_names.update(roots.get(candidate.casefold(), ()))
        if module_root.casefold() == project_name.casefold().replace("-", "_"):
            project_is_bundled = True

    packages = {f"{name}=={importlib.metadata.version(name)}" for name in distribution_names}
    if project_is_bundled:
        packages.add(f"{project_name}=={project_version}")
    return sorted(packages, key=str.casefold)


def build_spdx_sbom(
    *,
    artifact_name: str,
    artifact_size: int,
    packages: Iterable[str],
    source_date_epoch: int,
) -> dict[str, object]:
    """Create a minimal deterministic SPDX 2.3 package inventory."""
    package_list = sorted(set(packages), key=str.casefold)
    if artifact_size > 0 and not package_list:
        raise ValueError("non-empty artifact cannot have an empty SBOM")
    namespace_hash = hashlib.sha256(
        (artifact_name + "\n" + "\n".join(package_list)).encode()
    ).hexdigest()
    created = datetime.fromtimestamp(source_date_epoch, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
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


def verify_build_sbom(*, artifact: Path, sbom: Path, build_metadata: Path) -> None:
    """Verify that signing uses the exact non-empty SBOM emitted by the build."""
    artifact = Path(artifact)
    sbom = Path(sbom)
    build_metadata = Path(build_metadata)
    for path in (artifact, sbom, build_metadata):
        if not path.is_file():
            raise FileNotFoundError(path)
    try:
        metadata_document = json.loads(build_metadata.read_text(encoding="utf-8"))
        expected_artifact = metadata_document["artifact"]["name"]
        expected_sbom = metadata_document["sbom"]
        expected_sbom_name = expected_sbom["name"]
        expected_sbom_sha256 = expected_sbom["sha256"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("build metadata has no usable SBOM binding") from exc
    if expected_artifact != artifact.name or expected_sbom_name != sbom.name:
        raise ValueError("build metadata names do not match the signing artifact and SBOM")
    if expected_sbom_sha256 != _sha256(sbom):
        raise ValueError("attested SBOM differs from build-generated SBOM")
    try:
        sbom_document = json.loads(sbom.read_text(encoding="utf-8"))
        packages = sbom_document["packages"]
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("build-generated SBOM has no usable package inventory") from exc
    if artifact.stat().st_size > 0 and (not isinstance(packages, list) or not packages):
        raise ValueError("non-empty artifact cannot have an empty SBOM")


def sign_update_manifest(
    *,
    artifact: Path,
    sbom: Path,
    metadata: Path,
    private_key_pem: bytes,
    product_version: str,
    source_commit: str,
    build_workflow: str,
    target_platform: str,
    architecture: str,
    channel: str,
    rollout_percent: int,
) -> dict[str, object]:
    """Sign the updater's artifact and provenance manifest."""
    artifact = Path(artifact)
    sbom = Path(sbom)
    metadata = Path(metadata)
    for path in (artifact, sbom, metadata):
        if not path.is_file():
            raise FileNotFoundError(path)
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
        "schema_version": 2,
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
        "sbom_name": sbom.name,
        "sbom_sha256": _sha256(sbom),
        "metadata_name": metadata.name,
        "metadata_sha256": _sha256(metadata),
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
    sbom.add_argument("--artifact", type=Path, required=True)
    sbom.add_argument("--pyinstaller-analysis", type=Path, required=True)
    sbom.add_argument("--project-name", required=True)
    sbom.add_argument("--project-version", required=True)
    sbom.add_argument("--output", type=Path, required=True)
    verify_sbom = subparsers.add_parser("verify-build-sbom")
    verify_sbom.add_argument("--artifact", type=Path, required=True)
    verify_sbom.add_argument("--sbom", type=Path, required=True)
    verify_sbom.add_argument("--build-metadata", type=Path, required=True)
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
    manifest.add_argument("--sbom", type=Path, required=True)
    manifest.add_argument("--metadata", type=Path, required=True)
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
        if not args.artifact.is_file():
            raise FileNotFoundError(args.artifact)
        _write_json(
            args.output,
            build_spdx_sbom(
                artifact_name=args.artifact.name,
                artifact_size=args.artifact.stat().st_size,
                packages=packages_from_pyinstaller_analysis(
                    args.pyinstaller_analysis,
                    project_name=args.project_name,
                    project_version=args.project_version,
                ),
                source_date_epoch=source_date_epoch,
            ),
        )
        return 0
    if args.command == "verify-build-sbom":
        verify_build_sbom(
            artifact=args.artifact,
            sbom=args.sbom,
            build_metadata=args.build_metadata,
        )
        return 0
    if args.command == "sign-update-manifest":
        encoded_key = os.environ.get("DESKTOP_UPDATE_SIGNING_KEY_BASE64", "")
        if not encoded_key:
            raise SystemExit("signing identity not provisioned: desktop update manifest key")
        try:
            private_key_pem = base64.b64decode(encoded_key, validate=True)
        except ValueError as exc:
            raise SystemExit("desktop update signing key is not valid base64") from exc
        _write_json(
            args.output,
            sign_update_manifest(
                artifact=args.artifact,
                sbom=args.sbom,
                metadata=args.metadata,
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
