Review of the proposed pure agent-chat codec boundary. I read the three proposal docs and every cited source at this checkout (`7e125b4a`): `protocol_encoders.py`, `discovery_protocols.py`, `api_key_http_provider.py`, `engine_tool_client.py`, `ModelConfig`/`ProviderResponse` in `providers/base.py`, `SelectedModel`, `Interaction`/`_ineligibility`, and the installed `mcp` 1.28.0 / `fastmcp` 3.2.0 types. No edits, no dispatch, no network.

## Evidenced source facts (what the slice must not touch, confirmed)

- **Legacy codecs are text-only.** `encode_openai_chat` builds only system+user messages (`protocol_encoders.py:59-81`); `decode_openai_chat` reads `choices[0].message.content` and raises on blank, ignoring `finish_reason` and `tool_calls` entirely (`protocol_encoders.py:84-112`).
- **Price guard blocks any agent body today.** `_openrouter_constrained_body` rejects any top-level key outside `{model, messages, temperature, max_tokens}` and any message whose key set is not exactly `{role, content}` with string content (`discovery_protocols.py:53-66`). A body with `tools`, an assistant message carrying `tool_calls`, or a `tool`-role message cannot pass. This is the correct held state.
- **Executor refusal is explicit.** `api_key_http_provider.py:234-237` raises when a selected HTTP model has `engine_mcp_enabled`. `complete()` returns only `ProviderResponse`.
- **Eligibility is held at the selector too.** The OpenRouter discovery protocol declares `Interaction(needs_tools=False)` (`discovery_protocols.py:98`); `_ineligibility` refuses tool interactions unless `connection.executor_tools` and `model.tools is True` (`model_policy.py:192-195`); the HTTP snapshot hardcodes `executor_tools=False` (`discovery_snapshot.py:180`). Three independent holds; the codec slice changes none.
- **The tool client returns raw MCP results.** `EngineToolSession.call` returns `CallToolResult` from `call_tool_mcp`, refuses names outside the discovered subset, and marks post-invoke failures `unknown` (`engine_tool_client.py:159-173`). `session.tools` yields deep copies of `mcp.types.Tool`. Installed `CallToolResult` = `content: list[ContentBlock]`, `structuredContent: dict|None`, `isError: bool`, plus `_meta` and `extra="allow"`.
- **`ProviderResponse` already has `tool_phase` and `side_effect_state`** (`base.py:280-285`), and `WriterExecutionReceipt.observe` accepts only `ProviderResponse`.

## Findings

**AGREE** on the core shape: a private, pure, credential-free codec for the existing `openai_chat` wire; a detached immutable reply record separating "terminal text" from "awaiting tool execution"; whole-batch validation before returning any request; exact 1:1 ordered result correlation with refusal on missing/duplicate/orphan results; opaque reasoning snapshot replayed only to the same source; MCP `content`/`structuredContent`/`isError` carried as tool-result content, never promoted to system/user; no retry, no dispatch, no model selection in the codec. This matches the OpenRouter/OpenAI tool-calling contract as I know it and as the author cited.

**DISAGREE_EVIDENCE � do not extend `ProviderResponse` or `ENCODERS`.** `ProviderResponse.text` is a required `str` and every consumer treats it as terminal (`base.py:258-291`; `api_key_http_provider.py:310-319`). Registering the agent codec in `ENCODERS` would also change `ApiKeyHttpProvider.__init__` acceptance (`api_key_http_provider.py:114-118`). Correction: new private module, not registered anywhere; `ProviderResponse` is reused only as the *terminal* projection, where `side_effect_state` and `tool_phase` get set from the journal so the existing receipt path works unchanged.

**DISAGREE_CONCERN � the proposal leaves eight cases implicit that must be pinned as explicit unsupported/handled before code**, or the codec will "fake universal compatibility" by accident:

1. **Exactly one choice.** Legacy takes `choices[0]`. For a tool batch, a second choice is an ambiguous batch. Refuse `len(choices) != 1`.
2. **Per-choice errors.** OpenRouter can return `choices[0].error` and `finish_reason: "error"` with a 200 body. Legacy checks only top-level `error` (`protocol_encoders.py:92`). Refuse both.
3. **Refusal field name.** OpenAI's `message.refusal` (string|null) is the refusal signal. Non-empty ? stop reason `refusal`, held in its own field, never in `text`.
4. **Stop/finish semantics.** Presence of a non-empty `tool_calls` array governs "awaiting tools"; `finish_reason` corroborates. `length` with tool calls ? refuse the batch (truncated). `length` with text ? `truncated`, not `completed`. `content_filter` ? its own stop. Unknown finish reason ? `unknown`, fail-closed, never `completed`. Some upstreams return `stop` alongside tool calls, so do not require `finish_reason == "tool_calls"`.
5. **Empty-string arguments.** Some models send `""` for no-argument tools. `""` is not JSON. Proposal must decide; I recommend refuse in this slice (coercing to `{}` manufactures an argument set for a tool with defaults), and revisit with live fixtures.
6. **Tool call `id`.** Some upstreams behind OpenRouter omit or blank ids. Refuse; never synthesize an id, since a synthesized id breaks exact journal correlation and may confuse the provider on replay.
7. **Non-text MCP content blocks.** `ContentBlock` includes image/audio/resource. Serializing base64 into a tool message is "intact" but unbounded. Refuse with a fixed diagnostic; the served engine tools return text/JSON so this costs nothing live. Also exclude `_meta` and `extra="allow"` fields from the tool-message projection; serialize exactly `{content, structuredContent, isError}`.
8. **Continuation projection.** Replaying the raw assistant message verbatim may carry `refusal: null`, `function_call: null`, `annotations: []`, `audio`. A strict compatible endpoint with `require_parameters` can 400. Project a fixed allowlist: `role`, `content`, `tool_calls` (id/type/function.name/function.arguments as verbatim strings), `reasoning_details` verbatim, `reasoning` verbatim. Record names of dropped keys on the record; refuse continuation if any dropped key held a non-empty value. That honours "do not silently strip".

Also pin: never set `strict: true` on tool definitions (changes schema semantics), validate names against `^[A-Za-z0-9_-]{1,64}$`, bound description length, and reject arguments via `json.loads(..., object_pairs_hook=<dup-rejecting>, parse_constant=<raise>)` so NaN/Infinity and duplicate keys fail as the proposal intends (default `json.loads` accepts `NaN`).

**API facts I state from knowledge, not re-fetched** (author read the docs; confirm with a real fixture): tool message `content` must be a string on most compatible endpoints; `reasoning_details` is the field OpenRouter says to pass back unchanged; OpenRouter normalizes `finish_reason` and adds `native_finish_reason`; OpenRouter can return `usage.cost` when the request sets `usage: {include: true}`. That last one is a top-level field the guard currently rejects and is the cleanest future answer to the "missing cost is unknown" gap in the loop doc, but it belongs to the admission slice, not this one.

## Smallest records and signatures

New module `tinyassets/providers/agent_chat_codec.py`, importing only `reported_model`, `ProtocolDecodeError`, `OPENAI_CHAT_PATH` from the legacy file.

```python
StopReason = Literal["completed", "tool_requests", "truncated",
                     "content_filter", "refusal", "unknown"]

@dataclass(frozen=True, slots=True)
class ToolRequest:
    call_id: str          # verbatim provider id, 1..256 printable
    name: str             # exact member of the request's tool-name set
    arguments_json: str   # verbatim wire string, replayed as-is
    # parsed object is validated but NOT stored mutable; expose via
    # json.loads(arguments_json) at the caller, or a MappingProxyType

@dataclass(frozen=True, slots=True)
class AgentReply:
    stop: StopReason
    text: str | None              # None when content is null/blank on a tool round
    refusal: str | None
    tool_requests: tuple[ToolRequest, ...]
    continuation_json: str        # allowlisted assistant-message projection
    dropped_fields: tuple[str, ...]
    requested_model: str          # the model_id sent
    reported_model: str           # reported_model(body), "" = unknown
    raw_finish_reason: str
    input_tokens: int | None
    output_tokens: int | None

@dataclass(frozen=True, slots=True)
class ToolOutcome:
    call_id: str
    result_json: str   # canonical dump of exactly {content, structuredContent, isError}
    is_error: bool

@dataclass(frozen=True, slots=True)
class ToolRound:
    reply: AgentReply                    # stop must be "tool_requests"
    outcomes: tuple[ToolOutcome, ...]    # 1:1, same order as reply.tool_requests

def tool_definitions(tools: Sequence[mcp.types.Tool]) -> tuple[dict, ...]
def encode_openai_chat_agent(*, prompt: str, system: str, model: str,
        tools: Sequence[dict], rounds: Sequence[ToolRound],
        temperature: float | None = None, max_tokens: int | None = None,
        tool_choice: Literal["auto", "none", "required"] = "auto",
    ) -> tuple[str, dict]
def decode_openai_chat_agent(response_body: Any, *, requested_model: str,
        tool_names: frozenset[str]) -> AgentReply
def tool_outcome(request: ToolRequest, result: mcp.types.CallToolResult) -> ToolOutcome
```

