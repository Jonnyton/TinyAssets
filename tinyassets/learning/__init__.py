"""Learning system -- style rules, craft cards, criteria discovery.

Implements the observation -> promotion cycle, calibration, and
creation-time learning.
"""

from tinyassets.learning.craft_cards import CraftCard, generate_craft_cards
from tinyassets.learning.criteria_discovery import (
    DiscoveredCriterion,
    discover_criteria,
)
from tinyassets.learning.style_rules import (
    LearningOutput,
    LearningSystem,
    StyleRule,
    StyleRuleState,
)

__all__ = [
    "CraftCard",
    "DiscoveredCriterion",
    "LearningOutput",
    "LearningSystem",
    "StyleRule",
    "StyleRuleState",
    "discover_criteria",
    "generate_craft_cards",
]
