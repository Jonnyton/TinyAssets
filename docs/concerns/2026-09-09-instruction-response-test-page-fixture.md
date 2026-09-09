# Runtime instruction-response test misses its seeded page

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

Next: independent review of the fixture/current read contract and Linux CI
comparison. Preserve the advertised-handle and truncation assertions. This finding
does not close any app gap or excuse a new candidate failure.
