---
title: Wiki known-issues convention (chatbot auto-log)
date: 2026-04-19
author: navigator
status: superseded
status_detail: EXPLORATORY / SUPERSEDED — do not implement
superseded_by: docs/design-notes/2026-04-20-wiki-bug-reports-convention.md
---

# Wiki known-issues convention — EXPLORATORY / SUPERSEDED

**Do not implement this design.** This note captured a verbatim
reading of the spec the user ratified with their chatbot on
2026-04-19: a single `known-issues` page in the `references` category.
Team-lead reviewed the trade-offs on 2026-04-20 and approved the
alternative design (per-file `BUG-NNN-slug.md` + top-level `bugs/`
category + dedicated `file_bug` verb) on engineering grounds —
scalability, lint separation, clean API surface. The user ratified the
*principle* (auto-file friction-free); substrate-team picks the
implementation.

**See `docs/design-notes/2026-04-20-wiki-bug-reports-convention.md`
for the canonical design to implement.** This file is preserved for
history so the exploration trail isn't lost, and because the seed-entry
template bodies below can still be useful reference — the 2026-04-20
seed-entries artifact re-uses them verbatim against the per-file
schema.

## Ratified spec (verbatim)

### Location — single page, not a folder

One top-level wiki page: **`known-issues`**, in the existing
`references` category. Lives at `pages/references/known-issues.md`.

Named unmissably so every `wiki list` surfaces it at the top of the
references block. No new category, no nested folder — lowest-friction
adoption path.

### Index header link

Add at the top of `wiki/index.md`, unmissable for any chatbot that
orients via index-first:

> 🐛 **Bug? Log it in [[known-issues]] before working around it.**

### Per-entry template (use verbatim)

Each bug is an H2 section inside the one page:

```
## [BUG-NNN] <short title>
- **Surface:** <tool / action / env>
- **Severity:** low / medium / high / blocker
- **Status:** open / workaround-known / fixed-in-version / wontfix
- **Repro:** <minimal steps>
- **Observed:** <what happens>
- **Expected:** <what should happen>
- **Workaround:** <if any>
- **First seen:** <date + session context>
- **Related:** <other BUG-NNN or wiki pages>
```

### Schema meta-note (the forcing function)

Include at the top of `known-issues.md`, right under the page title:

> **When any tool returns a malformed result, silent corruption, or
> mismatched schema, log a new entry in `known-issues` using the
> template. Do this even if you work around the issue — the log is the
> forcing function.**

### Two seed entries to land on day one

