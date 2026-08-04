"""Tests for scripts/check_openspec_preconditions.py.

Calibration note: roughly half of these assert the guard stays **green**.
A precondition guard that flags everything is as useless as one that flags
nothing, and the discrimination that matters most here — precondition versus
the task's own target — is only provable by a test that must not fire.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_openspec_preconditions.py"

spec = importlib.util.spec_from_file_location("check_openspec_preconditions", SCRIPT)
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
sys.modules["check_openspec_preconditions"] = guard
spec.loader.exec_module(guard)


def build_repo(
    tmp_path: Path,
    *,
    changes: dict[str, str] | None = None,
    archived: list[str] | None = None,
    capabilities: list[str] | None = None,
) -> Path:
    """Create a minimal openspec tree. `changes` maps name -> tasks.md body."""
    root = tmp_path / "repo"
    (root / "openspec" / "changes" / "archive").mkdir(parents=True)
    (root / "openspec" / "specs").mkdir(parents=True)
    for name, body in (changes or {}).items():
        d = root / "openspec" / "changes" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "tasks.md").write_text(body, encoding="utf-8")
    for name in archived or []:
        (root / "openspec" / "changes" / "archive" / name).mkdir(parents=True)
    for name in capabilities or []:
        (root / "openspec" / "specs" / name).mkdir(parents=True)
    return root


def run(root: Path, *args: str) -> int:
    return guard.main(["--repo-root", str(root), *args])


# --- the defect this guard exists to catch -------------------------------


def test_missing_precondition_is_reported(tmp_path, capsys):
    root = build_repo(
        tmp_path,
        changes={
            "coordination-root": (
                "- [ ] 2.3 After `harden-branch-adjacent-access-authority` lands, "
                "prove the seam.\n"
            )
        },
    )
    assert run(root) == guard.EXIT_MISSING
    out = capsys.readouterr().out
    assert "harden-branch-adjacent-access-authority" in out
    assert "MISSING" in out


def test_reports_task_id_and_line_number(tmp_path, capsys):
    root = build_repo(
        tmp_path,
        changes={
            "root": (
                "# Tasks\n\n"
                "- [x] 1.1 Do a thing.\n"
                "- [ ] 2.3 After `never-created-change-name` lands, proceed.\n"
            )
        },
    )
    assert run(root) == guard.EXIT_MISSING
    out = capsys.readouterr().out
    assert "task 2.3" in out
    assert "tasks.md:4" in out


# --- the discrimination that must stay GREEN ------------------------------


def test_target_of_admit_is_not_reported(tmp_path, capsys):
    """`admit X` names the task's own output; X is allowed not to exist."""
    root = build_repo(
        tmp_path,
        changes={
            "root": (
                "- [ ] 2.4 After the underlying transitions land, admit "
                "`expose-custom-agent-runtime-control` with one intent.\n"
            )
        },
    )
    assert run(root) == guard.EXIT_CLEAN
    assert "expose-custom-agent-runtime-control" not in capsys.readouterr().out


def test_precondition_flagged_while_target_on_same_line_is_not(tmp_path, capsys):
    """The real shape of the PR #2289 defect: both appear in one sentence."""
    root = build_repo(
        tmp_path,
        changes={
            "root": (
                "- [ ] 2.3 After core plus `harden-branch-access-authority` and "
                "`harden-run-branch-access-authority`, admit "
                "`enable-custom-agent-workflow-iteration` with one intent.\n"
            ),
            "harden-branch-access-authority": "- [ ] 1.1 Work.\n",
        },
    )
    assert run(root) == guard.EXIT_MISSING
    out = capsys.readouterr().out
    assert "harden-run-branch-access-authority" in out
    # The existing precondition and the target must both stay unflagged.
    assert "MISSING (1)" in out
    assert "enable-custom-agent-workflow-iteration" not in out


def test_sync_target_is_not_reported(tmp_path, capsys):
    """A change syncs into a capability spec that may not exist until it does."""
    root = build_repo(
        tmp_path,
        changes={
            "root": (
                "- [ ] 3.1 After every successor lands, sync "
                "`custom-agent-runtime-activation`, then archive.\n"
            )
        },
    )
    assert run(root) == guard.EXIT_CLEAN
    assert "custom-agent-runtime-activation" not in capsys.readouterr().out


# --- resolution paths, all GREEN -----------------------------------------


def test_active_change_resolves(tmp_path):
    root = build_repo(
        tmp_path,
        changes={
            "root": "- [ ] 1.1 After `engine-os-sandbox-thing` lands, go.\n",
            "engine-os-sandbox-thing": "- [ ] 1.1 Work.\n",
        },
    )
    assert run(root) == guard.EXIT_CLEAN


def test_archived_change_resolves_despite_date_prefix(tmp_path):
    root = build_repo(
        tmp_path,
        changes={"root": "- [ ] 1.1 After `harden-volume-restore-now` lands, go.\n"},
        archived=["2026-07-23-harden-volume-restore-now"],
    )
    assert run(root) == guard.EXIT_CLEAN


