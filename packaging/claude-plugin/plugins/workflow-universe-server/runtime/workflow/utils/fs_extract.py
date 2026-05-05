"""Archive extraction helper for runner file-system nodes.

The public entry point is ``fs_extract``. It intentionally returns plain
JSON-serializable data so sandbox runners and MCP-facing helpers can pass the
result through without leaking implementation objects.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class FsExtractError(RuntimeError):
    """Raised when an archive cannot be extracted safely."""


@dataclass(frozen=True, slots=True)
class FsExtractResult:
    """Result returned by :func:`fs_extract`."""

    format: str
    source: str
    destination: str
    extracted_files: list[str]
    joined_from: list[str]
    extractor: str

    def to_dict(self) -> dict[str, object]:
        return {
            "format": self.format,
            "source": self.source,
            "destination": self.destination,
            "extracted_files": list(self.extracted_files),
            "joined_from": list(self.joined_from),
            "extractor": self.extractor,
        }


_SPLIT_RE = re.compile(r"^(?P<base>.+)\.(?P<num>\d{1,3})$")
_SEVEN_ZIP_FORMATS = {".7z"}
_LZH_FORMATS = {".lha", ".lzh"}


def fs_extract(
    source: str | Path,
    destination: str | Path,
    *,
    split_parts: Iterable[str | Path] | None = None,
) -> dict[str, object]:
    """Extract ``source`` into ``destination``.

    Supported directly:
    - ``.zip``
    - ``.tar``, ``.tar.gz``, ``.tgz``

    Supported when an extractor binary is installed:
    - ``.7z`` via ``7z``, ``7zz``, or ``7za``
    - ``.lha`` / ``.lzh`` via ``7z``, ``7zz``, ``7za``, or ``bsdtar``

    Split files can be joined first by passing ``split_parts``. If omitted and
    ``source`` ends in ``.001`` or ``.1``, contiguous sibling parts are joined
    automatically. The joined archive is written to a temporary file and never
    left in the destination.
    """
    src = Path(source)
    dest = Path(destination)
    if not src.exists():
        raise FsExtractError(f"source does not exist: {src}")
    if not src.is_file():
        raise FsExtractError(f"source is not a file: {src}")

    dest.mkdir(parents=True, exist_ok=True)
    joined_from: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="workflow-fs-extract-") as tmp:
        archive = src
        parts = _normalize_split_parts(src, split_parts)
        if parts:
            archive = Path(tmp) / _joined_archive_name(parts[0])
            _join_split_parts(parts, archive)
            joined_from = parts

        fmt = _detect_format(archive, original_name=src.name)
        before = _snapshot_files(dest)
        extractor = _extract_archive(archive, dest, fmt)
        extracted = sorted(
            str(path.relative_to(dest).as_posix())
            for path in _snapshot_files(dest) - before
        )

    return FsExtractResult(
        format=fmt,
        source=str(src),
        destination=str(dest),
        extracted_files=extracted,
        joined_from=[str(part) for part in joined_from],
        extractor=extractor,
    ).to_dict()


def _detect_format(archive: Path, *, original_name: str) -> str:
    lower = archive.name.lower()
    original_lower = original_name.lower()
    for candidate in (lower, original_lower):
        if candidate.endswith((".tar.gz", ".tgz")):
            return "tar.gz"
        if candidate.endswith(".tar"):
            return "tar"
        if candidate.endswith(".zip"):
            return "zip"
        ext = Path(candidate).suffix.lower()
        if ext in _SEVEN_ZIP_FORMATS:
            return "7z"
        if ext in _LZH_FORMATS:
            return "lzh"
    detected = _detect_format_from_magic(archive)
    if detected:
        return detected
    raise FsExtractError(f"unsupported archive format: {original_name}")


def _detect_format_from_magic(archive: Path) -> str:
    with archive.open("rb") as fh:
        header = fh.read(512)
    if header.startswith(b"7z\xbc\xaf'\x1c"):
        return "7z"
    if header.startswith(b"PK\x03\x04"):
        return "zip"
    if len(header) >= 7 and header[2:7].startswith(b"-lh"):
        return "lzh"
    if len(header) >= 265 and header[257:265] in {b"ustar\x00", b"ustar  \x00"}:
        return "tar"
    return ""


def _extract_archive(archive: Path, dest: Path, fmt: str) -> str:
    if fmt in {"tar", "tar.gz"}:
        mode = "r:gz" if fmt == "tar.gz" else "r:"
        with tarfile.open(archive, mode) as tf:
            members = tf.getmembers()
            _validate_tar_members(members, dest)
            tf.extractall(dest, members=members, filter="data")
        return "python:tarfile"

    if fmt == "zip":
        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
            _validate_zip_members(infos, dest)
            zf.extractall(dest)
        return "python:zipfile"

    if fmt in {"7z", "lzh"}:
        return _extract_with_tool(archive, dest, fmt)

    raise FsExtractError(f"unsupported archive format: {fmt}")


def _extract_with_tool(archive: Path, dest: Path, fmt: str) -> str:
    candidates = ["7z", "7zz", "7za"]
    if fmt == "lzh":
        candidates.append("bsdtar")
    tool = next((name for name in candidates if shutil.which(name)), None)
    if tool is None:
        raise FsExtractError(
            f"{fmt} extraction requires one of: {', '.join(candidates)}"
        )

    with tempfile.TemporaryDirectory(prefix="workflow-fs-extract-stage-") as tmp:
        staging = Path(tmp)
        if tool == "bsdtar":
            cmd = [tool, "-xf", str(archive), "-C", str(staging)]
        else:
            cmd = [tool, "x", str(archive), f"-o{staging}", "-y"]
        result = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            tail = detail[-1] if detail else f"exit code {result.returncode}"
            raise FsExtractError(f"{tool} failed to extract {archive.name}: {tail}")
        _move_staged_files(staging, dest)
    return tool


def _normalize_split_parts(
    source: Path,
    split_parts: Iterable[str | Path] | None,
) -> list[Path]:
    if split_parts is not None:
        parts = [Path(part) for part in split_parts]
    else:
        parts = _discover_split_parts(source)
    if not parts:
        return []
    missing = [str(part) for part in parts if not part.is_file()]
    if missing:
        raise FsExtractError(f"split part(s) missing: {', '.join(missing)}")
    return parts


def _discover_split_parts(source: Path) -> list[Path]:
    match = _SPLIT_RE.match(source.name)
    if match is None or int(match.group("num")) != 1:
        return []
    width = len(match.group("num"))
    base = match.group("base")
    parts: list[Path] = []
    index = 1
    while True:
        candidate = source.with_name(f"{base}.{index:0{width}d}")
        if not candidate.exists():
            break
        parts.append(candidate)
        index += 1
    return parts if len(parts) > 1 else []


def _joined_archive_name(first_part: Path) -> str:
    match = _SPLIT_RE.match(first_part.name)
    if match is None:
        return first_part.name
    return match.group("base")


def _join_split_parts(parts: list[Path], destination: Path) -> None:
    with destination.open("wb") as out:
        for part in parts:
            with part.open("rb") as fh:
                shutil.copyfileobj(fh, out)


def _snapshot_files(root: Path) -> set[Path]:
    if not root.exists():
        return set()
    return {path for path in root.rglob("*") if path.is_file()}


def _validate_tar_members(members: list[tarfile.TarInfo], dest: Path) -> None:
    for member in members:
        if member.issym() or member.islnk():
            raise FsExtractError(f"archive contains link member: {member.name}")
        _safe_output_path(dest, member.name)


def _validate_zip_members(members: list[zipfile.ZipInfo], dest: Path) -> None:
    for member in members:
        mode = member.external_attr >> 16
        if (mode & 0o170000) == 0o120000:
            raise FsExtractError(f"archive contains symlink member: {member.filename}")
        _safe_output_path(dest, member.filename)


def _safe_output_path(dest: Path, member_name: str) -> Path:
    target = (dest / member_name).resolve()
    dest_resolved = dest.resolve()
    try:
        target.relative_to(dest_resolved)
    except ValueError as exc:
        raise FsExtractError(f"archive member escapes destination: {member_name}") from exc
    return target


def _move_staged_files(staging: Path, dest: Path) -> None:
    for path in sorted(staging.rglob("*")):
        relative = path.relative_to(staging)
        _safe_output_path(dest, relative.as_posix())
        target = dest / relative
        if path.is_symlink():
            raise FsExtractError(f"archive contains symlink member: {relative}")
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()
        shutil.move(str(path), str(target))
