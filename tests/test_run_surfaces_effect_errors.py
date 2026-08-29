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
