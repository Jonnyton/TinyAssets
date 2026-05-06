"""Tests for BUG-029: run_branch error responses include failure_class + suggested_action."""
import json
from unittest.mock import patch

import pytest

from workflow.api.runs import (
    _classify_run_error,
    _classify_run_outcome_error,
)
from workflow.graph_compiler import EmptyResponseError
from workflow.runs import RunOutcome


class TestClassifyRunError:
    def test_empty_response_error_class(self):
        exc = EmptyResponseError("node x returned empty string")
        result = _classify_run_error(exc, "b1")
        assert result["failure_class"] == "empty_llm_response"
        assert "Ask the host" in result["suggested_action"]
        assert "get_status" in result["suggested_action"]
        assert result["status"] == "error"

    def test_recursion_error_class(self):
        exc = RecursionError("maximum recursion depth exceeded")
        result = _classify_run_error(exc, "b1")
        assert result["failure_class"] == "recursion_limit"
        assert "recursion_limit_override" in result["suggested_action"]

    def test_timeout_error_class(self):
        exc = TimeoutError("operation timed out")
        result = _classify_run_error(exc, "b1")
        assert result["failure_class"] == "timeout"
        assert result["suggested_action"]

    def test_provider_keyword_in_message(self):
        exc = RuntimeError("provider ANTHROPIC_API_KEY not set")
        result = _classify_run_error(exc, "b1")
        assert result["failure_class"] == "provider_unavailable"
        assert "keys" in result["suggested_action"].lower()

    def test_approval_keyword_in_message(self):
        exc = RuntimeError("source_code node requires approval")
        result = _classify_run_error(exc, "b1")
        assert result["failure_class"] == "node_not_approved"
        assert "approve_source_code" in result["suggested_action"]

    def test_quota_exhausted_rate_limit(self):
        exc = RuntimeError("rate limit exceeded for this model")
        result = _classify_run_error(exc, "b1")
        assert result["failure_class"] == "quota_exhausted"
        assert "llm_type" in result["suggested_action"]

    def test_quota_exhausted_quota_keyword(self):
        exc = RuntimeError("quota exceeded — upgrade plan")
        result = _classify_run_error(exc, "b1")
        assert result["failure_class"] == "quota_exhausted"

    def test_permission_denied_auth_expired(self):
        exc = RuntimeError("auth expired, please renew token")
        result = _classify_run_error(exc, "b1")
        assert result["failure_class"] == "permission_denied:auth_expired"
        assert "rotate" in result["suggested_action"].lower()

    def test_permission_denied_approval_required(self):
        exc = RuntimeError("permission denied for this operation")
        result = _classify_run_error(exc, "b1")
        assert result["failure_class"] == "permission_denied:approval_required"

    def test_state_mutation_conflict_concurrent(self):
        exc = RuntimeError("concurrent modification detected on branch")
        result = _classify_run_error(exc, "b1")
        assert result["failure_class"] == "state_mutation_conflict"
        assert "get_branch" in result["suggested_action"]

    def test_state_mutation_conflict_stale(self):
        exc = RuntimeError("stale state — resource was modified externally")
        result = _classify_run_error(exc, "b1")
        assert result["failure_class"] == "state_mutation_conflict"

    def test_node_not_approved_backward_compat(self):
        exc = RuntimeError("source_code node requires approval first")
        result = _classify_run_error(exc, "b1")
        assert result["failure_class"] == "node_not_approved"

    def test_unknown_exception_class(self):
        exc = ValueError("some unknown internal error")
        result = _classify_run_error(exc, "b1")
        assert result["failure_class"] == "unknown"
        assert "get_run" in result["suggested_action"]

    def test_error_message_always_present(self):
        """All failure classes include the original error message."""
        for exc in [
            EmptyResponseError("x"),
            RecursionError("y"),
            TimeoutError("z"),
            ValueError("w"),
        ]:
            result = _classify_run_error(exc, "b1")
            assert "Run failed:" in result["error"]


