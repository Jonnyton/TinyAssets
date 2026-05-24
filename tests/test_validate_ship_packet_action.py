"""Tests for ``extensions action=validate_ship_packet`` (PR #198 Phase 2A).

Wraps ``workflow.auto_ship.validate_ship_request`` as an MCP action so the
loop's release_safety_gate prompt and external callers (chatbots /
canaries) can reach it via tool. The validator itself is exercised
exhaustively in ``tests/test_auto_ship.py`` — these tests cover the
wrapper layer only.
"""

from __future__ import annotations

import inspect
import json

from workflow.api.auto_ship_actions import (
    _AUTO_SHIP_ACTIONS,
    _action_open_auto_ship_pr,
    _action_validate_ship_packet,
)
from workflow.api.extensions import _extensions_impl

# ── Wrapper layer (handler-level) ──────────────────────────────────────────


class TestHandlerLayer:
    def test_dispatch_dict_exposes_action(self):
        assert "validate_ship_packet" in _AUTO_SHIP_ACTIONS
        assert _AUTO_SHIP_ACTIONS["validate_ship_packet"] is _action_validate_ship_packet
        assert "open_auto_ship_pr" in _AUTO_SHIP_ACTIONS
        assert _AUTO_SHIP_ACTIONS["open_auto_ship_pr"] is _action_open_auto_ship_pr

    def test_missing_body_json_returns_error(self):
        result = json.loads(_action_validate_ship_packet({}))
        assert "error" in result
        assert "body_json" in result["error"]

    def test_empty_body_json_returns_error(self):
        result = json.loads(_action_validate_ship_packet({"body_json": ""}))
        assert "error" in result

    def test_whitespace_body_json_returns_error(self):
        result = json.loads(_action_validate_ship_packet({"body_json": "   "}))
        assert "error" in result

    def test_invalid_json_returns_parse_error(self):
        result = json.loads(_action_validate_ship_packet({"body_json": "not json"}))
        assert "error" in result
        assert "body_json is not valid JSON" in result["error"]

    def test_valid_packet_returns_decision_dict(self):
        packet = {
            "release_gate_result": "APPROVE_AUTO_SHIP",
            "ship_class": "docs_canary",
            "child_keep_reject_decision": "KEEP",
            "coding_packet": {"status": "KEEP_READY"},
            "child_score": 9.5,
            "risk_level": "low",
            "blocked_execution_record": {},
            "stable_evidence_handle": "child_run:b:r",
            "automation_claim_status": "child_attached_with_handle",
            "rollback_plan": "Revert commit <sha>",
            "changed_paths": ["docs/autoship-canaries/x.md"],
            "diff": "+ added\n",
        }
        result = json.loads(_action_validate_ship_packet({
            "body_json": json.dumps(packet),
        }))
        assert result["validation_result"] == "passed"
        assert result["would_open_pr"] is True
        assert result["dry_run"] is True
        assert result["ship_status"] == "skipped"

    def test_blocked_packet_returns_decision_dict_with_violations(self):
        packet = {
            "release_gate_result": "HOLD",  # NOT approved
            "ship_class": "docs_canary",
            "child_keep_reject_decision": "REVIEW_READY",
            "stable_evidence_handle": "x",
            "automation_claim_status": "child_attached_with_handle",
            "rollback_plan": "y",
            "changed_paths": ["docs/autoship-canaries/x.md"],
            "diff": "x",
        }
        result = json.loads(_action_validate_ship_packet({
            "body_json": json.dumps(packet),
        }))
        assert result["validation_result"] == "blocked"
        assert result["would_open_pr"] is False
        assert len(result["violations"]) >= 1


# ── Dispatch via _extensions_impl ──────────────────────────────────────────


