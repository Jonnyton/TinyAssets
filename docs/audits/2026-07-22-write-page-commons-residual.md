# `write_page scope=commons` residual — classification

**Date:** 2026-07-22
**Lane:** `claude/write-page-commons-residual`
**Verdict:** **LIVE, misworded, and surface-scoped** — the residual is real on
`/mcp`, but the same handle on the live `/mcp-directory` surface already does
what the residual asks for, without the guard the residual was protecting.
**Evidence base:** `origin/main` @ `2b9639a3`. Static analysis + existing test
assertions + one read-only probe of the live surface. No writes were performed.

---

## Why this audit exists

STATUS.md carries a three-part Concern:

> [filed:2026-07-02 verified:2026-07-22] Reshape residuals: WebFetch SSRF guard,
> `write_page` scope=commons, legacy `mcp_server.py` doors.

A previous restock cycle declined to brief the middle clause, on the grounds that
`git grep commons origin/main -- tinyassets/api/wiki.py` returned nothing, so it
could not tell whether the item was unimplemented or stale.

**That grep used the wrong file.** `write_page` is not defined in
`tinyassets/api/wiki.py` at all:

```console
$ git grep -ln "def write_page" origin/main -- tinyassets/
origin/main:tinyassets/directory_server.py
origin/main:tinyassets/universe_server.py
```

Two definitions — and that turns out to be the whole story.

## What "scope=commons" actually names

The clause is shorthand for a **deferred fix**, not a missing feature. It traces
to `docs/design-notes/2026-07-02-universe-intelligence-relay-architecture.md:456-458`,
in the list of items Codex accepted as deferrable for M1:

> (a) authenticated founders cannot free-form commons-write via `write_page`
> (omitted id resolves to home → relays; kept fail-closed to prevent a
> private-canon→public-commons leak) — **planned fix: a `scope="commons"` param**

carried forward at line 517 ("Still open from §15"). This is why the clause
greps to nothing: **it names the proposed remedy (a parameter) rather than the
defect (a capability gap).** No `scope` argument exists on either `write_page`.

## Finding 1 — on `/mcp`, the residual is real

`tinyassets/universe_server.py:751` routes in this order:

| Line | Branch | Destination |
|---|---|---|
| `:809-815` | anonymous + mutating → `write_gate_rejection` | **rejected** |
| `:816` | `kind=` issue filing | commons ✔ |
| `:844-851` | `target_universe` truthy | `relay_to_universe` |
| `:882-899` | fall-through | commons free-form write/patch |

The fall-through at `:882-899` is the only free-form commons path, and it is
reached only when `target_universe` is falsy — which never happens for a caller
allowed to write:

1. **Authenticated callers never reach it.** `:849` calls `_request_universe("")`
   (`tinyassets/api/helpers.py:89`), which for an authenticated request returns
   the founder's bound home or falls back to `_designated_public_universe()`,
   whose final fallback is the literal `"default-universe"` (`helpers.py:143`).
   It cannot return `""`, so `:851` always relays.
2. **Anonymous callers are rejected first.** `:813` calls
   `write_gate_rejection("write_page")` (`tinyassets/auth/middleware.py:443`),
   which rejects anonymous mutating calls when `writes_require_identity()` is
   true — derived from `is_auth_required() or resolve_always_writes()`
   (`provider.py:728-739`), and the production WorkOS "optional" provider returns
   `resolve_always_writes() → True` (`provider.py:1118-1127`).
3. **The one ungated anonymous path is a no-op** — `is_patch_preview`
   (`:809-812`) skips the gate only for `dry_run=True` patches, which mutate
   nothing.

**On `/mcp`, no caller can create or patch a free-form commons page.** Only
`kind=` filings reach the commons. `tests/test_universe_write_boundary.py::TestPrivateCanonRelay`
locks this in: `test_founder_page_write_is_relayed_not_written` (`:193-225`)
authenticates a founder *holding `tinyassets.wiki.write`*, issues a plain page
write, and asserts it lands **neither** in her universe wiki **nor** on the
shared commons.

## Finding 2 — `/mcp-directory` has no relay at all

This is the part the residual's wording hides, and it inverts the conclusion.

`tinyassets/directory_server.py:421` defines a **second** `write_page` with an
identical signature and the same anonymous write gate — but **zero relay logic**:

```console
$ git show origin/main:tinyassets/directory_server.py \
    | grep -n "relay\|_request_universe\|is_authenticated_request"
(no matches)
```

