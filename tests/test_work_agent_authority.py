"""Fresh step authority against real foreground stores, not tool-execution proof."""

import sqlite3
from contextlib import contextmanager

import pytest

from tests.test_run_provider_session import _branch, _run_branch
from tests.test_work_model_selection import http_wire  # noqa: F401 - pytest fixture
from tinyassets.foreground_run_provider import _ForegroundRunProviderSession
from tinyassets.provider_assignment_manifest import ModelAccess
from tinyassets.providers.base import ModelConfig
from tinyassets.storage.provider_work_authority import db_path


@pytest.mark.parametrize("manifest", [False, True])
@pytest.mark.parametrize("change", [
    None, "closed", "subject", "cancelled", "revoked", "child", "claim", "home", "seal",
])
@pytest.mark.usefixtures("http_wire")
def test_step_rechecks_current_authority_without_new_reservation(
    tmp_path, monkeypatch, authenticate_request, manifest, change,
):
    # Avoid persona/tool transport setup: only admission and its independent
    # between-step fence are in scope. No engine tool is ever executed here.
    monkeypatch.setattr(
        "tinyassets.shared_self.prepare_shared_self_turn",
        lambda base, uid, owner, prompt, config: (prompt, "", ModelConfig()),
    )
    original = _ForegroundRunProviderSession._authorize_attempt
    observations = []

    @contextmanager
    def authorize(session, **kwargs):
        with original(session, **kwargs) as launch:
            carrier = launch[0]
            assert session._check_agent_authority(carrier) == "acct_alice"
            yield launch
            # Provider has settled; read-only step checking remains valid, but
            # must not consume/rearm the already consumed inference carrier.
            assert session._check_agent_authority(carrier) == "acct_alice"
            with sqlite3.connect(db_path(tmp_path)) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM provider_invocation_reservations",
                ).fetchone()
            if change == "closed":
                session._closed = True
            elif change == "subject":
                session._branch_snapshot["node_defs"][0]["prompt_template"] = "changed"
            elif change == "cancelled":
                from tinyassets.runs import request_cancel

                request_cancel(tmp_path, session.bound_run_id)
            elif change in {"revoked", "child", "claim"}:
                with sqlite3.connect(db_path(tmp_path)) as conn:
                    if change == "revoked":
                        conn.execute("UPDATE provider_work_bindings SET state = 'revoked'")
                    elif change == "child":
                        conn.execute("DELETE FROM provider_work_bindings WHERE binding_id = ?",
                                     (carrier.binding_id,))
                    else:
                        conn.execute("DELETE FROM provider_work_execution_claims")
            elif change == "home":
                from tinyassets.daemon_server import set_founder_home

                set_founder_home(tmp_path, founder_sub="acct_alice", universe_id="other",
                                 platform_generated=True)
            elif change == "seal":
                object.__setattr__(carrier, "_seal", b"invalid")
            if change:
                with pytest.raises((PermissionError, ValueError)):
                    session._check_agent_authority(carrier)
            else:
                assert session._check_agent_authority(carrier) == "acct_alice"
                with pytest.raises(PermissionError, match="consumed"):
                    carrier.validate_for_call(role="writer", operation="run_graph")
            with sqlite3.connect(db_path(tmp_path)) as conn:
                assert conn.execute(
                    "SELECT COUNT(*) FROM provider_invocation_reservations",
                ).fetchone() == count
            observations.append(change)

    monkeypatch.setattr(_ForegroundRunProviderSession, "_authorize_attempt", authorize)
    branch = _branch(node_count=1)
    branch.node_defs[0].tools_allowed = ["universe_self"]
    result, _, _ = _run_branch(
        tmp_path, monkeypatch, authenticate_request, branch, open_provider=manifest,
        model_access=ModelAccess("discovered") if manifest else None,
    )
    assert observations == [change], result
