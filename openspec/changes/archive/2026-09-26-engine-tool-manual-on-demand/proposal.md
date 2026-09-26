## Why

Every model round-trip of every served founder turn re-sends the whole engine
tool-definition block — **63,383 B** measured 2026-09-25 — and one handle's manual
is **38,513 chars** of it (61%). A served turn is an agentic loop, so a turn with
two tool steps pays that preamble three times. Production confirmed the cost is
real: on the free universe (2026-09-26 UTC, `/data/.tinyassets.db`) "remember my
favorite color" ran 3 rounds, "still remember my color" 3 rounds, and the founder
waited 1-2 minutes for each trivial reply.

The manual is genuine capability guidance, so it cannot be trimmed. But it is
needed only by a turn that is actually building a graph, and the repo already has
the pattern for exactly this: `universe_tools._HARNESS_HEAD` keeps a one-line
skill index resident and has the agent `read` the full `SKILL.md` on match. Make
the guidance **reachable** instead of **resident**.

## What Changes

- The engine surface gains a read-only handbook: engine
  `read_graph target="handbook"` returns the chapter index, and
  `query="<handle>.<chapter>"` returns one chapter verbatim. No effect, no
  writes, no new handle.
- `write_graph`'s long-form chapters move out of its advertised description into
  handbook chapters, byte-for-byte. Measured split: **9,607 chars stay resident**
  (purpose, the `operation` catalogue, the FILE INPUTS exact shape, delivery /
  custody / webhooks / recurring-work one-liners, the no-effect parity note,
  `Args:`), **28,906 chars move** into three chapters — `connections` (16,507),
  `code_nodes` (7,378), `workspaces` (5,021) — plus a resident chapter index that
  names each one and when to fetch it.
- One composition accessor, `served_tool_guidance(handle)`, returns description +
  every chapter, so "the agent can reach this guidance" stays one executable
  fact. The 12 existing assertion sites that read `write_graph.__doc__` across 8
  test modules move to it, except guidance that must stay **resident** by the
  rule in design.md.
- The per-round guidance ratchet in `tests/test_converse_turn_cost.py` drops from
  58,000 to the new measured size.
- **The public connector is not touched.** Measured: the public and engine
  surfaces do NOT share descriptions (`universe_server.write_graph.__doc__` is
  16,623 chars, the engine's is 38,513 — the engine's grew to 2.3x). Chatbot
  clients read the public surface, so leaving it alone makes "canonical handles
  keep working" true by construction rather than by test.
- One path for every account: no plan, tier, provider or universe branch.

## Capabilities

### New Capabilities
- `served-agent-tool-guidance`: what guidance the served engine surface keeps
  resident in every round's tool block versus reachable on demand, the handbook
  retrieval contract, and the per-round guidance budget.

### Modified Capabilities
- `live-mcp-connector-surface`: adds the requirement that the PUBLIC advertised
  descriptions are unchanged by engine-side guidance relocation — the two
  surfaces are independent, and the canary's canonical handle set is unaffected.

## Impact

- `tinyassets/engine_mcp_server.py` — the `write_graph` docstring split, the
  chapter constants, the `handbook` target on the engine `read_graph`, and
  `served_tool_guidance`.
- `tests/test_converse_turn_cost.py` — ratchet lowered to the measured size.
- 8 test modules with 12 sites reading `engine.write_graph.__doc__`:
  `test_http_connection_removal`, `test_removal_is_reachable_from_the_served_surface`,
  `test_request_fields_are_answerable`, `test_served_automation_lifecycle`,
  `test_served_docs_teach_a_parseable_packet`,
  `test_served_docs_teach_every_required_packet_field`,
  `test_served_webhook_triggers`, `test_served_workspace_build_surface`.
- Not touched: `tinyassets/universe_server.py` (the public connector), the
  canonical handle set, `scripts/mcp_public_canary.py` expectations.
- Cost of the trade: one extra round-trip on a turn that actually needs a chapter,
  against ~7.2k fewer tokens on EVERY round of EVERY turn.