class TestDispatchIntegration:
    def test_public_extensions_signature_exposes_ledger_kwargs(self):
        from workflow import universe_server as us

        params = inspect.signature(us.extensions).parameters
        for name in (
            "record_in_ledger",
            "universe_id",
            "request_id",
            "parent_run_id",
            "child_run_id",
            "branch_def_id",
            "release_gate_result",
            "ship_class",
            "changed_paths_json",
            "stable_evidence_handle",
        ):
            assert name in params

    def test_action_routes_to_handler_via_extensions_dispatch(self):
        packet = {
            "release_gate_result": "APPROVE_AUTO_SHIP",
            "ship_class": "docs_canary",
            "child_keep_reject_decision": "KEEP",
            "coding_packet": {"status": "KEEP_READY"},
            "child_score": 9.5,
            "risk_level": "low",
            "blocked_execution_record": {},
            "stable_evidence_handle": "child_run:b:r",
            "automation_claim_status": "child_attached_with_handle",
            "rollback_plan": "Revert commit <sha>",
            "changed_paths": ["docs/autoship-canaries/x.md"],
            "diff": "+ x\n",
        }
        result_str = _extensions_impl(
            action="validate_ship_packet",
            body_json=json.dumps(packet),
        )
        result = json.loads(result_str)
        assert result["validation_result"] == "passed"

    def test_action_with_no_body_json_routes_and_errors_at_handler(self):
        result_str = _extensions_impl(action="validate_ship_packet")
        result = json.loads(result_str)
        assert "error" in result
        assert "body_json" in result["error"]

    def test_validate_ship_packet_dispatch_forwards_ledger_kwargs(
        self,
        tmp_path,
        monkeypatch,
    ):
        from workflow.auto_ship_ledger import read_attempts

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "default-uni")
        universe = tmp_path / "ledger-uni"
        universe.mkdir(parents=True, exist_ok=True)
        packet = {
            "release_gate_result": "APPROVE_AUTO_SHIP",
            "ship_class": "docs_canary",
            "child_keep_reject_decision": "KEEP",
            "coding_packet": {"status": "KEEP_READY"},
            "child_score": 9.5,
            "risk_level": "low",
            "blocked_execution_record": {},
            "stable_evidence_handle": "packet-evidence",
            "automation_claim_status": "child_attached_with_handle",
            "rollback_plan": "Revert commit <sha>",
            "changed_paths": ["docs/autoship-canaries/from-packet.md"],
            "diff": "+ x\n",
        }

        result_str = _extensions_impl(
            action="validate_ship_packet",
            body_json=json.dumps(packet),
            record_in_ledger=True,
            universe_id="ledger-uni",
            request_id="REQ-DISPATCH",
            parent_run_id="parent-run",
            child_run_id="child-run",
            branch_def_id="branch-def",
            release_gate_result="APPROVE_AUTO_SHIP",
            ship_class="docs_canary",
            changed_paths_json=json.dumps([
                "docs/autoship-canaries/from-dispatch.md",
            ]),
            stable_evidence_handle="dispatch-evidence",
        )
        result = json.loads(result_str)

        assert result.get("ledger_error") is None
        assert result["ship_attempt_id"]
        rows = read_attempts(universe)
        assert len(rows) == 1
        row = rows[0]
        assert row.request_id == "REQ-DISPATCH"
        assert row.parent_run_id == "parent-run"
        assert row.child_run_id == "child-run"
        assert row.branch_def_id == "branch-def"
        assert row.stable_evidence_handle == "dispatch-evidence"
        assert json.loads(row.changed_paths_json) == [
            "docs/autoship-canaries/from-dispatch.md",
        ]

    def test_public_extensions_wrapper_records_ledger_row(
        self,
        tmp_path,
        monkeypatch,
    ):
        """The public MCP wrapper forwards ledger fields to the action."""
        from workflow import universe_server as us
        from workflow.auto_ship_ledger import read_attempts

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "default-uni")
        universe = tmp_path / "wrapper-uni"
        universe.mkdir(parents=True, exist_ok=True)
        packet = {
            "release_gate_result": "APPROVE_AUTO_SHIP",
            "ship_class": "docs_canary",
            "child_keep_reject_decision": "KEEP",
            "coding_packet": {"status": "KEEP_READY"},
            "child_score": 9.5,
            "risk_level": "low",
            "blocked_execution_record": {},
            "stable_evidence_handle": "packet-evidence",
            "automation_claim_status": "child_attached_with_handle",
            "rollback_plan": "Revert commit <sha>",
            "changed_paths": ["docs/autoship-canaries/from-packet.md"],
            "diff": "+ x\n",
        }

        result_str = us.extensions(
            action="validate_ship_packet",
            body_json=json.dumps(packet),
            record_in_ledger="true",
            universe_id="wrapper-uni",
            request_id="REQ-WRAPPER",
            parent_run_id="parent-run",
            child_run_id="child-run",
            branch_def_id="branch-def",
            stable_evidence_handle="wrapper-evidence",
        )
        result = json.loads(result_str)

        assert result.get("ledger_error") is None
        assert result["ship_attempt_id"]
        rows = read_attempts(universe)
        assert len(rows) == 1
        row = rows[0]
        assert row.ship_attempt_id == result["ship_attempt_id"]
        assert row.request_id == "REQ-WRAPPER"
        assert row.parent_run_id == "parent-run"
        assert row.child_run_id == "child-run"
        assert row.branch_def_id == "branch-def"
        assert row.stable_evidence_handle == "wrapper-evidence"

    def test_open_auto_ship_pr_routes_to_handler_disabled(self, tmp_path, monkeypatch):
        from workflow.auto_ship_ledger import ShipAttempt, find_attempt, record_attempt

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "test-uni")
        monkeypatch.delenv("WORKFLOW_AUTO_SHIP_PR_CREATE_ENABLED", raising=False)
        universe = tmp_path / "test-uni"
        universe.mkdir(parents=True, exist_ok=True)
        record_attempt(universe, ShipAttempt(
            ship_attempt_id="ship_route",
            created_at="2026-05-03T00:00:00+00:00",
            updated_at="2026-05-03T00:00:00+00:00",
            ship_status="skipped",
            would_open_pr=True,
        ))

        result_str = _extensions_impl(
            action="open_auto_ship_pr",
            ship_attempt_id="ship_route",
            head_branch="auto-change/issue-999-codex-123",
            title="[auto-change] BUG-999",
        )
        result = json.loads(result_str)

        assert result["ship_status"] == "skipped"
        assert result["error_class"] == "pr_create_disabled"
        row = find_attempt(universe, "ship_route")
        assert row is not None
        assert row.error_class == "pr_create_disabled"


