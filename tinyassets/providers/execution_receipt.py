"""Request-owned answer telemetry, never routing authority or shared state."""

from dataclasses import dataclass, field

from tinyassets.providers.base import ProviderResponse


def _label(value: object, maximum: int) -> str:
    if not isinstance(value, str) or not 0 < len(value) <= maximum or not value.isprintable():
        return ""
    return value.strip()


#: The three fields every receipt has carried. ``provider_display`` is optional
#: and ABSENT when nothing resolved, so a row stored before it existed still
#: normalizes and an unresolved source renders no blank label.
_REQUIRED_FIELDS = {"provider", "model", "model_status"}


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    """Hashable historical observation; never model choice or access authority."""

    provider: str
    model: str
    model_status: str
    provider_display: str = ""


def normalize_execution_receipt(value: object) -> dict[str, str] | None:
    """Return only consistent, bounded labels, without retaining caller objects."""
    if isinstance(value, ExecutionReceipt):
        value = {"provider": value.provider, "model": value.model,
                 "model_status": value.model_status,
                 **({"provider_display": value.provider_display}
                    if value.provider_display else {})}
    if not isinstance(value, dict) or not _REQUIRED_FIELDS <= set(value):
        return None
    if set(value) - _REQUIRED_FIELDS - {"provider_display"}:
        return None
    provider, model, status = value["provider"], value["model"], value["model_status"]
    if not isinstance(provider, str) or not provider or _label(provider, 400) != provider:
        return None
    if not isinstance(model, str) or (model and _label(model, 200) != model):
        return None
    if status != ("reported" if model else "unknown"):
        return None
    out = {"provider": provider, "model": model, "model_status": status}
    if "provider_display" in value:
        display = value["provider_display"]
        # An empty or malformed label is a REFUSAL, not a blank: the caller is
        # claiming a display name it does not have, and the renderer must fall
        # back to `provider` rather than print nothing beside "Answered by".
        if not isinstance(display, str) or not display or _label(display, 200) != display:
            return None
        out["provider_display"] = display
    return out


@dataclass(slots=True)
class WriterExecutionReceipt:
    """Create once per reply; pass observe ONLY to that reply's writer call.

    The collector keeps the first completed response, not a last-call slot that
    learning or other requests could overwrite. It holds only safe labels, never
    prompts, response text, credentials, tool output or mutable provider objects.
    """

    _receipt: tuple[str, str, str] | None = field(default=None, init=False)

    def observe(self, response: ProviderResponse) -> None:
        if self._receipt is not None or not isinstance(response, ProviderResponse):
            return
        provider = _label(response.provider, 400)
        if not provider or response.degraded or response.failure_class is not None:
            return
        self._receipt = (
            provider,
            _label(response.reported_model, 200),
            # The owner's own name for the source, when the router resolved one.
            _label(getattr(response, "provider_display", ""), 200),
        )

    def projection(self) -> dict[str, str] | None:
        if self._receipt is None:
            return None
        provider, model, display = self._receipt
        return {
            "provider": provider,
            "model": model,
            "model_status": "reported" if model else "unknown",
            **({"provider_display": display} if display else {}),
        }
