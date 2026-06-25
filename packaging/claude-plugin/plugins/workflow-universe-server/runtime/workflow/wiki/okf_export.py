"""Read-only OKF v0.1 export for promoted Workflow wiki pages."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflow.api.wiki import _parse_frontmatter, _wiki_root_for_universe

OKF_VERSION = "0.1"

_RESERVED_FILENAMES = frozenset({"index.md", "log.md"})
_EXCLUDED_ROOTS = frozenset({"drafts", "raw", "daemon-wiki"})
_WIKILINK_RE = re.compile(r"\[\[([^\[\]\n]+)\]\]")
_H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
_SAFE_PLAIN_SCALAR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _./:@+\-]*$")


def export_universe_okf_bundle(universe_id: str, target_dir: str | Path) -> dict[str, Any]:
    """Export one universe's promoted wiki pages as an OKF v0.1 bundle.

    ``universe_id`` is resolved by ``workflow.api.wiki._wiki_root_for_universe``
    so this exporter follows the same ``<universe_dir>/wiki`` convention as the
    chatbot-facing wiki API without adding an MCP action or write path.
    """
    wiki_root = _wiki_root_for_universe(universe_id)
    return export_okf_bundle(wiki_root, target_dir)


def export_okf_bundle(wiki_root: str | Path, target_dir: str | Path) -> dict[str, Any]:
    """Export a resolved wiki root's curated ``pages/**/*.md`` to ``target_dir``."""
    source_root = Path(wiki_root).resolve()
    bundle_root = Path(target_dir).resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(f"Wiki root not found: {source_root}")
    if _is_relative_to(bundle_root, source_root):
        raise ValueError("target_dir must not be inside the source wiki root")

    exported_sources, reserved_sources = _collect_exported_sources(source_root)
    link_index = _build_link_index(exported_sources, source_root)
    excluded_files = _collect_excluded_files(source_root)
    concepts: list[dict[str, str]] = []
    unresolved_links: list[dict[str, str]] = []

    bundle_root.mkdir(parents=True, exist_ok=True)
    for source_path in exported_sources:
        source_rel = _source_rel_path(source_root, source_path)
        bundle_rel = _bundle_rel_path(source_root, source_path)
        raw = source_path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(raw)
        concept_meta = _concept_frontmatter(meta, body, source_rel, bundle_rel, source_path)
        converted_body = _convert_wikilinks(
            body,
            source=bundle_rel,
            link_index=link_index,
            unresolved_links=unresolved_links,
        )
        target_path = bundle_root / bundle_rel
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            _render_markdown(concept_meta, converted_body),
            encoding="utf-8",
        )
        concepts.append({
            "id": bundle_rel.removesuffix(".md"),
            "path": bundle_rel,
            "title": str(concept_meta["title"]),
            "description": str(concept_meta.get("description", "")),
            "timestamp": str(concept_meta["timestamp"]),
        })

    _write_index(bundle_root, concepts)
    _write_log(bundle_root, concepts)

    report = _conformance_report(
        bundle_root=bundle_root,
        source_root=source_root,
        concepts=concepts,
        excluded_files=excluded_files,
        unresolved_links=unresolved_links,
        reserved_sources=reserved_sources,
    )
    return report


def _collect_exported_sources(wiki_root: Path) -> tuple[list[Path], list[str]]:
    pages_dir = wiki_root / "pages"
    if not pages_dir.is_dir():
        return [], []
    exported: list[Path] = []
    reserved_sources: list[str] = []
    for path in sorted(pages_dir.rglob("*.md")):
        if not path.is_file():
            continue
        if path.name.lower() == "soul.md":
            continue
        if path.name.lower() in _RESERVED_FILENAMES:
            reserved_sources.append(_source_rel_path(wiki_root, path))
            continue
        exported.append(path)
    return exported, reserved_sources


def _collect_excluded_files(wiki_root: Path) -> list[dict[str, str]]:
    excluded: list[dict[str, str]] = []
    for path in sorted(wiki_root.rglob("*.md")):
        if not path.is_file():
            continue
        rel = _source_rel_path(wiki_root, path)
        parts = Path(rel).parts
        reason = ""
        if path.name.lower() == "soul.md":
            reason = "soul.md"
        elif parts and parts[0] in _EXCLUDED_ROOTS:
            reason = parts[0]
        if reason:
            excluded.append({"path": rel, "reason": reason})
    return excluded


