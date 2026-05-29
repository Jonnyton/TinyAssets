"""Gemini provider -- ``google-genai`` SDK (free tier).

10 RPM, 250 RPD on the free tier.  Used primarily as a judge to
provide a different model family from Claude and GPT.

Optional dependency: ``pip install fantasy-author[gemini]``.
"""

from __future__ import annotations

import asyncio
import os
import time

from workflow.exceptions import ProviderError, ProviderUnavailableError
from workflow.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    require_api_key_provider_opt_in,
)


class GeminiProvider(BaseProvider):
    """Calls Gemini via the ``google-genai`` SDK (free tier)."""

    name = "gemini-free"
    family = "google"

    def __init__(self) -> None:
        require_api_key_provider_opt_in(self.name)

        try:
            from google import genai  # noqa: F401
        except ImportError:
            raise ProviderUnavailableError(
                "google-genai not installed. "
                "Install with: pip install fantasy-author[gemini]"
            )

        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ProviderUnavailableError("GEMINI_API_KEY not set")

        self._client = genai.Client(api_key=api_key)
        self._model = "gemini-2.5-flash"

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
    ) -> ProviderResponse:
        from google.genai import types

        start = time.monotonic()

        try:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system or None,
                    temperature=config.temperature,
                    max_output_tokens=config.max_tokens,
                ),
            )
        except Exception as exc:
            msg = str(exc).lower()
            if "quota" in msg or "rate" in msg or "429" in msg:
                raise ProviderUnavailableError(
                    f"Gemini rate-limited: {exc}"
                ) from exc
            raise ProviderError(f"Gemini call failed: {exc}") from exc

        elapsed_ms = (time.monotonic() - start) * 1000
        text = response.text or ""

        return ProviderResponse(
            text=text,
            provider=self.name,
            model=self._model,
            family=self.family,
            latency_ms=elapsed_ms,
        )
