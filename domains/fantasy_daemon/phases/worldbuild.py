"""Worldbuild node -- universe graph; invoked by dispatch_execution on worldbuild signals."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from domains.fantasy_daemon.phases.world_state_db import connect, get_all_facts, init_db
from workflow.universe_soul import (
    premise_from_soul,
    read_legacy_premise,
    write_universe_soul,
)

logger = logging.getLogger(__name__)

# Worldbuilding topics in priority order.  Each cycle generates at most
# ``_MAX_DOCS_PER_CYCLE`` documents from the first uncovered topics.
WORLDBUILD_TOPICS = [
    "characters",
    "locations",
    "factions",
    "magic_system",
    "history",
    "culture",
    "creatures",
    "artifacts",
    "politics",
    "religion",
]

_MAX_DOCS_PER_CYCLE = 2

# Phase-level loop guardrail: after this many consecutive worldbuild cycles
# produce no signals_acted and no generated_files, self-pause the daemon
# rather than spin forever. Counter lives in ``health["worldbuild_noop_streak"]``
# and resets whenever a cycle lands real work. See STATUS.md entry for #9
# (bounded reflection didn't fire) and #6 (default-universe stuck for 15h).
_MAX_WORLDBUILD_NOOP_STREAK = 3


def worldbuild(state: dict[str, Any]) -> dict[str, Any]:
    """Perform worldbuilding: act on creative signals or fill gaps.

    Signal-driven (primary path):
    1. Read pending worldbuild signals from state or disk.
    2. For each signal, generate/update canon docs for SPECIFIC topics:
       - new_element: create a focused doc on the element.
       - contradiction: call LLM to decide which version is better,
         then update whichever is weaker.
       - expansion: read existing doc and expand with new details.
    3. Clear consumed signals.

    Gap-filling (fallback when no signals):
    1. Read the premise (PROGRAM.md) and user direction notes.
    2. Scan existing canon files and identify missing topics.
    3. Call the LLM to generate 1-2 new canon documents.
    4. Write generated documents to ``{universe_path}/canon/``.

    Always:
    5. Run MemoryManager promotion gates.
    6. Count high-confidence facts in the world state DB.
    7. Trigger KG re-indexing.
    8. Increment ``world_state_version``.

    Parameters
    ----------
    state : UniverseState
        Full universe state.  Optional ``_memory_manager`` for
        promotion gates, ``_db_path`` for world state DB,
        ``_universe_path`` for file I/O.

    Returns
    -------
    dict
        Partial state with:
        - ``world_state_version``: incremented version.
        - ``canon_facts_count``: updated count of high-confidence facts.
        - ``worldbuild_signals``: empty list (signals consumed).
        - ``quality_trace``: trace entry for this node.
    """
    from domains.fantasy_daemon.phases._activity import activity_log, update_phase
    from domains.fantasy_daemon.phases._paths import resolve_db_path

    db_path = resolve_db_path(state)
    promoted_count = 0
    canon_count = state.get("canon_facts_count", 0)

    activity_log(state, "Worldbuild: starting cycle")
    update_phase(state, "worldbuild")

    # --- 0. Auto-generate premise from canon if PROGRAM.md is missing ---
    auto_premise = _maybe_generate_premise(state)

    # --- 1. Check for creative signals ---
    signals = _load_worldbuild_signals(state)
    signals_acted = 0

    if signals:
        # --- 2. Act on specific signals (incremental) ---
        signals_acted, consumed_indices = _act_on_signals_incremental(signals, state)
        generated_files = [f"signal_{i}" for i in range(signals_acted)]
        # --- 3. Remove only consumed signals (leave unprocessed ones) ---
        _remove_consumed_signals(state, consumed_indices)
    else:
        # --- Fallback: gap-filling for bootstrap ---
        generated_files = _generate_canon_documents(state)

    # --- 4b. Trigger re-ingestion of new canon files ---
    if generated_files:
        universe_path = state.get("_universe_path")
        if universe_path:
            try:
                from workflow.memory.ingestion import ProgressiveIngestor
                canon_dir = Path(universe_path) / "canon"
                universe_id = Path(universe_path).stem
                ingestor = ProgressiveIngestor(canon_dir, universe_id)
                ingestor.survey()
                new = ingestor.check_for_new_files()
                if new:
                    ingestor.triage()
                    from workflow.memory.ingestion import IngestionPriority
                    for section in ingestor.get_next_batch(IngestionPriority.IMMEDIATE):
                        ingestor.mark_ingested(section)
                    logger.info("Ingested %d new canon files into memory", len(new))
            except Exception as e:
                logger.warning("Canon re-ingestion failed: %s", e)

    # --- 5. Run promotion gates via MemoryManager ---
    from workflow import runtime_singletons as runtime

    mgr = runtime.memory_manager
    if mgr is not None:
        try:
            result = mgr.run_promotion_gates()
            promoted_count = len(result.promoted_facts)
            logger.info(
                "Worldbuild promotion: %d facts, %d style rules, %d ASP candidates",
                promoted_count,
                len(result.promoted_style_rules),
                len(result.asp_rule_candidates),
            )
        except Exception as e:
            logger.warning("MemoryManager.run_promotion_gates() failed: %s", e)

    # --- 6. Count high-confidence facts in world state DB ---
    try:
        init_db(db_path)
        with connect(db_path) as conn:
            all_facts = get_all_facts(conn)
            # Canon = facts with confidence >= 0.8
            canon_count = sum(
                1 for f in all_facts if f.get("confidence", 0) >= 0.8
            )
    except Exception as e:
        logger.warning("Failed to count facts in world state DB: %s", e)

    # --- 7. Optionally trigger KG re-indexing ---
    _trigger_kg_reindex(state)

    # --- 8. Run Leiden community detection ---
    _run_leiden_clustering(state)

    # --- 9. Rebuild RAPTOR tree from updated canon ---
    _rebuild_raptor(state)

    # --- Phase-level loop guardrail: no-op streak tracking ---
    # A cycle counts as "no-op" when it acted on zero signals AND generated
    # zero new canon files. Unbounded no-op cycles starved default-universe
    # for 15h (STATUS.md #6/#9). Self-pause via health["stopped"] so the
    # universe graph's should_continue_universe routes to end.
    health = dict(state.get("health", {}))
    noop_this_cycle = signals_acted == 0 and not generated_files
    if noop_this_cycle:
        streak = int(health.get("worldbuild_noop_streak", 0)) + 1
    else:
        streak = 0
    health["worldbuild_noop_streak"] = streak

    # Phase 6 Task D: only bump world_state_version on real progress.
    # Unconditional bumping made telemetry climb on no-op cycles and masked
    # stuck state (STATUS 2026-04-14). Progress = acted on a signal,
    # generated a file, or promoted a fact via memory gates.
    prev_version = state.get("world_state_version", 0)
    made_progress = (
        signals_acted > 0 or bool(generated_files) or promoted_count > 0
    )
    new_version = prev_version + 1 if made_progress else prev_version

    stuck = noop_this_cycle and streak >= _MAX_WORLDBUILD_NOOP_STREAK
    if stuck:
        health["stopped"] = True
        health["idle_reason"] = "worldbuild_stuck"
        reason = (
            f"Worldbuild stuck: {streak} consecutive no-op cycles "
            "(no signals, no generated files). Self-pausing."
        )
        logger.warning(reason)
        activity_log(state, f"Worldbuild: {reason}")

    result: dict[str, Any] = {
        "world_state_version": new_version,
        "canon_facts_count": canon_count,
        "worldbuild_signals": [],  # Signals consumed
        "health": health,
        "quality_trace": [
            {
                "node": "worldbuild",
                "action": "worldbuild_real",
                "promoted_facts": promoted_count,
                "canon_facts_count": canon_count,
                "world_state_version": new_version,
                "generated_files": generated_files,
                "signals_acted": signals_acted,
                "auto_premise": bool(auto_premise),
                "noop_streak": streak,
                "self_paused": stuck,
            }
        ],
    }

    # Propagate auto-generated premise into state so downstream nodes see it
    if auto_premise:
        instructions = dict(state.get("workflow_instructions", {}))
        instructions["premise"] = auto_premise
        result["workflow_instructions"] = instructions
        result["premise_kernel"] = auto_premise

    return result


# ---------------------------------------------------------------------------
# Auto-premise generation
# ---------------------------------------------------------------------------


def _maybe_generate_premise(state: dict[str, Any]) -> str:
    """Auto-generate a premise from canon files if PROGRAM.md is missing.

    Only fires on the first worldbuild pass (version == 0).  Reads canon
    filenames and a sample of each file, then asks the LLM for a 2-3
    sentence creative direction.

    Returns the generated premise text, or empty string if not needed.
    """
    version = state.get("world_state_version", 0)
    if version > 0:
        return ""

    universe_path = state.get(
        "_universe_path", state.get("universe_path", "")
    )
    if not universe_path:
        return ""

    universe_dir = Path(universe_path)
    # Skip if premise already exists (on disk or in state)
    if read_legacy_premise(universe_dir).strip() or premise_from_soul(universe_dir).strip():
        return ""
    existing_premise = state.get("premise_kernel", "")
    if existing_premise and existing_premise.strip():
        return ""

    # Check for canon files
    canon_dir = universe_dir / "canon"
    if not canon_dir.exists():
        return ""

    canon_files: list[tuple[str, str]] = []
    try:
        for f in sorted(canon_dir.iterdir()):
            if f.is_file() and f.suffix == ".md" and not f.name.startswith("."):
                try:
                    sample = f.read_text(encoding="utf-8")[:500]
                    canon_files.append((f.name, sample))
                except OSError:
                    canon_files.append((f.name, ""))
            if len(canon_files) >= 10:
                break
    except OSError:
        return ""

    if not canon_files:
        return ""

    # Build prompt
    from domains.fantasy_daemon.phases._provider_stub import call_provider

    file_summaries = "\n\n".join(
        f"**{name}**:\n{sample}" for name, sample in canon_files
    )

    system = (
        "You are a creative writing director. Given a set of worldbuilding "
        "source materials, write a 2-3 sentence creative direction for a "
        "fantasy novel set in this world. Focus on what makes this world "
        "interesting and what the story's emotional core should be. "
        "Be specific to THIS world, not generic. Return ONLY the premise."
    )

    prompt = (
        f"# Source Materials ({len(canon_files)} files)\n\n"
        f"{file_summaries}\n\n"
        f"# Task\n\n"
        f"Write a 2-3 sentence creative direction for a novel in this world."
    )

    premise = call_provider(prompt, system, role="writer")
    if not premise or not premise.strip():
        logger.info("Auto-premise: LLM returned empty; skipping")
        return ""

    premise = premise.strip()

    # Write to PROGRAM.md as compatibility mirror and soul.md as intent profile.
    try:
        (universe_dir / "PROGRAM.md").write_text(premise, encoding="utf-8")
        write_universe_soul(
            universe_dir, purpose=premise, lineage="auto-generated-from-canon",
        )
        logger.info(
            "Auto-premise: generated from %d canon files (%d chars)",
            len(canon_files), len(premise),
        )
    except OSError as e:
        logger.warning("Failed to write auto-generated PROGRAM.md: %s", e)
        return ""

    return premise


# ---------------------------------------------------------------------------
# Signal-driven worldbuilding
# ---------------------------------------------------------------------------


def _load_worldbuild_signals(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Load pending worldbuild signals from state or disk.

    Checks two sources:
    1. ``worldbuild_signals`` in state (direct propagation).
    2. ``{universe_path}/worldbuild_signals.json`` on disk (file-based).
    """
    # Check state first
    signals = state.get("worldbuild_signals", [])
    if signals:
        return list(signals)

    # Check file-based signals
    universe_path = state.get(
        "_universe_path", state.get("universe_path", "")
    )
    if not universe_path:
        return []

    signals_file = Path(universe_path) / "worldbuild_signals.json"
    if not signals_file.exists():
        return []

    try:
        data = json.loads(signals_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError, TypeError):
        pass

    return []


