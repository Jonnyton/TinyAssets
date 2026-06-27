---
title: Wiki bug-report convention (chatbot-auto-file)
date: 2026-04-20
author: navigator
status: shipped
shipped_date: 2026-04-20
shipped_in: 529ecd5  # wiki: file_bug tool action + bugs category + BUG-001/002 seed
status_detail: canonical convention shipped; BUG-001..034+ filed via the live tool
supersedes: docs/design-notes/2026-04-19-wiki-known-issues-convention.md
related_patches: docs/design-notes/2026-04-20-wiki-bug-reports-patches.md
related_seed_entries: docs/design-notes/2026-04-20-wiki-bug-reports-seed-entries.md
---

# Wiki bug-report convention — CANONICAL

Approved by team-lead 2026-04-20. The user ratified a *principle* on
2026-04-19 ("natural for chatbots/users to auto-file bugs"); that
principle admits multiple substrate implementations. This design wins
on engineering axes — per-file scalability, new top-level `bugs/`
category for lint separation and triage queries, dedicated `file_bug`
verb for a clean API surface. Supersedes the 2026-04-19
`known-issues` single-page draft; both files are retained for history.

Related artifacts (same package):

- `2026-04-20-wiki-bug-reports-patches.md` — paste-ready code patches.
- `2026-04-20-wiki-bug-reports-seed-entries.md` — paste-ready BUG-001
  + BUG-002 markdown for dev / chatbot to `wiki action=file_bug` once
  the page exists.

## Problem

When a chatbot (Claude.ai, future clients) hits a defect in the TinyAssets
MCP server mid-conversation, the current options are all bad:

- Silently work around it and move on (most common) — the bug dies in chat
  history, host never learns about it.
- User manually copy-pastes the failure to the host — high-friction, most
  users won't bother.
- File a GitHub issue — outside the chatbot's tool surface; chatbot cannot
  do it without the user leaving Claude.ai.

Today's session (2026-04-19) produced two real bugs this way:
`changes_json` silent string-to-chars mangling and a cross-OS wiki path
leak. Both were caught only because the host was co-reviewing the chat.
Without that, both would have vanished.

We need a place chatbots can auto-file bugs to, using a tool they
already have (`wiki`), that future chatbots + users can auto-discover
without being told.

## 3-layer lens

