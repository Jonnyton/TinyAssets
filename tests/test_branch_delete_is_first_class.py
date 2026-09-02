"""A universe can delete its own branches from the surfaces it actually uses.

Tiny, in the app, 2026-09-02, asked "are you able to delete branches yet?":

    Not yet. I can list branches, read them, run them, create them, and patch
    them, but I do not have a branch delete operation exposed right now.
    I counted 106 branches in the current universe.

`delete_branch` has existed for months behind the deprecated `extensions`
tool, author-gated. It was never put on `write_graph`, on either served
surface. Inside your universe you are god; the only invariant is not
affecting other users. So: an OWN, PRIVATE, UNPUBLISHED branch deletes; a
public or published one is refused, because the commons may be remixing it.
"""
from __future__ import annotations

import json

import pytest


def _spec(name: str) -> dict:
    return {
        "name": name,
        "entry_point": "ready",
        "node_defs": [{
            "node_id": "ready",
            "display_name": "Ready",
            "prompt_template": "Do the work.",
        }],
        "edges": [{"from": "START", "to": "ready"}, {"from": "ready", "to": "END"}],
        "state_schema": [{"name": "x", "type": "str"}],
    }


# ------------------------------------------- the universe/app surface (real)


@pytest.fixture
def universe_surface(monkeypatch, tmp_path):
    import tinyassets.universe_server as us
    from tinyassets.api import permissions

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(us, "write_gate_rejection", lambda name: None)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    actor = {"id": "alice"}
    monkeypatch.setattr(permissions, "current_actor_id", lambda: actor["id"])
    # Branch authoring reads the credential-validated request subject, never an
    # env actor (`_request_branch_actor`).
    monkeypatch.setattr(permissions, "current_request_actor_id", lambda: actor["id"])
    return us, actor


def _create(us, name: str) -> str:
    out = json.loads(us.write_graph(
        target="branch", operation="create", payload_json=json.dumps(_spec(name)),
        idempotency_key=f"create-{name}-0123456789",
    ))
    assert "branch_def_id" in out, out
    return out["branch_def_id"]


def _listed(us) -> set[str]:
    out = json.loads(us.read_graph(target="branches"))
    return {b["branch_def_id"] for b in out.get("branches", [])}


def test_an_OWN_private_branch_deletes_and_is_gone_from_the_listing(universe_surface):
    us, _actor = universe_surface
    bid = _create(us, "probe")
    assert bid in _listed(us)

    out = json.loads(us.write_graph(target="branch", operation="delete", branch_id=bid))

    assert out == {"branch_def_id": bid, "status": "deleted"}, out
    assert bid not in _listed(us)


def test_another_authors_branch_cannot_be_deleted(universe_surface):
    """Author-gated by the existing handler: a non-author sees not-found, the
    same envelope get_branch uses, so existence is not confirmed."""
    us, actor = universe_surface
    bid = _create(us, "alices")
    actor["id"] = "mallory"

    out = json.loads(us.write_graph(target="branch", operation="delete", branch_id=bid))

    assert "error" in out and "deleted" not in json.dumps(out)
    actor["id"] = "alice"
    assert bid in _listed(us), "a non-author deleted someone else's branch"


def test_a_non_author_cannot_even_probe_a_PUBLIC_branch_for_deletion(universe_surface):
    """A public branch is readable by anyone, so the resolve step lets a
    non-author through; the author gate must still answer not-found before the
    public/published reasons are given, or the gate is decoration."""
    us, actor = universe_surface
    bid = _create(us, "alices-public")
    patched = json.loads(us.write_graph(
        target="branch", operation="patch", branch_id=bid,
        changes_json=json.dumps([{"op": "set_visibility", "visibility": "public"}]),
    ))
    assert "error" not in patched, patched
    actor["id"] = "mallory"

    out = json.loads(us.write_graph(target="branch", operation="delete", branch_id=bid))

    assert out.get("error", "").startswith("Branch '"), out   # not-found envelope
    assert out.get("error") not in ("branch_is_public", "branch_is_published")
    actor["id"] = "alice"
    assert bid in _listed(us)


def test_a_PUBLISHED_branch_is_refused_because_the_commons_may_depend_on_it(universe_surface):
    us, _actor = universe_surface
    bid = _create(us, "shared")
    published = json.loads(us.write_graph(target="branch", operation="publish", branch_id=bid))
    assert "error" not in published, published

    out = json.loads(us.write_graph(target="branch", operation="delete", branch_id=bid))

    assert out.get("error") == "branch_is_published", out
    assert bid in _listed(us)


def test_a_PUBLIC_branch_is_refused_because_it_is_in_the_commons(universe_surface):
    us, _actor = universe_surface
    bid = _create(us, "commons")
    patched = json.loads(us.write_graph(
        target="branch", operation="patch", branch_id=bid,
        changes_json=json.dumps([{"op": "set_visibility", "visibility": "public"}]),
    ))
    assert "error" not in patched, patched

    out = json.loads(us.write_graph(target="branch", operation="delete", branch_id=bid))

    assert out.get("error") == "branch_is_public", out
    assert bid in _listed(us)


def test_delete_needs_a_branch_id(universe_surface):
    us, _actor = universe_surface
    out = json.loads(us.write_graph(target="branch", operation="delete"))
    assert "error" in out


def test_the_tool_text_names_delete_so_the_universe_can_find_it(universe_surface):
    """Tiny checked its tool surface and found no delete. The text is the
    surface."""
    us, _ = universe_surface
    import inspect

    doc = inspect.getdoc(us.write_graph) or ""
    assert "delete" in doc.lower() and "branch" in doc.lower()


# ------------------------------------------ the served build surface (engine)


def _bind(monkeypatch, *, actor="sub-9", graph="u-9", allow=("u-9",)):
    import tinyassets.engine_mcp_http as http
    from tinyassets import engine_mcp_server as s

    monkeypatch.setattr(s, "_ACTOR_ID", actor)
    monkeypatch.setattr(s, "_GRAPH_ID", graph)
    monkeypatch.setattr(http, "run_graph_allowlist", lambda: frozenset(allow))
    monkeypatch.setattr(s, "_engine_run_admit", lambda **kw: True)
    return s


def _capture(monkeypatch):
    import tinyassets.api.extensions as ext

    seen: dict = {}

    def _impl(**kw):
        seen.update(kw)
        return json.dumps({"branch_def_id": kw.get("branch_def_id"), "status": "deleted"})

    monkeypatch.setattr(ext, "_extensions_impl", _impl)
    return seen


def test_served_delete_forwards_to_the_guarded_handler(monkeypatch):
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)

    out = json.loads(s.write_graph(target="branch", operation="delete", branch_id="b-1"))

    assert out["status"] == "deleted"
    assert seen["action"] == "delete_own_branch", seen
    assert seen["branch_def_id"] == "b-1"


def test_served_delete_requires_branch_id(monkeypatch):
    s = _bind(monkeypatch)
    seen = _capture(monkeypatch)

    out = json.loads(s.write_graph(target="branch", operation="delete"))

    assert "error" in out and "branch_id" in out["error"]
    assert seen == {}, "the handler was reached without a branch id"


def test_served_surface_advertises_delete(monkeypatch):
    s = _bind(monkeypatch)
    _capture(monkeypatch)
    out = json.loads(s.write_graph(target="branch", operation="destroy", branch_id="b-1"))
    assert "delete" in out["error"], "the refusal does not name the operation that exists"
    import inspect

    assert "delete" in (inspect.getdoc(s.write_graph) or "").lower()
