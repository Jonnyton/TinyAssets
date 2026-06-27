"""ASP engine -- Clingo wrapper for formal constraint validation.

Primary interface consumed by the evaluation agent's Tier 1 structural
checks:  ``ASPEngine.validate(scene_facts, world_rules) -> ValidationResult``

Uses incremental multi-shot solving for validating multiple scenes
without re-grounding the base program each time.
"""

from __future__ import annotations

import logging
from pathlib import Path

from typing_extensions import TypedDict

from tinyassets.constraints.constraint_surface import ConstraintSurface

logger = logging.getLogger(__name__)

# Default path to the base world rules ASP program
_DEFAULT_RULES_PATH = Path(__file__).resolve().parents[2] / "data" / "world_rules.lp"


class ValidationResult(TypedDict):
    """Result of an ASP validation run."""

    satisfiable: bool
    """True if the program has at least one answer set (no violations)."""

    violations: list[str]
    """Human-readable descriptions of violated constraints.
    Empty when satisfiable is True."""

    models: list[list[str]]
    """String representations of atoms in each answer set found.
    Empty when unsatisfiable."""

    atoms: list[str]
    """Flat list of all shown atoms from the first model.
    Convenience accessor -- empty when unsatisfiable."""


class ASPEngine:
    """Clingo-based Answer Set Programming engine.

    Parameters
    ----------
    base_rules_path : str or Path or None
        Path to a ``.lp`` file with base world rules.  Defaults to
        ``data/world_rules.lp``.  Pass an empty string to skip loading
        base rules.
    """

    def __init__(self, base_rules_path: str | Path | None = None) -> None:
        if base_rules_path is None:
            base_rules_path = _DEFAULT_RULES_PATH
        self._base_rules: str = ""
        if base_rules_path:
            p = Path(base_rules_path)
            if p.exists():
                self._base_rules = p.read_text(encoding="utf-8")
            else:
                logger.warning("Base rules file not found: %s", p)

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    def validate(
        self,
        scene_facts: str,
        world_rules: str | None = None,
    ) -> ValidationResult:
        """Validate scene facts against world rules.

        Parameters
        ----------
        scene_facts : str
            ASP facts describing the current scene state.
        world_rules : str or None
            Additional ASP rules beyond the base rules.  If *None*, only
            the base rules loaded at construction time are used.

        Returns
        -------
        ValidationResult
            Contains satisfiability flag, violation descriptions, models,
            and shown atoms.
        """
        import clingo  # lazy import -- clingo is optional in early phases

        program = self._base_rules
        if world_rules:
            program += "\n" + world_rules
        program += "\n" + scene_facts

        ctl = clingo.Control(["0"])  # enumerate all models
        ctl.add("base", [], program)
        ctl.ground([("base", [])])

        models: list[list[str]] = []
        with ctl.solve(yield_=True) as handle:
            for model in handle:
                atoms = [str(a) for a in model.symbols(shown=True)]
                models.append(atoms)
            solve_result = handle.get()

        satisfiable = solve_result.satisfiable is True

        if satisfiable:
            first_atoms = models[0] if models else []
            return ValidationResult(
                satisfiable=True,
                violations=[],
                models=models,
                atoms=first_atoms,
            )

        # UNSAT: constraints are violated -- this is a valid result, not an error
        violations = self._extract_violations(program)
        return ValidationResult(
            satisfiable=False,
            violations=violations,
            models=[],
            atoms=[],
        )

    def validate_incremental(
        self,
        scenes: list[str],
        world_rules: str | None = None,
    ) -> list[ValidationResult]:
        """Validate multiple scenes using incremental multi-shot solving.

        Each scene's facts are added as a separate grounding step,
        avoiding full re-grounding of the base program.

        Parameters
        ----------
        scenes : list of str
            ASP fact strings, one per scene.
        world_rules : str or None
            Additional rules beyond the base.

        Returns
        -------
        list of ValidationResult
            One result per scene.
        """
        import clingo

        # Build the base program with step-based incremental encoding
        base_program = self._base_rules
        if world_rules:
            base_program += "\n" + world_rules

        results: list[ValidationResult] = []

        ctl = clingo.Control(["0"])
        ctl.add("base", [], base_program)
        ctl.ground([("base", [])])

        for i, scene_facts in enumerate(scenes):
            step_name = f"step_{i}"
            ctl.add(step_name, [], scene_facts)
            ctl.ground([(step_name, [])])

            models: list[list[str]] = []
            with ctl.solve(yield_=True) as handle:
                for model in handle:
                    atoms = [str(a) for a in model.symbols(shown=True)]
                    models.append(atoms)
                solve_result = handle.get()

            satisfiable = solve_result.satisfiable is True

            if satisfiable:
                first_atoms = models[0] if models else []
                results.append(ValidationResult(
                    satisfiable=True,
                    violations=[],
                    models=models,
                    atoms=first_atoms,
                ))
            else:
                full_program = base_program + "\n" + scene_facts
                violations = self._extract_violations(full_program)
                results.append(ValidationResult(
                    satisfiable=False,
                    violations=violations,
                    models=[],
                    atoms=[],
                ))

        return results

    def validate_surface(
        self,
        surface: ConstraintSurface,
        extra_rules: str = "",
    ) -> ValidationResult:
        """Translate a ConstraintSurface to ASP facts and validate.

        Parameters
        ----------
        surface : ConstraintSurface
            The constraint surface to validate.
        extra_rules : str
            Additional ASP rules beyond the base.

        Returns
        -------
        ValidationResult
        """
        facts = surface_to_asp_facts(surface)
        return self.validate(facts, world_rules=extra_rules or None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_violations(program: str) -> list[str]:
        """Best-effort extraction of which integrity constraints were violated.

        Clingo does not natively report *which* constraint caused UNSAT.
        We parse the integrity constraints from the program and report
        them all as potential violations.  A future enhancement could use
        Clingo's assumption-based debugging for precise core extraction.
        """
        violations: list[str] = []
        for line in program.splitlines():
            stripped = line.strip()
            if stripped.startswith(":-"):
                # Remove the leading ":- " and trailing "."
                body = stripped[2:].rstrip(".")
                violations.append(f"Integrity constraint violated: {body.strip()}")
        return violations


def surface_to_asp_facts(surface: ConstraintSurface) -> str:
    """Convert a ConstraintSurface to ASP fact predicates.

    Generates ground atoms that pair with the rules in ``world_rules.lp``.
    Names are sanitised (spaces -> underscores, lowercase for predicates,
    quoted strings for atom arguments).
    """
    lines: list[str] = []

    def _q(s: str) -> str:
        """Quote a string for ASP atom arguments."""
        safe = s.replace('"', '\\"').replace("\n", " ")
        return f'"{safe}"'

    # Characters
    for ch in surface.get("characters", []):
        name = ch.get("name", "unknown")
        lines.append(f"character({_q(name)}).")
        # Knowledge boundaries -> knows/2 facts
        for fact in ch.get("locked_facts", []):
            lines.append(f"knows({_q(name)}, {_q(fact)}).")

    # Institutions
    for inst in surface.get("institutions", []):
        name = inst.get("name", "unknown")
        lines.append(f"institution({_q(name)}).")
        if inst.get("public_face"):
            lines.append(f"has_public_face({_q(name)}).")
        if inst.get("hidden_function"):
            lines.append(f"has_hidden_agenda({_q(name)}).")

    # Power systems -> abilities with costs
    for ps in surface.get("power_systems", []):
        sys_name = ps.get("name", "unknown")
        for cap in ps.get("capabilities", []):
            lines.append(f"ability({_q(cap)}, {_q(sys_name)}).")
        for cost in ps.get("costs", []):
            # Link cost to each capability in the system
            for cap in ps.get("capabilities", []):
                lines.append(f"has_cost({_q(cap)}, {_q(sys_name)}).")

    # Conflicts
    for rp in surface.get("resource_pressures", []):
        name = rp.get("name", "unknown")
        lines.append(f"conflict({_q(name)}).")
        if rp.get("scarcity"):
            lines.append(f"driven_by_scarcity({_q(name)}).")
        if rp.get("info_asymmetry"):
            lines.append(f"driven_by_info_asymmetry({_q(name)}).")

    # Timeline events
    for evt in surface.get("timeline_events", []):
        name = evt.get("name", "unknown")
        lines.append(f"historical_event({_q(name)}).")
        if evt.get("cause"):
            lines.append(f"has_explicit_cause({_q(name)}).")

    # Knowledge layers (topics)
    for evt in surface.get("timeline_events", []):
        name = evt.get("name", "unknown")
        lines.append(f"topic({_q(name)}).")
        if evt.get("public_narrative"):
            lines.append(f'knowledge_layer({_q(name)}, "public").')
        if evt.get("reality"):
            lines.append(f'knowledge_layer({_q(name)}, "hidden").')

    # Character goal conflicts
    characters = surface.get("characters", [])
    for ch in characters:
        name = ch.get("name", "unknown")
        for rel in ch.get("relationships", []):
            other = rel.get("character", "")
            if rel.get("conflict"):
                lines.append(
                    f"exists_goal_conflict({_q(name)}, {_q(other)})."
                )

    return "\n".join(lines)
