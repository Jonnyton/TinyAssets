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


# --- skip the image (and so the recreate) when production already serves it --

_DEPLOY_WORKFLOW = _REPO / ".github" / "workflows" / "deploy-prod.yml"
_HOST_WORKFLOW = _REPO / ".github" / "workflows" / "install-host-services.yml"


def _step(job: str, name: str) -> dict:
    steps = _load()["jobs"][job]["steps"]
    return next(step for step in steps if step.get("name") == name)


def test_every_published_image_passes_through_the_runtime_decision():
    jobs = _load()["jobs"]
    build = jobs["build-and-push"]
    assert build["needs"] == "decide"
    # Anything but an explicit skip builds.
    assert build["if"] == "needs.decide.outputs.decision != 'skip'"
    assert jobs["decide"]["outputs"]["decision"] == "${{ steps.decide.outputs.decision }}"


def test_write_permissions_are_scoped_to_the_job_that_needs_them():
    workflow = _load()
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["decide"]["permissions"] == {
        "contents": "read",
        "actions": "write",
    }
    assert workflow["jobs"]["build-and-push"]["permissions"] == {
        "contents": "read",
        "packages": "write",
    }


def test_decision_reads_the_served_sha_from_the_protected_receipt():
    served = _step("decide", "Read the sha production serves")
    assert served["if"] == "github.event_name == 'push'"
    assert "python scripts/deployed_sha.py --json" in served["run"]
    assert "TINYASSETS_WIKI_CANARY_TOKEN" in served["env"]
    checkout = _load()["jobs"]["decide"]["steps"][0]
    assert checkout["with"]["fetch-depth"] == 0


def test_skip_cancels_the_run_and_fails_loudly_if_the_cancel_never_lands():
    """deploy-prod and install-host-services run only on SUCCESS, so a
    cancelled (or failed) build deploys and recreates nothing."""
    cancel = _step("decide", "Cancel this run -- production already serves this runtime")
    assert cancel["if"] == "steps.decide.outputs.decision == 'skip'"
    assert 'gh run cancel "${GITHUB_RUN_ID}"' in cancel["run"]
    assert cancel["run"].rstrip().endswith("exit 1")

    for path in (_DEPLOY_WORKFLOW, _HOST_WORKFLOW):
        wf = yaml.safe_load(path.read_text(encoding="utf-8"))
        job = next(iter(wf["jobs"].values()))
        assert "github.event.workflow_run.conclusion == 'success'" in job["if"], path.name


def _run_decide_step(tmp_path, *, event, served, head, crash_script=None):
    import os
    import shutil
    import subprocess
    import sys

    bash = (
        "C:/Program Files/Git/bin/bash.exe"
        if Path("C:/Program Files/Git/bin/bash.exe").exists()
        else shutil.which("bash")
    )
    if not bash:
        pytest.skip("bash is required to execute the decide step")
    out = tmp_path / "gh-output"
    python = Path(sys.executable).as_posix()
    if crash_script is None:
        shim = f'python() {{ "{python}" "$@"; }}\n'
    else:
        # The real interpreter, running a classifier that dies mid-decision.
        shim = f'python() {{ "{python}" "{Path(crash_script).as_posix()}"; }}\n'
    script = shim + _step("decide", "Decide")["run"]
    result = subprocess.run(
        [bash, "-s"],
        cwd=_REPO,
        input=script,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "EVENT_NAME": event,
            "SERVED_SHA": served,
            "GITHUB_SHA": head,
            "GITHUB_OUTPUT": out.as_posix(),
        },
    )
    assert result.returncode == 0, result.stderr
    values = dict(
        line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines()
    )
    return values


def test_decide_step_skips_a_head_production_already_serves(tmp_path):
    import subprocess

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=_REPO, capture_output=True, text=True, check=True
    ).stdout.strip()
    values = _run_decide_step(tmp_path, event="push", served=head, head=head)
    assert values["decision"] == "skip"


def test_decide_step_builds_on_manual_dispatch_and_unknown_receipt(tmp_path):
    import subprocess

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=_REPO, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert _run_decide_step(
        tmp_path, event="workflow_dispatch", served=head, head=head
    )["decision"] == "build"
    assert _run_decide_step(tmp_path, event="push", served="", head=head)["decision"] == "build"


def test_decide_step_builds_when_the_classifier_crashes(tmp_path):
    crash = tmp_path / "crash.py"
    crash.write_text("raise RuntimeError('classifier died')\n", encoding="utf-8")
    values = _run_decide_step(
        tmp_path, event="push", served="a" * 40, head="HEAD", crash_script=crash
    )
    assert values["decision"] == "build"
    assert values["reason"] == "runtime classifier failed"
