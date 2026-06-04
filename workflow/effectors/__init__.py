"""Effectors package for external write operations.

Each effector implements the ExternalWriteEffector interface and is
registered here for discovery by the workflow engine.
"""

from __future__ import annotations

from typing import Dict, Type

from workflow.effectors.base import ExternalWriteEffector
from workflow.effectors.github_pr import GitHubPREffector
from workflow.effectors.github_read import GitHubReadEffector
from workflow.effectors.github_search import GitHubSearchEffector
from workflow.effectors.windows_desktop import WindowsDesktopEffector
from workflow.effectors.wiki_write import WikiWriteEffector

# Registry of all available effectors by sink name
EFFECTOR_REGISTRY: Dict[str, Type[ExternalWriteEffector]] = {
    "github_pr": GitHubPREffector,
    "github_read": GitHubReadEffector,
    "github_search": GitHubSearchEffector,
    "windows_desktop": WindowsDesktopEffector,
    "wiki_write": WikiWriteEffector,
}

__all__ = [
    "EFFECTOR_REGISTRY",
    "ExternalWriteEffector",
    "GitHubPREffector",
    "GitHubReadEffector",
    "GitHubSearchEffector",
    "WindowsDesktopEffector",
    "WikiWriteEffector",
]
