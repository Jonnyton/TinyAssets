# Wiki discovery contamination — live baseline

**Verified:** 2026-07-21 America/Los_Angeles (2026-07-22 UTC) against the installed live connector at `https://tinyassets.io/mcp`.

## Finding

The wiki is not merely coordination-heavy in storage; its current ranking makes coordination the complete visible answer to representative onboarding searches.

| Measure | 2026-05-19 baseline | 2026-07-21 live | Change |
|---|---:|---:|---:|
| Pages changed since 2026-05-01 | 614 | 1,418 | +804 (+131.0%) |
| Previously classified agent coordination | 495 / 614 (80.6%) | corpus-wide recount unavailable through the paginated public handle | — |
| Conservative coordination lower bound in newest 100 | — | 69 / 100 | 69% minimum |
| Coordination among four onboarding-query top tens | — | 40 / 40 | 100% |

The 69% lower bound counts a page as coordination only when either (a) it is under `pages/patch-requests`, `pages/bugs`, or `pages/design-proposals`, or (b) its path/title/excerpt contains an explicit operational marker such as Codex, Cowork, Claude, checker, PR/BUG id, host approval, daemon, connector, patch loop, or auto-change. It deliberately does not count many ambiguous platform plans/notes, so it is a floor rather than an estimate.

## Reproduction

Required connector opening call:

```text
get_status()
```

Feed probe:

```text
read_page(changed_since="2026-05-01T00:00:00Z", max_results=100)
=> total_matches=1418, count=100, truncated_count=1318
```

Search probes (top 10 each):

| Query | Coordination results |
|---|---:|
| `research tracker workflow` | 10 / 10 |
| `workflow schema` | 10 / 10 |
| `define workflow branch` | 10 / 10 |
| `claims tracker` | 10 / 10 |

Representative returned titles include Cowork checker keys, Codex/Cowork alignment logs, PR implementation records, BUG filings, host third-key decisions, and sandbox/capability-token reviews. No result teaches a new user how to define the requested workflow.

## Root causes in source

1. `tinyassets/api/wiki.py::_wiki_search` scans every shared page/draft and has no audience boundary.
2. The public `read_page.category` parameter is forwarded, but `_wiki_search` discards it in `**_kwargs`; callers cannot constrain the corpus as advertised.
3. `since` and ambient relevance feeds are also unfiltered, so coordination reappears after an exact read.
4. `tinyassets/universe_server.py::write_graph(target="branch")` always routes to `patch_branch`; it exposes no `spec_json` branch-create path.
5. The mature internal `build_branch` schema exists only in hidden/internal prompt text and source, not in the wiki discovery surface.

## Decision

Implement a logical discovery/coordination split in the existing store. Default new-user reads to discovery, keep exact paths stable, provide explicit coordination/all scopes, and use authoritative `audience` frontmatter with a conservative legacy category fallback. Restore branch creation additively through the existing `write_graph` handle and publish its schema as an `audience: discovery` workflow page.

This is the shortest reversible path to verified onboarding recovery. A physical move can remain a later storage optimization; it is not required to stop discovery from returning internal logs now.