def _remove_consumed_signals(
    state: dict[str, Any], consumed_indices: set[int],
) -> None:
    """Remove only the consumed signals, leaving unprocessed ones.

    This makes the synthesis queue resumable -- interrupted processing
    doesn't lose unprocessed signals.
    """
    universe_path = state.get(
        "_universe_path", state.get("universe_path", "")
    )
    if not universe_path or not consumed_indices:
        return

    signals_file = Path(universe_path) / "worldbuild_signals.json"
    try:
        if not signals_file.exists():
            return
        all_signals = json.loads(signals_file.read_text(encoding="utf-8"))
        if not isinstance(all_signals, list):
            return
        remaining = [
            s for i, s in enumerate(all_signals) if i not in consumed_indices
        ]
        signals_file.write_text(
            json.dumps(remaining, indent=2) + "\n", encoding="utf-8",
        )
        logger.info(
            "Removed %d consumed signals, %d remaining",
            len(consumed_indices), len(remaining),
        )
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to update worldbuild signals: %s", e)


def _act_on_signals_incremental(
    signals: list[dict[str, Any]], state: dict[str, Any],
) -> tuple[int, set[int]]:
    """Act on worldbuild signals incrementally.

    Returns (count_acted, set_of_consumed_indices).
    Only processes up to _MAX_DOCS_PER_CYCLE signals per pass.
    """
    universe_path = state.get(
        "_universe_path", state.get("universe_path", "")
    )
    if not universe_path:
        return 0, set()

    universe_dir = Path(universe_path)
    canon_dir = universe_dir / "canon"

    premise = _read_premise(universe_dir, state)
    if not premise:
        return 0, set()

    acted = 0
    consumed: set[int] = set()
    for idx, signal in enumerate(signals[:_MAX_DOCS_PER_CYCLE]):
        try:
            sig_type = signal.get("type", "")
            topic = signal.get("topic", "unknown")
            detail = signal.get("detail", "")

            if sig_type == "new_element":
                _handle_new_element(canon_dir, topic, detail, premise, state)
                acted += 1
                consumed.add(idx)
            elif sig_type == "contradiction":
                _handle_contradiction(canon_dir, topic, detail, premise, state)
                acted += 1
                consumed.add(idx)
            elif sig_type == "expansion":
                _handle_expansion(canon_dir, topic, detail, premise, state)
                acted += 1
                consumed.add(idx)
            elif sig_type == "synthesize_source":
                source_file = signal.get("source_file", "")
                if source_file:
                    success = _handle_synthesize_source(
                        canon_dir, source_file, premise, state,
                    )
                    if success:
                        acted += 1
                    else:
                        _record_synthesis_failure(canon_dir, source_file)
                    # Always consume — re-emit will re-queue if needed
                    consumed.add(idx)
            else:
                logger.debug("Unknown signal type: %s", sig_type)
                consumed.add(idx)  # Remove unknown signals too
        except Exception as e:
            logger.warning(
                "Failed to act on signal %s/%s: %s", signal.get("type"), topic, e
            )
            # Don't mark as consumed on failure -- will retry next cycle

    return acted, consumed


