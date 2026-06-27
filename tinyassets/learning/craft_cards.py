"""Craft cards -- compressed lessons from chapter evaluations.

Each craft card captures a single lesson learned from the writing and
evaluation process: what dimension was affected, what the issue was,
evidence from the text, and a recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CraftCard:
    """A compressed lesson from a chapter evaluation."""

    card_id: str
    dimension: str         # e.g. "pacing", "dialogue", "voice"
    issue: str             # what went wrong (or right)
    evidence: str          # specific quotes or metrics
    recommendation: str    # what to do differently
    chapter_number: int = 0
    severity: str = "info"  # "info" | "warning" | "critical"


def generate_craft_cards(
    chapter_state: dict[str, Any],
    style_rules: list[Any] | None = None,
) -> list[CraftCard]:
    """Generate craft cards from a chapter's evaluation data.

    Examines ``style_observations``, ``quality_trend``, and newly
    promoted/decayed style rules to produce actionable lessons.

    Parameters
    ----------
    chapter_state : dict
        ChapterState with evaluation data.
    style_rules : list | None
        Recently promoted or decayed style rules.

    Returns
    -------
    list[CraftCard]
        One card per notable lesson (typically 1-5 per chapter).
    """
    cards: list[CraftCard] = []
    chapter_num = chapter_state.get("chapter_number", 0)
    card_counter = 0

    # Cards from style observations (including editorial-sourced).
    style_obs = chapter_state.get("style_rules_observed", [])
    for obs in style_obs:
        if isinstance(obs, dict):
            dim = obs.get("dimension", "general")
            observation = obs.get("observation", "")
        else:
            dim = "general"
            observation = str(obs)

        if observation:
            card_counter += 1
            cards.append(CraftCard(
                card_id=f"cc-{chapter_num}-{card_counter}",
                dimension=dim,
                issue=observation,
                evidence="",
                recommendation=f"Monitor {dim} in upcoming scenes",
                chapter_number=chapter_num,
            ))

    # Editorial notes flow through style_rules_observed via learn.py's
    # _editorial_to_observations — no direct editorial_notes reading here.

    # Cards from quality trend.
    quality = chapter_state.get("quality_trend", {}) or {}
    accept_rate = quality.get("accept_rate")
    if accept_rate is not None and accept_rate < 0.5:
        card_counter += 1
        cards.append(CraftCard(
            card_id=f"cc-{chapter_num}-{card_counter}",
            dimension="overall_quality",
            issue=f"Low accept rate ({accept_rate:.0%}) in chapter {chapter_num}",
            evidence=f"Accept rate: {accept_rate:.2f}",
            recommendation="Review structural evaluation feedback for patterns",
            chapter_number=chapter_num,
            severity="warning",
        ))

    # Cards from promoted style rules.
    if style_rules:
        for rule in style_rules:
            state_val = getattr(rule.state, "value", "") if hasattr(rule, "state") else ""
            if state_val == "promoted":
                card_counter += 1
                desc = getattr(rule, "description", "")
                dim = getattr(rule, "dimension", "general")
                cards.append(CraftCard(
                    card_id=f"cc-{chapter_num}-{card_counter}",
                    dimension=dim,
                    issue=f"Pattern promoted to active rule: {desc}",
                    evidence=f"{getattr(rule, 'observation_count', 0)} observations "
                             f"across {getattr(rule, 'chapter_spread', 0)} chapters",
                    recommendation=f"Apply {dim} guidance in future scenes",
                    chapter_number=chapter_num,
                    severity="info",
                ))

    return cards
