"""Sandbox detection module.

Re-exports the key symbols from tinyassets.sandbox.detect so callers can do::

    from tinyassets.sandbox import detect_bwrap, SandboxStatus, SandboxUnavailableError
"""

from __future__ import annotations

from tinyassets.sandbox.detect import (
    _BWRAP_FAILURE_PATTERNS,
    SandboxStatus,
    SandboxUnavailableError,
    check_bwrap_output,
    detect_bwrap,
)

__all__ = [
    "SandboxStatus",
    "SandboxUnavailableError",
    "_BWRAP_FAILURE_PATTERNS",
    "check_bwrap_output",
    "detect_bwrap",
]