def _handle_new_element(
    canon_dir: Path,
    topic: str,
    detail: str,
    premise: str,
    state: dict[str, Any],
) -> None:
    """Create a focused canon document for a newly discovered element."""
    from domains.fantasy_daemon.phases._provider_stub import call_provider, last_provider

    topic_slug = topic.lower().replace(" ", "_").replace("-", "_")
    topic_label = topic.replace("_", " ").title()

    # Read existing canon for context
    existing_topics = _scan_existing_canon(canon_dir)
    existing_list = ", ".join(sorted(existing_topics)) if existing_topics else "none yet"

    system = (
        "You are a worldbuilding author for a fantasy novel. "
        "A new element has been discovered during writing. Create a focused, "
        "detailed canon document for it. Use markdown formatting with headers "
        "and lists. Be specific to this world, not generic. Write 300-800 words. "
        "Return ONLY the document content."
    )

    prompt = (
        f"# Story Premise\n\n{premise}\n\n"
        f"# Existing Canon Coverage\n\n{existing_list}\n\n"
        f"# New Discovery\n\n"
        f"Topic: {topic_label}\n"
        f"Detail from prose: {detail}\n\n"
        f"# Task\n\n"
        f"Create a canon document for this new element. Ground it in the "
        f"premise and expand on what the prose revealed."
    )

    content = call_provider(
        prompt, system, role="writer",
        fallback_response=_mock_worldbuild_response(topic),
    )
    if content:
        filename = f"{topic_slug}.md"
        _write_canon_file(canon_dir, filename, content, model=last_provider)
        logger.info("Created canon for new element: %s", filename)


