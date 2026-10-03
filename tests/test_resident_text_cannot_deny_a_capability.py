"""The text the agent is handed must not deny a capability the platform ships.

Live on prod 2026-10-03: asked to publish, the founder's main agent answered that
it has NO publish action. Nothing was missing -- #4315 had shipped publish as a
pending-request ask and ``write_graph`` was on the served allowlist the whole
time. What the agent read was a sentence that had been true and had silently
become false:

    "Publishing to the commons, changing visibility to public, and forking a
     foreign shape are NOT available here (they stay in the browser flow)"

The agent was obeying its instructions. No test could fail, because every test
asked whether the capability WORKED -- and it did. Nothing asked whether the
agent was told it exists.

So this guard reads the resident text the way the agent receives it and fails
when a capability's own words sit next to a phrase denying that capability
exists. It is deliberately narrow: see ``_DENIALS`` for why "cannot" is not one
of them.

Scope note: this checks the RESIDENT text -- the descriptions re-sent on every
model round-trip, which is what an agent reads before deciding whether it can do
something. A handbook chapter cannot answer a question the agent never asks,
which is exactly how the live bug survived.
"""

from __future__ import annotations

import ast
import asyncio
import pathlib
import re

import pytest

from tinyassets import engine_mcp_server as engine
from tinyassets.served_tools import SERVED_ENGINE_MCP_TOOLS

_PENDING_REQUESTS = (
    pathlib.Path(__file__).resolve().parents[1] / "tinyassets" / "api" / "pending_requests.py"
)

#: Words that NAME a capability, per action kind. A denial phrase next to one of
#: these is the contradiction this guard exists to catch.
CAPABILITY_WORDS: dict[str, tuple[str, ...]] = {
    "publish": ("publish", "publishing", "share", "sharing"),
    "install": ("install", "installing"),
    "bind_model_access": ("model access",),
    "connect": ("connect", "connecting"),
    "connect_http": ("connect_http",),
    "extend_http": ("extend_http",),
    "remove_http": ("remove_http",),
    "rotate_http": ("rotate_http",),
    "grant_workspace_consent": ("workspace consent",),
}

#: Action kinds that are not a capability the agent offers its owner, so there
#: is nothing for the resident text to deny. Each needs a reason a reader can
#: check -- an unexplained entry here is how a guard quietly stops guarding.
NOT_A_CAPABILITY: dict[str, str] = {
    "answer": "the person's half of a request, never the agent's to perform",
    "grant_patch_intake": "the owner's consent to an intake, not an action the agent takes",
}

#: Phrases that claim a capability DOES NOT EXIST. Deliberately not "cannot" or
#: "can't": the resident text correctly says "I cannot publish myself" right
#: beside the publish ask, because publishing needs the person's confirmation.
#: That sentence is true and load-bearing, and a guard that fires on the text
#: doing its job gets suppressed or deleted -- which is worse than no guard.
#: These phrases deny the capability's EXISTENCE; "cannot" describes its SHAPE.
_DENIALS: tuple[str, ...] = (
    "not available",
    "unavailable",
    "stay in the browser",
    "stays in the browser",
    "browser flow",
    "browser step",
    "not supported",
    "no way to",
)

#: Characters either side of a capability word that count as "next to" it. Wide
#: enough to span the sentence the live bug was in, narrow enough to stop at the
#: next bullet. Tuned on that sentence and on the true-statement cases above, so
#: if it ever false-positives the first move is NARROWING it, not adding an
#: exception.
_WINDOW = 160


def _shipped_action_kinds() -> set[str]:
    """Every ``type`` ``_validated_action`` accepts, read from its own source.

    Parsed rather than listed so a new action kind is covered the day it lands.
    A hand-kept list is the same thing that broke: text that was right when it
    was written and nobody revisited.
    """
    tree = ast.parse(_PENDING_REQUESTS.read_text(encoding="utf-8"))
    dispatch = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_validated_action"
    )
    from tinyassets.api import pending_requests

    def _literal(node: ast.AST) -> list[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, ast.Name):
            # The dispatch compares one kind against an imported CONSTANT
            # (PATCH_INTAKE_ACTION), which a literal-only scan cannot see -- so a
            # capability added that way would be silently uncovered, which is the
            # rot this guard exists to catch. Resolved from the module itself.
            value = getattr(pending_requests, node.id, None)
            return [value] if isinstance(value, str) else []
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return [v for element in node.elts for v in _literal(element)]
        return []

    kinds: set[str] = set()
    for node in ast.walk(dispatch):
        if not isinstance(node, ast.Compare) or not isinstance(node.left, ast.Name):
            continue
        if node.left.id != "kind":
            continue
        for comparator in node.comparators:
            kinds.update(_literal(comparator))
    assert "publish" in kinds, (
        "the dispatch no longer reads as `kind == \"...\"`, so this guard is "
        "parsing nothing -- fix the extractor rather than deleting the test")
    return kinds


