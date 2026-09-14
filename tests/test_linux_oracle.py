"""Container bootstrap regressions; actual oracle run supplies integration proof."""

import re
import subprocess
import sys
import tomllib
from pathlib import Path

from scripts import linux_oracle


def test_classic_builder_gets_real_dependency_generation():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / linux_oracle.DOCKERFILE).read_text(encoding="utf-8")
    # Execute the actual Docker RUN's Python payload, not a duplicate generator.
    # A classic builder silently ignored the previous Docker-heredoc payload.
    match = re.search(
        r'^RUN python -c "(.+)" > /tmp/oracle/requirements\.txt', dockerfile, re.MULTILINE
    )
    assert match is not None
    payload = match.group(1).replace(
        "'/tmp/oracle/pyproject.toml'", repr((root / "pyproject.toml").as_posix())
    )
    result = subprocess.run(
        [sys.executable, "-c", payload], capture_output=True, text=True, check=True
    )
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert result.stdout.splitlines() == (
        project["dependencies"] + project["optional-dependencies"]["dev"]
    )
    assert result.stdout.strip()
    assert "test -s /tmp/oracle/requirements.txt" in dockerfile
    assert "python -m pytest --version" in dockerfile


def test_snapshot_preserves_container_ownership_without_trusting_host_git():
    assert ".git" in linux_oracle.COPY_EXCLUDES
    assert "tar -C /work --no-same-owner -xf -" in linux_oracle._RUN_SCRIPT
    assert "git init -q ." in linux_oracle._RUN_SCRIPT
    assert "safe.directory" not in linux_oracle._RUN_SCRIPT