def _handle_contradiction(
    canon_dir: Path,
    topic: str,
    detail: str,
    premise: str,
    state: dict[str, Any],
) -> None:
    """Resolve a contradiction between prose and canon.

    Asks the LLM which version makes for a better, more coherent universe
    given the full premise and context. Does NOT default to either side.
    """
    from domains.fantasy_daemon.phases._provider_stub import call_provider, last_provider

    topic_slug = topic.lower().replace(" ", "_").replace("-", "_")

    # Find the relevant canon file
    canon_content = ""
    canon_filename = ""
    if canon_dir.exists():
        for f in canon_dir.iterdir():
            if f.is_file() and f.suffix == ".md":
                slug = f.stem.lower().replace("-", "_").replace(" ", "_")
                if slug == topic_slug or topic_slug in slug or slug in topic_slug:
                    canon_content = f.read_text(encoding="utf-8")
                    canon_filename = f.name
                    break

    if not canon_content:
        # No existing canon to contradict -- treat as new element
        _handle_new_element(canon_dir, topic, detail, premise, state)
        return

    system = (
        "You are a worldbuilding continuity editor for a fantasy novel. "
        "There is a contradiction between what the prose says and what the "
        "canon notes say. Your job is NOT to automatically prefer either side. "
        "Instead, decide which version makes for a BETTER, more coherent "
        "universe given the full premise, the direction the story is going, "
        "and what serves the narrative best.\n\n"
        "If the canon is right, rewrite the canon document to be clearer about "
        "the correct version (so the writing stays aligned).\n"
        "If the prose discovered something better, rewrite the canon to "
        "incorporate the improvement.\n"
        "If both have merit, synthesize a version that keeps the best of each.\n\n"
        "Return ONLY the revised canon document content in markdown."
    )

    prompt = (
        f"# Story Premise\n\n{premise}\n\n"
        f"# Current Canon ({canon_filename})\n\n{canon_content[:2000]}\n\n"
        f"# Contradiction Found in Prose\n\n{detail}\n\n"
        f"# Task\n\n"
        f"Which version makes for a better universe? Rewrite the canon "
        f"document to resolve this contradiction. Explain nothing -- just "
        f"return the revised document."
    )

    new_content = call_provider(
        prompt, system, role="writer",
        fallback_response=canon_content,  # Keep original on failure
    )
    if new_content and new_content != canon_content:
        filepath = canon_dir / canon_filename
        filepath.write_text(new_content, encoding="utf-8")
        # Update provenance marker
        _write_canon_marker(canon_dir, canon_filename, model=last_provider)
        logger.info(
            "Resolved contradiction in %s: %s", canon_filename, detail[:80]
        )


