"""A same-account rotation carries custody forward; nothing in flight is voided.

The founder's always-on background agent wakes about once a minute, and a
renewal republished the agent revision, the assignment, every member binding
and the custody reference -- voiding every receipt in flight at each 12-hour
rotation (docs/concerns/2026-09-28-a-renewal-voids-other-running-receipts.md).
openspec/changes/carry-custody-across-rotation. Real stores, real refresh core;
only the token spend and issuer metadata are synthetic.
"""

from __future__ import annotations

import base64
import json
import sqlite3

import pytest

from tests import test_run_provider_session as foreground
from tests import test_served_refresh_renews_binding as served_refresh
from tests.test_run_provider_session import _module_local_cloud_admission  # noqa: F401
from tests.test_subscription_credential_refresh import (
    ID_TOKEN,
    _endpoint_from_the_credential,
    _jwt,
)
from tests.test_workflow_lanes_refresh import (
    _redeposit_stale as _redeposit_stale_alice,
)

_custody_matches_the_vault = served_refresh._custody_matches_the_vault
_redeposit_stale = served_refresh._redeposit_stale
rig = served_refresh.rig
reader = served_refresh.reader
configured = served_refresh.configured
served = served_refresh.served
agent = served_refresh.agent


def _authority_state(base):
    from tinyassets.storage.provider_work_authority import db_path

    conn = sqlite3.connect(db_path(base))
    conn.row_factory = sqlite3.Row
    try:
        return {
            "assignment": dict(conn.execute("SELECT * FROM provider_assignments").fetchone()),
            "bindings": sorted(
                (r["binding_id"], r["generation"], r["binding_digest"])
                for r in conn.execute("SELECT * FROM provider_work_bindings")
            ),
            "agents": sorted(
                (r["agent_binding_id"], r["revision"])
                for r in conn.execute("SELECT * FROM agent_bindings")
            ),
            "custody": sorted(
                (r["service"], r["reference_id"], r["generation"], r["reference_digest"],
                 r["record_digest"])
                for r in conn.execute("SELECT * FROM llm_credential_custody")
            ),
        }
    finally:
        conn.close()


def _codex(state):
    return next(c for c in state["custody"] if c[0] == "codex")


def _spend_as(monkeypatch, *, id_token: str = ""):
    from tinyassets import subscription_refresh

    _endpoint_from_the_credential(monkeypatch)
    spent: list[str] = []

    def spend(document, **_):
        spent.append(document.refresh_token)
        return subscription_refresh._rebuild(
            document, access_token="a-2", refresh_token="r-2", id_token=id_token,
        )

    monkeypatch.setattr(subscription_refresh, "_spend", spend)
    return spent


def _refresh(agent):
    from tinyassets import subscription_refresh

    subscription_refresh.refresh_deposited_subscriptions(
        base_path=agent.served.rig.base, universe_dir=agent.served.context.universe_dir,
        owner_user_id="owner", universe_id="u-models",
    )


@pytest.mark.parametrize("configured", ["mixed"], indirect=True)
def test_a_same_account_rotation_moves_only_the_byte_pin(agent, monkeypatch):
    from tinyassets import subscription_refresh

    _redeposit_stale(agent)
    before = _authority_state(agent.served.rig.base)
    spent = _spend_as(monkeypatch)
    real_renew = subscription_refresh.renew_accepted_source
    renewed: list[str] = []
    monkeypatch.setattr(
        subscription_refresh, "renew_accepted_source",
        lambda **kwargs: renewed.append(kwargs["service"]) or real_renew(**kwargs),
    )

    _refresh(agent)

    # A carried rotation is not a renewal: nothing republished, nothing asked.
    assert renewed == []

    after = _authority_state(agent.served.rig.base)
    assert spent == ["r-1"]
    assert _custody_matches_the_vault(agent)
    for key in ("assignment", "bindings", "agents"):
        assert after[key] == before[key], key
    assert _codex(after)[:4] == _codex(before)[:4], "reference and generation are the consent"
    assert _codex(after)[4] != _codex(before)[4], "the byte pin follows the bytes"


