# START HERE — Claude Code Kickoff (post-vacation, one session)

**You are Claude Code, in a checkout of github.com/Jonnyton/tinyassets, with this bundle unzipped alongside.**
This bundle is the complete output of a 2026-07-08/09 design sprint with Claude Fable 5 (access since ended). Everything is decided; your job is landing and executing, not redesigning.

## Immediate sequence

1. **Land the bundle** (from repo root, bundle unzipped as ./paid_market_core):
```bash
git checkout -b paid-market-core
cp -r paid_market_core/tinyassets/paid_market tinyassets/
cp paid_market_core/tests/test_paid_market_core.py tests/
mkdir -p docs/design-notes && cp paid_market_core/docs/design-notes/*.md docs/design-notes/ 2>/dev/null
cp paid_market_core/docs/*.md docs/exec-plans/active/
cp paid_market_core/SUCCESSION-2026-07-08.md paid_market_core/USER-PATH-2026-07-08.md paid_market_core/DEMO-RUNBOOK-cookbook.md docs/
python3 -m pytest tests/test_paid_market_core.py -q --noconftest   # expect 173 passed
git add -A && git commit -m "Paid-market core + Tracks E-I specs + demo runbook (design sprint 2026-07-08/09)"
git push -u origin paid-market-core   # then open PR
```
(Repo conftest needs langgraph; the suite is standalone by design — keep --noconftest until env has full deps.)

2. **Production fixes (P0/P1)** — verify with the founder these are done; if not, they outrank everything:
   - P0: `write_graph` has NO approval gate — anonymous public writes persist (test artifact goal `1a917636ae83` needs deletion). Restore the gate WITH an actionable error message.
   - P1: `/data/wiki` Permission denied — wiki subsystem down; volume must be writable by daemon uid.
   - Evidence: docs/.../2026-07-08-production-mcp-sweep.md

3. **Read, in order:** OPERATING-NOTES.md (binding constraints — esp. §1 non-custodial, which shapes Wave 2) → SUCCESSION-2026-07-08.md (execution order, module map, do-not-redesign warnings) → USER-PATH-2026-07-08.md (binding UX law: primitives + commons, never features; seam register; demo-path coverage table) → DEMO-RUNBOOK-cookbook.md (the investor demo; its dependencies are demo-blocking).

## Adopt OpenSpec at landing (step 1.5 — before any Wave 2 code)
After the bundle lands and tests pass, initialize OpenSpec (Fission-AI, `openspec init`) and migrate:
- Track E–I specs + token architecture + boundary/demand notes → `openspec/specs/` as capability specs (source of truth). Preserve the HARD RULES verbatim as requirements — they are the drift-guards this framework exists for.
- Each queued work item below (Wave 2 transport, demo seeds, migrations) → an OpenSpec **change proposal** (proposal + design + tasks) BEFORE implementation. No Wave 2 code outside a proposal.
- Repo's legacy docs/exec-plans remain as historical record; new work flows through openspec/changes only. Reconcile inside the repo — do not duplicate spec systems.
- OPERATING-NOTES, USER-PATH's design law, and SUCCESSION's do-not-redesign warnings become the OpenSpec project conventions/AGENTS guidance.

## Work queue after landing (from SUCCESSION §3, demo-blocking items promoted)

A. Track E Wave 2 transport: claim + settle + ledger persistence — call the adapters in ledger.py, NEVER hand-write postings; every settlement path ends with assert_drained. Matching uses match.best_execution, never greedy.
B. Demo-blocking seeds (see also docs/2026-07-09-demand-side-design.md §4 and docs/2026-07-09-boundary-layer-design.md (connections-as-grants, action caps, exactly-once effect rules §4 + adapters-never-see-credentials §10 — hard rules; typed artifact flows §12; commons substrate/scopes/lenses/federation: docs/2026-07-09-commons-architecture.md — note its §6 do-not-build list; brain crawl format: docs/2026-07-09-brain-crawl-format.md — root=index.md only, gardener standing goal, profile-as-commons-artifact; discovery flows + distribution-artifact checklist: docs/2026-07-09-discovery-flows.md — note the supply-door sequencing HARD RULE and the earnings-calculator artifact; market opens at zero via supply-curve clearing: docs/2026-07-09-market-open-dynamics.md — supersedes any floating-base-price language, volunteer lane bypasses settlement; market-data layer/screeners/explorer: docs/2026-07-09-market-data-layer.md — feeds are primitives, screeners are lenses, optimizer ships as a standing goal; founder-universe archetype: docs/2026-07-09-founder-universe-archetype.md + FOUNDER-GOAL-MANIFEST.md (user zero's 16 standing goals; sentinel + gardener first) — conversion is REMIX via model adaptation profiles; cross-venue routing: docs/2026-07-09-cross-venue-routing.md — no fee on external pass-through [hard rule], generalized ceiling, cross-venue index day one) — every archetype ships with week-one-win standing goals; bounty rules pinned in §2): six harness archetypes (OpenClaw/Hermes/Obsidian/project-folder/Codex/Claude shapes) · Dataset Forge commons graph (Track G §5b) · appliance carrier rev-1 (Track I §3e) · recipe fine-tune pipeline · code-CAD design-flow nodes + printable gates (Track I §I5).
C. Migrations 006/007 → quote/curve endpoints (unauthenticated, cached, MCP text-block REQUIRED) → ceiling poller (the "-1" sentinel is already handled).
D. Then Tracks F → H → G → I per their wave tables.

## Founder decisions still open (do not guess these)
Forward collateral/threshold/bucket defaults (Track E §3, §6 trust-memory override) · training threshold (F §2) · license registry contents (G §2) · shuttle min-fill (I §2) · carrier in-house vs bounty (I §3e) · token items (token-architecture §6 + legal gates §5, stacking with Track H §3) · runbook open items (recipe collection, family question, meeting date, maker city).

## Also in this bundle
- TinyAssets-Pitch.pptx — the investor deck (15 slides, finished; $900K ask, staged hiring). Keep in sync with any narrative changes.
- Full module map + invariant discipline: SUCCESSION §3-4. The pure modules assert conservation and fail loud; if transport ever needs to "adjust" a settlement number, stop — that is a design error, and two demonstrated exploits in the adversarial review doc show why.