def _handle_expansion(
    canon_dir: Path,
    topic: str,
    detail: str,
    premise: str,
    state: dict[str, Any],
) -> None:
    """Expand an existing thin canon document with new details from prose."""
    from domains.fantasy_daemon.phases._provider_stub import call_provider, last_provider

    topic_slug = topic.lower().replace(" ", "_").replace("-", "_")

    # Find the relevant canon file
    canon_content = ""
    canon_filename = ""
    if canon_dir.exists():
        for f in canon_dir.iterdir():
            if f.is_file() and f.suffix == ".md":
                slug = f.stem.lower().replace("-", "_").replace(" ", "_")
                if slug == topic_slug or topic_slug in slug or slug in topic_slug:
                    canon_content = f.read_text(encoding="utf-8")
                    canon_filename = f.name
                    break

    if not canon_content:
        # No existing doc -- treat as new element
        _handle_new_element(canon_dir, topic, detail, premise, state)
        return

    system = (
        "You are a worldbuilding author for a fantasy novel. "
        "An existing canon document needs to be expanded with new details "
        "that were revealed during writing. Integrate the new information "
        "naturally into the existing document. Keep everything that was there, "
        "add the new details, and ensure internal consistency. "
        "Return ONLY the revised document content in markdown."
    )

    prompt = (
        f"# Story Premise\n\n{premise}\n\n"
        f"# Current Document ({canon_filename})\n\n{canon_content}\n\n"
        f"# New Details from Prose\n\n{detail}\n\n"
        f"# Task\n\n"
        f"Expand the document with the new details. Keep existing content, "
        f"add the new information, maintain consistency."
    )

    new_content = call_provider(
        prompt, system, role="writer",
        fallback_response=canon_content,  # Keep original on failure
    )
    if new_content and new_content != canon_content:
        filepath = canon_dir / canon_filename
        filepath.write_text(new_content, encoding="utf-8")
        _write_canon_marker(canon_dir, canon_filename, model=last_provider)
        logger.info(
            "Expanded %s with: %s", canon_filename, detail[:80]
        )


def _handle_synthesize_source(
    canon_dir: Path,
    source_file: str,
    premise: str,
    state: dict[str, Any],
) -> bool:
    """Synthesize structured canon documents from a source file.

    Reads the source file from canon/sources/, extracts text, and
    generates structured canon documents using the ingestion framework.
    Updates the manifest with source -> synthesized doc mappings.

    Returns True if synthesis produced at least one document.
    """
    sources_dir = canon_dir / "sources"
    source_path = sources_dir / source_file
    if not source_path.exists():
        logger.warning("Source file not found: %s", source_path)
        return False

    try:
        data = source_path.read_bytes()
    except OSError as e:
        logger.warning("Failed to read source file %s: %s", source_file, e)
        return False

    from workflow.ingestion.extractors import (
        extract_text,
        get_last_bite_outcomes,
        synthesize_source,
    )

    text = extract_text(source_file, data)
    if not text.strip():
        logger.warning("No text extracted from %s", source_file)
        return False

    generated = synthesize_source(text, source_file, canon_dir, premise)

    # Task #17 Fix C: pull per-bite outcomes (populated for Tier-2 runs
    # only; empty dict for single-pass Tier-1) and mirror into the
    # manifest as ``last_bite_outcomes``. Lets a failed bite-loop be
    # diagnosed without re-running synthesis.
    bite_outcomes = get_last_bite_outcomes(source_file)

    # Update manifest with synthesized doc mappings
    if generated:
        from workflow.ingestion.core import SourceManifest

        manifest = SourceManifest.load(canon_dir)
        entry = manifest.get(source_file)
        if entry is not None:
            entry.synthesized_docs = generated
            if bite_outcomes:
                entry.last_bite_outcomes = bite_outcomes
            manifest.save(canon_dir)

        logger.info(
            "Synthesized %d docs from source %s: %s",
            len(generated), source_file, ", ".join(generated),
        )

        # Task #17 Fix E (expanded 2026-04-19 per task #49): forward
        # defense across BOTH knowledge.db + story.db. A successful
        # canon synthesis means any drift rows the daemon wrote against
        # the placeholder premise are now obsolete; wipe them
        # universe-wide so retrieval doesn't resurface hallucinated
        # "canon" on subsequent cycles.
        try:
            from domains.fantasy_daemon.phases.drift_cleanup import (
                cleanup_drift_all,
            )

            universe_path = state.get(
                "_universe_path", state.get("universe_path", "")
            )
            kg_path = state.get("_kg_path", "")
            db_path = state.get("_db_path", "")
            if universe_path and (kg_path or db_path):
                universe_id = Path(universe_path).stem
                cleanup_drift_all(universe_id, kg_path, db_path)
        except Exception:
            logger.warning(
                "Post-synthesis drift_cleanup failed for %s",
                source_file, exc_info=True,
            )

        return True

    # Synthesis produced nothing — still record the bite outcomes so
    # the manifest state explains why (e.g. "5 bites, all parse_failed").
    if bite_outcomes:
        from workflow.ingestion.core import SourceManifest

        manifest = SourceManifest.load(canon_dir)
        entry = manifest.get(source_file)
        if entry is not None:
            entry.last_bite_outcomes = bite_outcomes
            manifest.save(canon_dir)

    logger.warning("Synthesis produced no documents for %s", source_file)
    return False