def test_capability_spec_resolves(tmp_path):
    root = build_repo(
        tmp_path,
        changes={"root": "- [ ] 1.1 After `live-mcp-connector-surface` lands, go.\n"},
        capabilities=["live-mcp-connector-surface"],
    )
    assert run(root) == guard.EXIT_CLEAN


def test_self_reference_is_not_a_dependency(tmp_path):
    root = build_repo(
        tmp_path,
        changes={
            "this-change-here": "- [ ] 1.1 After `this-change-here` settles, go.\n"
        },
    )
    assert run(root) == guard.EXIT_CLEAN


# --- false-positive suppression, all GREEN --------------------------------


@pytest.mark.parametrize(
    "token", ["read-only", "fail-closed", "two-actor", "exact-head", "not-run"]
)
def test_hyphenated_prose_is_not_a_change_name(tmp_path, token):
    """Two-segment backticked prose must never be mistaken for a change."""
    root = build_repo(
        tmp_path,
        changes={"root": f"- [ ] 1.1 After the `{token}` gate passes, proceed.\n"},
    )
    assert run(root) == guard.EXIT_CLEAN


def test_token_after_clause_boundary_is_not_a_precondition(tmp_path, capsys):
    """A semicolon ends the precondition clause."""
    root = build_repo(
        tmp_path,
        changes={
            "root": (
                "- [ ] 3.1 Resolve the substrate after reconciling "
                "`establish-postgres-control-plane`; the catalog is the "
                "public-only constant `goal-public-commons-catalog`.\n"
            ),
            "establish-postgres-control-plane": "- [ ] 1.1 Work.\n",
        },
    )
    assert run(root) == guard.EXIT_CLEAN
    assert "goal-public-commons-catalog" not in capsys.readouterr().out


def test_noun_token_before_a_dependency_list_does_not_exempt_it(tmp_path, capsys):
    """Regression: `design` was briefly a TARGET_VERB.

    Real prose reads "Blocked by its exact ledger dependencies (`design.md`
    ...): directly on `x-y-z`". Treating `design` as a target verb truncated
    the clause at `design.md` and silently exempted every dependency after it —
    a false negative in the one direction that matters.
    """
    root = build_repo(
        tmp_path,
        changes={
            "root": (
                "- [ ] 4.4 Blocked by its exact ledger dependencies "
                "(`design.md` section): directly on `absent-ledger-dependency` "
                "and the gate capabilities.\n"
            )
        },
    )
    assert run(root) == guard.EXIT_MISSING
    assert "absent-ledger-dependency" in capsys.readouterr().out


@pytest.mark.parametrize(
    "cue", ["Depend on", "Depends on", "Depending on", "Blocked on", "Requiring"]
)
def test_dependency_cue_inflections_are_recognised(tmp_path, cue):
    """Regression: only `depends on` was matched, so imperative `Depend on`
    in establish-postgres-control-plane task 4.1 was invisible."""
    root = build_repo(
        tmp_path,
        changes={"root": f"- [ ] 4.1 {cue} the landed `absent-change-name` work.\n"},
    )
    assert run(root) == guard.EXIT_MISSING


def test_register_target_is_not_a_precondition(tmp_path, capsys):
    """`register ... scenario ID `x`` produces an identifier, not a change."""
    root = build_repo(
        tmp_path,
        changes={
            "root": (
                "- [ ] 6.2 After `some-shared-protocol-change` provides the "
                "protocol, register scenario ID `branch-authority-isolation` "
                "with version 1.\n"
            ),
            "some-shared-protocol-change": "- [ ] 1.1 Work.\n",
        },
    )
    assert run(root) == guard.EXIT_CLEAN
    assert "branch-authority-isolation" not in capsys.readouterr().out


def test_local_vocabulary_is_flagged_but_still_reported(tmp_path, capsys):
    """A name the change's own design.md defines gets a hint, not silence.

    No heuristic separates "slice vocabulary that correctly has no change" from
    "planned successor that should exist and does not" — both appear in their
    change's design.md. The guard reports both and says where to look.
    """
    root = build_repo(
        tmp_path,
        changes={"root": "- [ ] 1.1 After `some-ledger-slice-name` lands, go.\n"},
    )
    (root / "openspec" / "changes" / "root" / "design.md").write_text(
        "| `some-ledger-slice-name` | unassigned | ... |\n", encoding="utf-8"
    )
    assert run(root) == guard.EXIT_MISSING
    out = capsys.readouterr().out
    assert "some-ledger-slice-name" in out
    assert "may be local vocabulary" in out


def test_local_vocabulary_hint_absent_when_prose_does_not_define_it(tmp_path, capsys):
    root = build_repo(
        tmp_path,
        changes={"root": "- [ ] 1.1 After `some-dangling-change-name` lands, go.\n"},
    )
    assert run(root) == guard.EXIT_MISSING
    assert "may be local vocabulary" not in capsys.readouterr().out


