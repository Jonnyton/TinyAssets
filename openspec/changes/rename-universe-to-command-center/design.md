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
| The place or account | "command center": "your command center's connections", "Switch command center", "No public command centers" |
| The actor | "your agent": "Your agent is thinking...", "your agent replied", "Suggested by your agent", "Message your agent" |
| Agent self-reference | First person; the agent works *in* "my command center" (the place) |
| New-user greeting | "Welcome, commander." (empty-thread heading, `app.html` `#thread-empty`) |
| The person | "commander" only in the greeting; elsewhere "you" as today |

**Actor or place (lead decision, 2026-10-01).** "Universe" did two jobs: it
named the place a person owns, and it named the mind that acts in it. The
rename splits them. When the old word is the **subject of an action** (it
thinks, replies, answers, sees, asks, builds, uses, is waiting on you), the
new copy says **"your agent"**. When it names **where or whose** (a connection,
a folder, an account, a setting, a list), the new copy says **"command
center"**. New copy follows the same rule; a test cannot enforce the
judgement, so review does.

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

The table is applied at **every boundary that validates arguments**, not only at
MCP. Codex's refute found three such boundaries:

- **MCP.** A FastMCP `Middleware.on_call_tool`, the pattern already used at
  `engine_mcp_server.py:287` and `universe_server.py:3991`, rewrites a call's
  arguments before the tool's argument validation, on both servers. FastMCP
  3.2.0 runs middleware ahead of tool execution under its default validation
  setting. `strict_input_validation` must stay off, because it would add SDK
  validation upstream of middleware, and a test pins that it is off. The
  advertised schema carries only the new names, so aliases cost zero
  description bytes.
- **The owner door (HTTP).** `owner_door/routes.py:_validated` (`:61`) refuses
  unknown argument names, and the app's `Owner.read` posts to it
  (`app.html:1608`). It normalizes through the table **before** that check. The
  same applies to the other app JSON routes that take `universe_id` (e.g. Stop,
  `app.html:1852`).
- **Direct Python callers.** Python callers of a renamed function, for example
  `engine_mcp_server.py:725` calling the connector's
  `get_status(universe_id=...)`, are migrated in the same PR. They do not get
  an alias: a Python call can be changed and checked, so it needs no
  compatibility path. A test fails if any call site still passes a retired
  keyword to a renamed function.

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

### D4. Responses carry both key names during the window; the bridge keeps both permanently

*Revised after Codex's refute.* The first draft switched response keys
outright and relied on the app's stale-asset reload, which does not hold:

- the reload checks only every ten minutes (`app.html:7598`), waits while the
  person is typing (`:7613`), and can hold for up to three hours while a turn is
  in flight (`:7626`);
- already-loaded bridge code rejects a conversation or file response that has
  no `universe_id` (`app_ui.js:425`, `:541`, `:558`);
- `get_status` promises one release of deprecation notice before a field is
  renamed, and a `schema_version` bump for breaking changes
  (`universe_server.py:3923`).

So, during the alias window, every response that carries a renamed key carries
**both**: `command_center_id` and `universe_id` (and so on), holding the same
value from the same source. One authority, two spellings. `get_status` adds a
`deprecated_fields` note naming the old keys and keeps its `schema_version`; it
bumps the version only when the old keys are removed.

The old response keys are removed together with the input aliases (D3's 14-day
condition), in the same PR, which also bumps `schema_version`.

First-party readers switch to the new key in C1 and fall back to the old one:

- `app.html` and `app_ui.js`;
- the website read contract (`WebSite/shared/mcp/public-read-contract.js`);
- `scripts/mcp_tool_canary.py:241`, which the uptime workflow runs;
- the owner-door contract test (`tests/test_owner_door.py:329`).

Because the server keeps emitting the old keys, deploy order does not matter.

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

### D6. Code identifiers: renamed (C3), in one freeze window

*Decided by the founder, 2026-10-01: "rename them too". This replaces the
earlier recommendation not to.*

**Scope.** Every identifier, module, test name and env var that spells the old
word:

- 7,059 identifier occurrences and 323 distinct names;
- 12 `universe_*` modules (`universe_server.py` becomes
  `command_center_server.py`, and so on);
- about 17,000 test lines that import or monkeypatch them by module path;
- the `TINYASSETS_*UNIVERSE*` env vars.

The plugin id `tinyassets-universe-server` is renamed too, and the old id stays
in the marketplace as a forwarding entry for one release, because installed
copies update by id.

**Mechanics.**

1. A codemod (`scripts/rename_command_center.py`, written in C3) does the
   mechanical part. It renames identifiers with libcst, renames modules with
   `git mv`, and rewrites import strings and `monkeypatch.setattr("tinyassets.universe_...")`
   targets. It is deterministic, so running it twice is a no-op.
