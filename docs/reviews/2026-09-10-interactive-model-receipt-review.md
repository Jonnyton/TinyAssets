# Interactive answering-model receipt — independent shape review

September10,2026 UTC. Review12667 completed APPROVE231s and inspected the
in-flight internal response observer/collector. Public input/decorator unchanged;
server optional execution-envelope integration followed this approved shape.
No activation of model selection or picker, and no whole-feature exact-head
approval. UI source-name mapping and CLI structured-model evidence remain open.
The private conditional forwarding nit is harmless and retained for existing
injected bridges; it is not new authority. Final tests in receipt-proof.

## Verbatim result

VERDICT: APPROVE. The proposed shape is the smallest safe, backwards-compatible way to carry the actual answering provider and model to the app, and the in-flight working-tree diff already matches it.

**AGREE, source truth.** The successful envelope is reduced to text at `tinyassets/providers/call.py:322` after being stored only in the module global at `call.py:55`. That global is rewritten by every call, including the learning extraction at `tinyassets/universe_intelligence.py:624`, and is already consumed elsewhere at `tinyassets/ingestion/extractors.py:315`. Reading it after `converse` returns would misattribute the reply. The observer fires inside the router call on the winning response, which is the same object the router returns at `tinyassets/providers/router.py:1248`.

**AGREE, isolation.** The observer is threaded through `call_provider`, `_call_writer` and `converse` only. It is not passed to `extract_learning`, and the collector in `tinyassets/providers/execution_receipt.py` keeps the first successful response, so learning cannot overwrite it. The collector is a per-request local with no ContextVar or shared slot. The router's worker thread returns before the observer runs on the caller's thread.

**AGREE, no retry on observer failure.** The observer call in `_once` is wrapped in its own try/except before `return result.text`, so it never reaches the `except Exception` in `call_provider` that would raise on the governed path, and `_call_writer` retries only on exhaustion.

**AGREE, evidence split.** HTTP sets `reported_model` from the same validated field as `model` at `tinyassets/providers/api_key_http_provider.py:266`, using the printable, bounded validator at `tinyassets/providers/protocol_encoders.py:45`. The CLI adapters hardcode `model="claude"` at `tinyassets/providers/claude_provider.py:747` and `model or "provider-default"` at `tinyassets/providers/codex_provider.py:1054`. Those are requested or family labels, so a separate empty-default field is required rather than reusing `model`.

**AGREE, compatibility.** `ProviderResponse` is a frozen slots dataclass and the new field is appended last with a default, so positional construction stays valid. The public input signature and decorator are untouched. The structured adapter parses the JSON dict with no output schema at `tinyassets/universe_server.py:226`, and both app paths check `typeof payload.reply === "string"` first at `tinyassets/onboarding/app.html:1918` and `app.html:2167`, so an extra `execution` key is ignored. Conditional forwarding keeps the positional test fakes at `tests/test_universe_intelligence.py:678` and following working, and every `converse` fake in `tests/test_converse_handle.py` accepts `**_kw`.

**AGREE, smallest connection.** A field on `UniverseContext` would leak the observer into learning extraction. Changing the return type breaks the string contract. Reading the global is the bug. Routing through authority settlement is a new engine. The optional kwarg plus first-write collector is the minimum.

**DISAGREE_CONCERN, non-blocking:**
- The HTTP provider label is the internal source id at `api_key_http_provider.py:120`, not a display name. The later UI must map it, not render it as the picker's name.
- The Claude CLI stream does emit a structured init `model` event the adapter currently ignores. Treating it as unknown now is honest, but the proposal should not read as a permanent CLI exclusion.
- `call_provider` builds a conditional dict for a private function that already declares the parameter. Only the two seams that test fakes touch need the conditional forwarding.

Landing remains gated on server-envelope integration, omission of `execution` on every held or error path, and the collector tests passing.