@pytest.mark.parametrize("configured", ["mixed"], indirect=True)
def test_a_rotation_naming_another_account_renews(agent, monkeypatch):
    _redeposit_stale(agent)
    before = _authority_state(agent.served.rig.base)
    other = _jwt({"iss": "https://sign-in.example.net", "client_id": "client-1",
                  "sub": "another-account"})
    _spend_as(monkeypatch, id_token=other)

    _refresh(agent)

    after = _authority_state(agent.served.rig.base)
    assert _custody_matches_the_vault(agent)
    assert after["assignment"]["generation"] == before["assignment"]["generation"] + 1
    assert _codex(after)[2] == _codex(before)[2] + 1


@pytest.mark.parametrize("configured", ["mixed"], indirect=True)
def test_a_legacy_v1_custody_row_renews_then_carries(agent, monkeypatch):
    """A v1 reference hashes the bytes in, so it cannot carry: its first rotation
    renews (writing v2), and the NEXT rotation carries."""
    from tinyassets import subscription_refresh
    from tinyassets.credential_vault import _custody_reference_digest
    from tinyassets.storage.provider_work_authority import db_path

    _redeposit_stale(agent)
    # Leave the row exactly as the deployed code wrote it: the v1 formula. Reads
    # accept it, which the served turn relies on for every existing universe.
    with sqlite3.connect(db_path(agent.served.rig.base)) as conn:
        ref, owner, uid, service, gen, record = conn.execute(
            "SELECT reference_id, owner_user_id, universe_id, service, generation, "
            "record_digest FROM llm_credential_custody WHERE service = 'codex'"
        ).fetchone()
        conn.execute(
            "UPDATE llm_credential_custody SET reference_digest = ? WHERE reference_id = ?",
            (_custody_reference_digest(reference_id=ref, owner_user_id=owner,
                                       universe_id=uid, service=service,
                                       generation=gen, record_digest=record), ref),
        )
    before = _authority_state(agent.served.rig.base)
    _spend_as(monkeypatch)

    _refresh(agent)

    renewed = _authority_state(agent.served.rig.base)
    assert _codex(renewed)[2] == _codex(before)[2] + 1
    assert _custody_matches_the_vault(agent)

    monkeypatch.setattr(subscription_refresh, "document_is_stale", lambda *_a: True)
    _refresh(agent)

    carried = _authority_state(agent.served.rig.base)
    assert carried["assignment"] == renewed["assignment"]
    assert _codex(carried)[:4] == _codex(renewed)[:4]
    assert _custody_matches_the_vault(agent)


@pytest.mark.parametrize("configured", ["mixed"], indirect=True)
def test_bytes_nobody_pinned_are_still_refused(agent):
    """The reference no longer covers the bytes; the pin still does."""
    from tinyassets.credential_vault import (
        current_llm_subscription_custody,
        write_credential_vault,
    )
    from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore

    _redeposit_stale(agent)
    write_credential_vault(
        agent.served.context.universe_dir, [{
            "credential_type": "llm_subscription", "service": "codex",
            "auth_json_b64": base64.b64encode(json.dumps({"tokens": {
                "id_token": ID_TOKEN, "access_token": "x", "refresh_token": "y",
            }}).encode()).decode(),
        }], owner_user_id="owner", universe_id="u-models",
    )
    store = SQLiteProviderWorkAuthorityStore(agent.served.rig.base)
    with store.connection() as conn:
        assert current_llm_subscription_custody(
            conn, universe_dir=agent.served.context.universe_dir, owner_user_id="owner",
            universe_id="u-models", service="codex",
        ) is None