class TestRunBranchTaxonomyIntegration:
    """Integration tests: mock execute_branch_async to raise, verify MCP response shape."""

    def _call_run_branch(self, exc_to_raise):
        from workflow.api.runs import _action_run_branch

        branch_dict = {
            "branch_def_id": "b1", "name": "Test", "description": "",
            "author": "tester", "domain_id": "fantasy", "goal_id": "",
            "tags": [], "version": 1, "parent_def_id": "", "fork_from": None,
            "graph_nodes": [], "edges": [], "conditional_edges": [],
            "entry_point": "", "node_defs": [], "state_schema": [],
            "published": False, "visibility": "public",
            "created_at": "", "updated_at": "", "stats": {},
            "default_llm_policy": None, "concurrency_budget": None,
        }

        def raise_exc(*a, **kw):
            raise exc_to_raise

        with (
            patch("workflow.daemon_server.get_branch_definition", return_value=branch_dict),
            patch("workflow.api.helpers._base_path", return_value="/fake"),
            patch("workflow.api.engine_helpers._current_actor", return_value="tester"),
            patch("workflow.api.engine_helpers._current_actor", return_value="tester"),
            patch("workflow.api.runs._ensure_runs_recovery"),
            patch("workflow.branches.BranchDefinition.validate", return_value=[]),
            patch("workflow.runs.execute_branch_async", side_effect=raise_exc),
        ):
            return json.loads(_action_run_branch({"branch_def_id": "b1"}))

    def test_empty_response_error_surfaces_in_mcp(self):
        result = self._call_run_branch(EmptyResponseError("empty"))
        assert result["failure_class"] == "empty_llm_response"
        assert result["suggested_action"]
        assert result["status"] == "error"

    def test_recursion_error_surfaces_in_mcp(self):
        result = self._call_run_branch(RecursionError("too deep"))
        assert result["failure_class"] == "recursion_limit"

    def test_unknown_error_surfaces_in_mcp(self):
        result = self._call_run_branch(RuntimeError("some mystery error"))
        assert result["failure_class"] in ("unknown", "provider_unavailable", "node_not_approved")
        assert result["suggested_action"]


class TestClassifyRunOutcomeError:
    """Unit tests for _classify_run_outcome_error — the async-path string classifier."""

    @pytest.mark.parametrize("error_str,expected_class,action_fragment", [
        (
            "Empty LLM response: Node 'extract_claims': LLM returned empty response — "
            "check provider availability and credentials",
            "empty_llm_response",
            "llm_type",
        ),
        (
            "Branch run timed out after 120s",
            "timeout",
            "timeout param",
        ),
        (
            "Rate limit exceeded for this API key",
            "quota_exhausted",
            "llm_type",
        ),
        # Gap 1: provider "call failed" strings (Groq/Gemini/Grok generic errors)
        (
            "Groq call failed: connection reset by peer",
            "provider_error",
            "llm_type",
        ),
        (
            "Gemini call failed: unexpected EOF",
            "provider_error",
            "llm_type",
        ),
        (
            # "server error" substring triggers provider_overloaded, not provider_error
            "Grok call failed: internal server error",
            "provider_overloaded",
            "30-60s",
        ),
        # Gap 2: Claude subprocess failure strings
        (
            "claude -p returned exit code 1 quickly -- api likely unavailable",
            "provider_subprocess_failed",
            "binary",
        ),
        (
            "claude -p crashed with windows exit code 0xc0000374"
            " — subprocess failure, applying cooldown",
            "provider_subprocess_failed",
            "binary",
        ),
        # Gap 3: model overloaded / 503
        (
            # "503" hits overload check; "rate-limited" (hyphen) does NOT match "rate limit" (space)
            "Gemini rate-limited: 503 service unavailable — model overloaded",
            "provider_overloaded",
            "30-60s",
        ),
        (
            "server error: overloaded, please retry",
            "provider_overloaded",
            "30-60s",
        ),
        (
            "503 service temporarily unavailable",
            "provider_overloaded",
            "30-60s",
        ),
        # Gap 4: context window exceeded
        (
            "maximum context length exceeded: 8192 tokens, got 12000",
            "context_length_exceeded",
            "fewer nodes",
        ),
        (
            "context_length_exceeded: prompt is too long",
            "context_length_exceeded",
            "fewer nodes",
        ),
        (
            "too many tokens in the input",
            "context_length_exceeded",
            "fewer nodes",
        ),
    ])
    def test_known_patterns(self, error_str, expected_class, action_fragment):
        result = _classify_run_outcome_error(error_str)
        assert result is not None
        fc, action = result
        assert fc == expected_class
        assert action_fragment.lower() in action.lower()

    def test_empty_response_action_names_host_next_step(self):
        result = _classify_run_outcome_error(
            "Empty LLM response: Node 'extract_claims': LLM returned empty response"
        )
        assert result is not None
        assert result[0] == "empty_llm_response"
        assert "Ask the host" in result[1]
        assert "get_status" in result[1]

    def test_unknown_pattern_returns_none(self):
        assert _classify_run_outcome_error("some opaque internal error xyz") is None

    def test_empty_string_returns_none(self):
        assert _classify_run_outcome_error("") is None

    def test_empty_response_real_message(self):
        """Exact message from graph_compiler.py EmptyResponseError."""
        msg = (
            "Node 'extract_claims': LLM returned empty response — "
            "check provider availability and credentials"
        )
        result = _classify_run_outcome_error(f"Empty LLM response: {msg}")
        assert result is not None
        assert result[0] == "empty_llm_response"
        assert result[1]


