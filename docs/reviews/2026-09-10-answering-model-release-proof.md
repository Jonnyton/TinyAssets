# Answering-model observation release

September10,2026 UTC. Existing select-agent-models work, isolated onto
codex/show-answering-model over deployed3b541c116e7ca3a6bc029f9e453a13246c6ba216.
One intent: show request-owned answering provider/model evidence beside each new
reply. This is not a clickable picker, saved-policy activation, full HTTP agent,
CLI resolved-model telemetry, persisted history receipt or fallback engine.

Runtime/tests extracted from reviewed feature215aacf2 (request-local observer)
and6f0e6273 (reply-owned UI), excluding unrelated discovery/authority/preferences/
HTTP-client work. Observer shape APPROVE231s; UI shape ADAPT251s addressed before
build and exact feature implementation APPROVE284s. Final isolated head still
requires independent approval before ready/merge. No new tool input/decorator,
endpoint, persistent schema, authority, grant or workflow edits.

Fresh Windows baseline302 passed/0 skipped25.69s on3b541c11; actual Docker Linux
baseline302 passed/0 skipped17.84s. Final Windows352 passed/0 skipped31.92s;
Linux final352 passed/0 skipped24.05s. The50 additions cover writer receipts, both MCP result
channels, inference/learning separation and actual app JavaScript including
typed/spoken/queued replies, Unicode, malicious labels, unknown metadata and no
reuse of previous answers. Feature tests included two actual UI regressions red
before implementation; the isolated baseline does not claim those new tests ran.

Command: `python -m pytest -q tests/test_writer_execution_receipt.py
tests/test_universe_intelligence.py tests/test_api_key_http_provider.py
tests/test_converse_handle.py tests/test_providers.py
tests/test_universe_server_mcp_structured_results.py tests/test_onboarding_app.py
tests/test_realtime_voice.py tests/test_mirror_parity_gate.py --tb=short -rs`.
Baseline omits the then-absent writer_execution_receipt file. Linux uses the same
group through the reviewed scripts/linux_oracle.py harness against this worktree,
Python3.11.16/Git2.47.3/bubblewrap0.12.0; WindowsPython3.14. All traffic synthetic.
397 runtime mirrors/import, focused Ruff and diff checks pass. Existing FastMCP
asyncio deprecation warnings remain, no skipped-platform claim.

No deployment or live receipt-display proof yet. After gated rollout require
authenticated deployed SHA/public canary, refresh the owned visible app tab,
send exactly "Retest your workflow checklist", and inspect the rendered answer
and its own footer. CLI model may correctly remain not reported; do not infer
it from the answer's prose. No permission request approvals or workflow edits.
Existing owner conversation is not anonymous/first-contact/cross-client proof.
Look for organic post-fix use separately; none observed before deployment.

Rollback: normal reviewed revert/redeploy of this isolated release if answers
are lost, mismatched or falsely attributed. Reverify protected SHA/canary and
rendered conversation. No stored preference, credential, grant or user data
migration to undo. History reload currently loses these new transient footers;
that limitation is explicitly outside this observation-only release.

## Isolated review and packaging correction,03:30UTC

Claude exact84053a845bfd3b2194da7ae2c27b83a15119232c APPROVE249s independently
reproduced143 receipt/app tests. Final self-contained verdict is preserved in
output/answering-model-release-result.md. Nongating: this is an extracted slice
of existing select-agent-models planning, not a second proposal directory;
failure_class responses intentionally do not supply successful receipts; commit
hook's cp1252 decoding failure must be recorded, not called clean. The last
point is resolved by explicitly scanning the exact29,528-character committed
Python diff through the same check_diff using UTF-8: no forbidden imports.
The underlying checker repair already exists in primary92ad462d and is a separate
unlanded fix; this release does not bypass or alter that gate.

Draft PR3734 initially failed brand-parity and the same brand test in preview
contracts because the generated receipt hashes the whole app HTML. Ran canonical
`python WebSite/brand/render_marks.py`; only generated-assets.json changed, one
app checksum, no other asset/runtime/test bytes. All six pre-commit-scoped
invariants now pass including52 matching brand artifacts. After locked `npm ci`,
`npm test` at WebSite/site-react passes233 tests with4 existing Windows skips
(237 total); earlier missing-yaml run is superseded, not a source regression.
CI Linux had236 passes and only the stale app hash failure before this correction.
No website route/style/brand geometry edits or separate public-site deployment.
Generated manifest/proof-only head correction requires fresh exact-head review.
