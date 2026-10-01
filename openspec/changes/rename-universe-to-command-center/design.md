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

### D3. Retired input names are refused, naming the replacement (clean cutover)

*Founder, 2026-10-01, on this rename: "no old ids do not keep working, we are
still early in production so we are not maintaining old systems we dont have
old users we just have current testers that need to cleanly move to the new
system". This replaces the alias window the first draft proposed.*

`tinyassets/command_center_names.py` is the one authority. Every name is
derived by one rule (`universe` -> `command_center`), not a hand list. It does
three things:

- **Refuses retired names.** A retired argument name (`universe_id`) or enum
  value (`target=universe`, `universe_files`, `universe_file`, `scope=universe`)
  is refused as `{"error": "renamed", "retired": ..., "current": ...}`, for
  example "renamed: universe_id is now command_center_id". It is never
  silently accepted. The refusal comes from a FastMCP middleware
  (`CommandCenterNames`) registered innermost on both servers, so it runs
  before the tool's own validation and names the replacement instead of
  FastMCP's generic "unexpected keyword". On the connector it governs the
  seven advertised handles only; a hidden legacy tool keeps its own schema.
- **Maps current values to the handlers' names.** `internal_value` maps
  `command_center` to `universe` (and so on) until the code rename (C3)
  changes the handlers themselves. A retired value reaching a router directly
  becomes `retired:<value>`, an unknown target, so a caller that skips the
  edge also fails.
- **Renames parameters with a local binding.** `read_page`, `write_page` and
  `get_status` take `command_center_id`; inside, it is bound to the internal
  name until C3. Direct Python callers are migrated in the same PR.

The owner door (the app's private HTTP reads) passes targets through the same
routers, so the app sends the current target names. Its response keys stay
internal until C3, because only first-party code reads them.

A workspace packet's `storage: "universe"` and a branch's declared
`delivery_sender_universe_id` input are **not** renamed here. Both are stored
inside people's branch definitions, so they move with the storage migration
(C4), which rewrites the stored definitions and the code in one step.

### D4. Responses carry current names only; every first-party reader moves in the same PR

`CommandCenterNames` respells each JSON tool result before the result ceiling
measures it:

- keys (`universe_id` becomes `command_center_id`, `universes` becomes
  `command_centers`);
- error codes (`no_home_universe` becomes `no_home_command_center`);
- stored actor ids in identity fields, presented as `command_center:<id>`
  until C4 rewrites the stored value.

Responses do not carry the old keys alongside the new ones. A person's own
content is never respelled: run output, run files, command-center files,
conversation pages, `read_page`, and the engine's `read` / `write` / `edit` /
`bash` (Hard Rule 9).

First-party readers switch in the same PR:

- the website read contract and its baked snapshot (`command_centers`);
- `scripts/mcp_tool_canary.py`;
- the custom UI bridge, whose `whoami()` returns `command_center_id` /
  `command_center_name`. Production on 2026-10-01 holds **zero** stored UI
  bundles that call `whoami` or read `universe_name` (read-only count over
  `universe_app_ui`), so the cutover breaks no stored bundle.

`get_status` bumps `schema_version` to 3, per its own contract, which now says
a rename bumps the version with no alias window.

**The default agent definition.** A published definition is immutable and
fingerprinted under its idempotency key, so C1 publishes a **new** one
(`platform:command-center-default` / `command-center-default-v1`, named "Your
agent") rather than editing the old one, which would raise `AgentConflictError`
at every onboarding. New homes bind to it. A home bound to the retired
definition is still recognised as the founder's platform binding: the next
serving gesture re-points it to the new definition at its exact revision, and
the storage migration (C4) re-points the rest. The retired definition is looked
up, never re-published.

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

No person sees these, with **one exception the refute found**:

- **The stored actor id.** `api/runs.py:1508` prints `Actor:
  {run_record['actor']}` into the run summary, and `:1536` returns the raw value
  structurally, so `universe:<id>` reaches the chatbot.

The storage stays, and the presentation translates. C1 adds one
`present_actor()` at the API boundary. It renders `universe:<id>` as
`command_center:<id>` in summaries and in the structured field. The raw stored
value is never parsed back from presented output; nothing takes an actor as
input. `u-` in an id is not the word, so ids themselves are untouched. The `/u`
jail hides root dot-entries (`universe_tools.py:294`), so the marker files are
not visible to the agent.

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

### D9. Native shells carry their own copy and ship on their own release

The refute found copy that a live SPA deploy does not reach:

- the Android notification-channel description
  (`mobile/native/android/TinyAssetsMessagingService.java:225`);
- the iOS microphone permission string (`mobile/scripts/add_ios_scheme.py:46`);
- the bundled loading pages (`mobile/www/index.html:43`,
  `desktop-app/src/loading.html:43`).

C0 changes all four. Android also returns early when the channel already exists
(`:222`), so an updated binary would keep the old description. `ensureChannel`
therefore always calls `createNotificationChannel`. Android applies a new name
and description to an existing channel id and leaves the user's importance
setting alone. These reach people only with the next Play and desktop
releases. The founder runs those (`docs/host-actions.md`), and until then the
shells show the old word on those few strings.

## Risks / Trade-offs

- **Code and product words diverge** (D6). Mitigated by the PLAN glossary line.
  A contributor reading `universe_id` in code needs one sentence to translate.
- **An alias lingers.** The 14-day zero-hit rule is measured. If hits never
  reach zero (a client hard-coded `universe_id`), the aliases stay, which costs
  nothing.
- **Response size during the window.** Responses carry both id keys, a few
  bytes per response, until the aliases are removed (D4).
- **Copy tests.** Many tests assert exact strings, so C0 updates them in the
  same slice. A green suite after C0 proves the tests moved, not that they were
  weakened: each changed assertion swaps the old string for the new one, and no
  assertion is deleted.

## Migration Plan

C0 (copy, including the native strings, which ship with the next native
releases) → C1 (one PR covering the server and the first-party readers):

- new names primary;
- aliases at all three boundaries (D3);
- dual response keys (D4);
- `present_actor` (D7);
- the renamed prompt;
- evidence: canary `--assert-handles` green and `deployed_sha.py
  --assert-contains`.

→ C2 (living docs and specs, with the capability dir renames and every reference
updated) → alias and old-key removal with a `schema_version` bump, once the
14-day condition holds. C3 and C4 run only if the founder
overrules D6 or D7.

Rollback: C0 and C2 are text. C1 rolls back by reverting the PR. Because
responses carry both keys and inputs accept both names, a rollback leaves no
client unable to call or read.

## Open Questions

- The founder decides D6 (code identifiers) and D7 (storage). The
  recommendation for both is no.