@pytest.mark.parametrize("configured", ["mixed"], indirect=True)
def test_a_launch_copy_that_differs_from_the_pin_is_refused(agent, monkeypatch):
    """After the copy, the copied BYTES are compared with the pin. The v2
    reference does not cover the bytes, so a reference check alone would pass."""
    from tinyassets import credential_vault
    from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore

    _redeposit_stale(agent)
    with SQLiteProviderWorkAuthorityStore(agent.served.rig.base).connection() as conn:
        custody = credential_vault.current_llm_subscription_custody(
            conn, universe_dir=agent.served.context.universe_dir, owner_user_id="owner",
            universe_id="u-models", service="codex",
        )
    assert custody is not None
    real_write = credential_vault._write_exclusive_snapshot_file

    def corrupt(path, contents):
        real_write(path, contents + b" " if path.name == "auth.json" else contents)

    monkeypatch.setattr(credential_vault, "_write_exclusive_snapshot_file", corrupt)
    with pytest.raises(PermissionError, match="custody digest disagrees"):
        credential_vault.snapshot_llm_subscription_credential(
            universe_dir=agent.served.context.universe_dir, custody=custody,
        )


def test_a_foreground_run_survives_a_rotation_between_its_nodes(
    tmp_path, monkeypatch, authenticate_request,
):
    """The receipt in flight: another session rotates the sign-in after node 1;
    node 2 still launches on the SAME receipt, on the rotated bytes."""
    from tinyassets import subscription_refresh

    seed = foreground._seed_serving_assignment

    def seed_then_age(base_path, **kwargs):
        seed(base_path, **kwargs)
        _redeposit_stale_alice(base_path)

    monkeypatch.setattr(foreground, "_seed_serving_assignment", seed_then_age)
    spent = _spend_as(monkeypatch)
    # The run's own first-node refresh finds nothing stale; the rotation comes
    # from ANOTHER session, between the run's two nodes.
    real_stale = subscription_refresh.document_is_stale
    armed = {"now": False}
    monkeypatch.setattr(
        subscription_refresh, "document_is_stale",
        lambda document, now: armed["now"] and real_stale(document, now),
    )

    def rotate_between_nodes(_name, count):
        if count == 1:
            armed["now"] = True
            subscription_refresh.refresh_deposited_subscriptions(
                base_path=tmp_path, universe_dir=tmp_path / "universe_alice",
                owner_user_id="acct_alice", universe_id="universe_alice",
            )
            armed["now"] = False

    response, provider, _ = foreground._run_branch(
        tmp_path, monkeypatch, authenticate_request, foreground._branch(node_count=2),
        after_provider_call=rotate_between_nodes,
    )

    assert spent == ["r-1"], "the other session's rotation did not happen"
    assert response["terminal_status"] == "completed", response["terminal_error"]
    assert len(provider.calls) == 2


def test_a_background_attempt_survives_a_rotation_between_its_nodes(tmp_path, monkeypatch):
    """The founder's always-on agent: its attempt's one receipt spans a rotation
    another session makes between two nodes, and the attempt still succeeds."""
    from tests import test_background_budget_finalization_e2e as background
    from tinyassets import subscription_refresh
    from tinyassets.branch_tasks_v2 import Epoch2BranchTaskAdapter

    def serving():
        background._seed_serving_assignment(tmp_path)
        _redeposit_stale_alice(tmp_path)

    spent = _spend_as(monkeypatch)
    real_stale = subscription_refresh.document_is_stale
    armed = {"now": False}
    monkeypatch.setattr(
        subscription_refresh, "document_is_stale",
        lambda document, now: armed["now"] and real_stale(document, now),
    )
    real_complete = background._CountingProvider.complete
    launches = {"n": 0}

    async def complete(self, *args, **kwargs):
        response = await real_complete(self, *args, **kwargs)
        launches["n"] += 1
        if launches["n"] == 1:
            armed["now"] = True
            subscription_refresh.refresh_deposited_subscriptions(
                base_path=tmp_path, universe_dir=tmp_path / "universe_alice",
                owner_user_id="acct_alice", universe_id="universe_alice",
            )
            armed["now"] = False
        return response

    monkeypatch.setattr(background._CountingProvider, "complete", complete)

    task_id, _audience, _consumer, _fake, _states = background._run_consumer_once(
        tmp_path, monkeypatch, setup_serving=serving, policy=[None, None],
    )

    task = Epoch2BranchTaskAdapter(tmp_path).get(task_id)
    assert spent == ["r-1"], "the other session's rotation did not happen"
    assert task is not None and task.status == "succeeded", task and task.error
    assert launches["n"] == 2
