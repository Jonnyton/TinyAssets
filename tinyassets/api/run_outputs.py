"""Bounded, lossless views of persisted run output (no second output store)."""
from __future__ import annotations

import json
from typing import Any

DEFAULT_OUTPUT_CHARS = 8192
MAX_OUTPUT_CHARS = 32768
CATALOG_PAGE_FIELDS = 64


def _serialized(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def output_catalog(output: dict[str, Any], *, offset: int = 0) -> dict[str, Any]:
    """Field metadata only; offset is a field index, not a content cursor."""
    names = sorted(output)
    selected = names[offset:offset + CATALOG_PAGE_FIELDS]
    end = offset + len(selected)
    return {
        "fields": [
            {"name": name, "type": type(output[name]).__name__,
             "total_chars": len(_serialized(output[name]))}
            for name in selected
        ],
        "offset": offset,
        "total_fields": len(names),
        "next_offset": end if end < len(names) else None,
        "offset_unit": "fields",
    }


def read_output(
    output: dict[str, Any], *, field_name: str = "", offset: int = 0,
    max_chars: int = DEFAULT_OUTPUT_CHARS,
) -> dict[str, Any]:
    """Strings stay verbatim; other fields are chunked Unicode JSON.

    The exact typed value is present only on a complete first read. Continuation
    never masquerades as a complete value. Limits bound transport, not run output.
    """
    if type(offset) is not int or offset < 0:
        return {"error": "output_offset must be a non-negative integer."}
    if type(max_chars) is not int or not 1 <= max_chars <= MAX_OUTPUT_CHARS:
        return {"error": f"output_max_chars must be between 1 and {MAX_OUTPUT_CHARS}."}
    if not field_name:
        if offset > len(output):
            return {"error": "output_offset is past the field catalog."}
        return {"output_catalog": output_catalog(output, offset=offset)}
    if field_name not in output:
        return {"error": f"Output field '{field_name}' not present on run.",
                "output_catalog": output_catalog(output)}
    value = output[field_name]
    serialized = _serialized(value)
    total = len(serialized)
    if offset > total:
        return {"error": "output_offset is past the selected field."}
    chunk = serialized[offset:offset + max_chars]
    end = offset + len(chunk)
    result = {
        "field_name": field_name,
        "encoding": "text" if isinstance(value, str) else "json",
        "chunk": chunk, "offset": offset, "length": len(chunk),
        "total_chars": total, "offset_unit": "unicode_code_points",
        "truncated": end < total, "next_offset": end if end < total else None,
    }
    if offset == 0 and end == total:
        result["value"] = value
    return result
