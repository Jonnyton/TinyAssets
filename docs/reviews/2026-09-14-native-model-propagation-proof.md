# Native explicit model propagation — local proof, September14 2026

Environment: feature branch codex/select-agent-models, working tree based on
f8299c49. No deployment, real provider inference, or private workflow changes.
Shape gate: owner-authorized Fable5.1 review completed576s, ADAPT; full artifact
model-selector-shape-fable.md and remaining-model-execution.md dispositions.
The final release review is still reserved for the finished candidate.

## Implemented

- Accepted explicit native IDs reach request-local configuration and Codex `-m`
  or Claude `--model` (both streaming/plain structured paths), without a fallback
  flag or a compiled release list. Empty authorized default omits the flag and
  ignores the process-global Codex model override; caller injection is cleared.
- Current serving and workflow authority remain separate. Native facts are not
  HTTP pricing/wire facts. Workflow selections persist strict version1 native
  evidence inside the existing sealed selection record and settle once.
- Provider default, requested ID and reported answering ID remain distinct.
  Unknown Codex model telemetry stays empty; requested IDs do not attest output.
- Picker rows include accepted declared IDs, label availability unverified, and
  distinguish provider-default behavior from a verified complete catalogue.
- Four existing chat-only/tool-loop guards pinned with five negative tests.
  They have not been relaxed; workflow HTTP tools are still unfinished.

## Verification

Initial four new cases failed on unmodified runtime: chat/workflow selection
refused and ModelConfig had no native selection input. After implementation:

Windows Python3.14, September14 around06:20–06:22UTC:

`python -m pytest -q tests/test_native_model_execution.py tests/test_native_model_authority.py tests/test_run_provider_session.py tests/test_providers.py tests/test_provider_served_router.py tests/test_served_model_preferences.py tests/test_model_options_api.py tests/test_interactive_http_agent.py tests/test_work_model_selection.py tests/test_provider_invocation_selection.py tests/test_model_options.py tests/test_app_model_picker.py tests/test_app_model_choice.py tests/test_agent_workflow_fences.py --tb=short --show-capture=no --disable-warnings -rs`

**367 passed,3 skipped,76.82s.** Two skips are real POSIX shared-reader/bubblewrap
checks, which the Linux run executes. Third requires a real configured Codex
test universe/snapshot; no live-account proof is claimed.

Same14-file command under actual Linux oracle, September14 around06:22UTC:
Python3.11.16, git2.47.3, bubblewrap0.12.0, `python3 scripts/linux_oracle.py --`
followed by the same pytest arguments. **369 passed,1 skipped,51.89s.** The sole
skip is that same real-account integration. Original added catalogue-order test
incorrectly expected declaration insertion order; corrected to ModelAccess's
existing canonical sorted membership. No runtime change was needed for it.

Supporting Windows policy/catalogue/strict-record group:114 passed (separate
overlapping group, do not sum with the above). Focused Ruff and strict OpenSpec
validation pass. Plugin runtime rebuilt and import probe passes. Canonical mark
generator refreshed only app.html's checksum in generated-assets.json; no icons
or other site assets differ. Brand parity test passes. Synthetic DOM verifies
the new basis labels; this is not rendered live browser acceptance.

## Still open

Fresh account-native enumeration (Codex metadata adapter and Claude CLI seam),
workflow-owned HTTP multi-round tools/budget/lineage/cancellation, full exact-head
release review/CI, installer timeout, deployment and ordinary app proof. No full
task checkbox or all-available-model success claim is justified by this slice.

Official metadata docs checked September14: [Codex model/list](https://learn.chatgpt.com/docs/app-server#list-models-modellist)
and [Claude initialize/models](https://code.claude.com/docs/en/agent-sdk/typescript#sdkcontrolinitializeresponse).
They support further adapter work, not access to this owner's live account.
