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
| **Credential blindness — the vault, always** | if a secret escapes, someone else's workflow reaches your accounts; this is what makes remix safe |
| The commons as a sanctioned user-to-user path | still an interaction surface — but the vault, scopes and cancellation bound it, so it needs no reputation gate |

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
| No network in the jail | nothing — resolved below: arbitrate (rate, quota, per-tenant egress), never prohibit |

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

### Credentials: the vault is absolute, and it is what makes the commons work

Founder, 2026-08-31:

> "credentials should never beable to exape a vault. so even if a user uses
> someone elses workflow credentials should not be stealable and the agent can
> always edit or cancel the workflow and an agent wouldnt use an uninspected
> workflow it didnt test and come to trust first"

An earlier draft of this document called credential blindness "the author's
call inside their own universe". **That was wrong**, and it is wrong on this
document's own test. If a credential can escape, then running someone else's
workflow lets *them* reach *your* accounts — a user-to-user effect. Credential
blindness therefore **passes** the floor test and is platform, non-optional,
first-party code included.

It is also the property that makes a commons possible at all. Remix is safe
**by construction**: no workflow, yours or anyone's, can read a secret. That is
a far stronger foundation than a reputation or review system, and it means the
commons does **not** need the heavy trust model this document previously
treated as load-bearing.

The existing design is already this and stays: the in-memory broker over a unix
socket, `git_environment` built from empty, `http.curloptResolve` address
pinning, bundles as the only object transfer, and no credential mount in the
jail. Do not relax any of it while deleting the guards that never mattered.

#### What the vault does NOT do — state it, because it changes what to build

**The vault stops theft, not use.** A workflow that cannot read your token can
still *call* the API with it while it runs, including calling somewhere you did
not intend. Secrecy bounds the permanent loss; it does not bound the live blast
radius.

Two things bound that, and they are the founder's own points 2 and 3:

* **Scope** — what the connection is allowed to do at all. This is why
  `git_read:owner/name` / `git_write:owner/name` being per-repository matters,
  and why scopes deserve more attention than secrecy now that secrecy is
  settled.
* **Revocation and control** — "the agent can always edit or cancel the
  workflow". Cancellation must therefore be real and immediate, not advisory,
  and it must be reachable while a run is in flight.

And trust is established the way the founder describes: *"an agent wouldnt use
an uninspected workflow it didnt test and come to trust first."* Inspection and
testing are the user's judgement, not a platform gate. The platform's job is to
make the worst case survivable, which the vault does.

### Network — resolved: arbitrate, never prohibit

Two corrections got this to a settled answer.

**There are no anonymous actors.** Founder, 2026-08-31: *"there are no
anoymous unsers. universes can only be created by users, and only universes can
do anything on the plateform."* An earlier draft of this section argued against
"raw anonymous sockets from the shared IP". That framing was wrong and
contradicts a rule already recorded in this project: every execution is
attached to a universe, and every universe to a user. Nothing here is
unattributable.

**So the problem is shared fate, not anonymity.** Every universe's traffic
leaves from one public IP. Services judge by IP, so one universe that gets the
address rate-limited or blocklisted degrades every other universe on the host.
Attribution identifies who did it; it does not un-blocklist anyone. That
collateral damage is a real user-to-user effect and is the only part of network
access the floor lets the platform touch.

**Therefore: arbitrate, never prohibit.** Because every action already has an
owner, the platform has what it needs — per-tenant egress rate and quota,
attribution (which already exists: `/data/.outbound-proxy/<connection>/audit.jsonl`),
and, when a use case demands it, **per-tenant egress identity**, which removes
shared fate outright. A prohibition on sockets is the wrong instrument; it
denies the owner a capability to solve a problem that arbitration solves.

**Why it is not urgent.** Outbound today goes through
`authenticated_external_call` on a connection the user holds, so reputation
attaches to the user's own provider account rather than to the droplet. Email —
the case where a blocklist does lasting damage — travels via the user's own
email provider. The shared-IP exposure is therefore small in the current shape.

**Scoping decision, not a safety one.** Slice 1 needs no raw sockets, because
everything it does is authenticated anyway. That is "not needed yet", **not**
"not allowed". When a use case arrives, build per-tenant egress; do not build a
proxy pool speculatively, and do not write a prohibition into the surface.

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

1. **Cancellation must be real.** "The agent can always edit or cancel the
   workflow" is now load-bearing: with the vault settled, revocation is what
   bounds a borrowed workflow's live blast radius. Verify that cancel actually
   stops a run mid-flight — including one inside `ws.run` — rather than being
   advisory. If it is advisory today, that is a P1 in the founder's terms and
   not in mine.
2. **Scopes deserve the attention secrecy no longer needs.** A borrowed
   workflow cannot read a token but can use it; the connection's scope is the
   ceiling on that. Per-repository git scopes already exist; audit whether
   every other connection type is as narrow.
3. **Per-tenant arbitration must exist before the host-wide slot is removed**,
   or the one remaining shared-resource invariant is unenforced. The only item
   here that is a build rather than a delete.
4. **Per-tenant egress identity** — build when a use case needs raw sockets;
   it removes shared-IP fate outright. Not speculative work.
5. **Where libraries live** — naming, versioning, import. Still its own change,
   but much lighter than feared: the vault means it is a distribution problem,
   not a safety one.
6. **Migration.** `write_graph` keeps working until the script path is proven
   live. Deprecating it stays a founder call.

## How this gets proven

Not by tests — all four gates passed a full suite.

The founder's universe writes one `.py` that checks out the repo, runs a real
compile check, edits `README.md`, pushes and opens a PR, uncoached, through the
live connector, and the gate count is zero.
