"""Version-independent MCP tool parameter descriptions.

FastMCP's docstring->schema extraction is version-dependent: ``fastmcp``
3.2.0 ships none, 3.4.x parses Google-style ``Args:`` blocks. The live
``/mcp`` surface must advertise the *same* labelled tool contract on
every FastMCP/Python combination, so we parse the ``Args:`` block
ourselves at registration time and inject the descriptions into the
adapter's signature + annotations. FastMCP reads parameter descriptions
from ``__annotations__`` on all versions, so this lands the labels
deterministically without per-parameter ``Field`` boilerplate.

Design: the function docstring is the *default* source of truth; an
explicit ``Annotated[T, Field(description=...)]`` at the parameter site
*overrides* it (we never clobber an existing ``Field``). That layering
keeps one description per parameter while still allowing a hand-tuned
override where a docstring line would be awkward.
"""

from __future__ import annotations

import logging
import re
from inspect import Parameter, Signature, signature
from typing import Annotated, get_type_hints

from pydantic import Field
from pydantic.fields import FieldInfo

logger = logging.getLogger("mcp_schema_utils")

# Section headers that terminate a Google-style ``Args:`` block.
_DOC_SECTIONS = frozenset(
    {
        "Returns",
        "Return",
        "Raises",
        "Yields",
        "Examples",
        "Example",
        "Note",
        "Notes",
        "Attributes",
        "See Also",
    }
)

_ARG_LINE = re.compile(r"^(\w+)\s*(?:\([^)]*\))?:\s*(.*)$")


def parse_docstring_args(doc: str | None) -> dict[str, str]:
    """Extract ``{param: description}`` from a Google-style ``Args:`` block.

    Continuation lines (indented under a parameter) are folded into that
    parameter's description. Returns an empty dict when there is no
    ``Args:`` block.
    """
    if not doc:
        return {}
    out: dict[str, str] = {}
    in_args = False
    cur: str | None = None
    buf: list[str] = []

    def _flush() -> None:
        if cur is not None:
            out[cur] = " ".join(buf).strip()

    for line in doc.splitlines():
        stripped = line.strip()
        if stripped == "Args:":
            in_args = True
            continue
        if not in_args:
            continue
        if stripped.endswith(":") and stripped[:-1] in _DOC_SECTIONS:
            _flush()
            cur = None
            buf = []
            break
        match = _ARG_LINE.match(stripped)
        if match:
            _flush()
            cur = match.group(1)
            buf = [match.group(2)] if match.group(2) else []
        elif stripped and cur is not None:
            buf.append(stripped)
    _flush()
    return out


def _has_explicit_field(annotation: object) -> bool:
    """True when ``annotation`` already declares a pydantic ``Field``.

    ``get_origin(Annotated[T, ...])`` returns ``T`` (not ``Annotated``), so
    detection goes through ``__metadata__``, which only ``Annotated`` types
    carry.
    """
    metadata = getattr(annotation, "__metadata__", ())
    return any(isinstance(meta, FieldInfo) for meta in metadata)


def describe_signature(fn) -> tuple[Signature, dict[str, object]]:
    """Build a labelled ``(signature, annotations)`` pair for an MCP adapter.

    The returned signature has return annotation ``dict`` (FastMCP adapters
    return a structured dict) and each documented parameter without an
    explicit ``Field`` gains ``Annotated[ann, Field(description=...)]``.
    The annotations dict mirrors the signature because FastMCP reads
    parameter descriptions from ``__annotations__``. Assign both onto the
    wrapper::

        _tool.__signature__, _tool.__annotations__ = describe_signature(fn)
    """
    sig = signature(fn)
    # Both MCP server modules use ``from __future__ import annotations``
    # (PEP 563), so ``sig.parameters[...].annotation`` is a *string*.
    # Resolve to real types (preserving ``Annotated`` metadata) so explicit
    # ``Field`` overrides are detected and the injected schema is correct.
    try:
        hints = get_type_hints(fn, include_extras=True)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("could not resolve type hints for %s: %s", getattr(fn, "__name__", fn), exc)
        hints = {}
    descriptions = parse_docstring_args(fn.__doc__)
    params = []
    for name, param in sig.parameters.items():
        annotation = hints.get(name, param.annotation)
        if (
            name in descriptions
            and descriptions[name]
            and annotation is not Parameter.empty
            and not _has_explicit_field(annotation)
        ):
            annotation = Annotated[annotation, Field(description=descriptions[name])]
        # Always carry the resolved (real-type) annotation so FastMCP and
        # the override check see types, not PEP 563 strings.
        if annotation is not Parameter.empty:
            param = param.replace(annotation=annotation)
        params.append(param)
    new_sig = sig.replace(parameters=params, return_annotation=dict)
    annotations: dict[str, object] = {
        name: param.annotation
        for name, param in new_sig.parameters.items()
        if param.annotation is not Parameter.empty
    }
    annotations["return"] = dict
    return new_sig, annotations
