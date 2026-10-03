"""Shape invariants for .github/workflows/real-browser-proof.yml.

The job exists because every Playwright-gated proof (the custom-UI form cases
in ``tests/test_custom_ui_forms_browser.py``) is SKIPPED by ``required-tests``,
which installs no browser, and a skip is invisible in a green run. Each
assertion pins a property whose loss would turn the job back into decoration
or widen it past cloud-only test infrastructure. The assertion helper it shares
with linux-jail-proof is exercised in ``tests/test_linux_jail_proof_workflow.py``.

PyYAML is imported hard: skipping this file is how the invariants would go quiet.
"""

from __future__ import annotations

import functools
import importlib.util
import re
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parent.parent
_WORKFLOW = _REPO / ".github" / "workflows" / "real-browser-proof.yml"
_SCRIPT = _REPO / "scripts" / "ci_assert_junit_case.py"
_JOB = "real-browser-proof"

_spec = importlib.util.spec_from_file_location("ci_assert_junit_case", _SCRIPT)
assert _spec and _spec.loader
_assert = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_assert)


@functools.cache
def _marked() -> list[str]:
    # Inside tests only: collecting the marked cases imports test modules.
    return _assert.marked_cases(_REPO, "real_browser")


def _load() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _triggers(wf: dict) -> dict:
    return wf[True] if True in wf else wf["on"]


def _job(wf: dict) -> dict:
    assert list(wf["jobs"]) == [_JOB]
    return wf["jobs"][_JOB]


def _step(wf: dict, needle: str) -> dict:
    hits = [s for s in _job(wf)["steps"]
            if needle in (s.get("name") or "") or needle in (s.get("uses") or "")]
    assert len(hits) == 1, f"expected one step matching {needle!r}, got {len(hits)}"
    return hits[0]


def test_triggers_are_pull_request_paths_plus_dispatch_only():
    triggers = _triggers(_load())
    assert set(triggers) == {"pull_request", "workflow_dispatch"}
    paths = triggers["pull_request"]["paths"]
    for required in (
        ".github/workflows/real-browser-proof.yml",
        "scripts/ci_assert_junit_case.py",
        "tinyassets/onboarding/app_ui.js",
        "tinyassets/onboarding/ui_frame.py",
    ):
        assert required in paths, f"{required} must retrigger the proof"


def test_every_literal_trigger_path_exists():
    for path in _triggers(_load())["pull_request"]["paths"]:
        if not any(ch in path for ch in "*?["):
            assert (_REPO / path).exists(), f"trigger path {path} does not exist"


def test_read_only_hosted_and_no_persisted_credentials():
    wf = _load()
    assert wf["permissions"] == {"contents": "read"}
    job = _job(wf)
    assert "permissions" not in job and "environment" not in job
    assert job["runs-on"] == "ubuntu-latest"
    assert _step(wf, "actions/checkout@")["with"]["persist-credentials"] is False
    assert "secrets." not in _WORKFLOW.read_text(encoding="utf-8")


def test_run_blocks_never_interpolate_expressions():
    for step in _job(_load())["steps"]:
        assert "${{" not in (step.get("run") or ""), step.get("name")


