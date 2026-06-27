"""Tests for the learning system: style rules, craft cards, criteria discovery."""

from __future__ import annotations

from tinyassets.learning.craft_cards import CraftCard, generate_craft_cards
from tinyassets.learning.criteria_discovery import (
    DiscoveredCriterion,
    discover_criteria,
)
from tinyassets.learning.style_rules import (
    LearningSystem,
    Observation,
    StyleRule,
    StyleRuleState,
)

# ---------------------------------------------------------------------------
# Style rules
# ---------------------------------------------------------------------------


class TestStyleRules:
    def test_observation_creates_rule(self):
        system = LearningSystem()
        obs = [
            Observation(
                dimension="dialogue",
                observation="dialogue missing in action scenes",
                scene_id="1-1-1",
                chapter_number=1,
            ),
        ]
        new_rules = system.add_observations(obs)
        assert len(new_rules) == 1
        assert new_rules[0].dimension == "dialogue"
        assert new_rules[0].state == StyleRuleState.OBSERVED

    def test_promotion_after_threshold(self):
        system = LearningSystem()
        # Add 3 observations across 2 chapters.
        for i in range(3):
            system.add_observations([
                Observation(
                    dimension="pacing",
                    observation="pacing flat in transitions",
                    scene_id=f"1-{i + 1}-1",
                    chapter_number=i + 1,
                ),
            ])

        output = system.observe({"quality_trend": {"accept_rate": 0.8}})
        assert len(output.promoted_rules) == 1
        assert output.promoted_rules[0].state == StyleRuleState.PROMOTED

    def test_no_promotion_below_threshold(self):
        system = LearningSystem()
        # Only 2 observations.
        for i in range(2):
            system.add_observations([
                Observation(
                    dimension="voice",
                    observation="voice inconsistent",
                    scene_id=f"1-{i + 1}-1",
                    chapter_number=i + 1,
                ),
            ])

        output = system.observe({"quality_trend": {"accept_rate": 0.8}})
        assert len(output.promoted_rules) == 0

    def test_no_promotion_single_chapter(self):
        system = LearningSystem()
        # 3 observations but all in same chapter.
        for i in range(3):
            system.add_observations([
                Observation(
                    dimension="pacing",
                    observation="pacing flat",
                    scene_id=f"1-1-{i + 1}",
                    chapter_number=1,
                ),
            ])
        output = system.observe({"quality_trend": {"accept_rate": 0.8}})
        assert len(output.promoted_rules) == 0

    def test_decay_when_accept_rate_drops(self):
        system = LearningSystem()
        # Promote a rule.
        for i in range(3):
            system.add_observations([
                Observation(
                    dimension="pacing",
                    observation="pacing flat",
                    scene_id=f"1-{i + 1}-1",
                    chapter_number=i + 1,
                ),
            ])
        system.observe({"quality_trend": {"accept_rate": 0.8}})
        # Verify it's promoted.
        assert len(system.active_rules()) == 1

        # Accept rate drops by 25 points (> 20 threshold).
        output = system.observe({"quality_trend": {"accept_rate": 0.55}})
        assert len(output.decayed_rules) == 1
        assert output.decayed_rules[0].state == StyleRuleState.DECAYED

    def test_decay_does_not_trigger_on_small_drop(self):
        system = LearningSystem()
        for i in range(3):
            system.add_observations([
                Observation(
                    dimension="dialogue",
                    observation="dialogue stiff",
                    scene_id=f"1-{i + 1}-1",
                    chapter_number=i + 1,
                ),
            ])
        system.observe({"quality_trend": {"accept_rate": 0.8}})

        # Only 10 point drop (< 20 threshold).
        output = system.observe({"quality_trend": {"accept_rate": 0.7}})
        assert len(output.decayed_rules) == 0

    def test_same_dimension_clusters_into_one_rule(self):
        system = LearningSystem()
        system.add_observations([
            Observation(
                dimension="voice",
                observation="voice wobble A",
                scene_id="1-1-1",
                chapter_number=1,
            ),
        ])
        system.add_observations([
            Observation(
                dimension="voice",
                observation="voice wobble B",
                scene_id="1-2-1",
                chapter_number=2,
            ),
        ])
        # Should be clustered into one rule with 2 observations.
        rules = [r for r in system.rules.values() if r.dimension == "voice"]
        assert len(rules) == 1
        assert rules[0].observation_count == 2

    def test_active_rules_returns_promoted_only(self):
        system = LearningSystem()
        for i in range(3):
            system.add_observations([
                Observation(
                    dimension="pacing",
                    observation="flat",
                    scene_id=f"1-{i + 1}-1",
                    chapter_number=i + 1,
                ),
            ])
        # Before promotion.
        assert len(system.active_rules()) == 0
        system.observe({"quality_trend": {"accept_rate": 0.8}})
        assert len(system.active_rules()) == 1


