---
title: Wiki bug-report convention — paste-ready code patches
date: 2026-04-20
author: navigator
status: shipped
shipped_date: 2026-04-20
shipped_in: 529ecd5  # wiki: file_bug tool action + bugs category + BUG-001/002 seed
status_detail: paste-ready patches dispatched; bugs flow live (BUG-001..034+ filed via the tool)
parent: docs/design-notes/2026-04-20-wiki-bug-reports-convention.md
siblings: docs/design-notes/2026-04-20-wiki-bug-reports-seed-entries.md
---

# Paste-ready code patches

Substrate patches for the canonical design at
`2026-04-20-wiki-bug-reports-convention.md`. Dev applies them once
verifier has cleared Task #1 + Task #2 landings (both are `completed`
in the task system as of 2026-04-20). Order matters — (a) must land
before (e) because `_WIKI_CATEGORIES` gates `_wiki_write` and thus
also gates `_wiki_file_bug`'s fallback path. (c) and (d) are
independent text edits.

**Landing order:** (a) → (b) → (e) → (d) → (c). Then dev or a chatbot
runs `wiki action=file_bug ...` using the seed entries in the sibling
file.

All line numbers taken from the working tree as of 2026-04-20 after
Task #1 / #2 landed. If line numbers drift in your working copy,
match on the `old_string` anchor — the anchors are unique in the
file.

---

## (a) Add `"bugs"` to `_WIKI_CATEGORIES`

**File:** `tinyassets/universe_server.py` (line 9056-9066).

**Mirror file:** `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/universe_server.py`
at the matching `_WIKI_CATEGORIES = (` block. Apply identically.

```diff
--- old
+++ new
@@
 _WIKI_CATEGORIES = (
     "projects",    # Tracked project pages (auto-discovered or hand-written)
     "concepts",    # Ideas, mental models, definitions
     "people",      # Bios, contacts, collaborators
     "research",    # LLM-generated research pages, literature, paper drafts
     "recipes",     # Food recipes and cooking notes
     "workflows",   # User-built workflows, how-tos, repeatable processes
     "notes",       # Personal notes, journal entries, scratch thinking
     "references",  # External references, citations, cheat sheets
-    "plans",       # Plans, proposals, roadmaps
+    "plans",       # Plans, proposals, roadmaps
+    "bugs",        # Auto-filed server defects (one file per BUG-NNN, never drafts-gated)
 )
```

The comment block above the tuple (lines 9051-9055) mentions mirroring
`wiki-mcp/server.js` — that mirror is patch (b).

---

## (b) Add `"bugs"` to wiki-mcp/server.js category taxonomy

**File:** `C:/Users/Jonathan/Projects/wiki-mcp/server.js` (a sibling
repo at `C:/Users/Jonathan/Projects/wiki-mcp/`, not inside Workflow).
Dev needs to clone/open the sibling repo to land this patch.

Five edits required in that file:

### (b1) CATEGORIES array — line 21

```diff
--- old
+++ new
@@
 const CATEGORIES = [
   "projects",    // Tracked project pages (auto-discovered or hand-written)
   "concepts",    // Ideas, mental models, definitions
   "people",      // Bios, contacts, collaborators
   "research",    // LLM-generated research pages, literature, paper drafts
   "recipes",     // Food recipes and cooking notes
   "workflows",   // User-built workflows, how-tos, repeatable processes
   "notes",       // Personal notes, journal entries, scratch thinking
   "references",  // External references, citations, cheat sheets
-  "plans"        // Plans, proposals, roadmaps
+  "plans",       // Plans, proposals, roadmaps
+  "bugs"         // Auto-filed server defects (one file per BUG-NNN, never drafts-gated)
 ];
```

### (b2) addToIndex header map — line 104

