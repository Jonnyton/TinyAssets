"""Tests for command_center.collector — fixture repos + homes in tmp_path."""

from __future__ import annotations

import json
import time
from pathlib import Path

from command_center import collector


def make_cfg(tmp_path: Path) -> collector.Config:
    """A Config rooted at a fake repo with fake provider homes, no network."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "workflow").mkdir()
    (root / "docs").mkdir()
    (root / "STATUS.md").write_text(
        "| Task | Files | Depends | Status |\n"
        "|------|-------|---------|--------|\n"
        "| Fix the compiler | workflow/graph_compiler.py | - | claimed:kimi ACTIVE 2026-07-19 |\n",
        encoding="utf-8",
    )
    cfg = collector.Config(
        root=root,
        directory_url=None,  # offline in tests
        inbox_dir=root / ".agents" / "village-inbox",
        claude_home=tmp_path / "claude",
        codex_home=tmp_path / "codex",
        kimi_home=tmp_path / "kimi",
        data_dirs=[tmp_path / "data"],
    )
    return cfg


def make_universe(data_root: Path, uid: str = "u-test123") -> Path:
    udir = data_root / uid
    udir.mkdir(parents=True)
    (udir / "identity.md").write_text("name: Castles Test\n", encoding="utf-8")
    (udir / "soul.md").write_text(
        "# Castles\n\nA fantasy kingdom of castles and dragons and long quests.\n",
        encoding="utf-8",
    )
    (udir / "config.yaml").write_text(
        "preferred_writer: claude\npreferred_judge: codex\n", encoding="utf-8"
    )
    (udir / "log.md").write_text("line one\nline two: wrote chapter 3\n", encoding="utf-8")
    return udir


def test_discover_zones_only_existing(tmp_path: Path):
    cfg = make_cfg(tmp_path)
    zones = collector.discover_zones(cfg, [], [], time.time())
    ids = {z["id"] for z in zones}
    assert "keep" in ids and "docs" in ids and "square" in ids
    assert "web" not in ids  # WebSite/ does not exist in the fixture


def test_discover_zones_heat(tmp_path: Path):
    cfg = make_cfg(tmp_path)
    now = time.time()
    recent = [("workflow/a.py", now - 60), ("workflow/b.py", now - 60), ("docs/c.md", now - 7200)]
    zones = {z["id"]: z for z in collector.discover_zones(cfg, [], recent, now)}
    assert zones["keep"]["heat"] == 2
    assert zones["docs"]["heat"] == 0  # older than 15 minutes


def test_discover_universes_local(tmp_path: Path):
    cfg = make_cfg(tmp_path)
    make_universe(cfg.data_dirs[0])
    universes = collector.discover_universes(cfg, time.time())
    assert len(universes) == 1
    u = universes[0]
    assert u["id"] == "u-test123"
    assert u["name"] == "Castles Test"
    assert u["emoji"] == "🏰"  # fantasy keyword
    assert u["preset"] == "claude / codex"
    assert u["last_activity"] == "line two: wrote chapter 3"
    assert u["source"] == "local"


def test_talk_to_universe_writes_engine_note(tmp_path: Path):
    cfg = make_cfg(tmp_path)
    udir = make_universe(cfg.data_dirs[0])
    (udir / "notes.json").write_text("[]", encoding="utf-8")
    result = collector.talk(cfg, "universe:u-test123", "more dragons please")
    assert result["ok"] is True
    assert result["mode"] == "notes.json"
    notes = json.loads((udir / "notes.json").read_text(encoding="utf-8"))
    assert len(notes) == 1
    note = notes[0]
    assert note["source"] == "user"
    assert note["category"] == "direction"
    assert note["status"] == "unread"
    assert note["text"] == "more dragons please"
    assert isinstance(note["timestamp"], float)


def test_talk_to_dormant_universe_pins_inbox(tmp_path: Path):
    cfg = make_cfg(tmp_path)
    udir = make_universe(cfg.data_dirs[0])  # no notes.json → dormant path
    result = collector.talk(cfg, "universe:u-test123", "wake up soon")
    assert result["ok"] is True
    assert result["mode"] == "village-inbox"
    assert "wake up soon" in (udir / "village-inbox.md").read_text(encoding="utf-8")


def test_talk_to_agent_and_chat_history(tmp_path: Path):
    cfg = make_cfg(tmp_path)
    result = collector.talk(cfg, "agent:claude-abc123", "how is it going?")
    assert result["ok"] is True
    assert result["mode"] == "inbox"
    messages = collector.chat_history(cfg, "agent:claude-abc123")
    assert len(messages) == 1
    assert messages[0]["who"] == "host"
    assert "how is it going?" in messages[0]["text"]


def test_talk_rejects_bad_target(tmp_path: Path):
    cfg = make_cfg(tmp_path)
    assert collector.talk(cfg, "nope", "hi")["ok"] is False
    assert collector.talk(cfg, "universe:missing", "hi")["ok"] is False


def test_detect_agents_from_claude_transcript(tmp_path: Path):
    cfg = make_cfg(tmp_path)
    project = cfg.claude_home / "projects" / "C--fake-repo"
    project.mkdir(parents=True)
    entries = [
        {
            "type": "assistant",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cwd": str(cfg.root),
            "sessionId": "deadbeefcafe",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Edit",
                        "input": {"file_path": str(cfg.root / "workflow" / "graph.py")},
                    }
                ]
            },
        }
    ]
    (project / "deadbeef-cafe.jsonl").write_text(
        "\n".join(json.dumps(e) for e in entries), encoding="utf-8"
    )
    now = time.time()
    zones = collector.discover_zones(cfg, [], [], now)
    agents = collector.detect_agents(cfg, [], zones, now)
    claude = [a for a in agents if a["provider"] == "claude"]
    assert claude, f"expected a claude agent, got {agents}"
    assert claude[0]["zone"] == "keep"
    assert "editing" in claude[0]["action"]
    assert claude[0]["status"] == "active"


def test_detect_agents_from_status_claim(tmp_path: Path):
    cfg = make_cfg(tmp_path)
    now = time.time()
    zones = collector.discover_zones(cfg, [], [], now)
    agents = collector.detect_agents(cfg, [], zones, now)
    claimed = [a for a in agents if a["id"].startswith("claim-")]
    assert claimed
    assert claimed[0]["provider"] == "kimi"
    assert "Fix the compiler" in claimed[0]["action"]
    assert claimed[0]["zone"] == "keep"


def test_snapshot_shape_offline(tmp_path: Path):
    cfg = make_cfg(tmp_path)
    make_universe(cfg.data_dirs[0])
    snap = collector.snapshot(cfg)
    for key in ("generated_at", "repo", "day_phase", "zones", "agents", "universes",
                "world", "events", "stats"):
        assert key in snap, key
    assert snap["repo"] == "repo"
    assert snap["world"]["reachable"] is False
    assert snap["stats"]["universes_total"] == 1


def test_kimi_agent_named_by_session_title(tmp_path: Path):
    cfg = make_cfg(tmp_path)
    sdir = cfg.kimi_home / "sessions" / "wd_repo_ab12" / "session_abc12345-xyz"
    sdir.mkdir(parents=True)
    (cfg.kimi_home / "session_index.jsonl").write_text(
        json.dumps({
            "sessionId": "session_abc12345-xyz",
            "sessionDir": str(sdir),
            "workDir": str(cfg.root),
        }) + "\n",
        encoding="utf-8",
    )
    (sdir / "state.json").write_text(
        json.dumps({
            "title": "build a command center for my phone",
            "agents": {"main": {"homedir": str(sdir / "agents" / "main"),
                                "type": "main", "parentAgentId": None}},
        }),
        encoding="utf-8",
    )
    now = time.time()
    zones = collector.discover_zones(cfg, [], [], now)
    agents = collector.detect_agents(cfg, [], zones, now)
    kimi = [a for a in agents if a["provider"] == "kimi" and a["kind"] == "main"]
    assert kimi, f"expected a kimi agent, got {agents}"
    assert kimi[0]["name"] == "build a command center for my…"
    assert kimi[0]["label"]
    assert kimi[0]["serial"] == "abc12345"


def test_universe_name_skips_okf_frontmatter(tmp_path: Path):
    data = tmp_path / "data"
    udir = data / "u-abc123"
    udir.mkdir(parents=True)
    (udir / "identity.md").write_text(
        "---\ntype: Universe Identity\nstatus: not-learned\n---\n\n"
        "# Identity\n\nI do not yet know my name or what I am.\n",
        encoding="utf-8",
    )
    name = collector._universe_name(udir, data)
    assert name.startswith("unnamed mind"), name
    assert "type" not in name


def test_universe_name_from_root_index(tmp_path: Path):
    data = tmp_path / "data"
    udir = data / "u-abc123"
    udir.mkdir(parents=True)
    (data / "universes.md").write_text(
        "| Universe id | Learned name |\n| --- | --- |\n"
        "| `u-abc123` | Castle Concordance | not-learned |\n",
        encoding="utf-8",
    )
    assert collector._universe_name(udir, data) == "Castle Concordance"


def test_universe_name_never_returns_yes_no_cells(tmp_path: Path):
    """Regression: full index rows have brain/canon/wiki yes-no cells — those
    must never be mistaken for a learned name."""
    data = tmp_path / "data"
    udir = data / "u-xyz789"
    udir.mkdir(parents=True)
    (data / "universes.md").write_text(
        "| Universe id | Learned name | Identity status | Brain | Canon | Wiki |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| `u-xyz789` | Not learned yet | not-learned | [index](u-xyz789/index.md) | yes | no |\n",
        encoding="utf-8",
    )
    name = collector._universe_name(udir, data)
    assert name.startswith("unnamed mind"), name


def test_strip_frontmatter():
    assert collector._strip_frontmatter("---\na: 1\n---\nbody") == "body"
    assert collector._strip_frontmatter("no fence") == "no fence"


def test_live_universe_mapping():
    entry = {
        "id": "echoes-of-the-cosmos",
        "word_count": 12000,
        "phase_human": "writing chapter 4",
        "staleness": "fresh",
        "last_activity_at": "2026-07-20T05:43:59+00:00",
        "accept_rate": 0.9,
    }
    universe = collector._live_universe(entry)
    assert universe is not None
    assert universe["name"] == "Echoes Of The Cosmos"
    assert universe["status"] == "alive"
    assert universe["words"] == 12000
    assert universe["ts"] is not None
    assert universe["brief"]["accept_rate"] == 0.9
    assert collector._live_universe({"id": ""}) is None