# ---------------------------------------------------------------------------
# Craft cards
# ---------------------------------------------------------------------------


class TestCraftCards:
    def test_generates_from_observations(self):
        state = {
            "chapter_number": 3,
            "style_rules_observed": [
                {"dimension": "pacing", "observation": "transitions too abrupt"},
            ],
            "quality_trend": {"accept_rate": 0.9},
        }
        cards = generate_craft_cards(state)
        assert len(cards) >= 1
        assert isinstance(cards[0], CraftCard)
        assert cards[0].dimension == "pacing"

    def test_generates_warning_on_low_accept_rate(self):
        state = {
            "chapter_number": 5,
            "style_rules_observed": [],
            "quality_trend": {"accept_rate": 0.3},
        }
        cards = generate_craft_cards(state)
        warning_cards = [c for c in cards if c.severity == "warning"]
        assert len(warning_cards) >= 1

    def test_empty_state_no_crash(self):
        cards = generate_craft_cards({})
        assert isinstance(cards, list)

    def test_promoted_rule_generates_card(self):
        rule = StyleRule(
            rule_id="rule-1",
            dimension="dialogue",
            description="dialogue too stiff in action",
            state=StyleRuleState.PROMOTED,
        )
        rule.observations = [None, None, None]  # type: ignore
        rule.chapters_seen = {1, 2, 3}
        state = {
            "chapter_number": 4,
            "style_rules_observed": [],
            "quality_trend": {},
        }
        cards = generate_craft_cards(state, style_rules=[rule])
        assert len(cards) >= 1
        assert "promoted" in cards[0].issue.lower()


# ---------------------------------------------------------------------------
# Criteria discovery
# ---------------------------------------------------------------------------


class TestCriteriaDiscovery:
    def test_discovers_repeated_terms(self):
        rationales = [
            {"rationale": "The atmosphere feels oppressive and claustrophobic", "judge_id": "j1"},
            {"rationale": "Atmosphere is well-crafted but claustrophobic", "judge_id": "j2"},
            {"rationale": "Strong atmosphere throughout the scene", "judge_id": "j1"},
        ]
        discovered = discover_criteria(rationales, threshold=3)
        dims = [d.dimension for d in discovered]
        assert "atmosphere" in dims

    def test_does_not_discover_below_threshold(self):
        rationales = [
            {"rationale": "The foreshadowing is subtle", "judge_id": "j1"},
            {"rationale": "Good pacing overall", "judge_id": "j2"},
        ]
        discovered = discover_criteria(rationales, threshold=3)
        assert len(discovered) == 0

    def test_empty_rationales(self):
        discovered = discover_criteria([], threshold=3)
        assert discovered == []

    def test_returns_discovered_criterion_type(self):
        rationales = [
            {"rationale": "symbolism is heavy-handed", "judge_id": "j1"},
            {"rationale": "too much symbolism detracts", "judge_id": "j2"},
            {"rationale": "symbolism overwhelms narrative", "judge_id": "j3"},
        ]
        discovered = discover_criteria(rationales, threshold=3)
        for d in discovered:
            assert isinstance(d, DiscoveredCriterion)
            assert d.evidence_count >= 3


