"""Unit tests for command_center.parsers — pure parsing, no I/O beyond tmp files."""

from __future__ import annotations

import json
from pathlib import Path

from command_center import parsers


def test_slugify():
    assert parsers.slugify("Claude Code v2!") == "claude-code-v2"
    assert parsers.slugify("___") == "agent"
    assert len(parsers.slugify("x" * 100)) <= 40


def test_tail_jsonl_reads_last_lines(tmp_path: Path):
    path = tmp_path / "t.jsonl"
    path.write_text(
        "\n".join(json.dumps({"i": i}) for i in range(10)) + "\nnot-json\n", encoding="utf-8"
    )
    entries = parsers.tail_jsonl(path, max_lines=5)
    assert [e["i"] for e in entries] == [7, 8, 9]


def test_iso_to_epoch():
    assert parsers.iso_to_epoch("2026-07-19T21:46:50Z") is not None
    assert parsers.iso_to_epoch("garbage") is None
    assert parsers.iso_to_epoch(123) is None


def test_parse_status_claims():
    status = """## Work

| Task | Files | Depends | Status |
|------|-------|---------|--------|
| Build the thing | workflow/a.py, docs/b.md | - | claimed:codex-gpt5-desktop ACTIVE 2026-06-27 |
| Waiting row | x.py | - | dev-ready |
| Another | y.py | #1 | in-flight |

## Next
"""
    claims = parsers.parse_status_claims(status)
    assert len(claims) == 2
    assert claims[0]["provider"] == "codex-gpt5-desktop"
    assert claims[0]["active"] is True
    assert claims[0]["files"] == ["workflow/a.py", "docs/b.md"]
    assert claims[1]["status"] == "in-flight"


def test_parse_claude_transcript():
    entries = [
        {
            "type": "user",
            "timestamp": "2026-07-19T10:00:00Z",
            "cwd": "C:\\repo",
            "sessionId": "abc123",
            "message": {"role": "user", "content": "hi"},
        },
        {
            "type": "assistant",
            "timestamp": "2026-07-19T10:01:00Z",
            "isSidechain": True,
            "message": {
                "model": "claude-test",
                "content": [
                    {"type": "tool_use", "name": "Edit",
                     "input": {"file_path": "C:\\repo\\workflow\\x.py"}}
                ],
            },
        },
        {"type": "last-prompt", "lastPrompt": "fix the bug", "sessionId": "abc123"},
    ]
    info = parsers.parse_claude_transcript(entries)
    assert info["cwd"] == "C:\\repo"
    assert info["action"] == "editing C:\\repo\\workflow\\x.py"
    assert info["file"] == "C:\\repo\\workflow\\x.py"
    assert info["sidechain"] is True
    assert info["last_prompt"] == "fix the bug"
    assert info["model"] == "claude-test"
    assert info["ts"] is not None


def test_parse_codex_rollout():
    entries = [
        {
            "timestamp": "2026-07-19T09:00:00Z",
            "type": "session_meta",
            "payload": {"type": "session_meta", "cwd": "C:\\repo", "id": "rollout-9"},
        },
        {
            "timestamp": "2026-07-19T09:05:00Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "shell",
                "arguments": json.dumps({"command": ["pytest", "-q"]}),
            },
        },
    ]
    info = parsers.parse_codex_rollout(entries)
    assert info["cwd"] == "C:\\repo"
    assert info["action"] == "running pytest -q"
    assert info["ts"] is not None


def test_parse_activity_log_mixed_eras():
    text = (
        "2026-06-24 [claude-code] shipped the config mechanism\n"
        "[2026-05-30] claude-code: merged enqueue verb\n"
        "short\n"
        "- 2026-04-09T21:30:00-07:00 [codex] added seed surfaces\n"
    )
    events = parsers.parse_activity_log(text)
    assert len(events) == 3
    assert events[0]["actor"] == "claude-code"
    assert "config mechanism" in events[0]["text"]
    assert events[1]["actor"] == "claude-code"
    assert events[2]["actor"] == "codex"


def test_zone_for_relpath_longest_prefix():
    zones = {"keep": "workflow", "api": "workflow/api", "square": ""}
    assert parsers.zone_for_relpath("workflow/api/universe.py", zones) == "api"
    assert parsers.zone_for_relpath("workflow/graph.py", zones) == "keep"
    assert parsers.zone_for_relpath("random.txt", zones) == "square"


def test_norm_rel(tmp_path: Path):
    assert parsers.norm_rel(str(tmp_path / "a" / "b.py"), tmp_path) == "a/b.py"
    assert parsers.norm_rel("C:\\elsewhere\\x.py", tmp_path) is None


def test_make_label():
    assert parsers.make_label("fix the flaky test") == "fix the flaky test"
    assert parsers.make_label("") == ""
    assert parsers.make_label(None) == ""
    assert parsers.make_label("<system-reminder>stuff") == ""
    long = parsers.make_label("word " * 30, max_len=34)
    assert long.endswith("…") and len(long) <= 35
    assert parsers.make_label("  spaced\n\nout   text ") == "spaced out text"


def test_parse_claude_transcript_opening_prompt_and_branch():
    entries = [
        {
            "type": "queue-operation",
            "operation": "enqueue",
            "timestamp": "2026-07-19T10:00:00Z",
            "sessionId": "abc123",
            "content": "Refactor the lease store module",
            "gitBranch": "feat/lease-store",
        },
        {
            "type": "assistant",
            "timestamp": "2026-07-19T10:02:00Z",
            "message": {"content": [{"type": "tool_use", "name": "Read",
                                     "input": {"file_path": "C:\\repo\\lease_store.py"}}]},
        },
    ]
    info = parsers.parse_claude_transcript(entries)
    assert info["first_prompt"] == "Refactor the lease store module"
    assert info["branch"] == "feat/lease-store"
    assert info["action"].startswith("reading")
