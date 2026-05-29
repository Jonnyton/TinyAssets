"""Sandbox-safe canon filename helpers."""

from __future__ import annotations

import re

_CANON_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def safe_canon_slug(value: str) -> str:
    """Return a sandbox-safe canon topic slug.

    LLM-synthesized topic names are not trusted path components. Canon topic
    slugs are restricted to lowercase ASCII letters, digits, and underscores.
    """
    slug = _CANON_SLUG_RE.sub("_", str(value).lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        raise ValueError("canon topic must resolve to a non-empty safe slug")
    return slug


def safe_canon_filename(value: str) -> str:
    """Return a safe ``.md`` filename for a canon topic or filename."""
    raw = str(value).strip()
    if raw.lower().endswith(".md"):
        raw = raw[:-3]
    return f"{safe_canon_slug(raw)}.md"