# ---------------------------------------------------------------------------
# Learn node integration
# ---------------------------------------------------------------------------


class TestLearnNode:
    """Verify the learn node calls into the real LearningSystem."""

    def _get_learn_module(self):
        """Get the learn module (not the function re-exported by __init__)."""
        import importlib
        return importlib.import_module("domains.fantasy_daemon.phases.learn")

    def test_learn_returns_expected_keys(self):
        learn_mod = self._get_learn_module()

        state = {
            "chapter_number": 1,
            "quality_trend": {"accept_rate": 0.9},
            "style_observations": [],
            "style_rules_observed": [],
        }
        result = learn_mod.learn(state)
        assert "style_rules_observed" in result
        assert "craft_cards_generated" in result

    def test_learn_processes_observations(self):
        """Learn node should ingest style observations and pass them
        to the LearningSystem."""
        learn_mod = self._get_learn_module()

        # Reset module-level learning system for test isolation
        learn_mod._learning_system = LearningSystem()

        state = {
            "chapter_number": 1,
            "quality_trend": {"accept_rate": 0.8},
            "style_observations": [
                {
                    "dimension": "pacing",
                    "observation": "pacing too fast",
                    "scene_id": "1-1-1",
                },
            ],
            "style_rules_observed": [],
        }
        learn_mod.learn(state)

        # The learning system should have ingested the observation
        rules = learn_mod._learning_system.rules
        assert len(rules) >= 1
        pacing_rules = [r for r in rules.values() if r.dimension == "pacing"]
        assert len(pacing_rules) == 1
        assert pacing_rules[0].observation_count == 1

    def test_learn_generates_craft_cards_on_low_accept_rate(self):
        """Low accept rate should generate warning craft cards."""
        learn_mod = self._get_learn_module()

        learn_mod._learning_system = LearningSystem()

        state = {
            "chapter_number": 2,
            "quality_trend": {"accept_rate": 0.3},
            "style_observations": [],
            "style_rules_observed": [],
        }
        result = learn_mod.learn(state)

        warning_cards = [
            c for c in result["craft_cards_generated"]
            if c["severity"] == "warning"
        ]
        assert len(warning_cards) >= 1

    def test_learn_discovers_criteria_from_observations(self):
        """Repeated terms in observations should surface as craft cards."""
        learn_mod = self._get_learn_module()
        learn_mod._learning_system = LearningSystem()

        state = {
            "chapter_number": 3,
            "quality_trend": {},
            "style_observations": [
                {
                    "observation": "The atmosphere feels oppressive and claustrophobic",
                    "source": "editorial",
                },
                {
                    "observation": "Atmosphere is well-crafted but claustrophobic",
                    "source": "editorial",
                },
                {
                    "observation": "Strong atmosphere throughout the scene",
                    "source": "editorial",
                },
            ],
            "style_rules_observed": [],
        }
        result = learn_mod.learn(state)

        # Should generate an info craft card for discovered dimension.
        info_cards = [
            c for c in result["craft_cards_generated"]
            if c["severity"] == "info" and "atmosphere" in c["dimension"]
        ]
        assert len(info_cards) >= 1


# ---------------------------------------------------------------------------
# Editorial notes → learning pipeline
# ---------------------------------------------------------------------------


