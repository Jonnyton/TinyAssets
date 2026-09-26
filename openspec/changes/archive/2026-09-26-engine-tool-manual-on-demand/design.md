## Context

Measured 2026-09-25 (`tests/test_converse_turn_cost.py`, real converse path,
synthetic wire). A served founder turn is an agentic loop: round-trips are
`1 + tool_steps + 1`, and every one re-sends the entire system prompt plus the
entire engine tool block.

| engine handle | definition bytes | description chars |
|---|---|---|
| `write_graph` | 40,719 | **38,513** |
| `read_graph` | 7,172 | 6,274 |
| `run_graph` | 4,143 | 3,608 |
| `connect_compute` | 3,595 | 3,074 |
| `source_channel` | 1,788 | 1,432 |
| `write_brain` | 1,407 | 952 |
| the other 8 | 4,559 | 2,515 |
| **total** | **63,383** | **56,328** |

`inspect.cleandoc` saves 0 bytes (already dedented) and the engine surface
attaches no per-parameter descriptions, so there is no duplication to strip: the
only lever is relocation. Production confirms the loop shape — on the free
universe (2026-09-26 UTC) two recall turns ran 3 rounds each with
`tools=[read_brain]`, one no-tool turn ran 2.

Constraint from the founder and the lead: the canonical public connector handles
must keep working for chatbot clients, behaviour identical, one path for all
accounts.

## Goals / Non-Goals

**Goals:**
- Cut the per-round guidance preamble roughly in half without losing a byte of
  guidance or restricting anything the agent may do.
- Keep "the agent can reach this guidance" a single executable fact.
- Leave the public connector surface provably untouched.

**Non-Goals:**
- Trimming, summarising or rewriting guidance. Every moved byte moves verbatim.
- Changing the public connector's descriptions, the canonical handle set, or any
  canary expectation.
- Reducing the number of tool steps a turn may take, or capping anything.
- Touching `extract_learning`'s round-trip (its own change; deferring it needs a
  provider lease that outlives the request — see
  `docs/concerns/2026-09-25-converse-turn-round-trip-cost.md`).

## Decisions

### D1 — Reachable, not resident; via a read-only `handbook` target on the engine `read_graph`

Engine `read_graph target="handbook"` returns the chapter index;
`query="<handle>.<chapter>"` returns that chapter verbatim.

*Why this over the alternatives:*
- **A new handle** (`read_manual`) would add a primitive to a surface whose whole
  problem is size, and every new handle's own schema joins the per-round block.
  `check_primitive_exists action` shows no collision for `handbook`, but a target
  on the existing read handle costs ~80 bytes instead of ~400.
- **`write_graph operation="manual"`** puts a read on the write verb axis. A
  read-only operation on a handle whose refusals are all about effects invites
  exactly the confusion the surface spends bytes preventing.
- **A file in the universe folder** (the `SKILL.md` analogue literally) needs the
  bwrap folder tools, which exist only on the container, and would write a
  platform copy of the manual into every universe — storage shape, and a second
  definition of one fact. The handbook keeps one definition, in source, greppable.
- **A FastMCP tool transformation** serving a short description to the agent
  would make the manual reachable from nowhere.

### D2 — The split line: resident is what prevents a WRONG FIRST CALL

A chapter may move if a turn can tell from the resident text that it needs the
chapter *before* it composes a call. Guidance stays resident when not having it
produces a call that is wrong rather than a call that is absent.

Resident (9,607 chars): purpose; the `operation` catalogue; the FILE INPUTS exact
shape (it is resident today precisely because a live failure used the wrong
manifest key, and the refusal arrives only after the attempt); the delivery,
owned-custody, webhook and recurring-work one-liners; the no-effect parity note;
`Args:`; and the chapter index.

Moved verbatim (28,906 chars): `connections` (16,507 — credential asks, labelled
fields, look-it-up-first, path patterns, extend/remove, base64 writes,
`$ta.replace`), `code_nodes` (7,378), `workspaces` (5,021 — including the git
checkout pair).

Projected after: `write_graph` definition ~11,800 B, total block ~34,500 B — a
**46% cut** (~7.2k fewer tokens per round-trip). Measured for real in tasks 10-11.

### D3 — One accessor, `served_tool_guidance(handle)`, is the contract

12 assertion sites across 8 test modules currently read
`engine.write_graph.__doc__` and assert a specific piece of guidance is present.
They are the executable definition of what the agent must be told, and they must
not silently become weaker. Each site is re-pointed deliberately:

- a site whose guidance is **resident** keeps reading `__doc__` (it is asserting
  residence, and that is now a real property);
- a site whose guidance **moved** reads `served_tool_guidance(...)` (it is
  asserting reachability);
- and a new test asserts the two sets partition: every chapter is reachable, the
  index names every chapter, and no chapter text is also resident.

Reviewing all 12 rather than bulk-replacing is the point: a bulk replace would
turn "the agent is told X up front" into "X exists somewhere" without anyone
deciding that was acceptable.

### D4 — The public surface is untouched, and that is measured, not asserted

`universe_server.write_graph.__doc__` is 16,623 chars; the engine's is 38,513.
They are independent docstrings on independent functions, so the engine split
cannot reach the public description. A test pins the public description's
independence so a future edit cannot quietly couple them.

## Risks / Trade-offs

- **The agent builds a graph without fetching the chapter and gets it wrong.** →
  The resident index names each chapter and when to fetch it, the FILE-INPUTS
  shape stays resident, and `write_graph`'s refusals already carry the specific
  rule. Worst case is one extra round-trip on a graph-building turn — against
  ~7.2k tokens saved on every round of every turn.
- **A moved chapter becomes unreachable (silently losing guidance).** → The
  partition test fails if the index, the chapters and the retrieval disagree.
- **The 12 re-pointed assertions get weaker without anyone noticing.** → D3 makes
  each one an explicit resident-or-reachable decision, and the partition test
  fails if a chapter is claimed resident.
- **A future handle re-grows the block.** → the ratchet in
  `tests/test_converse_turn_cost.py`, lowered to the new measured size.
- **The relocation corrupts the text** (quoting, braces, backslashes in a 623-line
  block full of JSON examples). → byte-equality is asserted: the chapters
  concatenated back in order must equal the pre-change docstring exactly, pinned
  against a digest recorded in the test.

## Migration Plan

Pure in-process text relocation: no storage, no migration, no deploy
precondition. Rollback is the revert. The engine MCP route is private and
localhost-only, so no public canary state changes; the canary still runs because
the repo requires it for any surface-adjacent change.

## Open Questions

- Should `read_graph`, `run_graph` and `connect_compute` (6,274 / 3,608 / 3,074)
  get the same treatment? Deliberately out of scope: prove the pattern on the one
  handle that is 61% of the cost, measure the live effect, then decide. They are
  each an order of magnitude smaller.
