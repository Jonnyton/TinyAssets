"""DOME outline expansion -- recursive deepening with KG feedback.

Implements the Dynamic Outline with Memory Enhancement pattern from
NAACL 2025 (arxiv.org/abs/2412.13575).  At each decomposition level:

    rough outline -> query KG -> refine -> detailed outline

The KG feedback parameter accepts lightweight entity/fact/relationship
feedback and annotates generated beats with bounded consistency notes.
"""

from __future__ import annotations

import copy
import logging
import re

from typing_extensions import NotRequired, TypedDict

from workflow.planning.htn_planner import Outline, ScenePlan

logger = logging.getLogger(__name__)

_CAPITALIZED_PHRASE_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9_-]{2,}(?:\s+[A-Z][A-Za-z0-9_-]{2,}){0,3}\b"
)

_ENTITY_KEYS = (
    "name",
    "entity",
    "entity_name",
    "character",
    "subject",
    "object",
)

_TEXT_KEYS = ("text", "summary", "description")

_REL_SOURCE_KEYS = ("source", "from", "subject", "left")
_REL_TARGET_KEYS = ("target", "to", "object", "right")
_REL_TYPE_KEYS = ("type", "relation", "relationship", "predicate")


def _clean_name(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip(" \t\r\n\"'`.,;:()[]{}")
    if len(text) < 2 or len(text) > 80:
        return None
    return text


def _add_name(names: dict[str, str], value: object) -> None:
    text = _clean_name(value)
    if not text:
        return
    names.setdefault(text.casefold(), text)


def _extract_names_from_text(names: dict[str, str], text: object) -> None:
    if not isinstance(text, str):
        return
    for match in _CAPITALIZED_PHRASE_RE.finditer(text):
        _add_name(names, match.group(0))


def _collect_known_names(kg_feedback: dict) -> dict[str, str]:
    names: dict[str, str] = {}
    for entity in kg_feedback.get("entities", []):
        if isinstance(entity, dict):
            for key in _ENTITY_KEYS:
                _add_name(names, entity.get(key))
            for key in _TEXT_KEYS:
                _extract_names_from_text(names, entity.get(key))
        else:
            _add_name(names, entity)

    for fact in kg_feedback.get("facts", []):
        if isinstance(fact, dict):
            for key in _ENTITY_KEYS:
                _add_name(names, fact.get(key))
            for key in _TEXT_KEYS:
                _extract_names_from_text(names, fact.get(key))
        else:
            _extract_names_from_text(names, fact)

    return names


def _relationship_note(relationship: object) -> tuple[str, str, str] | None:
    if not isinstance(relationship, dict):
        return None
    source = next(
        (_clean_name(relationship.get(key)) for key in _REL_SOURCE_KEYS
         if _clean_name(relationship.get(key))),
        None,
    )
    target = next(
        (_clean_name(relationship.get(key)) for key in _REL_TARGET_KEYS
         if _clean_name(relationship.get(key))),
        None,
    )
    rel_type = next(
        (_clean_name(relationship.get(key)) for key in _REL_TYPE_KEYS
         if _clean_name(relationship.get(key))),
        "related_to",
    )
    if not source or not target:
        return None
    return source, rel_type or "related_to", target


def _mentions_name(text: str, name: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE) is not None


class SceneBeat(TypedDict):
    """A beat within a scene -- the finest level of outline detail."""

    description: str
    character_focus: str
    tension_level: float  # 0.0-1.0
    beat_type: str  # "action", "dialogue", "reflection", "revelation"
    kg_notes: NotRequired[list[str]]


class DetailedScene(TypedDict):
    """A scene with expanded beat-level detail."""

    title: str
    summary: str
    preconditions: list[str]
    effects: list[str]
    characters: list[str]
    location: str
    beats: list[SceneBeat]
    tension_curve: list[float]


class DetailedOutline(TypedDict):
    """An outline with per-scene beats, tension curves, and arc tracking."""

    acts: list[dict]  # Same structure as ActPlan but scenes are DetailedScene
    premise_kernel: str
    thematic_core: str
    characters_extracted: list[str]
    expansion_depth: int
    kg_enriched: bool


class DOMEExpander:
    """Recursive outline expander with optional KG feedback.

    Parameters
    ----------
    max_depth : int
        Maximum number of expansion iterations (default 2).
    """

    def __init__(self, max_depth: int = 2) -> None:
        self._max_depth = max_depth

    def expand(
        self,
        outline: Outline,
        kg_feedback: dict | None = None,
    ) -> DetailedOutline:
        """Expand a sparse outline into a detailed outline with beats.

        Parameters
        ----------
        outline : Outline
            The HTN-generated outline to expand.
        kg_feedback : dict or None
            Knowledge graph feedback for consistency checking.
            Stubbed -- when None, expansion proceeds without KG enrichment.

        Returns
        -------
        DetailedOutline
            The expanded outline with per-scene beats and tension curves.
        """
        detailed_acts: list[dict] = []

        for act in outline["acts"]:
            detailed_chapters: list[dict] = []

            for chapter in act["chapters"]:
                detailed_scenes: list[DetailedScene] = []

                for scene in chapter["scenes"]:
                    detailed = self._expand_scene(scene, kg_feedback)
                    detailed_scenes.append(detailed)

                detailed_chapter = {
                    "title": chapter["title"],
                    "summary": chapter["summary"],
                    "scenes": detailed_scenes,
                    "preconditions": chapter["preconditions"],
                    "effects": chapter["effects"],
                }
                detailed_chapters.append(detailed_chapter)

            detailed_act = {
                "name": act["name"],
                "summary": act["summary"],
                "chapters": detailed_chapters,
                "preconditions": act["preconditions"],
                "effects": act["effects"],
            }
            detailed_acts.append(detailed_act)

        # Iterative deepening: refine tension curves
        for depth in range(self._max_depth):
            detailed_acts = self._refine_pass(detailed_acts, depth, kg_feedback)

        return DetailedOutline(
            acts=detailed_acts,
            premise_kernel=outline["premise_kernel"],
            thematic_core=outline["thematic_core"],
            characters_extracted=outline["characters_extracted"],
            expansion_depth=self._max_depth,
            kg_enriched=kg_feedback is not None,
        )

    def _expand_scene(
        self,
        scene: ScenePlan,
        kg_feedback: dict | None,
    ) -> DetailedScene:
        """Expand a single scene into beats.

        Generates 3-5 beats per scene with a tension curve.
        """
        beat_count = 4  # Default beat count per scene
        beats: list[SceneBeat] = []
        beat_types = ["action", "dialogue", "reflection", "revelation"]

        for i in range(beat_count):
            # Tension rises through the scene, peaks at 3/4
            tension = self._compute_beat_tension(i, beat_count)
            beat = SceneBeat(
                description=f"Beat {i + 1} of {scene['title']}: {scene['summary']}",
                character_focus=scene["characters"][0] if scene["characters"] else "Protagonist",
                tension_level=tension,
                beat_type=beat_types[i % len(beat_types)],
            )
            beats.append(beat)

        tension_curve = [b["tension_level"] for b in beats]

        return DetailedScene(
            title=scene["title"],
            summary=scene["summary"],
            preconditions=scene["preconditions"],
            effects=scene["effects"],
            characters=scene["characters"] or ["Protagonist"],
            location=scene["location"] or "Unspecified",
            beats=beats,
            tension_curve=tension_curve,
        )

    @staticmethod
    def _compute_beat_tension(beat_index: int, total_beats: int) -> float:
        """Compute tension for a beat using a simple arc curve.

        Tension rises to a peak at approximately 3/4 through the scene,
        then drops slightly for the resolution beat.
        """
        if total_beats <= 1:
            return 0.5
        progress = beat_index / (total_beats - 1)
        # Peak at 0.75 progress
        if progress <= 0.75:
            return round(0.3 + 0.6 * (progress / 0.75), 2)
        else:
            return round(0.9 - 0.3 * ((progress - 0.75) / 0.25), 2)

    def _refine_pass(
        self,
        acts: list[dict],
        depth: int,
        kg_feedback: dict | None,
    ) -> list[dict]:
        """Refine the outline in an iterative deepening pass.

        Currently adjusts tension curves for cross-scene consistency.
        With KG feedback, this would also check entity references and
        adjust beats for knowledge boundary compliance.
        """
        refined = copy.deepcopy(acts)

        if kg_feedback is not None:
            # KG-enriched refinement: check entity consistency
            logger.info("DOME refinement pass %d with KG feedback", depth + 1)
            self._apply_kg_feedback(refined, kg_feedback)
        else:
            logger.debug("DOME refinement pass %d (no KG feedback)", depth + 1)

        # Cross-scene tension normalisation: ensure no two adjacent scenes
        # have identical peak tension
        for act in refined:
            for chapter in act["chapters"]:
                scenes = chapter["scenes"]
                for i in range(1, len(scenes)):
                    prev_peak = max(scenes[i - 1]["tension_curve"], default=0.5)
                    curr_peak = max(scenes[i]["tension_curve"], default=0.5)
                    if abs(prev_peak - curr_peak) < 0.05:
                        # Adjust current scene tension slightly
                        bump = 0.1 * (1 if i % 2 == 0 else -1)
                        scenes[i]["tension_curve"] = [
                            round(max(0.0, min(1.0, t + bump)), 2)
                            for t in scenes[i]["tension_curve"]
                        ]

        return refined

    @staticmethod
    def _apply_kg_feedback(acts: list[dict], kg_feedback: dict) -> None:
        """Apply knowledge graph feedback to refine beats.

        Checks character references in beats against KG entities and
        annotates beats with known relationships and facts.
        """
        known_names = _collect_known_names(kg_feedback)
        relationships = [
            note
            for note in (
                _relationship_note(rel)
                for rel in kg_feedback.get("relationships", [])
            )
            if note is not None
        ]

        if not known_names and not relationships:
            return

        name_values = sorted(known_names.values(), key=str.casefold)
        for act in acts:
            for chapter in act.get("chapters", []):
                for scene in chapter.get("scenes", []):
                    scene_text = " ".join(
                        str(part)
                        for part in (
                            scene.get("title", ""),
                            scene.get("summary", ""),
                            " ".join(scene.get("characters", [])),
                            scene.get("location", ""),
                        )
                    )
                    scene_mentions = [
                        name for name in name_values
                        if _mentions_name(scene_text, name)
                    ]
                    for index, beat in enumerate(scene.get("beats", [])):
                        beat_text = " ".join(
                            str(part)
                            for part in (
                                scene_text,
                                beat.get("description", ""),
                                beat.get("character_focus", ""),
                                beat.get("beat_type", ""),
                            )
                        )
                        mentions = [
                            name for name in name_values
                            if _mentions_name(beat_text, name)
                        ]
                        notes: list[str] = []
                        if mentions:
                            notes.append(
                                "KG entities referenced: "
                                + ", ".join(mentions[:5])
                            )
                        elif index == 0 and name_values:
                            notes.append(
                                "KG context available: "
                                + ", ".join(name_values[:5])
                            )

                        relationship_notes = []
                        for source, rel_type, target in relationships:
                            if _mentions_name(beat_text, source) and _mentions_name(
                                beat_text, target,
                            ):
                                relationship_notes.append(
                                    f"{source} {rel_type} {target}"
                                )
                        if relationship_notes:
                            notes.append(
                                "KG relationships referenced: "
                                + "; ".join(relationship_notes[:3])
                            )

                        if scene_mentions and index == 0:
                            notes.append(
                                "KG scene entities: "
                                + ", ".join(scene_mentions[:5])
                            )

                        if notes:
                            beat.setdefault("kg_notes", []).extend(notes)
