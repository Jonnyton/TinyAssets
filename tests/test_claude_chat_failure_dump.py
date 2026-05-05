"""Tests for `scripts/claude_chat.py::_capture_failure_dump`.

The dump is the fallback diagnostic path when claude.ai's DOM shifts
or a response streams past the 180s timeout. Without it, user-sim just
sees "(timeout)" with no way to tell whether it's a Claude.ai-side
freeze or a selector drift in the script. These tests lock in the
contract: every failure produces three artifacts under
`output/claude_chat_failures/` (html + png + txt), and dump failures
themselves never crash the caller.

We don't need a real browser — the helper only needs `page.content`,
`page.screenshot`, `page.url`, and `page.evaluate`. A fake with those
four surfaces is enough.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def claude_chat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Load scripts/claude_chat.py as a module with FAILURE_DIR pointed at tmp."""
    root = Path(__file__).resolve().parent.parent
    src = root / "scripts" / "claude_chat.py"
    spec = importlib.util.spec_from_file_location("_claude_chat_under_test", src)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_claude_chat_under_test"] = module
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "FAILURE_DIR", tmp_path / "failures")
    return module


class FakePage:
    """Minimal page stand-in supporting the four methods the dump uses."""

    def __init__(
        self, *,
        html: str = "<html>ok</html>",
        url: str = "https://claude.ai/chat/fake",
        visible_text: str = "some rendered text",
        screenshot_fails: bool = False,
        html_fails: bool = False,
    ) -> None:
        self._html = html
        self.url = url
        self._visible = visible_text
        self._screenshot_fails = screenshot_fails
        self._html_fails = html_fails
        self.screenshot_calls: list[dict] = []
        self.bring_to_front_calls = 0

    def content(self) -> str:
        if self._html_fails:
            raise RuntimeError("content() blew up")
        return self._html

    def bring_to_front(self) -> None:
        self.bring_to_front_calls += 1

    def screenshot(
        self, *, path: str | None = None, full_page: bool = False,
    ) -> bytes | None:
        self.screenshot_calls.append({"path": path, "full_page": full_page})
        if self._screenshot_fails:
            raise RuntimeError("screenshot blew up")
        if path is not None:
            Path(path).write_bytes(b"fake-png")
            return None
        return b"fake-png"

    def evaluate(self, _script: str) -> str:
        if "requestAnimationFrame" in _script:
            return {"visible": True, "ready": True, "hasFrame": True}
        return self._visible


def test_dump_writes_three_artifacts(claude_chat, tmp_path: Path) -> None:
    page = FakePage(html="<html><body>hello</body></html>")
    base = claude_chat._capture_failure_dump(
        page, "input_not_found", note="user-sim P2",
    )
    assert base, "returned basename must be non-empty on success"

    failures = tmp_path / "failures"
    html_file = failures / f"{base}.html"
    png_file = failures / f"{base}.png"
    txt_file = failures / f"{base}.txt"
    assert html_file.exists()
    assert png_file.exists()
    assert txt_file.exists()

    assert "<body>hello</body>" in html_file.read_text(encoding="utf-8")
    txt = txt_file.read_text(encoding="utf-8")
    assert "reason: input_not_found" in txt
    assert "url: https://claude.ai/chat/fake" in txt
    assert "note: user-sim P2" in txt
    assert "some rendered text" in txt
    assert page.screenshot_calls[0]["full_page"] is True
    assert page.bring_to_front_calls == 1


def test_dump_sanitizes_reason_for_filename(claude_chat, tmp_path: Path) -> None:
    """Reasons used as filenames must not escape the target directory or
    blow up on unusual characters. Keep alnum + dash/underscore, truncate
    to 40 chars.
    """
    page = FakePage()
    base = claude_chat._capture_failure_dump(
        page, "../../../etc/passwd  with  spaces  and  punctuation!!!",
    )
    assert base
    # Must NOT start with "../" — path traversal must be scrubbed.
    assert ".." not in base.split("_", 1)[1]
    # Must not exceed 40 chars in the reason suffix (plus ts_ prefix ~16).
    reason_part = base.split("_", 1)[1]
    assert len(reason_part) <= 40


def test_dump_survives_screenshot_failure(claude_chat, tmp_path: Path) -> None:
    """Screenshot failure must NOT prevent html + txt from being written."""
    page = FakePage(screenshot_fails=True)
    base = claude_chat._capture_failure_dump(page, "timeout")
    assert base

    failures = tmp_path / "failures"
    assert (failures / f"{base}.html").exists()
    assert (failures / f"{base}.txt").exists()
    # .png may or may not exist; the screenshot attempt is logged but not required.


def test_dump_survives_content_failure(claude_chat, tmp_path: Path) -> None:
    """Even if page.content() blows up, we still write txt with url + note."""
    page = FakePage(html_fails=True)
    base = claude_chat._capture_failure_dump(
        page, "input_not_found", note="chat frozen",
    )
    assert base
    txt = (tmp_path / "failures" / f"{base}.txt").read_text(encoding="utf-8")
    assert "chat frozen" in txt


def test_dump_never_raises(claude_chat, tmp_path: Path) -> None:
    """The helper is called from error paths — it must not itself raise."""

    class ExplodingPage:
        def content(self): raise RuntimeError("boom")
        def screenshot(self, **_): raise RuntimeError("boom")
        def evaluate(self, *_): raise RuntimeError("boom")
        url = "https://claude.ai/"

    page = ExplodingPage()
    # No exception, returns a basename, produces whatever artifacts it can.
    base = claude_chat._capture_failure_dump(page, "all_broken")
    assert base


def test_wait_for_response_returns_timed_out_flag(claude_chat) -> None:
    """Guard the new tuple contract: (text, timed_out). Regression happens
    the moment someone changes this back to a bare str return.
    """
    import inspect
    sig = inspect.signature(claude_chat._wait_for_response_complete)
    ret = sig.return_annotation
    # `tuple[str, bool]` as parsed by typing
    assert str(ret).replace(" ", "") in (
        "tuple[str,bool]",
        "typing.Tuple[str,bool]",
    )


def test_stable_screenshot_retries_black_frame(claude_chat, tmp_path: Path) -> None:
    """A transient all-black compositor frame should be retried before save."""
    Image = pytest.importorskip("PIL.Image")
    import io

    def png(color: tuple[int, int, int]) -> bytes:
        buf = io.BytesIO()
        Image.new("RGB", (4, 4), color).save(buf, format="PNG")
        return buf.getvalue()

    class ScreenshotPage(FakePage):
        def __init__(self) -> None:
            super().__init__()
            self._frames = [png((0, 0, 0)), png((12, 20, 28))]

        def screenshot(
            self, *, path: str | None = None, full_page: bool = False,
        ) -> bytes | None:
            self.screenshot_calls.append({"path": path, "full_page": full_page})
            return self._frames.pop(0)

    page = ScreenshotPage()
    path = tmp_path / "stable.png"
    claude_chat._save_stable_screenshot(page, path, timeout_s=0.5)

    assert path.read_bytes() == png((12, 20, 28))
    assert len(page.screenshot_calls) == 2
    assert page.bring_to_front_calls == 1