def test_the_marker_is_registered_and_carried_by_the_form_proofs():
    pyproject = (_REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert '"real_browser:' in pyproject
    files = {n.split("::")[0] for n in _marked()}
    assert "tests/test_custom_ui_forms_browser.py" in files, files


def test_every_marked_file_retriggers_the_proof():
    paths = set(_triggers(_load())["pull_request"]["paths"])
    for path in sorted({n.split("::")[0] for n in _marked()}):
        assert path in paths, f"{path} carries real_browser but does not retrigger the proof"


def test_the_browser_is_installed_from_the_pinned_extra():
    wf = _load()
    assert "'.[dev,browser]'" in _step(wf, "Install the project")["run"]
    assert "playwright install --with-deps chromium" in (
        _REPO / "docker/linux-oracle.Dockerfile").read_text()
    pyproject = (_REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'browser = \[\s*"playwright==\d+\.\d+\.\d+"', pyproject)


def test_assertion_step_always_runs_over_the_marker():
    wf = _load()
    step = _step(wf, "Assert every real-browser case")
    assert step["if"] == "always()"
    assert "--marker real_browser" in step["run"]
    run_step = _step(wf, "Run the real-browser proofs")
    assert "-m real_browser" in run_step["run"]
    assert step["env"]["JUNIT_PATH"] == run_step["env"]["OUT_DIR"] + "/junit-real-browser.xml"


def test_junit_uploaded_even_on_failure():
    step = _step(_load(), "Upload junit")
    assert step["if"] == "always()"
    assert step["with"]["path"].endswith("/junit-real-browser.xml")


def test_not_the_required_context():
    assert _job(_load())["name"] == _JOB != "required-tests"


def test_preview_dependency_has_no_privileged_install_or_fallback():
    wf = _load()
    steps = _job(wf)["steps"]
    profile = _step(wf, "Allow user namespaces for the jail container only")
    jail = yaml.safe_load((_REPO / ".github/workflows/linux-jail-proof.yml").read_text())
    expected = next(s for s in jail["jobs"]["linux-jail-proof"]["steps"]
                    if s.get("name") == profile["name"])
    assert profile == expected
    assert "if" not in profile and not profile.get("continue-on-error", False)
    assert steps.index(profile) < steps.index(_step(wf, "Run the real-browser proofs"))
    assert "scripts/ci_bwrap_dependency.py" in _triggers(wf)["pull_request"]["paths"]
    assert all("ci_bwrap_dependency.py" not in s.get("run", "") for s in steps)
    for name in ("Run the real-browser proofs", "Run the complete preview containment module"):
        run = _step(wf, name)["run"]
        assert 'python scripts/linux_oracle.py --out "$OUT_DIR" --apparmor ta-jail-userns' in run
        assert "--env TINYASSETS_DATA_DIR=/tmp/ta-data" in run
        assert "--no-bwrap" not in run and "--as-root" not in run
        assert "|| true" not in run
    assert "sysctl" not in _WORKFLOW.read_text()
    assert "--privileged" not in _WORKFLOW.read_text()


def test_complete_preview_module_is_executed_and_every_collected_case_asserted():
    run = _step(_load(), "Run the complete preview containment module")
    assert "-- tests/test_ui_preview.py -q" in run["run"]
    pytest_args = run["run"].split("-- tests/test_ui_preview.py", 1)[1]
    assert " -m " not in pytest_args and " -k " not in pytest_args
    assert "|| true" not in run["run"] and not run.get("continue-on-error", False)
    check = _step(_load(), "Assert every preview case executed")
    assert check["if"] == "always()"
    assert "tests/test_ui_preview.py --collect-only" in check["run"]
    assert '"${#cases[@]}" -eq 0' in check["run"]
    assert 'args+=(--nodeid "$case")' in check["run"]
    assert 'ci_assert_junit_case.py --junit "$JUNIT_PATH"' in check["run"]
    assert check["env"]["JUNIT_PATH"] == run["env"]["OUT_DIR"] + "/junit-preview.xml"
    artifact = _step(_load(), "Upload preview junit")
    assert artifact["if"] == "always()"
    assert artifact["with"]["path"].endswith("/junit-preview.xml")


def test_approved_trial_is_branch_isolated_and_records_the_actual_image():
    job = _job(_load())
    assert job["if"] == (
        "(github.event_name == 'pull_request' && "
        "github.head_ref == 'codex/cloud-4316-approved-oracle-trial-20261003') || "
        "(github.event_name == 'workflow_dispatch' && "
        "github.ref_name == 'codex/cloud-4316-approved-oracle-trial-20261003')"
    )
    step = _step(_load(), "Build and record the approved oracle image")
    assert 'docker image inspect "$tag"' in step["run"]
    assert 'docker build -f docker/linux-oracle.Dockerfile -t "$tag" .' in step["run"]
    assert "oracle._image_tag(Path.cwd())" in step["run"]
    assert "oracle.docker_command" in step["run"] and "oracle.ORACLE_UID" in step["run"]
    assert "continue-on-error" not in step
