"""Domain-neutral universe soul profile helpers.

PR-139 slice 3 keeps the old ``PROGRAM.md`` premise file as a compatibility
mirror while introducing ``soul.md`` as the durable universe-intent artifact.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from pathlib import Path

SOUL_FILENAME = "soul.md"
SOUL_VERSIONS_DIR = "soul_versions"
LEGACY_PREMISE_FILENAME = "PROGRAM.md"
SOUL_SCHEMA_VERSION = 1
DEFAULT_DOMAIN_SHAPE = "general"
DEFAULT_EDIT_AUTHORITY = "soul.edit"
NO_LOOP_DECLARED = ""
NO_LOOP_MARKER = "_None recorded._"


@dataclass(frozen=True)
class UniverseSoul:
    schema_version: int = SOUL_SCHEMA_VERSION
    purpose: str = ""
    why: str = ""
    hard_lines: tuple[str, ...] = ()
    soft_preferences: tuple[str, ...] = ()
    open_to_contributors: tuple[str, ...] = ()
    domain_shape: str = DEFAULT_DOMAIN_SHAPE
    lineage: str = "template"
    edit_authority: str = DEFAULT_EDIT_AUTHORITY
    loop_branch_def_id: str = NO_LOOP_DECLARED

    def summary(self) -> dict[str, object]:
        return {
            "path": SOUL_FILENAME,
            "schema_version": self.schema_version,
            "purpose": self.purpose,
            "domain_shape": self.domain_shape,
            "lineage": self.lineage,
            "edit_authority": self.edit_authority,
            "loop_branch_def_id": self.loop_branch_def_id,
            "versions_dir": SOUL_VERSIONS_DIR,
        }


@dataclass(frozen=True)
class PinnedUniverseSoul:
    soul: UniverseSoul
    content: str
    version_id: str
    content_sha256: str

    def context(self, *, max_chars: int = 4000) -> dict[str, object]:
        content = self.content[:max_chars].rstrip()
        truncated = len(self.content) > max_chars
        return {
            "path": SOUL_FILENAME,
            "version_id": self.version_id,
            "content_sha256": self.content_sha256,
            "schema_version": self.soul.schema_version,
            "purpose": self.soul.purpose,
            "why": self.soul.why,
            "hard_lines": list(self.soul.hard_lines),
            "soft_preferences": list(self.soul.soft_preferences),
            "open_to_contributors": list(self.soul.open_to_contributors),
            "domain_shape": self.soul.domain_shape,
            "lineage": self.soul.lineage,
            "edit_authority": self.soul.edit_authority,
            "loop_branch_def_id": self.soul.loop_branch_def_id,
            "identity_boundary": (
                "Universe soul guides this context only; it does not change "
                "the actor identity or user memory scope."
            ),
            "content": content,
            "truncated": truncated,
        }


def soul_path(universe_dir: Path) -> Path:
    return universe_dir / SOUL_FILENAME


def legacy_premise_path(universe_dir: Path) -> Path:
    return universe_dir / LEGACY_PREMISE_FILENAME


def has_soul(universe_dir: Path) -> bool:
    return soul_path(universe_dir).is_file()


def render_soul_markdown(soul: UniverseSoul) -> str:
    return "\n".join([
        "# Universe Soul",
        "",
        f"- Schema version: {soul.schema_version}",
        f"- Domain shape: {soul.domain_shape}",
        f"- Lineage: {soul.lineage}",
        f"- Edit authority: {soul.edit_authority}",
        f"- Loop branch: {soul.loop_branch_def_id or NO_LOOP_MARKER}",
        "",
        "## Purpose",
        "",
        soul.purpose.strip(),
        "",
        "## Why",
        "",
        soul.why.strip(),
        "",
        "## Hard Lines",
        "",
        _render_list(soul.hard_lines),
        "",
        "## Soft Preferences",
        "",
        _render_list(soul.soft_preferences),
        "",
        "## Open To Contributors",
        "",
        _render_list(soul.open_to_contributors),
        "",
        "## Edit Authority",
        "",
        soul.edit_authority.strip() or DEFAULT_EDIT_AUTHORITY,
        "",
    ])


def read_universe_soul(universe_dir: Path) -> UniverseSoul | None:
    path = soul_path(universe_dir)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return None

    return UniverseSoul(
        schema_version=_read_int_meta(text, "Schema version", SOUL_SCHEMA_VERSION),
        purpose=_read_section(text, "Purpose"),
        why=_read_section(text, "Why"),
        hard_lines=_read_list_section(text, "Hard Lines"),
        soft_preferences=_read_list_section(text, "Soft Preferences"),
        open_to_contributors=_read_list_section(text, "Open To Contributors"),
        domain_shape=_read_meta(text, "Domain shape", DEFAULT_DOMAIN_SHAPE),
        lineage=_read_meta(text, "Lineage", "unknown"),
        edit_authority=(
            _read_section(text, "Edit Authority")
            or _read_meta(text, "Edit authority", DEFAULT_EDIT_AUTHORITY)
        ),
        loop_branch_def_id=_read_loop_branch_meta(text),
    )


def read_pinned_universe_soul(universe_dir: Path) -> PinnedUniverseSoul | None:
    soul = read_universe_soul(universe_dir)
    if soul is None:
        return None

    try:
        content = soul_path(universe_dir).read_text(encoding="utf-8")
    except OSError:
        return None

    version_id = _matching_soul_version_id(universe_dir, content)
    if version_id is None:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        version_id = f"{SOUL_FILENAME}@sha256:{digest[:12]}"

    return PinnedUniverseSoul(
        soul=soul,
        content=content,
        version_id=version_id,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def write_universe_soul(
    universe_dir: Path,
    *,
    purpose: str = "",
    why: str = "",
    hard_lines: tuple[str, ...] = (),
    soft_preferences: tuple[str, ...] = (),
    open_to_contributors: tuple[str, ...] = (),
    domain_shape: str = DEFAULT_DOMAIN_SHAPE,
    lineage: str = "template",
    edit_authority: str = DEFAULT_EDIT_AUTHORITY,
    loop_branch_def_id: str = NO_LOOP_DECLARED,
) -> UniverseSoul:
    universe_dir.mkdir(parents=True, exist_ok=True)
    existing = read_universe_soul(universe_dir)
    if existing is None:
        soul = UniverseSoul(
            purpose=purpose.strip(),
            why=why.strip(),
            hard_lines=tuple(item.strip() for item in hard_lines if item.strip()),
            soft_preferences=tuple(
                item.strip() for item in soft_preferences if item.strip()
            ),
            open_to_contributors=tuple(
                item.strip() for item in open_to_contributors if item.strip()
            ),
            domain_shape=domain_shape.strip() or DEFAULT_DOMAIN_SHAPE,
            lineage=lineage.strip() or "template",
            edit_authority=edit_authority.strip() or DEFAULT_EDIT_AUTHORITY,
            loop_branch_def_id=loop_branch_def_id.strip(),
        )
    else:
        soul = replace(
            existing,
            purpose=purpose.strip() if purpose.strip() else existing.purpose,
            why=why.strip() if why.strip() else existing.why,
            hard_lines=(
                tuple(item.strip() for item in hard_lines if item.strip())
                or existing.hard_lines
            ),
            soft_preferences=(
                tuple(item.strip() for item in soft_preferences if item.strip())
                or existing.soft_preferences
            ),
            open_to_contributors=(
                tuple(item.strip() for item in open_to_contributors if item.strip())
                or existing.open_to_contributors
            ),
            domain_shape=domain_shape.strip() or existing.domain_shape,
            lineage=lineage.strip() or existing.lineage,
            edit_authority=edit_authority.strip() or existing.edit_authority,
            loop_branch_def_id=(
                loop_branch_def_id.strip() or existing.loop_branch_def_id
            ),
        )

    rendered = render_soul_markdown(soul)
    soul_path(universe_dir).write_text(rendered, encoding="utf-8")
    _write_soul_version(universe_dir, rendered)
    return soul


def ensure_universe_soul(
    universe_dir: Path,
    *,
    purpose: str = "",
    loop_branch_def_id: str = NO_LOOP_DECLARED,
) -> UniverseSoul:
    existing = read_universe_soul(universe_dir)
    if existing is not None and (
        (existing.purpose or not purpose.strip())
        and (existing.loop_branch_def_id or not loop_branch_def_id.strip())
    ):
        return existing
    return write_universe_soul(
        universe_dir,
        purpose=purpose,
        lineage="created-from-premise" if purpose.strip() else "template",
        loop_branch_def_id=loop_branch_def_id,
    )


def read_legacy_premise(universe_dir: Path) -> str:
    try:
        return legacy_premise_path(universe_dir).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError:
        return ""


def premise_from_soul(universe_dir: Path) -> str:
    soul = read_universe_soul(universe_dir)
    return soul.purpose if soul is not None else ""


def loop_branch_from_soul(universe_dir: Path) -> str:
    soul = read_universe_soul(universe_dir)
    return soul.loop_branch_def_id if soul is not None else NO_LOOP_DECLARED


def _render_list(items: tuple[str, ...]) -> str:
    if not items:
        return "_None recorded._"
    return "\n".join(f"- {item}" for item in items)


def _write_soul_version(universe_dir: Path, rendered: str) -> None:
    versions_dir = universe_dir / SOUL_VERSIONS_DIR
    versions_dir.mkdir(parents=True, exist_ok=True)
    versions = sorted(versions_dir.glob("[0-9][0-9][0-9][0-9].md"))
    if versions:
        try:
            if versions[-1].read_text(encoding="utf-8") == rendered:
                return
        except OSError:
            pass
    next_number = 1
    if versions:
        try:
            next_number = int(versions[-1].stem) + 1
        except ValueError:
            next_number = len(versions) + 1
    (versions_dir / f"{next_number:04d}.md").write_text(rendered, encoding="utf-8")


def _matching_soul_version_id(universe_dir: Path, content: str) -> str | None:
    versions_dir = universe_dir / SOUL_VERSIONS_DIR
    if not versions_dir.is_dir():
        return None
    for path in sorted(versions_dir.glob("[0-9][0-9][0-9][0-9].md"), reverse=True):
        try:
            if path.read_text(encoding="utf-8") == content:
                return f"{SOUL_VERSIONS_DIR}/{path.name}"
        except OSError:
            continue
    return None


def _read_meta(text: str, key: str, default: str) -> str:
    pattern = rf"(?im)^-\s*{re.escape(key)}:\s*(.+?)\s*$"
    match = re.search(pattern, text)
    if not match:
        return default
    return match.group(1).strip() or default


def _read_int_meta(text: str, key: str, default: int) -> int:
    raw = _read_meta(text, key, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def _read_loop_branch_meta(text: str) -> str:
    raw = _read_meta(text, "Loop branch", NO_LOOP_DECLARED)
    if raw in {NO_LOOP_MARKER, "none", "None", "NONE"}:
        return NO_LOOP_DECLARED
    return raw


def _read_section(text: str, heading: str) -> str:
    pattern = rf"(?ims)^##\s+{re.escape(heading)}\s*$\n(?P<body>.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, text)
    if not match:
        return ""
    body = match.group("body").strip()
    return "" if body == "_None recorded._" else body


def _read_list_section(text: str, heading: str) -> tuple[str, ...]:
    body = _read_section(text, heading)
    if not body:
        return ()
    items: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "_None recorded._":
            continue
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
        else:
            items.append(stripped)
    return tuple(item for item in items if item)
