# Workflow

**A global goals engine. Fully self-hostable, open-source (MIT platform / CC0 catalog), runs on your own infrastructure.** Humanity declares shared Goals — research breakthroughs, great novels, successful prosecutions, cures, open datasets, whatever people actually want done — and a legion of diverse AI-augmented workflows pursues each Goal in parallel. Branches evolve, cross-pollinate, and get ranked by how far their outputs advance up each Goal's real-world outcome-gate ladder. The system is built for whatever people collectively care about next.

This repo contains substantial architecture and implementation work. The starter surfaces below help you navigate, extend, and connect — including via Obsidian if you use it.

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
