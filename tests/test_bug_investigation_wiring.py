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


def test_file_bug_transient_registry_is_retryable_not_terminal(tmp_path, monkeypatch):
    # Codex r20 #2: the tri-state must thread through the FULL resolution chain
    # (resolver + file_bug), not just claim_task. A TRANSIENT registry error
    # (SQLite locked) at file_bug's handler resolution must surface a RETRYABLE
    # trigger — NEVER a terminal handler_not_found — so the investigation can
    # retry once storage recovers. The filing itself always persists.
    import json as _json
    import sqlite3

    import tinyassets.daemon_server as ds
    from tinyassets.api import wiki as wiki_api

    wiki_root = tmp_path / "wiki"
    data_root = tmp_path / "data"
    wiki_api._ensure_wiki_scaffold(wiki_root)
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(wiki_root))
    _register_handler_branch(data_root, monkeypatch)   # sets DATA_DIR + registers
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
    )
    monkeypatch.setenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", "bug_investigation")

    # Registry read fails TRANSIENTLY at handler resolution (AFTER registration).
    def _locked(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(ds, "get_branch_definition", _locked)

    out = _json.loads(wiki_api._wiki_file_bug(
        component="engine", severity="minor", title="transient registry",
        observed="boom",
    ))
    assert out["status"] == "filed"                       # filing persists
    inv = out["investigation"]
    assert inv["status"] == "retryable", inv              # RETRYABLE, not terminal
    assert inv["error"] == "handler_unavailable", inv
    assert inv["status"] not in ("failed", "skipped"), inv


def test_retry_consumer_reattempts_pending_trigger_when_registry_recovers(
    tmp_path, monkeypatch,
):
    # Codex r21 #1c: a pending/unavailable trigger must ACTUALLY get retried, not
    # sit forever (re-filing dedups). The retry consumer re-resolves the handler
    # and, once the registry has recovered, enqueues the investigation + marks the
    # receipt queued.
    from tinyassets.branch_tasks import read_queue
    from tinyassets.bug_investigation import retry_pending_investigation_triggers
    from tinyassets.wiki import trigger_receipts as _tr

    _register_handler_branch(tmp_path, monkeypatch)   # DATA_DIR=tmp_path + registers
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
    )
    monkeypatch.setenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", "bug_investigation")

    # A trigger LEFT PENDING (its handler was transiently unavailable at file time).
    _tr.create_pending(
        request_id="BUG-RETRY", request_kind="bug",
        request_page="pages/bugs/bug-retry.md",
        branch_def_id="branch-canonical-abc", universe_id=tmp_path.name,
    )
    assert any(
        r.request_id == "BUG-RETRY" for r in _tr.pending_attempts(universe_id=None)
    )
    assert read_queue(tmp_path) == []

    # Registry is healthy now -> the retry consumer drains it.
    summary = retry_pending_investigation_triggers(tmp_path, universe_id=tmp_path.name)
    assert "BUG-RETRY" in summary["queued"], summary
    q = read_queue(tmp_path)
    assert any(
        t.request_type == "bug_investigation"
        and t.branch_def_id == "branch-canonical-abc"
        for t in q
    ), q
    # The receipt is no longer pending — it queued (not stranded).
    assert not any(
        r.request_id == "BUG-RETRY" for r in _tr.pending_attempts(universe_id=None)
    )


def test_retry_consumer_fails_pending_trigger_when_handler_definitively_gone(
    tmp_path, monkeypatch,
):
    # Complement (Codex r21 #1b/#1c): if the handler is DEFINITIVELY missing
    # (KeyError — registry initialized, id absent) at retry, the pending trigger
    # becomes terminal FAILED, not retried forever.
    from tinyassets.bug_investigation import retry_pending_investigation_triggers
    from tinyassets.daemon_server import delete_branch_definition
    from tinyassets.wiki import trigger_receipts as _tr

    _register_handler_branch(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
    )
    monkeypatch.setenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", "bug_investigation")
    # Registry is initialized but the handler is GONE -> KeyError -> definitive miss.
    delete_branch_definition(tmp_path, branch_def_id="branch-canonical-abc")

    _tr.create_pending(
        request_id="BUG-DEAD", request_kind="bug",
        request_page="pages/bugs/bug-dead.md",
        branch_def_id="branch-canonical-abc", universe_id=tmp_path.name,
    )
    summary = retry_pending_investigation_triggers(tmp_path, universe_id=tmp_path.name)
    assert "BUG-DEAD" in summary["failed"], summary
    assert not any(
        r.request_id == "BUG-DEAD" for r in _tr.pending_attempts(universe_id=None)
    )


