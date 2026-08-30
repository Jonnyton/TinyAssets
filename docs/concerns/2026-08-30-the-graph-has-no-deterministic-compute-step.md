# The graph has no deterministic compute step, so every patch shape becomes a platform operator

**Filed:** 2026-08-30
**Verified:** 2026-08-30, live, on the founder's own universe (`u-01kxm1vszd8hwp7em418asq8h9`), across ~14 hours of one job: "change one line of README.md, open the PR, merge it".
**Severity:** P2 — nothing is broken, but each new *shape* of edit has cost a deploy, and the founder noticed: *"you're having to do a lot of things to make something very specific work when the user should just be able to do a lot of things."*

## What happened

To let a universe change one line of a file it had fetched, the platform grew,
one deploy at a time:

| Deploy | Operator / piece | The failure it answered |
|---|---|---|
| #2704 era | `$ta.base64`, `$ta.from_base64`, `$ta.ref`, `$ta.effect`, `$ta.concat` | the model could not carry file bytes through `run_graph` inputs (double-encoding, truncation); append needed the fetched body in place |
| #2709 | `body_hint` on a truncated evidence preview | the model re-typed a file it could only see 4 KiB of |
| #2716 | `$ta.replace {in, old, new, count}` | changing a line re-typed the file; PR #2714 stripped every blank line |
| #2717 | the refusal shows the input near the closest partial match | the model guessed at a newline where the file had a space, twice |

Every one of these is channel-agnostic in name. Every one is a reaction to one
failure. Together they are a small programming language being written one
operator per bug — and the next edit shape (insert after a heading, delete a
block, edit two files atomically) will need the next operator.

## Why it is structural

A branch node today is one of two things:

1. an **LLM step** — which is lossy for bytes (it re-types), and cannot see a
   fetched result anyway (evidence is a 4 KiB preview, visible only *after* the
   run);
2. a **declarative effect packet** — which can reference earlier results
   (`$ta.effect`) but cannot compute over them.

Nothing deterministic can run *between* a fetch and a write. That is the gap
the `$ta.*` vocabulary fills by hand.

The reason the model cannot simply run `git`/`gh` in its sandbox is deliberate
and right: the model process is **credential-blind** — tokens are applied in an
isolated worker and never reach the LLM. But credential-blindness only forbids
*credentials* in the model's reach, not *data*. A step that has the fetched
bytes and no credentials violates nothing.

The founder's mental model (2026-08-30): the user has an agent; the agent has a
graph and channels; GitHub is one channel through the channel-agnostic node the
user builds; any LLM source; any workflow. In that model "change one line" is
three lines of code in a node, not a platform operator.

## What would fix it

A **sandboxed code node**: no credentials, inputs = the node's declared state
keys plus earlier effects' `response.body`/`status` (the same view `$ta.effect`
has), output = values the next packet references. Fetch (credentialed worker)
→ code (bytes, no credentials) → write (credentialed worker). The `source_code`
attribute already exists in the node vocabulary (`branches.py`,
`engine_mcp_server.py`), and `mark_approved` — the approval that would let one
run — has zero callers (verified 2026-08-30: `grep -rn 'mark_approved('
tinyassets/` finds only the definition). The primitive the founder's model
assumes is present in the schema and dead in the code.

Second half: the model's *view* of results. `_EVIDENCE_BODY_PREVIEW_CHARS =
4096` means a 6.8 KB README is never fully visible to the agent that must
author an exact `old`. A code node removes the need to see it; until then the
preview cap is the other reason the operators keep growing.

This is a `PLAN.md`-level decision (execution primitive, sandbox = authority
surface): OpenSpec proposal + design before code, founder approval for the
principle.

## What not to do meanwhile

Do not add another `$ta.*` operator after #2717. If a live job needs one, that
is evidence for this file, not a reason to grow the vocabulary.

## How to resolve this file

Delete it when a universe can fetch → compute → write a one-file change with
no `$ta.*` operator in the packet, proven live and uncoached — or when the
founder decides the transform vocabulary *is* the intended compute model, in
which case that becomes a `PLAN.md` statement and this stops being a concern.
