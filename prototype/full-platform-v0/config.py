"""Prototype v0 config — env-var driven.

Testnet-phase posture: secrets live OUTSIDE the project folder per
host directive 2026-04-19 (task #65). No vault needed this iteration;
file at a user-home path, env-var configurable for portability.

Real-currency phase later: multisig + proper vault (1Password /
Bitwarden / HashiCorp Vault) + hardware-signing at launch.
See SUCCESSION.md §3.
"""

from __future__ import annotations

import os
from pathlib import Path


def treasury_key_path() -> Path:
    """Return the filesystem path to the treasury wallet seed file.

    Precedence:
        1. TINYASSETS_TREASURY_KEY_PATH env var (explicit override).
        2. ~/.workflow-secrets/base-sepolia-treasury-v0.txt (default).

    The file itself is gitignored + lives outside the project folder.
    This function only returns the path; callers are responsible for
    reading + parsing (and for refusing to log the contents).
    """
    env = os.environ.get("TINYASSETS_TREASURY_KEY_PATH")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".workflow-secrets" / "base-sepolia-treasury-v0.txt"


def treasury_key_exists() -> bool:
    """Cheap existence check. Never reads contents."""
    return treasury_key_path().is_file()


__all__ = ["treasury_key_path", "treasury_key_exists"]