def test_retry_is_exactly_once_under_concurrent_polls(tmp_path, monkeypatch):
    # Codex r22 #1: N concurrent poller threads processing the SAME pending
    # receipt must produce EXACTLY ONE queue task (stable branch_task_id +
    # idempotent append-under-lock), never N.
    import threading

    from tinyassets.branch_tasks import read_queue
    from tinyassets.bug_investigation import retry_pending_investigation_triggers
    from tinyassets.wiki import trigger_receipts as _tr

    _register_handler_branch(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
    )
    monkeypatch.setenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", "bug_investigation")
    _tr.create_pending(
        request_id="BUG-CONC", request_kind="bug",
        request_page="pages/bugs/bug-conc.md",
        branch_def_id="branch-canonical-abc", universe_id=tmp_path.name,
        payload_json='{"bug_id": "BUG-CONC", "title": "conc"}',
    )

    n = 5
    barrier = threading.Barrier(n)

    def _poll():
        barrier.wait()  # maximize contention
        retry_pending_investigation_triggers(tmp_path, universe_id=tmp_path.name)

    threads = [threading.Thread(target=_poll) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    q = [t for t in read_queue(tmp_path) if t.request_type == "bug_investigation"]
    assert len(q) == 1, [t.branch_task_id for t in q]   # EXACTLY ONE, not n
    assert not any(
        r.request_id == "BUG-CONC" for r in _tr.pending_attempts(universe_id=None)
    )


def test_retry_crash_recovery_does_not_double_enqueue(tmp_path, monkeypatch):
    # Codex r22 #1 (crash case): a crash AFTER enqueue but BEFORE mark_queued
    # leaves the receipt pending + the task queued. The next poll re-enqueues with
    # the SAME stable id -> idempotent no-op -> STILL exactly one task.
    from tinyassets.branch_tasks import read_queue
    from tinyassets.bug_investigation import retry_pending_investigation_triggers
    from tinyassets.wiki import trigger_receipts as _tr

    _register_handler_branch(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
    )
    monkeypatch.setenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", "bug_investigation")
    _tr.create_pending(
        request_id="BUG-CRASH", request_kind="bug",
        request_page="pages/bugs/bug-crash.md",
        branch_def_id="branch-canonical-abc", universe_id=tmp_path.name,
        payload_json='{"bug_id": "BUG-CRASH"}',
    )
    # First poll enqueues task-1 + marks queued.
    retry_pending_investigation_triggers(tmp_path, universe_id=tmp_path.name)
    # Simulate a crash BEFORE mark_queued: force the receipt back to pending.
    with _tr._conn() as c:
        c.execute(
            "UPDATE wiki_trigger_attempts SET status='pending' WHERE request_id=?",
            ("BUG-CRASH",),
        )
    # Re-poll: same stable id -> append_if_absent finds the existing task -> no dup.
    retry_pending_investigation_triggers(tmp_path, universe_id=tmp_path.name)

    q = [t for t in read_queue(tmp_path) if t.request_type == "bug_investigation"]
    assert len(q) == 1, [t.branch_task_id for t in q]   # STILL exactly one


def test_retry_preserves_original_filing_content(tmp_path, monkeypatch):
    # Codex r22 #2: a retried trigger enqueues the SAME content (title/component/
    # severity/observed/expected/repro) reconstructed from the persisted payload —
    # not a bare {"bug_id": ...} that queues "bug BUG-CONTEXT: Untitled".
    import json as _json

    from tinyassets.branch_tasks import read_queue
    from tinyassets.bug_investigation import retry_pending_investigation_triggers
    from tinyassets.wiki import trigger_receipts as _tr

    _register_handler_branch(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
    )
    monkeypatch.setenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", "bug_investigation")
    payload = {
        "bug_id": "BUG-CONTEXT", "title": "Export button broken",
        "component": "export", "severity": "major", "kind": "bug",
        "observed": "no download", "expected": "csv downloads",
        "repro": "click export",
    }
    _tr.create_pending(
        request_id="BUG-CONTEXT", request_kind="bug",
        request_page="pages/bugs/bug-context.md",
        branch_def_id="branch-canonical-abc", universe_id=tmp_path.name,
        payload_json=_json.dumps(payload),
    )
    retry_pending_investigation_triggers(tmp_path, universe_id=tmp_path.name)

    task = next(
        t for t in read_queue(tmp_path) if t.request_type == "bug_investigation"
    )
    blob = _json.dumps(task.inputs)
    # The ORIGINAL filing fields survive — NOT lost to a bare bug_id.
    for value in (
        "Export button broken", "export", "major",
        "no download", "csv downloads", "click export",
    ):
        assert value in blob, (value, task.inputs)
    assert "Untitled" not in task.inputs.get("request_text", "")


def test_retry_records_actual_handler_provenance(tmp_path, monkeypatch):
    # Codex r22 #3: the receipt records the ACTUAL rebound handler + source, so it
    # can't contradict the queued task; branch_def_id is a REAL branch id, never
    # synthetic goal: text.
    from tinyassets.branch_tasks import read_queue
    from tinyassets.bug_investigation import retry_pending_investigation_triggers
    from tinyassets.wiki import trigger_receipts as _tr

    _register_handler_branch(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
    )
    monkeypatch.setenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", "bug_investigation")
    # The receipt recorded a STALE handler; the current config resolves a
    # DIFFERENT one. Retry REBINDS to the current one and records it.
    _tr.create_pending(
        request_id="BUG-PROV", request_kind="bug",
        request_page="pages/bugs/bug-prov.md",
        branch_def_id="stale-handler-A", universe_id=tmp_path.name,
        payload_json='{"bug_id": "BUG-PROV"}',
    )
    retry_pending_investigation_triggers(tmp_path, universe_id=tmp_path.name)

    task = next(
        t for t in read_queue(tmp_path) if t.request_type == "bug_investigation"
    )
    assert task.branch_def_id == "branch-canonical-abc"   # rebound to current
    rec = next(
        r for r in _tr.recent_attempts(limit=20) if r.request_id == "BUG-PROV"
    )
    assert rec.branch_def_id == "branch-canonical-abc"    # receipt == task, no drift
    assert rec.resolution_source == "env_fallback"
    assert not (rec.branch_def_id or "").startswith("goal:")


def test_retry_does_not_cross_universe_boundaries(tmp_path, monkeypatch):
    # Codex r22 #4: a universe-A poll must NOT consume a universe-B receipt nor a
    # NULL-universe legacy receipt (which is quarantined for explicit recovery).
    from tinyassets.branch_tasks import read_queue
    from tinyassets.bug_investigation import retry_pending_investigation_triggers
    from tinyassets.wiki import trigger_receipts as _tr

    _register_handler_branch(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
    )
    monkeypatch.setenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", "bug_investigation")
    _tr.create_pending(
        request_id="BUG-OTHER", request_kind="bug", request_page="p",
        branch_def_id="branch-canonical-abc", universe_id="other-universe",
        payload_json='{"bug_id": "BUG-OTHER"}',
    )
    _tr.create_pending(
        request_id="BUG-LEGACY", request_kind="bug", request_page="p",
        branch_def_id="branch-canonical-abc", universe_id=None,
        payload_json='{"bug_id": "BUG-LEGACY"}',
    )
    summary = retry_pending_investigation_triggers(tmp_path, universe_id=tmp_path.name)

    assert "BUG-OTHER" not in summary["queued"]
    assert "BUG-LEGACY" not in summary["queued"]
    assert read_queue(tmp_path) == []   # nothing enqueued into THIS universe
    pend = {r.request_id for r in _tr.pending_attempts(universe_id=None)}
    assert {"BUG-OTHER", "BUG-LEGACY"} <= pend   # both untouched
    # The legacy NULL-universe receipt is quarantined for EXPLICIT recovery.
    assert "BUG-LEGACY" in {r.request_id for r in _tr.orphan_universe_attempts()}


def test_initial_enqueue_crash_then_retry_is_exactly_once(tmp_path, monkeypatch):
    # Codex r23 #1: the REAL crash window. file_bug's INITIAL enqueue and the
    # retry now derive the SAME stable task id from the receipt, so
    # initial-enqueue -> crash-before-mark_queued -> retry yields EXACTLY ONE task
    # (not two). (The r22 test only covered a retry-created receipt.)
    import json as _json

    from tinyassets.api import wiki as wiki_api
    from tinyassets.branch_tasks import read_queue
    from tinyassets.bug_investigation import retry_pending_investigation_triggers
    from tinyassets.wiki import trigger_receipts as _tr

    wiki_root = tmp_path / "wiki"
    data_root = tmp_path / "data"
    wiki_api._ensure_wiki_scaffold(wiki_root)
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(wiki_root))
    _register_handler_branch(data_root, monkeypatch)   # DATA_DIR=data_root + registers
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
    )
    monkeypatch.setenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", "bug_investigation")

    # INITIAL enqueue via file_bug -> ONE task (stable id) + receipt marked queued.
    out = _json.loads(wiki_api._wiki_file_bug(
        component="engine", severity="minor", title="crash window", observed="boom",
    ))
    assert out["investigation"]["status"] == "queued", out
    rec = _tr.recent_attempts(limit=5)[0]
    upath = wiki_api._universe_dir(rec.universe_id)
    q1 = [t for t in read_queue(upath) if t.request_type == "bug_investigation"]
    assert len(q1) == 1, [t.branch_task_id for t in q1]
    # The initial task id is the STABLE receipt-derived id (not a bare uuid4).
    assert q1[0].branch_task_id == f"inv:{rec.trigger_attempt_id}"

    # Simulate a crash BEFORE mark_queued: force the receipt back to pending.
    with _tr._conn() as c:
        c.execute(
            "UPDATE wiki_trigger_attempts SET status='pending' "
            "WHERE trigger_attempt_id=?", (rec.trigger_attempt_id,),
        )
    # Retry -> SAME stable id -> idempotent append -> STILL exactly one task.
    retry_pending_investigation_triggers(upath, universe_id=rec.universe_id)
    q2 = [t for t in read_queue(upath) if t.request_type == "bug_investigation"]
    assert len(q2) == 1, [t.branch_task_id for t in q2]   # exactly ONE, not two


