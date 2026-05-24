"""Connector catalog versioning for chatbot-host cache invalidation."""

from __future__ import annotations

# Bump when the chatbot-visible MCP tool catalog changes: tool names,
# parameters, annotations, descriptions, or structured output contracts.
DIRECTORY_TOOL_CATALOG_VERSION = "2026-05-07-issue-269"

DIRECTORY_MCP_PATH = "/mcp-directory"
VERSIONED_DIRECTORY_MCP_PATH = (
    f"{DIRECTORY_MCP_PATH}/catalog/{DIRECTORY_TOOL_CATALOG_VERSION}"
)


def directory_mcp_remote_url(base_url: str = "https://tinyassets.io") -> str:
    """Return the versioned directory MCP URL advertised to chatbot hosts."""
    return f"{base_url.rstrip('/')}{VERSIONED_DIRECTORY_MCP_PATH}"