2. It writes a **non-mechanical report**: every site it refuses to touch, for a
   person to review. That covers strings that are machine values (SQL, JSON
   keys, stored identity, which belong to C4), `getattr` / `importlib` by
   string, and fiction-domain "universe" meaning a story world.
3. Env vars: the new name wins, and the old name is still read, with one
   deprecation log line, until C4's verification passes. Operators' compose
   files change in the same window (`compose-flags-inert-without-droplet-sync`).

**Freeze window.** The lead pauses the other lanes, the codemod runs on a fresh
`origin/main`, and the PR lands. Then the lead rebases the paused lanes, and the
same codemod run on each lane's branch does most of that rebase. The PR is
gated on:

- the full suite in the Linux oracle and in CI's merge group;
- the mirror rebuild (`build_plugin.py`);
- the channel-agnostic and vendor-neutral ratchets;
- the description budgets (D5);
- `cross-provider-drift`.

There are no compatibility shims for old module paths. Anything importing an
old path fails loudly, which is the point of doing it in one window.

**Persisted shapes stay put in C3** (refute #4). Renaming a Python name can
change what gets written. `BranchTask.universe_id` is serialized with `asdict`
and read back by filtering on the current fields (`branch_tasks.py:86`,
`:126`), so a plain rename would drop the old key on read and fail
construction. For every persisted field the codemod reports, meaning every
`asdict` / from-dict / TypedDict state key / JSON writer, C3 adds an explicit
serialization adapter: the code name changes, the **serialized** key stays
`universe_id`, and reads accept both. Graph state keys like `_universe_path`,
which SqliteSaver checkpoints hold, get the same treatment. C4 moves the
serialized keys later. Digest inputs are frozen: any hash over a dict
containing a renamed key keeps the literal old key name in its input, or bumps
a digest version that still verifies old digests.
`conversation_run_admissions.py:340` and `provider_assignment_manifest.py:153`
are the known cases; the codemod reports the rest.

**Launch paths are verified by running them**, not by an import test:

- `pyproject.toml` entry points (`:82`);
- `deploy/deploy_fail_safe.sh`'s pre-deploy gate, which imports
  `tinyassets.universe_server` (`:1220`);
- Dockerfile CMD, systemd units, the plugin's `plugin.json` / `.mcp.json`,
  and the mcpb manifest;
- multiprocessing spawn targets.

C3's gate builds the image, runs the deploy gate script, and starts each entry
point.

**Ordering.** C3 lands after C2 and before C4. C3 keeps every SQL string,
table, column, serialized key and on-disk name exactly as it is, so code and
storage change in separate, separately revertible steps.

### D7. Storage: migrated (C4), guarded, from a schema-derived inventory

*Decided by the founder, 2026-10-01: "rename them too". This replaces the
earlier recommendation not to. C4 gets its own change directory
(`migrate-storage-to-command-center`), because a migration is spec-first. This
section is the safety contract that change must meet.*

**What moves.**

- Tables: `universes` becomes `command_centers`, `universe_acl` becomes
  `command_center_acl`, and so on.
- Columns: `universe_id` becomes `command_center_id`; `queue_universe_id`,
  `sender_universe_id` and the rest follow.
- Marker files: `.universe_id` becomes `.command_center_id`,
  `.universe-tool-slots` becomes `.command-center-tool-slots`, and
  `.universe_seats.db` becomes `.command_center_seats.db`.
- The stored actor prefix: `universe:<id>` becomes `command_center:<id>`.
- The account-deletion key, `UNIVERSE_KEY`, follows the column.

**What does not move: the `u-` id prefix and the `u-<id>` directories.** `u-`
is not the word. It is part of an opaque id copied into hundreds of rows,
URLs, bind mounts and the `/u` jail mount, so renaming it would be an id
migration, not a name migration. The inventory lists these directories anyway,
so the decision is visible. This is the one item the founder confirms
(Open Questions).

**1. The inventory is derived, never hand-listed**
(`deletion-set-derived-from-schema`). `scripts/command_center_storage_inventory.py`
walks every data root a runtime can have. It reports, read-only:

- **SQLite**, in every file including per-home databases and satellites:
  - tables and columns whose name contains `universe`;
  - TEXT values `LIKE 'universe:%'` or equal to `'universe'`;
  - `CHECK` clauses and index, trigger and view SQL in `sqlite_master` that
    name either. For example, `workspace_pool.py:239` constrains
    `storage_class IN ('scratch','universe')` and `:264` constrains lock scope
    to `'universe','host'`.
- **LanceDB** table schemas (`retrieval/vector_store.py:123`: `universe_id`,
  `tag_universes`).
- **SqliteSaver checkpoints**: payloads decoded through the saver's serde,
  for state keys such as `_universe_path` (`fantasy_daemon/__main__.py:2208`).
- **JSON / JSONL files** under the data roots whose keys contain `universe`.
  For example, branch tasks are written at `branch_tasks.py:270`.
- **Marker files** and directories named `.universe*`.

That output is the migration's input. The migration rewrites what the
inventory finds, by rule:

- a table or column rename;
- a table rebuild, where a `CHECK` literal or a constrained value changes
  (SQLite cannot alter a CHECK);
- a value rewrite;
- a LanceDB schema rewrite;
- a serde-aware checkpoint rewrite;
- a JSON key rewrite.

A table nobody remembered is still migrated. A name or format the rule cannot
map stops the run before anything moves.

**Every runtime migrates its own data roots.** The same start-up migration code
runs in the production container, the desktop app and the local plugin
runtime, because those keep data outside the production volume:

- desktop homes default to `Documents/TinyAssets/default-universe`
  (`desktop/launcher.py:68`);
- the plugin opens a user-chosen root (`plugin.json:38`).

A production container migration cannot reach those installs, so each install
migrates itself the first time it runs a C4b build. The desktop's
user-visible default folder name changes only for **new** installs. An
existing folder is the person's own files: the launcher still finds it and
does not move it.

**2. A layout guard ships first, alone (C4a).** A new `data_dir()/.layout.json`
records `{"layout": 1, "state": "stable"}`, written if absent. Every image from
C4a on refuses to start unless it knows the layout **and** the state is
`stable`. It checks before opening any database, fails loudly and serves
nothing.

- **The crash window is closed** (refute #3). C4b writes
  `{"layout": 1, "state": "migrating"}` durably (fsync of the file and its
  directory) **before its first mutation**. A crash anywhere after that leaves
  a marker every C4a+ image refuses. Only a completed, verified run writes
  `{"layout": 2, "state": "stable"}`.
- **An image built for layout 1 cannot run on renamed data** (layout 2, or
  `migrating`). That is the deploy-rollback guard.
- **The automatic fail-safe is made migration-aware in C4a.**
  `deploy/deploy_fail_safe.sh` rolls back to the previous image on an
  unhealthy deploy (`:1356`, `:1383-1388`) without restoring data. Its stated
  contract is "startup migrations are backward-compatible" (`:91`), which C4b
  is not. C4a changes it: when the marker reads `migrating` or a layout newer
  than the previous image's, it does **not** start the previous image. It
  stops, reports `deploy_result=rollback_needs_restore`, and leaves the
  service down for the restore below. Serving nothing is the fail-safe; an old
  image on new data is not.
- **Images older than C4a cannot read the marker.** On renamed data they would
  see no `universes` table and could create a blank home. So C4b's
  pre-flight asserts with `deployed_sha.py` that the image the fail-safe would
  fall back to contains C4a. Release reconciliation deploys only main HEAD
  (`release-reconcile.yml:340`), which after C4a always contains the guard.
- C4a deploys and runs at least one full day before C4b, so the guard is the
  production baseline when the migration runs.

**3. One locked, idempotent, resumable migration (C4b).** It runs at container
start, before the server binds its port.

**Exclusion is a protocol, not an assumption** (refute #2). No single lock is
taken by every process today. Host jobs open databases directly: the backup
timer runs `deploy/backup.sh`, which opens databases at `:135`, and operator
scripts such as `scripts/universe_ownership_inventory.py:127` query directly.
So C4a puts each kind of process under exclusion:

- **In-container processes, including per-turn engine children,** take a
  shared lock on `data_dir()/.layout.lock`. The migration takes it
  exclusively.
- **Host jobs:** C4b's deploy step stops and disables the backup timer, and
  `backup.sh` takes the same lock file through the bind mount (`flock`).
- **Operator scripts** go through one helper that refuses unless the marker
  is `stable`.

A process that cannot get the lock waits or fails. It never reads half a
migration.

- **Per database:** one transaction holding all of that database's work:
  `ALTER TABLE ... RENAME TO` / `RENAME COLUMN`, rebuilds for changed `CHECK`
  literals, and value rewrites (`universe:` actor prefix, the stored
  `'universe'` enum values). A database is either all old or all new.
- **Progress record:** a dedicated `_command_center_layout` table per
  database. `PRAGMA user_version` is **not** used, because subsystems already
  own it for their own migrations (`storage/owner_devices.py:166`).
- **LanceDB, checkpoints and JSON files:** rewritten to a new file or table,
  then swapped atomically. The old copy is kept until verification passes.
- **Per file:** an atomic `os.replace`.
- **Progress:** recorded per database and file, so a crash resumes where it
  stopped. Every step checks whether it is already done (new name present, old
  absent), so a re-run is a no-op.
- **Finish:** the marker flips to layout 2 only after the post-migration
  verification passes.

**Readers accept both shapes until the migration is verified.** Within one
database there is no mixed state to read, because of the transaction. Across
databases, files and values, readers fall back:

- actor-prefix comparisons match `universe:` and `command_center:`;
- seat and slot files open the new name and fall back to the old;
- scripts and canaries reading storage accept either name.

These fallbacks come out in a cleanup PR once the 14-day verification holds.

**4. Deletion and export are proven against the migrated schema.** A test
builds a data dir with every real schema creator, migrates it, and then:

- **fails if any table or column still contains `universe`**, which guards
  against an unmigrated column;
- asserts `delete_account` removes every row of the deleted account and none
  of another's;
- asserts the operator reset (`scoped_reset`) does the same.

Export has no code path today: the `/account` page routes data-export requests
to the legal address, and they are answered by hand. C4b's runbook updates the
operator's export queries to the new names, and the dry run executes them
against the migrated copy. There is no export code to test.

The existing `tests/test_account_deletion.py` new-column guard moves to the
new key name.

**5. Dry run on a copy of production, never on production.**

- Take a consistent copy without touching the live service. Use SQLite's
  online backup API (`sqlite3 .backup`) per database, the LanceDB directory
  copied after a flush, and plain copies of the JSON and marker files. All of
  it is read-only on the droplet. **Not** `deploy/backup-restore.sh`, which
  *restores* (it stops consumers at `:282` and replaces the live volume at
  `:300`). And not `backup.sh`'s live tar, which tolerates files changing
  under it (`:164`).
- Copy it off the droplet, and run the migration in the Linux oracle container
  against the copy.
- The report gives, per database: row counts per table before and after (old
  name mapped to new name; they must match exactly), and actor-prefix counts
  (all moved, none left).
- Reader checks before and after: `get_status`, `read_graph` (status, graphs,
  runs) for every home, and the account-deletion refusal analysis for every
  account. The answers must be identical.
- The dry-run report is attached to the C4b PR. If any count or reader
  differs, C4b does not run.

**6. Backup and a written rollback.**

- **The backup is quiesced and consistent.** At the start of the window: stop
  the container and the backup timer, so nothing writes. Then take a full tar
  of the data volume with `deploy/backup.sh`'s full tier, run against the
  stopped volume, and record its timestamp and sha256. This is the **recovery
  point**.
- **Nothing is written after the recovery point until the migration has
  verified**, because the server binds its port only after verification. A
  rollback before the service reopens therefore loses nothing.
- **Rollback after the service has reopened loses data, and that is
  stated.** Restoring the snapshot discards every write since the recovery
  point: turns, runs, requests, uploads. It cannot undo external effects
  already performed, such as a sent message or an opened PR. So once the
  service has reopened, the default is to **roll forward** (fix and
  redeploy). Restore is chosen only when the migrated data is wrong, and the
  window's writes are then listed from the live database before the restore,
  so each affected person can be told.
- **Rollback steps:**
  1. Stop the container.
  2. Restore the snapshot with `deploy/backup-restore.sh`, its intended use.
  3. Deploy the image sha that ran before C4b (`deployed_sha.py` records it).
     That image is C4a or later, so it accepts the restored layout 1 / stable
     marker.
  4. Run the canary.
- The steps go in `docs/ops/` with exact commands, and are rehearsed once
  against the dry-run copy.

**7. A measured quiet window.** Every deploy interrupts in-flight turns. Turns
on production over the 14 days to 2026-10-01 17:00Z (read-only count of
`agent_turns.created_at`, by UTC hour):

| UTC hours | 17-21 | 22-03 | 04-16 |
|---|---|---|---|
| Turns/hour, 14 days total | 6-15 | 25-63 | 85-130 |

Proposed window: **18:00-20:00 UTC** (11:00-13:00 Pacific). It is re-measured
the day before, and the founder's own planned sessions are checked, because
the founder is the main live user.

### D6/D7 shared risk: two big steps on one surface

C3 and C4b each touch nearly every module. They are deliberately separate:
C3 changes code only, so it is revertible by a plain revert. C4b changes data
only, so it rolls back only by restore. Neither waits on the other's
deprecation window. C4b needs only C3's code to have run in production long
enough to be trusted.

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
updated) → C3 (code identifiers, one freeze window, D6) → C4a (the layout
guard ships alone, D7) → C4b (the storage migration in a measured quiet
window, D7) → alias and old-key removal with a `schema_version` bump, once the
14-day condition holds.

Rollback: C0 and C2 are text. C1 rolls back by reverting the PR. Because
responses carry both keys and inputs accept both names, a rollback leaves no
client unable to call or read. C3 rolls back by reverting the one PR before
C4b runs. C4b rolls back only by restore plus the previous image (D7), never by
a revert alone.

## Open Questions

- **The `u-` id prefix (D7).** It is kept. It is an opaque value, not the
  word, and renaming it is an id migration. The founder confirms this or asks
  for that migration separately.