def test_retry_clears_stale_goal_on_env_rebind(tmp_path, monkeypatch):
    # Codex r23 #3: a receipt recorded with an OLD goal, rebound to the ENV handler
    # on retry, must have its goal CLEARED — not preserved as a stale goal that
    # contradicts the env-resolved task.
    from tinyassets.bug_investigation import retry_pending_investigation_triggers
    from tinyassets.wiki import trigger_receipts as _tr

    _register_handler_branch(tmp_path, monkeypatch)
    monkeypatch.delenv("TINYASSETS_BUG_INVESTIGATION_GOAL_ID", raising=False)  # env path
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
    )
    monkeypatch.setenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", "bug_investigation")
    # A receipt carrying a STALE goal + stale handler.
    _tr.create_pending(
        request_id="BUG-GOAL", request_kind="bug", request_page="p",
        branch_def_id="stale-A", goal_id="goal-old", universe_id=tmp_path.name,
        payload_json='{"bug_id": "BUG-GOAL"}',
    )
    retry_pending_investigation_triggers(tmp_path, universe_id=tmp_path.name)

    rec = next(
        r for r in _tr.recent_attempts(limit=10) if r.request_id == "BUG-GOAL"
    )
    assert rec.branch_def_id == "branch-canonical-abc"   # rebound to env handler
    assert rec.resolution_source == "env_fallback"
    assert not rec.goal_id, rec.goal_id   # STALE "goal-old" CLEARED, not preserved