class TestEditorialToObservations:
    """Test that editorial notes are converted to learning observations."""

    def test_protect_items_become_strength_observations(self):
        from domains.fantasy_daemon.phases.learn import _editorial_to_observations

        state = {
            "editorial_notes": {
                "protect": ["vivid imagery", "strong pacing"],
                "concerns": [],
            },
            "book_number": 1,
            "scene_number": 2,
        }
        obs = _editorial_to_observations(state, chapter_number=3)
        assert len(obs) == 2
        assert obs[0]["dimension"] == "strength"
        assert obs[0]["source"] == "editorial_protect"
        assert "vivid imagery" in obs[0]["observation"]

    def test_concerns_become_growth_observations(self):
        from domains.fantasy_daemon.phases.learn import _editorial_to_observations

        state = {
            "editorial_notes": {
                "protect": [],
                "concerns": [
                    {"text": "Wrong name", "clearly_wrong": True},
                    {"text": "Pacing slow", "clearly_wrong": False},
                ],
            },
        }
        obs = _editorial_to_observations(state, chapter_number=1)
        assert len(obs) == 2
        assert obs[0]["dimension"] == "error"
        assert obs[1]["dimension"] == "craft"

    def test_empty_editorial_returns_empty(self):
        from domains.fantasy_daemon.phases.learn import _editorial_to_observations

        obs = _editorial_to_observations({}, chapter_number=1)
        assert obs == []

    def test_none_editorial_returns_empty(self):
        from domains.fantasy_daemon.phases.learn import _editorial_to_observations

        state = {"editorial_notes": None}
        obs = _editorial_to_observations(state, chapter_number=1)
        assert obs == []


class TestCraftCardsFromEditorial:
    """Test that editorial notes produce craft cards via the learn pipeline."""

    def _get_learn_module(self):
        import importlib
        return importlib.import_module("domains.fantasy_daemon.phases.learn")

    def test_protect_generates_strength_card(self):
        """Editorial protect items → strength craft cards via learn pipeline."""
        learn_mod = self._get_learn_module()
        learn_mod._learning_system = LearningSystem()

        state = {
            "chapter_number": 5,
            "quality_trend": {},
            "style_observations": [],
            "style_rules_observed": [],
            "editorial_notes": {
                "protect": ["excellent dialogue rhythm"],
                "concerns": [],
            },
        }
        learn_mod.learn(state)
        rules = learn_mod._learning_system.rules
        strength_rules = [r for r in rules.values() if r.dimension == "strength"]
        assert len(strength_rules) >= 1

    def test_concern_generates_observation(self):
        """Editorial concerns → learning observations via learn pipeline."""
        learn_mod = self._get_learn_module()
        learn_mod._learning_system = LearningSystem()

        state = {
            "chapter_number": 3,
            "quality_trend": {},
            "style_observations": [],
            "style_rules_observed": [],
            "editorial_notes": {
                "protect": [],
                "concerns": [
                    {
                        "text": "Pacing drags in middle",
                        "clearly_wrong": False,
                    },
                ],
            },
        }
        learn_mod.learn(state)
        rules = learn_mod._learning_system.rules
        craft_rules = [r for r in rules.values() if r.dimension == "craft"]
        assert len(craft_rules) >= 1

    def test_clearly_wrong_generates_error_observation(self):
        """clearly_wrong concerns → error dimension observations."""
        learn_mod = self._get_learn_module()
        learn_mod._learning_system = LearningSystem()

        state = {
            "chapter_number": 2,
            "quality_trend": {},
            "style_observations": [],
            "style_rules_observed": [],
            "editorial_notes": {
                "protect": [],
                "concerns": [
                    {"text": "Wrong character name", "clearly_wrong": True},
                ],
            },
        }
        learn_mod.learn(state)
        rules = learn_mod._learning_system.rules
        error_rules = [r for r in rules.values() if r.dimension == "error"]
        assert len(error_rules) >= 1


class TestReflexionWithEditorial:
    """Test that reflexion uses editorial notes."""

    def test_template_critique_uses_editorial(self):
        from tinyassets.memory.reflexion import ReflexionEngine

        engine = ReflexionEngine()
        editorial = {
            "protect": ["strong voice"],
            "concerns": [
                {"text": "Wrong name", "clearly_wrong": True, "quoted_passage": "Kael said"},
            ],
        }
        critique = engine._template_critique({}, None, editorial)
        assert "ERROR" in critique
        assert "Wrong name" in critique
        assert "Kael said" in critique
        assert "strength" in critique.lower()
