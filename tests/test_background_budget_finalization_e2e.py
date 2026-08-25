"""END-TO-END finalization proof for the background budget path (Codex REJECT #2, #2528).

Composes the production-faithful cloud-automation harness from
``tests/test_cloud_automation_continuation.py`` (real activation store, real background
binding, a REAL provider-work binding row via ``install_test_binding``, real
``commit_admission``, the real attempt-issuance service, the real Epoch-2 claim
adapter) with the served-side seeding from ``tests/test_provider_served_router.py``
(``write_credential_vault`` -> ``publish_definition`` -> ``create_binding`` ->
``bind_serving_provider`` -> ``set_serving``, which is what makes
``reserve_served_provider_budget``'s assignment + custody gates pass), then drives ONE
background call through the REAL ``ProviderRouter`` and asserts the router
reserved-before-launch and FINALIZED the call's actual usage for the
``budget_owner="background_attempt"`` attempt.

No SimpleNamespace stubs, no in-memory hand-DDL: the whole schema comes up through
the real boot bring-up (``initialize_author_server``). Three monkeypatches, all
named honestly: ``_branch_roles`` (a roles lookup on ``branch_versions``, unrelated
to budget) and the ``datetime`` of both ``background_served_provider`` and
``storage.provider_work_authority`` frozen to the harness ``NOW`` (the rows are
anchored at 2026-08-01; this aligns the clocks, it does not bypass a budget gate).
It proves the reserve->finalize persistence of ``ProviderResponse`` usage for a
background attempt - NOT that a production adapter obeys ``max_tokens`` (Codex #6,
tracked separately).

This PASSES against the real stores: it is the finalization proof for Codex REJECT #2
(and re-proves #1). The seams it walked to get here — each a real store the production
path touches — are listed in the draft PR body, along with the two real bugs it found
(the ``agent_binding_id`` key mismatch; the hard-coded ``converse`` reserve gate).
"""

from __future__ import annotations

from pathlib import Path

OWNER = "acct_alice"
UNIVERSE = "universe_alice"


def _seed_served_side(base: Path) -> None:
    """The exact public calls a universe makes to get a 'ready' served assignment
    (which reserve_served_provider_budget validates) on the SAME owner/universe the
    continuation harness uses."""
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.custom_agents import create_binding, publish_definition
    from tinyassets.provider_serving_binding import bind_serving_provider, set_serving

    universe_dir = base / UNIVERSE
    universe_dir.mkdir(parents=True, exist_ok=True)
    write_credential_vault(
        universe_dir,
        [{"credential_type": "llm_subscription", "service": "codex", "auth_json_b64": "e30="}],
        owner_user_id=OWNER,
        universe_id=UNIVERSE,
    )
    definition = publish_definition(
        base,
        author_id=OWNER,
        payload={
            "schema_version": 1,
            "name": "Served",
            "description": "budget e2e fixture",
            "tags": ["test"],
            "components": {"identity": {"kind": "soul", "config": {}}},
        },
    )
    agent = create_binding(
        base,
        universe_id=UNIVERSE,
        definition_id=definition["agent_definition_id"],
        created_by=OWNER,
        payload={
            "schema_version": 1,
            "name": "served binding",
            "role": "operator",
            "goals": [],
            "components": {},
        },
    )
    connected = bind_serving_provider(
        base_path=base,
        universe_dir=universe_dir,
        owner_user_id=OWNER,
        universe_id=UNIVERSE,
        agent_binding_id=agent["agent_binding_id"],
        expected_revision=1,
        provider="codex",
    )
    set_serving(
        base_path=base,
        universe_dir=universe_dir,
        owner_user_id=OWNER,
        universe_id=UNIVERSE,
        agent_binding_id=agent["agent_binding_id"],
        expected_revision=connected["agent_binding"]["revision"],
        enabled=True,
    )