def test_enqueue_revalidates_handler_at_durable_boundary(tmp_path, monkeypatch):
    # Codex r14 #4 (G4 deletion race): a handler deleted between the upstream
    # existence check and the durable enqueue must NOT queue a dead reference —
    # the revalidation immediately before append_task refuses with
    # HandlerDeletedError and the queue stays EMPTY.
    import pytest

    from tinyassets.bug_investigation import (
        HandlerDeletedError,
        enqueue_investigation_request,
    )
    from tinyassets.daemon_server import delete_branch_definition

    _register_handler_branch(tmp_path, monkeypatch)   # registers + sets DATA_DIR
    monkeypatch.setenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", "bug_investigation")
    # The concurrent delete lands after the (upstream) resolution.
    delete_branch_definition(tmp_path, branch_def_id="branch-canonical-abc")

    with pytest.raises(HandlerDeletedError):
        enqueue_investigation_request(
            bug_ref={"bug_id": "BUG-RACE"},
            canonical_branch_def_id="branch-canonical-abc",
            base_path=tmp_path,
        )
    assert read_queue(tmp_path) == []   # NO dead reference queued


def test_maybe_enqueue_recovers_from_handler_deleted_race(tmp_path, monkeypatch):
    # The G4 revalidation is a RuntimeError subclass, so _maybe_enqueue_investigation
    # recovers (filing survives, returns None) — nothing queued against a dead ref.
    _register_handler_branch(tmp_path, monkeypatch)
    monkeypatch.setenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", "bug_investigation")
    monkeypatch.setenv(
        "TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", "branch-canonical-abc"
    )
    from tinyassets.daemon_server import delete_branch_definition

    delete_branch_definition(tmp_path, branch_def_id="branch-canonical-abc")
    # resolved_branch_def_id threaded in so the resolver isn't re-consulted; the
    # DURABLE revalidation is what must catch the delete.
    result = _maybe_enqueue_investigation(
        bug_id="BUG-RACE2",
        frontmatter={"title": "x"},
        base_path=tmp_path,
        resolved_branch_def_id="branch-canonical-abc",
    )
    assert result is None
    assert read_queue(tmp_path) == []


