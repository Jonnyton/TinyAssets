"""Ollama provider -- HTTP to ``localhost:11434``.

Always local, always free, unlimited rate.  Used as the ultimate
fallback for every role and as the default for embeddings and
extraction (local-first for speed).

No external dependencies beyond the stdlib ``urllib``.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from tinyassets.exceptions import ProviderError, ProviderUnavailableError
from tinyassets.providers.base import BaseProvider, ModelConfig, ProviderResponse

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_TEXT_MODEL = "qwen3.5-nothink:latest"
_DEFAULT_EMBED_MODEL = "nomic-embed-text"


class OllamaProvider(BaseProvider):
    """Calls a local Ollama server over HTTP."""

    name = "ollama-local"
    family = "local"

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        text_model: str = _DEFAULT_TEXT_MODEL,
        embed_model: str = _DEFAULT_EMBED_MODEL,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._text_model = text_model
        self._embed_model = embed_model

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
    ) -> ProviderResponse:
        payload = {
            "model": self._text_model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {
                "temperature": config.temperature,
            },
        }
        if system:
            payload["system"] = system
        if config.max_tokens is not None:
            payload["options"]["num_predict"] = config.max_tokens

        start = time.monotonic()
        import logging as _log
        _logger = _log.getLogger("tinyassets.providers.ollama")
        _logger.info("Ollama call starting: model=%s prompt_len=%d system_len=%d",
                      self._text_model, len(prompt), len(system))

        try:
            req = urllib.request.Request(
                f"{self._base_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=config.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ProviderUnavailableError(
                f"Ollama unreachable at {self._base_url}: {exc}"
            ) from exc
        except Exception as exc:
            raise ProviderError(f"Ollama call failed: {exc}") from exc

        elapsed_ms = (time.monotonic() - start) * 1000
        text = body.get("response", "")
        _logger.info("Ollama response: %.1fs, %d chars", elapsed_ms / 1000, len(text))

        return ProviderResponse(
            text=text,
            provider=self.name,
            model=self._text_model,
            family=self.family,
            latency_ms=elapsed_ms,
        )

    async def embed(self, text: str) -> list[float]:
        """Generate embeddings using the local embedding model.

        Tries the modern ``/api/embed`` endpoint first; falls back to the
        legacy ``/api/embeddings`` if the server returns 404 (older Ollama).
        """
        # Modern endpoint (batching, float32, L2-normalized)
        payload = {
            "model": self._embed_model,
            "input": text,
        }
        try:
            return self._embed_request("/api/embed", payload, key="embeddings")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise ProviderUnavailableError(
                    f"Ollama embed HTTP {exc.code}: {exc}"
                ) from exc
        except urllib.error.URLError as exc:
            raise ProviderUnavailableError(
                f"Ollama unreachable for embedding: {exc}"
            ) from exc

        # Legacy fallback (single prompt, float64)
        legacy_payload = {
            "model": self._embed_model,
            "prompt": text,
        }
        try:
            return self._embed_request(
                "/api/embeddings", legacy_payload, key="embedding",
            )
        except urllib.error.URLError as exc:
            raise ProviderUnavailableError(
                f"Ollama unreachable for embedding (legacy): {exc}"
            ) from exc
        except Exception as exc:
            raise ProviderError(f"Ollama embed failed: {exc}") from exc

    def _embed_request(
        self, path: str, payload: dict, *, key: str
    ) -> list[float]:
        """Send an embedding request and extract the vector."""
        req = urllib.request.Request(
            f"{self._base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        result = body.get(key, [[]])
        if isinstance(result, list) and result:
            # /api/embed returns [[...]], /api/embeddings returns [...]
            first = result[0]
            return first if isinstance(first, list) else result
        return []
