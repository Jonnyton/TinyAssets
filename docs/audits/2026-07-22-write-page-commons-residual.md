# `write_page scope=commons` residual — classification

**Date:** 2026-07-22
**Lane:** `claude/write-page-commons-residual`
**Verdict:** **LIVE — misworded, and narrower than filed.** The residual is true
of the canonical `write_page` *handle*, not of the platform: two other live,
authenticated-callable paths already free-form commons-write. The same two paths
also bypass the 2026-07-02 brain-write relay.
**Evidence base:** `origin/main` @ `2b9639a3` (re-checked against `19bf2534`;
the intervening commits touch only `.agents/activity.log` and a `docs/specs/`
file). Static analysis + existing test assertions + one read-only `tools/list`
probe. **No writes were performed against any live surface.**
**Cross-family review:** Codex — `partially-refuted`. See *Review* below; its
refutation is folded into Findings 2 and 3 and corrected this document's original
conclusion.

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

Two definitions — and the gap between them is most of the story.

## What "scope=commons" actually names

The clause is shorthand for a **deferred fix**, not a missing feature. It traces
to `docs/design-notes/2026-07-02-universe-intelligence-relay-architecture.md:456-458`,
in the list of items Codex accepted as deferrable for M1:

> (a) authenticated founders cannot free-form commons-write via `write_page`
> (omitted id resolves to home → relays; kept fail-closed to prevent a
> private-canon→public-commons leak) — **planned fix: a `scope="commons"` param**

carried forward at line 517 ("Still open from §15"). This is why the clause
greps to nothing: **it names the proposed remedy (a parameter) rather than the
defect.** No `scope` argument exists on either `write_page` today.

## Finding 1 — the canonical `write_page` handle genuinely cannot select commons

`tinyassets/universe_server.py:751` routes in this order:

| Line | Branch | Destination |
|---|---|---|
| `:809-815` | anonymous + mutating → `write_gate_rejection` | **rejected** |
| `:816` | `kind=` issue filing | commons ✔ |
| `:844-851` | `target_universe` truthy | `relay_to_universe` |
| `:882-899` | fall-through | commons free-form write/patch |

The fall-through at `:882-899` is reached only when `target_universe` is falsy,
which never happens for a caller allowed to write:

1. **Authenticated callers never reach it.** `:849` calls `_request_universe("")`
   (`api/helpers.py:89`), which returns the founder's bound home or falls back to
   `_designated_public_universe()`, whose final fallback is the literal
   `"default-universe"` (`helpers.py:143`). It cannot return `""`, so `:851`
   always relays.
2. **Anonymous callers are rejected first**, by `write_gate_rejection`
   (`auth/middleware.py:443`) whenever `writes_require_identity()` is true.
3. **The one ungated anonymous path is a no-op** — `is_patch_preview`
   (`:809-812`) skips the gate only for `dry_run=True` patches. Codex confirmed
   this preview is genuinely non-mutating (`api/wiki.py:930-949`).

`tests/test_universe_write_boundary.py::TestPrivateCanonRelay` locks this in:
`test_founder_page_write_is_relayed_not_written` (`:193-225`) authenticates a
founder *holding `tinyassets.wiki.write`*, issues a plain page write, and asserts
it lands **neither** in her universe wiki **nor** on the shared commons.

`kind=` filings are not a substitute: they accept only
bug/feature/design/patch_request and explicitly reject arbitrary `content`/body
(`api/wiki.py:1994-2025`).

### Production write-gating (corrected)

An earlier draft of this audit said "the production WorkOS 'optional' provider,"
conflating two providers. Codex's correction: `deploy-prod.yml:580-603` selects
**WorkOS when configured and `optional` otherwise**, and *both* return
`resolve_always_writes() → True` (`auth/workos_provider.py:186-196`;
`auth/provider.py:1112-1127`). No production deploy configuration sets the write
gate false. The conclusion holds; the attribution was imprecise.

## Finding 2 — but the *platform* has two other authenticated commons-write paths

This is where the residual's wording misleads, and where Codex's refutation
lands. "Authenticated founders cannot free-form commons-write" is true of the
handle and **false of the platform**.

### (a) The hidden legacy `wiki` tool — on canonical `/mcp` itself

`universe_server.py:1010-1017` lists `wiki` in `_DEPRECATED_TOOL_NAMES`. The
`_DeprecatedToolVisibility` middleware (`:1939-1970`) drops those tools from
`tools/list` **but keeps them callable** — its own comment: *"tools/call
resolution is unaffected — so the legacy tools stay dispatchable"* and
*"Signed-in callers and dev mode keep them for the migration release."*