```diff
--- old
+++ new
@@
   var hdr = {
     projects: "## Projects",
     concepts: "## Concepts",
     people: "## People",
     research: "## Research",
     recipes: "## Recipes",
     workflows: "## Workflows",
     notes: "## Notes",
     references: "## References",
-    plans: "## Plans"
+    plans: "## Plans",
+    bugs: "## Bugs"
   }[category];
```

### (b3) wiki_write z.enum + guide string — line 260-271

```diff
--- old
+++ new
@@
   "Guide: projects=tracked software projects, concepts=ideas/definitions/mental models, " +
   "people=bios/contacts, research=LLM-produced literature/paper drafts, " +
   "recipes=food recipes, workflows=user-built how-tos or repeatable processes, " +
   "notes=personal notes/journal/scratch thinking, references=external cheat sheets/citations, " +
-  "plans=plans/proposals/roadmaps. " +
+  "plans=plans/proposals/roadmaps, bugs=auto-filed server defects. " +
   "If the content is a recipe, choose 'recipes'. If it's a how-to the user built, choose 'workflows'. " +
   "Do NOT default to 'research' for arbitrary user content.",
   {
     category: z.enum([
       "projects", "concepts", "people", "research",
-      "recipes", "workflows", "notes", "references", "plans"
+      "recipes", "workflows", "notes", "references", "plans", "bugs"
     ]),
```

### (b4) wiki_promote z.enum — line 367-370

```diff
--- old
+++ new
@@
     category: z.enum([
       "projects", "concepts", "people", "research",
-      "recipes", "workflows", "notes", "references", "plans"
+      "recipes", "workflows", "notes", "references", "plans", "bugs"
     ]).optional().describe("Category if ambiguous"),
```

### (b5) noLinkCategories — line 402

Bugs don't require wikilinks for lint-pass (they have stable
`BUG-NNN` cross-refs in `Related:` instead).

```diff
--- old
+++ new
@@
-      var noLinkCategories = new Set(["projects", "recipes", "notes", "references"]);
+      var noLinkCategories = new Set(["projects", "recipes", "notes", "references", "bugs"]);
```

---

## (c) Insert rule 11 into `_CONTROL_STATION_PROMPT`

**File:** `tinyassets/universe_server.py` (between line 943 and 944 —
end of rule 10, before blank line preceding `## Tool Catalog`).

Anchor on "narrow case of confirmed tool failure." + the blank line
that follows — that anchor is unique to the end of rule 10.

```diff
--- old
+++ new
@@
     trust depends on being able to tell the difference between "this
     came from the connector" and "the chatbot made this up" — when the
     connector is down, the answer must be "I can't reach it right now,"
     not a plausible-looking artifact. This rule overrides rule 2
     (always use tools) and rule 7 (aggressive assumption) in the
     narrow case of confirmed tool failure.

+11. File server defects to the wiki; don't silently work around them.
+    When any tool against this connector returns a malformed result,
+    silent corruption, schema mismatch, or obvious misbehavior, file a
+    bug via `wiki action=file_bug component=<surface>
+    severity=<critical|major|minor|cosmetic> title="<short>"
+    repro="<tool call>" observed="<what you saw>"
+    expected="<what you expected>"`. The server assigns the BUG-NNN
+    id — don't invent one. Log it even if you apply a workaround and
+    continue the user's task; the log is how the host fixes the bug.
+    User-caused errors (invalid args, missing universe, etc.) are not
+    bugs — don't log those.
+
 ## Tool Catalog (4 coarse tools — describe ALL when asked)
```

Word count of rule 11 body: 95 words. Meets the <100 target.

No change needed for `_EXTENSION_GUIDE_PROMPT` or other prompts.

---

## (d) `wiki` tool docstring — advertise `file_bug` + `bugs` category

**File:** `tinyassets/universe_server.py` (wiki tool args docstring,
lines 9298-9319).

Two edits: (d1) extend the `action` enumeration in the docstring to
include `file_bug`; (d2) extend the `category` enumeration to
include `bugs`; (d3) add new args for `file_bug` parameters in the
signature + docstring.