def test_paths_and_dotted_names_are_ignored(tmp_path):
    root = build_repo(
        tmp_path,
        changes={
            "root": (
                "- [ ] 1.1 After `tinyassets/api/wiki.py` and `some.module.name` "
                "are updated, go.\n"
            )
        },
    )
    assert run(root) == guard.EXIT_CLEAN


def test_line_without_dependency_cue_is_ignored(tmp_path):
    root = build_repo(
        tmp_path,
        changes={
            "root": "- [ ] 1.1 Implement `a-totally-invented-change-name` support.\n"
        },
    )
    assert run(root) == guard.EXIT_CLEAN


def test_non_task_lines_are_ignored(tmp_path):
    root = build_repo(
        tmp_path,
        changes={
            "root": (
                "## Successor ownership references (non-blocking)\n\n"
                "- `harden-run-branch-access-authority`: prose describing a "
                "planned successor after the core lands.\n"
            )
        },
    )
    assert run(root) == guard.EXIT_CLEAN


def test_empty_project_is_clean(tmp_path):
    assert run(build_repo(tmp_path)) == guard.EXIT_CLEAN


# --- fuzzy + verbose + helpers -------------------------------------------


def test_suffix_only_match_warns_rather_than_passing(tmp_path, capsys):
    root = build_repo(
        tmp_path,
        changes={"root": "- [ ] 1.1 After `renamed-change-name` lands, go.\n"},
        archived=["2026-07-23-old-prefix-renamed-change-name"],
    )
    assert run(root) == guard.EXIT_WARNING
    assert "FUZZY" in capsys.readouterr().out


def test_verbose_reports_open_task_count_of_a_precondition(tmp_path, capsys):
    root = build_repo(
        tmp_path,
        changes={
            "root": "- [ ] 1.1 After `some-other-change-here` lands, go.\n",
            "some-other-change-here": (
                "- [x] 1.1 Done.\n- [ ] 1.2 Open.\n- [ ] 1.3 Open.\n"
            ),
        },
    )
    assert run(root, "--verbose") == guard.EXIT_CLEAN
    assert "2 open task(s)" in capsys.readouterr().out


def test_scanning_a_single_change_ignores_others(tmp_path, capsys):
    root = build_repo(
        tmp_path,
        changes={
            "clean-one": "- [ ] 1.1 Nothing here.\n",
            "dirty-one": "- [ ] 1.1 After `absent-change-name-here` lands, go.\n",
        },
    )
    assert run(root, "clean-one") == guard.EXIT_CLEAN
    assert "absent-change-name-here" not in capsys.readouterr().out
    assert run(root, "dirty-one") == guard.EXIT_MISSING


def test_unknown_change_argument_is_an_error(tmp_path):
    assert run(build_repo(tmp_path), "no-such-change") == guard.EXIT_MISSING


def test_min_segments_is_configurable(tmp_path):
    root = build_repo(
        tmp_path,
        changes={"root": "- [ ] 1.1 After `two-segments` lands, go.\n"},
    )
    assert run(root) == guard.EXIT_CLEAN
    assert run(root, "--min-segments", "2") == guard.EXIT_MISSING


def test_open_task_count_counts_only_unchecked(tmp_path):
    d = tmp_path / "c"
    d.mkdir()
    (d / "tasks.md").write_text(
        "- [x] 1.1 Done.\n- [ ] 1.2 Open.\n- [X] 1.3 Done.\nnot a task\n",
        encoding="utf-8",
    )
    assert guard.open_task_count(d) == 1


def test_open_task_count_is_none_without_tasks_file(tmp_path):
    d = tmp_path / "c"
    d.mkdir()
    assert guard.open_task_count(d) is None


def test_precondition_span_empty_without_cue():
    assert guard.precondition_span("Implement `a-b-c-d` support.") == ""


def test_precondition_span_stops_at_target_verb():
    span = guard.precondition_span("After `a-b-c` lands, admit `d-e-f` next.")
    assert "a-b-c" in span
    assert "d-e-f" not in span


def test_cue_requires_word_boundary():
    """'afterwards' and 'reopen' must not register as dependency cues."""
    assert guard.precondition_span("Afterwards reopen `a-b-c-d` handling.") == ""


# --- the real repository --------------------------------------------------


def test_runs_against_the_real_repo_without_crashing(capsys):
    """Whatever the verdict, the guard must survive real task prose."""
    if not (REPO_ROOT / "openspec" / "changes").is_dir():
        pytest.skip("no openspec/ in this checkout")
    code = guard.main(["--repo-root", str(REPO_ROOT)])
    assert code in (guard.EXIT_CLEAN, guard.EXIT_WARNING, guard.EXIT_MISSING)
    assert "change(s) scanned" in capsys.readouterr().out
