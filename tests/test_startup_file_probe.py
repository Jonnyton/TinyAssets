"""BUG-027 — startup_file_probe detects missing required data files.

Guards:
- startup_file_probe() returns [] when all required files exist.
- startup_file_probe() returns the relative path when a required file is absent.
- startup_file_probe() logs a WARNING when a file is missing.
- get_status() includes missing_data_files field (empty list in a normal checkout).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path


class TestStartupFileProbe:
    def test_returns_empty_when_all_present(self, tmp_path: Path):
        from tinyassets.storage.rotation import _REQUIRED_DATA_FILES, startup_file_probe

        for rel in _REQUIRED_DATA_FILES:
            full = tmp_path / rel
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text("% dummy lp\n")

        result = startup_file_probe(package_root=tmp_path)
        assert result == []

    def test_returns_missing_path_when_absent(self, tmp_path: Path):
        from tinyassets.storage.rotation import startup_file_probe

        result = startup_file_probe(package_root=tmp_path)
        assert "data/world_rules.lp" in result

    def test_logs_warning_when_file_missing(self, tmp_path: Path, caplog):
        from tinyassets.storage.rotation import startup_file_probe

        with caplog.at_level(logging.WARNING, logger="tinyassets.storage.rotation"):
            startup_file_probe(package_root=tmp_path)

        assert any("missing" in m.lower() for m in caplog.messages)

    def test_no_warning_when_all_present(self, tmp_path: Path, caplog):
        from tinyassets.storage.rotation import _REQUIRED_DATA_FILES, startup_file_probe

        for rel in _REQUIRED_DATA_FILES:
            full = tmp_path / rel
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text("% present\n")

        with caplog.at_level(logging.WARNING, logger="tinyassets.storage.rotation"):
            startup_file_probe(package_root=tmp_path)

        assert not any("missing" in m.lower() for m in caplog.messages)

    def test_default_root_finds_real_checkout(self):
        """In a normal checkout, world_rules.lp exists → probe returns []."""
        from tinyassets.storage.rotation import startup_file_probe

        result = startup_file_probe()
        assert result == [], (
            f"Expected no missing data files in checkout, got: {result}"
        )

    def test_required_files_list_is_non_empty(self):
        from tinyassets.storage.rotation import _REQUIRED_DATA_FILES

        assert len(_REQUIRED_DATA_FILES) >= 1
        assert "data/world_rules.lp" in _REQUIRED_DATA_FILES


class TestGetStatusMissingDataFiles:
    def test_missing_data_files_in_get_status(self, tmp_path, monkeypatch):
        """get_status includes missing_data_files key."""
        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
        (tmp_path / "default-universe").mkdir()

        from tinyassets.universe_server import get_status
        raw = get_status("default-universe")
        payload = json.loads(raw)

        assert "missing_data_files" in payload
        assert isinstance(payload["missing_data_files"], list)

    def test_missing_data_files_empty_in_checkout(self, tmp_path, monkeypatch):
        """In a normal checkout, no data files are missing."""
        monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
        (tmp_path / "default-universe").mkdir()

        from tinyassets.universe_server import get_status
        raw = get_status("default-universe")
        payload = json.loads(raw)

        assert payload["missing_data_files"] == [], (
            f"Expected empty missing_data_files in checkout: {payload['missing_data_files']}"
        )
