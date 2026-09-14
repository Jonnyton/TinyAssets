"""Normalized native metadata. No account authority or provider wire names."""

from dataclasses import dataclass
from datetime import datetime

from tinyassets.providers.native_model_selection import validate_model_id


@dataclass(frozen=True, slots=True)
class NativeModel:
    model_id: str
    input_modalities: frozenset[str]
    hidden: bool = False

    def __post_init__(self):
        if not validate_model_id(self.model_id):
            raise ValueError("native catalogue needs a nonempty model ID")
        if (type(self.input_modalities) is not frozenset
                or any(type(item) is not str or not item or len(item) > 100
                       for item in self.input_modalities)
                or type(self.hidden) is not bool):
            raise ValueError("invalid native model metadata")


@dataclass(frozen=True, slots=True)
class NativeCatalogue:
    models: tuple[NativeModel, ...]
    default_model_id: str | None
    observed_at: datetime

    def __post_init__(self):
        if (type(self.models) is not tuple
                or any(type(model) is not NativeModel for model in self.models)):
            raise ValueError("invalid native catalogue models")
        ids = {model.model_id for model in self.models}
        if len(ids) != len(self.models):
            raise ValueError("duplicate native catalogue model")
        if self.default_model_id is not None and self.default_model_id not in ids:
            raise ValueError("native default must occur in the catalogue")
        if (not isinstance(self.observed_at, datetime)
                or self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None):
            raise ValueError("native catalogue needs an aware observation time")