def test_claim_task_refuses_dead_handler_at_consumption(tmp_path, monkeypatch):
    # Codex r15 #5: the enqueue-boundary check only NARROWS the race window — a
    # delete while the task sits queued still needs closure at CONSUMPTION. The
    # claim boundary must revalidate the handler before transitioning to running:
    # a deleted handler yields a structured dead_ref terminal state, never a run
    # against a dead reference.
    import json as _json

    from tinyassets.branch_tasks import claim_task, queue_path
    from tinyassets.bug_investigation import enqueue_investigation_request
    from tinyassets.daemon_server import delete_branch_definition

    _register_handler_branch(tmp_path, monkeypatch)
    monkeypatch.setenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", "bug_investigation")

    request_id = enqueue_investigation_request(
        bug_ref={"bug_id": "BUG-CLAIM"},
        canonical_branch_def_id="branch-canonical-abc",
        base_path=tmp_path,
    )
    assert request_id   # enqueued while the handler existed

    # Handler deleted while the task sits QUEUED (the window the enqueue check
    # can't cover).
    delete_branch_definition(tmp_path, branch_def_id="branch-canonical-abc")

    claimed = claim_task(tmp_path, request_id, claimer="daemon-1")
    assert claimed is None   # refused — NOT transitioned to running

    raw = _json.loads(queue_path(tmp_path).read_text(encoding="utf-8"))
    row = next(r for r in raw if r["branch_task_id"] == request_id)
    assert row["status"] == "dead_ref"                       # structured outcome
    assert row["dead_ref_reason"].startswith("handler_deleted:")

    # Codex r16 #4: dead_ref is a COMPLETE terminal state.
    # (a) terminal_at is stamped (like mark_status) so get_status's loop-stall
    #     signal counts this as a real terminal transition.
    assert row.get("terminal_at"), "dead_ref must stamp terminal_at"
    # (b) dead_ref_reason survives BranchTask deserialization (from_dict filters
    #     to declared fields — it must be a declared field, not silently dropped).
    from tinyassets.branch_tasks import BranchTask

    task = BranchTask.from_dict(row)
    assert task.status == "dead_ref"
    assert task.dead_ref_reason.startswith("handler_deleted:")
    assert task.terminal_at
    # (c) get_status loop-health counts dead_ref and surfaces it as a warning.
    from tinyassets.api.status import _compute_supervisor_liveness

    live = _compute_supervisor_liveness(tmp_path)
    assert live["queue_state"]["dead_ref"] == 1, live["queue_state"]
    assert any(
        "dead_ref_terminals" in w for w in live["warnings"]
    ), live["warnings"]


