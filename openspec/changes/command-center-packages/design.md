# Design: share a whole command center as one package

Builds on `universe-agent-harness` §4.15 (manifest, quarantine, activation),
§4.16 (platform state out of agent reach) and §4.17 (one manifest, profiles,
scrub, ingestion boundary), and on the `publish` ask from
`in-platform-agent-systems`. Only the delta is written here.

## D1. One manifest, three profiles

`command-center.json` gains a third `profile` value: `publish`. It is the same
manifest the D11 export writes (`format_version`, `profile`, `agents`, `files`,
`workflows`, `ui`, `automations`, `needs`), so the manifest is built once
(`tinyassets/command_center_packages.py`) and the export reuses it.

| Profile | What | Where it goes | Size limit |
|---|---|---|---|
| `share` | harness subset | the public definition | 256 KiB |
| `export` | the whole folder | private local output | none |
| `publish` | the whole folder minus the private items | a public package blob | the publisher's storage quota |

## D2. What a `publish` package contains

The command-center folder is walked without following links, through the
universe-file readers.

**Never included, even when named:**
- every entry whose name starts with `.` at any depth: platform and runtime
  state, credentials, session files, `.env`;
- `workspaces/`, the managed repository checkouts;
- platform-written runtime files such as `activity.log`, `status.json`,
  `ledger.json` and any SQLite database;
- the brain files that describe the owner or hold the control plane:
  `founder.md`, `soul.md`, `soul.edit.md`, `soul_versions/` and `log.md`;
- the wiki's `drafts/`, `raw/` and `daemon-wiki/`;
- any file in which the platform's credential parser
  (`tinyassets.credential_shape`) detects a credential;
- any file carrying contact details (an email address or a phone number). The
  `export` profile alone may include those item by item;
- any file that is not UTF-8 text. A binary cannot be inspected, so the public
  profile never carries one;
- any file whose PATH carries a credential or contact details.

**Included by default**, because the founder asked for the whole command
center: harness files (`AGENTS.md`, `identity.md`, `settings.yaml`, `skills/`,
`extensions/`, `agents/<id>/`), workspace files and `wiki/pages/`.
- The owner can leave out any path or folder (`exclude`).
- Every `MEMORY.md` (the root one and each `agents/<id>/MEMORY.md`) is left out
  unless the owner names items as `<path>#<id>` (`memory_items`; a bare id means
  the root file). That file then carries only those bullets.

**One final-output check.** After assembly, the whole public output (every
path, the manifest, and the definition with its name, description and
components) is scanned once more with the credential parser and the contact
detector. A hit anywhere refuses the publish and names where.

**Connections** become named references. `needs.connections` in the manifest
lists the connection names that the published workflows refer to. The package
carries no `.env.example`, because the ingestion boundary admits no dot file.
The D11 export writes one locally from `needs`. `needs.model` is the `model`
from `settings.yaml`, when one is set.

The tab says plainly that detection cannot prove a file is free of personal
data. It lists every included file, and every excluded file with its reason.

## D3. Storage: a blob, an index, one listing

- **Blob.** A canonical JSON document `{format_version, manifest, files: {path:
  base64}}`, stored at `.command-center-packages/blobs/<sha256>.json` in the
  data root, outside every universe folder (§4.16). It is written once,
  atomically, and never modified.
- **Index.** `.command-center-packages/packages.db` has two tables:
  - `blobs`: one row per (author, sha256), recorded before the blob is written.
    The `packages` store measures this table, so a blob that a failed publish
    left unlisted is still charged to its author. Identical content is charged
    once per author.
  - `package_versions`: one row per listed version, with its definition id.
- **Listing.** The `publish` ask's one definition gains the tag
  `tinyassets.command-center-package.v1` and a `package` component (kind
  `tinyassets.package.v1`). The component carries `format_version`, `version`,
  `blob_sha256`, `size_bytes`, `file_count`, `agents` and `needs`.
  - Definitions are already immutable. A republish under the same name by the
    same author is the next `version`.
  - `browse_commons kind="packages"` filters definitions by the tag.
- **Quota.** The blob's bytes are admitted against the publisher's account
  through `storage_accounting.admitted(... store="packages")` before it is
  written. Over the quota, nothing is published, and the refusal names the
  package's size and the quota's numbers.

## D4. Publish: the existing ask, one more block

`publish` accepts an optional `package` block:
`{exclude: [path], include: [path], memory_items: [id], agent: <agent_id>}`.
- `build_snapshot` builds the package as well. The digest covers the branch
  rows, the definition (including its version number, allocated at ask time)
  and the blob's sha256.
- **The consent record is platform-owned.** The ask writes a pin to
  `packages.db`, keyed by (universe, request). The pin holds the action, the
  digest, the agent, and the tab's kind, title and body. This applies to every
  `publish` ask, not only to packages.
  - The rail renders a publish or install row's title and body from the pin,
    so an agent that rewrites the row in its own folder changes nothing the
    owner sees.
  - The answer executes the pin's action, not the row's.
  - A row with no pin cannot be confirmed.
- `execute_action` records and writes the blob, quota-gated, before flipping
  anything public. A retry of a confirmed request finds the pin `activated`
  and returns its receipt.

## D5. Install: quarantine, preview, activation

A new pending-request action, `install`:
`{agent_definition_id, agent: <agent_id>}`.

