"""Request-owned answer telemetry, never routing authority or shared state."""

from dataclasses import dataclass, field

from tinyassets.providers.base import ProviderResponse


def _label(value: object, maximum: int) -> str:
    if not isinstance(value, str) or not 0 < len(value) <= maximum or not value.isprintable():
        return ""
    return value.strip()


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    """Hashable historical observation; never model choice or access authority."""

    provider: str
    model: str
    model_status: str


def normalize_execution_receipt(value: object) -> dict[str, str] | None:
    """Return only consistent, bounded labels, without retaining caller objects."""
    if isinstance(value, ExecutionReceipt):
        value = {"provider": value.provider, "model": value.model,
                 "model_status": value.model_status}
    if not isinstance(value, dict) or set(value) != {"provider", "model", "model_status"}:
        return None
    provider, model, status = value["provider"], value["model"], value["model_status"]
    if not isinstance(provider, str) or not provider or _label(provider, 400) != provider:
        return None
    if not isinstance(model, str) or (model and _label(model, 200) != model):
        return None
    if status != ("reported" if model else "unknown"):
        return None
    return {"provider": provider, "model": model, "model_status": status}


@dataclass(slots=True)
class WriterExecutionReceipt:
    """Create once per reply; pass observe ONLY to that reply's writer call.

    The collector keeps the first completed response, not a last-call slot that
    learning or other requests could overwrite. It holds only safe labels, never
    prompts, response text, credentials, tool output or mutable provider objects.
    """

    _receipt: tuple[str, str] | None = field(default=None, init=False)

    def observe(self, response: ProviderResponse) -> None:
        if self._receipt is not None or not isinstance(response, ProviderResponse):
            return
        provider = _label(response.provider, 400)
        if not provider or response.degraded or response.failure_class is not None:
            return
        self._receipt = (provider, _label(response.reported_model, 200))

    def projection(self) -> dict[str, str] | None:
        if self._receipt is None:
            return None
        provider, model = self._receipt
        return {
            "provider": provider,
            "model": model,
            "model_status": "reported" if model else "unknown",
        }
