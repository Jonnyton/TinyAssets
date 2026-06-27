"""HTN planner -- Hierarchical Task Network decomposition for narrative planning.

Decomposes a high-level goal (premise) into a structured outline:
    goal -> acts (3) -> chapters (3-5 per act) -> scenes (3-7 per chapter)

Each level carries explicit preconditions and effects, enabling ASP
validation at every decomposition step.

HTN is planning scaffolding, not text generation.  The symbolic layer
informs the neural layer.
"""

from __future__ import annotations

import logging

from typing_extensions import TypedDict

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Types
# ------------------------------------------------------------------

class ScenePlan(TypedDict):
    """A single scene in the decomposition."""

    title: str
    summary: str
    preconditions: list[str]
    effects: list[str]
    characters: list[str]
    location: str


class ChapterPlan(TypedDict):
    """A chapter containing scenes."""

    title: str
    summary: str
    scenes: list[ScenePlan]
    preconditions: list[str]
    effects: list[str]


class ActPlan(TypedDict):
    """An act containing chapters."""

    name: str
    summary: str
    chapters: list[ChapterPlan]
    preconditions: list[str]
    effects: list[str]


class Outline(TypedDict):
    """The full decomposed outline."""

    acts: list[ActPlan]
    premise_kernel: str
    thematic_core: str
    characters_extracted: list[str]


# ------------------------------------------------------------------
# Three-act template used for template-based decomposition
# ------------------------------------------------------------------

_THREE_ACT_TEMPLATE: list[dict] = [
    {
        "name": "Act I: Establishment",
        "summary_template": "Introduce the world, characters, and central conflict of: {goal}",
        "chapter_count": 3,
        "preconditions": [],
        "effects": ["world_established", "protagonist_introduced", "conflict_seeded"],
    },
    {
        "name": "Act II: Confrontation",
        "summary_template": "Escalate conflict, test protagonist, reveal truths: {goal}",
        "chapter_count": 5,
        "preconditions": ["world_established", "protagonist_introduced", "conflict_seeded"],
        "effects": ["conflict_escalated", "alliances_formed", "stakes_raised"],
    },
    {
        "name": "Act III: Resolution",
        "summary_template": "Climax and resolution of: {goal}",
        "chapter_count": 3,
        "preconditions": ["conflict_escalated", "stakes_raised"],
        "effects": ["conflict_resolved", "character_arcs_completed"],
    },
]


class HTNPlanner:
    """Hierarchical Task Network planner for narrative structure.

    Currently uses template-based decomposition.  When the provider
    routing layer (integration agent) is available, this can be enhanced
    to use LLM-generated decompositions via subprocess calls.
    """

    def decompose(
        self,
        goal: str,
        world_state: dict | None = None,
    ) -> Outline:
        """Decompose a high-level goal into a structured outline.

        Parameters
        ----------
        goal : str
            The premise or high-level narrative goal.
        world_state : dict or None
            Optional world state that constrains decomposition.

        Returns
        -------
        Outline
            Hierarchical outline with acts, chapters, and scenes.
        """
        acts: list[ActPlan] = []

        for act_template in _THREE_ACT_TEMPLATE:
            chapters = self._decompose_act_to_chapters(
                act_name=act_template["name"],
                goal=goal,
                chapter_count=act_template["chapter_count"],
                act_preconditions=act_template["effects"],
            )
            act = ActPlan(
                name=act_template["name"],
                summary=act_template["summary_template"].format(goal=goal),
                chapters=chapters,
                preconditions=act_template["preconditions"],
                effects=act_template["effects"],
            )
            acts.append(act)

        characters = self._extract_characters(acts, goal)
        thematic_core = self._extract_thematic_core(goal)

        return Outline(
            acts=acts,
            premise_kernel=goal,
            thematic_core=thematic_core,
            characters_extracted=characters,
        )

    def _decompose_act_to_chapters(
        self,
        act_name: str,
        goal: str,
        chapter_count: int,
        act_preconditions: list[str],
    ) -> list[ChapterPlan]:
        """Decompose an act into chapters with scenes."""
        chapters: list[ChapterPlan] = []
        cumulative_effects: list[str] = []

        for i in range(chapter_count):
            scenes = self._decompose_chapter_to_scenes(
                chapter_num=i + 1,
                act_name=act_name,
                goal=goal,
            )
            chapter_effects = [f"chapter_{i + 1}_complete"]
            chapter = ChapterPlan(
                title=f"{act_name} - Chapter {i + 1}",
                summary=f"Chapter {i + 1} of {act_name}: advancing {goal}",
                scenes=scenes,
                preconditions=list(cumulative_effects),
                effects=chapter_effects,
            )
            chapters.append(chapter)
            cumulative_effects.extend(chapter_effects)

        return chapters

    @staticmethod
    def _decompose_chapter_to_scenes(
        chapter_num: int,
        act_name: str,
        goal: str,
    ) -> list[ScenePlan]:
        """Decompose a chapter into scenes."""
        # Template: 3-5 scenes per chapter
        scene_count = 3 + (chapter_num % 3)  # 3, 4, or 5
        scenes: list[ScenePlan] = []
        cumulative: list[str] = []

        for j in range(scene_count):
            effects = [f"scene_{chapter_num}_{j + 1}_done"]
            scene = ScenePlan(
                title=f"Scene {j + 1}",
                summary=f"Scene {j + 1} of Chapter {chapter_num} ({act_name})",
                preconditions=list(cumulative),
                effects=effects,
                characters=[],
                location="",
            )
            scenes.append(scene)
            cumulative.extend(effects)

        return scenes

    @staticmethod
    def _extract_characters(acts: list[ActPlan], goal: str) -> list[str]:
        """Extract character names mentioned in the goal.

        Template-based: returns placeholder names.  LLM-enhanced mode
        would parse the premise for actual character references.
        """
        return ["Protagonist", "Antagonist", "Ally"]

    @staticmethod
    def _extract_thematic_core(goal: str) -> str:
        """Derive a thematic question from the goal."""
        return f"What does it mean when {goal.lower().rstrip('.')}?"