It passes `universe_id` straight through to `_wiki_impl`
(`directory_server.py:496-515`). So for an **authenticated** caller:

| Call | Result on `/mcp` | Result on `/mcp-directory` |
|---|---|---|
| page write, `universe_id` omitted | `relay_to_universe` | **free-form commons write** |
| page write, `universe_id=<own home>` | `relay_to_universe` | **direct write into that universe's wiki** |

Both surfaces are mounted by the same `create_app()`
(`universe_server.py:2213-2222`): `/mcp` → `mcp`, `/mcp-directory` and
`/mcp-directory/catalog/<version>` → `directory_mcp`. The docstring at `:2205`
states both "route to the same backend state," and
`connector_catalog.directory_mcp_remote_url()` returns the versioned directory
path as "the versioned directory MCP URL **advertised to chatbot hosts**."

The directory surface's own test asserts this behavior as intended —
`tests/test_directory_server.py::test_directory_write_page_honors_target_universe`
(`:346-377`) writes `universe_id="splitroot"` and asserts the content lands at
`<data>/splitroot/wiki/drafts/plans/archon-telemetry-contract.md` and *not* on
the shared wiki. That is the exact substrate `universe_server.write_page` refuses
to write and relays instead.

### The asymmetry is not an auth-scope artifact

Both surfaces share the *same* downstream gates, so neither explains the split:

- The **anonymous write gate** is identical — `directory_server.py:477-479` calls
  the same `write_gate_rejection("write_page")`.
- The **action-scope gate** (`require_action_scope("wiki", action, …)`) and the
  **per-universe ACL** live inside `_wiki_impl` (`api/wiki.py:2491-2504`,
  `:2535-2541`), i.e. downstream of both callers.

The divergence is purely that `/mcp` returns `relay_to_universe` *before*
reaching `_wiki_impl` and `/mcp-directory` does not. The two tests hold identity
constant and still disagree: the relay test authenticates a founder holding
`tinyassets.wiki.write` and gets a relay; the directory test authenticates a
founder with `_FOUNDER_SCOPES` + `admin` on the target universe
(`test_directory_server.py:60-69`) and gets a write.

### It is live — and it is the publicly listed URL

`deploy/cloudflare-worker/worker.js:210-212` explicitly proxies `/mcp-directory`
and everything under it. `docs/ops/acceptance-probe-catalog.md:190` lists
`https://tinyassets.io/mcp-directory` as a connector URL under test. More
pointedly, `packaging/registry/server.json:24` publishes
`https://tinyassets.io/mcp-directory/catalog/…` as the remote URL for external
MCP directory listings — so the surface *without* the relay guard is the one
advertised to third-party hosts, while AGENTS.md Hard Rule 11 names
`https://tinyassets.io/mcp` as "canonical public endpoint … only."

A read-only `tools/list` probe on 2026-07-22 confirms the endpoint is serving MCP:

```console
$ curl -s -X POST https://tinyassets.io/mcp-directory -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
{"jsonrpc":"2.0","id":"server-error","error":{"code":-32600,
 "message":"Bad Request: Missing session ID"}}
```

("Missing session ID" is the MCP transport demanding a session — the route
exists and is live. No write was attempted.)

### Two consequences

1. **The residual's premise is surface-scoped, not absolute.** "Authenticated
   founders cannot free-form commons-write via `write_page`" is true of `/mcp`
   and false of `/mcp-directory`.
2. **The relay reshape is enforced on only one of two live surfaces.** The §13
   invariant — *"the chatbot does not write the brain"* — is what
   `universe_server.write_page` implements and what `TestPrivateCanonRelay`
   guards. `directory_server.write_page` bypasses it for any authenticated
   founder who supplies their own `universe_id`. The per-universe ACL still
   confines them to universes they own (`api/wiki.py:2491-2504`), so this is not
   a cross-founder leak — but it is the same-founder brain-write door the reshape
   was written to close.

