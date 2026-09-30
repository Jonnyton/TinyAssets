# Design: in-platform-agent-systems

## The floor this must hold

The only platform invariant is cross-user: nothing here may read or change
another user's universe, and nothing becomes public without its owner saying
yes to exactly that. Each part below is placed so that it cannot break this.

## 1. `universe_file` / `universe_files` (connector read targets)

- Arguments reuse existing `read_graph` parameters: `graph_id` names the
  universe, `query` is the path relative to `/u`, and `file_offset` /
  `file_max_bytes` page a file (at most 262,144 bytes per read, default
  65,536). No new parameter.
- **Who may read:** only a caller holding admin on that universe
  (`universe_access_error(..., write=False)` is not enough, because a public
  universe is readable by anyone and its files are not the same as its public
  face). Anyone else gets `not_found`, the same envelope an absent path gets,
  so the refusal does not reveal whether the universe exists.
- **Paths:** each component is checked with `universe_files._check_component`.
  Absolute paths, `..` and NUL bytes are refused. Listing one directory returns
  at most 500 entries (name, `file`/`dir`, size), sorted, with `truncated`.
- **Traversal is anchored to descriptors, not paths.** Production is Linux.
  The data directory is opened once, and the universe root is opened beneath
  it with `O_NOFOLLOW`, so a root that is itself a link is refused (the path
  is never resolved first; resolving strips the link). Every further
  component is opened with `openat(O_NOFOLLOW)` from the descriptor above it.
  A listing stats each entry through the directory's descriptor
  (`dir_fd=`, `follow_symlinks=False`), so swapping a directory for a link
  after it was opened changes nothing the read sees. Windows has no `openat`,
  so there a reparse point anywhere on the path, root included, refuses the
  read. Windows hosts are single-tenant trays, so the check-then-use race
  left there crosses no user.
- **Encoding:** UTF-8 text is returned as `text`. Anything else is returned as
  `base64`. `next_offset` / `eof` as `run_file`.
- **Bridge:** `listFiles(dir)` and `readFile(path, offset)`. `graph_id` is
  always the viewer's home. The reply is picked fields. The bundle can read
  everything its viewer can read in `/u`. That is the same residual already
  accepted for `readConversation`: the frame has no network, so what it reads
  it can only show or send back into the viewer's own universe.

## 2. `app_event` (automation event type)

- `EVENT_TYPES` gains `app_event`. `EVENT_FILTER_KEYS["app_event"] = {"name"}`
  and `EVENT_REQUIRED_FILTER_KEYS["app_event"] = {"name"}`, so there is no
  "any app event" subscription that a stray UI could drive.
- Emitted by connector `run_graph operation="emit_event"` with
  `inputs_json {"name": <[a-z0-9][a-z0-9_.-]{0,63}>, "data": <JSON object,
  <= 8192 bytes canonical>}` under `graph_id`. It calls
  `automation_events.emit` with the verified request principal. Everything
  cross-user is already there: a principal's event wakes only subscriptions
  that principal owns, in their own current home, and only when `graph_id` is
  that home.
- **Whose compute:** a wake runs in the universe of the principal who emitted
  it, on that universe's own serving provider. The bridge always emits as the
  VIEWER into the viewer's own home, so a UI spends only the compute of the
  person looking at it, who is that universe's owner. An author's UI installed
  by someone else spends the installer's compute on the installer's agents,
  and never the author's. No path wakes a universe the emitter does not own,
  so no one can spend another user's compute.
- **Compute:** wakes run on the owner's own compute, bounded by concurrent
  seats. Account limits are storage and concurrent seats; there are no rate meters.
- **Reply:** `{"emitted": true, "woke": <count>}`, never ids of anything, so a
  UI cannot probe which subscriptions exist beyond "some" versus "none".
- **Bridge:** `tinyassets.emit(name, data)`. At most one in flight per frame,
  like `sendMessage`. `data` is carried verbatim into `inputs.event.data`. It
  is authored by UI code, so agent guidance treats it as input, not as
  instructions from the owner.

## 3. `publish` pending-request action

### Ask (served agent, `write_graph target="pending_request" operation="ask"`)

```
{"type": "publish", "name": "...", "description": "...",
 "branch_ids": ["<own branch_def_id>", ...],   # >= 1
 "ui_id": "<id in the owner's app_ui library>",   # optional
 "automation_ids": ["<own automation id>", ...]}  # optional; each must drive a listed branch
```

Validated at ask time. Each branch must be authored by the asking owner and
live in this universe. The UI must exist in the owner's own `app_ui` row. Each
automation must be owned by the owner and must name a listed branch.

The platform then:

- builds the SNAPSHOT: the exact public payload, meaning every branch row as it
  is stored (every nested key, known to the model or not, apart from the
  volatile `visibility`, `published` and `updated_at`),
  plus the exact definition payload. That definition holds the UI's seven
  portable fields, a branch-ref per workflow naming the version id its
  snapshot will mint, and an automation-spec per trigger. It runs the
  definition scanner over ALL of it (branch rows included) and the
  definition's own validation, then pins `snapshot_digest`, the sha256 of
  the canonical serialization. The digest covers the published bytes
  themselves, so no field list can miss a field (astra rounds 1 and 2 each
  found one);
- REPLACES `title`/`body` with text it generates from the action: the public
  name and description, each workflow's name and node count, the UI's name,
  each trigger in words, and one fixed sentence: *"Anyone will be able to read
  and copy these. A copy runs in the copier's own universe on their own
  compute and never reaches yours. Publishing does not share your
  conversations, files, credentials or automation inputs."*

The agent cannot phrase the consent. The ask carries no fields.
`displayed_row_matches` already binds the executed action to the rendered
tab.

### Answer (person's surface only: app rail, connector `answer_request`)

1. Rebuild the snapshot from the live rows. Its digest must equal
   `snapshot_digest`, or the ask is refused with `request_pending: true` and
   "this changed after you were shown it; ask again". Every content check
   and the definition's validation run here, before anything is written.
2. Mint each version unmarked from its row as it will be flipped. Only its
   author can read it, even if the branch later becomes public.
3. The commit point: ONE `BEGIN IMMEDIATE` re-reads every branch row, refuses
   unless each still equals the snapshot, and flips them all public, or none.
4. Mark exactly the confirmed versions public, then publish the pre-validated definition (`publish_agent`, idempotency key
   derived from `request_id`). The only failure left here is storage, and it
   unmarks those versions and flips the branches back, so nothing is left public.
5. Resolve the request `answered`/`allowed` and return the definition id and
   version ids.

Why not one transaction across all of it: branch rows, versions and
definitions live in three SQLite files in WAL mode, and a transaction over
attached WAL databases is not atomic as a set. So the order does the work:
invisible writes first, a single atomic commit point, then one pre-validated
write that is compensated if storage fails.

Deny, Clear and a served turn publish nothing. The served surface has no
`answer_request`. That is the existing rule for every action-bearing ask: an
agent that could answer its own ask could consent for its owner.

### Versions carry their own publication mark (founder, 2026-09-30)

`patch_branch` snapshots every edit, so most of a branch's versions are private
edit history. Round 3 showed that publishing a branch exposed all of it,
including a credential the owner had since removed. Each version now has a
`public` mark:
- Anyone but the branch's author reads a version only when its branch is
  readable AND the version is marked.
- `publish_branch_version(public=True)` sets the mark. That also covers an
  identical snapshot returned from history.
- The mark is set only by the explicit connector `publish_version`, by this
  ask's accept (after the flip), and by the platform's default selector.
- Migration: existing rows are marked except `patch_branch`'s own snapshots,
  which are the one minter whose notes say so.
- Listings for non-authors show only marked versions. The commons'
  "published" scope means "has a marked version".

The snapshot also pins `stats` and `version`. Only `visibility`, `published`
and `updated_at` are exempt, because a public read returns both of the others.

### What the owner's branch being public means

This is the existing commons model: a public branch is a readable, copyable
shape. Later edits to that branch are also readable, and a new version needs a
new publish. The tab says the workflows become public, not "a snapshot of
them".

## 4. Install (no new primitive)

A second user's universe runs `read_commons_shape agent_definition_id=...`.
Each `branch-ref` goes to `remix_shape`, which makes a new PRIVATE branch
owned by the installer. The `ui` component is saved into the installer's own
`app_ui` library (private, runs against the installer's bridge). Each
`automation-spec` becomes `write_graph target="automation" operation="create"`
against the installer's copy. The author's universe is never addressed: a
branch-ref names a published version (read-only), and a UI's bridge pins to
its viewer's home. A UI should find its agents by automation or branch NAME
(`listAutomations`), because ids differ per copy. The `interfaces` and
`systems` chapters say so.

## Rejected alternatives

- **Let the bundle run any of the viewer's branches** (`run_graph` from the
  bridge). A shared UI could then start any agent the owner has. With
  `app_event`, the owner, or their universe, decides which agents a UI may
  wake, by name.
- **Let the served agent publish directly with a consent flag in the call.**
  The agent runs as the owner, so any flag it can set, it can set without
  asking. Consent has to be an answer on a surface the person drives.
- **Snapshot-only publishing** (publish a version while keeping the branch
  private). Readability of a version follows its branch today
  (`_resolve_readable_version`). Changing that is a commons-model change, out
  of scope.