def _build_link_index(sources: list[Path], wiki_root: Path) -> dict[str, str]:
    index: dict[str, str] = {}
    for source in sources:
        bundle_rel = _bundle_rel_path(wiki_root, source)
        concept_id = bundle_rel.removesuffix(".md")
        keys = {
            source.stem,
            concept_id,
            f"pages/{concept_id}",
            bundle_rel,
            f"pages/{bundle_rel}",
        }
        for key in keys:
            normalized = _normalize_wikilink_target(key)
            if normalized and normalized not in index:
                index[normalized] = bundle_rel
    return index


def _concept_frontmatter(
    meta: dict[str, str],
    body: str,
    source_rel: str,
    bundle_rel: str,
    source_path: Path,
) -> dict[str, Any]:
    concept_type = _first_nonempty(meta.get("type", ""), meta.get("kind", ""), "note")
    title = _first_nonempty(meta.get("title", ""), _first_h1(body), _title_from_slug(bundle_rel))
    timestamp = _first_nonempty(meta.get("updated", ""), _mtime_iso(source_path))

    output: dict[str, Any] = {
        "type": concept_type,
        "title": title,
        "timestamp": timestamp,
        "workflow_original_path": source_rel,
    }
    for optional_key in ("description", "resource"):
        value = meta.get(optional_key, "").strip()
        if value:
            output[optional_key] = value
    tags = _parse_list_value(meta.get("tags", ""))
    if tags:
        output["tags"] = tags

    category = Path(bundle_rel).parts[0] if len(Path(bundle_rel).parts) > 1 else ""
    if category:
        output.setdefault("workflow_category", category)
    for key, value in meta.items():
        normalized_key = _workflow_key(key)
        if normalized_key and value.strip():
            output[f"workflow_{normalized_key}"] = value.strip()
    return output


def _convert_wikilinks(
    body: str,
    *,
    source: str,
    link_index: dict[str, str],
    unresolved_links: list[dict[str, str]],
) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_target = match.group(1).strip()
        target, separator, alias = raw_target.partition("|")
        target = target.strip()
        label = alias.strip() if separator else target
        resolved = link_index.get(_normalize_wikilink_target(target))
        if not resolved:
            unresolved_links.append({"source": source, "target": target})
            return label
        return f"[{label}](/{resolved})"

    return _WIKILINK_RE.sub(replace, body)


def _write_index(bundle_root: Path, concepts: list[dict[str, str]]) -> None:
    lines = ["---", f'okf_version: "{OKF_VERSION}"', "---", "", "# Index", ""]
    for concept in sorted(concepts, key=lambda item: item["path"]):
        description = concept.get("description", "")
        suffix = f" - {description}" if description else ""
        lines.append(f"- [{concept['title']}]({concept['path']}){suffix}")
    lines.append("")
    (bundle_root / "index.md").write_text("\n".join(lines), encoding="utf-8")


def _write_log(bundle_root: Path, concepts: list[dict[str, str]]) -> None:
    by_date: dict[str, list[dict[str, str]]] = {}
    for concept in concepts:
        date = _timestamp_date(concept.get("timestamp", ""))
        by_date.setdefault(date, []).append(concept)
    if not by_date:
        today = datetime.now(timezone.utc).date().isoformat()
        by_date[today] = []

    lines = ["# Bundle Update Log", ""]
    for date in sorted(by_date.keys(), reverse=True):
        lines.append(f"## {date}")
        entries = by_date[date]
        if entries:
            for concept in sorted(entries, key=lambda item: item["path"]):
                lines.append(
                    f"* **Export**: Added [{concept['title']}](/{concept['path']})."
                )
        else:
            lines.append("* **Creation**: Created empty OKF export bundle.")
        lines.append("")
    (bundle_root / "log.md").write_text("\n".join(lines), encoding="utf-8")