- **BUG-001** — `changes_json` `input_keys` / `output_keys` silent
  character-split (Task #1 in the task system). Surface:
  `extensions action=patch_branch`, also `add_node`. Severity: high.
  Status: open.
- **BUG-002** — `WIKI_PATH` Windows-on-Linux `/app/C:\...` prefix
  leak (Task #2). Surface: `wiki` tool in container, `workflow.storage.wiki_path()`.
  Severity: high. Status: open.

### control_station prompt addition

One line routing TinyAssets-connector chatbots to `known-issues` when any
tool response looks malformed, and to file new entries via `wiki_write`
using the template (draft wording in §Refinement 3 below).

## Sequencing

Blocked by Task #2 (wiki path fix). Can't write to the wiki in-container
until the Windows-path leak is resolved. Once Task #2 is green in
whatever environment hosts the wiki, dev lands in one pass:

1. Create `pages/references/known-issues.md` with the meta-note +
   template reference + both seed entries.
2. Prepend the 🐛 line to `pages/index.md` (or `wiki/index.md`
   equivalent — confirm path during landing).
3. Add the control_station prompt line.
4. Append a line to `wiki/log.md` recording the initial landing.
5. Update Task #1 and Task #2 descriptions with
   `wiki:known-issues#BUG-001` / `#BUG-002` back-references.

No code changes to `_WIKI_CATEGORIES`, no new tool actions, no
schema-level surgery. The page is a normal `references`-category page;
existing `wiki action=write category=references filename=known-issues`
writes to `drafts/references/` and a subsequent `wiki action=promote`
lands it in `pages/references/`. For the initial landing of BOTH seed
entries + meta-note, dev may write the promoted file directly (the
draft-gate's purpose is stopping incremental junk; a fully-formed
initial page is its target end-state).

## Refinements flagged (narrow — do not block landing)

### 1. BUG-NNN numbering authority

The template uses `BUG-NNN` identifiers. With a single-page schema,
allocation is cheap: next-available integer = `max(existing BUG-NNN in
the page) + 1`. The first chatbot filing a new bug after BUG-002 picks
BUG-003 by scanning the page. Zero-padded to three digits (`BUG-003`
not `BUG-3`) for clean sorting and stable length.

Collision risk: two chatbots filing concurrently could both claim
BUG-003. Acceptable for now — `wiki_write` to a `references` page is an
overwrite-with-last-writer-wins, so the collision shows up as a
promoted-page diff in git (or obsidian sync) and host resolves. If
volume grows, a follow-up could add an allocator helper. Not blocking.

### 2. Cross-universe scope vs per-project

The spec puts `known-issues` at the wiki root (cross-project). This
matches the wiki's cross-project nature — bugs in `universe-server`,
`wiki-mcp`, `tray`, the `claude-chat` skill, etc. all co-locate on one
page. The `Surface:` field names which subsystem is affected.

Per-project bug pages (`pages/projects/<project>/known-issues.md`)
were considered and rejected: discoverability drops (chatbot would have
to know the project name first), and most users of the connector won't
know our internal project split. Single-page cross-project is correct.

Future pressure point: if one page grows past ~30 entries, split by
moving `status=fixed-in-version` + `status=wontfix` archived entries
to `pages/references/known-issues-archive.md`. Not needed for launch.

### 3. control_station prompt — paste-ready wording (<100 words)

Insert after rule 10 (degraded-mode) in `_CONTROL_STATION_PROMPT`:

> **11. Log server defects to the wiki.** When any tool returns a
> malformed result, silent corruption, schema mismatch, or obvious
> misbehavior, read `wiki page=known-issues`. If the bug isn't already
> there, append a new entry using the template on that page via
> `wiki action=write category=references filename=known-issues`.
> Include the exact tool call, observed output, and expected output.
> Log it even if you also apply a workaround — the log is how the host
> fixes the bug. User-caused errors (invalid args, missing universe)
> are not bugs; don't log those.

Word count: 96. Composes with rule 10 (STOP on tool failure): rule 10
handles "tool unreachable", rule 11 handles "tool returned nonsense".
For subtler bugs (malformed-but-usable output), only rule 11 fires —
chatbot logs + applies workaround + continues.

### 4. "fixed-in-version" format

The template's `Status: fixed-in-version` suggests a version string.
TinyAssets has no formal version numbers yet (git-commit-per-release
model). Propose: use short commit SHA in that slot, e.g.
`fixed-in-version: 5b2a282`. Human-friendly + links directly to the
fix commit. If/when TinyAssets gains semver releases, the same slot can
hold a version tag (`v0.4.0`). Zero-cost forward compatibility.

### 5. `reported_by` is not in the template — fine

The template omits "who reported this" as a field. `First seen:`
carries the date + session context (implicitly: "a chatbot in session
X" or "host on 2026-04-19"). Not a gap — adding `reported_by` invites
noise (every field is a maintenance burden per entry). Leave the
template exactly as ratified.

### 6. Related field — interlink discipline

`Related:` can hold both `BUG-NNN` cross-refs and wiki-page links
(`[[workflow-engine]]`, etc.). Treat it as freeform markdown. When a
bug supersedes another or duplicates one, use the `Related:` field to
state the relationship in prose (`"duplicate of BUG-001"`,
`"blocks BUG-007"`). Avoids adding dedicated `duplicate_of` /
`blocks` fields that would bloat the schema.

### 7. Legal `Surface:` values

Chatbots need a stable vocabulary so `Surface:` values aggregate
cleanly across entries. Propose: `<tool>.<action>` for MCP-tool bugs,
bare subsystem name for everything else. Enumeration:

**MCP tool surfaces** (five coarse tools on the TinyAssets MCP server,
plus the stdio shim — confirmed against `tinyassets/universe_server.py`
@mcp.tool definitions):

- `universe.<action>` — e.g. `universe.inspect`, `universe.add_canon_from_path`,
  `universe.submit_request`. One per action in the `universe` dispatch table.
- `extensions.<action>` — e.g. `extensions.build_branch`,
  `extensions.patch_branch`, `extensions.run_branch`, `extensions.add_node`.
- `goals.<action>` — e.g. `goals.search`, `goals.leaderboard`,
  `goals.common_nodes`.
- `gates.<action>` — outcome-gate actions (when `GATES_ENABLED`).
- `wiki.<action>` — e.g. `wiki.write`, `wiki.promote`, `wiki.search`.
- `get_status`, `get_progress` — bare tool names (single-purpose tools).

**Non-MCP surfaces:**

- `tray` — Windows tray app / `tab_watchdog.py`.
- `daemon` — background daemon (`workflow.daemon_server`, domain engines).
- `deploy` — Docker / compose / cloudflared infrastructure.
- `storage` — `tinyassets/storage/` resolvers and backends.
- `skills/<skill-name>` — `.claude/skills/` or `.agents/skills/` skill defects.
- `wiki-mcp` — separate `wiki-mcp/server.js` bridge (distinct from `wiki.*`).
- `user-sim` — user-simulator teammate / `claude_chat.py` skill.

Dev should NOT block landing on enumeration completeness — chatbots
filing against an un-enumerated surface just write a plausible string
(e.g. `ledger`), and the host updates this list when it appears. The
list is a guideline, not an allowlist. Not worth enforcing via lint.

## Paste-ready seed entries

These are the exact markdown dev should drop into
`pages/references/known-issues.md` beneath the meta-note. Both pulled
from the user chat on 2026-04-19 and the landed Task #1 / Task #2
descriptions. No re-derivation needed.

```markdown
## [BUG-001] changes_json input_keys/output_keys silently char-split when given a string

- **Surface:** extensions.patch_branch, extensions.add_node
- **Severity:** high
- **Status:** open
- **Repro:** Call `extensions action=patch_branch` with a
  `changes_json` op that sets `input_keys` or `output_keys` to a bare
  string (e.g. `"node.output"`) instead of a JSON array. Example op:
  `{"op": "update_node", "node_id": "x", "input_keys": "node.output"}`.
- **Observed:** Server accepts the string, coerces via `list(...)`,
  and stores `input_keys = ['n', 'o', 'd', 'e', '.', 'o', 'u', 't',
  'p', 'u', 't']`. Node validates as "fine" at edit time but is
  unrunnable at runtime. Same issue at the `add_node` code path
  (`_split_csv` is inconsistent with `patch_branch`).
- **Expected:** Reject non-list values with a clear error, OR
  parse intelligently (`json.loads` → fall back to CSV split → assert
  all entries are non-empty strings). Unified behavior across
  `patch_branch` and `add_node`.
- **Workaround:** Always pass `input_keys` / `output_keys` as JSON
  arrays (`["node.output"]`). Never a bare string.
- **First seen:** 2026-04-19, user chat while patching the
  `research_paper_7node` v2 workflow. Source:
  `tinyassets/universe_server.py:5404-5407` (patch path) and
  `tinyassets/universe_server.py:4160-4161` (add_node path). Mirror
  defect in `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/universe_server.py`.
- **Related:** Task #1 in the task system; dev fix in flight.
```

```markdown
## [BUG-002] WIKI_PATH Windows-style value leaks into Linux container as /app/C:\...

- **Surface:** wiki.read, wiki.write, wiki.list (all wiki actions in
  container); storage.wiki_path()
- **Severity:** high
- **Status:** open
- **Repro:** Deploy the TinyAssets MCP server in Docker with
  `TINYASSETS_WIKI_PATH=C:\Users\Jonathan\Projects\Wiki` (or legacy
  `WIKI_PATH`) inherited from a Windows host's env. Call any `wiki`
  action inside the container.
- **Observed:** Server replies
  `"Wiki not found at /app/C:\Users\Jonathan\Projects\Wiki"`. Linux
  `Path("/app") / "C:\\Users\\..."` treats the Windows absolute path
  as relative (no drive-letter detection), so `/app` prefixes the
  Windows path instead of replacing it.
- **Expected:** Per hard-rule #8 (fail loudly), the resolver should
  detect a Windows-style path on a Linux runtime and either reject
  with a clear error
  (`"TINYASSETS_WIKI_PATH=... is a Windows path but we're on Linux — refusing"`)
  or fall back to `$TINYASSETS_DATA_DIR/wiki` with a loud warning. Silent
  join is the failure mode.
- **Workaround:** Set `TINYASSETS_WIKI_PATH=/data/wiki` (or another
  Linux-native absolute path) explicitly in the container's environment
  overrides. Do not inherit the host-machine value.
- **First seen:** 2026-04-19, user chat while probing in-container
  wiki access. Source: `tinyassets/storage/__init__.py` (the `wiki_path`
  resolver landed in commit 5b2a282 but does not detect cross-OS
  path leakage). Mirror in
  `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/storage/__init__.py`.
- **Related:** Task #2 in the task system; blocks landing of this
  `known-issues` page itself.
```

## Non-goals

- Migration of existing design-note-tracked bugs into the page.
  `known-issues` is a forward-looking log; retro-filing is manual and
  optional.
- GitHub-issue bridging. Possible follow-up that syncs
  `status=open` entries into GitHub issues.
- Automated severity assignment. Chatbot judges severity per the
  template's low/medium/high/blocker ladder.
- Index-page rebuild automation. The 🐛 line is a static prepend;
  update manually if the format needs to change.

## Open questions for host

None. Spec is user-ratified; refinements above are navigator
suggestions narrow enough that dev can implement with or without them.
If any refinement is wrong, say so before landing — otherwise dev
proceeds.