def _resident_text() -> dict[str, str]:
    """What the agent is handed on every round-trip, per served handle.

    Read through ``mcp.list_tools()`` rather than from module constants: a
    constant would pass even if its handle were unregistered, and the question
    here is what the agent actually receives.
    """
    async def listing() -> dict[str, str]:
        tools = {tool.name: tool for tool in await engine.mcp.list_tools()}
        return {name: (tools[name].description or "")
                for name in SERVED_ENGINE_MCP_TOOLS if name in tools}

    return asyncio.run(listing())


def _contradictions(text: str, words: tuple[str, ...]) -> list[tuple[str, str, str]]:
    found = []
    lowered = text.lower()
    for word in words:
        for match in re.finditer(r"\b" + re.escape(word) + r"\b", lowered):
            start = max(0, match.start() - _WINDOW)
            end = min(len(lowered), match.end() + _WINDOW)
            window = lowered[start:end]
            for denial in _DENIALS:
                if denial in window:
                    found.append((word, denial, window.replace("\n", " ")))
    return found


@pytest.mark.parametrize("kind", sorted(CAPABILITY_WORDS))
def test_the_resident_text_does_not_deny_a_shipped_capability(kind: str) -> None:
    offences = []
    for handle, text in sorted(_resident_text().items()):
        for word, denial, window in _contradictions(text, CAPABILITY_WORDS[kind]):
            offences.append(f"{handle}: {word!r} within {_WINDOW} chars of {denial!r}\n"
                            f"    ...{window.strip()[:240]}...")
    assert not offences, (
        f"the resident text tells the agent that {kind!r} does not exist, and "
        f"api/pending_requests accepts it. An agent that reads a denial stops "
        f"there -- it has no reason to fetch a chapter to check whether the "
        f"denial is still true. Correct the text, or remove the action kind:\n"
        + "\n".join(offences)
    )


def test_every_shipped_action_kind_is_either_keyed_or_explained() -> None:
    """A new capability must not arrive uncovered.

    Keying it costs one line; declaring it not-a-capability costs one line and a
    reason. Doing neither is how this guard would rot into decoration while the
    text drifts again.
    """
    shipped = _shipped_action_kinds()
    accounted = set(CAPABILITY_WORDS) | set(NOT_A_CAPABILITY)
    unaccounted = sorted(shipped - accounted)
    assert not unaccounted, (
        f"action kind(s) {unaccounted} are accepted by api/pending_requests but this "
        "guard says nothing about them. Add the words a person would use for each to "
        "CAPABILITY_WORDS, or add it to NOT_A_CAPABILITY with the reason it is not "
        "something the agent offers its owner."
    )
    stale = sorted(accounted - shipped - {"publish"})
    assert not stale, (
        f"{stale} is keyed here but no longer accepted by api/pending_requests; "
        "drop it so the guard describes what ships")


def test_the_rule_catches_the_sentence_that_caused_the_outage() -> None:
    """Detection control: the scan is not vacuous.

    Without this, every assertion above passes just as well when the matching is
    broken. The string is the one that shipped, verbatim.
    """
    shipped_and_stale = (
        "The edit is transactional (all-or-nothing). Publishing to the commons, "
        "changing visibility to public, and forking a foreign shape are NOT "
        "available here (they stay in the browser flow); a patched source_code "
        "node re-enters UNAPPROVED."
    )
    hits = _contradictions(shipped_and_stale, CAPABILITY_WORDS["publish"])
    assert hits, "the rule no longer catches the sentence it was written for"
    assert {denial for _word, denial, _window in hits} >= {"not available", "browser flow"}


def test_a_true_statement_about_a_capabilitys_shape_is_not_a_denial() -> None:
    """The false positive that would get this guard deleted.

    The resident text says the agent cannot publish unilaterally, immediately
    beside the publish ask. That is true, and it is the sentence that stops the
    agent publishing without asking. It must stay quiet here.
    """
    true_statements = (
        "Sharing it is a ``publish`` ask the person confirms; I cannot publish myself.",
        "ANSWERING is NOT here, and must not be: an exposed answer_request would let "
        "it satisfy its own ask, and an exposed unmute_request would let it lift a mute.",
        "Public ``visibility`` and foreign forks are not on this operation.",
    )
    for sentence in true_statements:
        for words in CAPABILITY_WORDS.values():
            assert not _contradictions(sentence, words), (
                f"a true statement about how a capability works reads as a denial: {sentence!r}")
