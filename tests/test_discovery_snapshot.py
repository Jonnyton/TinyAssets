"""Profile-bound refresh provenance and async coordination, no live account IO."""

import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

from tests import test_model_discovery_capability as profile_tests
from tinyassets.exceptions import ProviderUnavailableError
from tinyassets.providers import definition as definitions
from tinyassets.providers import discovery_snapshot as snapshots

NOW = datetime(2026, 9, 9, 22, 0, tzinfo=timezone.utc)
rig = profile_tests.rig


def _model(model_id="new-company/new-model"):
    return {
        "id": model_id,
        "canonical_slug": model_id,
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        "supported_parameters": ["tools"],
        "context_length": 32000,
        "pricing": {"prompt": "0", "completion": "0", "image": "0", "request": "0"},
    }


@pytest.fixture
def reader(rig, monkeypatch):
    rig.publish()
    monkeypatch.setattr(snapshots, "_now", lambda: NOW)
    calls = []

    def read(**kwargs):
        calls.append(kwargs)
        assert kwargs["owner_user_id"] == "owner" and kwargs["universe_id"] == "u-models"
        assert kwargs["definition"].ref == "grant-models"
        if "benchmarks" in kwargs["url"]:
            return {
                "meta": {"as_of": NOW.isoformat()},
                "data": [
                    {
                        "source": "artificial-analysis",
                        "model_permaslug": "new-company/new-model",
                        "agentic_index": 52,
                        "intelligence_index": 64,
                    }
                ],
            }
        return {
            "owner_filtered": False,
            "executor_tools": True,
            "account_id": "remote-claim",
            "data": [_model()],
        }

    monkeypatch.setattr(snapshots, "read_http_discovery_document", read)
    return calls, read


def _refresh(rig):
    return snapshots.refresh_model_discovery(
        owner_user_id="owner", universe_id="u-models", definition_id=rig.definition.id
    )


def test_refresh_keeps_exact_provenance_and_never_upgrades_tool_or_account_authority(rig, reader):
    result = _refresh(rig)
    assert result.owner_id == "owner" and result.universe_id == "u-models"
    assert result.provider == f"api_key_http:{rig.definition.id}"
    assert result.connection_id == "conn-models" and result.grant_id == "grant-models"
    assert result.models.connection_id == result.provider
    assert result.models.owner_filtered and result.models.freshness == "fresh"
    assert result.models.executor_tools and result.models.authenticated_account_id is None
    assert result.models.default_model_id is None and result.warnings == ()
    assert result.models.models[0].scores.agentic == 52_000_000
    assert result.observed_at == result.completed_at == NOW
    assert len(result.source_digest) == 64 and "vault" not in repr(result)
    assert [call["url"] for call in reader[0]] == [result.catalogue_url, result.benchmark_url]
    assert definitions.get_definition("u-models", rig.definition.id) == rig.definition


def test_shared_physical_connection_keeps_exact_selector_binding_identity(rig, reader):
    first = _refresh(rig)
    second_definition = definitions.register_definition(
        universe_id="u-models",
        owner_user_id="owner",
        access_method="api_key_http",
        protocol="openai_chat",
        model="other-legacy-model",
        ref="grant-models",
    )
    second = snapshots.refresh_model_discovery(
        owner_user_id="owner", universe_id="u-models", definition_id=second_definition.id
    )
    assert first.connection_id == second.connection_id
    assert first.models.connection_id != second.models.connection_id
    assert first.source_digest != second.source_digest


@pytest.mark.parametrize(
    "field, value",
    [("owner_user_id", "other"), ("universe_id", "other"), ("definition_id", "missing")],
)
def test_wrong_scope_never_attempts_discovery(rig, reader, field, value):
    arguments = dict(owner_user_id="owner", universe_id="u-models", definition_id=rig.definition.id)
    with pytest.raises(ProviderUnavailableError):
        snapshots.refresh_model_discovery(**(arguments | {field: value}))
    assert reader[0] == []


@pytest.mark.parametrize("mutation, reason", [
    ("revoke", "source_revoked"), ("profile", "missing_discovery_scope"),
    ("scope", "missing_discovery_scope"), ("auth", "protocol_mismatch"),
])
def test_discovery_refusal_has_fixed_safe_reason(rig, reader, mutation, reason):
    if mutation == "revoke":
        rig.ledger.revoke_grant("grant-models")
    elif mutation == "profile":
        rig.publish(enabled=False)
    else:
        with rig.ledger._connect() as conn:
            if mutation == "scope":
                conn.execute("UPDATE outbound_connections SET scopes_json = '[\"POST\"]'")
            else:
                conn.execute("UPDATE outbound_connections SET auth_scheme = 'none'")
    with pytest.raises(snapshots.ModelDiscoveryUnavailable) as held:
        _refresh(rig)
    assert held.value.reason == reason
    assert "grant-models" not in str(held.value) and "vault" not in str(held.value)
    assert reader[0] == []


