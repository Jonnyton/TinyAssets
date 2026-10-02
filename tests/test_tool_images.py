"""The harness `read` shows an image to the model, bounded (pi's read behaviour).

The agent could not see what it made -- art it rendered, a screenshot of a UI
it built (founder's village, 2026-10-02). These pin the one shared rule every
file-reading tool uses (tinyassets.tool_images) and the engine `read` returning
it as image content through the real MCP middleware stack.
"""

from __future__ import annotations

import asyncio
import io
import struct
import zlib
from pathlib import Path

import pytest
from PIL import Image

from tests.engine_authority_helpers import mock_engine_admission
from tinyassets import tool_images, universe_tools
from tinyassets.tool_images import ToolImage, bound_image
from tinyassets.universe_tools import ToolRun


def _encode(image: Image.Image, fmt: str, **options) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, fmt, **options)
    return buffer.getvalue()


def _png(width: int, height: int, color=(40, 120, 200)) -> bytes:
    return _encode(Image.new("RGB", (width, height), color), "PNG")


def _shown(result: ToolImage) -> Image.Image:
    return Image.open(io.BytesIO(result.data))


# --------------------------------------------------------------------------- #
# the shared bound
# --------------------------------------------------------------------------- #


def test_a_small_image_is_shown_as_it_is():
    data = _png(64, 32)
    shown = bound_image(data, "art/tile.png")
    assert isinstance(shown, ToolImage)
    assert shown.data == data and shown.mime_type == "image/png"
    assert (shown.width, shown.height) == (64, 32)
    assert "art/tile.png: 64x32 image/png" == shown.text


