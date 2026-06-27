"""Constraint synthesis -- the neurosymbolic subgraph coordinator.

Takes a premise (sparse or rich) and produces a ConstraintSurface of
equal quality regardless of input richness.  Two modes:

- **EXTRACT**: Rich source documents -> decompose, validate, index.
- **GENERATE**: Sparse prompt -> HTN decompose -> DOME expand ->
  ASP validate -> iterate until ready.

Both modes output the same ConstraintSurface.
"""

from __future__ import annotations

import logging

from tinyassets.constraints.asp_engine import ASPEngine, ValidationResult
from tinyassets.constraints.constraint_surface import (
    READINESS_THRESHOLD,
    ConstraintSurface,
    empty_constraint_surface,
    score_constraint_surface,
)
from tinyassets.planning.dome_expansion import DOMEExpander
from tinyassets.planning.htn_planner import HTNPlanner

logger = logging.getLogger(__name__)

# Maximum deepening iterations before accepting best-effort result
# (never-block rule: the system must not loop indefinitely)
MAX_ITERATIONS: int = 3

# Minimum word count in source documents to classify as "rich"
_RICH_SOURCE_THRESHOLD: int = 500


class ConstraintSynthesis:
    """Constraint synthesis engine.

    Orchestrates the flow: classify -> process -> validate -> iterate.

    Parameters
    ----------
    asp_engine : ASPEngine or None
        ASP engine instance.  If None, a default is created.
    htn_planner : HTNPlanner or None
        HTN planner instance.  If None, a default is created.
    dome_expander : DOMEExpander or None
        DOME expander instance.  If None, a default is created.
    """

    def __init__(
        self,
        asp_engine: ASPEngine | None = None,
        htn_planner: HTNPlanner | None = None,
        dome_expander: DOMEExpander | None = None,
    ) -> None:
        self._asp = asp_engine or ASPEngine()
        self._htn = htn_planner or HTNPlanner()
        self._dome = dome_expander or DOMEExpander()

    def process(
        self,
        premise: str,
        source_documents: list[str] | None = None,
    ) -> ConstraintSurface:
        """Process a premise into a fully populated ConstraintSurface.

        Parameters
        ----------
        premise : str
            The narrative premise (can be 2 sentences or a full synopsis).
        source_documents : list of str or None
            Rich source documents (canon guides, world bibles, etc.).

        Returns
        -------
        ConstraintSurface
            Populated constraint surface, scored for readiness.
        """
        mode = self.classify_input(premise, source_documents)
        logger.info("Constraint synthesis mode: %s", mode)

        if mode == "EXTRACT":
            surface = self._extract_mode(premise, source_documents or [])
        else:
            surface = self._generate_mode(premise)

        # Validate and iterate
        surface = self._validate_and_iterate(surface)

        return surface

    @staticmethod
    def classify_input(
        premise: str,
        source_documents: list[str] | None,
    ) -> str:
        """Classify input richness to route processing mode.

        Returns ``"EXTRACT"`` for rich sources, ``"GENERATE"`` for sparse.
        """
        if not source_documents:
            return "GENERATE"

        total_words = sum(len(doc.split()) for doc in source_documents)
        if total_words >= _RICH_SOURCE_THRESHOLD:
            return "EXTRACT"

        return "GENERATE"

    def _extract_mode(
        self,
        premise: str,
        source_documents: list[str],
    ) -> ConstraintSurface:
        """EXTRACT mode: decompose rich source into ConstraintSurface.

        Parses source documents for explicit constraints, characters,
        world systems, and timeline events.
        """
        surface = empty_constraint_surface()
        surface["premise_kernel"] = premise

        combined_source = "\n\n".join(source_documents)

        # Extract structured elements from source documents
        surface["forcing_constraints"] = self._extract_forcing_constraints(combined_source)
        surface["characters"] = self._extract_characters(combined_source)
        surface["character_count"] = len(surface["characters"])
        surface["institutions"] = self._extract_institutions(combined_source)
        surface["power_systems"] = self._extract_power_systems(combined_source)
        surface["resource_pressures"] = self._extract_resource_pressures(combined_source)
        surface["locations"] = self._extract_locations(combined_source)
        surface["timeline_events"] = self._extract_timeline_events(combined_source)
        surface["writing_rules"] = self._extract_writing_rules(combined_source)
        surface["banned_patterns"] = self._extract_banned_patterns(combined_source)
        surface["thematic_core"] = premise

        # Score the surface
        score = score_constraint_surface(surface)
        surface["constraint_depth_score"] = score
        surface["ready_to_write"] = score >= READINESS_THRESHOLD

        return surface

    def _generate_mode(self, premise: str) -> ConstraintSurface:
        """GENERATE mode: sparse prompt -> HTN + DOME -> ConstraintSurface.

        Uses HTN decomposition to create structural scaffolding, then
        DOME expansion to deepen with beat-level detail.
        """
        # Step 1: HTN decomposition
        outline = self._htn.decompose(premise)

        # Step 2: DOME expansion
        detailed = self._dome.expand(outline)

        # Step 3: Translate expanded outline to ConstraintSurface
        surface = self._outline_to_surface(premise, outline, detailed)

        return surface

    def _validate_and_iterate(self, surface: ConstraintSurface) -> ConstraintSurface:
        """ASP validate and iterate until readiness threshold or max iterations."""
        for iteration in range(MAX_ITERATIONS):
            score = score_constraint_surface(surface)
            surface["constraint_depth_score"] = score
            surface["ready_to_write"] = score >= READINESS_THRESHOLD

            if surface["ready_to_write"]:
                logger.info(
                    "Constraint surface ready (score=%.4f, iteration=%d)",
                    score,
                    iteration,
                )
                return surface

            # ASP validation
            result = self._asp.validate_surface(surface)

            if result["satisfiable"]:
                logger.info(
                    "ASP satisfied but score below threshold (%.4f), deepening",
                    score,
                )
            else:
                logger.info(
                    "ASP violations found (%d), fixing gaps",
                    len(result["violations"]),
                )

            # Fill gaps based on violations and missing fields
            surface = self._fill_gaps(surface, result)

        # Max iterations reached -- accept best effort (never-block rule)
        final_score = score_constraint_surface(surface)
        surface["constraint_depth_score"] = final_score
        surface["ready_to_write"] = True  # Force ready after max iterations
        logger.warning(
            "Max iterations reached (score=%.4f), accepting best effort",
            final_score,
        )
        return surface

    def _fill_gaps(
        self,
        surface: ConstraintSurface,
        validation: ValidationResult,
    ) -> ConstraintSurface:
        """Address gaps in the constraint surface.

        Inspects which fields are under-populated and adds template
        content to increase the score.  With LLM providers available,
        this would generate richer content via subprocess calls.
        """
        # Fill characters if too few
        chars = surface.get("characters", [])
        if len(chars) < 3:
            for i in range(3 - len(chars)):
                chars.append({
                    "name": f"Character_{len(chars) + 1}",
                    "role": "supporting",
                    "arc": "to be determined",
                    "knowledge_boundary": [],
                    "locked_facts": [],
                    "relationships": [],
                })
            surface["characters"] = chars
            surface["character_count"] = len(chars)

        # Fill institutions if empty
        if not surface.get("institutions"):
            surface["institutions"] = [
                {
                    "name": "Governing_Body",
                    "public_face": "maintains order",
                    "hidden_function": "controls information",
                },
            ]

        # Fill forcing constraints if too few
        fc = surface.get("forcing_constraints", [])
        if len(fc) < 3:
            defaults = [
                "No deus ex machina resolutions",
                "Character actions must follow from established motivations",
                "All abilities have costs",
            ]
            for d in defaults:
                if d not in fc:
                    fc.append(d)
            surface["forcing_constraints"] = fc[:5]

        # Fill resource pressures if empty
        if not surface.get("resource_pressures"):
            surface["resource_pressures"] = [
                {
                    "name": "primary_resource_conflict",
                    "scarcity": True,
                    "info_asymmetry": False,
                },
            ]

        # Fill series spine if empty
        if not surface.get("series_spine"):
            surface["series_spine"] = [
                {"book": 1, "arc": "Introduction and establishment"},
            ]

        # Fill writing rules if empty
        if not surface.get("writing_rules"):
            surface["writing_rules"] = [
                "Show, don't tell",
                "Ground abstract concepts in physical sensation",
            ]

        # Fill locations if empty
        if not surface.get("locations"):
            surface["locations"] = [
                {"name": "Primary_Setting", "sensory_details": "to be developed"},
            ]

        # Fill timeline if empty
        if not surface.get("timeline_events"):
            surface["timeline_events"] = [
                {
                    "name": "Inciting_Event",
                    "cause": "to be determined",
                    "public_narrative": "known version",
                    "reality": "hidden truth",
                },
            ]

        # Recompute score
        score = score_constraint_surface(surface)
        surface["constraint_depth_score"] = score
        surface["ready_to_write"] = score >= READINESS_THRESHOLD

        return surface

    @staticmethod
    def _outline_to_surface(
        premise: str,
        outline: dict,
        detailed: dict,
    ) -> ConstraintSurface:
        """Translate an HTN + DOME outline into a ConstraintSurface."""
        surface = empty_constraint_surface()
        surface["premise_kernel"] = premise
        surface["thematic_core"] = outline.get("thematic_core", "")

        # Characters from HTN extraction
        chars = outline.get("characters_extracted", [])
        surface["characters"] = [
            {
                "name": c,
                "role": "primary",
                "arc": "from outline",
                "knowledge_boundary": [],
                "locked_facts": [],
                "relationships": [],
            }
            for c in chars
        ]
        surface["character_count"] = len(surface["characters"])

        # Series spine from acts
        acts = outline.get("acts", [])
        surface["series_spine"] = [
            {"book": 1, "arc": act.get("summary", act.get("name", ""))}
            for act in acts
        ]

        return surface

    # ------------------------------------------------------------------
    # Extraction helpers (template-based, to be enhanced with LLM)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_forcing_constraints(source: str) -> list[str]:
        """Extract forcing constraints from source text."""
        constraints: list[str] = []
        # Look for explicit constraint markers
        for marker in ["must not", "cannot", "never", "always", "rule:"]:
            for line in source.splitlines():
                if marker in line.lower() and line.strip() not in constraints:
                    constraints.append(line.strip())
        return constraints[:5]

    @staticmethod
    def _extract_characters(source: str) -> list[dict]:
        """Extract character entries from source text."""
        # Template: look for lines that mention character-like patterns
        chars: list[dict] = []
        seen_names: set[str] = set()
        for line in source.splitlines():
            stripped = line.strip()
            # Simple heuristic: capitalised words after "character" or at
            # line start that look like names
            if stripped and stripped[0].isupper() and len(stripped.split()) <= 4:
                name = stripped.split(":")[0].strip() if ":" in stripped else stripped
                if name and name not in seen_names and len(name) < 50:
                    seen_names.add(name)
                    chars.append({
                        "name": name,
                        "role": "extracted",
                        "arc": "",
                        "knowledge_boundary": [],
                        "locked_facts": [],
                        "relationships": [],
                    })
        return chars[:10]

    @staticmethod
    def _extract_institutions(source: str) -> list[dict]:
        """Extract institutions from source text."""
        institutions: list[dict] = []
        markers = ["guild", "church", "council", "order", "academy", "kingdom",
                    "empire", "court", "senate", "tribunal"]
        for line in source.splitlines():
            lower_line = line.lower()
            for marker in markers:
                if marker in lower_line:
                    name = line.strip().split(".")[0][:60]
                    institutions.append({
                        "name": name,
                        "public_face": "to be determined",
                        "hidden_function": "to be determined",
                    })
                    break
        return institutions[:5]

    @staticmethod
    def _extract_power_systems(source: str) -> list[dict]:
        """Extract power/magic systems from source text."""
        systems: list[dict] = []
        markers = ["magic", "power", "ability", "force", "gift", "talent"]
        for line in source.splitlines():
            lower_line = line.lower()
            for marker in markers:
                if marker in lower_line:
                    systems.append({
                        "name": line.strip()[:60],
                        "capabilities": [],
                        "costs": [],
                    })
                    break
        return systems[:3]

    @staticmethod
    def _extract_resource_pressures(source: str) -> list[dict]:
        """Extract resource pressures from source text."""
        pressures: list[dict] = []
        markers = ["scarce", "shortage", "control", "supply", "trade", "resource"]
        for line in source.splitlines():
            lower_line = line.lower()
            for marker in markers:
                if marker in lower_line:
                    pressures.append({
                        "name": line.strip()[:60],
                        "scarcity": True,
                        "info_asymmetry": False,
                    })
                    break
        return pressures[:3]

    @staticmethod
    def _extract_locations(source: str) -> list[dict]:
        """Extract locations from source text."""
        locations: list[dict] = []
        markers = ["city", "village", "mountain", "forest", "castle", "tower",
                    "river", "sea", "island", "pass", "valley"]
        for line in source.splitlines():
            lower_line = line.lower()
            for marker in markers:
                if marker in lower_line:
                    locations.append({
                        "name": line.strip()[:60],
                        "sensory_details": "",
                    })
                    break
        return locations[:5]

    @staticmethod
    def _extract_timeline_events(source: str) -> list[dict]:
        """Extract timeline events from source text."""
        events: list[dict] = []
        markers = ["year", "ago", "before", "after", "during", "when",
                    "battle", "war", "founding", "fall"]
        for line in source.splitlines():
            lower_line = line.lower()
            for marker in markers:
                if marker in lower_line:
                    events.append({
                        "name": line.strip()[:60],
                        "cause": "extracted",
                        "public_narrative": "",
                        "reality": "",
                    })
                    break
        return events[:5]

    @staticmethod
    def _extract_writing_rules(source: str) -> list[str]:
        """Extract writing rules from source text."""
        rules: list[str] = []
        markers = ["write", "style", "voice", "tone", "pov", "perspective"]
        for line in source.splitlines():
            lower_line = line.lower()
            for marker in markers:
                if marker in lower_line:
                    rules.append(line.strip())
                    break
        return rules[:5]

    @staticmethod
    def _extract_banned_patterns(source: str) -> list[str]:
        """Extract banned patterns from source text."""
        banned: list[str] = []
        markers = ["avoid", "don't", "never use", "no ", "ban"]
        for line in source.splitlines():
            lower_line = line.lower()
            for marker in markers:
                if marker in lower_line:
                    banned.append(line.strip())
                    break
        return banned[:5]
