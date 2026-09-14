"""Native model requests without HTTP-shaped pricing or fabricated telemetry.

These immutable facts are not grants. The serving/work boundary validates the
current accepted member and its owned custody before issuing them to a router.
"""

from dataclasses import dataclass

from tinyassets.provider_assignment_manifest import ModelAccess


def validate_model_id(value):
    if (type(value) is not str or len(value) > 200 or value != value.strip()
            or value and not value.isprintable()):
        raise ValueError("invalid native model identifier")
    return value


@dataclass(frozen=True, slots=True)
class NativeSelection:
    provider: str
    requested_model_id: str
    default_model_id: str = ""
    basis: str = "owner_declared"

    def __post_init__(self):
        if type(self.provider) is not str or not self.provider:
            raise ValueError("invalid native source")
        validate_model_id(self.requested_model_id)
        validate_model_id(self.default_model_id)
        if self.basis != "owner_declared" or not self.requested_model_id:
            raise ValueError("native selection requires an explicit owner declaration")
        if self.default_model_id:
            raise ValueError("owner declaration cannot attest an executor default")

    def to_dict(self):
        return {"kind": "native", "version": 1, "provider": self.provider,
                "requested_model_id": self.requested_model_id,
                "default_model_id": self.default_model_id, "basis": self.basis}

    @classmethod
    def from_dict(cls, value):
        if (type(value) is not dict or set(value) != {
            "kind", "version", "provider", "requested_model_id", "default_model_id", "basis",
        } or value["kind"] != "native" or type(value["version"]) is not int
                or value["version"] != 1):
            raise ValueError("native selection fields do not match schema")
        return cls(value["provider"], value["requested_model_id"],
                   value["default_model_id"], value["basis"])


def accepted_native_selection(provider, model_id, access):
    """Return explicit declared native facts, or None for other/default paths."""
    from tinyassets.provider_serving_binding import _PROVIDER_SERVICE

    if provider not in _PROVIDER_SERVICE or model_id == "":
        return None
    validate_model_id(model_id)
    if (type(access) is not ModelAccess or access.model_scope != "explicit"
            or model_id not in access.model_ids):
        raise PermissionError("native model requires accepted explicit scope or fresh discovery")
    return NativeSelection(provider, model_id)


def native_model_arguments(model_id, flag):
    """Argument vector only; no shell interpolation and no implicit fallback."""
    if model_id is None:
        return []
    validate_model_id(model_id)
    return [flag, model_id] if model_id else []
