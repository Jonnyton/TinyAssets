"""Style rule lifecycle: observe -> cluster -> promote -> decay.

Style rules are patterns observed across multiple evaluations that
become active guidance for the writing system.

Lifecycle:
1. Observe: judge mentions a pattern in 3+ scenes across 3+ chapters.
2. Cluster: group observations by dimension ("dialogue", "pacing", etc.).
3. Promote: after 3+ clustered observations, promote to active rule.
4. Decay: rule deactivated when accept rate drops >20 points while active.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Promotion thresholds.
OBSERVATION_THRESHOLD = 3  # observations needed to promote
CHAPTER_SPREAD_THRESHOLD = 2  # distinct chapters needed

# Decay threshold: if accept rate drops by this much while rule is active.
DECAY_THRESHOLD = 0.20


class StyleRuleState(str, Enum):
    """Lifecycle state of a style rule."""

    OBSERVED = "observed"    # Pattern seen but not yet promoted.
    PROMOTED = "promoted"    # Active guidance rule.
    DECAYED = "decayed"      # Was active, now deactivated.


@dataclass
class Observation:
    """A single style observation from an evaluation."""

    dimension: str       # e.g. "dialogue", "pacing", "voice"
    observation: str     # e.g. "dialogue missing in action scenes"
    scene_id: str
    chapter_number: int
    source: str = ""     # judge_id or "structural"
    timestamp: float = field(default_factory=time.time)


@dataclass
class StyleRule:
    """A style rule derived from clustered observations."""

    rule_id: str
    dimension: str
    description: str
    state: StyleRuleState = StyleRuleState.OBSERVED
    observations: list[Observation] = field(default_factory=list)
    chapters_seen: set[int] = field(default_factory=set)
    promoted_at: float | None = None
    decayed_at: float | None = None
    accept_rate_at_promotion: float | None = None

    @property
    def observation_count(self) -> int:
        return len(self.observations)

    @property
    def chapter_spread(self) -> int:
        return len(self.chapters_seen)

    def should_promote(self) -> bool:
        """True if this rule has enough evidence to be promoted."""
        return (
            self.state == StyleRuleState.OBSERVED
            and self.observation_count >= OBSERVATION_THRESHOLD
            and self.chapter_spread >= CHAPTER_SPREAD_THRESHOLD
        )

    def promote(self, accept_rate: float) -> None:
        """Promote this rule to active guidance."""
        self.state = StyleRuleState.PROMOTED
        self.promoted_at = time.time()
        self.accept_rate_at_promotion = accept_rate
        logger.info("Style rule promoted: %s (%s)", self.rule_id, self.description)

    def should_decay(self, current_accept_rate: float) -> bool:
        """True if the accept rate dropped significantly while this rule is active."""
        if self.state != StyleRuleState.PROMOTED:
            return False
        if self.accept_rate_at_promotion is None:
            return False
        drop = self.accept_rate_at_promotion - current_accept_rate
        return drop >= DECAY_THRESHOLD

    def decay(self) -> None:
        """Deactivate this rule."""
        self.state = StyleRuleState.DECAYED
        self.decayed_at = time.time()
        logger.info("Style rule decayed: %s (%s)", self.rule_id, self.description)


@dataclass
class LearningOutput:
    """Output of the learning system for a chapter boundary."""

    new_rules: list[StyleRule] = field(default_factory=list)
    promoted_rules: list[StyleRule] = field(default_factory=list)
    decayed_rules: list[StyleRule] = field(default_factory=list)
    active_rules: list[StyleRule] = field(default_factory=list)


class LearningSystem:
    """Manages the style rule lifecycle.

    Usage::

        system = LearningSystem()
        # After each evaluation:
        system.add_observations(observations)
        # At chapter boundary:
        output = system.observe(chapter_state)
    """

    def __init__(self) -> None:
        self._rules: dict[str, StyleRule] = {}
        self._rule_counter = 0

    @property
    def rules(self) -> dict[str, StyleRule]:
        return dict(self._rules)

    def active_rules(self) -> list[StyleRule]:
        """Return all currently promoted (active) rules."""
        return [
            r for r in self._rules.values()
            if r.state == StyleRuleState.PROMOTED
        ]

    def add_observations(self, observations: list[Observation]) -> list[StyleRule]:
        """Ingest new observations and cluster them into rules.

        Observations are grouped by dimension.  If a dimension already
        has a rule, the observation is added to it.  Otherwise, a new
        rule is created.

        Returns newly created rules.
        """
        new_rules: list[StyleRule] = []
        for obs in observations:
            rule = self._find_or_create_rule(obs)
            if rule.rule_id not in self._rules:
                self._rules[rule.rule_id] = rule
                new_rules.append(rule)
            rule.observations.append(obs)
            rule.chapters_seen.add(obs.chapter_number)

        return new_rules

    def _find_or_create_rule(self, obs: Observation) -> StyleRule:
        """Find an existing rule for this dimension or create one."""
        # Look for an observed or promoted rule with the same dimension.
        for rule in self._rules.values():
            if (
                rule.dimension == obs.dimension
                and rule.state in (StyleRuleState.OBSERVED, StyleRuleState.PROMOTED)
            ):
                return rule

        # Create new rule.
        self._rule_counter += 1
        rule_id = f"rule-{self._rule_counter}"
        return StyleRule(
            rule_id=rule_id,
            dimension=obs.dimension,
            description=obs.observation,
        )

    def observe(self, chapter_state: dict[str, Any]) -> LearningOutput:
        """Run the learning loop at a chapter boundary.

        1. Check if any observed rules should be promoted.
        2. Check if any promoted rules should decay.
        3. Return the learning output.

        Parameters
        ----------
        chapter_state : dict
            ChapterState with ``quality_trend`` containing ``accept_rate``.

        Returns
        -------
        LearningOutput
            New, promoted, decayed, and active rules.
        """
        quality_trend = chapter_state.get("quality_trend", {}) or {}
        accept_rate = quality_trend.get("accept_rate", 1.0)

        promoted: list[StyleRule] = []
        decayed: list[StyleRule] = []

        for rule in self._rules.values():
            # Check promotion.
            if rule.should_promote():
                rule.promote(accept_rate)
                promoted.append(rule)

            # Check decay.
            if rule.should_decay(accept_rate):
                rule.decay()
                decayed.append(rule)

        active = self.active_rules()

        return LearningOutput(
            new_rules=[],  # new rules tracked via add_observations
            promoted_rules=promoted,
            decayed_rules=decayed,
            active_rules=active,
        )
