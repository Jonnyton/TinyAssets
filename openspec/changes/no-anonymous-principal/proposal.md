# No anonymous principal

**Founder directive, 2026-09-02:** *"anonymous should not be a possibility
anywhere in the codebase."* Reaffirming 2026-08-22: *"there is no such thing
as anonymous users. every user should have a universe and an auth and nothing
should happen on the platform unless its got that attached to the action."*

## Why now

The founder's assistant reported that its connector had "gone anonymous" and
that `get_status` still served a full universe status read with
`bearer_present: false` and a `v1:anonymous:` fingerprint. That is the
designed behaviour of the production auth mode (WorkOS resolve-always: reads
open, writes gated), and it is the thing the founder has now ruled out twice.

The inventory (2026-09-02, `origin/main`): 237 mentions of `anonymous` in 57
modules under `tinyassets/`. 75 construct or default to an anonymous actor,
81 gate on one, 81 are comments. One line makes the principal
(`auth/middleware.py:444`, `identity = ANONYMOUS` before the token is
inspected); four fallbacks would each re-create it on their own (the
ContextVar default, `current_identity()`'s `or ANONYMOUS`, the ASGI
middleware's seed, the dev provider). Every other site is downstream of those.

## What changes

1. **There is no anonymous identity.** The `ANONYMOUS` sentinel is deleted.
   An unresolved request has identity `None`, and `current_identity()` raises
   `PermissionError("Authentication required")` rather than returning a
   stand-in. Every `actor == "anonymous"` gate becomes unreachable and is
   deleted, not kept.
2. **A missing bearer on the MCP endpoint is a 401 challenge, in every mode.**
   `initialize`, `tools/list` and every `tools/call` included. MCP clients
   start OAuth on that 401; that is the flow the founder connector already
   relies on for writes. OAuth discovery routes, the app's own login and
   session routes, the connect-deposit routes and inbound hook routes keep
   their own authentication and are not "anonymous": each binds a named
   principal (the signed-in user, the hook's owner) before any handler runs.
3. **No environment-variable actor.** `UNIVERSE_SERVER_USER` never becomes an
   author or actor. The `author: str = "anonymous"` dataclass defaults and the
   SQL `DEFAULT 'anonymous'` go; an author is required at every write.
4. **Dev mode names its principal.** `DevAuthProvider` resolves a *named*
   local operator identity (`UNIVERSE_SERVER_DEV_USER`, no default) and
   refuses to start without it. Tests inject identities; none run "as
   nobody".
5. **Operational probes are named service principals.** The canary, the
   deployed-sha gate and the other scripts in `scripts/` authenticate with the
   existing canary bearer (`TINYASSETS_WIKI_CANARY_TOKEN`, generalized to a
   `canary` service identity with read capability). The healthy signal for an
   unauthenticated `initialize` becomes the 401 challenge itself.
6. **The public website reads a pulse, not a universe.** The three browser
   clients that call `tools/call` with `credentials: omit` move to
   `GET /pulse`: release sha, deploy time, uptime. No principal, because no
   universe state and no action. That route is the only unauthenticated read
   the daemon serves, and it is not an MCP call.

## What does not change

- Per-universe visibility and ACL (public / private / collaborator) stay as
  they are for *authenticated* callers. "Public" now means visible to any
  signed-in user, which is what the founder's remix model needs.
- First-contact provisioning stays on `converse` for an authenticated founder.
- The wiki canary's own token and route.

## Scope and staging

Authority change, so this proposal and `design.md` precede code and get a
Codex refutation round. Three PRs, each green on its own:

1. **Sources.** Delete the sentinel and the five fallbacks; 401 on missing
   token; named dev principal; named probes; `/pulse`; the spec deltas below.
   Tests that asserted an anonymous read flip to the 401 or the refusal.
2. **Sinks.** Delete the 81 now-unreachable gates and the 75 defaults, with
   the authoring paths made to require an author.
3. **Spec sync and archive.**

## Risks

- **Every MCP client must complete OAuth before `tools/list`.** Claude.ai and
  ChatGPT do; a client that cannot will see a 401 with a `WWW-Authenticate`
  challenge and a resource-metadata URL, which is the MCP standard.
- **Probes need the token in every workflow that runs them** (14 workflows).
  A probe without it fails loudly at `initialize`, which is the honest signal.
- **Hard Rules 11 and 14** keep their commands; the commands gain a bearer.
