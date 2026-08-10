"""Self-hosted engine provider -- a user-provided OpenAI-compatible endpoint.

Slice 3a of the ``wire-user-provided-engine-runtimes`` change. When a universe's
config sets ``engine_source=self_hosted_endpoint`` with a non-empty
``engine_endpoint``, the router binds THIS provider to that endpoint and routes
the universe's writer/judge calls to it -- never the platform fallback chain,
never a platform credential. This enforces the founder invariant: *a universe
runs only on something the user provided or authorized.*

The endpoint is an OpenAI-compatible chat-completions server -- the shape served
by vLLM, LM Studio, llama.cpp's server, LiteLLM, Ollama's ``/v1`` bridge, or a
self-hosted OpenAI-compatible gateway. No external dependency beyond stdlib
``urllib``: the endpoint is the user's own compute, so this provider holds NO
API key of its own (modelled on :class:`~tinyassets.providers.ollama_provider.
OllamaProvider`'s dependency-free HTTP client).

Fail-loud contract: an unreachable endpoint raises
:class:`~tinyassets.exceptions.ProviderUnavailableError`; any other bad response
raises :class:`~tinyassets.exceptions.ProviderError`. The router's engine-source
hook translates either into a hard, no-fallback failure so a self-hosted
universe can never silently execute on a platform provider.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from tinyassets.exceptions import ProviderError, ProviderUnavailableError
from tinyassets.providers.base import BaseProvider, ModelConfig, ProviderResponse

# Slice 3a carries no dedicated self-hosted model config field (the proposal's
# Impact keeps config.py as-is). OpenAI-compatible single-model servers (vLLM,
# LM Studio, llama.cpp) require a non-empty ``model`` field but usually ignore
# its value / serve one loaded model. The founder can pin an exact name for
# their daemon via TINYASSETS_SELF_HOSTED_MODEL when their gateway routes by it.
_DEFAULT_MODEL_ENV = "TINYASSETS_SELF_HOSTED_MODEL"
_DEFAULT_MODEL = "local-model"
_DEFAULT_MAX_TOKENS = 4096


class SelfHostedProvider(BaseProvider):
    """Calls a user-provided OpenAI-compatible chat-completions endpoint.

    Constructed per call by the router's engine-source hook, bound to the
    universe's ``engine_endpoint``; it is intentionally NOT registered in the
    fallback chains (the endpoint is per-universe, so no shared instance can
    hold it).
    """

    name = "self-hosted"
    family = "self-hosted"

    def __init__(self, endpoint: str, model: str = "") -> None:
        endpoint = (endpoint or "").strip()
        if not endpoint:
            # Defensive: the router hook already fails closed on an empty
            # endpoint before constructing this. Never let a blank endpoint
            # produce a silently-malformed request URL.
            raise ProviderUnavailableError(
                "self-hosted engine endpoint is empty; refusing to build a "
                "malformed request URL (fail closed)."
            )
        self._endpoint = endpoint
        self._url = self._chat_completions_url(endpoint)
        self._model = (
            model.strip()
            or os.environ.get(_DEFAULT_MODEL_ENV, "").strip()
            or _DEFAULT_MODEL
        )

    @staticmethod
    def _chat_completions_url(endpoint: str) -> str:
        """Resolve the chat-completions URL from a user-typed base endpoint.

        The endpoint is stored verbatim from ``set_engine`` (a base URL such as
        ``https://host/v1``, or a full ``.../chat/completions`` URL). Append the
        OpenAI chat-completions path only when it is not already present so both
        shapes work.
        """
        trimmed = endpoint.rstrip("/")
        if trimmed.endswith("/chat/completions"):
            return trimmed
        return f"{trimmed}/chat/completions"

    async def complete(
        self,
        prompt: str,
        system: str,
        config: ModelConfig,
        *,
        universe_dir: Path | None = None,
    ) -> ProviderResponse:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, object] = {
            "model": self._model,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens or _DEFAULT_MAX_TOKENS,
            "stream": False,
        }

        start = time.monotonic()
        try:
            req = urllib.request.Request(
                self._url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=config.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # A 4xx/5xx from the user's endpoint is an unavailability signal,
            # not a platform fault -- surface it loudly; the router fails closed.
            raise ProviderUnavailableError(
                f"self-hosted endpoint {self._url} returned HTTP {exc.code}: "
                f"{exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ProviderUnavailableError(
                f"self-hosted endpoint unreachable at {self._url}: {exc.reason}"
            ) from exc
        except (TimeoutError, OSError) as exc:
            raise ProviderUnavailableError(
                f"self-hosted endpoint unreachable at {self._url}: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - fail loud on any bad body
            raise ProviderError(
                f"self-hosted endpoint call failed for {self._url}: {exc}"
            ) from exc

        elapsed_ms = (time.monotonic() - start) * 1000
        text = self._extract_text(body)
        return ProviderResponse(
            text=text,
            provider=self.name,
            model=self._model,
            family=self.family,
            latency_ms=elapsed_ms,
        )

    @staticmethod
    def _extract_text(body: object) -> str:
        """Pull ``choices[0].message.content`` from an OpenAI-compatible body.

        Raises :class:`ProviderError` on a shape that is not a valid
        chat-completions response so a malformed endpoint fails loud rather than
        returning empty prose that looks real (Hard Rule #8).
        """
        if not isinstance(body, dict):
            raise ProviderError(
                f"self-hosted endpoint returned a non-object body: {type(body).__name__}"
            )
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderError(
                "self-hosted endpoint response has no 'choices' array "
                f"(keys: {sorted(body)})"
            )
        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise ProviderError(
                "self-hosted endpoint response 'choices[0].message.content' is "
                f"not a string (got {type(content).__name__})"
            )
        return content
