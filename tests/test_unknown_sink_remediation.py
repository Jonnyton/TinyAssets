"""An unknown sink must name the way forward, not just the refusal.

Found live 2026-08-28: the founder's universe tried `github_pull_request` and got
`unknown_sink`, then reported its PR path as "not executable yet". The sink was
removed in the channel-agnostic rebuild (#2451) and is never coming back — the
universe simply had no way to learn that from the error.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tinyassets.effectors import run_effects_for_branch


def _refusal(sink: str) -> dict:
    node = SimpleNamespace(node_id="n1", effects=[sink], output_keys=[])
    branch = SimpleNamespace(node_defs=[node])
    return run_effects_for_branch(branch=branch, run_state={}, run_id="r1")["n1"][sink]


@pytest.mark.parametrize(
    "retired", ["github_pull_request", "slack_message", "x_post", "desktop_notify"]
)
def test_a_retired_per_channel_sink_is_told_what_to_use_instead(retired):
    result = _refusal(retired)

    assert result["error_kind"] == "unknown_sink"
    # The way forward, not just the refusal.
    assert "authenticated_external_call" in result["remediation"]
    assert retired in result["remediation"]


def test_the_refusal_enumerates_what_is_actually_valid():
    result = _refusal("github_pull_request")
    assert result["valid_sinks"] == ["authenticated_external_call", "wiki_write_back"]


def test_a_valid_sink_is_not_refused():
    """Guard against the remediation path swallowing real sinks."""
    node = SimpleNamespace(node_id="n1", effects=["wiki_write_back"], output_keys=[])
    branch = SimpleNamespace(node_defs=[node])
    result = run_effects_for_branch(branch=branch, run_state={}, run_id="r1")["n1"][
        "wiki_write_back"
    ]
    assert result.get("error_kind") != "unknown_sink"