Malformed structure and any bad tool batch raise `ProtocolDecodeError` with fixed, provider-text-free messages; semantic stops return a record. Every record is JSON-serializable so the future journal stores it verbatim. That is the answer to "no duplicate transcript store": the journal row *is* the tool-round transcript, and `conversation_store` stays best-effort text memory.

## Next review boundary (design only, not implemented)

- **Guard sibling, not a weakening.** `_openrouter_constrained_agent_body(body, caps)` with allowlist `{model, messages, temperature, max_tokens, tools, tool_choice, parallel_tool_calls}` and per-role message shape checks; still refuses `provider` overrides, `plugins`, `models`, `route`, `transforms`. The legacy guard stays byte-identical.
- **Eligibility.** A second `Interaction(needs_tools=True, ...)` on the discovery protocol, and `executor_tools` flipping to True only when the loop is proven. The refusal at `api_key_http_provider.py:234` is removed in that same slice, never before.
- **Provider entrypoint.** A separate method (for example `complete_agent_round`) taking a prepared body and returning `AgentReply`; `complete()` remains text-only.
- **Admission.** Each inference passes the guard and `SelectedModel.cost_upper_bound` separately; its docstring's "text-only" assumption still yields a valid bound because it uses the full context as input, provided tool results are text. One `ProviderInvocationCarrier` per inference, never reused (loop doc lines 63-64).
- **Journal.** Persist intent per `ToolRequest` before `EngineToolSession.call`, persist `ToolOutcome` after; `unknown` outcomes hold the turn. `_call_writer`'s no-whole-turn-retry rule stays until that exists.

## Tests (synthetic fixtures only)

1. Round trip: two tool calls plus `reasoning_details` ? decode ? outcomes ? encode; assistant projection equals allowlisted original, tool messages in order with exact ids, identical `tools` array on both requests.
2. Whole-batch refusal: third call has invalid JSON ? raises, no partial record.
3. One case each: duplicate id, empty/missing id, `type != function`, unknown name, NaN, duplicate keys, array arguments, `""` arguments.
4. Finish matrix: `tool_calls`, `stop`+calls, `length`+text, `length`+calls, `content_filter`, `error`, per-choice `error`, unknown string, two choices.
5. `refusal` non-empty ? stop `refusal`, `text` None, refusal never in continuation text.
6. Detachment: mutate the parsed body after decode ? record unchanged; frozen records reject assignment.
7. Correlation: missing, extra, reordered, duplicate outcomes ? builder raises; `requested_model` mismatch across rounds ? raises.
8. Builder never emits `provider`, `plugins`, `models`, `route`, headers; key set exactly the allowlist; prompt bytes verbatim including unicode and surrounding whitespace.
9. `tool_outcome`: text + `structuredContent` + `isError=True` preserved; `_meta` and extras excluded; image block ? raises.
10. Pin the hold: the agent body raises in `_openrouter_constrained_body`, and existing `protocol_encoders` tests pass unchanged.
11. `reasoning`/`reasoning_details` never appear in `text`; array order survives the JSON round trip.
12. Usage absent/malformed ? None; no cost field fabricated.

**VERDICT: ADAPT.** The boundary, purity, and safety posture are right and reuse the correct primitives (`mcp.types`, `EngineToolSession.tools`, `reported_model`, `ProviderResponse` as terminal projection only). Before code, the proposal must pin the eight explicit cases above as stated unsupported/handled behaviour and adopt the allowlisted continuation projection rather than verbatim message replay. No additional review round is warranted for those adaptations.