class TestAsyncRunOutcomeEnrichment:
    """Test that _action_run_branch enriches failed RunOutcome with failure_class."""

    _BRANCH_DICT = {
        "branch_def_id": "b1", "name": "Test", "description": "",
        "author": "tester", "domain_id": "fantasy", "goal_id": "",
        "tags": [], "version": 1, "parent_def_id": "", "fork_from": None,
        "graph_nodes": [], "edges": [], "conditional_edges": [],
        "entry_point": "", "node_defs": [], "state_schema": [],
        "published": False, "visibility": "public",
        "created_at": "", "updated_at": "", "stats": {},
        "default_llm_policy": None, "concurrency_budget": None,
    }

    def _call_run_branch_with_outcome(self, outcome: RunOutcome) -> dict:
        from workflow.api.runs import _action_run_branch

        with (
            patch("workflow.daemon_server.get_branch_definition", return_value=self._BRANCH_DICT),
            patch("workflow.api.helpers._base_path", return_value="/fake"),
            patch("workflow.api.engine_helpers._current_actor", return_value="tester"),
            patch("workflow.api.engine_helpers._current_actor", return_value="tester"),
            patch("workflow.api.runs._ensure_runs_recovery"),
            patch("workflow.branches.BranchDefinition.validate", return_value=[]),
            patch("workflow.runs.execute_branch_async", return_value=outcome),
        ):
            return json.loads(_action_run_branch({"branch_def_id": "b1"}))

    def test_failed_outcome_empty_response_gets_enriched(self):
        outcome = RunOutcome(
            run_id="r1",
            status="failed",
            output={},
            error="Empty LLM response: Node 'extract_claims': LLM returned empty response — "
                  "check provider availability and credentials",
        )
        result = self._call_run_branch_with_outcome(outcome)
        assert result["failure_class"] == "empty_llm_response"
        assert result["suggested_action"]
        assert "llm_type" in result["suggested_action"]
        assert "Suggested action:" in result["text"]

    def test_failed_outcome_timeout_gets_enriched(self):
        outcome = RunOutcome(
            run_id="r2", status="failed", output={},
            error="Branch run timed out after 120s",
        )
        result = self._call_run_branch_with_outcome(outcome)
        assert result["failure_class"] == "timeout"
        assert result["suggested_action"]

    def test_successful_outcome_no_failure_class(self):
        outcome = RunOutcome(run_id="r3", status="completed", output={"result": "ok"}, error="")
        result = self._call_run_branch_with_outcome(outcome)
        assert "failure_class" not in result
        assert "suggested_action" not in result

    def test_failed_outcome_unknown_error_no_failure_class(self):
        outcome = RunOutcome(
            run_id="r4", status="failed", output={},
            error="some totally opaque internal error nobody knows about",
        )
        result = self._call_run_branch_with_outcome(outcome)
        assert "failure_class" not in result


