"""BUG-081 regression: patch_branch author authority gate.

Before this fix, `extensions action=patch_branch` accepted mutations
against any branch with ``visibility:public`` regardless of who the
branch's ``author`` field named. `visibility=public` was being treated as
"anyone can mutate," not "anyone can fork or read." Slice-0 substrate
probe 2026-05-13 demonstrated the gap by mutating a
chatgpt-community-builder-authored branch from a non-author session.

Fix: when the caller (``UNIVERSE_SERVER_USER``) differs from the branch's
``author``, patch_branch rejects with an auth error unless ``force=true``
is explicitly passed.
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
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    from workflow import universe_server as us

    importlib.reload(us)
    yield us, base, monkeypatch
    importlib.reload(us)


def _call(us, tool: str, action: str, **kwargs):
    fn = getattr(us, tool)
    return json.loads(fn(action=action, **kwargs))


def _build_as_alice(us) -> str:
    """Build a minimal branch authored by 'alice' (set by ext_env)."""
    spec = {
        "name": "alice-branch",
        "tags": ["initial"],
        "entry_point": "capture",
        "node_defs": [{
            "node_id": "capture",
            "display_name": "Capture",
            "prompt_template": "cap: {x}",
        }],
        "edges": [
            {"from": "START", "to": "capture"},
            {"from": "capture", "to": "END"},
        ],
        "state_schema": [{"name": "x", "type": "str"}],
    }
    res = _call(us, "extensions", "build_branch", spec_json=json.dumps(spec))
    assert res["status"] == "built", res
    return res["branch_def_id"]


def _patch_tags(us, bid: str, *, force: bool = False):
    return _call(
        us, "extensions", "patch_branch",
        branch_def_id=bid,
        changes_json=json.dumps([{"op": "set_tags", "tags": ["amended"]}]),
        force=force,
    )


class TestPatchBranchAuthGate:

    def test_author_can_patch_own_branch(self, ext_env):
        """The branch author can always patch their own branch."""
        us, _base, _monkeypatch = ext_env
        bid = _build_as_alice(us)  # caller = alice = author
        res = _patch_tags(us, bid)
        assert res["status"] == "patched", res
        assert res["patched_fields"] == ["tags"]

    def test_non_author_is_rejected(self, ext_env):
        """A different caller is rejected without force=true."""
        us, _base, monkeypatch = ext_env
        bid = _build_as_alice(us)  # author = alice

        # Switch to bob and try to mutate alice's branch.
        monkeypatch.setenv("UNIVERSE_SERVER_USER", "bob")
        importlib.reload(__import__("workflow.universe_server", fromlist=["x"]))
        from workflow import universe_server as us_bob

        res = _patch_tags(us_bob, bid)
        assert res["status"] == "rejected", res
        assert "denied" in res["error"].lower()
        assert res.get("branch_author") == "alice"
        assert res.get("caller") == "bob"

    def test_non_author_can_force_through(self, ext_env):
        """force=true bypasses the auth gate (escape hatch for ops)."""
        us, _base, monkeypatch = ext_env
        bid = _build_as_alice(us)  # author = alice

        monkeypatch.setenv("UNIVERSE_SERVER_USER", "bob")
        importlib.reload(__import__("workflow.universe_server", fromlist=["x"]))
        from workflow import universe_server as us_bob

        res = _patch_tags(us_bob, bid, force=True)
        assert res["status"] == "patched", res
        assert res["patched_fields"] == ["tags"]

    def test_anonymous_branch_still_gated(self, ext_env):
        """Even branches authored by 'anonymous' require force from non-anon
        callers — anonymous authorship is not a free-mutation pass.

        Otherwise the substrate would treat the default un-attributed
        identity as a "anyone can mutate this" marker, which inverts the
        intended safety property.
        """
        us, _base, monkeypatch = ext_env

        # Build the branch as anonymous.
        monkeypatch.setenv("UNIVERSE_SERVER_USER", "anonymous")
        importlib.reload(__import__("workflow.universe_server", fromlist=["x"]))
        from workflow import universe_server as us_anon
        bid = _build_as_alice(us_anon)  # author = anonymous

        # alice tries to mutate the anonymous-authored branch.
        monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
        importlib.reload(__import__("workflow.universe_server", fromlist=["x"]))
        from workflow import universe_server as us_alice

        res = _patch_tags(us_alice, bid)
        assert res["status"] == "rejected", res
        assert res.get("branch_author") == "anonymous"
        assert res.get("caller") == "alice"

    def test_anonymous_caller_against_authored_branch_is_rejected(self, ext_env):
        """An anonymous caller is also rejected when trying to mutate an
        authored branch. Anonymous is the most-restrictive identity, not
        the least.
        """
        us, _base, monkeypatch = ext_env
        bid = _build_as_alice(us)  # author = alice

        monkeypatch.setenv("UNIVERSE_SERVER_USER", "anonymous")
        importlib.reload(__import__("workflow.universe_server", fromlist=["x"]))
        from workflow import universe_server as us_anon

        res = _patch_tags(us_anon, bid)
        assert res["status"] == "rejected", res
        assert res.get("branch_author") == "alice"
        assert res.get("caller") == "anonymous"
