"""Tests for ``add_canon`` + ``add_canon_from_path`` MCP actions.

Covers two defect fixes landed together:

1. ``add_canon`` previously wrote directly to ``canon/<filename>`` and
   did NOT emit the ``synthesize_source`` signal — premise/canon/entity
   synthesis never fired on MCP uploads. Now routes through
   :func:`workflow.ingestion.core.ingest_file` so the signal fires.

2. ``add_canon_from_path`` is a new action for large uploads. The MCP
   client passes an **absolute server-side path**; the server reads
   the file itself so the LLM never has to copy content through the
   tool-call arg (breaks at >20K tokens: summarization drift, output
   cutoff, JSON-escape errors).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import workflow.api.engine_helpers as eh
import workflow.api.universe as us


def _call(action: str, **kwargs) -> dict:
    """Invoke an action through the dispatch+ledger path the tool uses."""
    base_kwargs = {
        "universe_id": "",
        "text": "",
        "path": "",
        "category": "direction",
        "target": "",
        "query_type": "facts",
        "filter_text": "",
        "request_type": "scene_direction",
        "branch_id": "",
        "filename": "",
        "provenance_tag": "",
        "limit": 20,
    }
    base_kwargs.update(kwargs)

    dispatch = {
        "add_canon": us._action_add_canon,
        "add_canon_from_path": us._action_add_canon_from_path,
    }
    handler = dispatch[action]
    return json.loads(us._dispatch_with_ledger(action, handler, base_kwargs))


@pytest.fixture
def universe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    base = tmp_path / "output"
    uid = "test-uni"
    (base / uid).mkdir(parents=True)
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", uid)
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "test-user")
    return uid


def _signals(uid: str) -> list[dict]:
    path = us._base_path() / uid / "worldbuild_signals.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


# ─── add_canon now emits synthesize_source ─────────────────────────────


class TestAddCanonSynthesisSignal:
    def test_add_canon_response_makes_version_semantics_explicit(
        self, universe: str,
    ) -> None:
        out = _call("add_canon", filename="ryn.md", text="# Ryn\n\nA scout.")

        assert out["source_operation"] == "created"
        assert out["version_semantics"] == {
            "mode": "filename_upsert",
            "identity": "canon/sources/ryn.md",
            "same_filename_behavior": (
                "A later add_canon call with the same filename replaces the "
                "stored source bytes and manifest entry when the content hash "
                "changes; identical bytes are treated as unchanged."
            ),
            "history_retained": False,
            "supersede_supported": False,
            "deprecate_supported": False,
        }

    def test_add_canon_emits_signal(self, universe: str) -> None:
        """The pre-fix path bypassed ingest_file and no signal ever
        fired. Post-fix: every user upload emits synthesize_source."""
        out = _call(
            "add_canon", filename="ryn.md", text="# Ryn\n\nA scout.",
            provenance_tag="rough notes",
        )
        assert out["status"] == "written"
        assert out["synthesis_signal_emitted"] is True

        signals = _signals(universe)
        assert len(signals) == 1
        assert signals[0]["type"] == "synthesize_source"
        assert signals[0]["source_file"] == "ryn.md"

    def test_add_canon_routes_to_sources_dir(self, universe: str) -> None:
        """User uploads land under ``canon/sources/`` per ingest_file
        routing, not ``canon/`` directly."""
        _call("add_canon", filename="notes.md", text="notes")
        udir = us._base_path() / universe
        assert (udir / "canon" / "sources" / "notes.md").exists()
        # The direct-to-canon path is no longer used for uploads.
        assert not (udir / "canon" / "notes.md").exists()

    def test_add_canon_ledger_entry_unchanged(self, universe: str) -> None:
        """Ledger contract from the 2a landing preserved."""
        _call(
            "add_canon", filename="ref.md", text="# Reference\n",
            provenance_tag="rough notes",
        )
        ledger_path = us._base_path() / universe / "ledger.json"
        entries = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert len(entries) == 1
        assert entries[0]["action"] == "add_canon"
        assert entries[0]["target"] == "canon/ref.md"
        assert entries[0]["payload"]["provenance"] == "rough notes"

    def test_add_canon_reports_replace_and_unchanged(
        self, universe: str,
    ) -> None:
        first = _call("add_canon", filename="notes.md", text="Old notes")
        second = _call("add_canon", filename="notes.md", text="New notes")
        third = _call("add_canon", filename="notes.md", text="New notes")

        assert first["source_operation"] == "created"
        assert second["source_operation"] == "replaced"
        assert third["source_operation"] == "unchanged"


# ─── add_canon_from_path happy path ────────────────────────────────────


class TestAddCanonFromPathHappyPath:
    def test_large_file_ingests_with_signal(
        self, universe: str, tmp_path: Path,
    ) -> None:
        """A 130KB markdown file — well past the LLM tool-arg reliable
        limit — ingests cleanly and emits synthesize_source."""
        src = tmp_path / "big-lore.md"
        # 130 KB of repeated markdown. Content doesn't matter; size does.
        body = (
            "# Silent Valley Lore\n\n"
            "The river clans have traded along the Ashwater for centuries. "
            * 2000  # ~130 KB
        )
        src.write_text(body, encoding="utf-8")
        size = src.stat().st_size
        assert size > 100 * 1024

        out = _call(
            "add_canon_from_path", path=str(src),
            provenance_tag="published novel",
        )
        assert "error" not in out
        assert out["filename"] == "big-lore.md"
        assert out["bytes_written"] == size
        assert out["synthesis_signal_emitted"] is True
        assert out["routed_to"] == "sources"
        assert out["provenance"] == "published novel"
        assert out["source_operation"] == "created"
        assert out["version_semantics"]["mode"] == "filename_upsert"
        assert out["version_semantics"]["identity"] == "canon/sources/big-lore.md"

        signals = _signals(universe)
        assert len(signals) == 1
        assert signals[0]["source_file"] == "big-lore.md"

        # File landed on disk verbatim.
        udir = us._base_path() / universe
        dest = udir / "canon" / "sources" / "big-lore.md"
        assert dest.exists()
        assert dest.stat().st_size == size

    def test_filename_override(
        self, universe: str, tmp_path: Path,
    ) -> None:
        src = tmp_path / "ugly-original-name.txt"
        src.write_text("clean contents", encoding="utf-8")
        out = _call(
            "add_canon_from_path", path=str(src), filename="clean.md",
        )
        assert out["filename"] == "clean.md"
        udir = us._base_path() / universe
        assert (udir / "canon" / "sources" / "clean.md").exists()

    def test_default_provenance_is_user_upload(
        self, universe: str, tmp_path: Path,
    ) -> None:
        src = tmp_path / "notes.md"
        src.write_text("some notes", encoding="utf-8")
        out = _call("add_canon_from_path", path=str(src))
        assert out["provenance"] == "user_upload"

    def test_meta_file_written(
        self, universe: str, tmp_path: Path,
    ) -> None:
        """Sidecar .meta.json records source_path for traceability."""
        src = tmp_path / "lore.md"
        src.write_text("lore", encoding="utf-8")
        _call("add_canon_from_path", path=str(src), provenance_tag="novel")

        udir = us._base_path() / universe
        meta_path = udir / "canon" / ".lore.md.meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["provenance"] == "novel"
        assert meta["source_path"] == str(src)

    def test_ledger_entry_appended(
        self, universe: str, tmp_path: Path,
    ) -> None:
        src = tmp_path / "ingest.md"
        src.write_text("content", encoding="utf-8")
        _call("add_canon_from_path", path=str(src), provenance_tag="draft")

        ledger_path = us._base_path() / universe / "ledger.json"
        entries = json.loads(ledger_path.read_text(encoding="utf-8"))
        assert len(entries) == 1
        assert entries[0]["action"] == "add_canon_from_path"
        assert entries[0]["target"] == "canon/sources/ingest.md"
        assert entries[0]["payload"]["provenance"] == "draft"
        assert entries[0]["payload"]["source_path"] == str(src)
        assert entries[0]["payload"]["synthesis_signal"] is True


# ─── add_canon_from_path rejects bad input ─────────────────────────────


class TestAddCanonFromPathRejections:
    def test_missing_path_rejected(self, universe: str) -> None:
        out = _call("add_canon_from_path", path="")
        assert "error" in out
        assert "path is required" in out["error"].lower()

    def test_relative_path_rejected(
        self, universe: str, tmp_path: Path,
    ) -> None:
        out = _call("add_canon_from_path", path="notes.md")
        assert "error" in out
        assert "absolute" in out["error"].lower()

    def test_nonexistent_path_rejected(
        self, universe: str, tmp_path: Path,
    ) -> None:
        ghost = tmp_path / "does-not-exist.md"
        out = _call("add_canon_from_path", path=str(ghost))
        assert "error" in out
        assert "not found" in out["error"].lower()

    def test_directory_path_rejected(
        self, universe: str, tmp_path: Path,
    ) -> None:
        """A directory is not a regular file."""
        out = _call("add_canon_from_path", path=str(tmp_path))
        assert "error" in out
        assert "regular file" in out["error"].lower()

    def test_non_utf8_file_rejected(
        self, universe: str, tmp_path: Path,
    ) -> None:
        """Latin-1 / binary content is rejected with a clear error —
        silent corruption of the canon pipeline would be much worse."""
        src = tmp_path / "latin1.md"
        # Valid latin-1 bytes that break UTF-8 decode (e.g. 0xFF).
        src.write_bytes(b"\xff\xfe\xfd not utf-8")
        out = _call("add_canon_from_path", path=str(src))
        assert "error" in out
        assert "utf-8" in out["error"].lower()
        # And the failed upload left no side effects.
        udir = us._base_path() / universe
        assert not (udir / "canon" / "sources" / "latin1.md").exists()
        assert _signals(universe) == []

    def test_rejection_leaves_no_ledger_entry(
        self, universe: str, tmp_path: Path,
    ) -> None:
        _call("add_canon_from_path", path=str(tmp_path / "missing"))
        ledger_path = us._base_path() / universe / "ledger.json"
        assert not ledger_path.exists()


# ─── Trust-model mitigations (task #15) ─────────────────────────────────


class TestAddCanonFromPathWhitelist:
    """``WORKFLOW_UPLOAD_WHITELIST`` opt-in enforcement."""

    def test_whitelist_unset_accepts_any_absolute(
        self, universe: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Default/demo behavior preserved: unset whitelist → accept."""
        monkeypatch.delenv("WORKFLOW_UPLOAD_WHITELIST", raising=False)
        src = tmp_path / "open.md"
        src.write_text("open content", encoding="utf-8")
        out = _call("add_canon_from_path", path=str(src))
        assert "error" not in out
        assert out["filename"] == "open.md"

    def test_whitelist_set_accepts_path_under_prefix(
        self, universe: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("WORKFLOW_UPLOAD_WHITELIST", str(tmp_path))
        src = tmp_path / "inside.md"
        src.write_text("inside content", encoding="utf-8")
        out = _call("add_canon_from_path", path=str(src))
        assert "error" not in out
        assert out["filename"] == "inside.md"

    def test_whitelist_set_rejects_path_outside_prefix(
        self, universe: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A sibling directory outside the whitelist is rejected."""
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        forbidden = tmp_path / "forbidden"
        forbidden.mkdir()
        bad_file = forbidden / "secret.md"
        bad_file.write_text("secret", encoding="utf-8")

        monkeypatch.setenv("WORKFLOW_UPLOAD_WHITELIST", str(allowed))
        out = _call("add_canon_from_path", path=str(bad_file))
        assert "error" in out
        assert "whitelist" in out["error"].lower()
        # And no ledger entry was appended.
        assert not (us._base_path() / universe / "ledger.json").exists()

    def test_whitelist_traversal_attempt_rejected(
        self, universe: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``resolve()`` collapses ``..`` before the prefix check so
        ``/allowed/../forbidden/x`` cannot slip past."""
        allowed = tmp_path / "allowed"
        allowed.mkdir()
        forbidden = tmp_path / "forbidden"
        forbidden.mkdir()
        bad_file = forbidden / "secret.md"
        bad_file.write_text("secret", encoding="utf-8")

        monkeypatch.setenv("WORKFLOW_UPLOAD_WHITELIST", str(allowed))
        traversal = allowed / ".." / "forbidden" / "secret.md"
        out = _call("add_canon_from_path", path=str(traversal))
        assert "error" in out
        assert "whitelist" in out["error"].lower()

    def test_whitelist_multiple_prefixes(
        self, universe: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Semicolon-separated list of prefixes; a file under any
        listed prefix passes."""
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        file_a = dir_a / "one.md"
        file_b = dir_b / "two.md"
        file_a.write_text("a", encoding="utf-8")
        file_b.write_text("b", encoding="utf-8")

        monkeypatch.setenv(
            "WORKFLOW_UPLOAD_WHITELIST", f"{dir_a};{dir_b}",
        )
        assert "error" not in _call("add_canon_from_path", path=str(file_a))
        assert "error" not in _call("add_canon_from_path", path=str(file_b))

    def test_whitelist_prefix_helper_parses_windows_drive(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Drive-letter colons on Windows must not get mis-split."""
        monkeypatch.setenv(
            "WORKFLOW_UPLOAD_WHITELIST",
            r"C:\Users\Jonathan\Desktop;D:\data",
        )
        prefixes = eh._upload_whitelist_prefixes()
        assert prefixes is not None
        # Whatever resolve produces, both drive-rooted paths must survive
        # as a single prefix each — not split at the drive colon.
        as_strs = [str(p) for p in prefixes]
        assert any("Desktop" in s for s in as_strs)
        assert any("data" in s for s in as_strs)
        # And we did NOT wind up with bare drive-letter prefixes.
        assert all(len(s) > 3 for s in as_strs)

    def test_whitelist_unset_helper_returns_none(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("WORKFLOW_UPLOAD_WHITELIST", raising=False)
        assert eh._upload_whitelist_prefixes() is None

    def test_whitelist_empty_string_is_none(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("WORKFLOW_UPLOAD_WHITELIST", "")
        assert eh._upload_whitelist_prefixes() is None


class TestAddCanonFromPathPreview:
    """Response echoes first 200 decoded chars so silent file-swap is detectable."""

    def test_preview_returns_first_200_chars(
        self, universe: str, tmp_path: Path,
    ) -> None:
        body = "A" * 500
        src = tmp_path / "long.md"
        src.write_text(body, encoding="utf-8")
        out = _call("add_canon_from_path", path=str(src))
        assert out["preview_first_200_bytes"] == "A" * 200

    def test_preview_shorter_than_200_for_short_file(
        self, universe: str, tmp_path: Path,
    ) -> None:
        body = "short file"
        src = tmp_path / "short.md"
        src.write_text(body, encoding="utf-8")
        out = _call("add_canon_from_path", path=str(src))
        assert out["preview_first_200_bytes"] == body

    def test_preview_empty_for_empty_file(
        self, universe: str, tmp_path: Path,
    ) -> None:
        src = tmp_path / "empty.md"
        src.write_text("", encoding="utf-8")
        out = _call("add_canon_from_path", path=str(src))
        assert out["preview_first_200_bytes"] == ""
        # Empty file still ingested cleanly (0 bytes written).
        assert "error" not in out

    def test_preview_uses_decoded_chars_not_bytes(
        self, universe: str, tmp_path: Path,
    ) -> None:
        """Multibyte UTF-8 chars count as 1 each in the preview, not per
        byte — the param name says ``bytes`` for MCP consistency but
        semantically it's 200 decoded chars."""
        # 200 emoji would be 800 bytes but 200 chars.
        body = "é" * 250  # 250 chars, 500 bytes
        src = tmp_path / "utf8.md"
        src.write_text(body, encoding="utf-8")
        out = _call("add_canon_from_path", path=str(src))
        assert out["preview_first_200_bytes"] == "é" * 200
        # Byte count reflects the disk size, not the char count.
        assert out["bytes_written"] == 500
