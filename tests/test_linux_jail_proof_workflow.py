"""Shape invariants for .github/workflows/linux-jail-proof.yml.

The job exists because `required-tests` records every bwrap-gated jail proof
(`tests/test_delivery_node_rpc.py::test_real_linux_jail_transports_delivery_rpc`
and the codex coding-turn cases in `tests/test_native_refresh_jail.py`) as
SKIPPED (no bubblewrap on the hosted image), and a skip is invisible in a green
run. Each assertion here pins a property whose loss would turn the job
back into decoration or widen it past "cloud-only test infrastructure":

  - it fires on PRs touching the jail/delivery slice and on manual dispatch,
    nothing else (a schedule or push trigger would make it a deploy-adjacent
    job it is not);
  - it runs on an ephemeral GitHub-hosted Ubuntu VM with read-only contents,
    no persisted credentials, no secrets, no environment, no container;
  - it never relaxes kernel/AppArmor protection and never adds a privileged
    daemon: the only escalation is `sudo -n` on the same bwrap/pytest argv;
  - it runs ONLY the named jail-proof modules, never the suite or the required
    gate;
  - its verdict is the named-case JUnit assertion over EVERY guarded case, run
    `always()`, so pytest's exit 0 on a skip cannot pass the job;
  - no `run:` block interpolates a `${{ }}` expression (values reach the shell
    through `env:` only).

The assertion helper is exercised on synthetic xunit1 reports for every state
it must distinguish, and every guarded nodeid is checked against the test source
so a rename cannot leave the workflow asserting a case that no longer exists.

PyYAML is imported hard: skipping this file is how the invariants would go quiet.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parent.parent
_WORKFLOW = _REPO / ".github" / "workflows" / "linux-jail-proof.yml"
_SCRIPT = _REPO / "scripts" / "ci_assert_junit_case.py"
_NODEID = "tests/test_delivery_node_rpc.py::test_real_linux_jail_transports_delivery_rpc"
_FILES = (
    "tests/test_delivery_node_rpc.py",
    "tests/test_native_refresh_jail.py",
    "tests/test_provider_universe_jail.py",
)
_NODEIDS = (
    _NODEID,
    "tests/test_native_refresh_jail.py::test_jail_reads_workspace_but_not_launch_credentials",
    "tests/test_native_refresh_jail.py::test_removing_the_launch_mask_exposes_the_snapshot",
    "tests/test_provider_universe_jail.py::test_claude_node_call_reads_only_its_own_universe",
    "tests/test_provider_universe_jail.py::test_codex_node_call_reads_only_its_own_universe",
    "tests/test_provider_universe_jail.py::test_router_jails_a_new_command_adapter_with_no_jail_code",
)
_RUN_STEP = "Run the jail proof modules"
_JOB = "linux-jail-proof"

_spec = importlib.util.spec_from_file_location("ci_assert_junit_case", _SCRIPT)
assert _spec and _spec.loader
_assert = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_assert)


def _load() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _text() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


def _triggers(wf: dict) -> dict:
    return wf[True] if True in wf else wf["on"]


def _job(wf: dict) -> dict:
    jobs = wf["jobs"]
    assert list(jobs) == [_JOB], f"exactly one job named {_JOB!r}, got {list(jobs)}"
    return jobs[_JOB]


def _steps(wf: dict) -> list[dict]:
    return _job(wf)["steps"]


def _step(wf: dict, needle: str) -> dict:
    hits = [s for s in _steps(wf)
            if needle in (s.get("name") or "") or needle in (s.get("uses") or "")]
    assert len(hits) == 1, f"expected one step matching {needle!r}, got {len(hits)}"
    return hits[0]


def _step_index(wf: dict, needle: str) -> int:
    steps = _steps(wf)
    return steps.index(_step(wf, needle))


def _code_text() -> str:
    # The workflow body with comment lines removed: the reach/escalation
    # checks are about what the job DOES, and the header comments legitimately
    # name the things it refuses to do.
    return "\n".join(
        line for line in _text().splitlines() if not line.lstrip().startswith("#")
    )


# --- triggers ---------------------------------------------------------------

def test_triggers_are_pull_request_paths_plus_dispatch_only():
    triggers = _triggers(_load())
    assert set(triggers) == {"pull_request", "workflow_dispatch"}
    paths = triggers["pull_request"]["paths"]
    assert paths, "pull_request must be path-scoped, not repo-wide"
    for required in (
        ".github/workflows/linux-jail-proof.yml",
        "scripts/ci_assert_junit_case.py",
        "tinyassets/node_sandbox.py",
        "tests/test_delivery_node_rpc.py",
        "tests/test_native_refresh_jail.py",
        "tinyassets/providers/codex_provider.py",
        "tests/test_provider_universe_jail.py",
        "tinyassets/providers/provider_jail.py",
        "tinyassets/providers/owned_process.py",
        "tinyassets/providers/router.py",
        "tinyassets/providers/claude_provider.py",
    ):
        assert required in paths, f"{required} must retrigger the proof"


def test_every_literal_trigger_path_exists():
    # A path filter naming a file that no longer exists is a trigger that
    # silently never fires for that file.
    paths = _triggers(_load())["pull_request"]["paths"]
    for path in paths:
        if any(ch in path for ch in "*?["):
            assert list(_REPO.glob(path)), f"glob {path} matches nothing"
        else:
            assert (_REPO / path).is_file(), f"{path} is not a file"


# --- authority / isolation --------------------------------------------------

def test_read_only_contents_and_no_job_level_widening():
    wf = _load()
    assert wf["permissions"] == {"contents": "read"}
    assert "permissions" not in _job(wf)


def test_hosted_ephemeral_runner_only():
    job = _job(_load())
    assert job["runs-on"] == "ubuntu-latest"
    assert "container" not in job
    assert "environment" not in job, "no deployment environment on a test job"
    assert 0 < job["timeout-minutes"] <= 20


def test_checkout_does_not_persist_credentials():
    step = _step(_load(), "actions/checkout@")
    assert step["with"]["persist-credentials"] is False


def test_no_secrets_self_hosted_desktop_or_production_reach():
    text = _code_text()
    for forbidden in (
        "secrets.", "self-hosted", "DESKTOP-KCPMGP3", "tinyassets.io",
        "deploy", "docker ", "--privileged", "GITHUB_TOKEN",
    ):
        assert forbidden not in text, f"{forbidden!r} must not appear"


def test_no_kernel_or_apparmor_relaxation():
    text = _code_text()
    assert "sysctl" not in text
    assert "apparmor_restrict_unprivileged_userns=0" not in text
    assert "aa-" not in text  # aa-complain / aa-disable / aa-teardown
    assert "/etc/apparmor" not in text
    # The only escalation is `sudo -n` in front of the same argv.
    for line in text.splitlines():
        if re.match(r"\s*(elif\s+)?sudo\s", line) and "apt-get" not in line:
            assert "sudo -n" in line, f"sudo must be non-interactive: {line.strip()}"


def test_run_blocks_never_interpolate_expressions():
    for step in _steps(_load()):
        run = step.get("run")
        if run:
            assert "${{" not in run, f"expression inside shell in step {step.get('name')!r}"


# --- what it runs -----------------------------------------------------------

def test_env_pins_the_test_files_and_every_named_case():
    env = _load()["env"]
    assert "JAIL_TEST_FILE" not in env and "JAIL_TEST_NODEID" not in env
    assert tuple(env["JAIL_TEST_FILES"].split()) == _FILES
    assert tuple(env["JAIL_TEST_NODEIDS"].split()) == _NODEIDS


def test_every_guarded_file_runs_and_retriggers_the_proof():
    wf = _load()
    files = set(wf["env"]["JAIL_TEST_FILES"].split())
    paths = set(_triggers(wf)["pull_request"]["paths"])
    for nodeid in wf["env"]["JAIL_TEST_NODEIDS"].split():
        path = nodeid.split("::")[0]
        assert path in files, f"{nodeid} is asserted but its file is never run"
        assert path in paths, f"{path} must retrigger the proof"


@pytest.mark.parametrize("nodeid", _NODEIDS)
def test_guarded_nodeid_resolves_to_a_bwrap_gated_test(nodeid):
    path, name = nodeid.split("::")[0], nodeid.split("::")[-1]
    src = (_REPO / path).read_text(encoding="utf-8")
    assert re.search(rf"^def {re.escape(name)}\(", src, re.M), f"{name} must exist"
    decorated = re.search(rf'@pytest\.mark\.skipif\(not shutil\.which\("bwrap"\)[^\n]*\n'
                          rf'def {re.escape(name)}\(', src)
    module_gate = re.search(r"^pytestmark = pytest\.mark\.skipif\(\n[^)]*_BWRAP", src, re.M)
    assert decorated or module_gate, f"{name} must be skipif-gated on bwrap"


def test_bubblewrap_installed_and_functionally_probed_before_pytest():
    wf = _load()
    install = _step(wf, "Install bubblewrap")
    assert "apt-get install" in install["run"] and "bubblewrap" in install["run"]
    probe = _step(wf, "Probe the jail")
    assert probe.get("id") == "probe"
    assert "--unshare-all" in probe["run"], "smoke must exercise the real userns flag"
    assert "--die-with-parent" in probe["run"]
    assert "exit 1" in probe["run"], "an unjailable runner must fail, not skip"
    assert 'runner=' in probe["run"]
    assert (_step_index(wf, "Install bubblewrap")
            < _step_index(wf, "Probe the jail")
            < _step_index(wf, _RUN_STEP))


def test_pytest_step_is_focused_and_off_repo():
    step = _step(_load(), _RUN_STEP)
    run = step["run"]
    env = step["env"]
    assert 'read -r -a files <<< "$JAIL_TEST_FILES"' in run
    assert 'args=("${files[@]}"' in run
    assert "ci_required_tests.py" not in run, "never the required gate"
    assert not re.search(r"pytest\s+tests(\s|$|/?\")", run), "never the whole suite"
    assert "--junitxml" in run and "--basetemp" in run
    assert "junit_family=xunit1" in run, "the assertion helper reads xunit1"
    for var in ("TINYASSETS_DATA_DIR", "PYTEST_BASETEMP", "JUNIT_PATH"):
        assert env[var].startswith("${{ runner.temp }}/"), f"{var} must live under runner.temp"
    assert env["JAIL_RUNNER"] == "${{ steps.probe.outputs.runner }}"
    # The exact setup-python interpreter, resolved once and reused under sudo.
    assert 'py="$(command -v python)"' in run
    assert '"$py" -m pytest' in run
    assert "sudo -n --preserve-env=" in run
    assert "sudo -E" not in run, "preserve only named variables"


def test_assertion_step_always_runs_and_names_the_case():
    wf = _load()
    step = _step(wf, "Assert every real-jail case")
    assert step["if"] == "always()"
    assert "scripts/ci_assert_junit_case.py" in step["run"]
    assert 'read -r -a nodeids <<< "$JAIL_TEST_NODEIDS"' in step["run"]
    assert 'nodeid_args+=(--nodeid "$nodeid")' in step["run"]
    assert '"${nodeid_args[@]}"' in step["run"]
    run_step = _step(wf, _RUN_STEP)
    assert step["env"]["JUNIT_PATH"] == run_step["env"]["JUNIT_PATH"]


def test_junit_uploaded_even_on_failure():
    step = _step(_load(), "actions/upload-artifact@")
    assert step["if"] == "always()"
    assert step["with"]["name"] == "junit-linux-jail-proof"
    assert step["with"]["path"].endswith("/junit-linux-jail.xml")


def test_not_the_required_context():
    job = _job(_load())
    assert job["name"] == _JOB
    assert job["name"] != "required-tests"


# --- the assertion helper ---------------------------------------------------

_CASE = ('<testcase classname="tests.test_delivery_node_rpc" '
         'name="test_real_linux_jail_transports_delivery_rpc" time="0.1">{inner}</testcase>')


def _junit(tmp_path: Path, *cases: str) -> Path:
    path = tmp_path / "junit.xml"
    path.write_text('<?xml version="1.0"?><testsuites><testsuite name="pytest">'
                    + "".join(cases) + "</testsuite></testsuites>", encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("cases", "code", "fragment"),
    [
        pytest.param([_CASE.format(inner="")], 0, "executed and passed", id="passed"),
        pytest.param(
            [_CASE.format(
                inner='<skipped type="pytest.skip" message="requires Linux bubblewrap"/>')],
            1, "skipped: requires Linux bubblewrap", id="skipped-is-not-pass",
        ),
        pytest.param([_CASE.format(inner='<failure message="boom"/>')],
                     1, "failure: boom", id="failed"),
        pytest.param([_CASE.format(inner='<error message="fixture"/>')],
                     1, "error: fixture", id="errored"),
        pytest.param(
            ['<testcase classname="tests.test_delivery_node_rpc" name="test_other"/>'],
            1, "ABSENT", id="absent-same-module",
        ),
        pytest.param(
            ['<testcase classname="tests.test_other" '
             'name="test_real_linux_jail_transports_delivery_rpc"/>'],
            1, "ABSENT", id="absent-same-name-other-module",
        ),
        pytest.param(
            [_CASE.format(inner=""), _CASE.format(inner='<skipped message="rerun"/>')],
            1, "skipped: rerun", id="any-bad-occurrence-fails",
        ),
    ],
)
def test_assertion_helper_verdicts(tmp_path, cases, code, fragment):
    got, message = _assert.check(_junit(tmp_path, *cases), _NODEID)
    assert got == code, message
    assert fragment in message


def test_assertion_helper_missing_or_broken_report_is_exit_2(tmp_path):
    code, message = _assert.check(tmp_path / "nope.xml", _NODEID)
    assert code == 2 and "no JUnit report" in message
    broken = tmp_path / "broken.xml"
    broken.write_text("<testsuites><testsuite", encoding="utf-8")
    code, message = _assert.check(broken, _NODEID)
    assert code == 2 and "not parseable" in message


def test_assertion_helper_main_writes_summary_and_exit_code(tmp_path):
    summary = tmp_path / "summary.md"
    junit = _junit(tmp_path, _CASE.format(inner='<skipped message="no bwrap"/>'))
    rc = _assert.main(["--junit", str(junit), "--nodeid", _NODEID, "--summary", str(summary)])
    assert rc == 1
    line = summary.read_text(encoding="utf-8")
    assert line.startswith("- **FAIL**") and _NODEID in line and "no bwrap" in line


_OTHER_NODEID = (
    "tests/test_native_refresh_jail.py::test_removing_the_launch_mask_exposes_the_snapshot"
)
_OTHER_CASE = ('<testcase classname="tests.test_native_refresh_jail" '
               'name="test_removing_the_launch_mask_exposes_the_snapshot" time="0.1">'
               '{inner}</testcase>')


@pytest.mark.parametrize(
    ("first", "second", "code"),
    [
        pytest.param("", "", 0, id="both-passed"),
        pytest.param("", '<skipped message="no bwrap"/>', 1, id="one-skip-fails-the-run"),
        pytest.param('<failure message="boom"/>', "", 1, id="first-bad-second-clean"),
    ],
)
def test_assertion_helper_checks_every_repeated_nodeid(tmp_path, first, second, code):
    summary = tmp_path / "summary.md"
    junit = _junit(tmp_path, _CASE.format(inner=first), _OTHER_CASE.format(inner=second))
    rc = _assert.main(["--junit", str(junit), "--nodeid", _NODEID,
                       "--nodeid", _OTHER_NODEID, "--summary", str(summary)])
    assert rc == code
    lines = summary.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2, "one verdict line per guarded case"
    assert _NODEID in lines[0] and _OTHER_NODEID in lines[1]


def test_assertion_helper_absent_second_case_fails(tmp_path):
    junit = _junit(tmp_path, _CASE.format(inner=""))
    rc = _assert.main(["--junit", str(junit), "--nodeid", _NODEID, "--nodeid", _OTHER_NODEID])
    assert rc == 1


def test_assertion_helper_rejects_malformed_nodeid(tmp_path):
    with pytest.raises(SystemExit):
        _assert.check(_junit(tmp_path, _CASE.format(inner="")), "not-a-nodeid")
