# EarthOS as a Workflow Universe — Build Record

**Date:** 2026-06-18
**Universe:** `earthos` (active)
**Goal:** `aa231afcf5cc` — "Build and maintain the public model of humanity's transition"
**Built by:** Cowork, on the live MCP platform, for Jonathan

This is the concrete follow-through on the synergy thesis in `2026-06-18-earthos-deep-dive-and-synergy.md`: a working EarthOS instance standing up on Workflow's existing primitives, to test how much of George Roessler's roadmap your platform already covers. Short answer: the whole conceptual spine went up in one session with zero new platform code.

## What was created

| Piece | Workflow primitive | ID / location |
|---|---|---|
| The EarthOS instance | Universe (soul + premise) | universe `earthos` |
| Its purpose / worldview | `soul.md` (full transition thesis, 8 domains, rebound discipline, risks/pathways, provenance method) | soul of `earthos` |
| The intent | Goal | `aa231afcf5cc` |
| Provenance honesty layer | Outcome-gate ladder (6 rungs) | ladder on the Goal |
| Mission of the Week | Runnable branch (3 nodes) | `earthos_verify_transition_signal_source_v1` (`4a0d0b9fa6c7`) |
| Response-layer mission | Runnable branch (3 nodes) | `earthos_summarize_policy_options_v1` (`214e76725d65`) |
| Foundational evidence | Canon source (daemon-synthesizable) | `canon/sources/civilization-model.md` |
| Living ontology — concept layer | Universe wiki page | `pages/concepts/earthos-eight-domains.md` |
| Living ontology — work layer | Universe wiki page | `pages/workflows/earthos-mission-catalog.md` |

Both branches validate as `runnable` and are bound to the Goal. The gate ladder is the literal EarthOS provenance scale turned into claimable rungs:

`signal_logged → emerging → needs_source → source_linked → established → response_mapped`

## EarthOS roadmap item → Workflow primitive (now instantiated)

| EarthOS roadmap (mostly unbuilt on his site) | On Workflow | Status here |
|---|---|---|
| "Living ontology" knowledge graph in a database | Universe wiki / brain (AI-maintainable) | **Built** (2 pages live; canon ingested) |
| Missions people claim and complete | Goal-bound branches | **Built** (2 runnable missions) |
| Provenance / confidence labels | Outcome-gate ladder + `claim_from_branch_run` | **Built** (6-rung ladder) |
| "Compare responses" / response layer | The policy-options mission branch | **Built** |
| Knowledge-graph → DB migration (Planned) | Already a DB-backed wiki | **N/A — already true** |
| AI-assisted gap detection (Future) | Daemon worldbuild + self-evolving loop | Available (daemon idle until invoked) |
| Node federation across cities (Future) | Per-universe instances under one platform | **Demonstrated** (earthos is one such node) |
| ITC time-credit ledger (Future) | contribution_events ledger + daemon market | Available (not wired in this pass) |
| Contributor pipeline + rewards (Planned) | 5 contribution surfaces + settle ledger | Available |

## What it would take to make it *do* work
Nothing structural — just a run. `extensions action=run_branch` on `4a0d0b9fa6c7` with a `transition_brief` input produces a `provenance_record`; `gates action=claim_from_branch_run` then records the rung reached against the ladder with an evidence URL. Multiple missions can fan out and be ranked on the Goal leaderboard. (Left un-run in this pass to avoid provider spend; the daemon has no auto-loop dispatched, so the universe is inert until explicitly invoked.)

## Honest notes
- Branch nodes are LLM-prompt nodes with no external effects and no source-code nodes, so there is nothing to sandbox-approve — they are safe to run.
- The two ontology pages and one canon doc are a deliberately small seed, not the full 69-concept graph; they prove the shape, not completeness.
- This is a faithful *port of the concept*, authored from the public site — not George's actual content or data.

## Pointers
- Synergy analysis: `docs/research/2026-06-18-earthos-deep-dive-and-synergy.md`
- Source project: https://earthos-assets--georgeroessler.replit.app/
