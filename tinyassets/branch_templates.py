"""Remixable starting points for the five workflow patterns.

Why these are DATA and not classes
----------------------------------
The AI SDK documents five workflow patterns — sequential chaining, routing,
parallel processing, orchestrator-worker, evaluator-optimizer — and implements
them as code you write with `generateText()`. We already have a strictly more
general substrate: a branch is nodes and edges, and users compose them.

So the useful import is not the implementations, it is the SHAPES. Shipping them
as platform classes would be the bundled-workflow trap ("crypto trading" and
"CRM" become platform features); shipping them as branch specs a user remixes is
the commons working as designed.

Observed 2026-08-07: asked for a niche watcher, the agent composed a two-node
branch from nothing because there was nothing to start from. A power user should
begin from a working shape and change it, which is faster than describing one
from scratch and much faster than building the platform themselves.

Every spec here is valid against the live validator: `entry_point` is required
once there are nodes, edges use ``from``/``to`` (not ``source``/``target``), and
every path must reach ``END`` or it is a cycle without an exit.
"""

from __future__ import annotations

from typing import Any

#: name -> (what it is for, spec)
TEMPLATES: dict[str, dict[str, Any]] = {
    "sequential": {
        "purpose": (
            "Do one thing, then the next, each using what came before. The "
            "default shape for 'gather, then think, then write'."
        ),
        "spec": {
            "name": "sequential_starter",
            "description": "Gather, then draft from what was gathered.",
            "entry_point": "gather",
            "nodes": [
                {
                    "node_id": "gather",
                    "display_name": "Gather",
                    "input_keys": ["topic"],
                    "output_keys": ["findings"],
                    "prompt_template": (
                        "Find the most notable current information about: "
                        "{topic}. List concrete findings, no preamble."
                    ),
                },
                {
                    "node_id": "draft",
                    "display_name": "Draft",
                    "input_keys": ["findings"],
                    "output_keys": ["draft"],
                    "prompt_template": (
                        "Write a short, plain piece from these findings:\n"
                        "{findings}"
                    ),
                },
            ],
            "edges": [
                {"from": "gather", "to": "draft"},
                {"from": "draft", "to": "END"},
            ],
        },
    },
    "routing": {
        "purpose": (
            "Classify the input first, then handle it the way that KIND of "
            "input deserves. Use when the work differs by what arrived."
        ),
        "spec": {
            "name": "routing_starter",
            "description": "Classify, then handle according to the class.",
            "entry_point": "classify",
            "nodes": [
                {
                    "node_id": "classify",
                    "display_name": "Classify",
                    "input_keys": ["request"],
                    "output_keys": ["kind"],
                    "prompt_template": (
                        "Classify this request into one short lowercase label "
                        "describing what KIND of work it needs. Reply with the "
                        "label only.\n\n{request}"
                    ),
                },
                {
                    "node_id": "handle",
                    "display_name": "Handle",
                    "input_keys": ["request", "kind"],
                    "output_keys": ["result"],
                    "prompt_template": (
                        "This is a {kind} request. Handle it appropriately for "
                        "that kind.\n\n{request}"
                    ),
                },
            ],
            "edges": [
                {"from": "classify", "to": "handle"},
                {"from": "handle", "to": "END"},
            ],
        },
    },
    "parallel": {
        "purpose": (
            "Look at the same thing from several angles at once, then "
            "synthesise. Use for reviews, audits, second opinions."
        ),
        "spec": {
            "name": "parallel_starter",
            "description": "Independent perspectives, then a synthesis.",
            "entry_point": "split",
            "nodes": [
                {
                    "node_id": "split",
                    "display_name": "Frame the question",
                    "input_keys": ["subject"],
                    "output_keys": ["framing"],
                    "prompt_template": "State plainly what is being assessed: {subject}",
                },
                {
                    "node_id": "angle_a",
                    "display_name": "First angle",
                    "input_keys": ["framing"],
                    "output_keys": ["view_a"],
                    "prompt_template": "Assess for correctness:\n{framing}",
                },
                {
                    "node_id": "angle_b",
                    "display_name": "Second angle",
                    "input_keys": ["framing"],
                    "output_keys": ["view_b"],
                    "prompt_template": "Assess for risk:\n{framing}",
                },
                {
                    "node_id": "synthesise",
                    "display_name": "Synthesise",
                    "input_keys": ["view_a", "view_b"],
                    "output_keys": ["verdict"],
                    "prompt_template": (
                        "Reconcile these two assessments into one verdict, "
                        "naming any disagreement rather than averaging it.\n\n"
                        "A:\n{view_a}\n\nB:\n{view_b}"
                    ),
                },
            ],
            "edges": [
                {"from": "split", "to": "angle_a"},
                {"from": "split", "to": "angle_b"},
                {"from": "angle_a", "to": "synthesise"},
                {"from": "angle_b", "to": "synthesise"},
                {"from": "synthesise", "to": "END"},
            ],
        },
    },
    "orchestrator_worker": {
        "purpose": (
            "Plan the work, then do each piece, then assemble. Use when the "
            "shape of the job is not known until you have looked at it."
        ),
        "spec": {
            "name": "orchestrator_starter",
            "description": "Plan, execute the plan, assemble the result.",
            "entry_point": "plan",
            "nodes": [
                {
                    "node_id": "plan",
                    "display_name": "Plan",
                    "input_keys": ["goal"],
                    "output_keys": ["plan"],
                    "prompt_template": (
                        "Break this goal into the smallest set of concrete "
                        "steps that would actually achieve it:\n{goal}"
                    ),
                },
                {
                    "node_id": "execute",
                    "display_name": "Execute",
                    "input_keys": ["plan"],
                    "output_keys": ["work"],
                    "prompt_template": "Carry out each step and show the result:\n{plan}",
                },
                {
                    "node_id": "assemble",
                    "display_name": "Assemble",
                    "input_keys": ["work"],
                    "output_keys": ["result"],
                    "prompt_template": "Assemble this into one coherent result:\n{work}",
                },
            ],
            "edges": [
                {"from": "plan", "to": "execute"},
                {"from": "execute", "to": "assemble"},
                {"from": "assemble", "to": "END"},
            ],
        },
    },
    "evaluator_optimizer": {
        "purpose": (
            "Produce something, judge it against criteria, improve it. Use "
            "when quality matters more than speed."
        ),
        "spec": {
            "name": "evaluator_starter",
            "description": "Draft, critique, revise.",
            "entry_point": "draft",
            "nodes": [
                {
                    "node_id": "draft",
                    "display_name": "Draft",
                    "input_keys": ["brief"],
                    "output_keys": ["draft"],
                    "prompt_template": "Produce a first version from:\n{brief}",
                },
                {
                    "node_id": "critique",
                    "display_name": "Critique",
                    "input_keys": ["draft", "brief"],
                    "output_keys": ["critique"],
                    "prompt_template": (
                        "Judge this against the brief. Name concrete faults, "
                        "not encouragement.\n\nBrief:\n{brief}\n\nDraft:\n{draft}"
                    ),
                },
                {
                    "node_id": "revise",
                    "display_name": "Revise",
                    "input_keys": ["draft", "critique"],
                    "output_keys": ["final"],
                    "prompt_template": (
                        "Revise the draft to answer every fault named.\n\n"
                        "Draft:\n{draft}\n\nFaults:\n{critique}"
                    ),
                },
            ],
            "edges": [
                {"from": "draft", "to": "critique"},
                {"from": "critique", "to": "revise"},
                {"from": "revise", "to": "END"},
            ],
        },
    },
}


def list_templates() -> list[dict[str, Any]]:
    """Name, purpose and node shape of each starting point."""
    return [
        {
            "template": name,
            "purpose": entry["purpose"],
            "nodes": [node["node_id"] for node in entry["spec"]["nodes"]],
            "inputs": sorted(
                {
                    key
                    for node in entry["spec"]["nodes"]
                    for key in node.get("input_keys", [])
                }
                - {
                    key
                    for node in entry["spec"]["nodes"]
                    for key in node.get("output_keys", [])
                }
            ),
        }
        for name, entry in sorted(TEMPLATES.items())
    ]


def template_spec(name: str) -> dict[str, Any]:
    """The full spec for one template, ready to hand to branch build."""
    entry = TEMPLATES.get((name or "").strip().lower())
    if entry is None:
        raise KeyError(name)
    # A copy: a caller edits this before building, and a shared dict would leak
    # one user's edits into the next reader's template.
    import copy

    return copy.deepcopy(entry["spec"])


__all__ = ["TEMPLATES", "list_templates", "template_spec"]
