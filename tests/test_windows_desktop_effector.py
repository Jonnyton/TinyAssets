"""PR-131 host-local Windows desktop effect adapter tests."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

from workflow.branches import NodeDefinition
from workflow.effectors import (
    EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME,
    run_effects_for_branch,
    run_windows_desktop_effector,
)
from workflow.storage.effector_consents import grant_consent
from workflow.storage.external_write_receipts import (
    STATUS_SUCCEEDED,
    lookup_receipt,
    record_receipt,
)


def _packet(**overrides):
    packet = {
        "schema": "workflow.external_effect_packet.v1",
        "effect_type": EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME,
        "strict_contract": "tiberian_sun_host_local_effect_packet_v2",
        "idempotency_key": (
            "14e46ebb6edda941255a98dc7f82cf6f15a58bc10198536ac9d00b37fe985fef"
        ),
        "lawful_source_url": (
            "https://downloads.cnc-comm.com/tiberian-sun/tsins/TSinstaller.exe"
        ),
        "source_filename": "TSinstaller.exe",
        "user_approval": (
            "I approve downloading Tiberian Sun on the local desktop host."
        ),
        "requested_actions": ["download", "hash", "launch_installer"],
        "asset_policy": {
            "host_local_only": True,
            "public_artifacts": ["source_url", "sha256", "redacted_evidence_handles"],
        },
    }
    packet.update(overrides)
    return packet


def test_windows_packet_without_user_approval_refuses_before_side_effects(tmp_path):
    runner = Mock()
    result = run_windows_desktop_effector(
        node_id="emit",
        output_keys=["effect_packet"],
        run_state={"effect_packet": _packet(user_approval="")},
        base_path=tmp_path,
        run_id="run-approval",
        action_runner=runner,
    )

    runner.assert_not_called()
    assert result["error_kind"] == "approval_required"
    assert result["phase"] == "phase_2"


def test_windows_packet_negative_approval_text_refuses_before_side_effects(tmp_path):
    runner = Mock()
    result = run_windows_desktop_effector(
        node_id="emit",
        output_keys=["effect_packet"],
        run_state={"effect_packet": _packet(user_approval="I do not approve this.")},
        base_path=tmp_path,
        run_id="run-denied",
        action_runner=runner,
    )

    runner.assert_not_called()
    assert result["error_kind"] == "approval_required"


def test_windows_packet_without_consent_refuses_before_side_effects(tmp_path):
    runner = Mock()
    result = run_windows_desktop_effector(
        node_id="emit",
        output_keys=["effect_packet"],
        run_state={"effect_packet": _packet()},
        base_path=tmp_path,
        run_id="run-consent",
        action_runner=runner,
    )

    runner.assert_not_called()
    assert result["dry_run"] is True
    assert result["reason"] == "missing_consent"
    assert result["destination"] == "host-local/windows-desktop"


def test_windows_packet_on_non_windows_returns_no_host_before_receipt(tmp_path):
    grant_consent(
        tmp_path,
        sink=EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME,
        destination="host-local/windows-desktop",
        granted_by="tester",
    )
    runner = Mock()
    # Inject a non-Windows runtime attestation explicitly so the test is
    # deterministic on every host. Without it the effector calls
    # attest_windows_desktop_runtime() and reads the real environment — on a
    # Windows dev box that attests os_name='nt', the no_host_available guard
    # never fires, and the Mock runner is invoked (then its non-serializable
    # result blows up receipt finalization). The subject under test is the
    # "wrong runtime refuses before any side effect" contract, not the
    # host-detection heuristic, so a posix attestation is the right fixture.
    result = run_windows_desktop_effector(
        node_id="emit",
        output_keys=["effect_packet"],
        run_state={"effect_packet": _packet()},
        base_path=tmp_path,
        run_id="run-posix",
        runtime_attestation={
            "os_name": "posix",
            "desktop_user_profile_present": False,
            "interactive_session": False,
            "container": False,
        },
        action_runner=runner,
    )

    runner.assert_not_called()
    assert result["error_kind"] == "no_host_available"
    assert result["reason"] == "BLOCKED_WRONG_RUNTIME"
    assert result["runtime_attestation"]["os_name"] != "nt"
    assert lookup_receipt(
        tmp_path,
        idempotency_hint=_packet()["idempotency_key"],
        sink=EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME,
    ) is None


def test_windows_packet_dedup_hit_returns_recorded_evidence(tmp_path):
    evidence = {
        "phase": "phase_2",
        "actions_completed": ["download", "hash", "launch_installer"],
        "sha256": "abc123",
    }
    record_receipt(
        tmp_path,
        idempotency_hint=_packet()["idempotency_key"],
        sink=EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME,
        evidence=evidence,
        run_id="previous",
        status=STATUS_SUCCEEDED,
    )
    grant_consent(
        tmp_path,
        sink=EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME,
        destination="host-local/windows-desktop",
        granted_by="tester",
    )
    result = run_windows_desktop_effector(
        node_id="emit",
        output_keys=["effect_packet"],
        run_state={"effect_packet": _packet()},
        base_path=tmp_path,
        run_id="run-dedup",
        runtime_attestation={
            "os_name": "nt",
            "desktop_user_profile_present": True,
            "interactive_session": True,
            "container": False,
        },
        action_runner=Mock(),
    )

    assert result["idempotency_dedup_hit"] is True
    assert result["evidence"] == evidence
    assert result["recorded_run_id"] == "previous"


def test_windows_packet_success_reserves_then_finalizes_redacted_receipt(tmp_path):
    grant_consent(
        tmp_path,
        sink=EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME,
        destination="host-local/windows-desktop",
        granted_by="tester",
    )

    def runner(*, packet, runtime_attestation, run_id):
        assert packet["source_filename"] == "TSinstaller.exe"
        assert runtime_attestation["os_name"] == "nt"
        assert run_id == "run-ok"
        return {
            "actions_completed": ["download", "hash", "launch_installer"],
            "download_receipt": {"path_handle": "local-path:deadbeef"},
            "sha256": "a" * 64,
            "installer_launch_receipt": {"pid": 4242},
            "private_path": r"C:\\Users\\Alice\\Desktop\\TSinstaller.exe",
        }

    result = run_windows_desktop_effector(
        node_id="emit",
        output_keys=["effect_packet"],
        run_state={"effect_packet": json.dumps(_packet())},
        base_path=tmp_path,
        run_id="run-ok",
        runtime_attestation={
            "os_name": "nt",
            "desktop_user_profile_present": True,
            "interactive_session": True,
            "container": False,
        },
        action_runner=runner,
    )

    assert result["phase"] == "phase_2"
    assert result["actions_completed"] == ["download", "hash", "launch_installer"]
    assert "private_path" not in result
    blob = json.dumps(result)
    assert "Alice" not in blob

    receipt = lookup_receipt(
        tmp_path,
        idempotency_hint=_packet()["idempotency_key"],
        sink=EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME,
    )
    assert receipt is not None
    assert receipt["status"] == STATUS_SUCCEEDED
    assert "private_path" not in receipt["evidence"]


def test_branch_dispatch_routes_windows_desktop_sink(tmp_path):
    branch = SimpleNamespace(
        node_defs=[
            NodeDefinition(
                node_id="emit",
                display_name="Emit",
                output_keys=["effect_packet"],
                effects=[EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME],
            ),
        ],
    )

    ev_map = run_effects_for_branch(
        branch=branch,
        run_state={"effect_packet": _packet(user_approval="")},
        base_path=tmp_path,
        run_id="run-dispatch",
    )

    ev = ev_map["emit"][EXTERNAL_WRITE_SINK_WINDOWS_DESKTOP_CLASSIC_GAME]
    assert ev["error_kind"] == "approval_required"
