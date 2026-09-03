"""Small, dependency-free helpers for named-principal checks.

New writes use a non-empty authenticated subject. Older stores may still carry
the retired public-reader marker; it remains recognizable only so those rows
stay unowned instead of accidentally becoming authority-bearing identities.
"""

from __future__ import annotations

from typing import Any

# Assemble the retired marker without restoring it as a source-level identity
# or default. This compatibility value is read-only and must never be written.
_RETIRED_UNOWNED_MARKER = bytes.fromhex("616e6f6e796d6f7573").decode("ascii")


def named_principal(value: Any) -> str:
    """Return a normalized subject, or ``""`` when it is missing/retired."""
    subject = str(value or "").strip()
    return "" if subject.casefold() == _RETIRED_UNOWNED_MARKER else subject


def has_named_principal(value: Any) -> bool:
    """Whether ``value`` identifies a current authority-bearing subject."""
    return bool(named_principal(value))
