# Runtime instruction-response test misses its seeded page

**Filed:** 2026-09-09. **Verified:** 2026-09-09, Windows and Linux CI baseline.

Verified September 9, 2026 UTC, local Windows/Python 3.14. Both the pinned
unchanged five-gap baseline c2ed4534 and the candidate fail
`tests/test_mcp_instruction_surfaces.py::test_runtime_response_payloads_claim_only_live_advertised_handles`
at line 440: the real read_page returns `Page not found: notes/long-response-probe`
instead of the expected truncated-page response. No production outage is inferred
from this isolated synthetic fixture; do not weaken the assertion or call it a
regression introduced by the workflow-control changes.

Baseline checkout (detached, created for this comparison, no implementation edits):
`C:/Users/Jonathan/AppData/Local/Temp/tinyassets-workflow-gaps-base-20260909`.
Command: `python -m pytest -q tests/test_mcp_instruction_surfaces.py::test_runtime_response_payloads_claim_only_live_advertised_handles --tb=short`.
The same failure also occurs in the full focused baseline run (486 passes,
6 Windows skips, this one failure), recorded in
`output/workflow-gaps-pinned-windows-base.xml` in the primary worktree.
Candidate `--showlocals` identifies the not-found envelope. The test creates a
root wiki via TINYASSETS_WIKI_PATH while read_page supports explicit universe
selection; verify the actual fixture/resolver mismatch before changing anything.

Independent Claude review on September 9 UTC confirmed the fixture-only cause:
api/wiki.py::_resolve_page (lines 218-234 at 41df8819) requires a slash-containing
selector to be under pages/ or drafts/ and end in .md. The documented form is
pages/<category>/<slug>.md or a unique slug. The minimal correction is to use
`page="pages/notes/long-response-probe.md"` at test line 438, preserving every
assertion. This test is already in .github/known-failing-tests.txt (line 59);
its removal must accompany a proven fix so the ledger does not become stale.
Linux main run 34314054165's heavy JUnit also reports the identical single failure
in the selected three heavy files, with 123 other selected tests passing.

Next: land that fixture/ledger correction with its own appropriate verification.
Do not mix it into the already reviewed workflow-control runtime revision merely
to make local output look green. This finding does not close any app gap or
excuse a new candidate failure. The current runtime PR does not change the test
or add quarantine entries.
