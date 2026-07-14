# Brain Crawl Format — Context-Lean, Indexed, Evolvable (2026-07-09)

**Status:** Binding design note. Applies the commons architecture (graph + lenses) to the universe brain's AI-facing surface. Industry grounding: context engineering (context window as RAM — load exactly what the next step needs), llms.txt-class routing surfaces (~10x token reduction serving clean markdown), AGENTS.md-class standards, and the LLM-Wiki pattern (accumulating, interlinked synthesis beats re-fragmenting retrieval).

## 1. The crawl surface is a LENS
The brain's substrate is the graph (artifacts + links + claims, commons-architecture §1/§3). Its AI-facing form is a GENERATED markdown tree — a lens, default-provided as a commons artifact, user-forkable like any lens. Serialization, not storage.

## 2. The root rule
The tree's root contains **exactly one file: `index.md`** — declaring (a) brain identity + theme, (b) **crawl-profile version** (e.g. `profile: OKF-2026.07`) so any visiting AI knows the convention in force, (c) a map of top-level sections: one-line summaries + token estimates + freshness. Budget: root index <= ~2k tokens (profile-tunable).

## 3. The fractal invariant (progressive disclosure)
Every directory: exactly one index summarizing its children within budget (default <= ~1k tokens); leaves are small, single-topic, front-mattered (`type, updated, links, ~tokens`). Link, never inline. Stable content-addresses. An AI spends tokens DECIDING where to go before spending tokens READING; no query pays for the whole brain.

## 4. Accumulate, don't fragment
Synthesis notes are first-class: recurring themes get compounded wiki-style pages that cross-reference sources, so subtle questions hit accumulated understanding instead of re-assembled fragments every time.

## 5. Crawlability is a GATE LADDER (machine-checkable)
Index coverage (no orphans) · per-level token budgets · link integrity · staleness bounds. A brain CLAIMS profile compliance with evidence. Archetypes may require it; lenses may filter on it.

## 6. The profile itself is a versioned COMMONS artifact
"AI-friendly crawlable" is not frozen platform law — the profile evolves in the commons (fork-first, upstream via proposals, per commons-architecture §5). Universes migrate between profile versions via workflow; the gate ladder verifies arrival. The community collectively evolves what crawlable means — by design, not accident.

## 7. The GARDENER (standing goal, ships with every archetype)
Brain maintenance is a standing goal: re-summarize indexes on change, merge fragments into synthesis notes, prune stale branches, refresh metadata, re-claim the crawlability gates. Memory upkeep = ordinary batch compute the brain purchases for itself — the demand engine feeding the brain's own quality.

## 8. Do-not-build
A fixed platform-owned brain schema; inlined mega-files; RAG-only retrieval with no accumulation; any crawl surface that isn't regenerable from the graph.