def test_background_call_reserves_and_finalizes_actual_usage_end_to_end(
    tmp_path: Path, monkeypatch
) -> None:
    import asyncio
    import sqlite3

    import tinyassets.background_served_provider as background_provider
    from tests.test_cloud_automation_continuation import (
        BRANCH_TASK_ID,
        NOW,
        _claimable_cloud_path,
    )
    from tinyassets.background_branch_authority_service import (
        BackgroundBranchAttemptFence,
        BackgroundBranchAuthorityOwnerKind,
        BackgroundBranchAuthorityOwnerRecord,
        BackgroundBranchAuthorityOwnerState,
        BackgroundBranchBindingFence,
    )
    from tinyassets.branch_tasks_v2 import AssignedConsumerLease, Epoch2BranchTaskAdapter
    from tinyassets.providers.base import BaseProvider, ModelConfig, ProviderResponse
    from tinyassets.providers.router import ProviderRouter
    from tinyassets.storage import db_path

    base = tmp_path
    # The ENTIRE production-faithful chain in one call (self-initializing): real daemon
    # + runtime + queue descriptor, activation store, background binding, a real
    # provider-work binding row, prepare -> activate -> claimable commit_admission ->
    # real attempt-issuance service -> real Epoch-2 claim. Returns the live claim.
    fixture, continuation, admission, audience, attempt, claimed_request = (
        _claimable_cloud_path(base)
    )
    binding = fixture[3].get_binding(fixture[1].background_binding_id)
    assert binding is not None
    # QUEUE_TASK owner fenced to the exact binding + attempt. FINDING: no production
    # code path mints this owner today (insert_owner is only ever called from the store
    # tests), so the consumer's owner gate is currently unsatisfiable in prod. Seeded
    # here as a REAL row (PENDING is the only valid QUEUE_TASK state); the prod minting
    # is a separate gap to close.
    fixture[3].insert_owner(BackgroundBranchAuthorityOwnerRecord(
        owner_kind=BackgroundBranchAuthorityOwnerKind.QUEUE_TASK,
        owner_id=BRANCH_TASK_ID,
        universe_id=UNIVERSE,
        authorizing_principal_id=OWNER,
        source_generation=attempt.source_generation,
        transition_generation=1,
        state=BackgroundBranchAuthorityOwnerState.PENDING,
        binding=BackgroundBranchBindingFence(binding),
        attempt=BackgroundBranchAttemptFence(attempt),
        hold_reason=None,
        updated_at=NOW.isoformat().replace("+00:00", "Z"),
    ))
    # The consumer's session needs the Epoch2BranchTask row (claimed_by set by the
    # real claim above) and a lease whose consumer_id IS that claimant.
    claimed = Epoch2BranchTaskAdapter(base, clock=lambda: NOW).get(BRANCH_TASK_ID)
    assert claimed is not None and claimed.claimed_by == claimed_request.claimed_by
    lease = AssignedConsumerLease(
        consumer_id=claimed.claimed_by,
        lease_id="assigned-lease:e2e",
        expires_at="2099-01-01T01:00:00+00:00",
    )

    # --- served side: makes reserve_served_provider_budget's gates pass -----------
    _seed_served_side(base)
    monkeypatch.setattr(background_provider, "_branch_roles", lambda *_a: ("writer",))
    # The harness pins every lease/claim to NOW (2026-08-01); the consumer compares
    # them against a hard datetime.now(). Freeze the consumer's clock to the SAME
    # instant the rows were written under — faithful, not a future-dated fake lease.
    from datetime import datetime as _real_datetime

    class _FrozenDatetime(_real_datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is None else NOW.astimezone(tz)

    monkeypatch.setattr(background_provider, "datetime", _FrozenDatetime)
    # The reserve gate constructs its OWN SQLiteProviderWorkAuthorityStore with the
    # default wall clock and checks the background binding's expires_at (NOW+30m in
    # harness time) against it — freeze that module's clock to NOW as well. Pure
    # test-clock artifact: real bindings carry real future expiries.
    import tinyassets.storage.provider_work_authority as _pwa_module

    monkeypatch.setattr(_pwa_module, "datetime", _FrozenDatetime)

    # --- the real router with a counting fake provider --------------------------
    class _CountingProvider(BaseProvider):
        def __init__(self) -> None:
            self.name = "codex"
            self.family = "codex"
            self.calls = 0

        async def complete(self, prompt, system, config: ModelConfig, *, universe_dir=None):
            self.calls += 1
            return ProviderResponse(
                text="routed-ok", provider="codex", model="fake", family="codex",
                latency_ms=0.0, input_tokens=700, output_tokens=300, cost_microunits=50,
            )

    fake = _CountingProvider()
    router = ProviderRouter({"codex": fake})

    def through_real_router(prompt, system, *, role, config, **kwargs):
        return asyncio.run(router.call(
            role, prompt, system, operation=kwargs["operation"],
            universe_context=kwargs["universe_context"],
        )).text

    session = background_provider._BackgroundAssignedProviderSession(
        base, claimed, lease, through_real_router
    )
    assert session("first") == "routed-ok"
    assert fake.calls == 1  # REJECT #1: the real background path launched.

    conn = sqlite3.connect(db_path(base))
    conn.row_factory = sqlite3.Row
    served_rows = conn.execute(
        "SELECT state, actual_total_tokens, actual_cost_microunits "
        "FROM served_provider_budget_reservations"
    ).fetchall()
    # REJECT #2: the router reserved AND finalized REAL usage for the background attempt.
    assert len(served_rows) == 1, [dict(r) for r in served_rows]
    assert served_rows[0]["actual_total_tokens"] == 1000
    assert served_rows[0]["actual_cost_microunits"] == 50
    assert served_rows[0]["state"] != "reserved"
    own = [r["state"] for r in conn.execute(
        "SELECT state FROM assigned_queue_provider_reservations"
    )]
    assert own == ["settled"]


def test_forged_served_provider_on_a_context_is_refused_before_launch(tmp_path: Path) -> None:
    """Codex REJECT #2 + #3 on #2531, reproduced and closed.

    ``ServedProviderAuthority`` is a plain frozen dataclass: anyone can build one of
    the right SHAPE. Authority is therefore established by PROVENANCE through a
    validator-owned, unforgeable fence (the same pattern as
    ``auth.middleware.ProviderRequestCapability``): there is NO public "register"
    primitive (REJECT #3: the first fix had one, so an attacker could self-bless a
    forgery), the fence cannot be constructed or serialized, and only the two
    genuine mint sites (inside ``provider_assignment`` / ``_authorize_launch``) mint
    one. Separately, an authority with an UNKNOWN ``budget_owner`` must fail closed
    before routing — it would otherwise skip the reservation block and launch with
    no budget (REJECT #3 reproduced exactly that).

    Genuine provenance is proven by the real-store e2e above (the background mint
    site opens a fence and the router launches); this test proves every forgery
    path is refused with ZERO provider calls.
    """
    import asyncio

    import pytest

    import tinyassets.provider_assignment as pa
    from tinyassets.config import UniverseConfig
    from tinyassets.exceptions import ProviderAuthorityHeldError
    from tinyassets.provider_assignment import IssuedAuthorityFence, ServedProviderAuthority
    from tinyassets.providers.base import (
        BaseProvider,
        ModelConfig,
        ProviderResponse,
        UniverseContext,
    )
    from tinyassets.providers.router import ProviderRouter

    class _CountingProvider(BaseProvider):
        def __init__(self) -> None:
            self.name = "codex"
            self.family = "codex"
            self.calls = 0

        async def complete(self, prompt, system, config: ModelConfig, *, universe_dir=None):
            self.calls += 1
            return ProviderResponse(
                text="should-not-run", provider="codex", model="fake", family="codex",
                latency_ms=0.0,
            )

    fake = _CountingProvider()
    router = ProviderRouter({"codex": fake})
    universe_dir = tmp_path / "u-forge"
    universe_dir.mkdir()

    def forged(budget_owner: str) -> ServedProviderAuthority:
        return ServedProviderAuthority(
            authority_kind="subscription_snapshot", provider="codex",
            max_invocations=10, request_max_invocations=0, max_tokens=100_000,
            max_cost_microunits=1_000_000, owner_user_id="attacker",
            universe_id="u-forge", agent_binding_id="b", binding_revision=1,
            binding_id="bid", binding_generation=1, binding_digest="d",
            credential_reference_id="c", credential_reference_generation=1,
            credential_reference_digest="cd", credential_service="codex",
            credential_snapshot_dir=universe_dir, request_capability=None,
            operation="background_branch_run", allowed_roles=("writer",),
            budget_owner=budget_owner,
        )

    def attempt(authority: ServedProviderAuthority) -> None:
        context = UniverseContext(
            universe_dir=universe_dir,
            config=UniverseConfig(allowed_providers=["codex"]),
            served_provider=authority,
        )
        asyncio.run(router.call(
            "writer", "p", "s", operation="background_branch_run", universe_context=context,
        ))

    # ATTACK 1 (REJECT #2): a shape-perfect forgery is refused before any launch.
    with pytest.raises(ProviderAuthorityHeldError):
        attempt(forged("background_attempt"))
    assert fake.calls == 0

    # ATTACK 2 (REJECT #3): self-blessing is impossible — no public register primitive
    # exists, and the fence cannot be constructed, mutated, or serialized.
    assert not hasattr(pa, "register_issued_authority")
    with pytest.raises(TypeError):
        IssuedAuthorityFence()
    with pytest.raises(TypeError):
        IssuedAuthorityFence(forged("background_attempt"))
    # Even a hand-built fence object smuggled into the open-fence table is refused:
    # its _secret is not the module-private sentinel.
    smuggled = object.__new__(IssuedAuthorityFence)
    object.__setattr__(smuggled, "_secret", object())  # not _MINT_SECRET
    victim = forged("background_attempt")
    object.__setattr__(smuggled, "_authority", victim)
    with pa._ISSUED_AUTHORITY_LOCK:
        pa._OPEN_FENCES[id(victim)] = smuggled
    try:
        assert pa.is_issued_authority(victim) is False
        with pytest.raises(ProviderAuthorityHeldError):
            attempt(victim)
    finally:
        with pa._ISSUED_AUTHORITY_LOCK:
            pa._OPEN_FENCES.pop(id(victim), None)
    assert fake.calls == 0

    # ATTACK 3 (REJECT #3): an UNKNOWN budget_owner can no longer skip reservation
    # and launch unbudgeted — refused before routing, zero provider calls.
    with pytest.raises(ProviderAuthorityHeldError):
        attempt(forged("free_lunch"))
    assert fake.calls == 0
