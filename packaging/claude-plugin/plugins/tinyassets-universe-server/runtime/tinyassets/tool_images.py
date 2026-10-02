"""An image a tool reads, bounded so it can be shown to the model.

The harness ``read`` tool shows an image file to the model the way pi.dev's does,
so the agent can look at what it made: art it rendered, a screenshot of a UI it
built (founder's village, 2026-10-02: the agent had no way to see its screen).
Every tool surface that reads files -- the engine-MCP ``read`` and the thin agent
loop's box ``read`` -- goes through :func:`bound_image`, so the bound is one rule.

The bytes are untrusted (anything in the agent's folder). Nothing here passes an
image through on its file extension: the format comes from the magic bytes, the
pixel count is bounded BEFORE decoding (a 1 KB PNG can declare a gigapixel
canvas), and anything that does not fit is downscaled and re-encoded, or refused
with a reason. The result is small enough for a model's context: at most
``MAX_EDGE`` pixels on the long edge and about ``MAX_IMAGE_BYTES`` bytes.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Any

#: Extensions ``read`` treats as images; everything else stays text.
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
#: Raw bytes a reader may take from the file before bounding (the jail's output
#: cap for an image read).
MAX_IMAGE_SOURCE_BYTES = 20 * 1024 * 1024
#: Pixels decoded at most; a larger declared canvas is refused unread.
MAX_SOURCE_PIXELS = 25_000_000
#: Long edge shown to the model; larger images are scaled down to it.
MAX_EDGE = 1568
#: Encoded size shown to the model.
MAX_IMAGE_BYTES = 1_500_000

_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def is_image_path(path: str) -> bool:
    return str(path or "").lower().endswith(IMAGE_SUFFIXES)


def sniff(data: bytes) -> str | None:
    """The image type the bytes ARE, whatever the file is called."""
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


@dataclass(frozen=True)
class ToolImage:
    """A bounded image plus the one line of text that accompanies it."""

    text: str
    mime_type: str
    data: bytes
    width: int
    height: int

    @property
    def base64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")

    def content_blocks(self) -> list[Any]:
        """The MCP content of a tool result: the line, then the image."""
        from mcp.types import ImageContent, TextContent

        return [TextContent(type="text", text=self.text),
                ImageContent(type="image", data=self.base64, mimeType=self.mime_type)]

    def tool_result(self) -> Any:
        """A FastMCP ``ToolResult``; the tool must be registered without an
        output schema, or the client reports an image result as an error."""
        from fastmcp.tools.base import ToolResult

        return ToolResult(content=self.content_blocks())


def bound_image(data: bytes, path: str = "") -> ToolImage | str:
    """``data`` as a :class:`ToolImage` the model can take, or a refusal line."""
    name = path or "image"
    if len(data) > MAX_IMAGE_SOURCE_BYTES:
        return f"error: {name} is over {MAX_IMAGE_SOURCE_BYTES} bytes; too large to show"
    mime = sniff(data)
    if mime is None:
        return (f"error: {name} is not a PNG, JPEG, GIF or WebP image "
                "(its bytes say otherwise); read it with bash if it is something else")
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow is a core dependency
        return f"error: {name} cannot be shown: no image library on this host"
    try:
        with Image.open(io.BytesIO(data)) as probe:
            width, height = probe.size
            if width * height > MAX_SOURCE_PIXELS:
                return (f"error: {name} is {width}x{height} pixels, over the "
                        f"{MAX_SOURCE_PIXELS} pixel bound; scale it down first")
            animated = bool(getattr(probe, "is_animated", False))
            if (max(width, height) <= MAX_EDGE and len(data) <= MAX_IMAGE_BYTES
                    and not animated):
                probe.verify()
                return ToolImage(f"{name}: {width}x{height} {mime}", mime, data,
                                 width, height)
        with Image.open(io.BytesIO(data)) as image:
            image.seek(0)
            frame = image.convert("RGBA" if _has_alpha(image) else "RGB")
    except Image.DecompressionBombError:
        # Pillow's own guard fires inside open() for an absurd declared canvas.
        return (f"error: {name} declares more pixels than the {MAX_SOURCE_PIXELS} "
                "pixel bound; scale it down first")
    except (OSError, ValueError) as exc:
        return f"error: {name} could not be decoded as {mime}: {exc}"
    scale = min(1.0, MAX_EDGE / max(width, height))
    if scale < 1.0:
        frame = frame.resize((max(1, round(width * scale)), max(1, round(height * scale))),
                             Image.LANCZOS)
    encoded, out_mime = _encode(frame)
    shown_w, shown_h = frame.size
    note = (f"{name}: {width}x{height} {mime}, shown as {shown_w}x{shown_h} {out_mime}"
            + (" (first frame)" if animated else ""))
    if len(encoded) > MAX_IMAGE_BYTES:
        return f"error: {name} is still over {MAX_IMAGE_BYTES} bytes after scaling"
    return ToolImage(note, out_mime, encoded, shown_w, shown_h)


def _has_alpha(image: Any) -> bool:
    return image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info


def _encode(frame: Any) -> tuple[bytes, str]:
    if frame.mode == "RGBA":
        buffer = io.BytesIO()
        frame.save(buffer, "PNG", optimize=True)
        if buffer.tell() <= MAX_IMAGE_BYTES:
            return buffer.getvalue(), "image/png"
        frame = frame.convert("RGB")
    for quality in (85, 70, 50):
        buffer = io.BytesIO()
        frame.save(buffer, "JPEG", quality=quality)
        if buffer.tell() <= MAX_IMAGE_BYTES:
            break
    return buffer.getvalue(), "image/jpeg"


__all__ = [
    "IMAGE_SUFFIXES",
    "MAX_EDGE",
    "MAX_IMAGE_BYTES",
    "MAX_IMAGE_SOURCE_BYTES",
    "MAX_SOURCE_PIXELS",
    "ToolImage",
    "bound_image",
    "is_image_path",
    "sniff",
]
