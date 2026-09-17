# Native answer-model observation: pre-build review

Date: September 17, 2026. Base: 0a8e00355deddee31158210297535619feabfb65.
Reviewer: Claude, `peer_agent.py claude --model fable`, read-only, exit 0 after 253s.
Scope: one native answer-model telemetry patch under `select-agent-models`.

## Independent verdict (verbatim)

I'll read the cited provider, receipt, and test sources, then give a structured verdict on the observation seam.

Reading is done. Writing the verdict now.

**Review scope:** approach and single-user safety of the proposed root-answer observation seam in the Claude stream reader. No code edits, no dispatches, no test runs.

**AGREE**

- **Root identification is sound.** The last root assistant frame's `message.model` is by construction the model that produced that message, and the exact-text match against the terminal result ties the label to the returned answer rather than to an earlier root turn, a child agent, or an init frame. Every mismatch path collapses to unknown, never to a borrowed label.
- **Excluding init, message_start, modelUsage and children is correct.** Init reports the requested alias, message_start is stream framing, modelUsage is an aggregate over all calls, and child frames carry a non-null parent. None of them is answer-owned.
- **Request-local state is safe.** All reader state lives in closures inside `_read_stream` (claude_provider.py:591-606). The receipt collector keeps the first response per reply and drops degraded or failed ones (execution_receipt.py:51-57). No consumer of `reported_model` routes, grants, or selects anything. Concurrent calls cannot cross-contaminate.
- **Codex stays unknown.** The JSONL protocol carries no resolved model (codex_provider.py:1057-1059). Leaving it unknown without scraping config or stderr is the right call. Record it as a remaining visibility gap, not a gate.

**DISAGREE_EVIDENCE**

- **The label must be identity-valid, not just bounded.** The coordinator passes the label straight into the journal at agent_turn_coordinator.py:245, and `records.identity` at agent_turn_records.py:59-71 raises on any value where `value != value.strip()`. The proposal rejects empty, overlong and nonprintable labels but does not say it strips. A model label with a stray outer space would fail the turn record, losing the user's answer over optional telemetry. Reuse the existing `model_receipt` in protocol_encoders.py:59-63, which already strips after the bound and printable checks. Add the synthetic-placeholder rejection on top. Do not write a second validator.
- **A new event kind changes watchdog accounting.** Every event returned from `_normalize_stream_obj` sets `progressed = True` (claude_provider.py:696-697). An assistant frame with valid metadata but empty content currently yields no events and is not liveness. Emitting an evidence event for it would make it liveness, contradicting the claim that watchdog behaviour is preserved. Either exclude the evidence kind from `progressed`, or attach model and parent fields to the existing text_delta payload for non-partial assistant frames.

**DISAGREE_CONCERN**

- **No in-repo evidence that the installed CLI emits `parent_tool_use_id`.** The key appears nowhere in the repo, and every fixture in test_provider_stream_and_classify.py omits it. The SDK parser uses `.get`, so it tolerates absence; the proposal requires explicit null. Strict is the safer direction, but if the CLI omits the key the feature is dead and indistinguishable from a real absence. Capture one real `stream-json --verbose` trace before landing and shape fixtures from it. That test file's own docstring at line 97 names payloads shaped to the implementation as the prior lesson.
- **Real stream-json splits one API message into one assistant frame per content block.** A final message of thinking then text works because the text frame is last. A final message with two text blocks would fail the match and read unknown. Fail-safe, but cheap to fix: accumulate text across frames sharing `message.id` instead of per frame. Optional.
- **Non-stream JSON could be closed later.** When the result's modelUsage has exactly one key, every call including the answer used that model. That is answer-owned by construction. Out of scope for this patch, note it as a follow-up.

**Remaining visibility limitation, recorded explicitly:** Codex answers and non-stream Claude JSON answers stay "Model not reported" after this patch. Capability 3 is not closed by it.

**Tests to add beyond the proposed list:** whitespace-padded label round-trips through the coordinator record; empty-content assistant frame does not reset the idle watchdog; same-message-id split frames match the terminal text.

VERDICT: ADAPT

Checked. The one running dispatch is this review's own output file, written by the dispatcher when this session exits. The vanished entries belong to other sessions. The task's hard constraints forbid dispatching, re-dispatching, and implementing, so there is nothing further for this lane to advance. The verdict above stands: ADAPT.



## Author disposition before release

- Reuse `protocol_encoders.model_receipt` (bounded, printable, stripped); reject the CLI synthetic placeholder.
- New internal evidence event explicitly skips watchdog/progress accounting. Empty-content watchdog regression included.
- Real installed CLI 2.1.261 capture on Windows, September 17: `claude --safe-mode --strict-mcp-config --tools "" --no-session-persistence -p --output-format stream-json --verbose --include-partial-messages "Reply only: hello"`. Subscription-only environment, exit 0. Sanitized assistant: explicit `parent_tool_use_id:null`, nonempty `message.id`, `message.model:claude-opus-5`, text `hello`; success result text `hello`. No secrets, session IDs, tool payloads or raw trace retained. Model is an observation, not a pinned release.
- Accumulate split blocks only for the same nonempty root message ID, and taint conflicting/missing model labels.
- Codex and terminal-only JSON remain unknown; full model-visibility capability is NOT closed by this patch. Aggregate usage inference is deferred because it is not an explicit answer identity.

## Release acceptance and rollback

Local verification on Windows, September 17, 2026: `python -m pytest -q tests/test_provider_stream_and_classify.py tests/test_native_model_execution.py tests/test_writer_execution_receipt.py tests/test_peer_agent.py tests/test_agent_native_journal.py tests/test_app_model_picker.py tests/test_app_model_choice.py tests/test_conversation_execution_history.py` -> 342 passed, 1 skipped (Linux-only bwrap), 2 pre-existing LangGraph deprecation warnings. New positive-observation tests were first red against the unmodified adapter (4 failures). Ruff and plugin build/import passed. A real subscription CLI response through the modified `_read_stream`, using the same safe/no-tools flags above, returned text `hello`, requested `claude`, reported `claude-opus-5`. This is supporting adapter proof, not production app acceptance.

Run stream/native-selection/receipt/journal/app/history regressions; rebuild plugin mirror; exact-head cross-family approval; required CI. Deploy then verify protected SHA and public canary. In the original owner's rendered app, temporarily choose Claude, send an ordinary greeting, verify reported model and reload persistence, then restore Automatic without changing saved defaults. Check fresh user-originated clean use separately.

No schema, authority, routing or preference change. Rollback by reverting this patch's runtime/mirror change and deploying the revert if optional telemetry breaks replies or assigns an incorrect model. Existing history receipts remain valid. Production/live proof is pending; this document is not a ship claim.
