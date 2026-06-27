"""Executable proof for daemon memory quality replay evaluation."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tinyassets.daemon_brain import (  # noqa: E402
    capture_daemon_memory,
    evaluate_daemon_memory_quality,
    memory_observability_status,
)
from tinyassets.daemon_registry import create_daemon  # noqa: E402


def _create_daemon(base: Path) -> dict:
    return create_daemon(
        base,
        display_name="Proof Memory Eval",
        created_by="proof",
        soul_mode="soul",
        soul_text="Proof Memory Eval keeps useful memories and rejects noisy ones.",
    )


def main() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = Path(tmp)
        daemon = _create_daemon(base)
        entry = capture_daemon_memory(
            base,
            daemon_id=daemon["daemon_id"],
            memory_kind="failure_mode",
            content=(
                "When child runs fail, verify provider_call reaches child "
                "prompt nodes."
            ),
            source_type="proof",
            source_id="daemon-memory-quality-eval",
            reliability="proof_observed",
            temporal_bounds={"valid_from": "2026-05-02"},
            language_type="policy",
            confidence=0.9,
            importance=0.9,
        )

        def replay(case: dict) -> str:
            if "provider_call reaches child prompt nodes" in case["context"]:
                return "Fix checks provider_call reaches child prompt nodes."
            return "Fix checks provider routing generally."

        result = evaluate_daemon_memory_quality(
            base,
            daemon_id=daemon["daemon_id"],
            query="child run provider_call",
            replay_fn=replay,
            expected_signals=["provider_call reaches child prompt nodes"],
        )
        assert result["entry_ids"] == [entry["entry_id"]], result
        assert result["outcome"] == "improved", result
        assert result["delta"] > 0.0, result

        status = memory_observability_status(base, daemon_id=daemon["daemon_id"])
        assert status["event_types"]["daemon.memory.eval"] == 1, status

    print("daemon_memory_quality_eval: ok")


if __name__ == "__main__":
    main()
