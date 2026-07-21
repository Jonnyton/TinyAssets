"""Groq provider -- ``groq`` SDK (free tier).

14,400 RPD on the free tier.  Runs Meta Llama models, providing yet
another model family for judge diversity.

Optional dependency: ``pip install fantasy-author[groq]``.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from tinyassets.exceptions import ProviderError, ProviderUnavailableError
from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    require_api_key_provider_opt_in,
)


class GroqProvider(BaseProvider):
    """Calls Groq API via the ``groq`` SDK (free tier)."""

    name = "groq-free"
    family = "meta"
    # Inherently tool-less HTTP text-generation — SAFE for a closed-surface node
    # (Codex S3 REJECT r3 C3).
    enforces_closed_tool_surface = True

    def __init__(self) -> None:
        require_api_key_provider_opt_in(self.name)

        try:
            import groq  # noqa: F401
        except ImportError:
            raise ProviderUnavailableError(
                "groq not installed. "
                "Install with: pip install fantasy-author[groq]"
            )

        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            raise ProviderUnavailableError("GROQ_API_KEY not set")

        self._client = groq.Groq(api_key=api_key)
        self._model = "llama-3.3-70b-versatile"

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        start = time.monotonic()

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens or 4096,
            )
        except Exception as exc:
            msg = str(exc).lower()
            if "rate" in msg or "429" in msg or "quota" in msg:
                raise ProviderUnavailableError(
                    f"Groq rate-limited: {exc}"
                ) from exc
            raise ProviderError(f"Groq call failed: {exc}") from exc

        elapsed_ms = (time.monotonic() - start) * 1000
        text = response.choices[0].message.content or ""

        return ProviderResponse(
            text=text,
            provider=self.name,
            model=self._model,
            family=self.family,
            latency_ms=elapsed_ms,
        )
