import importlib
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from workflow.utils.fs_extract import FsExtractError, fs_extract

fs_extract_mod = importlib.import_module("workflow.utils.fs_extract")


def test_fs_extract_tar_gz(tmp_path: Path) -> None:
    archive = tmp_path / "assets.tar.gz"
    payload = b"portable assets\n"
    with tarfile.open(archive, "w:gz") as tf:
        info = tarfile.TarInfo("roms/game.txt")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))

    result = fs_extract(archive, tmp_path / "out")

    assert result["format"] == "tar.gz"
    assert result["extractor"] == "python:tarfile"
    assert result["extracted_files"] == ["roms/game.txt"]
    assert (tmp_path / "out" / "roms" / "game.txt").read_text() == "portable assets\n"


def test_fs_extract_joins_split_archive_before_extracting(tmp_path: Path) -> None:
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, "w") as zf:
        zf.writestr("doom/shareware.txt", "joined\n")
    raw = zip_bytes.getvalue()

    first = tmp_path / "doom-shareware.zip.001"
    second = tmp_path / "doom-shareware.zip.002"
    first.write_bytes(raw[: len(raw) // 2])
    second.write_bytes(raw[len(raw) // 2 :])

    result = fs_extract(first, tmp_path / "out")

    assert result["format"] == "zip"
    assert result["joined_from"] == [str(first), str(second)]
    assert result["extracted_files"] == ["doom/shareware.txt"]
    assert (tmp_path / "out" / "doom" / "shareware.txt").read_text() == "joined\n"


def test_fs_extract_rejects_tar_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "bad.tar.gz"
    payload = b"bad\n"
    with tarfile.open(archive, "w:gz") as tf:
        info = tarfile.TarInfo("../escape.txt")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))

    with pytest.raises(FsExtractError, match="escapes destination"):
        fs_extract(archive, tmp_path / "out")

    assert not (tmp_path / "escape.txt").exists()


def test_fs_extract_uses_7z_for_lzh_when_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = tmp_path / "doom.lzh"
    archive.write_bytes(b"not a real lzh; subprocess is patched")
    out = tmp_path / "out"
    calls: list[list[str]] = []

    monkeypatch.setattr(
        fs_extract_mod.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name == "7z" else None,
    )

    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN202
        calls.append(cmd)
        output_arg = next(part for part in cmd if str(part).startswith("-o"))
        staging = Path(output_arg[2:])
        (staging / "DOOM1.WAD").write_text("wad", encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        return Completed()

    monkeypatch.setattr(fs_extract_mod.subprocess, "run", fake_run)

    result = fs_extract(archive, out)

    assert result["format"] == "lzh"
    assert result["extractor"] == "7z"
    assert result["extracted_files"] == ["DOOM1.WAD"]
    assert calls[0][0] == "7z"
    assert (out / "DOOM1.WAD").read_text(encoding="utf-8") == "wad"


def test_fs_extract_detects_extensionless_split_lzh_by_magic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "DOOM19S.1"
    second = tmp_path / "DOOM19S.2"
    first.write_bytes(b"\x00\x00-lh5-")
    second.write_bytes(b"payload")
    out = tmp_path / "out"

    monkeypatch.setattr(
        fs_extract_mod.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name == "7z" else None,
    )

    def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN202
        output_arg = next(part for part in cmd if str(part).startswith("-o"))
        staging = Path(output_arg[2:])
        (staging / "DOOM1.WAD").write_text("wad", encoding="utf-8")

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        return Completed()

    monkeypatch.setattr(fs_extract_mod.subprocess, "run", fake_run)

    result = fs_extract(first, out)

    assert result["format"] == "lzh"
    assert result["joined_from"] == [str(first), str(second)]
    assert result["extracted_files"] == ["DOOM1.WAD"]
