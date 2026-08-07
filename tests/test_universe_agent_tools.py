"""The universe agent's file tools: what they let in, and what they keep out.

Both directions are load-bearing. A containment check that refuses EVERYTHING
passes any reject-only suite while making the feature useless — the same shape
as the allowlist that rejected 100% of real inputs while green (see the
`silent-failure-dispatch-and-tests` class). So every "must refuse" case here has
a matching "must allow".
"""

from __future__ import annotations

import pytest

from tinyassets.universe_agent_tools import (
    MAX_WRITE_BYTES,
    AgentToolError,
    UniverseWorkspace,
    delete_file,
    list_files,
    read_file,
    write_file,
)


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "u-test"
    (root / "wiki" / "drafts").mkdir(parents=True)
    (root / "founder.md").write_text("My founder is Jonathan.\n", encoding="utf-8")
    (root / ".credentials" / "claude").mkdir(parents=True)
    (root / ".credentials" / "claude" / ".claude.json").write_text(
        '{"oauth":"super-secret"}', encoding="utf-8"
    )
    # A sibling universe that must stay invisible.
    (tmp_path / "u-other").mkdir()
    (tmp_path / "u-other" / "founder.md").write_text("someone else", encoding="utf-8")
    return UniverseWorkspace.for_dir(root)


# --------------------------------------------------------------------------
# ACCEPT — the feature actually works
# --------------------------------------------------------------------------


def test_reads_a_file_in_its_own_workspace(workspace):
    assert "Jonathan" in read_file(workspace, "founder.md")


def test_writes_and_reads_back(workspace):
    written = write_file(workspace, "identity.md", "I am Tiny.\n")
    assert written == "identity.md"
    assert read_file(workspace, "identity.md") == "I am Tiny.\n"


def test_writes_into_a_nested_path_creating_dirs(workspace):
    written = write_file(workspace, "agents/hermes/AGENT.md", "# Hermes\n")
    assert written == "agents/hermes/AGENT.md"
    assert read_file(workspace, "agents/hermes/AGENT.md") == "# Hermes\n"


def test_overwrites_an_existing_file(workspace):
    write_file(workspace, "founder.md", "updated\n")
    assert read_file(workspace, "founder.md") == "updated\n"


def test_lists_its_own_workspace(workspace):
    entries = list_files(workspace)
    assert "founder.md" in entries
    assert "wiki/" in entries


def test_deletes_a_file_it_owns(workspace):
    write_file(workspace, "scratch.md", "temp")
    assert delete_file(workspace, "scratch.md") == "scratch.md"
    with pytest.raises(AgentToolError):
        read_file(workspace, "scratch.md")


def test_a_dot_subpath_lists_the_root(workspace):
    assert list_files(workspace, ".") == list_files(workspace)


# --------------------------------------------------------------------------
# REFUSE — containment
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "../u-other/founder.md",
        "wiki/../../u-other/founder.md",
        "./../../u-other/founder.md",
    ],
)
def test_parent_traversal_is_refused(workspace, path):
    with pytest.raises(AgentToolError, match="escapes|relative"):
        read_file(workspace, path)


@pytest.mark.parametrize("path", ["/etc/passwd", "C:\\Windows\\win.ini", "\\\\host\\share"])
def test_absolute_paths_are_refused(workspace, path):
    with pytest.raises(AgentToolError, match="relative"):
        read_file(workspace, path)


def test_writing_outside_is_refused_not_just_reading(workspace):
    """The write path must be guarded independently of the read path."""
    with pytest.raises(AgentToolError):
        write_file(workspace, "../u-other/pwned.md", "hi")
    assert not (workspace.root.parent / "u-other" / "pwned.md").exists()


def test_a_symlink_escaping_the_root_is_refused(workspace, tmp_path):
    """resolve() collapses the link BEFORE the containment check.

    A prefix/string check would pass this — the link's own path is inside the
    workspace. Only resolving first catches it.
    """
    link = workspace.root / "escape"
    try:
        link.symlink_to(tmp_path / "u-other", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")
    with pytest.raises(AgentToolError, match="escapes"):
        read_file(workspace, "escape/founder.md")


def test_the_credential_vault_is_unreachable(workspace):
    """Containment alone is not enough — the vault lives INSIDE the workspace."""
    with pytest.raises(AgentToolError, match="reserved"):
        read_file(workspace, ".credentials/claude/.claude.json")
    with pytest.raises(AgentToolError, match="reserved"):
        write_file(workspace, ".credentials/claude/.claude.json", "{}")
    assert ".credentials/" not in list_files(workspace)


def test_an_empty_path_is_refused(workspace):
    with pytest.raises(AgentToolError, match="required"):
        read_file(workspace, "   ")


def test_oversized_content_is_refused(workspace):
    with pytest.raises(AgentToolError, match="too large"):
        write_file(workspace, "big.md", "x" * (MAX_WRITE_BYTES + 1))
    assert not (workspace.root / "big.md").exists()


def test_a_sibling_universe_sharing_a_name_prefix_is_refused(workspace, tmp_path):
    """`/data/u-test-evil` must not pass a check against `/data/u-test`.

    This is why containment is `is_relative_to` on resolved paths and never a
    string prefix — `str(sibling).startswith(str(root))` is TRUE here.
    """
    sibling = tmp_path / "u-test-evil"
    sibling.mkdir()
    (sibling / "loot.md").write_text("loot", encoding="utf-8")
    assert str(sibling).startswith(str(workspace.root))  # the trap, made explicit
    with pytest.raises(AgentToolError):
        read_file(workspace, "../u-test-evil/loot.md")


def test_the_workspace_itself_cannot_be_overwritten(workspace):
    with pytest.raises(AgentToolError):
        write_file(workspace, ".", "clobber")


def test_a_missing_workspace_is_refused_at_construction(tmp_path):
    with pytest.raises(AgentToolError, match="no workspace"):
        UniverseWorkspace.for_dir(tmp_path / "does-not-exist")
