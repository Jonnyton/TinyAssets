"""Tests for the ASP engine (Clingo wrapper) and world rules.

Validates:
- Program grounding, solving, SAT/UNSAT handling
- World rules load and ground without error
- ConstraintSurface -> ASP fact translation
- Incremental multi-shot solving
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tinyassets.constraints.asp_engine import ASPEngine, surface_to_asp_facts
from tinyassets.constraints.constraint_surface import (
    empty_constraint_surface,
    score_constraint_surface,
)

# ------------------------------------------------------------------
# ASPEngine.validate() basics
# ------------------------------------------------------------------


def test_asp_engine_satisfiable():
    """A satisfiable program returns SAT with correct atoms."""
    engine = ASPEngine(base_rules_path="")

    facts = """
    character("Ryn").
    character("Ashwater").
    location("Northern_Pass").
    can_be_in(C, L) :- character(C), location(L).
    #show can_be_in/2.
    """

    result = engine.validate(facts)
    assert result["satisfiable"] is True
    assert len(result["violations"]) == 0
    assert len(result["models"]) >= 1
    assert len(result["atoms"]) > 0
    # Should contain can_be_in atoms
    atom_strs = " ".join(result["atoms"])
    assert "can_be_in" in atom_strs


def test_asp_engine_unsatisfiable():
    """An integrity constraint violation returns UNSAT with violations."""
    engine = ASPEngine(base_rules_path="")

    facts = """
    character("Ryn").
    :- character("Ryn").
    """

    result = engine.validate(facts)
    assert result["satisfiable"] is False
    assert len(result["violations"]) > 0
    assert len(result["models"]) == 0
    assert len(result["atoms"]) == 0


def test_asp_validates_scene_plan_violation():
    """ASP catches a timeline constraint violation."""
    engine = ASPEngine(base_rules_path="")

    rules = """
    :- character_at(C, L1, T), character_at(C, L2, T), L1 != L2.
    """

    facts = """
    character_at("Ryn", "Pass", 1).
    character_at("Ryn", "Castle", 1).
    """

    result = engine.validate(facts, world_rules=rules)
    assert result["satisfiable"] is False


def test_asp_validates_scene_plan_ok():
    """ASP accepts a valid scene plan."""
    engine = ASPEngine(base_rules_path="")

    rules = """
    :- character_at(C, L1, T), character_at(C, L2, T), L1 != L2.
    """

    facts = """
    character_at("Ryn", "Pass", 1).
    character_at("Ryn", "Castle", 2).
    """

    result = engine.validate(facts, world_rules=rules)
    assert result["satisfiable"] is True


# ------------------------------------------------------------------
# World rules loading
# ------------------------------------------------------------------


def test_world_rules_load():
    """Base world_rules.lp loads and grounds without error."""
    rules_path = Path(__file__).resolve().parents[1] / "data" / "world_rules.lp"
    if not rules_path.exists():
        pytest.skip("world_rules.lp not found")

    engine = ASPEngine(base_rules_path=str(rules_path))
    assert len(engine._base_rules) > 0

    # Grounding with no facts should be satisfiable (no atoms to trigger constraints)
    result = engine.validate("")
    # With no facts, integrity constraints are vacuously satisfied
    assert result["satisfiable"] is True


def test_world_rules_catch_violation():
    """World rules catch an institution without a public face."""
    rules_path = Path(__file__).resolve().parents[1] / "data" / "world_rules.lp"
    if not rules_path.exists():
        pytest.skip("world_rules.lp not found")

    engine = ASPEngine(base_rules_path=str(rules_path))

    # Institution declared but no public face or hidden agenda
    facts = 'institution("Guild_of_Mages").'
    result = engine.validate(facts)
    assert result["satisfiable"] is False
    assert len(result["violations"]) > 0


# ------------------------------------------------------------------
# Surface to ASP facts
# ------------------------------------------------------------------


def test_surface_to_facts_characters():
    """Characters in a surface translate to character/1 atoms."""
    surface = empty_constraint_surface()
    surface["characters"] = [
        {"name": "Ryn", "locked_facts": ["knows_secret"]},
        {"name": "Ashwater", "locked_facts": []},
    ]

    facts = surface_to_asp_facts(surface)
    assert 'character("Ryn")' in facts
    assert 'character("Ashwater")' in facts
    assert 'knows("Ryn", "knows_secret")' in facts


def test_surface_to_facts_institutions():
    """Institutions translate to institution/1 + public/hidden atoms."""
    surface = empty_constraint_surface()
    surface["institutions"] = [
        {
            "name": "The Guild",
            "public_face": "magical education",
            "hidden_function": "political control",
        },
    ]

    facts = surface_to_asp_facts(surface)
    assert 'institution("The Guild")' in facts
    assert 'has_public_face("The Guild")' in facts
    assert 'has_hidden_agenda("The Guild")' in facts


def test_surface_to_facts_empty():
    """An empty surface produces no facts."""
    surface = empty_constraint_surface()
    facts = surface_to_asp_facts(surface)
    assert facts.strip() == ""


# ------------------------------------------------------------------
# Full surface validation
# ------------------------------------------------------------------


def test_validate_surface_complete():
    """A well-formed surface validates against world rules."""
    rules_path = Path(__file__).resolve().parents[1] / "data" / "world_rules.lp"
    if not rules_path.exists():
        pytest.skip("world_rules.lp not found")

    engine = ASPEngine(base_rules_path=str(rules_path))

    surface = empty_constraint_surface()
    surface["characters"] = [
        {
            "name": "Ryn",
            "locked_facts": [],
            "relationships": [{"character": "Kael", "conflict": True}],
        },
        {
            "name": "Kael",
            "locked_facts": [],
            "relationships": [{"character": "Ryn", "conflict": True}],
        },
    ]
    surface["institutions"] = [
        {
            "name": "The Order",
            "public_face": "justice",
            "hidden_function": "espionage",
        },
    ]
    surface["timeline_events"] = [
        {
            "name": "The Great War",
            "cause": "territorial dispute",
            "public_narrative": "righteous crusade",
            "reality": "resource grab",
        },
    ]
    surface["resource_pressures"] = [
        {"name": "water_scarcity", "scarcity": True, "info_asymmetry": False},
    ]

    result = engine.validate_surface(surface)
    assert result["satisfiable"] is True


# ------------------------------------------------------------------
# Incremental multi-shot solving
# ------------------------------------------------------------------


def test_incremental_solving():
    """Multi-shot solving validates multiple scenes sequentially."""
    engine = ASPEngine(base_rules_path="")

    rules = """
    :- character_at(C, L1, T), character_at(C, L2, T), L1 != L2.
    """

    scenes = [
        'character_at("Ryn", "Pass", 1).',
        'character_at("Ryn", "Castle", 2).',
    ]

    results = engine.validate_incremental(scenes, world_rules=rules)
    assert len(results) == 2
    assert results[0]["satisfiable"] is True
    assert results[1]["satisfiable"] is True


# ------------------------------------------------------------------
# Constraint surface scoring
# ------------------------------------------------------------------


def test_empty_surface_scores_zero():
    """An empty surface has a score of 0.0."""
    surface = empty_constraint_surface()
    score = score_constraint_surface(surface)
    assert score == 0.0


def test_populated_surface_scores_high():
    """A well-populated surface scores above the readiness threshold."""
    surface = empty_constraint_surface()
    surface["premise_kernel"] = "A world where magic has a price"
    surface["forcing_constraints"] = [
        "No free magic", "All power corrupts", "Knowledge is restricted",
    ]
    surface["power_systems"] = [{"name": "Arcane"}, {"name": "Divine"}, {"name": "Pact"}]
    surface["institutions"] = [{"name": "Guild"}, {"name": "Church"}, {"name": "Crown"}]
    surface["resource_pressures"] = [{"name": "mana"}, {"name": "land"}, {"name": "water"}]
    surface["characters"] = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    surface["locations"] = [{"name": "City"}, {"name": "Forest"}, {"name": "Mountain"}]
    surface["geography_logic"] = "Trade routes along rivers"
    surface["timeline_events"] = [{"name": "War"}, {"name": "Founding"}, {"name": "Cataclysm"}]
    surface["writing_rules"] = ["Show don't tell", "Deep POV", "Grounded metaphors"]
    surface["banned_patterns"] = ["info dumps", "deus ex machina", "purple prose"]
    surface["pov_constraints"] = [{"char": "A"}, {"char": "B"}, {"char": "C"}]
    surface["series_spine"] = [{"book": 1}, {"book": 2}, {"book": 3}]
    surface["thematic_core"] = "Power and its costs"

    score = score_constraint_surface(surface)
    assert score >= 0.75, f"Expected >= 0.75, got {score}"


def test_empty_surface_not_ready():
    """An empty surface is not ready to write."""
    surface = empty_constraint_surface()
    score = score_constraint_surface(surface)
    assert score < 0.75
    assert surface.get("ready_to_write") is False
