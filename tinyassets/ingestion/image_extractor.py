"""Image extractor -- Pillow resize + Ollama multimodal description.

Handles: .png, .jpg, .jpeg, .webp, .gif, .bmp, .tiff, .svg

Pipeline:
1. Resize image to max 1024px long edge via Pillow
2. Send to Ollama multimodal endpoint for text description
3. Description feeds into synthesis pipeline

Graceful fallback: if Pillow or Ollama vision is unavailable,
creates a placeholder description from image metadata.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# Max long edge for images sent to vision models.
MAX_IMAGE_DIMENSION = 1024

# Ollama endpoint for multimodal generation.
_OLLAMA_URL = "http://localhost:11434"

# Vision models to try, in preference order.
_VISION_MODELS = ["llava", "llava:13b", "bakllava", "llava-phi3"]


def extract_image_description(
    filename: str,
    data: bytes,
    *,
    premise: str = "",
) -> str:
    """Extract a text description from an image.

    Parameters
    ----------
    filename : str
        Image filename.
    data : bytes
        Raw image bytes.
    premise : str
        Story premise for context in the vision prompt.

    Returns
    -------
    str
        Text description of the image (500-1000 words target),
        or a placeholder if vision is unavailable.
    """
    # Step 1: Resize image
    resized_data = _resize_image(data)
    if resized_data is None:
        resized_data = data  # Use original if Pillow unavailable

    # Step 2: Try Ollama vision
    description = _ollama_vision(resized_data, filename, premise)
    if description:
        return description

    # Step 3: Fallback to metadata-based placeholder
    return _placeholder_description(filename, data)


def _resize_image(data: bytes) -> bytes | None:
    """Resize image to fit within MAX_IMAGE_DIMENSION, preserving aspect ratio.

    Returns resized PNG bytes, or None if Pillow is unavailable.
    """
    try:
        from PIL import Image
    except ImportError:
        logger.debug("Pillow not installed; skipping image resize")
        return None

    try:
        img = Image.open(io.BytesIO(data))

        # Skip resize if already small enough
        w, h = img.size
        if max(w, h) <= MAX_IMAGE_DIMENSION:
            # Re-encode as PNG for consistent format
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

        # Calculate new dimensions
        if w >= h:
            new_w = MAX_IMAGE_DIMENSION
            new_h = int(h * (MAX_IMAGE_DIMENSION / w))
        else:
            new_h = MAX_IMAGE_DIMENSION
            new_w = int(w * (MAX_IMAGE_DIMENSION / h))

        img = img.resize((new_w, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        logger.debug(
            "Resized image from %dx%d to %dx%d", w, h, new_w, new_h,
        )
        return buf.getvalue()
    except Exception as e:
        logger.warning("Image resize failed: %s", e)
        return None


def _ollama_vision(
    image_data: bytes,
    filename: str,
    premise: str = "",
) -> str:
    """Send image to Ollama multimodal endpoint for description.

    Returns the description text, or empty string if unavailable.
    """
    model = _find_vision_model()
    if not model:
        logger.info("No Ollama vision model available; using placeholder")
        return ""

    # Encode image as base64
    b64_image = base64.b64encode(image_data).decode("ascii")

    premise_context = (
        f" The image is related to this story: {premise}" if premise else ""
    )

    prompt = (
        f"Describe this image in detail for a fantasy worldbuilding reference. "
        f"Focus on: characters (appearance, clothing, posture, expression), "
        f"locations (architecture, landscape, atmosphere, lighting), "
        f"objects (weapons, artifacts, symbols), and mood/tone.{premise_context}\n\n"
        f"Write a thorough description of 500-1000 words. "
        f"Be specific about visual details that a fiction author would need."
    )

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [b64_image],
        "stream": False,
        "options": {"temperature": 0.3},
    }

    try:
        req = urllib.request.Request(
            f"{_OLLAMA_URL}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            text = result.get("response", "")
            if text.strip():
                logger.info(
                    "Ollama vision described %s: %d chars (%s)",
                    filename, len(text), model,
                )
                return text.strip()
    except urllib.error.URLError as e:
        logger.info("Ollama not reachable for vision: %s", e)
    except Exception as e:
        logger.warning("Ollama vision failed for %s: %s", filename, e)

    return ""


def _find_vision_model() -> str:
    """Find an available Ollama vision model.

    Checks the list of installed models against known vision-capable models.
    Returns the model name, or empty string if none found.
    """
    try:
        req = urllib.request.Request(f"{_OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            installed = {
                m.get("name", "").split(":")[0]
                for m in data.get("models", [])
            }
            # Also check full names with tags
            installed_full = {m.get("name", "") for m in data.get("models", [])}

            for candidate in _VISION_MODELS:
                base = candidate.split(":")[0]
                if candidate in installed_full or base in installed:
                    return candidate

            # Check if any installed model has "llava" or "vision" in name
            for name in installed_full:
                if "llava" in name or "vision" in name:
                    return name
    except (urllib.error.URLError, Exception):
        logger.debug("Cannot query Ollama models")

    return ""


def _placeholder_description(filename: str, data: bytes) -> str:
    """Generate a placeholder description from image metadata.

    Used when no vision model is available.
    """
    info_parts = [f"Image file: {filename}"]
    info_parts.append(f"Size: {len(data):,} bytes")

    # Try to get dimensions from Pillow
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        w, h = img.size
        info_parts.append(f"Dimensions: {w}x{h}")
        info_parts.append(f"Format: {img.format or 'unknown'}")
        if img.mode:
            info_parts.append(f"Color mode: {img.mode}")
    except Exception:
        ext = Path(filename).suffix.lower()
        info_parts.append(f"Format: {ext}")

    return (
        f"[Image awaiting visual analysis]\n\n"
        f"{chr(10).join(info_parts)}\n\n"
        f"This image has been stored in canon/sources/ but could not be "
        f"analyzed because no vision model is available. When a vision-capable "
        f"model (e.g., llava) is installed via Ollama, this image will be "
        f"re-analyzed to extract worldbuilding details."
    )
