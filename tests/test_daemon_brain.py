"""Focused pytest coverage for the daemon mini-brain runtime slice."""

from __future__ import annotations

from pathlib import Path

from workflow.daemon_brain import (
    build_daemon_brain_packet,
    capture_daemon_memory,
    list_daemon_memory,
    memory_observability_status,
    promote_daemon_memory_to_wiki,
    search_daemon_memory,
)
from workflow.daemon_memory import build_daemon_memory_packet
from workflow.daemon_registry import create_daemon
from workflow.daemon_wiki import daemon_wiki_root, scaffold_daemon_wiki


def _create_daemon(base: Path, name: str) -> dict:
    return create_daemon(
        base,
        display_name=name,
        created_by="pytest",
        soul_mode="soul",
        soul_text=f"{name} is a careful test daemon.",
        metadata={"daemon_wiki": {"cap_policy": "custom", "cap_bytes": 20000}},
    )


def test_daemon_brain_smoke_roundtrip(tmp_path: Path) -> None:
    ada = _create_daemon(tmp_path, "Test Ada")
    mira = _create_daemon(tmp_path, "Test Mira")

    scaffold_daemon_wiki(tmp_path, daemon=ada, soul_text="Test Ada soul.")
    review_page = (
        daemon_wiki_root(tmp_path, ada["daemon_id"])
        / "pages"
        / "brain"
        / "review.md"
    )
    assert review_page.exists()
    original_review = review_page.read_text(encoding="utf-8")

    first = capture_daemon_memory(
        tmp_path,
        daemon_id=ada["daemon_id"],
        memory_kind="failure_mode",
        content=(
            "When checking daemon routing, verify the executor identity is "
            "not copied."
        ),
        source_type="manual",
        source_id="pytest-source",
        reliability="host_observed",
        temporal_bounds={"valid_from": "2026-05-02"},
        language_type="policy",
        confidence=0.91,
        importance=0.86,
    )
    duplicate = capture_daemon_memory(
        tmp_path,
        daemon_id=ada["daemon_id"],
        memory_kind="failure_mode",
        content=(
            "When checking daemon routing, verify the executor identity is "
            "not copied."
        ),
        source_type="manual",
        source_id="pytest-source",
        reliability="host_observed",
        temporal_bounds={"valid_from": "2026-05-02"},
        language_type="policy",
    )
    assert duplicate["deduped"] is True
    assert duplicate["entry_id"] == first["entry_id"]

    capture_daemon_memory(
        tmp_path,
        daemon_id=mira["daemon_id"],
        memory_kind="policy",
        content="Mira-only packet planning memory must not leak into Ada search.",
        source_type="manual",
        source_id="pytest-source",
        reliability="host_observed",
        temporal_bounds={"valid_from": "2026-05-02"},
        language_type="policy",
    )

    listed = list_daemon_memory(tmp_path, daemon_id=ada["daemon_id"])
    assert listed["count"] == 1

    search = search_daemon_memory(
        tmp_path,
        daemon_id=ada["daemon_id"],
        query="executor identity copied",
        limit=5,
    )
    assert [entry["entry_id"] for entry in search["entries"]] == [
        first["entry_id"],
    ]
    assert all("Mira-only" not in entry["content"] for entry in search["entries"])

    brain_packet = build_daemon_brain_packet(
        tmp_path,
        daemon_id=ada["daemon_id"],
        query="daemon routing executor identity",
        max_chars=700,
    )
    assert first["entry_id"] in brain_packet["context"]
    assert len(brain_packet["context"]) <= 700

    full_packet = build_daemon_memory_packet(
        tmp_path,
        daemon_id=ada["daemon_id"],
        max_chars=2600,
        brain_query="daemon routing executor identity",
        brain_max_chars=700,
    )
    assert first["entry_id"] in full_packet["context"]
    assert len(full_packet["context"]) <= 2600
    assert full_packet["brain"]["selected_count"] == 1

    promotion = promote_daemon_memory_to_wiki(
        tmp_path,
        daemon_id=ada["daemon_id"],
        entry_ids=[first["entry_id"]],
        summary="Routing memories must preserve executor identity boundaries.",
    )
    assert promotion["promoted_count"] == 1
    promoted_review = review_page.read_text(encoding="utf-8")
    assert promoted_review.startswith(original_review)
    assert first["entry_id"] in promoted_review

    status = memory_observability_status(tmp_path, daemon_id=ada["daemon_id"])
    assert status["entry_count"] == 1
    assert status["event_count"] >= 5
