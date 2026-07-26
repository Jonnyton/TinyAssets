# First-contact birth moves from `get_status` to `converse` (2026-07-22)

**Status:** approved (host directive, 2026-07-22) — supersedes the 2026-07-15
auto-birth-on-`get_status` decision.

## Decision

A connected authenticated founder still **always** ends up with a home universe,
and still **never** has to know an incantation to get one. What changes is which
handle does the provisioning.

- **`get_status` becomes a pure read again** (`readOnlyHint=True`). The
  `allow_first_contact_birth` parameter is deleted outright, so no caller can
  reach birth through it.
- **`converse` with no `graph_id` resolves-or-creates the founder's home**, via
  `tinyassets/api/first_contact.py::ensure_founder_home`.
- **The connector instruction changes** from "call `get_status` FIRST" to "relay
  through `converse` FIRST".

## Why this reverses 2026-07-15

The 2026-07-15 directive was right about the failure it was fixing: a founder who
did not know the magic words never got a universe. That rationale is untouched
here. The founder's opening message still births their home; it simply births it
through the handle that the opening message was always going to hit.

What 2026-07-15 could not have known is that making the connector's opening call
mutate would collide with the connector's own shipped tool description. Observed
live on 2026-07-21, prod, with a fresh identity: the server instruction says
"Call `get_status` FIRST on each conversation's opening message", and the
assistant refused, verbatim:

> one of the 'read' calls (get_status) actually has a side effect ... an
> authenticated user with no existing 'home universe' gets one auto-created the
> first time it's called. That's not a passive lookup, so I didn't run it without
> checking with you first.

Two artifacts we ship contradicted each other, and the model sided with the tool
description over the instruction — correctly, from its point of view. With
`get_status` refused, it then did the thing the instructions explicitly forbid
(described the tools from their schemas) and told the user *"I can't tell you
with confidence what real-world service this maps to."*

So the 2026-07-15 shape did not merely annotate a side effect; it made the
opening call *refusable*, and a refused opening call is a worse onboarding
failure than the one it was written to prevent. Rewording the instruction was
considered and rejected: it would have papered over a read that mutates rather
than fixing it.

## What is preserved

- **No magic words.** The whole point of 2026-07-15. The founder's first message
  is a `converse` relay, and that births the home.
- **The relay contract, verbatim.** `converse` remains the universe speaking in
  first person with the chatbot relaying — *"you are the connector, not the
  universe."* This is **not** a reintroduction of chatbot embodiment, and the
  2026-07-02 relay reshape is untouched.
- **Scope gate before reservation.** A founder lacking create scope still gets
  the awaiting card and leaves no `founder_home` binding behind.
- **Single-birth under concurrency.** Atomic reservation plus serialized
  materialization; racing first-contact workers never double-create.
- **`read_graph target=status` stays pure**, as it already was.

## Risk accepted

A client that calls `get_status` but never `converse` leaves its founder with no
home universe. Under 2026-07-15 that client would have provisioned one.

This is the live risk of the new shape and it is accepted knowingly: the
connector instruction now points first contact at `converse`, and every real
first contact observed to date is a conversational turn rather than a bare status
poll. If a client is ever seen polling status without conversing, the fix is to
provision on that client's actual entry point — not to make a read mutate again.

## Provenance

The implementation landed as `519fb2ea` (PR #1552) and deployed to production the
same day, **before** this approval existed — a process failure worth recording
rather than tidying away. A cross-family review on the predecessor PR (#1551) had
already returned `reject`, on exactly the right grounds: the change reversed an
approved host directive, and that is not a dev-discretion call. The merge went
ahead because the branch was republished from a stranded clone without first
checking whether a PR already carried a verdict on the same work. Code was
verified; provenance was not.

The host approved the new shape on 2026-07-22 after the fact. That resolves the
`reject` — it was only ever a question of authority, and the authority has now
answered — but the ordering was wrong, and "verify the code, then verify whether
someone already judged this work" is the durable lesson.

## Affected surfaces

- Code: `tinyassets/api/first_contact.py` (new), `tinyassets/api/status.py`,
  `tinyassets/api/prompts.py`, `tinyassets/universe_server.py`, and the
  `packaging/claude-plugin/` mirror of each.
- Tests: `tests/test_first_contact.py`, `tests/test_get_status_primitive.py`,
  `tests/test_persona.py`, `tests/test_relay_ux_prompts.py`.
- Specs: `openspec/specs/identity-auth-and-access-control/spec.md`,
  `openspec/specs/live-mcp-connector-surface/spec.md`.
- Superseded: `docs/design-notes/2026-07-15-auto-birth-home-universe.md`.
