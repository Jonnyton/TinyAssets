"""Tests for probe_env_readability — bootstrap env-file mode check.

Closes the 2026-04-22 STATUS.md Concern:
  /etc/tinyassets/env mode flip root cause unknown; audit deploy/bootstrap
  so compose does not lose readable env again.

Structural fix: the probe runs at daemon startup and emits a loud
WARNING with mode bits + fix command if the file is unreadable.

All tests use a tmp_path file to avoid touching the real /etc/tinyassets/env.
"""

from __future__ import annotations

import pytest

from tinyassets.storage import probe_env_readability


class TestProbeEnvReadability:
    def test_readable_file_returns_true(self, tmp_path):
        env_file = tmp_path / "tinyassets.env"
        env_file.write_text("KEY=value\n")
        env_file.chmod(0o644)
        assert probe_env_readability(env_file) is True

    def test_missing_file_returns_true(self, tmp_path):
        env_file = tmp_path / "nonexistent.env"
        assert probe_env_readability(env_file) is True

    @pytest.mark.skipif(
        __import__("os").name == "nt",
        reason="chmod 000 permission denial not enforced on Windows",
    )
    def test_unreadable_file_returns_false(self, tmp_path):
        env_file = tmp_path / "tinyassets.env"
        env_file.write_text("KEY=value\n")
        env_file.chmod(0o000)
        try:
            result = probe_env_readability(env_file)
            assert result is False
        finally:
            env_file.chmod(0o644)

    @pytest.mark.skipif(
        __import__("os").name == "nt",
        reason="chmod 000 permission denial not enforced on Windows",
    )
    def test_unreadable_file_emits_warning(self, tmp_path, caplog):
        import logging
        env_file = tmp_path / "tinyassets.env"
        env_file.write_text("KEY=value\n")
        env_file.chmod(0o000)
        try:
            with caplog.at_level(logging.WARNING, logger="tinyassets.storage"):
                probe_env_readability(env_file)
            assert any(
                "readable" in r.message.lower() or "mode" in r.message.lower()
                for r in caplog.records
                if r.levelno >= logging.WARNING
            ), f"Expected a WARNING about readability; got: {[r.message for r in caplog.records]}"
        finally:
            env_file.chmod(0o644)

    @pytest.mark.skipif(
        __import__("os").name == "nt",
        reason="chmod 000 permission denial not enforced on Windows",
    )
    def test_warning_includes_fix_command(self, tmp_path, caplog):
        import logging
        env_file = tmp_path / "tinyassets.env"
        env_file.write_text("KEY=value\n")
        env_file.chmod(0o000)
        try:
            with caplog.at_level(logging.WARNING, logger="tinyassets.storage"):
                probe_env_readability(env_file)
            combined = " ".join(r.message for r in caplog.records)
            assert "chmod" in combined, (
                "Warning must include the fix command ('chmod') so the operator "
                f"can recover without hunting docs. Got: {combined!r}"
            )
        finally:
            env_file.chmod(0o644)

    def test_readable_file_no_warning_emitted(self, tmp_path, caplog):
        import logging
        env_file = tmp_path / "tinyassets.env"
        env_file.write_text("KEY=value\n")
        env_file.chmod(0o644)
        with caplog.at_level(logging.WARNING, logger="tinyassets.storage"):
            probe_env_readability(env_file)
        assert not caplog.records, (
            "No warning should be emitted for a readable env file"
        )

    def test_missing_file_no_warning_emitted(self, tmp_path, caplog):
        import logging
        env_file = tmp_path / "nonexistent.env"
        with caplog.at_level(logging.WARNING, logger="tinyassets.storage"):
            probe_env_readability(env_file)
        assert not caplog.records, (
            "No warning should be emitted for a missing env file"
        )
