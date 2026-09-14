Both finished result files are prior-stage verdicts and neither changes this review. The shape review returned ADAPT with eight cases to pin before code; I verified each of those eight in the committed codec above. The engine tool client review returned APPROVE on the earlier slice. The "running" dispatch is this review itself, whose result the dispatcher writes from my stdout. Under my read-only, no-dispatch mandate there is no other lane I may advance, so the final answer stands as delivered.

**Reviewed:** `e6bc197b15fd387a763b8838183b16e21b72de27` on `codex/select-agent-models`, diff from `0797ef6f`. Eight files changed. No legacy module is in the diff, and nothing in `tinyassets/` imports the new codec. Working tree clean.

**Reproduced (2026-09-09, Windows, system Python, this worktree):**

```
python -m pytest -q tests/test_agent_chat_codec.py --tb=short -rs   -> 91 passed in 0.86s
python -m ruff check tinyassets/providers/agent_chat_codec.py tests/test_agent_chat_codec.py -> All checks passed
cmp canonical agent_chat_codec.py vs packaging/.../runtime/tinyassets/providers/agent_chat_codec.py -> identical
```

**Contract findings**

- **AGREE, complete-batch validation.** Every call passes exact key-set, id identity, function type, enabled-name regex, and strict JSON-object checks before any request is returned (`agent_chat_codec.py:121-143`). Decode returns a whole record or raises. `length` with calls raises. `tool_calls` finish with no calls raises.
- **AGREE, finish/refusal/unsupported content.** Refusal wins, empties `text` and `tool_requests`, and is absent from the continuation. `content_filter`, `length`, and unknown reasons never read as completed. Non-text assistant content raises. Non-empty `function_call` or `audio` holds even a text stop, as the protocol doc pins.
- **AGREE, opaque same-source continuation.** Fixed allowlist projection, type-checked reasoning replayed verbatim, dropped keys recorded, and the builder refuses any dropped key, any non-tool stop, or a `(source_ref, requested_model)` mismatch.
- **AGREE, exact result correlation.** Tuple required, length equality, positional id equality, cross-round uniqueness, error-flag consistency, and envelope re-validation on replay. Tests cover missing, extra, reversed, duplicate, orphan, flipped flag, and malformed JSON.
- **AGREE, immutability.** Frozen slotted records hold JSON strings, definitions and result projections are deep-copied through dump-then-parse, and tests mutate sources after decode and after `tool_outcome`.
- **AGREE, fixed diagnostics.** Every raise is a literal string with `from None`. Provider text fed into error bodies never surfaces.
- **AGREE, legacy guards.** No diff touches the encoders, price guard, HTTP provider, or tool client. The test pins the guard rejecting the agent body and the codec's absence from `ENCODERS`.

**Non-gating notes**

- **DISAGREE_CONCERN, `index` key.** Line 129 demands exactly `{id, type, function}`. Several compatible backends add `index` on non-streaming tool calls. Probe: raises "unsupported tool call shape". Fail-closed by design, but likely the first live blocker. Revisit with real fixtures.
- **DISAGREE_CONCERN, cross-round id reuse.** The `seen` set at lines 322 and 340 spans rounds, so models emitting per-turn ids like `call_0` cannot pass round two. Stricter than the wire contract. Revisit with real fixtures.
- **Note.** `content_filter` and `truncated` records keep `text`. Typed stop, so not a defect here, but the future terminal projection must not surface it.
- **Test-coverage note.** A forged `tool_requests` tuple with unchanged continuation, and a round naming a tool removed from the current `tools`, both raise per my probe but are not in the suite.
- **Cosmetic.** The duplicate-key and nonfinite messages are always replaced by "invalid JSON object".
- The manifest diff is only the onboarding app checksum. The tasks note is accurate.

**Required changes:** none.

VERDICT: APPROVE