_MAX_SYNTHESIS_RETRIES = 3


def _record_synthesis_failure(canon_dir: Path, source_file: str) -> None:
    """Increment synthesis_attempts in the manifest after a failed attempt.

    Marks the source as permanently failed once the retry limit is reached.
    This is the only place synthesis_attempts should be incremented —
    the API re-emit path reads the count but never changes it.
    """
    manifest_path = canon_dir / ".manifest.json"
    manifest: dict[str, Any] = {}
    try:
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    entry = manifest.get(source_file, {})
    attempts = entry.get("synthesis_attempts", 0) + 1
    entry["synthesis_attempts"] = attempts

    if attempts >= _MAX_SYNTHESIS_RETRIES:
        entry["synthesis_failed"] = True
        logger.warning(
            "Source %s failed synthesis after %d attempts, "
            "marking as permanently failed",
            source_file, attempts,
        )
    else:
        logger.info(
            "Synthesis attempt %d/%d failed for %s",
            attempts, _MAX_SYNTHESIS_RETRIES, source_file,
        )

    manifest[source_file] = entry
    try:
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
        )
    except OSError:
        logger.debug("Failed to update manifest", exc_info=True)


def _write_canon_marker(
    canon_dir: Path, filename: str, model: str = ""
) -> None:
    """Write a provenance marker for a canon file (used by reflect)."""
    import time as _time

    marker = canon_dir / f".{filename}.reviewed"
    try:
        marker.write_text(
            json.dumps({"reviewed_at": _time.time(), "model": model}),
            encoding="utf-8",
        )
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Canon document generation (gap-filling fallback)
# ---------------------------------------------------------------------------


def _generate_canon_documents(state: dict[str, Any]) -> list[str]:
    """Generate missing canon documents for the universe.

    Reads the premise and existing canon, identifies gaps, calls the
    LLM for up to ``_MAX_DOCS_PER_CYCLE`` new documents, and writes
    them to the canon directory.

    Returns a list of filenames that were generated (may be empty).
    """
    universe_path = state.get(
        "_universe_path", state.get("universe_path", "")
    )
    if not universe_path:
        logger.debug("No universe path available; skipping canon generation")
        return []

    universe_dir = Path(universe_path)
    canon_dir = universe_dir / "canon"

    # Read premise
    premise = _read_premise(universe_dir, state)
    if not premise:
        logger.info("No premise found; skipping canon generation")
        return []

    # Read user direction notes (optional enrichment)
    direction_notes = _read_direction_notes(universe_dir)

    # Scan existing canon files
    existing_topics = _scan_existing_canon(canon_dir)

    # Identify gaps
    gaps = _identify_gaps(existing_topics)
    if not gaps:
        logger.info("All worldbuilding topics covered; skipping generation")
        return []

    # Generate up to _MAX_DOCS_PER_CYCLE documents
    topics_to_generate = gaps[:_MAX_DOCS_PER_CYCLE]
    generated: list[str] = []

    for topic in topics_to_generate:
        try:
            content = _call_for_worldbuild(
                topic, premise, direction_notes, existing_topics
            )
            if content:
                from domains.fantasy_daemon.phases._provider_stub import last_provider
                filename = f"{topic}.md"
                _write_canon_file(canon_dir, filename, content, model=last_provider)
                # Verify the file actually exists on disk
                written_path = canon_dir / filename
                if written_path.exists():
                    generated.append(filename)
                    logger.info(
                        "Generated canon file: %s (%d chars, path=%s)",
                        filename, len(content), written_path,
                    )
                else:
                    logger.warning(
                        "Canon file %s was written but does not exist at %s",
                        filename, written_path,
                    )
            else:
                logger.warning("LLM returned empty content for topic '%s'", topic)
        except Exception as e:
            logger.warning(
                "Failed to generate canon for topic '%s': %s", topic, e
            )
            # Graceful: continue with next topic

    return generated