class TestComposeRunSnapshotEnrichment:
    """Test that _compose_run_snapshot enriches failed runs with failure_class/suggested_action."""

    def _make_snapshot(self, status: str, error: str) -> dict:
        from workflow.api.runs import _compose_run_snapshot

        run_record = {
            "run_id": "r1",
            "branch_def_id": "b1",
            "status": status,
            "actor": "tester",
            "error": error,
            "started_at": None,
            "finished_at": None,
        }
        with (
            patch("workflow.daemon_server.get_branch_definition", side_effect=KeyError("b1")),
            patch("workflow.runs.build_node_status_map", return_value=[]),
            patch("workflow.api.runs._run_mermaid_from_events", return_value=""),
        ):
            return _compose_run_snapshot(run_record, [])

    def test_failed_run_empty_response_enriched(self):
        snapshot = self._make_snapshot(
            "failed",
            "Empty LLM response: Node 'extract_claims': LLM returned empty response — "
            "check provider availability and credentials",
        )
        assert snapshot["failure_class"] == "empty_llm_response"
        assert snapshot["suggested_action"]

    def test_failed_run_unknown_error_not_enriched(self):
        snapshot = self._make_snapshot("failed", "some opaque crash nobody knows")
        assert "failure_class" not in snapshot
        assert "suggested_action" not in snapshot

    def test_completed_run_not_enriched(self):
        snapshot = self._make_snapshot("completed", "")
        assert "failure_class" not in snapshot
        assert "suggested_action" not in snapshot


# ---------------------------------------------------------------------------
# BUG-029 actionable_by — Mara's chain-break (2026-04-24): chatbot had to
# guess "ask host to fix provider availability" because the error didn't
# tell it WHO can fix this. The third field closes that.
# ---------------------------------------------------------------------------


class TestActionableByCanonicalTable:
    """The canonical failure_class -> actionable_by table is `runs.ACTIONABLE_BY`.

    Both classifier paths and `list_recent_runs` consult it so the same
    failure_class always emits the same actionable_by — no per-call-site
    drift.
    """

    def test_table_imports(self):
        from workflow.runs import ACTIONABLE_BY
        assert isinstance(ACTIONABLE_BY, dict)
        assert ACTIONABLE_BY  # non-empty

    def test_values_only_in_allowed_set(self):
        from workflow.runs import ACTIONABLE_BY
        allowed = {"chatbot", "host", "user", "none"}
        for failure_class, actor in ACTIONABLE_BY.items():
            assert actor in allowed, (
                f"ACTIONABLE_BY[{failure_class!r}] = {actor!r}; "
                f"must be one of {allowed}"
            )

    @pytest.mark.parametrize("failure_class,expected_actor", [
        # Mara's case — host-side provider config / credentials.
        ("empty_llm_response", "host"),
        ("provider_unavailable", "host"),
        ("provider_subprocess_failed", "host"),
        ("provider_exhausted", "host"),
        ("sandbox_unavailable", "host"),
        ("node_not_approved", "host"),
        ("permission_denied:approval_required", "host"),
        ("permission_denied:auth_expired", "host"),
        # Chatbot can fix via another tool call.
        ("quota_exhausted", "chatbot"),
        ("provider_overloaded", "chatbot"),
        ("provider_error", "chatbot"),
        ("recursion_limit", "chatbot"),
        ("timeout", "chatbot"),
        ("context_length_exceeded", "chatbot"),
        ("state_mutation_conflict", "chatbot"),
        ("snapshot_schema_drift", "chatbot"),
        ("interrupted", "chatbot"),
        # Opaque/internal — chatbot escalates raw error for human judgment.
        ("unknown", "user"),
        ("error", "user"),
        # Terminal by design — no fix exists, no escalation needed.
        ("cancelled", "none"),
    ])
    def test_canonical_mapping(self, failure_class, expected_actor):
        from workflow.runs import ACTIONABLE_BY
        assert ACTIONABLE_BY[failure_class] == expected_actor

    def test_none_value_present(self):
        """Sanity: at least one terminal class maps to "none" — proves
        the value is in active use, not an aspirational fourth bucket."""
        from workflow.runs import ACTIONABLE_BY
        terminal = [k for k, v in ACTIONABLE_BY.items() if v == "none"]
        assert terminal, (
            "ACTIONABLE_BY must use 'none' for at least one terminal "
            "class — chatbot reading actionable_by='none' knows the run "
            "is dead by design (don't suggest retry, don't escalate)."
        )


