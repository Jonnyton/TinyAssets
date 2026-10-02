# Design: command-center-cutover

The safety contract is in `rename-universe-to-command-center/design.md`: D6
(code), D7.1-D7.7 (storage), D10 (one cutover), D11 (`cc-` ids). This file
covers execution: order, tooling, the freeze window, and the evidence each
step must produce.

## E1. Read-only first: the inventory is a deliverable

`scripts/command_center_inventory.py` runs read-only against a data root and
prints a machine-readable report:

- every SQLite table, column, `CHECK` / index / trigger / view clause, and TEXT
  or BLOB value naming `universe` or holding a `u-<ulid>`, decoded per
  encoding (D7.1, D11);
- LanceDB schemas, checkpoint payloads (via serde), JSON keys and values, and
  marker files and folders;
- derived identities: length-prefixed lease keys, hashed connection and grant
  ids, content digests over records that contain an id;
- the exempt verbatim stores (uploads, run outputs, conversation text, brain
  files), listed by name so the scan's skips are explicit.

Run it first on a production copy. Its counts are what the migration must
bring to zero, and what the dry run compares.

## E2. The migration is code with its own tests before it ever runs

`tinyassets/command_center_migration.py` runs phases 1-5 under the exclusive
`.layout.lock` that C4a introduced:

- it writes `{"layout": 1, "state": "migrating"}` before its first change;
- it makes one transaction per database and keeps a per-database progress
  table;
- every step is idempotent and resumable.

It is tested against fixture data roots built by every real schema creator.
Those tests cover crash and resume at every phase boundary, digest and
reference integrity, decoded round trips, independent deletion and export
counts, and a test that fails on any surviving operational old name or id.

## E3. Order of work

1. The inventory script, then a production-copy report attached to the PR.
2. The codemod: deterministic, plus its report of non-mechanical sites.
3. The migration module and its tests.
4. A dry run on a consistent production copy (SQLite online backup, never
   `backup-restore.sh`). The row-count and reader report is attached.
5. The rollback runbook in `docs/ops/`, rehearsed on the dry-run copy.
6. The freeze window, in the measured quiet window (18:00-20:00 UTC,
   re-measured the day before):
   - the lead pauses the other lanes;
   - stop the backup timer, take the quiesced backup and record its sha256;
   - deploy;
   - the migration runs and verifies before the port binds;
   - external phase;
   - reopen;
   - canary (`--assert-handles`) and `deployed_sha.py`;
   - rebase the lanes with the codemod.

## E4. What blocks the window

Any of these stops the cutover:

- an inventory category the migration does not handle;
- a dry-run count or reader mismatch;
- an unrehearsed rollback;
- C4a not in production for at least a day;
- a WorkOS record holding an id that the live check finds.

## E5. Ids are never shown to people (founder, 2026-10-02)

*"keep the cc prefix, never show ids to users."* `cc-<ulid>` is the single id
form after the cutover. It is a machine value only.

**Covered surfaces:** the app (`app.html`, `app_ui.js`), the website, push and
in-app notification text, and served agent guidance about how to refer to the
command center. None of them renders an id. They show the command center's
name, falling back to **"Your command center"**.

**Guard test:** `tests/test_ids_never_shown.py`. It drives the app's render
paths with a home whose id is `cc-<ulid>` and fails if the id appears in
visible text. It also checks two more things:
- notification titles and bodies, through `owner_notifications`;
- served descriptions and instructions, which must never instruct the agent to
  speak or show an id.

It lands with or after notify-prompt's app-header fix, which removes the one
known place the raw id shows today.

## E6. The target on-disk layout: storage moves once

*Agreed with openshell-spike on 2026-10-02 and written as the shared text in
`target-architecture` design §"Target on-disk layout (agreed with
command-center-cutover)" (#4263). The founder's rule: "do things correct the
first time". This cutover moves storage straight into the target layout, so
the later sealed-box slice is an image build, not a second data migration.*

**One rule decides every item.** Anything the daemon *trusts* (authority,
identity, owner settings, records) is **platform** state. Anything the person
or their agent may write is **user content**, which the daemon treats as
untrusted.

Under `data_dir()`:

| Path | Holds | Mounted into the jail/box |
|---|---|---|
| `cc-<ulid>/` | User content: brain files (identity, founder, origin, body, orgchart, projects, goals, index, log, voice, `AGENTS.md`), harness dirs (skills, prompts, extensions, workflows, bin, notes, wiki), upload bytes (verbatim, Hard Rule 9), run output files, permanent workspaces, anything the agent creates | Yes. It is the future box volume (`/cc`) |
| `.platform/cc-<ulid>/` | Per-command-center platform state: the credential vault and file-OAuth CLI credentials (`.credentials/`); the per-home DBs (runs, consent, usage, attention, conversation custody and journals, checkpoints, `outbound.db`, `knowledge.db`, `story.db`, `lancedb`); rules, auto-review, activity, pending effects, proposals, import quarantine, browser profile; the `.command_center_id` marker, lease/seat/slot/lock/stamp files, worker-supervisor state and the egress proxy socket (today's `.universe-sidecars/<id>/` folds in here); upload custody records; and the owner-door files `soul.md` and `config.yaml` | Never. The agent gets a read-only projection of `soul.md` and `config.yaml`, refreshed at wake and never read back |
| `.platform/accounts/<account_id>/` | Per-account platform state: storage allocation ledger, compute-hour meter, seats. Created empty by the cutover | Never |
| root DBs (`.tinyassets.db`, `.runs.db`, `.langgraph_runs.db`, ...) | Unchanged location; tables and columns renamed (D7) | Never |

**Answers that set the split:**

- **Permanent workspaces** are user content.
- **Conversation history** is platform state; the agent sees it only through
  read-only projections.
- **Run output files** are user content, while run records, receipts and
  checkpoints are platform state.

**One resolver** builds every path: `command_center_dir(id)`,
`platform_dir(id)` and `account_platform_dir(account_id)`. A test fails on
any hand-built path (D11).

**What this adds to the migration.** Phase 1 (names) also *moves* each item
to its target place. The move is a same-filesystem rename, made atomic per
item, with progress recorded. The inventory (E1) classifies every entry of
every home into one of the four rows above. An entry it cannot classify stops
the run, so nothing is guessed into the box.

Once this lands, target-architecture's S2 ("platform state out of the home
dir") is delivered by this cutover.