def _read_premise(universe_dir: Path, state: dict[str, Any]) -> str:
    """Read the story premise from PROGRAM.md, soul.md, or state.

    Falls back to ``premise_kernel`` in state if the file is missing.
    """
    content = read_legacy_premise(universe_dir).strip()
    if content:
        return content
    content = premise_from_soul(universe_dir).strip()
    if content:
        return content

    # Fallback to state
    return state.get("premise_kernel", "")


def _read_direction_notes(universe_dir: Path) -> str:
    """Read user direction notes for worldbuild context."""
    try:
        from workflow.notes import (
            format_notes_for_context,
            get_active_direction_notes,
        )

        notes = get_active_direction_notes(universe_dir)
        return format_notes_for_context(notes)
    except Exception:
        return ""


def _scan_existing_canon(canon_dir: Path) -> set[str]:
    """Return the set of topic slugs already covered by canon files.

    Maps filenames to topic slugs by stripping the extension and
    normalizing.  For example, ``magic_system.md`` -> ``magic_system``.
    """
    if not canon_dir.exists():
        return set()

    existing: set[str] = set()
    try:
        for f in canon_dir.iterdir():
            if f.is_file() and f.suffix == ".md":
                slug = f.stem.lower().replace("-", "_").replace(" ", "_")
                existing.add(slug)
    except OSError:
        logger.debug("Failed to scan canon directory", exc_info=True)

    return existing


def _identify_gaps(existing_topics: set[str]) -> list[str]:
    """Return worldbuilding topics not yet covered, in priority order."""
    return [t for t in WORLDBUILD_TOPICS if t not in existing_topics]


def _call_for_worldbuild(
    topic: str,
    premise: str,
    direction_notes: str,
    existing_topics: set[str],
) -> str:
    """Call the LLM to generate a worldbuilding document for a topic.

    Uses the provider stub's ``call_provider`` with role ``"writer"``.
    Returns the generated markdown content, or an empty string on failure.
    """
    from domains.fantasy_daemon.phases._provider_stub import call_provider

    topic_label = topic.replace("_", " ").title()

    existing_list = ", ".join(sorted(existing_topics)) if existing_topics else "none yet"

    system = (
        "You are a worldbuilding assistant for a fantasy novel. "
        "Generate a detailed, well-structured markdown document for the "
        "requested worldbuilding topic. Use headers, lists, and clear "
        "descriptions. Be creative but internally consistent. "
        "Write in an encyclopedic reference style suitable for an author "
        "to consult while writing."
    )

    prompt = (
        f"# Story Premise\n\n{premise}\n\n"
    )

    if direction_notes:
        prompt += f"# User Direction Notes\n\n{direction_notes}\n\n"

    prompt += (
        f"# Existing Canon Coverage\n\n"
        f"Topics already documented: {existing_list}\n\n"
        f"# Task\n\n"
        f"Generate a comprehensive worldbuilding document for: **{topic_label}**\n\n"
        f"The document should:\n"
        f"- Be consistent with the premise above\n"
        f"- Not contradict any existing canon topics\n"
        f"- Include specific names, details, and relationships\n"
        f"- Be 500-1500 words\n"
        f"- Use markdown formatting with headers and lists\n"
    )

    result = call_provider(
        prompt,
        system,
        role="writer",
        fallback_response=_mock_worldbuild_response(topic),
    )

    return result


def _mock_worldbuild_response(topic: str) -> str:
    """Generate a deterministic mock worldbuilding document.

    Used when no LLM provider is available (tests, offline mode).
    """
    topic_label = topic.replace("_", " ").title()
    return (
        f"# {topic_label}\n\n"
        f"## Overview\n\n"
        f"This document describes the {topic_label.lower()} of the world.\n\n"
        f"## Details\n\n"
        f"- The {topic_label.lower()} are a central element of the story.\n"
        f"- They have deep historical roots and complex relationships.\n"
        f"- Further details will emerge as the narrative develops.\n"
    )


def _write_canon_file(
    canon_dir: Path, filename: str, content: str, model: str = "",
) -> None:
    """Write a canon document to the canon directory.

    Creates the canon directory if it does not exist.  Writes a sidecar
    marker recording which model generated the file so that the reflect
    node can enforce quality-tier guards (weaker models never overwrite
    stronger models' work).
    """
    import json as _json
    import time as _time

    canon_dir.mkdir(parents=True, exist_ok=True)
    filepath = canon_dir / filename
    filepath.write_text(content, encoding="utf-8")

    # Write provenance marker
    marker = canon_dir / f".{filename}.reviewed"
    try:
        marker.write_text(
            _json.dumps({"reviewed_at": _time.time(), "model": model}),
            encoding="utf-8",
        )
    except OSError:
        pass

    logger.debug("Wrote canon file: %s (%d chars, model=%s)", filepath, len(content), model)


