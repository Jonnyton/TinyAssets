"""Tests for the workflow-builder framing + no-simulation rule.

Tasks #27, #28, #34 are text-only fixes to Universe Server prompts and
tool descriptions. The risk isn't that the text is wrong today — it's
that someone later edits the copy back to fiction-only framing or drops
the anti-simulation clause without realizing those lines are load-bearing.

These tests pin the behavioral claims. Copy can be rewritten freely as
long as the guarded intents stay present.
"""

from __future__ import annotations

import asyncio
import re

from tinyassets.universe_server import mcp


def _list_tools():
    return asyncio.run(mcp.list_tools(run_middleware=False))


def _list_prompts():
    return asyncio.run(mcp.list_prompts(run_middleware=False))


def test_server_instructions_lead_with_workflow_builder_not_fiction() -> None:
    """#28: instructions must frame the server as a general workflow
    platform, not "primarily for fiction". Fantasy is a benchmark.
    """
    text = (mcp.instructions or "").lower()
    # TinyAssets builder framing must appear — and appear before the word
    # "fiction" (which is allowed as an example, not the lead).
    assert "workflow builder" in text
    # At least one non-fiction example domain must appear so the bot
    # knows recipe trackers / research / planners are in scope.
    example_domains = [
        "research", "recipe", "screenplay", "journalism",
        "wedding", "news summariz",
    ]
    assert any(d in text for d in example_domains), (
        "server instructions should name at least one non-fiction example"
    )
    # General-purpose framing must remain explicit even if the copy no longer
    # phrases that as a negation of fantasy/fiction.
    assert "domain-agnostic" in text, (
        "instructions must explicitly frame TinyAssets as domain-agnostic"
    )


def test_server_instructions_point_to_control_station_prompt() -> None:
    """#15 (post-c97feac relocation): server instructions no longer carry
    the NO SIMULATION block directly — that moved to control_station's
    @mcp.prompt return to reduce the lexical surface Claude.ai's
    injection-mitigation heuristic crystallizes around. Server instructions
    must instead direct the client to load the canonical prompt.

    Rationale: docs/design-notes/2026-04-18-claude-ai-injection-
    hallucination.md §5.1, docs/audits/2026-04-18-universe-server-
    directive-relocation-plan.md §3.
    """
    text = mcp.instructions or ""
    lower = text.lower()
    # Must point to the control_station prompt as the canonical
    # behavioral surface.
    assert "control_station" in lower, (
        "server instructions must direct clients to the control_station prompt"
    )
    # Handshake points at the canonical prompt; it must not carry a hard-rule
    # block itself.
    assert "universe isolation" in lower
    assert "hard rule" not in lower
    assert "never transfer" not in lower
    assert len(text) < 1600


def test_extensions_tool_description_points_to_prompts_for_rules() -> None:
    """#15 (post-c97feac): the extensions tool description no longer
    carries the NO SIMULATION / INTENT DISAMBIGUATION / AFFIRMATIVE CONSENT
    blocks. Description is I/O contract only; behavioral rules live in
    control_station + extension_guide prompts. Description must cite
    those prompts.
    """
    tool = next(t for t in _list_tools() if t.name == "extensions")
    text = (tool.description or "").lower()
    # Must reference the prompts that carry the behavioral guidance.
    assert "control_station" in text or "extension_guide" in text
    # Still name core action surface so the bot can find it.
    assert "run_branch" in text
    assert "build_branch" in text
    assert "no simulation" not in text
    assert "affirmative consent" not in text
    assert len(tool.description or "") < 900


def test_wiki_tool_description_is_not_a_catchall() -> None:
    """#27: wiki must explicitly refuse the "save anything" role when a
    user wants workflow structure, state, or task tracking. Route them
    to `extensions` instead.
    """
    tool = next(t for t in _list_tools() if t.name == "wiki")
    text = tool.description or ""
    lower = text.lower()
    compact = re.sub(r"\s+", " ", lower)
    # Scope negation — wiki is NOT for workflow structure / state.
    assert (
        "not for workflow" in compact
        or "save anything" in compact
    )
    # Explicit routing guidance to `extensions`.
    assert "extensions" in lower
    # Name at least one misuse pattern we want the bot to recognize.
    assert "build / design / create a workflow" in lower or "build a workflow" in lower


