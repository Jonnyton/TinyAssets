"""Tests for the file_bug → enqueue_investigation_request forward-trigger seam.

Task #34 (FRESH-A). Covers `_maybe_enqueue_investigation` directly. The
integration with `_wiki_file_bug` is captured as a skipped test that flips
to active once verifier-2 lands the one-line call site in
`universe_server.py`. Spec: `docs/exec-plans/active/2026-04-25-file-bug-wiring.md`.
"""

from __future__ import annotations

from unittest.mock import patch

from tinyassets.branch_tasks import read_queue
from tinyassets.bug_investigation import (
    REQUEST_TYPE_BUG_INVESTIGATION,
    _maybe_enqueue_investigation,
)

# ── _maybe_enqueue_investigation: env-gate ────────────────────────────────────


class TestEnvGate:
    def test_returns_none_when_env_unset(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", raising=False)
        result = _maybe_enqueue_investigation(
            bug_id="BUG-100",
            frontmatter={"title": "x"},
            base_path=tmp_path,
        )
        assert result is None
        assert read_queue(tmp_path) == []

    def test_returns_none_when_env_empty_string(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "")
        result = _maybe_enqueue_investigation(
            bug_id="BUG-101",
            frontmatter={"title": "x"},
            base_path=tmp_path,
        )
        assert result is None
        assert read_queue(tmp_path) == []

    def test_returns_none_when_env_whitespace(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "   ")
        result = _maybe_enqueue_investigation(
            bug_id="BUG-102",
            frontmatter={"title": "x"},
            base_path=tmp_path,
        )
        assert result is None
        assert read_queue(tmp_path) == []



def _register_handler_branch(base, monkeypatch, branch_def_id="branch-canonical-abc"):
    """G4 (2026-07-15): the resolver refuses handler ids that don't exist in
    the branch registry, so happy-path tests must register their id first —
    and pin TINYASSETS_DATA_DIR so the guard reads THIS test's registry."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import initialize_author_server, save_branch_definition

    initialize_author_server(base)
    save_branch_definition(
        base,
        branch_def=BranchDefinition(
            branch_def_id=branch_def_id, name=branch_def_id,
        ).to_dict(),
    )


# ── _maybe_enqueue_investigation: happy path ──────────────────────────────────


class TestEnqueuesWhenBound:
    def test_enqueues_when_canonical_bound(self, tmp_path, monkeypatch):
        _register_handler_branch(tmp_path, monkeypatch)
        monkeypatch.setenv(
            "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
        )
        monkeypatch.delenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", raising=False)
        request_id = _maybe_enqueue_investigation(
            bug_id="BUG-200",
            frontmatter={
                "title": "crash on load",
                "severity": "high",
                "component": "engine",
            },
            base_path=tmp_path,
        )
        assert request_id is not None
        assert len(request_id) == 36

        queue = read_queue(tmp_path)
        assert len(queue) == 1
        task = queue[0]
        assert task.branch_task_id == request_id
        assert task.request_type == REQUEST_TYPE_BUG_INVESTIGATION
        assert task.branch_def_id == "branch-canonical-abc"
        assert task.inputs["bug_id"] == "BUG-200"
        assert task.inputs["title"] == "crash on load"
        assert task.inputs["severity"] == "high"

    def test_passes_universe_id_through(self, tmp_path, monkeypatch):
        _register_handler_branch(tmp_path, monkeypatch)
        monkeypatch.setenv(
            "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
        )
        monkeypatch.delenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", raising=False)
        _maybe_enqueue_investigation(
            bug_id="BUG-201",
            frontmatter={"title": "x"},
            base_path=tmp_path,
            universe_id="custom-universe",
        )
        queue = read_queue(tmp_path)
        assert queue[0].universe_id == "custom-universe"

    def test_frontmatter_bug_id_overridden_by_arg(self, tmp_path, monkeypatch):
        _register_handler_branch(tmp_path, monkeypatch)
        """Even if frontmatter has a stale bug_id, the explicit arg wins."""
        monkeypatch.setenv(
            "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
        )
        monkeypatch.delenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", raising=False)
        _maybe_enqueue_investigation(
            bug_id="BUG-202",
            frontmatter={"bug_id": "BUG-WRONG", "title": "x"},
            base_path=tmp_path,
        )
        queue = read_queue(tmp_path)
        assert queue[0].inputs["bug_id"] == "BUG-202"


# ── _maybe_enqueue_investigation: graceful failure ────────────────────────────


class TestGracefulFailure:
    def test_returns_none_on_dispatcher_rejection(self, tmp_path, monkeypatch):
        """When `TINYASSETS_REQUEST_TYPE_PRIORITIES` excludes bug_investigation,
        enqueue raises RuntimeError. Filing must NOT break — caller gets None.

        Codex r11 #4: this must register a LIVE handler, else the G4 existence
        guard short-circuits (returns "" -> None) BEFORE the dispatcher path and
        the test is a false green. We assert the handler DOES resolve so this
        genuinely exercises the dispatcher-rejection path."""
        from tinyassets.bug_investigation import _resolve_investigation_handler

        _register_handler_branch(tmp_path, monkeypatch)   # LIVE handler
        monkeypatch.setenv(
            "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
        )
        monkeypatch.setenv(
            "TINYASSETS_REQUEST_TYPE_PRIORITIES", "paid_market,branch_run"
        )
        # The handler RESOLVES (not a resolver short-circuit) — so None below
        # comes from the DISPATCHER rejection, not the existence guard.
        assert _resolve_investigation_handler(tmp_path) == "branch-canonical-abc"

        result = _maybe_enqueue_investigation(
            bug_id="BUG-300",
            frontmatter={"title": "x"},
            base_path=tmp_path,
        )
        assert result is None
        assert read_queue(tmp_path) == []   # dispatcher refused -> nothing queued

    def test_returns_none_on_missing_bug_id(self, tmp_path, monkeypatch):
        """Empty bug_id is a malformed input — log and return None, do not crash."""
        monkeypatch.setenv(
            "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
        )
        monkeypatch.delenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", raising=False)
        result = _maybe_enqueue_investigation(
            bug_id="",
            frontmatter={"title": "x"},
            base_path=tmp_path,
        )
        assert result is None
        assert read_queue(tmp_path) == []

    def test_returns_none_on_value_error_from_enqueue(self, tmp_path, monkeypatch):
        """If `enqueue_investigation_request` raises ValueError, we recover."""
        monkeypatch.setenv(
            "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
        )
        monkeypatch.delenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", raising=False)
        with patch(
            "tinyassets.bug_investigation.enqueue_investigation_request",
            side_effect=ValueError("boom"),
        ):
            result = _maybe_enqueue_investigation(
                bug_id="BUG-301",
                frontmatter={"title": "x"},
                base_path=tmp_path,
            )
        assert result is None

    def test_none_frontmatter_does_not_crash(self, tmp_path, monkeypatch):
        _register_handler_branch(tmp_path, monkeypatch)
        monkeypatch.setenv(
            "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
        )
        monkeypatch.delenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", raising=False)
        request_id = _maybe_enqueue_investigation(
            bug_id="BUG-302",
            frontmatter=None,  # type: ignore[arg-type]
            base_path=tmp_path,
        )
        assert request_id is not None
        queue = read_queue(tmp_path)
        assert queue[0].inputs["bug_id"] == "BUG-302"


def test_wiki_file_bug_distinguishes_enqueue_failure_from_no_canonical(
    tmp_path, monkeypatch,
):
    """Codex r11 #4: a valid handler whose enqueue is REFUSED must report
    ``enqueue_failed`` — a DISTINCT class from ``no_canonical_branch`` (which is
    'no handler configured'). Both leave the filing intact."""
    import json as _json

    from tinyassets.api import wiki as wiki_api

    wiki_root = tmp_path / "wiki"
    data_root = tmp_path / "data"
    wiki_api._ensure_wiki_scaffold(wiki_root)
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(wiki_root))
    _register_handler_branch(data_root, monkeypatch)   # sets DATA_DIR + registers
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
    )
    # Priorities exclude bug_investigation -> the dispatcher refuses the enqueue.
    monkeypatch.setenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", "paid_market,branch_run")

    out = _json.loads(wiki_api._wiki_file_bug(
        component="engine", severity="minor", title="valid handler enqueue fail",
        observed="boom",
    ))
    assert out["status"] == "filed"                         # filing persists
    assert out["investigation"]["status"] == "enqueue_failed"
    assert out["investigation"]["branch_def_id"] == "branch-canonical-abc"

    # Contrast: NO handler configured -> no_canonical_branch (not enqueue_failed).
    monkeypatch.delenv("TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", raising=False)
    monkeypatch.delenv("TINYASSETS_BUG_INVESTIGATION_GOAL_ID", raising=False)
    out2 = _json.loads(wiki_api._wiki_file_bug(
        component="engine", severity="minor", title="no handler", observed="boom",
    ))
    assert out2["status"] == "filed"
    assert out2["investigation"]["status"] == "skipped"
    assert out2["investigation"].get("reason") == "no_canonical_branch"


# ── Integration: _wiki_file_bug call site ─────────────────────────────────────


def test_wiki_file_bug_invokes_maybe_enqueue_investigation(tmp_path, monkeypatch):
    """The post-write trigger queues investigation without breaking filing.

    1. _wiki_file_bug succeeds (returns status=filed) regardless of helper outcome.
    2. _maybe_enqueue_investigation is called once with bug_id + frontmatter +
       base_path of the universe.
    3. A queued request appends the Investigation section to the bug page.
    """
    from tinyassets.api import wiki as wiki_api

    wiki_root = tmp_path / "wiki"
    data_root = tmp_path / "data"
    wiki_api._ensure_wiki_scaffold(wiki_root)
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(wiki_root))
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(data_root))

    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
    )
    monkeypatch.delenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", raising=False)

    with patch(
        "tinyassets.bug_investigation._maybe_enqueue_investigation",
        return_value="fake-request-id",
    ) as helper:
        result_json = wiki_api._wiki_file_bug(
            component="engine",
            severity="minor",
            title="example bug",
            observed="boom",
        )

    import json as _json
    result = _json.loads(result_json)
    assert result["status"] == "filed"
    assert result["investigation"] == {
        "status": "queued",
        "dispatcher_request_id": "fake-request-id",
    }
    assert result["trigger"]["status"] == "queued"
    assert result["trigger"]["dispatcher_request_id"] == "fake-request-id"
    assert result["trigger"]["branch_def_id"] == "branch-canonical-abc"
    assert helper.call_count == 1
    bug_id = result["bug_id"]
    call_kwargs = helper.call_args.kwargs or {}
    call_args = helper.call_args.args or ()
    # accept either kwarg or positional first arg
    assert (call_kwargs.get("bug_id") == bug_id) or (
        call_args and call_args[0] == bug_id
    )
    assert call_kwargs["frontmatter"]["effort_class"] == "standard"
    assert (
        call_kwargs["frontmatter"]["effort_dispatch_route"]["lane"]
        == "standard-triage"
    )
    assert "## Investigation" in (wiki_root / result["path"]).read_text(
        encoding="utf-8"
    )


def test_wiki_file_bug_returns_failed_trigger_receipt_on_enqueue_error(
    tmp_path, monkeypatch,
):
    """A trigger helper failure must be visible in the file_bug response."""
    from tinyassets.api import wiki as wiki_api

    wiki_root = tmp_path / "wiki"
    data_root = tmp_path / "data"
    wiki_api._ensure_wiki_scaffold(wiki_root)
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(wiki_root))
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(data_root))
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc",
    )

    with patch(
        "tinyassets.bug_investigation._maybe_enqueue_investigation",
        side_effect=RuntimeError("dispatcher rejected"),
    ):
        result_json = wiki_api._wiki_file_bug(
            component="engine",
            severity="minor",
            title="enqueue error bug",
            observed="boom",
        )

    import json as _json
    result = _json.loads(result_json)
    assert result["status"] == "filed"
    assert result["investigation"]["status"] == "error"
    assert "dispatcher rejected" in result["investigation"]["error"]
    assert result["trigger"]["status"] == "failed"
    assert result["trigger"]["branch_def_id"] == "branch-canonical-abc"
    assert result["trigger"]["error"] == {
        "class": "RuntimeError",
        "message": "dispatcher rejected",
    }


def test_wiki_file_bug_resolves_handler_once_shared_provenance(tmp_path, monkeypatch):
    """Codex S1 latest-model Finding 3: the handler is resolved ONCE at the
    entry point and threaded into BOTH the receipt and the enqueue. A resolver
    that flips between calls must not yield mismatched provenance — the receipt
    and the enqueue must reflect the SAME (first) resolution, and the resolver
    must be called exactly once."""
    from unittest.mock import MagicMock

    import tinyassets.bug_investigation as bi
    from tinyassets.api import wiki as wiki_api

    wiki_root = tmp_path / "wiki"
    data_root = tmp_path / "data"
    wiki_api._ensure_wiki_scaffold(wiki_root)
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(wiki_root))
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(data_root))

    # The resolver would return DIFFERENT handlers on successive calls — a
    # canonical change/removal racing the filing. With the single-resolution
    # fix only the FIRST is ever observed.
    resolver = MagicMock(side_effect=[("handler-ONE", "ok"), ("handler-TWO", "ok")])
    monkeypatch.setattr(bi, "resolve_investigation_handler_detail", resolver)

    captured: dict[str, str] = {}

    def _fake_enqueue(*, bug_ref, canonical_branch_def_id, base_path, universe_id=""):
        captured["branch_def_id"] = canonical_branch_def_id
        return "req-shared"

    monkeypatch.setattr(bi, "enqueue_investigation_request", _fake_enqueue)

    import json as _json

    result = _json.loads(wiki_api._wiki_file_bug(
        component="engine", severity="minor", title="resolution race", observed="boom",
    ))

    assert resolver.call_count == 1                        # SINGLE resolution
    assert result["trigger"]["branch_def_id"] == "handler-ONE"   # receipt = call-1
    assert captured["branch_def_id"] == "handler-ONE"     # enqueue = SAME resolution
