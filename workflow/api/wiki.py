"""Wiki subsystem — extracted from workflow/universe_server.py (Task #9).

The wiki action handlers, helpers, constants, and dispatch live here so
they're independently testable and the decomposition audit's Step 2 ships
clean. The MCP tool decoration stays in `workflow/universe_server.py`
(Pattern A2 from `docs/exec-plans/completed/2026-04-26-decomp-step-2-prep.md`):
the decorated tool there delegates to the plain `wiki(...)` function below.

Public surface (test imports):
    wiki(action, ...)            → str: dispatch entry point
    _ensure_wiki_scaffold(root)  → None: idempotent dir + anchor scaffold
    _WIKI_CATEGORIES             → tuple: canonical category enum
    _wiki_file_bug(...)          → str: bug-filing handler (referenced by docs)
    _wiki_cosign_bug(...)        → str: cosign handler

Other helpers and action handlers are module-private (single-leading-underscore)
but importable for tests via `workflow.universe_server` re-exports.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflow.api.helpers import (
    _default_universe,
    _find_all_pages,
    _read_text,
    _universe_dir,
    _wiki_drafts_dir,
    _wiki_pages_dir,
    _wiki_root,
)

# Wiki category taxonomy. Expanded 2026-04-13 to stop user-intent content
# (recipes, workflows, personal notes) getting dumped into `research/`
# because the enum didn't offer anything more appropriate. Mirrors the
# canonical list in `wiki-mcp/server.js` — keep the two in lockstep. The
# original four come first for back-compat with existing index headers.
_WIKI_CATEGORIES = (
    "projects",    # Tracked project pages (auto-discovered or hand-written)
    "concepts",    # Ideas, mental models, definitions
    "people",      # Bios, contacts, collaborators
    "research",    # LLM-generated research pages, literature, paper drafts
    "recipes",     # Food recipes and cooking notes
    "workflows",   # User-built workflows, how-tos, repeatable processes
    "notes",       # Personal notes, journal entries, scratch thinking
    "references",  # External references, citations, cheat sheets
    "plans",       # Plans, proposals, roadmaps
    "bugs",        # Auto-filed server defects (one file per BUG-NNN, never drafts-gated)
)

_STOP_WORDS = frozenset(
    "the a an is are was were be been being have has had do does did will would "
    "could should may might shall can need and or but if then else when at by for "
    "with about against between through during before after above below to from in "
    "on of that this these those it its not no nor so very just also".split()
)

_WIKI_SEARCH_COMPLETENESS_WARNING = (
    "wiki action=search is lexical best-effort, not a complete discovery or "
    "change-feed proof. For recent changes use wiki action=since with "
    "changed_since=<ISO timestamp>; for authoritative content read candidate "
    "pages with action=read."
)


_logger_wiki = logging.getLogger("universe_server.wiki")


def _wiki_raw_dir() -> Path:
    return _wiki_root() / "raw"


def _wiki_index_path() -> Path:
    return _wiki_root() / "index.md"


def _wiki_log_path() -> Path:
    return _wiki_root() / "log.md"


def _ensure_wiki_scaffold(wiki_root: Path) -> None:
    """Ensure the wiki tree exists so read/list/search don't error on a
    fresh deploy (Task #6 — post-scrub droplet boot has an empty
    `/data/wiki`).

    Idempotent: every `mkdir` uses `exist_ok=True`; anchor files are
    only written when absent. Safe to call on every `wiki` invocation —
    steady-state cost is ~10 stat calls.

    Creates:
      - `wiki_root` itself + `pages/<cat>/` + `drafts/<cat>/` for every
        entry in `_WIKI_CATEGORIES`.
      - `log/` (matches existing `_wiki_log_path` shape — `.md` file at
        the root, but also reserves the `log/` dir for future per-day
        rollover if the log grows large).
      - `index.md`, `WIKI.md`, `log.md` as minimal anchor pages if they
        don't already exist. Never overwrites user content.
    """
    from datetime import date as _date
    today = _date.today().isoformat()

    wiki_root.mkdir(parents=True, exist_ok=True)
    for base in ("pages", "drafts"):
        for cat in _WIKI_CATEGORIES:
            (wiki_root / base / cat).mkdir(parents=True, exist_ok=True)
    (wiki_root / "log").mkdir(parents=True, exist_ok=True)
    (wiki_root / "raw").mkdir(parents=True, exist_ok=True)

    anchors = {
        "index.md": (
            f"---\ntitle: Index\ntype: index\nupdated: {today}\n---\n\n"
            f"# Wiki Index\n\nWiki seeded {today} by Workflow daemon. "
            "Categories populate as chatbots write. See `log.md` for "
            "recent activity; `bugs/` for active defects.\n"
        ),
        "WIKI.md": (
            f"---\ntitle: Wiki Schema\ntype: schema\nupdated: {today}\n---\n\n"
            "# Wiki Schema\n\nCategories, frontmatter conventions, and "
            "lint rules. See AGENTS.md + the wiki tool docstring for the "
            "live contract.\n"
        ),
        "log.md": (
            "# Wiki Log\n\n"
            f"{today} | scaffold | wiki seeded by Workflow daemon\n"
        ),
    }
    for name, body in anchors.items():
        path = wiki_root / name
        if not path.exists():
            path.write_text(body, encoding="utf-8")


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Parse YAML frontmatter from markdown. Returns (meta, body)."""
    match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
    if not match:
        return {}, content
    meta: dict[str, str] = {}
    lines = match.group(1).split("\n")
    for index, line in enumerate(lines):
        if line and line[0].isspace():
            continue
        idx = line.find(":")
        if idx > 0:
            value = line[idx + 1:].strip()
            if not value:
                block_lines: list[str] = []
                for next_line in lines[index + 1:]:
                    if next_line and not next_line[0].isspace():
                        break
                    stripped = next_line.strip()
                    if stripped:
                        block_lines.append(stripped)
                value = "\n".join(block_lines)
            meta[line[:idx].strip()] = value
    return meta, match.group(2)


def _page_rel_path(filepath: Path) -> str:
    """Return the wiki-relative path for a page."""
    try:
        return filepath.relative_to(_wiki_root()).as_posix()
    except ValueError:
        return filepath.name


def _resolve_page(name: str) -> Path | None:
    """Find a page by name across pages/ and drafts/ subdirectories."""
    clean = name.removesuffix(".md")
    specials = {
        "index": _wiki_index_path(),
        "log": _wiki_log_path(),
        "schema": _wiki_root() / "WIKI.md",
    }
    if clean.lower() in specials:
        p = specials[clean.lower()]
        return p if p.exists() else None

    for base_dir in [_wiki_pages_dir(), _wiki_drafts_dir()]:
        for sub in _WIKI_CATEGORIES:
            fp = base_dir / sub / (clean + ".md")
            if fp.exists():
                return fp

    needle = clean.lower().replace("-", "").replace("_", "").replace(" ", "")
    all_pages = _find_all_pages(_wiki_pages_dir()) + _find_all_pages(_wiki_drafts_dir())
    for p in all_pages:
        base = p.stem.lower().replace("-", "").replace("_", "").replace(" ", "")
        if base == needle or needle in base or base in needle:
            return p

    return None


