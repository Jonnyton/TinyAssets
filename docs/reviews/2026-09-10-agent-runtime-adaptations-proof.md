# Interactive runtime adaptations: local proof, not activation

September10,2026,05:19UTC. Feature codex/select-agent-models, changes after
a56893124bf4398d3ea72789f08c3042dd58e125. Shape review ADAPT294s captured in
2026-09-10-interactive-agent-runtime-shape-review.md; implementation review of the
actual integrated runner remains required before landing. No provider/tool/network
dispatch occurred in these tests, apart from local test HTTP fixtures.

## Implemented

- Detached immutable captured tool inventories and portable completed history.
  Same source/model retains supported reasoning; switching drops foreign reasoning
  while preserving exact arguments, known results and repeated per-batch wire IDs.
- Current owner/home/tombstone guard shared with preference storage, checked under
  the journal's BEGIN IMMEDIATE for every mutation. Preference exception import
  compatibility preserved. Former-home deletion test now models actual historical
  rebinding instead of creating new work for an already-former home.
- Explicit failed-inference retry only with no reply/tools, immutable older failed
  rounds, one concurrent retry winner, and no held-tool replay. Abandon closes only
  zero-round unused roots and makes those safe for scoped reset.
- OpenRouter bounded-body validation accepts exact supported tool-request/history
  shapes while retaining complete max_price and require_parameters; no plugin,
  transport override, extra model or incomplete result batch admitted. Legacy
  codec registration unchanged. The old test asserting ALL tools are rejected was
  updated to assert missing price bounds are still refused; successful zero-price
  tool shape and malformed history have dedicated tests.

## Reproducible verification

Windows PowerShell, feature working tree, Python pytest command:

```text
python -m pytest -q tests/test_agent_chat_portable_history.py tests/test_agent_price_guard.py tests/test_agent_chat_codec.py tests/test_agent_turn_journal.py tests/test_account_deletion.py tests/test_onboarding_model_preferences.py tests/test_model_price_applicability.py tests/test_selected_model_authority.py tests/test_mirror_parity_gate.py --tb=short -rs
```

373passed,0skips,24.75s (session63624), one existing dependency deprecation warning.
Ruff check for changed canonical modules/tests and git diff --check pass.
python packaging/claude-plugin/build_plugin.py generated412mirrors and import probe
passed. Mirrors are included in the above focused tests.

Actual Linux oracle, WSL Ubuntu native Docker, identical WORKING TREE snapshot:

```text
python3 scripts/linux_oracle.py -- -q tests/test_agent_chat_portable_history.py tests/test_agent_price_guard.py tests/test_agent_chat_codec.py tests/test_agent_turn_journal.py tests/test_account_deletion.py tests/test_onboarding_model_preferences.py tests/test_model_price_applicability.py tests/test_selected_model_authority.py tests/test_mirror_parity_gate.py --tb=short -rs
```

373passed,0skips,22.02s (session22171), one dependency deprecation warning.
Image tinyassets-linux-oracle:ce0e83fb15a8; Python3.11.16/git2.47.3/bwrap0.12.0.
Windows worktree gitdir resolved explicitly through GIT_DIR TinyAssets6 and
GIT_WORK_TREE select-agent-models; no production connection or workflow mutation.

These nine files do NOT include scoped-reset's three previously baselined Linux
failures. This green group does not resolve that separate fixture concern.

## Still required

Real claiming-thread runner and writer integration; per-inference observer after
capability consumption; first-resolution finite plan sealing; full input/output
accounting; typed HTTP agent request/reply; tools-capable fresh model admission;
candidate/default/fallback consumption and clickable app UI. No full-agent hold
was removed in router or HTTP adapter. No new deployment or live readiness claim.
