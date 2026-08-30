"""A run whose declared effect failed must not report a clean success.

Observed live 2026-08-29. The universe was asked to open a one-line PR. It built
the branch, launched run ``cf350418157949cd``, and the run reported::

    status: completed
    error:  ""
    nodes:  plan_change -> ran, open_pr -> ran

No pull request existed. No branch existed. No GitHub call appeared in the daemon
log across the whole window. The node had declared ``effects:
["github_pull_request"]`` — a sink that is NOT in the registry, which holds only
``authenticated_external_call`` and ``wiki_write_back`` — so the dispatcher
recorded ``unknown effect sink: github_pull_request`` and the run reported
success anyway.

The failure was never lost: ``_collect_external_write_errors`` already gathered
it into ``output["external_write_errors"]``. It was then discarded by an
unconditional ``error=""`` on the very next line. So every observer that reads a
run's ``error`` — the universe that launched it included — was told it worked.

This is Hard Rule 8 at the exact line where it was broken.
"""

from __future__ import annotations

from tinyassets.runs import (
    _collect_external_write_errors,
    _external_write_error_summary,
)


def _evidence(**per_sink):
    return {"open_pr": dict(per_sink)}


def test_an_unknown_sink_produces_a_summary_naming_it():
    """The live case: a node declaring a sink the registry does not have."""
    errors = _collect_external_write_errors(
        _evidence(
            github_pull_request={
                "error": "unknown effect sink: github_pull_request",
                "error_kind": "unknown_sink",
            }
        )
    )
    assert errors, "the dispatcher's error was not collected"
    summary = _external_write_error_summary(errors)
    assert "github_pull_request" in summary
    assert "open_pr" in summary, "the summary must name the node"
    assert summary, "an empty summary is the bug"


def test_a_refused_call_produces_a_summary():
    """The other live case: the call fired and the destination refused it."""
    errors = _collect_external_write_errors(
        _evidence(
            authenticated_external_call={
                "error": "connection authority refused: missing_consent",
                "error_kind": "missing_consent",
            }
        )
    )
    summary = _external_write_error_summary(errors)
    assert "missing_consent" in summary
    assert "authenticated_external_call" in summary


def test_a_clean_effect_yields_no_error_rows():
    """A run that really did its work must stay clean."""
    errors = _collect_external_write_errors(
        _evidence(authenticated_external_call={"delivered": True, "response": {}})
    )
    assert errors == []


def test_the_summary_is_bounded():
    """A pathological branch must not put a wall of text in the run's error."""
    errors = [
        {"node_id": f"n{i}", "sink": "s", "error": "boom", "error_kind": "x"}
        for i in range(20)
    ]
    summary = _external_write_error_summary(errors)
    assert "+15 more" in summary
    assert len(summary) < 500


def test_the_error_field_is_wired_at_both_call_sites():
    """Structural: the fix is worthless if only one of the two paths carries it.

    Both effector call sites in ``runs.py`` previously ended with a hardcoded
    ``error=""``. This pins that neither of them silently returns to that.
    """
    import inspect

    from tinyassets import runs

    source = inspect.getsource(runs)
    assert source.count("error=effect_error,") == 4, (
        "expected each call site to pass effect_error to BOTH update_run_status "
        "and RunOutcome"
    )
    assert 'output=output, error="",' not in source, (
        "a call site still hardcodes an empty error, which is the original bug"
    )


# --- a dead sink must say what to use instead --------------------------------


