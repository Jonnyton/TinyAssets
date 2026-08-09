"""Self-patch: assemble a github_pull_request packet from the node's declaration.

Live 2026-08-09 ("he is able to patch himself"): u-tiny's self-patch branch
generated the file content correctly but the run always ended at
``no_matching_packet`` and no PR was opened — the github_pull_request effector
required the LLM to emit a literal ``external_write_packet`` JSON, which prompt
nodes refuse (the same issue solved for twitter_post). These pin the handoff→PR
packet assembly and the dispatcher fallback.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def base(tmp_path):
    from tinyassets.daemon_server import initialize_author_server

    initialize_author_server(str(tmp_path))
    (tmp_path / "u-a").mkdir(exist_ok=True)
    return tmp_path


_GH_DECLARATION = {
    "output_field": "changelog_content",
    "adapter": "raw",
    "adapter_action": "github_pull_request",
    "destination": "jonnyton/tinyassets",
    "effect_class": "reversible",
    "outcome_kind": "pull_request",
    "params": {
        "base_branch": "main",
        "draft": True,
        "file_path": "CHANGELOG.md",
        "head_branch": "auto/add-changelog",
        "title": "chore: add CHANGELOG.md",
    },
}


class _GHNode:
    def __init__(self, handoffs):
        self.node_id = "write_and_pr"
        self.output_keys = ["changelog_content"]
        self.effects = ["github_pull_request"]
        self.handoffs = handoffs


def test_packet_from_handoffs_builds_a_github_pr_packet():
    from tinyassets.effectors.github_pr import packet_from_handoffs

    packet = packet_from_handoffs(
        _GHNode([_GH_DECLARATION]),
        {"changelog_content": "# Changelog\n\n- init"},
    )
    assert packet == {
        "sink": "github_pull_request",
        "destination": "jonnyton/tinyassets",
        "payload": {
            "changes_json": {"CHANGELOG.md": "# Changelog\n\n- init"},
            "base_branch": "main",
            "title": "chore: add CHANGELOG.md",
            "draft": True,
            "head_branch": "auto/add-changelog",
        },
    }


def test_github_assembly_needs_a_declaration_content_and_a_path():
    from tinyassets.effectors.github_pr import packet_from_handoffs

    # No declaration at all.
    assert packet_from_handoffs(_GHNode([]), {"changelog_content": "x"}) is None
    # Declared, but the output field holds no text.
    assert (
        packet_from_handoffs(_GHNode([_GH_DECLARATION]), {"changelog_content": ""})
        is None
    )
    # A twitter handoff is not a github one.
    other = dict(_GH_DECLARATION, adapter="twitter_post", adapter_action="post")
    assert packet_from_handoffs(_GHNode([other]), {"changelog_content": "x"}) is None
    # No file path named → nothing to write.
    nopath = dict(_GH_DECLARATION, params={"base_branch": "main"})
    assert packet_from_handoffs(_GHNode([nopath]), {"changelog_content": "x"}) is None


def test_ambiguous_multiple_github_handoffs_are_refused():
    # Codex 2026-08-09: two github_pull_request declarations must NOT collapse to
    # the first — a wrong-repo write is worse than no write. Refuse (None).
    from tinyassets.effectors.github_pr import packet_from_handoffs

    second = dict(_GH_DECLARATION, destination="someone/else")
    got = packet_from_handoffs(
        _GHNode([_GH_DECLARATION, second]), {"changelog_content": "x"}
    )
    assert got is None


def test_draft_defaults_true_when_params_omit_it():
    from tinyassets.effectors.github_pr import packet_from_handoffs

    decl = dict(_GH_DECLARATION, params={"file_path": "X.md", "head_branch": "h"})
    packet = packet_from_handoffs(_GHNode([decl]), {"changelog_content": "hi"})
    assert packet["payload"]["draft"] is True
    assert packet["payload"]["base_branch"] == "main"  # sensible default


def test_dispatcher_assembles_github_pr_packet_from_handoff(base):
    """End to end through run_effects_for_branch: a node whose output is plain
    file content still reaches the PR effector via the declaration — getting PAST
    no_matching_packet to the authority/gate stage (which is where the earlier
    self-patch attempts should have reached, not a dead 'no packet')."""
    from tinyassets.effectors.github_pr import run_effects_for_branch

    class _Branch:
        node_defs = [_GHNode([_GH_DECLARATION])]

    results = run_effects_for_branch(
        branch=_Branch(),
        run_state={"changelog_content": "# Changelog\n\n- init"},
        base_path=base / "u-a",
        run_id="r_gh_assembly",
    )
    ev = results["write_and_pr"]["github_pull_request"]
    assert ev.get("error_kind") != "no_matching_packet"
    assert ev.get("packet_assembled_from_handoff") is True


def test_package_wrapper_carries_handoffs_for_github_pr(base):
    """Production takes the package-level wrapper, which rebuilds each node as a
    SimpleNamespace — it must carry handoffs or github self-patch assembles
    nothing (the same trap that bit twitter_post live)."""
    from tinyassets.effectors import run_effects_for_branch

    class _Branch:
        node_defs = [_GHNode([_GH_DECLARATION])]

    results = run_effects_for_branch(
        branch=_Branch(),
        run_state={"changelog_content": "# Changelog\n\n- init"},
        base_path=base / "u-a",
        run_id="r_gh_wrapper",
    )
    ev = results["write_and_pr"]["github_pull_request"]
    assert ev.get("error_kind") != "no_matching_packet"
    assert ev.get("packet_assembled_from_handoff") is True
