"""Scoped reader for large Markdown, text, and JSON artifacts.

The goal is to give agents a deterministic way to inspect oversized files
without falling back to raw whole-file reads that are likely to be truncated
by the host toolchain.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_MAX_CHARS = 12_000
LIST_PREVIEW_ITEMS = 20


@dataclass(frozen=True)
class MarkdownHeading:
    """Heading discovered in a Markdown document."""

    level: int
    title: str
    line_number: int


@dataclass(frozen=True)
class SearchMatch:
    """A single line-oriented search hit with bounded context."""

    match_line: int
    start_line: int
    end_line: int
    excerpt: str


def read_text_file(path: Path) -> str:
    """Read a text file as UTF-8 with replacement for invalid bytes."""

    return path.read_text(encoding="utf-8", errors="replace")


def file_kind(path: Path) -> str:
    """Infer the file kind from the filename."""

    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix == ".json":
        return "json"
    return "text"


def text_stats(path: Path) -> dict[str, Any]:
    """Return basic file metadata for quick triage."""

    text = read_text_file(path)
    return {
        "path": str(path),
        "kind": file_kind(path),
        "bytes": path.stat().st_size,
        "lines": len(text.splitlines()),
        "chars": len(text),
    }


def _normalize_heading(title: str) -> str:
    return " ".join(title.strip().split()).casefold()


def list_markdown_headings(text: str) -> list[MarkdownHeading]:
    """Return Markdown headings, ignoring fenced code blocks."""

    headings: list[MarkdownHeading] = []
    in_fence = False
    fence_marker = ""

    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            continue

        if in_fence:
            continue

        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", stripped)
        if not match:
            continue

        title = match.group(2).rstrip("#").rstrip()
        headings.append(
            MarkdownHeading(
                level=len(match.group(1)),
                title=title,
                line_number=index,
            )
        )

    return headings


def extract_markdown_section(text: str, heading: str) -> str:
    """Extract a Markdown heading and its body until the next peer/parent heading."""

    headings = list_markdown_headings(text)
    normalized = _normalize_heading(heading)

    start_heading = next(
        (item for item in headings if _normalize_heading(item.title) == normalized),
        None,
    )
    if start_heading is None:
        raise ValueError(f"Heading not found: {heading!r}")

    lines = text.splitlines()
    end_line = len(lines)

    for candidate in headings:
        if candidate.line_number <= start_heading.line_number:
            continue
        if candidate.level <= start_heading.level:
            end_line = candidate.line_number - 1
            break

    return extract_text_lines(text, start_heading.line_number, end_line)


def extract_text_lines(text: str, start_line: int, end_line: int) -> str:
    """Return a bounded, inclusive line range."""

    lines = text.splitlines()
    if not lines:
        return ""

    start = max(1, start_line)
    end = min(len(lines), end_line)
    if start > end:
        return ""

    return "\n".join(lines[start - 1 : end])


def search_text(
    text: str,
    pattern: str,
    *,
    context_lines: int = 2,
    ignore_case: bool = False,
) -> list[SearchMatch]:
    """Search line by line and return matches with context."""

    flags = re.IGNORECASE if ignore_case else 0
    regex = re.compile(pattern, flags)
    lines = text.splitlines()
    matches: list[SearchMatch] = []

    for index, line in enumerate(lines, start=1):
        if not regex.search(line):
            continue
        start = max(1, index - context_lines)
        end = min(len(lines), index + context_lines)
        excerpt = "\n".join(lines[start - 1 : end])
        matches.append(
            SearchMatch(
                match_line=index,
                start_line=start,
                end_line=end,
                excerpt=excerpt,
            )
        )

    return matches


def resolve_json_pointer(payload: Any, pointer: str) -> Any:
    """Resolve a RFC 6901 JSON Pointer against a loaded JSON payload."""

    if pointer in {"", "/"}:
        return payload
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must start with '/' or be empty")

    current = payload
    for raw_part in pointer.split("/")[1:]:
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            try:
                index = int(part)
            except ValueError as exc:
                raise ValueError(f"List segment must be an integer: {part!r}") from exc
            try:
                current = current[index]
            except IndexError as exc:
                raise ValueError(f"List index out of range: {index}") from exc
            continue
        if isinstance(current, dict):
            if part not in current:
                raise ValueError(f"Object key not found: {part!r}")
            current = current[part]
            continue
        raise ValueError(f"Cannot descend through non-container node at segment {part!r}")

    return current


def _slice_list_value(value: Any, start: int | None, end: int | None) -> Any:
    if isinstance(value, list) and (start is not None or end is not None):
        return value[start:end]
    if start is not None or end is not None:
        raise ValueError("Start/end slicing is only valid when the resolved JSON node is a list")
    return value


def _ensure_bounded_output(rendered: str, max_chars: int) -> str:
    if len(rendered) > max_chars:
        raise ValueError(
            f"Result too large ({len(rendered)} chars > {max_chars}); narrow the query"
        )
    return rendered


def _json_node_summary(value: Any) -> str:
    if isinstance(value, dict):
        return f"object keys={len(value)}"
    if isinstance(value, list):
        return f"list len={len(value)}"
    return type(value).__name__


def render_json_keys(payload: Any, *, pointer: str = "", max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Render child keys/items for a JSON object or list."""

    value = resolve_json_pointer(payload, pointer)

    if isinstance(value, dict):
        lines = [f"{key}\t{_json_node_summary(child)}" for key, child in value.items()]
    elif isinstance(value, list):
        lines = [f"[list len={len(value)} preview={min(len(value), LIST_PREVIEW_ITEMS)}]"]
        lines.extend(
            f"{index}\t{_json_node_summary(child)}"
            for index, child in enumerate(value[:LIST_PREVIEW_ITEMS])
        )
    else:
        raise ValueError("json-keys requires the resolved node to be an object or list")

    rendered = "\n".join(lines)
    return _ensure_bounded_output(rendered, max_chars)


