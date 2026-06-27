"""Entry-point wrapper for the tinyassets-probe CLI.

Delegates to scripts/mcp_probe.py so the script stays stdlib-only and
usable standalone (python scripts/mcp_probe.py) while also being
installable as `tinyassets-probe` via pyproject.toml.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ is not on the package path — add it once.
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from mcp_probe import main  # noqa: E402


def entry_point() -> None:
    sys.exit(main())