def test_universe_tool_description_is_general_not_fiction_only() -> None:
    """#28 post-4ef0769 (universe docstring trimmed to ≤6 lines + Args):
    the multi-domain example list moved to control_station prompt (which
    is the canonical framing surface). Universe tool description must
    still avoid fiction-only framing but gets the breadth via pointer
    to control_station.
    """
    tool = next(t for t in _list_tools() if t.name == "universe")
    text = (tool.description or "").lower()
    # Must cite control_station as the framing + operating-guidance source.
    assert "control_station" in text
    # Not fiction-only — generic workspace framing.
    assert "workflow" in text or "workspace" in text
    # No fiction-exclusive framing.
    assert "only for fiction" not in text
    assert "hard rule" not in text
    assert len(tool.description or "") < 2200


def test_control_station_prompt_carries_the_rules() -> None:
    """#27/#28/#34 post-4ef0769: the prompt a control-station client loads
    must carry workflow-builder framing, routing guidance, and the
    never-simulate rule. Copy may be rephrased (4ef0769 moved hard rule 5
    to sentence-case + dropped 'Silently simulating breaks user trust'
    distinctive lexical fingerprint).
    """
    from tinyassets.api.prompts import _CONTROL_STATION_PROMPT
    text = _CONTROL_STATION_PROMPT.lower()
    # Broad framing.
    assert "workflow builder" in text or "workflow" in text
    assert (
        "benchmark" in text
        or "not the exclusive" in text
        or "fully general" in text
        or "domain-agnostic" in text
    )
    # Routing: extensions for workflow design, wiki for knowledge only.
    assert "extensions" in text
    assert "wiki" in text
    # Never-simulate clause — rephrased; positive-phrased "say so plainly
    # and stop" carries the contract post-relocation.
    assert "say so plainly and stop" in text or "no simulation" in text or "fake output" in text
    assert "stop" in text


def test_control_station_promotes_chatbot_builder_behaviors_page() -> None:
    """Navigator D8: build-branch-adjacent work should start from the
    canonical chatbot-builder behavior guide, not stale memory.
    """
    from tinyassets.api.prompts import _CONTROL_STATION_PROMPT

    text = _CONTROL_STATION_PROMPT.lower()
    assert "chatbot-builder-behaviors.md" in text
    assert "canonical chatbot-builder behavior" in text
    assert "wiki action=read" in text
    assert "stale memory" in text


def test_control_station_routes_daemon_memory_actions() -> None:
    """Daemon mini-brain actions must be discoverable from control_station."""
    from tinyassets.api.prompts import _CONTROL_STATION_PROMPT

    text = _CONTROL_STATION_PROMPT
    for action in [
        "daemon_memory_capture",
        "daemon_memory_search",
        "daemon_memory_review",
        "daemon_memory_promote",
        "daemon_memory_status",
    ]:
        assert action in text
    assert "inputs_json" in text
    assert "daemon_id" in text


def test_universe_schema_exposes_daemon_id_for_daemon_memory_actions() -> None:
    """BUG-086: daemon memory status requires daemon_id, so the MCP schema
    must expose a top-level daemon_id field instead of forcing callers through
    hidden inputs_json.
    """
    tool = next(t for t in _list_tools() if t.name == "universe")
    properties = tool.parameters.get("properties", {})
    assert "daemon_id" in properties
    assert "daemon_id" not in tool.parameters.get("required", [])


def test_control_station_routes_treasury_status_as_read_only() -> None:
    """Treasury/cost-ledger status must be discoverable as a read-only route."""
    from tinyassets.api.prompts import _CONTROL_STATION_PROMPT

    text = _CONTROL_STATION_PROMPT
    assert "treasury_status" in text
    assert "read-only" in text.lower()
    assert "no autonomous spend" in text.lower()


def test_extension_guide_prompt_points_to_control_station() -> None:
    """#15 (post-c97feac): _EXTENSION_GUIDE_PROMPT no longer dup'd the
    NO SIMULATION block. It now points to control_station as the
    canonical behavioral surface. Guide focuses on node/branch authoring;
    runtime rules live in control_station.
    """
    from tinyassets.universe_server import _EXTENSION_GUIDE_PROMPT
    text = _EXTENSION_GUIDE_PROMPT.lower()
    assert "control_station" in text, (
        "extension_guide must direct readers to control_station for "
        "runtime rules (never-simulate, intent-disambiguation)"
    )
    # Guide is still about node authoring — keep that content signal.
    assert "node" in text or "branch" in text