def _wiki_builtin_link_targets() -> set[str]:
    """Return built-in wiki pages that are valid wikilink targets."""
    targets: set[str] = set()
    for slug in ("index", "log", "schema"):
        if _resolve_page(slug) is not None:
            targets.add(slug)
    return targets


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text."""
    words = re.sub(r"[^a-z0-9\s-]", " ", text.lower()).split()
    return {w for w in words if len(w) > 2 and w not in _STOP_WORDS}


def _wiki_similarity_score(
    meta_a: dict[str, str], body_a: str,
    meta_b: dict[str, str], body_b: str,
) -> float:
    """Compute similarity between two draft pages."""
    kw_a = _extract_keywords(body_a)
    kw_b = _extract_keywords(body_b)
    if not kw_a or not kw_b:
        return 0.0
    overlap = len(kw_a & kw_b)
    jaccard = overlap / (len(kw_a) + len(kw_b) - overlap)

    links_a = {m.lower() for m in re.findall(r"\[\[([^\]]+)\]\]", body_a)}
    links_b = {m.lower() for m in re.findall(r"\[\[([^\]]+)\]\]", body_b)}
    link_overlap = len(links_a & links_b)
    link_score = (
        link_overlap / max(len(links_a), len(links_b))
        if links_a or links_b else 0.0
    )

    slug_a = (meta_a.get("title") or "").lower().replace("-", "").replace("_", "").replace(" ", "")
    slug_b = (meta_b.get("title") or "").lower().replace("-", "").replace("_", "").replace(" ", "")
    title_bonus = 0.3 if slug_a and slug_b and (slug_a in slug_b or slug_b in slug_a) else 0.0

    return jaccard * 0.4 + link_score * 0.3 + title_bonus


def _parse_wiki_timestamp(value: str) -> datetime | None:
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.fromisoformat(f"{raw}T00:00:00+00:00")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _page_updated_at(path: Path, meta: dict[str, str]) -> datetime:
    parsed = _parse_wiki_timestamp(meta.get("updated", ""))
    if parsed is not None:
        return parsed
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _wiki_read_terms(
    *,
    page: str,
    query: str,
    meta: dict[str, str],
    body: str,
) -> set[str]:
    text = query.strip()
    if not text:
        text = " ".join(
            part for part in (
                page,
                meta.get("title", ""),
                meta.get("tags", ""),
                meta.get("type", ""),
                body[:1200],
            ) if part
        )
    return _extract_keywords(text)


def _coerce_feed_limit(value: Any) -> int:
    try:
        raw = int(value or 0)
    except (TypeError, ValueError):
        raw = 10
    return max(0, min(raw, 20))


def _coerce_result_limit(value: Any) -> int:
    try:
        raw = int(value or 0)
    except (TypeError, ValueError):
        raw = 10
    return max(1, min(raw, 100))


def _ambient_relevance_feed(
    *,
    source: Path,
    page: str,
    query: str,
    changed_since: str,
    max_results: int,
    source_meta: dict[str, str],
    source_body: str,
) -> dict[str, Any]:
    terms = _wiki_read_terms(
        page=page,
        query=query,
        meta=source_meta,
        body=source_body,
    )
    since = _parse_wiki_timestamp(changed_since)
    limit = _coerce_feed_limit(max_results)
    candidates: list[dict[str, Any]] = []
    for candidate in (
        _find_all_pages(_wiki_pages_dir()) + _find_all_pages(_wiki_drafts_dir())
    ):
        if candidate == source:
            continue
        raw = _read_text(candidate)
        if not raw:
            continue
        meta, body = _parse_frontmatter(raw)
        updated_at = _page_updated_at(candidate, meta)
        if since is not None and updated_at <= since:
            continue
        haystack = " ".join(
            part for part in (
                meta.get("title", ""),
                meta.get("tags", ""),
                meta.get("type", ""),
                body,
            ) if part
        ).lower()
        matched_terms = sorted(term for term in terms if term in haystack)
        if not matched_terms:
            continue
        title = meta.get("title") or candidate.stem
        excerpt = body.replace("\n", " ").strip()[:220]
        candidates.append({
            "path": _page_rel_path(candidate),
            "title": title,
            "updated": updated_at.isoformat().replace("+00:00", "Z"),
            "matched_terms": matched_terms[:8],
            "score": len(matched_terms),
            "excerpt": excerpt,
        })

    candidates.sort(key=lambda item: (-item["score"], item["path"]))
    items = candidates[:limit]
    return {
        "source_path": _page_rel_path(source),
        "query_terms": sorted(terms)[:20],
        "changed_since": changed_since.strip(),
        "items": items,
        "truncated_count": max(0, len(candidates) - len(items)),
    }


def _add_to_index(category: str, slug: str, title: str) -> None:
    """Add an entry to the wiki index.md under the right section."""
    idx_path = _wiki_index_path()
    if not idx_path.exists():
        return
    idx = idx_path.read_text(encoding="utf-8")
    if f"[[{slug}]]" in idx:
        return
    header_map = {
        "projects": "## Projects",
        "concepts": "## Concepts",
        "people": "## People",
        "research": "## Research",
        "recipes": "## Recipes",
        "workflows": "## Workflows",
        "notes": "## Notes",
        "references": "## References",
        "plans": "## Plans",
    }
    hdr = header_map.get(category)
    if not hdr:
        return
    entry = f"- [[{slug}]] -- {title or slug}"
    lines = idx.split("\n")
    insert_at = -1
    in_section = False
    for i, line in enumerate(lines):
        if line.startswith(hdr):
            in_section = True
            insert_at = i + 1
        elif in_section and line.startswith("## "):
            break
        elif in_section and line.startswith("- "):
            insert_at = i + 1
    if insert_at > 0:
        lines.insert(insert_at, entry)
        idx_path.write_text("\n".join(lines), encoding="utf-8")


def _append_wiki_log(msg: str) -> None:
    """Append an entry to the wiki log."""
    log_path = _wiki_log_path()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n## [{today}] {msg}\n")
    except OSError:
        pass


def _sanitize_slug(name: str) -> str:
    """Convert a filename into a safe wiki slug."""
    clean = name.removesuffix(".md")
    return re.sub(r"[^a-z0-9-]", "-", clean.lower()).strip("-")


def _resolve_bugs_canonical(parent: Path, slug: str) -> Path | None:
    """Find the canonical bugs/<slug>.md path, preferring uppercase + trailing-hyphen variants.

    Three corner cases this resolves:

    1. **Direct case-sensitive hit on the slug.** If `<slug>.md` exists, it's
       canonical only when there's no uppercase sibling that lowercases to it
       (BUG-003 fix: lowercase duplicate must NOT win when an uppercase BUG
       canonical exists).
    2. **Wrong-case canonical** (BUG-028). e.g. slug=`bug-007-foo`, canonical
       on disk is `BUG-007-foo.md` — match the canonical.
    3. **Trailing-hyphen canonical** (BUG-018). The slug sanitizer strips
       trailing hyphens; if the canonical filename actually has one, match
       `<slug>-.md` (case-insensitive).

    Returns the resolved canonical Path, or None if no match.
    Preference order when multiple candidates match:
      uppercase BUG-prefix > exact-case > anything else
    """
    direct = parent / (slug + ".md")
    direct_dash = parent / (slug + "-.md")

    candidates: list[Path] = []
    for candidate in parent.glob("*.md"):
        cstem = candidate.stem
        if cstem.lower() == slug or cstem.lower() == slug + "-":
            candidates.append(candidate)

    if not candidates:
        return None

    def _rank(p: Path) -> tuple[int, int, str]:
        name = p.name
        # Lower number wins. Prefer uppercase BUG-prefix (canonical convention)
        # then prefer exact slug-name match over trailing-hyphen variant.
        is_upper_bug = 0 if name.startswith("BUG-") else 1
        is_exact = 0 if p == direct else (1 if p == direct_dash else 2)
        return (is_upper_bug, is_exact, name)

    candidates.sort(key=_rank)
    return candidates[0]


# ---------------------------------------------------------------------------
# Wiki action implementations
# ---------------------------------------------------------------------------


def _wiki_read(
    page: str = "",
    query: str = "",
    changed_since: str = "",
    max_results: int = 10,
    **_kwargs: Any,
) -> str:
    if not page:
        return json.dumps({"error": "page parameter is required."})

    resolved = _resolve_page(page)
    if resolved is None:
        return json.dumps({"error": f"Page not found: {page}"})

    text = _read_text(resolved)
    is_draft = _wiki_drafts_dir() in resolved.parents
    rel = _page_rel_path(resolved)
    meta, body = _parse_frontmatter(text)
    updated_at = _page_updated_at(resolved, meta)
    content = _draft_read_content(text, is_draft=is_draft)
    source_read_proof = {
        "path": rel,
        "title": meta.get("title") or resolved.stem,
        "updated": updated_at.isoformat().replace("+00:00", "Z"),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "is_draft": is_draft,
    }
    ambient_feed = _ambient_relevance_feed(
        source=resolved,
        page=page,
        query=query,
        changed_since=changed_since,
        max_results=max_results,
        source_meta=meta,
        source_body=body,
    )

    if len(text) > 15000:
        return json.dumps({
            "path": rel,
            "is_draft": is_draft,
            "content": content[:15000],
            "truncated": True,
            "total_chars": len(text),
            "source_read_proof": source_read_proof,
            "ambient_relevance_feed": ambient_feed,
        })
    return json.dumps({
        "path": rel,
        "is_draft": is_draft,
        "content": content,
        "truncated": False,
        "source_read_proof": source_read_proof,
        "ambient_relevance_feed": ambient_feed,
    })


def _draft_read_content(text: str, *, is_draft: bool) -> str:
    if not is_draft or text.startswith("[DRAFT]"):
        return text
    return "[DRAFT] " + text


def _wiki_search(query: str = "", max_results: int = 10, **_kwargs: Any) -> str:
    if not query:
        return json.dumps({"error": "query parameter is required."})

    all_pages = (
        _find_all_pages(_wiki_pages_dir()) + _find_all_pages(_wiki_drafts_dir())
    )
    terms = query.lower().split()
    scored: list[dict[str, Any]] = []

    for p in all_pages:
        raw = _read_text(p)
        if not raw:
            continue
        lower = raw.lower()
        meta, body = _parse_frontmatter(raw)
        title = meta.get("title", p.stem)
        is_draft = _wiki_drafts_dir() in p.parents

        score = 0
        for t in terms:
            if t in title.lower():
                score += 10
            score += lower.count(t)

        if score > 0:
            excerpt = ""
            body_lower = body.lower()
            for t in terms:
                ti = body_lower.find(t)
                if ti >= 0:
                    start = max(0, ti - 80)
                    end = min(len(body), ti + len(t) + 80)
                    excerpt = "..." + body[start:end].replace("\n", " ").strip() + "..."
                    break
            scored.append({
                "path": _page_rel_path(p),
                "title": ("[DRAFT] " if is_draft else "") + title,
                "score": score,
                "excerpt": excerpt,
            })

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:max_results]

    if not top:
        return json.dumps({
            "results": [],
            "note": f"No results for: {query}",
            "search_complete": False,
            "completeness_warning": _WIKI_SEARCH_COMPLETENESS_WARNING,
        })
    return json.dumps({
        "query": query,
        "results": top,
        "count": len(top),
        "search_complete": False,
        "completeness_warning": _WIKI_SEARCH_COMPLETENESS_WARNING,
    })


def _wiki_result_item(path: Path, *, is_draft: bool) -> dict[str, Any]:
    raw = _read_text(path)
    meta, body = _parse_frontmatter(raw)
    updated_at = _page_updated_at(path, meta)
    return {
        "path": _page_rel_path(path),
        "title": meta.get("title") or path.stem,
        "type": meta.get("type", "unknown"),
        "updated": updated_at.isoformat().replace("+00:00", "Z"),
        "is_draft": is_draft,
        "excerpt": body.replace("\n", " ").strip()[:220],
    }


def _wiki_since(
    changed_since: str = "",
    max_results: int = 10,
    **_kwargs: Any,
) -> str:
    if not changed_since.strip():
        return json.dumps({
            "error": "changed_since parameter is required for action=since.",
            "hint": "Pass an ISO timestamp, for example 2026-05-06T00:00:00Z.",
        })
    since = _parse_wiki_timestamp(changed_since)
    if since is None:
        return json.dumps({
            "error": "changed_since must be a valid ISO timestamp.",
            "changed_since": changed_since,
        })

    candidates: list[dict[str, Any]] = []
    for path in _find_all_pages(_wiki_pages_dir()):
        item = _wiki_result_item(path, is_draft=False)
        updated_at = _parse_wiki_timestamp(item["updated"])
        if updated_at is not None and updated_at > since:
            candidates.append(item)
    for path in _find_all_pages(_wiki_drafts_dir()):
        item = _wiki_result_item(path, is_draft=True)
        updated_at = _parse_wiki_timestamp(item["updated"])
        if updated_at is not None and updated_at > since:
            candidates.append(item)

    candidates.sort(key=lambda item: (item["updated"], item["path"]), reverse=True)
    limit = _coerce_result_limit(max_results)
    results = candidates[:limit]
    return json.dumps({
        "changed_since": changed_since.strip(),
        "results": results,
        "count": len(results),
        "total_matches": len(candidates),
        "truncated_count": max(0, len(candidates) - len(results)),
    })


def _wiki_list(**_kwargs: Any) -> str:
    promoted = _find_all_pages(_wiki_pages_dir())
    drafts = _find_all_pages(_wiki_drafts_dir())

    pages_list: list[dict[str, Any]] = []
    for p in promoted:
        raw = _read_text(p)
        meta, _ = _parse_frontmatter(raw)
        pages_list.append({
            "path": _page_rel_path(p),
            "title": meta.get("title", p.stem),
            "type": meta.get("type", "unknown"),
            "confidence": meta.get("confidence", ""),
            "is_draft": False,
        })

    drafts_list: list[dict[str, Any]] = []
    for p in drafts:
        raw = _read_text(p)
        meta, _ = _parse_frontmatter(raw)
        drafts_list.append({
            "path": _page_rel_path(p),
            "title": meta.get("title", p.stem),
            "type": meta.get("type", "unknown"),
            "is_draft": True,
        })

    return json.dumps({
        "promoted": pages_list,
        "promoted_count": len(pages_list),
        "drafts": drafts_list,
        "drafts_count": len(drafts_list),
    })


def _wiki_write(
    category: str = "",
    filename: str = "",
    content: str = "",
    log_entry: str = "",
    **_kwargs: Any,
) -> str:
    if not filename or not content:
        return json.dumps({"error": "filename and content are required."})
    if category not in _WIKI_CATEGORIES:
        return json.dumps({
            "error": f"Invalid category '{category}'.",
            "valid": list(_WIKI_CATEGORIES),
        })

    slug = _sanitize_slug(filename)
    promoted_path = _wiki_pages_dir() / category / (slug + ".md")

    # Alias-resolution for the bugs category. Runs BEFORE the .exists() check
    # so a pre-existing lowercase-duplicate (BUG-003) or trailing-hyphen
    # canonical (BUG-018) cannot bypass canonical-preferring resolution.
    #
    # BUG-003: lowercase duplicate already exists alongside an uppercase
    # canonical → we must prefer the uppercase canonical.
    # BUG-028: file_bug filename is lowercase but a wrong-case canonical
    # already exists → resolve to canonical.
    # BUG-018: canonical filename has a trailing hyphen the slug sanitizer
    # strips → match a "<slug>-.md" sibling as the canonical.
    if category == _BUGS_CATEGORY:
        parent = _wiki_pages_dir() / category
        if parent.is_dir():
            canonical = _resolve_bugs_canonical(parent, slug)
            if canonical is not None and canonical != promoted_path:
                _logger_wiki.warning(
                    "wiki write alias: '%s' resolved to canonical '%s'. "
                    "Rename '%s' → '%s' (or remove duplicate) to eliminate.",
                    slug + ".md",
                    canonical.name,
                    canonical.name if canonical.name != (slug + ".md") else slug,
                    slug + ".md",
                )
                promoted_path = canonical

    if promoted_path.exists():
        try:
            promoted_path.write_text(content, encoding="utf-8")
            _append_wiki_log(
                f"update | pages/{category}/{slug} | {log_entry or 'in-place update'}"
            )
            return json.dumps({
                "path": f"pages/{category}/{slug}.md",
                "status": "updated",
                "note": "Updated existing promoted page in-place.",
            })
        except OSError as exc:
            return json.dumps({"error": f"Failed to write: {exc}"})

    draft_path = _wiki_drafts_dir() / category / (slug + ".md")
    try:
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not draft_path.exists()
        draft_path.write_text(content, encoding="utf-8")
        action_word = "draft" if is_new else "draft-update"
        _append_wiki_log(
            f"{action_word} | drafts/{category}/{slug} | {log_entry or 'new draft'}"
        )
        return json.dumps({
            "path": f"drafts/{category}/{slug}.md",
            "status": "drafted" if is_new else "updated",
            "note": (
                f"{'Drafted' if is_new else 'Updated draft'}: "
                "call wiki promote to move to pages/."
            ),
        })
    except OSError as exc:
        return json.dumps({"error": f"Failed to write draft: {exc}"})


def _wiki_patch(
    page: str = "",
    old_text: str = "",
    new_text: str = "",
    expected_sha256: str = "",
    log_entry: str = "",
    dry_run: bool = True,
    **_kwargs: Any,
) -> str:
    if not page:
        return json.dumps({"error": "page parameter is required."})
    if not old_text:
        return json.dumps({"error": "old_text parameter is required."})

    resolved = _resolve_page(page)
    if resolved is None:
        return json.dumps({"error": f"Page not found: {page}"})

    text = _read_text(resolved)
    old_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    rel = _page_rel_path(resolved)

    if expected_sha256 and expected_sha256 != old_sha:
        return json.dumps({
            "error": "content hash mismatch",
            "status": "conflict",
            "path": rel,
            "expected_sha256": expected_sha256,
            "actual_sha256": old_sha,
        })

    matches = text.count(old_text)
    if matches != 1:
        return json.dumps({
            "error": "old_text must match exactly once",
            "status": "conflict",
            "path": rel,
            "matches": matches,
            "sha256": old_sha,
        })

    patched = text.replace(old_text, new_text, 1)
    new_sha = hashlib.sha256(patched.encode("utf-8")).hexdigest()
    response = {
        "path": rel,
        "matches": matches,
        "old_sha256": old_sha,
        "new_sha256": new_sha,
        "old_total_chars": len(text),
        "new_total_chars": len(patched),
    }

    if dry_run:
        response.update({"status": "dry_run", "would_write": old_sha != new_sha})
        return json.dumps(response)

    try:
        resolved.write_text(patched, encoding="utf-8")
        _append_wiki_log(f"patch | {rel} | {log_entry or 'exact replacement'}")
        response.update({"status": "patched"})
        return json.dumps(response)
    except OSError as exc:
        return json.dumps({"error": f"Failed to patch: {exc}"})


def _wiki_consolidate(
    similarity_threshold: float = 0.25,
    dry_run: bool = True,
    **_kwargs: Any,
) -> str:
    all_drafts = _find_all_pages(_wiki_drafts_dir())
    if len(all_drafts) < 2:
        return json.dumps({"note": "Fewer than 2 drafts, nothing to consolidate."})

    parsed: list[dict[str, Any]] = []
    for dp in all_drafts:
        raw = _read_text(dp)
        meta, body = _parse_frontmatter(raw)
        parsed.append({
            "path": dp,
            "rel_path": _page_rel_path(dp),
            "raw": raw,
            "meta": meta,
            "body": body,
        })

    merged: set[int] = set()
    clusters: list[list[int]] = []
    for i in range(len(parsed)):
        if i in merged:
            continue
        cluster = [i]
        for j in range(i + 1, len(parsed)):
            if j in merged:
                continue
            score = _wiki_similarity_score(
                parsed[i]["meta"], parsed[i]["body"],
                parsed[j]["meta"], parsed[j]["body"],
            )
            if score >= similarity_threshold:
                cluster.append(j)
                merged.add(j)
        if len(cluster) > 1:
            merged.add(i)
            clusters.append(cluster)

    if not clusters:
        return json.dumps({
            "note": f"No similar drafts found at threshold {similarity_threshold}.",
        })

    report: list[str] = []
    for cl in clusters:
        names = [parsed[idx]["rel_path"] for idx in cl]
        report.append(f"Cluster: {' + '.join(names)}")
        if not dry_run:
            cl.sort(key=lambda idx: len(parsed[idx]["body"]), reverse=True)
            primary = parsed[cl[0]]
            sections = [primary["raw"]]
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for k in range(1, len(cl)):
                secondary = parsed[cl[k]]
                sections.append(
                    f"\n\n---\n*Consolidated from {secondary['rel_path']} "
                    f"on {today}*\n\n{secondary['body']}"
                )
                try:
                    secondary["path"].unlink()
                except OSError:
                    pass
            try:
                primary["path"].write_text("".join(sections), encoding="utf-8")
            except OSError:
                pass
            report.append(
                f"  -> Merged into {primary['rel_path']}, "
                f"removed {len(cl) - 1} duplicate(s)"
            )

    return json.dumps({
        "mode": "dry_run" if dry_run else "executed",
        "clusters": len(clusters),
        "report": report,
    })


def _wiki_promote(
    filename: str = "",
    category: str = "",
    skip_lint: bool = False,
    **_kwargs: Any,
) -> str:
    if not filename:
        return json.dumps({"error": "filename is required."})

    slug = _sanitize_slug(filename)
    draft_path: Path | None = None
    found_category = category

    if category:
        p = _wiki_drafts_dir() / category / (slug + ".md")
        if p.exists():
            draft_path = p
    else:
        for cat in _WIKI_CATEGORIES:
            p = _wiki_drafts_dir() / cat / (slug + ".md")
            if p.exists():
                draft_path = p
                found_category = cat
                break

    if not draft_path:
        return json.dumps({
            "error": f"Draft not found: {slug}.",
            "hint": "Use wiki list to see available drafts.",
        })

    content = _read_text(draft_path)
    meta, body = _parse_frontmatter(content)

    if not skip_lint:
        issues = _promotion_lint_issues(meta, body, found_category)
        if issues:
            return json.dumps({
                "error": "Promotion blocked.",
                "issues": issues,
                "hint": "Fix these issues or set skip_lint=true.",
            })

    dest_path = _wiki_pages_dir() / found_category / (slug + ".md")
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if "updated:" in content:
            content = re.sub(r"updated:.*", f"updated: {today}", content)
        dest_path.write_text(content, encoding="utf-8")
        draft_path.unlink()
        _add_to_index(found_category, slug, meta.get("title", slug))
        _append_wiki_log(
            f"promote | {found_category}/{slug} | moved from drafts to pages"
        )
        return json.dumps({
            "path": f"pages/{found_category}/{slug}.md",
            "status": "promoted",
        })
    except OSError as exc:
        return json.dumps({"error": f"Failed to promote: {exc}"})


def _wiki_ingest(
    filename: str = "",
    content: str = "",
    source_url: str = "",
    **_kwargs: Any,
) -> str:
    if not filename or not content:
        return json.dumps({"error": "filename and content are required."})

    raw_dir = _wiki_raw_dir()
    try:
        raw_dir.mkdir(parents=True, exist_ok=True)
        target = raw_dir / Path(filename).name
        target.write_text(content, encoding="utf-8")
        url_note = f" ({source_url})" if source_url else ""
        _append_wiki_log(f"ingest | {filename}{url_note}")
        return json.dumps({
            "path": f"raw/{target.name}",
            "status": "saved",
            "note": "Saved to raw/. Now call wiki write to create a synthesis page in drafts/.",
        })
    except OSError as exc:
        return json.dumps({"error": f"Failed to ingest: {exc}"})


def _wiki_supersede(
    old_page: str = "",
    new_draft: str = "",
    reason: str = "",
    **_kwargs: Any,
) -> str:
    if not old_page or not new_draft or not reason:
        return json.dumps({"error": "old_page, new_draft, and reason are required."})

    old_slug = _sanitize_slug(old_page)
    new_slug = _sanitize_slug(new_draft)

    old_path: Path | None = None
    old_category = ""
    for cat in _WIKI_CATEGORIES:
        p = _wiki_pages_dir() / cat / (old_slug + ".md")
        if p.exists():
            old_path = p
            old_category = cat
            break
    if not old_path:
        return json.dumps({"error": f"Old page not found in pages/: {old_slug}"})

    new_exists = False
    for cat in _WIKI_CATEGORIES:
        p = _wiki_drafts_dir() / cat / (new_slug + ".md")
        if p.exists():
            new_exists = True
            break
    if not new_exists:
        return json.dumps({
            "error": f"Replacement draft not found in drafts/: {new_slug}.",
            "hint": "Write the replacement first with wiki write.",
        })

    try:
        old_content = old_path.read_text(encoding="utf-8")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if "confidence:" in old_content:
            old_content = re.sub(r"confidence:.*", "confidence: superseded", old_content)
        else:
            old_content = old_content.replace(
                "\n---\n", "\nconfidence: superseded\n---\n", 1
            )

        if "superseded_by:" in old_content:
            old_content = re.sub(r"superseded_by:.*", f"superseded_by: {new_slug}", old_content)
        else:
            old_content = old_content.replace(
                "\n---\n", f"\nsuperseded_by: {new_slug}\n---\n", 1
            )

        old_content = re.sub(r"updated:.*", f"updated: {today}", old_content)

        fm_match = re.match(r"^(---\n.*?\n---\n)(.*)", old_content, re.DOTALL)
        if fm_match:
            notice = (
                f"> **Superseded** on {today} by [[{new_slug}]]. "
                f"Reason: {reason}\n\n"
            )
            body = re.sub(r"^> \*\*Superseded\*\*.*\n\n", "", fm_match.group(2))
            old_content = fm_match.group(1) + notice + body

        old_path.write_text(old_content, encoding="utf-8")
        _append_wiki_log(
            f"supersede | {old_category}/{old_slug} -> {new_slug} | {reason}"
        )
        return json.dumps({
            "status": "superseded",
            "old_page": old_slug,
            "new_draft": new_slug,
            "note": f"Superseded {old_slug}. Now call wiki promote on {new_slug}.",
        })
    except OSError as exc:
        return json.dumps({"error": f"Failed to supersede: {exc}"})


def _promotion_lint_issues(
    meta: dict[str, str],
    body: str,
    category: str,
) -> list[str]:
    issues: list[str] = []
    if not meta.get("title"):
        issues.append("Missing title in frontmatter")
    if not meta.get("type"):
        issues.append("Missing type in frontmatter")
    if not meta.get("sources") and not meta.get("path"):
        issues.append("Missing sources in frontmatter")
    if len(body.strip()) < 50:
        issues.append("Body too short (< 50 chars)")
    if not re.search(r"\[\[.+?\]\]", body) and category != "projects":
        issues.append(
            "No wikilinks found -- pages should cross-reference; use [[index]] "
            "for the first page in a fresh wiki"
        )
    return issues


def _wiki_lint_single_page(page: str) -> str:
    resolved = _resolve_page(page)
    if resolved is None:
        return json.dumps({"error": f"Page not found: {page}"})

    rel = _page_rel_path(resolved)
    is_draft = _wiki_drafts_dir() in resolved.parents
    category = resolved.parent.name
    raw = _read_text(resolved)
    meta, body = _parse_frontmatter(raw)
    page_name = resolved.stem
    page_names = {p.stem for p in _find_all_pages(_wiki_pages_dir())}
    link_targets = page_names | _wiki_builtin_link_targets()
    issues: list[str] = []

    for m in re.findall(r"\[\[([^\]]+)\]\]", raw):
        link = m.lower().replace(" ", "-")
        if link not in link_targets:
            issues.append(f"MISSING: [[{link}]]")

    if is_draft:
        issues.extend(_promotion_lint_issues(meta, body, category))
    else:
        idx_content = _read_text(_wiki_index_path())
        indexed = {
            m.lower().replace(" ", "-")
            for m in re.findall(r"\[\[([^\]]+)\]\]", idx_content)
        }
        inbound = 0
        for p in _find_all_pages(_wiki_pages_dir()):
            if p == resolved:
                continue
            for m in re.findall(r"\[\[([^\]]+)\]\]", _read_text(p)):
                link = m.lower().replace(" ", "-")
                if link == page_name:
                    inbound += 1

        if inbound == 0 and page_name not in indexed:
            issues.append(f"ORPHAN: {page_name}")
        if page_name not in indexed:
            issues.append(f"NOT INDEXED: {page_name}")

        _append_page_metadata_lint(issues, page_name, meta)

    if not issues:
        return json.dumps({"status": "healthy", "page": rel, "issues": []})
    return json.dumps({
        "status": "issues_found",
        "page": rel,
        "count": len(issues),
        "issues": issues,
    })


def _append_page_metadata_lint(
    issues: list[str],
    page_name: str,
    meta: dict[str, str],
) -> None:
    now = datetime.now(timezone.utc)
    confidence = (meta.get("confidence") or "").strip().lower()
    updated_str = meta.get("updated")
    days_since: int | None = None
    if updated_str:
        try:
            updated_date = datetime.fromisoformat(updated_str).replace(
                tzinfo=timezone.utc
            )
            days_since = (now - updated_date).days
        except ValueError:
            pass

    if confidence == "superseded":
        successor = (meta.get("superseded_by") or "").strip()
        if successor and successor not in {
            p.stem for p in _find_all_pages(_wiki_pages_dir())
        }:
            issues.append(
                f"BROKEN SUPERSESSION: {page_name} points to "
                f"[[{successor}]] which does not exist"
            )
        return

    if (
        (not confidence or confidence == "high")
        and days_since is not None
        and days_since > 90
    ):
        issues.append(f"STALE HIGH: {page_name} (last updated {days_since} days ago)")
    if confidence == "low" and days_since is not None and days_since > 30:
        issues.append(
            f"LINGERING LOW: {page_name} (confidence: low for {days_since} days)"
        )
    if not confidence and meta.get("title"):
        issues.append(f"NO CONFIDENCE: {page_name}")
    if (
        not meta.get("sources")
        and not meta.get("path")
        and meta.get("type") != "project"
    ):
        issues.append(f"NO SOURCES: {page_name}")


def _wiki_lint(page: str = "", **_kwargs: Any) -> str:
    if page:
        return _wiki_lint_single_page(page)

    all_pages = _find_all_pages(_wiki_pages_dir())
    all_drafts = _find_all_pages(_wiki_drafts_dir())
    page_names: set[str] = set()
    inbound: dict[str, int] = {}
    all_linked: set[str] = set()

    for p in all_pages:
        name = p.stem
        page_names.add(name)
        raw = _read_text(p)
        for m in re.findall(r"\[\[([^\]]+)\]\]", raw):
            link = m.lower().replace(" ", "-")
            inbound[link] = inbound.get(link, 0) + 1
            all_linked.add(link)

    idx_content = _read_text(_wiki_index_path())
    indexed: set[str] = set()
    for m in re.findall(r"\[\[([^\]]+)\]\]", idx_content):
        indexed.add(m.lower().replace(" ", "-"))

    issues: list[str] = []
    link_targets = page_names | _wiki_builtin_link_targets()

    for n in page_names:
        if inbound.get(n, 0) == 0 and n not in indexed:
            issues.append(f"ORPHAN: {n}")
    for link in all_linked:
        if link not in link_targets:
            issues.append(f"MISSING: [[{link}]]")
    for n in page_names:
        if n not in indexed:
            issues.append(f"NOT INDEXED: {n}")
    for n in indexed:
        if n not in page_names:
            issues.append(f"INDEX GHOST: [[{n}]]")

    now = datetime.now(timezone.utc)
    superseded_count = 0

    for p in all_pages:
        raw = _read_text(p)
        meta, _ = _parse_frontmatter(raw)
        page_name = p.stem
        confidence = (meta.get("confidence") or "").strip().lower()
        updated_str = meta.get("updated")
        days_since: int | None = None
        if updated_str:
            try:
                updated_date = datetime.fromisoformat(updated_str).replace(
                    tzinfo=timezone.utc
                )
                days_since = (now - updated_date).days
            except ValueError:
                pass

        if confidence == "superseded":
            superseded_count += 1
            successor = (meta.get("superseded_by") or "").strip()
            if successor and successor not in page_names:
                issues.append(
                    f"BROKEN SUPERSESSION: {page_name} points to "
                    f"[[{successor}]] which does not exist"
                )
        else:
            if (
                (not confidence or confidence == "high")
                and days_since is not None
                and days_since > 90
            ):
                issues.append(
                    f"STALE HIGH: {page_name} (last updated {days_since} days ago)"
                )
            if confidence == "low" and days_since is not None and days_since > 30:
                issues.append(
                    f"LINGERING LOW: {page_name} (confidence: low for {days_since} days)"
                )
            if not confidence and meta.get("title"):
                issues.append(f"NO CONFIDENCE: {page_name}")
            if (
                not meta.get("sources")
                and not meta.get("path")
                and meta.get("type") != "project"
            ):
                issues.append(f"NO SOURCES: {page_name}")

    if superseded_count:
        issues.append(
            f"SUPERSEDED: {superseded_count} page(s) marked superseded"
        )

    if all_drafts:
        issues.append(f"DRAFTS PENDING: {len(all_drafts)} draft(s) awaiting promotion")
        for d in all_drafts:
            issues.append(f"  draft: {_page_rel_path(d)}")

    if not issues:
        return json.dumps({"status": "healthy", "issues": []})
    return json.dumps({"status": "issues_found", "count": len(issues), "issues": issues})


def _wiki_sync_projects(**_kwargs: Any) -> str:
    projects_root = _wiki_root().parent
    skip_dirs = {"Wiki", "wiki-mcp", ".git", "node_modules"}
    pp_dir = _wiki_pages_dir() / "projects"

    try:
        pp_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return json.dumps({"error": f"Cannot create projects dir: {exc}"})

    if not projects_root.is_dir():
        return json.dumps({"error": f"Projects root not found: {projects_root}"})

    dirs = [
        d.name for d in sorted(projects_root.iterdir())
        if d.is_dir() and d.name not in skip_dirs and not d.name.startswith(".")
    ]

    existing: dict[str, str] = {}
    for f in pp_dir.iterdir():
        if f.suffix == ".md" and f.is_file():
            raw = _read_text(f)
            meta, _ = _parse_frontmatter(raw)
            page_path = meta.get("path", "")
            if page_path:
                existing[Path(page_path.replace("\\", "/")).name] = f.stem
            existing[f.stem] = f.stem

    fresh: list[str] = []
    for d in dirs:
        slug = re.sub(r"[^a-z0-9]+", "-", d.lower()).strip("-")
        if d not in existing and slug not in existing:
            fresh.append(d)

    if not fresh:
        return json.dumps({"note": "All projects already in wiki.", "synced": 0})

    created: list[str] = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for d in fresh:
        slug = re.sub(r"[^a-z0-9]+", "-", d.lower()).strip("-")
        title = d.replace("-", " ").replace("_", " ").title()
        pp = projects_root / d

        desc = ""
        for df in ["README.md", "CLAUDE.md", "PLAN.md"]:
            dp = pp / df
            if dp.exists():
                try:
                    file_content = dp.read_text(encoding="utf-8")
                    for line in file_content.split("\n"):
                        tr = line.strip()
                        if (
                            tr
                            and not tr.startswith("#")
                            and not tr.startswith("---")
                            and not tr.startswith("@")
                            and len(tr) > 10
                        ):
                            desc = tr[:200]
                            break
                except OSError:
                    pass
                break

        tags = ["auto-discovered"]
        try:
            pf = [f.name for f in pp.iterdir()]
        except OSError:
            pf = []
        if "pyproject.toml" in pf or "requirements.txt" in pf:
            tags.append("python")
        if "package.json" in pf:
            tags.append("node")
        if "Cargo.toml" in pf:
            tags.append("rust")
        if "project.godot" in pf:
            tags.append("godot")
        if "AGENTS.md" in pf:
            tags.append("multi-agent")

        page_content = (
            f"---\ntitle: {title}\ntype: project\ncreated: {today}\n"
            f"updated: {today}\nsources: []\ntags: [{', '.join(tags)}]\n"
            f"path: {pp}\n---\n\n# {title}\n\n"
            f"{desc or '(Auto-discovered project.)'}\n\n"
            f"## See Also\n\n- [[workflow-engine]]\n"
        )

        try:
            (pp_dir / (slug + ".md")).write_text(page_content, encoding="utf-8")
            _add_to_index("projects", slug, title)
            created.append(f"{slug} (from {d})")
        except OSError:
            pass

    if created:
        _append_wiki_log(
            f"sync | Auto-discovered {len(created)} project(s) | "
            f"Created: {', '.join(created)}"
        )
    return json.dumps({
        "synced": len(created),
        "created": created,
    })


# ---------------------------------------------------------------------------
# Bug-filing helper — _wiki_file_bug
# ---------------------------------------------------------------------------

_BUG_ID_RE = re.compile(r"^BUG-(\d{3,})", re.IGNORECASE)
_BUGS_CATEGORY = "bugs"
_KIND_FEATURES_DIR = "feature-requests"
_KIND_DESIGNS_DIR = "design-proposals"
_KIND_PATCH_REQUESTS_DIR = "patch-requests"
_VALID_SEVERITIES = ("critical", "major", "minor", "cosmetic")

# Per-kind routing: kind -> (category-dir-name, ID-prefix). Each prefix has its
# own independent NNN counter. New filings route per kind; existing pages stay
# put (no migration). Default kind="bug" preserves the historical pages/bugs/
# location and BUG-NNN sequence — backward-compat clean.
_KIND_ROUTING: dict[str, tuple[str, str]] = {
    "bug":           (_BUGS_CATEGORY,           "BUG"),
    "feature":       (_KIND_FEATURES_DIR,       "FEAT"),
    "design":        (_KIND_DESIGNS_DIR,        "DESIGN"),
    "patch_request": (_KIND_PATCH_REQUESTS_DIR, "PR"),
}


def _next_id(pages_dir: Path, drafts_dir: Path, prefix: str) -> str:
    """Allocate the next ``<PREFIX>-NNN`` id for a kind's directory pair.

    Scans both ``pages_dir`` and ``drafts_dir`` so concurrent writes don't
    collide with an already-promoted entry. Returns ``<PREFIX>-001`` when
    both dirs are empty or missing. Glob is case-insensitive via *.md plus a
    prefix-anchored regex filter.
    """
    pat = re.compile(rf"^{re.escape(prefix)}-(\d{{3,}})", re.IGNORECASE)
    seen: set[int] = set()
    for base in (pages_dir, drafts_dir):
        if not base.is_dir():
            continue
        for p in base.glob("*.md"):
            m = pat.match(p.stem)
            if m:
                try:
                    seen.add(int(m.group(1)))
                except ValueError:
                    continue
    next_n = (max(seen) + 1) if seen else 1
    return f"{prefix}-{next_n:03d}"


def _next_bug_id(bugs_pages_dir: Path) -> str:
    """Backward-compat wrapper preserving the original BUG-NNN signature.

    Existing call sites that pass only the pages dir still work; the drafts
    dir is resolved internally to keep behavior identical to the prior
    implementation.
    """
    return _next_id(
        bugs_pages_dir, _wiki_drafts_dir() / _BUGS_CATEGORY, "BUG"
    )


def _slugify_title(title: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:max_len] or "untitled"


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
    kind: str = "bug",
    extra_tags: list[str] | None = None,
) -> str:
    comp_tag = component.split(".")[0] if component else "unknown"
    base_tags = [kind, comp_tag]
    if extra_tags:
        base_tags.extend(t for t in extra_tags if t not in base_tags)
    tags_str = ", ".join(base_tags)
    return (
        f"---\n"
        f"id: {bug_id}\n"
        f"title: {title}\n"
        f"type: {kind}\n"
        f"kind: {kind}\n"
        f"created: {first_seen_date}\n"
        f"updated: {first_seen_date}\n"
        f"component: {component}\n"
        f"severity: {severity}\n"
        f"status: open\n"
        f"reported_by: chatbot\n"
        f"tags: [{tags_str}]\n"
        f"---\n\n"
        f"# {bug_id}: {title}\n\n"
        f"## What happened\n\n{observed or '_not specified_'}\n\n"
        f"## What was expected\n\n{expected or '_not specified_'}\n\n"
        f"## Repro\n\n{repro or '_not specified_'}\n\n"
        f"## Workaround\n\n{workaround or '_none_'}\n\n"
        f"## First seen\n\n{first_seen_date}\n\n"
        f"## Related\n\n_none yet_\n"
    )


_VALID_BUG_KINDS = frozenset({"bug", "feature", "design", "patch_request"})
_BUG_DEDUP_THRESHOLD = 0.5


def _bug_token_set(text: str) -> set[str]:
    """Return a lowercase word set from text, ignoring short tokens."""
    return {w for w in re.sub(r"[^a-z0-9]+", " ", text.lower()).split() if len(w) > 2}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _scan_existing_bugs(bugs_dir: Path) -> list[dict[str, Any]]:
    """Return a list of {bug_id, title, status, haystack_tokens} for all existing bugs.

    Haystack uses only frontmatter title + "What happened" section to avoid
    dilution from markdown scaffolding tokens (dates, template headings, etc.).
    """
    if not bugs_dir.is_dir():
        return []
    results = []
    for p in bugs_dir.glob("*.md"):
        m = re.match(r"^([A-Z]+)-(\d{3,})", p.stem, re.IGNORECASE)
        if not m:
            continue
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm_title = ""
        fm_status = "open"
        in_fm = False
        observed_text = ""
        in_observed = False
        for i, line in enumerate(raw.splitlines()):
            if i == 0 and line.strip() == "---":
                in_fm = True
                continue
            if in_fm:
                if line.strip() == "---":
                    in_fm = False
                    continue
                if line.startswith("title:"):
                    fm_title = line[6:].strip()
                elif line.startswith("status:"):
                    fm_status = line[7:].strip()
            else:
                if line.startswith("## What happened"):
                    in_observed = True
                    continue
                if in_observed:
                    if line.startswith("##"):
                        in_observed = False
                    else:
                        observed_text += " " + line
                if len(observed_text) > 300:
                    break
        haystack = _bug_token_set(fm_title + " " + observed_text[:300])
        results.append({
            "bug_id": f"{m.group(1).upper()}-{m.group(2)}",
            "title": fm_title,
            "status": fm_status,
            "haystack_tokens": haystack,
            "path": str(p),
        })
    return results


def _scan_queued_filings(universe_path: Path, kind: str) -> list[dict[str, Any]]:
    """Return active queued filings of the requested kind from BranchTask queue."""
    try:
        from workflow.branch_tasks import read_queue
        from workflow.bug_investigation import REQUEST_TYPE_BUG_INVESTIGATION
    except Exception:  # noqa: BLE001 - queue dedupe is best-effort for filing.
        return []

    results: list[dict[str, Any]] = []
    try:
        queue = read_queue(universe_path)
    except Exception as exc:  # noqa: BLE001 - corrupt queue should not block filing.
        _logger_wiki.warning("file_bug queued filing scan failed: %s", exc)
        return []

    for task in queue:
        if task.request_type != REQUEST_TYPE_BUG_INVESTIGATION:
            continue
        if task.status not in {"pending", "running"}:
            continue
        inputs = task.inputs if isinstance(task.inputs, dict) else {}
        if str(inputs.get("kind") or "bug").strip().lower() != kind:
            continue
        bug_id = str(inputs.get("bug_id") or "").strip()
        title = str(inputs.get("title") or "").strip()
        observed = str(inputs.get("observed") or "").strip()
        if not bug_id and not title and not observed:
            continue
        results.append({
            "bug_id": bug_id or task.branch_task_id,
            "title": title,
            "status": task.status,
            "haystack_tokens": _bug_token_set(title + " " + observed[:300]),
            "path": "",
            "source": "queue",
            "dispatcher_request_id": task.branch_task_id,
        })
    return results


def _wiki_cosign_bug(
    bug_id: str = "",
    reporter_context: str = "",
    **_kwargs: Any,
) -> str:
    """Append a cosign to an existing bug / feature / design / patch filing.

    Derives the target directory from the ``bug_id`` prefix
    (``BUG-`` → ``pages/bugs/``, ``FEAT-`` → ``pages/feature-requests/``,
    ``DESIGN-`` → ``pages/design-proposals/``, ``PR-`` →
    ``pages/patch-requests/``). Appends a ``## Cosigns`` section (or
    extends existing), and increments the ``cosign_count`` frontmatter
    field. Returns ``{status: "cosigned", bug_id, cosign_count}``.
    """
    if not bug_id:
        return json.dumps({"error": "bug_id is required for cosign_bug."})
    if not reporter_context:
        return json.dumps({"error": "reporter_context is required for cosign_bug."})

    # Derive category dir from bug_id prefix. Falls back to bugs/ for
    # backward-compat with raw "NNN" / unrecognized formats.
    bid_upper = bug_id.upper()
    category_dir = _BUGS_CATEGORY
    for _kind, (_dir, _prefix) in _KIND_ROUTING.items():
        if bid_upper.startswith(f"{_prefix}-"):
            category_dir = _dir
            break

    bugs_dir = _wiki_pages_dir() / category_dir
    # Find the matching file (case-insensitive prefix match)
    matches = [
        p for p in bugs_dir.glob("*.md")
        if (p.stem.split("-", 2)[0].upper() + "-" + p.stem.split("-", 2)[1]) == bid_upper
    ]
    if not matches:
        return json.dumps({
            "error": f"Bug not found: {bug_id}",
            "hint": "Check bug_id format (e.g. BUG-042 / FEAT-007 / DESIGN-003).",
        })

    target = matches[0]
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        return json.dumps({"error": f"Cannot read bug file: {exc}"})

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Increment cosign_count in frontmatter
    cosign_count = 1
    if "cosign_count:" in raw:
        for line in raw.splitlines():
            if line.startswith("cosign_count:"):
                try:
                    cosign_count = int(line.split(":", 1)[1].strip()) + 1
                except ValueError:
                    cosign_count = 1
        raw = re.sub(r"cosign_count:\s*\d+", f"cosign_count: {cosign_count}", raw)
    else:
        # Insert cosign_count into frontmatter (before closing ---)
        raw = re.sub(
            r"^(---\n(?:.|\n)*?)\n---",
            rf"\1\ncosign_count: {cosign_count}\n---",
            raw, count=1,
        )

    # Append or extend ## Cosigns section
    cosign_entry = f"\n- [{today}] {reporter_context}"
    if "## Cosigns" in raw:
        raw = raw.rstrip() + cosign_entry + "\n"
    else:
        raw = raw.rstrip() + f"\n\n## Cosigns\n{cosign_entry}\n"

    try:
        target.write_text(raw, encoding="utf-8")
    except OSError as exc:
        return json.dumps({"error": f"Cannot write bug file: {exc}"})

    _append_wiki_log(f"cosign_bug | {target.name} | {bug_id} cosign_count={cosign_count}")
    return json.dumps({
        "status": "cosigned",
        "bug_id": bid_upper,
        "cosign_count": cosign_count,
        "path": f"pages/{category_dir}/{target.name}",
    })


def _wiki_file_bug(
    component: str = "",
    severity: str = "",
    title: str = "",
    repro: str = "",
    observed: str = "",
    expected: str = "",
    workaround: str = "",
    kind: str = "bug",
    tags: str = "",
    force_new: bool = False,
    verbose: bool = False,
    **_kwargs: Any,
) -> str:
    """File a bug, feature request, design proposal, or patch request.

    ``kind`` defaults to "bug"; set to "feature", "design", or
    "patch_request" for non-bug filings. All kinds use the same request
    pipeline — navigator vets before dev implements (design-participation
    rule).

    Bypasses the draft-gate — filings land in pages/ immediately
    for host triage. ID is server-assigned via _next_bug_id. Atomic
    create guards against concurrent file_bug races.

    ``force_new`` skips the similarity check and always mints a new id.
    When omitted, a Jaccard similarity ≥ 0.5 against an existing bug's
    title+body returns {status: "similar_found"} instead of filing.

    Chatbot callers should check current repository/PLAN.md context before
    filing platform changes. The source repo is
    https://github.com/Jonnyton/Workflow; PLAN.md is canonical design and
    scoping truth. This does not require a wiki duplicate search because the
    server performs filing deduplication.
    """
    if not title or not component or not severity:
        return json.dumps({
            "error": "title, component, and severity are required.",
            "hint": "severity must be one of: " + " | ".join(_VALID_SEVERITIES),
        })
    if severity not in _VALID_SEVERITIES:
        return json.dumps({
            "error": f"Invalid severity '{severity}'.",
            "valid": list(_VALID_SEVERITIES),
        })
    effective_kind = kind.strip().lower() if kind else "bug"
    if effective_kind not in _VALID_BUG_KINDS:
        return json.dumps({
            "error": f"Invalid kind '{kind}'.",
            "valid": sorted(_VALID_BUG_KINDS),
        })

    category_dir, id_prefix = _KIND_ROUTING[effective_kind]
    pages_dir = _wiki_pages_dir() / category_dir
    drafts_dir = _wiki_drafts_dir() / category_dir
    try:
        pages_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return json.dumps({"error": f"Cannot create {category_dir} dir: {exc}"})

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = _slugify_title(title)
    universe_id = _default_universe()
    universe_path = _universe_dir(universe_id)

    # Dedup check: scan existing filings of THIS kind for Jaccard similarity
    # ≥ threshold, including active queued filings that may not have completed
    # yet. Per-kind only — a feature-request shouldn't dedup against a bug
    # because they're different work surfaces; same title may legitimately
    # exist as both. Skip when force_new=True.
    if not force_new:
        query_tokens = _bug_token_set(title + " " + (observed or ""))
        existing = _scan_existing_bugs(pages_dir)
        existing.extend(_scan_queued_filings(universe_path, effective_kind))
        scored = []
        for entry in existing:
            sim = _jaccard(query_tokens, entry["haystack_tokens"])
            if sim >= _BUG_DEDUP_THRESHOLD:
                scored.append((sim, entry))
        if scored:
            scored.sort(key=lambda x: -x[0])
            top3 = [
                {
                    "bug_id": e["bug_id"],
                    "title": e["title"],
                    "similarity": round(s, 3),
                    "status": e["status"],
                    "source": e.get("source", "wiki"),
                }
                for s, e in scored[:3]
            ]
            return json.dumps({
                "status": "similar_found",
                "bug_id": None,
                "similar": top3,
                "hint": (
                    "Similar filings exist. Use cosign_bug to add your context "
                    "to the top match, or set force_new=true if the symptom is "
                    "materially different."
                ),
            })

    for attempt in (1, 2):
        bug_id = _next_id(pages_dir, drafts_dir, id_prefix)
        filename = f"{bug_id.lower()}-{slug}.md"
        target = pages_dir / filename
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
            kind=effective_kind,
            extra_tags=[t.strip() for t in tags.split(",") if t.strip()],
        )
        try:
            with open(target, "x", encoding="utf-8") as fh:
                fh.write(body)
            break
        except FileExistsError:
            if attempt == 2:
                return json.dumps({
                    "error": f"{id_prefix} id collision retry exhausted.",
                    "hint": "Retry in a moment — concurrent filers.",
                })
            time.sleep(0.05)
            continue
    else:
        return json.dumps({"error": "Failed to write bug report."})

    rel_path = f"pages/{category_dir}/{filename}"
    _append_wiki_log(
        f"file_bug | {rel_path} | {bug_id} {title} [{severity}] kind={effective_kind}"
    )
    # FEAT-004: per-request-id traceable trigger receipt. Created BEFORE the
    # enqueue so a crash in the trigger helper still leaves a durable record
    # showing a trigger was expected. Backward-compatible: the existing
    # ``investigation`` block in the response is preserved verbatim, and the
    # new ``trigger`` block is additive.
    investigation: dict[str, Any] = {"status": "skipped"}
    trigger_block: dict[str, Any] | None = None
    _receipt = None
    try:
        from workflow import bug_investigation
        from workflow.wiki import trigger_receipts as _tr

        frontmatter = {
            "bug_id": bug_id,
            "title": title,
            "type": effective_kind,
            "kind": effective_kind,
            "component": component,
            "severity": severity,
            "status": "open",
            "observed": observed,
            "expected": expected,
            "repro": repro,
            "workaround": workaround,
        }
        # Pre-write trigger receipt (status=pending). Read canonical branch_def_id
        # from env so the receipt records what we *expected* to invoke even if the
        # enqueue helper rejects.
        import os as _os
        canonical_branch_def_id = _os.environ.get(
            "WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID", "",
        ).strip() or None
        try:
            _receipt = _tr.create_pending(
                request_id=bug_id,
                request_kind=effective_kind,
                request_page=rel_path,
                branch_def_id=canonical_branch_def_id,
            )
        except Exception as _rcpt_exc:  # noqa: BLE001 - filing must survive receipt-store outage.
            _logger_wiki.warning(
                "file_bug trigger_receipt create failed for %s: %s", bug_id, _rcpt_exc,
            )
            _receipt = None

        try:
            request_id = bug_investigation._maybe_enqueue_investigation(
                bug_id=bug_id,
                frontmatter=frontmatter,
                base_path=universe_path,
                universe_id=universe_id,
            )
        except Exception as _enq_exc:
            # Trigger helper raised. Update receipt then re-raise into the outer
            # except so the existing investigation = {"status": "error"} branch
            # behavior is preserved.
            if _receipt is not None:
                try:
                    _receipt = _tr.mark_failed(_receipt, error=_enq_exc)
                    trigger_block = _receipt.to_response()
                except Exception:  # noqa: BLE001 - last-resort, don't break filing.
                    pass
            raise

        if request_id:
            investigation_section = bug_investigation.format_investigation_comment(
                request_id=request_id,
                status="queued",
            )
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(investigation_section)
            investigation = {
                "status": "queued",
                "dispatcher_request_id": request_id,
            }
            # Default response shape is compact — callers needing the
            # full BranchTask mirror pass verbose=True. Cuts the typical
            # file_bug response from ~3.7 KB to ~600 bytes (no 23-field
            # BranchTask dump that mirrors inputs.request_text). The
            # trigger_attempt_id + dispatcher_request_id below are already
            # enough for chatbots/canaries to join request -> run; the full
            # mirror is operator-only and can be fetched on-demand via
            # ``universe action=queue_list`` with the branch_task_id.
            if verbose:
                try:
                    from workflow.branch_tasks import read_queue

                    task = next(
                        (
                            t for t in read_queue(universe_path)
                            if t.branch_task_id == request_id
                        ),
                        None,
                    )
                    if task is not None:
                        investigation["branch_task"] = task.to_dict()
                except Exception as _queue_exc:  # noqa: BLE001
                    _logger_wiki.warning(
                        "file_bug investigation task read failed for %s: %s",
                        bug_id,
                        _queue_exc,
                    )
            if _receipt is not None:
                try:
                    _receipt = _tr.mark_queued(
                        _receipt, dispatcher_request_id=request_id,
                    )
                except Exception:  # noqa: BLE001
                    pass
        else:
            # Skipped because no canonical branch configured (env var empty
            # or filing without bug_id). Record on the receipt for audit.
            if _receipt is not None:
                try:
                    _receipt = _tr.mark_skipped(
                        _receipt, reason="no_canonical_branch",
                    )
                except Exception:  # noqa: BLE001
                    pass

        if _receipt is not None:
            trigger_block = _receipt.to_response()
    except Exception as exc:  # noqa: BLE001 - bug filing itself must survive trigger failure.
        _logger_wiki.warning("file_bug investigation trigger failed for %s: %s", bug_id, exc)
        investigation = {"status": "error", "error": str(exc)}

    response_body: dict[str, Any] = {
        "path": rel_path,
        "bug_id": bug_id,
        "status": "filed",
        "kind": effective_kind,
        "severity": severity,
        "component": component,
        "investigation": investigation,
        "note": "Filing sent to navigator triage pipeline. "
                f"Use `wiki action=list category={category_dir}` to view.",
    }
    if trigger_block is not None:
        # FEAT-004: surface the structured trigger receipt so callers (canaries
        # / chatbots / operators) have a per-request-id join key without log
        # scraping. ``investigation`` is preserved above for backward compat.
        response_body["trigger"] = trigger_block
    return json.dumps(response_body)


# ---------------------------------------------------------------------------
# Dispatch entry — plain function. The MCP tool wrapper lives in
# workflow/universe_server.py and delegates here (Pattern A2).
# ---------------------------------------------------------------------------


def wiki(
    action: str,
    page: str = "",
    query: str = "",
    category: str = "",
    filename: str = "",
    content: str = "",
    log_entry: str = "",
    old_text: str = "",
    new_text: str = "",
    expected_sha256: str = "",
    source_url: str = "",
    old_page: str = "",
    new_draft: str = "",
    reason: str = "",
    similarity_threshold: float = 0.25,
    dry_run: bool = True,
    skip_lint: bool = False,
    max_results: int = 10,
    component: str = "",
    severity: str = "",
    title: str = "",
    repro: str = "",
    observed: str = "",
    expected: str = "",
    workaround: str = "",
    kind: str = "bug",
    tags: str = "",
    force_new: bool = False,
    bug_id: str = "",
    reporter_context: str = "",
    verbose: bool = False,
    changed_since: str = "",
) -> str:
    """Dispatch entry for the wiki MCP tool. See universe_server.py for the
    chatbot-facing docstring; this function is the implementation invoked by
    the @mcp.tool wrapper there.
    """
    try:
        wiki_root = _wiki_root()
    except ValueError as exc:
        # _wiki_root() raises when WORKFLOW_WIKI_PATH holds a Windows path on
        # a POSIX runtime (2026-04-19 container incident).
        return json.dumps({
            "error": str(exc),
            "hint": (
                "Unset WORKFLOW_WIKI_PATH to use the platform default "
                "(data_dir()/wiki), or set it to a POSIX absolute path "
                "like '/data/wiki'."
            ),
        })

    # Task #6 — scaffold the tree on first call so fresh deploys
    # (empty /data/wiki) don't error on read/list/search/lint. Idempotent.
    try:
        _ensure_wiki_scaffold(wiki_root)
    except OSError as exc:
        return json.dumps({
            "error": f"Wiki scaffold failed at {wiki_root}: {exc}",
            "hint": (
                "Check filesystem permissions on the wiki root. The volume "
                "must be writable by the daemon uid."
            ),
        })

    if not wiki_root.is_dir():
        return json.dumps({
            "error": f"Wiki not found at {wiki_root}.",
            "hint": (
                "Set WORKFLOW_WIKI_PATH to the wiki directory."
            ),
        })

    dispatch = {
        "read": _wiki_read,
        "search": _wiki_search,
        "since": _wiki_since,
        "list": _wiki_list,
        "lint": _wiki_lint,
        "write": _wiki_write,
        "patch": _wiki_patch,
        "consolidate": _wiki_consolidate,
        "promote": _wiki_promote,
        "ingest": _wiki_ingest,
        "supersede": _wiki_supersede,
        "sync_projects": _wiki_sync_projects,
        "file_bug": _wiki_file_bug,
        "cosign_bug": _wiki_cosign_bug,
    }

    handler = dispatch.get(action)
    if handler is None:
        return json.dumps({
            "error": f"Unknown action '{action}'.",
            "available_actions": sorted(dispatch.keys()),
        })

    kwargs: dict[str, Any] = {
        "page": page,
        "query": query,
        "category": category,
        "filename": filename,
        "content": content,
        "log_entry": log_entry,
        "old_text": old_text,
        "new_text": new_text,
        "expected_sha256": expected_sha256,
        "source_url": source_url,
        "old_page": old_page,
        "new_draft": new_draft,
        "reason": reason,
        "similarity_threshold": similarity_threshold,
        "dry_run": dry_run,
        "skip_lint": skip_lint,
        "max_results": max_results,
        "component": component,
        "severity": severity,
        "title": title,
        "repro": repro,
        "observed": observed,
        "expected": expected,
        "workaround": workaround,
        "kind": kind,
        "tags": tags,
        "force_new": force_new,
        "bug_id": bug_id,
        "reporter_context": reporter_context,
        "verbose": verbose,
        "changed_since": changed_since,
    }

    return handler(**kwargs)