# ── Wrapper resilience ─────────────────────────────────────────────────────


class TestResilience:
    def test_packet_that_makes_validator_raise_returns_error_dict_not_crash(self, monkeypatch):
        """Even if validate_ship_request unexpectedly raises, the wrapper
        returns a JSON error dict rather than letting MCP get a 500.
        """
        def boom(packet):
            raise RuntimeError("simulated validator failure")

        # Need to patch the import location used inside the handler.
        monkeypatch.setattr("workflow.auto_ship.validate_ship_request", boom)

        result = json.loads(_action_validate_ship_packet({
            "body_json": json.dumps({"any": "packet"}),
        }))
        assert "error" in result
        assert "validate_ship_request raised" in result["error"]
        assert result.get("exception_class") == "RuntimeError"


# ── Ledger recording (PR #198 §8 wire-up — Slice A consumer) ──────────────


class TestLedgerRecording:
    """The wire-up surface added on top of PR #224. ``record_in_ledger``
    is opt-in: when omitted (or falsy) the response is byte-identical
    to the pre-wire-up behavior (no extra keys, no IO).

    When opt-in, every validator outcome — passed OR blocked — produces
    one row in the ledger keyed by ``ship_attempt_id``, and the response
    is augmented with that id. Failure to write the row surfaces as
    ``ledger_error`` so callers see the problem without losing the
    decision payload.
    """

    @staticmethod
    def _packet(**overrides):
        base = {
            "release_gate_result": "APPROVE_AUTO_SHIP",
            "ship_class": "docs_canary",
            "child_keep_reject_decision": "KEEP",
            "coding_packet": {"status": "KEEP_READY"},
            "child_score": 9.5,
            "risk_level": "low",
            "blocked_execution_record": {},
            "stable_evidence_handle": "h:1",
            "automation_claim_status": "child_attached_with_handle",
            "rollback_plan": "r",
            "changed_paths": ["docs/autoship-canaries/x.md"],
            "diff": "+x\n",
        }
        base.update(overrides)
        return base

    @staticmethod
    def _setup_universe(tmp_path, monkeypatch, name="test-uni"):
        from pathlib import Path
        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", name)
        (Path(tmp_path) / name).mkdir(parents=True, exist_ok=True)
        return Path(tmp_path) / name

    def test_record_off_response_is_byte_identical_to_pr224(self, tmp_path, monkeypatch):
        self._setup_universe(tmp_path, monkeypatch)
        from workflow.auto_ship_ledger import read_attempts
        result = json.loads(_action_validate_ship_packet({
            "body_json": json.dumps(self._packet()),
        }))
        assert "ship_attempt_id" not in result
        assert "ledger_error" not in result
        # And nothing was written
        from pathlib import Path
        assert read_attempts(Path(tmp_path) / "test-uni") == []

    def test_record_on_passed_writes_skipped_row(self, tmp_path, monkeypatch):
        u = self._setup_universe(tmp_path, monkeypatch)
        from workflow.auto_ship_ledger import read_attempts
        result = json.loads(_action_validate_ship_packet({
            "body_json": json.dumps(self._packet()),
            "record_in_ledger": True,
            "request_id": "REQ-1",
            "parent_run_id": "run_1",
            "branch_def_id": "branch-1",
            "child_run_id": "child_1",
        }))
        assert result.get("ledger_error") is None
        attempt_id = result["ship_attempt_id"]
        assert attempt_id and attempt_id.startswith("ship_")
        rows = read_attempts(u)
        assert len(rows) == 1
        row = rows[0]
        assert row.ship_attempt_id == attempt_id
        assert row.ship_status == "skipped"  # validator passed, dry-run
        assert row.would_open_pr is True
        assert row.request_id == "REQ-1"
        assert row.parent_run_id == "run_1"
        assert row.branch_def_id == "branch-1"
        assert row.child_run_id == "child_1"
        # Pulled from packet by default
        assert row.release_gate_result == "APPROVE_AUTO_SHIP"
        assert row.ship_class == "docs_canary"
        # Rollback handle carried from validator's rollback_handle
        assert row.rollback_handle.startswith("revert:")

    def test_record_on_blocked_writes_blocked_row_with_violations(self, tmp_path, monkeypatch):
        u = self._setup_universe(tmp_path, monkeypatch)
        from workflow.auto_ship_ledger import read_attempts
        result = json.loads(_action_validate_ship_packet({
            "body_json": json.dumps(self._packet(release_gate_result="HOLD")),
            "record_in_ledger": True,
            "request_id": "REQ-2",
        }))
        assert result.get("ledger_error") is None
        rows = read_attempts(u)
        assert len(rows) == 1
        row = rows[0]
        assert row.ship_status == "blocked"
        assert row.would_open_pr is False
        assert "release_gate_not_approved" in row.error_class
        # error_message is the violations payload as JSON
        violations = json.loads(row.error_message)
        assert any(v["rule_id"] == "release_gate_not_approved" for v in violations)

    def test_explicit_universe_id_overrides_default(self, tmp_path, monkeypatch):
        from pathlib import Path

        from workflow.auto_ship_ledger import read_attempts
        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "default-uni")
        (Path(tmp_path) / "default-uni").mkdir(parents=True, exist_ok=True)
        (Path(tmp_path) / "other-uni").mkdir(parents=True, exist_ok=True)

        json.loads(_action_validate_ship_packet({
            "body_json": json.dumps(self._packet()),
            "record_in_ledger": True,
            "universe_id": "other-uni",
            "request_id": "REQ-X",
        }))
        assert read_attempts(Path(tmp_path) / "default-uni") == []
        rows_other = read_attempts(Path(tmp_path) / "other-uni")
        assert len(rows_other) == 1
        assert rows_other[0].request_id == "REQ-X"

    def test_string_truthy_record_flag_enables_recording(self, tmp_path, monkeypatch):
        u = self._setup_universe(tmp_path, monkeypatch)
        from workflow.auto_ship_ledger import read_attempts
        result = json.loads(_action_validate_ship_packet({
            "body_json": json.dumps(self._packet()),
            "record_in_ledger": "true",
            "request_id": "REQ-S",
        }))
        assert "ship_attempt_id" in result
        assert len(read_attempts(u)) == 1

    def test_string_falsy_record_flag_skips_recording(self, tmp_path, monkeypatch):
        u = self._setup_universe(tmp_path, monkeypatch)
        from workflow.auto_ship_ledger import read_attempts
        for falsy in ("false", " False ", "0", "no", "off", ""):
            result = json.loads(_action_validate_ship_packet({
                "body_json": json.dumps(self._packet()),
                "record_in_ledger": falsy,
            }))
            assert "ship_attempt_id" not in result, falsy
        assert read_attempts(u) == []

    def test_changed_paths_json_kwarg_overrides_packet_paths(self, tmp_path, monkeypatch):
        u = self._setup_universe(tmp_path, monkeypatch)
        from workflow.auto_ship_ledger import read_attempts
        json.loads(_action_validate_ship_packet({
            "body_json": json.dumps(self._packet(
                changed_paths=["docs/autoship-canaries/from-packet.md"],
            )),
            "record_in_ledger": True,
            "request_id": "REQ-CP",
            "changed_paths_json": json.dumps([
                "docs/autoship-canaries/override-a.md",
                "docs/autoship-canaries/override-b.md",
            ]),
        }))
        rows = read_attempts(u)
        assert len(rows) == 1
        paths = json.loads(rows[0].changed_paths_json)
        assert paths == [
            "docs/autoship-canaries/override-a.md",
            "docs/autoship-canaries/override-b.md",
        ]

    def test_malformed_changed_paths_json_falls_back_to_packet(self, tmp_path, monkeypatch):
        u = self._setup_universe(tmp_path, monkeypatch)
        from workflow.auto_ship_ledger import read_attempts
        json.loads(_action_validate_ship_packet({
            "body_json": json.dumps(self._packet(changed_paths=["docs/autoship-canaries/x.md"])),
            "record_in_ledger": True,
            "request_id": "REQ-FB",
            "changed_paths_json": "not-json",
        }))
        rows = read_attempts(u)
        paths = json.loads(rows[0].changed_paths_json)
        assert paths == ["docs/autoship-canaries/x.md"]

    def test_ledger_write_failure_surfaces_in_response(self, tmp_path, monkeypatch):
        """If record_attempt raises (e.g. invalid universe), the wrapper
        blocks acceptance and surfaces ledger_error."""
        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "")
        # No universe directories exist; helper falls back to "default-universe"
        # which doesn't exist as a dir. record_attempt creates it via mkdir —
        # so we instead force a path-traversal validation error.
        result = json.loads(_action_validate_ship_packet({
            "body_json": json.dumps(self._packet()),
            "record_in_ledger": True,
            "universe_id": "../escape-attempt",
            "request_id": "REQ-ERR",
        }))
        # A packet cannot be accepted for shipping without its requested
        # ledger row.
        assert result["validation_result"] == "blocked"
        assert result["would_open_pr"] is False
        assert result["ship_status"] == "failed"
        assert any(v["rule_id"] == "ledger_record_failed" for v in result["violations"])
        assert "ledger_error" in result
        assert (
            "Invalid universe_id" in result["ledger_error"]
            or "invalid universe_id" in result["ledger_error"]
        )
        # And no ship_attempt_id — the write didn't happen
        assert result.get("ship_attempt_id") is None

    def test_extensions_dispatch_blocks_acceptance_when_requested_ledger_not_recorded(
        self,
        tmp_path,
        monkeypatch,
    ):
        """Regression for BUG-058: the public extensions action must not
        return an accepting ship decision when record_in_ledger=true but no
        ledger row is created.
        """
        from workflow.auto_ship_ledger import read_attempts

        monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "default-uni")
        (tmp_path / "default-uni").mkdir(parents=True, exist_ok=True)

        result = json.loads(_extensions_impl(
            action="validate_ship_packet",
            body_json=json.dumps(self._packet()),
            record_in_ledger=True,
            universe_id="../escape-attempt",
            request_id="REQ-BUG-058",
        ))

        assert result["validation_result"] == "blocked"
        assert result["would_open_pr"] is False
        assert result["ship_status"] == "failed"
        assert result.get("ship_attempt_id") is None
        assert any(v["rule_id"] == "ledger_record_failed" for v in result["violations"])
        assert read_attempts(tmp_path / "default-uni") == []

    def test_two_recorded_calls_produce_distinct_ledger_rows(self, tmp_path, monkeypatch):
        """The validator is pure but the wrapper must produce a fresh
        ship_attempt_id on each call so the ledger gives a per-call audit
        trail rather than collapsing identical packets."""
        u = self._setup_universe(tmp_path, monkeypatch)
        from workflow.auto_ship_ledger import read_attempts
        result_a = json.loads(_action_validate_ship_packet({
            "body_json": json.dumps(self._packet()),
            "record_in_ledger": True,
            "request_id": "REQ-A",
        }))
        result_b = json.loads(_action_validate_ship_packet({
            "body_json": json.dumps(self._packet()),
            "record_in_ledger": True,
            "request_id": "REQ-A",  # same request_id intentionally
        }))
        assert result_a["ship_attempt_id"] != result_b["ship_attempt_id"]
        rows = read_attempts(u)
        assert len(rows) == 2
