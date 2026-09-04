# Wolf Moon favicon/parity review resolution

Date: 2026-09-03  
Environment: Windows worktree, Python 3.11+, Node 20-compatible site toolchain

The evidence-bearing cross-family review in
`2026-09-03-wolf-moon-favicon-parity-review-round2.md` approved the canonical
export, cache versioning, receipt integrity, desktop/mobile/store coverage, and
retired-Svelte scope. It returned one `DISAGREE_EVIDENCE`: it could not establish
an unconditional pull-request gate for brand parity.

That finding was adopted. `scripts/invariants/brand_parity.py` now registers as
`pre_commit_scope = True` in `scripts/invariants_run.py`. The existing
`.github/workflows/invariants.yml` runs `python scripts/invariants_run.py
--pre-commit` on every pull request with no path filter. This is independent of
the site workflow and the required pytest lane.

Verification after adaptation:

- `python scripts/invariants_run.py --pre-commit` — all seven invariants green;
  brand parity checked 52 generated artifacts.
- `python -m pytest -q tests/test_brand_parity.py tests/test_invariants_framework.py`
  — 17 passed.
- `python -m ruff check WebSite/brand/render_marks.py
  mobile/scripts/render_app_icons.py scripts/invariants/brand_parity.py
  scripts/invariants_run.py tests/test_brand_parity.py
  tests/test_invariants_framework.py` — clean.

The third and final peer-review process did not satisfy its contract: it made a
commit despite a read-only instruction and returned a progress message rather
than `AGREE`/`DISAGREE_EVIDENCE` plus a verdict. Its output is not counted as
approval. Per the three-round cap, no fourth review was dispatched. The round-2
finding is resolved by the executable evidence above; no other findings remain.