def render_json_value(
    payload: Any,
    *,
    pointer: str = "",
    start: int | None = None,
    end: int | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str:
    """Render a JSON value, optionally slicing a resolved list."""

    value = resolve_json_pointer(payload, pointer)
    value = _slice_list_value(value, start, end)
    rendered = json.dumps(value, indent=2, ensure_ascii=True)
    return _ensure_bounded_output(rendered, max_chars)


def render_matches(matches: list[SearchMatch], max_chars: int) -> str:
    """Render search hits in a readable, line-numbered format."""

    chunks = []
    for match in matches:
        chunks.append(
            "\n".join(
                [
                    f"Match line {match.match_line} (context {match.start_line}-{match.end_line}):",
                    match.excerpt,
                ]
            )
        )
    rendered = "\n\n".join(chunks)
    return _ensure_bounded_output(rendered, max_chars)


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI parser."""

    parser = argparse.ArgumentParser(description="Scoped reader for large project docs")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--max-chars", type=int)

    subparsers = parser.add_subparsers(dest="command", required=True)

    stat_parser = subparsers.add_parser("stat", help="Show basic file stats", parents=[common])
    stat_parser.add_argument("path")

    headings_parser = subparsers.add_parser(
        "headings",
        help="List Markdown headings",
        parents=[common],
    )
    headings_parser.add_argument("path")

    section_parser = subparsers.add_parser(
        "section",
        help="Show one Markdown section",
        parents=[common],
    )
    section_parser.add_argument("path")
    section_parser.add_argument("--heading", required=True)

    lines_parser = subparsers.add_parser(
        "lines",
        help="Show an inclusive line range",
        parents=[common],
    )
    lines_parser.add_argument("path")
    lines_parser.add_argument("--start", type=int, required=True)
    lines_parser.add_argument("--end", type=int, required=True)

    search_parser = subparsers.add_parser(
        "search",
        help="Search text with context",
        parents=[common],
    )
    search_parser.add_argument("path")
    search_parser.add_argument("--pattern", required=True)
    search_parser.add_argument("--context", type=int, default=2)
    search_parser.add_argument("--ignore-case", action="store_true")

    json_keys_parser = subparsers.add_parser(
        "json-keys",
        help="List child keys/items at a JSON node",
        parents=[common],
    )
    json_keys_parser.add_argument("path")
    json_keys_parser.add_argument("--pointer", default="")

    json_parser = subparsers.add_parser(
        "json",
        help="Show a JSON node by pointer",
        parents=[common],
    )
    json_parser.add_argument("path")
    json_parser.add_argument("--pointer", default="")
    json_parser.add_argument("--start", type=int)
    json_parser.add_argument("--end", type=int)

    return parser


def run_docview(argv: list[str] | None = None) -> str:
    """Execute the requested subcommand and return the rendered output."""

    parser = build_parser()
    args = parser.parse_args(argv)
    max_chars = args.max_chars if args.max_chars is not None else DEFAULT_MAX_CHARS
    path = Path(args.path).resolve()
    if not path.is_file():
        raise ValueError(f"File not found: {path}")

    if args.command == "stat":
        return json.dumps(text_stats(path), indent=2, ensure_ascii=True)

    text = read_text_file(path)

    if args.command == "headings":
        headings = list_markdown_headings(text)
        rendered = "\n".join(
            f"L{heading.line_number:04d} H{heading.level} {heading.title}" for heading in headings
        )
        return _ensure_bounded_output(rendered, max_chars)

    if args.command == "section":
        section = extract_markdown_section(text, args.heading)
        return _ensure_bounded_output(section, max_chars)

    if args.command == "lines":
        excerpt = extract_text_lines(text, args.start, args.end)
        return _ensure_bounded_output(excerpt, max_chars)

    if args.command == "search":
        matches = search_text(
            text,
            args.pattern,
            context_lines=args.context,
            ignore_case=args.ignore_case,
        )
        if not matches:
            return "No matches."
        return render_matches(matches, max_chars)

    payload = json.loads(text)

    if args.command == "json-keys":
        return render_json_keys(payload, pointer=args.pointer, max_chars=max_chars)

    if args.command == "json":
        return render_json_value(
            payload,
            pointer=args.pointer,
            start=args.start,
            end=args.end,
            max_chars=max_chars,
        )

    raise ValueError(f"Unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""

    try:
        output = run_docview(argv)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    write_output(output)
    return 0


def write_output(
    output: str,
    *,
    stream: Any | None = None,
    binary_stream: Any | None = None,
) -> None:
    """Write output without crashing on narrow console encodings."""

    target = stream or sys.stdout
    fallback = binary_stream or getattr(target, "buffer", None)

    try:
        target.write(output)
        target.write("\n")
    except UnicodeEncodeError:
        if fallback is None:
            raise
        encoding = getattr(target, "encoding", None) or "utf-8"
        fallback.write(output.encode(encoding, errors="replace"))
        fallback.write(b"\n")


if __name__ == "__main__":
    raise SystemExit(main())
