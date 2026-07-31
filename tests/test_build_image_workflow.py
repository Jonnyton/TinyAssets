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
        "tinyassets/**",
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


def test_manual_retag_is_digest_and_revision_bound():
    workflow = _load()
    dispatch = _triggers(workflow).get("workflow_dispatch") or {}
    inputs = dispatch.get("inputs") or {}
    text = _text()

    assert {"source_digest", "source_revision"} <= set(inputs)
    assert "^sha256:[0-9a-f]{64}$" in text
    assert "^[0-9a-f]{40}$" in text
    assert "org.opencontainers.image.revision" in text
    assert '[[ "${observed_revision}" == "${revision}" ]]' in text
    assert (
        'docker buildx imagetools create --tag "${image}:${revision:0:12}" '
        '"${image}@${digest}"'
    ) in text


def test_manual_retag_skips_image_rebuild():
    workflow = _load()
    steps = workflow["jobs"]["build-and-push"]["steps"]
    by_name = {step.get("name"): step for step in steps}

    assert (
        by_name["Build and push image"]["if"]
        == "inputs.source_digest == '' && inputs.source_revision == ''"
    )
    assert (
        by_name["Retag recorded immutable image"]["if"]
        == "inputs.source_digest != '' || inputs.source_revision != ''"
    )


def test_build_image_publishes_only_short_sha_tag():
    text = _text()
    assert "${image}:${short_sha}" in text
    assert "${image}:latest" not in text