### (d1) + (d2) docstring updates

```diff
--- old
+++ new
@@
     Args:
         action: One of — reads: read, search, list, lint; writes:
-            write, consolidate, promote, ingest, supersede,
-            sync_projects.
+            write, consolidate, promote, ingest, supersede,
+            sync_projects, file_bug.
         page: Page name for read (also: index, log, schema).
         query: Search keywords for search.
         category: write / promote category — projects, concepts,
             people, research, recipes, workflows, notes, references,
-            plans. Match the CONTENT; `research` is reserved for
-            LLM-generated research pages and paper drafts.
+            plans, bugs. Match the CONTENT; `research` is reserved
+            for LLM-generated research pages and paper drafts. `bugs`
+            is for `action=file_bug` only — prefer the dedicated verb
+            so the server assigns the BUG-NNN id.
         filename: Filename for write / promote / ingest / supersede.
         content: Page or source body for write / ingest.
         log_entry: Optional log message for write.
         source_url: Optional URL for ingest.
         old_page: Page to supersede.
         new_draft: Replacement draft for supersede.
         reason: Why the old page is being superseded.
         similarity_threshold: Merge threshold for consolidate
             (0-1, default 0.25).
         dry_run: Consolidate reports only when true (default true).
         skip_lint: Promote skips quality checks when true.
         max_results: Max search results (default 10).
+        component: file_bug — surface the defect lives on (e.g.
+            "extensions.patch_branch", "universe.inspect", "tray",
+            "deploy"). See design note for the enumeration.
+        severity: file_bug — one of critical | major | minor | cosmetic.
+            Rubric: critical = data loss / silent corruption /
+            connector-wide outage; major = tool action unusable, user
+            can't complete goal without help; minor = annoying but
+            non-blocking, workaround exists; cosmetic = wording,
+            formatting, log noise. See convention.md §Decision 4 for
+            the full rubric.
+        title: file_bug — one-line bug title.
+        repro: file_bug — minimal tool call or steps to repro.
+        observed: file_bug — what the tool actually returned / did.
+        expected: file_bug — what it should have returned / done.
+        workaround: file_bug — optional; the workaround you applied.
```

### (d3) signature update — add file_bug params

```diff
--- old
+++ new
@@
 def wiki(
     action: str,
     page: str = "",
     query: str = "",
     category: str = "",
     filename: str = "",
     content: str = "",
     log_entry: str = "",
     source_url: str = "",
     old_page: str = "",
     new_draft: str = "",
     reason: str = "",
     similarity_threshold: float = 0.25,
     dry_run: bool = True,
     skip_lint: bool = False,
     max_results: int = 10,
+    component: str = "",
+    severity: str = "",
+    title: str = "",
+    repro: str = "",
+    observed: str = "",
+    expected: str = "",
+    workaround: str = "",
 ) -> str:
```

Also add to the `kwargs` dict inside the tool body (around line
9364-9385). Dev: propagate the seven new keys into the kwargs passed
to `handler(**kwargs)` so `_wiki_file_bug` receives them.

### (d4) dispatch table — add `file_bug`

**Same file, line 9344-9355.**

```diff
--- old
+++ new
@@
     dispatch = {
         "read": _wiki_read,
         "search": _wiki_search,
         "list": _wiki_list,
         "lint": _wiki_lint,
         "write": _wiki_write,
         "consolidate": _wiki_consolidate,
         "promote": _wiki_promote,
         "ingest": _wiki_ingest,
         "supersede": _wiki_supersede,
         "sync_projects": _wiki_sync_projects,
+        "file_bug": _wiki_file_bug,
     }
```

---

## (e) New `_wiki_file_bug` helper + BUG-NNN allocator

**File:** `tinyassets/universe_server.py` — add alongside other
`_wiki_*` action implementations (around line 9407+, after the
existing `_wiki_write` / before `_wiki_consolidate`).