@pytest.mark.parametrize(
    "mutation", ["revoke", "remove_profile", "narrow", "credential_ref", "definition"]
)
def test_source_change_during_read_cannot_publish_fresh_snapshot(
    rig, reader, monkeypatch, mutation
):
    def change_then_read(**kwargs):
        result = reader[1](**kwargs)
        if "models/user" in kwargs["url"]:
            if mutation == "revoke":
                rig.ledger.revoke_grant("grant-models")
            elif mutation == "remove_profile":
                rig.publish(enabled=False)
            elif mutation == "narrow":
                with rig.ledger._connect() as raw:
                    raw.execute("UPDATE outbound_connections SET allowed_endpoints_json = '[]'")
            elif mutation == "credential_ref":
                with rig.ledger._connect() as raw:
                    raw.execute(
                        "UPDATE outbound_connections SET credential_ref = 'vault://http/replacement'"
                    )
            else:
                path = definitions._store_path("u-models")
                rows = json.loads(path.read_text(encoding="utf-8"))
                rows[0]["model"] = "tampered"
                path.write_text(json.dumps(rows), encoding="utf-8")
        return result

    monkeypatch.setattr(snapshots, "read_http_discovery_document", change_then_read)
    with pytest.raises(ProviderUnavailableError):
        _refresh(rig)


def test_benchmark_failure_keeps_unranked_catalogue_and_safe_warning(rig, reader, monkeypatch):
    def missing(**kwargs):
        if "benchmarks" in kwargs["url"]:
            raise ProviderUnavailableError("private-upstream-detail")
        return reader[1](**kwargs)

    monkeypatch.setattr(snapshots, "read_http_discovery_document", missing)
    result = _refresh(rig)
    assert result.models.models[0].scores is None
    assert result.warnings == ("benchmark_unavailable",) and "private-upstream" not in repr(result)


def test_stale_benchmark_date_is_not_freshened_by_fetch(rig, reader, monkeypatch):
    def old(**kwargs):
        result = reader[1](**kwargs)
        if "meta" in result:
            result["meta"]["as_of"] = (NOW - timedelta(days=2)).isoformat()
        return result

    monkeypatch.setattr(snapshots, "read_http_discovery_document", old)
    assert _refresh(rig).models.models[0].scores.freshness == "stale"


def test_fresh_read_observes_new_model_without_renaming_connection(rig, reader, monkeypatch):
    first = _refresh(rig)

    def added(**kwargs):
        value = reader[1](**kwargs)
        if "models/user" in kwargs["url"]:
            value["data"].append(_model("future-provider/not-known-at-build-time"))
        return value

    monkeypatch.setattr(snapshots, "read_http_discovery_document", added)
    second = _refresh(rig)
    assert len(first.models.models) == 1 and len(second.models.models) == 2
    assert first.source_digest == second.source_digest
    assert first.models.connection_id == second.models.connection_id


@pytest.mark.parametrize("delta", [timedelta(minutes=6), timedelta(seconds=-1)])
def test_excessive_delay_or_backwards_clock_refuses_fresh_label(rig, reader, monkeypatch, delta):
    times = iter((NOW, NOW, NOW + delta))
    monkeypatch.setattr(snapshots, "_now", lambda: next(times))
    with pytest.raises(ProviderUnavailableError, match="freshness window"):
        _refresh(rig)


def test_catalogue_request_duration_counts_against_freshness(rig, reader, monkeypatch):
    def delayed(**kwargs):
        monkeypatch.setattr(snapshots, "_now", lambda: NOW + timedelta(minutes=6))
        return reader[1](**kwargs)

    monkeypatch.setattr(snapshots, "read_http_discovery_document", delayed)
    with pytest.raises(ProviderUnavailableError, match="freshness window"):
        _refresh(rig)


def test_cancelled_waiter_does_not_duplicate_or_cancel_active_read(rig, reader, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    actual = snapshots.refresh_model_discovery
    calls = []

    def held(**kwargs):
        calls.append(kwargs)
        entered.set()
        assert release.wait(5)
        return actual(**kwargs)

    monkeypatch.setattr(snapshots, "refresh_model_discovery", held)

    async def scenario():
        args = dict(owner_user_id="owner", universe_id="u-models", definition_id=rig.definition.id)
        first = asyncio.create_task(snapshots.refresh_model_discovery_async(**args))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            second = asyncio.create_task(snapshots.refresh_model_discovery_async(**args))
            await asyncio.sleep(0)
            assert len(calls) == 1
            release.set()
            result = await asyncio.wait_for(second, 5)
            assert result.models.owner_filtered
            await asyncio.sleep(0)
            assert not snapshots._INFLIGHT
            await snapshots.refresh_model_discovery_async(**args)
            assert len(calls) == 2
        finally:
            release.set()

    asyncio.run(scenario())


def test_failed_async_refresh_does_not_poison_later_refresh(rig, reader, monkeypatch):
    actual = snapshots.refresh_model_discovery
    calls = []

    def once_failed(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise ProviderUnavailableError("temporary test refusal")
        return actual(**kwargs)

    monkeypatch.setattr(snapshots, "refresh_model_discovery", once_failed)

    async def scenario():
        args = dict(owner_user_id="owner", universe_id="u-models", definition_id=rig.definition.id)
        with pytest.raises(ProviderUnavailableError):
            await snapshots.refresh_model_discovery_async(**args)
        result = await snapshots.refresh_model_discovery_async(**args)
        assert result.models.owner_filtered and len(calls) == 2
        await asyncio.sleep(0)
        assert not snapshots._INFLIGHT

    asyncio.run(scenario())