def test_control_station_prompts_list_first_for_query_intent() -> None:
    """#42 post-4ef0769: list_branches USE-THIS-FIRST guidance + user-
    phrase enumeration moved from extensions tool description to
    control_station prompt's canonical Intent-Disambiguation section.
    """
    from tinyassets.api.prompts import _CONTROL_STATION_PROMPT
    text = _CONTROL_STATION_PROMPT.lower()
    # list_branches is the query-intent routing target.
    assert "list_branches" in text
    # Query-intent cue phrases enumerated.
    user_phrases = [
        "what do i have",
        "pull up",
        "show me",
        "list my",
        "find my",
    ]
    hits = [p for p in user_phrases if p in text]
    assert len(hits) >= 3, (
        f"control_station must enumerate query-intent cue phrases; "
        f"found: {hits}"
    )


def test_extensions_tool_still_lists_branch_query_actions() -> None:
    """#42 post-4ef0769: describe_branch / get_branch / list_branches
    remain listed as action names in the extensions tool's I/O contract
    description. Preference guidance (use-this-when / use-this-first /
    phone-legibility) moved to prompts.
    """
    tool = next(t for t in _list_tools() if t.name == "extensions")
    text = (tool.description or "").lower()
    # Action names present for discovery.
    assert "describe_branch" in text
    assert "get_branch" in text
    assert "list_branches" in text


def test_branch_design_guide_prompt_covers_branch_authoring() -> None:
    """#42 post-4ef0769: _BRANCH_DESIGN_GUIDE is the canonical author-
    facing prompt for branch design. The describe_vs_get preference
    guidance is light content in the guide; the guide's primary role is
    teaching the branch-authoring contract.
    """
    from tinyassets.api.branches import _BRANCH_DESIGN_GUIDE
    text = _BRANCH_DESIGN_GUIDE.lower()
    # Guide covers branches as the core concept.
    assert "branch" in text
    # References run_branch so authors understand the runtime contract.
    assert "run_branch" in text or "extensions" in text
    assert "batch_receipt" in text
    assert "not an authorization grant" in text
    assert "source_code approval" in text


def test_control_station_pins_register_explicit_ask_rule() -> None:
    """#15 (post-c97feac migration of #46): the affirmative-consent rule
    for `register` moved from the extensions tool description into the
    control_station prompt's canonical Intent-Disambiguation section.
    Test now pins the rule at its new canonical site.

    Tool description retains the action name only; behavioral rule
    (explicit-ask / route-queries-to-list) lives where clients load it
    on orient, not in tool-metadata space.
    """
    from tinyassets.api.prompts import _CONTROL_STATION_PROMPT
    text = _CONTROL_STATION_PROMPT.lower()
    # Intent-disambiguation section carries the rule.
    assert "intent disambiguation" in text or "explicit user" in text
    # register is named as a write that requires explicit ask.
    assert "register" in text
    # Query-intent cues (enumerated at canonical site).
    query_cues = [
        "what do i have", "show me", "list my", "find my", "pull up",
    ]
    hits = [c for c in query_cues if c in text]
    assert len(hits) >= 3, (
        f"control_station must enumerate query-intent phrases at canonical "
        f"site; found: {hits}"
    )
    # "When intent is ambiguous, ask" refusal language must be present.
    assert "ambiguous" in text or "ask" in text


def test_control_station_pins_build_branch_explicit_ask_rule() -> None:
    """#15 (post-c97feac migration of #46): build_branch's affirmative-
    consent rule moved to control_station prompt alongside register's.
    Same canonical site — query-intent routes to list_branches.
    """
    from tinyassets.api.prompts import _CONTROL_STATION_PROMPT
    text = _CONTROL_STATION_PROMPT.lower()
    assert "build_branch" in text or "build" in text
    # list_branches as the query-intent alternative.
    assert "list_branches" in text
    # Explicit-ask language at canonical site.
    assert "explicit" in text or "ambiguous" in text


def test_universe_tool_docstring_points_to_cross_universe_rule() -> None:
    """#15 post-4ef0769: the cross-universe isolation rule moved from the
    universe tool docstring to control_station prompt's canonical section
    (one lexical site, not two). Docstring must still direct the client
    to control_station for the rule.
    """
    tool = next(t for t in _list_tools() if t.name == "universe")
    text = (tool.description or "").lower()
    # Docstring cites control_station as the rule source.
    assert "control_station" in text
    # Universe-isolation concept surfaced (docstring can still name it
    # even while deferring full rule to control_station).
    assert "universe" in text


def test_control_station_prompt_has_cross_universe_section() -> None:
    """#15: control_station must teach the bot NOT to transfer facts
    across universes. Named section so a future reword can't silently
    drop the whole block.
    """
    from tinyassets.api.prompts import _CONTROL_STATION_PROMPT
    text = _CONTROL_STATION_PROMPT.lower()
    # Named section header.
    assert "cross-universe" in text
    # The load-bearing header shape the bot must recognize.
    assert "universe: <id>" in text or "universe:" in text
    # Transfer prohibition.
    assert "never carry facts" in text or "never transfer" in text
    # Ground-truth guidance — tool output over chat memory.
    assert "ground truth" in text