**Ask (served agent).**
1. The platform reads the definition. It must carry the package tag.
2. It loads the blob from platform storage and verifies its sha256.
3. It runs the ingestion boundary (§4.17):
   - bounds on bytes, file count, path depth and path length;
   - absolute paths, traversal, backslashes, NUL, empty and dot components,
     and dot-prefixed names are rejected;
   - case and Unicode (NFC, casefolded) collisions are rejected;
   - only regular-file payloads are accepted (base64 text).
4. It writes a **quarantine record** in `.command-center-packages/quarantine/`,
   keyed by (universe, agent, request). The record holds the digest and the
   planned destination of every file. That includes which destinations already
   exist in the installer's command center: those are kept as they are and
   named.
5. The tab is the platform's words: name, author, version, size, what it
   needs, what lands where, and what stays the installer's. It states that
   everything runs as the installer, on their own connections, and that the
   automations arrive paused.

**Answer (person surface only).** The platform:
1. reads the quarantine record for this request and this universe;
2. re-verifies the blob;
3. recomputes the destination plan. If it differs from the pinned plan,
   nothing is materialised and the owner is asked to ask again;
4. claims the record atomically (`pinned` to `activating`);
5. reserves the installer's `universe_files` bytes before any effect;
6. materialises the package, recording each component's new id in the record
   as it goes:
   - remix each branch-ref into a private branch owned by the installer, under
     its published name. The snapshot's skills are passed explicitly, so
     nothing falls back to the source branch's live skills. The model policy
     is cleared, so the copy uses the installer's own model;
   - add the UI to the installer's library, under a fresh `ui_id` if theirs is
     taken;
   - create each automation against the copy its spec names. It is created
     paused in the same insert, so it is never runnable before the owner
     resumes it;
   - write the files;
7. marks the record `activated`, with the receipt.

A retry of an `activated` record returns the receipt. A retry of an
`activating` record resumes, skipping the components already recorded. A
failure releases the claim and leaves the ask pending.

**Where files land.** Harness files at the package root (`AGENTS.md`,
`identity.md`, `MEMORY.md`, `settings.yaml`, `skills/`, `extensions/`,
`prompts/`) go to `agents/<slug>/`. The package's `agents/<id>/` go to
`agents/<slug>-<id>/`. This is the §4.14 roster layout, so the installer's own
main agent is never overwritten. Workspace files and `wiki/pages/` land at
their own relative paths, because the UI and the workflows address them by
path. A path that already exists is kept as the installer's own.
- The destination map is checked after relocation for case and Unicode
  collisions, and for a file that would sit where a folder must.
- Every file is created `O_EXCL | O_NOFOLLOW`, beneath directories opened one
  component at a time without following links. A link that the installer's own
  agent plants between preview and confirmation refuses the write; it never
  redirects it.

**References stay by name.** A UI finds its workflows and automations by name
(served `interfaces` chapter), so the copies keep their published names. An
automation's `event_filter.branch_def_id`, which names a workflow key, maps to
the installer's copy. The tab lists each needed connection and whether the
installer already has one by that name.

**Floor.**
- Nothing in the package carries the publisher's credentials, private data or
  any write path back to them.
- Workflow copies are private remixes authored by the installer.
- Automations are owned by the installer and run as them.
- The quarantine and activation records live outside every agent-reachable
  location.

The served agent may read the preview: the ask's own return value, wrapped as
untrusted content. It cannot answer the ask.

**What this MVP installs.** It installs command centers built the way the
served guidance builds them: workflows with agent nodes, automations, a UI and
shared files. That is the GTM Village's shape. Harness files land as files;
the runtime for a roster agent is D8.

## Out of scope for this slice

- Rules suggestions (`rules.json`). They activate "as written or stricter" and
  need the D1 rules store's import path.
- The roster runtime for `agents/<slug>/`. Until D8 these are files the
  installer's agents can read and adopt.
- Converting the wiki to OKF. The package carries `wiki/pages/` verbatim so the
  copy round-trips. The OKF conversion belongs to the export (D11).
- Unpublishing and sweeping orphan blobs.
- Binaries in a public package.

## Review log

- **gpt-6-astra design refute, round 1 (2026-10-01): ADAPT.** Ten findings.
  Adopted:
  - 2: one final-output check, paths included; memory scoped per file; no
    binaries.
  - 3: the rail renders publish and install rows from the platform pin.
  - 4: the destination map is validated after relocation; the writer refuses
    links; the plan is re-checked at commit.
  - 5: the remix passes the snapshot's skills and clears the model policy. The
    cross-author live-skills fallback is also closed in `branches.py`.
  - 6: a claimed, resumable activation; automations are created paused.
  - 7: names are preserved, the event-filter workflow key is mapped, and
    connection needs are previewed.
  - 8: blob ownership is recorded before the write; the version is pinned at
    ask time.
  - 9: no dot file in the package.
  - 10: the MVP is scoped to the shape the guidance builds.

  Kept, with the reason:
  - 1: workspace files and wiki pages are included by default. The founder's
    direction (2026-10-02, relayed by the lead) defines the `publish` profile
    as "the export layout minus the private items". The tab lists every
    included file, the owner confirms that list, and the tab states the
    detection limit. The lead holds this tradeoff for the founder.
