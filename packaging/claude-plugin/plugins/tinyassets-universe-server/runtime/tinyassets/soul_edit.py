"""The universe's learn/write path: apply a governed soul edit.

Implements the `soul.edit` contract from the universe-creation spec: the
execution path READS AND FOLLOWS the universe's own ``soul.edit.md`` policy
(the authority lives in the file, not in a hardcoded list). An edit is a
learning event — proposed learning with source and context, never a blind
overwrite — that updates only the explicitly changed governed files, appends
``log.md``, and writes a new ``soul_versions/`` snapshot.

This is what lets a universe REMEMBER what its founder teaches it: learned
files flip ``status: not-learned`` → ``learned``, and the persona
(``tinyassets.persona.resolve_persona`` over
``tinyassets.universe_self_model.read_self_model``) voices them from then on.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from tinyassets.universe_soul import SOUL_FILENAME, SOUL_VERSIONS_DIR

SOUL_EDIT_POLICY_FILENAME = "soul.edit.md"

# Files whose frontmatter records the learning event. soul.md is the
# operational entrypoint — its frontmatter (okf_source, edit_authority, …) is
# preserved verbatim and carries no learned-status flag.
_LEARNED_STATUS_EXEMPT = frozenset({SOUL_FILENAME})


class SoulEditError(ValueError):
    """A soul edit that violates the universe's soul.edit.md policy."""


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split an OKF concept doc into (frontmatter dict, body)."""
    if not text.startswith("---"):
        raise SoulEditError("governed file is missing OKF frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SoulEditError("governed file has malformed OKF frontmatter")
    meta = yaml.safe_load(parts[1])
    if not isinstance(meta, dict):
        raise SoulEditError("governed file frontmatter is not a mapping")
    return meta, parts[2].lstrip("\n")


def _render(meta: dict[str, Any], body: str) -> str:
    fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
    if not body.endswith("\n"):
        body += "\n"
    return f"---\n{fm}\n---\n\n{body}"


def read_governed_files(universe_dir: Path) -> tuple[str, ...]:
    """Parse the governed-file list from the universe's ``soul.edit.md``.

    The policy file is the authority. No policy file → no soul edits.
    """
    policy_path = universe_dir / SOUL_EDIT_POLICY_FILENAME
    try:
        policy = policy_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SoulEditError(
            f"soul edit policy missing: {SOUL_EDIT_POLICY_FILENAME} is required "
            "(the execution path reads and follows it)"
        ) from exc

    section = re.search(
        r"^##\s+Governed files\s*$(.*?)(?=^##\s|\Z)",
        policy,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not section:
        raise SoulEditError("soul.edit.md has no 'Governed files' section")
    governed = tuple(re.findall(r"^\s*-\s*`([^`]+)`", section.group(1), flags=re.MULTILINE))
    if not governed:
        raise SoulEditError("soul.edit.md governs no files")
    return governed


def apply_soul_edit(
    universe_dir: Path,
    *,
    changes: dict[str, str],
    source: str,
    context: str,
    summary: str = "",
    name: str = "",
) -> dict[str, Any]:
    """Apply one governed learning event to the universe's soul bundle.

    ``changes`` maps governed filename → new markdown BODY (frontmatter is
    managed here: preserved, with ``status: learned`` + ``learned_from``
    recorded). ``name`` optionally records the universe's learned self-name in
    ``identity.md`` frontmatter — a name-only learning event needs no body.
    ``source`` and ``context`` are required: an edit is proposed learning, not
    a blind overwrite.
    """
    universe_dir = Path(universe_dir)
    source = (source or "").strip()
    context = (context or "").strip()
    name = (name or "").strip()
    if not source or not context:
        raise SoulEditError(
            "source and context are required — a soul edit is a learning "
            "event, not a blind overwrite"
        )

    governed = read_governed_files(universe_dir)
    changes = dict(changes or {})
    if name and "identity.md" not in changes:
        changes["identity.md"] = ""  # name-only: keep the existing body
    if not changes:
        raise SoulEditError("nothing to learn: provide changes and/or a name")

    for filename in changes:
        if filename != Path(filename).name or filename.startswith("."):
            raise SoulEditError(f"invalid governed filename: {filename!r}")
        if filename not in governed:
            raise SoulEditError(
                f"'{filename}' is not governed by {SOUL_EDIT_POLICY_FILENAME} "
                f"(governed: {', '.join(governed)})"
            )

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    updated: list[str] = []
    new_contents: dict[str, str] = {}
    for filename, new_body in changes.items():
        path = universe_dir / filename
        try:
            meta, old_body = _split_frontmatter(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise SoulEditError(f"governed file missing on disk: {filename}") from exc
        body = new_body if (new_body or "").strip() else old_body
        if filename not in _LEARNED_STATUS_EXEMPT:
            meta["status"] = "learned"
            meta["learned_from"] = source
            meta["learned_at"] = now
        if name and filename == "identity.md":
            meta["name"] = name
        rendered = _render(meta, body)
        new_contents[filename] = rendered
        path.write_text(rendered, encoding="utf-8")
        updated.append(filename)

    log_entry = summary.strip() or f"learned {', '.join(sorted(updated))}"
    _append_log(universe_dir, f"- learned: {log_entry} (source: {source})")
    snapshot_rel = _write_edit_snapshot(
        universe_dir,
        files=new_contents,
        source=source,
        context=context,
        summary=log_entry,
        stamp=now,
    )

    return {
        "updated_files": sorted(updated),
        "snapshot": snapshot_rel,
        "log_entry": log_entry,
        "source": source,
    }


def _append_log(universe_dir: Path, line: str) -> None:
    log_path = universe_dir / "log.md"
    try:
        text = log_path.read_text(encoding="utf-8")
    except OSError:
        text = "# Update Log\n"
    if not text.endswith("\n"):
        text += "\n"
    log_path.write_text(text + line + "\n", encoding="utf-8")


def _write_edit_snapshot(
    universe_dir: Path,
    *,
    files: dict[str, str],
    source: str,
    context: str,
    summary: str,
    stamp: str,
) -> str:
    """Write a self-describing snapshot of this edit and index it.

    Every accepted edit writes a NEW snapshot (policy), so the record embeds
    the edit metadata — two identical-content edits still produce distinct
    snapshots because each records its own event.
    """
    versions_dir = universe_dir / SOUL_VERSIONS_DIR
    versions_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(versions_dir.glob("[0-9][0-9][0-9][0-9].md"))
    next_number = 1
    if existing:
        try:
            next_number = int(existing[-1].stem) + 1
        except ValueError:
            next_number = len(existing) + 1

    meta = {
        "type": "Soul Edit Snapshot",
        "title": f"Soul Edit {next_number:04d}",
        "description": summary,
        "source": source,
        "learned_at": stamp,
        "files": ", ".join(sorted(files)),
    }
    body_parts = [f"# Soul Edit {next_number:04d}", "", context, ""]
    for filename in sorted(files):
        body_parts += [f"## {filename}", "", "```markdown", files[filename].rstrip(), "```", ""]
    snapshot_name = f"{next_number:04d}.md"
    (versions_dir / snapshot_name).write_text(
        _render(meta, "\n".join(body_parts)), encoding="utf-8",
    )

    index_path = versions_dir / "index.md"
    try:
        index_text = index_path.read_text(encoding="utf-8")
    except OSError:
        index_text = "# Soul Version Index\n"
    if not index_text.endswith("\n"):
        index_text += "\n"
    index_path.write_text(
        index_text
        + f"- [{next_number:04d}]({snapshot_name}) — learned: {summary}\n",
        encoding="utf-8",
    )
    return f"{SOUL_VERSIONS_DIR}/{snapshot_name}"
