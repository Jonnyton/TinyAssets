# Design: splitting the catalogue's two readers

## The shape question this answers

One read serves two callers with opposite needs. The owner's picker needs every
choice they own; a model needs a payload that fits beside a conversation and
several other tool calls. The design question is **who decides which one arrives**.

Three candidates, and why two are wrong:

**Guess from the caller.** Serve complete to the first-party app, bounded to
anything else. Rejected: the platform would be deriving a behavioural switch from
a transport fact, and the single most important case defeats it — a model driving
the founder's own signed-in session (the `ui-test` route, which AGENTS.md makes
the final chatbot-surface proof) is indistinguishable from the app. It would also
mean the bounded path is the one path never exercised by the proof route.

**Overload an existing parameter.** `query="compact"` needs no new surface, but
`query` already means "filter by text". A field with two meanings is two
definitions of one fact, and the second one wins silently the first time a user's
model is genuinely called `compact`.

**A separate target, chosen by the caller.** `model_options_summary`. Additive:
no parameter changes, no change to `model_options`, nothing for the picker to
adopt. Both reads are explicit and independently specifiable, which is what makes
the exemption in (3) auditable — one named target is exempt from the
`structured_content` ceiling, and that is a fact a test can assert.

## Why the ceiling and the projection are both needed

They fail differently and neither substitutes for the other.

The **ceiling** is a backstop with a uniform, honest failure mode: any read that
outgrows the budget comes back marked, and a read added next year is covered
without anyone remembering. But a truncated catalogue is a *bad answer* — the
agent gets an arbitrary prefix and cannot tell whether the model it wants is in
the part that was cut.

The **projection** is the good answer: per-source counts and the head of the
platform's own ordering, so the agent sees that there are 347 models while
looking at 8, and can page or filter to the rest. But it only covers the reads
someone thought about.

Ship both. The engine surface already does (PR #4037).

## Ordering is borrowed, never invented

The summary's "top N" is the head of `order_index` — the plan's own candidate
order — with models outside that order following rather than disappearing. This
projection ranks nothing. A model that is a legitimate choice but sits outside
the fallback order is still reachable by paging, and its absence from the head is
the plan's judgement, not the projection's.

## The cursor is a cursor

`output_offset` for this target is **not an index**: `0` means "no cursor yet",
which is the default summary view, so the flat listing's first row is cursor `1`.
Otherwise offset `0` would be ambiguous between "the default view" and "start at
row zero", and row zero would be unreachable. Callers copy back the `next_offset`
they were handed and never compute one — the same convention `read_graph` already
documents for `conversation` and `run_output`.

## The exemption list is the part to watch

**Corrected while building this.** The first draft said the ceiling covers every
`read_graph` and `get_status` reply with `model_options` as the single exemption,
and that the list should shrink to zero. Enumerating the actual consumers rather
than assuming them changed all three claims.

**Two exemptions, not one, and they are different in kind.**

- `run_file`'s contract is exact bytes. Measured on the real dispatch path: a
  256 KB chunk (a 349,681-byte reply) came back as a 24,576-byte marker carrying
  neither `bytes_base64` nor `next_offset`, so the caller could not even page to
  recover — a file its owner uploaded became unreadable to their own universe.
  This exemption is **permanent**: `file_max_bytes` already bounds the read, and a
  byte ceiling layered over it only breaks the first one.
- `model_options` is the picker's completeness requirement. This one **is**
  temporary, and (1) is what eventually retires it.

So "shrink to zero" was wrong. The right invariant: a target qualifies by being
unusable when partial, or by a stated completeness requirement — **never by being
large**, which is the condition the ceiling exists to handle. A third entry
justified by size is the smell, not a third entry as such.

**An allowlist of handles, not a denylist.** The ceiling covers `read_graph` and
nothing else, because every other handle registered on this surface carries
something a ceiling would destroy rather than bound:

- `converse` carries the universe's own reply to its founder. That reply is the
  product; clipping it is data loss the user reads.
- `read_page` / `write_page` carry content the user authored — Hard Rule 9.
- `get_status` is read by the owner's own app: `active_host` and
  `supervisor_liveness` at `tinyassets/onboarding/app.html:3800`, `:3864`, `:3867`
  drive the status dot. Bounding it breaks the client in exactly the way bounding
  `model_options` would break the picker.

`get_status` therefore needs the same split this change performs for the
catalogue — a complete client read beside a bounded model-facing one. That is a
separate capability and a separate change; it is **out of scope** here rather than
a third exemption, because calling it an exemption would imply the ceiling should
eventually reach it as written, and it should not.

The lesson worth keeping: both corrections came from enumerating consumers —
`grep` for what reads the field, and read the client — not from reasoning about
what a payload looks like. The first draft of this design was wrong in the same
way for `get_status` that PR #4037 was wrong for `run_file`.

## What stays out of scope

- **No per-turn context-window scaling.** The engine's ceiling can scale with the
  selected model's window, but the persistent per-universe HTTP engine server is
  started by a supervisor and outlives any one turn's model choice, so in
  production the input is absent. Host decision 2026-09-26: skip it, the fixed
  default is the fix. `TINYASSETS_ENGINE_RESULT_CEILING_BYTES` remains as the
  deploy-level escape hatch.
- **No change to the collector or the row.** `read_model_options` and
  `model_options_document()` are untouched, so the shared learned catalogue
  (#4028) composes with this rather than colliding: its rows flow through the
  projection unchanged, including `availability_basis:
  "platform_verified_elsewhere"` with `in_candidate_catalog: false`, which the
  compact row carries deliberately so the agent can tell a model it can use from
  one another universe proved works.
