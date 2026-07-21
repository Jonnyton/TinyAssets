"""Tests for docs/ops/host-independence-runbook.md anchors + the
secrets-expiry-check DEFAULT_METADATA's runbook: references.

The expiry-check workflow opens GH issues pointing operators at a
specific anchor (e.g. `#cloudflare-api-token`). If the anchor is
renamed or deleted, those auto-opened issues carry a broken link —
a silent degradation of the on-call experience.

Invariant: every `runbook:` reference in
``.github/workflows/secrets-expiry-check.yml``'s DEFAULT_METADATA that
points at the runbook must resolve to a live anchor in
``docs/ops/host-independence-runbook.md``.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_RUNBOOK = _REPO / "docs" / "ops" / "host-independence-runbook.md"
_WORKFLOW = _REPO / ".github" / "workflows" / "secrets-expiry-check.yml"


def _slugify(heading: str) -> str:
    """GitHub Markdown anchor slug: lowercase, drop non-word chars, join
    words with hyphens. Matches GitHub's actual slugger for Markdown
    headings — close-enough for what this runbook uses (plain ASCII
    heading text, no emoji).
    """
    # Strip leading `#` marks + whitespace.
    text = heading.lstrip("#").strip().lower()
    # GitHub's rule: keep letters, digits, hyphens, underscores; replace
    # spaces with hyphens; drop everything else.
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text


def _runbook_anchors() -> set[str]:
    """Return the set of anchors available in the runbook (derived from
    ``#``/``##``/``###``/``####`` headings)."""
    text = _RUNBOOK.read_text(encoding="utf-8")
    anchors: set[str] = set()
    for line in text.splitlines():
        if line.startswith("#"):
            anchors.add(_slugify(line))
    return anchors


def _metadata_runbook_refs() -> list[tuple[str, str]]:
    """Return [(secret_name, anchor_fragment), ...] for every runbook
    reference that points into the host-independence-runbook."""
    text = _WORKFLOW.read_text(encoding="utf-8")
    # The DEFAULT_METADATA block is embedded in the workflow's inline
    # Python. Parse conservatively — each item has a "name" and a
    # "runbook" field; we extract them line-adjacent.
    refs: list[tuple[str, str]] = []
    current_name: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        m_name = re.match(r'"name":\s*"([^"]+)"', stripped)
        if m_name:
            current_name = m_name.group(1)
            continue
        m_runbook = re.match(
            r'"runbook":\s*"docs/ops/host-independence-runbook\.md#([^"]+)"',
            stripped,
        )
        if m_runbook and current_name:
            refs.append((current_name, m_runbook.group(1)))
            current_name = None
    return refs


# ---- smoke ---------------------------------------------------------------


def test_runbook_exists():
    assert _RUNBOOK.is_file(), f"missing: {_RUNBOOK}"


def test_workflow_exists():
    assert _WORKFLOW.is_file(), f"missing: {_WORKFLOW}"


def test_metadata_has_runbook_refs():
    """Sanity: the metadata-extraction regex finds at least the core set.
    Catches regressions that would silently make the anchor-check no-op."""
    refs = _metadata_runbook_refs()
    names = {n for n, _ in refs}
    # At minimum the metadata must cover these — taken from the lead's
    # 7d9e6cf-ish rewrite.
    must_have = {
        "CLOUDFLARE_API_TOKEN",
        "DIGITALOCEAN_TOKEN",
        "DO_SSH_KEY",
        "PUSHOVER_USER_KEY",
        "PUSHOVER_APP_TOKEN",
    }
    missing = must_have - names
    assert not missing, f"expected metadata entries missing: {missing}"


# ---- the invariant -------------------------------------------------------


def test_every_metadata_anchor_resolves_in_runbook():
    """Every runbook: reference in DEFAULT_METADATA must hit a real
    anchor. Renaming a heading without updating the workflow breaks
    operator-facing links in auto-opened expiry issues.
    """
    available = _runbook_anchors()
    broken: list[str] = []
    for name, anchor in _metadata_runbook_refs():
        if anchor not in available:
            broken.append(f"{name} -> #{anchor}")
    assert not broken, (
        "secrets-expiry-check.yml references anchors that don't exist "
        "in host-independence-runbook.md:\n  " + "\n  ".join(broken) +
        "\nAvailable anchors sample: " +
        ", ".join(sorted(a for a in available if "-" in a)[:10]) + " ..."
    )


def test_runbook_has_per_secret_rotation_headings():
    """Structural check — the per-secret sub-section pattern should hold:
    every major metadata entry has its own subsection. Catches accidental
    heading-level changes that would break slugification."""
    text = _RUNBOOK.read_text(encoding="utf-8")
    # Headings that SHOULD be H4 (`####`) to match the flat anchor style.
    expected_h4 = {
        "cloudflare-api-token",
        "cloudflare-zone-id",
        "digitalocean-token",
        "do-ssh-key",
        "do-droplet-host",
        "do-ssh-user",
        "pushover-user-key",
        "pushover-app-token",
    }
    found: set[str] = set()
    for line in text.splitlines():
        if line.startswith("#### "):
            found.add(_slugify(line))
    missing = expected_h4 - found
    assert not missing, (
        f"missing per-secret H4 subsections: {missing}. "
        "Each metadata entry gets its own `#### <anchor>` subsection."
    )


def test_do_ssh_key_anchor_points_to_backup_section():
    """The backup key is the break-glass credential; the do-ssh-key
    rotation runbook must cross-reference the §5b backup section so
    operators can find it from the expiry-issue link."""
    text = _RUNBOOK.read_text(encoding="utf-8")
    # Find the do-ssh-key section and confirm it mentions §5b or the
    # backup key explicitly.
    i = text.find("#### do-ssh-key")
    assert i >= 0, "do-ssh-key anchor section missing"
    # Look ahead until the next #### heading.
    j = text.find("\n#### ", i + 5)
    section = text[i:j] if j > 0 else text[i:]
    assert "backup" in section.lower() or "§5b" in section or "5b" in section, (
        "do-ssh-key section must cross-reference §5b backup-key runbook "
        "so break-glass recovery is discoverable from expiry-issue links"
    )
