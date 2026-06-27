from __future__ import annotations

from pathlib import Path

import pytest

from fantasy_daemon.__main__ import (
    _record_loop_daemon_signal,
    _resolve_loop_daemon_context,
)
from tinyassets import daemon_registry, daemon_wiki


def test_loop_identity_prefers_project_default_soul_daemon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    universe_path = tmp_path / "default-universe"
    universe_path.mkdir()
    daemon = daemon_registry.create_daemon(
        tmp_path,
        display_name="TinyAssets Developer Daemon",
        created_by="host",
        soul_text="Work hard on TinyAssets uptime and verify every change.",
        domain_claims=["developer", "workflow-platform", "loop-runner"],
        metadata={"project_loop_default": True},
    )

    context = _resolve_loop_daemon_context(universe_path, "default-universe")

    assert context["daemon_id"] == daemon["daemon_id"]
    assert context["source"] == "project_loop_default"
    assert context["has_soul"] is True
    assert context["domain_claims"] == [
        "developer",
        "workflow-platform",
        "loop-runner",
    ]
    assert "Work hard on TinyAssets uptime" in context["soul_text"]
    assert "Daemon Wiki Schema" in context["daemon_wiki_context"]


def test_loop_identity_env_override_fails_loudly_for_unknown_daemon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_LOOP_DAEMON_ID", "daemon::missing")
    universe_path = tmp_path / "default-universe"
    universe_path.mkdir()

    with pytest.raises(RuntimeError, match="does not match a registered daemon"):
        _resolve_loop_daemon_context(universe_path, "default-universe")


def test_loop_signal_records_into_soul_daemon_wiki(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    universe_path = tmp_path / "default-universe"
    universe_path.mkdir()
    daemon = daemon_registry.create_daemon(
        tmp_path,
        display_name="TinyAssets Developer Daemon",
        created_by="host",
        soul_text="Learn from loop outcomes without changing the soul casually.",
        metadata={"project_loop_default": True},
    )
    context = _resolve_loop_daemon_context(universe_path, "default-universe")

    _record_loop_daemon_signal(
        context,
        universe_path=universe_path,
        source_id="branch-task-1",
        outcome="failed",
        summary="Verification failed after a loop run.",
        details="The daemon must tighten its pre-final checks.",
    )

    root = daemon_wiki.daemon_wiki_root(tmp_path, daemon["daemon_id"])
    digest = root / "pages" / "signals" / "learning-signals.md"

    assert "node | failed | branch-task-1" in digest.read_text(encoding="utf-8")
    assert list((root / "raw" / "signals").glob("*branch-task-1-failed.md"))