class TestActionableByOnTypedExceptionPath:
    """`_classify_run_error` returns include actionable_by."""

    def test_empty_response_is_host_actionable(self):
        """Mara's case — chatbot must surface host-action, not retry."""
        exc = EmptyResponseError("node x returned empty string")
        result = _classify_run_error(exc, "b1")
        assert result["actionable_by"] == "host"

    def test_recursion_is_chatbot_actionable(self):
        exc = RecursionError("maximum recursion depth exceeded")
        result = _classify_run_error(exc, "b1")
        assert result["actionable_by"] == "chatbot"

    def test_timeout_is_chatbot_actionable(self):
        exc = TimeoutError("operation timed out")
        result = _classify_run_error(exc, "b1")
        assert result["actionable_by"] == "chatbot"

    def test_unknown_is_user_actionable(self):
        exc = ValueError("some unknown internal error")
        result = _classify_run_error(exc, "b1")
        assert result["failure_class"] == "unknown"
        assert result["actionable_by"] == "user"

    def test_quota_exhausted_is_chatbot_actionable(self):
        # Chatbot can switch llm_type; doesn't need host.
        exc = RuntimeError("rate limit exceeded for this model")
        result = _classify_run_error(exc, "b1")
        assert result["actionable_by"] == "chatbot"

    def test_provider_unavailable_is_host_actionable(self):
        exc = RuntimeError("provider ANTHROPIC_API_KEY not set")
        result = _classify_run_error(exc, "b1")
        assert result["actionable_by"] == "host"

    def test_field_always_present_when_failure_class_is(self):
        """No silent-drop: every failure response has all 3 fields together."""
        for exc in [
            EmptyResponseError("x"),
            RecursionError("y"),
            TimeoutError("z"),
            ValueError("w"),
            RuntimeError("rate limit hit"),
            RuntimeError("provider auth missing"),
        ]:
            result = _classify_run_error(exc, "b1")
            assert "failure_class" in result
            assert "suggested_action" in result
            assert "actionable_by" in result


class TestActionableByOnAsyncOutcomePath:
    """`_action_run_branch` enrichment includes actionable_by on RunOutcome.error."""

    _BRANCH_DICT = {
        "branch_def_id": "b1", "name": "Test", "description": "",
        "author": "tester", "domain_id": "fantasy", "goal_id": "",
        "tags": [], "version": 1, "parent_def_id": "", "fork_from": None,
        "graph_nodes": [], "edges": [], "conditional_edges": [],
        "entry_point": "", "node_defs": [], "state_schema": [],
        "published": False, "visibility": "public",
        "created_at": "", "updated_at": "", "stats": {},
        "default_llm_policy": None, "concurrency_budget": None,
    }

    def _call(self, outcome):
        from workflow.api.runs import _action_run_branch

        with (
            patch("workflow.daemon_server.get_branch_definition", return_value=self._BRANCH_DICT),
            patch("workflow.api.helpers._base_path", return_value="/fake"),
            patch("workflow.api.engine_helpers._current_actor", return_value="tester"),
            patch("workflow.api.engine_helpers._current_actor", return_value="tester"),
            patch("workflow.api.runs._ensure_runs_recovery"),
            patch("workflow.branches.BranchDefinition.validate", return_value=[]),
            patch("workflow.runs.execute_branch_async", return_value=outcome),
        ):
            return json.loads(_action_run_branch({"branch_def_id": "b1"}))

    def test_mara_empty_response_returns_host_actionable(self):
        """End-to-end Mara reproduction: empty LLM response -> host actionable."""
        outcome = RunOutcome(
            run_id="r1",
            status="failed",
            output={},
            error="Empty LLM response: Node 'extract_claims': LLM returned empty response — "
                  "check provider availability and credentials",
        )
        result = self._call(outcome)
        assert result["failure_class"] == "empty_llm_response"
        assert result["actionable_by"] == "host"
        assert result["suggested_action"]

    def test_timeout_returns_chatbot_actionable(self):
        outcome = RunOutcome(
            run_id="r2", status="failed", output={},
            error="Branch run timed out after 120s",
        )
        result = self._call(outcome)
        assert result["actionable_by"] == "chatbot"

    def test_quota_returns_chatbot_actionable(self):
        outcome = RunOutcome(
            run_id="r3", status="failed", output={},
            error="Rate limit exceeded for this API key",
        )
        result = self._call(outcome)
        assert result["actionable_by"] == "chatbot"

    def test_completed_run_omits_actionable_by(self):
        outcome = RunOutcome(run_id="r4", status="completed", output={"x": 1}, error="")
        result = self._call(outcome)
        assert "actionable_by" not in result

    def test_unrecognized_error_omits_actionable_by(self):
        """Same shape as failure_class/suggested_action — opaque error stays raw."""
        outcome = RunOutcome(
            run_id="r5", status="failed", output={},
            error="some totally opaque internal error nobody knows about",
        )
        result = self._call(outcome)
        assert "actionable_by" not in result


