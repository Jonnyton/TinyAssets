"""Robust JSON parsing for LLM-generated output.

Wraps the ``json_repair`` library to provide a single entry point for
parsing JSON that may be malformed, wrapped in markdown fences, or
embedded in prose.  Every call site that previously did the
``json.loads`` -> regex-extract -> fallback dance should use this instead.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from json_repair import repair_json

logger = logging.getLogger(__name__)


def parse_llm_json(
    raw: str,
    *,
    fallback: Any = None,
    expect_type: type | None = None,
) -> Any:
    """Parse JSON from raw LLM output, repairing common defects.

    Parameters
    ----------
    raw
        The raw text from an LLM response.  May contain markdown fences,
        trailing prose, missing quotes, trailing commas, etc.
    fallback
        Value to return if parsing fails entirely.  Defaults to ``None``.
    expect_type
        If set, the parsed result must be an instance of this type.
        If it is not, ``fallback`` is returned instead.

    Returns
    -------
    Any
        The parsed Python object, or *fallback* on failure.
    """
    if not raw or not raw.strip():
        return fallback

    text = raw.strip()

    # Fast path: try stdlib first (cheapest, no repair overhead)
    try:
        result = json.loads(text)
        if expect_type is None or isinstance(result, expect_type):
            return result
    except (json.JSONDecodeError, TypeError):
        pass

    # Repair path: json_repair handles fences, trailing text, broken syntax
    try:
        result = repair_json(text, return_objects=True)
        if expect_type is None or isinstance(result, expect_type):
            return result
        logger.debug(
            "json_repair returned %s but expected %s",
            type(result).__name__,
            expect_type.__name__,
        )
    except Exception as exc:
        logger.debug("json_repair failed: %s", exc)

    return fallback
