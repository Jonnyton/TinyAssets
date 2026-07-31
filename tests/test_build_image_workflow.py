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
_RECOVERY_RETAG_WORKFLOW = (
    _REPO / ".github" / "workflows" / "recovery-retag-image.yml"
)

pytestmark = pytest.mark.skipif(
    not _YAML_AVAILABLE, reason="pyyaml not installed"
)


def _load() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _text() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


def _load_recovery_retag() -> dict:
    return yaml.safe_load(
        _RECOVERY_RETAG_WORKFLOW.read_text(encoding="utf-8")
    )


def _recovery_retag_text() -> str:
    return _RECOVERY_RETAG_WORKFLOW.read_text(encoding="utf-8")


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


def test_recovery_retag_is_isolated_from_deploy_trigger():
    build_workflow = _load()
    retag_workflow = _load_recovery_retag()

    assert build_workflow["name"] == "Build and publish image"
    assert retag_workflow["name"] != build_workflow["name"]
    assert set(_triggers(retag_workflow)) == {"workflow_dispatch"}


def test_manual_retag_is_digest_and_revision_bound():
    workflow = _load_recovery_retag()
    dispatch = _triggers(workflow).get("workflow_dispatch") or {}
    inputs = dispatch.get("inputs") or {}
    text = _recovery_retag_text()

    assert {"source_digest", "source_revision"} <= set(inputs)
    assert "^sha256:[0-9a-f]{64}$" in text
    assert "^[0-9a-f]{40}$" in text
    assert "org.opencontainers.image.revision" in text
    assert '[[ "${observed_revision}" == "${revision}" ]]' in text
    assert (
        "docker buildx imagetools create --prefer-index=false "
        '--tag "${image}:${revision:0:12}" "${image}@${digest}"'
    ) in text
    assert 'git fetch --no-tags origin "${revision}"' in text
    assert text.index('git fetch --no-tags origin "${revision}"') < text.index(
        'git cat-file -e "${revision}^{commit}"'
    )


def test_manual_retag_skips_image_rebuild():
    build_text = _text()
    retag_text = _recovery_retag_text()

    assert "Retag recorded immutable image" not in build_text
    assert "docker/build-push-action@v6" not in retag_text
    assert "Retag recorded immutable image" in retag_text


def test_build_image_publishes_only_short_sha_tag():
    text = _text()
    assert "${image}:${short_sha}" in text
    assert "${image}:latest" not in text
