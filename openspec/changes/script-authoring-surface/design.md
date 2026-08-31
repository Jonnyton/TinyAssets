# Design — your universe is your computer; the floor is other people

## The floor, in the founder's words

> "the floor is a user custom do what ever they want as we can make it. the
> floor is they cant effect other users except what ever ways we build for
> users to interact. but within your own universe you are god as if you have
> your own computer in the cloud with an openclaw ageint on it that has full
> access, but also has commons libraries of graphs"

So there is exactly **one** invariant:

> **You cannot affect another user except through an interaction surface we
> deliberately built.**

Inside your own universe you are god. It is your computer in the cloud, with an
agent on it that has full access, plus commons libraries you can pull in.

An earlier draft of this document proposed four primitives. That was wrong in a
specific way worth recording: **half of it was protecting the user from
themselves.** Isolated execution "with no network, no credentials" is not a
tenant boundary — it is a leash on the owner. The correct test is narrower and
much more permissive.

## The test

> Does this stop me affecting **another user**, or the host everyone shares?

Yes → platform, and the user must not be able to opt out.
No → it is the user's, whatever it is protecting them from.

## Re-running every constraint against it

### Platform — genuinely cross-tenant, keep

| Constraint | Why it survives |
|---|---|
| Another universe's data, credentials and compute are unreachable | the invariant itself |
| `RLIMIT_AS` + aggregate-RSS watchdog | host memory is shared; nothing else bounds a process tree's sum |
| Resource share / per-tenant quota | one tenant starving another is the failure |
| Identity — you cannot act as someone else | the invariant, on the identity axis |
| The commons is an interaction surface, so it needs a trust model | the only sanctioned user-to-user path |

### Not platform — the user's, and currently taken from them

| Constraint | What it actually protects against |
|---|---|
| `ALLOWED_IMPORTS` allowlist | your code, from you |
| `FORBIDDEN_PATTERNS` denylist | same, and it is string matching — `'sub' + 'process'` walks past it |
| `MAX_RPC_CALLS = 32` | how many times your workflow may call out |
| `MAX_WORKSPACE_COMMANDS = 64` | your loop length |
| `MAX_WORKSPACE_READ_BYTES`, `MAX_WORKSPACE_GLOB_RESULTS` | your file sizes, your file counts |
| `MAX_WORKSPACE_TIMEOUT_SECONDS = 1800` | see the chain below |
| Branch naming, "never the default branch" | your git workflow |
| Retry / resume / recovery policy | your workflow's error handling |
| No network in the jail | **contested — see below** |
| Credential blindness inside your own universe | your own credential, from your own agent |

### The `ws.__globals__` finding inverts

`docs/concerns/2026-08-31-ws-globals-defeats-the-import-allowlist.md` was filed
today as P1: node code reaches `subprocess` and `os` through
`ws.read.__func__.__globals__`, defeating the import allowlist.

Measured then, and it still holds: the jail contains it — no network, no
`/data`, no credential mount, no cross-universe reach. So under this floor **it
is not a vulnerability**. It is your code, in your universe, reaching your own
tools.

The finding survives; the conclusion inverts. It is evidence that the allowlist
is **theatre** — a guard that cost real engineering, is trivially walked past
with string concatenation, and protects nobody but the author from themselves.
**Delete the allowlist and the denylist. Do not fix the leak.** That concern
file needs rewriting to say so.

### Network and credentials — the two that need care

Neither is settled by the floor alone, and neither is settled by the old
answer.

**Network.** "You are god in your own universe" says your code should have it.
The cross-tenant edge is real but narrow: shared egress IP reputation, and
abuse attributable to the platform. That is an *arbitration* problem — rate,
quota, attribution — not a reason the owner cannot make an outbound request.

**Credentials.** Blindness protects your credential from your own agent, which
the floor says is your call. But the commons complicates it: importing someone
else's library means running their code next to your credential, and the
commons *is* a sanctioned interaction surface, so harm through it is
cross-user. The answer is therefore not "expose credentials" or "hide them"
but **whose code is running** — first-party vs. imported — which lands in the
commons trust model, not here.

## The chain, now visibly a chain

`MAX_WORKSPACE_TIMEOUT_SECONDS = 1800` is defended as multi-tenant safety
because a workspace holds the host-wide slot for its whole run. True — and the
slot is itself a policy. So:

1. one host-wide slot creates contention,
2. which forces a 30-minute ceiling so one tenant cannot starve the rest,
3. which contradicts *a turn runs until finished, not wall-clock*.

Only step 2's *goal* is platform. Replace the slot with per-tenant quota and
steps 2 and 3 both disappear — **and interrupting a long run becomes the user's
call**, which is what the founder said it was.

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

`workspace` and `http` are **commons library code**, not platform verbs. Two
workspaces? Make two. A retry? Write a loop. A different pooling strategy? Fork
the library and the commons gets a better one. The graph runtime is a library
too — graphs do not disappear, they stop being the only way in and become
something users publish and remix.

Entry point: `run_script(source)`. Nothing else.

## Open questions

1. **The commons trust model** is now the load-bearing question — imported code
   running beside your credentials is the one genuinely cross-user path. Its
   own change.
2. **Per-tenant arbitration must exist before the host-wide slot is removed.**
   This is the one item that is a build, not a delete.
3. **Network egress attribution** — what the platform owes when a tenant's
   traffic is abusive.
4. **Migration.** `write_graph` keeps working until the script path is proven
   live. Deprecating it stays a founder call.

## How this gets proven

Not by tests — all four gates passed a full suite.

The founder's universe writes one `.py` that checks out the repo, runs a real
compile check, edits `README.md`, pushes and opens a PR, uncoached, through the
live connector, and the gate count is zero.
