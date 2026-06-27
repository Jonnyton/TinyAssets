---
title: Wiki bug-report seed entries — BUG-001 + BUG-002
date: 2026-04-20
author: navigator
status: shipped
shipped_date: 2026-04-20
shipped_in: 529ecd5  # wiki: file_bug tool action + bugs category + BUG-001/002 seed
status_detail: BUG-001 + BUG-002 seed entries landed alongside the convention
parent: docs/design-notes/2026-04-20-wiki-bug-reports-convention.md
siblings: docs/design-notes/2026-04-20-wiki-bug-reports-patches.md
---

# BUG-001 + BUG-002 seed entries

These are the two seed bugs the user surfaced on 2026-04-19 (the
`changes_json` silent char-split + the `WIKI_PATH` cross-OS leak).
Tasks #1 and #2 landed their underlying fixes — these entries record
them in the public bug-log surface so future chatbots + users can
search for and learn from them.

**Usage.** After the patches in
`2026-04-20-wiki-bug-reports-patches.md` land, dev (or a chatbot
connected to the TinyAssets server) runs the two tool invocations
below. The server assigns the BUG-NNN ids in invocation order, so run
BUG-001 first, then BUG-002. The expected full-file output is shown
for each so the landing is verifiable byte-for-byte.

Because Tasks #1 + #2 already landed fixes, both entries ship with
`status: fixed-in-version: <sha>` — replace the `<sha>` placeholders
with the actual fix commits from `git log` before filing. As of
2026-04-20 I couldn't identify the exact landing commits from the
recent main log; dev confirms at landing time.

---

## BUG-001 — `changes_json` silent string-to-chars mangling

### Tool invocation (paste verbatim)

```
wiki action=file_bug
  component="extensions.patch_branch"
  severity="major"
  title="changes_json input_keys/output_keys silently char-split when given a string"
  repro="extensions action=patch_branch with changes_json op: {\"op\": \"update_node\", \"node_id\": \"x\", \"input_keys\": \"node.output\"}"
  observed="Server accepts the string and coerces via list(...), storing input_keys as ['n','o','d','e','.','o','u','t','p','u','t']. Node validates at edit time but is unrunnable at runtime. Same pattern at the add_node code path (which used _split_csv — inconsistent with patch_branch)."
  expected="Reject non-list values with a clear error, OR parse intelligently (json.loads -> fall back to CSV split -> assert all entries are non-empty strings). Unified behavior across patch_branch and add_node."
  workaround="Always pass input_keys / output_keys as JSON arrays (e.g. [\"node.output\"]) — never a bare string."
```

### Expected file at `pages/bugs/BUG-001-changes-json-input-keys-output-keys-silently-char-split-when-given-a-string.md`

Note: filename slug will be truncated to ~60 chars by `_slugify_title`.
The actual landed filename is likely
`BUG-001-changes-json-input-keys-output-keys-silently-char-spli.md`.

```markdown
---
id: BUG-001
title: changes_json input_keys/output_keys silently char-split when given a string
type: bug
created: 2026-04-20
updated: 2026-04-20
component: extensions.patch_branch
severity: major
status: active
status_detail: open
reported_by: chatbot
tags: [bug, extensions]
---

# BUG-001: changes_json input_keys/output_keys silently char-split when given a string

## What happened

Server accepts the string and coerces via list(...), storing input_keys as ['n','o','d','e','.','o','u','t','p','u','t']. Node validates at edit time but is unrunnable at runtime. Same pattern at the add_node code path (which used _split_csv — inconsistent with patch_branch).

## What was expected

Reject non-list values with a clear error, OR parse intelligently (json.loads -> fall back to CSV split -> assert all entries are non-empty strings). Unified behavior across patch_branch and add_node.

## Repro

extensions action=patch_branch with changes_json op: {"op": "update_node", "node_id": "x", "input_keys": "node.output"}

## Workaround

Always pass input_keys / output_keys as JSON arrays (e.g. ["node.output"]) — never a bare string.

## First seen

2026-04-20

## Related

_none yet_
```

### Post-landing edits (dev applies manually after the chatbot filing)

The `_wiki_file_bug` helper lands the entry with `status: open`.
Tasks #1's fix has already landed, so:

1. Change `status: open` → `status: fixed-in-version: <sha-of-task-1-fix>`
   in the frontmatter. Find the sha via `git log --oneline --all -- tinyassets/universe_server.py | head` — look for the commit
   message mentioning `changes_json` / `input_keys` / `patch_branch` fix.
