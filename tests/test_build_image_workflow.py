"""Tests for the production image workflow trigger shape."""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import yaml

    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

_REPO = Path(__file__).resolve().parent.parent
_WORKFLOW = _REPO / ".github" / "workflows" / "build-image.yml"

pytestmark = pytest.mark.skipif(
    not _YAML_AVAILABLE, reason="pyyaml not installed"
)


def _load() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _text() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


def _triggers(wf: dict) -> dict:
    return wf.get(True, {}) or {}


def test_build_image_push_is_limited_to_runtime_paths():
    """Docs/site/status-only pushes must not restart the production daemon."""

    triggers = _triggers(_load())
    push = triggers.get("push") or {}
    paths = set(push.get("paths") or [])

    assert paths, "build-image push trigger must use positive runtime paths"
    assert "STATUS.md" not in paths
    assert "docs/**" not in paths
    assert "WebSite/**" not in paths
    assert ".github/workflows/build-image.yml" not in paths

    for required in {
        "Dockerfile",
        ".dockerignore",
        "pyproject.toml",
        "PLAN.md",
        "workflow/**",
        "domains/**",
        "fantasy_daemon/**",
        "data/world_rules.lp",
        "scripts/mcp_public_canary.py",
        "deploy/**",
    }:
        assert required in paths


def test_build_image_keeps_manual_dispatch():
    triggers = _triggers(_load())
    assert "workflow_dispatch" in triggers


def test_build_image_publishes_only_short_sha_tag():
    text = _text()
    assert "${image}:${short_sha}" in text
    assert "${image}:latest" not in text