def test_control_station_prompt_has_intent_disambiguation() -> None:
    """#46: control_station must teach the bot to classify intent BEFORE
    picking a tool. Query / Build / Run must each have a clear routing
    rule, and ambiguity must route to ASK, not write.
    """
    from tinyassets.api.prompts import _CONTROL_STATION_PROMPT
    text = _CONTROL_STATION_PROMPT.lower()
    assert "intent disambiguation" in text
    # Each intent class must be present with at least one cue phrase.
    assert "query" in text and "list_branches" in text
    assert "build" in text and ("build_branch" in text or "register" in text)
    assert "run" in text and "run_branch" in text
    # Ambiguity → ASK, not write.
    assert "ask" in text
    assert "never write state on ambiguous intent" in text or "do not write state" in text
    # At least three query-intent cue phrases so a single reword can't
    # erase the routing contract.
    query_cues = ["what do i have", "show me", "list", "find my", "pull up"]
    hits = [c for c in query_cues if c in text]
    assert len(hits) >= 3, (
        f"control_station must enumerate query-intent cues; found: {hits}"
    )


# ---------------------------------------------------------------------------
# Hard rules 7/8/9 pins (commit 27d67d3, LIVE-F1 + LIVE-F2 + LIVE-F3).
# These defensive tests lock the three new hard rules against silent drift.
# Verifier-recommended pattern: parallels test_control_station_prompt_
# has_intent_disambiguation.
# ---------------------------------------------------------------------------


def test_control_station_prompt_has_rule_7_assume_workflow() -> None:
    """LIVE-F1 (Maya): chatbot must assume TinyAssets on plausible intent
    rather than present a disambiguation picker. Rule 7 in control_station
    hard rules.
    """
    from tinyassets.api.prompts import _CONTROL_STATION_PROMPT
    text = _CONTROL_STATION_PROMPT.lower()
    # Aggressive-assume directive present.
    assert "assume workflow" in text or "aggressive assumption is a feature" in text
    # Forbids disambiguation pickers on ambiguous references.
    assert "disambiguation picker" in text or "do not ask" in text
    # Enumerates at least two ambiguous user phrases the rule applies to.
    ambiguous_phrases = [
        "the workflow thing", "the connector", "the thing i added",
        "my builder", "my ai thing",
    ]
    hits = [p for p in ambiguous_phrases if p in text]
    assert len(hits) >= 2, (
        f"Rule 7 must enumerate ambiguous reference phrases; found: {hits}"
    )


def test_control_station_prompt_has_rule_8_no_fabrication() -> None:
    """LIVE-F2 (Maya Yardi BLOCKER): chatbot must not fabricate prior-
    conversation content. Rule 8 in control_station hard rules.
    """
    from tinyassets.api.prompts import _CONTROL_STATION_PROMPT
    text = _CONTROL_STATION_PROMPT.lower()
    # Core fabrication prohibition.
    assert "never fabricate prior-conversation content" in text \
        or "do not reference facts" in text \
        or "pattern-matching a plausible" in text
    # Safe-default: ask, don't assert on uncertainty.
    assert "safe default is to ask" in text or "ask, not" in text \
        or "unsure whether the user" in text


def test_control_station_prompt_has_rule_9_user_vocabulary() -> None:
    """LIVE-F3 (Maya): chatbot must speak in the user's vocabulary, not
    engine-internal terms. Rule 9 in control_station hard rules.
    """
    from tinyassets.api.prompts import _CONTROL_STATION_PROMPT
    text = _CONTROL_STATION_PROMPT.lower()
    # Core user-vocabulary directive.
    assert "speak in the user's vocabulary" in text
    # Names at least some engine-internal terms the rule forbids using
    # before user introduces them.
    forbidden_teaching = ["branch", "canon", "node", "daemon"]
    hits = [t for t in forbidden_teaching if t in text]
    # Rule lists these exactly so it can tell the chatbot what NOT to
    # preemptively teach. Finding ≥2 means the enumeration is intact.
    assert len(hits) >= 2, (
        f"Rule 9 must enumerate forbidden-until-user-introduces terms; "
        f"found: {hits}"
    )
    # Engine-vocabulary exception detected by usage context, not a setting.
    assert "detected by" in text or "usage context" in text or \
        "engine-vocabulary" in text
