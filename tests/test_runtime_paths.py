"""The deploy chain's runtime classifier: skip what production does not run.

Every deploy recreates the production daemon and kills in-flight user turns.
``scripts/runtime_paths.py`` decides whether a merge changes anything
production runs; build-image.yml, release-reconcile.yml and deployed_sha.py all
ask it. The dangerous direction is a runtime change classified as skippable,
so most of these tests pin the FAIL-OPEN cases.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.runtime_repo_fixture import SERVED_LIMIT, make_repo, plan

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

_SPEC = importlib.util.spec_from_file_location(
    "runtime_paths_under_test", REPO_ROOT / "scripts" / "runtime_paths.py"
)
assert _SPEC is not None and _SPEC.loader is not None
rp = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = rp
_SPEC.loader.exec_module(rp)

_WINDOWS_GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
_BASH = str(_WINDOWS_GIT_BASH) if _WINDOWS_GIT_BASH.exists() else shutil.which("bash")

yaml = pytest.importorskip("yaml")


@pytest.fixture
def repo(tmp_path):
    return make_repo(tmp_path / "repo")


def _decide(repo, base, head):
    return rp.decide(repo.root, base, head)


# --- Dockerfile parsing -----------------------------------------------------


def test_real_dockerfile_context_copies_are_all_runtime():
    sources, everything = rp.dockerfile_copy_sources(
        (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    )
    assert everything is False
    assert {
        "pyproject.toml",
        "PLAN.md",
        "tinyassets",
        "domains",
        "fantasy_daemon",
        "data/world_rules.lp",
        "deploy/native/ta_op.c",
        "deploy/codex-flock-wrapper.sh",
        "deploy/docker-entrypoint.sh",
        "scripts/codex_cli_smoke.py",
        "scripts/mcp_public_canary.py",
        "scripts/_canary_common.py",
        "scripts/workspace_bwrap_oracle.py",
    } <= set(sources)
    # Stage-to-stage copies read no build context.
    assert not any(src.startswith(("build/", "opt/", "tmp/")) for src in sources)


def test_parser_handles_flags_json_form_continuations_and_stage_copies():
    text = (
        "FROM x AS b\n"
        "# COPY commented/out.py /x\n"
        "COPY --chown=1:1 --chmod=0755 a.py \\\n"
        "     b/ /dst/\n"
        'COPY ["c d.txt", "/dst/"]\n'
        "COPY --from=b /build/x /x\n"
        "ADD https://example.invalid/f.tgz /tmp/\n"
        "COPY ./e/ ./e/\n"
        "RUN echo COPY not/an/instruction\n"
    )
    sources, everything = rp.dockerfile_copy_sources(text)
    assert everything is False
    assert sources == ["a.py", "b", "c d.txt", "e"]


@pytest.mark.parametrize(
    "line", ["COPY . /app/", "COPY *.py /app/", "COPY ./ /app/", 'COPY ["broken', "COPY onlyone"]
)
def test_an_unbounded_copy_makes_every_path_runtime(line):
    _, everything = rp.dockerfile_copy_sources(f"FROM x\n{line}\n")
    assert everything is True


def test_a_wildcard_is_bounded_by_its_directory():
    sources, everything = rp.dockerfile_copy_sources("FROM x\nCOPY scripts/*.py /app/\n")
    assert (sources, everything) == (["scripts"], False)


def test_host_manifest_matches_what_the_installer_prints():
    """Differential: the parsed array against the script's own manifest mode."""
    if not _BASH:
        pytest.skip("bash is required to run the installer's manifest mode")
    installer = REPO_ROOT / "deploy" / "install-host-uptime-services.sh"
    parsed = rp.host_manifest_files(installer.read_text(encoding="utf-8"))
    printed = subprocess.run(
        [_BASH, installer.as_posix()],
        cwd=REPO_ROOT,
        env={"TINYASSETS_PRINT_MANIFEST": "1", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert parsed, "RUNTIME_FILES array not found"
    assert set(parsed) <= set(printed)
    # Everything the installer ships is runtime, whether it came from the
    # array, the unit list, or deploy/.
    inputs = rp.runtime_inputs_from(_working_tree)
    assert [p for p in printed if not inputs.covers(p)] == []


# --- decisions --------------------------------------------------------------


def test_docs_only_merge_skips(repo):
    r, base = repo
    head = r.commit(
        "docs", {"docs/notes.md": "more\n", "AGENTS.md": "x\n", "tests/test_x.py": "#\n"}
    )
    decision = _decide(r, base, head)
    assert decision.build is False, decision.reason


def test_runtime_merge_builds(repo):
    r, base = repo
    head = r.commit("code", {"tinyassets/app.py": "VERSION = 2\n"})
    decision = _decide(r, base, head)
    assert decision.build is True
    assert decision.runtime_paths == ("tinyassets/app.py",)


def test_a_dockerfile_copy_source_outside_the_package_builds(repo):
    """scripts/_canary_common.py is COPYed into the image (the healthcheck
    imports it) but was never in build-image.yml's path filter."""
    r, base = repo
    head = r.commit("canary helper", {"scripts/_canary_common.py": "TOKEN = 2\n"})
    decision = _decide(r, base, head)
    assert decision.build is True
    assert decision.runtime_paths == ("scripts/_canary_common.py",)


def test_a_host_service_input_builds(repo):
    r, base = repo
    head = r.commit("watchdog", {"scripts/watchdog.py": "WATCH = 2\n"})
    assert _decide(r, base, head).runtime_paths == ("scripts/watchdog.py",)


def test_a_script_nothing_ships_does_not_build(repo):
    r, base = repo
    head = r.commit("tool", {"scripts/unrelated_tool.py": "TOOL = 2\n"})
    assert _decide(r, base, head).build is False


def test_batched_merges_are_judged_as_one_range(repo):
    """One push carrying a runtime merge and then a docs merge must build."""
    r, base = repo
    r.commit("code", {"tinyassets/app.py": "VERSION = 2\n"})
    head = r.commit("docs", {"docs/notes.md": "more\n"})
    decision = _decide(r, base, head)
    assert decision.build is True
    assert "tinyassets/app.py" in decision.runtime_paths


def test_docs_merge_after_an_undeployed_runtime_merge_builds(repo):
    """Production still serves `base`: the runtime merge never deployed (its
    build was cancelled by the next push, or its deploy rolled back). The docs
    merge on top must carry it out."""
    r, base = repo
    runtime = r.commit("code", {"tinyassets/app.py": "VERSION = 2\n"})
    docs = r.commit("docs", {"docs/notes.md": "more\n"})
    assert _decide(r, base, docs).build is True
    # Once the runtime merge IS what production serves, the same docs head skips.
    assert _decide(r, runtime, docs).build is False


def test_a_file_renamed_out_of_a_runtime_directory_builds(repo):
    r, base = repo
    head = r.rename("move", "tinyassets/app.py", "docs/app.py")
    decision = _decide(r, base, head)
    assert decision.build is True
    assert "tinyassets/app.py" in decision.runtime_paths


def test_a_dockerfile_change_builds(repo):
    r, base = repo
    head = r.commit("df", {".dockerignore": "docs/\ntests/\n"})
    assert _decide(r, base, head).build is True


def test_no_dockerfile_makes_everything_runtime(repo):
    r, base = repo
    gone = r.commit("drop df", {"Dockerfile": None})
    head = r.commit("docs", {"docs/notes.md": "more\n"})
    assert _decide(r, gone, head).build is True


def test_unreadable_host_manifest_makes_all_scripts_runtime(repo):
    r, _ = repo
    gone = r.commit("drop manifest", {"deploy/install-host-uptime-services.sh": None})
    head = r.commit("tool", {"scripts/unrelated_tool.py": "TOOL = 2\n"})
    assert _decide(r, gone, head).build is True


# --- PLAN.md: copied whole, served in excerpts --------------------------------


def test_plan_edit_outside_served_sections_skips(repo):
    r, base = repo
    head = r.commit("plan", {"PLAN.md": plan(unserved="a new principle")})
    decision = _decide(r, base, head)
    assert decision.build is False, decision.reason


def test_plan_edit_past_the_served_excerpt_skips(repo):
    """#3970's shape: new text deep inside a served section, beyond the
    excerpt the daemon returns. The served bytes are identical."""
    r, base = repo
    head = r.commit("plan", {"PLAN.md": plan(scoping_tail="a long new paragraph")})
    assert _decide(r, base, head).build is False


def test_plan_edit_inside_a_served_excerpt_builds(repo):
    r, base = repo
    head = r.commit("plan", {"PLAN.md": plan(daemon="the daemon changed")})
    decision = _decide(r, base, head)
    assert decision.build is True
    assert decision.runtime_paths == ("PLAN.md (served section: Module: Daemon Platform)",)


def test_removing_a_served_heading_builds(repo):
    r, base = repo
    text = plan().replace("## Module: Daemon Platform", "## Renamed Module")
    head = r.commit("plan", {"PLAN.md": text})
    assert _decide(r, base, head).build is True


def test_plan_edit_builds_when_served_headings_are_unreadable(repo):
    r, _ = repo
    gone = r.commit("drop module", {"tinyassets/api/universe.py": None})
    head = r.commit("plan", {"PLAN.md": plan(unserved="x")})
    decision = _decide(r, gone, head)
    assert decision.build is True
    assert decision.runtime_paths == ("PLAN.md (served headings unreadable)",)


def test_plan_compares_full_sections_when_the_excerpt_limit_is_unreadable(repo):
    r, _ = repo
    universe = (r.root / "tinyassets/api/universe.py").read_text(encoding="utf-8")
    no_limit = r.commit(
        "limit via name",
        {"tinyassets/api/universe.py": universe.replace(f", {SERVED_LIMIT})", ", LIMIT)")},
    )
    head = r.commit("plan", {"PLAN.md": plan(scoping_tail="past the excerpt")})
    assert _decide(r, no_limit, head).build is True


def test_plan_is_not_special_once_the_image_stops_copying_it(repo):
    r, _ = repo
    df = (r.root / "Dockerfile").read_text(encoding="utf-8").replace("COPY PLAN.md ./\n", "")
    no_copy = r.commit("stop copying PLAN", {"Dockerfile": df})
    head = r.commit("plan", {"PLAN.md": plan(daemon="changed")})
    assert _decide(r, no_copy, head).build is False


# --- what production serves -------------------------------------------------


def test_unknown_served_sha_builds(repo):
    r, base = repo
    head = r.commit("docs", {"docs/notes.md": "more\n"})
    assert _decide(r, None, head).build is True
    assert _decide(r, "", head).build is True


def test_served_sha_unknown_to_git_builds(repo):
    r, _ = repo
    head = r.commit("docs", {"docs/notes.md": "more\n"})
    assert _decide(r, "0" * 40, head).build is True


def test_served_sha_off_the_head_line_builds(repo):
    """A branch image deployed by hand: the head does not descend from it."""
    r, base = repo
    r.git("checkout", "-q", "-b", "side")
    side = r.commit("side", {"docs/notes.md": "side\n"})
    r.git("checkout", "-q", "main")
    head = r.commit("docs", {"docs/other.md": "main\n"})
    decision = _decide(r, side, head)
    assert decision.build is True
    assert "not an ancestor" in decision.reason


def test_unresolvable_head_builds(repo):
    r, base = repo
    assert _decide(r, base, "no-such-ref").build is True


def test_a_git_failure_builds(repo, monkeypatch):
    r, base = repo
    head = r.commit("docs", {"docs/notes.md": "more\n"})

    def broken(*_a, **_k):
        raise rp.ClassifyError("simulated git failure")

    monkeypatch.setattr(rp, "changed_paths", broken)
    decision = _decide(r, base, head)
    assert decision.build is True
    assert "could not classify" in decision.reason


def test_decide_cli_writes_github_outputs(repo, tmp_path):
    r, base = repo
    head = r.commit("docs", {"docs/notes.md": "more\n"})
    out = tmp_path / "gh-output"
    argv = ["--repo", str(r.root), "decide", "--base", base, "--head", head]
    assert rp.main([*argv, "--github-output", str(out)]) == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "decision=skip"
    assert lines[1].startswith("reason=production's ")


# --- history walks (release-reconcile, deployed_sha) ----------------------------


def test_newest_runtime_commit_walks_past_docs_and_unserved_plan(repo):
    r, _ = repo
    runtime = r.commit("code", {"tinyassets/app.py": "VERSION = 2\n"})
    r.commit("plan", {"PLAN.md": plan(unserved="x")})
    head = r.commit("docs", {"docs/notes.md": "more\n"})
    assert rp.newest_runtime_commit(r.root, head) == runtime


def test_newest_runtime_commit_fails_open_when_the_walk_runs_out(repo):
    r, _ = repo
    r.commit("code", {"tinyassets/app.py": "VERSION = 2\n"})
    head = r.commit("docs", {"docs/notes.md": "more\n"})
    assert rp.newest_runtime_commit(r.root, head, limit=1) == head


def test_runtime_commits_counts_only_runtime_commits(repo):
    r, base = repo
    runtime = r.commit("code", {"tinyassets/app.py": "VERSION = 2\n"})
    r.commit("plan", {"PLAN.md": plan(unserved="x")})
    head = r.commit("docs", {"docs/notes.md": "more\n"})
    assert rp.runtime_commits(r.root, base, head) == [runtime]


# --- the mirror of the daemon's PLAN.md serving (differential) ---------------


def _universe():
    return pytest.importorskip("tinyassets.api.universe")


def test_plan_serving_is_read_from_the_daemons_own_source():
    univ = _universe()
    serving = rp.plan_serving(
        (REPO_ROOT / "tinyassets" / "api" / "universe.py").read_text(encoding="utf-8")
    )
    assert serving is not None
    assert serving.headings == tuple(univ._CHANGE_LOOP_PLAN_HEADINGS)
    assert serving.limit == 1400


_LONG = "word " * 600


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(None, id="real-PLAN.md"),
        pytest.param("# nothing served here\n", id="no-sections"),
        pytest.param(
            "## Scoping Rules\n" + _LONG + "\n## Module: Goals & Gates  \nshort\n",
            id="long-and-padded",
        ),
        pytest.param("## Module: Daemon Platform\nat eof", id="section-at-eof"),
        pytest.param(
            "## Module: Evolution & Evaluation\n### sub\nkept\n## Next\ndropped\n", id="subheadings"
        ),
    ],
)
def test_served_plan_context_matches_the_daemon(tmp_path, monkeypatch, text):
    """The classifier must compare exactly what the daemon serves."""
    univ = _universe()
    if text is None:
        text = (REPO_ROOT / "PLAN.md").read_text(encoding="utf-8")
    (tmp_path / "PLAN.md").write_text(text, encoding="utf-8")
    monkeypatch.setattr(univ, "_bundled_source_root", lambda: tmp_path)
    serving = rp.plan_serving(
        (REPO_ROOT / "tinyassets" / "api" / "universe.py").read_text(encoding="utf-8")
    )
    assert rp.served_plan_context(text, serving) == univ._change_loop_plan_context()


