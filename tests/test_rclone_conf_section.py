"""scripts/rclone_conf_section.py installs [offregion] without touching [spaces]."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "rclone_conf_section.py"
sys.path.insert(0, str(REPO / "scripts"))

import rclone_conf_section as rcs  # noqa: E402

SPACES = "[spaces]\ntype = s3\naccess_key_id = AAA\nendpoint = sfo3.digitaloceanspaces.com\n"
OFFREGION = "[offregion]\ntype = s3\naccess_key_id = BBB\nendpoint = nyc3.digitaloceanspaces.com\n"


def test_add_keeps_every_other_section_byte_for_byte():
    out = rcs.add(SPACES, OFFREGION)
    assert out.startswith(SPACES)
    assert out.rstrip().endswith("endpoint = nyc3.digitaloceanspaces.com")
    assert out.count("[offregion]") == 1


def test_add_replaces_a_same_named_section():
    once = rcs.add(SPACES, OFFREGION)
    twice = rcs.add(once, OFFREGION.replace("BBB", "CCC"))
    assert twice.count("[offregion]") == 1
    assert "CCC" in twice and "BBB" not in twice
    assert SPACES in twice


def test_remove_drops_only_the_named_section():
    out = rcs.remove(rcs.add(SPACES, OFFREGION), "offregion")
    assert "[offregion]" not in out
    assert out.strip() == SPACES.strip()


def test_a_section_file_must_hold_exactly_one_section():
    with pytest.raises(ValueError):
        rcs.add(SPACES, OFFREGION + SPACES)
    with pytest.raises(ValueError):
        rcs.add(SPACES, "type = s3\n")


def test_cli_writes_0600_and_remove_of_a_missing_file_is_a_no_op(tmp_path):
    conf = tmp_path / "rclone.conf"
    conf.write_text(SPACES, encoding="utf-8")
    section = tmp_path / "offregion.section"
    section.write_text(OFFREGION, encoding="utf-8")
    subprocess.run([sys.executable, str(SCRIPT), "add", str(conf), str(section)], check=True)
    assert "[offregion]" in conf.read_text(encoding="utf-8")
    if os.name != "nt":
        assert stat.S_IMODE(conf.stat().st_mode) == 0o600
    missing = tmp_path / "absent.conf"
    subprocess.run([sys.executable, str(SCRIPT), "remove", str(missing), "offregion"], check=True)
    assert not missing.exists()


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_refuses_to_write_through_a_symlink(tmp_path):
    target = tmp_path / "elsewhere"
    target.write_text(SPACES, encoding="utf-8")
    link = tmp_path / "rclone.conf"
    link.symlink_to(target)
    section = tmp_path / "s"
    section.write_text(OFFREGION, encoding="utf-8")
    result = subprocess.run([sys.executable, str(SCRIPT), "add", str(link), str(section)],
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert target.read_text(encoding="utf-8") == SPACES


def test_untouched_crlf_sections_survive_byte_for_byte(tmp_path):
    conf = tmp_path / "rclone.conf"
    original = SPACES.replace("\n", "\r\n").encode("utf-8")
    conf.write_bytes(original)
    section = tmp_path / "s"
    section.write_text(OFFREGION, encoding="utf-8")
    subprocess.run([sys.executable, str(SCRIPT), "add", str(conf), str(section)], check=True)
    assert conf.read_bytes().startswith(original)


def test_headers_are_recognised_the_way_rclone_trims_them():
    """goconfig trims whitespace around a header and its name (Codex on #4279)."""
    messy = SPACES + "  [ offregion ]  \ntype = s3\naccess_key_id = OLD\n"
    out = rcs.add(messy, OFFREGION)
    assert out.count("offregion") == 1, "the messy spelling must be replaced, not duplicated"
    assert "OLD" not in out
    assert rcs.remove(messy, "offregion").strip() == SPACES.strip()


def test_removing_offregion_keeps_an_indented_spaces_section():
    conf = OFFREGION + " [spaces]\ntype = s3\n"
    out = rcs.remove(conf, "offregion")
    assert "[spaces]" in out and "type = s3" in out
