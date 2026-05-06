"""Tests that universe action responses include `universe_id` for isolation.

Context: Task #15. Claude.ai cross-universe hallucination was enabled by
tool responses that didn't name the universe they came from. When the bot
reads premise, canon, world-state, activity, etc., the response shape now
leads with `universe_id` so downstream reasoning can ground each fact to
its source universe.

Pairs with #47 (on-disk quarantine), #48 (retrieval audit), #51/#49/#53
(live-code hardening). This is the chat-side half of the cross-universe
cluster.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import workflow.api.universe as us


@pytest.fixture
def universe_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(base))
    return base


def _make_universe(base: Path, uid: str) -> Path:
    udir = base / uid
    udir.mkdir(parents=True)
    return udir


class TestUniverseIdInResponses:
    """Every read response that pulls universe-scoped content must name it."""

    def test_read_premise_includes_universe_id(self, universe_base):
        udir = _make_universe(universe_base, "alpha")
        (udir / "PROGRAM.md").write_text("An alpha premise.", encoding="utf-8")
        out = json.loads(us._action_read_premise(universe_id="alpha"))
        assert out["universe_id"] == "alpha"
        assert out["premise"] == "An alpha premise."

    def test_read_premise_missing_still_includes_universe_id(self, universe_base):
        _make_universe(universe_base, "alpha")
        out = json.loads(us._action_read_premise(universe_id="alpha"))
        assert out["universe_id"] == "alpha"
        assert out["premise"] is None

    def test_read_output_includes_universe_id(self, universe_base):
        udir = _make_universe(universe_base, "alpha")
        (udir / "output").mkdir()
        (udir / "output" / "note.md").write_text("hello", encoding="utf-8")
        out = json.loads(us._action_read_output(universe_id="alpha", path="note.md"))
        assert out["universe_id"] == "alpha"
        assert out["content"] == "hello"

    def test_render_artifact_includes_universe_id(self, universe_base):
        udir = _make_universe(universe_base, "alpha")
        (udir / "PROGRAM.md").write_text("Alpha premise.", encoding="utf-8")
        out = json.loads(us._action_render_artifact(
            universe_id="alpha",
            artifact_format="markdown",
            filename="alpha-share.md",
        ))
        assert out["universe_id"] == "alpha"
        assert out["format"] == "markdown"
        assert out["path"] == "exports/alpha-share.md"

    def test_list_canon_includes_universe_id(self, universe_base):
        udir = _make_universe(universe_base, "alpha")
        (udir / "canon").mkdir()
        (udir / "canon" / "a.md").write_text("x", encoding="utf-8")
        out = json.loads(us._action_list_canon(universe_id="alpha"))
        assert out["universe_id"] == "alpha"

    def test_list_canon_no_canon_dir_still_includes_universe_id(self, universe_base):
        _make_universe(universe_base, "alpha")
        out = json.loads(us._action_list_canon(universe_id="alpha"))
        assert out["universe_id"] == "alpha"

    def test_read_canon_includes_universe_id(self, universe_base):
        udir = _make_universe(universe_base, "alpha")
        (udir / "canon").mkdir()
        (udir / "canon" / "a.md").write_text("hello", encoding="utf-8")
        out = json.loads(us._action_read_canon(universe_id="alpha", filename="a.md"))
        assert out["universe_id"] == "alpha"
        assert out["filename"] == "a.md"

    def test_query_world_no_data_includes_universe_id(self, universe_base):
        _make_universe(universe_base, "alpha")
        out = json.loads(us._action_query_world(universe_id="alpha", query_type="timeline"))
        # timeline has no store; should still echo the universe
        assert out["universe_id"] == "alpha"

    def test_get_activity_includes_universe_id(self, universe_base):
        udir = _make_universe(universe_base, "alpha")
        (udir / "activity.log").write_text("[..] line\n", encoding="utf-8")
        out = json.loads(us._action_get_activity(universe_id="alpha", limit=5))
        assert out["universe_id"] == "alpha"

    def test_get_activity_missing_log_includes_universe_id(self, universe_base):
        _make_universe(universe_base, "alpha")
        out = json.loads(us._action_get_activity(universe_id="alpha"))
        assert out["universe_id"] == "alpha"

    def test_get_ledger_empty_includes_universe_id(self, universe_base):
        _make_universe(universe_base, "alpha")
        out = json.loads(us._action_get_ledger(universe_id="alpha"))
        assert out["universe_id"] == "alpha"

    def test_control_daemon_status_includes_universe_id(self, universe_base):
        _make_universe(universe_base, "alpha")
        out = json.loads(us._action_control_daemon(universe_id="alpha", text="status"))
        assert out["universe_id"] == "alpha"

    def test_different_universes_stay_distinct(self, universe_base):
        """Two universes must never cross-contaminate through the response."""
        udir_a = _make_universe(universe_base, "alpha")
        udir_b = _make_universe(universe_base, "beta")
        (udir_a / "PROGRAM.md").write_text("Alpha premise.", encoding="utf-8")
        (udir_b / "PROGRAM.md").write_text("Beta premise.", encoding="utf-8")

        out_a = json.loads(us._action_read_premise(universe_id="alpha"))
        out_b = json.loads(us._action_read_premise(universe_id="beta"))

        assert out_a["universe_id"] == "alpha"
        assert out_a["premise"] == "Alpha premise."
        assert out_b["universe_id"] == "beta"
        assert out_b["premise"] == "Beta premise."

    def test_inspect_includes_universe_id(self, universe_base):
        """Pre-existing behaviour — regression guard."""
        _make_universe(universe_base, "alpha")
        out = json.loads(us._action_inspect_universe(universe_id="alpha"))
        assert out["universe_id"] == "alpha"


class TestScopeHeader:
    """#15: the dispatcher wraps every universe-scoped response with a
    phone-legible `Universe: <id>` `text` lead-in, puts `universe_id`
    first, and leaves everything else structurally intact.
    """

    def test_dispatch_injects_text_header_on_read(self, universe_base):
        _make_universe(universe_base, "alpha")
        (universe_base / "alpha" / "PROGRAM.md").write_text(
            "An alpha premise.", encoding="utf-8",
        )
        out = json.loads(us._dispatch_with_ledger(
            "read_premise",
            us._action_read_premise,
            {"universe_id": "alpha"},
        ))
        assert "text" in out
        assert out["text"].startswith("Universe: alpha")
        assert out["premise"] == "An alpha premise."

    def test_universe_id_is_first_key(self, universe_base):
        _make_universe(universe_base, "alpha")
        out_str = us._dispatch_with_ledger(
            "read_premise",
            us._action_read_premise,
            {"universe_id": "alpha"},
        )
        out = json.loads(out_str)
        first_key = next(iter(out.keys()))
        assert first_key == "universe_id"

    def test_text_header_on_write_path(self, universe_base):
        _make_universe(universe_base, "alpha")
        out = json.loads(us._dispatch_with_ledger(
            "set_premise",
            us._action_set_premise,
            {"universe_id": "alpha", "text": "Fresh premise."},
        ))
        assert out["universe_id"] == "alpha"
        assert "text" in out
        assert out["text"].startswith("Universe: alpha")
        assert out["status"] == "updated"

    def test_error_without_universe_id_is_unchanged(self, universe_base):
        # An error response with no universe_id must NOT get a fake scope
        # header — we don't want to falsely claim a universe.
        out = json.loads(us._dispatch_with_ledger(
            "set_premise",
            us._action_set_premise,
            {"universe_id": "alpha", "text": ""},  # empty → error
        ))
        assert "error" in out
        if "text" in out:
            assert not out["text"].startswith("Universe: ")

    def test_multi_universe_list_not_scoped(self, universe_base):
        # list_universes returns a multi-universe response with no
        # single universe_id — must not get a scope header.
        _make_universe(universe_base, "alpha")
        _make_universe(universe_base, "beta")
        out = json.loads(us._dispatch_with_ledger(
            "list",
            us._action_list_universes,
            {},
        ))
        assert "universes" in out
        if "text" in out:
            assert not out["text"].startswith("Universe: ")

    def test_existing_text_field_preserved_under_header(self):
        # If a handler already emits a `text` field, the helper prepends
        # the header rather than clobbering it.
        fake = json.dumps({"universe_id": "alpha", "text": "Prior prose."})
        wrapped = json.loads(us._scope_universe_response(fake))
        assert wrapped["text"].startswith("Universe: alpha")
        assert "Prior prose." in wrapped["text"]

    def test_preserves_all_other_fields(self, universe_base):
        udir = _make_universe(universe_base, "alpha")
        (udir / "canon").mkdir()
        (udir / "canon" / "a.md").write_text("x", encoding="utf-8")
        out = json.loads(us._dispatch_with_ledger(
            "list_canon",
            us._action_list_canon,
            {"universe_id": "alpha"},
        ))
        assert out["universe_id"] == "alpha"
        assert out["count"] == 1
        assert out["canon_files"][0]["filename"] == "a.md"

    def test_non_universe_scoped_response_unchanged(self):
        # `_scope_universe_response` should leave dicts without
        # universe_id alone.
        payload = json.dumps({"branches": [], "count": 0})
        out = us._scope_universe_response(payload)
        assert json.loads(out) == {"branches": [], "count": 0}

    def test_non_json_response_unchanged(self):
        out = us._scope_universe_response("not json at all")
        assert out == "not json at all"
