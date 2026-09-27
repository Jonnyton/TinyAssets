"""Native metadata crosses the real public picker composition, not only a plan."""

import json
from dataclasses import replace
from datetime import timedelta

import pytest

from tests import test_native_discovery_integration as integration
from tinyassets import daemon_server, universe_server
from tinyassets.api import model_options, permissions
from tinyassets.credential_vault import write_credential_vault
from tinyassets.exceptions import ProviderError

native = integration.native


@pytest.fixture
def picker(native, monkeypatch):
    integration.install_discovery(native, monkeypatch)
    (native.universe / "soul.md").write_text("# Picker fixture", encoding="utf-8")
    daemon_server.grant_universe_access(
        native.base, universe_id=native.universe.name, actor_id="owner-1", permission="admin",
    )
    monkeypatch.setattr(model_options, "_base_path", lambda: native.base)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "owner-1")
    return lambda: json.loads(universe_server.read_graph(target="model_options"))


@pytest.mark.parametrize("native", ["discovered"], indirect=True)
def test_native_public_picker_lists_default_and_discovered_model(picker, native):
    result = picker()
    assert result["kind"] == "advisory_model_options"
    assert result["choice_authority"] == "accepted_manifest"
    # THIS source's own rows: the provider default plus what discovery enumerated.
    # Filtered by basis rather than taking every row the picker offers, because a
    # universe on this source kind also sees the reviewed public list
    # (models/subscription.json), and those are candidates to grant with their own
    # basis and their own reason. Their behaviour is asserted in
    # tests/test_public_model_lists.py; this test is about discovery.
    choices = [row for row in result["options"]
               if row["reference"]["provider_ref"] == "codex"
               and row["availability_basis"] in ("executor_default", "executor_enumerated")]
    assert {row["reference"]["model_id"] for row in choices} == {"", "new-account-model"}
    assert all(row["in_candidate_catalog"] and not row["reasons"] for row in choices)
    source = next(row for row in result["sources"] if row["provider_ref"] == "codex")
    assert source["warnings"] == []
    assert source["observed_at"] <= source["completed_at"] < source["expires_at"]
    assert native.provider.calls == 0
    serialized = json.dumps(result)
    assert str(native.base) not in serialized and "custody" not in serialized


@pytest.mark.parametrize("native", ["discovered"], indirect=True)
def test_public_picker_refresh_discovers_new_account_model(picker, native, monkeypatch):
    ids = ["initial-model"]

    async def discover():
        return integration.catalogue(ids)

    integration.install_discovery(native, monkeypatch, discover)
    def enumerated(result):
        return [row["reference"]["model_id"] for row in result["options"]
                if row["availability_basis"] == "executor_enumerated"]

    before = picker()
    ids.append("future-model-not-in-any-release-table")
    after = picker()
    # Asserted on the ENUMERATED rows, not on a position in the whole list: the public
    # list contributes rows too, so "the last option" is no longer the new discovery.
    assert len(after["options"]) == len(before["options"]) + 1
    assert enumerated(after) == enumerated(before) + [ids[-1]]


@pytest.mark.parametrize("native", ["discovered"], indirect=True)
@pytest.mark.parametrize("unsupported", [False, True])
def test_public_picker_unknown_metadata_keeps_default(picker, native, monkeypatch, unsupported):
    async def discover():
        if unsupported:
            return None
        raise ProviderError("fixture discovery failure")

    integration.install_discovery(native, monkeypatch, discover)
    result = picker()
    # Discovery failed, so this SOURCE contributes only its provider default. The
    # reviewed public list still contributes its own rows -- separately sourced and
    # separately marked -- so the assertion names the basis rather than the whole list.
    own = [row for row in result["options"]
           if row["availability_basis"] in ("executor_default", "executor_enumerated")]
    assert [row["reference"]["model_id"] for row in own] == [""]
    assert own[0]["in_candidate_catalog"]
    # And nothing listed is admitted: a public list says an id exists, not that this
    # universe may use it.
    listed = [row for row in result["options"]
              if row["availability_basis"] == "publicly_listed"]
    assert all(not row["in_candidate_catalog"] and row["reasons"] for row in listed)
    assert native.provider.calls == 0


@pytest.mark.parametrize("native", ["discovered"], indirect=True)
@pytest.mark.parametrize("failure", ["expired", "revoked"])
def test_native_public_picker_rechecks_after_metadata_io(picker, native, monkeypatch, failure):
    prepare = model_options.prepare_owned_model_plan

    def changed_after_prepare(**kwargs):
        prepared = prepare(**kwargs)
        if failure == "revoked":
            write_credential_vault(native.universe, [], owner_user_id="owner-1",
                                   universe_id=native.universe.name)
            return prepared
        return replace(prepared, snapshots=tuple(
            replace(snapshot, observed_at=snapshot.observed_at - timedelta(minutes=6))
            for snapshot in prepared.snapshots
        ))

    monkeypatch.setattr(model_options, "prepare_owned_model_plan", changed_after_prepare)
    result = picker()
    assert result["kind"] == "advisory_model_options"
    assert not result["options"] and not result["order"]
    source = next(row for row in result["sources"] if row["provider_ref"] == "codex")
    assert source["reasons"] and "observed_at" not in source
    assert native.provider.calls == 0
