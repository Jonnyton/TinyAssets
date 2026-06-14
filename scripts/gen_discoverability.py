#!/usr/bin/env python3
"""Regenerate the README "Proof of life" block from durable sources.

Goal: the entry path always surfaces the project's strongest, *current*
evidence without rotting or bloating. So:

- Volatile operational facts (deploy SHA, queue throughput, canary status,
  provider list) are LINKED to live state (`get_status` / Actions), never
  copied into the README, so they can never go stale here.
- The one repo-derived figure (the offline test count) is recomputed here.
- The block is BOUNDED: this script rewrites only the marked region, never
  appends, so the README cannot grow over time.

Usage:
    python scripts/gen_discoverability.py          # rewrite the block in place
    python scripts/gen_discoverability.py --check   # exit 1 if it would change
"""
from __future__ import annotations

import datetime
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
TESTS_DIR = ROOT / "tests"
START = "<!-- proof:start -->"
END = "<!-- proof:end -->"
_DEF = re.compile(r"^\s*(async\s+)?def test_", re.M)


def count_tests() -> tuple[int, int]:
    files = sorted(TESTS_DIR.rglob("test_*.py"))
    funcs = 0
    for f in files:
        try:
            funcs += len(_DEF.findall(f.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            pass
    return len(files), funcs


def render(n_files: int, n_funcs: int, date: str) -> str:
    return f"""{START}
The engine runs on its own infrastructure and patches itself in public. The volatile facts below are *linked to live state* rather than copied here, so this section can't go stale:

- **It ships its own fixes.** The patch loop turns filed capability gaps into machine-authored PRs through a cross-family writer/checker gate — see [`.github/workflows/auto-fix-bug.yml`](.github/workflows/auto-fix-bug.yml) and [`workflow/bug_investigation.py`](workflow/bug_investigation.py). Recent self-patches: the [commit and Actions history](https://github.com/Jonnyton/Workflow/actions).
- **Canary-gated deploys, live receipts.** The current deploy SHA, canary status, queue throughput, and the provider list are returned live by the `get_status` MCP tool and rendered at [tinyassets.io/fine-print](https://tinyassets.io/fine-print) — read the numbers there rather than trusting a copy here.
- **{n_funcs:,} tests across {n_files:,} files, all offline.** Providers are mocked (`_FORCE_MOCK=True`); no API keys: `pip install -e .[dev] && pytest -q`.

Honest caveat (the site says this too): the *user-facing* outcome loop hasn't shipped a real external artifact yet — draft mode is on, OAuth is unwired, `run_count` is 0. What's proven today is the engine, the architecture, and the self-patching loop; the first shipped real-world outcome is the next milestone.

<sub>Repo facts refreshed {date} by `scripts/gen_discoverability.py` (bounded — rewrites only between the markers).</sub>
{END}"""


def main() -> None:
    text = README.read_text(encoding="utf-8")
    n_files, n_funcs = count_tests()
    block = render(n_files, n_funcs, datetime.date.today().isoformat())
    if START in text and END in text:
        new = re.sub(re.escape(START) + r".*?" + re.escape(END), block, text, count=1, flags=re.S)
    else:
        new = re.sub(r"## Proof of life\n.*?(?=\n## )", "## Proof of life\n\n" + block + "\n", text, count=1, flags=re.S)
    if "--check" in sys.argv:
        sys.exit(0 if new == text else 1)
    README.write_text(new, encoding="utf-8")
    print(f"proof-of-life refreshed: {n_funcs} tests / {n_files} files")


if __name__ == "__main__":
    main()
