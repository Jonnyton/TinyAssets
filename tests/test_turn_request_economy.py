"""Resident orientation and greeting restraint after prod turn bdec018e."""

import pytest

from tests import test_interactive_http_agent as http
from tinyassets import universe_files, universe_intelligence, universe_tools
from tinyassets.daemon_server import get_founder_home

rig = http.rig
reader = http.reader
served = http.served
agent = http.agent
run = http.run
HEADING = "## What is in my folder now"


def seed(root):
    (root / "workflows/x").mkdir(parents=True)
    (root / "workflows/x/index.html").write_bytes(b"x" * 1024)
    (root / "notes").mkdir(exist_ok=True)
    (root / "notes/a.md").write_bytes(b"a" * 2048)


def test_folder_paths_sizes_sort_and_two_levels(tmp_path):
    seed(tmp_path)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts/z.txt").write_text("prompt")
    (tmp_path / "workflows/x/deeper").mkdir()
    (tmp_path / "workflows/x/deeper/hidden.txt").write_text("hidden")
    text = universe_tools.harness_prompt(tmp_path).split(HEADING)[1]
    assert "notes/a.md (2.0 KB)" in text
    assert "workflows/x/index.html (1.0 KB)" in text
    assert "prompts/z.txt" in text
    assert "hidden.txt" not in text
    lines = [line for line in text.splitlines() if line.startswith("- ")]
    assert lines == sorted(lines)


def test_folder_listing_is_bounded(tmp_path):
    (tmp_path / "notes").mkdir()
    for n in range(100):
        (tmp_path / f"notes/{n:03}.md").touch()
    text = universe_tools.harness_prompt(tmp_path).split(HEADING)[1]
    assert len([line for line in text.splitlines() if line.startswith("- ")]) == 40
    assert "60 more entries; `bash ls` shows them" in text


@pytest.mark.parametrize("directory", [False, True])
def test_external_symlink_is_not_followed_or_listed(tmp_path, directory):
    root = tmp_path / "universe"
    seed(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("foreign")
    try:
        (root / "notes/link").symlink_to(
            outside if directory else secret, target_is_directory=directory,
        )
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip("Windows process lacks symlink privilege; requires Linux oracle")
        raise
    text = universe_tools.harness_prompt(root)
    assert "notes/a.md" in text
    assert "link" not in text and "secret.txt" not in text and "foreign" not in text


def test_unreadable_directory_omits_entire_section(tmp_path, monkeypatch):
    seed(tmp_path)
    original = universe_files.list_universe_entries

    def unreadable(root, path):
        if path == "workflows/x":
            raise PermissionError("unreadable")
        return original(root, path)

    monkeypatch.setattr(universe_files, "list_universe_entries", unreadable)
    assert HEADING not in universe_tools.harness_prompt(tmp_path)


def test_resident_batching_and_direct_ui_install(tmp_path):
    text = universe_tools.harness_prompt(tmp_path)
    assert "independent reads or checks" in text
    assert "together in one reply, not one per reply" in text
    assert 'write_graph target="app_ui" operation="add_ui"' in text
    assert 'payload_json={"component": {...}}' in text
    assert "write_graph.interfaces" in text
    assert "rather than staging pieces in /u files and reading them back" in text


def test_continuity_greeting_is_one_contextual_reply():
    text = universe_intelligence._CROSS_SURFACE_CONTINUITY
    assert "one thread" in text
    assert "answer in context in one reply" in text
    assert "where any unfinished work stands and what I would do next" in text
    assert "do not start or resume multi-step work on a greeting alone" in text


def test_scripted_greeting_request_count(agent, monkeypatch, signed_in):
    """Measure pipeline requests, not whether a real model obeys the prompt.

    The scripted model asks for zero tool rounds; the real served path must
    add no orientation requests of its own (at most reply plus learning).
    """
    root = agent.served.context.universe_dir
    seed(root)
    agent.requested_rounds = 0
    from tinyassets import daemon_server

    monkeypatch.setattr(daemon_server, "get_founder_home", get_founder_home)
    signed_in("owner")
    monkeypatch.setattr(universe_intelligence, "_universe_dir", lambda uid: root)
    assert run(agent, greeting=True) == "finished exact answer"
    assert 1 <= len(agent.wires) <= 2
    assert agent.latest().state == "completed"
    assert len(agent.wires) == 2, "the existing learning pass is counted too"
    messages = agent.wires[0][1]["body"]["messages"]
    system = next(message["content"] for message in messages if message["role"] == "system")
    assert HEADING in system
    assert "workflows/x/index.html" in system and "notes/a.md" in system
    assert any(message["role"] == "user" and message["content"] == "hi" for message in messages)
