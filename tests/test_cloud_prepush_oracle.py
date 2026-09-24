"""Cloud pre-push oracle: input rejection, exact argv, hosted-only contract."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts"))

import cloud_prepush_oracle as oracle  # noqa: E402

_WORKFLOW = _REPO / ".github" / "workflows" / "cloud-prepush-oracle.yml"
_SHA = "a" * 40
_PATCH = (
    b"diff --git a/tinyassets/x.py b/tinyassets/x.py\n"
    b"--- a/tinyassets/x.py\n+++ b/tinyassets/x.py\n"
    b"@@ -1 +1 @@\n-old\n+new\n"
)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# --------------------------------------------------------------------------
# node-id parser
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "not json",
        "{}",
        "[]",
        "[1]",
        '[""]',
        '["-k"]',
        '["--pdb"]',
        '["-p", "no:cacheprovider"]',
        '["/tmp/test_x.py"]',
        '["C:\\\\tests\\\\test_x.py"]',
        '["tests/../tinyassets/x.py"]',
        '["tinyassets/test_x.py"]',
        '["tests/test_x.txt"]',
        '["tests//test_x.py"]',
        '[" tests/test_x.py"]',
        '["tests/test_x.py\\n::test_y"]',
    ],
)
def test_nodeid_rejection(bad):
    with pytest.raises(oracle.OracleInputError):
        oracle.validate_nodeids(bad)


def test_nodeid_cap():
    ids = json.dumps([f"tests/test_{i}.py" for i in range(oracle.MAX_NODEIDS + 1)])
    with pytest.raises(oracle.OracleInputError, match="cap"):
        oracle.validate_nodeids(ids)


def test_nodeid_accepts_relative_under_tests_with_params():
    ids = ["tests/test_x.py", "tests/sub/test_y.py::TestK::test_z[a-b=1]"]
    assert oracle.validate_nodeids(json.dumps(ids)) == ids


# --------------------------------------------------------------------------
# patch size / hash / paths / content
# --------------------------------------------------------------------------


def test_patch_roundtrip():
    assert oracle.decode_patch(_b64(_PATCH), _sha(_PATCH).upper()) == _PATCH


def test_patch_over_cap_rejected():
    big = b"diff --git a/tests/t.py b/tests/t.py\n" + b"+" * 50_000
    assert len(_b64(big)) > oracle.MAX_PATCH_B64_CHARS
    with pytest.raises(oracle.OracleInputError, match="cap"):
        oracle.decode_patch(_b64(big), _sha(big))


@pytest.mark.parametrize("b64", ["", "   ", "!!!notbase64!!!", "QUJD=x"])
def test_patch_bad_base64_rejected(b64):
    with pytest.raises(oracle.OracleInputError):
        oracle.decode_patch(b64, "0" * 64)


def test_patch_hash_mismatch_rejected():
    with pytest.raises(oracle.OracleInputError, match="mismatch"):
        oracle.decode_patch(_b64(_PATCH), "0" * 64)
    with pytest.raises(oracle.OracleInputError, match="64 hex"):
        oracle.decode_patch(_b64(_PATCH), "abc")


@pytest.mark.parametrize(
    "path",
    [
        ".github/workflows/tests.yml",
        oracle.HELPER_REL,
        "../etc/passwd",
        "/etc/passwd",
        "tests/../pyproject.toml",
        "pyproject.toml",
        "docs/x.md",
        "tests\\test_x.py",
    ],
)
def test_patch_path_rejected(path):
    patch = f"diff --git a/{path} b/{path}\n".encode()
    with pytest.raises(oracle.OracleInputError):
        oracle.validate_patch_paths(oracle.patch_paths(patch))


def test_patch_without_git_header_rejected():
    with pytest.raises(oracle.OracleInputError, match="diff --git"):
        oracle.patch_paths(b"--- a/x\n+++ b/x\n")


def test_patch_quoted_path_rejected():
    with pytest.raises(oracle.OracleInputError, match="quoted"):
        oracle.patch_paths(b'diff --git "a/tests/t.py" "b/tests/t.py"\n')


def test_patch_allowed_roots():
    paths = oracle.patch_paths(
        b"diff --git a/tinyassets/a.py b/tinyassets/a.py\n"
        b"diff --git a/tests/test_a.py b/tests/test_a.py\n"
        b"diff --git a/scripts/other.py b/scripts/other.py\n"
    )
    oracle.validate_patch_paths(paths)


def test_patch_credential_marker_rejected():
    bad = _PATCH + b"+-----BEGIN RSA PRIVATE KEY-----\n"
    with pytest.raises(oracle.OracleInputError, match="credential"):
        oracle.validate_patch_content(bad)
    oracle.validate_patch_content(_PATCH)


# --------------------------------------------------------------------------
# base ref
# --------------------------------------------------------------------------


@pytest.mark.parametrize("ref", ["main", "HEAD", "abc123", "A" * 40, "a" * 39, None])
def test_base_sha_rejection(ref):
    with pytest.raises(oracle.OracleInputError):
        oracle.validate_base_sha(ref)


def test_head_must_equal_base():
    oracle.validate_head_matches(_SHA, _SHA + "\n")
    with pytest.raises(oracle.OracleInputError, match="not base_sha"):
        oracle.validate_head_matches(_SHA, "b" * 40)


# --------------------------------------------------------------------------
# exact argv
# --------------------------------------------------------------------------


def test_git_apply_argv_exact_no_unsafe_paths(tmp_path):
    patch = tmp_path / "c.patch"
    assert oracle.build_git_apply_argv(patch, check=True) == [
        "git", "apply", "--check", "--", str(patch)
    ]
    assert oracle.build_git_apply_argv(patch, check=False) == [
        "git", "apply", "--", str(patch)
    ]


def test_apply_runs_check_then_apply_with_exact_argv(tmp_path):
    calls: list[tuple[list[str], str]] = []

    def runner(argv, cwd, check):
        calls.append((list(argv), cwd))
        return subprocess.CompletedProcess(argv, 0)

    patch = tmp_path / "c.patch"
    oracle.apply_patch(patch, tmp_path, runner)
    assert calls == [
        (["git", "apply", "--check", "--", str(patch)], str(tmp_path)),
        (["git", "apply", "--", str(patch)], str(tmp_path)),
    ]


def test_apply_stops_at_failed_check(tmp_path):
    calls = []

    def runner(argv, cwd, check):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 1)

    with pytest.raises(oracle.OracleInputError, match="--check"):
        oracle.apply_patch(tmp_path / "c.patch", tmp_path, runner)
    assert len(calls) == 1


def test_pytest_argv_exact_with_separator(tmp_path):
    ids = ["tests/test_a.py::test_b", "tests/test_c.py"]
    argv = oracle.build_pytest_argv(
        ids, temp_root=tmp_path, junit_path=tmp_path / "junit.xml", python="py"
    )
    assert argv == [
        "py", "-m", "pytest", "-p", "no:cacheprovider", "-q", "--no-header", "-rfEs",
        "--basetemp", str(tmp_path / "pt"), "--junitxml", str(tmp_path / "junit.xml"),
        "--", *ids,
    ]


def test_materialize_rejects_head_mismatch_before_writing(tmp_path, monkeypatch):
    monkeypatch.setenv(oracle.ENV_BASE_SHA, _SHA)
    monkeypatch.setenv(oracle.ENV_PATCH_B64, _b64(_PATCH))
    monkeypatch.setenv(oracle.ENV_PATCH_SHA256, _sha(_PATCH))
    monkeypatch.setenv(oracle.ENV_TESTS_JSON, '["tests/test_x.py"]')

    def runner(argv, cwd, check, capture_output, text):
        return subprocess.CompletedProcess(argv, 0, stdout="b" * 40 + "\n", stderr="")

    work = tmp_path / "work"
    args = oracle.build_parser().parse_args(
        ["materialize", "--work", str(work), "--repo", str(tmp_path)]
    )
    with pytest.raises(oracle.OracleInputError, match="not base_sha"):
        oracle.cmd_materialize(args, runner)
    assert not work.exists()


def test_materialize_writes_patch_and_manifest(tmp_path, monkeypatch):
    monkeypatch.setenv(oracle.ENV_BASE_SHA, _SHA)
    monkeypatch.setenv(oracle.ENV_PATCH_B64, _b64(_PATCH))
    monkeypatch.setenv(oracle.ENV_PATCH_SHA256, _sha(_PATCH))
    monkeypatch.setenv(oracle.ENV_TESTS_JSON, '["tests/test_x.py"]')

    def runner(argv, cwd, check, capture_output, text):
        out = _SHA + "\n" if argv[1] == "rev-parse" else ""
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")

    work = tmp_path / "work"
    args = oracle.build_parser().parse_args(
        ["materialize", "--work", str(work), "--repo", str(tmp_path)]
    )
    assert oracle.cmd_materialize(args, runner) == 0
    assert (work / "candidate.patch").read_bytes() == _PATCH
    manifest = json.loads((work / "manifest.json").read_text())
    assert manifest == {
        "base_sha": _SHA, "patch_sha256": _sha(_PATCH),
        "patch_bytes": len(_PATCH), "nodeids": ["tests/test_x.py"],
    }


def test_main_rejection_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(oracle.ENV_BASE_SHA, "main")
    rc = oracle.main(["materialize", "--work", str(tmp_path / "w"), "--repo", str(tmp_path)])
    assert rc == 2
    assert "REJECTED" in capsys.readouterr().err


# --------------------------------------------------------------------------
# verdict: failure / skip are never proof
# --------------------------------------------------------------------------


def _junit(tmp_path, **attrs) -> Path:
    base = {"tests": 3, "failures": 0, "errors": 0, "skipped": 0}
    base.update(attrs)
    xml = '<testsuites><testsuite name="pytest" ' + " ".join(
        f'{k}="{v}"' for k, v in base.items()
    ) + "/></testsuites>"
    p = tmp_path / "junit.xml"
    p.write_text(xml, encoding="utf-8")
    return p


def test_verdict_all_pass_is_proof(tmp_path):
    assert oracle.verdict(oracle.junit_counts(_junit(tmp_path)), 0)[0] == "PROOF"


@pytest.mark.parametrize(
    "attrs,exit_code",
    [({"failures": 1}, 1), ({"errors": 1}, 1), ({"skipped": 1}, 0), ({"tests": 0}, 5), ({}, 3)],
)
def test_verdict_failure_skip_or_nonzero_is_not_proof(tmp_path, attrs, exit_code):
    label, _ = oracle.verdict(oracle.junit_counts(_junit(tmp_path, **attrs)), exit_code)
    assert label == "NOT-PROOF"


def test_report_exits_nonzero_on_skip_and_writes_summary(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    (work / "manifest.json").write_text(json.dumps({
        "base_sha": _SHA, "patch_sha256": _sha(_PATCH), "patch_bytes": len(_PATCH),
        "nodeids": ["tests/test_x.py"],
    }))
    (work / "run.json").write_text(json.dumps({"pytest_exit": 0, "argv": []}))
    _junit(work, skipped=1)
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    rc = oracle.main(["report", "--work", str(work)])
    assert rc == 1
    text = summary.read_text()
    assert "NOT-PROOF" in text and _SHA in text and _sha(_PATCH) in text
    assert json.loads((work / "result.json").read_text())["verdict"] == "NOT-PROOF"


# --------------------------------------------------------------------------
# hosted-only / least-privilege workflow contract
# --------------------------------------------------------------------------


def _wf() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _text() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


def test_workflow_is_manual_only_contents_read():
    wf = _wf()
    assert list((wf.get(True) or wf.get("on")).keys()) == ["workflow_dispatch"]
    assert wf["permissions"] == {"contents": "read"}
    assert list(wf["jobs"]) == ["oracle"]
    job = wf["jobs"]["oracle"]
    assert job["runs-on"] == "ubuntu-latest"
    assert "environment" not in job
    assert "services" not in job and "container" not in job
    assert isinstance(job["timeout-minutes"], int) and job["timeout-minutes"] <= 30
    assert "permissions" not in job


def test_workflow_has_no_secrets_docker_or_deploy():
    text = _text()
    assert "secrets." not in text
    assert "self-hosted" not in text
    assert "--unsafe-paths" not in text
    for word in ("docker", "wsl", "deploy", "publish", "gh release", "git push"):
        assert not re.search(rf"^\s*(run:|-)?[^#\n]*\b{word}\b", text, re.M | re.I), word


def test_workflow_never_interpolates_inputs_into_shell():
    for step in _wf()["jobs"]["oracle"]["steps"]:
        run = step.get("run")
        if run:
            assert "${{" not in run, run
    text = _text()
    assert "github.event.inputs" not in text
    # inputs are only ever bound through env:
    for m in re.finditer(r"\$\{\{\s*inputs\.(\w+)\s*\}\}", text):
        line = text[text.rfind("\n", 0, m.start()) + 1 : m.start()]
        assert re.match(r"\s+(ORACLE_\w+|ref):\s*$", line), line


def test_workflow_two_checkouts_tooling_then_validated_candidate_no_credentials():
    """Tooling at the workflow revision, candidate at base_sha, validated first.

    Release blocker this pins: an older base commit does not contain the
    helper, so the helper must run from a checkout of the WORKFLOW revision
    and never from the candidate tree.
    """
    steps = _wf()["jobs"]["oracle"]["steps"]
    checkouts = [(i, s) for i, s in enumerate(steps)
                 if s.get("uses", "").startswith("actions/checkout@")]
    assert len(checkouts) == 2
    (i_tool, tooling), (i_cand, candidate) = checkouts
    # tooling: workflow revision (no ref override), own directory, no creds
    assert "ref" not in tooling["with"]
    assert tooling["with"]["path"] == "tooling"
    assert tooling["with"]["persist-credentials"] is False
    # candidate: pinned to the validated input sha, own directory, no creds
    assert candidate["with"]["ref"] == "${{ inputs.base_sha }}"
    assert candidate["with"]["path"] == "candidate"
    assert candidate["with"]["persist-credentials"] is False
    # the trusted helper validates base_sha strictly between the two checkouts
    validate = [i for i, s in enumerate(steps) if "validate-base" in s.get("run", "")]
    assert len(validate) == 1 and i_tool < validate[0] < i_cand
    assert steps[validate[0]]["run"].strip() == 'python "$ORACLE_HELPER" validate-base'
    uses = [s.get("uses", "") for s in steps]
    assert all(u.startswith(("actions/checkout@", "actions/setup-python@",
                             "actions/upload-artifact@")) for u in uses if u)


def test_workflow_helper_runs_from_tooling_never_from_candidate():
    job = _wf()["jobs"]["oracle"]
    assert job["env"]["ORACLE_HELPER"] == (
        "${{ github.workspace }}/tooling/scripts/cloud_prepush_oracle.py"
    )
    assert job["env"]["ORACLE_CANDIDATE"] == "${{ github.workspace }}/candidate"
    helper_lines = [line.strip() for s in job["steps"]
                    for line in s.get("run", "").splitlines()
                    if "cloud_prepush_oracle" in line or "ORACLE_HELPER" in line]
    assert helper_lines, "no helper invocation found"
    for line in helper_lines:
        assert line.startswith('python "$ORACLE_HELPER" '), line
        assert "scripts/cloud_prepush_oracle.py" not in line, line
    # every repo-touching stage names the candidate checkout explicitly
    for stage in ("materialize", "apply", "run"):
        line = next(ln for ln in helper_lines if f'"$ORACLE_HELPER" {stage} ' in ln)
        assert '--repo "$ORACLE_CANDIDATE"' in line, line
    # nothing ever runs with the candidate helper path or an implicit cwd repo
    assert "candidate/scripts" not in _text()


def test_workflow_installs_in_candidate_after_checkout_before_apply_in_order():
    steps = _wf()["jobs"]["oracle"]["steps"]
    runs = [s.get("run", "") for s in steps]
    idx = {k: next(i for i, r in enumerate(runs) if k in r)
           for k in ("validate-base", "pip install -e", "materialize",
                     " apply ", " run ", " report ")}
    i_cand = next(i for i, s in enumerate(steps)
                  if s.get("uses", "").startswith("actions/checkout@")
                  and s.get("with", {}).get("path") == "candidate")
    assert (idx["validate-base"] < i_cand < idx["pip install -e"] < idx["materialize"]
            < idx[" apply "] < idx[" run "] < idx[" report "])
    assert steps[idx["pip install -e"]]["working-directory"] == "candidate"
    setup = next(s for s in steps if s.get("uses", "").startswith("actions/setup-python@"))
    assert setup["with"]["cache-dependency-path"] == "candidate/pyproject.toml"


def test_validate_base_subcommand_reads_env_and_exits_2_on_bad_input(monkeypatch, capsys):
    monkeypatch.setenv(oracle.ENV_BASE_SHA, _SHA)
    assert oracle.main(["validate-base"]) == 0
    for bad in ("main", _SHA[:7], _SHA.upper(), "--upload-pack=x", ""):
        monkeypatch.setenv(oracle.ENV_BASE_SHA, bad)
        assert oracle.main(["validate-base"]) == 2, bad
    monkeypatch.delenv(oracle.ENV_BASE_SHA)
    assert oracle.main(["validate-base"]) == 2
    assert "REJECTED" in capsys.readouterr().err


def test_workflow_uploads_junit_always_and_reports_always():
    steps = _wf()["jobs"]["oracle"]["steps"]
    upload = steps[-1]
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["if"] == "always()"
    assert "junit.xml" in upload["with"]["path"]
    report = steps[-2]
    assert "report" in report["run"] and report["if"] == "always()"
    run_step = next(s for s in steps if " run " in s.get("run", ""))
    assert run_step["env"]["TINYASSETS_DATA_DIR"].startswith("${{ runner.temp }}")
    assert run_step["env"]["TMPDIR"].startswith("${{ runner.temp }}")
