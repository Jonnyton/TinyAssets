"""A patch that changes nothing is not a patch.

Tiny spent two sessions failing to rename one branch. First it reported the
rename blocked by a write cap; after the cap was raised tenfold it reported
again, live on 2026-09-03:

    passing `name="TinyAssets PR Builder"` on a patch applied `0` ops and left
    the name unchanged

`set_name` exists and passes the served allowlist, so the rename was never
unsupported. The defect is that a patch carrying no recognisable ops answered
`status: "patched"` with `ops_applied: 0` -- a success receipt for an untouched
branch, which is exactly what Hard Rule 8 forbids.
"""

from __future__ import annotations

import json

import pytest

from tinyassets.engine_mcp_server import _sanitize_served_patch_changes


# --------------------------------------------------------------------------
# the served surface
# --------------------------------------------------------------------------


def test_an_empty_op_list_is_refused_rather_than_reported_as_patched():
    with pytest.raises(ValueError) as raised:
        _sanitize_served_patch_changes([])
    message = str(raised.value)
    assert "at least one op" in message
    # ...and it says what to send, because the caller who got here was one
    # sentence away from succeeding.
    assert '"op": "set_name"' in message


@pytest.mark.parametrize(
    ("payload", "expected_op"),
    [
        ({"name": "TinyAssets PR Builder"}, "set_name"),
        ({"rename_branch": "TinyAssets PR Builder"}, "set_name"),
        ({"rename": "TinyAssets PR Builder"}, "set_name"),
        ({"title": "TinyAssets PR Builder"}, "set_name"),
        ({"description": "a builder"}, "set_description"),
        ({"goal_id": "g-1"}, "set_goal"),
    ],
)
def test_a_field_shaped_payload_is_answered_with_the_op_that_sets_it(
    payload, expected_op,
):
    """The shape a caller reaches for when they think "set these fields".

    Answering only "must be a JSON array of ops" leaves them to guess the
    vocabulary, which is what happened live: tiny tried `rename_branch`, then
    `name=`, and got a dead end both times.
    """
    with pytest.raises(ValueError) as raised:
        _sanitize_served_patch_changes(payload)
    message = str(raised.value)
    assert expected_op in message, message
    # The suggestion is the literal op list, ready to send back.
    suggestion = message.split("send it as ops: ", 1)[1]
    ops = json.loads(suggestion)
    assert ops[0]["op"] == expected_op
    assert list(payload.values())[0] in ops[0].values()


def test_the_suggested_ops_are_accepted_verbatim():
    """The sentence has to be actionable, not merely encouraging: what it hands
    back must survive the sanitizer unchanged."""
    with pytest.raises(ValueError) as raised:
        _sanitize_served_patch_changes({"name": "TinyAssets PR Builder"})
    suggestion = str(raised.value).split("send it as ops: ", 1)[1]

    sanitized = _sanitize_served_patch_changes(json.loads(suggestion))
    assert json.loads(sanitized) == [
        {"op": "set_name", "name": "TinyAssets PR Builder"}
    ]


def test_an_unrelated_dict_still_gets_the_plain_type_error():
    """No invented advice when there is nothing to advise."""
    with pytest.raises(ValueError) as raised:
        _sanitize_served_patch_changes({"nonsense": 1})
    assert "must be a JSON array of ops" in str(raised.value)
    assert "send it as ops" not in str(raised.value)


def test_a_real_rename_still_passes_the_served_surface():
    """The rename was never unsupported, and must stay supported."""
    sanitized = json.loads(
        _sanitize_served_patch_changes(
            [{"op": "set_name", "name": "TinyAssets PR Builder"}]
        )
    )
    assert sanitized == [{"op": "set_name", "name": "TinyAssets PR Builder"}]


# --------------------------------------------------------------------------
# the API beneath it
# --------------------------------------------------------------------------


def test_the_api_refuses_an_empty_change_list_too(tmp_path, monkeypatch):
    """A direct caller gets the same answer: a patch with no ops is rejected,
    not reported as patched."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    from tinyassets.api import branches as br

    result = json.loads(br._ext_branch_patch({
        "branch_def_id": "b-does-not-matter",
        "changes_json": "[]",
    }))
    assert result["status"] == "rejected"
    assert "empty list" in result["error"]
    assert '"op": "set_name"' in result["error"]


def test_the_api_rejects_before_it_resolves_the_branch(tmp_path, monkeypatch):
    """The refusal is about the REQUEST, so it does not depend on the branch
    existing -- and cannot be mistaken for 'branch not found'."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    from tinyassets.api import branches as br

    result = json.loads(br._ext_branch_patch({
        "branch_def_id": "b-nope",
        "changes_json": "[]",
    }))
    assert result["status"] == "rejected"
    assert "not found" not in result["error"].lower()
