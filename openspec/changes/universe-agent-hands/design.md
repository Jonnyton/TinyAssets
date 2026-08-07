# Design

## The decision that unblocks this

The current policy denies `mcp__*` with a wildcard because the CLI has no
"allow-only-X" mode and the logged-in account's connectors load regardless of
`--setting-sources` (verified 2026-07-03: the sandboxed turn saw
`mcp__codex__codex` → arbitrary code execution). The conclusion drawn at the
time — that giving the engine platform tools requires an OS sandbox first — was
correct for the mechanism then in view.

`--strict-mcp-config` changes that. It ignores **all** other MCP configuration
and uses only what `--mcp-config` names. Combined with the existing
`--setting-sources project` and the per-universe Claude config dir
(`resolve_claude_config_dir`), the turn's MCP surface becomes exactly what the
daemon hands it — a positive grant, not a rot-prone deny list.

Verify before building on it (task 1.1). If `--strict-mcp-config` does not hold,
this whole change reverts to being blocked on `engine-os-sandbox`, and that is a
finding worth having early rather than late.

## Why daemon-implemented file tools, not `Read`/`Write`/`Edit`

The 2026-07-03 note records that `Read` cannot be confined to a directory via
the CLI: headless treats `Read`/`Glob`/`Grep` as default-allowed, and a bare
deny is all-or-nothing. Precedence makes the obvious workaround fail too —
denying `Read` broadly while allowing `Read(./**)` loses, because deny wins.

So the filesystem capability arrives as MCP tools the daemon implements
(`fs_list` / `fs_read` / `fs_write` / `fs_delete`, universe-scoped), where
confinement is a `Path.resolve()` containment check in Python — the pattern
`_scoped_wiki_root` already uses. `Read`/`Write`/`Edit`/`Bash` stay denied.

Consequence worth stating plainly: containment is only as good as that check.
It must reject `..` traversal, absolute paths outside the root, and symlinks
that resolve outside it, and it must be tested in the ACCEPT direction too — a
guard that rejects everything passes a reject-only test suite
(`env-var-identity-switch-is-a-no-op`, `silent-failure-dispatch-and-tests`).

## Where authority lives

Tier decides the **tool grant**, not the write. One place, before the model runs:

| Turn tier | MCP server attached | File tools | Effect |
|---|---|---|---|
| FOUNDER | yes, scoped to this universe | yes | can build, manage, edit |
| anything else | none | none | conversation only |

This is strictly stronger than the current `if bound_tier == FOUNDER:` around
the extractor, because a non-founder turn cannot even *attempt* a write — there
is no tool to call. It also preserves the guarantee that `api/wiki.py:2523-2541`
depends on: that path skips the MCP ACL gate on the stated grounds that the
intelligence is first-party for its own universe, which only holds while
something upstream proves the caller is the owner.

The MCP server binds one universe at construction. It never takes a universe id
from the model — the same rule that removed `fallback_universe_id` from
`deliver_app_event`. A tool that accepts a universe id is a tool that can be
talked into naming someone else's.

## Harness templates

A harness shape (OpenClaw, Hermes, Claude Code, Codex) is a **seed set of files
in the project folder** — what the instruction file is called, how memory and
skills are laid out, what conventions apply. It is not platform code and gets no
special-casing. `create_agent` takes an optional template name that seeds those
files; the agent can then edit them, mix them, or write its own. This is the
"reduced powerful composable primitives" rule: ship the folder and the file
tool, not fifteen bundled harnesses.

## Self-modification

"Change his own GitHub and thus change himself" composes from parts that exist:
the `community-patch-loop` spec and the patch automation already open PRs
against the platform. The agent drives it through
`write_graph target=automation`, the same verb a chatbot user has today. Nothing
here grants the engine git or shell access — it asks the platform to run an
automation, and the automation does the work under its own authority.

## The platform tools cannot call the API directly (found 2026-08-07)

`api/cloud_automations.py:49-55` authorises through
`permissions.is_authenticated_request()` + `permissions.current_actor_id()` —
**request-scoped daemon state**. `api/custom_agents.py` is the same shape. The
MCP server is spawned by the CLI, which is spawned by the daemon, so it is a
separate process with none of that context: a direct call returns
`authentication_required`, or worse, resolves to `anonymous` and quietly reads
nothing.

Do NOT solve this by having the subprocess assert an identity from the
environment. That path is already a known dead end — four security tests once
passed while running as the resource OWNER because `UNIVERSE_SERVER_USER` never
reaches the credential-derived authority checks. An env var that names an actor
is a wish, not an authorization.

**The universe MCP server is a thin client of the daemon**, exactly like the
Slack transport became for `deliver_app_event`. It holds no authority; it
describes an intent and the daemon executes it under the founder's own,
server-derived authority. The daemon already serves an authenticated local
ingress on `8002` (`app_ingress_http`), so this is a second route on a proven
channel rather than a new mechanism.

One difference from the chat ingress, and it matters: the app-ingress HMAC key
authorises "deliver an event as any sender" — deliberately broad, because the
transport serves many universes. A per-turn tool server serves exactly ONE
universe, so it must get a **per-turn, universe-scoped, expiring token**, not
the shared key. Otherwise a token that leaks out of one universe's subprocess
can act on every universe, which is precisely the blast radius the
bind-one-universe-at-construction rule exists to prevent.
