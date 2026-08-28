"""Running a branch requires being allowed to READ it.

The scope check on `run_branch` establishes that the caller may WRITE to the universe
the run is recorded under -- their own. It says nothing about the branch being run.

`_resolve_branch_id` passes an unresolvable selector THROUGH so the caller's KeyError
handler can report "not found". That is right for a branch that does not exist, and
wrong for one that exists and is private: the raw load succeeds, the run executes
someone else's content, and the output is filed under the caller's universe.
"""

from __future__ import annotations

import pathlib

from tinyassets.api import branches, runs


def test_a_readable_branch_still_resolves(monkeypatch):
    monkeypatch.setattr(
        branches, "_resolve_readable_branch", lambda sel, base: ("bd-ok", {"x": 1})
    )
    assert branches.resolve_branch_id_for_read("bd-ok", "/base") == "bd-ok"


def test_an_unreadable_branch_resolves_to_None_not_to_itself(monkeypatch):
    """The whole bug in one assertion."""
    monkeypatch.setattr(branches, "_resolve_readable_branch", lambda sel, base: None)
    assert branches.resolve_branch_id_for_read("bd-private", "/base") is None
    # The permissive sibling still passes through -- that is its documented job, and
    # it is why the run path must not use it.
    assert branches._resolve_branch_id("bd-private", "/base") == "bd-private"


def test_the_run_path_uses_the_read_checked_resolver():
    """Asserted against the source: the bug was WHICH resolver got called."""
    src = pathlib.Path(runs.__file__).read_text(encoding="utf-8")
    body = src.split("def _action_run_branch(")[1].split("\ndef ")[0]
    assert "resolve_branch_id_for_read" in body, (
        "run_branch must resolve through the read-checked resolver"
    )
    assert "_resolve_branch_id(" not in body, (
        "the permissive resolver passes an unreadable id straight through"
    )


def test_the_read_check_happens_before_the_branch_is_loaded():
    """Order is the property. Checking after the load has already disclosed it."""
    src = pathlib.Path(runs.__file__).read_text(encoding="utf-8")
    body = src.split("def _action_run_branch(")[1].split("\ndef ")[0]
    check_at = body.index("resolve_branch_id_for_read")
    load_at = body.index("get_branch_definition(")
    assert check_at < load_at


def test_an_unreadable_branch_is_reported_as_not_found(monkeypatch):
    """Saying 'exists but not yours' is itself a disclosure."""
    import json

    monkeypatch.setattr(runs, "_ensure_runs_recovery", lambda: None)
    monkeypatch.setattr(runs, "_run_actor_for_kwargs", lambda kw: "actor-a")
    monkeypatch.setattr(runs, "_base_path", lambda: "/base")
    monkeypatch.setattr(
        branches, "resolve_branch_id_for_read", lambda sel, base: None
    )

    out = json.loads(runs._action_run_branch({"branch_def_id": "bd-someone-elses"}))
    assert "not found" in out["error"]
    assert "private" not in out["error"].lower()
    assert "permission" not in out["error"].lower()
