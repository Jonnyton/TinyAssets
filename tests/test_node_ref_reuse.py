"""#66: cross-branch node reuse via explicit node_ref + copy intent.

Before: ``extensions action=add_node`` silently created a hollow node
whenever the caller's ``node_id`` collided with an existing standalone
registered node. No error, no warning — the hollow clone replaced the
canonical body. That made #62 (cross-branch node-reuse discovery)
architecturally pointless: even if the bot found a rigor_checker to
reuse, saying "add_node node_id=rigor_checker" just made a new empty
node_def, not a copy of the canonical one.

After: add_node / build_branch / patch_branch's add_node op refuse the
shadow and point the caller at ``node_ref_json`` (for atomic add_node)
or a ``node_ref`` field inside the spec/ops (for composite paths).
``intent="copy"`` is the explicit consent override for "I know this
collides and I want the existing body".
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def ext_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    from workflow import universe_server as us

    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _call(us, tool: str, action: str, **kwargs):
    fn = getattr(us, tool)
    return json.loads(fn(action=action, **kwargs))


def _register_standalone(us, node_id: str, display_name: str,
                         source: str = "def run(state): return state\n"):
    return _call(
        us, "extensions", "register",
        node_id=node_id,
        display_name=display_name,
        description=f"Standalone {display_name}",
        phase="custom",
        input_keys="state",
        output_keys="state",
        source_code=source,
    )


def _build_empty_branch(us, name: str = "b") -> str:
    spec = {
        "name": name,
        "entry_point": "seed",
        "node_defs": [{
            "node_id": "seed",
            "display_name": "Seed",
            "prompt_template": "start: {x}",
        }],
        "edges": [
            {"from": "START", "to": "seed"},
            {"from": "seed", "to": "END"},
        ],
        "state_schema": [{"name": "x", "type": "str"}],
    }
    result = _call(us, "extensions", "build_branch",
                   spec_json=json.dumps(spec))
    assert result["status"] == "built", result
    return result["branch_def_id"]


# ─────────────────────────────────────────────────────────────────────────────
# Silent shadowing is refused
# ─────────────────────────────────────────────────────────────────────────────


class TestHollowNodeShadowRefused:
    """Bare node_id collision must loudly reject, not silently hollow-clone."""

    def test_add_node_with_colliding_node_id_errors(self, ext_env):
        us, _ = ext_env
        _register_standalone(us, "rigor_checker", "Rigor Checker")
        bid = _build_empty_branch(us)
        # No node_ref, no intent — must refuse the shadow.
        result = _call(
            us, "extensions", "add_node",
            branch_def_id=bid,
            node_id="rigor_checker",
            display_name="Silent Clone Attempt",
        )
        assert "error" in result
        err = result["error"].lower()
        assert "standalone" in err
        assert "node_ref" in err or "intent" in err

    def test_build_branch_with_colliding_node_id_errors(self, ext_env):
        us, _ = ext_env
        _register_standalone(us, "rigor_checker", "Rigor Checker")
        spec = {
            "name": "shadow-attempt",
            "entry_point": "rigor_checker",
            "node_defs": [{
                "node_id": "rigor_checker",
                "display_name": "Silent Clone",
                "prompt_template": "x",
            }],
            "edges": [
                {"from": "START", "to": "rigor_checker"},
                {"from": "rigor_checker", "to": "END"},
            ],
            "state_schema": [{"name": "y", "type": "str"}],
        }
        result = _call(us, "extensions", "build_branch",
                       spec_json=json.dumps(spec))
        assert result["status"] == "rejected"
        combined = " ".join(result.get("errors") or []).lower()
        assert "standalone" in combined
        assert "node_ref" in combined or "intent" in combined

    def test_patch_branch_add_node_colliding_id_errors(self, ext_env):
        us, _ = ext_env
        _register_standalone(us, "rigor_checker", "Rigor Checker")
        bid = _build_empty_branch(us)
        ops = [{
            "op": "add_node",
            "node_id": "rigor_checker",
            "display_name": "Silent Clone",
        }]
        result = _call(us, "extensions", "patch_branch",
                       branch_def_id=bid,
                       changes_json=json.dumps(ops))
        assert result.get("status") == "rejected"
        joined = json.dumps(result).lower()
        assert "standalone" in joined


# ─────────────────────────────────────────────────────────────────────────────
# Explicit reuse works
# ─────────────────────────────────────────────────────────────────────────────


class TestExplicitNodeRefCopiesCanonicalBody:
    """node_ref_json / node_ref in spec copies the canonical body."""

    def test_add_node_with_node_ref_copies_standalone_body(self, ext_env):
        us, base = ext_env
        _register_standalone(
            us, "rigor_checker", "Rigor Checker",
            source="def audit(state): state['audited']=True; return state\n",
        )
        bid = _build_empty_branch(us)
        ref_json = json.dumps(
            {"source": "standalone", "node_id": "rigor_checker"},
        )
        result = _call(
            us, "extensions", "add_node",
            branch_def_id=bid,
            node_id="rigor_checker",
            display_name="",  # resolver fills in from ref
            node_ref_json=ref_json,
        )
        assert result.get("status") == "added", result

        # Confirm the branch now carries the canonical body, not a hollow node.
        from workflow.daemon_server import get_branch_definition
        branch = get_branch_definition(base, branch_def_id=bid)
        nd = next(
            n for n in branch["node_defs"]
            if n["node_id"] == "rigor_checker"
        )
        assert "audit" in nd["source_code"]
        assert nd["display_name"] == "Rigor Checker"

    def test_intent_copy_permits_shadow_without_ref(self, ext_env):
        """intent='copy' + inline fields is the non-lookup escape hatch
        (caller knows what they're doing). The caller's inline fields
        win — we do NOT silently replace them with standalone body.
        """
        us, base = ext_env
        _register_standalone(us, "rigor_checker", "Rigor Checker")
        bid = _build_empty_branch(us)
        result = _call(
            us, "extensions", "add_node",
            branch_def_id=bid,
            node_id="rigor_checker",
            display_name="My Override",
            prompt_template="overridden: {x}",
            intent="copy",
        )
        assert result.get("status") == "added", result
        from workflow.daemon_server import get_branch_definition
        branch = get_branch_definition(base, branch_def_id=bid)
        nd = next(
            n for n in branch["node_defs"]
            if n["node_id"] == "rigor_checker"
        )
        assert nd["display_name"] == "My Override"
        assert nd["prompt_template"] == "overridden: {x}"

    def test_build_branch_node_ref_copies_from_other_branch(self, ext_env):
        us, base = ext_env
        # Seed source branch with a custom node.
        source_spec = {
            "name": "source-branch",
            "entry_point": "shared_audit",
            "node_defs": [{
                "node_id": "shared_audit",
                "display_name": "Shared Audit",
                "prompt_template": "audit: {x}",
                "description": "canonical audit node",
            }],
            "edges": [
                {"from": "START", "to": "shared_audit"},
                {"from": "shared_audit", "to": "END"},
            ],
            "state_schema": [{"name": "x", "type": "str"}],
        }
        source = _call(us, "extensions", "build_branch",
                       spec_json=json.dumps(source_spec))
        assert source["status"] == "built"
        source_bid = source["branch_def_id"]

        # Target branch reuses shared_audit via node_ref.
        target_spec = {
            "name": "target-branch",
            "entry_point": "shared_audit",
            "node_defs": [{
                "node_id": "shared_audit",
                "display_name": "",
                "node_ref": {
                    "source": source_bid,
                    "node_id": "shared_audit",
                },
            }],
            "edges": [
                {"from": "START", "to": "shared_audit"},
                {"from": "shared_audit", "to": "END"},
            ],
            "state_schema": [{"name": "x", "type": "str"}],
        }
        target = _call(us, "extensions", "build_branch",
                       spec_json=json.dumps(target_spec))
        assert target["status"] == "built", target
        from workflow.daemon_server import get_branch_definition
        branch = get_branch_definition(base, branch_def_id=target["branch_def_id"])
        nd = next(
            n for n in branch["node_defs"]
            if n["node_id"] == "shared_audit"
        )
        assert nd["prompt_template"] == "audit: {x}"
        assert nd["description"] == "canonical audit node"

    def test_build_branch_node_ref_preserves_standalone_approval(
        self, ext_env, monkeypatch,
    ):
        us, base = ext_env
        _register_standalone(
            us, "approved_recipe", "Approved Recipe",
            source="def run(state): return {'manifest': 'ok'}\n",
        )
        monkeypatch.setenv("UNIVERSE_SERVER_USER", "host-operator")
        try:
            approved = _call(
                us, "extensions", "approve", node_id="approved_recipe",
            )
        finally:
            monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
        assert approved["approved"] is True

        spec = {
            "name": "approved-node-ref",
            "entry_point": "approved_recipe",
            "node_defs": [{
                "node_id": "approved_recipe",
                "display_name": "",
                "node_ref": {
                    "source": "standalone",
                    "node_id": "approved_recipe",
                },
            }],
            "edges": [
                {"from": "START", "to": "approved_recipe"},
                {"from": "approved_recipe", "to": "END"},
            ],
            "state_schema": [
                {"name": "manifest", "type": "str"},
                {"name": "state", "type": "dict"},
            ],
        }
        built = _call(us, "extensions", "build_branch",
                      spec_json=json.dumps(spec))
        assert built["status"] == "built", built

        from workflow.daemon_server import get_branch_definition
        branch = get_branch_definition(base, branch_def_id=built["branch_def_id"])
        nd = next(
            n for n in branch["node_defs"]
            if n["node_id"] == "approved_recipe"
        )
        assert nd["approved"] is True

    def test_build_branch_raw_approved_field_cannot_bypass_approval(self, ext_env):
        us, base = ext_env
        spec = {
            "name": "approval-bypass-attempt",
            "entry_point": "unsafe_recipe",
            "node_defs": [{
                "node_id": "unsafe_recipe",
                "display_name": "Unsafe Recipe",
                "source_code": "def run(state): return {'manifest': 'ok'}\n",
                "approved": True,
            }],
            "edges": [
                {"from": "START", "to": "unsafe_recipe"},
                {"from": "unsafe_recipe", "to": "END"},
            ],
            "state_schema": [{"name": "manifest", "type": "str"}],
        }
        built = _call(us, "extensions", "build_branch",
                      spec_json=json.dumps(spec))
        assert built["status"] == "built", built

        from workflow.daemon_server import get_branch_definition
        branch = get_branch_definition(base, branch_def_id=built["branch_def_id"])
        nd = next(
            n for n in branch["node_defs"]
            if n["node_id"] == "unsafe_recipe"
        )
        assert nd["approved"] is False

    def test_node_ref_to_unknown_source_errors(self, ext_env):
        us, _ = ext_env
        bid = _build_empty_branch(us)
        ref_json = json.dumps(
            {"source": "no-such-branch", "node_id": "rigor_checker"},
        )
        result = _call(
            us, "extensions", "add_node",
            branch_def_id=bid,
            node_id="rigor_checker",
            display_name="",
            node_ref_json=ref_json,
        )
        assert "error" in result

    def test_node_ref_to_unknown_standalone_errors(self, ext_env):
        us, _ = ext_env
        bid = _build_empty_branch(us)
        ref_json = json.dumps(
            {"source": "standalone", "node_id": "ghost_node"},
        )
        result = _call(
            us, "extensions", "add_node",
            branch_def_id=bid,
            node_id="ghost_node",
            display_name="",
            node_ref_json=ref_json,
        )
        assert "error" in result
        assert "ghost_node" in result["error"]


# ─────────────────────────────────────────────────────────────────────────────
# Intent edge cases
# ─────────────────────────────────────────────────────────────────────────────


class TestIntentEdgeCases:
    def test_unknown_intent_rejected(self, ext_env):
        us, _ = ext_env
        _register_standalone(us, "rigor_checker", "Rigor Checker")
        bid = _build_empty_branch(us)
        result = _call(
            us, "extensions", "add_node",
            branch_def_id=bid,
            node_id="rigor_checker",
            display_name="X",
            intent="slurp",
        )
        assert "error" in result
        assert "intent" in result["error"].lower()

    def test_intent_reference_unsupported_for_v1(self, ext_env):
        us, _ = ext_env
        _register_standalone(us, "rigor_checker", "Rigor Checker")
        bid = _build_empty_branch(us)
        result = _call(
            us, "extensions", "add_node",
            branch_def_id=bid,
            node_id="rigor_checker",
            display_name="X",
            intent="reference",
        )
        assert "error" in result
        assert "not supported" in result["error"].lower() or \
               "live" in result["error"].lower()

    def test_fresh_node_id_without_collision_still_works(self, ext_env):
        """Regression guard: the resolver must not break the plain
        'create a brand new node' path.
        """
        us, _ = ext_env
        bid = _build_empty_branch(us)
        result = _call(
            us, "extensions", "add_node",
            branch_def_id=bid,
            node_id="brand_new",
            display_name="Brand New",
            prompt_template="hi: {x}",
        )
        assert result.get("status") == "added", result

    def test_malformed_node_ref_json_errors(self, ext_env):
        us, _ = ext_env
        bid = _build_empty_branch(us)
        result = _call(
            us, "extensions", "add_node",
            branch_def_id=bid,
            node_id="x",
            display_name="X",
            node_ref_json="{not: valid json",
        )
        assert "error" in result
