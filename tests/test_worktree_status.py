from __future__ import annotations

import importlib.util
import io
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "worktree_status.py"
SPEC = importlib.util.spec_from_file_location("worktree_status", SCRIPT)
assert SPEC is not None
worktree_status = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = worktree_status
SPEC.loader.exec_module(worktree_status)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_parse_porcelain_branch_and_detached_entries() -> None:
    text = """worktree C:/repo
HEAD abc123
branch refs/heads/main

worktree C:/repo-review
HEAD def456
detached

"""

    entries = worktree_status.parse_porcelain(text)

    assert len(entries) == 2
    assert entries[0].slug == "repo"
    assert entries[0].branch == "main"
    assert entries[1].detached is True
    assert entries[1].branch == "(detached HEAD)"


def test_classify_dirty_overrides_everything() -> None:
    assert (
        worktree_status.classify(
            dirty=True,
            purpose_exists=False,
            purpose_complete=False,
            age_hours=100,
            upstream="none",
        )
        == "IN_FLIGHT_NEEDS_PURPOSE"
    )


def test_classify_dirty_current_checkout_is_explicit() -> None:
    assert (
        worktree_status.classify(
            dirty=True,
            purpose_exists=False,
            purpose_complete=False,
            age_hours=1,
            upstream="none",
            current=True,
        )
        == "DIRTY_CURRENT_NEEDS_PURPOSE"
    )


def test_classify_orphaned_requires_missing_purpose_old_and_untracked() -> None:
    assert (
        worktree_status.classify(
            dirty=False,
            purpose_exists=False,
            purpose_complete=False,
            age_hours=25,
            upstream="none",
        )
        == "ORPHANED"
    )
    assert (
        worktree_status.classify(
            dirty=False,
            purpose_exists=False,
            purpose_complete=False,
            age_hours=1,
            upstream="none",
        )
        == "NEEDS_PURPOSE"
    )


def test_classify_ready_to_remove_when_upstream_gone() -> None:
    assert (
        worktree_status.classify(
            dirty=False,
            purpose_exists=True,
            purpose_complete=True,
            age_hours=1,
            upstream="gone",
        )
        == "READY_TO_REMOVE"
    )


def test_classify_ready_to_remove_when_branch_fully_merged() -> None:
    assert (
        worktree_status.classify(
            dirty=False,
            purpose_exists=False,
            purpose_complete=False,
            age_hours=1,
            upstream="tracking",
            branch="codex/landed-fix",
            fully_merged=True,
        )
        == "READY_TO_REMOVE"
    )


def test_ready_to_remove_action_uses_underscore_state() -> None:
    action = worktree_status._action_for_state(
        state="READY_TO_REMOVE",
        current=False,
        live_safety="ISOLATED_UNTIL_MERGED",
        status_ref=False,
    )

    assert "Log remove/sweep" in action


def test_ready_to_remove_sweep_commands_remove_worktree_and_local_branch() -> None:
    status = worktree_status.WorktreeStatus(
        slug="wf-landed",
        path="/tmp/wf-landed",
        branch="codex/landed-fix",
        head="abc123",
        state="READY_TO_REMOVE",
        age_hours=1,
        upstream="tracking",
        dirty=False,
        current=False,
        live_safety="ISOLATED_UNTIL_MERGED",
        status_ref=False,
        purpose_exists=False,
        purpose_missing_fields=[],
        purpose="-",
        memory_refs=[],
        action="Log remove/sweep in .agents/worktrees.md after ideas are extracted.",
    )

    commands = worktree_status.sweep_commands([status])

    assert commands == [
        "git worktree remove /tmp/wf-landed",
        "git branch -d codex/landed-fix",
    ]


def test_build_status_handles_missing_worktree_path(tmp_path: Path) -> None:
    missing = tmp_path / "wf-missing"

    status = worktree_status.build_status(
        worktree_status.WorktreeEntry(
            path=str(missing),
            head="abc123",
            branch_ref="refs/heads/codex/missing",
        ),
        repo=tmp_path,
    )

    assert status.state == "MISSING"
    assert "path missing" in status.action


def test_build_status_marks_fully_merged_branch_ready_to_remove(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    topic_path = tmp_path / "wf-topic"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "checkout", "-q", "-b", "codex/topic")
    (repo / "topic.txt").write_text("topic\n", encoding="utf-8")
    _git(repo, "add", "topic.txt")
    _git(repo, "commit", "-q", "-m", "topic")
    topic_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "codex/topic", "-m", "merge topic")
    _git(repo, "worktree", "add", "-q", str(topic_path), "codex/topic")

    status = worktree_status.build_status(
        worktree_status.WorktreeEntry(
            path=str(topic_path),
            head=topic_head,
            branch_ref="refs/heads/codex/topic",
        ),
        repo=repo,
    )

    assert status.state == "READY_TO_REMOVE"


