"""Request-owned answer telemetry, never routing authority or shared state."""

from dataclasses import dataclass, field

from tinyassets.providers.base import ProviderResponse


def _label(value: object, maximum: int) -> str:
    if not isinstance(value, str) or not 0 < len(value) <= maximum or not value.isprintable():
        return ""
    return value.strip()


#: The three fields every receipt has carried. ``provider_display`` and
#: ``requested_model`` are optional and ABSENT when nothing resolved, so a row
#: stored before they existed still normalizes and renders no blank label.
_REQUIRED_FIELDS = {"provider", "model", "model_status"}
_OPTIONAL_FIELDS = ("provider_display", "requested_model")


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    """Hashable historical observation; never model choice or access authority."""

    provider: str
    model: str
    model_status: str
    provider_display: str = ""
    requested_model: str = ""


def normalize_execution_receipt(value: object) -> dict[str, str] | None:
    """Return only consistent, bounded labels, without retaining caller objects."""
    if isinstance(value, ExecutionReceipt):
        value = {"provider": value.provider, "model": value.model,
                 "model_status": value.model_status,
                 **{name: getattr(value, name) for name in _OPTIONAL_FIELDS
                    if getattr(value, name)}}
    if not isinstance(value, dict) or not _REQUIRED_FIELDS <= set(value):
        return None
    if set(value) - _REQUIRED_FIELDS - set(_OPTIONAL_FIELDS):
        return None
    provider, model, status = value["provider"], value["model"], value["model_status"]
    if not isinstance(provider, str) or not provider or _label(provider, 400) != provider:
        return None
    if not isinstance(model, str) or (model and _label(model, 200) != model):
        return None
    if status != ("reported" if model else "unknown"):
        return None
    out = {"provider": provider, "model": model, "model_status": status}
    for name in _OPTIONAL_FIELDS:
        if name not in value:
            continue
        label = value[name]
        # An empty or malformed label is a REFUSAL, not a blank: the caller is
        # claiming a display name (or a request) it does not have, and the
        # renderer must fall back rather than print nothing beside its words.
        if not isinstance(label, str) or not label or _label(label, 200) != label:
            return None
        out[name] = label
    return out


@dataclass(slots=True)
class WriterExecutionReceipt:
    """Create once per reply; pass observe ONLY to that reply's writer call.

    The collector keeps the first completed response, not a last-call slot that
    learning or other requests could overwrite. It holds only safe labels, never
    prompts, response text, credentials, tool output or mutable provider objects.
    """

    _receipt: tuple[str, str, str, str] | None = field(default=None, init=False)

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
            # What the call asked for. Kept apart from `model`: a request is not
            # evidence of what answered, so it never turns `unknown` into
            # `reported` (a source that reports nothing still says so).
            _label(getattr(response, "requested_model", ""), 200),
        )

    def projection(self) -> dict[str, str] | None:
        if self._receipt is None:
            return None
        provider, model, display, requested = self._receipt
        return {
            "provider": provider,
            "model": model,
            "model_status": "reported" if model else "unknown",
            **({"provider_display": display} if display else {}),
            **({"requested_model": requested} if requested else {}),
        }