`wiki(action="write"|"patch", universe_id="")` therefore reaches `_wiki_impl`
directly, and an empty `universe_id` explicitly selects the shared root, which
`api/wiki.py:2486-2490` documents as *"a shared surface and is not gated here."*

So a signed-in founder can free-form commons-write **on `/mcp`**, today, via a
tool that is invisible in `tools/list` but dispatchable.

### (b) `directory_server.write_page` — on `/mcp-directory`

`tinyassets/directory_server.py:421` defines a second `write_page` with an
identical signature and the same anonymous write gate, but **zero relay logic**:

```console
$ git show origin/main:tinyassets/directory_server.py \
    | grep -n "relay\|_request_universe\|is_authenticated_request"
(no matches)
```

It passes `universe_id` straight to `_wiki_impl` (`:496-515`). Its own test
asserts this as intended — `test_directory_write_page_honors_target_universe`
(`test_directory_server.py:346-377`) writes `universe_id="splitroot"` and asserts
the content lands at `<data>/splitroot/wiki/drafts/plans/…`.

| Call (authenticated) | `/mcp` `write_page` | `/mcp` legacy `wiki` | `/mcp-directory` `write_page` |
|---|---|---|---|
| page write, id omitted | `relay_to_universe` | **commons write** | **commons write** |
| page write, id = own home | `relay_to_universe` | **direct universe write** | **direct universe write** |

### The split is not an auth-scope artifact

All three paths share the same downstream gates — the anonymous write gate, the
`require_action_scope("wiki", …)` check (`api/wiki.py:2535-2541`), and the
per-universe ACL (`:2491-2504`). The last two live *inside* `_wiki_impl`,
downstream of every caller. The divergence is purely that `write_page` on `/mcp`
returns `relay_to_universe` **before** reaching `_wiki_impl` and the other two do
not.

The two test suites hold identity constant and still disagree: the relay test
grants `tinyassets.wiki.write` and gets a relay; the directory test grants
`_FOUNDER_SCOPES` + `admin` on the target universe
(`test_directory_server.py:60-69`) and gets a write.

## Finding 3 — the same two paths bypass the brain-write relay

This is the more serious half, and it is *not* what the residual tracks.

The §13 invariant — *"the chatbot does not write the brain"* — is implemented in
exactly two places:

1. `universe_server.write_page`, which relays any universe-targeted page write
   (`:844-899`).
2. `_BRAIN_WRITE_RELAY_ACTIONS` (`:1026-1031`) = `{set_premise, add_canon,
   add_canon_from_path, soul.edit}`, relayed at `:1111` — and its own header
   comment scopes it to *"the deprecated fat `universe` tool."*

The legacy **`wiki`** tool's `write`/`patch` are in neither set, and
`directory_server.write_page` has no relay at all. So a signed-in founder can
write directly into their own universe's page substrate — the private canon the
reshape was written to protect — via either path. The per-universe ACL still
confines them to universes they own, so this is **not** a cross-founder leak; it
is the same-founder brain-write door the reshape closed on one handle and left
open on two others.

