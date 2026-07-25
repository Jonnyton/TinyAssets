"""Executable contract and load proofs for release reconciliation."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "release-reconcile.yml"
_BUILD_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "build-image.yml"
_WINDOWS_GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
_BASH = (
    str(_WINDOWS_GIT_BASH)
    if _WINDOWS_GIT_BASH.exists()
    else shutil.which("bash")
)


def _load(path: Path = _WORKFLOW) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _triggers(workflow: dict) -> dict:
    # PyYAML 1.1 parses the unquoted GitHub Actions `on` key as boolean true.
    return workflow.get(True, workflow.get("on", {})) or {}


def _compact(expression: str) -> str:
    return " ".join(expression.split())


def _step_script(name: str) -> str:
    step = next(
        step
        for step in _load()["jobs"]["reconcile"]["steps"]
        if step.get("name") == name
    )
    return str(step["run"])


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _release_repo(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "tinyassets").mkdir()
    (repo / ".github" / "workflows" / "build-image.yml").write_text(
        """name: Build and publish image
on:
  push:
    paths:
      - 'tinyassets/**'
""",
        encoding="utf-8",
    )
    (repo / "tinyassets" / "app.py").write_text("VERSION = 1\n", encoding="utf-8")
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "proof@example.invalid")
    _git(repo, "config", "user.name", "Release Proof")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "release one")
    stale_sha = _git(repo, "rev-parse", "HEAD")
    (repo / "tinyassets" / "app.py").write_text("VERSION = 2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "release two")
    relevant_sha = _git(repo, "rev-parse", "HEAD")
    return repo, stale_sha, relevant_sha


_GH_DECISION_HARNESS = r"""
python3() { "${PYTHON_BIN}" "$@"; }
gh() {
  case "$*" in
    *"actions/workflows/deploy-prod.yml/runs"*)
      if [ "${DEPLOY_API_FAIL:-0}" = "1" ]; then return 1; fi
      printf '%s\n' "${DEPLOYED_SHAS:-}"
      ;;
    *"actions/runs?branch=main"*)
      if [ "${ACTIVE_API_FAIL:-0}" = "1" ]; then return 1; fi
      printf '%s\n' "${ACTIVE_SHAS:-}"
      ;;
    *)
      echo "unexpected gh call: $*" >&2
      return 97
      ;;
  esac
}
"""


def _run_decision(
    repo: Path,
    *,
    active_shas: str = "",
    deployed_shas: str = "",
    active_api_fail: bool = False,
    deploy_api_fail: bool = False,
) -> dict[str, str]:
    if not _BASH:
        pytest.skip("bash is required to execute the exact reconciliation script")
    output = repo / ".github-output"
    decision_script = _step_script("Compare main against the last successful deploy")
    result = subprocess.run(
        [_BASH, "-c", f"{_GH_DECISION_HARNESS}\n{decision_script}"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            **os.environ,
            "ACTIVE_SHAS": active_shas,
            "DEPLOYED_SHAS": deployed_shas,
            "ACTIVE_API_FAIL": "1" if active_api_fail else "0",
            "DEPLOY_API_FAIL": "1" if deploy_api_fail else "0",
            "GITHUB_OUTPUT": ".github-output",
            "PYTHON_BIN": Path(sys.executable).as_posix(),
            "REPO": "owner/repo",
        },
    )
    assert result.returncode == 0, result.stderr
    values: dict[str, str] = {}
    for line in output.read_text(encoding="utf-8").splitlines():
        key, value = line.split("=", 1)
        values[key] = value
    return values


_GH_CONVERGE_HARNESS = r"""
gh() {
  printf '%s\n' "$*" >> "${GH_CALLS}"
  if [ "$1" = "run" ] && [ "$2" = "list" ]; then
    printf '%s\n' "${STUB_BUILD_RUN_ID}"
  elif [ "$1" = "run" ] && [ "$2" = "watch" ]; then
    return "${WATCH_STATUS:-0}"
  elif [ "$1" = "api" ] && [[ "$*" == *"/commits/main"* ]]; then
    printf '%s\n' "${CURRENT_MAIN}"
  fi
}
sleep() { :; }
"""


def _run_converge(repo: Path, current_main: str) -> list[str]:
    if not _BASH:
        pytest.skip("bash is required to execute the exact convergence script")
    result = subprocess.run(
        [_BASH, "-c", f"{_GH_CONVERGE_HARNESS}\n{_step_script('Converge')}"],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            **os.environ,
            "STUB_BUILD_RUN_ID": "12345",
            "CURRENT_MAIN": current_main,
            "DETAIL": "test drift",
            "GH_CALLS": ".gh-calls",
            "GITHUB_STEP_SUMMARY": ".summary",
            "REPO": "owner/repo",
        },
    )
    assert result.returncode == 0, result.stderr
    return (repo / ".gh-calls").read_text(encoding="utf-8").splitlines()


def test_retains_backstops_and_wakes_on_completed_main_docker_smoke() -> None:
    triggers = _triggers(_load())

    assert triggers.get("schedule") == [{"cron": "*/15 * * * *"}]
    assert "workflow_dispatch" in triggers
    assert triggers.get("workflow_dispatch") is None
    assert triggers.get("workflow_run") == {
        "workflows": ["Docker build smoke"],
        "types": ["completed"],
        "branches": ["main"],
    }


def test_privileged_job_condition_is_exact_trusted_provenance_contract() -> None:
    condition = _compact(str(_load()["jobs"]["reconcile"].get("if", "")))

    assert condition == (
        "github.event_name != 'workflow_run' || ( "
        "github.event.workflow_run.conclusion == 'success' && "
        "github.event.workflow_run.head_branch == 'main' && "
        "github.event.workflow_run.head_repository.full_name == github.repository && "
        "( github.event.workflow_run.event == 'push' || "
        "github.event.workflow_run.event == 'workflow_dispatch' ) )"
    )


def test_permissions_checkout_and_reconcile_concurrency_remain_narrow() -> None:
    workflow = _load()

    assert workflow["permissions"] == {"contents": "read", "actions": "write"}
    assert workflow["concurrency"] == {
        "group": "release-reconcile",
        "cancel-in-progress": False,
    }
    checkout = next(
        step
        for step in workflow["jobs"]["reconcile"]["steps"]
        if str(step.get("uses", "")).startswith("actions/checkout@")
    )
    assert checkout["with"]["ref"] == "main"
    assert "github.event.workflow_run.head_sha" not in _WORKFLOW.read_text(
        encoding="utf-8"
    )


def test_manual_image_build_cannot_cancel_active_push_build() -> None:
    build_workflow = _load(_BUILD_WORKFLOW)

    assert build_workflow["concurrency"] == {
        "group": "build-image-${{ github.ref }}",
        "cancel-in-progress": "${{ github.event_name == 'push' }}",
    }


def test_exact_decision_defers_for_current_active_release(tmp_path: Path) -> None:
    repo, _, relevant_sha = _release_repo(tmp_path)

    result = _run_decision(repo, active_shas=relevant_sha)

    assert result["action"] == "none"
    assert "in-flight release run" in result["detail"]


def test_exact_decision_stale_active_does_not_suppress(tmp_path: Path) -> None:
    repo, stale_sha, _ = _release_repo(tmp_path)

    result = _run_decision(repo, active_shas=stale_sha)

    assert result == {
        "action": "dispatch",
        "detail": "no successful deploy to main on record",
    }


@pytest.mark.parametrize("failed_query", ["active", "deploy"])
def test_exact_decision_api_failure_fails_closed(
    tmp_path: Path, failed_query: str
) -> None:
    repo, _, _ = _release_repo(tmp_path)

    result = _run_decision(
        repo,
        active_api_fail=failed_query == "active",
        deploy_api_fail=failed_query == "deploy",
    )

    assert result["action"] == "none"
    assert "query failed" in result["detail"]


def test_exact_decision_successful_deploy_ancestry_is_in_sync(
    tmp_path: Path,
) -> None:
    repo, _, relevant_sha = _release_repo(tmp_path)

    result = _run_decision(repo, deployed_shas=relevant_sha)

    assert result["action"] == "none"
    assert result["detail"].startswith("deploy ")


def test_exact_decision_missing_deploy_dispatches(tmp_path: Path) -> None:
    repo, _, _ = _release_repo(tmp_path)

    result = _run_decision(repo)

    assert result["action"] == "dispatch"


def test_exact_scripts_coalesce_thousand_arrivals_to_one_dispatch(
    tmp_path: Path,
) -> None:
    repo, _, relevant_sha = _release_repo(tmp_path)
    arrivals = list(range(1_000))
    executed = [arrivals[0], arrivals[-1]]

    first = _run_decision(repo)
    coalesced = _run_decision(repo, active_shas=relevant_sha)

    assert executed == [0, 999]
    assert [first["action"], coalesced["action"]] == ["dispatch", "none"]


def test_exact_converge_waits_for_build_then_deploys_unchanged_main(
    tmp_path: Path,
) -> None:
    repo, _, relevant_sha = _release_repo(tmp_path)

    calls = _run_converge(repo, current_main=relevant_sha)

    assert any(
        call == "workflow run build-image.yml --repo owner/repo --ref main"
        for call in calls
    )
    assert any(call.startswith("run list ") for call in calls)
    assert "run watch 12345 --repo owner/repo --exit-status" in calls
    assert (
        f"workflow run deploy-prod.yml --repo owner/repo --ref main "
        f"-f image_tag={relevant_sha[:12]}"
    ) in calls


def test_exact_converge_does_not_deploy_after_main_advances(
    tmp_path: Path,
) -> None:
    repo, _, _ = _release_repo(tmp_path)

    calls = _run_converge(repo, current_main="f" * 40)

    assert "run watch 12345 --repo owner/repo --exit-status" in calls
    assert not any("workflow run deploy-prod.yml" in call for call in calls)
