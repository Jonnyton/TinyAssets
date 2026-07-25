from __future__ import annotations

import inspect

import pytest

from tinyassets.effectors.outbound_boundary import (
    confirm_held_effect,
    execute_capped_action,
)
from tinyassets.storage.external_write_receipts import (
    STATUS_HELD,
    lookup_receipt,
)
from tinyassets.storage.outbound_connections import (
    ActionCap,
    ConnectionLedger,
)


def _ledger_with_cap(tmp_path) -> tuple[ConnectionLedger, object]:
    ledger = ConnectionLedger(tmp_path / "boundary.db")
    ledger.create_connection(
        connection_id="conn-1",
        owner_user_id="user-1",
        connection_class="issue-writer",
        scopes=("issues:write",),
        provider="github",
        destination="github.com/acme/widgets",
        credential_ref="vault://github/user-1",
    )
    ledger.grant_connection(
        grant_id="grant-1",
        connection_id="conn-1",
        owner_user_id="user-1",
        universe_id="universe-1",
        unprompted_action_cap=ActionCap(
            name="issues-per-action",
            maximum=2,
            unit="issues",
        ),
    )
    calls: list[object] = []
    proxy = ledger.resolve_scoped_proxy(
        owner_user_id="user-1",
        universe_id="universe-1",
        connection_class="issue-writer",
        dispatch=lambda _grant, _verb, request: calls.append(request)
        or {"issue_id": 17},
    )
    return ledger, (proxy, calls)


def test_unprompted_cap_is_machine_readable_and_a_separate_authority_axis(tmp_path):
    ledger, _ = _ledger_with_cap(tmp_path)

    decision = ledger.evaluate_unprompted_action_cap(
        grant_id="grant-1",
        action_value=3,
    )

    assert decision.as_dict() == {
        "status": "held",
        "cap": {
            "name": "issues-per-action",
            "maximum": 2,
            "unit": "issues",
        },
        "action_value": 3,
        "authorization_axis": "unprompted_action",
    }
    parameters = inspect.signature(
        ledger.evaluate_unprompted_action_cap
    ).parameters
    assert "tool_authorized" not in parameters
    assert "spend_cap" not in parameters


def test_above_cap_holds_without_execution_or_consumption_until_confirmation(
    tmp_path,
):
    ledger, (proxy, calls) = _ledger_with_cap(tmp_path)
    universe = tmp_path / "universe"

    held = execute_capped_action(
        universe_dir=universe,
        ledger=ledger,
        grant_id="grant-1",
        proxy=proxy,
        tool_authorized=True,
        action_value=3,
        effect_key="effect-1",
        sink="github_issue",
        run_id="run-1",
        verb="issues:write",
        request={"title": "Needs confirmation"},
    )

    assert held["status"] == "held"
    assert held["cap"]["name"] == "issues-per-action"
    assert held["consumption"] == {"funds": 0, "quota": 0}
    assert held["remediation"] == {
        "action": "confirm_held_effect",
        "effect_key": "effect-1",
        "message": "Confirm this effect to exceed cap 'issues-per-action'.",
    }
    assert calls == []
    receipt = lookup_receipt(
        universe,
        idempotency_hint="effect-1",
        sink="github_issue",
    )
    assert receipt is not None
    assert receipt["status"] == STATUS_HELD

    confirm_held_effect(
        universe_dir=universe,
        effect_key="effect-1",
        sink="github_issue",
        authorized_by="user-1",
    )
    executed = execute_capped_action(
        universe_dir=universe,
        ledger=ledger,
        grant_id="grant-1",
        proxy=proxy,
        tool_authorized=True,
        action_value=3,
        effect_key="effect-1",
        sink="github_issue",
        run_id="run-2",
        verb="issues:write",
        request={"title": "Needs confirmation"},
    )
    assert executed["status"] == "executed"
    assert calls == [{"title": "Needs confirmation"}]


def test_same_action_at_cap_executes_without_hold(tmp_path):
    ledger, (proxy, calls) = _ledger_with_cap(tmp_path)

    result = execute_capped_action(
        universe_dir=tmp_path / "universe",
        ledger=ledger,
        grant_id="grant-1",
        proxy=proxy,
        tool_authorized=True,
        action_value=2,
        effect_key="effect-at-cap",
        sink="github_issue",
        run_id="run-1",
        verb="issues:write",
        request={"title": "At cap"},
    )

    assert result["status"] == "executed"
    assert calls == [{"title": "At cap"}]


def test_tool_authorization_denial_is_not_overridden_by_cap(tmp_path):
    ledger, (proxy, calls) = _ledger_with_cap(tmp_path)

    with pytest.raises(PermissionError, match="tool authorization"):
        execute_capped_action(
            universe_dir=tmp_path / "universe",
            ledger=ledger,
            grant_id="grant-1",
            proxy=proxy,
            tool_authorized=False,
            action_value=1,
            effect_key="effect-denied",
            sink="github_issue",
            run_id="run-1",
            verb="issues:write",
            request={"title": "Denied"},
        )
    assert calls == []
