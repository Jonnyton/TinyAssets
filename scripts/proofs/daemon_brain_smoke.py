"""Executable smoke proof for the daemon mini-brain runtime slice.

Focused pytest coverage now lives in ``tests/test_daemon_brain.py``. Keep this
script as a direct CLI proof for operators who want a no-pytest smoke check.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tinyassets.daemon_brain import (  # noqa: E402
    build_daemon_brain_packet,
    capture_daemon_memory,
    list_daemon_memory,
    memory_observability_status,
    promote_daemon_memory_to_wiki,
    search_daemon_memory,
)
from tinyassets.daemon_memory import build_daemon_memory_packet  # noqa: E402
from tinyassets.daemon_registry import create_daemon  # noqa: E402
from tinyassets.daemon_wiki import daemon_wiki_root, scaffold_daemon_wiki  # noqa: E402


def _create_daemon(base: Path, name: str) -> dict:
    return create_daemon(
        base,
        display_name=name,
        created_by="proof",
        soul_mode="soul",
        soul_text=f"{name} is a careful proof daemon.",
        metadata={"daemon_wiki": {"cap_policy": "custom", "cap_bytes": 20000}},
    )


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = Path(tmp)
        ada = _create_daemon(base, "Proof Ada")
        mira = _create_daemon(base, "Proof Mira")

        scaffold_daemon_wiki(base, daemon=ada, soul_text="Proof Ada soul.")
        review_page = daemon_wiki_root(base, ada["daemon_id"]) / "pages" / "brain" / "review.md"
        assert review_page.exists(), "scaffold should create the brain review page"
        original_review = review_page.read_text(encoding="utf-8")

        first = capture_daemon_memory(
            base,
            daemon_id=ada["daemon_id"],
            memory_kind="failure_mode",
            content="When checking daemon routing, verify the executor identity is not copied.",
            source_type="manual",
            source_id="proof-source",
            reliability="host_observed",
            temporal_bounds={"valid_from": "2026-05-02"},
            language_type="policy",
            confidence=0.91,
            importance=0.86,
        )
        duplicate = capture_daemon_memory(
            base,
            daemon_id=ada["daemon_id"],
            memory_kind="failure_mode",
            content="When checking daemon routing, verify the executor identity is not copied.",
            source_type="manual",
            source_id="proof-source",
            reliability="host_observed",
            temporal_bounds={"valid_from": "2026-05-02"},
            language_type="policy",
        )
        assert first["entry_id"] == duplicate["entry_id"], (
            "duplicate content should dedupe per daemon"
        )
        assert duplicate["deduped"] is True

        capture_daemon_memory(
            base,
            daemon_id=mira["daemon_id"],
            memory_kind="policy",
            content="Mira-only packet planning memory must not leak into Ada search.",
            source_type="manual",
            source_id="proof-source",
            reliability="host_observed",
            temporal_bounds={"valid_from": "2026-05-02"},
            language_type="policy",
        )

        listed = list_daemon_memory(base, daemon_id=ada["daemon_id"])
        assert listed["count"] == 1, listed

        search = search_daemon_memory(
            base,
            daemon_id=ada["daemon_id"],
            query="executor identity copied",
            limit=5,
        )
        assert [entry["entry_id"] for entry in search["entries"]] == [first["entry_id"]]
        assert all("Mira-only" not in entry["content"] for entry in search["entries"])

        brain_packet = build_daemon_brain_packet(
            base,
            daemon_id=ada["daemon_id"],
            query="daemon routing executor identity",
            max_chars=700,
        )
        assert first["entry_id"] in brain_packet["context"]
        assert len(brain_packet["context"]) <= 700

        full_packet = build_daemon_memory_packet(
            base,
            daemon_id=ada["daemon_id"],
            max_chars=2600,
            brain_query="daemon routing executor identity",
            brain_max_chars=700,
        )
        assert first["entry_id"] in full_packet["context"]
        assert len(full_packet["context"]) <= 2600
        assert full_packet["brain"]["selected_count"] == 1

        promotion = promote_daemon_memory_to_wiki(
            base,
            daemon_id=ada["daemon_id"],
            entry_ids=[first["entry_id"]],
            summary="Routing memories must preserve executor identity boundaries.",
        )
        assert promotion["promoted_count"] == 1
        promoted_review = review_page.read_text(encoding="utf-8")
        assert promoted_review.startswith(original_review)
        assert first["entry_id"] in promoted_review

        status = memory_observability_status(base, daemon_id=ada["daemon_id"])
        assert status["entry_count"] == 1
        assert status["event_count"] >= 5

    print("daemon_brain_smoke: ok")


if __name__ == "__main__":
    main()