class TestActionableByOnGetRunSnapshot:
    """`_compose_run_snapshot` includes actionable_by — what `get_run` actually returns."""

    def _make_snapshot(self, status, error):
        from workflow.api.runs import _compose_run_snapshot

        run_record = {
            "run_id": "r1", "branch_def_id": "b1", "status": status,
            "actor": "tester", "error": error,
            "started_at": None, "finished_at": None,
        }
        with (
            patch("workflow.daemon_server.get_branch_definition", side_effect=KeyError("b1")),
            patch("workflow.runs.build_node_status_map", return_value=[]),
            patch("workflow.api.runs._run_mermaid_from_events", return_value=""),
        ):
            return _compose_run_snapshot(run_record, [])

    def test_mara_get_run_returns_host_actionable(self):
        """Reproduce Mara's flow: she'd called get_run on the failed run.

        With this fix her chatbot would have read actionable_by="host" off
        the response and surfaced the right action without guessing.
        """
        snapshot = self._make_snapshot(
            "failed",
            "Empty LLM response: Node 'extract_claims': LLM returned empty response — "
            "check provider availability and credentials",
        )
        assert snapshot["failure_class"] == "empty_llm_response"
        assert snapshot["actionable_by"] == "host"
        assert snapshot["suggested_action"]

    def test_completed_omits_actionable_by(self):
        snapshot = self._make_snapshot("completed", "")
        assert "actionable_by" not in snapshot

    def test_failed_unknown_omits_actionable_by(self):
        # Symmetric with failure_class/suggested_action — opaque means no enrichment.
        snapshot = self._make_snapshot("failed", "some opaque crash nobody knows")
        assert "actionable_by" not in snapshot


class TestActionableByOnListRecentRuns:
    """`list_recent_runs` (powering get_routing_evidence) emits actionable_by."""

    def test_failed_run_includes_actionable_by(self, tmp_path):
        # Drive list_recent_runs end-to-end via the real DB layer.
        from workflow.runs import (
            create_run,
            initialize_runs_db,
            list_recent_runs,
            update_run_status,
        )
        initialize_runs_db(tmp_path)
        run_id = create_run(
            tmp_path, branch_def_id="b1", thread_id="t1",
            run_name="t", actor="tester", inputs={},
        )
        update_run_status(
            tmp_path, run_id, status="failed",
            error="provider exhausted, all in cooldown",
        )
        rows = list_recent_runs(tmp_path, limit=10)
        assert rows
        row = rows[0]
        assert row["failure_class"] == "provider_exhausted"
        assert row["actionable_by"] == "host"

    def test_empty_llm_response_includes_host_next_action(self, tmp_path):
        from workflow.runs import (
            create_run,
            initialize_runs_db,
            list_recent_runs,
            update_run_status,
        )
        initialize_runs_db(tmp_path)
        run_id = create_run(
            tmp_path, branch_def_id="b1", thread_id="t3",
            run_name="t", actor="tester", inputs={},
        )
        update_run_status(
            tmp_path, run_id, status="failed",
            error=(
                "Empty LLM response: Node 'extract_claims': LLM returned empty response"
            ),
        )
        rows = list_recent_runs(tmp_path, limit=10)
        row = rows[0]
        assert row["failure_class"] == "empty_llm_response"
        assert row["actionable_by"] == "host"
        assert "Ask the host" in row["suggested_action"]
        assert "get_status" in row["suggested_action"]

    def test_completed_run_actionable_by_empty(self, tmp_path):
        from workflow.runs import (
            create_run,
            initialize_runs_db,
            list_recent_runs,
            update_run_status,
        )
        initialize_runs_db(tmp_path)
        run_id = create_run(
            tmp_path, branch_def_id="b1", thread_id="t2",
            run_name="t", actor="tester", inputs={},
        )
        update_run_status(tmp_path, run_id, status="completed")
        rows = list_recent_runs(tmp_path, limit=10)
        row = rows[0]
        # No failure → empty failure_class → empty actionable_by (not "user").
        assert row["failure_class"] == ""
        assert row["actionable_by"] == ""
