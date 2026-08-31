# Design — the platform is four primitives; everything else is a library

## How this document got here

Three founder corrections in one session, each rejecting a thing I had presented
as necessary:

1. *"why cant the user just build .py's"* — the graph DSL is a second,
   hand-written description of what the code was going to do. Four production
   gates in one day, all of them defects in that description.
2. *"its up to the user if they want to interupt the long run, or they should
   be able to spin up additional workspaces"* — I had claimed one workspace,
   fixed before launch, was inherent to bwrap. It is not: a *given* jail's
   mounts are fixed, which says nothing about how many jails a run may have.
3. *"the graph that runs the workspaces is just another user buildable things"*
   — and the orchestration I then proposed to hard-code (jail per workspace,
   warm pools, lifecycle, concurrency) is itself a library.

Each time I mistook an inherited choice for a constraint. The pattern is worth
stating because it is the thing this document exists to stop.

## The floor test

> Something belongs to the platform **only if it is enforced against the user's
> code** — if the user must not be able to opt out.

Everything a user could opt out of is a library, and a library is remixable
from the commons, so users improve it instead of maintainers patching it.

### The four primitives

1. **Isolated execution.** `exec_isolated(argv, fs)` — run this, with this
   filesystem, no network, no `/data`, no credentials, bounded memory. The
   user cannot opt out of the boundary; that is the point of it.
2. **Authenticated call.** `call(connection, request)` — perform this using a
   credential the caller never sees. Custody is the platform's because
   exposing it is the failure being prevented.
3. **Durable state.** Somewhere the user's own data persists and is theirs.
4. **Identity and arbitration.** Who owns this, and one tenant not starving
   another. Enforced against everyone, so nobody's library can waive it.

That is the whole platform.

### What stops being platform

| Today | Actually |
|---|---|
| workspace (checkout / create / push / discard) | a **library**: isolated exec + a git clone over an authenticated call |
| the graph runtime — nodes, edges, entry points, effects | a **library** |
| jail-per-workspace, warm pools, workspace lifecycle | a **library** |
| retry, resume, crash recovery | a **library** |
| branch naming, "never the default branch" | the user's code |
| `MAX_RPC_CALLS`, `MAX_WORKSPACE_COMMANDS`, glob and read caps | gone — they bound DSL node shape, which stops existing |
| `MAX_WORKSPACE_TIMEOUT_SECONDS` | gone — see below |

## What this deletes, concretely

Every one of the four gates lived in the layer this removes:

* **#2737** the served builder dropping the `workspace` keyword — no builder.
* **#2742** the effect-sink allowlist refusing `workspace` — no sink names.
* **#2742** consent reachable under two spellings — consent is checked at the
  call, against what is being done, not against a declaration.
* **#2748** docs teaching a packet without `"sink"` — no packets.

The DSL's safety story was that a node *declares* its effects and the platform
checks consent against the declaration — a promise about future behaviour,
checked before the code runs. Gate 4 was exactly a node whose declaration and
behaviour disagreed. Checking at the call is strictly more accurate, and the
isolation boundary is unchanged.

## Run length and interruption

`MAX_WORKSPACE_TIMEOUT_SECONDS = 1800` is defended in the code as multi-tenant
safety: a workspace holds the host-wide slot for its whole run. True — and the
slot is itself a hard-coded policy, so a concurrency decision manufactures a
ceiling that contradicts *a turn runs until finished, not wall-clock*.

**Interrupting a long run is the user's call.** The platform's obligation is
primitive 4: one tenant's long run must not starve another. That is per-tenant
arbitration, not a clock. Fix the slot; do not inherit the ceiling.

## What a user's file looks like

```python
def main():
    ws = workspace.checkout(connection="http_7931…", repo="o/n", ref="main")
    if ws.run(["python", "-m", "compileall", "-q", "."])["returncode"] != 0:
        return {"status": "compile failed"}
    ws.write("README.md", ws.read("README.md").rstrip() + "\n")
    ws.push(branch="whatever-the-user-wants")
    return http.request("POST", "/repos/o/n/pulls", json={...})
```

`workspace` and `http` are **imported library code**, not platform verbs. A
user who wants two workspaces makes two. A user who wants a retry writes a
loop. A user who wants a different pooling strategy forks the library and the
commons gets a better one.

The entry point is `run_script(source)`. Nothing else.

## Open questions

1. **Where libraries live, and how a script imports one.** This is now the
   load-bearing question, and it is a commons question, not a runtime one:
   naming, versioning, remixing, trust in a shared library. Deliberately not
   answered here.
2. **Warm jails.** Performance only, and now a *library* concern. Measure
   before optimising.
3. **Per-tenant arbitration** has to actually exist before the host-wide slot
   is removed, or primitive 4 is unenforced. This is the one item that must be
   built rather than deleted.
4. **Migration.** `write_graph` keeps working until the script path is proven
   live; nothing is removed first. Deprecating the DSL stays a founder call.

## How this gets proven

Not by tests — all four gates passed a full suite.

The founder's universe writes one `.py` that checks out the repo, runs a real
compile check, edits `README.md`, pushes and opens a PR, uncoached, through the
live connector, and the gate count is zero. Any gate it hits is the same class
of evidence this document is built on and belongs in it.