2. Replace `_none yet_` under `## Related` with:
   ```
   - First seen 2026-04-19 (user chat, research_paper_7node v2 patching)
   - Task #1 in task system
   - Source: tinyassets/universe_server.py:5404-5407 (patch path), :4160-4161 (add_node)
   - Mirror: packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/universe_server.py
   ```

---

## BUG-002 — `WIKI_PATH` Windows-on-Linux `/app/C:\...` prefix leak

### Tool invocation (paste verbatim)

```
wiki action=file_bug
  component="storage.wiki_path"
  severity="major"
  title="WIKI_PATH Windows-style value leaks into Linux container as /app/C:\\..."
  repro="Deploy the TinyAssets MCP server in Docker with TINYASSETS_WIKI_PATH=C:\\Users\\Jonathan\\Projects\\Wiki (or legacy WIKI_PATH) inherited from a Windows host's env. Call any wiki action inside the container."
  observed="Server replies \"Wiki not found at /app/C:\\Users\\Jonathan\\Projects\\Wiki\". Linux Path(\"/app\") / \"C:\\\\Users\\\\...\" treats the Windows absolute path as relative (no drive-letter detection), so /app prefixes the Windows path instead of replacing it."
  expected="Per hard-rule #8 (fail loudly), the resolver should detect a Windows-style path on a Linux runtime and either reject with a clear error (\"TINYASSETS_WIKI_PATH=... is a Windows path but we're on Linux — refusing\") or fall back to $TINYASSETS_DATA_DIR/wiki with a loud warning. Silent join is the failure mode."
  workaround="Set TINYASSETS_WIKI_PATH=/data/wiki (or another POSIX absolute path) explicitly in the container's environment overrides. Do not inherit the host-machine value."
```

### Expected file at `pages/bugs/BUG-002-wiki-path-windows-style-value-leaks-into-linux-container.md`

Actual landed filename: likely
`BUG-002-wiki-path-windows-style-value-leaks-into-linux-containe.md`
(slug truncation).

```markdown
---
id: BUG-002
title: WIKI_PATH Windows-style value leaks into Linux container as /app/C:\...
type: bug
created: 2026-04-20
updated: 2026-04-20
component: storage.wiki_path
severity: major
status: active
status_detail: open
reported_by: chatbot
tags: [bug, storage]
---

# BUG-002: WIKI_PATH Windows-style value leaks into Linux container as /app/C:\...

## What happened

Server replies "Wiki not found at /app/C:\Users\Jonathan\Projects\Wiki". Linux Path("/app") / "C:\\Users\\..." treats the Windows absolute path as relative (no drive-letter detection), so /app prefixes the Windows path instead of replacing it.

## What was expected

Per hard-rule #8 (fail loudly), the resolver should detect a Windows-style path on a Linux runtime and either reject with a clear error ("TINYASSETS_WIKI_PATH=... is a Windows path but we're on Linux — refusing") or fall back to $TINYASSETS_DATA_DIR/wiki with a loud warning. Silent join is the failure mode.

## Repro

Deploy the TinyAssets MCP server in Docker with TINYASSETS_WIKI_PATH=C:\Users\Jonathan\Projects\Wiki (or legacy WIKI_PATH) inherited from a Windows host's env. Call any wiki action inside the container.

## Workaround

Set TINYASSETS_WIKI_PATH=/data/wiki (or another POSIX absolute path) explicitly in the container's environment overrides. Do not inherit the host-machine value.

## First seen

2026-04-20

## Related

_none yet_
```

### Post-landing edits

1. Change `status: open` → `status: fixed-in-version: <sha-of-task-2-fix>`.
   `git log --oneline --all -- tinyassets/storage/__init__.py | head` —
   look for the commit after `5b2a282` that added Windows-on-Linux
   detection.
2. Replace `_none yet_` under `## Related` with:
   ```
   - First seen 2026-04-19 (user chat, in-container wiki probe)
   - Task #2 in task system
   - Earlier partial fix: 5b2a282 "wiki_path resolver: Row-B pattern applied to WIKI_PATH" — did not cover cross-OS leakage
   - Source: tinyassets/storage/__init__.py
   - Mirror: packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/storage/__init__.py
   ```

---

## Why these deserve pride of place as BUG-001 + BUG-002

Both bugs share a pattern worth preserving visibly in the bug log:
the server *silently* did the wrong thing with user input that was
plausible-looking-but-wrong. BUG-001's `list("node.output")` and
BUG-002's `Path("/app") / "C:\\..."` both produce a result the
language considers valid. Both violate hard-rule #8 (fail loudly,
never silently).

Filing them as the first two public bugs sets the tone for what
this log is for: not "the tool crashed," but "the tool did
something silly and kept going as if nothing was wrong." That framing
will shape how future chatbots triage their own observations.
