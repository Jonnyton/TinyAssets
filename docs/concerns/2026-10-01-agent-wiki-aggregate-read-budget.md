---
severity: P2
title: Agent-written wiki has no aggregate read budget in the daemon
filed: '2026-10-01'
summary: harness W1 bounds each wiki page read, but page scans, ambient feeds and listings walk every page with no total budget, and wiki writes still follow links a provider jail could plant
---

# Agent-written wiki: aggregate read budget and link-following writes

**Found:** 2026-10-01, gpt-6-astra refute of harness W1 (PR #4185), points 1
and 3. **Severity:** P2. The damage stays inside one universe's daemon calls,
but they run in the shared daemon process. **Owner:** the harness lane
(`universe-agent-harness`, slice W2).

## What W1 does and does not bound

W1 makes `wiki/` agent-writable. Every single-page read is now link-free and
bounded (`api/helpers._read_text` through `universe_files`). Inside a universe
wiki operation, a path outside the wiki is refused.

Two things remain open:

1. **No total budget.** `_find_all_pages` lists every `.md` under a directory,
   and a single page read scans every sibling for its ambient feed
   (`api/wiki.py` `_ambient_relevance_feed`). Listings keep every page's
   frontmatter title. The reviewer reproduced 32 hard links to one 65 KB file
   producing a 2.1 MB listing. Hard links inside `wiki/` are allowed, so a
   per-file bound and the jail's own limits do not bound daemon memory or CPU.
2. **Writes follow links.** The index and log appenders and the write-back
   page replacement write by path (`api/wiki.py` `_add_to_index`,
   `_append_wiki_log`; `effectors/wiki_write_back.py`
   `_append_or_update_section`). The tool jail's seccomp refuses creating a
   symlink, so the four-tool agent cannot plant one. A workflow provider jail
   binds the universe read-write and already could, before W1.

## Resolution

- Give scans and listings an aggregate budget (pages, bytes and output),
  reported loudly and paged rather than silently cut
  (`data-size-must-not-change-what-a-user-sees`), or run them in a
  limit-enforced worker.
- Write wiki pages, index and log through descriptor-relative, no-follow opens
  from the universe's wiki directory.

Delete this file when both land.
