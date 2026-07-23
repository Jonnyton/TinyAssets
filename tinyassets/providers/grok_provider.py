"""Grok provider -- xAI API (OpenAI-compatible).

Uses grok-4.1-fast ($0.20/M tokens, covered by free credits).
Provides an additional model family for judge diversity.

Uses the ``openai`` SDK pointed at api.x.ai/v1.
Optional dependency: ``pip install openai``.
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


class GrokProvider(BaseProvider):
    """Calls xAI Grok API via the ``openai`` SDK (OpenAI-compatible)."""

    name = "grok-free"
    family = "xai"
    # Inherently tool-less HTTP text-generation — SAFE for a closed-surface node
    # (Codex S3 REJECT r3 C3).
    enforces_closed_tool_surface = True

    def __init__(self) -> None:
        require_api_key_provider_opt_in(self.name)

        try:
            import openai  # noqa: F401
        except ImportError:
            raise ProviderUnavailableError(
                "openai not installed. "
                "Install with: pip install openai"
            )

        api_key = os.environ.get("XAI_API_KEY", "")
        if not api_key:
            raise ProviderUnavailableError("XAI_API_KEY not set")

        self._client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1",
        )
        self._model = "grok-4.1-fast"

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
            if "rate" in msg or "429" in msg or "quota" in msg or "limit" in msg:
                raise ProviderUnavailableError(
                    f"Grok rate-limited: {exc}"
                ) from exc
            raise ProviderError(f"Grok call failed: {exc}") from exc

        elapsed_ms = (time.monotonic() - start) * 1000
        text = response.choices[0].message.content or ""

        return ProviderResponse(
            text=text,
            provider=self.name,
            model=self._model,
            family=self.family,
            latency_ms=elapsed_ms,
        )
