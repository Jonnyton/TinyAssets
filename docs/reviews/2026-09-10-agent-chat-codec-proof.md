# Private agent-chat codec proof

September10,2026,04:02UTC. Feature worktree codex/select-agent-models;
synthetic protocol fixtures, no production inference or tool dispatch.

Shape review at7e125b4a returned ADAPT after300s; full review is in
2026-09-10-agent-chat-codec-shape-review.md. Its eight cases and allowlisted
continuation were pinned in agent-chat-protocol.md before code. Added source_ref
alongside requested_model enforces the reviewed same-connection boundary even
when two connections advertise the same opaque model identifier.

New agent_chat_codec.py is a private pure module, mirrored into the plugin. It
is not registered in ENCODERS or connected to a provider. Frozen JSON-backed
records distinguish completed text, tool requests, refusal and incomplete stops;
tool batches validate completely and results correlate exactly in order. User
text and tool argument strings stay verbatim. Opaque reasoning is continuation
data, never UI or authority. Non-text MCP content is explicitly unsupported.
Malformed/incompatible data never becomes a partially executable batch.

Verification September10,04:01UTC:

```
python -m pytest -q tests/test_agent_chat_codec.py tests/test_protocol_encoders.py tests/test_api_key_http_provider.py tests/test_engine_tool_client.py tests/test_writer_execution_receipt.py tests/test_mirror_parity_gate.py --tb=short -rs
python -m ruff check tinyassets/providers/agent_chat_codec.py tests/test_agent_chat_codec.py
```

Windows Python:224passed,0skips,7.46s. Same six-file group through
scripts/linux_oracle.py in actual Ubuntu Docker (Python3.11.16,git2.47.3,
bwrap0.12.0):224passed,0skips,2.78s. Includes91 new codec cases; unchanged
legacy encoder/provider baseline is54passing cases. Ruff passes. Plugin was
rebuilt with packaging/claude-plugin/build_plugin.py; mirror parity is included.
Canonical brand generator refresh carries only the previously landed answering-
model app checksum; no brand appearance changes.

Implementation review is pending on the committed head. No claim of live HTTP
agent support: existing eligibility, selected-executor refusal and legacy price
guard remain unchanged. Durable tool intent/results, per-inference admission,
cost-constrained agent requests and actual authorized tool execution must be
integrated before a working HTTP selector can be enabled. No private workflow,
owner grant, credential, selection or background-self state changed.
