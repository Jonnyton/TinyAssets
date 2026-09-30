"""Workflow runs refresh the owner's sign-in before they pin authority.

Only the served turn refreshed a deposited subscription document (#4032/#4076),
so a workflow run launched the CLI with whatever was stored, however old
(docs/concerns/2026-09-26-pr4032-refresh-launch-integration.md). A run pins the
assignment in its one receipt, and a refresh renews the accepted source, which
moves the assignment. So the refresh has to run before that pin.

The tests drive the real foreground `run_graph` lane over its real stores. Only
the terminal provider, the token spend and the issuer metadata are synthetic.
(The background lane's copies went with the consumer's epoch-2 claim pass in
the fleet prune: nothing can claim a background slice any more.)
"""

from __future__ import annotations

import base64
import json

from tests import test_run_provider_session as foreground
from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401
from tests.test_run_provider_session import _module_local_cloud_admission  # noqa: F401
from tests.test_subscription_credential_refresh import (
    ID_TOKEN,
    _endpoint_from_the_credential,
)

OWNER = "acct_alice"
UID = "universe_alice"


def _stale_document() -> str:
    return base64.b64encode(json.dumps({
        "tokens": {"id_token": ID_TOKEN, "access_token": "a-1", "refresh_token": "r-1"},
        "last_refresh": "2020-01-01T00:00:00Z",
    }).encode("utf-8")).decode("ascii")


def _redeposit_stale(base_path) -> None:
    """The owner's accepted codex sign-in, now older than the refresh window."""
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.daemon_server import grant_universe_access, set_founder_home
    from tinyassets.onboarding.serving import ensure_founder_serving

    set_founder_home(base_path, founder_sub=OWNER, universe_id=UID, platform_generated=True)
    grant_universe_access(
        base_path, universe_id=UID, actor_id=OWNER, permission="admin", granted_by=OWNER,
    )
    write_credential_vault(
        base_path / UID, [{
            "credential_type": "llm_subscription", "service": "codex",
            "auth_json_b64": _stale_document(),
        }], owner_user_id=OWNER, universe_id=UID,
    )
    renewed = ensure_founder_serving(
        base_path=base_path, universe_dir=base_path / UID, owner_user_id=OWNER,
        universe_id=UID, service="codex",
    )
    assert renewed["status"] == "serving", renewed


def _rotating_spend(monkeypatch) -> list[str]:
    from tinyassets import subscription_refresh

    _endpoint_from_the_credential(monkeypatch)
    spent: list[str] = []

    def spend(document, **_):
        spent.append(document.refresh_token)
        return subscription_refresh._rebuild(
            document, access_token="a-2", refresh_token="r-2", id_token="",
        )

    monkeypatch.setattr(subscription_refresh, "_spend", spend)
    return spent


def _custody_matches_the_vault(base_path) -> bool:
    from tinyassets.credential_vault import current_llm_subscription_custody
    from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore

    with SQLiteProviderWorkAuthorityStore(base_path).connection() as conn:
        return current_llm_subscription_custody(
            conn, universe_dir=base_path / UID, owner_user_id=OWNER,
            universe_id=UID, service="codex",
        ) is not None


def _stored_refresh_token(base_path) -> str:
    from tinyassets.credential_vault import load_credential_vault

    record = next(
        r for r in load_credential_vault(base_path / UID)
        if r.get("credential_type") == "llm_subscription"
    )
    return json.loads(base64.b64decode(record["auth_json_b64"]))["tokens"]["refresh_token"]


def test_a_foreground_run_refreshes_before_its_receipt_and_still_completes(
    tmp_path, monkeypatch, authenticate_request,
):
    seed = foreground._seed_serving_assignment

    def seed_then_age(base_path, **kwargs):
        seed(base_path, **kwargs)
        _redeposit_stale(base_path)

    monkeypatch.setattr(foreground, "_seed_serving_assignment", seed_then_age)
    spent = _rotating_spend(monkeypatch)

    response, provider, _ = foreground._run_branch(
        tmp_path, monkeypatch, authenticate_request, foreground._branch(node_count=2),
    )

    assert response["terminal_status"] == "completed", response["terminal_error"]
    # Once for the run, before its one receipt -- not once per node.
    assert spent == ["r-1"]
    assert len(provider.calls) == 2
    assert _stored_refresh_token(tmp_path) == "r-2"
    assert _custody_matches_the_vault(tmp_path)


