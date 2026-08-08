"""The five workflow shapes, as remixable starting points.

Every spec must be VALID against the real validator's rules, or a template is a
trap: the user starts from it and gets a rejection they did not cause.
"""

from __future__ import annotations

import pytest

from tinyassets.branch_templates import TEMPLATES, list_templates, template_spec


def test_all_five_patterns_are_present():
    assert set(TEMPLATES) == {
        "sequential", "routing", "parallel",
        "orchestrator_worker", "evaluator_optimizer",
    }


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_every_template_declares_an_entry_point(name):
    """Required once a branch has nodes — the validator's first complaint."""
    spec = template_spec(name)
    assert spec["entry_point"]
    assert spec["entry_point"] in {n["node_id"] for n in spec["nodes"]}


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_every_edge_uses_from_and_to(name):
    """`source`/`target` is silently wrong — the validator rejects it."""
    for edge in template_spec(name)["edges"]:
        assert set(edge) == {"from", "to"}, edge


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_every_path_reaches_END(name):
    """Otherwise: 'nodes in cycle without exit condition'."""
    spec = template_spec(name)
    assert any(e["to"] == "END" for e in spec["edges"]), name


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_every_edge_names_a_real_node(name):
    spec = template_spec(name)
    ids = {n["node_id"] for n in spec["nodes"]} | {"END"}
    for edge in spec["edges"]:
        assert edge["from"] in ids, edge
        assert edge["to"] in ids, edge


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_every_prompt_placeholder_is_a_declared_input(name):
    """A prompt referencing an undeclared key fails to COMPILE at run time.

    This is the failure that cost a whole live round: "references declared
    input_keys ['topic'] that are not present in state".
    """
    import re

    spec = template_spec(name)
    produced = {k for n in spec["nodes"] for k in n.get("output_keys", [])}
    for node in spec["nodes"]:
        declared = set(node.get("input_keys", [])) | produced
        for placeholder in re.findall(r"\{(\w+)\}", node["prompt_template"]):
            assert placeholder in declared, f"{name}/{node['node_id']}: {placeholder}"


def test_listing_names_the_inputs_a_user_must_supply():
    """What the automation has to provide — outputs are produced, not supplied."""
    listed = {item["template"]: item for item in list_templates()}
    assert listed["sequential"]["inputs"] == ["topic"]
    assert "findings" not in listed["sequential"]["inputs"]


def test_a_template_is_a_copy_not_the_shared_dict():
    """A caller edits before building; edits must not leak to the next reader."""
    first = template_spec("sequential")
    first["name"] = "mutated"
    first["nodes"][0]["prompt_template"] = "clobbered"
    assert template_spec("sequential")["name"] == "sequential_starter"
    assert "clobbered" not in template_spec("sequential")["nodes"][0]["prompt_template"]


def test_an_unknown_template_raises():
    with pytest.raises(KeyError):
        template_spec("does_not_exist")