# --- the workflows agree with the classifier ---------------------------------


def _working_tree(path: str) -> str | None:
    target = REPO_ROOT / path
    return target.read_text(encoding="utf-8") if target.is_file() else None


def _build_image_push_paths() -> list[str]:
    wf = yaml.safe_load((WORKFLOWS / "build-image.yml").read_text(encoding="utf-8"))
    on = wf.get("on", wf.get(True))
    return list(on["push"]["paths"])


def _filter_covers(patterns: list[str], path: str) -> bool:
    for pattern in patterns:
        if pattern.endswith("/**"):
            prefix = pattern[: -len("**")]
            if path.rstrip("/") + "/" == prefix or path.startswith(prefix):
                return True
        elif pattern == path.rstrip("/"):
            return True
    return False


def test_build_image_path_filter_is_a_superset_of_every_runtime_input():
    """The dangerous direction: a runtime input the pre-filter never sees is a
    change that never builds, never deploys, and never alarms."""
    inputs = rp.runtime_inputs_from(_working_tree)
    assert inputs.everything is False
    patterns = _build_image_push_paths()
    missing = [p for p in inputs.paths if not _filter_covers(patterns, p)]
    assert missing == [], f"build-image.yml push paths omit runtime inputs: {missing}"


#: Scripts the deploy workflows run on the GitHub runner only, to verify.
RUNNER_ONLY_SCRIPTS = {"scripts/deployed_sha.py"}


@pytest.mark.parametrize("workflow", ["deploy-prod.yml", "install-host-services.yml"])
def test_every_script_the_deploy_workflows_ship_is_runtime(workflow):
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    named = set(re.findall(r"scripts/[A-Za-z0-9_.-]+\.py", text)) - RUNNER_ONLY_SCRIPTS
    assert named, f"{workflow} names no scripts -- the scan is broken"
    inputs = rp.runtime_inputs_from(_working_tree)
    assert sorted(p for p in named if not inputs.covers(p)) == []
