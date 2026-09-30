"""The daemon wiki is never capped and never evicted.

Founder, 2026-09-30: an account has exactly two limits -- the cloud bytes a
universe occupies, and how many agent runs it may have at once. A daemon wiki's
bytes ARE those bytes, accounted once by the tier storage gate.

What this replaces: an age-scaled per-wiki byte cap (16 MiB in the first month,
plateauing at 64 MiB for a user daemon and 128 MiB for a project one) and
``compact_daemon_wiki``, which DELETED the daemon's own raw signal files to get
back under it. The prompt bound (``max_chars``) stays -- trimming what a model is
SENT is a different decision from deleting a record.
"""

from __future__ import annotations

import pytest

from tinyassets import daemon_memory


def test_the_cap_policy_and_the_compactor_are_gone():
    for gone in (
        "daemon_memory_policy",
        "compact_daemon_wiki",
        "VALID_CAP_POLICIES",
        "DEFAULT_FIRST_MONTH_CAP_BYTES",
        "DEFAULT_USER_PLATEAU_BYTES",
        "DEFAULT_PROJECT_PLATEAU_BYTES",
        "_signal_candidates",
        "_trim_sectioned_page",
        "_append_compaction_summary",
        "_is_protected",
    ):
        assert not hasattr(daemon_memory, gone), f"{gone} came back"

    # The PROMPT bound stays: it shapes one model call and deletes nothing.
    assert daemon_memory.DEFAULT_MEMORY_PACKET_CHARS == 8000
    assert daemon_memory.DEFAULT_BRAIN_PACKET_CHARS == 1600


def test_wiki_status_observes_bytes_and_names_no_limit(tmp_path):
    """An observation has no cap, no ratio, no pressure and no compaction flag."""
    root = tmp_path / "wiki"
    (root / "raw" / "signals").mkdir(parents=True)
    (root / "WIKI.md").write_text("x" * 100, encoding="utf-8")
    (root / "raw" / "signals" / "s1.md").write_text("y" * 250, encoding="utf-8")

    import tinyassets.daemon_wiki as dw

    original = dw.daemon_wiki_root
    dw.daemon_wiki_root = lambda _base, _did: root
    try:
        observed = daemon_memory.daemon_wiki_status(tmp_path, daemon_id="d-1")
    finally:
        dw.daemon_wiki_root = original

    assert observed["total_bytes"] == 350
    assert observed["file_count"] == 2
    assert observed["exists"] is True
    for gone in (
        "cap_bytes",
        "cap_policy",
        "usage_ratio",
        "pressure_level",
        "needs_compaction",
        "evictable_signal_bytes",
        "policy",
    ):
        assert gone not in observed, f"{gone} is a limit field, not an observation"


def test_building_a_packet_deletes_no_wiki_file(tmp_path, monkeypatch):
    """The real packet builder, over bytes far past the old 16 MiB first-month cap.

    Every signal file must still be on disk afterwards. Under the old code the
    ``enforce_cap=True`` default ran the compactor on every build and unlinked
    them.
    """
    from tinyassets.daemon_registry import create_daemon
    from tinyassets.daemon_wiki import daemon_wiki_root

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    daemon = create_daemon(
        tmp_path,
        display_name="Ada",
        created_by="pytest",
        soul_mode="soul",
        soul_text="I keep what I learn.",
    )
    did = daemon["daemon_id"]

    # Scaffold + 40 signal files of 512 KiB each => ~20 MiB, over the old cap.
    daemon_memory.build_daemon_memory_packet(tmp_path, daemon_id=did, include_brain=False)
    signals = daemon_wiki_root(tmp_path, did) / "raw" / "signals"
    signals.mkdir(parents=True, exist_ok=True)
    for i in range(40):
        (signals / f"s{i:03d}.md").write_text("z" * (512 * 1024), encoding="utf-8")
    names = sorted(path.name for path in signals.glob("*.md"))
    assert len(names) == 40

    packet = daemon_memory.build_daemon_memory_packet(
        tmp_path, daemon_id=did, max_chars=2000, include_brain=False
    )

    assert sorted(path.name for path in signals.glob("*.md")) == names, (
        "a packet build deleted the daemon's own signal records"
    )
    assert packet["memory_status"]["total_bytes"] > 16 * 1024 * 1024
    assert "compaction" not in packet
    # The PROMPT is still bounded, which is the part that was always correct.
    assert len(packet["context"]) <= 2000


def test_enforce_cap_is_not_a_parameter_any_more():
    import inspect

    params = inspect.signature(daemon_memory.build_daemon_memory_packet).parameters
    assert "enforce_cap" not in params
    with pytest.raises(TypeError):
        daemon_memory.build_daemon_memory_packet("x", daemon_id="d", enforce_cap=True)