This second door is **not** the one tracked by the row's third clause: that one
is `tinyassets/mcp_server.py` (the stdio daemon server, owned by PR #1561).
`directory_server.py` is a distinct, currently unrecorded path.

## Why the residual is also worse than filed on `/mcp`

The `/mcp` side widened silently after filing, because a different lane closed
the remaining path:

- **As filed (2026-07-02):** authenticated founders could not commons-write; the
  anonymous/dev fall-through still worked.
- **After #1441 (2026-07-13) and #1437 (2026-07-15):** anonymous writes answer a
  401 challenge, so the fall-through became unreachable in production too.

Nobody re-verified the clause against the intervening auth work — the row was
stamped `verified:2026-07-22` while still carrying its 2026-07-02 wording.

## It contradicts the design note's own write-principals matrix

§13's matrix (line 332) states the intended model:

| Writer | Brain | Branches | Commons |
|---|---|---|---|
| Universe intelligence | YES — sole brain writer | yes | yes |
| **Chatbot / app, founder's WorkOS** | NO — relays via `converse` | yes | **yes** |

`/mcp` denies the last cell. `/mcp-directory` grants it *and* the cell above it
that should read NO. Neither surface matches the intended row.

## Spec status — a genuine gap

`openspec/specs/live-mcp-connector-surface/spec.md` (AGENTS.md Hard Rule 11's
named as-built truth) specifies `write_page`'s handle set (line 28) and its
anonymous 401 gate (line 71). It says nothing about commons routing, nothing
about a `scope` argument, and nothing about `/mcp-directory` having different
write semantics for the same handle name.
`openspec/specs/wiki-commons/spec.md` specifies the fifteen `wiki` actions and
the universe ACL gate, but not the relay/commons split.

So the as-built truth for all of the above lives **only** in a design note and in
two mutually contradictory test files. That is spec drift independent of how the
capability question is settled.

## Git history

`git log --follow origin/main -- tinyassets/universe_server.py` shows **no
commits between 2026-06-26 and 2026-07-13**. The relay reshape described in the
2026-07-02 design note never landed on `main` as its own commit; the file's next
touch is `d9250f8f` (#1441), then `b91a6b07` (#1437), `b372e000` (#1462),
`519fb2ea` (#1552). The reshape reached `main` folded into that later work.

This rules out the "stale — closed by the reshape, nobody deleted the row"
reading: there was no separate reshape commit that could have closed it, and no
`scope` param exists in either file today. It also plausibly explains Finding 2 —
a reshape that landed folded into unrelated work is exactly the shape that
updates one server module and misses its twin.

## Classification

**LIVE — misworded.** Not stale. Not unverifiable.

- The behavior the clause points at is real on `/mcp`, reachable by inspection,
  and test-enforced.
- The wording names a parameter that does not exist, which is why it greps to
  nothing and why the previous cycle could not classify it.
- The wording also implies a platform-wide property that does not hold: the
  same handle behaves oppositely on the other live surface.

## What "done" means

This is a **design decision, not a defect fix** on the `/mcp` side — the gap is
fail-closed on purpose, and reversing it means changing a passing boundary test.
A follow-up lane should:

1. **Decide the intent** — should founders free-form commons-write at all, or are
   `kind=` filings the intended sole commons surface? The design note says the
   former; `/mcp` implements the latter; `/mcp-directory` implements the former.
   This is the host-decision at the centre of the row.
2. **Reconcile the two surfaces.** Whatever (1) decides, the same handle name
   should not have opposite write semantics on two live paths that "route to the
   same backend state."
3. If commons-write is wanted: add the explicit target (the design note proposes
   `scope="commons"`) so a commons write is *chosen*, never *inferred from the
   absence of a universe target* — the implicit derivation at
   `universe_server.py:844-851` is what makes the current behavior surprising.
4. Update `tests/test_universe_write_boundary.py::TestPrivateCanonRelay` and
   `tests/test_directory_server.py::test_directory_write_page_honors_target_universe`
   together; today they encode contradictory contracts.
5. Write the outcome into `openspec/specs/live-mcp-connector-surface/spec.md`
   either way — the spec gap stands regardless of how (1) resolves.

**Finding 2 is the more urgent half and is not this lane's to fix.** It is
recommended as its own row rather than folded into this one, because it is a
live-surface write-boundary question, not a wording question, and STATUS.md is
heavily contended this session.

## STATUS.md action taken

The clause was rewritten in place, from the remedy to the defect:

> `write_page` commons write unreachable (universe_server.py:851 always relays;
> audit 2026-07-22)

Scope of the edit was deliberately held to that single clause. The row's other
two residuals (WebFetch SSRF guard; legacy `mcp_server.py` doors, owned by
PR #1561) were not touched.

## Verification

Static analysis of `origin/main` @ `2b9639a3`, the existing test assertions in
`tests/test_universe_write_boundary.py` and `tests/test_directory_server.py`, and
one read-only `tools/list` probe of `https://tinyassets.io/mcp-directory`. No
runtime write was attempted against any surface, and no live founder identity was
used. Cross-family review: dispatched to Codex as a refutation ask; verdict
recorded in the PR thread.
