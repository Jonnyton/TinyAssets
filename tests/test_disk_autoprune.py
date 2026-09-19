"""Both historical cleanup entrypoints use the same safe retention command."""

import subprocess
import sys
from pathlib import Path

from scripts import disk_autoprune

ROOT = Path(__file__).resolve().parents[1]


def test_compatibility_entrypoint_is_shared_main():
    from scripts.daemon_image_retention import main

    assert disk_autoprune.main is main


def test_help_does_not_touch_docker_or_network():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/disk_autoprune.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0
    assert "--apply" in result.stdout


def test_both_cleanup_units_are_bounded_and_preserve_rotation():
    for name in ("tinyassets-prune.service", "tinyassets-disk-watch.service"):
        source = (ROOT / "deploy" / name).read_text()
        assert "scripts/disk_autoprune.py --apply" in source
        assert "EnvironmentFile=/etc/tinyassets/env" in source
        assert "WorkingDirectory=/opt/tinyassets-host-uptime/current" in source
        assert "TimeoutStartSec=180s" in source
        directives = "\n".join(line for line in source.splitlines() if not line.startswith("#"))
        for forbidden in ("system prune", "image prune", "builder prune", "journalctl", "--force"):
            assert forbidden not in directives
    source = (ROOT / "deploy/tinyassets-disk-watch.service").read_text()
    assert "ExecStart=/usr/bin/python3 -m scripts.rotate_run_transcripts" in source
