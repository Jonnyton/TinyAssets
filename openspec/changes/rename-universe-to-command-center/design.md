# Design: rename-universe-to-command-center

## Context

The founder renamed the product concept on 2026-10-01: a person's universe is
now their **command center**. The rename is approved; this document decides
how to do it safely. The inventory and counts are in `proposal.md`.

What makes this more than a find-and-replace:

1. **The MCP input schema is strict.** FastMCP 3.2.0 rejects an unknown keyword
   argument (`unexpected_keyword_argument`; verified locally 2026-10-01 with a
   one-tool server called with `universe_id` against a `command_center_id`
   signature). A plain rename would break every chatbot conversation that cached
   the old tool list.
2. **Users' own code depends on the old names.** Custom UI bundles stored in
   accounts read `universe_id` and `universe_name` from the bridge identity
   (`onboarding/app_ui.js:346`).
3. **Storage keys are part of the deletion and ownership logic.** Account
   deletion builds its table set from the schema's universe column. Run actors
   are stored as `universe:<id>` and compared by prefix
   (`automation_events.py:75`, `:320`).
4. **The resident description budget has almost no headroom.** The served
   engine block is 29,839 of 30,000 characters
   (`tests/test_converse_turn_cost.py:79`), and it contains 34 occurrences of
   "universe".

## Goals / Non-Goals

**Goals**

- A person never reads "universe" in the app, the website, the store copy, a
  served description, the connector instructions, a prompt name, a parameter
  name, an error code, or the agent's own words.
- No client breaks during the switch: no cached tool list, open window, website
  build or stored custom UI.
- One authority for the old-to-new name mapping.

**Non-Goals**

- Rewriting dated records: `docs/audits`, `docs/reviews`, dated design notes,
  `.agents/activity.log`, `archive/`, and archived changes. A rename sweep
  rewrites evidence; they describe what was true when written.
- The fiction domain's "universe" when it means a story world.
- Retiring the hidden legacy fat tool `universe`. It is not advertised and its
  retirement is a separate decision.
- The canary handle set. No handle name changes.

## Decisions

### D1. Vocabulary

| Use | Form |
|---|---|
| Prose | "command center", "your command center", plural "command centers" |
| Titles / buttons | "Command Center" only in title case contexts; buttons are sentence case: "Switch command center" |
| Identifiers / keys | `command_center`, `command_center_id`, `command_centers` |
| Agent self-reference | "I'm your command center" (first person, matching current "my universe" phrasing) |
| New-user greeting | "Welcome, commander." (empty-thread heading, `app.html` `#thread-empty`) |
| The person | "commander" only in the greeting; elsewhere "you" as today |

"Command center" is 6 characters longer than "universe". That matters only in
the resident description budget (D5).

### D2. Handles stay; one prompt is renamed

`read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`,
`converse` and `get_status` keep their names. `scripts/mcp_public_canary.py
--assert-handles` therefore does not change, and Hard Rule 11's canonical set is
untouched. The canary still runs after C1 deploys, because C1 changes the public
surface.

`meet_universe` becomes `meet_command_center`, titled "Meet Your Command
Center", and the old prompt is removed rather than aliased. People pick prompts
from a list, so nothing calls the old name, and the spec's catalog is exact. The
delta spec updates the catalog.

### D3. Old input names are rewritten before validation, in one table

One module, `tinyassets/command_center_aliases.py`, holds the only mapping:

- parameter names: `universe_id` → `command_center_id`;
- `target` values: `universe` → `command_center`, `universe_files` →
  `command_center_files`, `universe_file` → `command_center_file`;
- any other enum value C1's generated inventory finds (e.g. a workspace
  `storage: "universe"`).

A FastMCP `Middleware.on_call_tool`, the pattern already used at
`engine_mcp_server.py:287` and `universe_server.py:3991`, rewrites an incoming
call's arguments through that table **before** schema validation, on both the
connector server and the engine server. The advertised schema carries only the
new names, so aliases cost zero description bytes. The app's own HTTP routes
that take `universe_id` in a JSON body (e.g. Stop, `app.html:1852`) normalize
through the same table.

The rewrite rules:

- If both names are sent with **different** values, the call is refused with
  `conflicting_alias`, naming both. It never guesses.
- If both are sent with the same value, the call is accepted.

Every alias hit logs one structured line (`alias_used name=<old> handle=<h>`).
A test enforces the table against the live schema: every new name must exist in
the advertised schema, and no advertised parameter or target may still contain
"universe".

**Deprecation window.** Aliases are removed in a separate small PR once
production logs show **zero alias hits for 14 consecutive days**, measured with
`scripts/droplet.py`. This is a measured condition, not a date. Bridge aliases
(D4) are exempt and permanent.

Rejected alternatives:

- *Both names as visible parameters.* This costs schema bytes on every turn, and
  shows the old word to the chatbot.
- *A hard cut with no aliases.* Every open conversation would fail on its next
  call, and the error would name a parameter the user never chose.

### D4. Response keys switch to the new names; the bridge keeps both

Server responses emit `command_center_id`, `command_centers` and the renamed
error codes. They do **not** emit both old and new keys: duplicating them costs
bytes on every read and leaves two authorities for one fact.

First-party clients move with the slice:

- `app.html` and `app_ui.js` are served by the same deploy, so they switch
  atomically. The desktop (Electron) and Android shells load the live SPA.
- The website deploys separately (`deploy-site-react.yml`). Its read contract
  (`WebSite/shared/mcp/public-read-contract.js`) accepts **either** key, and that
  change lands and is verified live **before** the server stops emitting the old
  key.
- An open app window from before the deploy is covered by D3 on input, and by
  the existing stale-asset reload on output.

**The custom UI bridge is the exception.** Its identity object returns
`command_center_id` and `command_center_name` **and** `universe_id` and
`universe_name`, permanently. Every bridge method name or argument a bundle can
send keeps accepting its old form too. Stored bundles are user-authored code
(Hard Rule 9 applies in spirit), and nothing measures which bundles read which
key. Removing these keys would need a scan of every stored bundle, which is out
of scope.

### D5. Paying for the longer word inside the description budget

A plain swap in the resident engine block costs +204 characters against 161 of
headroom. C0/C1 therefore rewrite the affected sentences rather than swap
words. Where a sentence already says "your" or "the owner's", it can drop the
noun ("your folder" for "your universe folder"). The ratchet value is **not**
raised. The `write_graph` description must stay under 12,000
(`tests/test_served_tool_guidance.py:369`). The connector tool docstrings carry
no equivalent ceiling today, but they get the same rewrite-not-swap treatment.
The channel-agnostic and vendor-neutral ratchets are unaffected: the change
introduces no channel or vendor words. `build_plugin.py` regenerates the mirror
in each slice.

### D6. Code identifiers: recommend **not** renaming (C3 cut)

The cost:

- 7,059 identifier occurrences and 12 modules renamed (`universe_server.py`,
  `universe_intelligence.py`, ...), plus about 17,000 test lines that import or
  monkeypatch them by module path.
- A regenerated 10,000-line plugin mirror.
- A conflict with every open PR.
- A diff no reviewer can meaningfully check.

It changes nothing a person or the agent reads. Without it, the cost is one
glossary sentence in PLAN.md: "command center (in code and storage:
`universe`)". It replaces the existing definition in place.

If the founder wants it anyway, it is one scripted, generated PR in a window
with no open PRs, gated on the full suite plus the Linux oracle, with no
compatibility shims.

The plugin id `tinyassets-universe-server` follows the same reasoning: installed
copies update by that id. Its display name and description are copy and change
in C0. The id stays.

### D7. Storage and on-disk names: recommend **not** renaming

This covers `u-<id>` directories, the 11 `universe*` tables, about 80
`universe_id` columns, `.universe_id`, `.universe-tool-slots`,
`.universe_seats.db`, the stored `universe:<id>` actor ids, and the
`TINYASSETS_*UNIVERSE*` env vars.

No person sees these. `u-` is not even the word. The actor id is opaque, and it
appears in a read only as an identifier.

A migration would have to:

- rename tables and columns under the write lock, during a deploy that already
  kills in-flight turns;
- rewrite every stored actor id and every prefix comparison;
- re-derive the account-deletion table set, which keys on the column name, so a
  missed table becomes a cross-user retention bug;
- invalidate idempotency digests that include ids;
- move directories that bind mounts and jails resolve by path;
- run against production data with no rollback short of a restore.

Recommendation: **leave storage as is.** "Everywhere" is satisfied at every
surface a person or agent reads. The API boundary (D3/D4) is the single place
the names translate. If the founder overrules this, C4 becomes its own change
with a migration, a backfill, a dry run on a production copy, and a rollback
plan.

### D8. Agent self-reference and existing brains

Served guidance, the persona and seed text, and `universe_tools.py`'s
self-description ("My universe is a folder, mounted at /u ...") switch to the
command center. **Existing users' brain and soul files are not rewritten**:
they are agent-authored memory in the user's space, and rewriting them would be
the platform editing a user's agent. The served guidance names the new term, so
an agent with older notes reads "command center" in its current instructions
and adopts it. The `/u` mount point is unchanged; it is a path, not the word.

## Risks / Trade-offs

- **Code and product words diverge** (D6). Mitigated by the PLAN glossary line.
  A contributor reading `universe_id` in code needs one sentence to translate.
- **An alias lingers.** The 14-day zero-hit rule is measured. If hits never
  reach zero (a client hard-coded `universe_id`), the aliases stay, which costs
  nothing.
- **Website skew.** The website accepts either key before the server switches
  (D4 ordering).
- **Copy tests.** Many tests assert exact strings, so C0 updates them in the
  same slice. A green suite after C0 proves the tests moved, not that they were
  weakened: each changed assertion swaps the old string for the new one, and no
  assertion is deleted.

## Migration Plan

C0 (copy) → C1a (website accepts either key; verify live) → C1b (server: new
names, aliases middleware, renamed prompt, error codes; canary
`--assert-handles` green; `deployed_sha.py --assert-contains`) → C2 (living
docs, specs, capability dir renames with every reference updated) → alias
removal once the 14-day condition holds. C3 and C4 run only if the founder
overrules D6 or D7.

Rollback: C0 and C2 are text. C1b rolls back by reverting the PR. Because inputs
accept both names, a rollback leaves no client unable to call.

## Open Questions

- The founder decides D6 (code identifiers) and D7 (storage). The
  recommendation for both is no.