def test_a_large_image_is_scaled_to_the_long_edge():
    shown = bound_image(_png(4000, 2000), "shot.png")
    assert isinstance(shown, ToolImage)
    assert (shown.width, shown.height) == (tool_images.MAX_EDGE, tool_images.MAX_EDGE // 2)
    assert _shown(shown).size == (shown.width, shown.height)
    assert len(shown.data) <= tool_images.MAX_IMAGE_BYTES
    assert "4000x2000" in shown.text and "shown as 1568x784" in shown.text


def test_transparency_survives_scaling_and_noise_is_squeezed_under_the_byte_bound():
    rgba = Image.new("RGBA", (2000, 2000), (0, 0, 0, 0))
    shown = bound_image(_encode(rgba, "PNG"), "sprite.png")
    assert isinstance(shown, ToolImage) and shown.mime_type == "image/png"
    assert _shown(shown).mode == "RGBA"
    import random

    noise = Image.frombytes("RGB", (1500, 1500), random.Random(0).randbytes(1500 * 1500 * 3))
    loud = bound_image(_encode(noise, "PNG"), "noise.png")
    assert isinstance(loud, ToolImage), loud
    assert len(loud.data) <= tool_images.MAX_IMAGE_BYTES


@pytest.mark.parametrize("fmt, mime", [("JPEG", "image/jpeg"), ("WEBP", "image/webp"),
                                       ("GIF", "image/gif")])
def test_each_supported_format_is_recognised_by_its_bytes(fmt, mime):
    data = _encode(Image.new("RGB", (40, 30), (200, 10, 10)), fmt)
    shown = bound_image(data, "x." + fmt.lower())
    assert isinstance(shown, ToolImage) and shown.mime_type == mime


def test_an_animated_gif_shows_its_first_frame():
    frames = [Image.new("RGB", (20, 20), c) for c in ((255, 0, 0), (0, 255, 0))]
    data = _encode(frames[0], "GIF", save_all=True, append_images=frames[1:], duration=50)
    shown = bound_image(data, "walk.gif")
    assert isinstance(shown, ToolImage) and "(first frame)" in shown.text
    red, green, _ = _shown(shown).convert("RGB").getpixel((5, 5))
    assert red > 240 and green < 16, "the first frame, not the second"


def test_a_declared_giant_canvas_is_refused_before_it_is_decoded():
    """A few hundred bytes can declare a gigapixel PNG; decoding it would take
    the daemon's memory, so the header is checked first."""
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    bomb = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 40000, 40000, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00" * 64)) + chunk(b"IEND", b""))
    assert len(bomb) < 200
    refused = bound_image(bomb, "bomb.png")
    assert isinstance(refused, str) and "pixel bound" in refused, refused
    # Between Pillow's own guard and ours, the header check is what refuses.
    mid = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", 6000, 6000, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"\x00" * 64)) + chunk(b"IEND", b""))
    refused = bound_image(mid, "mid.png")
    assert isinstance(refused, str) and "6000x6000" in refused, refused


def test_the_extension_is_not_trusted():
    refused = bound_image(b"#!/bin/sh\necho not an image\n", "evil.png")
    assert isinstance(refused, str) and "its bytes say otherwise" in refused
    refused = bound_image(b"<svg xmlns='http://www.w3.org/2000/svg'/>", "x.png")
    assert isinstance(refused, str)


def test_a_truncated_image_is_refused_with_a_reason():
    data = _png(2000, 2000)[:400]
    refused = bound_image(data, "cut.png")
    assert isinstance(refused, str) and "could not be decoded" in refused


# --------------------------------------------------------------------------- #
# universe_tools.read_file: the jailed read
# --------------------------------------------------------------------------- #


class _Spy:
    def __init__(self, run: ToolRun) -> None:
        self.calls: list[dict] = []
        self._run = run

    def __call__(self, universe_dir, inner, **kwargs):
        self.calls.append({"inner": list(inner), **kwargs})
        return self._run


def _universe(tmp_path: Path) -> Path:
    path = tmp_path / "data" / "u-alpha"
    path.mkdir(parents=True)
    return path


def test_an_image_is_read_whole_inside_the_jail_with_its_own_output_cap(tmp_path, monkeypatch):
    data = _png(10, 10)
    spy = _Spy(ToolRun(0, data, None, 0.0))
    monkeypatch.setattr(universe_tools, "RUNNER", spy)
    shown = universe_tools.read_file(_universe(tmp_path), "previews/village.png")
    assert isinstance(shown, ToolImage) and shown.data == data
    call = spy.calls[0]
    assert call["inner"][-1] == "/u/previews/village.png"
    assert "cat --" in call["inner"][2]
    assert call["limits"].output_bytes == tool_images.MAX_IMAGE_SOURCE_BYTES
    # Every other limit is the default: only the output cap is raised.
    assert call["limits"].memory_bytes == universe_tools.DEFAULT_LIMITS.memory_bytes
    assert call["limits"].wall_seconds == universe_tools.DEFAULT_LIMITS.wall_seconds


def test_text_reads_keep_the_default_cap(tmp_path, monkeypatch):
    spy = _Spy(ToolRun(0, b"hello\n", None, 0.0))
    monkeypatch.setattr(universe_tools, "RUNNER", spy)
    assert universe_tools.read_file(_universe(tmp_path), "notes/a.md") == "hello\n"
    assert spy.calls[0]["limits"].output_bytes == universe_tools.DEFAULT_LIMITS.output_bytes


@pytest.mark.parametrize("run, needle", [
    (ToolRun(None, b"x" * 10, "output_limit", 0.0), "too large to show"),
    (ToolRun(1, b"no such file: /u/a.png\n", None, 0.0), "no such file"),
    (ToolRun(0, b"plain text, misnamed", None, 0.0), "its bytes say otherwise"),
])
def test_an_unreadable_image_is_an_error_line(tmp_path, monkeypatch, run, needle):
    monkeypatch.setattr(universe_tools, "RUNNER", _Spy(run))
    out = universe_tools.read_file(_universe(tmp_path), "a.png")
    assert isinstance(out, str) and out.startswith("error:") and needle in out


# --------------------------------------------------------------------------- #
# the engine `read`: image content through the real middleware stack
# --------------------------------------------------------------------------- #


def test_the_engine_read_returns_image_content_the_client_accepts(tmp_path, monkeypatch):
    from fastmcp import Client

    import tinyassets.api.helpers as helpers
    from tinyassets import engine_mcp_server as s

    root = tmp_path / "data"
    (root / "u-a").mkdir(parents=True)
    monkeypatch.setattr(helpers, "_base_path", lambda: root)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    monkeypatch.setenv("TINYASSETS_ENGINE_MCP_TOOLS", "1")
    monkeypatch.setattr(s, "_ACTOR_ID", "actor-a")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-a")
    mock_engine_admission(monkeypatch, {"u-a"})
    image = _png(3000, 1000)

    def runner(universe_dir, inner, **kwargs):
        return ToolRun(0, image if inner[-1].endswith(".png") else b"text body\n", None, 0.0)

    monkeypatch.setattr(universe_tools, "RUNNER", runner)

    async def calls():
        async with Client(s.mcp) as client:
            tool = next(t for t in await client.list_tools() if t.name == "read")
            shot = await client.call_tool("read", {"path": "previews/v.png"},
                                          raise_on_error=False)
            text = await client.call_tool("read", {"path": "notes/a.md"},
                                          raise_on_error=False)
            return tool, shot, text

    tool, shot, text = asyncio.run(calls())
    assert tool.outputSchema is None
    assert not shot.is_error, shot
    kinds = [block.type for block in shot.content]
    assert kinds == ["text", "image"], kinds
    assert shot.content[1].mimeType in ("image/png", "image/jpeg")
    assert "shown as 1568x523" in shot.content[0].text
    assert not text.is_error and text.content[0].text.startswith("text body")