def _conformance_report(
    *,
    bundle_root: Path,
    source_root: Path,
    concepts: list[dict[str, str]],
    excluded_files: list[dict[str, str]],
    unresolved_links: list[dict[str, str]],
    reserved_sources: list[str],
) -> dict[str, Any]:
    issues: list[str] = []
    reserved_files: dict[str, dict[str, Any]] = {}

    for path in sorted(bundle_root.rglob("*.md")):
        rel = path.relative_to(bundle_root).as_posix()
        text = path.read_text(encoding="utf-8")
        if path.name == "index.md":
            valid, meta = _validate_index(rel, text)
            reserved_files[rel] = {"valid": valid, **meta}
            if not valid:
                issues.append(f"{rel}: invalid index.md structure")
            continue
        if path.name == "log.md":
            valid = _validate_log(text)
            reserved_files[rel] = {"valid": valid}
            if not valid:
                issues.append(f"{rel}: invalid log.md structure")
            continue

        meta = _parse_yamlish_frontmatter(text)
        if meta is None:
            issues.append(f"{rel}: missing or unparseable frontmatter")
        elif not meta.get("type", "").strip():
            issues.append(f"{rel}: missing non-empty type")

    for rel in reserved_sources:
        issues.append(f"{rel}: source reserved filename was not exported as a concept")

    return {
        "okf_version": OKF_VERSION,
        "source_wiki_root": source_root.as_posix(),
        "target_dir": bundle_root.as_posix(),
        "conformant": not any(
            issue
            for issue in issues
            if "source reserved filename" not in issue
        ),
        "counts": {
            "concepts_exported": len(concepts),
            "excluded_by_privacy": len(excluded_files),
            "unresolved_links": len(unresolved_links),
        },
        "concepts": concepts,
        "excluded_files": excluded_files,
        "unresolved_links": unresolved_links,
        "reserved_files": reserved_files,
        "issues": issues,
    }


def _validate_index(rel: str, text: str) -> tuple[bool, dict[str, str]]:
    if rel == "index.md" and text.startswith("---\n"):
        meta = _parse_yamlish_frontmatter(text)
        okf_version = meta.get("okf_version", "") if meta else ""
        return meta == {"okf_version": OKF_VERSION}, {"okf_version": okf_version}
    return (not text.startswith("---\n")), {}


def _validate_log(text: str) -> bool:
    has_date_heading = bool(
        re.search(r"^## \d{4}-\d{2}-\d{2}$", text, re.MULTILINE)
    )
    return not text.startswith("---\n") and has_date_heading


def _parse_yamlish_frontmatter(text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        return None
    try:
        raw_meta, _body = text.removeprefix("---\n").split("\n---\n", 1)
    except ValueError:
        return None
    meta: dict[str, str] = {}
    current_key = ""
    for line in raw_meta.splitlines():
        if not line.strip():
            continue
        if line.startswith("  "):
            continue
        key, separator, value = line.partition(":")
        if not separator or not key.strip():
            return None
        current_key = key.strip()
        meta[current_key] = value.strip().strip('"')
    return meta if current_key or not raw_meta.strip() else None


def _render_markdown(meta: dict[str, Any], body: str) -> str:
    lines = ["---"]
    for key, value in meta.items():
        lines.extend(_render_yaml_key_value(key, value))
    lines.extend(["---", ""])
    return "\n".join(lines) + body.lstrip("\n")


def _render_yaml_key_value(key: str, value: Any) -> list[str]:
    if isinstance(value, list):
        if not value:
            return []
        return [f"{key}:"] + [f"  - {_format_yaml_scalar(item)}" for item in value]
    text = str(value)
    if "\n" in text:
        return [f"{key}: |"] + [f"  {line}" for line in text.splitlines()]
    return [f"{key}: {_format_yaml_scalar(text)}"]


def _format_yaml_scalar(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return '""'
    lowered = text.lower()
    if (
        _SAFE_PLAIN_SCALAR_RE.match(text)
        and lowered not in {"null", "true", "false", "yes", "no", "on", "off"}
    ):
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _parse_list_value(value: str) -> list[str]:
    text = value.strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
        return [item.strip().strip("'\"") for item in text.split(",") if item.strip()]
    if "\n" in text:
        items: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                items.append(stripped[2:].strip().strip("'\""))
        return [item for item in items if item]
    return [text.strip("'\"")]


def _first_h1(body: str) -> str:
    match = _H1_RE.search(body)
    return match.group(1).strip() if match else ""


def _title_from_slug(bundle_rel: str) -> str:
    return Path(bundle_rel).stem.replace("-", " ").replace("_", " ").title()


def _first_nonempty(*values: str) -> str:
    for value in values:
        stripped = value.strip()
        if stripped:
            return stripped
    return ""


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat().replace(
        "+00:00",
        "Z",
    )


def _timestamp_date(timestamp: str) -> str:
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", timestamp.strip())
    if match:
        return match.group(1)
    return datetime.now(timezone.utc).date().isoformat()


def _workflow_key(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", key.strip().lower()).strip("_")


def _normalize_wikilink_target(target: str) -> str:
    normalized = target.strip().removeprefix("/").removesuffix(".md").replace("\\", "/")
    return normalized.lower()


def _source_rel_path(wiki_root: Path, path: Path) -> str:
    return path.relative_to(wiki_root).as_posix()


def _bundle_rel_path(wiki_root: Path, path: Path) -> str:
    return path.relative_to(wiki_root / "pages").as_posix()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True