def test_claim_task_transient_registry_error_stays_retryable(tmp_path, monkeypatch):
    # Codex r19 #2: a TRANSIENT registry read error (e.g. SQLite 'database is
    # locked') must NOT become a permanent dead_ref. Consumption-time
    # revalidation distinguishes definitive-missing (terminal) from
    # transient-unavailable (retryable): the task stays PENDING for a later claim
    # once storage recovers — never permanently discarded on a momentary lock.
    import json as _json
    import sqlite3

    import tinyassets.daemon_server as ds
    from tinyassets.branch_tasks import claim_task, queue_path
    from tinyassets.bug_investigation import enqueue_investigation_request

    _register_handler_branch(tmp_path, monkeypatch)
    monkeypatch.setenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", "bug_investigation")

    request_id = enqueue_investigation_request(
        bug_ref={"bug_id": "BUG-LOCK"},
        canonical_branch_def_id="branch-canonical-abc",
        base_path=tmp_path,
    )
    assert request_id   # enqueued while storage was healthy

    # Simulate a TRANSIENT storage failure at claim-time revalidation (AFTER
    # enqueue, so only the revalidation read sees it).
    def _locked(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(ds, "get_branch_definition", _locked)

    claimed = claim_task(tmp_path, request_id, claimer="daemon-1")
    assert claimed is None   # not claimed while storage is unavailable

    raw = _json.loads(queue_path(tmp_path).read_text(encoding="utf-8"))
    row = next(r for r in raw if r["branch_task_id"] == request_id)
    # RETRYABLE: still pending, NOT terminal dead_ref, no dead_ref stamp.
    assert row["status"] == "pending", row
    assert not row.get("terminal_at"), row
    assert not row.get("dead_ref_reason"), row


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
    # fix only the FIRST is ever observed. (r22 #3: file_bug now resolves via the
    # 4-tuple provenance resolver — branch_def_id, reason, source, goal_id.)
    resolver = MagicMock(side_effect=[
        ("handler-ONE", "ok", "env_fallback", ""),
        ("handler-TWO", "ok", "env_fallback", ""),
    ])
    monkeypatch.setattr(
        bi, "resolve_investigation_handler_with_provenance", resolver,
    )

    captured: dict[str, str] = {}

    def _fake_enqueue(
        *, bug_ref, canonical_branch_def_id, base_path, universe_id="",
        request_id="", **_kw,
    ):
        captured["branch_def_id"] = canonical_branch_def_id
        return request_id or "req-shared"

    monkeypatch.setattr(bi, "enqueue_investigation_request", _fake_enqueue)

    import json as _json

    result = _json.loads(wiki_api._wiki_file_bug(
        component="engine", severity="minor", title="resolution race", observed="boom",
    ))

    assert resolver.call_count == 1                        # SINGLE resolution
    assert result["trigger"]["branch_def_id"] == "handler-ONE"   # receipt = call-1
    assert captured["branch_def_id"] == "handler-ONE"     # enqueue = SAME resolution
