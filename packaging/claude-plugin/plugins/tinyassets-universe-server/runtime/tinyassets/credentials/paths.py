"""Canonical on-disk locations for the credential vault.

Platform ciphertext lives under ``data_dir()/private/credential-vault/v1`` so a
containerized deploy with ``TINYASSETS_DATA_DIR=/data`` gets
``/data/private/credential-vault/v1/vault.db`` inside the bind-mount. KEK files
are deliberately NOT here — they live in a root-only path OUTSIDE ``/data`` (see
:class:`~tinyassets.credentials.crypto.FileKeyProvider`).

Local (Windows) DPAPI blobs live under ``%LOCALAPPDATA%\\TinyAssets\\
credential-store\\v1`` — outside any repository or universe directory.
"""

from __future__ import annotations

import os
from pathlib import Path

from tinyassets.storage import data_dir

PLATFORM_SUBDIR = ("private", "credential-vault", "v1")
PLATFORM_DB_FILENAME = "vault.db"

LOCAL_SUBDIR = ("TinyAssets", "credential-store", "v1")


def platform_vault_dir(base: str | Path | None = None) -> Path:
    """Directory holding the platform ciphertext DB (created by callers)."""
    root = Path(base) if base is not None else data_dir()
    return root.joinpath(*PLATFORM_SUBDIR)


def platform_vault_db_path(base: str | Path | None = None) -> Path:
    """Full path to the platform SQLite vault DB."""
    return platform_vault_dir(base) / PLATFORM_DB_FILENAME


def local_store_dir(base: str | Path | None = None) -> Path:
    """Directory holding per-ref DPAPI blobs (Windows current-user custody).

    Defaults to ``%LOCALAPPDATA%\\TinyAssets\\credential-store\\v1``. ``base``
    overrides the LOCALAPPDATA root (used by tests).
    """
    if base is not None:
        root = Path(base)
    else:
        localappdata = os.environ.get("LOCALAPPDATA", "").strip()
        root = Path(localappdata) if localappdata else Path.home() / "AppData" / "Local"
    return root.joinpath(*LOCAL_SUBDIR)