def test_an_unknown_sink_names_the_supported_sinks():
    """"Unknown effect sink" alone is not actionable.

    A branch stored before a per-channel sink was retired keeps naming it every
    run, and the node silently does nothing. The live case was a stored
    "Docs Touch PR" branch still declaring `github_pull_request`. The platform
    ships exactly two sinks on purpose, so the remedy is always the same shape
    and the error can just say it.
    """
    from tinyassets.effectors import run_effects_for_branch

    class _Node:
        node_id = "open_pr"
        effects = ["github_pull_request"]
        output_keys = ["delivery_receipt"]

    class _Branch:
        node_defs = [_Node()]

    evidence = run_effects_for_branch(
        branch=_Branch(), run_state={}, base_path=None, run_id="r1"
    )
    row = evidence["open_pr"]["github_pull_request"]

    assert row["error_kind"] == "unknown_sink"
    assert row["supported_sinks"] == [
        "authenticated_external_call",
        "wiki_write_back",
    ]
    assert "does nothing" in row["error"], "must say the node is a no-op"
    assert "Rebuild" in row["error"], "must say what to do about it"
    assert "authenticated_external_call" in row["error"]
    assert "external_write_packet" in row["error"], "must name the packet shape"


def test_a_known_sink_is_untouched_by_the_unknown_sink_path():
    """The guard must not change behaviour for a sink that exists."""
    from tinyassets.effectors import run_effects_for_branch

    class _Node:
        node_id = "call"
        effects = ["authenticated_external_call"]
        output_keys = []

    class _Branch:
        node_defs = [_Node()]

    evidence = run_effects_for_branch(
        branch=_Branch(), run_state={}, base_path=None, run_id="r1"
    )
    row = evidence["call"]["authenticated_external_call"]
    assert row.get("error_kind") != "unknown_sink"


def _branch_with_one_call(node_id="call_github"):
    class _Node:
        effects = ["authenticated_external_call"]
        output_keys = []

    _Node.node_id = node_id

    class _Branch:
        node_defs = [_Node()]

    return _Branch()


def test_a_far_side_refusal_reaches_the_log(monkeypatch, caplog):
    """Concern 2026-08-28: GitHub answered 403, the run said `completed`, and
    the daemon log said nothing for 25 minutes. One warning per refused
    outbound call, naming run, node, status and the first bytes of the body."""
    import logging

    from tinyassets import effectors

    def refused(**_kw):
        return {
            "delivered": True,
            "verb": "POST",
            "response": {
                "status": 403,
                "body": '{"message":"Resource not accessible by personal access token"}',
                "headers": {"x-accepted-github-permissions": "contents=write"},
            },
        }

    monkeypatch.setitem(effectors._EFFECTORS, "authenticated_external_call", refused)
    with caplog.at_level(logging.WARNING, logger="tinyassets.effectors"):
        effectors.run_effects_for_branch(
            branch=_branch_with_one_call(), run_state={}, base_path=None, run_id="r403"
        )
    lines = [r.getMessage() for r in caplog.records if "far side" in r.getMessage()]
    assert len(lines) == 1, caplog.text
    for part in ("run=r403", "node=call_github", "status=403", "Resource not accessible"):
        assert part in lines[0]


def test_a_packet_refused_before_the_wire_reaches_the_log(monkeypatch, caplog):
    import logging

    from tinyassets import effectors

    monkeypatch.setitem(
        effectors._EFFECTORS,
        "authenticated_external_call",
        lambda **_kw: {"delivered": False, "error_kind": "missing_consent"},
    )
    with caplog.at_level(logging.WARNING, logger="tinyassets.effectors"):
        effectors.run_effects_for_branch(
            branch=_branch_with_one_call("ask"), run_state={}, base_path=None, run_id="rmc"
        )
    lines = [r.getMessage() for r in caplog.records if "did not fire" in r.getMessage()]
    assert len(lines) == 1 and "kind=missing_consent" in lines[0] and "node=ask" in lines[0]


def test_a_clean_delivery_logs_nothing(monkeypatch, caplog):
    import logging

    from tinyassets import effectors

    monkeypatch.setitem(
        effectors._EFFECTORS,
        "authenticated_external_call",
        lambda **_kw: {
            "delivered": True, "verb": "POST", "response": {"status": 201, "body": "{}"}
        },
    )
    with caplog.at_level(logging.WARNING, logger="tinyassets.effectors"):
        effectors.run_effects_for_branch(
            branch=_branch_with_one_call(), run_state={}, base_path=None, run_id="rok"
        )
    assert not [r for r in caplog.records if "external effect" in r.getMessage()]