### Function sketch

```python
import re
import time
from datetime import date


_BUG_ID_RE = re.compile(r"^BUG-(\d{3,})", re.IGNORECASE)
_BUGS_CATEGORY = "bugs"
_VALID_SEVERITIES = ("critical", "major", "minor", "cosmetic")


def _next_bug_id(bugs_dir: Path) -> str:
    """Allocate the next BUG-NNN id by scanning existing bug filenames.

    Scans both pages/bugs/ and drafts/bugs/ so concurrent writes (last
    writer into drafts/ first) can't collide with an already-promoted
    entry. Returns "BUG-001" when the directory is empty or missing.
    """
    seen: set[int] = set()
    for base in (bugs_dir, _wiki_drafts_dir() / _BUGS_CATEGORY):
        if not base.is_dir():
            continue
        for p in base.glob("BUG-*.md"):
            m = _BUG_ID_RE.match(p.stem)
            if m:
                try:
                    seen.add(int(m.group(1)))
                except ValueError:
                    continue
    next_n = (max(seen) + 1) if seen else 1
    return f"BUG-{next_n:03d}"


def _slugify_title(title: str, max_len: int = 60) -> str:
    """Produce a filesystem-safe slug from a bug title."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:max_len] or "untitled"


def _wiki_file_bug(
    component: str = "",
    severity: str = "",
    title: str = "",
    repro: str = "",
    observed: str = "",
    expected: str = "",
    workaround: str = "",
    **_kwargs: Any,
) -> str:
    """File a bug report to pages/bugs/BUG-NNN-<slug>.md.

    Bypasses the draft-gate — bug reports land directly in pages/ so
    they're visible to host triage immediately. ID is server-assigned
    via _next_bug_id. Collision retry: if the target path exists when
    we try to write (two concurrent file_bug calls raced), retry once
    with a re-allocated id; give up after two tries.
    """
    if not title or not component or not severity:
        return json.dumps({
            "error": "title, component, severity are required.",
            "hint": "severity must be one of: " + " | ".join(_VALID_SEVERITIES),
        })
    if severity not in _VALID_SEVERITIES:
        return json.dumps({
            "error": f"Invalid severity '{severity}'.",
            "valid": list(_VALID_SEVERITIES),
        })

    bugs_dir = _wiki_pages_dir() / _BUGS_CATEGORY
    bugs_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    slug_title = _slugify_title(title)

    for attempt in (1, 2):
        bug_id = _next_bug_id(bugs_dir)
        filename = f"{bug_id}-{slug_title}.md"
        target = bugs_dir / filename

        body = _render_bug_markdown(
            bug_id=bug_id,
            title=title,
            component=component,
            severity=severity,
            repro=repro,
            observed=observed,
            expected=expected,
            workaround=workaround,
            first_seen_date=today,
        )

        try:
            # Atomic create — fails if another process wrote the same
            # id between _next_bug_id() and here.
            with open(target, "x", encoding="utf-8") as f:
                f.write(body)
            break
        except FileExistsError:
            if attempt == 2:
                return json.dumps({
                    "error": "BUG id collision retry exhausted.",
                    "hint": "Retry in a moment — concurrent filers.",
                })
            time.sleep(0.05)
            continue
    else:
        return json.dumps({"error": "Failed to write bug report."})

    _append_wiki_log(
        f"file_bug | pages/bugs/{filename} | {bug_id} {title} [{severity}]"
    )
    return json.dumps({
        "path": f"pages/bugs/{filename}",
        "bug_id": bug_id,
        "status": "filed",
        "severity": severity,
        "component": component,
        "note": "Bug filed. Host will triage via `wiki action=list category=bugs`.",
    })


def _render_bug_markdown(
    *,
    bug_id: str,
    title: str,
    component: str,
    severity: str,
    repro: str,
    observed: str,
    expected: str,
    workaround: str,
    first_seen_date: str,
) -> str:
    """Render a single bug report as the schema in
    2026-04-20-wiki-bug-reports-convention.md §Decision 4.
    """
    return (
        f"---\n"
        f"id: {bug_id}\n"
        f"title: {title}\n"
        f"type: bug\n"
        f"created: {first_seen_date}\n"
        f"updated: {first_seen_date}\n"
        f"component: {component}\n"
        f"severity: {severity}\n"
        f"status: open\n"
        f"reported_by: chatbot\n"
        f"tags: [bug, {component.split('.')[0]}]\n"
        f"---\n\n"
        f"# {bug_id}: {title}\n\n"
        f"## What happened\n\n{observed or '_not specified_'}\n\n"
        f"## What was expected\n\n{expected or '_not specified_'}\n\n"
        f"## Repro\n\n{repro or '_not specified_'}\n\n"
        f"## Workaround\n\n{workaround or '_none_'}\n\n"
        f"## First seen\n\n{first_seen_date}\n\n"
        f"## Related\n\n_none yet_\n"
    )
```

