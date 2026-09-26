# The served `write_graph` never tells the agent what `name` and `description` are for

**Filed:** 2026-09-26 (lead's finding on PR #4000 round 2; sharpened here)
**Verified:** 2026-09-26, local Windows, FastMCP 3.2.0, repo venv — repro below
**Severity:** P2 — two parameters of the served build handle arrive with no guidance,
on main, on every FastMCP version

## What the lead found

On FastMCP 3.4 (what CI and production resolve — 3.4.7) the `name / description:`
entry in `write_graph`'s `Args:` block never reaches the agent. Present on main, not
caused by the handbook split.

## What the repro shows, which is worse

The docstring documents **7 of the 9 parameters**. `name` and `description` have no
`Args:` entry at all, on any version:

```
python -c "import re,inspect; from tinyassets import engine_mcp_server as s; \
 doc=s.write_graph.__doc__; args=doc.partition('Args:')[2]; \
 print(re.findall(r'^\s{4,}([a-z_]+):', args, re.M)); \
 print(list(inspect.signature(getattr(s.write_graph,'fn',s.write_graph)).parameters))"
```

```
['target', 'operation', 'payload_json', 'branch_id', 'automation_id',
 'expected_revision', 'idempotency_key']
['target', 'operation', 'name', 'description', 'payload_json',
 'idempotency_key', 'branch_id', 'automation_id', 'expected_revision']
```

So this is not a 3.4 extraction bug. There is nothing to extract for those two. The
version only changes how it LOOKS: on 3.2 the agent reads an `Args:` block that
silently omits them; on 3.4, where each parameter's prose becomes its schema
`description`, `name` and `description` arrive with none.

## Why it matters

`write_graph target="branch" operation="create"` is how a universe builds its own
workflows, and `name` is how the branch is labelled. An agent with no guidance for a
parameter either omits it (a branch named by default) or guesses — and this repo's
own history says an undocumented capability is a capability that does not exist
("A capability the agent is not told about is one that does not exist — which is how
the last six gates happened", `tests/test_request_fields_are_answerable.py`).

## Not fixed here, deliberately

PR #4000 relocated existing guidance byte-for-byte and its preservation test pins
that nothing was lost. Writing NEW `Args:` prose for two parameters is an addition,
not a relocation — it would break that pin and hide an unreviewed content change
inside a latency PR. It wants its own small change:

- add `name:` and `description:` entries to the engine `write_graph` `Args:` block,
  saying what each labels and when it is required;
- assert every signature parameter has an entry, so the next added parameter cannot
  ship undocumented (the check is four lines — the repro above is most of it);
- check the PUBLIC connector's `write_graph` for the same gap, since it is an
  independent docstring (16,623 chars vs the engine's).