def test_classify_clean_local_branch_with_purpose_needs_pr_or_status() -> None:
    assert (
        worktree_status.classify(
            dirty=False,
            purpose_exists=True,
            purpose_complete=True,
            age_hours=1,
            upstream="none",
            branch="codex/demo",
        )
        == "NEEDS_PR_OR_STATUS"
    )


def test_classify_status_ref_makes_active_lane() -> None:
    assert (
        worktree_status.classify(
            dirty=False,
            purpose_exists=True,
            purpose_complete=True,
            age_hours=30,
            upstream="tracking",
            status_ref=True,
            branch="codex/demo",
        )
        == "ACTIVE_LANE"
    )


def test_render_table_includes_state_branch_and_purpose() -> None:
    status = worktree_status.WorktreeStatus(
        slug="wf-demo",
        path="C:/wf-demo",
        branch="codex/demo",
        head="abc123",
        state="ACTIVE_LANE",
        age_hours=1.25,
        upstream="tracking",
        dirty=False,
        current=True,
        live_safety="ISOLATED_UNTIL_MERGED",
        status_ref=True,
        purpose_exists=True,
        purpose_missing_fields=[],
        purpose="demo purpose",
        memory_refs=[".claude/agent-memory/navigator/demo.md"],
        action="Pickup through STATUS Files/Depends/Status; do not bypass gates.",
    )

    table = worktree_status.render_table([status])

    assert "wf-demo" in table
    assert "ACTIVE_LANE" in table
    assert "yes" in table
    assert "codex/demo" in table
    assert "1" in table
    assert "Pickup through STATUS" in table
    assert "demo purpose" in table
    assert "state map" in table


def test_force_utf8_stdio_reconfigures_narrow_windows_streams(monkeypatch) -> None:
    class NarrowStream:
        encoding = "cp1252"

        def __init__(self) -> None:
            self.reconfigured_to: str | None = None

        def reconfigure(self, *, encoding: str) -> None:
            self.reconfigured_to = encoding

    stdout = NarrowStream()
    stderr = NarrowStream()
    monkeypatch.setattr(worktree_status.sys, "stdout", stdout)
    monkeypatch.setattr(worktree_status.sys, "stderr", stderr)

    worktree_status._force_utf8_stdio()

    assert stdout.reconfigured_to == "utf-8"
    assert stderr.reconfigured_to == "utf-8"


def test_force_utf8_stdio_wraps_legacy_stream_buffer(monkeypatch) -> None:
    class LegacyNarrowStream:
        encoding = "cp1252"

        def __init__(self) -> None:
            self.buffer = io.BytesIO()

    stdout = LegacyNarrowStream()
    monkeypatch.setattr(worktree_status.sys, "stdout", stdout)

    worktree_status._force_utf8_stdio()
    worktree_status.sys.stdout.write("branch → ready\n")
    worktree_status.sys.stdout.flush()

    assert stdout.buffer.getvalue().decode("utf-8") == "branch → ready\n"


def test_memory_refs_read_from_purpose_file(tmp_path: Path) -> None:
    (tmp_path / "_PURPOSE.md").write_text(
        "\n".join(
            [
                "Purpose: demo",
                "Memory refs:",
                "- .claude/agent-memory/navigator/demo.md",
                "- .agents/activity.log",
            ]
        ),
        encoding="utf-8",
    )

    assert worktree_status._memory_refs(tmp_path) == [
        ".claude/agent-memory/navigator/demo.md",
        ".agents/activity.log",
    ]


def test_memory_refs_read_provider_agnostic_memory_block(tmp_path: Path) -> None:
    (tmp_path / "_PURPOSE.md").write_text(
        "\n".join(
            [
                "Purpose: demo",
                "Memory refs:",
                "- .cursor/rules/workflow.mdc",
                "- .codex/session-notes.md",
                "Related implications:",
                "- docs/audits/demo.md",
            ]
        ),
        encoding="utf-8",
    )

    assert worktree_status._memory_refs(tmp_path) == [
        ".cursor/rules/workflow.mdc",
        ".codex/session-notes.md",
    ]


def test_purpose_missing_fields_detects_incomplete_template(tmp_path: Path) -> None:
    (tmp_path / "_PURPOSE.md").write_text("Purpose: demo\nBranch: codex/demo\n", encoding="utf-8")

    missing = worktree_status._purpose_missing_fields(tmp_path)

    assert "Provider:" in missing
    assert "Idea feed refs:" in missing