This is distinct from the row's third clause, which tracks
`tinyassets/mcp_server.py` (the stdio daemon server, owned by PR #1561). Both
`wiki`-on-`/mcp` and `directory_server.py` are separate, currently unrecorded
paths.

### Both are live, and one is the publicly listed URL

`deploy/cloudflare-worker/worker.js:210-212` proxies `/mcp-directory` and
everything under it. `docs/ops/acceptance-probe-catalog.md:190` lists it as a
connector URL under test. `packaging/registry/server.json:24` publishes
`https://tinyassets.io/mcp-directory/catalog/…` as the remote URL for external
MCP directory listings — so a surface without the relay guard is the one
advertised to third-party hosts, while AGENTS.md Hard Rule 11 names
`https://tinyassets.io/mcp` as "canonical public endpoint … only."

A read-only `tools/list` probe on 2026-07-22 confirms it is serving:

```console
$ curl -s -X POST https://tinyassets.io/mcp-directory -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
{"jsonrpc":"2.0","id":"server-error","error":{"code":-32600,
 "message":"Bad Request: Missing session ID"}}
```

("Missing session ID" is the MCP transport demanding a session — the route exists
and is live. No write was attempted.)

## The design note's own write-principals matrix

§13's matrix (line 332) states the intended model:

| Writer | Brain | Branches | Commons |
|---|---|---|---|
| Universe intelligence | YES — sole brain writer | yes | yes |
| **Chatbot / app, founder's WorkOS** | NO — relays via `converse` | yes | **yes** |

Codex's framing is exact: *"The principals matrix is satisfied at platform level
by the legacy/directory routes, but not by the canonical `/mcp` `write_page`
handle."* The Commons cell is satisfied only by the two routes that also violate
the Brain cell. No single path implements the intended row.

## Spec status — a genuine gap

`openspec/specs/live-mcp-connector-surface/spec.md` (AGENTS.md Hard Rule 11's
named as-built truth) specifies `write_page`'s handle set (line 28) and its
anonymous 401 gate (line 71). It says nothing about commons routing, nothing
about a `scope` argument, nothing about `/mcp-directory` having different write
semantics for the same handle name, and nothing about deprecated tools remaining
dispatchable after being hidden from `tools/list`.
`openspec/specs/wiki-commons/spec.md` specifies the fifteen `wiki` actions and
the ACL gate, but not the relay/commons split.

So the as-built truth above lives **only** in a design note and in two mutually
contradictory test files. That is spec drift independent of how the capability
question is settled.

## Git history

`git log --follow origin/main -- tinyassets/universe_server.py` shows **no
commits between 2026-06-26 and 2026-07-13**. The relay reshape never landed on
`main` as its own commit; the file's next touch is `d9250f8f` (#1441), then
`b91a6b07` (#1437), `b372e000` (#1462), `519fb2ea` (#1552).

This rules out "stale — closed by the reshape, nobody deleted the row": there was
no separate reshape commit that could have closed it, and Codex confirmed no
later closure exists (`write_page` still has no `scope` param). It also plausibly
explains Finding 3 — a reshape that landed folded into unrelated work is exactly
the shape that guards one handle and misses its siblings.

## Classification

**LIVE — misworded.** Not stale. Not unverifiable. **Rewrite, do not delete.**

- The behavior the clause points at is real for the canonical handle, reachable
  by inspection, and test-enforced.
- The wording names a parameter that does not exist, which is why it greps to
  nothing and why the previous cycle could not classify it.
- The wording also implies a platform-wide property that does not hold: two
  other live authenticated paths already do the thing it says is impossible.

## What "done" means

The `/mcp` `write_page` side is a **design decision, not a defect fix** — the gap
is fail-closed on purpose, and reversing it means changing a passing boundary
test. A follow-up lane should:

1. **Decide the intent** — should founders free-form commons-write, and through
   which handle? The design note says yes; the canonical handle says no; two
   deprecated/secondary paths say yes. This is the host-decision at the centre of
   the row.
2. **Reconcile the paths.** The same logical operation should not have opposite
   semantics across `/mcp` `write_page`, `/mcp` `wiki`, and `/mcp-directory`
   `write_page` — all of which "route to the same backend state"
   (`universe_server.py:2205-2211`).
3. If commons-write is wanted: add the explicit target (`scope="commons"`) so a
   commons write is *chosen*, never *inferred from the absence of a universe
   target* — the implicit derivation at `:844-851` is what makes the current
   behavior surprising.
4. Update `TestPrivateCanonRelay` and
   `test_directory_write_page_honors_target_universe` together; today they encode
   contradictory contracts.
5. Write the outcome into `openspec/specs/live-mcp-connector-surface/spec.md`
   either way — the spec gap stands regardless of how (1) resolves.

**Finding 3 is the more urgent half and is not this lane's to fix.** It is a live
write-boundary question, not a wording question. It is recommended as its own
row rather than folded into this one, because STATUS.md is heavily contended this
session and a wide edit would strand the lane.

## STATUS.md action taken

The clause was rewritten in place, from the remedy to the defect, and scoped to
the handle rather than the platform:

> `write_page` can't select commons (universe_server.py:851); legacy `wiki` +
> `/mcp-directory` bypass the relay (audit 2026-07-22)

The edit was deliberately held to that single clause. The row's other two
residuals (WebFetch SSRF guard; legacy `mcp_server.py` doors, owned by PR #1561)
were not touched.

## Review

Dispatched to Codex as a refutation ask (`codex exec -` on stdin, read-only
sandbox), framed as "try to refute this claim" with the exact verify commands.

**Verdict: `partially-refuted` @ `origin/main@19bf2534`.**

- **Confirmed:** the narrow `universe_server.write_page` claim, the auth-gating
  conclusion, that the anonymous patch preview is non-mutating, that `kind=` is
  not equivalent to free-form writing, and that no later closure exists.
- **Refuted:** the broader capability-gap interpretation — Codex found the hidden
  legacy `wiki` handle on `/mcp` (Finding 2a), which this document had missed
  entirely. It independently found the directory path as well.
- **Corrected:** the production-provider description (see Finding 1).

Codex's recommended disposition — *"REWRITTEN concretely, not deleted"* — is what
was applied. Finding 3 is this author's extension of Codex's refutation: if those
two paths can commons-write, they can also write private canon, because the relay
sets do not cover them.
