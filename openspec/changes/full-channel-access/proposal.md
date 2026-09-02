# Full channel access

**Founder, 2026-09-02, in the app thread**, after their universe raised a
second GitHub ask minutes after they had approved "full jonnyton/tinyassets
repo patching": *"it shouldn't have needed to ask that, the other request was
already for full repo access"* and *"a more agnostic term it should have
asked for should have been full channel access."*

## The problem

A connection (a "channel": one deposited key under one destination label)
is granted as a list of exact endpoints, a list of git scopes per repository,
and a list of workspace consents per repository. Each is least-privilege by
construction, which means the agent raises an ask per widening, and the
owner answers the same question in three shapes: reach these paths, clone
this repo, push to this repo. The live thread shows the cost: three asks in
one afternoon for one key the founder had already decided to trust fully.

The platform's only invariant is not affecting OTHER users. Inside their own
universe the owner decides how much of their own key their own universe may
use; the platform's job is to say exactly what a yes means and to keep the
key out of the thread. An exact-path allow-list is a choice the owner may
make, not one the platform should force.

## What changes

1. **One ask shape: `access: "full"`.** On `connect_http` (a deposit) and
   `extend_http` (a widening), `"access": "full"` means: everything this key
   can do on this channel. The platform expands it, the owner reads the
   expansion on the tab, and answering is the yes.
2. **The expansion is the channel's, not the platform's guess.** For a
   channel with declared hosts: every declared host, any path, every verb.
   For a channel whose git transport host differs from its API host (GitHub
   today, via the forge table), the git host is covered through git scopes,
   never through an HTTP endpoint on that host. Git scopes and workspace
   consents are satisfied for any repository the key itself can reach on
   the channel's git host, for checkout, push and provision. Nothing is
   stored as a wildcard: the connection carries one `access_mode`, and the
   four enforcement readers consult it (design D2, D3).
3. **The rail sentence says all of it.** "Full access to your github key:
   anything the key itself can do at api.github.com, and git clone or push to
   any repository it can reach on github.com, including running that
   repository's code in your universe's sandbox. You do not need to paste
   it again."
4. **A later widening on a full channel is `already_held`.** The agent is
   told it holds the channel and never asks again for reach on it.
5. **Full is the default the agent is taught.** The served guidance says:
   ask for full channel access unless the owner asked for less; exact
   endpoints remain available for an owner who prefers them.

## What does not change

- The egress layer still pins hosts (SSRF), verbs to the five it knows, and
  the OS sandbox around code. "Full" widens the owner's authority over their
  own key; it does not widen what the platform does on anyone else's.
- Consent for workspace operations stays typed (checkout / push /
  provision); "full" grants all three, an exact ask still grants one.
- Revocation: removing the key removes everything. Today it does not:
  `remove_http` deletes the ledger row and leaves the workspace consents
  active under a connection id that is deterministic per destination, so a
  re-deposit inherits them. This change fixes that (design D6).

## Scope

Authority change (grants, git scopes, workspace consents), so this proposal
and `design.md` precede code and get a Codex refutation round. One PR.
