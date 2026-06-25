# Workflow

**A global goals engine. Fully self-hostable, open-source (MIT platform / CC0 catalog), runs on your own infrastructure.** Humanity declares shared Goals — research breakthroughs, great novels, successful prosecutions, cures, open datasets, whatever people actually want done — and a legion of diverse AI-augmented workflows pursues each Goal in parallel. Branches evolve, cross-pollinate, and get ranked by how far their outputs advance up each Goal's real-world outcome-gate ladder. The system is built for whatever people collectively care about next.

This repo contains substantial architecture and implementation work. The starter surfaces below help you navigate, extend, and connect — including via Obsidian if you use it.

**Built by Jonathan Farnsworth** (jonathan.m.farnsworth@gmail.com, GitHub [@Jonnyton](https://github.com/Jonnyton)) — sole human author; the only co-authors are the project's own AI agents.

## Proof of life

<!-- proof:start -->
The engine runs on its own infrastructure and patches itself in public. The volatile facts below are *linked to live state* rather than copied here, so this section can't go stale:

- **It ships its own fixes.** The patch loop turns filed capability gaps into machine-authored PRs through a cross-family writer/checker gate — see [`.github/workflows/auto-fix-bug.yml`](.github/workflows/auto-fix-bug.yml) and [`workflow/bug_investigation.py`](workflow/bug_investigation.py). Recent self-patches: the [commit and Actions history](https://github.com/Jonnyton/Workflow/actions).
- **Canary-gated deploys, live receipts.** The current deploy SHA, canary status, queue throughput, and the provider list are returned live by the `get_status` MCP tool and rendered at [tinyassets.io/fine-print](https://tinyassets.io/fine-print) — read the numbers there rather than trusting a copy here.
- **7,856 tests across 406 files, all offline.** Providers are mocked (`_FORCE_MOCK=True`); no API keys: `pip install -e .[dev] && pytest -q`.

Honest caveat (the site says this too): the *user-facing* outcome loop hasn't shipped a real external artifact yet — draft mode is on, OAuth is unwired, `run_count` is 0. What's proven today is the engine, the architecture, and the self-patching loop; the first shipped real-world outcome is the next milestone.

<sub>Repo facts refreshed 2026-06-14 by `scripts/gen_discoverability.py` (bounded — rewrites only between the markers).</sub>
<!-- proof:end -->

## The flagship: the patch loop

A user's chatbot hits a capability gap → files it as a patch request → a daemon picks it up, drafts a fix, routes it through evidence gates, and ships when the gates are satisfied → the next summon starts smarter. No design committee drew this loop; it was pulled out of `user-sim` sessions where chatbot-personas filed the first patches against the system. Walk it on the site at [/patch-loop](https://tinyassets.io/patch-loop); read the implementation in [`auto-fix-bug.yml`](.github/workflows/auto-fix-bug.yml) + [`workflow/bug_investigation.py`](workflow/bug_investigation.py).

## See the code (one click from here)

The entry path should reach functions, not just docs. Representative core:

- **The MCP surface** every chatbot connects to — [`workflow/universe_server.py`](workflow/universe_server.py) (the `universe` / `extensions` / `goals` / `gates` / `wiki` / `get_status` tools).
- **The daemon run loop** — [`fantasy_daemon/__main__.py`](fantasy_daemon/__main__.py), the current default runtime (LangGraph universe graph, SQLite checkpointer, pause/resume). The branch-execution *substrate* is goal-agnostic — branch specs compile to graphs via [`workflow/graph_compiler.py`](workflow/graph_compiler.py) — though this domain is still the hardcoded default; extracting the runtime into each universe's soul-declared loop is tracked in the [de-fantasy audit](docs/audits/2026-06-24-fantasy-architecture-residue-audit.md).
- **Branch spec → executable graph** — [`workflow/graph_compiler.py`](workflow/graph_compiler.py) (compiles a declarative branch into a runnable `StateGraph`; approval-gated node execution).
- **The evaluation/gate primitive** — [`workflow/node_eval.py`](workflow/node_eval.py).

## What's strongest here

A coherent, dependency-verified stack (LangGraph / FastMCP / LanceDB / igraph / clingo) wired into a single self-patching engine; design philosophy with teeth (minimal primitives, fork-over-build, commons-first privacy); operational seriousness (canary-gated deploys, deploy receipts tied to source SHA, ~7,800 offline tests); and a system honest enough to file bugs against itself and state in public what it hasn't shipped yet.

## Quick Start (for contributors)

Clone-to-green-tests in ~5 minutes on a clean machine:

```bash
git clone https://github.com/Jonnyton/Workflow.git
cd Workflow
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .[dev]
pytest -q                 # full suite — no API keys needed (tests mock providers)
ruff check                # lints clean on a fresh clone
```

All tests run offline with `_FORCE_MOCK=True` set in `tests/conftest.py`. No `ANTHROPIC_API_KEY` or similar required for CI or local dev. If any test fails on a clean clone, file an issue — that's a TEST-1 regression.

Cross-platform notes:
- Tested on Windows, macOS, Linux. Paths use `pathlib.Path` — backslashes don't leak into tests.
- Python 3.11+ required (see `pyproject.toml`).
- The tray (`workflow/workflow_tray.py`) is Windows-first; macOS/Linux support is work-in-progress. Platform code is cross-platform.

## Start Here

1. Read [STATUS.md](STATUS.md) for live state.
2. Read [PLAN.md](PLAN.md) for architecture and design intent.
3. Read [AGENTS.md](AGENTS.md) for process rules.
4. Read [docs/project-lineage.md](docs/project-lineage.md) for how Workflow grew out of the earlier Hex, Echoes, Fantasy Writer, and Fantasy Author work.
5. Use `python scripts/docview.py` for large Markdown, text, and JSON files
   before any raw whole-file read.
6. Capture loose user ideas in [ideas/INBOX.md](ideas/INBOX.md) or with
   `python scripts/capture_idea.py "Idea summary"`.

## Core Hubs

- [AGENTS.md](AGENTS.md): process truth.
- [PLAN.md](PLAN.md): design truth.
- [STATUS.md](STATUS.md): live-state truth.
- [docs/portfolio/README.md](docs/portfolio/README.md): public project graph, lineage, and auto-maintenance standard.
- [ideas/INDEX.md](ideas/INDEX.md): idea capture, triage, and shipped ledger.
- [knowledge/INDEX.md](knowledge/INDEX.md): human-readable knowledge map.

## Notes

- The new `knowledge/` docs complement `knowledge.db`; they do not replace it.
- The new `docs/exec-plans/` surface complements existing planning docs like
  `BUILD_PREP.md` and `RESTRUCTURE_PLAN.md`; it does not invalidate them.
- The user may steer multiple live sessions across different providers at once.
  Durable coordination belongs in files, not only in chat.
