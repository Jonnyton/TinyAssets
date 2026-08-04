"""Content-addressed inputs for requester-owned cloud automations."""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path, PurePosixPath

_MAX_ACCEPTED_SPEC_BYTES = 2 * 1024 * 1024


def validate_accepted_spec_ref(value: str) -> str:
    """Return a safe repository-relative POSIX path."""
    clean = value.strip()
    path = PurePosixPath(clean)
    if (
        not clean
        or "\\" in clean
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != clean
    ):
        raise ValueError("accepted_spec_ref must be a repository-relative POSIX path")
    return clean


def _digest(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _artifact_path(base_path: str | Path, digest: str) -> Path:
    prefix, separator, hexdigest = digest.partition(":")
    if prefix != "sha256" or separator != ":" or len(hexdigest) != 64:
        raise ValueError("accepted spec digest must be a sha256 digest")
    return Path(base_path) / "cloud-automation-inputs" / hexdigest


def stage_accepted_spec(
    base_path: str | Path,
    *,
    accepted_spec_ref: str,
    content: str,
    expected_digest: str,
) -> Path:
    """Verify and atomically retain an accepted spec supplied by its owner."""
    validate_accepted_spec_ref(accepted_spec_ref)
    if not isinstance(content, str):
        raise ValueError("accepted_spec_content must be text")
    encoded = content.encode("utf-8")
    if len(encoded) > _MAX_ACCEPTED_SPEC_BYTES:
        raise ValueError("accepted_spec_content exceeds 2 MiB")
    if _digest(encoded) != expected_digest:
        raise ValueError("accepted spec digest does not match accepted_spec_content")
    target = _artifact_path(base_path, expected_digest)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if _digest(target.read_bytes()) != expected_digest:
            raise ValueError("stored accepted spec digest does not match its identity")
        return target
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(encoded)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def load_accepted_spec(
    base_path: str | Path,
    *,
    accepted_spec_ref: str,
    expected_digest: str,
) -> bytes:
    """Resolve and re-hash the immutable accepted spec or fail closed."""
    validate_accepted_spec_ref(accepted_spec_ref)
    target = _artifact_path(base_path, expected_digest)
    if not target.is_file():
        raise ValueError("accepted spec artifact is unavailable")
    content = target.read_bytes()
    if _digest(content) != expected_digest:
        raise ValueError("stored accepted spec digest does not match its identity")
    return content


__all__ = [
    "load_accepted_spec",
    "stage_accepted_spec",
    "validate_accepted_spec_ref",
]
