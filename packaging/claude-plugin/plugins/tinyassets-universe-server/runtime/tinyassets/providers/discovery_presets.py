"""Installed compatibility documents, separate from owner-authored metadata.

This file contains no source behavior or code callbacks. New user connections
use SourceContract; they cannot opt into bundled trust or legacy parsing.
"""

import json
from functools import cache
from pathlib import Path


@cache
def _raw():
    return Path(__file__).with_name("source_contract_presets.json").read_text(encoding="utf-8")


def bundled_discovery_documents():
    """Detached data on each read; no CWD dependency or network discovery."""
    return json.loads(_raw())


def compatibility_document():
    documents = [value for value in bundled_discovery_documents().values()
                 if value.get("compatibility_default") is True]
    if len(documents) != 1:
        raise ValueError("exactly one legacy compatibility document required")
    return documents[0]
