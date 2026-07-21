"""Portable design-artifact envelope helpers (S2-owned).

The ``tinyassets.branch_design/v1`` envelope wraps a ``build_branch`` spec so a
design can be exported from one universe and imported into another. The FORMAT
constants (``DESIGN_FORMAT`` / ``_REQUIRED_ENVELOPE_KEYS``) are owned by the
S1 ``branch_designs`` package (the repo seed authors artifacts in this format);
these connector import/export helpers are S2's and live here so
``branch_designs`` stays S1-owned and synced verbatim.
"""

from __future__ import annotations

from typing import Any

from tinyassets.branch_designs import _REQUIRED_ENVELOPE_KEYS, DESIGN_FORMAT

__all__ = [
    "DESIGN_FORMAT",
    "is_design_envelope",
    "validate_design_envelope",
    "unwrap_design_artifact",
    "wrap_spec_as_design_artifact",
]


def is_design_envelope(data: Any) -> bool:
    """True when a decoded dict CLAIMS to be a design envelope.

    The discriminator is the PRESENCE of the ``design_format`` key, NOT a
    version match: any dict carrying ``design_format`` is treated as an
    envelope and must be validated — a future/foreign version like
    ``tinyassets.branch_design/v999`` is REJECTED loudly, never silently
    accepted as a raw ``build_branch`` spec. A dict WITHOUT ``design_format``
    is a raw spec.
    """
    return isinstance(data, dict) and "design_format" in data


def _validate_design_identity(design_id: Any, design_version: Any) -> None:
    """Type-gate the envelope identity fields — ``design_id`` a non-empty
    string, ``design_version`` a positive integer; no silent coercion."""
    if not isinstance(design_id, str) or not design_id.strip():
        raise ValueError(
            f"design_id must be a non-empty string, got "
            f"{type(design_id).__name__} ({design_id!r})"
        )
    # bool is a subclass of int — exclude it explicitly.
    if (
        isinstance(design_version, bool)
        or not isinstance(design_version, int)
        or design_version < 1
    ):
        raise ValueError(
            f"design_version must be a positive integer, got "
            f"{type(design_version).__name__} ({design_version!r})"
        )


def validate_design_envelope(data: Any) -> None:
    """Raise ``ValueError`` unless ``data`` is a well-formed v1 envelope."""
    if not isinstance(data, dict):
        raise ValueError("design artifact must be a JSON object")
    missing = [k for k in _REQUIRED_ENVELOPE_KEYS if k not in data]
    if missing:
        raise ValueError(f"missing envelope keys: {missing}")
    if data["design_format"] != DESIGN_FORMAT:
        raise ValueError(
            f"unsupported design_format {data['design_format']!r} "
            f"(expected {DESIGN_FORMAT!r})"
        )
    _validate_design_identity(data["design_id"], data["design_version"])
    if not isinstance(data["spec"], dict):
        raise ValueError("design artifact 'spec' must be a JSON object")


def unwrap_design_artifact(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the ``build_branch`` spec carried by an envelope
    (validated; fail loud)."""
    validate_design_envelope(data)
    return dict(data["spec"])


def wrap_spec_as_design_artifact(
    spec: dict[str, Any],
    *,
    design_id: str,
    design_version: int = 1,
    title: str = "",
    provenance: str = "",
) -> dict[str, Any]:
    """Wrap a ``build_branch`` spec in the portable envelope (validates the
    identity fields — no silent coercion on export)."""
    _validate_design_identity(design_id, design_version)
    return {
        "design_format": DESIGN_FORMAT,
        "design_id": design_id,
        "design_version": design_version,
        "title": title or (spec.get("name") or ""),
        "provenance": provenance,
        "spec": spec,
    }
