"""Workflow runs refresh the owner's sign-in before they pin authority.

The founder's background agent runs as a workflow node on codex. Only the served
turn refreshed a deposited subscription document (#4032/#4076), so a workflow
run launched the CLI with whatever was stored, however old
(docs/concerns/2026-09-26-pr4032-refresh-launch-integration.md). Each lane pins
the assignment in a receipt, and a refresh renews the accepted source, which
moves the assignment. So the refresh has to run before that pin: before the
foreground run's single receipt, and at each background node call's entry.

Both tests drive the real lanes over their real stores (the foreground
`run_graph` path and the assigned queue consumer). Only the terminal provider,
the token spend and the issuer metadata are synthetic.
"""

from __future__ import annotations

import base64
import json

from tests import test_background_budget_finalization_e2e as background
from tests import test_run_provider_session as foreground
from tests import test_workflow_http_agent as http_agent
from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401
from tests.test_run_provider_session import _module_local_cloud_admission  # noqa: F401
from tests.test_subscription_credential_refresh import (
    ID_TOKEN,
    _endpoint_from_the_credential,
)
from tinyassets.branch_tasks_v2 import Epoch2BranchTaskAdapter

work_agent = http_agent.work_agent
http_wire = http_agent.http_wire

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


def test_a_background_node_refreshes_at_its_entry_and_still_succeeds(tmp_path, monkeypatch):
    def serving():
        background._seed_serving_assignment(tmp_path)
        _redeposit_stale(tmp_path)

    spent = _rotating_spend(monkeypatch)

    task_id, _audience, _consumer, fake, _states = background._run_consumer_once(
        tmp_path, monkeypatch, setup_serving=serving,
    )

    task = Epoch2BranchTaskAdapter(tmp_path).get(task_id)
    assert task is not None and task.status == "succeeded", task and task.error
    assert spent == ["r-1"]
    assert len(fake.calls) == 1
    assert _stored_refresh_token(tmp_path) == "r-2"
    assert _custody_matches_the_vault(tmp_path)


def test_a_background_agent_node_on_native_codex_refreshes_and_completes(
    tmp_path, monkeypatch, work_agent,
):
    """The founder's own shape: a background workflow agent node on codex."""
    from tests import test_background_work_agent as agent_rig
    from tinyassets.providers.agent_capacity_boundary import NativeCompletionEvidence
    from tinyassets.providers.base import ProviderResponse

    seed = background._seed_serving_assignment

    def seed_then_age(base_path, **kwargs):
        seed(base_path, **kwargs)
        _redeposit_stale(base_path)

    monkeypatch.setattr(background, "_seed_serving_assignment", seed_then_age)
    spent = _rotating_spend(monkeypatch)
    launched: list[str] = []

    async def native(self, prompt, system, config, *, universe_dir=None):
        launched.append(_stored_refresh_token(tmp_path))
        return ProviderResponse(
            text="background native work completed", provider="codex", model="native-default",
            family="codex", latency_ms=1, input_tokens=3, output_tokens=4, cost_microunits=0,
            native_evidence=NativeCompletionEvidence("codex", True, True, "committed"),
        )

    monkeypatch.setattr(background._CountingProvider, "agent_execution_kind", "native_agent",
                        raising=False)
    monkeypatch.setattr(background._CountingProvider, "complete", native)

    task, result = agent_rig.run(tmp_path, monkeypatch, native=True)

    assert task.status == "succeeded", (result, work_agent.errors)
    assert spent == ["r-1"]
    # The launch ran on the ROTATED sign-in, not the stale one.
    assert launched == ["r-2"]
    assert _custody_matches_the_vault(tmp_path)