def _counting_refresh(monkeypatch) -> list[str]:
    """Count calls to the REAL refresh; a spend count cannot see a no-op call."""
    from tinyassets import subscription_refresh

    real = subscription_refresh.refresh_deposited_subscriptions
    calls: list[str] = []

    def counted(**kwargs):
        calls.append(kwargs["owner_user_id"])
        return real(**kwargs)

    monkeypatch.setattr(subscription_refresh, "refresh_deposited_subscriptions", counted)
    return calls


def test_another_users_public_branch_never_refreshes_the_requesters_sign_in(
    tmp_path, monkeypatch, authenticate_request,
):
    """Refused by admission as not the principal's Branch -- and refused before any
    spend or renewal of the requester's credential."""
    seed = foreground._seed_serving_assignment

    def seed_then_age(base_path, **kwargs):
        seed(base_path, **kwargs)
        _redeposit_stale(base_path)

    monkeypatch.setattr(foreground, "_seed_serving_assignment", seed_then_age)
    spent = _rotating_spend(monkeypatch)
    calls = _counting_refresh(monkeypatch)
    branch = foreground._branch(node_count=1, author="acct_bob")
    branch.visibility = "public"

    response, provider, _ = foreground._run_branch(
        tmp_path, monkeypatch, authenticate_request, branch,
    )

    assert response["terminal_status"] == "failed"
    assert provider.calls == []
    assert calls == [] and spent == []
    assert _stored_refresh_token(tmp_path) == "r-1"


def test_an_async_sub_branch_that_runs_first_refreshes_for_itself(
    tmp_path, monkeypatch, authenticate_request,
):
    """A child session may launch before its parent has made any provider call.

    A flag copied from the parent (which had refreshed nothing yet) launched the
    child on the stale sign-in (Codex round 2 on #4082). The child is minted by
    the real sibling path from a parent session that has not been admitted.
    """
    from tinyassets.daemon_server import save_branch_definition
    from tinyassets.foreground_run_provider import (
        _session_from_provider_call,
        prepare_foreground_run_provider,
    )
    from tinyassets.runs import create_run, update_run_status

    seed = foreground._seed_serving_assignment

    def seed_then_age(base_path, **kwargs):
        seed(base_path, **kwargs)
        _redeposit_stale(base_path)

    monkeypatch.setattr(foreground, "_seed_serving_assignment", seed_then_age)
    spent = _rotating_spend(monkeypatch)
    calls = _counting_refresh(monkeypatch)
    _, _, captured = foreground._run_branch(
        tmp_path, monkeypatch, authenticate_request, foreground._branch(node_count=1),
    )
    parent = _session_from_provider_call(captured["provider_call"])
    # The parent as a child would find it: bound to its run, nothing refreshed.
    parent._sign_ins_refreshed = False
    calls.clear()
    spent.clear()
    _redeposit_stale(tmp_path)

    child_branch = foreground._branch(node_count=1)
    save_branch_definition(tmp_path, branch_def=child_branch.to_dict())
    child_run_id = create_run(
        tmp_path, branch_def_id=child_branch.branch_def_id, thread_id="thread-child",
        inputs={}, actor=f"universe:{UID}",
    )
    update_run_status(tmp_path, child_run_id, status="running")
    child = _session_from_provider_call(prepare_foreground_run_provider(
        captured["provider_call"], run_id=child_run_id, branch=child_branch,
        branch_version_id=None, allowed_statuses={"running", "queued"},
    ))
    assert child is not parent
    child._refresh_sign_ins()

    assert calls == [OWNER]
    assert spent == ["r-1"]
    assert _stored_refresh_token(tmp_path) == "r-2"
    assert _custody_matches_the_vault(tmp_path)
