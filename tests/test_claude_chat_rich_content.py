"""Tests for `scripts/claude_chat.py::_extract_rich_content` + formatter.

The bug: claude.ai renders mermaid diagrams and artifacts alongside the
text reply, but `_read_last_assistant_text` only captures inner_text.
User-sim missions lost visibility into everything that wasn't prose.

The fix is selector-driven: scan the last assistant message for artifact
containers and `<pre><code class="language-X">` blocks, record them in
the trace as `[ARTIFACT: title]`, `[MERMAID]`, or `[CODE:lang]` sections.

These tests use a fake Playwright-like locator graph — enough to exercise
the traversal without a real browser.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def claude_chat(monkeypatch: pytest.MonkeyPatch):
    root = Path(__file__).resolve().parent.parent
    src = root / "scripts" / "claude_chat.py"
    spec = importlib.util.spec_from_file_location(
        "_claude_chat_rich_under_test", src,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_claude_chat_rich_under_test"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Fake Playwright locator graph
# ---------------------------------------------------------------------------


class FakeLocator:
    """A tiny Playwright-locator stand-in.

    Supports the subset `_extract_rich_content` uses:
      - .locator(selector) -> FakeLocator
      - .count() -> int
      - .nth(i) -> FakeLocator
      - .first -> FakeLocator
      - .inner_text() -> str
      - .get_attribute(name) -> str | None
    Each node can also hold an `attributes` dict and a `children`
    mapping of selector string -> list of FakeLocator.
    """

    def __init__(
        self,
        *,
        text: str = "",
        attributes: dict[str, str] | None = None,
        children: dict[str, list["FakeLocator"]] | None = None,
    ) -> None:
        self.text = text
        self.attributes = attributes or {}
        self.children = children or {}

    def locator(self, selector: str) -> "FakeLocator":
        matched = self.children.get(selector, [])
        return FakeLocatorList(matched)

    def count(self) -> int:
        return 1

    def nth(self, i: int) -> "FakeLocator":
        if i == 0:
            return self
        raise IndexError(i)

    @property
    def first(self) -> "FakeLocator":
        return self

    def inner_text(self) -> str:
        return self.text

    def get_attribute(self, name: str) -> str | None:
        return self.attributes.get(name)


class FakeLocatorList(FakeLocator):
    """Like FakeLocator but represents a list of matches."""

    def __init__(self, nodes: list[FakeLocator]) -> None:
        super().__init__()
        self._nodes = nodes

    def count(self) -> int:
        return len(self._nodes)

    def nth(self, i: int) -> FakeLocator:
        return self._nodes[i]

    @property
    def first(self) -> FakeLocator:
        return self._nodes[0] if self._nodes else FakeLocator()

    def inner_text(self) -> str:
        return self._nodes[0].inner_text() if self._nodes else ""

    def get_attribute(self, name: str) -> str | None:
        return self._nodes[0].get_attribute(name) if self._nodes else None


class FakePage:
    """Minimal page: responds to `.locator(selector)` returning FakeLocatorList."""

    def __init__(self, root_children: dict[str, list[FakeLocator]]) -> None:
        self.root = FakeLocator(children=root_children)

    def locator(self, selector: str) -> FakeLocatorList:
        return self.root.locator(selector)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _code_node(text: str, language: str = "") -> FakeLocator:
    cls = f"language-{language}" if language else ""
    return FakeLocator(text=text, attributes={"class": cls})


def _artifact_node(
    title: str, body: str,
    *,
    title_selector: str = "[data-testid*=\"artifact-title\" i]",
) -> FakeLocator:
    title_node = FakeLocator(text=title)
    return FakeLocator(
        text=body,
        children={title_selector: [title_node]},
    )


def _assistant_with(children: dict[str, list[FakeLocator]]) -> FakePage:
    """Build a page where the last assistant message exposes `children`."""
    assistant = FakeLocator(children=children)
    # `_last_assistant_locator` tries ASSISTANT_MSG_SELECTORS in order.
    # First one is 'div[data-testid="assistant-message"]'.
    return FakePage({
        'div[data-testid="assistant-message"]': [assistant],
    })


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def test_extract_returns_empty_when_no_assistant_message(claude_chat) -> None:
    page = FakePage({})
    assert claude_chat._extract_rich_content(page) == []


def test_extract_captures_mermaid_code_block(claude_chat) -> None:
    mermaid = _code_node("graph TD;\n  A-->B", language="mermaid")
    page = _assistant_with({"pre code": [mermaid]})
    items = claude_chat._extract_rich_content(page)
    assert len(items) == 1
    assert items[0]["kind"] == "mermaid"
    assert items[0]["text"] == "graph TD;\n  A-->B"
    assert items[0]["language"] == "mermaid"


def test_extract_labels_non_mermaid_code_blocks(claude_chat) -> None:
    py_node = _code_node("print('hi')", language="python")
    page = _assistant_with({"pre code": [py_node]})
    items = claude_chat._extract_rich_content(page)
    assert len(items) == 1
    assert items[0]["kind"] == "code"
    assert items[0]["language"] == "python"


def test_extract_collects_artifact_with_title(claude_chat) -> None:
    art = _artifact_node(
        title="My TinyAssets Diagram",
        body="My TinyAssets Diagram\nStep 1\nStep 2\nStep 3",
    )
    page = _assistant_with({
        '[data-testid*="artifact" i]': [art],
    })
    items = claude_chat._extract_rich_content(page)
    assert len(items) == 1
    assert items[0]["kind"] == "artifact"
    assert items[0]["title"] == "My TinyAssets Diagram"
    assert "Step 1" in items[0]["text"]


def test_extract_deduplicates_identical_text(claude_chat) -> None:
    """If an artifact container wraps the same <pre><code> we extract
    independently, don't record the body twice.
    """
    shared = "graph TD;\n  A-->B"
    art = _artifact_node(title="Diagram", body=shared)
    code = _code_node(shared, language="mermaid")
    page = _assistant_with({
        '[data-testid*="artifact" i]': [art],
        "pre code": [code],
    })
    items = claude_chat._extract_rich_content(page)
    # One artifact, then the code block with same text is skipped.
    assert len(items) == 1
    assert items[0]["kind"] == "artifact"


def test_extract_handles_multiple_code_blocks(claude_chat) -> None:
    page = _assistant_with({
        "pre code": [
            _code_node("graph A;", language="mermaid"),
            _code_node("print('x')", language="python"),
            _code_node("SELECT * FROM t", language="sql"),
        ],
    })
    items = claude_chat._extract_rich_content(page)
    assert len(items) == 3
    kinds = [i["kind"] for i in items]
    assert kinds == ["mermaid", "code", "code"]
    languages = [i["language"] for i in items]
    assert languages == ["mermaid", "python", "sql"]


def test_extract_handles_code_block_without_language(claude_chat) -> None:
    node = FakeLocator(text="no language attr", attributes={"class": ""})
    page = _assistant_with({"pre code": [node]})
    items = claude_chat._extract_rich_content(page)
    assert len(items) == 1
    assert items[0]["kind"] == "code"
    assert items[0]["language"] == ""


def test_extract_skips_empty_bodies(claude_chat) -> None:
    page = _assistant_with({
        "pre code": [_code_node("", language="mermaid")],
    })
    assert claude_chat._extract_rich_content(page) == []


def test_extract_never_raises_on_selector_errors(claude_chat) -> None:
    """If a DOM call blows up mid-traversal, return what we have instead
    of propagating the exception into user-sim.
    """

    class ExplodingLocator:
        def count(self): raise RuntimeError("boom")
        def nth(self, _i): raise RuntimeError("boom")
        @property
        def first(self): raise RuntimeError("boom")
        def inner_text(self): raise RuntimeError("boom")
        def get_attribute(self, _n): raise RuntimeError("boom")
        def locator(self, _s): raise RuntimeError("boom")

    class ExplodingPage:
        def locator(self, _s): return ExplodingLocator()

    # Should not raise.
    result = claude_chat._extract_rich_content(ExplodingPage())
    assert result == []


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def test_format_empty_list_returns_empty_string(claude_chat) -> None:
    assert claude_chat._format_rich_content([]) == ""


def test_format_artifact_section(claude_chat) -> None:
    out = claude_chat._format_rich_content([
        {"kind": "artifact", "title": "Diagram", "language": "", "text": "BODY"},
    ])
    assert "[ARTIFACT: Diagram]" in out
    assert "BODY" in out


def test_format_mermaid_section(claude_chat) -> None:
    out = claude_chat._format_rich_content([
        {"kind": "mermaid", "title": "", "language": "mermaid", "text": "graph A;"},
    ])
    assert "[MERMAID]" in out
    assert "graph A;" in out


def test_format_labels_code_with_language(claude_chat) -> None:
    out = claude_chat._format_rich_content([
        {"kind": "code", "title": "", "language": "python", "text": "print('x')"},
    ])
    assert "[CODE:python]" in out
    assert "print('x')" in out


def test_format_preserves_item_order(claude_chat) -> None:
    out = claude_chat._format_rich_content([
        {"kind": "artifact", "title": "A", "language": "", "text": "aaa"},
        {"kind": "mermaid", "title": "", "language": "mermaid", "text": "bbb"},
        {"kind": "code", "title": "", "language": "sh", "text": "ccc"},
    ])
    assert out.index("aaa") < out.index("bbb") < out.index("ccc")
