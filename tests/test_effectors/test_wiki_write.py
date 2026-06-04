"""Tests for the wiki write-back effector."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from workflow.effectors.wiki_write import WikiWriteConfig, WikiWriteEffector


@pytest.fixture
def temp_wiki_page() -> str:
    """Create a temporary wiki page file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("# Test Wiki Page\n\nExisting content.\n")
        path = f.name
    yield path
    Path(path).unlink(missing_ok=True)


@pytest.fixture
def effector() -> WikiWriteEffector:
    """Create a WikiWriteEffector with default config."""
    return WikiWriteEffector()


@pytest.mark.asyncio
async def test_write_success(effector: WikiWriteEffector, temp_wiki_page: str):
    """Test successful write to a wiki page."""
    packet = {
        "page_path": temp_wiki_page,
        "content": "This is the loop result content.",
        "section_title": "Loop Result",
        "metadata": {"run_id": "12345", "quality_score": 89.8},
    }
    result = await effector.write(packet)
    assert result.success is True
    assert result.sink_name == "wiki_write"
    assert result.details["page_path"] == temp_wiki_page
    assert result.details["section_title"] == "Loop Result"

    # Verify the content was appended
    with open(temp_wiki_page, "r") as f:
        content = f.read()
    assert "## Loop Result" in content
    assert "This is the loop result content." in content
    assert "12345" in content


@pytest.mark.asyncio
async def test_write_missing_fields(effector: WikiWriteEffector):
    """Test write with missing required fields."""
    packet: Dict[str, Any] = {"content": "some content"}
    result = await effector.write(packet)
    assert result.success is False
    assert "missing required fields" in result.error

    packet2: Dict[str, Any] = {"page_path": "/some/path"}
    result2 = await effector.write(packet2)
    assert result2.success is False
    assert "missing required fields" in result2.error


@pytest.mark.asyncio
async def test_write_empty_content(effector: WikiWriteEffector, temp_wiki_page: str):
    """Test write with empty content."""
    packet = {
        "page_path": temp_wiki_page,
        "content": "",
    }
    result = await effector.write(packet)
    assert result.success is False
    assert "missing required fields" in result.error


@pytest.mark.asyncio
async def test_write_invalid_path(effector: WikiWriteEffector):
    """Test write to an invalid path."""
    packet = {
        "page_path": "/nonexistent/dir/page.md",
        "content": "test content",
    }
    result = await effector.write(packet)
    assert result.success is False
    assert result.error is not None


@pytest.mark.asyncio
async def test_build_section_with_metadata(effector: WikiWriteEffector):
    """Test building a section with metadata."""
    section = effector._build_section(
        title="Test Section",
        content="Hello world",
        metadata={"key": "value"},
    )
    assert "## Test Section" in section
    assert "Hello world" in section
    assert "<!-- metadata:" in section
    assert '"key": "value"' in section


@pytest.mark.asyncio
async def test_build_section_without_metadata(effector: WikiWriteEffector):
    """Test building a section without metadata."""
    section = effector._build_section(
        title="No Metadata",
        content="Just content",
        metadata={},
    )
    assert "## No Metadata" in section
    assert "Just content" in section
    assert "<!-- metadata:" not in section


@pytest.mark.asyncio
async def test_create_effector_from_config():
    """Test factory function with config."""
    from workflow.effectors.wiki_write import create_effector

    config = {
        "wiki_base_url": "https://wiki.example.com",
        "api_token": "test-token",
        "max_retries": 5,
    }
    eff = create_effector(config)
    assert eff.config.wiki_base_url == "https://wiki.example.com"
    assert eff.config.api_token == "test-token"
    assert eff.config.max_retries == 5


@pytest.mark.asyncio
async def test_create_effector_no_config():
    """Test factory function without config."""
    from workflow.effectors.wiki_write import create_effector

    eff = create_effector()
    assert eff.config.wiki_base_url == ""
    assert eff.config.api_token is None
    assert eff.config.max_retries == 3


@pytest.mark.asyncio
async def test_close(effector: WikiWriteEffector):
    """Test close method (no-op for now)."""
    # Should not raise
    await effector.close()