# ---------------------------------------------------------------------------
# KG re-indexing
# ---------------------------------------------------------------------------


def _trigger_kg_reindex(state: dict[str, Any]) -> None:
    """Index canon files into KG + vector store.

    Reads all canon/*.md files and passes them through the indexer
    which extracts entities/relationships/facts and indexes text chunks.
    Uses runtime singletons for the retrieval backends.
    """
    from workflow import runtime_singletons as runtime

    kg = runtime.knowledge_graph
    vs = runtime.vector_store
    embed = runtime.embed_fn
    if kg is None and vs is None:
        logger.debug("No retrieval backends available; skipping indexing")
        return

    universe_path = state.get("_universe_path", "")
    if not universe_path:
        return

    canon_dir = Path(universe_path) / "canon"
    if not canon_dir.is_dir():
        return

    from domains.fantasy_daemon.phases._provider_stub import call_provider
    from workflow.ingestion.indexer import index_text
    from workflow.memory.scoping import MemoryScope

    # Memory-scope Stage 2b: derive the universe tier from the
    # universe directory name (same convention Stage 2a migration used
    # when backfilling NULL rows). No sub-tiers on the worldbuild path
    # — canon ingestion is universe-wide.
    universe_id = Path(universe_path).name or ""
    scope = MemoryScope(universe_id=universe_id) if universe_id else None

    total_stats: dict[str, int] = {
        "entities": 0, "edges": 0, "facts": 0, "chunks_indexed": 0,
    }

    try:
        for f in sorted(canon_dir.iterdir()):
            if not f.is_file() or f.suffix != ".md" or f.name.startswith("."):
                continue
            try:
                text = f.read_text(encoding="utf-8")
                if not text.strip():
                    continue
                stats = index_text(
                    text,
                    source_id=f.stem,
                    knowledge_graph=kg,
                    vector_store=vs,
                    embed_fn=embed,
                    provider_call=call_provider,
                    scope=scope,
                )
                for k, v in stats.items():
                    total_stats[k] = total_stats.get(k, 0) + v
            except Exception as e:
                logger.warning("Failed to index %s: %s", f.name, e)
    except OSError:
        logger.debug("Failed to scan canon directory for indexing")

    logger.info(
        "KG re-index: %d entities, %d edges, %d facts, %d vector chunks",
        total_stats["entities"], total_stats["edges"],
        total_stats["facts"], total_stats["chunks_indexed"],
    )


def _run_leiden_clustering(state: dict[str, Any]) -> None:
    """Run Leiden community detection on the KG after indexing.

    Detects communities (character groups, factions, plot threads) and
    stores them in the KG's community table. Non-blocking -- failures
    are logged but don't affect the worldbuild cycle.
    """
    from workflow import runtime_singletons as runtime

    kg = runtime.knowledge_graph
    if kg is None:
        return

    try:
        from workflow.knowledge.leiden import detect_communities_from_kg

        communities = detect_communities_from_kg(kg)
        if communities:
            # Store communities in KG for retrieval
            try:
                kg.store_communities(communities)
            except AttributeError:
                # KG may not have store_communities yet -- just log
                logger.debug(
                    "KG.store_communities not available; %d communities detected but not stored",
                    len(communities),
                )
            logger.info(
                "Leiden clustering: %d communities detected",
                len(communities),
            )
        else:
            logger.debug("Leiden clustering: no communities (empty graph)")
    except Exception as e:
        logger.debug("Leiden clustering skipped: %s", e)


def _rebuild_raptor(state: dict[str, Any]) -> None:
    """Rebuild RAPTOR tree from updated canon files.

    Called after worldbuild writes/updates canon docs so the retrieval
    router gets fresh multi-level summaries.  Uses the shared helper
    in ``knowledge.raptor`` which is also called at daemon startup.
    """
    from workflow import runtime_singletons as runtime

    universe_path = state.get("_universe_path")
    if not universe_path:
        return

    try:
        from workflow.knowledge.raptor import rebuild_raptor_from_canon

        canon_dir = str(Path(universe_path) / "canon")
        universe_id = Path(universe_path).stem or "default"
        rebuild_raptor_from_canon(
            canon_dir=canon_dir,
            embed_fn=runtime.embed_fn,
            universe_id=universe_id,
        )
    except Exception as e:
        logger.debug("RAPTOR rebuild skipped: %s", e)
