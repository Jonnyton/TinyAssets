"""Existing graph authority used by the portable layout consumer, with real stores.

These are installation controls, not evidence that the browser renders a layout.
The consumed DOM and ordinary app acceptance are separate required tests.
"""

import copy
import json

import pytest

from tinyassets.api.custom_agents import custom_agents
from tinyassets.auth.middleware import identity_context
from tinyassets.auth.provider import Identity


def actor(name):
    return identity_context(Identity(user_id=name, username=name, capabilities=["write"]))


def definition(name="Shared compact layout"):
    return {
        "schema_version": 1, "name": name, "tags": ["tinyassets-app-layout-v1"],
        "components": {"my_layout": {
            "kind": "tinyassets.app-layout.v1", "version": 1,
            "surfaces": ["requests", "conversation", "models", "status"],
            "density": "compact",
        }, "retained_component": {"kind": "future_renderer", "user_option": "preserve"}},
    }


def configuration(name):
    return {"schema_version": 1, "name": name, "role": "app_experience",
            "customizations": {"private_label": name}}


def publish(payload):
    result = custom_agents(action="publish_agent", payload=payload)
    assert result.get("status") == "published", result
    return result["agent"]


def install(uid, did, config):
    result = custom_agents(action="create_binding", universe_id=uid,
                           definition_id=did, payload=config)
    assert result.get("status") == "configured", result
    return result["binding"]


@pytest.fixture
def homes(tmp_path, monkeypatch):
    from tinyassets.daemon_server import grant_universe_access, set_founder_home

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    for owner in ("alice", "bob"):
        uid = "u-" + owner
        (tmp_path / uid).mkdir()
        set_founder_home(tmp_path, founder_sub=owner, universe_id=uid,
                         platform_generated=True)
        grant_universe_access(tmp_path, universe_id=uid, actor_id=owner,
                              permission="admin")
    return tmp_path


def test_other_owner_discovers_remixes_and_applies_without_copying_private_data(homes):
    from tinyassets import conversation_store

    with actor("alice"):
        source = publish(definition())
        private_source = install("u-alice", source["agent_definition_id"],
                                 configuration("alice-private-installation"))
    conversation_store.record_exchange(homes / "u-bob", "bob", "private question", "private answer")
    history = conversation_store.load_recent_readonly(homes / "u-bob", "bob")
    memory = homes / "u-bob" / "private-memory.md"
    memory.write_text("bob-private-memory-verbatim\n", encoding="utf-8")

    with actor("bob"):
        found = custom_agents(action="list_agents", tags=["tinyassets-app-layout-v1"])
        assert source["agent_definition_id"] in {a["agent_definition_id"] for a in found["agents"]}
        assert custom_agents(action="get_binding", universe_id="u-alice",
                             binding_id=private_source["agent_binding_id"])["error"] == "not_found"
        private_config = configuration("bob-private-installation")
        installed = install("u-bob", source["agent_definition_id"], private_config)
        remix = copy.deepcopy(source["portable_definition"])
        remix.pop("content_fingerprint", None)
        remix["name"] = "My comfortable remix"
        remix["components"]["my_layout"]["density"] = "comfortable"
        remix["lineage"] = {key: [{"definition_id": source["agent_definition_id"],
                                  "component_key": key, "credit_share": 1.0}]
                             for key in remix["components"]}
        child = publish(remix)
        changed = custom_agents(action="update_binding", universe_id="u-bob",
                                binding_id=installed["agent_binding_id"],
                                expected_revision=installed["revision"],
                                definition_id=child["agent_definition_id"],
                                payload=copy.deepcopy(installed["configuration"]))
        assert changed.get("status") == "configured", changed
        readback = custom_agents(action="get_binding", universe_id="u-bob",
                                 binding_id=installed["agent_binding_id"])["binding"]
        assert readback["configuration"] == private_config
        assert readback["agent_definition_id"] == child["agent_definition_id"]
        assert readback["revision"] == installed["revision"] + 1
        assert readback["status"] == "configured"
        portable = child["portable_definition"]
        assert (portable["components"]["retained_component"]
                == remix["components"]["retained_component"])
        encoded = json.dumps(portable)
        assert all(sentinel not in encoded for sentinel in (
            "alice-private-installation", "bob-private-installation", "private question",
            "private answer", "bob-private-memory", installed["agent_binding_id"],
        ))

    assert conversation_store.load_recent_readonly(homes / "u-bob", "bob") == history
    assert memory.read_text(encoding="utf-8") == "bob-private-memory-verbatim\n"


def test_layout_revision_conflict_and_foreign_mutation_leave_current_installation(homes):
    with actor("alice"):
        source = publish(definition())
    with actor("bob"):
        binding = install("u-bob", source["agent_definition_id"], configuration("private"))
        args = {"action": "update_binding", "universe_id": "u-bob",
                "binding_id": binding["agent_binding_id"], "expected_revision": 1,
                "definition_id": source["agent_definition_id"],
                "payload": configuration("new private value")}
        assert custom_agents(**args)["status"] == "configured"
        assert custom_agents(**args)["error"] == "agent_conflict"
    with actor("alice"):
        assert "error" in custom_agents(**{**args, "expected_revision": 2})
    with actor("bob"):
        current = custom_agents(action="get_binding", universe_id="u-bob",
                                binding_id=binding["agent_binding_id"])["binding"]
        assert current["revision"] == 2
        assert current["configuration"] == configuration("new private value")


def test_nonserving_layout_binding_preserves_real_serving_authority(tmp_path, monkeypatch):
    from tests.test_open_serving_bind import _bound_and_serving
    from tinyassets.daemon_server import grant_universe_access
    from tinyassets.provider_assignment import load_provider_assignment
    from tinyassets.provider_serving_binding import serving_connection_is_current

    universe, serving, _ = _bound_and_serving(tmp_path, monkeypatch)
    grant_universe_access(tmp_path, universe_id="u-owner", actor_id="owner-1",
                          permission="admin")
    before = load_provider_assignment(tmp_path, universe_id="u-owner")
    with actor("owner-1"):
        source = publish(definition())
        layout = install("u-owner", source["agent_definition_id"], configuration("My layout"))
        assert layout["agent_binding_id"] != serving["agent_binding_id"]
        assert "provider_ref" not in layout["configuration"]
        assert layout["status"] == "configured"
        assert serving_connection_is_current(tmp_path, universe_dir=universe,
                                             universe_id="u-owner", owner_user_id="owner-1")
    assert load_provider_assignment(tmp_path, universe_id="u-owner") == before