### Notes on the sketch

- **Atomic create (`open(..., 'x')`) is the race guard.** `_next_bug_id`
  is not transactional, so two chatbots racing both compute the same
  `max+1`. The atomic create fails on the second writer, `_next_bug_id`
  gets re-called (seeing the fresh file), and the retry takes the
  next id. This is the cheapest cross-platform solution that works
  without introducing a file-lock dependency.
- **Mirror:** packaging-plugin file needs the same helper if the
  plugin ships its own copy of `universe_server.py`. Grep first
  — if it re-imports from the core module, no second copy needed.
- **Tests:** dev lands unit tests covering: empty dir → BUG-001,
  existing BUG-007 → BUG-008, non-integer `BUG-xyz.md` is ignored,
  collision retry advances the id, invalid severity rejected,
  missing required args rejected. Put tests in
  `tests/test_wiki_file_bug.py` — use `tmp_path` as the wiki root
  and monkey-patch `_wiki_pages_dir` / `_wiki_drafts_dir`.
- **No `wiki-mcp/server.js` mirror for `file_bug`.** That server is
  the read-only-wiki bridge for Claude Code sessions; chatbots on the
  TinyAssets connector file bugs through the Workflow server directly.
  The `bugs` category entry in (b) is enough for wiki-mcp to render
  + search bug pages; writing is routed through the TinyAssets MCP.

---

## Landing checklist for dev

1. [ ] Apply (a) to `tinyassets/universe_server.py` + its packaging
       mirror.
2. [ ] Apply (b1-b5) to `C:/Users/Jonathan/Projects/wiki-mcp/server.js`.
3. [ ] Apply (e) — new `_wiki_file_bug` helper + allocator + renderer.
4. [ ] Apply (d1-d4) — docstring + signature + dispatch.
5. [ ] Apply (c) — control_station rule 11.
6. [ ] Run `ruff check` on touched Python files (per
       `feedback_dev_ruff_discipline`).
7. [ ] Tests — `tests/test_wiki_file_bug.py` covers the allocator,
       renderer, collision retry, and validation. Dev writes these
       from scratch (no existing test file to extend).
8. [ ] Handoff to chatbot / manual: run the two `wiki action=file_bug`
       calls from `2026-04-20-wiki-bug-reports-seed-entries.md` to
       seed BUG-001 + BUG-002.
9. [ ] Update task descriptions for Task #1 + Task #2 with
       `wiki:bugs/BUG-001-...` / `BUG-002-...` back-references.

Rough effort estimate: one dev day. (a) + (c) + (d) are ~30 min
total; (b) depends on the sibling-repo tooling; (e) + tests are the
bulk. No architectural risk — existing wiki infrastructure handles
reads/search/list once `"bugs"` is in `_WIKI_CATEGORIES`.