- *System*: exposes a canonical, discoverable sink for defect reports.
- *Chatbot*: has a single clear primitive ("when the server misbehaves,
  write to `wiki:bugs/...`") and can execute it without leaving the tool
  surface.
- *User*: gets their friction surfaced into a durable, searchable place
  instead of lost to chat history.

Load-bearing question: does this make the chatbot better at serving the
user's real goal? Yes — it converts a dead-end friction ("tool broke,
move on") into a report the host can act on, without interrupting the
user's actual task.

## Decision 1 — location: top-level `bugs/` category

Add `bugs` as a tenth entry to `_WIKI_CATEGORIES` alongside the existing
nine (`projects`, `concepts`, `people`, `research`, `recipes`,
`workflows`, `notes`, `references`, `plans`).

Why top-level (not `notes/bugs/` or `meta/bugs/`):

- **Discoverability.** Every chatbot reading `wiki/index.md` to orient
  itself sees `## Bugs` as a first-class heading. Nesting inside `notes/`
  hides it.
- **Schema separation.** Bugs have required front-matter (component,
  severity, repro, status, fixed-in-commit) that other categories don't.
  A separate category lets `_wiki_lint` enforce bug-specific rules
  without polluting other categories' validators.
- **Search + triage.** Host can run
  `wiki action=list category=bugs status=open` and get a clean triage
  queue. Cross-category queries mix signal with noise.
- **Parity with existing taxonomy.** `recipes`, `workflows`, `plans`
  were added 2026-04-13 for the same reason — the previous four didn't
  fit user-intent content. Bugs are the same class of first-class
  content type.

`meta/bugs/` was the other candidate. Rejected because the wiki doesn't
otherwise use nested top-level folders, and `meta/` implies
"about-the-wiki", not "about-any-project's-software".

## Decision 2 — scope: any software defect, not just the TinyAssets MCP server

Initial framing was "bugs in the TinyAssets MCP server". Broaden: any software
defect a chatbot or user hits while working on any project the wiki
covers. The `component` front-matter field tells the reader which
project/surface is affected (e.g. `universe-server`, `wiki-mcp`, `tray`,
`claude-chat-skill`).

Why broader: the wiki is already cross-project. Constraining `bugs/` to
one project forces a second convention for each other project's bugs,
which defeats the "one natural place" goal.

## Decision 3 — draft-gate: bypass for bug reports

Bug reports land directly in `pages/bugs/`, not `drafts/bugs/`.

Why bypass the gate:

- **Speed to host visibility.** A bug buried in `drafts/` isn't in
  `index.md`, isn't in standard `wiki list` output, and requires a
  promotion step before triage is possible. That defeats auto-filing.
- **Low cost of false positives.** Unlike a malformed research page,
  a speculative bug report is still useful — it's evidence something
  felt wrong to the chatbot. Host can reclassify or close.
- **Consistent with `sync_projects` precedent.** `wiki_sync_projects`
  already writes directly to `pages/projects/` for auto-discovered
  stubs. Auto-filed bugs follow the same pattern: structural content
  produced without human authorship, tagged for later curation.

The gate's purpose (prevent junk accumulation in promoted knowledge) is
served by the `status` field instead — `wontfix`, `cannot-repro`, and
`fixed` entries naturally age out of the active triage view.

This requires a small extension to `_wiki_write`: when
`category == "bugs"`, skip the drafts directory and write straight to
`pages/bugs/`. Alternative (preferred, lower complexity): leave
`_wiki_write` alone and add a dedicated `_wiki_file_bug` helper invoked
by `action="file_bug"`. That also gives the chatbot a verb that exactly
matches the behavioral directive in `control_station`.

## Decision 4 — schema

File-per-bug, named `BUG-NNN-slug.md` (e.g. `BUG-001-changes-json-input-keys-mangle.md`).

Why BUG-NNN (not `YYYY-MM-DD-slug`):

- **Stable cross-references.** Host already speaks in `BUG-001` /
  `BUG-002` shorthand (see 2026-04-19 mobile-session note in
  STATUS.md). Every date-slug reference would drift as bugs are re-dated.
- **Chat-friendly.** `"saw BUG-001 again"` is shorter + more memorable
  than a dated slug. Chatbots pattern-match IDs in tool output.
- **Dedup signal.** A chatbot scanning `wiki list category=bugs` sees
  `BUG-NNN` prefix and can search existing IDs before filing a
  duplicate. Date-slugs invite accidental duplicates.

ID allocation: next-available integer, zero-padded to 3 digits. Chatbot
writes `wiki action=file_bug` (or `action=write category=bugs` with no
explicit ID); server assigns the next ID by scanning existing
`pages/bugs/BUG-*.md`. See Decision 6 for the `file_bug` action spec.

Required frontmatter:

```yaml
---
id: BUG-NNN
title: One-line bug title
type: bug
created: YYYY-MM-DD
updated: YYYY-MM-DD
component: universe-server | wiki-mcp | tray | claude-chat-skill | ...
severity: critical | major | minor | cosmetic
status: active
status_detail: open | investigating | fixed | wontfix | cannot-repro | duplicate
reported_by: chatbot | user | navigator | ...
repro_chat: (optional) URL or chat-id where the bug surfaced
fixed_in_commit: (optional, populated on status=fixed)
duplicate_of: (optional BUG-NNN, populated on status=duplicate)
tags: [relevant tags]
---
```

Body structure (free-form but lint-suggested):

```markdown
## What happened
Observed behavior. What the chatbot tried, what the server returned.

## What was expected
Intended behavior.

## Repro
Exact tool call(s) + args that trigger the defect.

## Evidence
Tool output, stack trace, or file paths that document the failure.

## Impact
Which users / workflows are blocked. How often it surfaces.
```

`severity` rubric (keep short, chatbots pattern-match):

- `critical` — data loss, silent corruption, connector-wide outage.
- `major` — a tool action is unusable; user cannot complete their goal
  without a workaround.
- `minor` — annoying but non-blocking; workaround exists.
- `cosmetic` — wording, formatting, log noise.

## Decision 5 — INDEX.md layout

`pages/bugs/INDEX.md` (not `index.md` lowercase — matches existing
pattern of category-level overview pages). Sections:

- **Open (highest severity first).** One-line per bug: title, severity,
  component, date.
- **Investigating.** Same format.
- **Recently fixed (last 30 days).** With `fixed_in_commit` short-sha.
- **Archive.** Wontfix / cannot-repro / duplicate / fixed >30 days.

INDEX.md should be maintainable by hand initially. Automation (rebuild
from frontmatter) is a follow-up if volume justifies it.

## Decision 6 — control_station directive

Add a new hard rule to `_CONTROL_STATION_PROMPT` (insert after rule 10
"degraded-mode", as rule 11). Draft:

> **11. File bugs to the wiki, don't work around them.**
> When a tool call against this connector returns a clear defect — a
> validation error the user didn't cause, a 500, silently wrong data,
> a tool description that disagrees with actual behavior, or any
> server-side misbehavior — file a bug via
> `wiki action=write category=bugs filename=YYYY-MM-DD-short-slug`.
> Include the exact tool call, the response you saw, and what you
> expected. This is lightweight: one `wiki` call, then continue the
> user's task (use a workaround if one exists). Do NOT silently route
> around the bug without recording it — undocumented defects accumulate.
> Severity guidance: use `major` for "user cannot complete their goal
> without help", `critical` for data loss / silent corruption, `minor`
> otherwise. This rule does NOT apply to user-caused errors (invalid
> args, missing universe, etc.) — those are expected behavior, not
> bugs.

Trade-off considered: rule 10 (degraded-mode) already instructs STOP on
tool failure. Rule 11 adds "file it" on top of STOP. They compose: tool
failure → stop + tell user → (one extra call) file bug → continue only
if user says to.

Interaction with rule 2 ("always use tools"): the bug-filing itself is
a tool call, so this reinforces rule 2 rather than violating it.

## Decision 7 — chatbot-auto-discoverability

Three mechanisms, strongest first:

1. **control_station rule 11** (above) — the primary mechanism. Every
   chatbot loads this prompt on first connect.
2. **`wiki list` output** — `category=bugs` appears in the category
   enum; chatbots exploring the wiki surface discover it naturally.
3. **`wiki/index.md`** — add a `## Bugs` section with a pointer to
   `pages/bugs/INDEX.md`.

For user-typed bugs, the discoverability path is: `wiki` tool's
`action=write` doc-string lists `bugs` as a category; CLAUDE-style
chatbots adopting TinyAssets already pattern-match "I want to report a
bug" → `wiki action=write category=bugs`.

## Decision 8 — cross-repo parity

`wiki-mcp/server.js` mirrors `_WIKI_CATEGORIES` per the in-code comment.
Any new category MUST be added there too or the two surfaces drift.
Include this in the dev task.

## Proposed deliverables

Landed as sibling commits:

1. This design note (docs/design-notes/).
2. `_WIKI_CATEGORIES` += `"bugs"` in `tinyassets/universe_server.py` and
   its `packaging/claude-plugin/` mirror.
3. Matching update in `wiki-mcp/server.js` category enum.
4. `pages/bugs/INDEX.md` skeleton + one seed entry for the
   `changes_json` bug + one seed entry for the cross-OS wiki path bug.
5. Rule 11 added to `_CONTROL_STATION_PROMPT`.
6. Docstring update on `wiki` tool: mention `bugs` as a valid category
   with the auto-file guidance.
7. Tasks #1 + #2 description updated with `wiki:bugs/...` links.

## Open questions

None for host. Ship unless someone objects within one session.

## Non-goals

- GitHub-issue bridging. Out of scope; possible follow-up that syncs
  `status=open` bugs into GitHub issues.
- Bug prioritization / milestone tracking. Host's existing STATUS.md
  and task-system already handle that.
- Rich reproducibility automation (record-and-replay). Out of scope.
