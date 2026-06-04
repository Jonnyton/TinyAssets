"""Wiki write-back effector for publishing loop result packets onto wiki pages.

This module implements an external-write sink (symmetric with
EXTERNAL_WRITE_SINK_GITHUB_PR in github_pr.py) that appends a node's
external_write_packet as a comment/section on a target wiki page.

The effector is registered in workflow/effectors/__init__.py and is
intended to be used by patch-loop runs to write their result packet
back onto the originating filing wiki page.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from workflow.effectors.base import ExternalWriteEffector, ExternalWriteResult

logger = logging.getLogger(__name__)


@dataclass
class WikiWriteConfig:
    """Configuration for the wiki write-back effector."""
    wiki_base_url: str = ""
    api_token: Optional[str] = None
    max_retries: int = 3
    retry_delay_seconds: float = 1.0


class WikiWriteEffector(ExternalWriteEffector):
    """Effector that writes a node's result packet onto a wiki page.

    The effector appends the packet as a structured section (e.g., a
    comment or a new subsection) on the target wiki page identified
    by the packet's metadata.
    """

    SINK_NAME = "wiki_write"

    def __init__(self, config: Optional[WikiWriteConfig] = None):
        self.config = config or WikiWriteConfig()
        self._session = None

    async def write(self, packet: Dict[str, Any]) -> ExternalWriteResult:
        """Write the given packet onto the target wiki page.

        Args:
            packet: The external_write_packet dict. Expected keys:
                - page_path: str, path to the wiki page (e.g., "pages/patch-requests/pr-166.md")
                - content: str, the content to append
                - section_title: Optional[str], title for the new section
                - metadata: Optional[dict], additional metadata to embed

        Returns:
            ExternalWriteResult indicating success or failure.
        """
        page_path = packet.get("page_path")
        content = packet.get("content")
        section_title = packet.get("section_title", "Loop Result")
        metadata = packet.get("metadata", {})

        if not page_path or not content:
            return ExternalWriteResult(
                success=False,
                error="Packet missing required fields: page_path, content",
                sink_name=self.SINK_NAME,
            )

        try:
            # Build the section to append
            section = self._build_section(section_title, content, metadata)

            # In a real implementation, this would call the wiki API to append.
            # For now, we simulate the write via a local file operation.
            # Replace with actual HTTP call to wiki API.
            result = await self._append_to_wiki_page(page_path, section)

            if result:
                logger.info(
                    "Successfully wrote packet to wiki page '%s'", page_path
                )
                return ExternalWriteResult(
                    success=True,
                    sink_name=self.SINK_NAME,
                    details={"page_path": page_path, "section_title": section_title},
                )
            else:
                return ExternalWriteResult(
                    success=False,
                    error="Failed to append to wiki page",
                    sink_name=self.SINK_NAME,
                )

        except Exception as e:
            logger.exception("Error writing to wiki page '%s'", page_path)
            return ExternalWriteResult(
                success=False,
                error=str(e),
                sink_name=self.SINK_NAME,
            )

    def _build_section(
        self, title: str, content: str, metadata: Dict[str, Any]
    ) -> str:
        """Build a markdown section string from the given parts."""
        lines = [f"\n## {title}\n"]
        if metadata:
            lines.append("<!-- metadata: " + json.dumps(metadata) + " -->\n")
        lines.append(content)
        if not content.endswith("\n"):
            lines.append("\n")
        return "".join(lines)

    async def _append_to_wiki_page(self, page_path: str, section: str) -> bool:
        """Append the given section to the wiki page at page_path.

        This is a stub implementation that writes to a local file.
        In production, this should be replaced with an actual wiki API call.
        """
        # TODO: Replace with actual wiki API integration
        # For now, simulate by writing to a local file for testing
        try:
            with open(page_path, "a", encoding="utf-8") as f:
                f.write(section)
            return True
        except OSError as e:
            logger.error("Failed to write to '%s': %s", page_path, e)
            return False

    async def close(self):
        """Clean up resources."""
        if self._session:
            await self._session.close()
            self._session = None


# Factory function for registration
def create_effector(config: Optional[Dict[str, Any]] = None) -> WikiWriteEffector:
    """Create a WikiWriteEffector instance from a config dict."""
    if config:
        cfg = WikiWriteConfig(**config)
    else:
        cfg = WikiWriteConfig()
    return WikiWriteEffector(config=cfg)
