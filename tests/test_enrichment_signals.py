from __future__ import annotations

import json

import pytest

from workflow.enrichment_signals import (
    ENRICHMENT_SIGNALS_FILENAME,
    LEGACY_WORLDBUILD_SIGNALS_FILENAME,
    append_enrichment_signals,
    load_enrichment_signals,
)


def test_neutral_empty_signal_file_does_not_fall_back_to_legacy(tmp_path) -> None:
    (tmp_path / LEGACY_WORLDBUILD_SIGNALS_FILENAME).write_text(
        json.dumps([{"type": "synthesize_source", "source_file": "old.md"}]),
        encoding="utf-8",
    )
    (tmp_path / ENRICHMENT_SIGNALS_FILENAME).write_text("[]\n", encoding="utf-8")

    assert load_enrichment_signals(tmp_path) == []


def test_missing_canonical_falls_back_to_legacy(tmp_path) -> None:
    # The ONLY legitimate fallback path: canonical genuinely absent.
    (tmp_path / LEGACY_WORLDBUILD_SIGNALS_FILENAME).write_text(
        json.dumps([{"type": "synthesize_source", "source_file": "old.md"}]),
        encoding="utf-8",
    )

    signals = load_enrichment_signals(tmp_path)
    assert [s["source_file"] for s in signals] == ["old.md"]


def test_present_but_malformed_canonical_file_strict_fails_loud(tmp_path) -> None:
    # Hard Rule #8: write-back callers read strict, so a PRESENT canonical file
    # that cannot be parsed RAISES rather than silently becoming [] (which would
    # overwrite the queue and drop pending work). This is the bug Tier D fixes.
    (tmp_path / ENRICHMENT_SIGNALS_FILENAME).write_text(
        "{not valid json", encoding="utf-8",
    )
    with pytest.raises(RuntimeError):
        load_enrichment_signals(tmp_path, strict=True)


def test_present_but_non_list_canonical_file_strict_fails_loud(tmp_path) -> None:
    # Valid JSON but the wrong shape is still corruption, not an empty queue.
    (tmp_path / ENRICHMENT_SIGNALS_FILENAME).write_text(
        json.dumps({"not": "a list"}), encoding="utf-8",
    )
    with pytest.raises(RuntimeError):
        load_enrichment_signals(tmp_path, strict=True)


def test_corrupt_canonical_file_read_only_degrades_loudly(tmp_path, caplog) -> None:
    # The default (non-strict) read is for read-only consumers (routing, counts,
    # scans): it must not crash the daemon over a regenerable scratch file, but
    # it must log loudly — degraded, never silent — and leave the file untouched.
    corrupt = tmp_path / ENRICHMENT_SIGNALS_FILENAME
    corrupt.write_text("{not valid json", encoding="utf-8")
    with caplog.at_level("ERROR"):
        assert load_enrichment_signals(tmp_path) == []
    assert any("unreadable/malformed" in r.getMessage() for r in caplog.records)
    assert corrupt.read_text(encoding="utf-8") == "{not valid json"


def test_append_does_not_overwrite_corrupt_file(tmp_path) -> None:
    # The concrete data-loss path Codex flagged: append reads-modifies-writes.
    # On a corrupt existing file it must raise and leave the file intact rather
    # than clobbering it with just the new signals.
    corrupt = tmp_path / ENRICHMENT_SIGNALS_FILENAME
    corrupt.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(RuntimeError):
        append_enrichment_signals(tmp_path, [{"type": "synthesize_source"}])
    assert corrupt.read_text(encoding="utf-8") == "{not valid json"
